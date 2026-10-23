//! T0 tests of the pure C5c session lifecycle: units queued behind one guarded session at a
//! time, each with its own C5a policy. Times are milliseconds from the session's start.
use atelier_build_v2::failure_policy::{CleanupState, End, Expiry, Limits, MonoTime, Stop};
use atelier_build_v2::guard_adapter::{
    AttemptEvent, CleanupReceipt, ExitInfo, LaunchEvent, StoppedBy,
};
use atelier_build_v2::leases::ProcessIdentity;
use atelier_build_v2::protocol::{FailureKind, JobOutputs, WorkerFailure};
use atelier_build_v2::session_lifecycle::*;
use atelier_build_v2::worker_lifecycle::{Custody, WorkerFault};
use atelier_build_v2::worker_session::{Event as WorkerEvent, JobFinished};
use std::path::PathBuf;
use std::time::Duration;

const JOB: u64 = 60_000;
const CLEAN: u64 = 5_000;
const QUIET: u64 = 1_000;
/// A resident session's own cleanup limit: units need CLEAN >= QUIET + SESSION_CLEAN.
const SESSION_CLEAN: u64 = 3_000;
const IDLE: u64 = 2_000;

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

fn limits(overall: Option<u64>) -> Limits {
    Limits {
        job: Duration::from_millis(JOB),
        cleanup: Duration::from_millis(CLEAN),
        overall: overall.map(Duration::from_millis),
    }
}

fn plan(id: &str, overall: Option<u64>) -> SessionInput {
    SessionInput::Submit(UnitPlan {
        id: id.into(),
        limits: limits(overall),
    })
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

fn completed(job: &str) -> WorkerEvent {
    WorkerEvent::Finished(JobFinished {
        job_id: job.into(),
        result: Ok(JobOutputs {
            files: vec![format!("{job}.glb")],
        }),
        cancel_requested: false,
    })
}

struct Sim {
    lifecycle: SessionLifecycle,
    config: SessionConfig,
    log: Vec<SessionCommand>,
}

impl Sim {
    fn new() -> Self {
        Self::with(SessionConfig {
            cleanup: Duration::from_millis(CLEAN),
            lifetime: Duration::from_millis(100 * JOB),
            idle: Duration::from_millis(IDLE),
            quiescence: None,
            custodian: false,
        })
    }

    /// Sessions that may serve further units on quiescence evidence.
    fn resident(lifetime: u64) -> Self {
        Self::with(SessionConfig {
            cleanup: Duration::from_millis(SESSION_CLEAN),
            lifetime: Duration::from_millis(lifetime),
            idle: Duration::from_millis(IDLE),
            quiescence: Some(Duration::from_millis(QUIET)),
            custodian: false,
        })
    }

    /// Sessions holding checkout custody: each unit's Run also waits for the monitor.
    fn custodian(mut self) -> Self {
        let config = SessionConfig {
            custodian: true,
            ..self.config()
        };
        self.lifecycle = SessionLifecycle::new(config);
        self
    }

    fn config(&self) -> SessionConfig {
        self.config
    }

    fn with(config: SessionConfig) -> Self {
        Self {
            lifecycle: SessionLifecycle::new(config),
            config,
            log: vec![],
        }
    }

    fn quiet(&mut self, ms: u64, session: u32) -> Vec<SessionCommand> {
        self.at(
            ms,
            SessionInput::Quiescent {
                session,
                sample_time: ms as f64 / 1000.0,
            },
        )
    }

    fn registered(&mut self, ms: u64, session: u32, unit: &str) -> Vec<SessionCommand> {
        self.at(
            ms,
            SessionInput::Registered {
                session,
                unit: unit.into(),
                ok: true,
            },
        )
    }

    fn at(&mut self, ms: u64, input: SessionInput) -> Vec<SessionCommand> {
        let commands = self
            .lifecycle
            .on(t(ms), input.clone())
            .unwrap_or_else(|error| panic!("{input:?}: {error:?}"));
        self.log.extend(commands.clone());
        commands
    }

    fn launch(&mut self, ms: u64, session: u32, event: LaunchEvent) -> Vec<SessionCommand> {
        self.at(
            ms,
            SessionInput::Launch(AttemptEvent {
                attempt: session,
                event,
            }),
        )
    }

    fn worker(&mut self, ms: u64, session: u32, event: WorkerEvent) -> Vec<SessionCommand> {
        self.at(
            ms,
            SessionInput::Worker {
                session,
                event: Ok(event),
            },
        )
    }

    /// Admission, the pinned worker, lease registration for `unit` and hello: `unit` runs.
    fn start(&mut self, ms: u64, session: u32, pid: u32, unit: &str) {
        assert_eq!(self.launch(ms, session, LaunchEvent::Admitted), vec![]);
        assert_eq!(
            self.launch(
                ms,
                session,
                LaunchEvent::ChildStarted {
                    worker: worker(pid)
                }
            ),
            vec![SessionCommand::Register {
                session,
                unit: unit.into(),
                worker: worker(pid)
            }]
        );
        assert_eq!(
            self.at(
                ms,
                SessionInput::Registered {
                    session,
                    unit: unit.into(),
                    ok: true
                }
            ),
            vec![]
        );
        assert_eq!(
            self.worker(
                ms,
                session,
                WorkerEvent::Ready {
                    worker_version: "w1".into()
                }
            ),
            vec![SessionCommand::Run {
                session,
                unit: unit.into()
            }]
        );
    }

    fn submits(&self) -> Vec<u32> {
        self.log
            .iter()
            .filter_map(|c| match c {
                SessionCommand::Submit { session } => Some(*session),
                _ => None,
            })
            .collect()
    }

    fn settled(&self) -> Vec<String> {
        self.log
            .iter()
            .filter_map(|c| match c {
                SessionCommand::Settled { unit } => Some(unit.clone()),
                _ => None,
            })
            .collect()
    }
}

#[test]
fn units_run_in_order_one_session_at_a_time() {
    let mut sim = Sim::new();
    assert_eq!(
        sim.at(0, plan("a", None)),
        vec![SessionCommand::Submit { session: 1 }]
    );
    assert_eq!(
        sim.at(0, plan("b", None)),
        vec![],
        "one admission at a time"
    );
    sim.at(0, SessionInput::Close);
    sim.start(10, 1, 101, "a");
    assert_eq!(
        sim.worker(100, 1, completed("a")),
        vec![SessionCommand::Shutdown { session: 1 }]
    );
    sim.worker(110, 1, WorkerEvent::Stopped);
    sim.launch(120, 1, exited(101));
    assert_eq!(
        sim.launch(130, 1, confirmed()),
        vec![
            SessionCommand::Submit { session: 2 },
            SessionCommand::Settled { unit: "a".into() }
        ],
        "the next session is queued only after the previous one is confirmed clean"
    );
    sim.start(200, 2, 202, "b");
    sim.worker(300, 2, completed("b"));
    sim.launch(310, 2, exited(202));
    sim.launch(320, 2, confirmed());
    assert!(sim.lifecycle.done());
    assert_eq!(sim.settled(), vec!["a".to_string(), "b".to_string()]);
    let a = sim.lifecycle.unit("a").unwrap();
    assert_eq!(a.outcome.end, End::Completed);
    assert_eq!(
        a.attempts,
        vec![UnitAttemptRecord {
            attempt: 1,
            session: 1,
            custody: Custody::Released,
            quiescent: None
        }]
    );
    assert_eq!(sim.lifecycle.unit("b").unwrap().attempts[0].session, 2);
}

fn exited(pid: u32) -> LaunchEvent {
    LaunchEvent::ChildExited {
        worker: worker(pid),
        exit: ExitInfo::Code(0),
        stopped_by: None,
    }
}

#[test]
fn a_crash_retry_joins_a_later_session_only_after_confirmed_cleanup() {
    let mut sim = Sim::new();
    sim.at(0, plan("a", None));
    sim.at(0, plan("b", None));
    sim.at(0, SessionInput::Close);
    sim.start(10, 1, 101, "a");
    // The pinned worker exited with no stop requested: crash evidence for "a" only.
    assert_eq!(
        sim.launch(
            100,
            1,
            LaunchEvent::ChildExited {
                worker: worker(101),
                exit: ExitInfo::Signal(9),
                stopped_by: None
            }
        ),
        vec![]
    );
    assert_eq!(
        sim.at(200, SessionInput::Tick),
        vec![],
        "no session before the receipt"
    );
    assert_eq!(
        sim.launch(300, 1, confirmed()),
        vec![SessionCommand::Submit { session: 2 }]
    );
    // The retry is first in line; its second attempt runs in session 2.
    sim.start(400, 2, 202, "a");
    sim.worker(500, 2, completed("a"));
    sim.launch(510, 2, exited(202));
    sim.launch(520, 2, confirmed());
    sim.start(600, 3, 303, "b");
    sim.worker(700, 3, completed("b"));
    sim.launch(710, 3, exited(303));
    sim.launch(720, 3, confirmed());
    assert!(sim.lifecycle.done());
    let a = sim.lifecycle.unit("a").unwrap();
    assert_eq!(a.outcome.end, End::Completed);
    assert_eq!(a.outcome.attempts, 2);
    assert_eq!(
        a.attempts.iter().map(|x| x.session).collect::<Vec<_>>(),
        vec![1, 2]
    );
    assert_eq!(sim.submits(), vec![1, 2, 3]);
}

#[test]
fn a_held_session_starts_no_further_session() {
    let mut sim = Sim::new();
    sim.at(0, plan("a", None));
    sim.at(0, plan("b", None));
    sim.at(0, SessionInput::Close);
    sim.start(10, 1, 101, "a");
    sim.launch(
        100,
        1,
        LaunchEvent::ChildExited {
            worker: worker(101),
            exit: ExitInfo::Signal(9),
            stopped_by: None,
        },
    );
    assert_eq!(
        sim.launch(200, 1, unconfirmed("tree cleanup incomplete")),
        vec![SessionCommand::Settled { unit: "b".into() }],
        "the waiting unit gives up; nothing new is queued"
    );
    let b = sim.lifecycle.unit("b").unwrap();
    assert_eq!(b.outcome.end, End::Failed(Stop::Cancelled));
    assert!(b.abort.unwrap().contains("unconfirmed"));
    assert!(b.attempts.is_empty(), "b never started");
    sim.at(100 + CLEAN, SessionInput::Tick);
    let a = sim.lifecycle.unit("a").unwrap();
    assert_eq!(
        a.outcome.cleanup,
        CleanupState::Unconfirmed(Expiry::CleanupLimit)
    );
    assert_eq!(
        a.attempts[0].custody,
        Custody::Held("tree cleanup incomplete".into())
    );
    assert_eq!(sim.submits(), vec![1]);
    assert!(sim.lifecycle.done());
}

#[test]
fn cancelling_one_waiting_unit_keeps_the_session_for_the_others() {
    let mut sim = Sim::new();
    sim.at(0, plan("a", None));
    sim.at(0, plan("b", None));
    assert_eq!(
        sim.at(5, SessionInput::CancelUnit("a".into())),
        vec![SessionCommand::Settled { unit: "a".into() }],
        "no stop: b still needs the session"
    );
    sim.start(10, 1, 101, "b");
    assert_eq!(
        sim.lifecycle.unit("a").unwrap().outcome.end,
        End::Failed(Stop::Cancelled)
    );
    // Cancelling the running unit stops the session through the guard.
    assert_eq!(
        sim.at(20, SessionInput::CancelUnit("b".into())),
        vec![SessionCommand::Stop { session: 1 }]
    );
}

#[test]
fn units_that_expire_while_waiting_withdraw_the_request_within_their_deadline() {
    let mut sim = Sim::new();
    sim.at(0, plan("a", Some(1_000)));
    sim.at(0, plan("b", Some(2_000)));
    sim.at(0, SessionInput::Close);
    assert_eq!(sim.lifecycle.queue_deadline(), Some(t(2_000)));
    assert_eq!(
        sim.at(1_000, SessionInput::Tick),
        vec![SessionCommand::Settled { unit: "a".into() }],
        "b still waits"
    );
    assert_eq!(
        sim.at(2_000, SessionInput::Tick),
        vec![
            SessionCommand::Stop { session: 1 },
            SessionCommand::Settled { unit: "b".into() }
        ]
    );
    // The withdrawn request settles no later than the last deadline: held, never released.
    assert!(sim.lifecycle.done());
    assert!(matches!(
        sim.lifecycle.sessions()[0].custody,
        Custody::Held(_)
    ));
}

#[test]
fn a_unit_after_close_or_twice_is_refused() {
    let mut sim = Sim::new();
    sim.at(0, plan("a", None));
    assert_eq!(
        sim.at(1, plan("a", None)),
        vec![SessionCommand::Refused {
            unit: "a".into(),
            reason: Refusal::DuplicateUnit
        }]
    );
    sim.at(2, SessionInput::Close);
    assert_eq!(
        sim.at(3, plan("b", None)),
        vec![SessionCommand::Refused {
            unit: "b".into(),
            reason: Refusal::Closed
        }]
    );
    assert!(sim.lifecycle.unit("b").is_none(), "nothing queued for b");
    assert_eq!(sim.submits(), vec![1]);
    let record = UnitRecord::refused("b".into(), Refusal::Closed);
    assert_eq!(record.refused, Some(Refusal::Closed));
    assert!(record.attempts.is_empty());
    assert_eq!(record.outcome.attempts, 0);
    assert_eq!(record.outcome.cleanup, CleanupState::NotNeeded);
}

#[test]
fn session_commands_never_delete_or_republish() {
    let mut sim = Sim::new();
    sim.at(0, plan("a", None));
    sim.at(0, SessionInput::Close);
    sim.start(10, 1, 101, "a");
    sim.worker(100, 1, completed("a"));
    sim.at(150, SessionInput::CancelAll);
    sim.launch(200, 1, exited(101));
    sim.launch(210, 1, confirmed());
    assert_eq!(sim.lifecycle.unit("a").unwrap().outcome.end, End::Completed);
    for command in &sim.log {
        assert!(matches!(
            command,
            SessionCommand::Submit { .. }
                | SessionCommand::Register { .. }
                | SessionCommand::Run { .. }
                | SessionCommand::Shutdown { .. }
                | SessionCommand::Stop { .. }
                | SessionCommand::Settled { .. }
        ));
    }
    assert!(!sim.log.contains(&SessionCommand::Stop { session: 1 }));
}

fn short(id: &str, job: u64, overall: Option<u64>) -> SessionInput {
    SessionInput::Submit(UnitPlan {
        id: id.into(),
        limits: Limits {
            job: Duration::from_millis(job),
            cleanup: Duration::from_millis(CLEAN),
            overall: overall.map(Duration::from_millis),
        },
    })
}

/// `a` runs and completes in session 1 (10..130 ms); session 2 is queued for `b`.
fn first_unit_done(sim: &mut Sim) {
    sim.start(10, 1, 101, "a");
    sim.worker(100, 1, completed("a"));
    sim.worker(110, 1, WorkerEvent::Stopped);
    sim.launch(120, 1, exited(101));
    assert_eq!(
        sim.launch(130, 1, confirmed()),
        vec![
            SessionCommand::Submit { session: 2 },
            SessionCommand::Settled { unit: "a".into() }
        ]
    );
}

#[test]
fn a_later_units_job_limit_counts_from_its_own_assignment() {
    let mut sim = Sim::new();
    sim.at(0, short("a", 1_000, None));
    sim.at(0, short("b", 1_000, None));
    sim.at(0, SessionInput::Close);
    first_unit_done(&mut sim);
    assert_eq!(
        sim.at(1_000, SessionInput::Tick),
        vec![],
        "b's limit has not started: it is not assigned yet"
    );
    sim.start(5_000, 2, 202, "b");
    assert_eq!(sim.at(5_999, SessionInput::Tick), vec![]);
    assert_eq!(
        sim.at(6_000, SessionInput::Tick),
        vec![SessionCommand::Stop { session: 2 }],
        "one job limit after b's own assignment"
    );
}

#[test]
fn a_later_units_capacity_wait_stays_outside_its_job_limit() {
    let mut sim = Sim::new();
    sim.at(0, short("a", 1_000, None));
    sim.at(0, short("b", 1_000, None));
    sim.at(0, SessionInput::Close);
    first_unit_done(&mut sim);
    sim.launch(200, 2, LaunchEvent::Queued);
    assert_eq!(
        sim.at(50_000, SessionInput::Tick),
        vec![],
        "waiting for capacity spends nothing"
    );
    sim.start(50_000, 2, 202, "b");
    assert_eq!(sim.at(50_999, SessionInput::Tick), vec![]);
    assert_eq!(
        sim.at(51_000, SessionInput::Tick),
        vec![SessionCommand::Stop { session: 2 }]
    );
}

#[test]
fn a_later_units_failed_registration_stops_its_run() {
    let mut sim = Sim::new();
    sim.at(0, plan("a", None));
    sim.at(0, plan("b", None));
    sim.at(0, SessionInput::Close);
    first_unit_done(&mut sim);
    sim.launch(200, 2, LaunchEvent::Admitted);
    assert_eq!(
        sim.launch(
            200,
            2,
            LaunchEvent::ChildStarted {
                worker: worker(202)
            }
        ),
        vec![SessionCommand::Register {
            session: 2,
            unit: "b".into(),
            worker: worker(202)
        }]
    );
    assert_eq!(
        sim.at(
            210,
            SessionInput::Registered {
                session: 2,
                unit: "b".into(),
                ok: false
            }
        ),
        vec![SessionCommand::Stop { session: 2 }]
    );
    sim.worker(
        220,
        2,
        WorkerEvent::Ready {
            worker_version: "w1".into(),
        },
    );
    assert!(
        !sim.log
            .iter()
            .any(|c| matches!(c, SessionCommand::Run { session: 2, .. })),
        "b never runs"
    );
    sim.launch(230, 2, confirmed());
    let b = sim.lifecycle.unit("b").unwrap();
    assert_eq!(b.outcome.end, End::Failed(Stop::Cancelled));
    assert!(b.abort.unwrap().contains("write lease"));
}

#[test]
fn hello_before_registration_waits_for_the_registration() {
    let mut sim = Sim::new();
    sim.at(0, plan("a", None));
    sim.at(0, SessionInput::Close);
    sim.launch(10, 1, LaunchEvent::Admitted);
    sim.launch(
        10,
        1,
        LaunchEvent::ChildStarted {
            worker: worker(101),
        },
    );
    assert_eq!(
        sim.worker(
            20,
            1,
            WorkerEvent::Ready {
                worker_version: "w1".into()
            }
        ),
        vec![],
        "no Run before the lease names the worker"
    );
    assert_eq!(
        sim.at(
            30,
            SessionInput::Registered {
                session: 1,
                unit: "a".into(),
                ok: true
            }
        ),
        vec![SessionCommand::Run {
            session: 1,
            unit: "a".into()
        }]
    );
}

#[test]
fn foreign_identities_and_pipe_loss_are_never_crash_evidence_for_a_unit() {
    let mut sim = Sim::new();
    sim.at(0, plan("a", None));
    sim.at(0, plan("b", None));
    sim.at(0, SessionInput::Close);
    sim.start(10, 1, 101, "a");
    assert_eq!(
        sim.at(
            50,
            SessionInput::Worker {
                session: 1,
                event: Err(WorkerFault::Disconnected("pipe closed".into())),
            }
        ),
        vec![],
        "pipe loss alone is no evidence"
    );
    assert_eq!(
        sim.launch(
            60,
            1,
            LaunchEvent::ChildExited {
                worker: worker(999),
                exit: ExitInfo::Signal(9),
                stopped_by: None
            }
        ),
        vec![SessionCommand::Stop { session: 1 }],
        "a foreign identity is an inconsistent report"
    );
    assert_eq!(
        sim.launch(70, 1, confirmed()),
        vec![
            SessionCommand::Submit { session: 2 },
            SessionCommand::Settled { unit: "a".into() }
        ]
    );
    let a = sim.lifecycle.unit("a").unwrap();
    assert_eq!(a.outcome.end, End::Failed(Stop::Protocol));
    assert_eq!(a.outcome.attempts, 1, "never retried");
    sim.start(100, 2, 202, "b");
}

#[test]
fn a_session_ended_before_admission_requeues_the_units_its_queue_limit_did_not_cover() {
    let mut sim = Sim::new();
    sim.at(0, plan("a", Some(1_000)));
    sim.at(10, plan("b", Some(600_000)));
    sim.at(10, SessionInput::Close);
    assert_eq!(sim.lifecycle.session_queue_deadline(1), Some(t(1_000)));
    assert_eq!(
        sim.at(1_000, SessionInput::Tick),
        vec![SessionCommand::Settled { unit: "a".into() }],
        "b still needs the session"
    );
    // The guard's queue window, sized for a, ends: b is not cancelled but gets a fresh session.
    assert_eq!(
        sim.launch(1_000 + CLEAN, 1, confirmed()),
        vec![SessionCommand::Submit { session: 2 }]
    );
    assert!(sim.lifecycle.unit("b").is_none(), "b is still waiting");
    assert_eq!(sim.lifecycle.session_queue_deadline(2), Some(t(600_010)));
    sim.start(7_000, 2, 202, "b");
    sim.worker(7_100, 2, completed("b"));
    sim.launch(7_200, 2, exited(202));
    sim.launch(7_300, 2, confirmed());
    assert_eq!(sim.lifecycle.unit("b").unwrap().outcome.end, End::Completed);

    // A unit the window did cover gives up when the admission owner ends early.
    let mut sim = Sim::new();
    sim.at(0, plan("c", Some(5_000)));
    sim.at(0, SessionInput::Close);
    assert_eq!(
        sim.launch(100, 1, confirmed()),
        vec![SessionCommand::Settled { unit: "c".into() }]
    );
    let c = sim.lifecycle.unit("c").unwrap();
    assert_eq!(c.outcome.end, End::Failed(Stop::Cancelled));
    assert!(c.abort.unwrap().contains("before admission"));
    assert_eq!(sim.submits(), vec![1]);
}

#[test]
fn an_expired_units_deadline_never_bounds_a_later_settlement() {
    let mut sim = Sim::new();
    sim.at(0, plan("a", Some(1_000)));
    sim.at(0, plan("b", None));
    assert_eq!(
        sim.at(1_000, SessionInput::Tick),
        vec![SessionCommand::Settled { unit: "a".into() }]
    );
    assert_eq!(
        sim.at(3_000, SessionInput::CancelUnit("b".into())),
        vec![
            SessionCommand::Stop { session: 1 },
            SessionCommand::Settled { unit: "b".into() }
        ]
    );
    assert_eq!(
        sim.lifecycle.next_deadline(),
        Some(t(3_000 + CLEAN)),
        "bounded by the cleanup limit, not a's past deadline"
    );
    assert_eq!(sim.lifecycle.sessions()[0].custody, Custody::Pending);
    assert_eq!(sim.at(3_001, plan("c", None)), vec![]);
    assert_eq!(
        sim.launch(3_100, 1, confirmed()),
        vec![SessionCommand::Submit { session: 2 }],
        "a later unit still gets a session"
    );
}

#[test]
fn a_late_confirmed_receipt_never_reopens_a_held_lifecycle_or_changes_a_published_record() {
    let mut sim = Sim::new();
    sim.at(0, plan("a", None));
    sim.at(0, plan("b", None));
    sim.start(10, 1, 101, "a");
    assert_eq!(
        sim.worker(100, 1, completed("a")),
        vec![SessionCommand::Shutdown { session: 1 }]
    );
    // No receipt within the limit: held, and b (no deadline of its own) gives up in this same
    // input, with nothing further to wake on.
    assert_eq!(
        sim.at(100 + CLEAN, SessionInput::Tick),
        vec![
            SessionCommand::Stop { session: 1 },
            SessionCommand::Settled { unit: "a".into() },
            SessionCommand::Settled { unit: "b".into() }
        ]
    );
    assert_eq!(sim.lifecycle.next_deadline(), None);
    let b = sim.lifecycle.unit("b").unwrap();
    assert!(b.abort.unwrap().contains("unconfirmed"));
    let published = sim.lifecycle.unit("a").unwrap();
    assert!(matches!(published.attempts[0].custody, Custody::Held(_)));
    assert_eq!(sim.launch(9_000, 1, confirmed()), vec![]);
    let Custody::Held(reason) = sim.lifecycle.sessions()[0].custody.clone() else {
        panic!("the session record stays held");
    };
    assert!(
        reason.contains("a confirmed cleanup receipt arrived late, at 9000 ms"),
        "the late receipt is kept as evidence in the held record: {reason}"
    );
    assert_eq!(sim.lifecycle.unit("a").unwrap(), published, "unchanged");
    assert_eq!(
        sim.at(9_100, plan("c", None)),
        vec![SessionCommand::Settled { unit: "c".into() }]
    );
    assert_eq!(sim.submits(), vec![1]);
}

#[test]
fn a_unit_already_past_its_deadline_is_never_requeued() {
    let mut sim = Sim::new();
    sim.at(0, plan("a", Some(1_000)));
    sim.at(10, plan("b", Some(1_990)));
    sim.at(10, SessionInput::Close);
    // The admission owner ends before admission at 2 s, before any tick reached b's deadline.
    assert_eq!(
        sim.launch(2_000, 1, confirmed()),
        vec![
            SessionCommand::Settled { unit: "a".into() },
            SessionCommand::Settled { unit: "b".into() }
        ]
    );
    assert_eq!(
        sim.lifecycle.unit("b").unwrap().outcome.end,
        End::Failed(Stop::OverallDeadline)
    );
    assert_eq!(sim.submits(), vec![1], "no session for an expired unit");
}

fn cancelled(job: &str) -> WorkerEvent {
    WorkerEvent::Finished(JobFinished {
        job_id: job.into(),
        result: Err(WorkerFailure {
            kind: FailureKind::Cancelled,
            message: "cancelled".into(),
        }),
        cancel_requested: true,
    })
}

fn register(session: u32, unit: &str, pid: u32) -> SessionCommand {
    SessionCommand::Register {
        session,
        unit: unit.into(),
        worker: worker(pid),
    }
}

#[test]
fn a_reused_session_runs_the_next_unit_only_after_quiescence_evidence() {
    let mut sim = Sim::resident(100 * JOB);
    sim.at(0, plan("a", None));
    sim.at(0, plan("b", None));
    sim.at(0, SessionInput::Close);
    sim.start(10, 1, 101, "a");
    assert_eq!(
        sim.quiet(50, 1),
        vec![],
        "evidence before the terminal reply counts for nothing"
    );
    assert_eq!(
        sim.worker(100, 1, completed("a")),
        vec![],
        "b waits: the worker stays up for it"
    );
    assert_eq!(
        sim.at(150, SessionInput::Tick),
        vec![],
        "no Run before evidence"
    );
    assert_eq!(
        sim.quiet(160, 1),
        vec![
            register(1, "b", 101),
            SessionCommand::Settled { unit: "a".into() }
        ],
        "a settles by quiescence and b joins the same session"
    );
    let a = sim.lifecycle.unit("a").unwrap();
    assert_eq!(a.outcome.end, End::Completed);
    assert_eq!(a.attempts[0].quiescent, Some(0.16));
    assert_eq!(a.attempts[0].custody, Custody::Pending);
    assert_eq!(
        sim.registered(170, 1, "b"),
        vec![SessionCommand::Run {
            session: 1,
            unit: "b".into()
        }]
    );
    // The last unit, closed: the session ends as a one-unit session would.
    assert_eq!(
        sim.worker(300, 1, completed("b")),
        vec![SessionCommand::Shutdown { session: 1 }]
    );
    sim.worker(310, 1, WorkerEvent::Stopped);
    sim.launch(320, 1, exited(101));
    assert_eq!(
        sim.launch(330, 1, confirmed()),
        vec![SessionCommand::Settled { unit: "b".into() }]
    );
    assert!(sim.lifecycle.done());
    assert_eq!(sim.submits(), vec![1], "one admission for both units");
    assert_eq!(sim.lifecycle.unit("b").unwrap().attempts[0].session, 1);
}

#[test]
fn without_quiescence_evidence_the_session_stops_and_the_receipt_settles_the_unit() {
    let mut sim = Sim::resident(100 * JOB);
    sim.at(0, plan("a", None));
    sim.at(0, plan("b", None));
    sim.at(0, SessionInput::Close);
    sim.start(10, 1, 101, "a");
    assert_eq!(sim.worker(100, 1, completed("a")), vec![]);
    assert_eq!(sim.lifecycle.next_deadline(), Some(t(100 + QUIET)));
    assert_eq!(
        sim.at(100 + QUIET, SessionInput::Tick),
        vec![SessionCommand::Stop { session: 1 }]
    );
    assert_eq!(
        sim.quiet(1_200, 1),
        vec![],
        "too late: the session is stopping"
    );
    sim.launch(1_300, 1, exited(101));
    assert_eq!(
        sim.launch(1_400, 1, confirmed()),
        vec![
            SessionCommand::Submit { session: 2 },
            SessionCommand::Settled { unit: "a".into() }
        ]
    );
    let a = sim.lifecycle.unit("a").unwrap();
    assert_eq!(a.attempts[0].custody, Custody::Released);
    assert_eq!(a.attempts[0].quiescent, None);
    sim.start(1_500, 2, 202, "b");
}

#[test]
fn evidence_past_its_bound_before_any_tick_never_settles_the_unit_or_reuses_the_worker() {
    // The reviewer's timeline: a completes at 100 ms with a 1 s bound, and its evidence arrives
    // at 1200 ms before any Tick.
    let mut sim = Sim::resident(100 * JOB);
    sim.at(0, plan("a", None));
    sim.at(0, plan("b", None));
    sim.at(0, SessionInput::Close);
    sim.start(10, 1, 101, "a");
    assert_eq!(sim.worker(100, 1, completed("a")), vec![]);
    assert_eq!(sim.lifecycle.next_deadline(), Some(t(100 + QUIET)));
    assert_eq!(
        sim.quiet(1_200, 1),
        vec![SessionCommand::Stop { session: 1 }],
        "too late: the session stops instead of running b on the same worker"
    );
    assert_eq!(sim.lifecycle.unit("a").unwrap().attempts[0].quiescent, None);
    sim.launch(1_300, 1, exited(101));
    assert_eq!(
        sim.launch(1_400, 1, confirmed()),
        vec![
            SessionCommand::Submit { session: 2 },
            SessionCommand::Settled { unit: "a".into() }
        ],
        "a settles only by the receipt; b gets a fresh session"
    );
}

#[test]
fn a_reusable_units_quiescence_wait_never_outlasts_its_overall_deadline() {
    // The reviewer's timeline: a completes at 100 ms with an overall deadline of 200 ms, a Tick
    // comes at 200 ms, and evidence arrives at 300 ms.
    let mut sim = Sim::resident(100 * JOB);
    sim.at(0, plan("a", Some(200)));
    sim.at(0, plan("b", None));
    sim.at(0, SessionInput::Close);
    sim.start(10, 1, 101, "a");
    assert_eq!(sim.worker(100, 1, completed("a")), vec![]);
    assert_eq!(
        sim.lifecycle.next_deadline(),
        Some(t(200)),
        "the next wake-up is the overall deadline (the policy's own; not the cap proof, which is \
         the late-evidence checks below)"
    );
    let at_deadline = sim.at(200, SessionInput::Tick);
    assert!(
        at_deadline.contains(&SessionCommand::Stop { session: 1 }),
        "{at_deadline:?}"
    );
    let late = sim.quiet(300, 1);
    assert!(
        !late.iter().any(|command| matches!(
            command,
            SessionCommand::Register { .. } | SessionCommand::Run { .. }
        )),
        "{late:?}"
    );
    let a = sim.lifecycle.unit("a").unwrap();
    assert_eq!(
        a.attempts[0].quiescent, None,
        "never settled by late evidence"
    );
    assert_ne!(a.attempts[0].custody, Custody::Released);
}

#[test]
fn cancelling_a_running_unit_cancels_only_its_job_when_others_wait() {
    let mut sim = Sim::resident(100 * JOB);
    sim.at(0, plan("a", None));
    sim.at(0, plan("b", None));
    sim.start(10, 1, 101, "a");
    assert_eq!(
        sim.at(50, SessionInput::CancelUnit("a".into())),
        vec![SessionCommand::Cancel {
            session: 1,
            unit: "a".into()
        }]
    );
    assert_eq!(
        sim.quiet(55, 1),
        vec![],
        "evidence before the cancelled job's terminal reply counts for nothing"
    );
    assert_eq!(sim.worker(60, 1, cancelled("a")), vec![]);
    assert_eq!(
        sim.quiet(70, 1),
        vec![
            register(1, "b", 101),
            SessionCommand::Settled { unit: "a".into() }
        ]
    );
    let a = sim.lifecycle.unit("a").unwrap();
    assert_eq!(a.outcome.end, End::Failed(Stop::Cancelled));
    assert_eq!(a.outcome.cleanup, CleanupState::Finished);
    // b's job limit counts from its own assignment at 70 ms, and also cancels only its job.
    sim.registered(80, 1, "b");
    assert_eq!(sim.at(70 + JOB - 1, SessionInput::Tick), vec![]);
    assert_eq!(
        sim.at(70 + JOB, SessionInput::Tick),
        vec![SessionCommand::Cancel {
            session: 1,
            unit: "b".into()
        }]
    );
    sim.worker(70 + JOB + 10, 1, cancelled("b"));
    sim.quiet(70 + JOB + 20, 1);
    assert_eq!(
        sim.lifecycle.unit("b").unwrap().outcome.end,
        End::Failed(Stop::JobLimit)
    );
    assert!(!sim.log.contains(&SessionCommand::Stop { session: 1 }));
    assert_eq!(sim.submits(), vec![1]);
}

#[test]
fn every_session_serves_one_unit_without_quiescence_evidence() {
    let mut sim = Sim::new();
    sim.at(0, plan("a", None));
    sim.at(0, plan("b", None));
    sim.start(10, 1, 101, "a");
    assert_eq!(
        sim.worker(100, 1, completed("a")),
        vec![SessionCommand::Shutdown { session: 1 }]
    );
    assert_eq!(
        sim.quiet(110, 1),
        vec![],
        "evidence is not configured: ignored"
    );
    assert!(!sim.log.iter().any(|c| matches!(
        c,
        SessionCommand::Register { session: 1, unit, .. } if unit == "b"
    )));
}

#[test]
fn an_open_idle_session_waits_for_more_units_then_shuts_down() {
    let mut sim = Sim::resident(100 * JOB);
    sim.at(0, plan("a", None));
    sim.start(10, 1, 101, "a");
    sim.worker(100, 1, completed("a"));
    assert_eq!(
        sim.quiet(110, 1),
        vec![SessionCommand::Settled { unit: "a".into() }]
    );
    assert_eq!(sim.lifecycle.next_deadline(), Some(t(110 + IDLE)));
    assert_eq!(
        sim.at(110 + IDLE / 2, plan("b", None)),
        vec![register(1, "b", 101)],
        "a unit submitted while idle joins at once"
    );
    sim.registered(1_200, 1, "b");
    sim.worker(1_300, 1, completed("b"));
    assert_eq!(
        sim.quiet(1_400, 1),
        vec![SessionCommand::Settled { unit: "b".into() }]
    );
    assert_eq!(sim.at(1_400 + IDLE - 1, SessionInput::Tick), vec![]);
    assert_eq!(
        sim.at(1_400 + IDLE, SessionInput::Tick),
        vec![SessionCommand::Shutdown { session: 1 }]
    );
}

#[test]
fn a_later_unit_that_does_not_fit_the_sessions_lifetime_gets_a_fresh_session() {
    // Admitted at 10 ms; the worst case (job, quiescence bound, session cleanup) fits with 100 ms
    // to spare, which is gone by 200 ms.
    let mut sim = Sim::resident(JOB + QUIET + SESSION_CLEAN + 100);
    sim.at(0, plan("a", None));
    sim.at(0, plan("b", None));
    sim.at(0, SessionInput::Close);
    sim.start(10, 1, 101, "a");
    sim.worker(100, 1, completed("a"));
    assert_eq!(
        sim.quiet(200, 1),
        vec![
            SessionCommand::Shutdown { session: 1 },
            SessionCommand::Settled { unit: "a".into() }
        ],
        "b's limits no longer fit"
    );
    sim.worker(210, 1, WorkerEvent::Stopped);
    sim.launch(220, 1, exited(101));
    assert_eq!(
        sim.launch(230, 1, confirmed()),
        vec![SessionCommand::Submit { session: 2 }]
    );
    sim.start(300, 2, 202, "b");
}

#[test]
fn a_cancel_the_worker_cannot_read_stops_the_session_and_the_receipt_settles_the_unit() {
    // C3: a running Unreal job owns the game thread, so `cancel` is never answered.
    let mut sim = Sim::resident(100 * JOB);
    sim.at(0, plan("a", None));
    sim.at(0, plan("b", None));
    sim.at(0, SessionInput::Close);
    sim.start(10, 1, 101, "a");
    assert_eq!(
        sim.at(50, SessionInput::CancelUnit("a".into())),
        vec![SessionCommand::Cancel {
            session: 1,
            unit: "a".into()
        }]
    );
    assert_eq!(
        sim.at(50 + QUIET, SessionInput::Tick),
        vec![SessionCommand::Stop { session: 1 }],
        "no terminal reply and no evidence in time: the guard stops the session"
    );
    sim.launch(
        60 + QUIET,
        1,
        LaunchEvent::ChildExited {
            worker: worker(101),
            exit: ExitInfo::Signal(9),
            stopped_by: Some(StoppedBy::Cancel),
        },
    );
    assert_eq!(
        sim.launch(70 + QUIET, 1, confirmed()),
        vec![
            SessionCommand::Submit { session: 2 },
            SessionCommand::Settled { unit: "a".into() }
        ],
        "the remaining unit gets a fresh session"
    );
    let a = sim.lifecycle.unit("a").unwrap();
    assert_eq!(a.outcome.end, End::Failed(Stop::Cancelled));
    assert_eq!(a.outcome.cleanup, CleanupState::Finished);
    assert_eq!(a.attempts[0].custody, Custody::Released);
    sim.start(2_000, 2, 202, "b");
}

#[test]
fn a_worker_that_exits_after_completed_ends_its_session_without_crash_evidence() {
    // C3: a worker that cannot reset replies `completed` and then exits cleanly.
    let mut sim = Sim::resident(100 * JOB);
    sim.at(0, plan("a", None));
    sim.at(0, plan("b", None));
    sim.at(0, SessionInput::Close);
    sim.start(10, 1, 101, "a");
    assert_eq!(sim.worker(100, 1, completed("a")), vec![]);
    assert_eq!(
        sim.launch(110, 1, exited(101)),
        vec![],
        "not crash evidence"
    );
    assert_eq!(
        sim.quiet(120, 1),
        vec![],
        "no reuse after the worker exited"
    );
    assert_eq!(
        sim.launch(130, 1, confirmed()),
        vec![
            SessionCommand::Submit { session: 2 },
            SessionCommand::Settled { unit: "a".into() }
        ]
    );
    let a = sim.lifecycle.unit("a").unwrap();
    assert_eq!(a.outcome.end, End::Completed);
    assert_eq!(a.outcome.attempts, 1, "never retried");
    assert_eq!(
        a.attempts[0].custody,
        Custody::Released,
        "settled by the receipt"
    );
    sim.start(200, 2, 202, "b");
}

fn limited(id: &str, job: u64, cleanup: u64) -> SessionInput {
    SessionInput::Submit(UnitPlan {
        id: id.into(),
        limits: Limits {
            job: Duration::from_millis(job),
            cleanup: Duration::from_millis(cleanup),
            overall: None,
        },
    })
}

/// a runs from 10 ms and is quiescent at 200 ms; b (job JOB, unit cleanup 50 s, unlike the
/// session's 3 s) then needs 200 + JOB + QUIET + SESSION_CLEAN of a session admitted at 10 ms.
fn second_joins(lifetime: u64) -> Vec<SessionCommand> {
    let mut sim = Sim::resident(lifetime);
    sim.at(0, plan("a", None));
    assert_eq!(sim.at(0, limited("b", JOB, 50_000)), vec![]);
    sim.at(0, SessionInput::Close);
    sim.start(10, 1, 101, "a");
    sim.worker(100, 1, completed("a"));
    sim.quiet(200, 1)
}

#[test]
fn the_lifetime_fit_counts_the_job_the_quiescence_bound_and_the_session_cleanup() {
    let exact = JOB + QUIET + SESSION_CLEAN + 190;
    assert_eq!(
        second_joins(exact),
        vec![
            register(1, "b", 101),
            SessionCommand::Settled { unit: "a".into() }
        ],
        "an exact fit joins"
    );
    assert_eq!(
        second_joins(exact - 1),
        vec![
            SessionCommand::Shutdown { session: 1 },
            SessionCommand::Settled { unit: "a".into() }
        ],
        "one millisecond short: a fresh session instead"
    );
}

#[test]
fn a_unit_a_session_could_never_serve_is_refused_at_submission() {
    let mut sim = Sim::resident(JOB + QUIET + SESSION_CLEAN);
    assert_eq!(
        sim.at(0, limited("fits", JOB, QUIET + SESSION_CLEAN)),
        vec![SessionCommand::Submit { session: 1 }],
        "the exact worst case and the exact cleanup bound are accepted"
    );
    assert_eq!(
        sim.at(0, limited("short_cleanup", JOB, QUIET + SESSION_CLEAN - 1)),
        vec![SessionCommand::Refused {
            unit: "short_cleanup".into(),
            reason: Refusal::CleanupBelowQuiescence
        }],
        "an unanswered cancel would pass its cleanup limit before the receipt"
    );
    assert_eq!(
        sim.at(0, limited("too_long", JOB + 1, CLEAN)),
        vec![SessionCommand::Refused {
            unit: "too_long".into(),
            reason: Refusal::NeverFits
        }],
        "the first unit too: it could never fit a fresh session"
    );
    assert!(sim.lifecycle.unit("short_cleanup").is_none());
    assert_eq!(sim.submits(), vec![1]);

    // One unit per session: only the job limit must fit the lifetime.
    let mut sim = Sim::new();
    assert_eq!(
        sim.at(0, limited("huge", 100 * JOB + 1, CLEAN)),
        vec![SessionCommand::Refused {
            unit: "huge".into(),
            reason: Refusal::NeverFits
        }]
    );
}

#[test]
fn a_failed_preparation_ends_the_unit_without_a_run() {
    // On a reused session: b's registration succeeded, but its attempt's request could not be
    // prepared. b never runs, and the session stops as after a failed registration.
    let mut sim = Sim::resident(100 * JOB);
    sim.at(0, plan("a", None));
    sim.at(0, plan("b", None));
    sim.at(0, SessionInput::Close);
    sim.start(10, 1, 101, "a");
    sim.worker(100, 1, completed("a"));
    assert_eq!(
        sim.quiet(160, 1),
        vec![
            register(1, "b", 101),
            SessionCommand::Settled { unit: "a".into() }
        ]
    );
    assert_eq!(sim.lifecycle.unit_attempt("b"), Some(1));
    assert_eq!(
        sim.at(
            170,
            SessionInput::PrepareFailed {
                session: 1,
                unit: "b".into(),
                reason: "staging failed".into()
            }
        ),
        vec![SessionCommand::Stop { session: 1 }]
    );
    sim.launch(180, 1, exited(101));
    assert_eq!(
        sim.launch(190, 1, confirmed()),
        vec![SessionCommand::Settled { unit: "b".into() }]
    );
    assert!(sim.lifecycle.done());
    assert!(
        !sim.log
            .iter()
            .any(|c| matches!(c, SessionCommand::Run { unit, .. } if unit == "b")),
        "b never runs"
    );
    let b = sim.lifecycle.unit("b").unwrap();
    assert_eq!(b.outcome.end, End::Failed(Stop::Cancelled));
    assert_eq!(b.outcome.attempts, 1);
    assert!(
        b.abort
            .unwrap()
            .contains("could not be prepared: staging failed")
    );
    assert_eq!(sim.submits(), vec![1], "never retried");
}

#[test]
fn a_crash_in_a_reused_session_retries_in_a_later_session_and_requeues_the_rest() {
    let mut sim = Sim::resident(100 * JOB);
    for id in ["a", "b", "c"] {
        sim.at(0, plan(id, None));
    }
    sim.at(0, SessionInput::Close);
    sim.start(10, 1, 101, "a");
    sim.worker(100, 1, completed("a"));
    sim.quiet(160, 1);
    assert_eq!(
        sim.registered(170, 1, "b"),
        vec![SessionCommand::Run {
            session: 1,
            unit: "b".into()
        }]
    );
    // The reused worker exits mid-job with no stop requested: crash evidence for b only.
    assert_eq!(
        sim.launch(
            200,
            1,
            LaunchEvent::ChildExited {
                worker: worker(101),
                exit: ExitInfo::Signal(9),
                stopped_by: None
            }
        ),
        vec![]
    );
    assert_eq!(
        sim.at(250, SessionInput::Tick),
        vec![],
        "no session before the receipt"
    );
    assert_eq!(
        sim.launch(300, 1, confirmed()),
        vec![SessionCommand::Submit { session: 2 }],
        "b's retry and c wait for one fresh session"
    );
    assert_eq!(sim.lifecycle.unit_attempt("b"), Some(1));
    // The retry is first in line, then c joins the same session after quiescence.
    sim.start(400, 2, 202, "b");
    assert_eq!(sim.lifecycle.unit_attempt("b"), Some(2));
    assert_eq!(sim.worker(500, 2, completed("b")), vec![]);
    assert_eq!(
        sim.quiet(560, 2),
        vec![
            register(2, "c", 202),
            SessionCommand::Settled { unit: "b".into() }
        ]
    );
    sim.registered(570, 2, "c");
    assert_eq!(
        sim.worker(600, 2, completed("c")),
        vec![SessionCommand::Shutdown { session: 2 }]
    );
    sim.worker(610, 2, WorkerEvent::Stopped);
    sim.launch(620, 2, exited(202));
    assert_eq!(
        sim.launch(630, 2, confirmed()),
        vec![SessionCommand::Settled { unit: "c".into() }]
    );
    assert!(sim.lifecycle.done());
    let b = sim.lifecycle.unit("b").unwrap();
    assert_eq!(b.outcome.end, End::Completed);
    assert_eq!(b.outcome.attempts, 2);
    assert_eq!(
        b.attempts.iter().map(|x| x.session).collect::<Vec<_>>(),
        vec![1, 2]
    );
    assert_eq!(b.attempts[0].custody, Custody::Released);
    assert_eq!(sim.lifecycle.unit("c").unwrap().attempts[0].session, 2);
    assert_eq!(sim.submits(), vec![1, 2]);
}

fn monitor(pid: u32) -> ProcessIdentity {
    ProcessIdentity {
        pid,
        boot: "boot-1".into(),
        started: format!("monitor-{pid}"),
    }
}

fn monitored(pid: u32) -> LaunchEvent {
    LaunchEvent::Monitor {
        monitor: monitor(pid),
        invocation: "a".repeat(32),
    }
}

fn register_monitor(session: u32, unit: &str, pid: u32) -> SessionCommand {
    SessionCommand::RegisterMonitor {
        session,
        unit: unit.into(),
        monitor: monitor(pid),
    }
}

fn monitor_registered(session: u32, unit: &str, ok: bool) -> SessionInput {
    SessionInput::MonitorRegistered {
        session,
        unit: unit.into(),
        ok,
    }
}

fn ready() -> WorkerEvent {
    WorkerEvent::Ready {
        worker_version: "w1".into(),
    }
}

fn runs(sim: &Sim) -> usize {
    sim.log
        .iter()
        .filter(|c| matches!(c, SessionCommand::Run { .. }))
        .count()
}

#[test]
fn a_custodian_session_runs_only_after_its_monitor_is_registered() {
    let mut sim = Sim::new().custodian();
    sim.at(0, plan("a", None));
    sim.at(0, plan("b", None));
    sim.at(0, SessionInput::Close);
    sim.launch(10, 1, LaunchEvent::Admitted);
    assert_eq!(
        sim.launch(
            10,
            1,
            LaunchEvent::ChildStarted {
                worker: worker(101)
            }
        ),
        vec![register(1, "a", 101)]
    );
    assert_eq!(sim.registered(20, 1, "a"), vec![]);
    assert_eq!(
        sim.worker(30, 1, ready()),
        vec![],
        "no Run before the custody monitor is registered"
    );
    assert_eq!(
        sim.launch(40, 1, monitored(900)),
        vec![register_monitor(1, "a", 900)]
    );
    assert_eq!(
        sim.at(50, monitor_registered(1, "a", true)),
        vec![SessionCommand::Run {
            session: 1,
            unit: "a".into()
        }]
    );
    assert_eq!(
        sim.launch(60, 1, monitored(900)),
        vec![],
        "the same identity again changes nothing"
    );
    sim.worker(100, 1, completed("a"));
    sim.worker(110, 1, WorkerEvent::Stopped);
    sim.launch(120, 1, exited(101));
    sim.launch(130, 1, confirmed());
    // The next session's monitor, registered before its worker this time: the Run still waits
    // for both registrations and hello.
    sim.launch(200, 2, LaunchEvent::Admitted);
    sim.launch(
        200,
        2,
        LaunchEvent::ChildStarted {
            worker: worker(202),
        },
    );
    assert_eq!(
        sim.launch(210, 2, monitored(902)),
        vec![register_monitor(2, "b", 902)]
    );
    assert_eq!(sim.at(220, monitor_registered(2, "b", true)), vec![]);
    assert_eq!(sim.worker(230, 2, ready()), vec![]);
    assert_eq!(
        sim.registered(240, 2, "b"),
        vec![SessionCommand::Run {
            session: 2,
            unit: "b".into()
        }]
    );

    // A reused session registers its known monitor for each later unit at assignment.
    let mut sim = Sim::resident(100 * JOB).custodian();
    sim.at(0, plan("a", None));
    sim.at(0, plan("b", None));
    sim.at(0, SessionInput::Close);
    sim.launch(10, 1, LaunchEvent::Admitted);
    sim.launch(
        10,
        1,
        LaunchEvent::ChildStarted {
            worker: worker(101),
        },
    );
    sim.registered(10, 1, "a");
    sim.launch(10, 1, monitored(900));
    sim.at(10, monitor_registered(1, "a", true));
    assert_eq!(runs(&sim), 0, "hello is still missing");
    sim.worker(20, 1, ready());
    sim.worker(100, 1, completed("a"));
    assert_eq!(
        sim.quiet(160, 1),
        vec![
            register(1, "b", 101),
            register_monitor(1, "b", 900),
            SessionCommand::Settled { unit: "a".into() }
        ]
    );
    assert_eq!(sim.registered(170, 1, "b"), vec![]);
    assert_eq!(
        sim.at(180, monitor_registered(1, "b", true)),
        vec![SessionCommand::Run {
            session: 1,
            unit: "b".into()
        }]
    );
}

/// A custodian session at hello with a's worker registered, before any monitor.
fn waiting_for_monitor() -> Sim {
    let mut sim = Sim::new().custodian();
    sim.at(0, plan("a", None));
    sim.at(0, SessionInput::Close);
    sim.launch(10, 1, LaunchEvent::Admitted);
    sim.launch(
        10,
        1,
        LaunchEvent::ChildStarted {
            worker: worker(101),
        },
    );
    sim.registered(20, 1, "a");
    sim.worker(30, 1, ready());
    sim
}

#[test]
fn a_missing_changed_or_unregistered_monitor_never_runs_the_unit() {
    // The registration fails: no Run, and the session stops.
    let mut sim = waiting_for_monitor();
    sim.launch(40, 1, monitored(900));
    assert_eq!(
        sim.at(50, monitor_registered(1, "a", false)),
        vec![SessionCommand::Stop { session: 1 }]
    );
    sim.launch(60, 1, exited(101));
    sim.launch(70, 1, confirmed());
    let a = sim.lifecycle.unit("a").unwrap();
    assert_eq!(a.outcome.end, End::Failed(Stop::Cancelled));
    assert!(a.abort.unwrap().contains("custody monitor"));
    assert_eq!(runs(&sim), 0);

    // A second, different identity is a guard fault.
    let mut sim = waiting_for_monitor();
    sim.launch(40, 1, monitored(900));
    assert_eq!(
        sim.launch(45, 1, monitored(901)),
        vec![SessionCommand::Stop { session: 1 }]
    );
    sim.at(50, monitor_registered(1, "a", true));
    assert_eq!(runs(&sim), 0, "nothing runs on a broken identity");

    // An identity reported before the pinned worker, or without custody, is a guard fault too.
    let mut sim = Sim::new().custodian();
    sim.at(0, plan("a", None));
    sim.launch(10, 1, LaunchEvent::Admitted);
    assert_eq!(
        sim.launch(20, 1, monitored(900)),
        vec![SessionCommand::Stop { session: 1 }]
    );
    let mut sim = Sim::new();
    sim.at(0, plan("a", None));
    sim.launch(10, 1, LaunchEvent::Admitted);
    sim.launch(
        10,
        1,
        LaunchEvent::ChildStarted {
            worker: worker(101),
        },
    );
    assert_eq!(
        sim.launch(20, 1, monitored(900)),
        vec![SessionCommand::Stop { session: 1 }]
    );

    // No identity at all: the unit never runs, and its job limit ends it.
    let mut sim = waiting_for_monitor();
    assert_eq!(
        sim.at(10 + JOB, SessionInput::Tick),
        vec![SessionCommand::Stop { session: 1 }]
    );
    assert_eq!(runs(&sim), 0);
}

fn protocol_fault() -> SessionInput {
    SessionInput::Worker {
        session: 1,
        event: Err(WorkerFault::Protocol("malformed frame".into())),
    }
}

fn starts_another_unit(commands: &[SessionCommand]) -> bool {
    commands.iter().any(|command| {
        matches!(
            command,
            SessionCommand::Register { .. } | SessionCommand::Run { .. }
        )
    })
}

#[test]
fn no_run_path_runs_a_unit_at_or_past_its_overall_deadline() {
    // The reviewer's timeline (overall deadline 200 ms, the last registration or hello at
    // 201 ms) on each of the three paths that can send a Run, before, at and past the bound.
    for path in ["ready", "registered", "monitor"] {
        for (at, should_run) in [(199, true), (200, false), (201, false)] {
            let mut sim = if path == "monitor" {
                Sim::new().custodian()
            } else {
                Sim::new()
            };
            sim.at(0, plan("a", Some(200)));
            sim.at(0, SessionInput::Close);
            sim.launch(10, 1, LaunchEvent::Admitted);
            sim.launch(
                10,
                1,
                LaunchEvent::ChildStarted {
                    worker: worker(101),
                },
            );
            let last = match path {
                "ready" => {
                    sim.registered(10, 1, "a");
                    sim.worker(at, 1, ready())
                }
                "registered" => {
                    sim.worker(10, 1, ready());
                    sim.registered(at, 1, "a")
                }
                _ => {
                    sim.registered(10, 1, "a");
                    sim.worker(10, 1, ready());
                    sim.launch(10, 1, monitored(900));
                    sim.at(at, monitor_registered(1, "a", true))
                }
            };
            let ran = last.contains(&SessionCommand::Run {
                session: 1,
                unit: "a".into(),
            });
            assert_eq!(ran, should_run, "{path} at {at} ms: {last:?}");
            if should_run {
                continue;
            }
            assert!(
                last.contains(&SessionCommand::Stop { session: 1 }),
                "{path} at {at} ms: {last:?}"
            );
            sim.launch(at + 10, 1, exited(101));
            sim.launch(at + 20, 1, confirmed());
            assert_eq!(runs(&sim), 0, "{path} at {at} ms");
            assert_eq!(
                sim.lifecycle.unit("a").unwrap().outcome.end,
                End::Failed(Stop::OverallDeadline),
                "{path} at {at} ms"
            );
        }
    }
}

#[test]
fn a_refreshed_quiet_window_never_outlasts_the_units_cleanup_limit() {
    // Cook-probe's timeline: quiescence 1000 ms, session cleanup 100 ms, unit cleanup 1100 ms
    // (the admitted minimum). A is cancelled at 100 ms (its cleanup limit is 1200 ms), its
    // cancelled terminal arrives at 1090 ms, and evidence arrives with no Tick before, at or
    // after the cleanup limit.
    let unit = |id: &str| {
        SessionInput::Submit(UnitPlan {
            id: id.into(),
            limits: Limits {
                job: Duration::from_millis(JOB),
                cleanup: Duration::from_millis(1_100),
                overall: None,
            },
        })
    };
    for (at, settles) in [(1_150, true), (1_200, false), (1_300, false)] {
        let mut sim = Sim::with(SessionConfig {
            cleanup: Duration::from_millis(100),
            lifetime: Duration::from_millis(100 * JOB),
            idle: Duration::from_millis(IDLE),
            quiescence: Some(Duration::from_millis(QUIET)),
            custodian: false,
        });
        sim.at(0, unit("a"));
        sim.at(0, unit("b"));
        sim.at(0, SessionInput::Close);
        sim.start(10, 1, 101, "a");
        assert_eq!(
            sim.at(100, SessionInput::CancelUnit("a".into())),
            vec![SessionCommand::Cancel {
                session: 1,
                unit: "a".into()
            }]
        );
        assert_eq!(sim.worker(1_090, 1, cancelled("a")), vec![]);
        let late = sim.quiet(at, 1);
        assert_eq!(
            late.contains(&register(1, "b", 101)),
            settles,
            "evidence at {at} ms: {late:?}"
        );
        if settles {
            let a = sim.lifecycle.unit("a").unwrap();
            assert_eq!(a.attempts[0].quiescent, Some(at as f64 / 1000.0));
        } else {
            assert!(
                late.contains(&SessionCommand::Stop { session: 1 }),
                "evidence at {at} ms: {late:?}"
            );
            // Still cleaning up, so it has no record yet: never settled by the late evidence.
            assert!(sim.lifecycle.unit("a").is_none(), "evidence at {at} ms");
        }
    }
}

#[test]
fn a_broken_or_lost_protocol_poisons_the_session_in_every_phase() {
    // A protocol fault while the completed unit awaits evidence, while its cancelled job cleans
    // up, and a lost response stream while it awaits evidence: no later evidence lets the
    // session take b.
    for case in ["quiescing", "cleaning-up", "disconnected"] {
        let mut sim = Sim::resident(100 * JOB);
        sim.at(0, plan("a", None));
        sim.at(0, plan("b", None));
        sim.at(0, SessionInput::Close);
        sim.start(10, 1, 101, "a");
        let mut later = vec![];
        match case {
            "quiescing" => {
                assert_eq!(sim.worker(100, 1, completed("a")), vec![]);
                let fault = sim.at(200, protocol_fault());
                assert!(
                    fault.contains(&SessionCommand::Stop { session: 1 }),
                    "{case}: {fault:?}"
                );
            }
            "cleaning-up" => {
                sim.at(100, SessionInput::CancelUnit("a".into()));
                let fault = sim.at(200, protocol_fault());
                assert!(
                    fault.contains(&SessionCommand::Stop { session: 1 }),
                    "{case}: {fault:?}"
                );
                later.extend(sim.worker(300, 1, cancelled("a")));
            }
            _ => {
                assert_eq!(sim.worker(100, 1, completed("a")), vec![]);
                let lost = sim.at(
                    200,
                    SessionInput::Worker {
                        session: 1,
                        event: Err(WorkerFault::Disconnected("stream lost".into())),
                    },
                );
                assert!(
                    lost.contains(&SessionCommand::Stop { session: 1 }),
                    "{case}: stops now, {lost:?}"
                );
            }
        }
        later.extend(sim.quiet(400, 1));
        assert!(!starts_another_unit(&later), "{case}: {later:?}");
        // A unit still cleaning up has no record yet; a settled one was never settled by evidence.
        if let Some(a) = sim.lifecycle.unit("a") {
            assert_eq!(a.attempts[0].quiescent, None, "{case}");
        }
        assert_eq!(runs(&sim), 1, "{case}: only a's own Run");
    }
}

#[test]
fn a_fault_while_a_unit_awaits_evidence_still_bounds_the_settlement() {
    // The reviewer's timeline: a guard fault after completion while awaiting quiescence. The
    // ending session keeps a wake-up at its cleanup limit, capped by the overall deadline.
    let mut sim = Sim::resident(100 * JOB);
    sim.at(0, plan("a", Some(1_000)));
    sim.at(0, plan("b", None));
    sim.at(0, SessionInput::Close);
    sim.start(10, 1, 101, "a");
    assert_eq!(sim.worker(100, 1, completed("a")), vec![]);
    let fault = sim.launch(200, 1, LaunchEvent::Fault("malformed bridge event".into()));
    assert!(
        fault.contains(&SessionCommand::Stop { session: 1 }),
        "{fault:?}"
    );
    assert_eq!(sim.lifecycle.next_deadline(), Some(t(1_000)));
    sim.at(1_000, SessionInput::Tick);
    assert!(matches!(
        sim.lifecycle.unit("a").unwrap().attempts[0].custody,
        Custody::Held(_)
    ));
    // A guard fault on a live idle session after a's quiescence settled it (custody pending,
    // no settlement limit yet, no unit policy): the stop still wakes at its cleanup limit.
    let mut sim = Sim::resident(100 * JOB);
    sim.at(0, plan("a", None));
    sim.start(10, 1, 101, "a");
    sim.worker(100, 1, completed("a"));
    sim.quiet(200, 1);
    assert_eq!(sim.settled(), vec!["a".to_string()]);
    assert_eq!(sim.lifecycle.sessions()[0].custody, Custody::Pending);
    let fault = sim.launch(300, 1, LaunchEvent::Fault("malformed bridge event".into()));
    assert!(
        fault.contains(&SessionCommand::Stop { session: 1 }),
        "{fault:?}"
    );
    assert_eq!(sim.lifecycle.next_deadline(), Some(t(300 + SESSION_CLEAN)));
}

#[test]
fn a_protocol_fault_on_an_idle_session_stops_it_with_a_bounded_settlement() {
    let mut sim = Sim::resident(100 * JOB);
    sim.at(0, plan("a", None));
    sim.start(10, 1, 101, "a");
    sim.worker(100, 1, completed("a"));
    sim.quiet(200, 1);
    assert_eq!(sim.settled(), vec!["a".to_string()]);
    let fault = sim.at(300, protocol_fault());
    assert!(
        fault.contains(&SessionCommand::Stop { session: 1 }),
        "{fault:?}"
    );
    assert_eq!(sim.lifecycle.next_deadline(), Some(t(300 + SESSION_CLEAN)));
}

#[test]
fn a_receipt_at_or_past_its_limit_before_any_tick_leaves_the_cleanup_unknown() {
    // T is the settlement limit after a completed unit's shutdown, or a crashed unit's own
    // cleanup limit. The confirmed receipt arrives at T - 1, T or T + 1, with no Tick before it.
    let limit = 100 + CLEAN;
    for crash in [false, true] {
        for at in [limit - 1, limit, limit + 1] {
            let case = format!("crash {crash}, receipt at {at}");
            let mut sim = Sim::new();
            sim.at(0, plan("a", None));
            sim.at(0, plan("b", None));
            sim.start(10, 1, 101, "a");
            if crash {
                let exit = LaunchEvent::ChildExited {
                    worker: worker(101),
                    exit: ExitInfo::Signal(9),
                    stopped_by: None,
                };
                assert_eq!(sim.launch(100, 1, exit), vec![], "{case}");
            } else {
                assert_eq!(
                    sim.worker(100, 1, completed("a")),
                    vec![SessionCommand::Shutdown { session: 1 }],
                    "{case}"
                );
                sim.worker(110, 1, WorkerEvent::Stopped);
                sim.launch(120, 1, exited(101));
            }
            let out = sim.launch(at, 1, confirmed());
            if at < limit {
                assert!(
                    out.contains(&SessionCommand::Submit { session: 2 }),
                    "{case}: released in time, {out:?}"
                );
                assert_eq!(sim.lifecycle.sessions()[0].custody, Custody::Released);
                continue;
            }
            assert!(
                !out.iter()
                    .any(|c| matches!(c, SessionCommand::Submit { .. })),
                "{case}: {out:?}"
            );
            let a = sim.lifecycle.unit("a").unwrap();
            assert!(
                matches!(a.attempts[0].custody, Custody::Held(_)),
                "{case}: {:?}",
                a.attempts
            );
            assert!(
                matches!(sim.lifecycle.sessions()[0].custody, Custody::Held(_)),
                "{case}: the session record stays held"
            );
            if crash {
                assert_eq!(
                    a.outcome.cleanup,
                    CleanupState::Unconfirmed(Expiry::CleanupLimit),
                    "{case}"
                );
                assert_eq!(a.outcome.attempts, 1, "{case}: never retried");
            }
            let b = sim.lifecycle.unit("b").unwrap();
            assert_eq!(b.outcome.end, End::Failed(Stop::Cancelled), "{case}");
            assert_eq!(sim.submits(), vec![1], "{case}");
        }
    }
}

#[test]
fn a_receipt_past_its_units_overall_deadline_in_any_phase_releases_nothing() {
    // a's overall deadline T covers its cleanup. The guard's confirmed receipt arrives at
    // T - 1, T or T + 1 with no Tick and no exit report before it, while b waits.
    const T: u64 = 1_000;
    for phase in [
        "admitted",
        "preparing",
        "running",
        "quiescing",
        "quiescing-exited",
        "cleaning-up",
        "settling",
    ] {
        for at in [T - 1, T, T + 1] {
            let case = format!("{phase}, receipt at {at}");
            let mut sim = if phase.starts_with("quiescing") {
                Sim::resident(100 * JOB)
            } else {
                Sim::new()
            };
            sim.at(0, plan("a", Some(T)));
            sim.at(0, plan("b", None));
            match phase {
                "admitted" => {
                    sim.launch(10, 1, LaunchEvent::Admitted);
                }
                "preparing" => {
                    sim.launch(10, 1, LaunchEvent::Admitted);
                    sim.launch(
                        10,
                        1,
                        LaunchEvent::ChildStarted {
                            worker: worker(101),
                        },
                    );
                    sim.registered(10, 1, "a");
                }
                "running" => sim.start(10, 1, 101, "a"),
                "cleaning-up" => {
                    sim.start(10, 1, 101, "a");
                    sim.at(100, SessionInput::CancelUnit("a".into()));
                }
                "quiescing-exited" => {
                    // The paid review's timeline: the reusable unit's worker exits after it
                    // completed, and the receipt follows past the deadline.
                    sim.start(10, 1, 101, "a");
                    sim.worker(100, 1, completed("a"));
                    sim.launch(150, 1, exited(101));
                }
                _ => {
                    sim.start(10, 1, 101, "a");
                    sim.worker(100, 1, completed("a"));
                }
            }
            let out = sim.launch(at, 1, confirmed());
            if at < T {
                assert!(
                    out.contains(&SessionCommand::Submit { session: 2 }),
                    "{case}: released in time, {out:?}"
                );
                let a = sim.lifecycle.unit("a").unwrap();
                assert_eq!(a.attempts[0].custody, Custody::Released, "{case}");
                continue;
            }
            assert!(
                !out.iter()
                    .any(|c| matches!(c, SessionCommand::Submit { .. })),
                "{case}: {out:?}"
            );
            let a = sim.lifecycle.unit("a").unwrap();
            assert!(
                matches!(a.attempts[0].custody, Custody::Held(_)),
                "{case}: {:?}",
                a.attempts
            );
            assert!(
                matches!(sim.lifecycle.sessions()[0].custody, Custody::Held(_)),
                "{case}: the session record stays held"
            );
            if a.outcome.end != End::Completed {
                assert!(
                    matches!(a.outcome.cleanup, CleanupState::Unconfirmed(_)),
                    "{case}: {:?}",
                    a.outcome
                );
            }
            let b = sim.lifecycle.unit("b").unwrap();
            assert_eq!(b.outcome.end, End::Failed(Stop::Cancelled), "{case}");
            assert_eq!(sim.submits(), vec![1], "{case}");
        }
    }
}
