//! One real guarded resident-session window for C5c slice 6 (not a test; run once by hand, under
//! normal admission, only after review).
//!
//! `resident_window --python PATH --out build/build-v2-c5c/resident-window-2` runs the real
//! Python job loop (the frozen `atelier/build_v2` worker files, launched by
//! `launch::WorkerCommand::python_job_loop`) through the real bridge
//! (`python -m atelier.build_v2.guarded_worker`), so every session goes through the existing
//! broker admission, process and tree guards, under the no-fork job sandbox. `PATH` is made
//! absolute (never resolved through the venv link), since the loop runs with `/` as its folder.
//!
//! The setup sequence (worker identity and command, validation and preparation with the proof's
//! install policy, real B3 locks and custody, both real leases) is `tests/support/resident_setup.rs`,
//! shared with `tests/resident_window_setup.rs`, which runs it on hosted CI without any launch.
//!
//! Each case holds real B3 checkout locks (build exclusive, content shared); their custodian
//! duplicates are the session's custody, so the guard pins a custody monitor that the bridge
//! publishes once. The driver's `register` callback calls the production `register_python_worker`
//! for the worker and for the monitor on both real leases (the local completion lease and the CAS
//! write lease), then independently re-reads both lease records from disk.
//!
//! The before-Run proof is causal: the driver sends a unit's `Run` only after its monitor's
//! registration returns, and that registration re-reads both leases and returns an error (so no
//! `Run`) unless both record this attempt's bound worker and this monitor. The job's first-write
//! time against the verification times is kept as supplementary evidence only.
//!
//! Cases (each with its own expected outcome):
//! - `s1-single`: A alone.
//! - `s2-reuse`: B then A in one session, A only after quiescence evidence.
//! - `s3-aba`: A, B, A again in one session; the second A gets its own prepared request.
//! - Crash and retry are NOT COVERED: no existing identity-bound primitive lets this controller
//!   end the guard's worker (the adapter signals only its own bridge, and never the worker), and a
//!   sandboxed job cannot end its loop. An idle expiry is not crash evidence, so there is no S4.
//! - Controller death and bridge liveness are NOT COVERED: no case kills the controller, so
//!   cleanup after the controller dies is unproven, and nothing observes the bridge.
//! - `s5-cancel`: a spinning unit cancelled while it runs: the cancel is sent only after the unit's
//!   monitor registration (so after its Run) and the job's own running marker (its output, written
//!   before it loops); `cancel_after_run_started` is a required condition of the case.
//! - `s6-originals`: the controller's original B3 guards are dropped right after the monitor's
//!   registration; exclusion is then held by the controller's session custody source and the
//!   monitor, never by the dropped originals. The bridge also keeps custody descriptors until
//!   `guarded.run` returns (guarded_worker.py), but nothing here identifies or observes it:
//!   `cleanup.json` and the tree custody record carry no bridge identity, so binding the bridge
//!   would need a guard record change, outside this slice. Monitor-only custody is not
//!   observable, since `run_session` borrows the session custody for the whole run.
//!
//! The cases run in order and stop at the first failing case. DIR/evidence.json is rewritten
//! after every case and on any setup failure (`passed: false` with its problems); every attempt
//! folder is kept. The 1800 s sequence deadline below is this program's own limit; the caller's
//! outer cleanup timeout (2400 s) is a separate limit. The limits are shared with the hosted test
//! (`tests/support/resident_setup.rs`): per unit, job 120 s, cleanup 80 s and overall 300 s; per
//! session, cleanup 60 s, quiescence 10 s, lifetime 600 s and idle 3 s; 10 GiB per admission.
//! Before each case folder or launch, every plan goes through the pure session lifecycle's own
//! refusal path (the preflight the hosted test also runs); any refusal fails the case verbatim. The result certifies only the resident
//! session, Q3 retention and the B3 custody seam: not MAC1, orphan or GC behaviour, nor the
//! production A9 constructor.
#[path = "../tests/support/resident_setup.rs"]
mod setup;

use atelier_build_v2::failure_policy::{End, Stop};
use atelier_build_v2::guard_adapter::GuardedLauncher;
use atelier_build_v2::leases::ProcessIdentity;
use atelier_build_v2::python_backend::register_python_worker;
use atelier_build_v2::session_lifecycle::UnitRecord;
use atelier_build_v2::worker_lifecycle::{
    CleanupCorrelation, Custody, SessionSpec, SessionUnit, SystemClock, cleanup_confirmed,
    run_session_prepared, session_channel,
};
use serde_json::{Value, json};
use setup::{
    CASE_UNITS, CaseSetup, IDLE, MEMORY_GIB, OUTPUT_ROOT, QUIESCENCE, SESSION_CLEANUP,
    SESSION_LIFETIME, UNIT_LIMITS, World, case_setup, installer_busy, job_output, lease_holds,
    preflight, reader_admitted, running_marker, session_config, unit_plan,
};
use std::cell::RefCell;
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};
use std::sync::mpsc;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

/// One enclosing deadline over the whole sequence of cases (the caller's outer cleanup timeout,
/// 2400 s, is separate).
const SEQUENCE_DEADLINE: Duration = Duration::from_secs(1800);
/// S5 waits at most this long, after the spinning unit's monitor registration, for the job's
/// running marker.
const MARKER_WAIT: Duration = Duration::from_secs(30);
/// S5 cancels this long after the spinning job's running marker appears.
const CANCEL_AFTER: Duration = Duration::from_secs(2);

fn arg(name: &str) -> Result<PathBuf, String> {
    let args: Vec<String> = std::env::args().collect();
    let at = args
        .iter()
        .position(|a| a == name)
        .ok_or_else(|| format!("missing {name}"))?;
    args.get(at + 1)
        .map(PathBuf::from)
        .ok_or_else(|| format!("missing value for {name}"))
}

/// This controller's own identity, by the same boot and process-start scheme the guards use.
fn own_identity(python: &Path) -> Result<ProcessIdentity, String> {
    let pid = std::process::id();
    let output = Command::new(python)
        .args([
            "-c",
            "import sys\nfrom atelier.harness.capacity_protocol import boot_id, process_start\n\
             print(boot_id()); print(process_start(int(sys.argv[1])))",
        ])
        .arg(pid.to_string())
        .output()
        .map_err(|error| format!("identity helper did not start: {error}"))?;
    if !output.status.success() {
        return Err(format!(
            "identity helper failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }
    let text = String::from_utf8(output.stdout).map_err(|error| error.to_string())?;
    let mut lines = text.lines();
    let mut next = || {
        lines
            .next()
            .filter(|line| !line.is_empty())
            .map(String::from)
            .ok_or("identity helper printed too little")
    };
    Ok(ProcessIdentity {
        pid,
        boot: next()?,
        started: next()?,
    })
}

/// `(pid, fd)` of every process holding `path` open, read-only through lsof. Pids only: this is
/// liveness inside the settlement window, not identity evidence (a pid could be reused).
fn holders(path: &Path) -> Vec<(u32, String)> {
    let Ok(output) = Command::new("/usr/sbin/lsof")
        .args(["-n", "-P", "-F", "pf", "--"])
        .arg(path)
        .output()
    else {
        return vec![];
    };
    let mut found = vec![];
    let mut pid = None;
    for line in String::from_utf8_lossy(&output.stdout).lines() {
        if let Some(value) = line.strip_prefix('p') {
            pid = value.parse().ok();
        } else if let (Some(fd), Some(pid)) = (line.strip_prefix('f'), pid) {
            found.push((pid, fd.to_string()));
        }
    }
    found
}

/// Whether `pid` still exists, read-only through ps (no signal of any kind). Pids only: a
/// settlement-window liveness check, not identity evidence.
fn alive(pid: u32) -> bool {
    Command::new("/bin/ps")
        .args(["-o", "pid=", "-p", &pid.to_string()])
        .output()
        .map(|output| !String::from_utf8_lossy(&output.stdout).trim().is_empty())
        .unwrap_or(true)
}

/// Whether this controller has no child left at all (waitid WNOWAIT: never reaps, never signals).
fn no_children() -> bool {
    // SAFETY: waitid writes only into the siginfo_t we own.
    let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
    let flags = libc::WEXITED | libc::WNOHANG | libc::WNOWAIT;
    let found = unsafe { libc::waitid(libc::P_ALL, 0, &mut info, flags) };
    found == -1 && std::io::Error::last_os_error().raw_os_error() == Some(libc::ECHILD)
}

fn read_json(path: &Path) -> Value {
    fs::read(path)
        .ok()
        .and_then(|bytes| serde_json::from_slice(&bytes).ok())
        .unwrap_or(Value::Null)
}

enum Wait {
    Got,
    Ended,
    Deadline,
}

#[derive(Clone, Copy, PartialEq)]
enum Kind {
    Batch,
    Cancel,
    DropOriginals,
}

struct Case {
    name: &'static str,
    kind: Kind,
    /// (unit id, declared unit, expected end)
    units: Vec<(&'static str, &'static str, End)>,
    sessions: usize,
}

/// The cases, with their units and order from the setup shared with
/// `tests/resident_window_setup.rs`, which submits the same plans to the session lifecycle.
fn cases() -> Vec<Case> {
    CASE_UNITS
        .iter()
        .map(|(name, units)| {
            let (kind, end) = match *name {
                "s5-cancel" => (Kind::Cancel, End::Failed(Stop::Cancelled)),
                "s6-originals" => (Kind::DropOriginals, End::Completed),
                _ => (Kind::Batch, End::Completed),
            };
            Case {
                name,
                kind,
                units: units
                    .iter()
                    .map(|(unit, declared)| (*unit, *declared, end.clone()))
                    .collect(),
                sessions: 1,
            }
        })
        .collect()
}

/// What every case shares: the setup's world, plus this controller's interpreter and identity.
struct Proof {
    python: PathBuf,
    owner: ProcessIdentity,
    world: World,
    started: Instant,
}

/// A registered identity and the wall time its on-disk lease verification finished.
type Verified = (ProcessIdentity, SystemTime);

/// One unit attempt's registrations, bound by `prepare` (worker) and after it (monitor).
#[derive(Default)]
struct BoundAttempt {
    worker: Option<Verified>,
    monitor: Option<Verified>,
}

/// Per unit: the worker verified but not yet bound to an attempt, the attempt `prepare` last
/// started, and every attempt's bound registrations.
#[derive(Default)]
struct Bound {
    pending_worker: Option<Verified>,
    current: Option<u32>,
    attempts: BTreeMap<u32, BoundAttempt>,
}

fn epoch(at: SystemTime) -> Option<f64> {
    at.duration_since(UNIX_EPOCH).ok().map(|d| d.as_secs_f64())
}

fn identity_json(identity: &ProcessIdentity) -> Value {
    json!({"pid": identity.pid, "started": identity.started, "boot": identity.boot})
}

/// One case. `Err` is a setup or driver failure (no case evidence beyond the error); `Ok` carries
/// the case's evidence, which passed only if its `problems` are empty.
fn run_case(proof: &Proof, case: &Case, root: &Path) -> Result<Value, String> {
    let world = &proof.world;
    let mut problems: Vec<String> = vec![];
    let units_in_case: Vec<(&str, &str)> = case
        .units
        .iter()
        .map(|(unit, declared, _)| (*unit, *declared))
        .collect();
    // Real B3 locks and custody, the proof's install policy, and every unit's two leases, all
    // bound before any launch: the exact sequence `tests/resident_window_setup.rs` runs on CI.
    let CaseSetup {
        checkout,
        reports,
        jobs,
        originals,
        custody,
        custody_set: _,
        lock_files,
        lock_paths,
        session_fds,
        store,
        local_leases,
        mut leases,
        lease_ids,
        key,
    } = case_setup(world, &proof.owner, root, &units_in_case)?;
    let mut originals = originals;
    let spec = SessionSpec {
        key: key.clone(),
        purpose: format!("build-v2 C5c resident window: {}", case.name),
        config: session_config(),
        report_root: reports.clone(),
        custody,
    };
    let declared: BTreeMap<String, &str> = case
        .units
        .iter()
        .map(|(unit, declared, _)| (unit.to_string(), *declared))
        .collect();
    let units: Vec<SessionUnit> = case
        .units
        .iter()
        .map(|(unit, declared, _)| SessionUnit {
            plan: unit_plan(unit),
            job: world.prepared[*declared].request(unit, &format!("/jobs/{unit}")),
            key: key.clone(),
        })
        .collect();

    let (handle, inbox) = session_channel();
    let (published, records) = mpsc::channel::<UnitRecord>();
    let (registered_tx, registered_rx) = mpsc::channel::<(String, bool)>();
    let mut registrations: Vec<Value> = vec![];
    let mut s6: Value = Value::Null;
    let mut cancel: Value = Value::Null;
    let mut collected: Vec<UnitRecord> = vec![];
    let deadline = proof.started + SEQUENCE_DEADLINE;
    let mut deadline_hit = false;

    let report = std::thread::scope(|scope| {
        let driver = scope.spawn(|| {
            let bound: RefCell<BTreeMap<String, Bound>> = RefCell::new(BTreeMap::new());
            let checks: RefCell<Vec<Value>> = RefCell::new(vec![]);
            let mut launcher = GuardedLauncher {
                bridge: vec![
                    proof.python.clone().into(),
                    "-m".into(),
                    "atelier.build_v2.guarded_worker".into(),
                ],
            };
            let mut register = |unit: &String, process: &ProcessIdentity| -> Result<(), String> {
                let leases = leases
                    .get_mut(unit)
                    .ok_or_else(|| format!("no leases bound for {unit}"))?;
                // The production registration: local lease first, then the CAS lease.
                register_python_worker(&mut leases.local, Some(&mut leases.cas), process)?;
                // Independently: both lease records on disk now hold this identity.
                lease_holds(&local_leases, &leases.local.lease().id, process)?;
                lease_holds(store.leases(), &leases.cas.lease().id, process)?;
                // A monitor is the identity a durable correlation already names. The role is
                // inferred, not passed in by the adapter; a wrong inference fails closed: a
                // worker taken for a monitor has no prepared attempt (`current`) or no bound
                // worker, and a monitor taken for a worker never matches `session.worker`, so
                // the before-Run gate or `worker_is_session` refuses the case.
                let correlation = CleanupCorrelation::find(&reports, process);
                let monitor = correlation.is_some();
                if let Some(correlation) = &correlation {
                    let hex = correlation.invocation.len() == 32
                        && correlation
                            .invocation
                            .bytes()
                            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b));
                    if correlation.schema != 1
                        || correlation.monitor != *process
                        || !hex
                        || !correlation.receipts.starts_with(&reports)
                    {
                        return Err(format!("correlation mismatch: {correlation:?}"));
                    }
                }
                let busy = installer_busy(&checkout);
                registrations.push(json!({
                    "unit": unit, "role": if monitor { "monitor" } else { "worker" },
                    "identity": identity_json(process),
                    "correlation": correlation.as_ref().map(|c| json!({
                        "invocation": c.invocation, "receipts": c.receipts})),
                    "local_lease": leases.local.lease().id, "cas_lease": leases.cas.lease().id,
                    "installer_busy": busy,
                    "after_seconds": proof.started.elapsed().as_secs_f64(),
                }));
                if !busy {
                    return Err("the installer was not excluded while the session lives".into());
                }
                if monitor && case.kind == Kind::DropOriginals && originals.is_some() {
                    let me = std::process::id();
                    let before: Vec<_> = lock_paths.iter().map(|path| holders(path)).collect();
                    drop(originals.take());
                    let after: Vec<_> = lock_paths.iter().map(|path| holders(path)).collect();
                    let mine: BTreeSet<String> = after
                        .iter()
                        .flatten()
                        .filter(|(pid, _)| *pid == me)
                        .map(|(_, fd)| fd.clone())
                        .collect();
                    let dropped: BTreeSet<String> = before
                        .iter()
                        .flatten()
                        .filter(|(pid, _)| *pid == me)
                        .map(|(_, fd)| fd.clone())
                        .filter(|fd| !session_fds.contains(fd))
                        .collect();
                    let monitor_holds = after
                        .iter()
                        .all(|list| list.iter().any(|(pid, _)| *pid == process.pid));
                    let busy = installer_busy(&checkout);
                    let shared_reader = reader_admitted(&checkout);
                    s6 = json!({
                        "holders_before": before, "holders_after": after,
                        "controller_fds_after": mine, "session_custody_fds": session_fds,
                        "dropped_original_fds": dropped, "monitor_holds_every_lock": monitor_holds,
                        "installer_busy_after_drop": busy, "shared_reader_admitted": shared_reader,
                        "claim": "exclusion is held by the controller's session custody source \
                                  and the monitor, not by the dropped original guards; the bridge \
                                  is neither identified nor observed (no guard record carries its \
                                  identity; binding it needs a guard record change, outside this \
                                  slice); monitor-only custody is not observable",
                        "shared_reader_expected": true,
                    });
                    // A second reader must still be admitted: content custody is held shared,
                    // so a refusal would mean the custody set holds it in the wrong scope.
                    if !(monitor_holds
                        && busy
                        && shared_reader
                        && mine == session_fds
                        && !dropped.is_empty())
                    {
                        return Err(
                            "custody attribution after dropping the originals failed".into()
                        );
                    }
                }
                // Bind this verified registration: a worker waits for its attempt's `prepare`; a
                // monitor belongs to the attempt `prepare` last started for this unit.
                let gate = {
                    let verified = SystemTime::now();
                    let mut bound = bound.borrow_mut();
                    let entry = bound.entry(unit.clone()).or_default();
                    if monitor {
                        let attempt = entry
                            .current
                            .ok_or("a monitor registered before its unit's attempt was prepared")?;
                        let bound_attempt = entry.attempts.entry(attempt).or_default();
                        bound_attempt.monitor = Some((process.clone(), verified));
                        let worker = bound_attempt
                            .worker
                            .as_ref()
                            .map(|(worker, _)| worker.clone())
                            .ok_or("a monitor registered for an attempt with no bound worker")?;
                        Some((attempt, worker))
                    } else {
                        entry.pending_worker = Some((process.clone(), verified));
                        None
                    }
                };
                // The causal before-Run check. The driver sends this attempt's `Run` only after
                // the monitor's registration returns Ok, so this re-read from disk precedes it:
                // both leases must record both the attempt's bound worker and this monitor, or
                // the registration fails and the unit never runs.
                if let Some((attempt, worker)) = gate {
                    let (local_id, cas_id) = (&leases.local.lease().id, &leases.cas.lease().id);
                    let held = |identity: &ProcessIdentity| {
                        lease_holds(&local_leases, local_id, identity)
                            .and_then(|()| lease_holds(store.leases(), cas_id, identity))
                    };
                    let worker_held = held(&worker);
                    let monitor_held = held(process);
                    checks.borrow_mut().push(json!({
                        "gate": "monitor registration, before Run",
                        "unit": unit, "attempt": attempt,
                        "worker": identity_json(&worker), "monitor": identity_json(process),
                        "local_lease": local_id, "cas_lease": cas_id,
                        "worker_on_both_leases": worker_held.is_ok(),
                        "monitor_on_both_leases": monitor_held.is_ok(),
                        "error": worker_held.as_ref().err().or(monitor_held.as_ref().err()),
                    }));
                    worker_held?;
                    monitor_held?;
                }
                let _ = registered_tx.send((unit.clone(), monitor));
                Ok(())
            };
            let mut prepare = |unit: &String, attempt: u32| -> Result<_, String> {
                // Its worker is durably on both leases, re-read from disk here. (Its monitor is
                // registered only after `prepare`; the monitor registration then re-checks both
                // identities on both leases before the Run.)
                let worker = {
                    let mut bound = bound.borrow_mut();
                    let entry = bound.entry(unit.clone()).or_default();
                    let worker = entry
                        .pending_worker
                        .take()
                        .ok_or("no verified worker registration before prepare")?;
                    entry.current = Some(attempt);
                    entry.attempts.entry(attempt).or_default().worker = Some(worker.clone());
                    worker
                };
                let (local_id, cas_id) = lease_ids.get(unit).ok_or("no leases bound")?;
                let on_disk = lease_holds(&local_leases, local_id, &worker.0)
                    .and_then(|()| lease_holds(store.leases(), cas_id, &worker.0));
                checks.borrow_mut().push(json!({
                    "gate": "prepare",
                    "unit": unit, "attempt": attempt, "worker": identity_json(&worker.0),
                    "worker_on_both_leases": on_disk.is_ok(), "error": on_disk.as_ref().err(),
                }));
                on_disk?;
                let declared = declared.get(unit).ok_or("unknown unit")?;
                let prepared = &world.prepared[*declared];
                let folder = jobs.join(format!("{unit}-{attempt}"));
                fs::create_dir(&folder).map_err(|error| error.to_string())?;
                fs::create_dir(folder.join(OUTPUT_ROOT)).map_err(|error| error.to_string())?;
                let request = prepared.request(unit, &folder.display().to_string());
                for code in &request.code {
                    let bytes = world
                        .sources
                        .get(code.as_str())
                        .ok_or("unknown code file")?;
                    let path = folder.join(code);
                    fs::create_dir_all(path.parent().unwrap()).map_err(|e| e.to_string())?;
                    fs::write(&path, bytes).map_err(|error| error.to_string())?;
                }
                Ok(request)
            };
            let result = run_session_prepared(
                &mut launcher,
                &SystemClock::new(),
                &spec,
                inbox,
                &mut register,
                &mut prepare,
                published,
            );
            (result, bound.into_inner(), checks.into_inner())
        });

        // Feed the session as the case requires, under the enclosing deadline. A driver that
        // ends early (its publication channel closes) is reported as such, never as a timeout.
        let wait_record = |collected: &mut Vec<UnitRecord>| -> Wait {
            loop {
                if Instant::now() >= deadline {
                    return Wait::Deadline;
                }
                match records.recv_timeout(Duration::from_secs(1)) {
                    Ok(record) => {
                        collected.push(record);
                        return Wait::Got;
                    }
                    Err(mpsc::RecvTimeoutError::Disconnected) => return Wait::Ended,
                    Err(mpsc::RecvTimeoutError::Timeout) => continue,
                }
            }
        };
        let mut ended = false;
        match case.kind {
            Kind::Batch | Kind::DropOriginals => {
                for unit in units {
                    handle.submit(unit);
                }
                handle.close();
            }
            Kind::Cancel => {
                for unit in units {
                    handle.submit(unit);
                }
                handle.close();
                // The spinning unit's MONITOR registration (its Run follows only after it), or
                // the driver's end, or the deadline.
                let monitor_registered = loop {
                    if Instant::now() >= deadline {
                        deadline_hit = true;
                        break false;
                    }
                    if driver.is_finished() {
                        ended = true;
                        break false;
                    }
                    match registered_rx.recv_timeout(Duration::from_secs(1)) {
                        Ok((unit, true)) if unit == "spin" => break true,
                        Ok(_) | Err(mpsc::RecvTimeoutError::Timeout) => continue,
                        Err(mpsc::RecvTimeoutError::Disconnected) => {
                            ended = true;
                            break false;
                        }
                    }
                };
                // Then, bounded, the running marker the spin job writes before it loops: its
                // declared output, which exists only once the job itself has run.
                let mut marker: Option<(PathBuf, f64)> = None;
                if monitor_registered {
                    let wait_until = (Instant::now() + MARKER_WAIT).min(deadline);
                    while marker.is_none() && Instant::now() < wait_until && !driver.is_finished() {
                        marker = running_marker(&jobs, "spin")
                            .map(|path| (path, proof.started.elapsed().as_secs_f64()));
                        if marker.is_none() {
                            std::thread::sleep(Duration::from_millis(100));
                        }
                    }
                    if marker.is_some() {
                        std::thread::sleep(CANCEL_AFTER);
                    }
                    // Cancel in every case so the unit ends; only a cancel after the marker
                    // counts as a running-job cancel.
                    let cancelled_after = proof.started.elapsed().as_secs_f64();
                    handle.cancel("spin");
                    cancel = json!({
                        "monitor_registered": true,
                        "running_marker": marker.as_ref().map(|(path, _)| path.display().to_string()),
                        "marker_seen_after_seconds": marker.as_ref().map(|(_, at)| *at),
                        "cancelled_after_seconds": cancelled_after,
                        "cancel_after_run_started": marker.is_some(),
                    });
                } else {
                    cancel =
                        json!({"monitor_registered": false, "cancel_after_run_started": false});
                }
            }
        }
        while collected.len() < case.units.len() && !deadline_hit && !ended {
            match wait_record(&mut collected) {
                Wait::Got => {}
                Wait::Ended => ended = true,
                Wait::Deadline => {
                    deadline_hit = true;
                    handle.cancel_all();
                }
            }
        }
        driver.join()
    });
    drop(registered_rx);

    let mut evidence = json!({"case": case.name});
    if deadline_hit {
        problems.push("the enclosing deadline passed".into());
    }
    let Ok((report, bound, lease_checks)) = report else {
        problems.push("the session driver panicked".into());
        evidence["problems"] = json!(problems);
        evidence["registrations"] = json!(registrations);
        return Ok(evidence);
    };
    let report = match report {
        Ok(report) => report,
        Err(error) => {
            problems.push(format!("run_session failed: {error:?}"));
            evidence["problems"] = json!(problems);
            evidence["registrations"] = json!(registrations);
            evidence["lease_checks"] = json!(lease_checks);
            return Ok(evidence);
        }
    };

    // A refused unit never runs: each refusal is evidence, and fails the case with its reason.
    let refusals: Vec<Value> = report
        .refused
        .iter()
        .map(|record| {
            json!({"unit": record.unit, "refusal": record.refused.map(|r| format!("{r:?}")),
                   "reason": record.abort})
        })
        .collect();
    for record in &report.refused {
        problems.push(format!(
            "{}: refused: {:?} ({})",
            record.unit,
            record.refused,
            record.abort.as_deref().unwrap_or("")
        ));
    }

    // Per-unit expected outcomes, each settled by its own receipt or quiescence evidence.
    let mut units_evidence = vec![];
    for (unit, _, expected) in &case.units {
        let Some(record) = report.units.iter().find(|record| record.unit == *unit) else {
            problems.push(format!("{unit}: no record"));
            continue;
        };
        if record.outcome.end != *expected {
            problems.push(format!(
                "{unit}: ended {:?}, expected {expected:?}",
                record.outcome.end
            ));
        }
        // The record as published, not the final report: each attempt must already carry its
        // release receipt or quiescence evidence when it was handed off.
        let published = collected.iter().find(|published| published.unit == *unit);
        match published {
            None => problems.push(format!("{unit}: never published")),
            Some(published) => {
                let settled = published.attempts.iter().all(|attempt| {
                    attempt.custody == Custody::Released || attempt.quiescent.is_some()
                });
                if !settled || published.outcome.end != *expected {
                    problems.push(format!(
                        "{unit}: published before release or quiescence evidence, or with \
                         another end"
                    ));
                }
            }
        }
        // The final record too, at the attempt level: every attempt released by its receipt or
        // settled by quiescence evidence, and none held. The session record alone is not enough.
        let released = record
            .attempts
            .iter()
            .all(|attempt| attempt.custody == Custody::Released || attempt.quiescent.is_some());
        let held = record
            .attempts
            .iter()
            .any(|attempt| matches!(attempt.custody, Custody::Held(_)));
        if !released || held {
            problems.push(format!(
                "{unit}: an attempt is not released or quiescent, or is held: {:?}",
                record.attempts
            ));
        }
        units_evidence.push(json!({
            "unit": unit, "end": format!("{:?}", record.outcome.end),
            "attempts": record.attempts.iter().map(|attempt| json!({
                "attempt": attempt.attempt, "session": attempt.session,
                "custody": format!("{:?}", attempt.custody), "quiescent": attempt.quiescent,
            })).collect::<Vec<_>>(),
            "outputs": record.outputs.as_ref().map(|outputs| outputs.files.clone()),
            "abort": record.abort,
        }));
    }
    if report.sessions.len() != case.sessions {
        problems.push(format!(
            "{} sessions, expected {}",
            report.sessions.len(),
            case.sessions
        ));
    }

    // Every session's cleanup is positively correlated with its own guard invocation.
    let mut sessions_evidence = vec![];
    for session in &report.sessions {
        let folder = reports.join(format!("attempt-{}", session.attempt));
        if session.custody != Custody::Released {
            problems.push(format!(
                "session {}: {:?}",
                session.attempt, session.custody
            ));
        }
        // A confirmed receipt after the session was held is kept in the held record; it is
        // evidence of a late receipt, never of release, and fails the case.
        let late_receipt = matches!(&session.custody, Custody::Held(reason)
            if reason.contains("a confirmed cleanup receipt arrived late"));
        if late_receipt {
            problems.push(format!("session {}: late cleanup receipt", session.attempt));
        }
        let correlation = CleanupCorrelation::read(&folder).ok();
        let confirmed = correlation.as_ref().is_some_and(cleanup_confirmed);
        if !confirmed {
            problems.push(format!(
                "session {}: cleanup not confirmed",
                session.attempt
            ));
        }
        let cleanup = read_json(&folder.join("cleanup.json"));
        let child_matches = session.worker.as_ref().is_some_and(|worker| {
            cleanup["child"][0].as_u64() == Some(worker.pid.into())
                && cleanup["child"][1].as_u64().map(|v| v.to_string())
                    == Some(worker.started.clone())
        });
        if !child_matches {
            problems.push(format!(
                "session {}: cleanup.json names another child",
                session.attempt
            ));
        }
        let tree = read_json(&folder.join("memory-health-tree.json"));
        let receipt_locks: BTreeSet<(u64, u64)> = tree["custody"]["lock_files"]
            .as_array()
            .map(|files| {
                files
                    .iter()
                    .filter_map(|pair| Some((pair[0].as_u64()?, pair[1].as_u64()?)))
                    .collect()
            })
            .unwrap_or_default();
        if receipt_locks != lock_files {
            problems.push(format!(
                "session {}: the guard released other locks",
                session.attempt
            ));
        }
        sessions_evidence.push(json!({
            "attempt": session.attempt, "admitted": session.admitted,
            "worker": session.worker.as_ref().map(identity_json),
            "custody": format!("{:?}", session.custody), "late_receipt": late_receipt,
            "correlation": correlation.as_ref().map(|c| json!({
                "monitor": identity_json(&c.monitor), "invocation": c.invocation})),
            "cleanup_confirmed": confirmed, "cleanup": cleanup,
            "tree_custody": tree["custody"],
            "resources": {
                "timings": read_json(&folder.join("execution-timings.json")),
                "memory": read_json(&folder.join("memory-health.json")),
            },
        }));
    }
    // Every attempt's registrations are bound to the session that ran it, and its monitor
    // registration's causal gate found both identities on both leases before its Run. The
    // verification times against the job's first write are supplementary evidence only (wall
    // clock and file times), never the proof, so they do not decide the case.
    let mut bindings = vec![];
    for record in &report.units {
        for attempt in &record.attempts {
            let bound_attempt = bound
                .get(&record.unit)
                .and_then(|unit| unit.attempts.get(&attempt.attempt));
            let worker = bound_attempt.and_then(|b| b.worker.clone());
            let monitor = bound_attempt.and_then(|b| b.monitor.clone());
            let session = report
                .sessions
                .iter()
                .find(|session| session.attempt == attempt.session);
            let folder = reports.join(format!("attempt-{}", attempt.session));
            let correlation = CleanupCorrelation::read(&folder).ok();
            let output = job_output(&jobs.join(format!("{}-{}", record.unit, attempt.attempt)));
            let first_write = fs::metadata(&output).and_then(|m| m.modified()).ok();
            let worker_is_session = worker
                .as_ref()
                .zip(session.and_then(|s| s.worker.as_ref()))
                .is_some_and(|((registered, _), ran)| registered == ran);
            let monitor_is_session = monitor
                .as_ref()
                .zip(correlation.as_ref())
                .is_some_and(|((registered, _), c)| *registered == c.monitor);
            let before = |verified: &Option<Verified>| {
                verified
                    .as_ref()
                    .zip(first_write)
                    .is_some_and(|((_, at), written)| *at < written)
            };
            let ordered = before(&worker) && before(&monitor);
            let gated = lease_checks.iter().any(|check| {
                check["gate"] == "monitor registration, before Run"
                    && check["unit"] == record.unit.as_str()
                    && check["attempt"] == attempt.attempt
                    && check["worker_on_both_leases"] == true
                    && check["monitor_on_both_leases"] == true
                    && worker
                        .as_ref()
                        .is_some_and(|(w, _)| check["worker"] == identity_json(w))
                    && monitor
                        .as_ref()
                        .is_some_and(|(m, _)| check["monitor"] == identity_json(m))
            });
            if !(worker_is_session && monitor_is_session && gated) {
                problems.push(format!(
                    "{} attempt {}: registrations not bound to session {} and gated before its \
                     Run (worker {worker_is_session}, monitor {monitor_is_session}, gate {gated})",
                    record.unit, attempt.attempt, attempt.session
                ));
            }
            bindings.push(json!({
                "unit": record.unit, "attempt": attempt.attempt, "session": attempt.session,
                "worker": worker.as_ref().map(|(w, _)| identity_json(w)),
                "worker_verified_at": worker.as_ref().and_then(|(_, at)| epoch(*at)),
                "monitor": monitor.as_ref().map(|(m, _)| identity_json(m)),
                "monitor_verified_at": monitor.as_ref().and_then(|(_, at)| epoch(*at)),
                "first_output_write_at": first_write.and_then(epoch),
                "worker_is_session_worker": worker_is_session,
                "monitor_is_session_monitor": monitor_is_session,
                "before_run_gate_passed": gated,
                "supplementary_both_verified_before_first_write": ordered,
            }));
        }
    }

    // Settlement: release every controller handle, then the installer must be admitted.
    let watched: Vec<u32> = registrations
        .iter()
        .filter_map(|entry| entry["identity"]["pid"].as_u64())
        .map(|pid| pid as u32)
        .collect();
    drop(originals);
    drop(spec);
    drop(leases);
    let installer_after = !installer_busy(&checkout);
    if !installer_after {
        problems.push("the installer is still excluded after settlement".into());
    }
    // Bounded: the launcher's reaper threads and the guards' monitors exit just after settlement.
    let settle_by = Instant::now() + Duration::from_secs(15);
    let (survivors, children) = loop {
        let survivors: Vec<u32> = watched.iter().copied().filter(|pid| alive(*pid)).collect();
        let children = !no_children();
        if (survivors.is_empty() && !children) || Instant::now() >= settle_by {
            break (survivors, children);
        }
        std::thread::sleep(Duration::from_millis(250));
    };
    if !survivors.is_empty() {
        problems.push(format!("owned processes survive: {survivors:?}"));
    }
    if children {
        problems.push("this controller still has children".into());
    }
    evidence["refused"] = json!(refusals);
    evidence["units"] = json!(units_evidence);
    evidence["sessions"] = json!(sessions_evidence);
    evidence["registrations"] = json!(registrations);
    evidence["lease_checks"] = json!(lease_checks);
    evidence["attempt_bindings"] = json!(bindings);
    evidence["installer_admitted_after_settlement"] = json!(installer_after);
    evidence["lock_files"] = json!(lock_files);
    if case.kind == Kind::DropOriginals {
        evidence["originals_dropped"] = s6;
    }
    if case.kind == Kind::Cancel {
        if cancel["cancel_after_run_started"] != true {
            problems.push("the cancel was not sent after the job's running marker".into());
        }
        evidence["cancel"] = cancel;
    }
    evidence["problems"] = json!(problems);
    Ok(evidence)
}

/// Everything before the first case: the shared setup's world, this controller's identity and an
/// absolute interpreter path.
fn prepare_proof(python: &Path, out: &Path) -> Result<Proof, String> {
    // Absolute but never canonicalized: resolving the venv's link would lose the venv.
    let python = std::path::absolute(python).map_err(|error| error.to_string())?;
    let source = Path::new(env!("CARGO_MANIFEST_DIR")).join("../studio/atelier/build_v2");
    let world = setup::world(&python, &source, &out.join("worker"))?;
    let owner = own_identity(&python)?;
    Ok(Proof {
        python,
        owner,
        world,
        started: Instant::now(),
    })
}

fn summary(proof: Option<&Proof>, problems: &[String], cases: &[Value], complete: bool) -> Value {
    let passed = complete
        && problems.is_empty()
        && cases.iter().all(|case| {
            case["problems"]
                .as_array()
                .is_some_and(|problems| problems.is_empty())
        });
    json!({
        "schema": 1,
        "certifies": "resident session reuse, Q3 retention on real leases and the B3 custody seam \
                      only; not MAC1, orphan or GC behaviour, nor the production A9 constructor",
        "not_covered": [
            "crash-retry: NOT COVERED (no existing identity-bound primitive may end the guard's \
             worker from this controller, and a sandboxed job cannot end its loop); no resident \
             retry acceptance is claimed",
            "controller death and bridge liveness: NOT COVERED (no case kills the controller, \
             so cleanup after the controller dies is unproven, and nothing observes the bridge)",
            "a real Held case",
            "MAC1, orphan or GC behaviour, M1, the production A9 constructor",
        ],
        "before_run_proof": "causal: each attempt's monitor registration re-reads both leases and \
                             fails (no Run) unless both record the attempt's bound worker and \
                             that monitor; first-write times are supplementary only",
        "worker": proof.map(|p| json!({"version": p.world.worker.version,
                                       "digest": p.world.worker.digest})),
        "python": proof.map(|p| p.python.display().to_string()),
        "memory_gib": MEMORY_GIB,
        "limits": {
            "unit_job_seconds": UNIT_LIMITS.job.as_secs(),
            "unit_cleanup_seconds": UNIT_LIMITS.cleanup.as_secs(),
            "unit_overall_seconds": UNIT_LIMITS.overall.map(|d| d.as_secs()),
            "session_cleanup_seconds": SESSION_CLEANUP.as_secs(),
            "session_lifetime_seconds": SESSION_LIFETIME.as_secs(), "idle_seconds": IDLE.as_secs(),
            "quiescence_seconds": QUIESCENCE.as_secs(),
            "sequence_deadline_seconds": SEQUENCE_DEADLINE.as_secs(),
        },
        "owner": proof.map(|p| identity_json(&p.owner)),
        "elapsed_seconds": proof.map(|p| p.started.elapsed().as_secs_f64()),
        "complete": complete,
        "passed": passed,
        "problems": problems,
        "cases": cases,
    })
}

fn write_evidence(out: &Path, summary: &Value) -> bool {
    let written = serde_json::to_vec_pretty(summary)
        .map_err(|error| error.to_string())
        .and_then(|bytes| {
            let partial = out.join("evidence.json.partial");
            fs::write(&partial, bytes)
                .and_then(|()| fs::rename(&partial, out.join("evidence.json")))
                .map_err(|error| error.to_string())
        });
    if let Err(error) = &written {
        eprintln!("cannot write evidence.json: {error}");
    }
    written.is_ok()
}

fn main() -> ExitCode {
    let (python, out) = match (arg("--python"), arg("--out")) {
        (Ok(python), Ok(out)) => (python, out),
        (Err(error), _) | (_, Err(error)) => {
            eprintln!("{error}");
            return ExitCode::from(2);
        }
    };
    // A fresh folder only: earlier evidence is never overwritten.
    if let Err(error) = fs::create_dir(&out) {
        eprintln!("--out must name a new folder: {error}");
        return ExitCode::from(2);
    }
    let out = match out.canonicalize() {
        Ok(out) => out,
        Err(error) => {
            eprintln!("cannot resolve --out: {error}");
            return ExitCode::from(2);
        }
    };
    let proof = match catch_unwind(AssertUnwindSafe(|| prepare_proof(&python, &out))) {
        Ok(Ok(proof)) => proof,
        Ok(Err(error)) => {
            write_evidence(
                &out,
                &summary(None, &[format!("setup: {error}")], &[], false),
            );
            println!("setup: FAIL ({error})");
            return ExitCode::FAILURE;
        }
        Err(_) => {
            write_evidence(&out, &summary(None, &["setup panicked".into()], &[], false));
            println!("setup: FAIL (panic)");
            return ExitCode::FAILURE;
        }
    };

    let mut cases_evidence: Vec<Value> = vec![];
    let mut problems: Vec<String> = vec![];
    for case in cases() {
        if !problems.is_empty() {
            cases_evidence.push(json!({"case": case.name,
                                       "problems": ["not started: an earlier case failed"]}));
            continue;
        }
        if proof.started.elapsed() >= SEQUENCE_DEADLINE {
            problems.push(format!("{}: not started: deadline", case.name));
            cases_evidence.push(json!({"case": case.name, "problems": ["not started: deadline"]}));
            continue;
        }
        let root = out.join(case.name);
        // The same pure preflight the hosted test runs, before any case folder or launch: a
        // unit the session would refuse fails the case at once, with every refusal verbatim.
        let plans: Vec<_> = case
            .units
            .iter()
            .map(|(unit, _, _)| unit_plan(unit))
            .collect();
        if let Err(refused) = preflight(session_config(), &plans) {
            let refusals: Vec<Value> = refused
                .iter()
                .map(|r| {
                    json!({"unit": r.unit, "refusal": r.reason.map(|x| format!("{x:?}")),
                           "reason": r.text})
                })
                .collect();
            let case_problems: Vec<String> = refused
                .iter()
                .map(|r| {
                    format!(
                        "preflight: {}: refused: {:?} ({})",
                        r.unit, r.reason, r.text
                    )
                })
                .collect();
            problems.push(format!("{}: failed", case.name));
            println!("{}: FAIL (preflight)", case.name);
            cases_evidence.push(json!({"case": case.name, "preflight_refused": refusals,
                                       "problems": case_problems}));
            write_evidence(
                &out,
                &summary(Some(&proof), &problems, &cases_evidence, false),
            );
            continue;
        }
        let result = fs::create_dir(&root)
            .map_err(|error| format!("cannot create the case folder: {error}"))
            .and_then(|()| {
                catch_unwind(AssertUnwindSafe(|| run_case(&proof, &case, &root)))
                    .unwrap_or_else(|_| Err("the case panicked".into()))
            });
        let case_evidence = match result {
            Ok(evidence) => evidence,
            Err(error) => json!({"case": case.name, "problems": [format!("setup: {error}")]}),
        };
        let passed = case_evidence["problems"]
            .as_array()
            .is_some_and(|problems| problems.is_empty());
        println!("{}: {}", case.name, if passed { "pass" } else { "FAIL" });
        if !passed {
            problems.push(format!("{}: failed", case.name));
        }
        cases_evidence.push(case_evidence);
        write_evidence(
            &out,
            &summary(Some(&proof), &problems, &cases_evidence, false),
        );
    }
    let summary = summary(Some(&proof), &problems, &cases_evidence, true);
    let written = write_evidence(&out, &summary);
    if written && summary["passed"] == true {
        ExitCode::SUCCESS
    } else {
        ExitCode::FAILURE
    }
}
