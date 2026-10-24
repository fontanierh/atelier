//! The C5c resident window's exact setup sequence (`tests/support/resident_setup.rs`, shared with
//! `examples/resident_window.rs`) on any host, stopping before any launch: no bridge, worker,
//! interpreter or admission is started. It binds the worker identity and command, validates and
//! prepares every unit with the proof's install policy, takes the real B3 locks and custody, opens
//! the receipt reader with the same policy, binds both leases of every case's units, and runs the
//! production registration on them, then re-reads both leases from disk.
#![cfg(unix)]

#[path = "support/resident_setup.rs"]
mod setup;

use atelier_build_v2::failure_policy::Limits;
use atelier_build_v2::launch::PYTHON_JOB_LOOP_VERSION;
use atelier_build_v2::leases::{LeaseStore, ProcessIdentity};
use atelier_build_v2::python_backend::register_python_worker;
use atelier_build_v2::session_lifecycle::{Refusal, UnitPlan};
use atelier_build_v2::worker_lifecycle::{JobSandbox, LockScope};
use std::collections::BTreeSet;
use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::time::Duration;

struct Scratch(PathBuf);
impl Scratch {
    fn new() -> Self {
        let path =
            std::env::temp_dir().join(format!("atelier-v2-resident-setup-{}", std::process::id()));
        fs::create_dir(&path).unwrap();
        Self(path.canonicalize().unwrap())
    }
}
impl Drop for Scratch {
    fn drop(&mut self) {
        // The materialized worker folder is read-only by design.
        let _ = fs::set_permissions(self.0.join("worker"), fs::Permissions::from_mode(0o755));
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn on_disk(store: &LeaseStore, id: &str) -> bool {
    store
        .lock()
        .and_then(|guard| guard.leases())
        .is_ok_and(|records| records.iter().any(|record| record.id == id))
}

#[test]
fn the_resident_window_setup_binds_every_input_without_launching() {
    let scratch = Scratch::new();
    let source = Path::new(env!("CARGO_MANIFEST_DIR")).join("../studio/atelier/build_v2");
    // Never executed: the sequence stops before any launch.
    let python = Path::new("/usr/bin/python3");

    // A relative interpreter is refused: the loop runs with `/` as its working folder.
    let snapshot = setup::worker_snapshot(&source).unwrap();
    assert!(
        setup::worker_command(Path::new("python3"), &snapshot, &scratch.0.join("relative"))
            .is_err()
    );

    let world = setup::world(python, &source, &scratch.0.join("worker")).unwrap();
    assert_eq!(world.command.program, python);
    assert_eq!(world.command.cwd, Path::new("/"));
    assert_eq!(world.worker.digest.len(), 64);
    assert_eq!(
        world
            .prepared
            .keys()
            .map(String::as_str)
            .collect::<Vec<_>>(),
        setup::UNITS.to_vec()
    );
    // The install policy the reader and `validate` share is valid and non-empty.
    let policy = setup::install_policy().unwrap();
    assert_eq!(policy.allowed_install_roots, setup::install_roots());
    assert!(!policy.allowed_install_roots.is_empty());

    let owner = ProcessIdentity {
        pid: std::process::id(),
        boot: "setup-test".into(),
        started: "setup-test".into(),
    };
    let worker = ProcessIdentity {
        pid: std::process::id(),
        boot: "setup-test".into(),
        started: "setup-test-worker".into(),
    };
    let monitor = ProcessIdentity {
        pid: std::process::id(),
        boot: "setup-test".into(),
        started: "setup-test-monitor".into(),
    };
    for (case, units) in setup::CASE_UNITS {
        let root = scratch.0.join(case);
        fs::create_dir(&root).unwrap();
        let mut bound = setup::case_setup(&world, &owner, &root, units)
            .unwrap_or_else(|error| panic!("{case}: {error}"));

        // Real B3 custody: the build lock exclusive and the content lock shared, as the key's set.
        assert_eq!(bound.custody.len(), 2, "{case}");
        let scopes: BTreeSet<LockScope> = bound.custody_set.iter().map(|c| c.scope).collect();
        assert_eq!(
            scopes,
            [LockScope::Exclusive, LockScope::Shared].into(),
            "{case}"
        );
        assert_eq!(bound.key.custody, bound.custody_set, "{case}");
        assert_eq!(bound.key.sandbox, JobSandbox::NoFork, "{case}");
        assert_eq!(bound.key.memory_gib, setup::MEMORY_GIB, "{case}");
        assert_eq!(bound.key.worker_version, PYTHON_JOB_LOOP_VERSION, "{case}");
        assert_eq!(bound.lock_files.len(), 2, "{case}");
        assert!(bound.lock_paths.iter().all(|path| path.is_file()), "{case}");
        assert!(setup::installer_busy(&bound.checkout), "{case}");
        assert!(setup::reader_admitted(&bound.checkout), "{case}");

        // Both leases of every unit are bound, and on disk, before any launch.
        assert_eq!(bound.leases.len(), units.len(), "{case}");
        for (unit, (local_id, cas_id)) in &bound.lease_ids {
            assert!(on_disk(&bound.local_leases, local_id), "{case} {unit}");
            assert!(on_disk(bound.store.leases(), cas_id), "{case} {unit}");
        }
        // The production registration of a worker and a monitor, then the independent re-read
        // the register callback's before-Run gate makes.
        for (unit, leases) in bound.leases.iter_mut() {
            let (local_id, cas_id) = &bound.lease_ids[unit];
            assert!(
                setup::lease_holds(&bound.local_leases, local_id, &worker).is_err(),
                "{case} {unit}"
            );
            for identity in [&worker, &monitor] {
                register_python_worker(&mut leases.local, Some(&mut leases.cas), identity).unwrap();
            }
            for identity in [&worker, &monitor] {
                setup::lease_holds(&bound.local_leases, local_id, identity).unwrap();
                setup::lease_holds(bound.store.leases(), cas_id, identity).unwrap();
            }
        }

        // Dropping the originals leaves the custody duplicates holding the locks.
        drop(bound.originals.take());
        assert!(setup::installer_busy(&bound.checkout), "{case}");
        let checkout = bound.checkout.clone();
        drop(bound);
        assert!(!setup::installer_busy(&checkout), "{case}");
    }
}

#[test]
fn the_session_lifecycle_accepts_every_resident_window_case() {
    // The exact limits the example runs with, then every case's exact plans in order through the
    // production refusal path (the same preflight the example runs before each case): no refusal
    // of any kind (closed, duplicate, cleanup below quiescence, never fits). Run 2 refused its
    // first unit here.
    assert_eq!(setup::UNIT_LIMITS.cleanup, Duration::from_secs(80));
    assert_eq!(setup::SESSION_CLEANUP, Duration::from_secs(60));
    assert_eq!(setup::QUIESCENCE, Duration::from_secs(10));
    for (case, units) in setup::CASE_UNITS {
        assert_eq!(
            setup::preflight(setup::session_config(), &setup::case_plans(units)),
            Ok(()),
            "{case}"
        );
    }
    // The inverse: run 2's unit cleanup (60 s, equal to the session's own cleanup limit) is
    // refused by the same path, with its typed reason and text.
    let plan = UnitPlan {
        id: "a".into(),
        limits: Limits {
            cleanup: Duration::from_secs(60),
            ..setup::UNIT_LIMITS
        },
    };
    let refused = setup::preflight(setup::session_config(), &[plan]).unwrap_err();
    assert!(
        refused.iter().any(|refused| refused.unit == "a"
            && refused.reason == Some(Refusal::CleanupBelowQuiescence)
            && refused.text == Refusal::CleanupBelowQuiescence.reason()),
        "{refused:?}"
    );
}

#[test]
fn the_running_marker_is_found_only_where_the_job_writes_its_output() {
    // The resolver the example uses, on the layout run 3 retained:
    // jobs/<unit>-<attempt>/<OUTPUT_ROOT>/<MARKER_PATH>. Files only: no runner or process. Its
    // own folder, since the setup test's scratch folder is named by this process.
    let path =
        std::env::temp_dir().join(format!("atelier-v2-resident-marker-{}", std::process::id()));
    fs::create_dir(&path).unwrap();
    let scratch = Scratch(path.canonicalize().unwrap());
    let jobs = scratch.0.join("jobs");
    let marker = jobs
        .join("spin-1")
        .join(setup::OUTPUT_ROOT)
        .join(setup::MARKER_PATH);
    assert_eq!(marker, setup::job_output(&jobs.join("spin-1")));
    assert!(marker.ends_with("spin-1/output/output/piece.txt"));
    // The layout run 3 looked for, one level short, is never taken for the marker.
    let short = jobs.join("spin-1/output/piece.txt");
    fs::create_dir_all(short.parent().unwrap()).unwrap();
    fs::write(&short, b"started").unwrap();
    assert_eq!(setup::running_marker(&jobs, "spin"), None);
    // Nor is a marker that has not started.
    fs::create_dir_all(marker.parent().unwrap()).unwrap();
    fs::write(&marker, b"").unwrap();
    assert_eq!(setup::running_marker(&jobs, "spin"), None);
    fs::write(&marker, b"started\n").unwrap();
    assert_eq!(setup::running_marker(&jobs, "spin"), Some(marker));
}
