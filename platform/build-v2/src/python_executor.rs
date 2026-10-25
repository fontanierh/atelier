//! Static Python dispatch through the existing C5c lifecycle, with no independent process owner.
use crate::failure_policy::{CleanupState, End, Limits, Stop};
use crate::guard_adapter::WorkerLauncher;
use crate::python_backend::{PythonCompletion, PythonInputs, PythonIo, PythonTicket};
use crate::python_worker::PythonWorkerBundle;
use crate::scheduler::{Control, Event, Executor, Flow, Work};
use crate::session_lifecycle::{SessionConfig, UnitPlan};
use crate::worker_lifecycle::{self, Custody, JobSpec, SystemClock};
use std::fs::File;
use std::path::PathBuf;
use std::time::Duration;

#[cfg(test)]
#[path = "../tests/support/python_dispatch_cases.rs"]
mod production_tests;

/// Only guard ChildStarted identities count, one per attempt (including retries).
/// Missing reports/uncertain custody cannot certify zero or a complete count.
fn record_launches(io: &mut PythonIo, unit: &str, report: Option<&worker_lifecycle::Report>) {
    io.launches_by_unit.remove(unit);
    if let Some(report) = report {
        let count = report
            .attempts
            .iter()
            .filter(|attempt| attempt.worker.is_some())
            .count();
        io.launches += count;
        if !matches!(report.outcome.cleanup, CleanupState::Unconfirmed(_))
            && report.attempts.iter().all(|attempt| {
                attempt.custody == Custody::Released
                    && (!attempt.admitted || attempt.worker.is_some())
            })
        {
            io.launches_by_unit.insert(unit.into(), count);
        }
    }
}

/// Private post-driver evidence only. It cannot certify policy, cleanup or publication.
/// No replace: a later observer cannot overwrite the original invocation's retained record.
fn retain_failure_diagnostics(
    root: &std::path::Path,
    unit: &str,
    key: &str,
    job: &str,
    attempts: &[crate::session_lifecycle::UnitAttemptRecord],
) -> std::io::Result<PathBuf> {
    use std::io::Write;
    use std::os::unix::fs::OpenOptionsExt;
    let path = root.join("diagnostic.json");
    let temporary = root.join(".diagnostic.pending");
    let bytes = serde_json::to_vec(&serde_json::json!({
        "version": 1, "unit": unit, "key": key, "job_id": job,
        "diagnostic": if attempts.iter().any(|a| a.diagnostic.is_some()) {
            "retained"
        } else { "none retained" },
        "attempts": attempts.iter().map(|a| serde_json::json!({
            "attempt": a.attempt, "session": a.session, "diagnostic": a.diagnostic,
        })).collect::<Vec<_>>(),
    }))?;
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW)
        .open(&temporary)?;
    // The private parent was reserved by this invocation before admission. Only this newly
    // created temporary is removed; occupied destination/temporary names are never replaced.
    let saved = (|| {
        file.write_all(&bytes)?;
        file.sync_all()?;
        std::fs::hard_link(&temporary, &path)?;
        File::open(root)?.sync_all()?;
        Ok(path)
    })();
    let _ = std::fs::remove_file(&temporary);
    saved
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::failure_policy::Outcome;
    use crate::leases::ProcessIdentity;
    use crate::worker_lifecycle::{AttemptRecord, Report};

    #[test]
    fn launch_evidence_counts_worker_attempts_and_never_turns_uncertainty_into_zero() {
        let mut io = PythonIo::default();
        let attempt = AttemptRecord {
            attempt: 1,
            admitted: false,
            worker: None,
            custody: Custody::Released,
        };
        let mut report = Report {
            outcome: Outcome {
                end: End::Failed(Stop::Cancelled),
                attempts: 0,
                cleanup: CleanupState::NotNeeded,
            },
            attempts: vec![attempt],
            unit_attempts: vec![],
            outputs: None,
            abort: Some("submission failed".into()),
        };
        record_launches(&mut io, "known-zero", Some(&report));
        assert_eq!(io.launches_by_unit["known-zero"], 0);
        report.attempts[0].admitted = true;
        record_launches(&mut io, "admitted-only", Some(&report));
        assert!(!io.launches_by_unit.contains_key("admitted-only"));
        report.attempts[0].worker = Some(ProcessIdentity {
            pid: 123,
            boot: "fixture".into(),
            started: "one".into(),
        });
        let mut retry = report.attempts[0].clone();
        retry.attempt = 2;
        retry.worker.as_mut().unwrap().started = "two".into();
        report.attempts.push(retry);
        record_launches(&mut io, "retry", Some(&report));
        assert_eq!(io.launches_by_unit["retry"], 2);
        assert_eq!(io.launches, 2);
        report.attempts[1].custody = Custody::Held("cleanup uncertain".into());
        record_launches(&mut io, "held", Some(&report));
        assert!(!io.launches_by_unit.contains_key("held"));
        io.launches_by_unit.insert("missing-report".into(), 0);
        record_launches(&mut io, "missing-report", None);
        assert!(!io.launches_by_unit.contains_key("missing-report"));
    }
    #[test]
    fn production_defaults_fit_after_startup_and_require_both_registrations() {
        use crate::failure_policy::MonoTime;
        use crate::guard_adapter::{AttemptEvent, LaunchEvent};
        use crate::leases::ProcessIdentity;
        use crate::session_lifecycle::{SessionCommand, SessionInput, SessionLifecycle};
        use crate::worker_session::Event as WorkerEvent;
        let limits = Limits {
            job: Duration::from_secs(120),
            cleanup: Duration::from_secs(30),
            overall: Some(Duration::from_secs(1800)),
        };
        let config = production_config(limits).unwrap();
        assert_eq!(config.lifetime, Duration::from_secs(150));
        assert!(config.custodian);
        assert!(config.quiescence.is_none());
        let mut policy = SessionLifecycle::new(config);
        let t = |seconds| MonoTime::from_elapsed(Duration::from_secs(seconds));
        let mut on = |seconds, input| {
            let commands = policy.on(t(seconds), input).unwrap();
            assert!(
                !commands
                    .iter()
                    .any(|cmd| matches!(cmd, SessionCommand::Refused { .. }))
            );
            commands
        };
        let submitted = on(
            0,
            SessionInput::Submit(UnitPlan {
                id: "a".into(),
                limits,
            }),
        );
        assert!(
            submitted
                .iter()
                .any(|cmd| matches!(cmd, SessionCommand::Submit { session: 1 }))
        );
        on(0, SessionInput::Close);
        let worker = ProcessIdentity {
            pid: 123,
            boot: "fixture".into(),
            started: "worker".into(),
        };
        let monitor = ProcessIdentity {
            pid: 124,
            boot: "fixture".into(),
            started: "monitor".into(),
        };
        let launch = |event| SessionInput::Launch(AttemptEvent { attempt: 1, event });
        on(1, launch(LaunchEvent::Admitted));
        on(2, launch(LaunchEvent::ChildStarted { worker }));
        on(
            3,
            SessionInput::Worker {
                session: 1,
                event: Ok(WorkerEvent::Ready {
                    worker_version: "fixture".into(),
                }),
            },
        );
        let commands = on(
            3,
            SessionInput::Registered {
                session: 1,
                unit: "a".into(),
                ok: true,
            },
        );
        assert!(
            !commands
                .iter()
                .any(|cmd| matches!(cmd, SessionCommand::Run { .. }))
        );
        on(
            4,
            launch(LaunchEvent::Monitor {
                monitor,
                invocation: "a".repeat(32),
            }),
        );
        let commands = on(
            4,
            SessionInput::MonitorRegistered {
                session: 1,
                unit: "a".into(),
                ok: true,
            },
        );
        assert!(
            commands
                .iter()
                .any(|cmd| matches!(cmd, SessionCommand::Run {unit,..} if unit=="a"))
        );

        let mut impossible = SessionLifecycle::new(SessionConfig {
            lifetime: Duration::from_secs(119),
            ..config
        });
        assert!(
            impossible
                .on(
                    t(0),
                    SessionInput::Submit(UnitPlan {
                        id: "no".into(),
                        limits
                    })
                )
                .unwrap()
                .iter()
                .any(|cmd| matches!(cmd, SessionCommand::Refused { .. }))
        );
        for bad in [
            Limits {
                job: Duration::ZERO,
                ..limits
            },
            Limits {
                cleanup: Duration::ZERO,
                ..limits
            },
            Limits {
                overall: Some(Duration::ZERO),
                ..limits
            },
            Limits {
                overall: None,
                ..limits
            },
            Limits {
                overall: Some(Duration::from_secs(149)),
                ..limits
            },
            Limits {
                job: Duration::MAX,
                ..limits
            },
        ] {
            assert!(production_config(bad).is_err());
        }
    }

    #[test]
    fn sole_session_acceptance_requires_exact_terminal_and_positive_cleanup() {
        use crate::failure_policy::Outcome;
        use crate::leases::ProcessIdentity;
        use crate::protocol::JobOutputs;
        use crate::session_lifecycle::{UnitAttemptRecord, UnitRecord};
        use crate::worker_lifecycle::{AttemptRecord, SessionReport};
        let valid = SessionReport {
            sessions: vec![AttemptRecord {
                attempt: 1,
                admitted: true,
                worker: Some(ProcessIdentity {
                    pid: 1,
                    boot: "fixture".into(),
                    started: "worker".into(),
                }),
                custody: Custody::Released,
            }],
            refused: vec![],
            units: vec![UnitRecord {
                unit: "a".into(),
                outcome: Outcome {
                    end: End::Completed,
                    attempts: 1,
                    cleanup: CleanupState::Finished,
                },
                attempts: vec![UnitAttemptRecord {
                    attempt: 1,
                    session: 1,
                    custody: Custody::Released,
                    quiescent: None,
                    diagnostic: None,
                }],
                outputs: Some(JobOutputs {
                    files: vec!["out.json".into()],
                }),
                abort: None,
                refused: None,
            }],
        };
        assert_eq!(
            sole_released_report("a", valid.clone())
                .unwrap()
                .outcome
                .end,
            End::Completed
        );
        let mut bad = valid.clone();
        bad.units.clear();
        assert!(sole_released_report("a", bad).is_err());
        let mut bad = valid.clone();
        bad.units.push(bad.units[0].clone());
        assert!(sole_released_report("a", bad).is_err());
        assert!(sole_released_report("foreign", valid.clone()).is_err());
        let mut bad = valid.clone();
        bad.sessions[0].custody = Custody::Held("uncertain".into());
        assert!(sole_released_report("a", bad).is_err());
        let mut bad = valid.clone();
        bad.units[0].attempts[0].quiescent = Some(1.0);
        assert!(sole_released_report("a", bad).is_err());
        let mut bad = valid.clone();
        bad.units[0].outputs = None;
        assert!(sole_released_report("a", bad).is_err());
        let mut bad = valid.clone();
        bad.sessions[0].worker = None;
        assert!(sole_released_report("a", bad).is_err());
        let mut bad = valid.clone();
        bad.units[0].outcome.cleanup =
            CleanupState::Unconfirmed(crate::failure_policy::Expiry::CleanupLimit);
        assert!(sole_released_report("a", bad).is_err());
    }
}

/// The production builder is shared with pure limits preflight. This is not a resident session:
/// each unit waits for the full guard receipt, with no quiescence-based release.
fn production_config(limits: Limits) -> Result<SessionConfig, String> {
    let overall = limits
        .overall
        .ok_or("production Python requires a bounded overall limit")?;
    if limits.job.is_zero() || limits.cleanup.is_zero() || overall.is_zero() {
        return Err("production Python limits must be positive".into());
    }
    let lifetime = limits
        .job
        .checked_add(limits.cleanup)
        .ok_or("production Python session lifetime overflow")?;
    if overall < lifetime {
        return Err("production Python overall limit cannot cover execution and cleanup".into());
    }
    Ok(SessionConfig {
        custodian: true,
        ..SessionConfig::single(limits.cleanup, lifetime)
    })
}

fn production_spec(job: &JobSpec, custody: File) -> Result<worker_lifecycle::SessionSpec, String> {
    use crate::worker_lifecycle::{
        CustodyIdentity, JobSandbox, LockScope, SessionKey, SessionSpec,
    };
    let identity = CustodyIdentity::of(&custody, LockScope::Exclusive)
        .map_err(|error| format!("cannot identify build custody: {error}"))?;
    Ok(SessionSpec {
        key: SessionKey {
            worker_version: job.worker_version.clone(),
            command: job.command.clone(),
            memory_gib: job.memory_gib,
            sandbox: JobSandbox::NoFork,
            custody: std::collections::BTreeSet::from([identity]),
        },
        purpose: job.purpose.clone(),
        config: production_config(job.limits)?,
        report_root: job.report_root.clone(),
        custody: vec![custody],
    })
}

/// A streamed Completed is insufficient: this adapter owns one sole unit and waits for the
/// entire session's positive cleanup before returning the same Work to publication.
fn sole_released_report(
    unit: &str,
    mut report: worker_lifecycle::SessionReport,
) -> Result<worker_lifecycle::Report, String> {
    if !report.refused.is_empty()
        || report.units.len() != 1
        || report.units[0].unit != unit
        || report.units[0].refused.is_some()
    {
        return Err("Python session omitted, refused or returned a foreign sole unit".into());
    }
    let record = report.units.remove(0);
    let sessions: std::collections::BTreeSet<_> = report
        .sessions
        .iter()
        .map(|attempt| attempt.attempt)
        .collect();
    let used: std::collections::BTreeSet<_> = record
        .attempts
        .iter()
        .map(|attempt| attempt.session)
        .collect();
    if sessions.len() != report.sessions.len()
        || used.len() != record.attempts.len()
        || !used.is_subset(&sessions)
    {
        return Err("Python unit/session attempt evidence is inconsistent".into());
    }
    if matches!(record.outcome.cleanup, CleanupState::Unconfirmed(_))
        || report
            .sessions
            .iter()
            .any(|attempt| attempt.custody != Custody::Released)
        || record
            .attempts
            .iter()
            .any(|attempt| attempt.custody != Custody::Released || attempt.quiescent.is_some())
    {
        return Err(format!(
            "Python session cleanup remains held or unconfirmed: outcome={:?}; sessions={:?}; abort={:?}",
            record.outcome, report.sessions, record.abort
        ));
    }
    if record.outcome.end == End::Completed
        && (report.sessions.is_empty()
            || record.attempts.is_empty()
            || record.outputs.is_none()
            || report
                .sessions
                .iter()
                .any(|attempt| !attempt.admitted || attempt.worker.is_none()))
    {
        return Err("completed Python session omitted actual attempt/output evidence".into());
    }
    Ok(worker_lifecycle::Report {
        outcome: record.outcome,
        attempts: report.sessions,
        unit_attempts: record.attempts,
        outputs: record.outputs,
        abort: record.abort,
    })
}

pub struct PythonExecution {
    pub interpreter: PathBuf,
    pub bundle: PythonWorkerBundle,
    pub profile: String,
    pub memory_gib: u32,
    pub limits: Limits,
}

pub struct UnrealExecution {
    pub locations: crate::unreal_controller::UnrealLocations,
    pub sources: crate::validate::SourceSnapshot,
    pub cache_root: PathBuf,
    pub worker: crate::keys::ImplementationIdentity,
    pub memory_gib: u32,
    pub limits: Limits,
}

pub struct PythonExecutor<L> {
    launcher: L,
    config: PythonExecution,
    blender: Option<PythonExecution>,
    recipes: Vec<PythonExecution>,
    unreal: Option<UnrealExecution>,
    node: Option<PathBuf>,
    scripted_fixture: bool,
}

impl<L> PythonExecutor<L> {
    /// Production uses one real C5c session per unit, with the original build custody and leases.
    /// The ordinary constructor never enables the scripted admission fixture.
    pub fn new(launcher: L, config: PythonExecution) -> Self {
        Self {
            launcher,
            config,
            blender: None,
            recipes: Vec::new(),
            unreal: None,
            node: None,
            scripted_fixture: false,
        }
    }

    pub fn with_node(mut self, path: PathBuf) -> Self {
        self.node = Some(path);
        self
    }

    pub fn with_unreal(mut self, config: UnrealExecution) -> Self {
        self.unreal = Some(config);
        self
    }

    pub fn with_recipe(mut self, config: PythonExecution) -> Self {
        self.recipes.push(config);
        self
    }

    pub fn with_blender(mut self, config: PythonExecution) -> Self {
        self.blender = Some(config);
        self
    }

    #[cfg(test)]
    pub(crate) fn scripted_fixture(launcher: L, config: PythonExecution) -> Self {
        Self {
            launcher,
            config,
            blender: None,
            recipes: Vec::new(),
            unreal: None,
            node: None,
            scripted_fixture: true,
        }
    }
}

impl<L: WorkerLauncher + Send> Executor<PythonTicket, PythonInputs, PythonCompletion>
    for PythonExecutor<L>
{
    /// @cc [owner:fontanierh,label:safety] static-python-cleanup-before-publication
    /// Production dispatch MUST use one C5c session per Work and register the actual worker and
    /// correlated custody monitor idempotently on both original leases
    /// before Run. Unconfirmed cleanup or any non-Released attempt MUST be fatal before publishing
    /// or starting more work. Cancellation MUST go through the existing lifecycle channel; every
    /// submitted handle MUST get a terminal event. Each leased guard report parent MUST be
    /// reserved before submission, and lifecycle abort diagnostics MUST remain failures rather
    /// than appear as user cancellation. See failed_submission_keeps_abort_reason_without_claiming_user_cancellation
    /// and actual_python_first_build_and_current_noop_have_real_zero_launch_and_write_evidence.
    /// Production limits MUST have positive job/cleanup and a bounded positive overall covering
    /// their checked sum before admission; see production_defaults_fit_after_startup_and_require_both_registrations.
    /// Production MUST retain exclusive build custody through the existing monitor and forbid Run
    /// without both registrations. Retry preparation MUST refuse attempts after the first without
    /// modifying partial bytes. Scripted fixture execution proves sandbox/I/O only, never actual
    /// admission/monitor custody. See production_dispatch_registers_original_leases_and_waits_for_full_cleanup,
    /// production_dispatch_missing_monitor_or_failed_registration_never_runs and
    /// production_crash_retry_refuses_old_staging_before_a_second_run; MAC1 remains pending.
    fn batch(
        &mut self,
        work: Vec<Work<PythonTicket, PythonInputs>>,
        control: &dyn Control,
        emit: &mut dyn FnMut(Event<PythonTicket, PythonInputs, PythonCompletion>) -> Flow,
    ) -> Result<(), String> {
        let mut stopped = false;
        let mut fatal = None;
        for mut work in work {
            // Every early refusal below precedes submission. A returned lifecycle report replaces
            // this zero; missing/uncertain lifecycle evidence removes it rather than proving zero.
            work.inputs()
                .io
                .borrow_mut()
                .launches_by_unit
                .insert(work.unit().into(), 0);
            if stopped || control.cancelled() {
                stopped |= emit(Event::Cancelled { work }) == Flow::Stop;
                continue;
            }
            let compatibility = work.compatibility();
            let config = if let Some(config) = self
                .recipes
                .iter()
                .find(|config| config.bundle.identity().version == compatibility.worker_version)
            {
                Some(config)
            } else if compatibility.worker_version == self.config.bundle.identity().version {
                Some(&self.config)
            } else {
                self.blender.as_ref().filter(|config| {
                    compatibility.worker_version == config.bundle.identity().version
                })
            };
            let native = self.unreal.as_ref().filter(|_| {
                matches!(
                    compatibility.op_kind.as_str(),
                    crate::unreal_controller::RAW_IMPORT
                        | crate::unreal_controller::FINISH
                        | crate::unreal_controller::AUTHOR
                )
            });
            if config.is_none() && native.is_none() {
                stopped |= emit(Event::Failed {
                    work,
                    reason: "no registered worker for keyed runtime".into(),
                }) == Flow::Stop;
                continue;
            }
            let config = config.unwrap_or(&self.config);
            let (worker, profile, memory_gib, limits) = if let Some(native) = native {
                (
                    native.worker.clone(),
                    "normal-unreal",
                    native.memory_gib,
                    native.limits,
                )
            } else {
                (
                    config.bundle.identity(),
                    config.profile.as_str(),
                    config.memory_gib,
                    config.limits,
                )
            };
            if compatibility.worker_version != worker.version
                || compatibility.worker_digest != worker.digest
                || compatibility.profile != profile
            {
                stopped |= emit(Event::Failed {
                    work,
                    reason: "execution context differs from keyed runtime".into(),
                }) == Flow::Stop;
                continue;
            }
            let job_dir = work.inputs().staged.job_dir();
            let scope = job_dir.parent().ok_or("job has no leased parent")?;
            let report_root = scope.join("guard");
            if let Err(error) = std::fs::create_dir(&report_root) {
                stopped |= emit(Event::Failed {
                    work,
                    reason: format!("cannot reserve leased guard report parent: {error}"),
                }) == Flow::Stop;
                continue;
            }
            let native_launch = if let Some(native) = native {
                match native
                    .locations
                    .build(
                        work.prepared(),
                        &work.inputs().staged,
                        &native.sources,
                        &native.cache_root,
                    )
                    .and_then(|context| {
                        crate::unreal_controller::prepare(
                            work.prepared(),
                            &work.inputs().staged,
                            &native.sources,
                            scope,
                            &context,
                        )
                    }) {
                    Ok(prepared) => Some(std::sync::Arc::new(std::sync::Mutex::new(prepared))),
                    Err(reason) => {
                        stopped |= emit(Event::Failed { work, reason }) == Flow::Stop;
                        continue;
                    }
                }
            } else {
                None
            };
            let (command, job, written) = if let Some(native) = &native_launch {
                let prepared = native.lock().map_err(|_| "native launch lock poisoned")?;
                (
                    prepared.command.clone(),
                    prepared.request.clone(),
                    crate::unreal::UNREAL_WORKER_FILES.len(),
                )
            } else {
                match config.bundle.command(&config.interpreter, scope) {
                    Ok(mut command) => {
                        if worker.version.starts_with("atelier-recipe-") {
                            if let Some(path) = &self.node {
                                command
                                    .args
                                    .extend(["--node".into(), path.as_os_str().to_owned()]);
                            }
                        }
                        (
                            command,
                            work.inputs().staged.request().clone(),
                            config.bundle.file_count(),
                        )
                    }
                    Err(reason) => {
                        stopped |= emit(Event::Failed { work, reason }) == Flow::Stop;
                        continue;
                    }
                }
            };
            work.inputs().io.borrow_mut().worker_files_written += written;
            let spec = JobSpec {
                job,
                worker_version: worker.version,
                command,
                purpose: format!("build-v2 {} unit", compatibility.op_kind),
                memory_gib,
                limits,
                report_root,
                custody: vec![],
            };
            let production = if self.scripted_fixture {
                None
            } else {
                match work
                    .inputs()
                    .custody
                    .try_clone()
                    .map_err(|error| error.to_string())
                    .and_then(|custody| production_spec(&spec, custody))
                {
                    Ok(spec) => Some(spec),
                    Err(reason) => {
                        stopped |= emit(Event::Failed { work, reason }) == Flow::Stop;
                        continue;
                    }
                }
            };
            let unit = work.unit().to_string();
            let (cancel, inbox) = worker_lifecycle::session_channel();
            if let Some(session) = &production {
                cancel.submit(worker_lifecycle::SessionUnit {
                    plan: UnitPlan {
                        id: unit.clone(),
                        limits: spec.limits,
                    },
                    job: spec.job.clone(),
                    key: session.key.clone(),
                });
                cancel.close();
            }

            let diagnostic_root = spec.report_root.clone();
            let diagnostic_job = spec.job.job_id.clone();
            // Compact metadata only, populated after the driver returns even if the adapter
            // subsequently refuses held/inconsistent cleanup. No report field grants authority.
            let diagnostics = std::sync::Mutex::new((false, Vec::new()));
            let before_run = native_launch.clone();
            let result = std::thread::scope(|scope| {
                let launcher = &mut self.launcher;
                let ticket = work.ticket_mut();
                let diagnostics = &diagnostics;
                let driver = scope.spawn(move || {
                    if let Some(session) = production {
                        let expected = unit.clone();
                        let job = spec.job.clone();
                        let (published, _records) = std::sync::mpsc::channel();
                        worker_lifecycle::run_session_ready_checked(
                            launcher,
                            &SystemClock::new(),
                            &session,
                            inbox,
                            &mut |id, identity| {
                                if id != &expected {
                                    return Err("registration for foreign unit".into());
                                }
                                ticket.register(identity)
                            },
                            &mut |id, attempt| {
                                if id != &unit {
                                    return Err("preparation for foreign unit".into());
                                }
                                if attempt != 1 {
                                    return Err(
                                        "fresh retry staging is unsupported; prior output retained"
                                            .into(),
                                    );
                                }
                                Ok(job.clone())
                            },
                            &mut |_| {
                                if let Some(native) = &before_run {
                                    native
                                        .lock()
                                        .map_err(|_| "native launch lock poisoned")?
                                        .verify_context()?;
                                }
                                Ok(())
                            },
                            published,
                        )
                        .map_err(|error| format!("{error:?}"))
                        .and_then(|report| {
                            if let Some(record) = report.units.iter().find(|r| r.unit == unit) {
                                *diagnostics.lock().unwrap() = (
                                    record.outcome.end == End::Completed,
                                    record.attempts.clone(),
                                );
                            }
                            sole_released_report(&unit, report)
                        })
                    } else {
                        worker_lifecycle::run_job(
                            launcher,
                            &SystemClock::new(),
                            &spec,
                            inbox,
                            &mut |identity| ticket.register(identity),
                        )
                        .inspect(|report| {
                            *diagnostics.lock().unwrap() = (
                                report.outcome.end == End::Completed,
                                report.unit_attempts.clone(),
                            );
                        })
                        .map_err(|error| format!("{error:?}"))
                    }
                });
                while !driver.is_finished() {
                    if control.cancelled() {
                        cancel.cancel_all();
                    }
                    std::thread::sleep(Duration::from_millis(5));
                }
                driver
                    .join()
                    .map_err(|_| "Python lifecycle driver panicked".to_string())?
            });
            if let Err(reason) = &result {
                use std::io::Write;
                let _ = writeln!(
                    std::io::stderr().lock(),
                    "worker preparation/lifecycle refused: {reason}"
                );
            }
            let (completed, diagnostics) = diagnostics.into_inner().unwrap_or_default();
            if !completed
                && !result
                    .as_ref()
                    .is_ok_and(|r| r.outcome.end == End::Completed)
            {
                match retain_failure_diagnostics(
                    &diagnostic_root,
                    work.unit(),
                    work.prepared().key(),
                    &diagnostic_job,
                    &diagnostics,
                ) {
                    Ok(path) => {
                        use std::io::Write;
                        let status = if diagnostics.iter().any(|a| a.diagnostic.is_some()) {
                            "retained"
                        } else {
                            "none retained"
                        };
                        let _ = writeln!(
                            std::io::stderr().lock(),
                            "Python failure diagnostic: {status}; {}",
                            path.display()
                        );
                    }
                    Err(error) => {
                        use std::io::Write;
                        let _ =
                            writeln!(std::io::stderr().lock(), "diagnostic not retained: {error}");
                    }
                }
            }
            record_launches(
                &mut work.inputs().io.borrow_mut(),
                work.unit(),
                result.as_ref().ok(),
            );
            let event = match result {
                Ok(report)
                    if !matches!(report.outcome.cleanup, CleanupState::Unconfirmed(_))
                        && report
                            .attempts
                            .iter()
                            .all(|attempt| attempt.custody == Custody::Released) =>
                {
                    if let Some(reason) = report.abort {
                        stopped |= emit(Event::Failed { work, reason }) == Flow::Stop;
                        continue;
                    }
                    match report.outcome.end {
                        End::Completed => {
                            if let Some(native) = &native_launch {
                                let verified = native
                                    .lock()
                                    .map_err(|_| "native launch lock poisoned")?
                                    .verify_completed(&work.inputs().staged);
                                if let Err(reason) = verified {
                                    stopped |= emit(Event::Failed { work, reason }) == Flow::Stop;
                                    continue;
                                }
                            }
                            match report.outputs {
                                Some(outputs) => Event::Completed {
                                    work,
                                    completion: PythonCompletion {
                                        reported: outputs.files,
                                    },
                                },
                                None => {
                                    fatal =
                                        Some("completed lifecycle omitted output manifest".into());
                                    Event::Failed {
                                        work,
                                        reason: "completed lifecycle omitted output manifest"
                                            .into(),
                                    }
                                }
                            }
                        }
                        End::Failed(Stop::Cancelled) => Event::Cancelled { work },
                        End::Failed(reason) => Event::Failed {
                            work,
                            reason: format!("Python unit failed: {reason:?}"),
                        },
                    }
                }
                Ok(_) => {
                    fatal = Some("Python attempt cleanup remains held".into());
                    Event::Failed {
                        work,
                        reason: "Python attempt cleanup remains held".into(),
                    }
                }
                Err(reason) => {
                    fatal = Some(reason.clone());
                    Event::Failed { work, reason }
                }
            };
            stopped |= emit(event) == Flow::Stop || fatal.is_some();
        }
        fatal.map_or(Ok(()), Err)
    }
}
