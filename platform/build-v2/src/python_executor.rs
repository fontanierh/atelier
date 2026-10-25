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

/// Scheduling partition only; every prepared launch still verifies its actual native profile.
fn native_session_group(
    params: &std::collections::BTreeMap<String, serde_json::Value>,
    content: &std::collections::BTreeMap<String, crate::schema::ContentIdentity>,
    store: bool,
) -> Result<Vec<u8>, String> {
    let modules = params.get("native_modules").cloned().unwrap_or(serde_json::Value::Null);
    let mut inputs = std::collections::BTreeMap::new();
    if !modules.is_null() {
        for slot in crate::native_modules::body_input_slots(&modules)? {
            inputs.insert(slot.clone(), content.get(&slot).ok_or("native context slot has no keyed input")?.clone());
        }
    }
    crate::keys::canonical_bytes(&serde_json::json!({"settings":params.get("settings").cloned().unwrap_or(serde_json::json!([])),
        "modules":modules,"inputs":inputs,"native_store":store})).map_err(|e| e.to_string())
}

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
    fn resident_groups_bind_settings_and_context_inputs_not_job_payloads() {
        use std::collections::BTreeMap;
        use crate::schema::ContentIdentity;
        let mut params = BTreeMap::new();
        let mut content = BTreeMap::new();
        let plain = native_session_group(&params, &content, false).unwrap();
        content.insert("asset".into(), ContentIdentity::Digest {digest:"a".repeat(64)});
        assert_eq!(plain, native_session_group(&params, &content, false).unwrap());
        assert_ne!(plain, native_session_group(&params, &content, true).unwrap());
        params.insert("settings".into(), serde_json::json!(["-ForceDPCVars=Bool=false"]));
        assert_ne!(plain, native_session_group(&params, &content, false).unwrap());
        params.insert("native_modules".into(), serde_json::json!({"editor":{
            "slot":"compiled","archive":"editor.tree.tar","modules":[]}}));
        assert!(native_session_group(&params, &content, false).is_err());
        content.insert("compiled".into(), ContentIdentity::Digest {digest:"b".repeat(64)});
        let context = native_session_group(&params, &content, false).unwrap();
        content.insert("asset".into(), ContentIdentity::Digest {digest:"c".repeat(64)});
        assert_eq!(context, native_session_group(&params, &content, false).unwrap());
        content.insert("compiled".into(), ContentIdentity::Digest {digest:"d".repeat(64)});
        assert_ne!(context, native_session_group(&params, &content, false).unwrap());
    }

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
        let mut resident = valid.units[0].attempts.clone();
        resident[0].custody = Custody::Pending;
        resident[0].quiescent = Some(1.0);
        assert!(resident_attempts_released(&resident, &valid.sessions));
        resident[0].quiescent = None;
        assert!(!resident_attempts_released(&resident, &valid.sessions));
        resident[0].quiescent = Some(1.0);
        resident[0].custody = Custody::Held("late".into());
        assert!(!resident_attempts_released(&resident, &valid.sessions));
        resident[0].custody = Custody::Pending;
        let mut held = valid.sessions.clone();
        held[0].custody = Custody::Held("uncertain".into());
        assert!(!resident_attempts_released(&resident, &held));
        assert!(!resident_attempts_released(&resident, &[]));
        resident[0].session = 99;
        assert!(!resident_attempts_released(&resident, &valid.sessions));
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

fn resident_attempts_released(
    attempts: &[crate::session_lifecycle::UnitAttemptRecord],
    sessions: &[worker_lifecycle::AttemptRecord],
) -> bool {
    !attempts.is_empty()
        && attempts.iter().all(|attempt| {
            // A quiescent unit's published snapshot is immutable, including Pending custody.
            // Its matching final session receipt supplies full cleanup; Held never upgrades.
            (attempt.custody == Custody::Released
                || (attempt.custody == Custody::Pending && attempt.quiescent.is_some()))
                && sessions.iter().any(|session| {
                    session.attempt == attempt.session
                        && session.custody == Custody::Released
                        && session.admitted
                        && session.worker.is_some()
                })
        })
}

pub struct PythonExecution {
    pub interpreter: PathBuf,
    pub bundle: PythonWorkerBundle,
    pub profile: String,
    pub memory_gib: u32,
    pub limits: Limits,
}

pub struct NativeToolExecution {
    pub interpreter: PathBuf,
    pub engine_root: PathBuf,
    pub bundle: crate::native_tools::NativeToolBundle,
    pub zen_state_root: PathBuf,
    pub export_project: Option<PathBuf>,
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
    native_tool: Option<NativeToolExecution>,
    node: Option<PathBuf>,
    media: [Option<PathBuf>; 2],
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
            native_tool: None,
            node: None,
            media: [None, None],
            scripted_fixture: false,
        }
    }

    pub fn with_native_tool(mut self, config: NativeToolExecution) -> Self {
        self.native_tool = Some(config);
        self
    }

    pub fn with_media(mut self, ffmpeg: Option<PathBuf>, ffprobe: Option<PathBuf>) -> Self {
        self.media = [ffmpeg, ffprobe];
        self
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
            native_tool: None,
            node: None,
            media: [None, None],
            scripted_fixture: true,
        }
    }
}

impl<L: WorkerLauncher + Send> Executor<PythonTicket, PythonInputs, PythonCompletion>
    for PythonExecutor<L>
{
    /// @cc [owner:fontanierh,label:safety] static-python-cleanup-before-publication
    /// Production dispatch MUST use C5c sessions and register each Work's actual worker and
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
        if cfg!(target_os = "macos") && !self.scripted_fixture && self.native_tool.is_some()
            && work.iter().filter(|unit|unit.compatibility().op_kind=="unreal.cook.produce"
                && !unit.prepared().ingredients().params.contains_key("global_data")).count()>1 {
            let mut groups=std::collections::BTreeMap::<Vec<u8>,Vec<_>>::new();let mut other=Vec::new();
            for unit in work {
                if unit.compatibility().op_kind=="unreal.cook.produce" && !unit.prepared().ingredients().params.contains_key("global_data") {
                    let ingredients=unit.prepared().ingredients();
                    let native_slots: std::collections::BTreeSet<_> = unit.prepared().inputs().iter().filter_map(|input| {
                        match &input.payload { crate::keys::InputPayload::Item{class,..} if class!="Data" && class!="JsonData" => Some(input.wire.name.as_str()), _=>None }
                    }).collect();
                    let context: std::collections::BTreeMap<_,_> = ingredients.content.iter().filter(|(name,_)|!native_slots.contains(name.as_str())).collect();
                    let key=crate::keys::canonical_bytes(&serde_json::json!({"project":ingredients.params.get("project"),"code":ingredients.code,"worker":ingredients.worker_digest,"context":context}))?;
                    groups.entry(key).or_default().push(unit);
                }else{other.push(unit);}
            }
            let mut stopped=false;let mut fatal=None;
            for mut group in groups.into_values(){while !group.is_empty(){let tail=if group.len()>32{group.split_off(32)}else{Vec::new()};
                if stopped||fatal.is_some()||control.cancelled(){for unit in group{emit(Event::Cancelled{work:unit});}}
                else {
                    let mut forward=|event|{let flow=emit(event);stopped|=flow==Flow::Stop;flow};
                    let result=if group.len()>1{self.source_cook_batch(group,control,&mut forward)}else{self.batch(group,control,&mut forward)};
                    if let Err(error)=result{fatal=Some(error);}
                }
                group=tail;
            }}
            if stopped||fatal.is_some()||control.cancelled(){for unit in other{emit(Event::Cancelled{work:unit});}return fatal.map_or(Ok(()),Err);}
            return self.batch(other,control,emit);
        }
        let native_kind = |kind: &str| matches!(kind,
            crate::unreal_controller::RAW_IMPORT | crate::unreal_controller::FINISH |
            crate::unreal_controller::AUTHOR | crate::native_verify::PACKAGE_OP);
        if cfg!(target_os="macos") && !self.scripted_fixture && self.unreal.is_some() {
            let count=work.iter().filter(|unit|native_kind(&unit.compatibility().op_kind)).count();
            if count>1 && count<work.len() {
                let (native,other): (Vec<_>,Vec<_>) = work.into_iter().partition(|unit|native_kind(&unit.compatibility().op_kind));
                let mut stopped=false;
                let result={let mut forward=|event|{let flow=emit(event);stopped|=flow==Flow::Stop;flow};self.batch(native,control,&mut forward)};
                if stopped||result.is_err()||control.cancelled(){for unit in other{emit(Event::Cancelled{work:unit});}return result;}
                return self.batch(other,control,emit);
            }
        }
        if cfg!(target_os = "macos")
            && !self.scripted_fixture
            && work.len() > 1
            && self.unreal.is_some()
            && work.iter().all(|unit| {
                matches!(
                    unit.compatibility().op_kind.as_str(),
                    crate::unreal_controller::RAW_IMPORT | crate::unreal_controller::FINISH | crate::unreal_controller::AUTHOR | crate::native_verify::PACKAGE_OP
                )
            })
        {
            let mut groups = std::collections::BTreeMap::<Vec<u8>, Vec<_>>::new();
            let mut stopped = false;
            for unit in work {
                let prepared = unit.inputs().native_verification.as_ref().map(|v| &v.unit).unwrap_or_else(|| unit.prepared());
                match native_session_group(&prepared.ingredients().params, &prepared.ingredients().content,
                                           unit.inputs().native_verification.is_some()) {
                    Ok(key) => groups.entry(key).or_default().push(unit),
                    Err(reason) => stopped |= emit(Event::Failed {work:unit, reason}) == Flow::Stop,
                }
            }
            let mut fatal = None;
            for group in groups.into_values() {
                if stopped || fatal.is_some() || control.cancelled() {
                    for work in group { emit(Event::Cancelled {work}); }
                    continue;
                }
                let mut forward = |event| { let flow = emit(event); stopped |= flow == Flow::Stop; flow };
                let result = if group.len() > 1 {
                    self.resident_native_batch(group, control, &mut forward)
                } else {
                    self.batch(group, control, &mut forward)
                };
                if let Err(error) = result { fatal = Some(error); }
            }
            return fatal.map_or(Ok(()), Err);
        }
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
                        | crate::native_verify::PACKAGE_OP
                )
            });
            let tool = self.native_tool.as_ref().filter(|tool| {
                compatibility.worker_version == tool.bundle.identity().version
                    && crate::native_tool_ops::supports(&compatibility.op_kind)
            });
            if config.is_none() && native.is_none() && tool.is_none() {
                stopped |= emit(Event::Failed {
                    work,
                    reason: "no registered worker for keyed runtime".into(),
                }) == Flow::Stop;
                continue;
            }
            let config = config.unwrap_or(&self.config);
            let (worker, profile, memory_gib, limits) = if let Some(tool) = tool {
                (
                    tool.bundle.identity(),
                    "native-tool",
                    tool.memory_gib,
                    tool.limits,
                )
            } else if let Some(native) = native {
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
                let prepared_unit = work
                    .inputs()
                    .native_verification
                    .as_ref()
                    .map(|verification| &verification.unit)
                    .unwrap_or_else(|| work.prepared());
                match native
                    .locations
                    .build(
                        prepared_unit,
                        &work.inputs().staged,
                        &native.sources,
                        &native.cache_root,
                    )
                    .and_then(|context| {
                        if let Some(verification) = &work.inputs().native_verification {
                            return crate::unreal_controller::prepare_verify(
                                &verification.unit,
                                &work.inputs().staged,
                                &native.sources,
                                scope,
                                &context,
                                &verification.context,
                            );
                        }
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
            if let Some(packaging) = &work.inputs().native_packaging {
                let result = tool
                    .and_then(|tool| tool.export_project.as_ref())
                    .ok_or_else(|| {
                        "native packaging requires its compiled SDK exporter".to_string()
                    })
                    .and_then(|export| {
                        packaging.write_carrier(work.inputs().staged.job_dir(), export)
                    });
                if let Err(reason) = result {
                    stopped |= emit(Event::Failed { work, reason }) == Flow::Stop;
                    continue;
                }
            }
            let (command, job, written) = if let Some(tool) = tool {
                let command = if matches!(
                    compatibility.op_kind.as_str(),
                    "unreal.cook.produce" | "unreal.package"
                ) {
                    tool.export_project
                        .as_ref()
                        .ok_or_else(|| {
                            "source cook requires execution.native_export_project".to_string()
                        })
                        .and_then(|project| {
                            tool.bundle.command_for_cook(
                                &tool.interpreter,
                                &tool.engine_root,
                                scope,
                                work.prepared().key(),
                                &tool.zen_state_root,
                                project,
                            )
                        })
                } else {
                    tool.bundle.command_for_unit(
                        &tool.interpreter,
                        &tool.engine_root,
                        scope,
                        work.prepared().key(),
                    )
                };
                match command {
                    Ok(command) => (
                        command,
                        work.inputs().staged.request().clone(),
                        crate::native_tools::NATIVE_TOOL_FILES.len(),
                    ),
                    Err(reason) => {
                        stopped |= emit(Event::Failed { work, reason }) == Flow::Stop;
                        continue;
                    }
                }
            } else if let Some(native) = &native_launch {
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
                        if worker.version.starts_with("atelier-recipe-") {
                            for (name, path) in ["--ffmpeg", "--ffprobe"].iter().zip(&self.media) {
                                if let Some(path) = path {
                                    command
                                        .args
                                        .extend([(*name).into(), path.as_os_str().to_owned()]);
                                }
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
                    Ok(mut spec) => {
                        if native.is_some()
                            || tool.is_some()
                            || compatibility.worker_version.starts_with("atelier-recipe-")
                        {
                            spec.key.sandbox = crate::worker_lifecycle::JobSandbox::Other;
                        }
                        Some(spec)
                    }
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

impl<L: WorkerLauncher + Send> PythonExecutor<L> {
    /// Execute a fixed source frontier under one original guard. Each member keeps
    /// its prepared key, inputs, output lease and stock-created Zen namespace.
    /// No member completion is issued before the entire SDK tree releases custody.
    fn source_cook_batch(
        &mut self,
        mut work: Vec<Work<PythonTicket, PythonInputs>>,
        control: &dyn Control,
        emit: &mut dyn FnMut(Event<PythonTicket, PythonInputs, PythonCompletion>) -> Flow,
    ) -> Result<(), String> {
        use std::io::Write;
        use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
        let tool = self.native_tool.as_ref().ok_or("missing source cook runtime")?;
        let setup: Result<_, String> = (|| {
            let first = work.first().ok_or("empty source frontier")?;
            let scope = first.inputs().staged.job_dir().parent().ok_or("missing source lease scope")?;
            let folder = scope.join("source-batch");
            std::fs::create_dir(&folder).map_err(|e|e.to_string())?;
            let mut jobs=Vec::new();
            for unit in &work {
                let keyed=unit.compatibility();
                if keyed.worker_digest!=tool.bundle.identity().digest || keyed.worker_version!=tool.bundle.identity().version
                    || keyed.profile!="native-tool" || keyed.op_kind!="unreal.cook.produce" {
                    return Err("source frontier runtime differs from keyed worker".into());
                }
                jobs.push(serde_json::json!({"job":unit.inputs().staged.request(),"key":unit.prepared().key(),"seconds":tool.limits.job.as_secs_f64()}));
            }
            let raw=serde_json::to_vec(&serde_json::json!({"version":1,"jobs":jobs})).map_err(|e|e.to_string())?;
            if raw.len()>64*1024*1024 {return Err("complete source frontier control exceeds 64MiB".into());}
            let path=folder.join("control.json");
            let mut file=std::fs::OpenOptions::new().write(true).create_new(true).mode(0o400)
                .custom_flags(libc::O_NOFOLLOW|libc::O_CLOEXEC).open(&path).map_err(|e|e.to_string())?;
            file.write_all(&raw).and_then(|_|file.sync_all()).map_err(|e|e.to_string())?;
            file.set_permissions(std::fs::Permissions::from_mode(0o400)).map_err(|e|e.to_string())?;
            let export=tool.export_project.as_ref().ok_or("source frontier requires compiled native exporter")?;
            let mut command=tool.bundle.command_for_cook(&tool.interpreter,&tool.engine_root,scope,first.prepared().key(),&tool.zen_state_root,export)?;
            command.args.extend(["--source-batch-control".into(),path.into_os_string()]);
            let report_root=scope.join("guard");std::fs::create_dir(&report_root).map_err(|e|e.to_string())?;
            let overall=tool.limits.overall.ok_or("source frontier requires bounded overall deadline")?;
            let maximum=overall.checked_sub(tool.limits.cleanup).ok_or("source frontier lacks cleanup allowance")?;
            let job=tool.limits.job.checked_mul(work.len().try_into().map_err(|_|"source frontier count overflow")?)
                .ok_or("source frontier lifetime overflow")?.min(maximum);
            let spec=JobSpec {job:first.inputs().staged.request().clone(),worker_version:tool.bundle.identity().version,
                command,purpose:format!("build-v2 stock source frontier ({} independent units)",work.len()),
                memory_gib:tool.memory_gib,limits:Limits{job,..tool.limits},report_root,custody:vec![]};
            let custody=first.inputs().custody.try_clone().map_err(|e|e.to_string())?;
            let mut session=production_spec(&spec,custody)?;
            // This is one fixed multi-action execution envelope, NOT live-session
            // quiescence. All source leases stay registered until full tree cleanup.
            session.key.sandbox=worker_lifecycle::JobSandbox::Other;
            Ok((spec,session,folder.join("result.json"),tool.bundle.files_len()))
        })();
        let (spec,session,result_path,written)=match setup {
            Ok(v)=>v,
            Err(reason)=>{for unit in work {emit(Event::Failed{work:unit,reason:reason.clone()});}return Ok(());}
        };
        work[0].inputs().io.borrow_mut().worker_files_written+=written;
        let (cancel,inbox)=worker_lifecycle::session_channel();
        cancel.submit(worker_lifecycle::SessionUnit{plan:UnitPlan{id:spec.job.unit.clone(),limits:spec.limits},job:spec.job.clone(),key:session.key.clone()});
        cancel.close();
        let result=std::thread::scope(|scope| {
            let launcher=&mut self.launcher;
            let mut tickets:Vec<_>=work.iter_mut().map(|unit|unit.ticket_mut()).collect();
            let expected=spec.job.unit.clone();let job=spec.job.clone();
            let driver=scope.spawn(move|| {
                let (published,_records)=std::sync::mpsc::channel();
                worker_lifecycle::run_session_ready_checked(launcher,&SystemClock::new(),&session,inbox,
                    &mut |id,identity| {if id!=&expected{return Err("foreign source envelope registration".into());}
                        for ticket in &mut tickets {ticket.register(identity)?;}Ok(())},
                    &mut |id,attempt| {if id!=&expected||attempt!=1{return Err("source frontier retries require fresh leases".into());}Ok(job.clone())},
                    &mut |_|Ok(()),published).map_err(|e|format!("{e:?}")).and_then(|report|sole_released_report(&expected,report))
            });
            while !driver.is_finished(){if control.cancelled(){cancel.cancel_all();}std::thread::sleep(Duration::from_millis(5));}
            driver.join().map_err(|_|"source frontier lifecycle panicked".to_string())?
        });
        let report=match result {
            Ok(report) if !matches!(report.outcome.cleanup,CleanupState::Unconfirmed(_))
                && report.attempts.iter().all(|a|a.custody==Custody::Released)=>report,
            Ok(_)=>{for unit in work {emit(Event::Failed{work:unit,reason:"source frontier cleanup remains held".into()});}return Err("source frontier cleanup remains held".into());}
            Err(reason)=>{for unit in work {emit(Event::Failed{work:unit,reason:reason.clone()});}return Err(reason);}
        };
        for unit in &work {record_launches(&mut unit.inputs().io.borrow_mut(),unit.unit(),Some(&report));}
        if report.abort.is_some() || report.outcome.end!=End::Completed {
            for unit in work {emit(Event::Failed{work:unit,reason:"source frontier execution did not complete".into()});}return Ok(());
        }
        let outcomes: Result<Vec<Result<Vec<String>,String>>,String>=(|| {
            use std::os::unix::fs::MetadataExt;
            let mut file=std::fs::OpenOptions::new().read(true).custom_flags(libc::O_NOFOLLOW|libc::O_CLOEXEC|libc::O_NONBLOCK)
                .open(result_path).map_err(|e|e.to_string())?;
            let info=file.metadata().map_err(|e|e.to_string())?;
            if !info.is_file()||info.nlink()!=1||info.len()>64*1024*1024{return Err("invalid source frontier completion file".to_string());}
            let mut raw=Vec::new();std::io::Read::read_to_end(&mut file,&mut raw).map_err(|e|e.to_string())?;
            let result:serde_json::Value=serde_json::from_slice(&raw).map_err(|e|e.to_string())?;
            if result["version"]!=1||result["sdk_processes"]!=1||result["sdk_closed"]!=true{return Err("source SDK completion is not closed".into());}
            let rows=result["members"].as_array().ok_or("missing source frontier members")?;
            if rows.len()!=work.len(){return Err("source frontier completion roster differs".into());}
            let mut outcomes=Vec::new();
            for (unit,row) in work.iter().zip(rows) {
                if row["job_id"].as_str()!=Some(&unit.inputs().staged.request().job_id)||row["key"].as_str()!=Some(unit.prepared().key()) {
                    return Err("source frontier completion belongs to another key/lease".into());
                }
                if row["status"]=="completed" {
                    let files:Vec<String>=serde_json::from_value(row["files"].clone()).map_err(|e|e.to_string())?;
                    outcomes.push(Ok(files));
                }else{outcomes.push(Err(row["error"].as_str().unwrap_or("source frontier member cancelled").to_owned()));}
            }
            Ok(outcomes)
        })();
        match outcomes {
            Ok(outcomes)=>{let mut stopped=false;for(unit,outcome)in work.into_iter().zip(outcomes){
                if stopped{emit(Event::Cancelled{work:unit});continue;}
                let event=match outcome {Ok(reported)=>Event::Completed{work:unit,completion:PythonCompletion{reported}},Err(reason)=>Event::Failed{work:unit,reason}};
                stopped=emit(event)==Flow::Stop;
            }}
            Err(reason)=>{for unit in work {emit(Event::Failed{work:unit,reason:reason.clone()});}}
        }
        Ok(())
    }

    /// Fixed C3 import/finish frontiers share an editor only with kernel no-fork, per-job reset
    /// receipts and fresh C5 quiescence. Publication waits for the entire admitted session's
    /// positive cleanup and released custody, including jobs already quiescent before shutdown.
    fn resident_native_batch(
        &mut self,
        mut work: Vec<Work<PythonTicket, PythonInputs>>,
        control: &dyn Control,
        emit: &mut dyn FnMut(Event<PythonTicket, PythonInputs, PythonCompletion>) -> Flow,
    ) -> Result<(), String> {
        use std::collections::BTreeMap;
        use std::sync::{Arc, Mutex};
        let native = self
            .unreal
            .as_ref()
            .ok_or("missing resident native execution")?;
        let mut launches = Vec::new();
        let setup = (|| {
            for unit in &work {
                let compatibility = unit.compatibility();
                if compatibility.worker_digest != native.worker.digest
                    || compatibility.worker_version != native.worker.version
                    || compatibility.profile != "normal-unreal"
                {
                    return Err(
                        "resident job runtime differs from keyed implementation".to_string()
                    );
                }
                let job = unit.inputs().staged.job_dir();
                let scope = job.parent().ok_or("resident job has no leased parent")?;
                let prepared = unit.inputs().native_verification.as_ref().map(|v| &v.unit).unwrap_or_else(|| unit.prepared());
                let context = native.locations.build(
                    prepared,
                    &unit.inputs().staged,
                    &native.sources,
                    &native.cache_root,
                )?;
                let mut launch = if let Some(verification) = &unit.inputs().native_verification {
                    let owner = launches.first().map(|first: &Arc<Mutex<crate::unreal_controller::PreparedUnrealLaunch>>|
                        first.lock().map_err(|_| "resident launch lock poisoned")).transpose()?;
                    crate::unreal_controller::prepare_verify_in_session(prepared, &unit.inputs().staged,
                        &native.sources, scope, &context, &verification.context, owner.as_deref())?
                } else {
                    crate::unreal_controller::prepare(prepared, &unit.inputs().staged,
                        &native.sources, scope, &context)?
                };
                launch.enable_resident()?;
                if let Some(first) = launches.first() {
                    let first: &Arc<Mutex<crate::unreal_controller::PreparedUnrealLaunch>> = first;
                    if first
                        .lock()
                        .map_err(|_| "resident launch lock poisoned")?
                        .profile
                        != launch.profile
                    {
                        return Err("incompatible native contexts in resident frontier".into());
                    }
                }
                launches.push(Arc::new(Mutex::new(launch)));
                unit.inputs().io.borrow_mut().worker_files_written +=
                    crate::unreal::UNREAL_WORKER_FILES.len();
            }
            let first = launches[0]
                .lock()
                .map_err(|_| "resident launch lock poisoned")?;
            let report_root = work[0]
                .inputs()
                .staged
                .job_dir()
                .parent()
                .ok_or("missing resident report scope")?
                .join("guard");
            std::fs::create_dir(&report_root).map_err(|e| e.to_string())?;
            let spec = JobSpec {
                job: first.request.clone(),
                worker_version: native.worker.version.clone(),
                command: first.command.clone(),
                purpose: "build-v2 resident fixed native frontier".into(),
                memory_gib: native.memory_gib,
                limits: native.limits,
                report_root,
                custody: vec![],
            };
            let custody = work[0]
                .inputs()
                .custody
                .try_clone()
                .map_err(|e| e.to_string())?;
            let mut session = production_spec(&spec, custody)?;
            let quiet = Duration::from_secs(5);
            let cleanup = native
                .limits
                .cleanup
                .checked_add(quiet)
                .ok_or("resident cleanup overflow")?;
            let overall = native
                .limits
                .overall
                .ok_or("resident overall deadline missing")?;
            let lifetime = native
                .limits
                .job
                .checked_add(quiet)
                .and_then(|v| v.checked_mul(work.len().try_into().ok()?))
                .and_then(|v| v.checked_add(native.limits.cleanup))
                .ok_or("resident lifetime overflow")?;
            session.config.lifetime = lifetime.min(overall);
            session.config.quiescence = Some(quiet);
            session.key.sandbox = worker_lifecycle::JobSandbox::NoFork;
            let limits = Limits {
                cleanup,
                ..native.limits
            };
            Ok((session, limits))
        })();
        let (session, limits) = match setup {
            Ok(value) => value,
            Err(reason) => {
                for unit in work {
                    emit(Event::Failed {
                        work: unit,
                        reason: reason.clone(),
                    });
                }
                return Ok(());
            }
        };
        let jobs: BTreeMap<_, _> = work
            .iter()
            .enumerate()
            .map(|(index, unit)| {
                (
                    unit.unit().to_owned(),
                    (
                        index,
                        launches[index].lock().unwrap().request.clone(),
                        unit.inputs().staged.job_dir().to_owned(),
                    ),
                )
            })
            .collect();
        let (cancel, inbox) = worker_lifecycle::session_channel();
        for (id, (_, job, _)) in &jobs {
            cancel.submit(worker_lifecycle::SessionUnit {
                plan: UnitPlan {
                    id: id.clone(),
                    limits,
                },
                job: job.clone(),
                key: session.key.clone(),
            });
        }
        cancel.close();
        let (published, records) = std::sync::mpsc::channel();
        let result = std::thread::scope(|scope| {
            let launcher = &mut self.launcher;
            let mut tickets: BTreeMap<_, _> = work
                .iter_mut()
                .map(|unit| {
                    let id = unit.unit().to_owned();
                    (id, unit.ticket_mut())
                })
                .collect();
            let jobs = &jobs;
            let launches = &launches;
            let driver = scope.spawn(move || {
                let mut previous: Option<usize> = None;
                worker_lifecycle::run_session_ready_checked(
                    launcher,
                    &SystemClock::new(),
                    &session,
                    inbox,
                    &mut |id, identity| {
                        tickets
                            .get_mut(id)
                            .ok_or("foreign resident registration")?
                            .register(identity)
                    },
                    &mut |id, attempt| {
                        if attempt != 1 {
                            return Err(
                                "resident retry needs fresh staging; prior output retained".into(),
                            );
                        }
                        Ok(jobs
                            .get(id)
                            .ok_or("foreign resident preparation")?
                            .1
                            .clone())
                    },
                    &mut |id| {
                        let (index, _, _) = jobs.get(id).ok_or("foreign resident Run")?;
                        if let Some(old) = previous {
                            let old_job = jobs
                                .values()
                                .find(|(i, _, _)| *i == old)
                                .ok_or("missing prior resident job")?;
                            launches[old]
                                .lock()
                                .map_err(|_| "resident launch lock poisoned")?
                                .verify_reset(&old_job.2)?;
                        }
                        if previous.is_none() {
                            launches[0]
                                .lock()
                                .map_err(|_| "resident launch lock poisoned")?
                                .verify_context()?;
                        }
                        if *index != 0 {
                            let owner = launches[0]
                                .lock()
                                .map_err(|_| "resident launch lock poisoned")?;
                            launches[*index]
                                .lock()
                                .map_err(|_| "resident launch lock poisoned")?
                                .bind_resident_context(&owner)?;
                        }
                        previous = Some(*index);
                        Ok(())
                    },
                    published,
                )
                .map_err(|e| format!("{e:?}"))
            });
            while !driver.is_finished() {
                if records
                    .try_iter()
                    .any(|record: crate::session_lifecycle::UnitRecord| {
                        record.outcome.end != End::Completed
                            || record.abort.is_some()
                            || record.refused.is_some()
                    })
                {
                    cancel.cancel_all();
                }
                if control.cancelled() {
                    cancel.cancel_all();
                }
                std::thread::sleep(Duration::from_millis(5));
            }
            driver
                .join()
                .map_err(|_| "resident native driver panicked".to_string())?
        });
        let report = match result {
            Ok(report) => report,
            Err(reason) => {
                for unit in work {
                    unit.inputs()
                        .io
                        .borrow_mut()
                        .launches_by_unit
                        .remove(unit.unit());
                    emit(Event::Failed {
                        work: unit,
                        reason: reason.clone(),
                    });
                }
                return Err(reason);
            }
        };
        let clean = !report.sessions.is_empty()
            && report.sessions.iter().all(|attempt| {
                attempt.custody == Custody::Released && attempt.admitted && attempt.worker.is_some()
            })
            && report.units.len() == work.len()
            && report.refused.is_empty();
        let observed = report
            .sessions
            .iter()
            .filter(|attempt| attempt.worker.is_some())
            .count();
        let sessions = report.sessions;
        work[0].inputs().io.borrow_mut().launches += observed;
        let mut records: BTreeMap<_, _> = report
            .units
            .into_iter()
            .map(|record| (record.unit.clone(), record))
            .collect();
        let report_root = work[0]
            .inputs()
            .staged
            .job_dir()
            .parent()
            .ok_or("missing resident evidence parent")?
            .join("guard");
        for unit in &work {
            if let Some(record) = records
                .get(unit.unit())
                .filter(|record| record.outcome.end != End::Completed)
            {
                use std::io::Write;
                let _ = writeln!(
                    std::io::stderr().lock(),
                    "resident native unit {} failed: {:?}; {:?}; {:?}",
                    unit.unit(),
                    record.outcome,
                    record.abort,
                    record.attempts
                );
                let _ = retain_failure_diagnostics(
                    &report_root,
                    unit.unit(),
                    unit.prepared().key(),
                    &launches[jobs[unit.unit()].0]
                        .lock()
                        .map_err(|_| "resident launch lock poisoned")?
                        .request
                        .job_id,
                    &record.attempts,
                );
            }
        }
        let mut stopped = false;
        for (index, unit) in work.into_iter().enumerate() {
            let record = records.remove(unit.unit());
            let event = if !clean {
                unit.inputs()
                    .io
                    .borrow_mut()
                    .launches_by_unit
                    .remove(unit.unit());
                Event::Failed {
                    work: unit,
                    reason: "resident native session cleanup or membership unconfirmed".into(),
                }
            } else if let Some(record) = record {
                let complete = !record.attempts.is_empty()
                    && record.refused.is_none()
                    && record.abort.is_none()
                    && !matches!(record.outcome.cleanup, CleanupState::Unconfirmed(_))
                    && resident_attempts_released(&record.attempts, &sessions);
                unit.inputs()
                    .io
                    .borrow_mut()
                    .launches_by_unit
                    .insert(unit.unit().into(), record.attempts.len());
                if complete && record.outcome.end == End::Completed {
                    let launch = launches[index]
                        .lock()
                        .map_err(|_| "resident launch lock poisoned")?;
                    let checked = launch
                        .verify_reset(unit.inputs().staged.job_dir())
                        .and_then(|_| launch.verify_completed(&unit.inputs().staged));
                    match (checked, record.outputs) {
                        (Ok(_), Some(outputs)) => Event::Completed {
                            work: unit,
                            completion: PythonCompletion {
                                reported: outputs.files,
                            },
                        },
                        (Err(reason), _) => Event::Failed { work: unit, reason },
                        _ => Event::Failed {
                            work: unit,
                            reason: "resident completion omitted output manifest".into(),
                        },
                    }
                } else {
                    Event::Failed {
                        work: unit,
                        reason: format!(
                            "resident native job failed: {:?}; {:?}",
                            record.outcome, record.abort
                        ),
                    }
                }
            } else {
                Event::Failed {
                    work: unit,
                    reason: "resident native session omitted unit".into(),
                }
            };
            if emit(event) == Flow::Stop {
                stopped = true;
            }
        }
        if !clean {
            return Err("resident native cleanup remains unconfirmed".into());
        }
        let _ = stopped;
        Ok(())
    }
}
