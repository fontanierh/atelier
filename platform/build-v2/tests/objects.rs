use atelier_build_v2::store::*;
use std::fs;
#[cfg(target_os = "macos")]
use std::path::Path;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
static SERIAL: AtomicU64 = AtomicU64::new(0);

struct Workspace(PathBuf);
impl Workspace {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "atelier-v2-objects-{}-{}",
            std::process::id(),
            SERIAL.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        Self(path)
    }
    fn path(&self, value: &str) -> PathBuf {
        self.0.join(value)
    }
    fn store(&self) -> ObjectStore {
        ObjectStore::open(self.path("store")).unwrap()
    }
}
impl Drop for Workspace {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
    }
}

#[test]
fn digest_encoding_rejects_noncanonical_or_pathlike_names() {
    assert_eq!(OBJECT_ALGORITHM, "sha256");
    assert_eq!(OBJECT_FORMAT_VERSION, 1);
    for invalid in [
        "",
        "../object",
        &"a".repeat(63),
        &"a".repeat(65),
        &"A".repeat(64),
        &"g".repeat(64),
    ] {
        assert!(ObjectDigest::from_hex(invalid).is_err());
    }
    let valid = "a".repeat(64);
    assert_eq!(ObjectDigest::from_hex(&valid).unwrap().as_hex(), valid);
}

#[test]
fn nonregular_sources_and_store_directories_are_refused() {
    let workspace = Workspace::new();
    let store = workspace.store();
    assert!(matches!(
        store.prepare(&workspace.0),
        Err(StoreError::InvalidFile(_))
    ));
    fs::write(workspace.path("plain-file"), b"unrelated").unwrap();
    assert!(ObjectStore::open(workspace.path("plain-file")).is_err());
    assert_eq!(
        fs::read(workspace.path("plain-file")).unwrap(),
        b"unrelated"
    );
}

#[cfg(unix)]
#[test]
fn symlink_sources_and_store_roots_are_refused() {
    let workspace = Workspace::new();
    let store = workspace.store();
    fs::write(workspace.path("source"), b"source").unwrap();
    std::os::unix::fs::symlink(workspace.path("source"), workspace.path("source-link")).unwrap();
    assert!(matches!(
        store.prepare(workspace.path("source-link")),
        Err(StoreError::InvalidFile(_))
    ));
    std::os::unix::fs::symlink(store.root(), workspace.path("store-link")).unwrap();
    assert!(matches!(
        ObjectStore::open(workspace.path("store-link")),
        Err(StoreError::InvalidFile(_))
    ));
}

#[cfg(not(target_os = "macos"))]
#[test]
fn unavailable_clone_backend_fails_without_copying() {
    let workspace = Workspace::new();
    let store = workspace.store();
    fs::write(workspace.path("source"), b"source").unwrap();
    let error = store.prepare(workspace.path("source")).unwrap_err();
    assert!(
        matches!(error, StoreError::Clone(ref error) if error.kind() == std::io::ErrorKind::Unsupported)
    );
    assert_eq!(fs::read(workspace.path("source")).unwrap(), b"source");
    assert_eq!(
        fs::read_dir(store.root().join("staging")).unwrap().count(),
        0
    );
}

#[cfg(target_os = "macos")]
mod apfs {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    use std::sync::{Arc, Barrier};
    const HELLO: &str = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824";

    fn source(workspace: &Workspace) -> PathBuf {
        let path = workspace.path("source");
        fs::write(&path, b"hello").unwrap();
        path
    }
    fn object(store: &ObjectStore) -> PathBuf {
        store.root().join("objects/sha256").join(HELLO)
    }
    fn writable(path: &Path) {
        fs::set_permissions(path, fs::Permissions::from_mode(0o644)).unwrap();
    }

    #[test]
    fn snapshot_is_frozen_and_hits_clone_independent_bytes() {
        let workspace = Workspace::new();
        let store = workspace.store();
        let input = source(&workspace);
        fs::set_permissions(&input, fs::Permissions::from_mode(0o755)).unwrap();
        let prepared = store.prepare(&input).unwrap();
        assert_eq!(prepared.digest().as_hex(), HELLO);
        assert_eq!(prepared.size(), 5);
        assert_eq!(prepared.source_mode(), 0o755);
        fs::write(&input, b"changed after snapshot").unwrap();
        let published = store.publish(prepared).unwrap();
        assert_eq!(published.outcome, PublishOutcome::Published);
        assert_eq!(published.source_mode, 0o755);
        assert_eq!(
            fs::metadata(object(&store)).unwrap().permissions().mode() & 0o777,
            0o444
        );
        let first = workspace.path("first");
        let second = workspace.path("second");
        store.clone_to(&published.digest, &first).unwrap();
        assert_eq!(fs::read(&first).unwrap(), b"hello");
        writable(&first);
        fs::write(&first, b"edited clone").unwrap();
        store.clone_to(&published.digest, &second).unwrap();
        assert_eq!(fs::read(&second).unwrap(), b"hello");
        assert_eq!(fs::read(object(&store)).unwrap(), b"hello");
        assert_eq!(fs::read(&input).unwrap(), b"changed after snapshot");
    }

    #[test]
    fn racing_publishers_keep_exactly_one_readonly_winner() {
        let workspace = Workspace::new();
        let store = workspace.store();
        let input = source(&workspace);
        let a = store.prepare(&input).unwrap();
        let b = store.prepare(&input).unwrap();
        let barrier = Arc::new(Barrier::new(3));
        let spawn = |prepared| {
            let barrier = barrier.clone();
            let store = store.clone();
            std::thread::spawn(move || {
                barrier.wait();
                store.publish(prepared).unwrap().outcome
            })
        };
        let a = spawn(a);
        let b = spawn(b);
        barrier.wait();
        let results = [a.join().unwrap(), b.join().unwrap()];
        assert_eq!(
            results
                .iter()
                .filter(|r| **r == PublishOutcome::Published)
                .count(),
            1
        );
        assert_eq!(
            results
                .iter()
                .filter(|r| **r == PublishOutcome::Existing)
                .count(),
            1
        );
        assert_eq!(fs::read(object(&store)).unwrap(), b"hello");
        assert_eq!(
            fs::read_dir(store.root().join("staging")).unwrap().count(),
            0
        );
    }

    #[test]
    fn existing_entries_and_clone_destinations_are_never_overwritten() {
        let workspace = Workspace::new();
        let store = workspace.store();
        let input = source(&workspace);
        let prepared = store.prepare(&input).unwrap();
        let digest = prepared.digest().clone();
        fs::write(object(&store), b"existing invalid entry").unwrap();
        fs::set_permissions(object(&store), fs::Permissions::from_mode(0o444)).unwrap();
        assert!(matches!(
            store.publish(prepared),
            Err(StoreError::InvalidFile(_))
        ));
        assert_eq!(fs::read(object(&store)).unwrap(), b"existing invalid entry");
        // Preserve the invalid object, rather than replacing it to make the test pass.
        let other = ObjectStore::open(workspace.path("other-store")).unwrap();
        other.publish(other.prepare(&input).unwrap()).unwrap();
        let destination = workspace.path("existing-destination");
        fs::write(&destination, b"unrelated").unwrap();
        assert!(matches!(
            other.clone_to(&digest, &destination),
            Err(StoreError::Clone(_))
        ));
        assert_eq!(fs::read(destination).unwrap(), b"unrelated");
    }

    #[test]
    fn discarded_and_wrong_store_tokens_clean_only_owned_staging_files() {
        let workspace = Workspace::new();
        let store = workspace.store();
        let input = source(&workspace);
        let marker = store.root().join("staging/unrelated");
        fs::write(&marker, b"keep").unwrap();
        drop(store.prepare(&input).unwrap());
        assert_eq!(
            fs::read_dir(store.root().join("staging")).unwrap().count(),
            1
        );
        let other = ObjectStore::open(workspace.path("other-store")).unwrap();
        assert!(matches!(
            other.publish(store.prepare(&input).unwrap()),
            Err(StoreError::WrongStore)
        ));
        assert_eq!(fs::read(&marker).unwrap(), b"keep");
        assert_eq!(fs::read(&input).unwrap(), b"hello");
        assert_eq!(
            fs::read_dir(store.root().join("staging")).unwrap().count(),
            1
        );
    }
}
