#![cfg(any(target_os = "macos", target_os = "linux"))]
use atelier_build_v2::{
    graph::*, install::*, keys::*, leases::*, results::*, schema::*, source_hashes::*, validate::*,
};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
static NEXT: AtomicU64 = AtomicU64::new(0);
struct Workspace(PathBuf);
impl Workspace {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "atelier-v2-installs-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        Self(path)
    }
    fn path(&self, p: &str) -> PathBuf {
        self.0.join(p)
    }
    fn installer(&self, project: &str) -> CheckoutInstaller {
        CheckoutInstaller::open(
            &self.0,
            self.path("cache"),
            InstallPolicy {
                project: namespace(project),
                allowed_install_roots: vec![
                    format!("games/{project}/Content"),
                    format!("games/{project}/Binaries"),
                ],
            },
        )
        .unwrap()
    }
}
impl Drop for Workspace {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
    }
}
fn namespace(project: &str) -> ProjectNamespace {
    ProjectNamespace::new(project).unwrap()
}
fn identity() -> LeaseIdentity {
    LeaseIdentity {
        provenance: Provenance {
            checkout: "fixture".into(),
            branch: "fixture".into(),
            commit: "fixture".into(),
            dirty: false,
            built_at: "now".into(),
        },
        owner: ProcessIdentity {
            pid: 1,
            boot: "test".into(),
            started: "owner".into(),
        },
        workers: vec![],
        upstream_result_keys: BTreeSet::new(),
    }
}
fn fixture(project: &str, version: &str) -> (BuildGraph, PreparedUnit) {
    fixture_named(project, version, "/Game/Shared")
}
fn fixture_named(project: &str, version: &str, logical: &str) -> (BuildGraph, PreparedUnit) {
    let declaration = Declaration {
        schema_version: SCHEMA_VERSION,
        cache_version: version.into(),
        units: vec![Unit {
            id: "export".into(),
            op: Op {
                kind: "blob".into(),
                version: "1".into(),
            },
            script: "ops/run.py".into(),
            code: vec!["ops/run.py".into()],
            inputs: vec![],
            params: BTreeMap::new(),
            conditional: None,
            output_groups: vec![],
            outputs: vec![Item {
                id: "mesh".into(),
                logical_path: logical.into(),
                class: "Blob".into(),
                destination: Destination::Checkout,
                files: vec![
                    OutputFile {
                        path: "output/main.bin".into(),
                        install_path: Some(format!("games/{project}/Content/Shared.bin")),
                        required: true,
                    },
                    OutputFile {
                        path: "output/extra.bin".into(),
                        install_path: Some(format!("games/{project}/Content/Shared.side")),
                        required: false,
                    },
                ],
            }],
        }],
    };
    let registry = BTreeMap::from([(
        ("blob".into(), "1".into()),
        OpDefinition {
            inputs: BTreeMap::new(),
            output_classes: BTreeSet::from(["Blob".into()]),
            params: BTreeMap::new(),
        },
    )]);
    let roots = vec![
        format!("games/{project}/Content"),
        format!("games/{project}/Binaries"),
    ];
    let graph = BuildGraph::validate(declaration.clone(), &registry, &roots).unwrap();
    let snapshot = BTreeMap::from([("ops/run.py".into(), SnapshotEntry::File(b"script".to_vec()))]);
    let validated = validate(&declaration, &registry, &snapshot, &roots).unwrap();
    let implementation = ImplementationIdentity {
        version: "1".into(),
        digest: "a".repeat(64),
    };
    let unit = prepare(
        &declaration,
        &validated,
        "export",
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
    .unwrap();
    (graph, unit)
}
fn view(project: &str, graph: &BuildGraph) -> OwnershipSnapshot {
    OwnershipSnapshot::from_projects([(namespace(project), graph)]).unwrap()
}

#[test]
fn receipt_owner_namespace_is_explicit_and_independent_of_selected_roots() {
    assert_ne!(
        OwnerId::new(namespace("first"), "/Game/Shared").unwrap(),
        OwnerId::new(namespace("second"), "/Game/Shared").unwrap()
    );
    assert_eq!(
        OwnerId::new(namespace("first"), "/Game/Shared").unwrap(),
        OwnerId::new(namespace("first"), "/game/shared").unwrap()
    );
    for bad in ["", ".", "..", "project/name", "with space"] {
        assert!(ProjectNamespace::new(bad).is_err());
    }
    let workspace = Workspace::new();
    fs::write(workspace.path("cache"), b"unavailable cache").unwrap();
    let reader = ReceiptReader::open(
        &workspace.0,
        InstallPolicy {
            project: namespace("first"),
            allowed_install_roots: vec!["games/first/Content".into()],
        },
    )
    .unwrap();
    let guard = reader.locks().try_build_exclusive().unwrap();
    let (_, unit) = fixture("first", "1");
    assert!(matches!(
        reader.receipt_status(&guard, &unit).unwrap(),
        CurrentStatus::Dirty
    ));
    assert_eq!(
        fs::read(workspace.path("cache")).unwrap(),
        b"unavailable cache"
    );
    fs::remove_file(workspace.path("cache")).unwrap();
    let installer = workspace.installer("first");
    let RestoreLookup::Miss(mut transaction) = installer
        .lookup_restore(
            &guard,
            &unit,
            identity(),
            &view("first", &fixture("first", "1").0),
            vec![],
        )
        .unwrap()
    else {
        panic!("unexpected cache hit")
    };
    transaction
        .add_worker(ProcessIdentity {
            pid: 2,
            boot: "test".into(),
            started: "worker".into(),
        })
        .unwrap();
    let store = ResultStore::open(workspace.path("cache")).unwrap();
    let mutex = store.leases().lock().unwrap();
    assert_eq!(
        mutex
            .leases()
            .unwrap()
            .iter()
            .filter(|lease| lease.result_keys.contains(unit.key()))
            .count(),
        1
    );
}

#[cfg(target_os = "macos")]
fn publish(
    workspace: &Workspace,
    unit: &PreparedUnit,
    main: &[u8],
    side: Option<&[u8]>,
    mode: u32,
) {
    use std::os::unix::fs::PermissionsExt;
    let serial = NEXT.fetch_add(1, Ordering::Relaxed);
    let main_path = workspace.path(&format!("produced-{serial}"));
    fs::write(&main_path, main).unwrap();
    fs::set_permissions(&main_path, fs::Permissions::from_mode(mode)).unwrap();
    let mut sources = BTreeMap::from([(("mesh".into(), "output/main.bin".into()), main_path)]);
    if let Some(side) = side {
        let path = workspace.path(&format!("side-{serial}"));
        fs::write(&path, side).unwrap();
        sources.insert(("mesh".into(), "output/extra.bin".into()), path);
    }
    let identity = identity();
    ResultStore::open(workspace.path("cache"))
        .unwrap()
        .begin(
            unit,
            identity.provenance,
            identity.owner,
            identity.workers,
            identity.upstream_result_keys,
        )
        .unwrap()
        .stage(sources, |_| Ok(()))
        .unwrap()
        .publish(|_| Ok(()))
        .unwrap();
}
#[cfg(target_os = "macos")]
fn restore(
    installer: &CheckoutInstaller,
    guard: &atelier_build_v2::checkout_locks::BuildGuard,
    unit: &PreparedUnit,
    view: &OwnershipSnapshot,
) {
    assert!(matches!(
        installer
            .prepare_restore(guard, unit, identity(), view, vec![])
            .unwrap()
            .unwrap()
            .commit(guard, |_| Ok(()))
            .unwrap(),
        InstallOutcome::Installed
    ));
}

#[cfg(target_os = "macos")]
#[test]
fn install_modes_receipts_and_clone_independence_survive_cache_removal() {
    use std::os::unix::fs::PermissionsExt;
    let workspace = Workspace::new();
    let installer = workspace.installer("first");
    let guard = installer.locks().try_build_exclusive().unwrap();
    let (graph, unit) = fixture("first", "1");
    let view = view("first", &graph);
    publish(&workspace, &unit, b"executable", Some(b"side"), 0o755);
    restore(&installer, &guard, &unit, &view);
    let path = workspace.path("games/first/Content/Shared.bin");
    assert_eq!(
        fs::metadata(&path).unwrap().permissions().mode() & 0o777,
        0o755
    );
    fs::remove_dir_all(workspace.path("cache")).unwrap();
    fs::write(workspace.path("cache"), b"unavailable cache").unwrap();
    let policy = InstallPolicy {
        project: namespace("first"),
        allowed_install_roots: vec!["games/first/Content".into()],
    };
    assert!(
        CheckoutInstaller::open(&workspace.0, workspace.path("cache"), policy.clone()).is_err()
    );
    let cold = ReceiptReader::open(&workspace.0, policy).unwrap();
    assert!(matches!(
        cold.receipt_status(&guard, &unit).unwrap(),
        CurrentStatus::Current(_)
    ));
    fs::write(&path, b"edited independently").unwrap();
    assert!(matches!(
        installer.receipt_status(&guard, &unit).unwrap(),
        CurrentStatus::Dirty
    ));
    assert_eq!(
        fs::read(workspace.path("games/first/Content/Shared.side")).unwrap(),
        b"side"
    );
}

#[cfg(target_os = "macos")]
#[test]
fn two_projects_same_logical_item_never_overwrite_receipts_or_retire_neighbor_sidecars() {
    let workspace = Workspace::new();
    let first = workspace.installer("first");
    let second = workspace.installer("second");
    let guard = first.locks().try_build_exclusive().unwrap();
    let (a1, u1) = fixture("first", "1");
    let (b1, v1) = fixture("second", "1");
    let both =
        OwnershipSnapshot::from_projects([(namespace("first"), &a1), (namespace("second"), &b1)])
            .unwrap();
    publish(&workspace, &u1, b"first", Some(b"first-side"), 0o644);
    publish(&workspace, &v1, b"second", Some(b"second-side"), 0o644);
    restore(&first, &guard, &u1, &both);
    restore(&second, &guard, &v1, &both);
    let (a2, u2) = fixture("first", "2");
    let both =
        OwnershipSnapshot::from_projects([(namespace("first"), &a2), (namespace("second"), &b1)])
            .unwrap();
    publish(&workspace, &u2, b"first-new", None, 0o644);
    restore(&first, &guard, &u2, &both);
    assert!(!workspace.path("games/first/Content/Shared.side").exists());
    assert_eq!(
        fs::read(workspace.path("games/second/Content/Shared.side")).unwrap(),
        b"second-side"
    );
    assert!(matches!(
        first.receipt_status(&guard, &u2).unwrap(),
        CurrentStatus::Current(_)
    ));
    assert!(matches!(
        second.receipt_status(&guard, &v1).unwrap(),
        CurrentStatus::Current(_)
    ));
}

#[cfg(target_os = "macos")]
#[test]
fn every_durable_install_cut_recovers_old_or_committed_named_files() {
    let cuts = [
        InstallEvent::JournalCreated,
        InstallEvent::FileStaged(0),
        InstallEvent::FileStaged(1),
        InstallEvent::Ready,
        InstallEvent::OldMoved(0),
        InstallEvent::NewMoved(0),
        InstallEvent::OldMoved(1),
        InstallEvent::NewMoved(1),
        InstallEvent::ReceiptsReady,
        InstallEvent::IndexCommitted,
        InstallEvent::CleanupComplete,
    ];
    for cut in cuts {
        let workspace = Workspace::new();
        let installer = workspace.installer("first");
        let guard = installer.locks().try_build_exclusive().unwrap();
        let (g1, u1) = fixture("first", "1");
        publish(&workspace, &u1, b"old", Some(b"old-side"), 0o644);
        restore(&installer, &guard, &u1, &view("first", &g1));
        let (g2, u2) = fixture("first", "2");
        let view = view("first", &g2);
        publish(&workspace, &u2, b"new", Some(b"new-side"), 0o755);
        let mut plan = installer
            .prepare_restore(&guard, &u2, identity(), &view, vec![])
            .unwrap()
            .unwrap();
        assert!(
            plan.commit_with(
                &guard,
                |event| if event == cut {
                    Err(std::io::Error::other("injected"))
                } else {
                    Ok(())
                },
                |_| Ok(())
            )
            .is_err(),
            "{cut:?}"
        );
        let committed = matches!(
            cut,
            InstallEvent::IndexCommitted | InstallEvent::CleanupComplete
        );
        if cut != InstallEvent::CleanupComplete {
            assert!(matches!(
                installer.locks().try_read_content(),
                Err(atelier_build_v2::checkout_locks::LockError::RecoveryRequired)
            ));
        }
        installer.recover(&guard, &view).unwrap();
        assert_eq!(
            fs::read(workspace.path("games/first/Content/Shared.bin")).unwrap(),
            if committed { &b"new"[..] } else { &b"old"[..] },
            "{cut:?}"
        );
        assert_eq!(
            fs::read(workspace.path("games/first/Content/Shared.side")).unwrap(),
            if committed {
                &b"new-side"[..]
            } else {
                &b"old-side"[..]
            },
            "{cut:?}"
        );
        installer.recover(&guard, &view).unwrap();
        installer.locks().try_read_content().unwrap();
    }
}

#[cfg(target_os = "macos")]
#[test]
fn foreign_files_busy_readers_root_failures_and_unknown_recovery_are_explicit() {
    use atelier_build_v2::checkout_locks::LockError;
    let workspace = Workspace::new();
    let installer = workspace.installer("first");
    let guard = installer.locks().try_build_exclusive().unwrap();
    let (graph, unit) = fixture("first", "1");
    let view = view("first", &graph);
    publish(&workspace, &unit, b"new", None, 0o644);
    fs::create_dir_all(workspace.path("games/first/Content")).unwrap();
    let target = workspace.path("games/first/Content/Shared.bin");
    fs::write(&target, b"foreign").unwrap();
    let mut plan = installer
        .prepare_restore(&guard, &unit, identity(), &view, vec![])
        .unwrap()
        .unwrap();
    assert!(plan.commit(&guard, |_| Ok(())).is_err());
    assert_eq!(fs::read(&target).unwrap(), b"foreign");
    fs::remove_file(&target).unwrap();
    let reader = installer.locks().try_read_content().unwrap();
    assert!(matches!(
        plan.commit(&guard, |_| Ok(())),
        Err(InstallError::Lock(LockError::Busy))
    ));
    drop(reader);
    assert!(matches!(
        plan.commit(&guard, |_| Err("root unavailable".into()))
            .unwrap(),
        InstallOutcome::InstalledWithRootPending(_)
    ));
    assert!(matches!(
        installer.receipt_status(&guard, &unit).unwrap(),
        CurrentStatus::Current(_)
    ));
    let (next_graph, next) = fixture("first", "2");
    let next_view = crate::view("first", &next_graph);
    publish(&workspace, &next, b"later", None, 0o644);
    let mut plan = installer
        .prepare_restore(&guard, &next, identity(), &next_view, vec![])
        .unwrap()
        .unwrap();
    assert!(
        plan.commit_with(
            &guard,
            |event| if event == InstallEvent::NewMoved(0) {
                Err(std::io::Error::other("cut"))
            } else {
                Ok(())
            },
            |_| Ok(())
        )
        .is_err()
    );
    fs::write(&target, b"unknown external edit").unwrap();
    assert!(installer.recover(&guard, &next_view).is_err());
    assert_eq!(fs::read(&target).unwrap(), b"unknown external edit");
    assert!(matches!(
        installer.locks().try_read_content(),
        Err(LockError::RecoveryRequired)
    ));
}

#[cfg(target_os = "macos")]
#[test]
fn whole_item_retirement_requires_exact_current_namespaced_receipt_authority() {
    let workspace = Workspace::new();
    let installer = workspace.installer("first");
    let guard = installer.locks().try_build_exclusive().unwrap();
    let (before, old) = fixture("first", "1");
    publish(&workspace, &old, b"old", Some(b"old-side"), 0o644);
    restore(&installer, &guard, &old, &view("first", &before));
    let CurrentStatus::Current(receipts) = installer.receipt_status(&guard, &old).unwrap() else {
        panic!("missing receipt")
    };
    let receipt = &receipts[0];
    let id = sha256(&canonical_bytes(receipt).unwrap());
    let removal = RemovalIntent {
        owner: receipt.owner.clone(),
        expected_receipt_id: id,
        exact_paths: receipt
            .files
            .iter()
            .map(|f| f.install_path.clone())
            .collect(),
    };
    let (after, new) = fixture_named("first", "2", "/Game/Replacement");
    let after_view = view("first", &after);
    publish(&workspace, &new, b"replacement", None, 0o644);
    let mut stale = removal.clone();
    stale.expected_receipt_id = "0".repeat(64);
    assert!(matches!(
        installer.prepare_restore(&guard, &new, identity(), &after_view, vec![stale]),
        Err(InstallError::Invalid(_))
    ));
    assert!(
        installer
            .prepare_restore(
                &guard,
                &old,
                identity(),
                &view("first", &before),
                vec![removal.clone()]
            )
            .is_err()
    );
    let mut foreign = removal.clone();
    foreign.owner.project = namespace("other");
    assert!(
        installer
            .prepare_restore(&guard, &new, identity(), &after_view, vec![foreign])
            .is_err()
    );
    let mut plan = installer
        .prepare_restore(&guard, &new, identity(), &after_view, vec![removal])
        .unwrap()
        .unwrap();
    assert!(matches!(
        plan.commit(&guard, |_| Ok(())).unwrap(),
        InstallOutcome::Installed
    ));
    assert_eq!(
        fs::read(workspace.path("games/first/Content/Shared.bin")).unwrap(),
        b"replacement"
    );
    assert!(!workspace.path("games/first/Content/Shared.side").exists());
    assert!(matches!(
        installer.receipt_status(&guard, &old).unwrap(),
        CurrentStatus::Dirty
    ));
    assert!(matches!(
        installer.receipt_status(&guard, &new).unwrap(),
        CurrentStatus::Current(_)
    ));
}

#[test]
fn malformed_journal_and_linked_metadata_fail_closed_without_cleanup() {
    use atelier_build_v2::checkout_locks::LockError;
    let workspace = Workspace::new();
    let installer = workspace.installer("first");
    let guard = installer.locks().try_build_exclusive().unwrap();
    let (graph, _) = fixture("first", "1");
    let view = view("first", &graph);
    let journal = workspace.path("build/build-v2/install/journal.json");
    let unrelated = workspace.path("unrelated");
    fs::write(&unrelated, b"keep").unwrap();
    for invalid in [
        &b"[]"[..],
        &b"{"[..],
        &b"{\"digest\":\"bad\",\"journal\":{}}"[..],
    ] {
        fs::write(&journal, invalid).unwrap();
        assert!(installer.recover(&guard, &view).is_err());
        assert_eq!(fs::read(&journal).unwrap(), invalid);
        assert_eq!(fs::read(&unrelated).unwrap(), b"keep");
        assert!(matches!(
            installer.locks().try_read_content(),
            Err(LockError::RecoveryRequired)
        ));
    }
    fs::remove_file(&journal).unwrap();
    std::os::unix::fs::symlink(&unrelated, &journal).unwrap();
    assert!(installer.recover(&guard, &view).is_err());
    assert!(
        fs::symlink_metadata(&journal)
            .unwrap()
            .file_type()
            .is_symlink()
    );
    assert_eq!(fs::read(&unrelated).unwrap(), b"keep");
    let isolated = Workspace::new();
    let target = Workspace::new();
    fs::write(target.path("sentinel"), b"foreign").unwrap();
    std::os::unix::fs::symlink(&target.0, isolated.path("build")).unwrap();
    assert!(
        CheckoutInstaller::open(
            &isolated.0,
            isolated.path("cache"),
            InstallPolicy {
                project: namespace("first"),
                allowed_install_roots: vec!["games/first/Content".into()]
            }
        )
        .is_err()
    );
    assert_eq!(fs::read(target.path("sentinel")).unwrap(), b"foreign");
}

#[cfg(target_os = "macos")]
#[test]
fn replaced_receipt_inode_is_foreign_before_restore_and_whole_item_retirement() {
    for retire in [false, true] {
        let workspace = Workspace::new();
        let installer = workspace.installer("first");
        let guard = installer.locks().try_build_exclusive().unwrap();
        let (old_graph, old) = fixture("first", "1");
        publish(&workspace, &old, b"old", Some(b"old-side"), 0o644);
        restore(&installer, &guard, &old, &view("first", &old_graph));
        let CurrentStatus::Current(receipts) = installer.receipt_status(&guard, &old).unwrap()
        else {
            panic!("missing old receipt")
        };
        let old_index = fs::read(workspace.path("build/build-v2/install/index.json")).unwrap();
        let target = workspace.path("games/first/Content/Shared.bin");
        let foreign = workspace.path("foreign-replacement");
        fs::write(&foreign, b"foreign keep").unwrap();
        fs::rename(&foreign, &target).unwrap();
        let (new_graph, new) = fixture_named(
            "first",
            "2",
            if retire {
                "/Game/Replacement"
            } else {
                "/Game/Shared"
            },
        );
        let new_view = view("first", &new_graph);
        publish(&workspace, &new, b"new", None, 0o644);
        let removals = if retire {
            let receipt = &receipts[0];
            vec![RemovalIntent {
                owner: receipt.owner.clone(),
                expected_receipt_id: sha256(&canonical_bytes(receipt).unwrap()),
                exact_paths: receipt
                    .files
                    .iter()
                    .map(|f| f.install_path.clone())
                    .collect(),
            }]
        } else {
            vec![]
        };
        let mut plan = installer
            .prepare_restore(&guard, &new, identity(), &new_view, removals)
            .unwrap()
            .unwrap();
        assert!(plan.commit(&guard, |_| Ok(())).is_err());
        assert_eq!(fs::read(&target).unwrap(), b"foreign keep");
        assert_eq!(
            fs::read(workspace.path("games/first/Content/Shared.side")).unwrap(),
            b"old-side"
        );
        assert_eq!(
            fs::read(workspace.path("build/build-v2/install/index.json")).unwrap(),
            old_index
        );
        assert!(
            !workspace
                .path("build/build-v2/install/journal.json")
                .exists()
        );
    }
}

#[cfg(target_os = "macos")]
#[test]
fn dirty_same_inode_edits_are_preserved_during_failed_install_rollback() {
    let workspace = Workspace::new();
    let installer = workspace.installer("first");
    let guard = installer.locks().try_build_exclusive().unwrap();
    let (g1, u1) = fixture("first", "1");
    publish(&workspace, &u1, b"old", None, 0o644);
    restore(&installer, &guard, &u1, &view("first", &g1));
    let target = workspace.path("games/first/Content/Shared.bin");
    fs::write(&target, b"dirty managed edit").unwrap();
    let (g2, u2) = fixture("first", "2");
    let view = view("first", &g2);
    publish(&workspace, &u2, b"new", None, 0o644);
    let mut plan = installer
        .prepare_restore(&guard, &u2, identity(), &view, vec![])
        .unwrap()
        .unwrap();
    assert!(
        plan.commit_with(
            &guard,
            |event| if event == InstallEvent::OldMoved(0) {
                Err(std::io::Error::other("cut after preserving dirty original"))
            } else {
                Ok(())
            },
            |_| Ok(())
        )
        .is_err()
    );
    installer.recover(&guard, &view).unwrap();
    assert_eq!(fs::read(&target).unwrap(), b"dirty managed edit");
    assert!(matches!(
        installer.receipt_status(&guard, &u1).unwrap(),
        CurrentStatus::Dirty
    ));
}

#[cfg(target_os = "macos")]
#[test]
fn preinstall_abort_preserves_unknown_clone_and_resumes_every_durable_cut() {
    use atelier_build_v2::checkout_locks::LockError;
    use std::os::unix::fs::MetadataExt;
    let cuts = [
        None,
        Some(RecoveryEvent::AbortIntentDurable),
        Some(RecoveryEvent::JournalArchived),
        Some(RecoveryEvent::ScopeQuarantined),
        Some(RecoveryEvent::ReaderBarrierCleared),
    ];
    for cut in cuts {
        let workspace = Workspace::new();
        let installer = workspace.installer("first");
        let guard = installer.locks().try_build_exclusive().unwrap();
        let (g1, u1) = fixture("first", "1");
        publish(&workspace, &u1, b"old", Some(b"old-side"), 0o644);
        restore(&installer, &guard, &u1, &view("first", &g1));
        let (g2, u2) = fixture("first", "2");
        let view = view("first", &g2);
        publish(&workspace, &u2, b"new", None, 0o644);
        let mut plan = installer
            .prepare_restore(&guard, &u2, identity(), &view, vec![])
            .unwrap()
            .unwrap();
        assert!(
            plan.commit_with(
                &guard,
                |event| if event == InstallEvent::CloneCreated(0) {
                    Err(std::io::Error::other("clone returned, no inode receipt"))
                } else {
                    Ok(())
                },
                |_| Ok(())
            )
            .is_err()
        );
        let journal_path = workspace.path("build/build-v2/install/journal.json");
        let before = fs::read(&journal_path).unwrap();
        let journal: serde_json::Value = serde_json::from_slice(&before).unwrap();
        let scope = journal["journal"]["scope"].as_str().unwrap();
        let stage = workspace.path(journal["journal"]["entries"][0]["stage"].as_str().unwrap());
        assert!(stage.is_file());
        let scope_identity = fs::metadata(workspace.path(scope)).unwrap();
        // The controller must preserve even leaves absent from the journal, without discovering them.
        fs::write(
            workspace.path(scope).join("unlisted-evidence"),
            b"preserve unknown",
        )
        .unwrap();
        assert!(matches!(
            installer.locks().try_read_content(),
            Err(LockError::RecoveryRequired)
        ));
        let attempt = installer.recover_with(&guard, &view, |event| {
            if cut.as_ref() == Some(&event) {
                Err(std::io::Error::other("abort cut"))
            } else {
                Ok(())
            }
        });
        assert_eq!(attempt.is_err(), cut.is_some(), "{cut:?}");
        if cut != Some(RecoveryEvent::ReaderBarrierCleared) && cut.is_some() {
            assert!(matches!(
                installer.locks().try_read_content(),
                Err(LockError::RecoveryRequired)
            ));
        }
        installer.recover(&guard, &view).unwrap();
        installer.recover(&guard, &view).unwrap();
        let quarantine = workspace.path(&format!(
            "build/build-v2/install/quarantine/{}",
            scope.rsplit('/').next().unwrap()
        ));
        let moved = fs::metadata(&quarantine).unwrap();
        assert_eq!(
            (moved.dev(), moved.ino()),
            (scope_identity.dev(), scope_identity.ino())
        );
        assert_eq!(fs::read(quarantine.join("new/0")).unwrap(), b"new");
        assert_eq!(
            fs::read(quarantine.join("unlisted-evidence")).unwrap(),
            b"preserve unknown"
        );
        let archived: serde_json::Value =
            serde_json::from_slice(&fs::read(quarantine.join("journal.json")).unwrap()).unwrap();
        assert_eq!(
            archived["digest"].as_str().unwrap(),
            sha256(&canonical_bytes(&archived["journal"]).unwrap())
        );
        assert_eq!(
            archived["journal"]["retention"]["result_key"]
                .as_str()
                .unwrap(),
            u2.key()
        );
        assert_eq!(
            archived["journal"]["retention"]["owner"]["pid"]
                .as_u64()
                .unwrap(),
            1
        );
        assert!(!journal_path.exists());
        assert!(!workspace.path(scope).exists());
        assert_eq!(
            fs::read(workspace.path("games/first/Content/Shared.bin")).unwrap(),
            b"old"
        );
        assert_eq!(
            fs::read(workspace.path("games/first/Content/Shared.side")).unwrap(),
            b"old-side"
        );
        assert!(matches!(
            installer.receipt_status(&guard, &u1).unwrap(),
            CurrentStatus::Current(_)
        ));
        installer.locks().try_read_content().unwrap();
        let store = ResultStore::open(workspace.path("cache")).unwrap();
        let mutex = store.leases().lock().unwrap();
        assert!(mutex.leases().unwrap().iter().any(|lease| !lease.rooted
            && lease.result_keys.contains(u2.key())
            && !lease.object_digests.is_empty()));
    }
}

#[cfg(target_os = "macos")]
#[test]
fn preinstall_abort_rejects_changed_outputs_trash_and_replaced_directory_identities() {
    use atelier_build_v2::checkout_locks::LockError;
    for damage in ["index", "output", "trash", "scope", "quarantine"] {
        let workspace = Workspace::new();
        let installer = workspace.installer("first");
        let guard = installer.locks().try_build_exclusive().unwrap();
        let (g1, u1) = fixture("first", "1");
        publish(&workspace, &u1, b"old", None, 0o644);
        restore(&installer, &guard, &u1, &view("first", &g1));
        let (g2, u2) = fixture("first", "2");
        let view = view("first", &g2);
        publish(&workspace, &u2, b"new", None, 0o644);
        let mut plan = installer
            .prepare_restore(&guard, &u2, identity(), &view, vec![])
            .unwrap()
            .unwrap();
        assert!(
            plan.commit_with(
                &guard,
                |event| if event == InstallEvent::CloneCreated(0) {
                    Err(std::io::Error::other("cut"))
                } else {
                    Ok(())
                },
                |_| Ok(())
            )
            .is_err()
        );
        let journal_path = workspace.path("build/build-v2/install/journal.json");
        let journal: serde_json::Value =
            serde_json::from_slice(&fs::read(&journal_path).unwrap()).unwrap();
        let scope = journal["journal"]["scope"].as_str().unwrap();
        let output = workspace.path("games/first/Content/Shared.bin");
        match damage {
            "index" => fs::write(
                workspace.path("build/build-v2/install/index.json"),
                b"{\"version\":1,\"receipts\":{},\"paths\":{}}",
            )
            .unwrap(),
            "output" => fs::write(&output, b"changed after interruption").unwrap(),
            "trash" => fs::write(
                workspace.path(journal["journal"]["entries"][0]["trash"].as_str().unwrap()),
                b"unexpected trash",
            )
            .unwrap(),
            "scope" => {
                fs::rename(
                    workspace.path(scope),
                    workspace.path("preserved-real-scope"),
                )
                .unwrap();
                fs::create_dir(workspace.path(scope)).unwrap();
            }
            "quarantine" => {
                assert!(
                    installer
                        .recover_with(&guard, &view, |event| {
                            if event == RecoveryEvent::ScopeQuarantined {
                                Err(std::io::Error::other("cut"))
                            } else {
                                Ok(())
                            }
                        })
                        .is_err()
                );
                let target = workspace.path(&format!(
                    "build/build-v2/install/quarantine/{}",
                    scope.rsplit('/').next().unwrap()
                ));
                fs::rename(&target, workspace.path("preserved-real-scope")).unwrap();
                fs::create_dir(&target).unwrap();
            }
            _ => unreachable!(),
        }
        let evidence = fs::read(&journal_path).unwrap();
        assert!(installer.recover(&guard, &view).is_err(), "{damage}");
        assert_eq!(fs::read(&journal_path).unwrap(), evidence);
        assert_eq!(
            fs::read(&output).unwrap(),
            if damage == "output" {
                &b"changed after interruption"[..]
            } else {
                &b"old"[..]
            }
        );
        assert!(matches!(
            installer.locks().try_read_content(),
            Err(LockError::RecoveryRequired)
        ));
    }
}

#[cfg(target_os = "macos")]
#[test]
fn metadata_only_cached_use_roots_same_transaction_without_materializing_checkout() {
    let workspace = Workspace::new();
    let installer = workspace.installer("first");
    let guard = installer.locks().try_build_exclusive().unwrap();
    let (graph, unit) = fixture("first", "1");
    let view = view("first", &graph);
    publish(&workspace, &unit, b"cached only", None, 0o644);
    let RestoreLookup::Hit(plan) = installer
        .lookup_restore(&guard, &unit, identity(), &view, vec![])
        .unwrap()
    else {
        panic!("expected hit")
    };
    let reader = installer.locks().try_read_content().unwrap();
    let rooted = std::cell::Cell::new(false);
    assert_eq!(
        plan.retain_cached(|result| {
            assert_eq!(result.result.key, unit.key());
            rooted.set(true);
            Ok(())
        })
        .unwrap()
        .result
        .key,
        unit.key()
    );
    assert!(rooted.get());
    assert!(!workspace.path("games/first/Content/Shared.bin").exists());
    assert!(
        !workspace
            .path("build/build-v2/install/journal.json")
            .exists()
    );
    drop(reader);
}

#[cfg(target_os = "macos")]
#[test]
fn interrupted_cleanup_resumes_after_each_leaf_directory_and_barrier_removal() {
    use atelier_build_v2::checkout_locks::LockError;
    for cut in [
        CleanupEvent::Leaf(1),
        CleanupEvent::Leaf(3),
        CleanupEvent::Directory(0),
        CleanupEvent::Directory(1),
        CleanupEvent::Directory(2),
        CleanupEvent::BarrierCleared,
    ] {
        let workspace = Workspace::new();
        let installer = workspace.installer("first");
        let guard = installer.locks().try_build_exclusive().unwrap();
        let (g1, u1) = fixture("first", "1");
        publish(&workspace, &u1, b"old", Some(b"old-side"), 0o644);
        restore(&installer, &guard, &u1, &view("first", &g1));
        let (g2, u2) = fixture("first", "2");
        let view = view("first", &g2);
        publish(&workspace, &u2, b"new", Some(b"new-side"), 0o644);
        let mut plan = installer
            .prepare_restore(&guard, &u2, identity(), &view, vec![])
            .unwrap()
            .unwrap();
        assert!(
            plan.commit_with(
                &guard,
                |event| if event == InstallEvent::Cleanup(cut) {
                    Err(std::io::Error::other("cleanup cut"))
                } else {
                    Ok(())
                },
                |_| Ok(())
            )
            .is_err(),
            "{cut:?}"
        );
        if cut != CleanupEvent::BarrierCleared {
            assert!(matches!(
                installer.locks().try_read_content(),
                Err(LockError::RecoveryRequired)
            ));
        }
        installer.recover(&guard, &view).unwrap();
        installer.recover(&guard, &view).unwrap();
        assert_eq!(
            fs::read(workspace.path("games/first/Content/Shared.bin")).unwrap(),
            b"new"
        );
        assert_eq!(
            fs::read(workspace.path("games/first/Content/Shared.side")).unwrap(),
            b"new-side"
        );
        assert!(
            !workspace
                .path("build/build-v2/install/journal.json")
                .exists()
        );
        assert!(matches!(
            installer.receipt_status(&guard, &u2).unwrap(),
            CurrentStatus::Current(_)
        ));
        installer.locks().try_read_content().unwrap();
    }
}

#[cfg(target_os = "macos")]
#[test]
fn extra_owner_index_membership_refuses_current_and_restore_without_mutation() {
    let workspace = Workspace::new();
    let installer = workspace.installer("first");
    let guard = installer.locks().try_build_exclusive().unwrap();
    let (graph, unit) = fixture("first", "1");
    let view = view("first", &graph);
    publish(&workspace, &unit, b"valid", None, 0o644);
    restore(&installer, &guard, &unit, &view);
    let path = workspace.path("build/build-v2/install/index.json");
    let mut index: serde_json::Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
    let owner = index["paths"]
        .as_object()
        .unwrap()
        .values()
        .next()
        .unwrap()
        .clone();
    index["paths"]
        .as_object_mut()
        .unwrap()
        .insert("games/first/content/extra.bin".into(), owner);
    let malformed = serde_json::to_vec(&index).unwrap();
    fs::write(&path, &malformed).unwrap();
    let foreign = workspace.path("games/first/Content/extra.bin");
    fs::write(&foreign, b"preserve").unwrap();
    assert!(matches!(
        installer.receipt_status(&guard, &unit),
        Err(InstallError::RecoveryRequired(_))
    ));
    let reader = ReceiptReader::open(
        &workspace.0,
        InstallPolicy {
            project: namespace("first"),
            allowed_install_roots: vec!["games/first/Content".into()],
        },
    )
    .unwrap();
    assert!(matches!(
        reader.receipt_status(&guard, &unit),
        Err(InstallError::RecoveryRequired(_))
    ));
    let mut plan = installer
        .prepare_restore(&guard, &unit, identity(), &view, vec![])
        .unwrap()
        .unwrap();
    assert!(matches!(
        plan.commit(&guard, |_| Ok(())),
        Err(InstallError::RecoveryRequired(_))
    ));
    assert_eq!(fs::read(&path).unwrap(), malformed);
    assert_eq!(fs::read(&foreign).unwrap(), b"preserve");
    assert!(
        !workspace
            .path("build/build-v2/install/journal.json")
            .exists()
    );
}

#[cfg(target_os = "macos")]
#[test]
fn unknown_private_cleanup_leaves_preserve_journal_and_block_readers() {
    use atelier_build_v2::checkout_locks::LockError;
    for committed in [false, true] {
        for location in ["new", "trash", ""] {
            let workspace = Workspace::new();
            let installer = workspace.installer("first");
            let guard = installer.locks().try_build_exclusive().unwrap();
            let (g1, u1) = fixture("first", "1");
            publish(&workspace, &u1, b"old", None, 0o644);
            restore(&installer, &guard, &u1, &view("first", &g1));
            let (g2, u2) = fixture("first", "2");
            let view = view("first", &g2);
            publish(&workspace, &u2, b"new", None, 0o644);
            let mut plan = installer
                .prepare_restore(&guard, &u2, identity(), &view, vec![])
                .unwrap()
                .unwrap();
            assert!(
                plan.commit_with(
                    &guard,
                    |event| if event
                        == if committed {
                            InstallEvent::IndexCommitted
                        } else {
                            InstallEvent::Ready
                        } {
                        Err(std::io::Error::other("before cleanup"))
                    } else {
                        Ok(())
                    },
                    |_| Ok(())
                )
                .is_err()
            );
            let journal_path = workspace.path("build/build-v2/install/journal.json");
            let evidence = fs::read(&journal_path).unwrap();
            let journal: serde_json::Value = serde_json::from_slice(&evidence).unwrap();
            let scope = workspace.path(journal["journal"]["scope"].as_str().unwrap());
            let unknown = scope.join(location).join("unknown-evidence");
            fs::write(&unknown, b"foreign keep").unwrap();
            assert!(
                matches!(
                    installer.recover(&guard, &view),
                    Err(InstallError::RecoveryRequired(_))
                ),
                "{location}"
            );
            assert!(
                matches!(
                    installer.recover(&guard, &view),
                    Err(InstallError::RecoveryRequired(_))
                ),
                "{location}"
            );
            assert_eq!(fs::read(&unknown).unwrap(), b"foreign keep");
            assert_eq!(fs::read(&journal_path).unwrap(), evidence);
            assert_eq!(
                fs::read(workspace.path("games/first/Content/Shared.bin")).unwrap(),
                if committed { &b"new"[..] } else { &b"old"[..] }
            );
            assert!(matches!(
                installer.locks().try_read_content(),
                Err(LockError::RecoveryRequired)
            ));
            let store = ResultStore::open(workspace.path("cache")).unwrap();
            let mutex = store.leases().lock().unwrap();
            assert!(mutex.leases().unwrap().iter().any(|lease| !lease.rooted
                && lease.result_keys.contains(u2.key())
                && !lease.object_digests.is_empty()));
        }
    }
}

#[cfg(target_os = "macos")]
#[test]
fn current_sources_pin_without_cache_and_clone_only_certified_unchanged_items() {
    use atelier_build_v2::protocol::StagedInput;
    use atelier_build_v2::staging::{ObjectSource, SourceErrorKind};
    let workspace = Workspace::new();
    let installer = workspace.installer("first");
    let guard = installer.locks().try_build_exclusive().unwrap();
    let (graph, unit) = fixture("first", "1");
    publish(&workspace, &unit, b"current bytes", None, 0o644);
    restore(&installer, &guard, &unit, &view("first", &graph));
    fs::remove_dir_all(workspace.path("cache")).unwrap();
    fs::write(workspace.path("cache"), b"unavailable").unwrap();
    let reader = ReceiptReader::open(
        &workspace.0,
        InstallPolicy {
            project: namespace("first"),
            allowed_install_roots: vec!["games/first/Content".into()],
        },
    )
    .unwrap();
    let observed = reader.current_identities(&guard, &unit).unwrap().unwrap();
    assert_eq!(observed.key(), unit.key());
    // Metadata observation alone retains no lock, even when consumer staging never happens.
    installer.recover(&guard, &view("first", &graph)).unwrap();
    let sources = reader.pin_current_sources(&guard, &unit).unwrap().unwrap();
    let receipt = &sources.receipts()[0];
    let input = PreparedInput {
        wire: StagedInput {
            name: "item".into(),
            path: "inputs/item".into(),
            identity: ContentIdentity::Digest {
                digest: "a".repeat(64),
            },
        },
        payload: InputPayload::Item {
            logical_path: receipt.logical_path.clone(),
            class: receipt.class.clone(),
            files: receipt
                .files
                .iter()
                .map(|file| StoredFile {
                    path: file.output_path.clone(),
                    digest: file.digest.clone(),
                    size: file.size,
                    mode: file.mode,
                })
                .collect(),
        },
    };
    // Resolve a real consumer key from certified output content, without running its producer.
    let mut declaration = graph.declaration().clone();
    let mut consumer = declaration.units[0].clone();
    consumer.id = "consumer".into();
    consumer.op.kind = "consume".into();
    consumer.script = "ops/consume.py".into();
    consumer.code = vec![consumer.script.clone()];
    consumer.inputs = vec![Input::Content {
        name: "item".into(),
        source: ContentSource::Item {
            unit: "export".into(),
            item: "mesh".into(),
        },
        whole: None,
        conditional: None,
    }];
    consumer.outputs = vec![Item {
        id: "consumed".into(),
        logical_path: "/Data/Consumed".into(),
        class: "Blob".into(),
        destination: Destination::Store,
        files: vec![OutputFile {
            path: "result.bin".into(),
            install_path: None,
            required: true,
        }],
    }];
    declaration.units.push(consumer);
    let code = b"def run(context):\n    context.output('result.bin').write_bytes((context.input('item') / 'output/main.bin').read_bytes() + b' consumed')\n".to_vec();
    let snapshot = BTreeMap::from([
        ("ops/run.py".into(), SnapshotEntry::File(b"script".to_vec())),
        ("ops/consume.py".into(), SnapshotEntry::File(code)),
    ]);
    let registry = BTreeMap::from([
        (
            ("blob".into(), "1".into()),
            OpDefinition {
                inputs: BTreeMap::new(),
                output_classes: BTreeSet::from(["Blob".into()]),
                params: BTreeMap::new(),
            },
        ),
        (
            ("consume".into(), "1".into()),
            OpDefinition {
                inputs: BTreeMap::from([(
                    "item".into(),
                    InputRule {
                        role: InputRole::Content,
                        required: true,
                        allow_absent_file: false,
                        allow_selector: false,
                        require_whole_reason: false,
                        item_classes: BTreeSet::from(["Blob".into()]),
                    },
                )]),
                output_classes: BTreeSet::from(["Blob".into()]),
                params: BTreeMap::new(),
            },
        ),
    ]);
    let validated = validate(
        &declaration,
        &registry,
        &snapshot,
        &["games/first/Content".into()],
    )
    .unwrap();
    let produced = BTreeMap::from([(
        ("export".into(), "mesh".into()),
        observed.items()[0].clone(),
    )]);
    let implementation = ImplementationIdentity {
        version: atelier_build_v2::launch::PYTHON_JOB_LOOP_VERSION.into(),
        digest: "a".repeat(64),
    };
    let prepared = prepare(
        &declaration,
        &validated,
        "consumer",
        &KeyContext {
            snapshot: &snapshot,
            versions: &BTreeMap::new(),
            produced: &produced,
            produced_groups: &BTreeMap::new(),
            staged_inputs: &BTreeMap::from([("item".into(), "inputs/item".into())]),
            worker: &implementation,
            validator: &implementation,
        },
        &mut SourceHashCache::default(),
    )
    .unwrap();
    let provider = sources.objects_for(&[&prepared.inputs()[0]]).unwrap();
    let staged = atelier_build_v2::staging::stage(
        &prepared,
        &snapshot,
        &provider,
        &workspace.path("consumer-job"),
        "consumer",
    )
    .unwrap();
    drop(provider);
    let objects = sources.objects_for(&[&input]).unwrap();
    let digest = atelier_build_v2::store::ObjectDigest::from_hex(&receipt.files[0].digest).unwrap();
    let clone = workspace.path("job-clone");
    objects.clone_object(&digest, &clone).unwrap();
    assert_eq!(fs::read(&clone).unwrap(), b"current bytes");
    assert!(matches!(
        installer.recover(&guard, &view("first", &graph)),
        Err(InstallError::Lock(
            atelier_build_v2::checkout_locks::LockError::Busy
        ))
    ));
    let mut mismatched = input.clone();
    if let InputPayload::Item { files, .. } = &mut mismatched.payload {
        files[0].mode = 0o755;
    }
    assert!(sources.objects_for(&[&mismatched]).is_err());
    fs::write(
        workspace.path("games/first/Content/Shared.bin"),
        b"changed live bytes",
    )
    .unwrap();
    let refused = workspace.path("refused");
    assert_eq!(
        objects.clone_object(&digest, &refused).unwrap_err().kind,
        SourceErrorKind::Changed
    );
    assert!(!refused.exists());
    assert_eq!(fs::read(&clone).unwrap(), b"current bytes");
    drop(objects);
    drop(sources);
    installer.recover(&guard, &view("first", &graph)).unwrap();
    // Read custody is gone before the child runs; its independent clone still has original bytes.
    let python = std::env::split_paths(&std::env::var_os("PATH").unwrap())
        .map(|path| path.join("python3"))
        .find(|path| path.is_file())
        .unwrap();
    let script = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../studio/atelier/build_v2/python_worker.py")
        .canonicalize()
        .unwrap();
    let command = atelier_build_v2::launch::WorkerCommand::python_job_loop(python, script);
    let outcome = atelier_build_v2::launch::run_staged(
        &atelier_build_v2::launch::DirectChild,
        &command,
        atelier_build_v2::launch::PYTHON_JOB_LOOP_VERSION,
        &staged,
    )
    .unwrap();
    let atelier_build_v2::launch::JobOutcome::Completed(actual) = outcome else {
        panic!("consumer failed: {outcome:?}")
    };
    assert_eq!(actual.len(), 1);
    assert_eq!(
        fs::read(&actual[0].source).unwrap(),
        b"current bytes consumed"
    );
    atelier_build_v2::staging::remove_job(staged.job_dir()).unwrap();
    assert!(reader.pin_current_sources(&guard, &unit).unwrap().is_none());
}

#[cfg(target_os = "macos")]
#[test]
fn retirement_valid_at_prepare_refuses_new_owner_receipt_before_journal_or_mutation() {
    let workspace = Workspace::new();
    let installer = workspace.installer("first");
    let guard = installer.locks().try_build_exclusive().unwrap();
    let (before, old) = fixture("first", "1");
    publish(&workspace, &old, b"old", Some(b"old-side"), 0o644);
    restore(&installer, &guard, &old, &view("first", &before));
    let CurrentStatus::Current(receipts) = installer.receipt_status(&guard, &old).unwrap() else {
        panic!("missing receipt")
    };
    let receipt = &receipts[0];
    let removal = RemovalIntent {
        owner: receipt.owner.clone(),
        expected_receipt_id: sha256(&canonical_bytes(receipt).unwrap()),
        exact_paths: receipt
            .files
            .iter()
            .map(|file| file.install_path.clone())
            .collect(),
    };
    let (after, target) = fixture_named("first", "2", "/Game/Replacement");
    publish(&workspace, &target, b"target", None, 0o644);
    let mut plan = installer
        .prepare_restore(
            &guard,
            &target,
            identity(),
            &view("first", &after),
            vec![removal],
        )
        .unwrap()
        .unwrap();
    let (new_graph, newer) = fixture("first", "3");
    publish(
        &workspace,
        &newer,
        b"new owner bytes",
        Some(b"new side"),
        0o644,
    );
    restore(&installer, &guard, &newer, &view("first", &new_graph));
    fs::write(
        workspace.path("games/first/Content/neighbor"),
        b"foreign neighbor",
    )
    .unwrap();
    let index = fs::read(workspace.path("build/build-v2/install/index.json")).unwrap();
    assert!(matches!(
        plan.commit(&guard, |_| panic!("stale plan cannot root")),
        Err(InstallError::Invalid(_))
    ));
    assert!(
        !workspace
            .path("build/build-v2/install/journal.json")
            .exists()
    );
    assert_eq!(
        fs::read(workspace.path("build/build-v2/install/index.json")).unwrap(),
        index
    );
    for (name, bytes) in [
        ("Shared.bin", b"new owner bytes".as_slice()),
        ("Shared.side", b"new side".as_slice()),
        ("neighbor", b"foreign neighbor".as_slice()),
    ] {
        assert_eq!(
            fs::read(workspace.path("games/first/Content").join(name)).unwrap(),
            bytes
        );
    }
    assert!(
        ResultStore::open(workspace.path("cache"))
            .unwrap()
            .leases()
            .lock()
            .unwrap()
            .leases()
            .unwrap()
            .iter()
            .any(|lease| !lease.rooted && lease.result_keys.contains(target.key()))
    );
}

#[cfg(target_os = "macos")]
fn freeze_local(
    reader: &ReceiptReader,
    guard: &atelier_build_v2::checkout_locks::BuildGuard,
    unit: &PreparedUnit,
    workspace: &Workspace,
    bytes: &[u8],
) -> atelier_build_v2::completion::FrozenCompletion {
    let work = reader.begin_completion(guard, unit, identity()).unwrap();
    assert!(!work.lease().rooted);
    let source = workspace.path("local-source");
    fs::write(&source, bytes).unwrap();
    work.freeze(
        vec![ActualOutput {
            path: "output/main.bin".into(),
            source,
        }],
        |outputs| {
            use std::io::Read;
            let mut actual = vec![];
            outputs[0]
                .object
                .reader()
                .unwrap()
                .read_to_end(&mut actual)
                .unwrap();
            assert_eq!(actual, bytes);
            Ok(())
        },
        |_, _, _| panic!("no groups"),
    )
    .unwrap()
}

#[cfg(target_os = "macos")]
#[test]
fn local_valid_completion_installs_without_cache_and_preserves_frozen_bytes_after_publish_failure()
{
    let workspace = Workspace::new();
    let reader = ReceiptReader::open(
        &workspace.0,
        InstallPolicy {
            project: namespace("first"),
            allowed_install_roots: vec!["games/first/Content".into()],
        },
    )
    .unwrap();
    let guard = reader.locks().try_build_exclusive().unwrap();
    let (graph, unit) = fixture("first", "1");
    let mut completion = freeze_local(&reader, &guard, &unit, &workspace, b"validated local bytes");
    let lease = completion.lease().clone();
    assert!(!workspace.path("cache").exists());
    // Changing live job output after freeze cannot affect publication or install.
    fs::write(workspace.path("local-source"), b"changed live output").unwrap();
    let store = ResultStore::open(workspace.path("cache")).unwrap();
    fs::remove_dir(workspace.path("cache/objects/sha256")).unwrap();
    fs::write(
        workspace.path("cache/objects/sha256"),
        b"unavailable objects",
    )
    .unwrap();
    assert!(
        completion
            .publish(&store, |_| panic!("cache publication failed before root"))
            .is_err()
    );
    fs::remove_dir_all(workspace.path("cache")).unwrap();
    fs::write(workspace.path("cache"), b"unavailable cache").unwrap();
    let mut plan = reader
        .prepare_local(&guard, completion, &view("first", &graph), vec![])
        .unwrap();
    assert!(matches!(
        plan.commit(&guard, |_| panic!("local result cannot claim cached root"))
            .unwrap(),
        InstallOutcome::InstalledLocally {
            retention_error: None
        }
    ));
    assert_eq!(
        fs::read(workspace.path("games/first/Content/Shared.bin")).unwrap(),
        b"validated local bytes"
    );
    assert!(matches!(
        reader.receipt_status(&guard, &unit).unwrap(),
        CurrentStatus::Current(_)
    ));
    let scope = workspace
        .path("build/build-v2/install/completions")
        .join(&lease.staging);
    let evidence: serde_json::Value =
        serde_json::from_slice(&fs::read(scope.join("completion.json")).unwrap()).unwrap();
    assert_eq!(evidence["envelope"]["result"]["key"], unit.key());
    let payload = evidence["objects"][0]["path"].as_str().unwrap();
    assert_eq!(
        fs::read(scope.join(payload)).unwrap(),
        b"validated local bytes"
    );
    assert_eq!(
        fs::read(workspace.path("cache")).unwrap(),
        b"unavailable cache"
    );
}

#[cfg(target_os = "macos")]
#[test]
fn frozen_completion_cache_adoption_does_not_rehash_live_output_and_conflicts_block_local_install()
{
    let workspace = Workspace::new();
    let installer = workspace.installer("first");
    let guard = installer.locks().try_build_exclusive().unwrap();
    let (graph, unit) = fixture("first", "1");
    let store = ResultStore::open(workspace.path("cache")).unwrap();
    let owner = identity();
    let original_upstream = BTreeSet::from(["b".repeat(64)]);
    let ticket = store
        .begin(
            &unit,
            owner.provenance,
            owner.owner,
            owner.workers,
            original_upstream.clone(),
        )
        .unwrap();
    let original_id = ticket.lease().id.clone();
    let mut completion = freeze_local(&installer, &guard, &unit, &workspace, b"frozen once");
    fs::write(workspace.path("local-source"), b"changed live source").unwrap();
    let result = completion
        .publish_with(ticket, |record| {
            assert_eq!(record.upstream_result_keys, original_upstream);
            let records = store.leases().lock().unwrap().leases().unwrap();
            assert_eq!(records.len(), 1);
            assert_eq!(records[0].id, original_id);
            assert!(!records[0].rooted && records[0].result_keys.contains(unit.key()));
            assert!(original_upstream.is_subset(&records[0].result_keys));
            assert!(!records[0].object_digests.is_empty());
            Ok(())
        })
        .unwrap();
    let records = store.leases().lock().unwrap().leases().unwrap();
    assert_eq!(records.len(), 1);
    assert_eq!(records[0].id, original_id);
    assert!(
        records[0].rooted
            && records[0].result_keys.is_empty()
            && records[0].object_digests.is_empty()
    );
    assert_eq!(
        result.result.outputs[0].files[0].digest,
        sha256(b"frozen once")
    );
    restore(&installer, &guard, &unit, &view("first", &graph));
    assert_eq!(
        fs::read(workspace.path("games/first/Content/Shared.bin")).unwrap(),
        b"frozen once"
    );
    let mut conflicting = freeze_local(
        &installer,
        &guard,
        &unit,
        &workspace,
        b"different same-key bytes",
    );
    assert!(matches!(
        conflicting.publish(&store, |_| panic!("conflict cannot root")),
        Err(ResultError::Nondeterminism(_))
    ));
    assert!(matches!(
        installer.prepare_local(&guard, conflicting, &view("first", &graph), vec![]),
        Err(InstallError::Invalid(_))
    ));
    let current_conflict = freeze_local(
        &installer,
        &guard,
        &unit,
        &workspace,
        b"different same-key bytes",
    );
    assert!(matches!(
        installer.prepare_local(&guard, current_conflict, &view("first", &graph), vec![]),
        Err(InstallError::LocalCompletion(ResultError::Nondeterminism(
            _
        )))
    ));
    assert!(
        !workspace
            .path("build/build-v2/install/journal.json")
            .exists()
    );
    assert_eq!(
        fs::read(workspace.path("games/first/Content/Shared.bin")).unwrap(),
        b"frozen once"
    );
}

#[cfg(target_os = "macos")]
#[test]
fn interrupted_local_install_retains_completion_and_uses_existing_quarantine_recovery() {
    let workspace = Workspace::new();
    let installer = workspace.installer("first");
    let guard = installer.locks().try_build_exclusive().unwrap();
    let (old_graph, old) = fixture("first", "1");
    publish(&workspace, &old, b"old", None, 0o644);
    restore(&installer, &guard, &old, &view("first", &old_graph));
    let (graph, unit) = fixture("first", "2");
    let completion = freeze_local(&installer, &guard, &unit, &workspace, b"new local");
    let lease = completion.lease().clone();
    let mut plan = installer
        .prepare_local(&guard, completion, &view("first", &graph), vec![])
        .unwrap();
    assert!(
        plan.commit_with(
            &guard,
            |event| if event == InstallEvent::CloneCreated(0) {
                Err(std::io::Error::other("fault after local clone"))
            } else {
                Ok(())
            },
            |_| panic!("fault cannot root")
        )
        .is_err()
    );
    assert!(installer.locks().try_read_content().is_err());
    installer.recover(&guard, &view("first", &graph)).unwrap();
    assert_eq!(
        fs::read(workspace.path("games/first/Content/Shared.bin")).unwrap(),
        b"old"
    );
    let scope = workspace
        .path("build/build-v2/install/completions")
        .join(&lease.staging);
    assert!(scope.join("completion.json").is_file());
    assert!(
        workspace
            .path("build/build-v2/install/completions/leases")
            .join(format!("{}.json", lease.id))
            .is_file()
    );
    installer.locks().try_read_content().unwrap();
}

#[cfg(target_os = "macos")]
#[test]
fn corrupt_cached_metadata_is_not_cached_and_does_not_invalidate_frozen_local_work() {
    use atelier_build_v2::integrity::{
        CompletionDecision, LocalOutputStatus, StoreFailureKind, classify_completion,
    };
    let workspace = Workspace::new();
    let installer = workspace.installer("first");
    let guard = installer.locks().try_build_exclusive().unwrap();
    let (graph, unit) = fixture("first", "1");
    let mut completion = freeze_local(&installer, &guard, &unit, &workspace, b"valid local output");
    let store = ResultStore::open(workspace.path("cache")).unwrap();
    let record = workspace
        .path("cache/results")
        .join(format!("{}.json", unit.key()));
    let corrupt = b"{\"malformed\":true}";
    fs::write(&record, corrupt).unwrap();
    let mut permissions = fs::metadata(&record).unwrap().permissions();
    permissions.set_readonly(true);
    fs::set_permissions(&record, permissions).unwrap();
    let outcome = completion.publish(&store, |_| panic!("corrupt cached record cannot root"));
    assert!(matches!(&outcome, Err(ResultError::Invalid(_))));
    assert_eq!(
        classify_completion(LocalOutputStatus::Valid, outcome),
        CompletionDecision::CompletedNotCached(StoreFailureKind::StoreMetadata)
    );
    let mut plan = installer
        .prepare_local(&guard, completion, &view("first", &graph), vec![])
        .unwrap();
    assert!(matches!(
        plan.commit(&guard, |_| panic!("local install cannot claim cached root"))
            .unwrap(),
        InstallOutcome::InstalledLocally {
            retention_error: None
        }
    ));
    assert_eq!(fs::read(&record).unwrap(), corrupt);
    assert_eq!(
        fs::read(workspace.path("games/first/Content/Shared.bin")).unwrap(),
        b"valid local output"
    );
    assert!(matches!(
        installer.receipt_status(&guard, &unit).unwrap(),
        CurrentStatus::Current(_)
    ));
}
