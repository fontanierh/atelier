//! The private HTTP boundary: loopback only, reached from the tailnet through `tailscale serve`, which names the
//! person in Tailscale-User-Login. Every POST also needs the board's own origin and its CSRF token.
use std::collections::{HashMap, HashSet};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::{Arc, LazyLock, Mutex};

use axum::body::Body;
use axum::http::{HeaderMap, HeaderValue, Method, Request, StatusCode, header};
use axum::response::Response;
use futures_util::StreamExt;
use regex::Regex;
use serde::Serialize;
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};
use tokio::io::{AsyncReadExt, AsyncSeekExt, AsyncWriteExt};

use crate::api;
use crate::db::{self, Error};
use crate::views::Query;
use crate::{files, inbox, markdown, push, store, views};

const CSP: &str = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; \
                   media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'";
/// The village scene compiles its own wasm, which the classic page's policy rightly forbids.
const WORLD_CSP: &str = "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; \
                         img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; \
                         form-action 'self'";
const REVIEW_CSP: &str = "default-src 'none'; style-src 'unsafe-inline' https://fonts.googleapis.com; \
                          font-src https://fonts.gstatic.com; img-src data:; base-uri 'none'; form-action 'none'; \
                          frame-ancestors 'none'";
const WORLD_TIMING_BYTES: usize = 4096;
const POSTS: &[&str] = &[
    "/api/broadcast", "/api/send", "/api/preview", "/api/upload", "/api/remove", "/api/task/dismiss", "/api/read",
    "/api/world/timing", "/api/push/subscribe", "/api/push/unsubscribe", "/api/push/test",
];

static STATIC: LazyLock<HashMap<&str, (&str, &str)>> = LazyLock::new(|| {
    HashMap::from([
        ("/", ("index.html", "text/html; charset=utf-8")),
        ("/board.css", ("board.css", "text/css; charset=utf-8")),
        ("/board.js", ("board.js", "text/javascript; charset=utf-8")),
        ("/board-fx.js", ("board-fx.js", "text/javascript; charset=utf-8")),
        ("/board-scene.js", ("board-scene.js", "text/javascript; charset=utf-8")),
        ("/icon.svg", ("icon.svg", "image/svg+xml")),
        ("/apple-touch-icon.png", ("apple-touch-icon.png", "image/png")),
        ("/manifest.webmanifest", ("manifest.webmanifest", "application/manifest+json")),
        ("/sw.js", ("sw.js", "text/javascript; charset=utf-8")),
        ("/board-theme.js", ("board-theme.js", "text/javascript; charset=utf-8")),
        ("/meadow-portrait-1.webp", ("meadow-portrait-1.webp", "image/webp")),
        ("/meadow-landscape-2.webp", ("meadow-landscape-2.webp", "image/webp")),
        ("/meadow-night-portrait-1.webp", ("meadow-night-portrait-1.webp", "image/webp")),
        ("/meadow-night-landscape-1.webp", ("meadow-night-landscape-1.webp", "image/webp")),
    ])
});
/// The board village's page is committed beside the classic board; its compiled scene is a local build product.
static WORLD: LazyLock<HashMap<&str, (&str, bool, &str)>> = LazyLock::new(|| {
    HashMap::from([
        ("/world", ("world/index.html", false, "text/html; charset=utf-8")),
        ("/world/", ("world/index.html", false, "text/html; charset=utf-8")),
        ("/world/world.css", ("world/world.css", false, "text/css; charset=utf-8")),
        ("/world/world.js", ("world/world.js", false, "text/javascript; charset=utf-8")),
        ("/world/ui.js", ("world/ui.js", false, "text/javascript; charset=utf-8")),
        ("/world/manifest.webmanifest", ("world/manifest.webmanifest", false, "application/manifest+json")),
        ("/world/board_world.js", ("board_world.js", true, "text/javascript; charset=utf-8")),
        ("/world/board_world_bg.wasm", ("board_world_bg.wasm", true, "application/wasm")),
    ])
});
static REVIEW_NAME: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^[a-z0-9][a-z0-9-]{0,79}$").unwrap());
static RANGE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^bytes=(\d*)-(\d*)$").unwrap());

pub struct Config {
    pub port: u16,
    pub origins: HashSet<String>,
    pub allowed_user: Option<String>,
    pub sender: String,
    pub remote_status: Option<PathBuf>,
    pub assets: PathBuf,
    pub world_build: PathBuf,
    pub push_subject: String,
    pub csrf: String,
}

/// A static file, its ETag and (for text) a gzip copy, reread only when the file changes on disk.
struct Asset {
    stamp: std::time::SystemTime,
    data: Arc<Vec<u8>>,
    tag: String,
    packed: Option<Arc<Vec<u8>>>,
}

static ASSETS: LazyLock<Mutex<HashMap<PathBuf, Arc<Asset>>>> = LazyLock::new(Default::default);

fn asset(path: &Path) -> std::io::Result<Arc<Asset>> {
    let stamp = std::fs::metadata(path)?.modified()?;
    if let Some(cached) = ASSETS.lock().unwrap().get(path) {
        if cached.stamp == stamp {
            return Ok(cached.clone());
        }
    }
    let data = std::fs::read(path)?;
    let image = matches!(path.extension().and_then(|e| e.to_str()), Some("webp" | "png"));
    let packed = (!image).then(|| Arc::new(gzip(&data, if data.len() < 1 << 20 { 9 } else { 6 })));
    let digest = Sha256::digest(&data);
    let tag = format!("\"{}\"", digest.iter().map(|b| format!("{b:02x}")).collect::<String>()[..24].to_owned());
    let item = Arc::new(Asset { stamp, data: Arc::new(data), tag, packed });
    ASSETS.lock().unwrap().insert(path.to_owned(), item.clone());
    Ok(item)
}

fn gzip(data: &[u8], level: u32) -> Vec<u8> {
    let mut encoder = flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::new(level));
    encoder.write_all(data).unwrap();
    encoder.finish().unwrap()
}

fn accepts_gzip(headers: &HeaderMap) -> bool {
    text(headers, "accept-encoding").contains("gzip")
}

fn text<'a>(headers: &'a HeaderMap, name: &str) -> &'a str {
    headers.get(name).and_then(|value| value.to_str().ok()).unwrap_or("")
}

/// The headers every response from the board carries.
fn respond(status: StatusCode, body: Vec<u8>, mime: &str, cache: &str, extra: &[(&str, String)], csp: &str) -> Response {
    let mut response = Response::builder()
        .status(status)
        .header(header::CONTENT_TYPE, mime)
        .header(header::CONTENT_LENGTH, body.len())
        .header(header::CACHE_CONTROL, cache);
    for (name, value) in extra {
        response = response.header(*name, value);
    }
    response
        .header("X-Content-Type-Options", "nosniff")
        .header("Referrer-Policy", "no-referrer")
        .header("Content-Security-Policy", csp)
        .body(Body::from(body))
        .unwrap()
}

/// JSON, gzipped for a browser that takes it: the page polls every few seconds, often over a relayed tailnet link.
fn json_response(status: StatusCode, value: &impl Serialize, headers: &HeaderMap) -> Response {
    let body = serde_json::to_vec(value).unwrap();
    if body.len() > 1024 && accepts_gzip(headers) {
        let extra = [("Content-Encoding", "gzip".to_owned()), ("Vary", "Accept-Encoding".to_owned())];
        return respond(status, gzip(&body, 5), "application/json; charset=utf-8", "no-store", &extra, CSP);
    }
    respond(status, body, "application/json; charset=utf-8", "no-store", &[], CSP)
}

fn problem(status: StatusCode, message: impl Into<String>, headers: &HeaderMap) -> Response {
    json_response(status, &api::Problem { error: message.into() }, headers)
}

/// Fast loads: the versioned paintings cache for a year (a new painting gets a new name); the app's own files
/// revalidate with an ETag, so a reload costs a 304 until they change, and travel gzipped. The page itself is never
/// stored: a Home Screen app launched before the network was up once showed an old board from the browser's cache.
fn static_file(path: &Path, mime: &str, csp: &str, headers: &HeaderMap) -> std::io::Result<Response> {
    let item = asset(path)?;
    let cache = if path.extension().is_some_and(|e| e == "webp") {
        "public, max-age=31536000, immutable"
    } else if mime.starts_with("text/html") {
        "no-store"
    } else {
        "no-cache"
    };
    if text(headers, "if-none-match") == item.tag {
        return Ok(Response::builder()
            .status(StatusCode::NOT_MODIFIED)
            .header(header::ETAG, &item.tag)
            .header(header::CACHE_CONTROL, cache)
            .body(Body::empty())
            .unwrap());
    }
    // The village's loader shows real progress from the size it will have once unpacked.
    let mut extra = vec![
        ("ETag", item.tag.clone()),
        ("Vary", "Accept-Encoding".to_owned()),
        ("X-Uncompressed-Length", item.data.len().to_string()),
    ];
    let mut data = item.data.as_ref().clone();
    if let (Some(packed), true) = (&item.packed, accepts_gzip(headers)) {
        data = packed.as_ref().clone();
        extra.push(("Content-Encoding", "gzip".to_owned()));
    }
    Ok(respond(StatusCode::OK, data, mime, cache, &extra, csp))
}

fn equal(a: &[u8], b: &[u8]) -> bool {
    a.len() == b.len() && a.iter().zip(b).fold(0u8, |diff, (x, y)| diff | (x ^ y)) == 0
}

/// The host is one the board is configured for, and a request through the proxy comes from the allowed person.
fn permitted(config: &Config, headers: &HeaderMap) -> Result<(), Response> {
    let host = text(headers, "host");
    if !config.origins.iter().any(|origin| origin.split_once("://").is_some_and(|(_, netloc)| netloc == host)) {
        return Err(problem(StatusCode::FORBIDDEN, "This host is not configured for the board.", headers));
    }
    let local = host == format!("127.0.0.1:{}", config.port) || host == format!("localhost:{}", config.port);
    if let (Some(user), false) = (&config.allowed_user, local) {
        if text(headers, "tailscale-user-login") != user {
            return Err(problem(StatusCode::FORBIDDEN, "Your Tailscale account does not have access to this board.",
                               headers));
        }
    }
    Ok(())
}

async fn blocking<T: Send + 'static>(work: impl FnOnce() -> db::Result<T> + Send + 'static) -> db::Result<T> {
    tokio::task::spawn_blocking(work).await.unwrap_or_else(|_| Err(Error::Io(std::io::Error::other("worker failed"))))
}

pub async fn handle(config: Arc<Config>, request: Request<Body>) -> Response {
    let headers = request.headers().clone();
    if let Err(refused) = permitted(&config, &headers) {
        return refused;
    }
    match *request.method() {
        Method::GET | Method::HEAD => get(config, request).await,
        Method::POST => post(config, request).await,
        _ => problem(StatusCode::METHOD_NOT_ALLOWED, "Not found.", &headers),
    }
}

async fn get(config: Arc<Config>, request: Request<Body>) -> Response {
    let headers = request.headers().clone();
    let path = request.uri().path().to_owned();
    let query = Query::parse(request.uri().query());
    let result = route(&config, &path, query, &headers).await;
    match result {
        Ok(response) => response,
        Err(Error::Bad(message)) => problem(StatusCode::BAD_REQUEST, message, &headers),
        Err(Error::Missing(_)) => problem(StatusCode::NOT_FOUND, "Not found.", &headers),
        Err(_) => problem(
            StatusCode::SERVICE_UNAVAILABLE,
            "The board is temporarily unavailable. Your draft is preserved; please retry.",
            &headers,
        ),
    }
}

async fn route(config: &Arc<Config>, path: &str, query: Query, headers: &HeaderMap) -> db::Result<Response> {
    if let Some((name, mime)) = STATIC.get(path) {
        return Ok(static_file(&config.assets.join(name), mime, CSP, headers)?);
    }
    if let Some((name, built, mime)) = WORLD.get(path) {
        let file = if *built { config.world_build.join(name) } else { config.assets.join(name) };
        if !file.is_file() {
            return Ok(problem(StatusCode::NOT_FOUND, "The board village is not built on this machine.", headers));
        }
        return Ok(static_file(&file, mime, WORLD_CSP, headers)?);
    }
    let reply = |value: db::Result<Value>| value.map(|value| json_response(StatusCode::OK, &value, headers));
    match path {
        "/api/state" => {
            let config = config.clone();
            let state = blocking(move || {
                views::snapshot(&query, config.remote_status.as_deref(), &config.sender, &config.csrf)
            })
            .await?;
            Ok(json_response(StatusCode::OK, &state, headers))
        }
        "/api/push/key" => reply(blocking(|| Ok(json!({"key": push::public_key()?}))).await),
        "/api/threads" | "/api/activity" => {
            let (config, view) = (config.clone(), path.to_owned());
            reply(
                blocking(move || {
                    let db = db::read()?;
                    if view == "/api/threads" {
                        let limit = query.bounded("limit", 30, 200)?;
                        Ok(serde_json::to_value(inbox::threads(&db, &config.sender, limit)?).unwrap())
                    } else {
                        let limit = query.bounded("limit", 60, 300)?;
                        let unread = query.text("unread") == "1";
                        let found = inbox::activity(&db, &config.sender, query.text("kind"), unread, limit)?;
                        Ok(serde_json::to_value(found).unwrap())
                    }
                })
                .await,
            )
        }
        "/api/thread" => {
            let id = query.number("id", 0)?;
            match blocking(move || views::thread(id)).await {
                Err(Error::Missing(_)) => {
                    Ok(problem(StatusCode::NOT_FOUND, "This conversation is no longer on the board.", headers))
                }
                found => Ok(json_response(StatusCode::OK, &found?, headers)),
            }
        }
        "/healthz" => {
            blocking(|| {
                db::read()?.query_row("SELECT count(*) FROM (SELECT id FROM messages LIMIT 1)", [], |_| Ok(()))?;
                Ok(())
            })
            .await?;
            Ok(json_response(StatusCode::OK, &api::Ok { ok: true }, headers))
        }
        _ if path == "/review" || path.starts_with("/review/") => {
            let name = path.trim_start_matches("/review").trim_matches('/');
            Ok(review(if name.is_empty() { "codebase-review" } else { name }, headers))
        }
        _ if path.starts_with("/api/attachment/") => {
            Ok(send_attachment(path.split('/').nth(3).unwrap_or(""), headers).await)
        }
        _ if path.starts_with("/api/document/") => {
            let id = path.split('/').nth(3).unwrap_or("").to_owned();
            let document = blocking(move || document(&id)).await?;
            Ok(match document {
                Some(document) => json_response(StatusCode::OK, &document, headers),
                None => problem(StatusCode::NOT_FOUND, "This attachment cannot be read here.", headers),
            })
        }
        _ => Ok(problem(StatusCode::NOT_FOUND, "Not found.", headers)),
    }
}

/// A report page (an agents' research write-up) from the board cache, for the same people as the board. Pages are
/// static: no scripts run, and only their own inline styles and Google Fonts load.
fn review(name: &str, headers: &HeaderMap) -> Response {
    let path = db::root().join("reviews").join(format!("{name}.html"));
    match (REVIEW_NAME.is_match(name), std::fs::read(&path)) {
        (true, Ok(page)) => respond(StatusCode::OK, page, "text/html; charset=utf-8", "no-cache", &[], REVIEW_CSP),
        _ => problem(StatusCode::NOT_FOUND, "There is no review by that name.", headers),
    }
}

/// A Markdown or text attachment rendered for the board's reader, so it opens in place instead of downloading.
fn document(id: &str) -> db::Result<Option<api::Document>> {
    let Some(item) = files::attachment(id).filter(files::Item::readable) else { return Ok(None) };
    let text = String::from_utf8_lossy(&std::fs::read(&item.path)?).into_owned();
    let name = item.name.to_lowercase();
    let html = if files::MARKDOWN_SUFFIXES.iter().any(|suffix| name.ends_with(suffix)) {
        markdown::render(&text)
    } else {
        format!("<pre><code>{}</code></pre>", escape(&text))
    };
    Ok(Some(api::Document { url: item.url(), name: item.name, size: item.size, html }))
}

/// Python's html.escape: & < > " and '.
fn escape(text: &str) -> String {
    text.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;").replace('"', "&quot;").replace('\'', "&#x27;")
}

/// An attachment's bytes. Byte ranges let Safari stream and seek videos; only safe media display inline.
async fn send_attachment(id: &str, headers: &HeaderMap) -> Response {
    let id = id.to_owned();
    let Ok(Some(item)) = blocking(move || Ok(files::attachment(&id))).await else {
        return problem(StatusCode::NOT_FOUND, "This attachment is no longer available.", headers);
    };
    let size = item.size;
    let (mut start, mut end, mut status) = (0, size.saturating_sub(1), StatusCode::OK);
    if let Some(range) = RANGE.captures(text(headers, "range").trim()) {
        let (first, last) = (&range[1], &range[2]);
        if !first.is_empty() || !last.is_empty() {
            if !first.is_empty() {
                start = first.parse().unwrap_or(u64::MAX);
                end = if last.is_empty() { size.saturating_sub(1) } else { last.parse().unwrap_or(u64::MAX) }
                    .min(size.saturating_sub(1));
            } else {
                start = size.saturating_sub(last.parse().unwrap_or(u64::MAX));
            }
            if start > end || size == 0 {
                return Response::builder()
                    .status(StatusCode::RANGE_NOT_SATISFIABLE)
                    .header("Content-Range", format!("bytes */{size}"))
                    .header(header::CONTENT_LENGTH, 0)
                    .body(Body::empty())
                    .unwrap();
            }
            status = StatusCode::PARTIAL_CONTENT;
        }
    }
    let Ok(mut file) = tokio::fs::File::open(&item.path).await else {
        return problem(StatusCode::NOT_FOUND, "This attachment is no longer available.", headers);
    };
    let length = if size == 0 { 0 } else { end - start + 1 };
    if file.seek(std::io::SeekFrom::Start(start)).await.is_err() {
        return problem(StatusCode::SERVICE_UNAVAILABLE, "The board is temporarily unavailable.", headers);
    }
    let inline = item.inline();
    let disposition = format!(
        "{}; filename*=UTF-8''{}",
        if inline { "inline" } else { "attachment" },
        files::quote(&item.name)
    );
    let mut response = Response::builder()
        .status(status)
        .header(header::CONTENT_TYPE, if inline { item.mime.as_str() } else { "application/octet-stream" })
        .header(header::CONTENT_LENGTH, length)
        .header(header::ACCEPT_RANGES, "bytes");
    if status == StatusCode::PARTIAL_CONTENT {
        response = response.header("Content-Range", format!("bytes {start}-{end}/{size}"));
    }
    response
        .header(header::CONTENT_DISPOSITION, HeaderValue::from_str(&disposition).unwrap())
        .header(header::CACHE_CONTROL, "private, max-age=86400")
        .header("X-Content-Type-Options", "nosniff")
        .header("Referrer-Policy", "no-referrer")
        .header("Content-Security-Policy", "sandbox; default-src 'none'; img-src 'self'; media-src 'self'")
        .body(Body::from_stream(tokio_util::io::ReaderStream::new(file.take(length))))
        .unwrap()
}

async fn post(config: Arc<Config>, request: Request<Body>) -> Response {
    let headers = request.headers().clone();
    let target = request.uri().path_and_query().map_or("", |p| p.as_str()).to_owned();
    if !POSTS.contains(&target.as_str()) {
        return problem(StatusCode::NOT_FOUND, "Not found.", &headers);
    }
    let origin = text(&headers, "origin");
    let same_host = origin.split_once("://").is_some_and(|(_, netloc)| netloc == text(&headers, "host"));
    if !config.origins.contains(origin)
        || !same_host
        || !equal(text(&headers, "x-board-csrf").as_bytes(), config.csrf.as_bytes())
    {
        return problem(StatusCode::FORBIDDEN, "Please refresh the board before sending.", &headers);
    }
    let length: i64 = text(&headers, "content-length").trim().parse().unwrap_or(-1);
    if target == "/api/upload" {
        return upload(request.into_body(), length, &headers).await;
    }
    if text(&headers, "content-type").split(';').next().unwrap_or("").trim() != "application/json" {
        return problem(StatusCode::UNSUPPORTED_MEDIA_TYPE, "A JSON message is required.", &headers);
    }
    if !(1..=40000).contains(&length) {
        return problem(StatusCode::PAYLOAD_TOO_LARGE, "Message is too large.", &headers);
    }
    let result = match axum::body::to_bytes(request.into_body(), length as usize).await {
        Ok(bytes) => match serde_json::from_slice::<Value>(&bytes) {
            Ok(Value::Object(data)) => act(&config, &target, data).await,
            Ok(_) => Err(Error::Bad("A message object is required.".into())),
            Err(error) => Err(Error::Bad(format!("The message is not valid JSON: {error}"))),
        },
        Err(_) => Err(Error::Bad("The message did not arrive whole. Try again.".into())),
    };
    match result {
        Ok(value) => json_response(StatusCode::OK, &value, &headers),
        Err(Error::Bad(message) | Error::Missing(message)) => problem(StatusCode::BAD_REQUEST, message, &headers),
        Err(Error::Db(_)) => problem(
            StatusCode::SERVICE_UNAVAILABLE,
            "The board is busy. Retry to safely finish this same message.",
            &headers,
        ),
        Err(Error::Io(_)) => problem(StatusCode::SERVICE_UNAVAILABLE, "The board could not save that. Try again.", &headers),
    }
}

fn field(data: &Map<String, Value>, name: &str) -> Value {
    data.get(name).cloned().unwrap_or(Value::Null)
}

async fn act(config: &Arc<Config>, target: &str, data: Map<String, Value>) -> db::Result<Value> {
    let value = |item: &dyn erased::Json| item.json();
    match target {
        "/api/world/timing" => {
            // Load and resume timings from the village on real phones, kept for reading back (one JSON per line).
            let mut line = Map::new();
            line.insert("time".into(), json!(db::now()));
            line.extend(data);
            let line = ascii(&Value::Object(line).to_string());
            if line.len() > WORLD_TIMING_BYTES {
                return db::bad("Timing report is too large.");
            }
            blocking(move || {
                let mut log = std::fs::OpenOptions::new()
                    .create(true)
                    .append(true)
                    .open(db::root().join("world-timings.jsonl"))?;
                log.write_all(format!("{line}\n").as_bytes())?;
                Ok(())
            })
            .await?;
            Ok(json!({"ok": true}))
        }
        "/api/preview" => match data.get("body") {
            Some(Value::String(body)) if body.chars().count() <= 8000 => {
                let body = body.clone();
                Ok(value(&api::Preview { html: blocking(move || Ok(markdown::render(&body))).await? }))
            }
            _ => db::bad("Preview needs a message of at most 8000 characters."),
        },
        "/api/push/subscribe" => {
            let subscription = field(&data, "subscription");
            blocking(move || push::subscribe(&subscription)).await?;
            Ok(value(&api::Subscribed { subscribed: true }))
        }
        "/api/push/unsubscribe" => {
            let Some(Value::String(endpoint)) = data.get("endpoint").cloned() else {
                return db::bad("A push endpoint is required.");
            };
            blocking(move || push::unsubscribe(&endpoint)).await?;
            Ok(value(&api::Subscribed { subscribed: false }))
        }
        "/api/push/test" => {
            // A sample notification, so the person can check this device receives them.
            let sample = push::Due {
                id: 0,
                sender: "Atelier board".into(),
                topic: "info".into(),
                body: "Notifications work on this device.".into(),
                task: None,
            };
            let delivered = push::send(&reqwest::Client::new(), &sample, &config.push_subject).await?;
            Ok(value(&api::Delivered { delivered }))
        }
        "/api/task/dismiss" => {
            let Some(task) = store::integer(&field(&data, "id")) else {
                return db::bad("Choose a task to dismiss.");
            };
            let (sender, note) = (config.sender.clone(), field(&data, "note"));
            let closed = blocking(move || store::dismiss_task(task, &sender, &note)).await?;
            Ok(value(&api::Dismissed { dismissed: task, already: !closed }))
        }
        "/api/read" => {
            let follow = match data.get("follow") {
                None | Some(Value::Null) => None,
                Some(Value::Bool(follow)) => Some(*follow),
                Some(_) => return db::bad("follow must be true or false"),
            };
            let sender = config.sender.clone();
            let everything = data.get("all") == Some(&Value::Bool(true));
            let key = blocking(move || {
                inbox::mark_read(&sender, &field(&data, "id"), &field(&data, "through"), everything, follow)
            })
            .await?;
            Ok(value(&api::Read { read: key }))
        }
        "/api/remove" => {
            let Some(Value::String(agent)) = data.get("agent").cloned() else {
                return db::bad("Choose an agent to remove.");
            };
            let name = agent.clone();
            blocking(move || store::remove(&name)).await?;
            Ok(value(&api::Removed { removed: agent }))
        }
        _ => {
            let recipient = if target == "/api/send" { data.get("recipient").cloned().unwrap_or("*".into()) } else { "*".into() };
            let sender = config.sender.clone();
            let rows = blocking(move || {
                let attachments = field(&data, "attachments");
                let body = files::with_attachments(&field(&data, "body"), &attachments)?;
                let topic = data.get("topic").cloned().unwrap_or("request".into());
                store::send_web(&sender, &body, &field(&data, "request_id"), &topic, &recipient,
                                &field(&data, "reply_to"))
            })
            .await?;
            let recipients = rows.iter().map(|row| row.recipient.clone()).collect();
            Ok(value(&api::Sent { messages: rows, recipients }))
        }
    }
}

mod erased {
    pub trait Json {
        fn json(&self) -> serde_json::Value;
    }

    impl<T: serde::Serialize> Json for T {
        fn json(&self) -> serde_json::Value {
            serde_json::to_value(self).unwrap()
        }
    }
}

/// JSON text with every non-ASCII character escaped, as Python's json.dumps writes it.
fn ascii(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for c in text.chars() {
        if c.is_ascii() {
            out.push(c);
        } else {
            let mut units = [0u16; 2];
            for unit in c.encode_utf16(&mut units) {
                out.push_str(&format!("\\u{unit:04x}"));
            }
        }
    }
    out
}

/// Stream one upload to disk; nothing is posted until a message refers to it. A photo's or video's pixel size, when
/// the uploader knows it, lets the board reserve its space before it loads.
async fn upload(body: Body, length: i64, headers: &HeaderMap) -> Response {
    let close = |mut response: Response| {
        response.headers_mut().insert(header::CONNECTION, HeaderValue::from_static("close"));
        response
    };
    let name = text(headers, "x-file-name").to_owned();
    let mime = text(headers, "content-type").split(';').next().unwrap_or("").trim().to_owned();
    let started = blocking(move || files::Upload::start(length.max(0) as u64, &name, &mime)).await;
    let mut stored = match started {
        Ok(stored) => stored,
        Err(Error::Bad(message)) => {
            let status = if message.contains("MB") { StatusCode::PAYLOAD_TOO_LARGE } else { StatusCode::BAD_REQUEST };
            return close(problem(status, message, headers));
        }
        Err(_) => return close(problem(StatusCode::SERVICE_UNAVAILABLE, "The file could not be saved. Try again.", headers)),
    };
    let mut out = tokio::fs::File::from_std(stored.file.take().unwrap());
    let mut remaining = stored.length;
    let mut stream = body.into_data_stream();
    while remaining > 0 {
        let chunk = match stream.next().await {
            Some(Ok(chunk)) => chunk,
            _ => return close(problem(StatusCode::BAD_REQUEST, "The upload was interrupted. Try again.", headers)),
        };
        let take = chunk.len().min(remaining as usize);
        if out.write_all(&chunk[..take]).await.is_err() {
            return close(problem(StatusCode::SERVICE_UNAVAILABLE, "The file could not be saved. Try again.", headers));
        }
        remaining -= take as u64;
    }
    if out.flush().await.is_err() || out.sync_data().await.is_err() {
        return close(problem(StatusCode::SERVICE_UNAVAILABLE, "The file could not be saved. Try again.", headers));
    }
    drop(out);
    let (width, height) = (text(headers, "x-media-width").to_owned(), text(headers, "x-media-height").to_owned());
    let finished = blocking(move || {
        let width = (!width.is_empty()).then_some(width);
        let height = (!height.is_empty()).then_some(height);
        stored.finish(width.as_deref(), height.as_deref())
    })
    .await;
    match finished {
        Ok(upload) => json_response(StatusCode::OK, &upload, headers),
        Err(_) => close(problem(StatusCode::SERVICE_UNAVAILABLE, "The file could not be saved. Try again.", headers)),
    }
}
