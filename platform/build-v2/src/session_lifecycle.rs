//! C5c: one guarded worker session serving a sequence of units.
//!
//! [`SessionLifecycle`] is the pure state machine behind both [`crate::worker_lifecycle::run_job`]
//! (a session with one unit) and resident batch sessions. A *session* is one guarded attempt: one
//! admission, one bridge and one pinned worker identity, tracked exactly as C5b tracks an attempt
//! (custody `Released` only from the guard's confirmed receipt, `Held` on anything less). Each
//! *unit* is one job with its own C5a [`JobPolicy`]: its job limit starts when it is assigned to an
//! admitted session, its overall deadline counts from its submission, and a crash retry joins a
//! later session only after the session it ran on is confirmed clean. Once any session is held,
//! no further session starts in this lifecycle (see [`SessionLifecycle`]).
//!
//! A session serves another unit only when [`SessionConfig::quiescence`] is set: after the
//! previous unit's terminal reply, the next `Run` waits for quiescence evidence taken after it
//! ([`SessionInput::Quiescent`]); without it in time the session stops and the unit settles only
//! by the session's cleanup receipt. Nothing here releases capacity, signals a process or deletes
//! a result.
use crate::failure_policy::{
    CleanupState, Decision, End, Event as PolicyEvent, JobPolicy, Limits, MonoTime, Observation,
    Outcome, Phase, Stop,
};
use crate::guard_adapter::{AttemptEvent, CleanupReceipt, LaunchEvent, StoppedBy};
use crate::leases::ProcessIdentity;
use crate::protocol::JobOutputs;
use crate::worker_lifecycle::{AttemptRecord, Custody, LifecycleError, WorkerFault};
use crate::worker_session::Event as WorkerEvent;
use std::time::Duration;

pub type UnitId = String;

/// One unit as the lifecycle sees it. The driver keeps the job request itself.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct UnitPlan {
    pub id: UnitId,
    pub limits: Limits,
}

/// How long an open session keeps an idle, admitted worker before shutting it down by default.
pub const DEFAULT_IDLE: Duration = Duration::from_secs(2);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SessionConfig {
    /// How long an ending session may take to deliver its cleanup receipt.
    pub cleanup: Duration,
    /// The guard's execution limit for each session, from its admission. A later unit joins a
    /// session only if its job and cleanup limits fit in what remains.
    pub lifetime: Duration,
    /// How long an open session with nothing queued keeps an idle, admitted worker.
    pub idle: Duration,
    /// `Some(bound)`: the driver delivers [`SessionInput::Quiescent`], so a session may serve
    /// further units, each only after the previous one is proven quiescent; the evidence must
    /// arrive within `bound` of the unit's terminal reply or cancel. Keep `bound` well under the
    /// units' cleanup limits. `None`: every session serves exactly one unit.
    pub quiescence: Option<Duration>,
    /// The sessions hold checkout custody, so each guard's custody monitor reports its identity
    /// ([`LaunchEvent::Monitor`]) and that identity must be registered for a unit before its
    /// `Run` (session-custodian-registered-before-run). The driver sets it from the custody set.
    pub custodian: bool,
}

impl SessionConfig {
    /// One unit per session, with the default idle time.
    pub fn single(cleanup: Duration, lifetime: Duration) -> Self {
        Self {
            cleanup,
            lifetime,
            idle: DEFAULT_IDLE,
            quiescence: None,
            custodian: false,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub enum SessionInput {
    /// A unit joins the queue; `now` is its submission time. A unit that can never be served is
    /// refused at once with a [`Refusal`]: [`SessionCommand::Refused`].
    Submit(UnitPlan),
    /// No more units will be submitted.
    Close,
    CancelUnit(UnitId),
    /// Cancel every unit and close.
    CancelAll,
    /// A guard observation for one session (`attempt` is the session number).
    Launch(AttemptEvent),
    Worker {
        session: u32,
        event: Result<WorkerEvent, WorkerFault>,
    },
    /// The session's worker was durably added to the unit's write lease (or not). The driver
    /// reports success only once the attempt's job request is also prepared.
    Registered {
        session: u32,
        unit: UnitId,
        ok: bool,
    },
    /// The worker was registered, but the job request for the unit's current attempt could not
    /// be prepared: the unit ends without a `Run`, as after a failed registration.
    PrepareFailed {
        session: u32,
        unit: UnitId,
        reason: String,
    },
    /// The session's custody monitor was durably added to the unit's write lease (or not), with
    /// its correlation record persisted first.
    MonitorRegistered {
        session: u32,
        unit: UnitId,
        ok: bool,
    },
    /// Quiescence evidence for `session`: a validated tree sample, taken after the session's
    /// latest terminal reply, that shows only the session's pinned worker (and the shared
    /// services the guard excludes). The driver validates the sample and its ordering.
    Quiescent {
        session: u32,
        sample_time: f64,
    },
    /// The session's admission owner could not be started; nothing is held.
    SubmitFailed {
        session: u32,
        reason: String,
    },
    Tick,
}

/// @cc [owner:fontanierh,label:correctness] session-commands-keep-published
/// Session commands MUST be limited to queueing, stopping and talking to a session's own worker,
/// lease registration (worker and custody monitor), cancelling a unit's job on its worker, refusing a unit and handing settled
/// unit records to the caller. No
/// command MAY delete, replace or unpublish a published result. See tests/session_lifecycle.rs
/// (`session_commands_never_delete_or_republish`, `a_unit_after_close_or_twice_is_refused`).
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum SessionCommand {
    /// Queue a new guarded session (one admission).
    Submit { session: u32 },
    /// Add the session's pinned worker to `unit`'s write lease before it may write for it.
    Register {
        session: u32,
        unit: UnitId,
        worker: ProcessIdentity,
    },
    /// @cc [owner:fontanierh,label:safety] session-custodian-registered-before-run
    /// In a session holding checkout custody, a unit's `Run` MUST additionally wait for its
    /// session's custody monitor identity, reported once by the guard after the pinned worker, to
    /// be durably registered for this unit (`MonitorRegistered { ok: true }`). A missing identity
    /// MUST leave the unit without a `Run` until its own limits end it; a failed registration MUST
    /// end it without a `Run` and stop the session; a second, different identity, or one reported
    /// before the worker or without custody, MUST be a guard fault. Monitor exit alone is never
    /// cleanup evidence. See tests/session_lifecycle.rs
    /// (`a_custodian_session_runs_only_after_its_monitor_is_registered`,
    /// `a_missing_changed_or_unregistered_monitor_never_runs_the_unit`) and tests/guard_adapter.rs
    /// (`the_custody_monitor_is_durably_registered_before_the_first_run`,
    /// `a_missing_changed_or_unregistered_monitor_prevents_the_run`).
    ///
    /// Persist the session's cleanup correlation, then add its custody monitor to `unit`'s write
    /// lease, so the lease stays live while that guard's cleanup is unconfirmed.
    RegisterMonitor {
        session: u32,
        unit: UnitId,
        monitor: ProcessIdentity,
    },
    /// Send `unit`'s job (`run`) on the session.
    Run { session: u32, unit: UnitId },
    /// Ask the session's worker to cancel `unit`'s running job (`cancel`); the session stays up.
    Cancel { session: u32, unit: UnitId },
    /// Ask an idle, healthy worker to exit (`shutdown`).
    Shutdown { session: u32 },
    /// Ask the guard to stop or withdraw the session. Never certifies cleanup.
    Stop { session: u32 },
    /// `unit` has its final outcome and every attempt of it is released or held.
    Settled { unit: UnitId },
    /// `unit` was not accepted. Nothing was queued or started for it; [`UnitRecord::refused`]
    /// is its record.
    Refused { unit: UnitId, reason: Refusal },
}

/// @cc [owner:fontanierh,label:safety] session-refuses-units-it-cannot-serve
/// A unit MUST be refused at submission, with nothing queued or started, when the session is
/// closed, its id was already submitted, or a session could never serve it within its limits:
/// with quiescence evidence its cleanup limit MUST be at least the quiescence bound plus the
/// session's cleanup limit (so an unanswered cancel settles by the receipt before its own cleanup
/// limit), and its worst case in a session (job limit, plus the quiescence bound and the session's
/// cleanup limit when sessions are reused) MUST fit a session's lifetime. See
/// tests/session_lifecycle.rs (`a_unit_after_close_or_twice_is_refused`,
/// `a_unit_a_session_could_never_serve_is_refused_at_submission`).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Refusal {
    /// Submitted after close.
    Closed,
    /// A unit with this id was already submitted.
    DuplicateUnit,
    /// Its cleanup limit is shorter than the quiescence bound plus the session's cleanup limit.
    CleanupBelowQuiescence,
    /// Its worst case in a session exceeds the session lifetime.
    NeverFits,
    /// Its session key (worker, version, admission profile or custody) differs from the session's.
    IncompatibleKey,
    /// Another unit of the session uses its job id.
    JobIdInUse,
}

impl Refusal {
    pub fn reason(self) -> &'static str {
        match self {
            Self::Closed => "refused: the session was already closed",
            Self::DuplicateUnit => "refused: a unit with this id was already submitted",
            Self::CleanupBelowQuiescence => {
                "refused: the unit's cleanup limit is shorter than the quiescence bound plus the \
                 session's cleanup limit"
            }
            Self::NeverFits => "refused: the unit's worst case never fits a session's lifetime",
            Self::IncompatibleKey => {
                "refused: the unit's worker, worker version, admission profile or custody set \
                 differs from the session's"
            }
            Self::JobIdInUse => "refused: another unit of this session uses the same job id",
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct UnitAttemptRecord {
    pub attempt: u32,
    pub session: u32,
    /// The session's custody, once its receipt (or settlement limit) decided it.
    pub custody: Custody,
    /// The time of the quiescence evidence that settled this attempt while its session lived on.
    pub quiescent: Option<f64>,
}

impl UnitAttemptRecord {
    fn settled(&self) -> bool {
        self.custody != Custody::Pending || self.quiescent.is_some()
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct UnitRecord {
    pub unit: UnitId,
    pub outcome: Outcome,
    pub attempts: Vec<UnitAttemptRecord>,
    /// The worker's reported outputs, for downstream validation and publication.
    pub outputs: Option<JobOutputs>,
    /// Why the lifecycle gave up when no failure kind describes it (for example a launch error).
    pub abort: Option<String>,
    /// Why the unit was refused at submission; nothing was queued or started for it.
    pub refused: Option<Refusal>,
}

impl UnitRecord {
    /// The record of a unit refused at submission, so the caller never waits for it.
    pub fn refused(unit: UnitId, reason: Refusal) -> Self {
        Self {
            unit,
            outcome: Outcome {
                end: End::Failed(Stop::Cancelled),
                attempts: 0,
                cleanup: CleanupState::NotNeeded,
            },
            attempts: vec![],
            outputs: None,
            abort: Some(reason.reason().into()),
            refused: Some(reason),
        }
    }
}

#[derive(Clone, Debug)]
struct SessionSlot {
    record: AttemptRecord,
    ready: bool,
    shutdown_sent: bool,
    stop_sent: bool,
    exited: bool,
    finished: bool,
    settle_by: Option<MonoTime>,
    /// The unit assigned to this session, running or awaiting its settlement.
    active: Option<usize>,
    /// Some unit has been assigned to this session.
    used: bool,
    /// When the session was admitted: the start of its lifetime.
    admitted_at: Option<MonoTime>,
    /// When an idle, open session with nothing queued shuts down.
    idle_by: Option<MonoTime>,
    /// The queue limit this session was submitted with: the latest overall deadline among the
    /// units then waiting, or `None` to wait until admitted.
    queue_until: Option<MonoTime>,
    /// The guard's custody monitor, once reported (custodian sessions only).
    monitor: Option<ProcessIdentity>,
    /// A malformed, duplicate or out-of-order frame, a lost response stream or a guard fault:
    /// the session never runs, takes or settles another unit on evidence again.
    poisoned: bool,
}

impl SessionSlot {
    fn new(session: u32) -> Self {
        Self {
            record: AttemptRecord {
                attempt: session,
                admitted: false,
                worker: None,
                custody: Custody::Pending,
            },
            ready: false,
            shutdown_sent: false,
            stop_sent: false,
            exited: false,
            finished: false,
            poisoned: false,
            settle_by: None,
            active: None,
            used: false,
            admitted_at: None,
            idle_by: None,
            queue_until: None,
            monitor: None,
        }
    }

    fn ending(&self) -> bool {
        self.stop_sent || self.shutdown_sent || self.finished
    }

    fn stop(&mut self, out: &mut Vec<SessionCommand>) {
        // Never interrupt the guard's own unwinding once the worker has exited.
        if !self.stop_sent && !self.exited && !self.finished {
            self.stop_sent = true;
            out.push(SessionCommand::Stop {
                session: self.record.attempt,
            });
        }
    }

    fn shutdown(&mut self, out: &mut Vec<SessionCommand>) {
        if !self.shutdown_sent {
            self.shutdown_sent = true;
            out.push(SessionCommand::Shutdown {
                session: self.record.attempt,
            });
        }
    }
}

#[derive(Clone, Debug)]
struct UnitSlot {
    plan: UnitPlan,
    policy: JobPolicy,
    /// Absolute end of the unit's optional overall deadline; `None` if absent or never reached.
    overall_deadline: Option<MonoTime>,
    attempts: Vec<UnitAttemptRecord>,
    /// The session this unit is assigned to, from assignment until it is requeued for a retry.
    session: Option<u32>,
    registered: bool,
    /// The session's custody monitor is registered for this attempt (custodian sessions).
    monitor_registered: bool,
    job_sent: bool,
    terminal_seen: bool,
    cancel_sent: bool,
    /// While its session lives on: the latest time for this unit's quiescence evidence.
    quiet_by: Option<MonoTime>,
    outcome: Option<Outcome>,
    outputs: Option<JobOutputs>,
    abort: Option<String>,
    /// The record handed to the caller with [`SessionCommand::Settled`]; it never changes.
    published: Option<UnitRecord>,
}

impl UnitSlot {
    fn waiting(&self) -> bool {
        self.session.is_none()
            && matches!(
                self.policy.phase(),
                Phase::Queued | Phase::AwaitingReadmission { .. }
            )
    }

    fn settled(&self) -> bool {
        self.outcome.is_some() && self.attempts.iter().all(UnitAttemptRecord::settled)
    }

    fn current(&self) -> Option<UnitRecord> {
        self.published.clone().or_else(|| self.record())
    }

    fn record(&self) -> Option<UnitRecord> {
        Some(UnitRecord {
            unit: self.plan.id.clone(),
            outcome: self.outcome.clone()?,
            attempts: self.attempts.clone(),
            outputs: self.outputs.clone(),
            abort: self.abort.clone(),
            refused: None,
        })
    }
}

/// @cc [owner:fontanierh,label:safety] session-held-is-sticky
/// Once any session's custody is held (an unconfirmed receipt, a missed settlement limit or a
/// unit's unconfirmed cleanup), the lifecycle MUST start no further session and every waiting
/// unit MUST give up. A later confirmed receipt MUST NOT reopen sessions or change a unit record
/// already handed out with `Settled`: a late confirmed receipt is recorded in the held record;
/// the session record stays Held. A confirmed receipt delivered at or past the settlement limit,
/// or past its unit's cleanup limit or overall deadline in any phase, is such a late receipt
/// even when no Tick came first: that cleanup stays unconfirmed and the session held. Recovery is a fresh lifecycle started by the caller. See
/// tests/session_lifecycle.rs (`a_held_session_starts_no_further_session`,
/// `a_late_confirmed_receipt_never_reopens_a_held_lifecycle_or_changes_a_published_record`,
/// `a_receipt_at_or_past_its_limit_before_any_tick_leaves_the_cleanup_unknown`).
#[derive(Clone, Debug)]
pub struct SessionLifecycle {
    config: SessionConfig,
    sessions: Vec<SessionSlot>,
    units: Vec<UnitSlot>,
    closed: bool,
    /// Why the first held session was held: the sticky gate against new sessions.
    held: Option<String>,
    /// The overall deadlines of units that gave up while waiting during the current input: an
    /// unneeded session ended by that same input never settles later than them.
    ending_cap: Option<MonoTime>,
}

fn reached(at: Option<MonoTime>, now: MonoTime) -> bool {
    at.is_some_and(|at| now >= at)
}

/// How a unit's final decision ends its session when nothing else needs it.
enum Ending {
    Shutdown,
    Stop,
    Neither,
}

impl SessionLifecycle {
    pub fn new(config: SessionConfig) -> Self {
        Self {
            config,
            sessions: vec![],
            units: vec![],
            closed: false,
            held: None,
            ending_cap: None,
        }
    }

    /// Every session (guarded attempt) so far, in order.
    pub fn sessions(&self) -> Vec<AttemptRecord> {
        self.sessions.iter().map(|s| s.record.clone()).collect()
    }

    pub fn unit_policy(&self, unit: &str) -> Option<&JobPolicy> {
        self.units
            .iter()
            .find(|u| u.plan.id == unit)
            .map(|u| &u.policy)
    }

    /// `unit`'s record once its outcome is known; after `Settled`, exactly the record handed out.
    pub fn unit(&self, unit: &str) -> Option<UnitRecord> {
        self.units
            .iter()
            .find(|u| u.plan.id == unit)
            .and_then(UnitSlot::current)
    }

    /// The number of `unit`'s latest attempt (1 for its first), once it was assigned a session.
    pub fn unit_attempt(&self, unit: &str) -> Option<u32> {
        self.units
            .iter()
            .find(|u| u.plan.id == unit)
            .and_then(|u| u.attempts.last())
            .map(|a| a.attempt)
    }

    /// Every accepted unit's record so far, in submission order.
    pub fn units(&self) -> Vec<UnitRecord> {
        self.units.iter().filter_map(UnitSlot::current).collect()
    }

    /// The queue limit `session` was submitted with ([`SessionLifecycle::queue_deadline`] then).
    pub fn session_queue_deadline(&self, session: u32) -> Option<MonoTime> {
        self.session_index(session)
            .and_then(|s| self.sessions[s].queue_until)
    }

    /// Every unit has its final outcome and every attempt of it and every session is released
    /// or held.
    pub fn settled(&self) -> bool {
        self.units.iter().all(UnitSlot::settled)
            && self
                .sessions
                .iter()
                .all(|s| s.record.custody != Custody::Pending)
    }

    /// Closed, and settled.
    pub fn done(&self) -> bool {
        self.closed && self.settled()
    }

    /// The next instant a [`SessionInput::Tick`] can change anything.
    pub fn next_deadline(&self) -> Option<MonoTime> {
        self.sessions
            .iter()
            .filter(|s| s.record.custody == Custody::Pending)
            .filter_map(|s| s.settle_by)
            .chain(self.units.iter().filter_map(|u| u.policy.next_deadline()))
            .chain(
                self.live()
                    .filter(|&s| !self.sessions[s].ending())
                    .and_then(|s| self.sessions[s].active)
                    .and_then(|index| self.units[index].quiet_by),
            )
            .chain(
                self.live()
                    .filter(|&s| !self.sessions[s].ending())
                    .and_then(|s| self.sessions[s].idle_by),
            )
            .min()
    }

    /// The latest instant a waiting unit can still start: a session's queue limit.
    /// `None` when some waiting unit has no overall deadline.
    pub fn queue_deadline(&self) -> Option<MonoTime> {
        let mut latest = None;
        for unit in self.units.iter().filter(|u| u.waiting()) {
            match unit.policy.next_deadline() {
                None => return None,
                Some(at) => latest = Some(latest.map_or(at, |l: MonoTime| l.max(at))),
            }
        }
        latest
    }

    fn live(&self) -> Option<usize> {
        self.sessions
            .last()
            .filter(|s| !s.finished)
            .map(|_| self.sessions.len() - 1)
    }

    fn session_index(&self, session: u32) -> Option<usize> {
        self.sessions
            .iter()
            .position(|s| s.record.attempt == session)
    }

    fn unit_index(&self, unit: &str) -> Option<usize> {
        self.units.iter().position(|u| u.plan.id == unit)
    }

    /// @cc [owner:fontanierh,label:correctness] session-retry-once
    /// Only the guard's exit observation for a session's pinned worker, with no stop or shutdown
    /// requested and no guard or deadline stop, MAY become crash evidence, and only for the unit
    /// assigned to that session; worker claims, pipe loss and foreign identities MUST NOT. A
    /// unit's retry MUST wait for its policy's `RequestAdmission`, which follows the confirmed
    /// cleanup receipt of the session it ran on, and MUST start only in a later session after
    /// that session's own admission. See tests/session_lifecycle.rs
    /// (`a_crash_retry_joins_a_later_session_only_after_confirmed_cleanup`,
    /// `foreign_identities_and_pipe_loss_are_never_crash_evidence_for_a_unit`).
    pub fn on(
        &mut self,
        now: MonoTime,
        input: SessionInput,
    ) -> Result<Vec<SessionCommand>, LifecycleError> {
        let mut out = vec![];
        match input {
            SessionInput::Submit(plan) => {
                if let Some(reason) = self.refusal(&plan) {
                    out.push(SessionCommand::Refused {
                        unit: plan.id,
                        reason,
                    });
                    return Ok(out);
                }
                self.units.push(UnitSlot {
                    policy: JobPolicy::new(now, plan.limits),
                    overall_deadline: plan.limits.overall.and_then(|span| now.checked_add(span)),
                    plan,
                    attempts: vec![],
                    session: None,
                    registered: false,
                    monitor_registered: false,
                    job_sent: false,
                    terminal_seen: false,
                    cancel_sent: false,
                    quiet_by: None,
                    outcome: None,
                    outputs: None,
                    abort: None,
                    published: None,
                });
            }
            SessionInput::Close => self.closed = true,
            SessionInput::CancelAll => {
                self.closed = true;
                for index in 0..self.units.len() {
                    self.decide(now, index, PolicyEvent::CancelRequested, &mut out)?;
                }
            }
            SessionInput::CancelUnit(unit) => {
                if let Some(index) = self.unit_index(&unit) {
                    self.decide(now, index, PolicyEvent::CancelRequested, &mut out)?;
                }
            }
            SessionInput::Tick => {
                for index in 0..self.units.len() {
                    self.decide(now, index, PolicyEvent::Tick, &mut out)?;
                }
            }
            SessionInput::SubmitFailed { session, reason } => {
                let Some(s) = self.session_index(session) else {
                    return Ok(out);
                };
                // A submit error means no admission owner was started
                // (launcher-submit-error-means-nothing-started), so nothing is held.
                let live = self.live() == Some(s);
                let slot = &mut self.sessions[s];
                slot.finished = true;
                slot.record.custody = Custody::Released;
                if live {
                    self.abort_waiting(now, &format!("launch failed: {reason}"), &mut out)?;
                }
            }
            SessionInput::Registered { session, unit, ok } => {
                let failure = (!ok)
                    .then(|| "worker identity could not be added to the write lease".to_string());
                self.registered(now, session, &unit, failure, &mut out)?;
            }
            SessionInput::PrepareFailed {
                session,
                unit,
                reason,
            } => {
                let failure = format!("the attempt's job request could not be prepared: {reason}");
                self.registered(now, session, &unit, Some(failure), &mut out)?;
            }
            SessionInput::MonitorRegistered { session, unit, ok } => {
                let (Some(s), Some(index)) = (self.session_index(session), self.unit_index(&unit))
                else {
                    return Ok(out);
                };
                if self.live() == Some(s) && self.units[index].session == Some(session) {
                    if ok {
                        self.units[index].monitor_registered = true;
                        self.run_if_ready(now, s, &mut out)?;
                    } else {
                        self.units[index].abort.get_or_insert(
                            "the guard's custody monitor could not be added to the write lease"
                                .into(),
                        );
                        self.decide(now, index, PolicyEvent::CancelRequested, &mut out)?;
                    }
                }
            }
            SessionInput::Worker { session, event } => {
                if let Some(s) = self.session_index(session) {
                    // A frame read after the session's receipt is dropped. By then the guard has
                    // reaped the worker and its unit's policy is done or waiting for a later
                    // session, so the frame could change nothing for this session (as in C5b,
                    // where such a frame only reached a done policy); dropping it keeps it from
                    // ever reaching a unit that has moved on.
                    if self.live() == Some(s) {
                        self.worker(now, s, event, &mut out)?;
                    }
                }
            }
            SessionInput::Launch(AttemptEvent { attempt, event }) => {
                self.launch(now, attempt, event, &mut out)?
            }
            SessionInput::Quiescent {
                session,
                sample_time,
            } => self.quiescent(now, session, sample_time, &mut out)?,
        }
        let pumped = self.pump(now, &mut out);
        self.ending_cap = None;
        pumped?;
        if self.settle(now, &mut out) {
            // A session held just now: the held gate ends the waiting units in this same input,
            // so a missing receipt can never leave them waiting with no deadline to wake on.
            self.pump(now, &mut out)?;
        }
        for unit in &mut self.units {
            if unit.published.is_none() && unit.settled() {
                unit.published = unit.record();
                out.push(SessionCommand::Settled {
                    unit: unit.plan.id.clone(),
                });
            }
        }
        Ok(out)
    }

    /// `unit`'s registration on `session` succeeded, or failed with `failure`: a unit whose
    /// registration or attempt preparation failed ends without a `Run`.
    fn registered(
        &mut self,
        now: MonoTime,
        session: u32,
        unit: &str,
        failure: Option<String>,
        out: &mut Vec<SessionCommand>,
    ) -> Result<(), LifecycleError> {
        let (Some(s), Some(index)) = (self.session_index(session), self.unit_index(unit)) else {
            return Ok(());
        };
        if self.live() != Some(s) || self.units[index].session != Some(session) {
            return Ok(());
        }
        match failure {
            None => {
                self.units[index].registered = true;
                self.run_if_ready(now, s, out)
            }
            Some(failure) => {
                self.units[index].abort.get_or_insert(failure);
                self.decide(now, index, PolicyEvent::CancelRequested, out)
            }
        }
    }

    /// Every unit waiting for the live session gives up with `reason`.
    fn abort_waiting(
        &mut self,
        now: MonoTime,
        reason: &str,
        out: &mut Vec<SessionCommand>,
    ) -> Result<(), LifecycleError> {
        for index in 0..self.units.len() {
            if self.units[index].waiting() {
                self.units[index].abort.get_or_insert(reason.into());
                self.decide(now, index, PolicyEvent::CancelRequested, out)?;
            }
        }
        Ok(())
    }

    /// Assign waiting units to the live session, end a session nothing needs, and queue a
    /// session for waiting units.
    fn pump(&mut self, now: MonoTime, out: &mut Vec<SessionCommand>) -> Result<(), LifecycleError> {
        if self.held.is_some() {
            // The held gate (session-held-is-sticky): even while the held session is still
            // unwinding, no waiting unit may wait for another session.
            self.abort_waiting(
                now,
                "a previous session's cleanup is unconfirmed, so no new session may start",
                out,
            )?;
        }
        if let Some(s) = self.live() {
            self.pump_live(now, s, out)?;
            return Ok(());
        }
        if !self.units.iter().any(UnitSlot::waiting) {
            return Ok(());
        }
        match self.sessions.last().map(|s| s.record.custody.clone()) {
            // The previous session's receipt is still due: no second admission meanwhile.
            Some(Custody::Pending) => Ok(()),
            _ => {
                let session = self.sessions.len() as u32 + 1;
                let mut slot = SessionSlot::new(session);
                slot.queue_until = self.queue_deadline();
                self.sessions.push(slot);
                out.push(SessionCommand::Submit { session });
                Ok(())
            }
        }
    }

    /// Whether a later unit may join session `s`: one per session unless quiescence evidence is
    /// delivered, and then only if its job and cleanup limits fit the session's remaining
    /// lifetime (an unused session takes any unit, as its lifetime starts with it).
    fn may_take(&self, s: usize, index: usize, now: MonoTime) -> bool {
        let slot = &self.sessions[s];
        if slot.poisoned {
            return false;
        }
        if !slot.used {
            return true; // refused at submission if it could not fit a fresh session
        }
        if self.config.quiescence.is_none() {
            return false;
        }
        let end = slot
            .admitted_at
            .and_then(|at| at.checked_add(self.config.lifetime));
        let need = self
            .worst_case(&self.units[index].plan.limits)
            .and_then(|span| now.checked_add(span));
        matches!((need, end), (Some(need), Some(end)) if need <= end)
    }

    /// How long a unit can keep its session: its job limit, and when sessions are reused also the
    /// quiescence bound and the session's own cleanup limit (an unanswered cancel's path).
    fn worst_case(&self, limits: &Limits) -> Option<Duration> {
        match self.config.quiescence {
            None => Some(limits.job),
            Some(bound) => limits
                .job
                .checked_add(bound)?
                .checked_add(self.config.cleanup),
        }
    }

    /// Why `plan` can never be served here, if it cannot (session-refuses-units-it-cannot-serve).
    fn refusal(&self, plan: &UnitPlan) -> Option<Refusal> {
        if self.closed {
            return Some(Refusal::Closed);
        }
        if self.unit_index(&plan.id).is_some() {
            return Some(Refusal::DuplicateUnit);
        }
        if let Some(bound) = self.config.quiescence {
            if bound
                .checked_add(self.config.cleanup)
                .is_none_or(|need| plan.limits.cleanup < need)
            {
                return Some(Refusal::CleanupBelowQuiescence);
            }
        }
        if self
            .worst_case(&plan.limits)
            .is_none_or(|need| need > self.config.lifetime)
        {
            return Some(Refusal::NeverFits);
        }
        None
    }

    /// Whether session `s` stays up after its active unit ends: quiescence evidence is
    /// delivered, the worker is healthy and idle-capable, and another unit is waiting or may
    /// still be submitted.
    fn reusable(&self, s: usize) -> bool {
        let slot = &self.sessions[s];
        self.config.quiescence.is_some()
            && slot.ready
            && !slot.poisoned
            && !slot.exited
            && !slot.ending()
            && (!self.closed || self.units.iter().any(UnitSlot::waiting))
    }

    /// Start waiting for unit `index`'s quiescence evidence on its live session, never past the
    /// unit's overall deadline, which bounds its cleanup too, nor past its policy's own cleanup
    /// limit, even when the window restarts at a cancelled job's terminal reply
    /// (session-unit-time-limits).
    fn await_quiet(&mut self, now: MonoTime, index: usize) {
        let bound = self.config.quiescence.unwrap_or_default();
        let unit = &mut self.units[index];
        unit.quiet_by = [
            now.checked_add(bound),
            unit.overall_deadline,
            unit.policy.next_deadline(),
        ]
        .into_iter()
        .flatten()
        .min();
    }

    /// End live session `s`: shut an idle healthy worker down, otherwise stop the session. Its
    /// settlement is bounded by the cleanup limit and `cap` (session-unit-time-limits).
    fn end(
        &mut self,
        now: MonoTime,
        s: usize,
        cap: Option<MonoTime>,
        out: &mut Vec<SessionCommand>,
    ) {
        let active_running = self.sessions[s]
            .active
            .is_some_and(|index| self.units[index].quiet_by.is_none());
        let slot = &mut self.sessions[s];
        if slot.record.admitted && slot.ready && !slot.exited && !active_running {
            slot.shutdown(out);
        } else {
            slot.stop(out);
        }
        if slot.settle_by.is_none() {
            slot.settle_by = [now.checked_add(self.config.cleanup), cap]
                .into_iter()
                .flatten()
                .min();
        }
    }

    /// Assign, keep or end the live session `s`.
    fn pump_live(
        &mut self,
        now: MonoTime,
        s: usize,
        out: &mut Vec<SessionCommand>,
    ) -> Result<(), LifecycleError> {
        // No quiescence evidence in time: the session stops, and the unit settles only by its
        // cleanup receipt (session-reuse-after-quiescence).
        if let Some(index) = self.sessions[s].active {
            if reached(self.units[index].quiet_by, now) && !self.sessions[s].ending() {
                self.units[index].quiet_by = None;
                let cap = self.units[index].overall_deadline;
                self.sessions[s].stop(out);
                let slot = &mut self.sessions[s];
                if slot.settle_by.is_none() {
                    slot.settle_by = [now.checked_add(self.config.cleanup), cap]
                        .into_iter()
                        .flatten()
                        .min();
                }
            }
        }
        loop {
            let slot = &self.sessions[s];
            if !slot.record.admitted || slot.ending() || slot.active.is_some() {
                break;
            }
            let Some(index) = self.units.iter().position(UnitSlot::waiting) else {
                break;
            };
            if !self.may_take(s, index, now) {
                break;
            }
            self.sessions[s].idle_by = None;
            self.assign(now, s, index, out)?;
        }
        if self.sessions[s].ending() {
            return Ok(());
        }
        let head = self.units.iter().position(UnitSlot::waiting);
        match self.sessions[s].active {
            Some(index) => {
                // A unit runs, or awaits its quiescence evidence. Closed with nothing waiting,
                // the session ends at once; the receipt then settles that unit.
                if self.units[index].quiet_by.is_some() && self.closed && head.is_none() {
                    let cap = self.units[index].overall_deadline;
                    self.end(now, s, cap, out);
                }
            }
            None => {
                if head.is_some_and(|index| self.may_take(s, index, now)) {
                    return Ok(()); // waiting for admission or hello
                }
                let slot = &mut self.sessions[s];
                let idle = head.is_none()
                    && !self.closed
                    && slot.record.admitted
                    && slot.ready
                    && (self.config.quiescence.is_some() || !slot.used);
                if idle {
                    let idle_by = *slot
                        .idle_by
                        .get_or_insert(now.checked_add(self.config.idle).unwrap_or(now));
                    if !reached(Some(idle_by), now) {
                        return Ok(());
                    }
                }
                // Nothing needs this session: withdraw a queued request, or end an idle worker.
                // Bounded by the units that gave up on it during this same input, never by an
                // earlier unit's deadline (session-unit-time-limits).
                let cap = if slot.used { None } else { self.ending_cap };
                self.end(now, s, cap, out);
            }
        }
        Ok(())
    }

    /// @cc [owner:fontanierh,label:safety] session-reuse-after-quiescence
    /// A session MUST send a later unit's `Run` only after the previous unit's terminal reply and
    /// quiescence evidence for that session taken after it, and only when quiescence evidence
    /// is configured; otherwise each session serves one unit. Without evidence within the bound
    /// the session MUST stop, and the unit then settles only by the session's cleanup receipt. A
    /// running unit's cancel or job limit MUST cancel only that job when the session stays up for
    /// others, and MUST NOT release anything. A malformed, lost or faulted stream poisons the
    /// session: it never runs, takes or settles another unit on evidence. Evidence rests on two
    /// things: the job sandbox denying fork and spawn (an assumption tied to that profile, see
    /// platform/studio/tests/test_build_v2_job_fork.py; a session refuses any key that does not
    /// declare it) and the driver accepting only fresh, exact tree samples taken after the latest
    /// terminal reply (quiescence-sample-evidence). Assumptions and gaps: a sample proves only what
    /// the guard's tree receipt discovered after excluding shared services, which is not a universal
    /// proof that no descendant escaped discovery; ordering a sample after the terminal reply uses
    /// wall clocks within a bounded skew, which is not causal ordering under a clock adjustment. A
    /// reused session MUST hold checkout custody, so every `Run` also waits for its guard's custody
    /// monitor to be durably registered (session-custodian-registered-before-run); `run_session`
    /// refuses reuse without custody. See tests/session_lifecycle.rs
    /// (`a_reused_session_runs_the_next_unit_only_after_quiescence_evidence`,
    /// `without_quiescence_evidence_the_session_stops_and_the_receipt_settles_the_unit`,
    /// `cancelling_a_running_unit_cancels_only_its_job_when_others_wait`,
    /// `every_session_serves_one_unit_without_quiescence_evidence`,
    /// `evidence_past_its_bound_before_any_tick_never_settles_the_unit_or_reuses_the_worker`,
    /// `a_broken_or_lost_protocol_poisons_the_session_in_every_phase`,
    /// `a_protocol_fault_on_an_idle_session_stops_it_with_a_bounded_settlement`).
    ///
    /// Quiescence evidence for `session`'s active unit, after its terminal reply: the unit's
    /// attempt is settled, its cleanup finished, and the session may take the next unit.
    fn quiescent(
        &mut self,
        now: MonoTime,
        session: u32,
        sample_time: f64,
        out: &mut Vec<SessionCommand>,
    ) -> Result<(), LifecycleError> {
        let Some(s) = self.session_index(session) else {
            return Ok(());
        };
        let slot = &self.sessions[s];
        if self.live() != Some(s) || slot.exited || slot.ending() || slot.poisoned {
            return Ok(());
        }
        let Some(index) = slot.active else {
            return Ok(());
        };
        let unit = &mut self.units[index];
        // Evidence at or past its bound is too late, even before a Tick: `pump_live` then stops
        // the session in this same input. The bound is checked against the delivery time `now`,
        // never against `sample_time`: the guard's wall clock and MonoTime are not comparable.
        if unit.quiet_by.is_none()
            || reached(unit.quiet_by, now)
            || !unit.terminal_seen
            || !sample_time.is_finite()
        {
            return Ok(());
        }
        unit.quiet_by = None;
        if let Some(last) = unit.attempts.last_mut() {
            last.quiescent = Some(sample_time);
        }
        if matches!(unit.policy.phase(), Phase::CleaningUp { .. }) {
            self.decide(now, index, PolicyEvent::CleanupFinished, out)?;
        }
        if self.sessions[s].active == Some(index) {
            self.sessions[s].active = None;
        }
        Ok(())
    }

    /// Record that session `s` is held: the sticky gate (session-held-is-sticky).
    fn hold(&mut self, s: usize, reason: &str) {
        self.held.get_or_insert(reason.into());
        let slot = &mut self.sessions[s];
        if slot.record.custody == Custody::Pending {
            slot.record.custody = Custody::Held(reason.into());
        }
        let session = slot.record.attempt;
        for unit in &mut self.units {
            for attempt in &mut unit.attempts {
                if attempt.session == session && attempt.custody == Custody::Pending {
                    attempt.custody = Custody::Held(reason.into());
                }
            }
        }
    }

    /// @cc [owner:fontanierh,label:correctness] session-unit-time-limits
    /// A unit's job limit MUST start at its own assignment to an admitted session, never at its
    /// submission, at its session's queueing or at another unit's admission; its overall deadline
    /// MUST count from its submission and bound its queue wait, run, cleanup and retry. An ending
    /// session's settlement MUST be bounded only by the deadlines of the units relying on it at
    /// that moment, never by an earlier unit's past deadline. See tests/session_lifecycle.rs
    /// (`a_later_units_job_limit_counts_from_its_own_assignment`,
    /// `a_later_units_capacity_wait_stays_outside_its_job_limit`,
    /// `units_that_expire_while_waiting_withdraw_the_request_within_their_deadline`,
    /// `an_expired_units_deadline_never_bounds_a_later_settlement`,
    /// `a_reusable_units_quiescence_wait_never_outlasts_its_overall_deadline`,
    /// `no_run_path_runs_a_unit_at_or_past_its_overall_deadline`,
    /// `a_refreshed_quiet_window_never_outlasts_the_units_cleanup_limit`,
    /// `a_fault_while_a_unit_awaits_evidence_still_bounds_the_settlement`).
    ///
    /// Give waiting unit `index` to admitted session `s`: this is the unit's own admission, so its
    /// job limit starts now.
    fn assign(
        &mut self,
        now: MonoTime,
        s: usize,
        index: usize,
        out: &mut Vec<SessionCommand>,
    ) -> Result<(), LifecycleError> {
        let session = self.sessions[s].record.attempt;
        let decision = self.units[index]
            .policy
            .decide(now, PolicyEvent::Admitted)
            .map_err(LifecycleError::Policy)?;
        match decision {
            Decision::Launch { attempt } => {
                let unit = &mut self.units[index];
                unit.session = Some(session);
                unit.registered = false;
                unit.monitor_registered = false;
                unit.job_sent = false;
                unit.terminal_seen = false;
                unit.cancel_sent = false;
                unit.quiet_by = None;
                unit.attempts.push(UnitAttemptRecord {
                    attempt,
                    session,
                    custody: Custody::Pending,
                    quiescent: None,
                });
                let slot = &mut self.sessions[s];
                slot.active = Some(index);
                slot.used = true;
                if let Some(worker) = slot.record.worker.clone() {
                    out.push(SessionCommand::Register {
                        session,
                        unit: self.units[index].plan.id.clone(),
                        worker,
                    });
                }
                if let Some(monitor) = slot.monitor.clone() {
                    out.push(SessionCommand::RegisterMonitor {
                        session,
                        unit: self.units[index].plan.id.clone(),
                        monitor,
                    });
                }
                Ok(())
            }
            other => self.apply(now, index, other, out),
        }
    }

    /// @cc [owner:fontanierh,label:safety] session-register-before-run
    /// A unit's `Run` MUST be sent only on its assigned session, after that session's pinned
    /// worker was durably registered for this unit (`Registered { ok: true }`) and said hello, in
    /// either order. A failed registration or attempt preparation MUST end the unit without a
    /// `Run` and stop the session. See tests/session_lifecycle.rs
    /// (`a_later_units_failed_registration_stops_its_run`,
    /// `a_failed_preparation_ends_the_unit_without_a_run`,
    /// `hello_before_registration_waits_for_the_registration`) and tests/guard_adapter.rs
    /// (`run_session_hands_each_settled_unit_off_without_waiting_for_its_receiver`).
    fn run_if_ready(
        &mut self,
        now: MonoTime,
        s: usize,
        out: &mut Vec<SessionCommand>,
    ) -> Result<(), LifecycleError> {
        let Some(index) = self.sessions[s].active else {
            return Ok(());
        };
        // Bring the unit's policy to `now` first: a deadline that passed since the last Tick
        // ends the unit here, and it never runs (session-unit-time-limits).
        self.decide(now, index, PolicyEvent::Tick, out)?;
        let slot = &self.sessions[s];
        if slot.active != Some(index) {
            return Ok(());
        }
        let unit = &mut self.units[index];
        if slot.ready
            && !slot.poisoned
            && unit.registered
            && (!self.config.custodian || unit.monitor_registered)
            && !unit.job_sent
            && matches!(unit.policy.phase(), Phase::Running { .. })
        {
            unit.job_sent = true;
            out.push(SessionCommand::Run {
                session: slot.record.attempt,
                unit: unit.plan.id.clone(),
            });
        }
        Ok(())
    }

    fn decide(
        &mut self,
        now: MonoTime,
        index: usize,
        event: PolicyEvent,
        out: &mut Vec<SessionCommand>,
    ) -> Result<(), LifecycleError> {
        let decision = self.units[index]
            .policy
            .decide(now, event)
            .map_err(LifecycleError::Policy)?;
        self.apply(now, index, decision, out)
    }

    fn apply(
        &mut self,
        now: MonoTime,
        index: usize,
        decision: Decision,
        out: &mut Vec<SessionCommand>,
    ) -> Result<(), LifecycleError> {
        let assigned = self.units[index]
            .session
            .and_then(|session| self.session_index(session));
        match decision {
            Decision::Wait | Decision::Launch { .. } => {}
            Decision::BeginCleanup { stop, .. } => {
                let Some(s) = assigned else {
                    return Err(LifecycleError::Invariant(
                        "cleanup for a unit with no session".into(),
                    ));
                };
                let reusable = self.live() == Some(s) && self.reusable(s);
                let unit = &self.units[index];
                if reusable && matches!(stop, Stop::WorkerReported(_)) && unit.terminal_seen {
                    // The worker reaped the job's child and is idle: wait for quiescence.
                    self.await_quiet(now, index);
                    return Ok(());
                }
                if reusable
                    && matches!(stop, Stop::Cancelled | Stop::JobLimit)
                    && unit.job_sent
                    && !unit.terminal_seen
                    && !unit.cancel_sent
                {
                    // Cancel this unit's job only; the session stays up for the others.
                    self.units[index].cancel_sent = true;
                    self.await_quiet(now, index);
                    out.push(SessionCommand::Cancel {
                        session: self.sessions[s].record.attempt,
                        unit: self.units[index].plan.id.clone(),
                    });
                    return Ok(());
                }
                let slot = &mut self.sessions[s];
                let graceful = matches!(stop, Stop::WorkerReported(_))
                    && slot.ready
                    && unit.terminal_seen
                    && !slot.exited;
                if graceful {
                    slot.shutdown(out);
                } else {
                    slot.stop(out);
                }
            }
            Decision::RequestAdmission { .. } => {
                let previous = self.units[index].attempts.last().map(|a| a.custody.clone());
                if previous != Some(Custody::Released) {
                    return Err(LifecycleError::Invariant(
                        "a retry needs the previous session's confirmed cleanup".into(),
                    ));
                }
                // Back in the queue for a later session; `pump` queues one.
                if let Some(s) = assigned {
                    self.sessions[s].active = None;
                }
                self.units[index].session = None;
            }
            Decision::Finish(outcome) => {
                let unconfirmed = matches!(outcome.cleanup, CleanupState::Unconfirmed(_));
                let completed = outcome.end == End::Completed;
                let deadline = self.units[index].overall_deadline;
                self.units[index].outcome = Some(outcome);
                let Some(s) = assigned else {
                    // Finished while waiting: if nothing else needs the session it waited for,
                    // `pump` ends it in this same input, and its settlement never outlasts this
                    // unit's deadline.
                    self.ending_cap = [self.ending_cap, deadline].into_iter().flatten().min();
                    return Ok(());
                };
                let unit = &self.units[index];
                if unit.attempts.last().is_some_and(|a| a.quiescent.is_some()) {
                    return Ok(()); // settled by quiescence: the session lives on
                }
                if completed && unit.terminal_seen && self.live() == Some(s) && self.reusable(s) {
                    self.await_quiet(now, index);
                    return Ok(());
                }
                let ending = {
                    let slot = &self.sessions[s];
                    if completed && slot.ready && !slot.exited {
                        Ending::Shutdown
                    } else if !completed {
                        Ending::Stop
                    } else {
                        Ending::Neither
                    }
                };
                let slot = &mut self.sessions[s];
                if !slot.finished {
                    match ending {
                        Ending::Shutdown => slot.shutdown(out),
                        Ending::Stop => slot.stop(out),
                        Ending::Neither => {}
                    }
                    if slot.settle_by.is_none() {
                        // Wait for the cleanup limit, but never past the overall deadline,
                        // which covers cleanup too (failure-policy-time-limits). An
                        // overflowing sum is never reached. Unsettled custody is then held.
                        slot.settle_by = [now.checked_add(self.config.cleanup), deadline]
                            .into_iter()
                            .flatten()
                            .min();
                    }
                }
                if unconfirmed {
                    self.hold(
                        s,
                        "the policy's cleanup limit or deadline passed without a confirmed receipt",
                    );
                }
            }
        }
        Ok(())
    }

    /// Stop live session `s` when no unit's policy governs its ending (its active unit awaits
    /// quiescence evidence, or none is active): it no longer waits for evidence, and its
    /// settlement is bounded by the cleanup limit and that unit's overall deadline, as in
    /// `pump_live`, so an ending session always has a wake-up (session-unit-time-limits).
    fn stop_ungoverned(&mut self, now: MonoTime, s: usize, out: &mut Vec<SessionCommand>) {
        let cap = self.sessions[s].active.and_then(|index| {
            let unit = &mut self.units[index];
            unit.quiet_by = None;
            unit.overall_deadline
        });
        let cleanup = now.checked_add(self.config.cleanup);
        let slot = &mut self.sessions[s];
        slot.stop(out);
        if slot.settle_by.is_none() {
            slot.settle_by = [cleanup, cap].into_iter().flatten().min();
        }
    }

    /// A malformed or inconsistent guard report for session `s`: never crash or cleanup evidence.
    fn fault(
        &mut self,
        now: MonoTime,
        s: usize,
        out: &mut Vec<SessionCommand>,
    ) -> Result<(), LifecycleError> {
        self.sessions[s].stop(out);
        self.sessions[s].poisoned = true;
        if self.live() != Some(s) {
            return Ok(());
        }
        match self.sessions[s].active {
            Some(index) => match self.units[index].policy.phase() {
                Phase::Running { .. } | Phase::CleaningUp { .. } => self.decide(
                    now,
                    index,
                    PolicyEvent::Observed(Observation::ProtocolViolation),
                    out,
                ),
                _ => {
                    self.stop_ungoverned(now, s, out);
                    Ok(())
                }
            },
            None if !self.sessions[s].record.admitted => {
                self.stop_ungoverned(now, s, out);
                self.abort_waiting(now, "the guard reported an inconsistent attempt", out)
            }
            None => {
                self.stop_ungoverned(now, s, out);
                Ok(())
            }
        }
    }

    fn launch(
        &mut self,
        now: MonoTime,
        session: u32,
        event: LaunchEvent,
        out: &mut Vec<SessionCommand>,
    ) -> Result<(), LifecycleError> {
        let Some(s) = self.session_index(session) else {
            return Ok(());
        };
        let current = self.sessions.len() == s + 1;
        if let LaunchEvent::Finished { cleanup, .. } = event {
            // Limits reached by the delivery time `now` apply before the receipt, as if a Tick
            // had come first: a receipt at or past the settlement limit, or past its unit's
            // cleanup limit or overall deadline (which covers cleanup) in any phase, leaves that
            // cleanup unknown (session-held-is-sticky).
            self.sessions[s].finished = true;
            let active = self.sessions[s].active.filter(|_| current);
            let cleaning = active.filter(|&index| {
                matches!(self.units[index].policy.phase(), Phase::CleaningUp { .. })
            });
            if let Some(index) = cleaning {
                self.decide(now, index, PolicyEvent::Tick, out)?;
            }
            let expired = active.is_some_and(|index| {
                let unit = &self.units[index];
                reached(unit.overall_deadline, now)
                    && unit.attempts.iter().any(|attempt| {
                        attempt.session == session
                            && attempt.custody == Custody::Pending
                            && attempt.quiescent.is_none()
                    })
            });
            let held = matches!(self.sessions[s].record.custody, Custody::Held(_));
            let late = held || expired || reached(self.sessions[s].settle_by, now);
            if late && self.sessions[s].record.custody == Custody::Pending {
                self.hold(s, "no confirmed cleanup receipt within the cleanup limit");
            }
            let custody = match (cleanup.clone(), &self.sessions[s].record.custody) {
                // A late confirmed receipt is recorded in the held record, which stays Held:
                // no reader of the session record can take it for a release.
                (CleanupReceipt::Confirmed, Custody::Held(reason)) if late => {
                    Custody::Held(format!(
                        "{reason}; a confirmed cleanup receipt arrived late, at {} ms",
                        now.elapsed().as_millis()
                    ))
                }
                (CleanupReceipt::Confirmed, _) => Custody::Released,
                (CleanupReceipt::Unconfirmed { reason }, _) => Custody::Held(reason),
            };
            let confirmed = cleanup == CleanupReceipt::Confirmed && !late;
            let slot = &mut self.sessions[s];
            slot.finished = true;
            // The session's own record shows the guard's latest receipt, as evidence. Unit
            // attempts and the gate against new sessions stay held (session-held-is-sticky).
            slot.record.custody = custody.clone();
            let (exited, admitted, active) = (slot.exited, slot.record.admitted, slot.active);
            let (stop_sent, queue_until) = (slot.stop_sent, slot.queue_until);
            for unit in &mut self.units {
                for attempt in &mut unit.attempts {
                    if attempt.session == session && attempt.custody == Custody::Pending {
                        attempt.custody = custody.clone();
                    }
                }
            }
            if let Custody::Held(reason) = custody {
                self.held.get_or_insert(reason);
            }
            if !current {
                return Ok(());
            }
            let Some(index) = active else {
                if !admitted && !exited && !stop_sent {
                    // Ended before admission without being asked to. A unit this session's
                    // queue limit covered gives up; a later or longer one waits for a fresh
                    // session, which `pump` queues once this one is released.
                    for index in 0..self.units.len() {
                        let unit = &self.units[index];
                        let covered = match (queue_until, unit.overall_deadline) {
                            (None, _) => true,
                            (Some(limit), Some(deadline)) => deadline <= limit,
                            (Some(_), None) => false,
                        };
                        if !unit.waiting() {
                            continue;
                        }
                        if covered {
                            self.units[index]
                                .abort
                                .get_or_insert("the admission owner ended before admission".into());
                            self.decide(now, index, PolicyEvent::CancelRequested, out)?;
                        } else if reached(unit.overall_deadline, now) {
                            // Already past its deadline: it ends now, never requeued.
                            self.decide(now, index, PolicyEvent::Tick, out)?;
                        }
                    }
                }
                return Ok(());
            };
            return match self.units[index].policy.phase().clone() {
                Phase::CleaningUp { .. } if confirmed => {
                    self.decide(now, index, PolicyEvent::CleanupFinished, out)
                }
                Phase::Running { .. } => {
                    // The guard finished without reporting the worker's exit.
                    self.decide(
                        now,
                        index,
                        PolicyEvent::Observed(Observation::ProtocolViolation),
                        out,
                    )?;
                    if confirmed {
                        self.decide(now, index, PolicyEvent::CleanupFinished, out)?;
                    } else if late {
                        // Its expired limits end the cleanup unconfirmed now.
                        self.decide(now, index, PolicyEvent::Tick, out)?;
                    }
                    Ok(())
                }
                _ => Ok(()),
            };
        }
        if self.live() != Some(s) {
            return Ok(());
        }
        match event {
            // A tree sample becomes evidence only through the driver's validation, as `Quiescent`.
            LaunchEvent::Queued | LaunchEvent::Finished { .. } | LaunchEvent::TreeSample(_) => {
                Ok(())
            }
            LaunchEvent::Admitted => {
                if self.sessions[s].record.admitted {
                    return self.fault(now, s, out);
                }
                self.sessions[s].record.admitted = true;
                self.sessions[s].admitted_at = Some(now);
                Ok(())
            }
            LaunchEvent::ChildStarted { worker } => {
                let (admitted, pinned) = {
                    let record = &self.sessions[s].record;
                    (record.admitted, record.worker.clone())
                };
                match pinned {
                    _ if !admitted => self.fault(now, s, out),
                    Some(pinned) if pinned == worker => Ok(()),
                    Some(_) => self.fault(now, s, out),
                    None => {
                        self.sessions[s].record.worker = Some(worker.clone());
                        if let Some(index) = self.sessions[s].active {
                            let unit = &self.units[index];
                            if unit.outcome.is_none() && !unit.registered {
                                out.push(SessionCommand::Register {
                                    session,
                                    unit: unit.plan.id.clone(),
                                    worker,
                                });
                            }
                        }
                        Ok(())
                    }
                }
            }
            LaunchEvent::ChildExited {
                worker, stopped_by, ..
            } => {
                let slot = &mut self.sessions[s];
                if slot.record.worker.as_ref() != Some(&worker) {
                    return self.fault(now, s, out);
                }
                slot.exited = true;
                let requested = slot.stop_sent || slot.shutdown_sent;
                let event = match stopped_by {
                    Some(StoppedBy::Guard) | Some(StoppedBy::Deadline) => {
                        Some(PolicyEvent::Observed(Observation::GuardStopped))
                    }
                    // Someone else asked the admission owner to stop: a cancellation, never a crash.
                    Some(StoppedBy::Cancel) if !requested => Some(PolicyEvent::CancelRequested),
                    Some(StoppedBy::Cancel) => None,
                    None if requested => None,
                    None => Some(PolicyEvent::Observed(Observation::UnexpectedExit)),
                };
                match (event, slot.active) {
                    (Some(event), Some(index)) => self.decide(now, index, event, out),
                    _ => Ok(()),
                }
            }
            LaunchEvent::Monitor { monitor, .. } => {
                let slot = &self.sessions[s];
                if !self.config.custodian || !slot.record.admitted || slot.record.worker.is_none() {
                    return self.fault(now, s, out);
                }
                match slot.monitor.clone() {
                    Some(pinned) if pinned == monitor => Ok(()),
                    Some(_) => self.fault(now, s, out),
                    None => {
                        self.sessions[s].monitor = Some(monitor.clone());
                        if let Some(index) = self.sessions[s].active {
                            let unit = &self.units[index];
                            if unit.outcome.is_none() && !unit.monitor_registered {
                                out.push(SessionCommand::RegisterMonitor {
                                    session,
                                    unit: unit.plan.id.clone(),
                                    monitor,
                                });
                            }
                        }
                        Ok(())
                    }
                }
            }
            LaunchEvent::Fault(_) => self.fault(now, s, out),
        }
    }

    fn worker(
        &mut self,
        now: MonoTime,
        s: usize,
        event: Result<WorkerEvent, WorkerFault>,
        out: &mut Vec<SessionCommand>,
    ) -> Result<(), LifecycleError> {
        let active = self.sessions[s].active;
        match event {
            Ok(WorkerEvent::Ready { .. }) => {
                self.sessions[s].ready = true;
                self.run_if_ready(now, s, out)
            }
            Ok(WorkerEvent::Started { .. }) | Ok(WorkerEvent::Stopped) => Ok(()),
            Ok(WorkerEvent::Finished(finished)) => {
                let Some(index) = active else {
                    return Ok(());
                };
                self.units[index].terminal_seen = true;
                match finished.result {
                    Ok(outputs) => {
                        self.decide(now, index, PolicyEvent::Completed, out)?;
                        let unit = &mut self.units[index];
                        if unit
                            .outcome
                            .as_ref()
                            .is_some_and(|o| o.end == End::Completed)
                        {
                            unit.outputs = Some(outputs);
                        }
                    }
                    Err(failure) => {
                        self.decide(now, index, PolicyEvent::WorkerFailed(failure.kind), out)?
                    }
                }
                let unit = &self.units[index];
                if unit.cancel_sent && unit.quiet_by.is_some() {
                    // The cancelled job's terminal reply: a fresh window for evidence after it.
                    self.await_quiet(now, index);
                }
                Ok(())
            }
            // A broken protocol poisons the session in every phase: it stops and never serves
            // another unit (build-v2-worker-session-order).
            Err(WorkerFault::Protocol(_)) => {
                self.sessions[s].poisoned = true;
                match active {
                    Some(index)
                        if matches!(
                            self.units[index].policy.phase(),
                            Phase::Running { .. } | Phase::CleaningUp { .. }
                        ) =>
                    {
                        self.decide(
                            now,
                            index,
                            PolicyEvent::Observed(Observation::ProtocolViolation),
                            out,
                        )?;
                        // A unit already cleaning up keeps its first stop reason; its policy's
                        // cleanup limit bounds the settlement.
                        self.units[index].quiet_by = None;
                        self.sessions[s].stop(out);
                        Ok(())
                    }
                    // A unit awaiting quiescence evidence, or none active.
                    _ => {
                        self.stop_ungoverned(now, s, out);
                        Ok(())
                    }
                }
            }
            // A lost response stream is not crash evidence, but no reply or hello can arrive any
            // more: the session never runs, takes or settles another unit on evidence. A session
            // with no running or cleaning-up unit stops now instead of waiting out its bound.
            Err(WorkerFault::Disconnected(_)) => {
                self.sessions[s].poisoned = true;
                let governed = active.is_some_and(|index| {
                    matches!(
                        self.units[index].policy.phase(),
                        Phase::Running { .. } | Phase::CleaningUp { .. }
                    )
                });
                if !governed {
                    self.stop_ungoverned(now, s, out);
                }
                Ok(())
            }
        }
    }

    /// Hold every session whose settlement limit passed; `true` if any was held now.
    fn settle(&mut self, now: MonoTime, out: &mut Vec<SessionCommand>) -> bool {
        let mut held = false;
        for s in 0..self.sessions.len() {
            let slot = &mut self.sessions[s];
            if slot.record.custody == Custody::Pending && reached(slot.settle_by, now) {
                slot.stop(out);
                self.hold(s, "no confirmed cleanup receipt within the cleanup limit");
                held = true;
            }
        }
        held
    }
}
