//! C5b: one job's owned worker lifecycle over guarded attempts, and the C5c session driver.
//!
//! [`Lifecycle`] is a pure state machine: a [`SessionLifecycle`] serving exactly one unit. It
//! combines the guard's observations ([`LaunchEvent`]), the worker session's events and caller
//! cancellation into C5a's [`JobPolicy`], and emits [`Command`]s. It tracks each attempt's custody
//! separately from the policy: an attempt is `Released` only by the guard's confirmed cleanup
//! receipt and `Held` on anything less. Nothing here releases capacity, signals a process or
//! deletes a result. [`run_session`] drives a session with a real [`WorkerLauncher`] and the C1a
//! session; [`run_job`] is a session with one unit.
use crate::failure_policy::{JobPolicy, Limits, MonoTime, Outcome, PolicyError};
use crate::guard_adapter::{
    AdmissionRequest, AttemptEvent, LaunchEvent, WorkerAttempt, WorkerCommand, WorkerLauncher,
    quiescence,
};
use crate::leases::ProcessIdentity;
use crate::protocol::{JobOutputs, JobRequest, Request, Response, read_frame, write_frame};
use crate::session_lifecycle::{
    Refusal, SessionCommand, SessionConfig, SessionInput, SessionLifecycle, UnitId, UnitPlan,
    UnitRecord,
};
use crate::worker_session::{Event as WorkerEvent, Session, SessionError};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet, VecDeque};
use std::fs::{self, File};
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError, Sender};
use std::thread;
use std::time::{Duration, Instant};

/// @cc [owner:fontanierh,label:safety] lifecycle-unconfirmed-cleanup-held
/// An attempt MUST become `Released` only from the guard's confirmed cleanup receipt, or when its
/// launch never started. Unconfirmed receipts, policy deadlines, cleanup limits and controller
/// gaps MUST leave it `Held`; a held attempt MUST NOT be relaunched, and the lifecycle MUST NOT
/// release capacity or checkout custody itself. See tests/worker_lifecycle.rs.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Custody {
    /// Started and not yet settled by a receipt.
    Pending,
    /// The guard confirmed cleanup (and, if admitted, capacity close released).
    Released,
    /// Cleanup is unconfirmed: capacity and checkout custody stay with the guard.
    Held(String),
}

#[derive(Clone, Debug, PartialEq)]
pub struct AttemptRecord {
    pub attempt: u32,
    pub admitted: bool,
    pub worker: Option<ProcessIdentity>,
    pub custody: Custody,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Report {
    pub outcome: Outcome,
    pub attempts: Vec<AttemptRecord>,
    /// Unit-attempt failure metadata, separate from guard/session attempt custody.
    pub unit_attempts: Vec<crate::session_lifecycle::UnitAttemptRecord>,
    /// The worker's reported outputs, for downstream validation and publication.
    pub outputs: Option<JobOutputs>,
    /// Why the lifecycle gave up when no failure kind describes it (for example a launch error).
    pub abort: Option<String>,
}

#[derive(Clone, Debug, PartialEq)]
pub enum WorkerFault {
    Protocol(String),
    /// The pipe ended or failed. Not crash evidence: only the guard's exit observation is.
    Disconnected(String),
}

#[derive(Clone, Debug, PartialEq)]
pub enum Input {
    Launch(AttemptEvent),
    Worker {
        attempt: u32,
        event: Result<WorkerEvent, WorkerFault>,
    },
    /// The attempt's worker identity was durably added to the write lease (or not).
    Registered {
        attempt: u32,
        ok: bool,
    },
    SubmitFailed {
        attempt: u32,
        reason: String,
    },
    Cancel,
    Tick,
}

/// @cc [owner:fontanierh,label:correctness] lifecycle-keeps-published
/// Lifecycle commands MUST be limited to queueing, stopping and talking to the attempt's own
/// worker and lease registration. No command MAY delete, replace or unpublish a published
/// result; completed outputs are handed to the caller. See tests/worker_lifecycle.rs.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Command {
    /// Queue a new admitted attempt.
    Submit { attempt: u32 },
    /// Add the pinned worker identity to the write lease before it may write.
    RegisterWorker {
        attempt: u32,
        worker: ProcessIdentity,
    },
    /// Send the job (`run`) on the attempt's session.
    StartJob { attempt: u32 },
    /// Ask an idle, healthy worker to exit (`shutdown`).
    Shutdown { attempt: u32 },
    /// Ask the guard to stop or withdraw the attempt. Never certifies cleanup.
    Stop { attempt: u32 },
}

#[derive(Clone, Debug, PartialEq)]
pub enum LifecycleError {
    Policy(PolicyError),
    /// An internal invariant failed; the attempt state is left unchanged.
    Invariant(String),
}

/// One job across at most [`crate::failure_policy::MAX_ATTEMPTS`] guarded attempts: a
/// [`SessionLifecycle`] serving exactly one unit, closed at once.
#[derive(Clone, Debug)]
pub struct Lifecycle {
    inner: SessionLifecycle,
}

const JOB_UNIT: &str = "job";

fn commands(commands: Vec<SessionCommand>) -> Vec<Command> {
    commands
        .into_iter()
        .filter_map(|command| match command {
            SessionCommand::Submit { session } => Some(Command::Submit { attempt: session }),
            SessionCommand::Register {
                session, worker, ..
            } => Some(Command::RegisterWorker {
                attempt: session,
                worker,
            }),
            SessionCommand::Run { session, .. } => Some(Command::StartJob { attempt: session }),
            SessionCommand::Shutdown { session } => Some(Command::Shutdown { attempt: session }),
            SessionCommand::Stop { session } => Some(Command::Stop { attempt: session }),
            // Never emitted for one unit: a single-unit lifecycle has no quiescence evidence, so
            // a cancel always stops the attempt.
            SessionCommand::Cancel { .. } => None,
            // Never emitted here: this pure lifecycle has no custody (`SessionConfig::single`).
            SessionCommand::RegisterMonitor { .. } => None,
            SessionCommand::Settled { .. } | SessionCommand::Refused { .. } => None,
        })
        .collect()
}

impl Lifecycle {
    /// A queued job: the first command is `Submit { attempt: 1 }`.
    pub fn new(submitted: MonoTime, limits: Limits) -> (Self, Vec<Command>) {
        let mut inner = SessionLifecycle::new(SessionConfig::single(limits.cleanup, limits.job));
        let unit = UnitPlan {
            id: JOB_UNIT.into(),
            limits,
        };
        let mut first = vec![];
        for input in [SessionInput::Submit(unit), SessionInput::Close] {
            first.extend(
                inner
                    .on(submitted, input)
                    .expect("a fresh session accepts one unit and close"),
            );
        }
        (Self { inner }, commands(first))
    }

    pub fn policy(&self) -> &JobPolicy {
        self.inner
            .unit_policy(JOB_UNIT)
            .expect("the lifecycle's one unit")
    }

    pub fn attempts(&self) -> Vec<AttemptRecord> {
        self.inner.sessions()
    }

    /// The finished job, once the outcome is known and every attempt is released or held.
    pub fn report(&self) -> Option<Report> {
        if !self.inner.settled() {
            return None;
        }
        let unit = self.inner.unit(JOB_UNIT)?;
        Some(Report {
            outcome: unit.outcome,
            attempts: self.attempts(),
            unit_attempts: unit.attempts,
            outputs: unit.outputs,
            abort: unit.abort,
        })
    }

    /// The next instant a [`Input::Tick`] can change anything.
    pub fn next_deadline(&self) -> Option<MonoTime> {
        self.inner.next_deadline()
    }

    /// @cc [owner:fontanierh,label:correctness] lifecycle-retry-once
    /// Only the guard's exit observation for the pinned worker identity, with no stop or
    /// shutdown requested and no guard or deadline stop, MAY become crash evidence; worker
    /// claims, pipe loss and foreign identities MUST NOT. A retry MUST be submitted only after
    /// the policy's `RequestAdmission`, which follows the previous attempt's confirmed cleanup
    /// receipt, and MUST launch only on the new attempt's own admission. See tests/worker_lifecycle.rs.
    pub fn on(&mut self, now: MonoTime, input: Input) -> Result<Vec<Command>, LifecycleError> {
        let input = match input {
            Input::Launch(event) => SessionInput::Launch(event),
            Input::Worker { attempt, event } => SessionInput::Worker {
                session: attempt,
                event,
            },
            Input::Registered { attempt, ok } => SessionInput::Registered {
                session: attempt,
                unit: JOB_UNIT.into(),
                ok,
            },
            Input::SubmitFailed { attempt, reason } => SessionInput::SubmitFailed {
                session: attempt,
                reason,
            },
            Input::Cancel => SessionInput::CancelAll,
            Input::Tick => SessionInput::Tick,
        };
        self.inner.on(now, input).map(commands)
    }
}

/// The controller's monotonic clock. Tests supply their own.
pub trait Clock {
    fn now(&self) -> MonoTime;
}

pub struct SystemClock(Instant);

impl SystemClock {
    pub fn new() -> Self {
        Self(Instant::now())
    }
}

impl Default for SystemClock {
    fn default() -> Self {
        Self::new()
    }
}

impl Clock for SystemClock {
    fn now(&self) -> MonoTime {
        MonoTime::from_elapsed(self.0.elapsed())
    }
}

/// Everything [`run_job`] needs for one job.
pub struct JobSpec {
    pub job: JobRequest,
    pub worker_version: String,
    pub command: WorkerCommand,
    pub purpose: String,
    pub memory_gib: u32,
    pub limits: Limits,
    /// Each attempt reports into a fresh `attempt-N` folder here.
    pub report_root: PathBuf,
    /// Checkout-lock duplicates; each attempt's custodian gets its own duplicate of each.
    pub custody: Vec<File>,
}

/// How a checkout lock is held: the scope part of a custody identity.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum LockScope {
    Exclusive,
    Shared,
}

/// A custody lock by what it locks, never by descriptor number: the lock file's device and
/// inode, and the scope it is held in.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct CustodyIdentity {
    pub device: u64,
    pub inode: u64,
    pub scope: LockScope,
}

impl CustodyIdentity {
    pub fn of(file: &File, scope: LockScope) -> io::Result<Self> {
        use std::os::unix::fs::MetadataExt;
        let metadata = file.metadata()?;
        Ok(Self {
            device: metadata.dev(),
            inode: metadata.ino(),
            scope,
        })
    }
}

/// @cc [owner:fontanierh,label:safety] session-refuses-incompatible-units
/// [`run_session`] MUST refuse, with a refused record and nothing queued or started, a unit whose
/// key differs from the session's in any part (exact worker command, worker version, admission
/// profile, job sandbox or custody set) or whose job id another unit of the session uses, and MUST refuse to
/// start at all unless its custody descriptors are exactly its key's custody set by device and
/// inode, each proven held in its declared scope by an independent non-blocking probe, and MUST
/// refuse to start a session reused on quiescence evidence unless its key declares the no-fork
/// job sandbox and it holds checkout custody (so a custody monitor is registered before every
/// `Run`). Custody is identified by lock file and scope, never by descriptor number. See
/// tests/guard_adapter.rs (`run_session_refuses_a_unit_with_another_key_or_a_used_job_id`,
/// `a_resident_session_refuses_a_key_without_the_no_fork_sandbox`,
/// `a_resident_session_without_custody_is_refused`,
/// `run_session_refuses_custody_that_is_not_its_keys_custody_set`,
/// `run_session_refuses_custody_not_held_in_its_declared_scope`).
///
/// What units sharing a session must share exactly: the worker, its version, the admission
/// profile, the job sandbox and the custody set.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SessionKey {
    pub worker_version: String,
    pub command: WorkerCommand,
    /// The admission profile: a job admission reserving this ceiling.
    pub memory_gib: u32,
    /// The sandbox the worker runs this key's jobs under.
    pub sandbox: JobSandbox,
    pub custody: BTreeSet<CustodyIdentity>,
}

/// The sandbox profile a worker runs its jobs under, as the caller declares it for a key.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum JobSandbox {
    /// The job profile whose kernel sandbox denies fork and spawn (pinned by
    /// platform/studio/tests/test_build_v2_job_fork.py). Only this profile may reuse a session.
    NoFork,
    /// Any other profile: every session serves one unit.
    Other,
}

/// The lock file an open descriptor refers to, for an independent probe.
fn lock_path(file: &File) -> io::Result<PathBuf> {
    use std::os::fd::AsRawFd;
    #[cfg(target_os = "macos")]
    {
        use std::os::unix::ffi::OsStrExt;
        let mut buffer = vec![0u8; libc::PATH_MAX as usize];
        // SAFETY: F_GETPATH writes at most PATH_MAX bytes into the buffer we own.
        if unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETPATH, buffer.as_mut_ptr()) } == -1 {
            return Err(io::Error::last_os_error());
        }
        let end = buffer.iter().position(|&b| b == 0).unwrap_or(buffer.len());
        Ok(PathBuf::from(std::ffi::OsStr::from_bytes(&buffer[..end])))
    }
    #[cfg(not(target_os = "macos"))]
    {
        std::fs::read_link(format!("/proc/self/fd/{}", file.as_raw_fd()))
    }
}

fn try_flock(file: &File, operation: libc::c_int) -> io::Result<bool> {
    use std::os::fd::AsRawFd;
    loop {
        // SAFETY: flock on a descriptor we own.
        if unsafe { libc::flock(file.as_raw_fd(), operation | libc::LOCK_NB) } == 0 {
            return Ok(true);
        }
        let error = io::Error::last_os_error();
        match error.kind() {
            io::ErrorKind::Interrupted => continue,
            io::ErrorKind::WouldBlock => return Ok(false),
            _ => return Err(error),
        }
    }
}

/// Whether the lock file behind `file` is held in `scope`, probed through an independent open of
/// the same file (device and inode checked), so the probe never touches `file`'s own lock. An
/// exclusive hold refuses both probes; a shared hold refuses only the exclusive one (the probe's
/// brief shared hold ends when it closes). This proves the file is held in that scope, not by
/// which descriptor.
fn holds(file: &File, scope: LockScope) -> io::Result<bool> {
    use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
    let expected = file.metadata()?;
    let probe = std::fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(lock_path(file)?)?;
    let actual = probe.metadata()?;
    if (actual.dev(), actual.ino()) != (expected.dev(), expected.ino()) {
        return Ok(false);
    }
    if try_flock(&probe, libc::LOCK_EX)? {
        return Ok(false); // nobody holds it; closing the probe releases this
    }
    let shared = try_flock(&probe, libc::LOCK_SH)?;
    Ok(match scope {
        LockScope::Exclusive => !shared,
        LockScope::Shared => shared,
    })
}

/// The custody descriptors are exactly the key's custody set: one descriptor per identity, by
/// device and inode, each holding its lock in the identity's scope.
fn custody_matches(files: &[File], key: &BTreeSet<CustodyIdentity>) -> Result<(), LifecycleError> {
    use std::os::unix::fs::MetadataExt;
    let refuse = |why: String| Err(LifecycleError::Invariant(why));
    let mut remaining: Vec<&CustodyIdentity> = key.iter().collect();
    if remaining.len() != files.len() {
        return refuse("the session's custody locks are not its key's custody set".into());
    }
    for file in files {
        let metadata = match file.metadata() {
            Ok(metadata) => metadata,
            Err(error) => return refuse(format!("cannot identify a custody lock: {error}")),
        };
        let Some(position) = remaining.iter().position(|identity| {
            (identity.device, identity.inode) == (metadata.dev(), metadata.ino())
        }) else {
            return refuse("the session's custody locks are not its key's custody set".into());
        };
        let identity = remaining.remove(position);
        match holds(file, identity.scope) {
            Ok(true) => {}
            Ok(false) => {
                return refuse(format!(
                    "a custody lock is not held in its declared {:?} scope",
                    identity.scope
                ));
            }
            Err(error) => return refuse(format!("cannot probe a custody lock: {error}")),
        }
    }
    Ok(())
}

/// The record a session persists, in its attempt folder, before its custody monitor is
/// registered on any lease: which guard invocation's cleanup decides whether that monitor's
/// lease entries may be treated as gone.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CleanupCorrelation {
    pub schema: u32,
    /// The custody monitor registered through `add_worker`.
    pub monitor: ProcessIdentity,
    /// The guard invocation the monitor reported with.
    pub invocation: String,
    /// The attempt folder holding the guard's receipts and the bridge's `cleanup.json`.
    pub receipts: PathBuf,
}

/// The correlation record's file name in an attempt folder.
pub const CORRELATION_FILE: &str = "custodian.json";
/// The bridge's durable cleanup decision in an attempt folder.
pub const CLEANUP_FILE: &str = "cleanup.json";
const RECORD_LIMIT: u64 = 64 * 1024;

fn read_bounded(path: &Path) -> io::Result<Vec<u8>> {
    let mut bytes = vec![];
    File::open(path)?
        .take(RECORD_LIMIT + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() as u64 > RECORD_LIMIT {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "record too large",
        ));
    }
    Ok(bytes)
}

impl CleanupCorrelation {
    /// The correlation record in attempt folder `receipts`.
    pub fn read(receipts: &Path) -> io::Result<Self> {
        let bytes = read_bounded(&receipts.join(CORRELATION_FILE))?;
        serde_json::from_slice(&bytes)
            .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))
    }

    /// The record naming `monitor` among the `attempt-N` folders under `report_root`, if any.
    pub fn find(report_root: &Path, monitor: &ProcessIdentity) -> Option<Self> {
        fs::read_dir(report_root)
            .ok()?
            .filter_map(Result::ok)
            .filter(|entry| entry.file_name().to_string_lossy().starts_with("attempt-"))
            .filter_map(|entry| Self::read(&entry.path()).ok())
            .find(|record| record.monitor == *monitor)
    }
}

/// The bridge's `cleanup.json`, as written by `atelier.build_v2.guarded_worker`.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CleanupRecord {
    schema: u32,
    invocation: String,
    boot: String,
    monitor: Option<(u32, u64)>,
    confirmed: bool,
    #[allow(dead_code)]
    child: Option<(u32, u64)>,
    #[allow(dead_code)]
    reason: Option<String>,
}

/// @cc [owner:fontanierh,label:safety] session-custodian-correlation
/// Before a session's custody monitor is added to any lease, the driver MUST durably persist its
/// [`CleanupCorrelation`] (monitor identity, guard invocation, attempt folder); a failure to
/// persist it MUST fail that registration. `cleanup_confirmed` MUST be true only for the bridge's
/// durable cleanup record of the same invocation, boot and monitor that confirms cleanup; a
/// missing, unreadable, malformed, unconfirmed or mismatched record MUST be false, so a reader
/// keeps a dead monitor's lease entries as unknown. Monitor exit alone is never evidence. See
/// tests/guard_adapter.rs (`the_custody_monitor_is_durably_registered_before_the_first_run`,
/// `cleanup_is_confirmed_only_by_this_invocations_durable_record`,
/// `a_controller_lost_after_registering_the_monitor_never_runs_and_leaves_its_correlation`).
pub fn cleanup_confirmed(correlation: &CleanupCorrelation) -> bool {
    let Ok(bytes) = read_bounded(&correlation.receipts.join(CLEANUP_FILE)) else {
        return false;
    };
    let Ok(record) = serde_json::from_slice::<CleanupRecord>(&bytes) else {
        return false;
    };
    let monitor = &correlation.monitor;
    let same_monitor = record
        .monitor
        .is_some_and(|(pid, started)| pid == monitor.pid && monitor.started == started.to_string());
    correlation.schema == 1
        && record.schema == 1
        && record.invocation == correlation.invocation
        && record.boot == monitor.boot
        && same_monitor
        && record.confirmed
}

fn correlate(report_dir: &Path, monitor: &ProcessIdentity, invocation: &str) -> io::Result<()> {
    crate::leases::replace_json(
        &report_dir.join(CORRELATION_FILE),
        &CleanupCorrelation {
            schema: 1,
            monitor: monitor.clone(),
            invocation: invocation.into(),
            receipts: report_dir.to_path_buf(),
        },
    )
}

/// Everything [`run_session`] needs for one session of compatible units.
pub struct SessionSpec {
    pub key: SessionKey,
    pub purpose: String,
    /// `lifetime` is the guard's execution limit for each session: a backstop, separate from
    /// unit job limits.
    pub config: SessionConfig,
    /// Each session reports into a fresh `attempt-N` folder here.
    pub report_root: PathBuf,
    /// Checkout-lock duplicates; each session's custodian gets its own duplicate of each. Their
    /// device and inode must be exactly the key's custody set.
    pub custody: Vec<File>,
}

/// One unit for [`run_session`]: its lifecycle plan, the job request it runs and the key it
/// needs its session to have.
#[derive(Clone, Debug)]
pub struct SessionUnit {
    pub plan: UnitPlan,
    pub job: JobRequest,
    pub key: SessionKey,
}

/// A settled session: every unit's record and every session's custody.
#[derive(Clone, Debug, PartialEq)]
pub struct SessionReport {
    pub sessions: Vec<AttemptRecord>,
    /// Every accepted unit, in submission order.
    pub units: Vec<UnitRecord>,
    /// Units refused at submission, in order; each was also handed to `published`.
    pub refused: Vec<UnitRecord>,
}

enum Message {
    Launch(AttemptEvent),
    Frame {
        attempt: u32,
        frame: io::Result<Option<Response>>,
    },
    WriteFailed {
        attempt: u32,
        error: String,
    },
    Submit(Box<SessionUnit>),
    CancelUnit(UnitId),
    Cancel,
    Close,
}

/// Cancels a running [`run_job`] or [`run_session`] from another thread.
#[derive(Clone)]
pub struct Canceller(Sender<Message>);

impl Canceller {
    pub fn cancel(&self) {
        let _ = self.0.send(Message::Cancel);
    }
}

/// Feeds a running [`run_session`] from another thread.
#[derive(Clone)]
pub struct SessionHandle(Sender<Message>);

impl SessionHandle {
    pub fn submit(&self, unit: SessionUnit) {
        let _ = self.0.send(Message::Submit(Box::new(unit)));
    }
    pub fn cancel(&self, unit: &str) {
        let _ = self.0.send(Message::CancelUnit(unit.into()));
    }
    pub fn cancel_all(&self) {
        let _ = self.0.send(Message::Cancel);
    }
    /// No more units: drain, then end the session gracefully.
    pub fn close(&self) {
        let _ = self.0.send(Message::Close);
    }
}

struct Live<A> {
    handle: A,
    session: Session,
    /// Queue to the attempt's writer thread; dropping it closes the request pipe once the
    /// thread finishes any write in progress.
    writer: Option<Sender<Request>>,
    /// When the controller received the latest terminal reply (seconds since the epoch): a tree
    /// sample is evidence only if taken after it.
    terminal_at: Option<f64>,
    /// The response stream ended (or there never was one): every frame is read.
    drained: bool,
    /// The guard's exit report and the session's later guard events, waiting for the response
    /// stream to end (session-exit-after-drain).
    held: Vec<AttemptEvent>,
    /// When a held exit report is applied even if the stream has not ended.
    drain_by: Option<MonoTime>,
    /// The guard's custody monitor and the invocation it reported with.
    monitor: Option<(ProcessIdentity, String)>,
    /// The session's cleanup correlation record is on disk.
    correlated: bool,
}

/// How long the guard's exit report may wait for the worker's response stream to end. The bridge
/// closes its own protocol descriptors before it reports the exit, so the end normally follows
/// within the reader's next read.
pub const EXIT_DRAIN_LIMIT: Duration = Duration::from_secs(2);

impl<A> Live<A> {
    /// The guard reported this session's worker exit, applied or still held.
    fn exit_held(&self) -> bool {
        self.held
            .iter()
            .any(|event| matches!(event.event, LaunchEvent::ChildExited { .. }))
    }

    /// The guard's exit report waits: still held, or released by the stream's end into `replay`
    /// and not yet applied there (session-exit-after-drain).
    fn exit_waiting(&self, attempt: u32, replay: &VecDeque<SessionInput>) -> bool {
        self.exit_held()
            || replay.iter().any(|input| {
                matches!(
                    input,
                    SessionInput::Launch(AttemptEvent {
                        attempt: replayed,
                        event: LaunchEvent::ChildExited { .. },
                    }) if *replayed == attempt
                )
            })
    }

    /// Release every held guard event, in order.
    fn release(&mut self, replay: &mut VecDeque<SessionInput>) {
        self.drain_by = None;
        for event in std::mem::take(&mut self.held) {
            replay.push_back(self.launch_input(event));
        }
    }

    fn launch_input(&mut self, event: AttemptEvent) -> SessionInput {
        match &event.event {
            // The admission owner is done; drop its pipes and handle.
            LaunchEvent::Finished { .. } => self.writer = None,
            LaunchEvent::Monitor {
                monitor,
                invocation,
            } if self.monitor.is_none() => {
                self.monitor = Some((monitor.clone(), invocation.clone()));
            }
            _ => {}
        }
        SessionInput::Launch(event)
    }
}

/// The session a `Stop` command may signal: none while its exit report waits, held or released
/// into `replay` and not yet applied (session-exit-after-drain).
fn stop_target<'a, A>(
    live: &'a mut BTreeMap<u32, Live<A>>,
    session: u32,
    replay: &VecDeque<SessionInput>,
) -> Option<&'a mut Live<A>> {
    live.get_mut(&session)
        .filter(|entry| !entry.exit_waiting(session, replay))
}

fn wall_clock() -> f64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_or(0.0, |elapsed| elapsed.as_secs_f64())
}

fn reader(attempt: u32, mut stream: Box<dyn Read + Send>, sink: Sender<Message>) {
    thread::spawn(move || {
        loop {
            let frame = read_frame::<_, Response>(&mut stream);
            let last = !matches!(frame, Ok(Some(_)));
            if sink.send(Message::Frame { attempt, frame }).is_err() || last {
                return;
            }
        }
    });
}

/// Requests are written on their own thread, so a worker that stops reading can never block
/// the lifecycle's deadline, cancellation or stop handling (failure-policy-time-limits). A
/// blocked write ends when the guard stops the worker and the pipe closes.
fn writer(
    attempt: u32,
    mut stream: Box<dyn Write + Send>,
    sink: Sender<Message>,
) -> Sender<Request> {
    let (requests, queue) = mpsc::channel::<Request>();
    thread::spawn(move || {
        for request in queue {
            if let Err(error) = write_frame(&mut stream, &request) {
                let _ = sink.send(Message::WriteFailed {
                    attempt,
                    error: error.to_string(),
                });
                return;
            }
        }
    });
    requests
}

/// A channel pair for [`run_job`]: hand out the [`Canceller`], pass the other half in.
pub fn job_channel() -> (Canceller, JobInbox) {
    let (sender, receiver) = mpsc::channel();
    (Canceller(sender.clone()), JobInbox { sender, receiver })
}

/// A channel pair for [`run_session`]: hand out the [`SessionHandle`], pass the other half in.
pub fn session_channel() -> (SessionHandle, JobInbox) {
    let (sender, receiver) = mpsc::channel();
    (SessionHandle(sender.clone()), JobInbox { sender, receiver })
}

pub struct JobInbox {
    sender: Sender<Message>,
    receiver: Receiver<Message>,
}

fn send<A>(entry: &Live<A>, request: Request) -> Result<(), WorkerFault> {
    let writer = entry
        .writer
        .as_ref()
        .ok_or_else(|| WorkerFault::Disconnected("no request pipe".into()))?;
    writer
        .send(request)
        .map_err(|_| WorkerFault::Disconnected("the request pipe closed".into()))
}

fn fault_of(error: SessionError) -> WorkerFault {
    match error {
        SessionError::Disconnected(message) => WorkerFault::Disconnected(message),
        other => WorkerFault::Protocol(other.to_string()),
    }
}

/// Run one job to a settled [`Report`]: every attempt released or held. It is a session with
/// one unit, closed at once. `register` must durably add a worker identity to the write lease
/// (B2 `add_worker`).
pub fn run_job<L: WorkerLauncher>(
    launcher: &mut L,
    clock: &dyn Clock,
    spec: &JobSpec,
    inbox: JobInbox,
    register: &mut dyn FnMut(&ProcessIdentity) -> Result<(), String>,
) -> Result<Report, LifecycleError> {
    let job = spec.job.clone();
    run_job_prepared(launcher, clock, spec, inbox, register, &mut |_| {
        Ok(job.clone())
    })
}

/// [`run_job`], with the job request prepared per attempt: `prepare(attempt)` returns the request
/// attempt `attempt` (1 for the first) runs, as [`run_session_prepared`] describes. `spec.job` is
/// the job's identity; every prepared request must keep its job id.
pub fn run_job_prepared<L: WorkerLauncher>(
    launcher: &mut L,
    clock: &dyn Clock,
    spec: &JobSpec,
    inbox: JobInbox,
    register: &mut dyn FnMut(&ProcessIdentity) -> Result<(), String>,
    prepare: &mut dyn FnMut(u32) -> Result<JobRequest, String>,
) -> Result<Report, LifecycleError> {
    let shared = Shared {
        worker_version: &spec.worker_version,
        command: &spec.command,
        purpose: &spec.purpose,
        memory_gib: spec.memory_gib,
        config: SessionConfig {
            custodian: !spec.custody.is_empty(),
            ..SessionConfig::single(spec.limits.cleanup, spec.limits.job)
        },
        report_root: &spec.report_root,
        custody: &spec.custody,
        key: None,
    };
    // The unit and the close reach the lifecycle before anything already in the inbox, so a
    // cancel sent before `run_job` cancels this job (C5b's queued cancel).
    let unit = (
        UnitPlan {
            id: JOB_UNIT.into(),
            limits: spec.limits,
        },
        spec.job.clone(),
    );
    let (published, _records) = mpsc::channel();
    let report = drive(
        launcher,
        clock,
        &shared,
        inbox,
        &mut |_, worker| register(worker),
        &mut |_, attempt, _| prepare(attempt),
        &mut |_| Ok(()),
        published,
        Some(unit),
    )?;
    let unit = report
        .units
        .into_iter()
        .next()
        .ok_or_else(|| LifecycleError::Invariant("the job's unit is missing".into()))?;
    Ok(Report {
        outcome: unit.outcome,
        attempts: report.sessions,
        unit_attempts: unit.attempts,
        outputs: unit.outputs,
        abort: unit.abort,
    })
}

/// @cc [owner:fontanierh,label:correctness] session-publication-off-lifecycle
/// A settled or refused unit's record MUST be handed off through `published` without waiting on
/// its receiver, so publication never blocks the lifecycle's deadlines, cancellation or stops.
/// This holds by type: `published` is an unbounded `std::sync::mpsc::Sender`, and a send to a
/// dropped receiver is ignored. See tests/guard_adapter.rs
/// (`run_session_hands_each_settled_unit_off_without_waiting_for_its_receiver`, which also
/// checks every record arrives in order and a dropped receiver never ends the session).
///
/// Run a session of compatible units to a settled [`SessionReport`]: every unit released or held,
/// after [`SessionHandle::close`]. `register` must durably add the session's worker identity to
/// the unit's write lease (B2 `add_worker`) before that unit runs.
pub fn run_session<L: WorkerLauncher>(
    launcher: &mut L,
    clock: &dyn Clock,
    spec: &SessionSpec,
    inbox: JobInbox,
    register: &mut dyn FnMut(&UnitId, &ProcessIdentity) -> Result<(), String>,
    published: Sender<UnitRecord>,
) -> Result<SessionReport, LifecycleError> {
    run_session_with(
        launcher,
        clock,
        spec,
        inbox,
        register,
        &mut |_, _, job| Ok(job.clone()),
        published,
    )
}

/// @cc [owner:fontanierh,label:correctness] session-prepare-per-attempt
/// `prepare` MUST be called exactly once for each attempt of a unit, after that attempt's
/// admission and its worker's registration and before its `Run`, and that `Run` MUST carry the
/// request it returned. A failure, or a request with another job id than the submitted one, MUST
/// end the unit without a `Run`. A retry gets its own call and request; nothing here reuses or
/// clears an earlier attempt's folder, which stays as evidence. `prepare` runs on the lifecycle
/// thread, so it must be quick (clones or links). See tests/guard_adapter.rs
/// (`a_crash_retry_runs_a_freshly_prepared_request_in_a_later_session`,
/// `a_failed_preparation_ends_the_unit_without_a_run_and_is_never_retried`) and
/// tests/session_lifecycle.rs (`a_failed_preparation_ends_the_unit_without_a_run`).
///
/// [`run_session`], with each attempt's job request prepared by `prepare(unit, attempt)` (1 for a
/// unit's first attempt) instead of the submitted one. The submitted request stays the unit's
/// identity: its job id must be unique in the session and every prepared request must keep it.
pub fn run_session_prepared<L: WorkerLauncher>(
    launcher: &mut L,
    clock: &dyn Clock,
    spec: &SessionSpec,
    inbox: JobInbox,
    register: &mut dyn FnMut(&UnitId, &ProcessIdentity) -> Result<(), String>,
    prepare: &mut dyn FnMut(&UnitId, u32) -> Result<JobRequest, String>,
    published: Sender<UnitRecord>,
) -> Result<SessionReport, LifecycleError> {
    run_session_with(
        launcher,
        clock,
        spec,
        inbox,
        register,
        &mut |unit, attempt, _| prepare(unit, attempt),
        published,
    )
}

/// Check actual worker startup evidence after Ready and durable registration, before Run.
/// A refusal sends no Run and follows the existing owned cancellation/cleanup path.
pub fn run_session_ready_checked<L: WorkerLauncher>(
    launcher: &mut L,
    clock: &dyn Clock,
    spec: &SessionSpec,
    inbox: JobInbox,
    register: &mut dyn FnMut(&UnitId, &ProcessIdentity) -> Result<(), String>,
    prepare: &mut dyn FnMut(&UnitId, u32) -> Result<JobRequest, String>,
    before_run: &mut dyn FnMut(&UnitId) -> Result<(), String>,
    published: Sender<UnitRecord>,
) -> Result<SessionReport, LifecycleError> {
    run_session_with_check(
        launcher,
        clock,
        spec,
        inbox,
        register,
        &mut |unit, attempt, _| prepare(unit, attempt),
        before_run,
        published,
    )
}

type Prepare<'a> = dyn FnMut(&UnitId, u32, &JobRequest) -> Result<JobRequest, String> + 'a;

fn run_session_with<L: WorkerLauncher>(
    launcher: &mut L,
    clock: &dyn Clock,
    spec: &SessionSpec,
    inbox: JobInbox,
    register: &mut dyn FnMut(&UnitId, &ProcessIdentity) -> Result<(), String>,
    prepare: &mut Prepare<'_>,
    published: Sender<UnitRecord>,
) -> Result<SessionReport, LifecycleError> {
    run_session_with_check(
        launcher,
        clock,
        spec,
        inbox,
        register,
        prepare,
        &mut |_| Ok(()),
        published,
    )
}

fn run_session_with_check<L: WorkerLauncher>(
    launcher: &mut L,
    clock: &dyn Clock,
    spec: &SessionSpec,
    inbox: JobInbox,
    register: &mut dyn FnMut(&UnitId, &ProcessIdentity) -> Result<(), String>,
    prepare: &mut Prepare<'_>,
    before_run: &mut dyn FnMut(&UnitId) -> Result<(), String>,
    published: Sender<UnitRecord>,
) -> Result<SessionReport, LifecycleError> {
    if spec.config.quiescence.is_some() && spec.key.sandbox != JobSandbox::NoFork {
        // Quiescence evidence assumes jobs cannot fork (session-reuse-after-quiescence); every
        // unit carries this key, so none may run on a reused session.
        return Err(LifecycleError::Invariant(
            "a session reused on quiescence evidence needs the no-fork job sandbox".into(),
        ));
    }
    if spec.config.quiescence.is_some() && spec.custody.is_empty() {
        // Reuse needs a registered custody monitor before every Run (Q3), and only a session
        // holding checkout custody has one.
        return Err(LifecycleError::Invariant(
            "a session reused on quiescence evidence needs checkout custody".into(),
        ));
    }
    custody_matches(&spec.custody, &spec.key.custody)?;
    let shared = Shared {
        worker_version: &spec.key.worker_version,
        command: &spec.key.command,
        purpose: &spec.purpose,
        memory_gib: spec.key.memory_gib,
        config: SessionConfig {
            custodian: !spec.custody.is_empty(),
            ..spec.config
        },
        report_root: &spec.report_root,
        custody: &spec.custody,
        key: Some(&spec.key),
    };
    drive(
        launcher, clock, &shared, inbox, register, prepare, before_run, published, None,
    )
}

/// What [`run_job`] and [`run_session`] share, borrowed so a custody duplicate is made only per
/// submitted session (a failure there is a launch failure, as in C5b).
struct Shared<'a> {
    worker_version: &'a str,
    command: &'a WorkerCommand,
    purpose: &'a str,
    memory_gib: u32,
    config: SessionConfig,
    report_root: &'a Path,
    custody: &'a [File],
    /// A session's units must carry exactly this key; `None` for [`run_job`]'s one unit.
    key: Option<&'a SessionKey>,
}

/// @cc [owner:fontanierh,label:correctness] session-exit-after-drain
/// The guard's exit report for a session's worker MUST reach the lifecycle only after the
/// worker's response stream has ended, so every reply the worker wrote before exiting is applied
/// first, or once [`EXIT_DRAIN_LIMIT`] has passed; the session's later guard events MUST follow it
/// in order. While the report waits, the driver MUST NOT signal that session's admission owner,
/// which is already unwinding. See tests/guard_adapter.rs
/// (`a_reply_read_after_the_exit_report_still_completes_the_unit`,
/// `an_exit_report_without_the_stream_end_applies_after_the_drain_limit`), and this module's
/// `a_stop_after_an_invalid_frame_never_signals_an_owner_whose_exit_waits_for_replay`.
///
/// `only`: one unit submitted and closed before the inbox is read.
#[allow(clippy::too_many_arguments)]
fn drive<L: WorkerLauncher>(
    launcher: &mut L,
    clock: &dyn Clock,
    spec: &Shared<'_>,
    inbox: JobInbox,
    register: &mut dyn FnMut(&UnitId, &ProcessIdentity) -> Result<(), String>,
    prepare: &mut Prepare<'_>,
    before_run: &mut dyn FnMut(&UnitId) -> Result<(), String>,
    published: Sender<UnitRecord>,
    only: Option<(UnitPlan, JobRequest)>,
) -> Result<SessionReport, LifecycleError> {
    let mut lifecycle = SessionLifecycle::new(spec.config);
    let mut jobs: BTreeMap<UnitId, JobRequest> = BTreeMap::new();
    // Each unit's request for its current attempt, from `prepare`, until its `Run` takes it.
    let mut prepared: BTreeMap<UnitId, JobRequest> = BTreeMap::new();
    let mut live: BTreeMap<u32, Live<L::Attempt>> = BTreeMap::new();
    let mut pending: Vec<SessionInput> = vec![];
    let mut replay: VecDeque<SessionInput> = VecDeque::new();
    let mut commands: Vec<SessionCommand> = vec![];
    let mut refused: Vec<UnitRecord> = vec![];
    if let Some((plan, job)) = only {
        let now = clock.now();
        jobs.insert(plan.id.clone(), job);
        commands.extend(lifecycle.on(now, SessionInput::Submit(plan))?);
        commands.extend(lifecycle.on(now, SessionInput::Close)?);
    }
    loop {
        for command in std::mem::take(&mut commands) {
            match command {
                SessionCommand::Submit { session } => {
                    let request = (|| -> io::Result<AdmissionRequest> {
                        let queue_limit =
                            lifecycle.session_queue_deadline(session).map(|deadline| {
                                // Slightly past the overall deadline, so the policy stops the
                                // attempt first and the guard withdraws it through normal cancel.
                                deadline
                                    .elapsed()
                                    .saturating_sub(clock.now().elapsed())
                                    .saturating_add(spec.config.cleanup)
                            });
                        Ok(AdmissionRequest {
                            purpose: spec.purpose.into(),
                            memory_gib: spec.memory_gib,
                            execution_limit: spec.config.lifetime,
                            queue_limit,
                            report_dir: spec.report_root.join(format!("attempt-{session}")),
                            custody: spec
                                .custody
                                .iter()
                                .map(File::try_clone)
                                .collect::<io::Result<_>>()?,
                        })
                    })();
                    let submitted = request.and_then(|request| {
                        launcher.submit(session, spec.command, request, {
                            let sink = inbox.sender.clone();
                            let (events, relay) = mpsc::channel::<AttemptEvent>();
                            thread::spawn(move || {
                                for event in relay {
                                    if sink.send(Message::Launch(event)).is_err() {
                                        return;
                                    }
                                }
                            });
                            events
                        })
                    });
                    match submitted {
                        Ok(mut handle) => {
                            let writer = handle.take_pipes().map(|(response, request)| {
                                reader(session, response, inbox.sender.clone());
                                writer(session, request, inbox.sender.clone())
                            });
                            live.insert(
                                session,
                                Live {
                                    handle,
                                    session: Session::new(spec.worker_version),
                                    drained: writer.is_none(),
                                    writer,
                                    terminal_at: None,
                                    held: vec![],
                                    drain_by: None,
                                    monitor: None,
                                    correlated: false,
                                },
                            );
                        }
                        Err(error) => pending.push(SessionInput::SubmitFailed {
                            session,
                            reason: error.to_string(),
                        }),
                    }
                }
                SessionCommand::Register {
                    session,
                    unit,
                    worker,
                } => {
                    // Registration first, then this attempt's request (session-prepare-per-attempt).
                    let input = if register(&unit, &worker).is_err() {
                        SessionInput::Registered {
                            session,
                            unit,
                            ok: false,
                        }
                    } else {
                        let made = match (jobs.get(&unit), lifecycle.unit_attempt(&unit)) {
                            (Some(job), Some(attempt)) => match prepare(&unit, attempt, job) {
                                Ok(request) if request.job_id == job.job_id => Ok(request),
                                Ok(_) => {
                                    Err("the prepared request changed the unit's job id".into())
                                }
                                Err(reason) => Err(reason),
                            },
                            _ => Err("no submitted job request or attempt for the unit".into()),
                        };
                        match made {
                            Ok(request) => {
                                prepared.insert(unit.clone(), request);
                                SessionInput::Registered {
                                    session,
                                    unit,
                                    ok: true,
                                }
                            }
                            Err(reason) => {
                                prepared.remove(&unit);
                                SessionInput::PrepareFailed {
                                    session,
                                    unit,
                                    reason,
                                }
                            }
                        }
                    };
                    pending.push(input);
                }
                SessionCommand::RegisterMonitor {
                    session,
                    unit,
                    monitor,
                } => {
                    // The correlation first, durably, then the lease (session-custodian-correlation).
                    let report_dir = spec.report_root.join(format!("attempt-{session}"));
                    let ok = live.get_mut(&session).is_some_and(|entry| {
                        let correlated = match &entry.monitor {
                            Some((reported, invocation)) if *reported == monitor => {
                                entry.correlated
                                    || correlate(&report_dir, &monitor, invocation).is_ok()
                            }
                            _ => false,
                        };
                        entry.correlated |= correlated;
                        correlated
                    }) && register(&unit, &monitor).is_ok();
                    pending.push(SessionInput::MonitorRegistered { session, unit, ok });
                }
                SessionCommand::Run { session, unit } => {
                    let Some(entry) = live.get_mut(&session) else {
                        continue;
                    };
                    let request = match prepared.remove(&unit) {
                        Some(job) => before_run(&unit)
                            .map_err(|reason| {
                                WorkerFault::Protocol(format!(
                                    "worker startup check refused: {reason}"
                                ))
                            })
                            .and_then(|()| entry.session.run(job).map_err(fault_of)),
                        None => Err(WorkerFault::Protocol(format!(
                            "no job request for unit {unit}"
                        ))),
                    };
                    if let Err(fault) = request.and_then(|request| send(entry, request)) {
                        pending.push(SessionInput::Worker {
                            session,
                            event: Err(fault),
                        });
                    }
                }
                SessionCommand::Cancel { session, .. } => {
                    let Some(entry) = live.get_mut(&session) else {
                        continue;
                    };
                    let request = entry.session.cancel().map_err(fault_of);
                    if let Err(fault) = request.and_then(|request| send(entry, request)) {
                        pending.push(SessionInput::Worker {
                            session,
                            event: Err(fault),
                        });
                    }
                }
                SessionCommand::Shutdown { session } => {
                    let Some(entry) = live.get_mut(&session) else {
                        continue;
                    };
                    let request = entry.session.shutdown().map_err(fault_of);
                    if let Err(fault) = request.and_then(|request| send(entry, request)) {
                        pending.push(SessionInput::Worker {
                            session,
                            event: Err(fault),
                        });
                    }
                }
                SessionCommand::Stop { session } => {
                    // A held exit report means the guard is already unwinding: never interrupt
                    // it (session-exit-after-drain). Its receipt or settlement limit decides.
                    if let Some(entry) = stop_target(&mut live, session, &replay) {
                        let _ = entry.handle.stop();
                    }
                }
                // Unbounded channel: a slow or absent receiver never blocks here.
                SessionCommand::Settled { unit } => {
                    if let Some(record) = lifecycle.unit(&unit) {
                        let _ = published.send(record);
                    }
                }
                SessionCommand::Refused { unit, reason } => {
                    let record = UnitRecord::refused(unit, reason);
                    let _ = published.send(record.clone());
                    refused.push(record);
                }
            }
        }
        if lifecycle.done() {
            return Ok(SessionReport {
                sessions: lifecycle.sessions(),
                units: lifecycle.units(),
                refused,
            });
        }
        let now = clock.now();
        for entry in live.values_mut() {
            if entry.drain_by.is_some_and(|by| now >= by) {
                entry.release(&mut replay);
            }
        }
        let next = pending.pop().or_else(|| replay.pop_front());
        let input = match next {
            Some(input) => input,
            None => {
                let drains = live.values().filter_map(|entry| entry.drain_by);
                let message = match lifecycle.next_deadline().into_iter().chain(drains).min() {
                    Some(deadline) => {
                        let wait = deadline
                            .elapsed()
                            .saturating_sub(clock.now().elapsed())
                            .max(Duration::from_millis(1));
                        match inbox.receiver.recv_timeout(wait) {
                            Ok(message) => Some(message),
                            Err(RecvTimeoutError::Timeout) => None,
                            Err(RecvTimeoutError::Disconnected) => None,
                        }
                    }
                    None => inbox.receiver.recv().ok(),
                };
                match message {
                    None => SessionInput::Tick,
                    Some(Message::Cancel) => SessionInput::CancelAll,
                    Some(Message::Close) => SessionInput::Close,
                    Some(Message::CancelUnit(unit)) => SessionInput::CancelUnit(unit),
                    Some(Message::Submit(unit)) => {
                        // Only an accepted unit's job is kept; the lifecycle refuses the rest.
                        let SessionUnit { plan, job, key } = *unit;
                        let id = plan.id.clone();
                        let mismatch = if spec.key.is_some_and(|want| *want != key) {
                            Some(Refusal::IncompatibleKey)
                        } else if jobs.values().any(|other| other.job_id == job.job_id) {
                            Some(Refusal::JobIdInUse)
                        } else {
                            None
                        };
                        if let Some(reason) = mismatch {
                            let record = UnitRecord::refused(id, reason);
                            let _ = published.send(record.clone());
                            refused.push(record);
                            continue;
                        }
                        let fresh = !jobs.contains_key(&id);
                        let out = lifecycle.on(clock.now(), SessionInput::Submit(plan))?;
                        let accepted = !out.iter().any(
                            |c| matches!(c, SessionCommand::Refused { unit, .. } if *unit == id),
                        );
                        if fresh && accepted {
                            jobs.insert(id, job);
                        }
                        commands = out;
                        continue;
                    }
                    Some(Message::WriteFailed { attempt, error }) => SessionInput::Worker {
                        session: attempt,
                        event: Err(WorkerFault::Disconnected(error)),
                    },
                    Some(Message::Launch(AttemptEvent {
                        attempt,
                        event: LaunchEvent::TreeSample(sample),
                    })) => {
                        // Evidence only when fresh and exact for the pinned worker, after the
                        // latest terminal reply (quiescence-sample-evidence), and never once the
                        // guard reported the worker's exit; otherwise dropped.
                        if live
                            .get(&attempt)
                            .is_some_and(|entry| !entry.held.is_empty())
                        {
                            continue;
                        }
                        let pinned = lifecycle
                            .sessions()
                            .into_iter()
                            .find(|record| record.attempt == attempt)
                            .and_then(|record| record.worker);
                        let after = live.get(&attempt).and_then(|entry| entry.terminal_at);
                        match (pinned, after) {
                            (Some(pinned), Some(after))
                                if quiescence(&sample, &pinned, after, wall_clock()).is_ok() =>
                            {
                                SessionInput::Quiescent {
                                    session: attempt,
                                    sample_time: sample.time,
                                }
                            }
                            _ => continue,
                        }
                    }
                    Some(Message::Launch(event)) => {
                        let Some(entry) = live.get_mut(&event.attempt) else {
                            commands = lifecycle.on(clock.now(), SessionInput::Launch(event))?;
                            continue;
                        };
                        let exit = matches!(event.event, LaunchEvent::ChildExited { .. });
                        if !entry.held.is_empty() || (exit && !entry.drained) {
                            // Wait for the replies the worker wrote before it exited.
                            if entry.held.is_empty() {
                                entry.drain_by = clock.now().checked_add(EXIT_DRAIN_LIMIT);
                            }
                            entry.held.push(event);
                            continue;
                        }
                        entry.launch_input(event)
                    }
                    Some(Message::Frame { attempt, frame }) => {
                        let Some(entry) = live.get_mut(&attempt) else {
                            continue;
                        };
                        if !matches!(frame, Ok(Some(_))) {
                            // The stream's end: a held exit report follows this input.
                            entry.drained = true;
                            entry.release(&mut replay);
                        }
                        let event = match frame {
                            Ok(Some(response)) => {
                                let event = entry.session.receive(response).map_err(fault_of);
                                if matches!(event, Ok(WorkerEvent::Finished(_))) {
                                    entry.terminal_at = Some(wall_clock());
                                }
                                event
                            }
                            Ok(None) => match entry.session.end_of_stream() {
                                Ok(()) => continue,
                                Err(error) => Err(fault_of(error)),
                            },
                            Err(error) => Err(if error.kind() == io::ErrorKind::InvalidData {
                                WorkerFault::Protocol(error.to_string())
                            } else {
                                WorkerFault::Disconnected(error.to_string())
                            }),
                        };
                        SessionInput::Worker {
                            session: attempt,
                            event,
                        }
                    }
                }
            }
        };
        commands = lifecycle.on(clock.now(), input)?;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::guard_adapter::ExitInfo;

    fn exit(pid: u32) -> AttemptEvent {
        AttemptEvent {
            attempt: 1,
            event: LaunchEvent::ChildExited {
                worker: ProcessIdentity {
                    pid,
                    boot: "boot-1".into(),
                    started: format!("start-{pid}"),
                },
                exit: ExitInfo::Code(0),
                stopped_by: None,
            },
        }
    }

    /// The reviewer's timeline: the guard's exit report is held waiting for the response stream,
    /// then the stream ends with an InvalidData frame error. The driver's frame arm releases the
    /// held exit into `replay` before it applies the protocol fault, whose Stop must still see
    /// the exit as waiting and never signal the unwinding owner.
    #[test]
    fn a_stop_after_an_invalid_frame_never_signals_an_owner_whose_exit_waits_for_replay() {
        let mut entry = Live {
            handle: (),
            session: Session::new("w1"),
            writer: None,
            terminal_at: None,
            drained: false,
            held: vec![exit(101)],
            drain_by: None,
            monitor: None,
            correlated: false,
        };
        let mut replay = VecDeque::new();
        assert!(entry.exit_waiting(1, &replay), "held: the exit waits");
        // The frame arm on `Err(InvalidData)`: the stream's end releases the held exit.
        entry.drained = true;
        entry.release(&mut replay);
        assert!(
            !entry.exit_held(),
            "the held list alone no longer shows the exit"
        );
        // The Stop arm's own target: no owner to signal while the released exit waits.
        let mut live = BTreeMap::from([(1, entry)]);
        assert!(
            stop_target(&mut live, 1, &replay).is_none(),
            "released but not yet applied: the exit still waits, so nothing is signalled"
        );
        assert!(
            stop_target(&mut live, 2, &replay).is_none(),
            "no such session"
        );
        // Once replayed (applied), the session may be signalled again.
        replay.clear();
        assert!(stop_target(&mut live, 1, &replay).is_some());
    }
}
