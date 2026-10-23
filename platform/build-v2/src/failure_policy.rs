//! C5a: pure failure, retry and deadline decisions for one job.
//!
//! A worker session (C1a) or scheduler feeds controller-side [`Event`]s with caller-supplied
//! monotonic times. This module reads no clock, never sleeps, launches or signals nothing, and
//! neither performs nor proves cleanup: [`Decision::BeginCleanup`] is a request. Real owned-process
//! cancellation and cleanup belong to C5b; capacity admission and guards belong to C7.
use crate::protocol::{FailureKind, WorkerFailure};
use std::time::Duration;

/// The first attempt plus at most one retry after a confirmed process crash.
pub const MAX_ATTEMPTS: u32 = 2;

/// A caller-supplied monotonic instant: elapsed time since an origin the caller chooses once
/// (for example a `std::time::Instant` captured by the session). It is never wall-clock time.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct MonoTime(Duration);

impl MonoTime {
    pub const fn from_elapsed(since_origin: Duration) -> Self {
        Self(since_origin)
    }

    pub const fn elapsed(self) -> Duration {
        self.0
    }

    /// `None` when the instant is unrepresentable; the policy treats that as never reached.
    pub fn checked_add(self, span: Duration) -> Option<Self> {
        self.0.checked_add(span).map(Self)
    }
}

/// @cc [owner:fontanierh,label:correctness] failure-policy-time-limits
/// Queue waiting MUST NOT spend the job limit; each admission MUST start a fresh job limit for
/// that attempt. The optional overall deadline MUST be measured from submission and cover queue,
/// execution, cleanup and any retry. Times MUST come from the caller's monotonic clock; overflowing
/// sums MUST mean "never reached" rather than panic or wrap. See tests/failure_policy.rs.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Limits {
    /// Runtime limit for one attempt, started by its admission.
    pub job: Duration,
    /// Time allowed for cleanup to be confirmed after it was requested.
    pub cleanup: Duration,
    /// An agent's explicit deadline from submission over the whole job, retries included.
    pub overall: Option<Duration>,
}

/// Facts observed by the controller side, never taken from a worker's own message.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Observation {
    /// The owned worker process exited while the controller had not asked it to stop and no
    /// guard had stopped it. This is the only crash evidence the policy accepts.
    UnexpectedExit,
    /// The memory/capacity guard stopped the process.
    GuardStopped,
    /// The controller rejected the session's frames, ordering or job identity.
    ProtocolViolation,
    /// The controller detected a dependency-rule violation (undeclared read or code).
    DependencyViolation,
}

/// The adapter interface: everything a session or scheduler may report for one job.
#[derive(Clone, Debug, PartialEq)]
pub enum Event {
    /// A capacity admission was granted for the next attempt.
    Admitted,
    /// The worker reported `completed`. Validation and publication happen downstream.
    Completed,
    /// The worker's own `failed` claim. Its kind is reported but never treated as an observation.
    WorkerFailed(FailureKind),
    Observed(Observation),
    CancelRequested,
    /// Cleanup of the owned process and unpublished scratch was confirmed.
    CleanupFinished,
    /// No new fact; lets the policy apply limits at `now`.
    Tick,
}

impl Event {
    pub fn worker_failed(failure: &WorkerFailure) -> Self {
        Self::WorkerFailed(failure.kind.clone())
    }

    fn name(&self) -> &'static str {
        match self {
            Self::Admitted => "admitted",
            Self::Completed => "completed",
            Self::WorkerFailed(_) => "worker_failed",
            Self::Observed(_) => "observed",
            Self::CancelRequested => "cancel_requested",
            Self::CleanupFinished => "cleanup_finished",
            Self::Tick => "tick",
        }
    }
}

/// Why an attempt stopped. `WorkerReported(Crash)` is a claim, distinct from an observed `Crash`.
#[derive(Clone, Debug, PartialEq)]
pub enum Stop {
    WorkerReported(FailureKind),
    Crash,
    Protocol,
    Dependency,
    Cancelled,
    JobLimit,
    OverallDeadline,
    GuardStop,
}

impl Stop {
    /// Reporting class only; retry eligibility is decided by [`JobPolicy`], not by this kind.
    pub fn kind(&self) -> FailureKind {
        match self {
            Self::WorkerReported(kind) => kind.clone(),
            Self::Crash => FailureKind::Crash,
            Self::Protocol => FailureKind::Protocol,
            Self::Dependency => FailureKind::Dependency,
            Self::Cancelled => FailureKind::Cancelled,
            Self::JobLimit | Self::OverallDeadline => FailureKind::Timeout,
            Self::GuardStop => FailureKind::GuardStop,
        }
    }
}

/// @cc [owner:fontanierh,label:correctness] failure-policy-keeps-published
/// A cleanup request MUST be limited to the attempt's owned process and unpublished job scratch.
/// No policy decision MAY request deleting, replacing or unpublishing already published results.
/// See tests/failure_policy.rs.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Discard {
    UnpublishedScratchOnly,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Expiry {
    CleanupLimit,
    OverallDeadline,
}

/// `Unconfirmed` means the owned process may still be alive: the caller must neither relaunch
/// nor treat its capacity as released until real cleanup (C5b/C7) confirms it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CleanupState {
    NotNeeded,
    Finished,
    Unconfirmed(Expiry),
}

#[derive(Clone, Debug, PartialEq)]
pub enum End {
    Completed,
    Failed(Stop),
}

#[derive(Clone, Debug, PartialEq)]
pub struct Outcome {
    pub end: End,
    /// Attempts launched (0 when the job never left the queue).
    pub attempts: u32,
    pub cleanup: CleanupState,
}

#[derive(Clone, Debug, PartialEq)]
pub enum Decision {
    Wait,
    /// Admission was granted: the caller may launch this attempt now.
    Launch {
        attempt: u32,
    },
    /// Stop the attempt and clean up; report [`Event::CleanupFinished`] when confirmed.
    BeginCleanup {
        stop: Stop,
        discard: Discard,
    },
    /// Retry is eligible, cleanup is confirmed: ask for a fresh admission. Not a launch permit.
    RequestAdmission {
        attempt: u32,
    },
    /// Terminal. A queued request or unused admission is withdrawn by the caller.
    Finish(Outcome),
}

#[derive(Clone, Debug, PartialEq)]
pub enum Phase {
    Queued,
    Running {
        attempt: u32,
        limit_at: Option<MonoTime>,
    },
    CleaningUp {
        attempt: u32,
        stop: Stop,
        retry_eligible: bool,
        limit_at: Option<MonoTime>,
    },
    AwaitingReadmission {
        attempt: u32,
    },
    Done(Outcome),
}

impl Phase {
    fn name(&self) -> &'static str {
        match self {
            Self::Queued => "queued",
            Self::Running { .. } => "running",
            Self::CleaningUp { .. } => "cleaning_up",
            Self::AwaitingReadmission { .. } => "awaiting_readmission",
            Self::Done(_) => "done",
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum PolicyError {
    ClockWentBackwards,
    UnexpectedEvent {
        phase: &'static str,
        event: &'static str,
    },
}

/// One job's failure, retry and deadline state. Rejected events leave it unchanged.
#[derive(Clone, Debug, PartialEq)]
pub struct JobPolicy {
    limits: Limits,
    overall_at: Option<MonoTime>,
    last: MonoTime,
    phase: Phase,
}

fn reached(at: Option<MonoTime>, now: MonoTime) -> bool {
    at.is_some_and(|at| now >= at)
}

fn earliest(a: Option<MonoTime>, b: Option<MonoTime>) -> Option<MonoTime> {
    match (a, b) {
        (Some(a), Some(b)) => Some(a.min(b)),
        (a, b) => a.or(b),
    }
}

fn finish(end: End, attempts: u32, cleanup: CleanupState) -> (Phase, Decision) {
    let outcome = Outcome {
        end,
        attempts,
        cleanup,
    };
    (Phase::Done(outcome.clone()), Decision::Finish(outcome))
}

impl JobPolicy {
    pub fn new(submitted: MonoTime, limits: Limits) -> Self {
        Self {
            limits,
            overall_at: limits.overall.and_then(|span| submitted.checked_add(span)),
            last: submitted,
            phase: Phase::Queued,
        }
    }

    pub fn phase(&self) -> &Phase {
        &self.phase
    }

    /// The next instant at which a [`Event::Tick`] can change the decision, if any.
    pub fn next_deadline(&self) -> Option<MonoTime> {
        match &self.phase {
            Phase::Queued | Phase::AwaitingReadmission { .. } => self.overall_at,
            Phase::Running { limit_at, .. } | Phase::CleaningUp { limit_at, .. } => {
                earliest(*limit_at, self.overall_at)
            }
            Phase::Done(_) => None,
        }
    }

    /// @cc [owner:fontanierh,label:correctness] failure-policy-retry-once
    /// Only a controller-observed unexpected exit on the first attempt MAY become retry-eligible.
    /// A retry MUST NOT launch until cleanup is confirmed within its limits and the overall
    /// deadline, and a new admission is then granted. Worker-claimed kinds, job, dependency and
    /// protocol errors, cancellation, timeouts, guard stops and cleanup timeouts MUST NOT retry;
    /// such a fact or cancellation arriving during crash cleanup MUST withdraw the pending retry.
    /// See tests/failure_policy.rs.
    pub fn decide(&mut self, now: MonoTime, event: Event) -> Result<Decision, PolicyError> {
        if now < self.last {
            return Err(PolicyError::ClockWentBackwards);
        }
        let (phase, decision) = self.step(now, &event)?;
        self.last = now;
        self.phase = phase;
        Ok(decision)
    }

    fn unexpected(&self, event: &Event) -> PolicyError {
        PolicyError::UnexpectedEvent {
            phase: self.phase.name(),
            event: event.name(),
        }
    }

    fn launch(&self, now: MonoTime, attempt: u32) -> (Phase, Decision) {
        let limit_at = now.checked_add(self.limits.job);
        (
            Phase::Running { attempt, limit_at },
            Decision::Launch { attempt },
        )
    }

    fn step(&self, now: MonoTime, event: &Event) -> Result<(Phase, Decision), PolicyError> {
        let overall = reached(self.overall_at, now);
        let keep = || Ok((self.phase.clone(), Decision::Wait));
        match &self.phase {
            Phase::Done(_) => keep(),
            Phase::Queued | Phase::AwaitingReadmission { .. } => {
                let (attempts, cleanup) = match self.phase {
                    Phase::AwaitingReadmission { attempt } => (attempt, CleanupState::Finished),
                    _ => (0, CleanupState::NotNeeded),
                };
                if !matches!(
                    event,
                    Event::Tick | Event::CancelRequested | Event::Admitted
                ) {
                    return Err(self.unexpected(event));
                }
                if overall {
                    return Ok(finish(
                        End::Failed(Stop::OverallDeadline),
                        attempts,
                        cleanup,
                    ));
                }
                match event {
                    Event::Admitted => Ok(self.launch(now, attempts.saturating_add(1))),
                    Event::CancelRequested => {
                        Ok(finish(End::Failed(Stop::Cancelled), attempts, cleanup))
                    }
                    _ => keep(),
                }
            }
            Phase::Running { attempt, limit_at } => {
                let attempt = *attempt;
                let stop = match event {
                    Event::Admitted | Event::CleanupFinished => return Err(self.unexpected(event)),
                    _ if overall => Stop::OverallDeadline,
                    _ if reached(*limit_at, now) => Stop::JobLimit,
                    Event::Tick => return keep(),
                    Event::Completed => {
                        return Ok(finish(End::Completed, attempt, CleanupState::NotNeeded));
                    }
                    Event::WorkerFailed(kind) => Stop::WorkerReported(kind.clone()),
                    Event::Observed(Observation::UnexpectedExit) => Stop::Crash,
                    Event::Observed(Observation::GuardStopped) => Stop::GuardStop,
                    Event::Observed(Observation::ProtocolViolation) => Stop::Protocol,
                    Event::Observed(Observation::DependencyViolation) => Stop::Dependency,
                    Event::CancelRequested => Stop::Cancelled,
                };
                let retry_eligible = stop == Stop::Crash && attempt < MAX_ATTEMPTS;
                Ok((
                    Phase::CleaningUp {
                        attempt,
                        stop: stop.clone(),
                        retry_eligible,
                        limit_at: now.checked_add(self.limits.cleanup),
                    },
                    Decision::BeginCleanup {
                        stop,
                        discard: Discard::UnpublishedScratchOnly,
                    },
                ))
            }
            Phase::CleaningUp {
                attempt,
                stop,
                retry_eligible,
                limit_at,
            } => {
                let late = reached(*limit_at, now);
                let failed = End::Failed(stop.clone());
                match event {
                    Event::Admitted => Err(self.unexpected(event)),
                    Event::CleanupFinished if *retry_eligible && !overall && !late => Ok((
                        Phase::AwaitingReadmission { attempt: *attempt },
                        Decision::RequestAdmission {
                            attempt: attempt.saturating_add(1),
                        },
                    )),
                    Event::CleanupFinished => Ok(finish(failed, *attempt, CleanupState::Finished)),
                    _ if overall => Ok(finish(
                        failed,
                        *attempt,
                        CleanupState::Unconfirmed(Expiry::OverallDeadline),
                    )),
                    _ if late => Ok(finish(
                        failed,
                        *attempt,
                        CleanupState::Unconfirmed(Expiry::CleanupLimit),
                    )),
                    // Cancellation or any non-crash failure fact withdraws a pending retry;
                    // the stop reason stays as first observed.
                    Event::CancelRequested
                    | Event::WorkerFailed(_)
                    | Event::Observed(
                        Observation::GuardStopped
                        | Observation::ProtocolViolation
                        | Observation::DependencyViolation,
                    ) => Ok((
                        Phase::CleaningUp {
                            attempt: *attempt,
                            stop: stop.clone(),
                            retry_eligible: false,
                            limit_at: *limit_at,
                        },
                        Decision::Wait,
                    )),
                    // Ticks, late completions and repeated exits while stopping change nothing.
                    _ => keep(),
                }
            }
        }
    }
}
