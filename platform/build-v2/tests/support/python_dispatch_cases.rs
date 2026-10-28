//! Portable production-dispatch proof with synthetic guard observations, no child processes.
//! The real backend issues original leases and staged inputs; a test tap stops before publication.
use super::*;
use crate::checkout_locks::INSTALL_METADATA;
use crate::graph::{BuildGraph, Target};
use crate::guard_adapter::*;
use crate::install::{
    CheckoutInstaller, InstallPolicy, OwnershipSnapshot, ProjectNamespace, ReceiptReader,
};
use crate::leases::{LeaseStore, ProcessIdentity};
use crate::protocol::{self, JobOutputs, Request, Response};
use crate::py_data::{PyDataSpec, py_data_validator_identity};
use crate::python_backend::{CacheAccess, PythonBackend};
use crate::python_worker::PYTHON_WORKER_FILES;
use crate::results::ResultStore;
use crate::scheduler::{self, Backend, Demand, Runtime};
use crate::schema::{Declaration, Provenance};
use crate::source_hashes::SourceHashCache;
use crate::validate::{SnapshotEntry, SourceSnapshot};
use std::collections::{BTreeMap, BTreeSet};
use std::io::{self, Cursor, Read, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, mpsc};

static SERIAL: AtomicU64 = AtomicU64::new(0);
struct Space(PathBuf);
impl Space {
    fn new() -> Self {
        let path = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "atelier-dispatch-{}-{}",
            std::process::id(),
            SERIAL.fetch_add(1, Ordering::Relaxed)
        ));
        std::fs::create_dir(&path).unwrap();
        for name in ["checkout", "cache"] {
            std::fs::create_dir(path.join(name)).unwrap();
        }
        Self(path)
    }
    fn at(&self, name: &str) -> PathBuf {
        self.0.join(name)
    }
}
impl Drop for Space {
    fn drop(&mut self) {
        use std::os::unix::fs::PermissionsExt;
        fn writable(path: &Path) {
            if path.is_dir() {
                std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o700)).unwrap();
                for child in std::fs::read_dir(path).unwrap() {
                    writable(&child.unwrap().path());
                }
            }
        }
        writable(&self.0);
        std::fs::remove_dir_all(&self.0).unwrap();
    }
}
fn identity(pid: u32) -> ProcessIdentity {
    ProcessIdentity {
        pid,
        boot: "synthetic-boot".into(),
        started: format!("synthetic-{pid}"),
    }
}
#[derive(Clone, Copy)]
enum Mode {
    Complete,
    WorkerFailure,
    DiagnosticCollision,
    ProtocolFailure,
    Held,
    MissingMonitor,
    RegistrationFailure,
    Crash,
    Cancel,
}
#[derive(Default)]
struct Seen {
    submissions: usize,
    runs: usize,
    completed_events: usize,
    durable_pairs: usize,
    custody: usize,
    cancelled: bool,
    partial: Option<PathBuf>,
    partial_verified: bool,
    report_root: Option<PathBuf>,
    diagnostic: Option<serde_json::Value>,
}
struct Synthetic {
    root: PathBuf,
    mode: Mode,
    seen: Arc<Mutex<Seen>>,
}
struct Stream {
    sender: Option<mpsc::Sender<Vec<u8>>>,
    events: mpsc::Sender<AttemptEvent>,
    attempt: u32,
    report: PathBuf,
    mode: Mode,
    root: PathBuf,
    seen: Arc<Mutex<Seen>>,
}
impl Stream {
    fn response(&self, response: Response) {
        let mut bytes = vec![];
        protocol::write_frame(&mut bytes, &response).unwrap();
        if let Some(tx) = &self.sender {
            let _ = tx.send(bytes);
        }
    }
    fn finish(&mut self, cleanup: CleanupReceipt) {
        self.sender.take();
        let _ = self.events.send(AttemptEvent {
            attempt: self.attempt,
            event: LaunchEvent::ChildExited {
                worker: identity(101),
                exit: ExitInfo::Code(0),
                stopped_by: None,
            },
        });
        let _ = self.events.send(AttemptEvent {
            attempt: self.attempt,
            event: LaunchEvent::Finished {
                cleanup,
                receipts: self.report.clone(),
            },
        });
    }
}
struct Input {
    shared: Arc<Mutex<Stream>>,
    bytes: Vec<u8>,
}
impl Write for Input {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        self.bytes.extend_from_slice(bytes);
        Ok(bytes.len())
    }
    fn flush(&mut self) -> io::Result<()> {
        if self.bytes.is_empty() {
            return Ok(());
        }
        let request: Request =
            protocol::read_frame(&mut Cursor::new(std::mem::take(&mut self.bytes)))?.unwrap();
        let mut s = self.shared.lock().unwrap();
        match request {
            Request::Run { job } => {
                s.seen.lock().unwrap().runs += 1;
                // Read the actual original durable records, not in-memory callbacks or counts.
                for root in [
                    s.root.join("cache"),
                    s.root
                        .join("checkout")
                        .join(INSTALL_METADATA)
                        .join("completions"),
                ] {
                    let records = LeaseStore::open(&root)
                        .unwrap()
                        .lock()
                        .unwrap()
                        .leases()
                        .unwrap();
                    let registered: Vec<_> = records
                        .iter()
                        .filter(|record| record.workers.contains(&identity(101)))
                        .collect();
                    assert_eq!(registered.len(), 1);
                    assert!(registered[0].workers.contains(&identity(102)));
                    assert!(!registered[0].rooted);
                    if root.ends_with("completions") {
                        assert_eq!(registered[0].id, job.job_id);
                    }
                    s.seen.lock().unwrap().durable_pairs += 1;
                }
                let correlation = worker_lifecycle::CleanupCorrelation::read(&s.report).unwrap();
                assert_eq!(correlation.monitor, identity(102));
                assert_eq!(correlation.invocation, "a".repeat(32));
                assert_eq!(correlation.receipts, s.report);
                if matches!(s.mode, Mode::Crash) {
                    let partial = Path::new(&job.job_dir).join("output/partial.bin");
                    std::fs::write(&partial, b"retained first-attempt bytes").unwrap();
                    s.seen.lock().unwrap().partial = Some(partial);
                    s.finish(CleanupReceipt::Confirmed);
                    return Ok(());
                }
                if matches!(s.mode, Mode::ProtocolFailure) {
                    s.response(Response::Completed {
                        job_id: "sentinel-foreign-job".into(),
                        outputs: JobOutputs { files: vec![] },
                    });
                    return Ok(());
                }
                s.response(Response::Started {
                    job_id: job.job_id.clone(),
                });
                if matches!(s.mode, Mode::WorkerFailure | Mode::DiagnosticCollision) {
                    s.response(Response::Failed {
                        job_id: job.job_id,
                        failure: protocol::WorkerFailure {
                            kind: protocol::FailureKind::Dependency,
                            message: "sentinel-worker-dependency-original-é".into(),
                        },
                    });
                    return Ok(());
                }
                if matches!(s.mode, Mode::Cancel) {
                    s.seen.lock().unwrap().cancelled = true;
                    return Ok(());
                }
                s.response(Response::Completed {
                    job_id: job.job_id,
                    outputs: JobOutputs {
                        files: vec!["out.json".into()],
                    },
                });
            }
            Request::Shutdown {} => {
                s.response(Response::Stopped {});
                let cleanup = if matches!(s.mode, Mode::Held) {
                    CleanupReceipt::Unconfirmed {
                        reason: "synthetic held".into(),
                    }
                } else {
                    CleanupReceipt::Confirmed
                };
                s.finish(cleanup);
            }
            Request::Cancel { job_id } => {
                s.response(Response::Failed {
                    job_id,
                    failure: protocol::WorkerFailure {
                        kind: protocol::FailureKind::Cancelled,
                        message: "synthetic cancellation".into(),
                    },
                });
                s.finish(CleanupReceipt::Confirmed);
            }
        }
        Ok(())
    }
}
struct Output {
    rx: mpsc::Receiver<Vec<u8>>,
    current: Cursor<Vec<u8>>,
}
impl Read for Output {
    fn read(&mut self, bytes: &mut [u8]) -> io::Result<usize> {
        if bytes.is_empty() {
            return Ok(0);
        }
        loop {
            let n = self.current.read(bytes)?;
            if n != 0 {
                return Ok(n);
            }
            match self.rx.recv() {
                Ok(next) => self.current = Cursor::new(next),
                Err(_) => return Ok(0),
            }
        }
    }
}
struct Attempt {
    shared: Arc<Mutex<Stream>>,
    pipes: Option<Pipes>,
}
impl WorkerAttempt for Attempt {
    fn stop(&mut self) -> io::Result<bool> {
        self.shared
            .lock()
            .unwrap()
            .finish(CleanupReceipt::Confirmed);
        Ok(true)
    }
    fn take_pipes(&mut self) -> Option<Pipes> {
        self.pipes.take()
    }
}
impl WorkerLauncher for Synthetic {
    type Attempt = Attempt;
    fn submit(
        &mut self,
        attempt: u32,
        command: &WorkerCommand,
        request: AdmissionRequest,
        events: mpsc::Sender<AttemptEvent>,
    ) -> io::Result<Attempt> {
        self.seen.lock().unwrap().submissions += 1;
        self.seen.lock().unwrap().report_root = request.report_dir.parent().map(Path::to_path_buf);
        self.seen.lock().unwrap().custody += request.custody.len();
        assert_eq!(request.custody.len(), 1);
        assert_eq!(request.execution_limit, Duration::from_secs(150));
        assert!(!command.env.keys().any(|key| key.contains("CUSTODY")));
        std::fs::create_dir(&request.report_dir)?;
        if matches!(self.mode, Mode::DiagnosticCollision) {
            use std::os::unix::fs::PermissionsExt;
            let existing = request.report_dir.parent().unwrap().join("diagnostic.json");
            std::fs::write(&existing, br#"{"sentinel":"original retained record"}"#)?;
            std::fs::set_permissions(existing, std::fs::Permissions::from_mode(0o600))?;
        }
        if matches!(self.mode, Mode::RegistrationFailure) {
            // Reserve the real local lease filename so its durable worker write fails.
            let local = self
                .root
                .join("checkout")
                .join(INSTALL_METADATA)
                .join("completions");
            let records = LeaseStore::open(&local)?.lock()?.leases()?;
            let path = local.join("leases").join(format!("{}.json", records[0].id));
            std::fs::rename(&path, path.with_extension("retained"))?;
            std::fs::create_dir(path)?;
        }
        let (tx, rx) = mpsc::channel();
        let shared = Arc::new(Mutex::new(Stream {
            sender: Some(tx),
            events: events.clone(),
            attempt,
            report: request.report_dir,
            mode: self.mode,
            root: self.root.clone(),
            seen: self.seen.clone(),
        }));
        for event in [
            LaunchEvent::Admitted,
            LaunchEvent::ChildStarted {
                worker: identity(101),
            },
        ] {
            events.send(AttemptEvent { attempt, event }).unwrap();
        }
        if matches!(self.mode, Mode::MissingMonitor) {
            events
                .send(AttemptEvent {
                    attempt,
                    event: LaunchEvent::Fault("monitor unavailable".into()),
                })
                .unwrap();
        } else {
            events
                .send(AttemptEvent {
                    attempt,
                    event: LaunchEvent::Monitor {
                        monitor: identity(102),
                        invocation: "a".repeat(32),
                    },
                })
                .unwrap();
        }
        shared.lock().unwrap().response(Response::Hello {
            worker_version: crate::launch::PYTHON_JOB_LOOP_VERSION.into(),
        });
        Ok(Attempt {
            shared: shared.clone(),
            pipes: Some((
                Box::new(Output {
                    rx,
                    current: Cursor::new(vec![]),
                }),
                Box::new(Input {
                    shared,
                    bytes: vec![],
                }),
            )),
        })
    }
}
struct Running(Arc<Mutex<Seen>>);
impl Control for Running {
    fn cancelled(&self) -> bool {
        self.0.lock().unwrap().cancelled
    }
}
struct Tap<L> {
    inner: PythonExecutor<L>,
    seen: Arc<Mutex<Seen>>,
}
impl<L: WorkerLauncher + Send> Executor<PythonTicket, PythonInputs, PythonCompletion> for Tap<L> {
    fn batch(
        &mut self,
        work: Vec<Work<PythonTicket, PythonInputs>>,
        control: &dyn Control,
        emit: &mut dyn FnMut(Event<PythonTicket, PythonInputs, PythonCompletion>) -> Flow,
    ) -> Result<(), String> {
        self.inner.batch(work, control, &mut |event| match event {
            Event::Completed { work, .. } => {
                self.seen.lock().unwrap().completed_events += 1;
                // Never promote synthetic response metadata into a publication proof.
                emit(Event::Failed {
                    work,
                    reason: "synthetic dispatch proof stops before validation/publication".into(),
                })
            }
            other => emit(other),
        })
    }
}
fn dispatch(mode: Mode, later: bool) -> (scheduler::Report, PythonIo, Arc<Mutex<Seen>>) {
    let space = Space::new();
    let mut declaration:Declaration=toml::from_str(r#"
schema_version=2
cache_version="dispatch-proof"
[[units]]
id="a"
op={kind="py_data",version="1"}
script="ops/a.py"
code=["ops/a.py"]
outputs=[{id="out",logical_path="/Data/A",class="JsonData",destination="store",files=[{path="out.json"}]}]
"#).unwrap();
    if later {
        let mut second = declaration.units[0].clone();
        second.id = "z".into();
        second.script = "ops/z.py".into();
        second.code = vec![second.script.clone()];
        second.outputs[0].logical_path = "/Data/Z".into();
        declaration.units.push(second);
    }
    let graph = BuildGraph::validate(
        declaration,
        &BTreeMap::from([(
            ("py_data".into(), "1".into()),
            PyDataSpec::new().build().unwrap(),
        )]),
        &["Game".into()],
    )
    .unwrap();
    let mut snapshot = SourceSnapshot::from([(
        "ops/a.py".into(),
        SnapshotEntry::File(b"def run(c): pass\n".to_vec()),
    )]);
    if later {
        snapshot.insert(
            "ops/z.py".into(),
            SnapshotEntry::File(b"def run(c): pass\n".to_vec()),
        );
    }
    let worker_snapshot = PYTHON_WORKER_FILES
        .into_iter()
        .map(|name| {
            (
                name.into(),
                SnapshotEntry::File(format!("# frozen synthetic {name}\n").into_bytes()),
            )
        })
        .collect();
    let bundle = PythonWorkerBundle::from_snapshot(&worker_snapshot).unwrap();
    let mut runtimes = BTreeMap::from([(
        "a".into(),
        Runtime {
            worker: bundle.identity(),
            validator: py_data_validator_identity(),
            staged_inputs: BTreeMap::new(),
            profile: "production-dispatch-proof".into(),
        },
    )]);
    let versions = Default::default();
    let mut demands = BTreeMap::from([("a".into(), BTreeSet::from([Demand::Stored]))]);
    let mut targets = vec![Target::Unit("a".into())];
    if later {
        runtimes.insert("z".into(), runtimes["a"].clone());
        demands.insert("z".into(), BTreeSet::from([Demand::Stored]));
        targets.push(Target::Unit("z".into()));
    }
    let request =
        scheduler::Request::select(&graph, &targets, &snapshot, &versions, &runtimes, &demands)
            .unwrap();
    let policy = InstallPolicy {
        project: ProjectNamespace::new("dispatch-proof").unwrap(),
        allowed_install_roots: vec!["Game".into()],
    };
    let reader = ReceiptReader::open(space.at("checkout"), policy.clone()).unwrap();
    let guard = reader.locks().try_build_exclusive().unwrap();
    let owners = OwnershipSnapshot::from_projects([(policy.project.clone(), &graph)]).unwrap();
    let provenance = Provenance {
        checkout: "fixture".into(),
        branch: "fixture".into(),
        commit: "fixture".into(),
        dirty: false,
        built_at: "fixture".into(),
    };
    let mut backend = PythonBackend::new(
        &graph,
        request.selected(),
        &snapshot,
        &reader,
        &guard,
        &owners,
        identity(99),
        provenance,
        || {
            Ok(CacheAccess {
                results: ResultStore::open(space.at("cache")).unwrap(),
                checkout: CheckoutInstaller::open(
                    space.at("checkout"),
                    space.at("cache"),
                    policy.clone(),
                )
                .unwrap(),
            })
        },
        |_, _| panic!("synthetic guard proof must not publish/root"),
    );
    let seen = Arc::new(Mutex::new(Seen::default()));
    let mut executor = Tap {
        inner: PythonExecutor::new(
            Synthetic {
                root: space.0.clone(),
                mode,
                seen: seen.clone(),
            },
            PythonExecution {
                interpreter: PathBuf::from("/synthetic/python"),
                bundle,
                profile: "production-dispatch-proof".into(),
                memory_gib: 1,
                limits: Limits {
                    job: Duration::from_secs(120),
                    cleanup: Duration::from_secs(30),
                    overall: Some(Duration::from_secs(1800)),
                },
            },
        ),
        seen: seen.clone(),
    };
    let report = scheduler::run(
        request,
        &mut backend,
        &mut executor,
        &Running(seen.clone()),
        &mut SourceHashCache::default(),
    )
    .unwrap();
    let io = backend.finish().unwrap();
    if matches!(mode, Mode::Crash) {
        let mut observed = seen.lock().unwrap();
        let path = observed
            .partial
            .as_ref()
            .expect("first crash wrote a partial sentinel");
        assert_eq!(
            std::fs::read(path).unwrap(),
            b"retained first-attempt bytes"
        );
        observed.partial_verified = true;
    }
    {
        use std::os::unix::fs::PermissionsExt;
        let mut observed = seen.lock().unwrap();
        let path = observed
            .report_root
            .as_ref()
            .unwrap()
            .join("diagnostic.json");
        if path.exists() {
            assert_eq!(
                std::fs::metadata(&path).unwrap().permissions().mode() & 0o777,
                0o600
            );
            observed.diagnostic =
                Some(serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap());
        }
    }
    assert_eq!(io.publications, 0);
    assert_eq!(io.installs, 0);
    (report, io, seen)
}
#[test]
fn production_dispatch_registers_original_leases_and_waits_for_full_cleanup() {
    let (report, io, seen) = dispatch(Mode::Complete, false);
    assert!(report.fatal.is_none());
    let seen = seen.lock().unwrap();
    assert_eq!(seen.runs, 1);
    assert_eq!(seen.completed_events, 1);
    assert_eq!(seen.durable_pairs, 2);
    assert_eq!(seen.custody, 1);
    assert_eq!(io.launches_by_unit["a"], 1);
    drop(seen);
    let (report, io, seen) = dispatch(Mode::Held, true);
    assert!(report.fatal.is_some());
    assert_eq!(seen.lock().unwrap().submissions, 1);
    assert_eq!(seen.lock().unwrap().completed_events, 0);
    assert!(!io.launches_by_unit.contains_key("a"));
}
#[test]
fn production_dispatch_missing_monitor_or_failed_registration_never_runs() {
    for mode in [Mode::MissingMonitor, Mode::RegistrationFailure] {
        let (_, _, seen) = dispatch(mode, false);
        assert_eq!(seen.lock().unwrap().runs, 0);
        assert_eq!(seen.lock().unwrap().completed_events, 0);
    }
}
#[test]
fn production_crash_retry_refuses_old_staging_before_a_second_run() {
    let (_, _, seen) = dispatch(Mode::Crash, false);
    let seen = seen.lock().unwrap();
    assert_eq!(seen.runs, 1);
    assert_eq!(seen.submissions, 2);
    assert_eq!(seen.completed_events, 0);
    assert!(seen.partial_verified);
}

#[test]
fn production_driver_rejects_wrong_key_and_unheld_custody_before_admission() {
    use crate::checkout_locks::CheckoutLocks;
    use crate::protocol::JobRequest;
    use crate::schema::Op;
    let space = Space::new();
    let locks = CheckoutLocks::open(space.at("checkout")).unwrap();
    let guard = locks.try_build_exclusive().unwrap();
    let job = JobSpec {
        job: JobRequest {
            job_id: "job".into(),
            unit: "a".into(),
            op: Op {
                kind: "py_data".into(),
                version: "1".into(),
            },
            job_dir: space.at("job").to_str().unwrap().into(),
            script: "ops/a.py".into(),
            code: vec!["ops/a.py".into()],
            inputs: vec![],
            params: BTreeMap::new(),
            outputs: vec![],
        },
        worker_version: crate::launch::PYTHON_JOB_LOOP_VERSION.into(),
        command: WorkerCommand {
            program: "/synthetic/python".into(),
            args: vec![],
            env: BTreeMap::new(),
            cwd: space.0.clone(),
        },
        purpose: "synthetic driver compatibility".into(),
        memory_gib: 1,
        limits: Limits {
            job: Duration::from_secs(120),
            cleanup: Duration::from_secs(30),
            overall: Some(Duration::from_secs(1800)),
        },
        report_root: space.at("reports"),
        custody: vec![],
    };
    let spec = production_spec(&job, guard.duplicate_for_custodian().unwrap()).unwrap();
    let seen = Arc::new(Mutex::new(Seen::default()));
    let mut launcher = Synthetic {
        root: space.0.clone(),
        mode: Mode::Complete,
        seen: seen.clone(),
    };
    let (handle, inbox) = worker_lifecycle::session_channel();
    let mut wrong = spec.key.clone();
    wrong.memory_gib += 1;
    handle.submit(worker_lifecycle::SessionUnit {
        plan: UnitPlan {
            id: "a".into(),
            limits: job.limits,
        },
        job: job.job.clone(),
        key: wrong,
    });
    handle.close();
    let (tx, _rx) = mpsc::channel();
    let report = worker_lifecycle::run_session_prepared(
        &mut launcher,
        &SystemClock::new(),
        &spec,
        inbox,
        &mut |_, _| panic!("wrong key cannot register"),
        &mut |_, _| panic!("wrong key cannot prepare"),
        tx,
    )
    .unwrap();
    assert_eq!(report.refused.len(), 1);
    assert!(sole_released_report("a", report).is_err());
    assert_eq!(seen.lock().unwrap().submissions, 0);

    let unheld = std::fs::OpenOptions::new()
        .read(true)
        .write(true)
        .create_new(true)
        .open(space.at("unheld.lock"))
        .unwrap();
    let spec = production_spec(&job, unheld).unwrap();
    let (_, inbox) = worker_lifecycle::session_channel();
    let (tx, _rx) = mpsc::channel();
    assert!(
        worker_lifecycle::run_session_prepared(
            &mut launcher,
            &SystemClock::new(),
            &spec,
            inbox,
            &mut |_, _| panic!("unheld custody cannot register"),
            &mut |_, _| panic!("unheld custody cannot prepare"),
            tx
        )
        .is_err()
    );
    assert_eq!(seen.lock().unwrap().submissions, 0);
}

#[test]
fn production_cancellation_settles_original_work_and_blocks_later_dispatch() {
    let (report, io, seen) = dispatch(Mode::Cancel, true);
    assert!(report.fatal.is_none());
    assert!(matches!(report.states["a"], scheduler::State::Cancelled));
    assert!(matches!(report.states["z"], scheduler::State::Cancelled));
    let seen = seen.lock().unwrap();
    assert_eq!(seen.runs, 1);
    assert_eq!(seen.submissions, 1);
    assert_eq!(seen.completed_events, 0);
    assert_eq!(io.launches_by_unit["a"], 1);
}

#[test]
fn production_failure_diagnostics_retain_worker_protocol_and_prepare_without_publication() {
    use crate::failure_policy::Stop;
    use crate::scheduler::State;
    for mode in [Mode::WorkerFailure, Mode::ProtocolFailure, Mode::Crash] {
        let (report, io, seen) = dispatch(mode, false);
        assert_eq!(io.publications, 0);
        assert_eq!(io.installs, 0);
        assert_eq!(io.receipt_writes, 0);
        assert!(
            report.fatal.is_none(),
            "positive sole-session cleanup remains accepted"
        );
        assert!(matches!(report.states["a"], State::Failed(_)));
        let seen = seen.lock().unwrap();
        assert_eq!(seen.completed_events, 0);
        let artifact = seen
            .diagnostic
            .as_ref()
            .expect("failed original scope retains private diagnostic");
        assert_eq!(artifact["unit"], "a");
        assert_eq!(artifact["diagnostic"], "retained");
        let attempts = artifact["attempts"].as_array().unwrap();
        match mode {
            Mode::WorkerFailure => {
                assert_eq!(attempts.len(), 1);
                assert_eq!(attempts[0]["diagnostic"]["source"], "worker");
                assert_eq!(attempts[0]["diagnostic"]["kind"], "dependency");
                assert_eq!(
                    attempts[0]["diagnostic"]["message"],
                    "sentinel-worker-dependency-original-é"
                );
                assert_eq!(seen.runs, 1);
            }
            Mode::ProtocolFailure => {
                assert_eq!(attempts[0]["diagnostic"]["source"], "protocol");
                assert!(
                    attempts[0]["diagnostic"]["message"]
                        .as_str()
                        .unwrap()
                        .contains("sentinel-foreign-job")
                );
                assert!(attempts[0]["diagnostic"]["kind"].is_null());
            }
            Mode::Crash => {
                assert_eq!(attempts.len(), 2);
                assert_eq!(attempts[0]["attempt"], 1);
                assert!(attempts[0]["diagnostic"].is_null()); // A crash did not supply a worker message.
                assert_eq!(attempts[1]["attempt"], 2);
                assert_eq!(attempts[1]["diagnostic"]["source"], "prepare");
                assert_eq!(
                    attempts[1]["diagnostic"]["message"],
                    "the attempt's job request could not be prepared: fresh retry staging is unsupported; prior output retained"
                );
                assert!(seen.partial_verified);
                assert_eq!(seen.runs, 1);
            }
            _ => unreachable!(),
        }
        // Policy's exact reason is still the existing kind-based stop, not retained text.
        if matches!(mode, Mode::WorkerFailure) {
            assert!(format!("{:?}", report.states["a"]).contains(&format!(
                "{:?}",
                Stop::WorkerReported(protocol::FailureKind::Dependency)
            )));
        }
    }
    for mode in [Mode::Complete, Mode::Held] {
        let (_, _, seen) = dispatch(mode, false);
        assert!(
            seen.lock().unwrap().diagnostic.is_none(),
            "Completed never writes failure diagnostics, even if cleanup is held"
        );
    }
}

#[test]
fn diagnostic_write_failure_preserves_existing_record_and_original_failed_outcome() {
    let (expected, _, _) = dispatch(Mode::WorkerFailure, false);
    let (actual, io, seen) = dispatch(Mode::DiagnosticCollision, false);
    assert_eq!(actual.states["a"], expected.states["a"]);
    assert_eq!(io.publications, 0);
    assert_eq!(io.installs, 0);
    assert_eq!(
        seen.lock().unwrap().diagnostic.as_ref().unwrap()["sentinel"],
        "original retained record"
    );
    let (_, _, missing) = dispatch(Mode::RegistrationFailure, false);
    let missing = missing.lock().unwrap();
    let record = missing.diagnostic.as_ref().unwrap();
    assert_eq!(record["diagnostic"], "none retained");
    assert!(
        record["attempts"]
            .as_array()
            .unwrap()
            .iter()
            .all(|a| a["diagnostic"].is_null())
    );
}
