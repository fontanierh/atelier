//! Web Push to the operator's phone, only for messages an agent explicitly flags with `board post --notify-operator`
//! (and operator tasks' asks). Subscriptions come from the board's own Home Screen app. Payloads are encrypted end to
//! end (RFC 8291 aes128gcm), so the push service relays them without reading them, and requests are signed with this
//! machine's VAPID key (RFC 8292).
use std::collections::BTreeMap;
use std::io::Write;
use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt};
use std::path::PathBuf;
use std::sync::{LazyLock, Mutex};
use std::time::Duration;

use aes_gcm::aead::{Aead, KeyInit};
use aes_gcm::{Aes128Gcm, Nonce};
use base64::Engine;
use base64::engine::general_purpose::{GeneralPurpose, GeneralPurposeConfig};
use base64::engine::{DecodePaddingMode, general_purpose::URL_SAFE_NO_PAD};
use hkdf::Hkdf;
use p256::ecdsa::signature::Signer;
use p256::ecdsa::{Signature, SigningKey};
use p256::elliptic_curve::sec1::ToEncodedPoint;
use p256::pkcs8::{DecodePrivateKey, EncodePrivateKey, LineEnding};
use p256::{PublicKey, SecretKey};
use rand::RngCore;
use regex::Regex;
use serde_json::{Value, json};
use sha2::Sha256;

use crate::db::{self, Result, bad};
use crate::files;

/// Only the browser vendors' push services: the server never POSTs to an arbitrary URL from a subscription.
const PUSH_HOSTS: &[&str] =
    &["web.push.apple.com", "fcm.googleapis.com", "updates.push.services.mozilla.com", "notify.windows.com"];
static LOCK: Mutex<()> = Mutex::new(());
static MARKUP: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"[*_`#>]+").unwrap());
const LENIENT: GeneralPurpose = GeneralPurpose::new(
    &base64::alphabet::URL_SAFE,
    GeneralPurposeConfig::new().with_decode_padding_mode(DecodePaddingMode::Indifferent),
);

pub fn b64(data: &[u8]) -> String {
    URL_SAFE_NO_PAD.encode(data)
}

pub fn unb64(text: &str) -> Option<Vec<u8>> {
    LENIENT.decode(text).ok()
}

fn folder() -> std::io::Result<PathBuf> {
    let path = db::root().join("board-push");
    std::fs::DirBuilder::new().recursive(true).mode(0o700).create(&path)?;
    Ok(path)
}

/// Write a file only this user can read, replacing the old one in one step.
fn private_file(path: &std::path::Path, data: &[u8]) -> std::io::Result<()> {
    let temporary = path.with_extension("tmp");
    let mut file =
        std::fs::OpenOptions::new().write(true).create(true).truncate(true).mode(0o600).open(&temporary)?;
    file.write_all(data)?;
    drop(file);
    std::fs::rename(temporary, path)
}

/// This machine's signing key, created on first use and kept private to the user.
pub fn vapid_key() -> Result<SecretKey> {
    let path = folder()?.join("vapid.pem");
    let _guard = LOCK.lock().unwrap();
    if !path.exists() {
        let key = SecretKey::random(&mut rand::rngs::OsRng);
        let pem = key.to_pkcs8_pem(LineEnding::LF).map_err(|_| std::io::Error::other("cannot encode the key"))?;
        private_file(&path, pem.as_bytes())?;
    }
    let pem = std::fs::read_to_string(&path)?;
    SecretKey::from_pkcs8_pem(&pem).map_err(|_| std::io::Error::other("the VAPID key cannot be read").into())
}

fn point(key: &PublicKey) -> Vec<u8> {
    key.to_encoded_point(false).as_bytes().to_vec()
}

pub fn public_key() -> Result<String> {
    Ok(b64(&point(&vapid_key()?.public_key())))
}

type Subscriptions = BTreeMap<String, Value>;

pub fn subscriptions() -> Subscriptions {
    let Ok(path) = folder().map(|folder| folder.join("subscriptions.json")) else { return Subscriptions::new() };
    match files::read_json(&path) {
        Some(Value::Object(items)) => items.into_iter().collect(),
        _ => Subscriptions::new(),
    }
}

fn save(items: &Subscriptions) -> Result<()> {
    private_file(&folder()?.join("subscriptions.json"), serde_json::to_string_pretty(items).unwrap().as_bytes())?;
    Ok(())
}

fn allowed_endpoint(endpoint: &str) -> bool {
    let Ok(parts) = url::Url::parse(endpoint) else { return false };
    let host = parts.host_str().unwrap_or("");
    parts.scheme() == "https"
        && parts.username().is_empty()
        && parts.password().is_none()
        && parts.port().is_none_or(|port| port == 443)
        && endpoint.chars().count() <= 2000
        && PUSH_HOSTS.iter().any(|allowed| host == *allowed || host.ends_with(&format!(".{allowed}")))
}

pub fn subscribe(subscription: &Value) -> Result<()> {
    let Value::Object(subscription) = subscription else {
        return bad("A push subscription is required.");
    };
    let endpoint = subscription.get("endpoint").and_then(Value::as_str).unwrap_or("");
    if !allowed_endpoint(endpoint) {
        return bad("This push service is not supported.");
    }
    let keys = subscription.get("keys");
    let text = |name: &str| keys.and_then(|keys| keys.get(name)).and_then(Value::as_str);
    let (Some(p256dh), Some(auth)) = (text("p256dh"), text("auth")) else {
        return bad("The push subscription keys are missing.");
    };
    let (Some(public), Some(secret)) = (unb64(p256dh), unb64(auth)) else {
        return bad("The push subscription keys are missing.");
    };
    if public.len() != 65 || public[0] != 4 || secret.len() != 16 || PublicKey::from_sec1_bytes(&public).is_err() {
        return bad("The push subscription keys are invalid.");
    }
    let _guard = LOCK.lock().unwrap();
    let mut items = subscriptions();
    items.insert(endpoint.to_owned(), json!({"p256dh": p256dh, "auth": auth, "added": db::now()}));
    save(&items)
}

pub fn unsubscribe(endpoint: &str) -> Result<()> {
    let _guard = LOCK.lock().unwrap();
    let mut items = subscriptions();
    if items.remove(endpoint).is_some() {
        save(&items)?;
    }
    Ok(())
}

fn hkdf(salt: &[u8], secret: &[u8], info: &[u8], out: &mut [u8]) {
    Hkdf::<Sha256>::new(Some(salt), secret).expand(info, out).expect("short outputs always expand");
}

/// RFC 8291 aes128gcm: one record, encrypted for the browser's key and authentication secret.
pub fn encrypt(payload: &[u8], p256dh: &str, auth: &str) -> Option<Vec<u8>> {
    let receiver = unb64(p256dh)?;
    let browser = PublicKey::from_sec1_bytes(&receiver).ok()?;
    let server = p256::ecdh::EphemeralSecret::random(&mut rand::rngs::OsRng);
    let sender = point(&server.public_key());
    let shared = server.diffie_hellman(&browser);
    let mut ikm = [0u8; 32];
    let info = [b"WebPush: info\0".as_slice(), &receiver, &sender].concat();
    hkdf(&unb64(auth)?, shared.raw_secret_bytes(), &info, &mut ikm);
    let mut salt = [0u8; 16];
    rand::rngs::OsRng.fill_bytes(&mut salt);
    let (mut key, mut nonce) = ([0u8; 16], [0u8; 12]);
    hkdf(&salt, &ikm, b"Content-Encoding: aes128gcm\0", &mut key);
    hkdf(&salt, &ikm, b"Content-Encoding: nonce\0", &mut nonce);
    let body = Aes128Gcm::new(&key.into()).encrypt(&Nonce::from(nonce), [payload, b"\x02"].concat().as_slice()).ok()?;
    Some([salt.as_slice(), &4096u32.to_be_bytes(), &[sender.len() as u8], &sender, &body].concat())
}

/// The Authorization header: a short-lived ES256 token for this push service, signed by the machine's key.
pub fn vapid(endpoint: &str, subject: &str, key: &SecretKey) -> Option<String> {
    let parts = url::Url::parse(endpoint).ok()?;
    let audience = format!("{}://{}", parts.scheme(), &endpoint[parts.scheme().len() + 3..][..parts.authority().len()]);
    let header = b64(br#"{"typ":"JWT","alg":"ES256"}"#);
    let exp = db::now() as i64 + 12 * 3600;
    let claims = b64(json!({"aud": audience, "exp": exp, "sub": subject}).to_string().as_bytes());
    let signed = format!("{header}.{claims}");
    let signature: Signature = SigningKey::from(key).sign(signed.as_bytes());
    Some(format!("vapid t={signed}.{}, k={}", b64(&signature.to_bytes()), b64(&point(&key.public_key()))))
}

/// A message the Pusher sends, with the operator task it belongs to (its ask, or a note in its thread).
pub struct Due {
    pub id: i64,
    pub sender: String,
    pub topic: String,
    pub body: String,
    pub task: Option<i64>,
}

fn topic_name(topic: &str) -> &str {
    match topic {
        "request" => "Request",
        "handoff" => "Handoff",
        "blocked" => "Blocked",
        "release" => "Release",
        "evidence" => "Evidence",
        "ack" => "Ack",
        "alert" => "Alert",
        other => other,
    }
}

/// What the notification shows, and where tapping it goes: the message's thread, or the Tasks page for an operator
/// task's ask and anything flagged in its thread (an edited ask).
pub fn payload(message: &Due) -> Value {
    let text = MARKUP.replace_all(files::split_attachments(&message.body).0, "");
    let text = text.split_whitespace().collect::<Vec<_>>().join(" ");
    let topic = if message.task.is_some() {
        "Operator task"
    } else if message.topic == "info" {
        ""
    } else {
        topic_name(&message.topic)
    };
    let mut body: String = text.chars().take(240).collect();
    if text.chars().count() > 240 {
        body.push('…');
    }
    if body.is_empty() {
        body = "Sent you files".into();
    }
    json!({
        "title": if topic.is_empty() { message.sender.clone() } else { format!("{} · {topic}", message.sender) },
        "body": body,
        "url": match message.task { Some(task) => format!("/?task={task}"), None => format!("/?m={}", message.id) },
        "tag": format!("board-{}", message.id),
    })
}

/// Where pushes go: the subscription's own endpoint, or (for the tests only) a local stand-in for every push
/// service, named by ATELIER_BOARD_PUSH_RELAY.
fn destination(endpoint: &str) -> String {
    match std::env::var("ATELIER_BOARD_PUSH_RELAY") {
        Ok(relay) if !relay.is_empty() => relay,
        _ => endpoint.to_owned(),
    }
}

/// Push one message to every subscribed device; drop subscriptions the push service says are gone.
pub async fn send(client: &reqwest::Client, message: &Due, subject: &str) -> Result<i64> {
    let data = payload(message).to_string();
    let key = vapid_key()?;
    let mut delivered = 0;
    for (endpoint, item) in subscriptions() {
        let field = |name: &str| item.get(name).and_then(Value::as_str).unwrap_or("").to_owned();
        let (Some(body), Some(authorization)) =
            (encrypt(data.as_bytes(), &field("p256dh"), &field("auth")), vapid(&endpoint, subject, &key))
        else {
            continue;
        };
        let response = client
            .post(destination(&endpoint))
            .timeout(Duration::from_secs(10))
            .header("TTL", "86400")
            .header("Urgency", "high")
            .header("Content-Encoding", "aes128gcm")
            .header("Content-Type", "application/octet-stream")
            .header("Authorization", authorization)
            .header("X-Push-Endpoint", &endpoint)
            .body(body)
            .send()
            .await;
        let Ok(response) = response else { continue };
        let status = response.status().as_u16();
        if status == 404 || status == 410 {
            unsubscribe(&endpoint)?;
        } else if status < 300 {
            delivered += 1;
        }
    }
    Ok(delivered)
}

fn newest() -> Result<i64> {
    Ok(db::read()?.query_row("SELECT coalesce(max(id), 0) FROM messages", [], |r| r.get(0))?)
}

fn due(after: i64, sender: &str) -> Result<Vec<Due>> {
    let db = db::read()?;
    let mut statement = db.prepare(
        "SELECT m.id, m.sender, m.topic, m.body, t.id AS task FROM messages m \
         LEFT JOIN operator_tasks t ON t.message IN (m.id, m.reply_to) \
         WHERE m.id>? AND m.notify=1 AND m.sender!=? ORDER BY m.id LIMIT 20",
    )?;
    let rows = statement.query_map(rusqlite::params![after, sender], |r| {
        Ok(Due { id: r.get(0)?, sender: r.get(1)?, topic: r.get(2)?, body: r.get(3)?, task: r.get(4)? })
    })?;
    Ok(rows.collect::<rusqlite::Result<_>>()?)
}

/// Watches the board for newly flagged messages and pushes each once. It starts after the newest message, so a
/// restart never replays old notifications.
pub async fn pusher(sender: String, subject: String, interval: Duration) {
    let client = reqwest::Client::new();
    let mut after = loop {
        match newest() {
            Ok(id) => break id,
            Err(_) => tokio::time::sleep(interval).await,
        }
    };
    loop {
        let found = {
            let sender = sender.clone();
            tokio::task::spawn_blocking(move || due(after, &sender)).await.unwrap_or_else(|_| Ok(Vec::new()))
        };
        match found {
            Ok(messages) => {
                for message in messages {
                    after = message.id;
                    if !subscriptions().is_empty() {
                        if let Err(error) = send(&client, &message, &subject).await {
                            eprintln!("push: {error:?}");
                        }
                    }
                }
            }
            Err(error) => eprintln!("push: {}", match error {
                db::Error::Db(_) => "database",
                _ => "files",
            }),
        }
        tokio::time::sleep(interval).await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn payload_names_the_topic_and_opens_the_thread_or_task() {
        let message = Due {
            id: 42,
            sender: "hidamari".into(),
            topic: "blocked".into(),
            body: "**Blocked** on your call: ship `v2`?".into(),
            task: None,
        };
        assert_eq!(
            payload(&message),
            json!({"title": "hidamari · Blocked", "body": "Blocked on your call: ship v2?", "url": "/?m=42", "tag": "board-42"})
        );
        let task = Due { task: Some(3), topic: "info".into(), body: String::new(), ..message };
        let shown = payload(&task);
        assert_eq!(shown["title"], "hidamari · Operator task");
        assert_eq!(shown["url"], "/?task=3");
        assert_eq!(shown["body"], "Sent you files");
    }

    #[test]
    fn only_real_push_services() {
        assert!(allowed_endpoint("https://web.push.apple.com/QGuQ"));
        assert!(allowed_endpoint("https://a.notify.windows.com/x"));
        for endpoint in [
            "http://web.push.apple.com/x",
            "https://evil.example/x",
            "https://web.push.apple.com.evil.example/x",
            "https://user@web.push.apple.com/x",
            "https://web.push.apple.com:8443/x",
        ] {
            assert!(!allowed_endpoint(endpoint), "{endpoint}");
        }
    }
}
