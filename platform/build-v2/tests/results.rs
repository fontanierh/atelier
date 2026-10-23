use atelier_build_v2::{keys::*, leases::*, results::*, schema::*, source_hashes::*, validate::*};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
#[cfg(target_os = "macos")]
use std::io::Read;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
static SERIAL: AtomicU64 = AtomicU64::new(0);

struct Workspace(PathBuf);
impl Workspace {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "atelier-v2-results-{}-{}",
            std::process::id(),
            SERIAL.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        Self(path)
    }
    fn path(&self, name: &str) -> PathBuf {
        self.0.join(name)
    }
    fn store(&self) -> ResultStore {
        ResultStore::open(self.path("store")).unwrap()
    }
}
impl Drop for Workspace {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
    }
}
fn process(pid: u32) -> ProcessIdentity {
    ProcessIdentity {
        pid,
        boot: "boot".into(),
        started: format!("start-{pid}"),
    }
}
fn provenance(name: &str) -> Provenance {
    Provenance {
        checkout: name.into(),
        branch: name.into(),
        commit: name.into(),
        dirty: false,
        built_at: "now".into(),
    }
}

fn prepared(id: &str) -> PreparedUnit {
    let declaration = Declaration {
        schema_version: SCHEMA_VERSION,
        cache_version: "1".into(),
        units: vec![Unit {
            id: id.into(),
            op: Op {
                kind: "data".into(),
                version: "1".into(),
            },
            script: "ops/run.py".into(),
            code: vec!["ops/run.py".into()],
            inputs: vec![],
            params: BTreeMap::new(),
            conditional: None,
            output_groups: vec![],
            outputs: vec![Item {
                id: "data".into(),
                logical_path: "/Data/result".into(),
                class: "Data".into(),
                destination: Destination::Store,
                files: vec![
                    OutputFile {
                        path: "result.bin".into(),
                        install_path: None,
                        required: true,
                    },
                    OutputFile {
                        path: "optional.bin".into(),
                        install_path: None,
                        required: false,
                    },
                ],
            }],
        }],
    };
    let registry = BTreeMap::from([(
        ("data".into(), "1".into()),
        OpDefinition {
            inputs: BTreeMap::new(),
            output_classes: BTreeSet::from(["Data".into()]),
            params: BTreeMap::new(),
        },
    )]);
    let snapshot = BTreeMap::from([("ops/run.py".into(), SnapshotEntry::File(b"code".to_vec()))]);
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
fn begin(store: &ResultStore, unit: &PreparedUnit) -> WriteTransaction {
    store
        .begin(
            unit,
            provenance("first"),
            process(1),
            vec![process(2)],
            BTreeSet::new(),
        )
        .unwrap()
}
#[cfg(target_os = "macos")]
fn sources(workspace: &Workspace, bytes: &[u8]) -> OutputSources {
    let path = workspace.path("source");
    fs::write(&path, bytes).unwrap();
    BTreeMap::from([(("data".into(), "result.bin".into()), path)])
}

#[test]
fn lease_is_durable_before_staging_and_unknown_liveness_never_expires() {
    let workspace = Workspace::new();
    let store = workspace.store();
    let unit = prepared("unit");
    let upstream = "b".repeat(64);
    let mut transaction = store
        .begin(
            &unit,
            provenance("first"),
            process(1),
            vec![process(2)],
            BTreeSet::from([upstream.clone()]),
        )
        .unwrap();
    transaction.add_worker(process(3)).unwrap();
    transaction.add_worker(process(3)).unwrap();
    let lease = transaction.lease().clone();
    assert_eq!(lease.workers, [process(2), process(3)]);
    assert!(workspace.path("store").join(&lease.staging).is_dir());
    assert!(
        fs::read_dir(workspace.path("store").join(&lease.staging))
            .unwrap()
            .next()
            .is_none()
    );
    assert!(lease.object_digests.is_empty());
    assert!(lease.result_keys.contains(unit.key()));
    assert!(lease.result_keys.contains(&upstream));
    drop(transaction);
    let records = store.leases().lock().unwrap().leases().unwrap();
    assert_eq!(records, [lease.clone()]);
    assert!(!lease.may_reclaim(|_| Liveness::Unknown));
    assert!(!lease.may_reclaim(|identity| if identity.pid == 2 {
        Liveness::Alive
    } else {
        Liveness::Dead
    }));
    assert!(!lease.may_reclaim(|identity| if identity.pid == 3 {
        Liveness::Alive
    } else {
        Liveness::Dead
    }));
    assert!(!lease.may_reclaim(|identity| if identity.pid == 2 {
        Liveness::Unknown
    } else {
        Liveness::Dead
    }));
    assert!(lease.may_reclaim(|_| Liveness::Dead));
}

#[test]
fn metadata_mutex_serializes_independent_handles_and_corrupt_leases_fail_closed() {
    let workspace = Workspace::new();
    let store = workspace.store();
    let counter = workspace.path("counter");
    fs::write(&counter, b"0").unwrap();
    let mut threads = vec![];
    for _ in 0..3 {
        let leases = store.leases().clone();
        let counter = counter.clone();
        threads.push(std::thread::spawn(move || {
            for _ in 0..4 {
                let _guard = leases.lock().unwrap();
                let count: u32 = fs::read_to_string(&counter).unwrap().parse().unwrap();
                fs::write(&counter, (count + 1).to_string()).unwrap();
            }
        }));
    }
    for thread in threads {
        thread.join().unwrap();
    }
    assert_eq!(fs::read_to_string(counter).unwrap(), "12");
    fs::write(workspace.path("store/leases/foreign.json"), b"{}").unwrap();
    assert!(store.leases().lock().unwrap().leases().is_err());
}

#[test]
fn missing_extra_outputs_and_incomplete_process_identity_refuse_before_publish() {
    let workspace = Workspace::new();
    let store = workspace.store();
    let unit = prepared("unit");
    assert!(matches!(
        begin(&store, &unit).stage(BTreeMap::new(), |_| panic!("not called")),
        Err(ResultError::Invalid(_))
    ));
    let mut bad = process(1);
    bad.started.clear();
    assert!(
        store
            .begin(&unit, provenance("bad"), bad, vec![], BTreeSet::new())
            .is_err()
    );
    assert!(
        fs::read_dir(workspace.path("store/results"))
            .unwrap()
            .next()
            .is_none()
    );
    let mut missing = begin(&store, &unit);
    assert!(missing.lookup().unwrap().is_none());
    assert!(missing.retain_hit(|_| panic!("no root for miss")).is_err());
}

#[test]
fn unsupported_result_versions_and_undeclared_groups_refuse() {
    let workspace = Workspace::new();
    let store = workspace.store();
    let unit = prepared("unit");
    let record = ResultEnvelope {
        version: ENVELOPE_VERSION,
        result: ResultRecord {
            schema_version: RESULT_SCHEMA_VERSION,
            unit: "unit".into(),
            key: unit.key().into(),
            ingredients: unit.ingredients().clone(),
            outputs: vec![],
            output_groups: vec![],
            provenance: provenance("fixture"),
        },
        upstream_result_keys: BTreeSet::new(),
    };
    let mut envelope_version = serde_json::to_value(&record).unwrap();
    envelope_version["version"] = 99.into();
    let mut result_version = serde_json::to_value(&record).unwrap();
    result_version["result"]["schema_version"] = (RESULT_SCHEMA_VERSION + 1).into();
    let mut groups = serde_json::to_value(&record).unwrap();
    groups["result"]["output_groups"] =
        serde_json::json!([{ "id":"geometry", "files":[], "projections":{} }]);
    let path = workspace
        .path("store/results")
        .join(format!("{}.json", unit.key()));
    for value in [envelope_version, result_version, groups] {
        fs::write(&path, serde_json::to_vec(&value).unwrap()).unwrap();
        let mut permissions = fs::metadata(&path).unwrap().permissions();
        permissions.set_readonly(true);
        fs::set_permissions(&path, permissions).unwrap();
        assert!(matches!(
            begin(&store, &unit).lookup(),
            Err(ResultError::Invalid(_))
        ));
        fs::remove_file(&path).unwrap();
    }
}

#[cfg(target_os = "macos")]
#[test]
fn validator_reads_frozen_hashed_bytes_and_modes_survive_source_changes() {
    use std::os::unix::fs::PermissionsExt;
    let workspace = Workspace::new();
    let store = workspace.store();
    let unit = prepared("unit");
    let sources = sources(&workspace, b"frozen bytes");
    fs::set_permissions(workspace.path("source"), fs::Permissions::from_mode(0o751)).unwrap();
    let staged = begin(&store, &unit)
        .stage(sources, |outputs| {
            fs::write(workspace.path("source"), b"different live bytes").unwrap();
            let mut bytes = vec![];
            outputs[0]
                .object
                .reader()
                .unwrap()
                .read_to_end(&mut bytes)
                .unwrap();
            assert_eq!(bytes, b"frozen bytes");
            assert_eq!(outputs[0].object.digest().as_hex(), sha256(&bytes));
            Ok(())
        })
        .unwrap();
    assert_eq!(staged.envelope().result.outputs[0].files[0].mode, 0o755);
    let result = staged.publish(|_| Ok(())).unwrap();
    assert_eq!(
        fs::read(
            workspace
                .path("store/objects/sha256")
                .join(&result.result.outputs[0].files[0].digest)
        )
        .unwrap(),
        b"frozen bytes"
    );
    let mut hit = begin(&store, &unit);
    assert_eq!(hit.lookup().unwrap().unwrap(), result);
    let hit = hit.retain_hit(|_| Ok(())).unwrap();
    assert_eq!(hit, result);
    let leases = store.leases().lock().unwrap().leases().unwrap();
    assert!(leases.iter().all(|lease| lease.rooted
        && lease.object_digests.is_empty()
        && lease.result_keys.is_empty()));
    assert!(
        leases
            .iter()
            .all(|lease| !lease.may_reclaim(|_| Liveness::Unknown))
    );
}

#[cfg(target_os = "macos")]
#[test]
fn validation_failure_and_unknown_outputs_never_publish_objects_or_records() {
    let workspace = Workspace::new();
    let store = workspace.store();
    let unit = prepared("unit");
    assert!(matches!(
        begin(&store, &unit).stage(sources(&workspace, b"bad"), |_| Err("bad format".into())),
        Err(ResultError::Validation(_))
    ));
    let mut outputs = sources(&workspace, b"good");
    outputs.insert(("data".into(), "foreign".into()), workspace.path("source"));
    assert!(matches!(
        begin(&store, &unit).stage(outputs, |_| panic!("not called")),
        Err(ResultError::Invalid(_))
    ));
    assert!(
        fs::read_dir(workspace.path("store/objects/sha256"))
            .unwrap()
            .next()
            .is_none()
    );
    assert!(
        fs::read_dir(workspace.path("store/results"))
            .unwrap()
            .next()
            .is_none()
    );
    assert_eq!(fs::read(workspace.path("source")).unwrap(), b"good");
}

#[cfg(target_os = "macos")]
#[test]
fn faults_at_each_publication_boundary_preserve_claims_and_prior_results() {
    for stop in [
        PublicationStep::Prepared,
        PublicationStep::Claimed,
        PublicationStep::ObjectPublished,
        PublicationStep::RecordPublished,
        PublicationStep::Rooted,
        PublicationStep::Released,
    ] {
        let workspace = Workspace::new();
        let store = workspace.store();
        let unit = prepared("unit");
        let transaction = begin(&store, &unit);
        let id = transaction.lease().id.clone();
        let mut outputs = sources(&workspace, b"payload");
        fs::write(workspace.path("sidecar"), b"sidecar").unwrap();
        outputs.insert(
            ("data".into(), "optional.bin".into()),
            workspace.path("sidecar"),
        );
        let staged = transaction.stage(outputs, |_| Ok(())).unwrap();
        let mut rooted = false;
        let result = staged.publish_observed(
            |_| {
                rooted = true;
                fs::write(workspace.path("durable-root-model"), unit.key())
                    .map_err(|error| error.to_string())
            },
            |step| {
                if step == stop {
                    Err(std::io::Error::other("injected stop"))
                } else {
                    Ok(())
                }
            },
        );
        assert!(result.is_err());
        let records = store.leases().lock().unwrap().leases().unwrap();
        let lease = records.iter().find(|lease| lease.id == id).unwrap();
        let released = stop == PublicationStep::Released;
        assert_eq!(lease.rooted, released);
        assert_eq!(lease.result_keys.contains(unit.key()), !released);
        assert_eq!(
            rooted,
            matches!(stop, PublicationStep::Rooted | PublicationStep::Released)
        );
        if !matches!(stop, PublicationStep::Prepared | PublicationStep::Released) {
            assert!(lease.object_digests.contains(&sha256(b"payload")));
            assert!(lease.object_digests.contains(&sha256(b"sidecar")));
        }
        let record_exists = workspace
            .path("store/results")
            .join(format!("{}.json", unit.key()))
            .exists();
        assert_eq!(
            record_exists,
            matches!(
                stop,
                PublicationStep::RecordPublished
                    | PublicationStep::Rooted
                    | PublicationStep::Released
            )
        );
        // Independent later failure cannot erase a previously published record.
        if record_exists {
            let previous = fs::read(
                workspace
                    .path("store/results")
                    .join(format!("{}.json", unit.key())),
            )
            .unwrap();
            let failed = begin(&store, &unit)
                .stage(sources(&workspace, b"bad"), |_| Err("later failure".into()));
            assert!(failed.is_err());
            assert_eq!(
                fs::read(
                    workspace
                        .path("store/results")
                        .join(format!("{}.json", unit.key()))
                )
                .unwrap(),
                previous
            );
        }
    }
}

#[cfg(target_os = "macos")]
#[test]
fn same_key_writers_deduplicate_and_keep_first_lineage_while_different_output_refuses() {
    let workspace = Workspace::new();
    let store = workspace.store();
    let unit = prepared("first-name");
    let renamed = prepared("second-name");
    assert_eq!(unit.key(), renamed.key());
    let first = begin(&store, &unit)
        .stage(sources(&workspace, b"same"), |_| Ok(()))
        .unwrap();
    let second = store
        .begin(
            &renamed,
            provenance("second"),
            process(3),
            vec![],
            BTreeSet::from(["b".repeat(64)]),
        )
        .unwrap()
        .stage(sources(&workspace, b"same"), |_| Ok(()))
        .unwrap();
    let first = first.publish(|_| Ok(())).unwrap();
    let second = second.publish(|_| Ok(())).unwrap();
    assert_eq!(second, first);
    assert_eq!(second.result.unit, "first-name");
    assert!(second.upstream_result_keys.is_empty());
    let different = begin(&store, &unit)
        .stage(sources(&workspace, b"different"), |_| Ok(()))
        .unwrap();
    assert!(matches!(
        different.publish(|_| panic!("no root for conflict")),
        Err(ResultError::Nondeterminism(_))
    ));
    let root_failure = begin(&store, &unit)
        .stage(sources(&workspace, b"same"), |_| Ok(()))
        .unwrap();
    assert!(matches!(
        root_failure.publish(|_| Err("disk full".into())),
        Err(ResultError::Root(_))
    ));
    assert_eq!(begin(&store, &unit).lookup().unwrap().unwrap(), first);
}

#[cfg(target_os = "macos")]
#[test]
fn concurrent_publication_and_gc_observer_share_claim_mutex_without_gap() {
    let workspace = Workspace::new();
    let store = workspace.store();
    let unit = prepared("unit");
    let one = begin(&store, &unit)
        .stage(sources(&workspace, b"same"), |_| Ok(()))
        .unwrap();
    let two = begin(&store, &unit)
        .stage(sources(&workspace, b"same"), |_| Ok(()))
        .unwrap();
    let leases = store.leases().clone();
    let key = unit.key().to_string();
    let root_path = workspace.path("root-model");
    let writer_root = root_path.clone();
    let writer = std::thread::spawn(move || {
        one.publish(|result| {
            fs::write(writer_root, &result.result.key).map_err(|error| error.to_string())
        })
        .unwrap()
    });
    let object_path = workspace.path("store/objects/sha256").join(sha256(b"same"));
    let mut removed = 0;
    let second = two
        .publish_observed(
            |result| fs::write(&root_path, &result.result.key).map_err(|error| error.to_string()),
            |step| {
                let guard = leases.lock().unwrap();
                let records = guard.leases().unwrap();
                // Minimal future-GC observer: only unclaimed/unrooted entries are
                // deletion candidates. No B5 policy or output-directory scan here.
                let protected = root_path.exists()
                    || records.iter().any(|lease| {
                        lease.result_keys.contains(&key)
                            || lease.object_digests.contains(&sha256(b"same"))
                    });
                if object_path.exists() && !protected {
                    fs::remove_file(&object_path).unwrap();
                    removed += 1;
                }
                if matches!(
                    step,
                    PublicationStep::Claimed
                        | PublicationStep::ObjectPublished
                        | PublicationStep::RecordPublished
                ) {
                    assert!(records.iter().any(|lease| lease.result_keys.contains(&key)
                        && lease.object_digests.contains(&sha256(b"same"))));
                }
                Ok(())
            },
        )
        .unwrap();
    assert_eq!(writer.join().unwrap(), second);
    assert_eq!(removed, 0);
    assert_eq!(begin(&store, &unit).lookup().unwrap().unwrap(), second);
}
