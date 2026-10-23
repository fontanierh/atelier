//! T0: the owned worker lifecycle over scripted guard observations, on a fake clock.
use atelier_build_v2::failure_policy::{
    CleanupState, End, Expiry, Limits, MonoTime, Outcome, Stop,
};
use atelier_build_v2::guard_adapter::{
    AttemptEvent, CleanupReceipt, ExitInfo, LaunchEvent, StoppedBy,
};
use atelier_build_v2::leases::ProcessIdentity;
use atelier_build_v2::protocol::{FailureKind, JobOutputs, WorkerFailure};
use atelier_build_v2::worker_lifecycle::*;
use atelier_build_v2::worker_session::{Event as WorkerEvent, JobFinished};
use std::path::PathBuf;
use std::time::Duration;

const JOB: u64 = 60_000;
const CLEAN: u64 = 5_000;

fn t(ms: u64) -> MonoTime {
    MonoTime::from_elapsed(Duration::from_millis(ms))
}

fn worker(pid: u32) -> ProcessIdentity {
    ProcessIdentity {
        pid,
        boot: "boot-1".into(),
        started: format!("start-{pid}"),
    }
}

struct Sim {
    lifecycle: Lifecycle,
    log: Vec<Command>,
}

impl Sim {
    fn new(overall: Option<u64>) -> (Self, Vec<Command>) {
        let (lifecycle, first) = Lifecycle::new(
            t(0),
            Limits {
                job: Duration::from_millis(JOB),
                cleanup: Duration::from_millis(CLEAN),
                overall: overall.map(Duration::from_millis),
            },
        );
        (
            Self {
                lifecycle,
                log: first.clone(),
            },
            first,
        )
    }

    fn at(&mut self, ms: u64, input: Input) -> Vec<Command> {
        let commands = self
            .lifecycle
            .on(t(ms), input.clone())
            .unwrap_or_else(|error| panic!("{input:?}: {error:?}"));
        self.log.extend(commands.clone());
        commands
    }

    fn launch(&mut self, ms: u64, attempt: u32, event: LaunchEvent) -> Vec<Command> {
        self.at(ms, Input::Launch(AttemptEvent { attempt, event }))
    }

    fn worker(&mut self, ms: u64, attempt: u32, event: WorkerEvent) -> Vec<Command> {
        self.at(
            ms,
            Input::Worker {
                attempt,
                event: Ok(event),
            },
        )
    }

    /// Admission, the pinned child, lease registration and hello: the job is sent.
    fn start(&mut self, ms: u64, attempt: u32, pid: u32) {
        assert_eq!(self.launch(ms, attempt, LaunchEvent::Queued), vec![]);
        assert_eq!(self.launch(ms, attempt, LaunchEvent::Admitted), vec![]);
        assert_eq!(
            self.launch(
                ms,
                attempt,
                LaunchEvent::ChildStarted {
                    worker: worker(pid)
                }
            ),
            vec![Command::RegisterWorker {
                attempt,
                worker: worker(pid)
            }]
        );
        assert_eq!(self.at(ms, Input::Registered { attempt, ok: true }), vec![]);
        assert_eq!(
            self.worker(
                ms,
                attempt,
                WorkerEvent::Ready {
                    worker_version: "w1".into()
                }
            ),
            vec![Command::StartJob { attempt }]
        );
        assert_eq!(
            self.worker(
                ms,
                attempt,
                WorkerEvent::Started {
                    job_id: "job".into()
                }
            ),
            vec![]
        );
    }

    fn report(&self) -> Report {
        self.lifecycle.report().expect("settled report")
    }

    fn submits(&self) -> usize {
        self.log
            .iter()
            .filter(|c| matches!(c, Command::Submit { .. }))
            .count()
    }
}

fn exited(pid: u32, exit: ExitInfo, stopped_by: Option<StoppedBy>) -> LaunchEvent {
    LaunchEvent::ChildExited {
        worker: worker(pid),
        exit,
        stopped_by,
    }
}

fn confirmed() -> LaunchEvent {
    LaunchEvent::Finished {
        cleanup: CleanupReceipt::Confirmed,
        receipts: PathBuf::from("receipts"),
    }
}

fn unconfirmed(reason: &str) -> LaunchEvent {
    LaunchEvent::Finished {
        cleanup: CleanupReceipt::Unconfirmed {
            reason: reason.into(),
        },
        receipts: PathBuf::from("receipts"),
    }
}

fn finished(result: Result<JobOutputs, WorkerFailure>) -> WorkerEvent {
    WorkerEvent::Finished(JobFinished {
        job_id: "job".into(),
        result,
        cancel_requested: false,
    })
}

fn outputs() -> JobOutputs {
    JobOutputs {
        files: vec!["piece.glb".into()],
    }
}

fn failed(stop: Stop, attempts: u32, cleanup: CleanupState) -> Outcome {
    Outcome {
        end: End::Failed(stop),
        attempts,
        cleanup,
    }
}

#[test]
fn queued_cancel_spawns_no_child_and_holds_no_capacity() {
    let (mut sim, first) = Sim::new(None);
    assert_eq!(first, vec![Command::Submit { attempt: 1 }]);
    sim.launch(10, 1, LaunchEvent::Queued);
    assert_eq!(
        sim.at(20, Input::Cancel),
        vec![Command::Stop { attempt: 1 }]
    );
    // Not settled until the guard confirms the withdrawn request.
    assert!(sim.lifecycle.report().is_none());
    // A late offer after the cancel never launches or registers anything.
    assert_eq!(sim.launch(25, 1, LaunchEvent::Admitted), vec![]);
    assert_eq!(sim.launch(30, 1, confirmed()), vec![]);
    let report = sim.report();
    assert_eq!(
        report.outcome,
        failed(Stop::Cancelled, 0, CleanupState::NotNeeded)
    );
    assert_eq!(report.attempts.len(), 1);
    assert_eq!(report.attempts[0].custody, Custody::Released);
    assert_eq!(report.attempts[0].worker, None);
    assert_eq!(
        sim.log,
        vec![Command::Submit { attempt: 1 }, Command::Stop { attempt: 1 }]
    );
}

#[test]
fn admitted_job_completes_then_shuts_down_and_releases() {
    let (mut sim, _) = Sim::new(None);
    sim.start(0, 1, 101);
    assert_eq!(
        sim.worker(100, 1, finished(Ok(outputs()))),
        vec![Command::Shutdown { attempt: 1 }]
    );
    sim.worker(110, 1, WorkerEvent::Stopped);
    assert_eq!(
        sim.launch(120, 1, exited(101, ExitInfo::Code(0), None)),
        vec![]
    );
    assert!(sim.lifecycle.report().is_none());
    sim.launch(130, 1, confirmed());
    let report = sim.report();
    assert_eq!(report.outcome.end, End::Completed);
    assert_eq!(report.outputs, Some(outputs()));
    assert_eq!(report.attempts[0].custody, Custody::Released);
    assert_eq!(report.attempts[0].worker, Some(worker(101)));
    assert!(!sim.log.contains(&Command::Stop { attempt: 1 }));
}

#[test]
fn job_failure_shuts_the_worker_down_and_never_retries() {
    let (mut sim, _) = Sim::new(None);
    sim.start(0, 1, 101);
    let failure = WorkerFailure {
        kind: FailureKind::Job,
        message: "bad input".into(),
    };
    assert_eq!(
        sim.worker(100, 1, finished(Err(failure))),
        vec![Command::Shutdown { attempt: 1 }]
    );
    sim.launch(110, 1, exited(101, ExitInfo::Code(0), None));
    sim.launch(120, 1, confirmed());
    let report = sim.report();
    assert_eq!(
        report.outcome,
        failed(
            Stop::WorkerReported(FailureKind::Job),
            1,
            CleanupState::Finished
        )
    );
    assert_eq!(report.outputs, None);
    assert_eq!(sim.submits(), 1);
}

#[test]
fn one_retry_only_after_confirmed_cleanup_and_a_new_admission() {
    let (mut sim, _) = Sim::new(Some(10 * JOB));
    sim.start(0, 1, 101);
    // The guard observed the pinned worker exit with no stop: crash evidence. No signal is sent
    // to an exited worker; the guard is already cleaning up.
    assert_eq!(
        sim.launch(100, 1, exited(101, ExitInfo::Signal(9), None)),
        vec![]
    );
    // Cleanup pending: nothing is resubmitted yet.
    assert_eq!(sim.at(200, Input::Tick), vec![]);
    assert_eq!(
        sim.launch(300, 1, confirmed()),
        vec![Command::Submit { attempt: 2 }]
    );
    // Waiting for the new admission: no launch, and a late event for attempt 1 changes nothing.
    assert_eq!(sim.launch(400, 1, LaunchEvent::Admitted), vec![]);
    assert_eq!(sim.at(5_000, Input::Tick), vec![]);
    sim.start(6_000, 2, 202);
    // Second crash: no further retry.
    assert_eq!(
        sim.launch(6_100, 2, exited(202, ExitInfo::Code(3), None)),
        vec![]
    );
    assert_eq!(sim.launch(6_200, 2, confirmed()), vec![]);
    let report = sim.report();
    assert_eq!(
        report.outcome,
        failed(Stop::Crash, 2, CleanupState::Finished)
    );
    assert_eq!(sim.submits(), 2);
    assert_eq!(
        report
            .attempts
            .iter()
            .map(|a| a.custody.clone())
            .collect::<Vec<_>>(),
        vec![Custody::Released, Custody::Released]
    );
}

#[test]
fn retried_attempt_can_complete() {
    let (mut sim, _) = Sim::new(None);
    sim.start(0, 1, 101);
    sim.launch(100, 1, exited(101, ExitInfo::Code(1), None));
    assert_eq!(
        sim.launch(200, 1, confirmed()),
        vec![Command::Submit { attempt: 2 }]
    );
    sim.start(300, 2, 202);
    sim.worker(400, 2, finished(Ok(outputs())));
    sim.launch(410, 2, exited(202, ExitInfo::Code(0), None));
    sim.launch(420, 2, confirmed());
    let report = sim.report();
    assert_eq!(report.outcome.end, End::Completed);
    assert_eq!(report.outcome.attempts, 2);
}

#[test]
fn timeout_guard_stop_and_cancel_never_retry() {
    // Timeout: the policy's job limit (from admission) stops the attempt through the guard.
    let (mut sim, _) = Sim::new(None);
    sim.start(1_000, 1, 101);
    assert_eq!(
        sim.at(1_000 + JOB, Input::Tick),
        vec![Command::Stop { attempt: 1 }]
    );
    sim.launch(
        1_000 + JOB + 10,
        1,
        exited(101, ExitInfo::Unknown, Some(StoppedBy::Cancel)),
    );
    sim.launch(1_000 + JOB + 20, 1, confirmed());
    assert_eq!(
        sim.report().outcome,
        failed(Stop::JobLimit, 1, CleanupState::Finished)
    );
    assert_eq!(sim.submits(), 1);

    // Guard stops (memory or the guard's own deadline) are not crashes.
    for by in [StoppedBy::Guard, StoppedBy::Deadline] {
        let (mut sim, _) = Sim::new(None);
        sim.start(0, 1, 101);
        assert_eq!(
            sim.launch(100, 1, exited(101, ExitInfo::Signal(9), Some(by))),
            vec![]
        );
        sim.launch(200, 1, confirmed());
        assert_eq!(
            sim.report().outcome,
            failed(Stop::GuardStop, 1, CleanupState::Finished)
        );
        assert_eq!(sim.submits(), 1);
    }

    // Our cancel: the requested exit is not a crash.
    let (mut sim, _) = Sim::new(None);
    sim.start(0, 1, 101);
    assert_eq!(
        sim.at(100, Input::Cancel),
        vec![Command::Stop { attempt: 1 }]
    );
    sim.launch(
        110,
        1,
        exited(101, ExitInfo::Unknown, Some(StoppedBy::Cancel)),
    );
    sim.launch(120, 1, confirmed());
    assert_eq!(
        sim.report().outcome,
        failed(Stop::Cancelled, 1, CleanupState::Finished)
    );

    // Someone else stopping the admission owner is a cancellation, not crash evidence.
    let (mut sim, _) = Sim::new(None);
    sim.start(0, 1, 101);
    assert_eq!(
        sim.launch(
            100,
            1,
            exited(101, ExitInfo::Unknown, Some(StoppedBy::Cancel))
        ),
        vec![]
    );
    sim.launch(110, 1, confirmed());
    assert_eq!(
        sim.report().outcome,
        failed(Stop::Cancelled, 1, CleanupState::Finished)
    );
    assert_eq!(sim.submits(), 1);

    // A crash whose cleanup is cancelled does not retry either.
    let (mut sim, _) = Sim::new(None);
    sim.start(0, 1, 101);
    sim.launch(100, 1, exited(101, ExitInfo::Code(1), None));
    assert_eq!(sim.at(150, Input::Cancel), vec![]);
    assert_eq!(sim.launch(200, 1, confirmed()), vec![]);
    assert_eq!(
        sim.report().outcome,
        failed(Stop::Crash, 1, CleanupState::Finished)
    );
    assert_eq!(sim.submits(), 1);
}

#[test]
fn uncertain_cleanup_is_held_and_never_released_or_relaunched() {
    // A crash is retry-eligible, but its cleanup receipt is unconfirmed.
    let (mut sim, _) = Sim::new(None);
    sim.start(0, 1, 101);
    sim.launch(100, 1, exited(101, ExitInfo::Signal(11), None));
    assert_eq!(
        sim.launch(200, 1, unconfirmed("tree cleanup incomplete")),
        vec![]
    );
    assert!(
        sim.lifecycle.report().is_none(),
        "the policy still awaits its cleanup limit"
    );
    assert_eq!(sim.at(100 + CLEAN, Input::Tick), vec![]);
    let report = sim.report();
    assert_eq!(
        report.outcome,
        failed(
            Stop::Crash,
            1,
            CleanupState::Unconfirmed(Expiry::CleanupLimit)
        )
    );
    assert_eq!(
        report.attempts[0].custody,
        Custody::Held("tree cleanup incomplete".into())
    );
    assert_eq!(sim.submits(), 1);

    // A policy deadline never certifies cleanup: the attempt is held, not released.
    let (mut sim, _) = Sim::new(Some(2_000));
    sim.start(0, 1, 101);
    assert_eq!(
        sim.at(2_000, Input::Tick),
        vec![Command::Stop { attempt: 1 }]
    );
    assert_eq!(sim.at(2_000 + CLEAN, Input::Tick), vec![]);
    let report = sim.report();
    assert_eq!(
        report.outcome,
        failed(
            Stop::OverallDeadline,
            1,
            CleanupState::Unconfirmed(Expiry::OverallDeadline)
        )
    );
    assert!(matches!(report.attempts[0].custody, Custody::Held(_)));

    // A completed job whose admission owner never confirms cleanup is held after the limit.
    let (mut sim, _) = Sim::new(None);
    sim.start(0, 1, 101);
    sim.worker(100, 1, finished(Ok(outputs())));
    assert!(sim.lifecycle.report().is_none());
    assert_eq!(
        sim.at(100 + CLEAN, Input::Tick),
        vec![Command::Stop { attempt: 1 }]
    );
    let report = sim.report();
    assert_eq!(report.outcome.end, End::Completed);
    assert_eq!(report.outputs, Some(outputs()));
    assert!(matches!(report.attempts[0].custody, Custody::Held(_)));
    // A positive receipt after the limit never releases it: it is kept as evidence in the held
    // record (session-held-is-sticky).
    sim.launch(9_000, 1, confirmed());
    assert_eq!(
        sim.lifecycle.attempts()[0].custody,
        Custody::Held(
            "no confirmed cleanup receipt within the cleanup limit; \
             a confirmed cleanup receipt arrived late, at 9000 ms"
                .into()
        )
    );
}

#[test]
fn foreign_or_stale_identities_are_never_crash_evidence() {
    let (mut sim, _) = Sim::new(None);
    sim.start(0, 1, 101);
    // An exit for another identity (reused PID, different start) is an inconsistent report.
    let foreign = LaunchEvent::ChildExited {
        worker: ProcessIdentity {
            pid: 101,
            boot: "boot-1".into(),
            started: "start-other".into(),
        },
        exit: ExitInfo::Signal(9),
        stopped_by: None,
    };
    assert_eq!(
        sim.launch(100, 1, foreign),
        vec![Command::Stop { attempt: 1 }]
    );
    sim.launch(
        110,
        1,
        exited(101, ExitInfo::Unknown, Some(StoppedBy::Cancel)),
    );
    sim.launch(120, 1, confirmed());
    assert_eq!(
        sim.report().outcome,
        failed(Stop::Protocol, 1, CleanupState::Finished)
    );
    assert_eq!(sim.submits(), 1);

    // A second, different child identity for the same attempt is refused the same way.
    let (mut sim, _) = Sim::new(None);
    sim.start(0, 1, 101);
    assert_eq!(
        sim.launch(
            100,
            1,
            LaunchEvent::ChildStarted {
                worker: worker(102)
            }
        ),
        vec![Command::Stop { attempt: 1 }]
    );

    // A child before admission, or a malformed guard report, is never trusted.
    let (mut sim, _) = Sim::new(None);
    assert_eq!(
        sim.launch(
            0,
            1,
            LaunchEvent::ChildStarted {
                worker: worker(101)
            }
        ),
        vec![Command::Stop { attempt: 1 }]
    );
    let (mut sim, _) = Sim::new(None);
    sim.start(0, 1, 101);
    assert_eq!(
        sim.launch(10, 1, LaunchEvent::Fault("garbage".into())),
        vec![Command::Stop { attempt: 1 }]
    );

    // Pipe loss and worker claims are not crash evidence either.
    let (mut sim, _) = Sim::new(None);
    sim.start(0, 1, 101);
    let lost = sim.at(
        50,
        Input::Worker {
            attempt: 1,
            event: Err(WorkerFault::Disconnected("eof".into())),
        },
    );
    assert_eq!(lost, vec![]);
    let claim = WorkerFailure {
        kind: FailureKind::Crash,
        message: "worker says crash".into(),
    };
    assert_eq!(
        sim.worker(60, 1, finished(Err(claim))),
        vec![Command::Shutdown { attempt: 1 }]
    );
    sim.launch(70, 1, exited(101, ExitInfo::Code(0), None));
    sim.launch(80, 1, confirmed());
    assert_eq!(
        sim.report().outcome,
        failed(
            Stop::WorkerReported(FailureKind::Crash),
            1,
            CleanupState::Finished
        )
    );
    assert_eq!(sim.submits(), 1);
}

#[test]
fn queue_wait_does_not_spend_the_job_limit_and_launch_failures_hold_nothing() {
    let (mut sim, _) = Sim::new(None);
    sim.launch(0, 1, LaunchEvent::Queued);
    assert_eq!(sim.at(10 * JOB, Input::Tick), vec![]);
    sim.start(10 * JOB, 1, 101);
    assert_eq!(sim.at(11 * JOB - 1, Input::Tick), vec![]);
    assert_eq!(
        sim.at(11 * JOB, Input::Tick),
        vec![Command::Stop { attempt: 1 }]
    );

    let (mut sim, _) = Sim::new(None);
    assert_eq!(
        sim.at(
            0,
            Input::SubmitFailed {
                attempt: 1,
                reason: "no bridge".into()
            }
        ),
        vec![]
    );
    let report = sim.report();
    assert_eq!(
        report.outcome,
        failed(Stop::Cancelled, 0, CleanupState::NotNeeded)
    );
    assert_eq!(report.attempts[0].custody, Custody::Released);
    assert!(report.abort.unwrap().contains("no bridge"));

    // A worker that cannot be added to the write lease never receives its job.
    let (mut sim, _) = Sim::new(None);
    sim.launch(0, 1, LaunchEvent::Admitted);
    sim.launch(
        0,
        1,
        LaunchEvent::ChildStarted {
            worker: worker(101),
        },
    );
    assert_eq!(
        sim.at(
            1,
            Input::Registered {
                attempt: 1,
                ok: false
            }
        ),
        vec![Command::Stop { attempt: 1 }]
    );
    sim.worker(
        2,
        1,
        WorkerEvent::Ready {
            worker_version: "w1".into(),
        },
    );
    assert!(!sim.log.contains(&Command::StartJob { attempt: 1 }));
}

#[test]
fn settlement_never_outlasts_the_overall_deadline() {
    // Paid review: a 10 s overall deadline, completion at 9 s and a 5 s cleanup limit must not
    // leave custody pending until 14 s; past the deadline an unsettled attempt is held.
    let (mut sim, _) = Sim::new(Some(10_000));
    sim.start(0, 1, 101);
    assert_eq!(
        sim.worker(9_000, 1, finished(Ok(outputs()))),
        vec![Command::Shutdown { attempt: 1 }]
    );
    assert_eq!(sim.lifecycle.next_deadline(), Some(t(10_000)));
    sim.at(9_999, Input::Tick);
    assert!(
        sim.lifecycle.report().is_none(),
        "still within the deadline"
    );
    sim.at(10_000, Input::Tick);
    let report = sim.report();
    assert_eq!(report.outcome.end, End::Completed);
    assert_eq!(
        report.outputs,
        Some(outputs()),
        "the completed work is kept"
    );
    assert!(matches!(report.attempts[0].custody, Custody::Held(_)));
    // A late confirmed receipt, after that Tick or with none before it, never makes the
    // report's attempts (the session records the executor reads) Released.
    sim.launch(10_100, 1, confirmed());
    assert!(matches!(sim.report().attempts[0].custody, Custody::Held(_)));
    for at in [10_000, 10_001] {
        let (mut sim, _) = Sim::new(Some(10_000));
        sim.start(0, 1, 101);
        sim.worker(9_000, 1, finished(Ok(outputs())));
        sim.launch(at, 1, confirmed());
        let report = sim.report();
        assert_eq!(report.outcome.end, End::Completed, "receipt at {at} ms");
        assert!(
            matches!(report.attempts[0].custody, Custody::Held(_)),
            "receipt at {at} ms: {:?}",
            report.attempts
        );
        // The Python executor's release check (python_executor.rs) never accepts it.
        let accepted = !matches!(report.outcome.cleanup, CleanupState::Unconfirmed(_))
            && report
                .attempts
                .iter()
                .all(|attempt| attempt.custody == Custody::Released);
        assert!(!accepted, "receipt at {at} ms");
    }

    // Without an overall deadline the cleanup limit alone bounds settlement, as before.
    let (mut sim, _) = Sim::new(None);
    sim.start(0, 1, 101);
    sim.worker(9_000, 1, finished(Ok(outputs())));
    assert_eq!(sim.lifecycle.next_deadline(), Some(t(9_000 + CLEAN)));
}

#[test]
fn completed_work_is_kept_and_later_facts_never_stop_or_retry_it() {
    let (mut sim, _) = Sim::new(Some(10 * JOB));
    sim.start(0, 1, 101);
    sim.worker(100, 1, finished(Ok(outputs())));
    // Later facts after completion: no stop of a completed worker, no retry, outputs kept.
    assert_eq!(sim.at(150, Input::Cancel), vec![]);
    assert_eq!(
        sim.launch(200, 1, exited(101, ExitInfo::Signal(9), None)),
        vec![]
    );
    assert_eq!(sim.launch(210, 1, confirmed()), vec![]);
    let report = sim.report();
    assert_eq!(report.outcome.end, End::Completed);
    assert_eq!(report.outputs, Some(outputs()));
    assert_eq!(sim.submits(), 1);
    assert!(!sim.log.contains(&Command::Stop { attempt: 1 }));
    // Every command in every scenario is one of the non-destructive kinds by construction.
    for command in &sim.log {
        assert!(matches!(
            command,
            Command::Submit { .. }
                | Command::RegisterWorker { .. }
                | Command::StartJob { .. }
                | Command::Shutdown { .. }
                | Command::Stop { .. }
        ));
    }
}
