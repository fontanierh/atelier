//! A read-only observer of the production capacity broker. HTTP requests only copy the cache.
use std::fs::{self, OpenOptions};
use std::io::Read;
use std::os::unix::fs::{FileTypeExt, MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};
use std::sync::{LazyLock, RwLock};
use std::time::Duration;

use serde::Deserialize;
use serde_json::Value;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::UnixStream;

use crate::api::{CapacitySnapshot, CapacityStatus, CapacityVector};
use crate::{db, floor};

const FRAME: usize = 65536;
const DEADLINE: Duration = Duration::from_millis(800);
const FRESH: f64 = 10.0;
const NAMESPACE: &str = "atelier.capacity-broker.v1";
static CACHE: LazyLock<RwLock<CapacityStatus>> = LazyLock::new(|| {
    RwLock::new(CapacityStatus {
        configuration: "checking".into(),
        availability: "checking".into(),
        checked_at: None,
        fresh: false,
        snapshot: None,
    })
});

fn private(info: &fs::Metadata) -> bool {
    info.uid() == unsafe { libc::getuid() } && info.mode() & 0o077 == 0
}

fn valid_vector(value: &CapacityVector) -> bool {
    value.gpu_mib <= value.memory_mib
}

fn profile(value: &Value) -> bool {
    let Some(value) = value.as_object() else { return false };
    if value.len() != 2 {
        return false;
    }
    let Some(resources) = value.get("resources").and_then(Value::as_object) else {
        return false;
    };
    let vector = serde_json::from_value::<CapacityVector>(Value::Object(resources.clone()));
    if resources.len() != 5 || !vector.as_ref().is_ok_and(valid_vector) {
        return false;
    }
    let Some(locks) = value.get("locks").and_then(Value::as_array) else {
        return false;
    };
    let mut unique = std::collections::HashSet::new();
    locks.iter().all(|lock| {
        lock.as_str()
            .is_some_and(|lock| !lock.is_empty() && unique.insert(lock))
    })
}

/// Absence of the default client file means legacy operation; explicit missing/invalid files do not.
fn configured(path: &Path, explicit: bool, cutover: &Path) -> Result<Option<(PathBuf, bool)>, ()> {
    if !path.is_absolute() {
        return Err(());
    }
    let barrier = match fs::symlink_metadata(cutover) {
        Ok(_) => true,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => false,
        Err(_) => return Err(()),
    };
    match fs::symlink_metadata(path) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound && !explicit && !barrier => return Ok(None),
        Err(_) => return Err(()),
        Ok(_) => {}
    }
    let parent = path.parent().ok_or(())?;
    if !private(&fs::metadata(parent).map_err(|_| ())?) {
        return Err(());
    }
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path)
        .map_err(|_| ())?;
    let info = file.metadata().map_err(|_| ())?;
    if !info.is_file() || !private(&info) || info.nlink() != 1 || info.len() > FRAME as u64 {
        return Err(());
    }
    let mut data = Vec::new();
    file.take(FRAME as u64 + 1).read_to_end(&mut data).map_err(|_| ())?;
    if data.len() > FRAME {
        return Err(());
    }
    let value: Value = serde_json::from_slice(&data).map_err(|_| ())?;
    let object = value.as_object().ok_or(())?;
    let full = object.len() == 4
        && value.get("schema").and_then(Value::as_u64) == Some(2)
        && value.get("cutover").and_then(Value::as_str).map(Path::new) == Some(cutover);
    let bridge = object.len() == 3 && value.get("schema").and_then(Value::as_u64) == Some(1) && !barrier;
    if !bridge && !full {
        return Err(());
    }
    let profiles = value.get("profiles").and_then(Value::as_object).ok_or(())?;
    if profiles.len() != 3
        || !["job", "game", "compile"]
            .iter()
            .all(|key| profiles.get(*key).is_some_and(profile))
    {
        return Err(());
    }
    let socket = PathBuf::from(value.get("socket").and_then(Value::as_str).ok_or(())?);
    if !socket.is_absolute() {
        return Err(());
    }
    Ok(Some((socket, full)))
}

fn endpoint(path: &Path) -> Result<(), ()> {
    for part in path.ancestors() {
        if fs::symlink_metadata(part).map_err(|_| ())?.file_type().is_symlink()
            && ![Path::new("/tmp"), Path::new("/var"), Path::new("/etc")].contains(&part)
        {
            return Err(());
        }
    }
    let info = fs::symlink_metadata(path).map_err(|_| ())?;
    let parent = fs::metadata(path.parent().ok_or(())?).map_err(|_| ())?;
    if !info.file_type().is_socket() || !private(&info) || !private(&parent) {
        return Err(());
    }
    Ok(())
}

#[derive(Deserialize)]
struct Reply {
    ok: bool,
    namespace: String,
    compatibility_healthy: Option<bool>,
    #[serde(flatten)]
    snapshot: CapacitySnapshot,
}

fn path_label(path: &str) -> Option<String> {
    let path = path.replace('\\', "/");
    let absolute =
        path.starts_with('/') || (path.as_bytes().get(1) == Some(&b':') && path.as_bytes().get(2) == Some(&b'/'));
    absolute.then(|| {
        path.trim_end_matches('/')
            .rsplit('/')
            .next()
            .filter(|name| !name.is_empty())
            .unwrap_or("root")
            .to_owned()
    })
}

fn lock_label(lock: &str) -> String {
    if let Some(name) = path_label(lock) {
        return name;
    }
    if let Some((scope, path)) = lock.split_once(':') {
        if let Some(name) = path_label(path) {
            return format!("{scope}:{name}");
        }
    }
    lock.to_owned()
}

fn decode(data: &[u8], now: f64) -> Result<CapacitySnapshot, ()> {
    if data.len() > FRAME || !data.ends_with(b"\n") || data[..data.len() - 1].contains(&b'\n') {
        return Err(());
    }
    let reply: Reply = serde_json::from_slice(data).map_err(|_| ())?;
    let mut snapshot = reply.snapshot;
    if !reply.ok
        || reply.namespace != NAMESPACE
        || !matches!((snapshot.mode.as_str(), snapshot.cutover), ("legacy-bridge", false) | ("capacity", true))
        || (snapshot.cutover && (reply.compatibility_healthy.is_none()
            || (reply.compatibility_healthy == Some(false) && !snapshot.recovering)))
        || snapshot.boot_id.is_empty()
        || snapshot.boot_id.len() > 256
        || !(0.0..FRESH).contains(&(now - snapshot.observed_at))
        || snapshot.records.len() > 32
        || snapshot.returned_records != snapshot.records.len() as u64
        || snapshot.returned_records > snapshot.total_records
        || ![&snapshot.total, &snapshot.reserve, &snapshot.charged_resources]
            .into_iter()
            .all(valid_vector)
    {
        return Err(());
    }
    for job in &mut snapshot.records {
        if !matches!(
            job.state.as_str(),
            "queued" | "waiting" | "gated" | "running" | "draining" | "uncertain" | "released"
        ) || job.charged != matches!(job.state.as_str(), "running" | "draining" | "uncertain")
            || !valid_vector(&job.resources)
            || !job.first_ready.is_finite()
            || job.first_ready < 0.0
            || job.locks.len() > 32
            || job.measured_at.is_some_and(|time| !time.is_finite() || time < 0.0)
        {
            return Err(());
        }
        let mut replacements: Vec<_> = job.locks.iter().map(|lock| (lock.clone(), lock_label(lock))).collect();
        if let Some(checkout) = &job.checkout {
            replacements.push((checkout.clone(), floor::folder_name(checkout)));
        }
        replacements.sort_by_key(|(original, _)| std::cmp::Reverse(original.len()));
        for (original, label) in replacements {
            if !original.is_empty() && original != label {
                job.wait_reason = job.wait_reason.replace(&original, &label);
            }
        }
        job.checkout = job.checkout.as_deref().map(floor::folder_name);
        for lock in &mut job.locks {
            *lock = lock_label(lock);
        }
    }
    Ok(snapshot)
}

async fn request(path: &Path) -> Result<CapacitySnapshot, ()> {
    endpoint(path)?;
    tokio::time::timeout(DEADLINE, async {
        let mut socket = UnixStream::connect(path).await.map_err(|_| ())?;
        socket
            .write_all(b"{\"namespace\":\"atelier.capacity-broker.v1\",\"action\":\"status\"}\n")
            .await
            .map_err(|_| ())?;
        let mut data = Vec::new();
        let mut block = [0u8; 2048];
        loop {
            let count = socket.read(&mut block).await.map_err(|_| ())?;
            if count == 0 || data.len() + count > FRAME {
                return Err(());
            }
            data.extend_from_slice(&block[..count]);
            if data.contains(&b'\n') {
                return decode(&data, db::now());
            }
        }
    })
    .await
    .map_err(|_| ())?
}

/// @cc [owner:fontanierh,label:safety] read-only-capacity-observation
/// The board MUST send only production status requests, with one bounded poll at a time. Broker
/// failures MUST remain unknown/stale, never an empty grant pool. HTTP snapshots MUST NOT wait
/// for broker I/O. Observation MUST NOT activate clients, obtain grants or change legacy locks.
pub fn start() {
    tokio::spawn(async {
        let explicit = std::env::var_os("ATELIER_CAPACITY_CLIENT");
        let path = explicit
            .clone()
            .map(PathBuf::from)
            .unwrap_or_else(|| db::home().join(".cache/atelier/capacity/client.json"));
        let mut previous = None;
        let cutover = db::home().join(".cache/atelier/capacity/cutover.json");
        let mut delay = 3;
        loop {
            let configuration = configured(&path, explicit.is_some(), &cutover);
            let mut status = snapshot();
            status.checked_at = Some(db::now());
            status.fresh = false;
            match configuration {
                Ok(None) => {
                    status.configuration = "legacy".into();
                    status.availability = "disabled".into();
                    status.snapshot = None;
                    previous = None;
                    delay = 3;
                }
                Err(()) => {
                    status.configuration = "invalid".into();
                    status.availability = "unavailable".into();
                    status.snapshot = None;
                    previous = None;
                    delay = (delay * 2).min(30);
                }
                Ok(Some((socket, full))) => {
                    if previous.as_ref() != Some(&(socket.clone(), full)) {
                        status.snapshot = None;
                    }
                    previous = Some((socket.clone(), full));
                    status.configuration = "configured".into();
                    match request(&socket).await {
                        Ok(value) if value.cutover == full => {
                            status.snapshot = Some(value);
                            status.availability = "available".into();
                            delay = 3;
                        }
                        Ok(_) | Err(()) => {
                            status.availability = "unavailable".into();
                            delay = (delay * 2).min(30);
                        }
                    }
                }
            }
            status.checked_at = Some(db::now());
            *CACHE.write().unwrap_or_else(|e| e.into_inner()) = status;
            tokio::time::sleep(Duration::from_secs(delay)).await;
        }
    });
}

fn freshness(mut status: CapacityStatus, now: f64) -> CapacityStatus {
    status.fresh = status.availability == "available"
        && status
            .snapshot
            .as_ref()
            .is_some_and(|value| (0.0..FRESH).contains(&(now - value.observed_at)));
    status
}

pub fn snapshot() -> CapacityStatus {
    freshness(CACHE.read().unwrap_or_else(|e| e.into_inner()).clone(), db::now())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::os::unix::fs::PermissionsExt;

    struct Folder(PathBuf);
    impl Folder {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!("board-capacity-{}", rand::random::<u64>()));
            fs::create_dir(&path).unwrap();
            fs::set_permissions(&path, fs::Permissions::from_mode(0o700)).unwrap();
            Self(path)
        }
    }
    impl Drop for Folder {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    fn sample(now: f64) -> Value {
        let vector = json!({"memory_mib": 4096, "cpu_millis": 1000, "temp_mib": 2048, "io_slots": 1, "gpu_mib": 1024});
        json!({"ok": true, "namespace": NAMESPACE, "boot_id": "test-boot", "epoch": 2,
            "mode": "legacy-bridge", "cutover": false, "observed_at": now, "recovering": true,
            "total": vector, "reserve": vector, "charged_resources": vector, "charged_count": 4,
            "waiting_count": 3, "total_records": 45, "returned_records": 1, "truncated": true,
            "records": [{"id": "held", "owner": "artist", "checkout": "/work/tree",
                "purpose": "import", "phase": "job", "state": "uncertain", "charged": true,
                "resources": vector, "locks": ["checkout:/work/tree", "gpu"], "first_ready": 900.0,
                "sequence": 1, "bypasses": 2, "retained": 3, "witnessed": 1,
                "wait_reason": "ownership unknown; reservation retained", "measured_memory_mib": null,
                "measured_at": null, "ancestry_unknown": true}]})
    }

    fn frame(value: &Value) -> Vec<u8> {
        let mut bytes = serde_json::to_vec(value).unwrap();
        bytes.push(b'\n');
        bytes
    }

    #[test]
    fn production_snapshot_preserves_all_record_totals_and_uncertain_charges() {
        let snapshot = decode(&frame(&sample(1000.)), 1001.).unwrap();
        assert_eq!(snapshot.charged_count, 4); // Never sum a truncated visible list.
        assert!(snapshot.records[0].charged && snapshot.truncated && snapshot.recovering);
        assert_eq!(snapshot.records[0].checkout.as_deref(), Some("tree"));
        assert_eq!(snapshot.records[0].locks, ["checkout:tree", "gpu"]);
        assert_eq!(snapshot.records[0].measured_memory_mib, None);
    }

    #[test]
    fn path_bearing_locks_are_labels_in_both_lock_lists_and_reasons() {
        let mut value = sample(1000.);
        value["records"][0]["locks"] = json!([
            "engine:/private/machine/UE_5.8",
            "/private/cache",
            "display:main",
            "engine:C:\\private\\UE_5.8"
        ]);
        value["records"][0]["wait_reason"] = json!("lock:engine:/private/machine/UE_5.8; lock:/private/cache");
        let snapshot = decode(&frame(&value), 1001.).unwrap();
        assert_eq!(
            snapshot.records[0].locks,
            ["engine:UE_5.8", "cache", "display:main", "engine:UE_5.8"]
        );
        assert_eq!(snapshot.records[0].wait_reason, "lock:engine:UE_5.8; lock:cache");
        value["records"][0]["checkout"] = json!("/private/machine");
        value["records"][0]["locks"] = json!([
            "/private",
            "engine:/private/machine/UE_5.8",
            "checkout:/private/machine"
        ]);
        value["records"][0]["wait_reason"] =
            json!("lock:engine:/private/machine/UE_5.8; lock:/private; lock:checkout:/private/machine");
        let snapshot = decode(&frame(&value), 1001.).unwrap();
        assert_eq!(
            snapshot.records[0].locks,
            ["private", "engine:UE_5.8", "checkout:machine"]
        );
        assert_eq!(
            snapshot.records[0].wait_reason,
            "lock:engine:UE_5.8; lock:private; lock:checkout:machine"
        );
    }

    #[test]
    fn shadow_cutover_stale_and_inconsistent_responses_stay_unknown() {
        for (field, invalid) in [
            ("namespace", json!("atelier.capacity-shadow.v1")),
            ("ok", json!(false)),
            ("mode", json!("full-capacity")),
            ("cutover", json!(true)),
            ("observed_at", json!(980.)),
            ("returned_records", json!(0)),
        ] {
            let mut value = sample(1000.);
            value[field] = invalid;
            assert!(decode(&frame(&value), 1001.).is_err(), "{field}");
        }
        let mut value = sample(1000.);
        value["records"][0]["charged"] = json!(false);
        assert!(decode(&frame(&value), 1001.).is_err());
        assert!(decode(&vec![b'x'; FRAME + 1], 1001.).is_err());
        let mut multiple = frame(&sample(1000.));
        multiple.extend_from_slice(b"{}\n");
        assert!(decode(&multiple, 1001.).is_err());
    }

    #[test]
    fn failed_or_old_observations_keep_snapshot_but_cannot_claim_freshness() {
        let status = CapacityStatus {
            configuration: "configured".into(),
            availability: "available".into(),
            checked_at: Some(1000.),
            fresh: false,
            snapshot: Some(decode(&frame(&sample(1000.)), 1001.).unwrap()),
        };
        assert!(freshness(status.clone(), 1001.).fresh);
        assert!(!freshness(status.clone(), 1011.).fresh);
        let failed = freshness(
            CapacityStatus {
                availability: "unavailable".into(),
                ..status
            },
            1001.,
        );
        assert!(!failed.fresh && failed.snapshot.unwrap().charged_count == 4);
    }

    #[test]
    fn full_mode_requires_matching_cutover_and_reports_failed_barrier_as_recovery() {
        let mut value = sample(1000.);
        value["mode"] = json!("capacity");
        value["cutover"] = json!(true);
        assert!(decode(&frame(&value), 1001.).is_err());
        value["compatibility_healthy"] = json!(true);
        assert!(decode(&frame(&value), 1001.).unwrap().cutover);
        value["compatibility_healthy"] = json!(false);
        assert!(decode(&frame(&value), 1001.).unwrap().recovering);
        value["recovering"] = json!(false);
        assert!(decode(&frame(&value), 1001.).is_err());
        value["mode"] = json!("legacy-bridge");
        assert!(decode(&frame(&value), 1001.).is_err());
    }

    #[test]
    fn only_absent_default_configuration_is_legacy() {
        let folder = Folder::new();
        let path = folder.0.join("client.json");
        let cutover = folder.0.join("cutover.json");
        assert_eq!(configured(&path, false, &cutover), Ok(None));
        assert!(configured(&path, true, &cutover).is_err());
        let resources = sample(1000.)["total"].clone();
        let profile = json!({"resources": resources, "locks": []});
        let config = json!({"schema": 1, "socket": folder.0.join("broker.sock"),
            "profiles": {"job": profile, "game": profile, "compile": profile}});
        fs::write(&path, config.to_string()).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        assert_eq!(configured(&path, false, &cutover), Ok(Some((folder.0.join("broker.sock"), false))));
        fs::write(&cutover, "preparing").unwrap();
        assert!(configured(&path, false, &cutover).is_err());
        let mut full = config;
        full["schema"] = json!(2);
        full["cutover"] = json!(cutover);
        fs::write(&path, full.to_string()).unwrap();
        assert_eq!(configured(&path, false, &cutover), Ok(Some((folder.0.join("broker.sock"), true))));
        fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
        assert!(configured(&path, false, &cutover).is_err());
        fs::remove_file(&path).unwrap();
        std::os::unix::fs::symlink(folder.0.join("missing"), &path).unwrap();
        assert!(configured(&path, false, &cutover).is_err());
    }

    #[tokio::test]
    async fn observer_sends_only_status_and_has_one_total_deadline() {
        use tokio::io::{AsyncBufReadExt, BufReader};
        let folder = Folder::new();
        let path = folder.0.join("broker.sock");
        let listener = tokio::net::UnixListener::bind(&path).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        let peer = tokio::spawn(async move {
            let (channel, _) = listener.accept().await.unwrap();
            let mut channel = BufReader::new(channel);
            let mut query = String::new();
            channel.read_line(&mut query).await.unwrap();
            assert_eq!(
                serde_json::from_str::<Value>(&query).unwrap(),
                json!({"namespace": NAMESPACE, "action": "status"})
            );
            // Dribbling incomplete data cannot extend the poll's total deadline.
            loop {
                if channel.get_mut().write_all(b" ").await.is_err() {
                    break;
                }
                tokio::time::sleep(Duration::from_millis(100)).await;
            }
        });
        let result = tokio::time::timeout(Duration::from_secs(3), request(&path)).await;
        assert!(result.is_ok(), "observer exceeded its total deadline");
        assert!(result.unwrap().is_err());
        peer.abort();
    }
}
