use atelier_build_v2::keys::{ImplementationIdentity, KeyContext, PreparedUnit, prepare};
use atelier_build_v2::leases::{LEASE_VERSION, LeaseRecord, Liveness, ProcessIdentity};
use atelier_build_v2::results::{ResultError, ResultStore};
use atelier_build_v2::roots::*;
use atelier_build_v2::schema::{
    Declaration, Destination, Item, Op, OutputFile, Provenance, SCHEMA_VERSION, Unit,
};
use atelier_build_v2::source_hashes::SourceHashCache;
use atelier_build_v2::store::ObjectDigest;
use atelier_build_v2::validate::{OpDefinition, SnapshotEntry, ValidatedDeclaration, validate};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};

static SERIAL: AtomicU64 = AtomicU64::new(0);

struct Workspace(PathBuf);
impl Workspace {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "atelier-v2-roots-{}-{}",
            std::process::id(),
            SERIAL.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(&path).unwrap();
        Self(path)
    }
    fn store(&self) -> PathBuf {
        self.0.join("store")
    }
    fn open(&self, project: &str) -> RootStore {
        fs::create_dir_all(self.store()).unwrap();
        RootStore::open(self.store(), project).unwrap()
    }
    fn project_dir(&self, project: &str) -> PathBuf {
        self.store().join("roots").join(project)
    }
}
impl Drop for Workspace {
    fn drop(&mut self) {
        let _ = fs::set_permissions(&self.0, fs::Permissions::from_mode(0o755));
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn provenance(name: &str) -> Provenance {
    Provenance {
        checkout: name.into(),
        branch: name.into(),
        commit: name.into(),
        dirty: false,
        built_at: format!("{name}-time"),
    }
}

fn process(pid: u32) -> ProcessIdentity {
    ProcessIdentity {
        pid,
        boot: "boot".into(),
        started: format!("start-{pid}"),
    }
}

fn key(seed: u8) -> String {
    format!("{seed:02x}").repeat(32)
}

fn declaration(units: &[&str]) -> Declaration {
    Declaration {
        schema_version: SCHEMA_VERSION,
        cache_version: "1".into(),
        units: units
            .iter()
            .map(|id| Unit {
                id: (*id).into(),
                op: Op {
                    kind: "data".into(),
                    version: "1".into(),
                },
                script: "ops/run.py".into(),
                code: vec!["ops/run.py".into()],
                inputs: vec![],
                params: BTreeMap::new(),
                outputs: vec![Item {
                    id: "data".into(),
                    logical_path: format!("/Data/{id}"),
                    class: "Data".into(),
                    destination: Destination::Store,
                    files: vec![OutputFile {
                        path: "result.bin".into(),
                        install_path: None,
                        required: true,
                    }],
                }],
                output_groups: vec![],
                conditional: None,
            })
            .collect(),
    }
}

fn validated(units: &[&str]) -> ValidatedDeclaration {
    let declaration = declaration(units);
    let registry = BTreeMap::from([(
        ("data".to_string(), "1".to_string()),
        OpDefinition {
            inputs: BTreeMap::new(),
            output_classes: BTreeSet::from(["Data".to_string()]),
            params: BTreeMap::new(),
        },
    )]);
    let snapshot = BTreeMap::from([(
        "ops/run.py".to_string(),
        SnapshotEntry::File(b"code".to_vec()),
    )]);
    validate(&declaration, &registry, &snapshot, &[]).unwrap()
}

fn roster(units: &[&str]) -> DeclaredRoster {
    DeclaredRoster::from_validated(&declaration(units), &validated(units)).unwrap()
}

fn prepared(id: &str) -> PreparedUnit {
    let declaration = declaration(&[id]);
    let registry = BTreeMap::from([(
        ("data".to_string(), "1".to_string()),
        OpDefinition {
            inputs: BTreeMap::new(),
            output_classes: BTreeSet::from(["Data".to_string()]),
            params: BTreeMap::new(),
        },
    )]);
    let snapshot = BTreeMap::from([(
        "ops/run.py".to_string(),
        SnapshotEntry::File(b"code".to_vec()),
    )]);
    let validated = validate(&declaration, &registry, &snapshot, &[]).unwrap();
    let implementation = ImplementationIdentity {
        version: "1".into(),
        digest: "a".repeat(64),
    };
    prepare(
        &declaration,
        &validated,
        id,
        &KeyContext {
            snapshot: &snapshot,
            versions: &BTreeMap::new(),
            produced: &BTreeMap::new(),
            produced_groups: &BTreeMap::new(),
            staged_inputs: &BTreeMap::new(),
            worker: &implementation,
            validator: &implementation,
        },
        &mut SourceHashCache::default(),
    )
    .unwrap()
}

fn session_files(root: &Path, project: &str) -> Vec<PathBuf> {
    let directory = root.join("roots").join(project).join("session");
    let mut paths: Vec<PathBuf> = fs::read_dir(directory)
        .unwrap()
        .map(|entry| entry.unwrap().path())
        .collect();
    paths.sort();
    paths
}

fn only_session(root: &Path, project: &str) -> PathBuf {
    let paths = session_files(root, project);
    assert_eq!(paths.len(), 1, "expected one open session");
    paths.into_iter().next().unwrap()
}

fn session_id(path: &Path) -> String {
    path.file_stem().unwrap().to_string_lossy().to_string()
}

struct FakeCustodians {
    registered: BTreeMap<u32, String>,
    unreadable: bool,
}
impl SessionCustodians for FakeCustodians {
    fn correlation(&self, identity: &ProcessIdentity) -> Result<Option<String>, String> {
        if self.unreadable {
            return Err("custodian registry unreadable".into());
        }
        Ok(self.registered.get(&identity.pid).cloned())
    }
}

struct FakeCleanup {
    confirmed: BTreeSet<String>,
    unreadable: bool,
}
impl CustodianCleanup for FakeCleanup {
    fn cleanup_confirmed(&self, correlation: &str) -> Result<bool, String> {
        if self.unreadable {
            return Err("cleanup record unreadable".into());
        }
        Ok(self.confirmed.contains(correlation))
    }
}

fn no_custodians() -> FakeCustodians {
    FakeCustodians {
        registered: BTreeMap::new(),
        unreadable: false,
    }
}

fn no_cleanup() -> FakeCleanup {
    FakeCleanup {
        confirmed: BTreeSet::new(),
        unreadable: false,
    }
}

fn lease(owner: u32, workers: &[u32]) -> LeaseRecord {
    LeaseRecord {
        version: LEASE_VERSION,
        id: "1-0".into(),
        staging: "staging/1-0".into(),
        owner: process(owner),
        workers: workers.iter().map(|pid| process(*pid)).collect(),
        result_keys: BTreeSet::new(),
        object_digests: BTreeSet::new(),
        rooted: false,
    }
}

fn begin(store: &RootStore, kind: RootKind, name: &str, pid: u32) -> BuildSession {
    store
        .begin_session(kind, provenance(name), process(pid))
        .unwrap()
}

#[test]
fn partial_build_merges_and_keeps_other_units_with_their_own_provenance() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    let mut first = begin(&store, RootKind::Main, "first", 1);
    first.use_result("unit.a", &key(1)).unwrap();
    first.use_result("unit.b", &key(2)).unwrap();
    let root = first.commit(None).unwrap();
    assert_eq!(root.entries.len(), 2);

    let mut second = begin(&store, RootKind::Main, "second", 1);
    second.use_result("unit.a", &key(3)).unwrap();
    let root = second.commit(None).unwrap();

    assert_eq!(root.entries["unit.a"].key, key(3));
    assert_eq!(root.entries["unit.a"].provenance, provenance("second"));
    assert_eq!(root.entries["unit.b"].key, key(2));
    assert_eq!(
        root.entries["unit.b"].provenance,
        provenance("first"),
        "an untouched entry must keep the provenance of the build that wrote it"
    );
    assert_eq!(root.provenance, provenance("second"));
}

#[test]
fn complete_roster_prunes_units_that_are_no_longer_declared() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.use_result("unit.removed", &key(2)).unwrap();
    session.commit(None).unwrap();

    let mut session = begin(&store, RootKind::Main, "second", 1);
    session.use_result("unit.a", &key(3)).unwrap();
    let root = session.commit(Some(&roster(&["unit.a"]))).unwrap();

    assert_eq!(
        root.entries.keys().cloned().collect::<Vec<_>>(),
        vec!["unit.a".to_string()]
    );
    assert_eq!(root.entries["unit.a"].key, key(3));
}

#[test]
fn none_never_prunes() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.use_result("unit.b", &key(2)).unwrap();
    session.commit(None).unwrap();

    let mut session = begin(&store, RootKind::Main, "second", 1);
    session.use_result("unit.a", &key(3)).unwrap();
    let root = session.commit(None).unwrap();
    assert_eq!(root.entries.len(), 2);
    assert_eq!(root.entries["unit.b"].key, key(2));
}

#[test]
fn a_release_is_a_frozen_snapshot_and_never_merges() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.commit(None).unwrap();

    let release_one = RootKind::Release {
        sequence: 1,
        label: "r13".into(),
    };
    let mut session = begin(&store, release_one.clone(), "release-one", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.commit(None).unwrap();

    let release_two = RootKind::Release {
        sequence: 2,
        label: "r14".into(),
    };
    let mut session = begin(&store, release_two.clone(), "release-two", 1);
    session.use_result("unit.b", &key(2)).unwrap();
    session.commit(None).unwrap();

    let second = store.root(&release_two).unwrap().unwrap();
    assert_eq!(
        second.entries.keys().cloned().collect::<Vec<_>>(),
        vec!["unit.b".to_string()],
        "a release must not inherit entries from another release or root"
    );
    let first = store.root(&release_one).unwrap().unwrap();
    assert_eq!(first.entries.len(), 1);
    assert_eq!(first.entries["unit.a"].key, key(1));
}

#[test]
fn a_commit_removes_only_its_own_session_journal() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    let mut alpha = begin(&store, RootKind::Main, "alpha", 1);
    alpha.use_result("unit.a", &key(1)).unwrap();
    let mut beta = begin(&store, RootKind::Main, "beta", 2);
    beta.use_result("unit.b", &key(2)).unwrap();

    let open_before = session_files(&workspace.store(), "yorimichi").len();
    alpha.commit(None).unwrap();
    assert_eq!(
        session_files(&workspace.store(), "yorimichi").len(),
        open_before - 1,
        "another build's journal must survive"
    );
    let view = store.retention().unwrap();
    assert!(view.keys.contains(&key(1)));
    assert!(
        view.keys.contains(&key(2)),
        "the open session still retains its own keys"
    );

    let root = beta.commit(None).unwrap();
    assert_eq!(root.entries.len(), 2);
    assert!(session_files(&workspace.store(), "yorimichi").is_empty());
}

#[test]
fn a_torn_journal_tail_fails_the_commit_and_preserves_root_and_journal() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.commit(None).unwrap();

    let mut session = begin(&store, RootKind::Main, "second", 1);
    session.use_result("unit.a", &key(2)).unwrap();
    let journal = only_session(&workspace.store(), "yorimichi");
    let bytes = fs::read(&journal).unwrap();
    fs::write(&journal, &bytes[..bytes.len() - 1]).unwrap();

    let error = session.commit(None).unwrap_err();
    assert!(
        matches!(error, RootError::Damaged(_)),
        "unexpected error: {error}"
    );
    assert!(
        journal.exists(),
        "the damaged journal must be kept for inspection"
    );
    let root = store.root(&RootKind::Main).unwrap().unwrap();
    assert_eq!(root.entries["unit.a"].key, key(1));
}

#[test]
fn a_corrupt_middle_record_fails_closed_and_retention_counts_parseable_keys() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    let mut session = begin(&store, RootKind::Main, "one", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.use_result("unit.b", &key(2)).unwrap();
    let journal = only_session(&workspace.store(), "yorimichi");
    let text = fs::read_to_string(&journal).unwrap();
    let mut lines: Vec<&str> = text.split('\n').collect();
    lines.pop();
    let mut damaged = format!("{}\n{}\n", lines[0], lines[1]);
    damaged.push_str("this is not a record\n");
    damaged.push_str(lines[2]);
    damaged.push('\n');
    fs::write(&journal, damaged).unwrap();

    let error = session.commit(None).unwrap_err();
    assert!(
        matches!(error, RootError::Damaged(_)),
        "unexpected: {error}"
    );
    assert!(store.root(&RootKind::Main).unwrap().is_none());

    let view = store.retention().unwrap();
    assert!(view.keys.contains(&key(1)));
    assert!(view.keys.contains(&key(2)));
    assert_eq!(view.damaged.len(), 1, "damage must be reported, not hidden");
}

#[test]
fn faults_at_each_commit_boundary_keep_the_journal_and_never_lose_retention() {
    let steps = [
        (CommitStep::JournalRead, false, true),
        (CommitStep::RootTemporary, false, true),
        (CommitStep::RootReplaced, true, true),
        (CommitStep::DirectorySynced, true, true),
        (CommitStep::SessionRemoved, true, false),
    ];
    for (fault, root_written, journal_kept) in steps {
        let workspace = Workspace::new();
        let store = workspace.open("yorimichi");
        let mut seed = begin(&store, RootKind::Main, "seed", 1);
        seed.use_result("unit.a", &key(1)).unwrap();
        seed.commit(None).unwrap();

        let mut session = begin(&store, RootKind::Main, "faulty", 1);
        session.use_result("unit.b", &key(2)).unwrap();
        let journal = only_session(&workspace.store(), "yorimichi");
        let error = session
            .commit_observed(None, |step| {
                if step == fault {
                    Err(io::Error::other("injected"))
                } else {
                    Ok(())
                }
            })
            .unwrap_err();
        assert!(matches!(error, RootError::Io(_)), "{fault:?}: {error}");
        assert_eq!(journal.exists(), journal_kept, "{fault:?}");
        let root = store.root(&RootKind::Main).unwrap().unwrap();
        assert_eq!(
            root.entries.contains_key("unit.b"),
            root_written,
            "{fault:?}"
        );
        assert_eq!(root.entries["unit.a"].key, key(1), "{fault:?}");
    }
}

#[test]
fn concurrent_commits_to_one_target_serialize_without_losing_entries() {
    let workspace = Workspace::new();
    let store = Arc::new(workspace.open("yorimichi"));
    let mut handles = vec![];
    for index in 0..4u8 {
        let store = Arc::clone(&store);
        handles.push(std::thread::spawn(move || {
            let mut session = store
                .begin_session(
                    RootKind::Main,
                    provenance(&format!("thread-{index}")),
                    process(10 + u32::from(index)),
                )
                .unwrap();
            session
                .use_result(&format!("unit.{index}"), &key(index + 1))
                .unwrap();
            session.commit(None).unwrap();
        }));
    }
    for handle in handles {
        handle.join().unwrap();
    }
    let root = store.root(&RootKind::Main).unwrap().unwrap();
    assert_eq!(root.entries.len(), 4);
    for index in 0..4u8 {
        assert_eq!(root.entries[&format!("unit.{index}")].key, key(index + 1));
    }
    assert!(session_files(&workspace.store(), "yorimichi").is_empty());
}

#[test]
fn projects_and_worktrees_are_isolated() {
    let workspace = Workspace::new();
    let alpha = workspace.open("alpha");
    let beta = workspace.open("beta");
    let mut session = begin(&alpha, RootKind::Main, "alpha", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.commit(None).unwrap();
    let mut session = begin(&beta, RootKind::Main, "beta", 1);
    session.use_result("unit.a", &key(2)).unwrap();
    session.commit(None).unwrap();

    assert_eq!(
        alpha.root(&RootKind::Main).unwrap().unwrap().entries["unit.a"].key,
        key(1)
    );
    assert_eq!(
        beta.root(&RootKind::Main).unwrap().unwrap().entries["unit.a"].key,
        key(2)
    );

    let one = RootKind::Worktree {
        id: "checkout-one".into(),
    };
    let two = RootKind::Worktree {
        id: "checkout-two".into(),
    };
    let mut session = begin(&alpha, one.clone(), "one", 1);
    session.use_result("unit.w", &key(3)).unwrap();
    session.commit(None).unwrap();
    assert!(alpha.root(&two).unwrap().is_none());
}

#[test]
fn releases_keep_the_three_greatest_sequences_and_refuse_a_different_duplicate() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    for sequence in 1..=5u64 {
        let kind = RootKind::Release {
            sequence,
            label: format!("r{sequence}"),
        };
        let mut session = begin(&store, kind, &format!("release-{sequence}"), 1);
        session
            .use_result(&format!("unit.{sequence}"), &key(sequence as u8))
            .unwrap();
        session.commit(None).unwrap();
        let records = store.roots().unwrap();
        let sequences: Vec<u64> = records
            .iter()
            .filter_map(|record| match &record.kind {
                RootKind::Release { sequence, .. } => Some(*sequence),
                _ => None,
            })
            .collect();
        let first = sequence.saturating_sub(2).max(1);
        let expected: Vec<u64> = (first..=sequence).collect();
        assert_eq!(sequences, expected, "after release {sequence}");
    }

    let duplicate = RootKind::Release {
        sequence: 4,
        label: "conflict".into(),
    };
    let mut session = begin(&store, duplicate, "conflict", 1);
    session.use_result("unit.other", &key(9)).unwrap();
    let error = session.commit(None).unwrap_err();
    assert!(
        matches!(error, RootError::Conflict(_)),
        "unexpected: {error}"
    );
    let kept = store
        .root(&RootKind::Release {
            sequence: 4,
            label: "r4".into(),
        })
        .unwrap()
        .unwrap();
    assert_eq!(kept.entries["unit.4"].key, key(4), "the first release wins");
}

#[test]
fn a_sequence_below_the_retained_window_is_refused() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    for sequence in 3..=5u64 {
        let kind = RootKind::Release {
            sequence,
            label: format!("r{sequence}"),
        };
        let mut session = begin(&store, kind, "release", 1);
        session.use_result("unit.a", &key(sequence as u8)).unwrap();
        session.commit(None).unwrap();
    }
    let stale = RootKind::Release {
        sequence: 1,
        label: "r1".into(),
    };
    let mut session = begin(&store, stale, "stale", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    let error = session.commit(None).unwrap_err();
    assert!(
        matches!(error, RootError::Conflict(_)),
        "unexpected: {error}"
    );
    assert!(
        !workspace
            .project_dir("yorimichi")
            .join("release/1.json")
            .exists()
    );
}

#[test]
fn an_identical_release_retry_keeps_the_first_record() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    let kind = RootKind::Release {
        sequence: 1,
        label: "r13".into(),
    };
    let mut first = begin(&store, kind.clone(), "first", 1);
    first.use_result("unit.a", &key(1)).unwrap();
    first.commit(None).unwrap();

    let mut retry = begin(&store, kind.clone(), "retry", 1);
    retry.use_result("unit.a", &key(1)).unwrap();
    retry.commit(None).unwrap();
    let record = store.root(&kind).unwrap().unwrap();
    assert_eq!(
        record.provenance,
        provenance("first"),
        "the first frozen record is kept"
    );
}

#[test]
fn a_release_fault_after_publish_before_trim_recovers_on_retry() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    for sequence in 1..=3u64 {
        let kind = RootKind::Release {
            sequence,
            label: format!("r{sequence}"),
        };
        let mut session = begin(&store, kind, "release", 1);
        session.use_result("unit.a", &key(sequence as u8)).unwrap();
        session.commit(None).unwrap();
    }
    let fourth = RootKind::Release {
        sequence: 4,
        label: "r16".into(),
    };
    let mut session = begin(&store, fourth.clone(), "fourth", 1);
    session.use_result("unit.a", &key(9)).unwrap();
    let journal = only_session(&workspace.store(), "yorimichi");
    let error = session
        .commit_observed(None, |step| {
            if step == CommitStep::DirectorySynced {
                Err(io::Error::other("injected before trim"))
            } else {
                Ok(())
            }
        })
        .unwrap_err();
    assert!(matches!(error, RootError::Io(_)), "unexpected: {error}");
    assert!(
        store.root(&fourth).unwrap().is_some(),
        "snapshot is durable"
    );
    assert!(journal.exists(), "the journal survives the failed trim");
    assert_eq!(store.roots().unwrap().len(), 4, "trimming has not run yet");

    let mut retry = begin(&store, fourth.clone(), "retry", 1);
    retry.use_result("unit.a", &key(9)).unwrap();
    retry.commit(None).unwrap();
    let sequences: Vec<u64> = store
        .roots()
        .unwrap()
        .iter()
        .filter_map(|record| match &record.kind {
            RootKind::Release { sequence, .. } => Some(*sequence),
            _ => None,
        })
        .collect();
    assert_eq!(sequences, vec![2, 3, 4]);
}

#[test]
fn pins_survive_trimming_until_an_exact_explicit_drop() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    let pin = RootKind::Pin {
        id: "keep-me".into(),
    };
    let mut session = begin(&store, pin.clone(), "pin", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.commit(None).unwrap();

    for sequence in 1..=4u64 {
        let kind = RootKind::Release {
            sequence,
            label: format!("r{sequence}"),
        };
        let mut session = begin(&store, kind, "release", 1);
        session
            .use_result("unit.r", &key(sequence as u8 + 8))
            .unwrap();
        session.commit(None).unwrap();
    }
    assert!(store.root(&pin).unwrap().is_some());
    assert_eq!(
        store.roots().unwrap().len(),
        4,
        "three releases plus one pin"
    );

    let removed = store.drop_root(&pin).unwrap().expect("pin exists");
    assert_eq!(removed.entries["unit.a"].key, key(1));
    assert!(store.root(&pin).unwrap().is_none());
    assert!(store.drop_root(&pin).unwrap().is_none());
    assert_eq!(store.roots().unwrap().len(), 3);
}

#[test]
fn malformed_root_metadata_fails_reads_and_retention_reports_damage() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.commit(None).unwrap();
    let path = workspace.project_dir("yorimichi").join("main.json");
    fs::write(&path, b"{ not json").unwrap();

    let error = store.root(&RootKind::Main).unwrap_err();
    assert!(
        matches!(error, RootError::Damaged(_)),
        "unexpected: {error}"
    );
    let view = store.retention().unwrap();
    assert_eq!(view.damaged.len(), 1);
    assert_eq!(fs::read(&path).unwrap(), b"{ not json");
}

#[test]
fn a_record_filed_under_another_target_fails_the_listing() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    let pin = RootKind::Pin { id: "kept".into() };
    let mut session = begin(&store, pin, "pin", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.commit(None).unwrap();
    let base = workspace.project_dir("yorimichi");
    fs::copy(base.join("pin/kept.json"), base.join("worktree/kept.json")).unwrap();

    let error = store.roots().unwrap_err();
    assert!(
        matches!(error, RootError::Damaged(_)),
        "unexpected: {error}"
    );
}

#[test]
fn retention_counts_root_and_open_session_keys() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.commit(None).unwrap();
    let mut open = begin(&store, RootKind::Main, "second", 1);
    open.use_result("unit.b", &key(2)).unwrap();

    let view = store.retention().unwrap();
    assert_eq!(
        view.keys.iter().cloned().collect::<Vec<_>>(),
        vec![key(1), key(2)]
    );
    assert!(view.damaged.is_empty());
}

#[test]
fn abandoning_a_session_releases_only_its_own_in_flight_retention() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.commit(None).unwrap();

    let mut abandoned = begin(&store, RootKind::Main, "abandoned", 1);
    abandoned.use_result("unit.b", &key(2)).unwrap();
    assert!(store.retention().unwrap().keys.contains(&key(2)));
    abandoned.abandon().unwrap();

    assert!(session_files(&workspace.store(), "yorimichi").is_empty());
    let view = store.retention().unwrap();
    assert_eq!(view.keys.iter().cloned().collect::<Vec<_>>(), vec![key(1)]);
    let root = store.root(&RootKind::Main).unwrap().unwrap();
    assert_eq!(root.entries.len(), 1);
    assert_eq!(root.entries["unit.a"].key, key(1));
}

#[cfg(target_os = "macos")]
#[test]
fn b2_publication_and_hit_callbacks_record_the_caller_unit_binding() {
    let workspace = Workspace::new();
    let results = ResultStore::open(workspace.store()).unwrap();
    let roots = workspace.open("yorimichi");
    let unit = prepared("unit.alpha");
    let output = workspace.0.join("out");
    fs::create_dir_all(&output).unwrap();
    fs::write(output.join("result.bin"), b"payload").unwrap();
    let mut session = begin(&roots, RootKind::Main, "build", 1);

    let transaction = results
        .begin(
            &unit,
            provenance("build"),
            process(1),
            vec![],
            BTreeSet::new(),
        )
        .unwrap();
    let staged = transaction
        .stage(
            BTreeMap::from([(
                ("data".to_string(), "result.bin".to_string()),
                output.join("result.bin"),
            )]),
            |_| Ok(()),
        )
        .unwrap();
    let published = staged
        .publish(session.root_callback("caller.unit"))
        .unwrap();
    assert_eq!(published.result.key, unit.key());

    let hit = results
        .begin(
            &unit,
            provenance("hit"),
            process(2),
            vec![],
            BTreeSet::new(),
        )
        .unwrap();
    let reused = hit.retain_hit(session.root_callback("caller.hit")).unwrap();
    assert_eq!(reused.result.key, unit.key());
    assert_eq!(
        reused.result.unit, "unit.alpha",
        "the winner keeps its own diagnostic unit, which is never the journal binding"
    );

    let journal = fs::read_to_string(only_session(&workspace.store(), "yorimichi")).unwrap();
    let lines: Vec<&str> = journal.lines().collect();
    assert_eq!(lines.len(), 3, "one header and two appended records");
    assert!(
        lines[1].contains("\"unit\":\"caller.unit\""),
        "{}",
        lines[1]
    );
    assert!(lines[1].contains(unit.key()), "{}", lines[1]);
    assert!(lines[2].contains("\"unit\":\"caller.hit\""), "{}", lines[2]);
    assert!(lines[2].contains(unit.key()), "{}", lines[2]);
    assert!(
        !lines[1].contains("unit.alpha") && !lines[2].contains("unit.alpha"),
        "the journal binding must come from the caller, never the winning envelope"
    );

    fs::remove_file(only_session(&workspace.store(), "yorimichi")).unwrap();
    let transaction = results
        .begin(
            &unit,
            provenance("broken"),
            process(3),
            vec![],
            BTreeSet::new(),
        )
        .unwrap();
    let lease_id = transaction.lease().id.clone();
    let staged = transaction
        .stage(
            BTreeMap::from([(
                ("data".to_string(), "result.bin".to_string()),
                output.join("result.bin"),
            )]),
            |_| Ok(()),
        )
        .unwrap();
    let error = staged
        .publish(session.root_callback("caller.broken"))
        .unwrap_err();
    assert!(matches!(error, ResultError::Root(_)), "unexpected: {error}");
    let records = results.leases().lock().unwrap().leases().unwrap();
    let lease = records.iter().find(|record| record.id == lease_id).unwrap();
    assert!(lease.result_keys.contains(unit.key()));
    assert!(
        !lease.rooted,
        "a failed root callback must keep the publication claims"
    );
}

#[test]
fn a_dead_custodian_with_unconfirmed_cleanup_is_retained() {
    let custodians = FakeCustodians {
        registered: BTreeMap::from([(2, "corr-2".to_string())]),
        unreadable: false,
    };
    let cleanup = FakeCleanup {
        confirmed: BTreeSet::new(),
        unreadable: false,
    };
    assert_eq!(
        may_reclaim(&lease(1, &[2]), |_| Liveness::Dead, &custodians, &cleanup),
        Reclaim::Retained(RetainReason::CleanupUnconfirmed("corr-2".into())),
        "a dead custodian never proves its guard cleanup ran"
    );
}

#[test]
fn an_owner_custodian_with_unconfirmed_cleanup_is_retained() {
    let custodians = FakeCustodians {
        registered: BTreeMap::from([(1, "corr-owner".to_string())]),
        unreadable: false,
    };
    let cleanup = FakeCleanup {
        confirmed: BTreeSet::new(),
        unreadable: false,
    };
    assert_eq!(
        may_reclaim(&lease(1, &[2]), |_| Liveness::Dead, &custodians, &cleanup),
        Reclaim::Retained(RetainReason::CleanupUnconfirmed("corr-owner".into())),
        "the owner's custodian cleanup is checked too"
    );
}

#[test]
fn a_draining_child_retains_until_its_cleanup_is_confirmed() {
    // The real scenario: controller and loop worker are dead, the registered custodian is dead,
    // and its cleanup is unconfirmed because a child is still draining.
    let custodians = FakeCustodians {
        registered: BTreeMap::from([(3, "corr-custodian".to_string())]),
        unreadable: false,
    };
    let mut cleanup = FakeCleanup {
        confirmed: BTreeSet::new(),
        unreadable: false,
    };
    let record = lease(1, &[2, 3]);
    assert_eq!(
        may_reclaim(&record, |_| Liveness::Dead, &custodians, &cleanup),
        Reclaim::Retained(RetainReason::CleanupUnconfirmed("corr-custodian".into()))
    );
    cleanup.confirmed.insert("corr-custodian".into());
    assert_eq!(
        may_reclaim(&record, |_| Liveness::Dead, &custodians, &cleanup),
        Reclaim::Reclaimable
    );
}

#[test]
fn a_dead_custodian_with_confirmed_cleanup_is_reclaimable() {
    let custodians = FakeCustodians {
        registered: BTreeMap::from([(2, "corr-2".to_string())]),
        unreadable: false,
    };
    let cleanup = FakeCleanup {
        confirmed: BTreeSet::from(["corr-2".to_string()]),
        unreadable: false,
    };
    assert_eq!(
        may_reclaim(
            &lease(1, &[2, 3]),
            |_| Liveness::Dead,
            &custodians,
            &cleanup
        ),
        Reclaim::Reclaimable
    );
}

#[test]
fn an_unreadable_custodian_or_cleanup_record_is_retained() {
    let cleanup = FakeCleanup {
        confirmed: BTreeSet::from(["corr-2".to_string()]),
        unreadable: false,
    };
    let unreadable_registry = FakeCustodians {
        registered: BTreeMap::new(),
        unreadable: true,
    };
    assert!(matches!(
        may_reclaim(
            &lease(1, &[2]),
            |_| Liveness::Dead,
            &unreadable_registry,
            &cleanup
        ),
        Reclaim::Retained(RetainReason::CustodianRecordUnreadable(_))
    ));

    let custodians = FakeCustodians {
        registered: BTreeMap::from([(2, "corr-2".to_string())]),
        unreadable: false,
    };
    let unreadable_cleanup = FakeCleanup {
        confirmed: BTreeSet::new(),
        unreadable: true,
    };
    assert!(matches!(
        may_reclaim(
            &lease(1, &[2]),
            |_| Liveness::Dead,
            &custodians,
            &unreadable_cleanup
        ),
        Reclaim::Retained(RetainReason::CustodianRecordUnreadable(_))
    ));
}

#[test]
fn alive_or_unknown_identities_still_retain_the_lease() {
    assert_eq!(
        may_reclaim(
            &lease(1, &[2]),
            |identity| if identity.pid == 1 {
                Liveness::Alive
            } else {
                Liveness::Dead
            },
            &no_custodians(),
            &no_cleanup(),
        ),
        Reclaim::Retained(RetainReason::IdentityNotConfirmedDead)
    );
    assert_eq!(
        may_reclaim(
            &lease(1, &[2]),
            |identity| if identity.pid == 2 {
                Liveness::Unknown
            } else {
                Liveness::Dead
            },
            &no_custodians(),
            &no_cleanup(),
        ),
        Reclaim::Retained(RetainReason::IdentityNotConfirmedDead)
    );
}

#[test]
fn missing_store_root_is_refused() {
    let workspace = Workspace::new();
    let error = RootStore::open(workspace.store(), "yorimichi").unwrap_err();
    assert!(
        matches!(error, RootError::Invalid(_)),
        "a missing store root must be refused: {error}"
    );
    assert!(!workspace.store().exists());
}

#[test]
fn retention_is_readable_under_the_callers_guard() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.commit(None).unwrap();

    let guard = store.leases().lock().unwrap();
    let view = store.retention_locked(&guard).unwrap();
    assert!(view.keys.contains(&key(1)));
    assert!(
        guard.leases().unwrap().is_empty(),
        "same guard, no second flock"
    );
}

#[test]
fn a_hit_release_is_visible_to_a_guarded_gc_read() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();

    // A key that only the session journal retains yet must still be visible to a GC that holds
    // the single metadata guard across its retention and lease reads.
    let guard = store.leases().lock().unwrap();
    let view = store.retention_locked(&guard).unwrap();
    assert!(view.keys.contains(&key(1)));
    assert!(guard.leases().unwrap().is_empty());
    drop(guard);

    session.commit(None).unwrap();
    assert!(store.retention().unwrap().keys.contains(&key(1)));
}

#[test]
fn missing_or_unreadable_metadata_is_damage() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.commit(None).unwrap();
    let project = workspace.project_dir("yorimichi");

    fs::set_permissions(&project, fs::Permissions::from_mode(0o000)).unwrap();
    let view = store.retention().unwrap();
    assert!(
        !view.damaged.is_empty(),
        "unreadable metadata must be damage"
    );
    fs::set_permissions(&project, fs::Permissions::from_mode(0o755)).unwrap();

    fs::remove_dir_all(workspace.store().join("roots")).unwrap();
    let view = store.retention().unwrap();
    assert_eq!(view.damaged.len(), 1, "a missing roots tree is damage");
}

#[test]
fn a_guard_from_another_store_is_refused() {
    let first = Workspace::new();
    let second = Workspace::new();
    let alpha = first.open("yorimichi");
    let beta = second.open("yorimichi");
    let guard = alpha.leases().lock().unwrap();
    assert!(matches!(
        beta.retention_locked(&guard),
        Err(RootError::Invalid(_))
    ));
    assert!(matches!(
        beta.roots_locked(&guard),
        Err(RootError::Invalid(_))
    ));
    assert!(alpha.retention_locked(&guard).is_ok());
    assert!(alpha.roots_locked(&guard).is_ok());
}

#[test]
fn reopening_a_project_with_missing_metadata_is_damage() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.commit(None).unwrap();
    fs::remove_dir_all(workspace.project_dir("yorimichi").join("session")).unwrap();

    let error = RootStore::open(workspace.store(), "yorimichi").unwrap_err();
    assert!(
        matches!(error, RootError::Damaged(_)),
        "reopening must not recreate lost metadata: {error}"
    );
    assert!(!workspace.project_dir("yorimichi").join("session").exists());
}

#[test]
fn retention_reports_a_missing_selected_project() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.commit(None).unwrap();
    fs::remove_dir_all(workspace.project_dir("yorimichi")).unwrap();

    let view = store.retention().unwrap();
    assert!(
        !view.damaged.is_empty(),
        "a vanished project must not look like empty retention"
    );
    assert!(view.keys.is_empty());
}

#[test]
fn retention_reports_a_missing_unselected_project() {
    let workspace = Workspace::new();
    let alpha = workspace.open("alpha");
    let beta = workspace.open("beta");
    let mut session = begin(&beta, RootKind::Main, "beta", 1);
    session.use_result("unit.beta", &key(2)).unwrap();
    session.commit(None).unwrap();
    fs::remove_dir_all(workspace.project_dir("beta")).unwrap();

    let view = alpha.retention().unwrap();
    assert!(
        !view.damaged.is_empty(),
        "another project's lost directory must not certify a clean store-wide view"
    );
}

#[test]
fn a_fresh_open_of_a_deleted_project_is_damage() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.commit(None).unwrap();
    drop(store);
    fs::remove_dir_all(workspace.project_dir("yorimichi")).unwrap();

    let error = RootStore::open(workspace.store(), "yorimichi").unwrap_err();
    assert!(
        matches!(error, RootError::Damaged(_)),
        "a deleted project must never look like a fresh one: {error}"
    );
    assert!(
        !workspace.project_dir("yorimichi").exists(),
        "a fresh open must not recreate a registered project"
    );
}

#[test]
fn a_fresh_open_after_roots_is_deleted_is_damage() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.commit(None).unwrap();
    drop(store);
    fs::remove_dir_all(workspace.store().join("roots")).unwrap();

    let error = RootStore::open(workspace.store(), "yorimichi").unwrap_err();
    assert!(
        matches!(error, RootError::Damaged(_)),
        "losing all of roots/ must be damage: {error}"
    );
    assert!(
        !workspace.store().join("roots").exists(),
        "a fresh open must not recreate roots/"
    );
}

#[test]
fn a_missing_registry_with_roots_present_is_damage() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    drop(store);
    fs::remove_file(workspace.store().join("meta").join("projects.json")).unwrap();

    let error = RootStore::open(workspace.store(), "yorimichi").unwrap_err();
    assert!(
        matches!(error, RootError::Damaged(_)),
        "roots/ without its registry must be damage: {error}"
    );
}

#[test]
fn a_first_open_registers_the_project() {
    let workspace = Workspace::new();
    workspace.open("yorimichi");
    let registry =
        fs::read_to_string(workspace.store().join("meta").join("projects.json")).unwrap();
    assert!(registry.contains("yorimichi"), "{registry}");

    // A second project in the same store is a genuine first use, and it keeps the first record.
    let store = workspace.open("hidamari");
    assert_eq!(store.project(), "hidamari");
    let registry =
        fs::read_to_string(workspace.store().join("meta").join("projects.json")).unwrap();
    assert!(registry.contains("yorimichi"), "{registry}");
    assert!(registry.contains("hidamari"), "{registry}");

    RootStore::open(workspace.store(), "yorimichi").unwrap();
}

#[test]
fn crash_temporary_file_is_swept_and_does_not_damage() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    let leftover = workspace.project_dir("yorimichi").join("tmp/999-1.tmp");
    fs::write(&leftover, b"half written root").unwrap();

    let view = store.retention().unwrap();
    assert!(view.damaged.is_empty(), "tmp leftovers are not damage");
    assert!(store.roots().unwrap().is_empty());
    session.commit(None).unwrap();
    assert!(!leftover.exists(), "the lock holder sweeps stale temps");
}

#[test]
fn an_empty_session_journal_is_damage_and_retains() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    let path = workspace
        .project_dir("yorimichi")
        .join("session/crashed.jsonl");
    fs::write(&path, b"").unwrap();

    let view = store.retention().unwrap();
    assert_eq!(view.damaged.len(), 1);
    assert!(view.keys.is_empty());
    assert!(store.sessions().is_err(), "damaged journals fail closed");
}

#[test]
fn sessions_release_only_a_confirmed_dead_owner() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    let mut first = begin(&store, RootKind::Main, "first", 77);
    first.use_result("unit.a", &key(1)).unwrap();
    let first_id = session_id(&only_session(&workspace.store(), "yorimichi"));
    let sessions = store.sessions().unwrap();
    assert_eq!(sessions.len(), 1);
    assert_eq!(sessions[0].owner, process(77));
    assert_eq!(sessions[0].entries.len(), 1);

    assert_eq!(
        store
            .release_dead_session(
                &first_id,
                |_| Liveness::Dead,
                &no_custodians(),
                &no_cleanup()
            )
            .unwrap(),
        Reclaim::Reclaimable
    );
    assert!(session_files(&workspace.store(), "yorimichi").is_empty());

    let mut second = begin(&store, RootKind::Main, "second", 78);
    second.use_result("unit.a", &key(1)).unwrap();
    let second_id = session_id(&only_session(&workspace.store(), "yorimichi"));
    assert_eq!(
        store
            .release_dead_session(
                &second_id,
                |_| Liveness::Alive,
                &no_custodians(),
                &no_cleanup()
            )
            .unwrap(),
        Reclaim::Retained(RetainReason::IdentityNotConfirmedDead)
    );
    assert!(only_session(&workspace.store(), "yorimichi").exists());

    let custodians = FakeCustodians {
        registered: BTreeMap::from([(78, "corr-78".to_string())]),
        unreadable: false,
    };
    assert_eq!(
        store
            .release_dead_session(&second_id, |_| Liveness::Dead, &custodians, &no_cleanup())
            .unwrap(),
        Reclaim::Retained(RetainReason::CleanupUnconfirmed("corr-78".into()))
    );
    let confirmed = FakeCleanup {
        confirmed: BTreeSet::from(["corr-78".to_string()]),
        unreadable: false,
    };
    assert_eq!(
        store
            .release_dead_session(&second_id, |_| Liveness::Dead, &custodians, &confirmed)
            .unwrap(),
        Reclaim::Reclaimable
    );
    assert!(session_files(&workspace.store(), "yorimichi").is_empty());
}

#[test]
fn a_failed_append_leaves_the_journal_unchanged() {
    let workspace = Workspace::new();
    let store = workspace.open("yorimichi");
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    let journal = only_session(&workspace.store(), "yorimichi");
    let before = fs::read(&journal).unwrap();
    fs::set_permissions(&journal, fs::Permissions::from_mode(0o444)).unwrap();

    assert!(session.use_result("unit.b", &key(2)).is_err());
    assert_eq!(fs::read(&journal).unwrap(), before, "no torn tail is left");
    fs::set_permissions(&journal, fs::Permissions::from_mode(0o644)).unwrap();
    assert_eq!(store.retention().unwrap().keys.len(), 1);
}

#[test]
fn a_roster_requires_a_complete_validated_declaration() {
    let declared = declaration(&["unit.a", "unit.b"]);
    let partial = ValidatedDeclaration {
        order: vec!["unit.a".into()],
        files: vec![],
    };
    assert!(DeclaredRoster::from_validated(&declared, &partial).is_err());

    let empty_declaration = declaration(&[]);
    let empty = ValidatedDeclaration {
        order: vec![],
        files: vec![],
    };
    assert!(DeclaredRoster::from_validated(&empty_declaration, &empty).is_err());

    let roster =
        DeclaredRoster::from_validated(&declared, &validated(&["unit.a", "unit.b"])).unwrap();
    assert!(roster.contains("unit.a") && roster.contains("unit.b"));
    assert_eq!(roster.digest().len(), 64);
}

// ---- B4b: coarse recent use, first-observed grace and the read-only readers ----

#[derive(Debug)]
struct TestClock(std::sync::Mutex<std::time::SystemTime>);

impl TestClock {
    fn at(seconds: u64) -> Arc<Self> {
        Arc::new(Self(std::sync::Mutex::new(
            std::time::UNIX_EPOCH + std::time::Duration::from_secs(seconds),
        )))
    }
    fn set(&self, seconds: u64) {
        *self.0.lock().unwrap() = std::time::UNIX_EPOCH + std::time::Duration::from_secs(seconds);
    }
}

impl Clock for TestClock {
    fn now(&self) -> std::time::SystemTime {
        *self.0.lock().unwrap()
    }
}

impl Workspace {
    fn open_at(&self, project: &str, clock: &Arc<TestClock>) -> RootStore {
        fs::create_dir_all(self.store()).unwrap();
        RootStore::open_with_clock(self.store(), project, Arc::clone(clock) as Arc<dyn Clock>)
            .unwrap()
    }
}

fn usage_file(workspace: &Workspace) -> PathBuf {
    workspace.store().join("usage.json")
}

fn usage_bytes(workspace: &Workspace) -> Option<Vec<u8>> {
    fs::read(usage_file(workspace)).ok()
}

fn usage_of(store: &RootStore) -> UsageView {
    let guard = store.leases().lock().unwrap();
    store.usage_locked(&guard).unwrap()
}

fn digest(fill: &str) -> ObjectDigest {
    ObjectDigest::from_hex(&fill.repeat(64)).unwrap()
}

#[test]
fn a_use_bucket_rounds_the_utc_day_up() {
    let midnight = UseBucket::ceil_day(std::time::UNIX_EPOCH).unwrap();
    assert_eq!(midnight.as_str(), "1970-01-01");
    let one_millisecond =
        UseBucket::ceil_day(std::time::UNIX_EPOCH + std::time::Duration::from_millis(1)).unwrap();
    assert_eq!(
        one_millisecond.as_str(),
        "1970-01-02",
        "sub-second precision must round up, not truncate"
    );
    let one_second =
        UseBucket::ceil_day(std::time::UNIX_EPOCH + std::time::Duration::from_secs(1)).unwrap();
    assert_eq!(one_second.as_str(), "1970-01-02");
    let next_midnight =
        UseBucket::ceil_day(std::time::UNIX_EPOCH + std::time::Duration::from_secs(86_400))
            .unwrap();
    assert_eq!(next_midnight.as_str(), "1970-01-02");
    let next_midnight_plus_one = UseBucket::ceil_day(
        std::time::UNIX_EPOCH
            + std::time::Duration::from_secs(86_400)
            + std::time::Duration::from_nanos(1),
    )
    .unwrap();
    assert_eq!(next_midnight_plus_one.as_str(), "1970-01-03");
    assert!(UseBucket::parse("2024-02-29").is_ok());
    assert!(UseBucket::parse("2026-02-29").is_err());
    assert!(UseBucket::parse("2026-13-01").is_err());
    assert!(UseBucket::parse("26-01-01").is_err());
}

#[test]
fn usage_keeps_the_newest_bucket_on_rollback() {
    let workspace = Workspace::new();
    let clock = TestClock::at(86_400);
    let store = workspace.open_at("yorimichi", &clock);
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.commit(None).unwrap();
    assert_eq!(
        usage_of(&store).results[&key(1)].as_str(),
        "1970-01-02",
        "the append records the round-up day"
    );

    clock.set(0);
    let mut rolled_back = begin(&store, RootKind::Main, "second", 1);
    rolled_back.use_result("unit.a", &key(1)).unwrap();
    rolled_back.commit(None).unwrap();
    assert_eq!(
        usage_of(&store).results[&key(1)].as_str(),
        "1970-01-02",
        "a clock rollback must never age a result"
    );
}

#[test]
fn a_future_bucket_is_kept() {
    let workspace = Workspace::new();
    let clock = TestClock::at(10 * 86_400);
    let store = workspace.open_at("yorimichi", &clock);
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.commit(None).unwrap();
    assert_eq!(usage_of(&store).results[&key(1)].as_str(), "1970-01-11");

    clock.set(2 * 86_400);
    let mut earlier = begin(&store, RootKind::Main, "second", 1);
    earlier.use_result("unit.a", &key(1)).unwrap();
    earlier.commit(None).unwrap();
    assert_eq!(
        usage_of(&store).results[&key(1)].as_str(),
        "1970-01-11",
        "a future bucket is kept, never aged down"
    );
}

#[test]
fn a_legacy_journal_entry_has_unknown_age() {
    use std::io::Write;
    let workspace = Workspace::new();
    let clock = TestClock::at(86_400);
    let store = workspace.open_at("yorimichi", &clock);
    let mut session = begin(&store, RootKind::Main, "legacy", 1);
    let journal = only_session(&workspace.store(), "yorimichi");
    let mut file = fs::OpenOptions::new().append(true).open(&journal).unwrap();
    writeln!(file, "{{\"unit\":\"unit.legacy\",\"key\":\"{}\"}}", key(9)).unwrap();
    drop(file);
    session.use_result("unit.a", &key(1)).unwrap();

    let view = usage_of(&store);
    assert!(view.damaged.is_empty(), "{:?}", view.damaged);
    assert!(
        !view.results.contains_key(&key(9)),
        "an entry without a bucket is unknown age, not a made-up date"
    );
    assert_eq!(view.results[&key(1)].as_str(), "1970-01-02");

    session.commit(None).unwrap();
    let view = usage_of(&store);
    assert!(!view.results.contains_key(&key(9)));
}

#[test]
fn usage_is_folded_once_per_commit_not_per_append() {
    let workspace = Workspace::new();
    let clock = TestClock::at(86_400);
    let store = workspace.open_at("yorimichi", &clock);
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    assert!(
        usage_bytes(&workspace).is_none(),
        "an append alone must never write usage"
    );
    session.use_result("unit.b", &key(2)).unwrap();
    assert!(usage_bytes(&workspace).is_none());
    session.commit(None).unwrap();
    let first = usage_bytes(&workspace).expect("the commit folds once");
    let view = usage_of(&store);
    assert!(view.results.contains_key(&key(1)));
    assert!(view.results.contains_key(&key(2)));

    let mut again = begin(&store, RootKind::Main, "second", 1);
    again.use_result("unit.a", &key(1)).unwrap();
    again.commit(None).unwrap();
    assert_eq!(
        usage_bytes(&workspace).unwrap(),
        first,
        "a commit that adds no newer bucket writes nothing"
    );
}

#[test]
fn the_usage_readers_and_open_existing_write_nothing() {
    let workspace = Workspace::new();
    let clock = TestClock::at(86_400);
    let store = workspace.open_at("yorimichi", &clock);
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.commit(None).unwrap();
    let mut open = begin(&store, RootKind::Main, "second", 1);
    open.use_result("unit.b", &key(2)).unwrap();

    let journal = only_session(&workspace.store(), "yorimichi");
    let usage_before = usage_bytes(&workspace).unwrap();
    let usage_mtime = fs::metadata(usage_file(&workspace))
        .unwrap()
        .modified()
        .unwrap();
    let journal_bytes = fs::read(&journal).unwrap();
    let journal_mtime = fs::metadata(&journal).unwrap().modified().unwrap();

    {
        let guard = store.leases().lock().unwrap();
        store.usage_locked(&guard).unwrap();
        store.all_project_retention_locked(&guard).unwrap();
    }
    RootStore::open_existing(workspace.store(), "yorimichi").unwrap();
    RootStore::open_existing_with_clock(
        workspace.store(),
        "yorimichi",
        Arc::clone(&clock) as Arc<dyn Clock>,
    )
    .unwrap();

    assert_eq!(usage_bytes(&workspace).unwrap(), usage_before);
    assert_eq!(
        fs::metadata(usage_file(&workspace))
            .unwrap()
            .modified()
            .unwrap(),
        usage_mtime,
        "the readers must not rewrite usage.json"
    );
    assert_eq!(fs::read(&journal).unwrap(), journal_bytes);
    assert_eq!(
        fs::metadata(&journal).unwrap().modified().unwrap(),
        journal_mtime,
        "the readers must not touch an open journal"
    );
}

#[test]
fn usage_damage_is_visible_to_the_caller() {
    let workspace = Workspace::new();
    let clock = TestClock::at(86_400);
    let store = workspace.open_at("yorimichi", &clock);
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.commit(None).unwrap();
    fs::write(usage_file(&workspace), b"{not json").unwrap();

    let view = usage_of(&store);
    assert!(
        !view.damaged.is_empty(),
        "a partial usage view must never look complete"
    );
}

#[test]
fn observe_objects_is_write_once() {
    let workspace = Workspace::new();
    let clock = TestClock::at(86_400);
    let store = workspace.open_at("yorimichi", &clock);
    let digest = digest("a");
    let mut objects = BTreeSet::new();
    objects.insert(digest.clone());
    {
        let guard = store.leases().lock().unwrap();
        store.observe_objects_locked(&guard, &objects).unwrap();
    }
    assert_eq!(
        usage_of(&store).observed[digest.as_hex()].as_str(),
        "1970-01-02"
    );

    clock.set(5 * 86_400);
    {
        let guard = store.leases().lock().unwrap();
        store.observe_objects_locked(&guard, &objects).unwrap();
    }
    assert_eq!(
        usage_of(&store).observed[digest.as_hex()].as_str(),
        "1970-01-02",
        "first-observed is write-once and never refreshed"
    );
}

#[test]
fn forgetting_usage_is_persisted_before_any_unlink() {
    let workspace = Workspace::new();
    let clock = TestClock::at(86_400);
    let store = workspace.open_at("yorimichi", &clock);
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.commit(None).unwrap();
    let digest = digest("b");
    let mut objects = BTreeSet::new();
    objects.insert(digest.clone());
    let mut results = BTreeSet::new();
    results.insert(key(1));
    {
        let guard = store.leases().lock().unwrap();
        store.observe_objects_locked(&guard, &objects).unwrap();
        store
            .forget_usage_locked(&guard, &results, &objects)
            .unwrap();
    }
    let view = usage_of(&store);
    assert!(
        !view.results.contains_key(&key(1)),
        "forgetting is durable before the caller unlinks anything"
    );
    assert!(!view.observed.contains_key(digest.as_hex()));

    clock.set(3 * 86_400);
    {
        let guard = store.leases().lock().unwrap();
        store.observe_objects_locked(&guard, &objects).unwrap();
    }
    assert_eq!(
        usage_of(&store).observed[digest.as_hex()].as_str(),
        "1970-01-04",
        "a republished digest starts fresh"
    );
}

#[test]
fn a_dead_sessions_recent_use_survives_its_release() {
    let workspace = Workspace::new();
    let clock = TestClock::at(86_400);
    let store = workspace.open_at("yorimichi", &clock);
    let mut session = begin(&store, RootKind::Main, "dead", 4_242);
    session.use_result("unit.a", &key(1)).unwrap();
    let id = session_id(&only_session(&workspace.store(), "yorimichi"));

    let verdict = store
        .release_dead_session(&id, |_| Liveness::Dead, &no_custodians(), &no_cleanup())
        .unwrap();
    assert_eq!(verdict, Reclaim::Reclaimable);
    assert!(
        !workspace
            .project_dir("yorimichi")
            .join("session")
            .join(format!("{id}.jsonl"))
            .exists()
    );
    assert_eq!(
        usage_of(&store).results[&key(1)].as_str(),
        "1970-01-02",
        "the released journal's use is folded before it is removed"
    );
}

#[test]
fn the_all_project_reader_sees_every_project() {
    let workspace = Workspace::new();
    let clock = TestClock::at(86_400);
    let alpha = workspace.open_at("alpha", &clock);
    let beta = workspace.open_at("beta", &clock);
    let mut session = begin(&alpha, RootKind::Main, "alpha", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.commit(None).unwrap();
    let mut session = begin(&beta, RootKind::Main, "beta", 1);
    session.use_result("unit.beta", &key(2)).unwrap();
    session.commit(None).unwrap();

    {
        let guard = alpha.leases().lock().unwrap();
        let all = alpha.all_project_retention_locked(&guard).unwrap();
        assert!(all.projects["alpha"].keys.contains(&key(1)));
        assert!(all.projects["beta"].keys.contains(&key(2)));
        assert!(all.damaged.is_empty(), "{:?}", all.damaged);
    }

    fs::remove_dir_all(workspace.project_dir("beta")).unwrap();
    let guard = alpha.leases().lock().unwrap();
    let all = alpha.all_project_retention_locked(&guard).unwrap();
    assert!(
        !all.damaged.is_empty(),
        "a missing project must not look like an empty one"
    );
}

#[test]
fn the_usage_readers_refuse_a_foreign_guard() {
    let workspace = Workspace::new();
    let other = Workspace::new();
    let clock = TestClock::at(0);
    let alpha = workspace.open_at("alpha", &clock);
    let beta = other.open_at("beta", &clock);
    let mut objects = BTreeSet::new();
    objects.insert(digest("c"));

    let guard = alpha.leases().lock().unwrap();
    assert!(beta.usage_locked(&guard).is_err());
    assert!(beta.all_project_retention_locked(&guard).is_err());
    assert!(beta.observe_objects_locked(&guard, &objects).is_err());
    assert!(
        beta.forget_usage_locked(&guard, &BTreeSet::new(), &objects)
            .is_err()
    );
}

#[test]
fn two_open_sessions_on_one_target_keep_the_other_journal() {
    let workspace = Workspace::new();
    let clock = TestClock::at(86_400);
    let store = workspace.open_at("yorimichi", &clock);
    let mut first = begin(&store, RootKind::Main, "first", 1);
    first.use_result("unit.a", &key(1)).unwrap();
    let mut second = begin(&store, RootKind::Main, "second", 1);
    second.use_result("unit.b", &key(2)).unwrap();
    first.commit(None).unwrap();

    let journal = only_session(&workspace.store(), "yorimichi");
    let text = fs::read_to_string(&journal).unwrap();
    assert!(
        text.contains(&key(2)),
        "the other session's journal survives"
    );
    assert!(
        usage_of(&store).results.contains_key(&key(2)),
        "an open session's use is still visible while it runs"
    );
}

#[test]
fn open_existing_creates_nothing() {
    use std::os::unix::fs::MetadataExt;
    let workspace = Workspace::new();
    fs::create_dir_all(workspace.store()).unwrap();
    let error = RootStore::open_existing(workspace.store(), "yorimichi").unwrap_err();
    assert!(
        matches!(error, RootError::Damaged(_)),
        "an uninitialized project is damage, not a first use: {error}"
    );
    assert!(!workspace.store().join("roots").exists());
    assert!(!workspace.store().join("meta").exists());
    assert!(
        !workspace.store().join("leases").exists(),
        "a refusal must not create the lease directory"
    );
    assert!(
        !workspace.store().join("staging").exists(),
        "a refusal must not create the staging directory"
    );
    assert!(
        !workspace.store().join("metadata.lock").exists(),
        "a refusal must not create the metadata mutex"
    );

    let clock = TestClock::at(0);
    let _store = workspace.open_at("yorimichi", &clock);
    let lock = workspace.store().join("metadata.lock");
    let before = fs::metadata(&lock).unwrap();
    let (inode, mtime) = (before.ino(), before.modified().unwrap());
    RootStore::open_existing(workspace.store(), "yorimichi").unwrap();
    let after = fs::metadata(&lock).unwrap();
    assert_eq!(
        after.ino(),
        inode,
        "the read path must not replace the mutex"
    );
    assert_eq!(
        after.modified().unwrap(),
        mtime,
        "the read path must not rewrite the mutex"
    );
}

#[test]
fn an_unknown_age_entry_invalidates_a_stored_bucket() {
    use std::io::Write;
    let workspace = Workspace::new();
    let clock = TestClock::at(86_400);
    let store = workspace.open_at("yorimichi", &clock);
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.commit(None).unwrap();
    assert_eq!(usage_of(&store).results[&key(1)].as_str(), "1970-01-02");

    let legacy = begin(&store, RootKind::Main, "legacy", 1);
    let journal = only_session(&workspace.store(), "yorimichi");
    let mut file = fs::OpenOptions::new().append(true).open(&journal).unwrap();
    writeln!(file, "{{\"unit\":\"unit.a\",\"key\":\"{}\"}}", key(1)).unwrap();
    drop(file);
    assert!(
        !usage_of(&store).results.contains_key(&key(1)),
        "an unknown use invalidates the stored day"
    );

    legacy.abandon().unwrap();
    assert!(
        !usage_of(&store).results.contains_key(&key(1)),
        "the invalidation is durable after abandon"
    );
}

#[test]
fn a_missing_session_directory_is_reported_by_usage() {
    let workspace = Workspace::new();
    let clock = TestClock::at(86_400);
    let store = workspace.open_at("yorimichi", &clock);
    fs::remove_dir_all(workspace.project_dir("yorimichi").join("session")).unwrap();
    let view = usage_of(&store);
    assert!(
        !view.damaged.is_empty(),
        "a vanished session directory must not read as clean"
    );
}

#[test]
fn a_damaged_journal_surfaces_and_is_not_unlinked() {
    let workspace = Workspace::new();
    let clock = TestClock::at(86_400);
    let store = workspace.open_at("yorimichi", &clock);
    let session = begin(&store, RootKind::Main, "torn", 1);
    let journal = only_session(&workspace.store(), "yorimichi");
    let mut text = fs::read_to_string(&journal).unwrap();
    text.push_str("{\"unit\":\"unit.a\",\"key\":\"");
    fs::write(&journal, text).unwrap();

    assert!(
        !usage_of(&store).damaged.is_empty(),
        "a torn journal is damage, not silence"
    );
    assert!(
        session.abandon().is_err(),
        "abandon must refuse to erase a damaged journal"
    );
    assert!(journal.exists(), "the damaged journal stays for retention");
}

#[test]
fn an_unknown_marker_survives_the_journal_that_created_it() {
    use std::io::Write;
    let workspace = Workspace::new();
    let clock = TestClock::at(86_400);
    let store = workspace.open_at("yorimichi", &clock);
    let mut stored = begin(&store, RootKind::Main, "stored", 1);
    stored.use_result("unit.a", &key(1)).unwrap();
    stored.commit(None).unwrap();
    assert_eq!(usage_of(&store).results[&key(1)].as_str(), "1970-01-02");
    let mut dated = begin(&store, RootKind::Main, "dated", 1);
    dated.use_result("unit.a", &key(1)).unwrap();
    let dated_journal = only_session(&workspace.store(), "yorimichi");
    let legacy = begin(&store, RootKind::Main, "legacy", 1);
    let legacy_journal = session_files(&workspace.store(), "yorimichi")
        .into_iter()
        .find(|path| path != &dated_journal)
        .unwrap();
    let mut file = fs::OpenOptions::new()
        .append(true)
        .open(&legacy_journal)
        .unwrap();
    writeln!(file, "{{\"unit\":\"unit.a\",\"key\":\"{}\"}}", key(1)).unwrap();
    drop(file);

    // Releasing the legacy journal folds the unknown floor and removes the journal. The older
    // dated journal is still open, and it must not make the key look known again.
    legacy.abandon().unwrap();
    let view = usage_of(&store);
    assert!(
        !view.results.contains_key(&key(1)),
        "an older dated journal must not resurrect a removed unknown observation"
    );
    assert!(
        view.unknown.contains_key(&key(1)),
        "the unknown floor is persisted"
    );

    dated.commit(None).unwrap();
    assert!(
        !usage_of(&store).results.contains_key(&key(1)),
        "and it survives the commit of the older dated journal too"
    );
}

#[test]
fn a_fold_refuses_to_run_while_any_journal_is_damaged() {
    let workspace = Workspace::new();
    let clock = TestClock::at(86_400);
    let store = workspace.open_at("yorimichi", &clock);
    let torn = begin(&store, RootKind::Main, "torn", 1);
    let torn_journal = only_session(&workspace.store(), "yorimichi");
    let mut text = fs::read_to_string(&torn_journal).unwrap();
    text.push_str("{\"unit\":\"unit.x\",\"key\":\"");
    fs::write(&torn_journal, text).unwrap();

    let mut healthy = begin(&store, RootKind::Main, "healthy", 1);
    healthy.use_result("unit.a", &key(1)).unwrap();
    let healthy_journal = session_files(&workspace.store(), "yorimichi")
        .into_iter()
        .find(|path| path != &torn_journal)
        .unwrap();

    let error = healthy.commit(None).unwrap_err();
    assert!(
        matches!(error, RootError::Damaged(_)),
        "a fold must refuse while any journal is damaged: {error}"
    );
    assert!(
        healthy_journal.exists(),
        "a refused fold must not unlink the healthy journal"
    );
    drop(torn);
}

#[test]
fn the_all_project_reader_aggregates_each_project_damage() {
    let workspace = Workspace::new();
    let clock = TestClock::at(86_400);
    let alpha = workspace.open_at("alpha", &clock);
    let beta = workspace.open_at("beta", &clock);
    fs::write(
        workspace.project_dir("beta").join("stray.txt"),
        b"unexpected",
    )
    .unwrap();

    let guard = alpha.leases().lock().unwrap();
    let all = alpha.all_project_retention_locked(&guard).unwrap();
    assert!(
        !all.projects["beta"].damaged.is_empty(),
        "beta reports its own damage"
    );
    assert!(
        !all.damaged.is_empty(),
        "and the aggregate must not drop it"
    );
}

#[test]
fn dropping_a_root_refuses_before_unlinking_while_usage_is_damaged() {
    let workspace = Workspace::new();
    let clock = TestClock::at(86_400);
    let store = workspace.open_at("yorimichi", &clock);
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.commit(None).unwrap();
    let torn = begin(&store, RootKind::Main, "torn", 1);
    let journal = only_session(&workspace.store(), "yorimichi");
    let mut text = fs::read_to_string(&journal).unwrap();
    text.push_str("{\"unit\":\"unit.x\",\"key\":\"");
    fs::write(&journal, text).unwrap();

    let error = store.drop_root(&RootKind::Main).unwrap_err();
    assert!(
        matches!(error, RootError::Damaged(_)),
        "the fold must refuse first: {error}"
    );
    assert!(
        store.root(&RootKind::Main).unwrap().is_some(),
        "a refused drop must leave the root and its retention intact"
    );
    drop(torn);
}

#[test]
fn a_commit_refuses_before_replacing_or_trimming_while_usage_is_damaged() {
    let workspace = Workspace::new();
    let clock = TestClock::at(86_400);
    let store = workspace.open_at("yorimichi", &clock);
    let worktree = RootKind::Worktree { id: "w1".into() };
    let mut seed = begin(&store, worktree.clone(), "seed", 1);
    seed.use_result("unit.a", &key(1)).unwrap();
    seed.commit(None).unwrap();
    for sequence in 1..=3 {
        let kind = RootKind::Release {
            sequence,
            label: format!("r{sequence}"),
        };
        let mut release = begin(&store, kind, "release", 1);
        release.use_result("unit.a", &key(1)).unwrap();
        release.commit(None).unwrap();
    }

    let _torn = begin(&store, RootKind::Main, "torn", 1);
    let journal = only_session(&workspace.store(), "yorimichi");
    let mut text = fs::read_to_string(&journal).unwrap();
    text.push_str("{\"unit\":\"unit.x\",\"key\":\"");
    fs::write(&journal, text).unwrap();

    let mut replace = begin(&store, worktree.clone(), "replace", 1);
    replace.use_result("unit.a", &key(2)).unwrap();
    let error = replace.commit(None).unwrap_err();
    assert!(
        matches!(error, RootError::Damaged(_)),
        "the fold must refuse the commit: {error}"
    );
    let current = store.root(&worktree).unwrap().unwrap();
    assert_eq!(
        current.entries["unit.a"].key,
        key(1),
        "a refused commit must not replace the existing root"
    );

    let fourth = RootKind::Release {
        sequence: 4,
        label: "r4".into(),
    };
    let mut next = begin(&store, fourth.clone(), "fourth", 1);
    next.use_result("unit.a", &key(1)).unwrap();
    assert!(next.commit(None).is_err());
    assert!(
        store.root(&fourth).unwrap().is_none(),
        "a refused commit must not write a partial release"
    );
    let oldest = RootKind::Release {
        sequence: 1,
        label: "r1".into(),
    };
    assert!(
        store.root(&oldest).unwrap().is_some(),
        "a refused commit must not trim the oldest release"
    );
}

#[test]
fn a_manual_release_trim_refuses_while_usage_is_damaged() {
    let workspace = Workspace::new();
    let clock = TestClock::at(86_400);
    let store = workspace.open_at("yorimichi", &clock);
    for sequence in 1..=3 {
        let kind = RootKind::Release {
            sequence,
            label: format!("r{sequence}"),
        };
        let mut release = begin(&store, kind, "release", 1);
        release.use_result("unit.a", &key(1)).unwrap();
        release.commit(None).unwrap();
    }
    let _torn = begin(&store, RootKind::Main, "torn", 1);
    let journal = only_session(&workspace.store(), "yorimichi");
    let mut text = fs::read_to_string(&journal).unwrap();
    text.push_str("{\"unit\":\"unit.x\",\"key\":\"");
    fs::write(&journal, text).unwrap();

    let error = store.trim_releases().unwrap_err();
    assert!(
        matches!(error, RootError::Damaged(_)),
        "a manual trim must refuse while the store is damaged: {error}"
    );
    for sequence in 1..=3 {
        let kind = RootKind::Release {
            sequence,
            label: format!("r{sequence}"),
        };
        assert!(
            store.root(&kind).unwrap().is_some(),
            "a refused trim must delete nothing"
        );
    }
}

#[test]
fn a_snapshot_refuses_before_trimming_while_usage_is_damaged() {
    let workspace = Workspace::new();
    let clock = TestClock::at(86_400);
    let store = workspace.open_at("yorimichi", &clock);
    let mut main = begin(&store, RootKind::Main, "main", 1);
    main.use_result("unit.a", &key(1)).unwrap();
    main.commit(None).unwrap();
    for sequence in 1..=3 {
        let kind = RootKind::Release {
            sequence,
            label: format!("r{sequence}"),
        };
        let mut release = begin(&store, kind, "release", 1);
        release.use_result("unit.a", &key(1)).unwrap();
        release.commit(None).unwrap();
    }
    let _torn = begin(&store, RootKind::Main, "torn", 1);
    let journal = only_session(&workspace.store(), "yorimichi");
    let mut text = fs::read_to_string(&journal).unwrap();
    text.push_str("{\"unit\":\"unit.x\",\"key\":\"");
    fs::write(&journal, text).unwrap();

    let target = RootKind::Release {
        sequence: 4,
        label: "r4".into(),
    };
    let error = store
        .snapshot(&RootKind::Main, target.clone(), provenance("snap"))
        .unwrap_err();
    assert!(
        matches!(error, RootError::Damaged(_)),
        "a snapshot must refuse while the store is damaged: {error}"
    );
    assert!(
        store.root(&target).unwrap().is_none(),
        "a refused snapshot writes nothing"
    );
    let oldest = RootKind::Release {
        sequence: 1,
        label: "r1".into(),
    };
    assert!(
        store.root(&oldest).unwrap().is_some(),
        "a refused snapshot trims nothing"
    );
}

#[test]
fn a_damaged_usage_record_refuses_a_root_drop() {
    let workspace = Workspace::new();
    let clock = TestClock::at(86_400);
    let store = workspace.open_at("yorimichi", &clock);
    let mut session = begin(&store, RootKind::Main, "first", 1);
    session.use_result("unit.a", &key(1)).unwrap();
    session.commit(None).unwrap();
    fs::write(usage_file(&workspace), b"{not json").unwrap();

    let error = store.drop_root(&RootKind::Main).unwrap_err();
    assert!(
        matches!(error, RootError::Damaged(_)),
        "a damaged usage record must refuse the drop: {error}"
    );
    assert!(
        store.root(&RootKind::Main).unwrap().is_some(),
        "the root stays when usage cannot be trusted"
    );
}

#[test]
fn a_clock_rollback_cannot_lower_an_unknown_tombstone() {
    use std::io::Write;
    let workspace = Workspace::new();
    let clock = TestClock::at(9 * 86_400);
    let store = workspace.open_at("yorimichi", &clock);
    let mut dated = begin(&store, RootKind::Main, "dated", 1);
    dated.use_result("unit.a", &key(1)).unwrap();
    let dated_journal = only_session(&workspace.store(), "yorimichi");

    clock.set(86_400);
    let legacy = begin(&store, RootKind::Main, "legacy", 1);
    let legacy_journal = session_files(&workspace.store(), "yorimichi")
        .into_iter()
        .find(|path| path != &dated_journal)
        .unwrap();
    let mut file = fs::OpenOptions::new()
        .append(true)
        .open(&legacy_journal)
        .unwrap();
    writeln!(file, "{{\"unit\":\"unit.a\",\"key\":\"{}\"}}", key(1)).unwrap();
    drop(file);
    legacy.abandon().unwrap();

    assert_eq!(
        usage_of(&store).unknown[&key(1)].as_str(),
        "1970-01-10",
        "the floor covers the dated observation it invalidated, not just the rolled-back today"
    );
    assert!(!usage_of(&store).results.contains_key(&key(1)));

    dated.abandon().unwrap();
    assert!(
        !usage_of(&store).results.contains_key(&key(1)),
        "the pre-existing day-10 bucket must not clear the floor"
    );
    assert!(usage_of(&store).unknown.contains_key(&key(1)));
}
