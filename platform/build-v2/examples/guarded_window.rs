// Retired experiment: explicit Cargo test/doctest targets must stay empty.
#![cfg(not(any(test, doctest)))]

//! One real guarded validation window for C5b/C7 (not a test; run by hand under normal admission).
//!
//! `guarded_window --python PATH --out DIR` runs a disposable Python worker with one descendant
//! through the real bridge (`python -m atelier.build_v2.guarded_worker`) and therefore through
//! the existing broker admission, process and tree guards. Scenarios: a completed job, one crash
//! retried after confirmed cleanup and a new admission, and a cancellation while running. Each
//! holds a real checkout-style flock through the custody path and probes a conflicting installer
//! while the worker lives and after the attempt settles. Evidence is written to DIR/evidence.json.
use atelier_build_v2::failure_policy::Limits;
use atelier_build_v2::guard_adapter::{GuardedLauncher, WorkerCommand};
use atelier_build_v2::protocol::JobRequest;
use atelier_build_v2::schema::{Op, OutputFile};
use atelier_build_v2::worker_lifecycle::{JobSpec, SystemClock, job_channel, run_job};
use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::fs::{self, File, OpenOptions};
use std::os::fd::AsRawFd;
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::time::Duration;

fn arg(name: &str) -> PathBuf {
    let args: Vec<String> = std::env::args().collect();
    let at = args.iter().position(|a| a == name).expect(name);
    PathBuf::from(&args[at + 1])
}

fn lock(path: &Path) -> File {
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(path)
        .unwrap();
    // SAFETY: flock on a descriptor we own.
    assert_eq!(
        unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
        0
    );
    file
}

fn installer_refused(path: &Path) -> bool {
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .open(path)
        .unwrap();
    // SAFETY: flock on a descriptor we own; the descriptor closes when `file` drops.
    unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) != 0 }
}

fn receipt(path: &Path) -> Value {
    fs::read(path)
        .ok()
        .and_then(|bytes| serde_json::from_slice(&bytes).ok())
        .unwrap_or(Value::Null)
}

fn job() -> JobRequest {
    JobRequest {
        job_id: "window".into(),
        unit: "window/piece".into(),
        op: Op {
            kind: "fixture".into(),
            version: "1".into(),
        },
        job_dir: "/jobs/window".into(),
        script: "code/run.py".into(),
        code: vec!["code/run.py".into()],
        inputs: vec![],
        params: Default::default(),
        outputs: vec![OutputFile {
            path: "piece.glb".into(),
            install_path: None,
            required: true,
        }],
    }
}

fn main() -> ExitCode {
    let python = arg("--python");
    let out = arg("--out");
    fs::create_dir_all(&out).unwrap();
    let worker = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/disposable_worker.py");
    let mut evidence = vec![];
    let mut ok = true;
    for (name, scenario, cancel) in [
        ("complete", "normal", false),
        ("crash-retry", "crash_once", false),
        ("cancel", "hang", true),
    ] {
        let root = out.join(name);
        fs::create_dir(&root).unwrap();
        let lock_path = root.join("checkout.lock");
        let original = lock(&lock_path);
        let custody = original.try_clone().unwrap();
        drop(original); // only the custody path holds exclusion from here on
        let mut env = BTreeMap::new();
        env.insert("PATH".into(), std::env::var("PATH").unwrap_or_default());
        env.insert(
            "CRASH_MARKER".into(),
            root.join("crash-marker").display().to_string(),
        );
        let spec = JobSpec {
            job: job(),
            worker_version: "disposable-1".into(),
            command: WorkerCommand {
                program: python.clone(),
                args: vec![worker.clone().into(), scenario.into()],
                env,
                cwd: root.clone(),
            },
            purpose: format!("build-v2 C5b/C7 guarded window: {name}"),
            // A job admission reserves the full job profile; ask for exactly that ceiling.
            memory_gib: 10,
            limits: Limits {
                job: Duration::from_secs(120),
                cleanup: Duration::from_secs(60),
                overall: Some(Duration::from_secs(1800)),
            },
            report_root: root.clone(),
            custody: vec![custody],
        };
        let mut launcher = GuardedLauncher {
            bridge: vec![
                python.clone().into(),
                "-m".into(),
                "atelier.build_v2.guarded_worker".into(),
            ],
        };
        let (canceller, inbox) = job_channel();
        let mut registered = vec![];
        let report = run_job(
            &mut launcher,
            &SystemClock::new(),
            &spec,
            inbox,
            &mut |worker| {
                registered.push(json!({
                    "pid": worker.pid, "started": worker.started, "boot": worker.boot,
                    "installer_refused_while_alive": installer_refused(&lock_path),
                }));
                if cancel {
                    canceller.cancel();
                }
                Ok(())
            },
        );
        drop(spec);
        let report = match report {
            Ok(report) => report,
            Err(error) => {
                ok = false;
                evidence.push(json!({"scenario": name, "error": format!("{error:?}")}));
                continue;
            }
        };
        let attempts: Vec<Value> = report
            .attempts
            .iter()
            .map(|attempt| {
                let folder = root.join(format!("attempt-{}", attempt.attempt));
                json!({
                    "attempt": attempt.attempt,
                    "admitted": attempt.admitted,
                    "worker": attempt.worker.as_ref().map(|w| json!({"pid": w.pid, "started": w.started, "boot": w.boot})),
                    "custody": format!("{:?}", attempt.custody),
                    "process_receipt": receipt(&folder.join("memory-health.json")),
                    "tree_receipt": receipt(&folder.join("memory-health-tree.json")),
                    "timings": receipt(&folder.join("execution-timings.json")),
                })
            })
            .collect();
        evidence.push(json!({
            "scenario": name,
            "outcome": format!("{:?}", report.outcome),
            "abort": report.abort,
            "registered": registered,
            "attempts": attempts,
            "installer_refused_after_settle": installer_refused(&lock_path),
        }));
    }
    let text = serde_json::to_string_pretty(&evidence).unwrap();
    fs::write(out.join("evidence.json"), &text).unwrap();
    println!("{text}");
    if ok {
        ExitCode::SUCCESS
    } else {
        ExitCode::FAILURE
    }
}
