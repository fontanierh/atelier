// Retired experiment: explicit Cargo test/doctest targets must stay empty.
#![cfg(not(any(test, doctest)))]

//! T1b: the production build-v2 Blender job loop inside the installed Blender, run once in one
//! admitted session (`cargo run --example t1b_blender_session` under `guarded --kind job`).
//! `ATELIER_T1B_BLENDER` names the Blender binary; `ATELIER_T1B_EVIDENCE`, when set, is where the
//! session writes its evidence record. It panics, exiting non-zero, on any failed check. It is an
//! example rather than an ignored test because CI hosts have no Blender and the T0 registry admits
//! no ignored tests; its registry row stays pending until its evidence is recorded.
#[path = "../tests/support/blender.rs"]
mod support;

use atelier_build_v2::launch::*;
use atelier_build_v2::protocol::FailureKind;
use atelier_build_v2::source_hashes::sha256;
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};
use support::*;

#[cfg(not(target_os = "macos"))]
fn main() {
    eprintln!("the T1b session needs macOS: the Blender job sandbox exists only there");
    std::process::exit(2);
}

#[cfg(target_os = "macos")]
fn main() {
    let blender = PathBuf::from(std::env::var("ATELIER_T1B_BLENDER").expect("ATELIER_T1B_BLENDER"));
    let script = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../studio/atelier/build_v2/blender_worker.py")
        .canonicalize()
        .unwrap();
    let command = WorkerCommand::blender_job_loop(blender.clone(), script).unwrap();
    let op = fs::read_to_string(fixture_file("t1b/pyramid_op.py")).unwrap();
    let space = Workspace::new();
    let secret = space.path("outside/secret.txt");
    fs::create_dir(space.path("outside")).unwrap();
    fs::write(&secret, b"not an input").unwrap();
    fs::write(space.path("outside/outside_mod.py"), b"VALUE = 1\n").unwrap();
    let missing = space.path("outside/never-created.png");
    let session_started = Instant::now();
    let mut runs: Vec<serde_json::Value> = vec![];
    let mut record = |name: &str, elapsed: Duration, outcome: &JobOutcome| {
        let files: BTreeMap<String, String> = match outcome {
            JobOutcome::Completed(actual) => actual
                .iter()
                .map(|file| (file.path.clone(), sha256(&fs::read(&file.source).unwrap())))
                .collect(),
            JobOutcome::Failed(_) => BTreeMap::new(),
        };
        let failure = match outcome {
            JobOutcome::Failed(failure) => {
                serde_json::json!({"kind": format!("{:?}", failure.kind),
                                                              "message": failure.message})
            }
            JobOutcome::Completed(_) => serde_json::Value::Null,
        };
        runs.push(
            serde_json::json!({"job": name, "ms": elapsed.as_millis() as u64, "files": files,
                                     "failure": failure}),
        );
    };
    let fixture = |params: serde_json::Value| Fixture::new(&op, params);
    let a = fixture(serde_json::json!({"seed": 7, "name": "a"}));
    let b = fixture(serde_json::json!({"seed": 7, "name": "b"}));

    let started = Instant::now();
    let mut session = Loop::start(&command, BLENDER_JOB_LOOP_VERSION).unwrap();
    let loop_start_ms = started.elapsed().as_millis() as u64;
    let worker_version = session.version.clone();
    let mut run = |session: &mut Loop, fixture: &Fixture, name: &str| {
        let job = stage_job(&space, fixture, name);
        let started = Instant::now();
        let outcome = session.run(&job);
        record(name, started.elapsed(), &outcome);
        (outcome, job)
    };

    // Order independence and a fresh process: the same export bytes every time.
    let mut produced = BTreeMap::new();
    for (name, fixture) in [
        ("alone", &a),
        ("b-first", &b),
        ("b-then-a", &a),
        ("a-first", &a),
        ("a-then-b", &b),
        ("a-b-a", &a),
    ] {
        let (outcome, job) = run(&mut session, fixture, name);
        assert_eq!(
            completed_paths(&outcome),
            ["model.glb", "probe.json"],
            "{name}"
        );
        produced.insert(name, read_outputs(&job));
    }
    // Seed determinism: same seed same bytes (above), another seed other bytes.
    let (outcome, seed_job) = run(
        &mut session,
        &fixture(serde_json::json!({"seed": 8, "name": "a"})),
        "seed-8",
    );
    assert_eq!(completed_paths(&outcome).len(), 2);
    let seed_8 = read_outputs(&seed_job);

    // Failures publish nothing, and the next job behaves.
    let attempts = |attempts: serde_json::Value| {
        fixture(serde_json::json!({"seed": 7, "name": "a", "attempts": attempts}))
    };
    let failure = attempts(serde_json::json!(["raise ValueError('t1b failure')"]));
    let (outcome, _) = run(&mut session, &failure, "raises");
    assert_eq!(failed(&outcome), FailureKind::Job);
    assert!(publish(&space, &failure, outcome).is_err());
    let (outcome, after_failure) = run(&mut session, &a, "after-failure");
    assert_eq!(completed_paths(&outcome).len(), 2);
    let after_failure = read_outputs(&after_failure);
    let mut refusals = BTreeMap::new();
    for (name, fixture) in [
        (
            "extra",
            attempts(serde_json::json!([
                "(context.output_dir / 'stray.bin').write_bytes(b'x')"
            ])),
        ),
        (
            "missing",
            fixture(serde_json::json!({"seed": 7, "name": "a", "skip_probe": true})),
        ),
        (
            "link",
            attempts(serde_json::json!([
                "os.symlink('/etc/hosts', context.output_dir / 'link.glb')"
            ])),
        ),
    ] {
        let (outcome, _) = run(&mut session, &fixture, name);
        let refusal = publish(&space, &fixture, outcome).unwrap_err();
        assert!(!published(&space, &fixture), "{name} published");
        refusals.insert(name, refusal);
    }

    // Undeclared access: each attempt is its own job and must fail as a dependency failure.
    let mut denials = BTreeMap::new();
    for (name, attempt) in [
        ("read-existing", format!("open({:?}).read()", secret)),
        ("check-missing", format!("os.path.exists({:?})", missing)),
        (
            "list-folder",
            format!("os.listdir({:?})", space.path("outside")),
        ),
        (
            "code-load",
            format!(
                "sys.path.insert(0, {:?})\nimport outside_mod",
                space.path("outside")
            ),
        ),
        (
            "network",
            "socket.create_connection(('127.0.0.1', 9), timeout=2)".to_string(),
        ),
        (
            "native-read-existing",
            format!("bpy.data.images.load({:?})", secret),
        ),
    ] {
        let (outcome, _) = run(&mut session, &attempts(serde_json::json!([attempt])), name);
        assert_eq!(failed(&outcome), FailureKind::Dependency, "{name}");
        denials.insert(name, "dependency");
    }
    // The documented gap: a native (C) probe of a missing undeclared path is not intercepted.
    let gap = attempts(serde_json::json!([format!(
        "try:\n    bpy.data.images.load({:?})\nexcept RuntimeError:\n    pass",
        missing
    )]));
    let (outcome, _) = run(&mut session, &gap, "native-check-missing");
    let native_missing = match &outcome {
        JobOutcome::Completed(_) => "not intercepted (documented gap)".to_string(),
        JobOutcome::Failed(failure) => format!("{:?}: {}", failure.kind, failure.message),
    };

    // A good job publishes, then the loop stops cleanly.
    let (outcome, _) = run(&mut session, &a, "publish");
    assert_eq!(
        publish(&space, &a, outcome).unwrap(),
        ["model.glb", "probe.json"]
    );
    let loop_status = session.close();
    assert!(loop_status.success(), "{loop_status}");

    // A fresh loop process gives the same bytes.
    let mut fresh = Loop::start(&command, BLENDER_JOB_LOOP_VERSION).unwrap();
    let (outcome, fresh_job) = run(&mut fresh, &a, "fresh-process");
    assert_eq!(completed_paths(&outcome).len(), 2);
    let fresh_outputs = read_outputs(&fresh_job);
    assert!(fresh.close().success());

    // Export bytes: equal in every order and process; the probe too except, if Blender's Python
    // ignores the declared hash seed, its `hash` field.
    let probe = |bytes: &[u8]| -> serde_json::Value { serde_json::from_slice(bytes).unwrap() };
    let without_hash = |bytes: &[u8]| {
        let mut value = probe(bytes);
        value.as_object_mut().unwrap().remove("hash");
        value
    };
    for name in ["alone", "b-then-a", "a-first", "a-b-a"] {
        assert_eq!(produced[name].0, fresh_outputs.0, "{name} export bytes");
        assert_eq!(
            without_hash(&produced[name].1),
            without_hash(&fresh_outputs.1),
            "{name} probe"
        );
    }
    assert_eq!(after_failure.0, fresh_outputs.0);
    assert_eq!(produced["b-first"].0, produced["a-then-b"].0);
    assert_ne!(produced["b-first"].0, fresh_outputs.0);
    assert_ne!(seed_8.0, fresh_outputs.0, "another seed moves the object");
    let hashes: BTreeSet<_> = produced
        .values()
        .chain([&fresh_outputs, &after_failure])
        .map(|outputs| probe(&outputs.1)["hash"].to_string())
        .collect();

    // Exactly the selected payload, params, seed and declared code reached the job.
    let seen = probe(&fresh_outputs.1);
    let selected = serde_json::to_vec(
        &serde_json::from_slice::<serde_json::Value>(
            &fs::read(fixture_file("t1b/pyramid.json")).unwrap(),
        )
        .unwrap()["pyramid"],
    )
    .unwrap();
    assert_eq!(seen["inputs"], serde_json::json!({"mesh": "in/mesh.json"}));
    assert_eq!(seen["params"], serde_json::json!({"seed": 7, "name": "a"}));
    assert_eq!(seen["seed"], 7);
    assert_eq!(seen["listing"], serde_json::json!(["in", "ops", "output"]));
    assert_eq!(
        seen["job_modules"],
        serde_json::json!(["atelier_job_entry"])
    );
    assert_eq!(
        seen["factory_scene_before"],
        serde_json::json!([[], [], []])
    );

    // Corner, UV and material fidelity of the export.
    let (document, triangles) = glb_triangles(&fresh_outputs.0);
    assert_eq!(triangles, expected_triangles());
    assert_eq!(document["nodes"].as_array().unwrap().len(), 1);
    assert_eq!(document["nodes"][0]["name"], "a");

    let evidence = serde_json::json!({
        "worker_version": worker_version,
        "blender": {"binary": blender, "version": seen["blender"], "build_hash": seen["build_hash"],
                    "addons": seen["addons"]},
        "loop_start_ms": loop_start_ms,
        "session_ms": session_started.elapsed().as_millis() as u64,
        "job_runs": runs.len(),
        "loop_processes": 2,
        "export_sha256": sha256(&fresh_outputs.0),
        "probe_sha256": sha256(&fresh_outputs.1),
        "seed_8_export_sha256": sha256(&seed_8.0),
        "selected_sha256": seen["selected_sha256"],
        "hash_seed": {"env": seen["hash_seed"], "hash_randomization": seen["hash_randomization"],
                      "distinct_hash_values": hashes.len()},
        "refusals": refusals,
        "denials": denials,
        "native_missing_check": native_missing,
        "loop_exit": loop_status.to_string(),
        "runs": runs,
        "selected_bytes_len": selected.len(),
    });
    if let Ok(path) = std::env::var("ATELIER_T1B_EVIDENCE") {
        fs::write(path, serde_json::to_vec_pretty(&evidence).unwrap()).unwrap();
    }
    println!("{}", serde_json::to_string_pretty(&evidence).unwrap());
}
