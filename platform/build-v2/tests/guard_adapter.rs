//! T0 real-process tests of the guard adapter and job driver, with a stand-in bridge
//! (tests/fixtures/fake_bridge.py) instead of real admission, and a disposable Python worker that
//! owns one descendant. Every wait is a bounded handshake; nothing sleeps.
use atelier_build_v2::failure_policy::{CleanupState, End, Limits, Stop};
use atelier_build_v2::guard_adapter::*;
use atelier_build_v2::leases::ProcessIdentity;
use atelier_build_v2::protocol::{JobRequest, Response, read_frame};
use atelier_build_v2::schema::{Op, OutputFile};
use atelier_build_v2::worker_lifecycle::*;
use serde_json::Value;
use std::collections::BTreeMap;
use std::ffi::OsString;
use std::fs::{self, File, OpenOptions};
use std::io;
use std::os::fd::AsRawFd;
use std::os::unix::ffi::OsStringExt;
use std::os::unix::fs::MetadataExt;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant};

static SERIAL: AtomicU64 = AtomicU64::new(0);
/// One bound for every handshake in these tests.
const BOUND: Duration = Duration::from_secs(5);

struct Workspace(PathBuf);
impl Workspace {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "atelier-v2-guard-{}-{}",
            std::process::id(),
            SERIAL.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        Self(path)
    }
    fn path(&self, name: &str) -> PathBuf {
        self.0.join(name)
    }
}
impl Drop for Workspace {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn fixture(name: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures")
        .join(name)
}

fn launcher(scenario: &str) -> GuardedLauncher {
    GuardedLauncher {
        bridge: vec![
            "python3".into(),
            fixture("fake_bridge.py").into(),
            scenario.into(),
        ],
    }
}

fn worker(space: &Workspace, scenario: &str) -> WorkerCommand {
    let mut env = BTreeMap::new();
    env.insert("PATH".into(), std::env::var("PATH").unwrap());
    env.insert(
        "WORKER_FD_REPORT".into(),
        space.path("worker-fds.json").display().to_string(),
    );
    env.insert(
        "CRASH_MARKER".into(),
        space.path("crash-marker").display().to_string(),
    );
    env.insert(
        "JOB_LOG".into(),
        space.path("jobs.log").display().to_string(),
    );
    WorkerCommand {
        program: "python3".into(),
        args: vec![fixture("disposable_worker.py").into(), scenario.into()],
        env,
        cwd: space.0.clone(),
    }
}

fn request(space: &Workspace, name: &str, custody: Vec<File>) -> AdmissionRequest {
    AdmissionRequest {
        purpose: "build-v2 T0 fake guard".into(),
        memory_gib: 1,
        execution_limit: Duration::from_secs(30),
        queue_limit: None,
        report_dir: space.path(name),
        custody,
    }
}

fn next(events: &mpsc::Receiver<AttemptEvent>) -> LaunchEvent {
    events
        .recv_timeout(BOUND)
        .expect("bridge event within bound")
        .event
}

/// A conflicting installer: a separate open file description asking for exclusion.
fn try_exclusive(path: &Path) -> bool {
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .open(path)
        .unwrap();
    // SAFETY: flock on a descriptor we own.
    unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) == 0 }
}

/// The installer gets exclusion within the bound: a blocking flock in a helper thread, so a
/// concurrent test's fork (which briefly shares every descriptor until exec) cannot flake it.
fn acquired_within(path: &Path, bound: Duration) -> bool {
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .open(path)
        .unwrap();
    let (done, acquired) = mpsc::channel();
    thread::spawn(move || {
        // SAFETY: flock on a descriptor this thread owns.
        let ok = unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX) == 0 };
        let _ = done.send(ok);
    });
    acquired.recv_timeout(bound).unwrap_or(false)
}

fn locked(path: &Path) -> File {
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

fn json(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

fn inode(file: &File) -> (u64, u64) {
    let meta = file.metadata().unwrap();
    (meta.dev(), meta.ino())
}

fn holds(record: &Value, wanted: (u64, u64)) -> bool {
    record["open"]
        .as_object()
        .unwrap()
        .values()
        .any(|pair| (pair[0].as_u64().unwrap(), pair[1].as_u64().unwrap()) == wanted)
}

#[test]
fn bridge_events_decode_strictly() {
    let receipts = Path::new("r");
    assert_eq!(
        decode_event(r#"{"event":"queued"}"#, receipts),
        LaunchEvent::Queued
    );
    assert_eq!(
        decode_event(
            r#"{"event":"child_exited","pid":7,"started":"s","boot":"b","returncode":-9,"stopped_by":null}"#,
            receipts
        ),
        LaunchEvent::ChildExited {
            worker: ProcessIdentity {
                pid: 7,
                boot: "b".into(),
                started: "s".into()
            },
            exit: ExitInfo::Signal(9),
            stopped_by: None,
        }
    );
    assert_eq!(
        decode_event(
            r#"{"event":"monitor","pid":8,"started":"80","boot":"b","invocation":"0123456789abcdef0123456789abcdef"}"#,
            receipts
        ),
        LaunchEvent::Monitor {
            monitor: ProcessIdentity {
                pid: 8,
                boot: "b".into(),
                started: "80".into()
            },
            invocation: "0123456789abcdef0123456789abcdef".into(),
        }
    );
    for bad in [
        "not json",
        r#"{"event":"queued","extra":1}"#,
        r#"{"event":"child_started","pid":0,"started":"s","boot":"b"}"#,
        r#"{"event":"child_started","pid":7,"started":"","boot":"b"}"#,
        r#"{"event":"finished","cleanup":"probably","reason":null}"#,
        r#"{"event":"monitor","pid":0,"started":"s","boot":"b","invocation":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}"#,
        r#"{"event":"monitor","pid":7,"started":"s","boot":"b","invocation":"short"}"#,
        r#"{"event":"monitor","pid":7,"started":"s","boot":"b","invocation":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}"#,
        r#"{"event":"monitor","pid":7,"started":"s","boot":"b"}"#,
        r#"{"event":"fault","reason":"the published custody monitor identity changed or went missing"}"#,
    ] {
        assert!(
            matches!(decode_event(bad, receipts), LaunchEvent::Fault(_)),
            "{bad}"
        );
    }
}

#[test]
fn bridge_alone_receives_its_descriptors_and_the_worker_only_the_protocol_pipe() {
    let space = Workspace::new();
    let lock_path = space.path("checkout.lock");
    let original = locked(&lock_path);
    let custody = original.try_clone().unwrap();
    let custody_inode = inode(&custody);
    let (sink, events) = mpsc::channel();
    let mut attempt = launcher("normal")
        .submit(
            1,
            &worker(&space, "normal"),
            request(&space, "attempt-1", vec![custody]),
            sink,
        )
        .unwrap();
    assert_eq!(next(&events), LaunchEvent::Queued);
    assert_eq!(next(&events), LaunchEvent::Admitted);
    assert!(matches!(next(&events), LaunchEvent::ChildStarted { .. }));
    // With custody the bridge also reports its custody monitor.
    assert!(matches!(next(&events), LaunchEvent::Monitor { .. }));
    let (mut response, request) = attempt.take_pipes().unwrap();
    let hello = read_frame::<_, Response>(&mut response).unwrap();
    assert!(matches!(hello, Some(Response::Hello { .. })));
    drop((response, request)); // the worker then sees EOF and exits cleanly
    assert!(matches!(
        next(&events),
        LaunchEvent::ChildExited {
            exit: ExitInfo::Code(0),
            stopped_by: None,
            ..
        }
    ));
    assert!(matches!(
        next(&events),
        LaunchEvent::Finished {
            cleanup: CleanupReceipt::Confirmed,
            ..
        }
    ));
    attempt.wait().unwrap();
    let bridge = json(&space.path("attempt-1/inherited.json"));
    let open = bridge["open"].as_object().unwrap();
    let mut expected: Vec<i64> = ["events", "liveness", "spec", "request", "response"]
        .iter()
        .map(|name| bridge[*name].as_i64().unwrap())
        .chain(
            bridge["custody"]
                .as_array()
                .unwrap()
                .iter()
                .map(|fd| fd.as_i64().unwrap()),
        )
        .collect();
    expected.sort();
    let mut got: Vec<i64> = open.keys().map(|fd| fd.parse().unwrap()).collect();
    got.sort();
    assert_eq!(
        got, expected,
        "the bridge inherits exactly its own descriptors"
    );
    assert!(holds(&bridge, custody_inode));
    assert_eq!(
        bridge["cwd"].as_str().map(PathBuf::from),
        Some(fs::canonicalize(&space.0).unwrap())
    );
    let worker_fds = json(&space.path("worker-fds.json"));
    let mut worker_open: Vec<i64> = worker_fds["open"]
        .as_object()
        .unwrap()
        .keys()
        .map(|fd| fd.parse().unwrap())
        .collect();
    worker_open.sort();
    let mut protocol = vec![
        worker_fds["request_fd"].as_i64().unwrap(),
        worker_fds["response_fd"].as_i64().unwrap(),
    ];
    protocol.sort();
    assert_eq!(
        worker_open, protocol,
        "the worker inherits only the protocol pipe"
    );
    assert!(
        !holds(&worker_fds, custody_inode),
        "custody never reaches the worker"
    );
    drop(original);
}

#[test]
fn stop_signals_only_the_unreaped_bridge_and_never_a_stale_pid() {
    let space = Workspace::new();
    let (sink, events) = mpsc::channel();
    let mut attempt = launcher("queue_forever")
        .submit(
            1,
            &worker(&space, "normal"),
            request(&space, "attempt-1", vec![]),
            sink,
        )
        .unwrap();
    assert_eq!(next(&events), LaunchEvent::Queued);
    // A queued stop withdraws: no child was spawned and the receipt confirms it.
    assert!(attempt.stop().unwrap());
    assert!(matches!(
        next(&events),
        LaunchEvent::Finished {
            cleanup: CleanupReceipt::Confirmed,
            ..
        }
    ));
    attempt.wait().unwrap();
    assert!(
        !space.path("attempt-1/stdout.log").exists(),
        "no worker was started"
    );
    // Exited and reaped: its PID is no longer ours, so nothing is signalled.
    assert!(!attempt.stop().unwrap());
    assert!(!attempt.stop().unwrap());
}

#[test]
fn custody_duplicate_keeps_exclusion_after_the_launcher_drops_its_own_descriptor() {
    let space = Workspace::new();
    let lock_path = space.path("checkout.lock");
    let original = locked(&lock_path);
    // The same open file description (F_DUPFD_CLOEXEC), as B3's duplicate_for_custodian returns.
    let custody = original.try_clone().unwrap();
    let (sink, events) = mpsc::channel();
    let mut attempt = launcher("queue_forever")
        .submit(
            1,
            &worker(&space, "normal"),
            request(&space, "attempt-1", vec![custody]),
            sink,
        )
        .unwrap();
    assert_eq!(next(&events), LaunchEvent::Queued);
    // Closing the launcher's own descriptor does not unlock: BSD flock, no LOCK_UN on drop.
    drop(original);
    assert!(
        !try_exclusive(&lock_path),
        "the custodian's duplicate still excludes installers"
    );
    assert!(attempt.stop().unwrap());
    assert!(matches!(next(&events), LaunchEvent::Finished { .. }));
    attempt.wait().unwrap();
    // The last descriptor of the description closed with the custodian.
    assert!(acquired_within(&lock_path, BOUND));
}

#[test]
fn controller_loss_stops_the_attempt_through_the_liveness_pipe() {
    let space = Workspace::new();
    let (sink, events) = mpsc::channel();
    let attempt = launcher("queue_forever")
        .submit(
            1,
            &worker(&space, "normal"),
            request(&space, "attempt-1", vec![]),
            sink,
        )
        .unwrap();
    assert_eq!(next(&events), LaunchEvent::Queued);
    drop(attempt);
    assert!(matches!(next(&events), LaunchEvent::Finished { .. }));
    assert!(space.path("attempt-1/liveness-eof").exists());
}

fn job() -> JobRequest {
    JobRequest {
        job_id: "job".into(),
        unit: "fixture/piece".into(),
        op: Op {
            kind: "fixture".into(),
            version: "1".into(),
        },
        job_dir: "/jobs/job".into(),
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

fn spec(space: &Workspace, scenario: &str, cleanup_ms: u64) -> JobSpec {
    JobSpec {
        job: job(),
        worker_version: "disposable-1".into(),
        command: worker(space, scenario),
        purpose: "build-v2 T0 fake guard".into(),
        memory_gib: 1,
        limits: Limits {
            job: Duration::from_secs(30),
            cleanup: Duration::from_millis(cleanup_ms),
            overall: Some(Duration::from_secs(60)),
        },
        report_root: space.0.clone(),
        custody: vec![],
    }
}

fn drive(
    scenario: &str,
    bridge: &str,
    cancel_on_register: bool,
    cleanup_ms: u64,
) -> (Report, Vec<ProcessIdentity>, Workspace) {
    let space = Workspace::new();
    let spec = spec(&space, scenario, cleanup_ms);
    let (canceller, inbox) = job_channel();
    let mut registered = vec![];
    let report = run_job(
        &mut launcher(bridge),
        &SystemClock::new(),
        &spec,
        inbox,
        &mut |worker| {
            registered.push(worker.clone());
            if cancel_on_register {
                canceller.cancel();
            }
            Ok(())
        },
    )
    .unwrap();
    (report, registered, space)
}

#[test]
fn driver_runs_a_job_over_dedicated_pipes_and_registers_the_worker_first() {
    let (report, registered, _space) = drive("normal", "normal", false, 3_000);
    assert_eq!(report.outcome.end, End::Completed);
    assert_eq!(report.outputs.unwrap().files, vec!["piece.glb".to_string()]);
    assert_eq!(report.attempts.len(), 1);
    assert_eq!(report.attempts[0].custody, Custody::Released);
    assert_eq!(registered, vec![report.attempts[0].worker.clone().unwrap()]);
}

#[test]
fn driver_retries_one_crash_with_a_fresh_admission_and_report_folder() {
    let (report, registered, space) = drive("crash_once", "normal", false, 3_000);
    assert_eq!(report.outcome.end, End::Completed);
    assert_eq!(report.outcome.attempts, 2);
    assert_eq!(registered.len(), 2);
    assert_ne!(registered[0], registered[1]);
    assert!(space.path("attempt-1/inherited.json").exists());
    assert!(space.path("attempt-2/inherited.json").exists());
    assert!(
        report
            .attempts
            .iter()
            .all(|a| a.custody == Custody::Released)
    );

    let (report, _, _space) = drive("crash", "normal", false, 3_000);
    assert_eq!(report.outcome.end, End::Failed(Stop::Crash));
    assert_eq!(report.outcome.attempts, 2);
}

#[test]
fn driver_never_retries_guard_stops_cancellation_or_foreign_exits() {
    let (report, _, _s) = drive("hang", "guard_stop", false, 3_000);
    assert_eq!(report.outcome.end, End::Failed(Stop::GuardStop));
    assert_eq!(report.attempts.len(), 1);

    let (report, _, _s) = drive("hang", "normal", true, 3_000);
    assert_eq!(report.outcome.end, End::Failed(Stop::Cancelled));
    assert_eq!(report.attempts.len(), 1);
    assert_eq!(report.attempts[0].custody, Custody::Released);

    let (report, _, _s) = drive("crash", "foreign_exit", false, 3_000);
    assert_eq!(report.outcome.end, End::Failed(Stop::Protocol));
    assert_eq!(report.attempts.len(), 1);
}

#[test]
fn driver_holds_an_attempt_whose_cleanup_is_unconfirmed() {
    let (report, _, _s) = drive("crash", "unconfirmed", false, 200);
    assert_eq!(report.outcome.end, End::Failed(Stop::Crash));
    assert!(matches!(
        report.outcome.cleanup,
        CleanupState::Unconfirmed(_)
    ));
    assert_eq!(
        report.attempts.len(),
        1,
        "a held attempt is never relaunched"
    );
    assert_eq!(
        report.attempts[0].custody,
        Custody::Held("scripted uncertain cleanup".into())
    );
}

/// Larger than any pipe buffer, so the launcher is still writing the spec when the bridge closes it.
fn padded(mut command: WorkerCommand) -> WorkerCommand {
    command.env.insert("PADDING".into(), "x".repeat(1 << 20));
    command
}

#[test]
fn submit_refuses_a_non_utf8_argument_before_starting_any_admission_owner() {
    let space = Workspace::new();
    let (sink, events) = mpsc::channel();
    let mut command = worker(&space, "normal");
    command.args.push(OsString::from_vec(vec![0xff, 0xfe]));
    let refused =
        launcher("normal").submit(1, &command, request(&space, "attempt-1", vec![]), sink);
    assert_eq!(
        refused.err().map(|error| error.kind()),
        Some(io::ErrorKind::InvalidInput)
    );
    assert!(
        !space.path("attempt-1").exists(),
        "refused before the report folder, so no bridge ever started"
    );
    assert!(events.recv_timeout(Duration::from_millis(200)).is_err());
}

#[test]
fn a_spec_write_failure_after_the_spawn_ends_unconfirmed_and_never_errs() {
    let space = Workspace::new();
    let (sink, events) = mpsc::channel();
    let mut attempt = launcher("spec_closed")
        .submit(
            1,
            &padded(worker(&space, "normal")),
            request(&space, "attempt-1", vec![]),
            sink,
        )
        .expect("an admission owner exists, so submit must not err");
    assert!(space.path("attempt-1/inherited.json").exists());
    assert!(
        attempt.take_pipes().is_none(),
        "no protocol pipes without a spec"
    );
    assert!(matches!(
        next(&events),
        LaunchEvent::Finished {
            cleanup: CleanupReceipt::Unconfirmed { .. },
            ..
        }
    ));
    assert!(
        !attempt.wait().unwrap().success(),
        "withdrawn by the launcher's SIGTERM"
    );
}

#[test]
fn driver_reports_launch_failure_only_before_a_spawn() {
    // Refused before any spawn: a launch failure, nothing held, nothing started.
    let space = Workspace::new();
    let mut job = spec(&space, "normal", 200);
    job.command.args.push(OsString::from_vec(vec![0xff]));
    let (_canceller, inbox) = job_channel();
    let report = run_job(
        &mut launcher("normal"),
        &SystemClock::new(),
        &job,
        inbox,
        &mut |_| Ok(()),
    )
    .unwrap();
    assert!(report.abort.unwrap().starts_with("launch failed"));
    assert_eq!(report.attempts.len(), 1);
    assert_eq!(report.attempts[0].custody, Custody::Released);
    assert!(!space.path("attempt-1").exists());

    // A spawned bridge whose spec write failed is not a launch failure: without a cleanup
    // receipt the attempt is held, never released, and never relaunched.
    let space = Workspace::new();
    let mut job = spec(&space, "normal", 200);
    job.command = padded(job.command);
    let (_canceller, inbox) = job_channel();
    let report = run_job(
        &mut launcher("spec_closed"),
        &SystemClock::new(),
        &job,
        inbox,
        &mut |_| Ok(()),
    )
    .unwrap();
    assert!(
        !report
            .abort
            .unwrap_or_default()
            .starts_with("launch failed")
    );
    assert_eq!(report.attempts.len(), 1);
    assert!(matches!(report.attempts[0].custody, Custody::Held(_)));
    assert!(space.path("attempt-1/inherited.json").exists());
}

#[test]
fn a_worker_that_stops_reading_cannot_block_the_overall_deadline() {
    // Paid review: hello, then the worker never reads; the job request is larger than any pipe
    // buffer. The 1 s overall deadline must still end the job long before the 120 s job limit.
    let space = Workspace::new();
    let mut job = spec(&space, "deaf", 200);
    job.limits = Limits {
        job: Duration::from_secs(120),
        cleanup: Duration::from_millis(200),
        overall: Some(Duration::from_secs(1)),
    };
    job.job
        .params
        .insert("padding".into(), Value::String("x".repeat(1 << 20)));
    let (_canceller, inbox) = job_channel();
    let began = std::time::Instant::now();
    let report = run_job(
        &mut launcher("normal"),
        &SystemClock::new(),
        &job,
        inbox,
        &mut |_| Ok(()),
    )
    .unwrap();
    assert!(
        began.elapsed() < Duration::from_secs(10),
        "returned in {:?}",
        began.elapsed()
    );
    assert_eq!(report.outcome.end, End::Failed(Stop::OverallDeadline));
    assert_eq!(report.attempts.len(), 1);
}

#[test]
fn concurrent_handshakes_stay_within_bound() {
    // Two attempts at once must not share descriptors or events.
    let handles: Vec<_> = (0..2)
        .map(|_| thread::spawn(|| drive("normal", "normal", false, 3_000).0.outcome.end))
        .collect();
    for handle in handles {
        assert_eq!(handle.join().unwrap(), End::Completed);
    }
}

fn key(job_spec: &JobSpec) -> SessionKey {
    SessionKey {
        worker_version: job_spec.worker_version.clone(),
        command: job_spec.command.clone(),
        memory_gib: job_spec.memory_gib,
        sandbox: JobSandbox::NoFork,
        custody: Default::default(),
    }
}

fn session_spec(space: &Workspace, job_spec: &JobSpec) -> SessionSpec {
    SessionSpec {
        key: key(job_spec),
        purpose: job_spec.purpose.clone(),
        config: atelier_build_v2::session_lifecycle::SessionConfig::single(
            Duration::from_secs(3),
            Duration::from_secs(30),
        ),
        report_root: space.0.clone(),
        custody: vec![],
    }
}

fn unit_with(id: &str, job_id: &str, limits: Limits, key: SessionKey) -> SessionUnit {
    let mut request = job();
    request.job_id = job_id.into();
    SessionUnit {
        plan: atelier_build_v2::session_lifecycle::UnitPlan {
            id: id.into(),
            limits,
        },
        job: request,
        key,
    }
}

#[test]
fn run_session_hands_each_settled_unit_off_without_waiting_for_its_receiver() {
    let space = Workspace::new();
    let job_spec = spec(&space, "normal", 3_000);
    let session = session_spec(&space, &job_spec);
    let (handle, inbox) = session_channel();
    handle.submit(unit_with("a", "a", job_spec.limits, key(&job_spec)));
    handle.submit(unit_with("a", "a", job_spec.limits, key(&job_spec))); // a duplicate id is refused, never dropped
    handle.submit(unit_with("b", "b", job_spec.limits, key(&job_spec)));
    handle.close();
    handle.submit(unit_with("c", "c", job_spec.limits, key(&job_spec))); // after close: refused
    // Nobody reads the records until the session is over: publication never blocks it.
    let (published, records) = mpsc::channel();
    let mut registered = vec![];
    let report = run_session(
        &mut launcher("normal"),
        &SystemClock::new(),
        &session,
        inbox,
        &mut |unit, worker| {
            registered.push((unit.clone(), worker.clone()));
            Ok(())
        },
        published,
    )
    .unwrap();
    let records: Vec<_> = records.try_iter().collect();
    assert_eq!(
        records
            .iter()
            .map(|r| (r.unit.as_str(), r.refused.is_some()))
            .collect::<Vec<_>>(),
        vec![("a", true), ("c", true), ("a", false), ("b", false)],
        "refusals are handed off at once, settled units as each settles"
    );
    assert!(records[2..].iter().all(|r| r.outcome.end == End::Completed));
    assert_eq!(report.units, records[2..].to_vec());
    assert_eq!(report.refused, records[..2].to_vec());
    assert!(
        report
            .sessions
            .iter()
            .all(|s| s.custody == Custody::Released),
        "every session confirmed clean"
    );
    assert_eq!(
        registered
            .iter()
            .map(|(unit, _)| unit.as_str())
            .collect::<Vec<_>>(),
        vec!["a", "b"],
        "each unit's lease gets its worker before the unit runs"
    );

    // A receiver that is gone never ends or blocks the session either.
    let space = Workspace::new();
    let session = session_spec(&space, &job_spec);
    let (handle, inbox) = session_channel();
    handle.submit(unit_with("a", "a", job_spec.limits, key(&job_spec)));
    handle.close();
    let (published, records) = mpsc::channel();
    drop(records);
    let report = run_session(
        &mut launcher("normal"),
        &SystemClock::new(),
        &session,
        inbox,
        &mut |_, _| Ok(()),
        published,
    )
    .unwrap();
    assert_eq!(report.units[0].outcome.end, End::Completed);
}

#[test]
fn a_cancel_sent_before_run_job_cancels_the_queued_job() {
    // Review of #646: the cancel is already in the inbox when run_job starts.
    let space = Workspace::new();
    let job = spec(&space, "normal", 3_000);
    let (canceller, inbox) = job_channel();
    canceller.cancel();
    let report = run_job(
        &mut launcher("queue_forever"),
        &SystemClock::new(),
        &job,
        inbox,
        &mut |_| Ok(()),
    )
    .unwrap();
    assert_eq!(report.outcome.end, End::Failed(Stop::Cancelled));
    assert_eq!(report.outcome.attempts, 0, "nothing was launched");
    assert_eq!(report.attempts.len(), 1, "the queued request was withdrawn");
    // The stop can reach the bridge before it handles signals; without a receipt the request
    // is held, which is still settled and never relaunched.
    assert_ne!(report.attempts[0].custody, Custody::Pending);
    assert_eq!(report.attempts[0].worker, None);
}

#[test]
fn run_session_refuses_a_unit_with_another_key_or_a_used_job_id() {
    let space = Workspace::new();
    let job_spec = spec(&space, "normal", 3_000);
    let session = session_spec(&space, &job_spec);
    let (handle, inbox) = session_channel();
    let mut other = key(&job_spec);
    other.memory_gib += 1;
    handle.submit(unit_with("a", "a", job_spec.limits, key(&job_spec)));
    handle.submit(unit_with("x", "x", job_spec.limits, other));
    handle.submit(unit_with("y", "a", job_spec.limits, key(&job_spec)));
    handle.close();
    let (published, records) = mpsc::channel();
    let report = run_session(
        &mut launcher("normal"),
        &SystemClock::new(),
        &session,
        inbox,
        &mut |_, _| Ok(()),
        published,
    )
    .unwrap();
    let records: Vec<_> = records.try_iter().collect();
    assert_eq!(
        records
            .iter()
            .map(|r| (r.unit.as_str(), r.refused.is_some()))
            .collect::<Vec<_>>(),
        vec![("x", true), ("y", true), ("a", false)]
    );
    assert!(records[0].abort.as_deref().unwrap().contains("differs"));
    assert!(records[1].abort.as_deref().unwrap().contains("job id"));
    assert_eq!(report.units.len(), 1, "nothing was queued for x or y");
    assert_eq!(report.units[0].outcome.end, End::Completed);
}

#[test]
fn run_session_refuses_custody_that_is_not_its_keys_custody_set() {
    let space = Workspace::new();
    let job_spec = spec(&space, "normal", 3_000);
    let lock = locked(&space.path("checkout.lock"));
    let identity = CustodyIdentity::of(&lock, LockScope::Exclusive).unwrap();
    let (descriptor_only, keyed_only) = {
        let mut a = session_spec(&space, &job_spec);
        a.custody = vec![lock.try_clone().unwrap()];
        let mut b = session_spec(&space, &job_spec);
        b.key.custody.insert(identity);
        (a, b)
    };
    for session in [descriptor_only, keyed_only] {
        let (handle, inbox) = session_channel();
        handle.close();
        let (published, _records) = mpsc::channel();
        assert!(matches!(
            run_session(
                &mut launcher("normal"),
                &SystemClock::new(),
                &session,
                inbox,
                &mut |_, _| Ok(()),
                published,
            ),
            Err(LifecycleError::Invariant(_))
        ));
    }
    assert!(!space.path("attempt-1").exists(), "no session was started");
    // The matching set is accepted.
    let mut session = session_spec(&space, &job_spec);
    session.custody = vec![lock.try_clone().unwrap()];
    session.key.custody.insert(identity);
    let (handle, inbox) = session_channel();
    handle.close();
    let (published, _records) = mpsc::channel();
    let report = run_session(
        &mut launcher("normal"),
        &SystemClock::new(),
        &session,
        inbox,
        &mut |_, _| Ok(()),
        published,
    )
    .unwrap();
    assert!(report.units.is_empty() && report.sessions.is_empty());
}

fn lock_with(path: &Path, operation: libc::c_int) -> File {
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(path)
        .unwrap();
    // SAFETY: flock on a descriptor we own.
    assert_eq!(
        unsafe { libc::flock(file.as_raw_fd(), operation | libc::LOCK_NB) },
        0
    );
    file
}

fn custody_run(space: &Workspace, job_spec: &JobSpec, file: &File, scope: LockScope) -> bool {
    let mut session = session_spec(space, job_spec);
    session.custody = vec![file.try_clone().unwrap()];
    session
        .key
        .custody
        .insert(CustodyIdentity::of(file, scope).unwrap());
    let (handle, inbox) = session_channel();
    handle.close();
    let (published, _records) = mpsc::channel();
    run_session(
        &mut launcher("normal"),
        &SystemClock::new(),
        &session,
        inbox,
        &mut |_, _| Ok(()),
        published,
    )
    .is_ok()
}

#[test]
fn run_session_refuses_custody_not_held_in_its_declared_scope() {
    let space = Workspace::new();
    let job_spec = spec(&space, "normal", 3_000);
    let exclusive = lock_with(&space.path("build.lock"), libc::LOCK_EX);
    assert!(custody_run(
        &space,
        &job_spec,
        &exclusive,
        LockScope::Exclusive
    ));
    assert!(
        !custody_run(&space, &job_spec, &exclusive, LockScope::Shared),
        "a scope mismatch is refused"
    );
    drop(exclusive);
    let shared = lock_with(&space.path("content.lock"), libc::LOCK_SH);
    assert!(custody_run(&space, &job_spec, &shared, LockScope::Shared));
    assert!(!custody_run(
        &space,
        &job_spec,
        &shared,
        LockScope::Exclusive
    ));
    drop(shared);
    // The same lock file, opened but never locked: same device and inode, no custody.
    let unlocked = File::open(space.path("build.lock")).unwrap();
    assert!(
        !custody_run(&space, &job_spec, &unlocked, LockScope::Exclusive),
        "an unlocked handle is refused"
    );
    assert!(!custody_run(
        &space,
        &job_spec,
        &unlocked,
        LockScope::Shared
    ));
    // The probe never takes the lock away: the file is still free to lock afterwards.
    let again = lock_with(&space.path("build.lock"), libc::LOCK_EX);
    drop(again);
}

fn pinned(pid: u32, started: &str) -> ProcessIdentity {
    ProcessIdentity {
        pid,
        boot: "boot".into(),
        started: started.into(),
    }
}

fn sample(time: f64, processes: &[(u32, &str)]) -> TreeSample {
    TreeSample {
        time,
        processes: processes
            .iter()
            .map(|(pid, started)| (*pid, started.to_string()))
            .collect(),
    }
}

#[test]
fn quiescence_refuses_every_sample_that_is_not_fresh_exact_evidence() {
    let worker = pinned(42, "77");
    let (after, now) = (1_000.0, 1_010.0);
    let check = |s: TreeSample| quiescence(&s, &worker, after, now);
    assert_eq!(check(sample(1_005.0, &[(42, "77")])), Ok(()));
    assert_eq!(
        check(sample(1_000.0, &[(42, "77")])),
        Err(SampleRefusal::Stale),
        "taken at the terminal reply's receipt: not after it"
    );
    assert_eq!(
        check(sample(999.0, &[(42, "77")])),
        Err(SampleRefusal::Stale)
    );
    assert_eq!(
        check(sample(now + SAMPLE_CLOCK_SKEW_SECONDS + 0.5, &[(42, "77")])),
        Err(SampleRefusal::Future)
    );
    assert_eq!(
        check(sample(f64::NAN, &[(42, "77")])),
        Err(SampleRefusal::Malformed)
    );
    assert_eq!(
        check(sample(f64::INFINITY, &[(42, "77")])),
        Err(SampleRefusal::Malformed)
    );
    assert_eq!(check(sample(1_005.0, &[])), Err(SampleRefusal::Empty));
    assert_eq!(
        check(sample(1_005.0, &[(42, "77"), (43, "5")])),
        Err(SampleRefusal::Unclassified),
        "a job's surviving process"
    );
    assert_eq!(
        check(sample(1_005.0, &[(41, "77")])),
        Err(SampleRefusal::WrongIdentity)
    );
    assert_eq!(
        check(sample(1_005.0, &[(42, "78")])),
        Err(SampleRefusal::WrongIdentity),
        "a reused pid"
    );
}

#[test]
fn tree_sample_events_decode_strictly() {
    let receipts = Path::new("receipts");
    assert_eq!(
        decode_event(
            r#"{"event":"tree_sample","time":12.5,"processes":[[42,"77"]]}"#,
            receipts
        ),
        LaunchEvent::TreeSample(sample(12.5, &[(42, "77")]))
    );
    for line in [
        r#"{"event":"tree_sample","time":"12.5","processes":[[42,"77"]]}"#,
        r#"{"event":"tree_sample","time":12.5,"processes":[[42,77]]}"#,
        r#"{"event":"tree_sample","time":12.5,"processes":"42"}"#,
        r#"{"event":"tree_sample","time":12.5}"#,
        r#"{"event":"tree_sample","time":12.5,"processes":[],"extra":1}"#,
    ] {
        assert!(
            matches!(decode_event(line, receipts), LaunchEvent::Fault(_)),
            "{line}"
        );
    }
}

fn resident_spec(space: &Workspace, job_spec: &JobSpec, quiet_ms: u64) -> SessionSpec {
    let mut session = session_spec(space, job_spec);
    session.config = atelier_build_v2::session_lifecycle::SessionConfig {
        cleanup: Duration::from_secs(3),
        lifetime: Duration::from_secs(30),
        idle: Duration::from_secs(2),
        quiescence: Some(Duration::from_millis(quiet_ms)),
        custodian: false, // the driver sets it from the custody set
    };
    // Reuse needs checkout custody, so that each Run waits for the custody monitor's registration.
    let lock = lock_with(&space.path("checkout.lock"), libc::LOCK_EX);
    session
        .key
        .custody
        .insert(CustodyIdentity::of(&lock, LockScope::Exclusive).unwrap());
    session.custody = vec![lock];
    session
}

fn resident_limits() -> Limits {
    Limits {
        job: Duration::from_secs(20),
        cleanup: Duration::from_secs(6),
        overall: Some(Duration::from_secs(60)),
    }
}

fn run_resident(bridge: &str, quiet_ms: u64) -> (SessionReport, Vec<(String, ProcessIdentity)>) {
    let space = Workspace::new();
    let job_spec = spec(&space, "normal", 3_000);
    let session = resident_spec(&space, &job_spec, quiet_ms);
    let (handle, inbox) = session_channel();
    handle.submit(unit_with("a", "a", resident_limits(), session.key.clone()));
    handle.submit(unit_with("b", "b", resident_limits(), session.key.clone()));
    handle.close();
    let (published, _records) = mpsc::channel();
    let mut registered = vec![];
    let report = run_session(
        &mut launcher(bridge),
        &SystemClock::new(),
        &session,
        inbox,
        &mut |unit, worker| {
            registered.push((unit.clone(), worker.clone()));
            Ok(())
        },
        published,
    )
    .unwrap();
    // Only the workers' registrations; each unit also registers the session's custody monitor.
    registered.retain(|(_, identity)| {
        report
            .sessions
            .iter()
            .any(|s| s.worker.as_ref() == Some(identity))
    });
    (report, registered)
}

#[test]
fn a_resident_session_reuses_its_worker_only_on_fresh_exact_samples() {
    let (report, registered) = run_resident("samples", 2_000);
    assert_eq!(report.sessions.len(), 1, "one admission for both units");
    assert!(report.units.iter().all(|u| u.outcome.end == End::Completed));
    assert!(
        report.units[0].attempts[0].quiescent.is_some(),
        "a settled by evidence"
    );
    assert_eq!(registered.len(), 2);
    assert_eq!(
        registered[0].1, registered[1].1,
        "the same worker served both"
    );
    assert_eq!(report.sessions[0].custody, Custody::Released);

    // Samples that list another process are never evidence: a fresh session for b.
    let (report, registered) = run_resident("busy_samples", 300);
    assert_eq!(report.sessions.len(), 2);
    assert!(report.units.iter().all(|u| u.outcome.end == End::Completed));
    assert_eq!(report.units[0].attempts[0].quiescent, None);
    assert_eq!(report.units[0].attempts[0].custody, Custody::Released);
    assert_ne!(registered[0].1, registered[1].1);
}

/// The (job id, job folder) of every `run` the workers received, in order.
fn runs(space: &Workspace) -> Vec<(String, String)> {
    fs::read_to_string(space.path("jobs.log"))
        .unwrap_or_default()
        .lines()
        .map(|line| {
            let run: Value = serde_json::from_str(line).unwrap();
            (
                run["job_id"].as_str().unwrap().to_string(),
                run["job_dir"].as_str().unwrap().to_string(),
            )
        })
        .collect()
}

fn staged(job: &JobRequest, unit: &str, attempt: u32) -> JobRequest {
    let mut job = job.clone();
    job.job_dir = format!("/jobs/{unit}-{attempt}");
    job
}

#[test]
fn a_crash_retry_runs_a_freshly_prepared_request_in_a_later_session() {
    // A resident session: a crashes once, its retry and then b share the second session.
    let space = Workspace::new();
    let job_spec = spec(&space, "crash_once", 3_000);
    let session = resident_spec(&space, &job_spec, 2_000);
    let (handle, inbox) = session_channel();
    handle.submit(unit_with("a", "a", resident_limits(), session.key.clone()));
    handle.submit(unit_with("b", "b", resident_limits(), session.key.clone()));
    handle.close();
    let (published, _records) = mpsc::channel();
    let mut calls = vec![];
    let report = run_session_prepared(
        &mut launcher("samples"),
        &SystemClock::new(),
        &session,
        inbox,
        &mut |_, _| Ok(()),
        &mut |unit, attempt| {
            calls.push((unit.clone(), attempt));
            let mut request = job();
            request.job_id = unit.clone();
            Ok(staged(&request, unit, attempt))
        },
        published,
    )
    .unwrap();
    assert_eq!(
        calls,
        vec![("a".into(), 1), ("a".into(), 2), ("b".into(), 1)],
        "one preparation per attempt, each after its admission"
    );
    assert_eq!(
        runs(&space),
        vec![
            ("a".into(), "/jobs/a-1".into()),
            ("a".into(), "/jobs/a-2".into()),
            ("b".into(), "/jobs/b-1".into()),
        ],
        "every run carries its own attempt's request"
    );
    let a = &report.units[0];
    assert_eq!(a.outcome.end, End::Completed);
    assert_eq!(a.outcome.attempts, 2);
    assert_eq!(
        a.attempts.iter().map(|x| x.session).collect::<Vec<_>>(),
        vec![1, 2],
        "the retry joined a later session"
    );
    assert_eq!(a.attempts[0].custody, Custody::Released);
    let b = &report.units[1];
    assert_eq!(b.outcome.end, End::Completed);
    assert_eq!(
        b.attempts[0].session, 2,
        "b requeued onto the retry's session"
    );
    assert_eq!(report.sessions.len(), 2);
    assert!(
        report
            .sessions
            .iter()
            .all(|s| s.custody == Custody::Released)
    );

    // run_job_prepared: the same per-attempt seam for one job.
    let space = Workspace::new();
    let job_spec = spec(&space, "crash_once", 3_000);
    let (_canceller, inbox) = job_channel();
    let mut attempts = vec![];
    let report = run_job_prepared(
        &mut launcher("normal"),
        &SystemClock::new(),
        &job_spec,
        inbox,
        &mut |_| Ok(()),
        &mut |attempt| {
            attempts.push(attempt);
            Ok(staged(&job(), "job", attempt))
        },
    )
    .unwrap();
    assert_eq!(report.outcome.end, End::Completed);
    assert_eq!(attempts, vec![1, 2]);
    assert_eq!(
        runs(&space),
        vec![
            ("job".into(), "/jobs/job-1".into()),
            ("job".into(), "/jobs/job-2".into()),
        ]
    );
}

#[test]
fn a_failed_preparation_ends_the_unit_without_a_run_and_is_never_retried() {
    let space = Workspace::new();
    let job_spec = spec(&space, "normal", 3_000);
    let session = session_spec(&space, &job_spec);
    let (handle, inbox) = session_channel();
    for id in ["a", "b", "c"] {
        handle.submit(unit_with(id, id, job_spec.limits, key(&job_spec)));
    }
    handle.close();
    let (published, _records) = mpsc::channel();
    let mut calls = vec![];
    let report = run_session_prepared(
        &mut launcher("normal"),
        &SystemClock::new(),
        &session,
        inbox,
        &mut |_, _| Ok(()),
        &mut |unit, attempt| {
            calls.push(unit.clone());
            let mut request = job();
            request.job_id = unit.clone();
            match unit.as_str() {
                "a" => Err("staging failed".into()),
                "b" => {
                    request.job_id = "other".into();
                    Ok(request)
                }
                _ => Ok(staged(&request, unit, attempt)),
            }
        },
        published,
    )
    .unwrap();
    assert_eq!(
        calls,
        vec!["a", "b", "c"],
        "no retry after a failed preparation"
    );
    assert_eq!(
        runs(&space),
        vec![("c".into(), "/jobs/c-1".into())],
        "only the prepared unit ran"
    );
    for (unit, why) in [
        (&report.units[0], "staging failed"),
        (&report.units[1], "changed the unit's job id"),
    ] {
        assert_eq!(unit.outcome.end, End::Failed(Stop::Cancelled));
        assert_eq!(unit.outcome.attempts, 1);
        assert!(unit.abort.as_ref().unwrap().contains(why), "{unit:?}");
        assert_eq!(unit.attempts[0].custody, Custody::Released);
    }
    assert_eq!(report.units[2].outcome.end, End::Completed);

    // Startup evidence is checked only when the worker is Ready; a rejection never sends Run.
    let space = Workspace::new();
    let job_spec = spec(&space, "normal", 3_000);
    let session = session_spec(&space, &job_spec);
    let (handle, inbox) = session_channel();
    handle.submit(unit_with(
        "checked",
        "checked",
        job_spec.limits,
        key(&job_spec),
    ));
    handle.close();
    let (published, _records) = mpsc::channel();
    let mut checked = 0;
    let report = run_session_ready_checked(
        &mut launcher("normal"),
        &SystemClock::new(),
        &session,
        inbox,
        &mut |_, _| Ok(()),
        &mut |unit, attempt| {
            let mut request = job();
            request.job_id = unit.clone();
            Ok(staged(&request, unit, attempt))
        },
        &mut |_| {
            checked += 1;
            Err("actual startup context mismatch".into())
        },
        published,
    )
    .unwrap();
    assert_eq!(checked, 1);
    assert!(runs(&space).is_empty());
    assert_ne!(report.units[0].outcome.end, End::Completed);
    assert!(
        report
            .sessions
            .iter()
            .all(|attempt| attempt.custody == Custody::Released)
    );
}

#[test]
fn a_stop_delivered_right_after_the_worker_starts_is_always_reported() {
    // a's preparation fails, so its session is stopped right after child_started; the bridge
    // holds its stop handler's lock until that SIGTERM is delivered (a handshake, not a delay).
    // The bridge must still report the stop and its cleanup, so b runs in the next session.
    let space = Workspace::new();
    let job_spec = spec(&space, "normal", 3_000);
    let session = session_spec(&space, &job_spec);
    let (handle, inbox) = session_channel();
    for id in ["a", "b"] {
        handle.submit(unit_with(id, id, job_spec.limits, key(&job_spec)));
    }
    handle.close();
    let (published, _records) = mpsc::channel();
    let mut calls = vec![];
    let report = run_session_prepared(
        &mut launcher("stop_after_start"),
        &SystemClock::new(),
        &session,
        inbox,
        &mut |_, _| Ok(()),
        &mut |unit, attempt| {
            calls.push(unit.clone());
            let mut request = job();
            request.job_id = unit.clone();
            match unit.as_str() {
                "a" => Err("staging failed".into()),
                _ => Ok(staged(&request, unit, attempt)),
            }
        },
        published,
    )
    .unwrap();
    // First, on every path: no bridge this test spawned outlives it.
    let (bridges, reaped) = bridges_reaped(&space, Duration::from_secs(10));
    assert_eq!(calls, vec!["a", "b"], "{report:?}");
    assert_eq!(runs(&space), vec![("b".into(), "/jobs/b-1".into())]);
    assert_eq!(report.units[0].outcome.end, End::Failed(Stop::Cancelled));
    assert_eq!(report.units[0].attempts[0].custody, Custody::Released);
    assert_eq!(report.units[1].outcome.end, End::Completed);
    assert!(
        report
            .sessions
            .iter()
            .all(|session| session.custody == Custody::Released),
        "{report:?}"
    );
    assert_eq!(bridges, 2, "each session's bridge recorded its PID");
    assert!(reaped, "a bridge was not reaped within the bound");
}

/// How many fake bridges this test spawned (by the PID each recorded), and whether all of them
/// were reaped by the launcher within `limit`. The probe is waitid with WNOWAIT on our own
/// children: it never signals and never reaps. The bridge bounds itself (fake_bridge.py
/// stop_after_start), so a stuck one still exits and is reaped. The test does not kill bridges
/// itself: the adapter signals its own unreaped bridge only with SIGTERM (a production bridge
/// owns an admission), and a kill by recorded PID could race the launcher's reaper.
fn bridges_reaped(space: &Workspace, limit: Duration) -> (usize, bool) {
    let pids: Vec<libc::pid_t> = fs::read_dir(&space.0)
        .unwrap()
        .filter_map(Result::ok)
        .filter_map(|entry| fs::read_to_string(entry.path().join("bridge.pid")).ok())
        .map(|text| text.trim().parse().unwrap())
        .collect();
    let deadline = Instant::now() + limit;
    loop {
        let unreaped = pids.iter().any(|&pid| {
            // SAFETY: waitid writes only into the siginfo_t we own. WNOWAIT leaves an exit status
            // for the launcher's reaper; 0 means `pid` is still our own child, so not yet reaped.
            let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
            let flags = libc::WEXITED | libc::WNOHANG | libc::WNOWAIT;
            unsafe { libc::waitid(libc::P_PID, pid as libc::id_t, &mut info, flags) == 0 }
        });
        if !unreaped {
            return (pids.len(), true);
        }
        if Instant::now() >= deadline {
            return (pids.len(), false);
        }
        std::thread::sleep(Duration::from_millis(20));
    }
}

#[test]
fn a_reply_read_after_the_exit_report_still_completes_the_unit() {
    // The bridge reports the exit before the worker has replied at all: the driver applies the
    // report only after the response stream ends, so the completed reply comes first.
    let (report, _, space) = drive("normal", "early_exit", false, 3_000);
    assert_eq!(report.outcome.end, End::Completed);
    assert_eq!(report.outcome.attempts, 1, "no retry from the early report");
    assert_eq!(report.attempts.len(), 1);
    assert_eq!(report.attempts[0].custody, Custody::Released);
    assert_eq!(report.outputs.unwrap().files, vec!["piece.glb".to_string()]);
    assert_eq!(runs(&space).len(), 1);
}

#[test]
fn an_exit_report_without_the_stream_end_applies_after_the_drain_limit() {
    // The worker keeps its pipe open and never replies: the exit report is applied once the
    // drain limit passes, long before the 30 s job limit, and is crash evidence as reported.
    let started = Instant::now();
    let (report, _, _space) = drive("hang", "early_exit", false, 1_000);
    let took = started.elapsed();
    assert_eq!(report.outcome.end, End::Failed(Stop::Crash), "{report:?}");
    assert_eq!(
        report.attempts.len(),
        1,
        "no retry without a confirmed receipt"
    );
    assert!(matches!(report.attempts[0].custody, Custody::Held(_)));
    assert!(took >= EXIT_DRAIN_LIMIT, "{took:?}");
    assert!(took < Duration::from_secs(15), "{took:?}");
}

#[test]
fn a_resident_session_refuses_a_key_without_the_no_fork_sandbox() {
    let space = Workspace::new();
    let job_spec = spec(&space, "normal", 3_000);
    let mut session = resident_spec(&space, &job_spec, 2_000);
    session.key.sandbox = JobSandbox::Other;
    let (handle, inbox) = session_channel();
    handle.submit(unit_with("a", "a", resident_limits(), session.key.clone()));
    handle.close();
    let (published, _records) = mpsc::channel();
    let error = run_session(
        &mut launcher("normal"),
        &SystemClock::new(),
        &session,
        inbox,
        &mut |_, _| Ok(()),
        published,
    )
    .unwrap_err();
    assert!(
        format!("{error:?}").contains("no-fork job sandbox"),
        "{error:?}"
    );
    assert!(
        !space.path("attempt-1").exists(),
        "nothing was queued or started"
    );

    // One unit per session needs no evidence: any sandbox may run there, and a unit declaring
    // another sandbox is another key.
    session.config = atelier_build_v2::session_lifecycle::SessionConfig::single(
        Duration::from_secs(3),
        Duration::from_secs(30),
    );
    let (handle, inbox) = session_channel();
    handle.submit(unit_with("a", "a", job_spec.limits, session.key.clone()));
    handle.submit(unit_with("b", "b", job_spec.limits, key(&job_spec)));
    handle.close();
    let (published, _records) = mpsc::channel();
    let report = run_session(
        &mut launcher("normal"),
        &SystemClock::new(),
        &session,
        inbox,
        &mut |_, _| Ok(()),
        published,
    )
    .unwrap();
    assert_eq!(report.units[0].outcome.end, End::Completed);
    assert_eq!(
        report.refused[0].refused,
        Some(atelier_build_v2::session_lifecycle::Refusal::IncompatibleKey)
    );
}

/// One job holding a real checkout lock as custody, through `bridge`; `fail` makes that call of
/// `register` (1 for the first) fail. Returns the report, every registered identity with whether
/// its correlation was already on disk and whether the worker had received a run, and the space.
#[allow(clippy::type_complexity)]
fn custody_job(
    bridge: &str,
    job_ms: u64,
    fail: Option<usize>,
) -> (
    Report,
    Vec<(ProcessIdentity, Option<CleanupCorrelation>, bool)>,
    Workspace,
) {
    let space = Workspace::new();
    let mut job_spec = spec(&space, "normal", 3_000);
    job_spec.limits.job = Duration::from_millis(job_ms);
    job_spec.custody = vec![lock_with(&space.path("checkout.lock"), libc::LOCK_EX)];
    let (_canceller, inbox) = job_channel();
    let mut seen = vec![];
    let report = run_job(
        &mut launcher(bridge),
        &SystemClock::new(),
        &job_spec,
        inbox,
        &mut |identity| {
            seen.push((
                identity.clone(),
                CleanupCorrelation::find(&space.0, identity),
                space.path("jobs.log").exists(),
            ));
            if fail == Some(seen.len()) {
                Err("scripted add_worker failure".into())
            } else {
                Ok(())
            }
        },
    )
    .unwrap();
    (report, seen, space)
}

#[test]
fn the_custody_monitor_is_durably_registered_before_the_first_run() {
    let (report, seen, space) = custody_job("normal", 30_000, None);
    assert_eq!(report.outcome.end, End::Completed);
    let worker = report.attempts[0].worker.clone().unwrap();
    assert_eq!(seen.len(), 2, "the worker, then the custody monitor");
    assert_eq!(seen[0].0, worker);
    let (monitor, correlation, ran) = &seen[1];
    assert_ne!(*monitor, worker);
    assert!(
        !ran && !seen[0].2,
        "no Run before both registrations returned"
    );
    let correlation = correlation
        .clone()
        .expect("the correlation was on disk before the monitor's registration");
    assert_eq!(correlation.monitor, *monitor);
    assert_eq!(correlation.receipts, space.path("attempt-1"));
    assert_eq!(runs(&space).len(), 1);
    assert_eq!(report.attempts[0].custody, Custody::Released);
    assert!(
        cleanup_confirmed(&correlation),
        "the guard's durable record confirms this invocation's cleanup"
    );
}

#[test]
fn a_missing_changed_or_unregistered_monitor_prevents_the_run() {
    let (report, seen, space) = custody_job("normal", 30_000, Some(2));
    assert_eq!(seen.len(), 2);
    assert_eq!(report.outcome.end, End::Failed(Stop::Cancelled));
    assert!(report.abort.unwrap().contains("custody monitor"));
    assert!(runs(&space).is_empty(), "a failed registration never runs");

    let (report, seen, space) = custody_job("no_monitor", 1_500, None);
    assert_eq!(seen.len(), 1, "only the worker: no monitor was reported");
    assert_eq!(report.outcome.end, End::Failed(Stop::JobLimit));
    assert!(runs(&space).is_empty(), "a missing identity never runs");

    let (report, _, space) = custody_job("monitor_changed", 30_000, None);
    assert_eq!(report.outcome.end, End::Failed(Stop::Protocol));
    assert!(runs(&space).is_empty(), "a changed identity never runs");
}

#[test]
fn cleanup_is_confirmed_only_by_this_invocations_durable_record() {
    let space = Workspace::new();
    let correlation = CleanupCorrelation {
        schema: 1,
        monitor: ProcessIdentity {
            pid: 77,
            boot: "boot-1".into(),
            started: "7700".into(),
        },
        invocation: "a".repeat(32),
        receipts: space.0.clone(),
    };
    let record = |change: &dyn Fn(&mut Value)| {
        let mut value = serde_json::json!({
            "schema": 1, "invocation": "a".repeat(32), "boot": "boot-1", "child": [5, 50],
            "monitor": [77, 7700], "confirmed": true, "reason": null,
        });
        change(&mut value);
        fs::write(space.path("cleanup.json"), value.to_string()).unwrap();
        cleanup_confirmed(&correlation)
    };
    assert!(
        !cleanup_confirmed(&correlation),
        "no record: unknown, so retained"
    );
    assert!(record(&|_| {}));
    for change in [
        &(|v: &mut Value| v["confirmed"] = false.into()) as &dyn Fn(&mut Value),
        &|v| v["invocation"] = "b".repeat(32).into(),
        &|v| v["boot"] = "boot-2".into(),
        &|v| v["monitor"] = serde_json::json!([77, 7701]),
        &|v| v["monitor"] = serde_json::json!([78, 7700]),
        &|v| v["monitor"] = Value::Null,
        &|v| v["schema"] = 2.into(),
        &|v| v["extra"] = 1.into(),
        &|v| *v = Value::String("confirmed".into()),
    ] {
        assert!(!record(change));
    }
    fs::write(space.path("cleanup.json"), "{not json").unwrap();
    assert!(!cleanup_confirmed(&correlation));
}

#[test]
fn a_controller_lost_after_registering_the_monitor_never_runs_and_leaves_its_correlation() {
    let space = Workspace::new();
    let mut job_spec = spec(&space, "normal", 3_000);
    job_spec.custody = vec![lock_with(&space.path("checkout.lock"), libc::LOCK_EX)];
    let (_canceller, inbox) = job_channel();
    let mut seen = vec![];
    // The controller dies right after add_worker returned for the monitor, before any Run.
    let crashed = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        run_job(
            &mut launcher("normal"),
            &SystemClock::new(),
            &job_spec,
            inbox,
            &mut |identity| {
                seen.push(identity.clone());
                if seen.len() == 2 {
                    panic!("the controller dies after registering the custody monitor");
                }
                Ok(())
            },
        )
    }));
    assert!(crashed.is_err());
    let monitor = seen[1].clone();
    let correlation =
        CleanupCorrelation::find(&space.0, &monitor).expect("the correlation survives the crash");
    if !space.path("attempt-1/cleanup.json").exists() {
        assert!(
            !cleanup_confirmed(&correlation),
            "until the guard's own record exists, nothing is confirmed"
        );
    }
    // The bridge sees its liveness pipe close, stops its run and records its cleanup decision.
    let deadline = std::time::Instant::now() + BOUND;
    while !space.path("attempt-1/cleanup.json").exists() && std::time::Instant::now() < deadline {
        thread::sleep(Duration::from_millis(10));
    }
    assert!(space.path("attempt-1/liveness-eof").exists());
    assert!(cleanup_confirmed(&correlation));
    assert!(runs(&space).is_empty(), "the job never ran");
}

#[test]
fn a_resident_session_without_custody_is_refused() {
    let space = Workspace::new();
    let job_spec = spec(&space, "normal", 3_000);
    let mut session = resident_spec(&space, &job_spec, 2_000);
    session.custody.clear();
    session.key.custody.clear();
    let (handle, inbox) = session_channel();
    handle.close();
    let (published, _records) = mpsc::channel();
    let error = run_session(
        &mut launcher("normal"),
        &SystemClock::new(),
        &session,
        inbox,
        &mut |_, _| Ok(()),
        published,
    )
    .unwrap_err();
    assert!(
        format!("{error:?}").contains("needs checkout custody"),
        "{error:?}"
    );
    assert!(!space.path("attempt-1").exists());
}
