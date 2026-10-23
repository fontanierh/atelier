use atelier_build_v2::failure_policy::*;
use atelier_build_v2::protocol::{FailureKind, WorkerFailure};
use std::time::Duration;

// Fake monotonic clock in milliseconds; no test reads a real clock or sleeps.
const MIN: u64 = 60_000;
const JOB: u64 = 10 * MIN;
const CLEAN: u64 = MIN;
const HOUR: u64 = 60 * MIN;

const ALL_KINDS: [FailureKind; 7] = [
    FailureKind::Job,
    FailureKind::Dependency,
    FailureKind::Protocol,
    FailureKind::Crash,
    FailureKind::Cancelled,
    FailureKind::Timeout,
    FailureKind::GuardStop,
];

fn t(ms: u64) -> MonoTime {
    MonoTime::from_elapsed(Duration::from_millis(ms))
}

fn policy(overall: Option<u64>) -> JobPolicy {
    JobPolicy::new(
        t(0),
        Limits {
            job: Duration::from_millis(JOB),
            cleanup: Duration::from_millis(CLEAN),
            overall: overall.map(Duration::from_millis),
        },
    )
}

fn launch(attempt: u32) -> Decision {
    Decision::Launch { attempt }
}

fn readmit(attempt: u32) -> Decision {
    Decision::RequestAdmission { attempt }
}

fn cleanup(stop: Stop) -> Decision {
    Decision::BeginCleanup {
        stop,
        discard: Discard::UnpublishedScratchOnly,
    }
}

fn failed(stop: Stop, attempts: u32, cleanup: CleanupState) -> Decision {
    Decision::Finish(Outcome {
        end: End::Failed(stop),
        attempts,
        cleanup,
    })
}

fn completed(attempts: u32) -> Decision {
    Decision::Finish(Outcome {
        end: End::Completed,
        attempts,
        cleanup: CleanupState::NotNeeded,
    })
}

struct Row {
    name: String,
    overall: Option<u64>,
    steps: Vec<(u64, Event, Decision)>,
}

fn row(name: &str, overall: Option<u64>, steps: Vec<(u64, Event, Decision)>) -> Row {
    Row {
        name: name.into(),
        overall,
        steps,
    }
}

/// Runs one scripted trace and checks invariants that hold for every decision.
fn run(row: &Row) -> Vec<Decision> {
    let mut policy = policy(row.overall);
    let mut decisions = vec![];
    let mut completed_seen = false;
    for (index, (at, event, expected)) in row.steps.iter().enumerate() {
        let decision = policy
            .decide(t(*at), event.clone())
            .unwrap_or_else(|error| panic!("{} step {index}: {error:?}", row.name));
        assert_eq!(&decision, expected, "{} step {index} ({event:?})", row.name);
        if let Decision::BeginCleanup { discard, .. } = &decision {
            assert_eq!(*discard, Discard::UnpublishedScratchOnly, "{}", row.name);
        }
        if completed_seen {
            assert_eq!(
                decision,
                Decision::Wait,
                "{}: completed work changed",
                row.name
            );
        }
        completed_seen |= matches!(
            &decision,
            Decision::Finish(Outcome {
                end: End::Completed,
                ..
            })
        );
        decisions.push(decision);
    }
    decisions
}

fn matrix() -> Vec<Row> {
    use CleanupState::{Finished, NotNeeded, Unconfirmed};
    use Event::*;
    use Observation::*;
    let mut rows = vec![];

    // Each worker-claimed kind, including a claimed crash, stops without retry.
    for kind in ALL_KINDS {
        let stop = Stop::WorkerReported(kind.clone());
        rows.push(row(
            &format!("worker claims {kind:?}"),
            None,
            vec![
                (0, Admitted, launch(1)),
                (5, WorkerFailed(kind), cleanup(stop.clone())),
                (6, CleanupFinished, failed(stop, 1, Finished)),
            ],
        ));
    }
    // Controller observations other than an unexpected exit never retry.
    for (observation, stop) in [
        (GuardStopped, Stop::GuardStop),
        (ProtocolViolation, Stop::Protocol),
        (DependencyViolation, Stop::Dependency),
    ] {
        rows.push(row(
            &format!("observed {observation:?}"),
            None,
            vec![
                (0, Admitted, launch(1)),
                (5, Observed(observation), cleanup(stop.clone())),
                (6, CleanupFinished, failed(stop, 1, Finished)),
            ],
        ));
    }
    rows.push(row(
        "completed before the job limit",
        None,
        vec![(0, Admitted, launch(1)), (JOB - 1, Completed, completed(1))],
    ));
    rows.push(row(
        "first crash retries after cleanup and a new admission, second crash fails",
        None,
        vec![
            (0, Admitted, launch(1)),
            (10, Observed(UnexpectedExit), cleanup(Stop::Crash)),
            // Cleanup pending: no relaunch, late facts are not new evidence.
            (20, Tick, Decision::Wait),
            (25, Completed, Decision::Wait),
            (26, Observed(UnexpectedExit), Decision::Wait),
            (30, CleanupFinished, readmit(2)),
            // New admission pending: eligibility alone never launches.
            (5 * HOUR, Tick, Decision::Wait),
            (5 * HOUR, Admitted, launch(2)),
            (
                5 * HOUR + 10,
                Observed(UnexpectedExit),
                cleanup(Stop::Crash),
            ),
            (
                5 * HOUR + 20,
                CleanupFinished,
                failed(Stop::Crash, 2, Finished),
            ),
        ],
    ));
    rows.push(row(
        "retried attempt can complete",
        None,
        vec![
            (0, Admitted, launch(1)),
            (10, Observed(UnexpectedExit), cleanup(Stop::Crash)),
            (20, CleanupFinished, readmit(2)),
            (30, Admitted, launch(2)),
            (40, Completed, completed(2)),
        ],
    ));
    rows.push(row(
        "queue wait does not spend the job limit; admission starts it",
        None,
        vec![
            (5 * HOUR, Tick, Decision::Wait),
            (5 * HOUR, Admitted, launch(1)),
            (5 * HOUR + JOB - 1, Tick, Decision::Wait),
            (5 * HOUR + JOB, Tick, cleanup(Stop::JobLimit)),
            (
                5 * HOUR + JOB + 1,
                CleanupFinished,
                failed(Stop::JobLimit, 1, Finished),
            ),
        ],
    ));
    rows.push(row(
        "a completion at the job limit is a timeout",
        None,
        vec![
            (0, Admitted, launch(1)),
            (JOB, Completed, cleanup(Stop::JobLimit)),
        ],
    ));
    rows.push(row(
        "a retry's job limit starts at its own admission",
        None,
        vec![
            (0, Admitted, launch(1)),
            (JOB - 1, Observed(UnexpectedExit), cleanup(Stop::Crash)),
            (JOB, CleanupFinished, readmit(2)),
            (3 * JOB, Admitted, launch(2)),
            (4 * JOB - 1, Tick, Decision::Wait),
            (4 * JOB, Tick, cleanup(Stop::JobLimit)),
        ],
    ));

    // The overall deadline covers queue, run, cleanup and retries.
    rows.push(row(
        "overall deadline while queued",
        Some(HOUR),
        vec![
            (HOUR - 1, Tick, Decision::Wait),
            (HOUR, Tick, failed(Stop::OverallDeadline, 0, NotNeeded)),
        ],
    ));
    rows.push(row(
        "admission granted after the overall deadline is not used",
        Some(HOUR),
        vec![(HOUR, Admitted, failed(Stop::OverallDeadline, 0, NotNeeded))],
    ));
    rows.push(row(
        "overall deadline while running",
        Some(HOUR),
        vec![
            (HOUR - JOB / 2, Admitted, launch(1)),
            (HOUR, Tick, cleanup(Stop::OverallDeadline)),
            (
                HOUR + 1,
                CleanupFinished,
                failed(Stop::OverallDeadline, 1, Finished),
            ),
        ],
    ));
    rows.push(row(
        "overall deadline while crash cleanup is pending",
        Some(HOUR),
        vec![
            (HOUR - 100, Admitted, launch(1)),
            (HOUR - 50, Observed(UnexpectedExit), cleanup(Stop::Crash)),
            (
                HOUR,
                Tick,
                failed(Stop::Crash, 1, Unconfirmed(Expiry::OverallDeadline)),
            ),
            (HOUR + 1, CleanupFinished, Decision::Wait),
        ],
    ));
    rows.push(row(
        "crash cleanup confirmed after the overall deadline does not retry",
        Some(HOUR),
        vec![
            (HOUR - 100, Admitted, launch(1)),
            (HOUR - 50, Observed(UnexpectedExit), cleanup(Stop::Crash)),
            (HOUR + 1, CleanupFinished, failed(Stop::Crash, 1, Finished)),
        ],
    ));
    rows.push(row(
        "overall deadline while awaiting a new admission",
        Some(HOUR),
        vec![
            (HOUR - 100, Admitted, launch(1)),
            (HOUR - 90, Observed(UnexpectedExit), cleanup(Stop::Crash)),
            (HOUR - 80, CleanupFinished, readmit(2)),
            (HOUR, Admitted, failed(Stop::OverallDeadline, 1, Finished)),
        ],
    ));
    rows.push(row(
        "overall deadline during the retry",
        Some(HOUR),
        vec![
            (HOUR - 100, Admitted, launch(1)),
            (HOUR - 90, Observed(UnexpectedExit), cleanup(Stop::Crash)),
            (HOUR - 80, CleanupFinished, readmit(2)),
            (HOUR - 70, Admitted, launch(2)),
            (
                HOUR,
                Observed(UnexpectedExit),
                cleanup(Stop::OverallDeadline),
            ),
            (
                HOUR + 1,
                CleanupFinished,
                failed(Stop::OverallDeadline, 2, Finished),
            ),
        ],
    ));

    // Cancellation in every state.
    rows.push(row(
        "cancel while queued",
        Some(HOUR),
        vec![(10, CancelRequested, failed(Stop::Cancelled, 0, NotNeeded))],
    ));
    rows.push(row(
        "cancel while running; the requested exit is not a crash",
        None,
        vec![
            (0, Admitted, launch(1)),
            (10, CancelRequested, cleanup(Stop::Cancelled)),
            (20, Observed(UnexpectedExit), Decision::Wait),
            (30, CleanupFinished, failed(Stop::Cancelled, 1, Finished)),
        ],
    ));
    rows.push(row(
        "cancel while crash cleanup is pending withdraws the retry",
        None,
        vec![
            (0, Admitted, launch(1)),
            (10, Observed(UnexpectedExit), cleanup(Stop::Crash)),
            (20, CancelRequested, Decision::Wait),
            (30, CleanupFinished, failed(Stop::Crash, 1, Finished)),
        ],
    ));
    // A non-crash failure fact during crash cleanup withdraws the retry like cancellation.
    for (event, label) in [
        (Observed(ProtocolViolation), "protocol violation"),
        (Observed(DependencyViolation), "dependency violation"),
        (Observed(GuardStopped), "guard stop"),
        (WorkerFailed(FailureKind::Job), "worker job failure claim"),
        (WorkerFailed(FailureKind::Crash), "worker crash claim"),
    ] {
        rows.push(row(
            &format!("{label} during crash cleanup withdraws the retry"),
            None,
            vec![
                (0, Admitted, launch(1)),
                (10, Observed(UnexpectedExit), cleanup(Stop::Crash)),
                (20, event, Decision::Wait),
                (30, CleanupFinished, failed(Stop::Crash, 1, Finished)),
                (40, Tick, Decision::Wait),
            ],
        ));
    }
    rows.push(row(
        "cancel while awaiting a new admission",
        None,
        vec![
            (0, Admitted, launch(1)),
            (10, Observed(UnexpectedExit), cleanup(Stop::Crash)),
            (20, CleanupFinished, readmit(2)),
            (30, CancelRequested, failed(Stop::Cancelled, 1, Finished)),
        ],
    ));
    rows.push(row(
        "cancel during the retry",
        None,
        vec![
            (0, Admitted, launch(1)),
            (10, Observed(UnexpectedExit), cleanup(Stop::Crash)),
            (20, CleanupFinished, readmit(2)),
            (30, Admitted, launch(2)),
            (40, CancelRequested, cleanup(Stop::Cancelled)),
            (50, CleanupFinished, failed(Stop::Cancelled, 2, Finished)),
        ],
    ));
    rows.push(row(
        "cancel after completion keeps the completed result",
        Some(HOUR),
        vec![
            (0, Admitted, launch(1)),
            (10, Completed, completed(1)),
            (20, CancelRequested, Decision::Wait),
            (2 * HOUR, Tick, Decision::Wait),
        ],
    ));

    // Cleanup timeouts never retry and do not claim the process is gone.
    rows.push(row(
        "crash cleanup timeout does not retry",
        None,
        vec![
            (0, Admitted, launch(1)),
            (10, Observed(UnexpectedExit), cleanup(Stop::Crash)),
            (10 + CLEAN - 1, Tick, Decision::Wait),
            (
                10 + CLEAN,
                Tick,
                failed(Stop::Crash, 1, Unconfirmed(Expiry::CleanupLimit)),
            ),
            (10 + CLEAN + 1, CleanupFinished, Decision::Wait),
        ],
    ));
    rows.push(row(
        "crash cleanup confirmed at its limit does not retry",
        None,
        vec![
            (0, Admitted, launch(1)),
            (10, Observed(UnexpectedExit), cleanup(Stop::Crash)),
            (
                10 + CLEAN,
                CleanupFinished,
                failed(Stop::Crash, 1, Finished),
            ),
        ],
    ));
    rows.push(row(
        "cancel cleanup timeout",
        None,
        vec![
            (0, Admitted, launch(1)),
            (10, CancelRequested, cleanup(Stop::Cancelled)),
            (
                10 + CLEAN,
                Tick,
                failed(Stop::Cancelled, 1, Unconfirmed(Expiry::CleanupLimit)),
            ),
        ],
    ));
    rows
}

#[test]
fn decision_matrix_retries_only_one_confirmed_crash_within_deadlines() {
    let rows = matrix();
    assert!(rows.len() >= 37);
    for row in &rows {
        run(row);
    }
}

#[test]
fn worker_claimed_crash_is_not_a_crash_observation() {
    let mut policy = policy(None);
    policy.decide(t(0), Event::Admitted).unwrap();
    let claim = WorkerFailure {
        kind: FailureKind::Crash,
        message: "worker says it crashed".into(),
    };
    let stop = Stop::WorkerReported(FailureKind::Crash);
    assert_eq!(
        policy.decide(t(1), Event::worker_failed(&claim)).unwrap(),
        cleanup(stop.clone())
    );
    // The real exit that follows the claim arrives while stopping and is not new evidence.
    assert_eq!(
        policy
            .decide(t(2), Event::Observed(Observation::UnexpectedExit))
            .unwrap(),
        Decision::Wait
    );
    assert_eq!(
        policy.decide(t(3), Event::CleanupFinished).unwrap(),
        failed(stop, 1, CleanupState::Finished)
    );
}

#[test]
fn no_decision_requests_deleting_published_work() {
    use Event::*;
    // After completion (validated and published downstream), no later fact changes the result.
    let later = [
        Admitted,
        Completed,
        CancelRequested,
        CleanupFinished,
        Tick,
        Observed(Observation::UnexpectedExit),
        Observed(Observation::GuardStopped),
        Observed(Observation::ProtocolViolation),
        Observed(Observation::DependencyViolation),
    ]
    .into_iter()
    .chain(ALL_KINDS.map(WorkerFailed));
    let mut policy = policy(Some(HOUR));
    policy.decide(t(0), Admitted).unwrap();
    assert_eq!(policy.decide(t(1), Completed).unwrap(), completed(1));
    let done = policy.phase().clone();
    for (index, event) in later.enumerate() {
        let at = 2 * HOUR + index as u64;
        assert_eq!(policy.decide(t(at), event).unwrap(), Decision::Wait);
        assert_eq!(policy.phase(), &done);
    }
    // Every cleanup request in the whole matrix is limited to unpublished scratch.
    let cleanups = matrix()
        .iter()
        .flat_map(run)
        .filter(|decision| matches!(decision, Decision::BeginCleanup { .. }))
        .count();
    assert!(cleanups > 20);
}

#[test]
fn stop_reasons_report_every_failure_kind() {
    let observed = [
        Stop::Crash,
        Stop::Protocol,
        Stop::Dependency,
        Stop::Cancelled,
        Stop::JobLimit,
        Stop::OverallDeadline,
        Stop::GuardStop,
    ];
    for kind in ALL_KINDS {
        assert_eq!(Stop::WorkerReported(kind.clone()).kind(), kind);
        assert!(
            observed.iter().any(|stop| stop.kind() == kind) || kind == FailureKind::Job,
            "{kind:?}"
        );
    }
    assert_eq!(Stop::JobLimit.kind(), FailureKind::Timeout);
    assert_eq!(Stop::OverallDeadline.kind(), FailureKind::Timeout);
}

#[test]
fn invalid_events_and_backwards_clock_leave_state_unchanged() {
    use Event::*;
    let mut policy = policy(Some(HOUR));
    for event in [
        Completed,
        WorkerFailed(FailureKind::Job),
        Observed(Observation::UnexpectedExit),
        CleanupFinished,
    ] {
        assert!(matches!(
            policy.decide(t(1), event),
            Err(PolicyError::UnexpectedEvent {
                phase: "queued",
                ..
            })
        ));
        assert_eq!(policy.phase(), &Phase::Queued);
    }
    policy.decide(t(10), Admitted).unwrap();
    let running = policy.phase().clone();
    assert_eq!(
        policy.decide(t(9), Tick),
        Err(PolicyError::ClockWentBackwards)
    );
    // Invalid events are rejected even when a deadline has also passed.
    for event in [Admitted, CleanupFinished] {
        assert!(matches!(
            policy.decide(t(2 * HOUR), event),
            Err(PolicyError::UnexpectedEvent {
                phase: "running",
                ..
            })
        ));
        assert_eq!(policy.phase(), &running);
    }
    policy
        .decide(t(20), Observed(Observation::UnexpectedExit))
        .unwrap();
    // Retry eligibility is not an admission: no admission may arrive during cleanup.
    assert_eq!(
        policy.decide(t(21), Admitted),
        Err(PolicyError::UnexpectedEvent {
            phase: "cleaning_up",
            event: "admitted"
        })
    );
    assert_eq!(policy.decide(t(22), CleanupFinished).unwrap(), readmit(2));
    for event in [
        Completed,
        WorkerFailed(FailureKind::Crash),
        Observed(Observation::UnexpectedExit),
        CleanupFinished,
    ] {
        assert!(matches!(
            policy.decide(t(23), event),
            Err(PolicyError::UnexpectedEvent {
                phase: "awaiting_readmission",
                ..
            })
        ));
    }
    assert_eq!(policy.decide(t(24), Admitted).unwrap(), launch(2));
}

#[test]
fn next_deadline_and_overflowing_limits_use_checked_arithmetic() {
    let mut policy = policy(Some(HOUR));
    assert_eq!(policy.next_deadline(), Some(t(HOUR)));
    policy.decide(t(100), Event::Admitted).unwrap();
    assert_eq!(policy.next_deadline(), Some(t(100 + JOB)));
    policy.decide(t(HOUR - 10), Event::Tick).unwrap();
    // The job limit already passed at HOUR - 10, so that tick began cleanup.
    assert!(matches!(policy.phase(), Phase::CleaningUp { .. }));
    assert_eq!(policy.next_deadline(), Some(t(HOUR)));
    policy.decide(t(HOUR), Event::Tick).unwrap();
    assert_eq!(policy.next_deadline(), None);

    let late = MonoTime::from_elapsed(Duration::MAX);
    assert_eq!(late.checked_add(Duration::from_nanos(1)), None);
    let mut unbounded = JobPolicy::new(
        late,
        Limits {
            job: Duration::MAX,
            cleanup: Duration::MAX,
            overall: Some(Duration::from_nanos(1)),
        },
    );
    assert_eq!(unbounded.next_deadline(), None);
    assert_eq!(unbounded.decide(late, Event::Tick).unwrap(), Decision::Wait);
    assert_eq!(unbounded.decide(late, Event::Admitted).unwrap(), launch(1));
    assert_eq!(unbounded.decide(late, Event::Tick).unwrap(), Decision::Wait);
    assert_eq!(
        unbounded
            .decide(late, Event::Observed(Observation::UnexpectedExit))
            .unwrap(),
        cleanup(Stop::Crash)
    );
    assert_eq!(unbounded.next_deadline(), None);
    assert_eq!(
        unbounded.decide(late, Event::CleanupFinished).unwrap(),
        readmit(2)
    );
}
