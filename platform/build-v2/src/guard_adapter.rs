//! C7: the launcher seam between the worker lifecycle and Atelier's existing guard.
//!
//! A [`WorkerLauncher`] queues one admitted attempt and reports what the guard observed as
//! [`LaunchEvent`]s on a channel. [`GuardedLauncher`] implements it with one bridge process per
//! attempt (`python -m atelier.build_v2.guarded_worker`), which calls the existing
//! `atelier.harness.safety.guarded.run` with the protocol pipe as `pass_fds`. Admission, the
//! memory and tree guards, reaping and capacity release all stay in that existing code; this
//! module adds no broker, lock, reservation or reaper, and never signals the worker itself.
use crate::leases::ProcessIdentity;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::ffi::OsString;
use std::fs::{self, File};
use std::io::{self, BufRead, BufReader, PipeWriter, Read, Write};
use std::os::fd::{AsRawFd, RawFd};
use std::os::unix::process::CommandExt;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::Sender;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

/// One worker invocation. The launcher appends `--request-fd N --response-fd M` for the two
/// inherited protocol pipe ends; stdout and stderr are logs.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct WorkerCommand {
    pub program: PathBuf,
    pub args: Vec<OsString>,
    /// The worker's complete environment.
    pub env: BTreeMap<String, String>,
    pub cwd: PathBuf,
}

/// What one attempt asks of normal admission and the guard.
#[derive(Debug)]
pub struct AdmissionRequest {
    pub purpose: String,
    /// Guard ceiling; normal admission reserves it in full.
    pub memory_gib: u32,
    /// The guard's own execution limit, which starts at admission.
    pub execution_limit: Duration,
    /// Bounded queue wait (the remaining overall deadline); `None` waits until admitted.
    pub queue_limit: Option<Duration>,
    /// Fresh per attempt; it must not exist yet.
    pub report_dir: PathBuf,
    /// Checkout-lock duplicates (`duplicate_for_custodian`) for the guard's long-lived custodian.
    /// They never reach the worker, its environment or its job inputs.
    pub custody: Vec<File>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ExitInfo {
    Code(i32),
    Signal(i32),
    /// The guard stopped the worker before its status could be read.
    Unknown,
}

/// Who ended the worker, as the guard and bridge recorded it.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StoppedBy {
    /// Memory guard stop (`memory_limit`).
    Guard,
    /// The guard's own execution limit (`test_duration` or its timeout).
    Deadline,
    /// The bridge was asked to stop (SIGTERM/SIGHUP or controller loss).
    Cancel,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum CleanupReceipt {
    /// The guard's tree receipt reported complete cleanup and capacity close released.
    Confirmed,
    /// Anything less. The attempt must be held: no release, no relaunch.
    Unconfirmed { reason: String },
}

/// One running tree receipt of the pinned worker, as the bridge relays it: the receipt's time
/// (seconds since the epoch) and its owned processes as `(pid, started)`, shared services
/// excluded. Evidence only once [`quiescence`] accepts it.
#[derive(Clone, Debug, PartialEq)]
pub struct TreeSample {
    pub time: f64,
    pub processes: Vec<(u32, String)>,
}

/// Why a tree sample is not quiescence evidence.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SampleRefusal {
    /// Not a finite time.
    Malformed,
    /// Taken before the unit's terminal reply was received.
    Stale,
    /// Later than the controller's clock allows.
    Future,
    /// The pinned worker is not the only process.
    Unclassified,
    /// The only process is not the pinned worker.
    WrongIdentity,
    /// No process at all: the worker is gone, so this is no evidence for a live session.
    Empty,
}

/// How far a sample may claim to be ahead of the controller's clock, as in the bridge.
pub const SAMPLE_CLOCK_SKEW_SECONDS: f64 = 2.0;

/// @cc [owner:fontanierh,label:safety] quiescence-sample-evidence
/// A tree sample MUST count as quiescence evidence only when its time is finite, strictly after
/// the unit's terminal reply was received (`after`, the controller's clock), no later than the
/// controller's clock plus the skew, and its process list is exactly the session's pinned worker
/// (pid and start time). An absent, stale, future, malformed, empty sample, one with any other
/// process or one naming another identity MUST be refused, never repaired. The ordering assumes
/// the monitor's and the controller's wall clocks agree within `SAMPLE_CLOCK_SKEW_SECONDS` and
/// are not adjusted between the terminal reply and the sample; it is not causal ordering. See
/// tests/guard_adapter.rs (`quiescence_refuses_every_sample_that_is_not_fresh_exact_evidence`).
pub fn quiescence(
    sample: &TreeSample,
    pinned: &ProcessIdentity,
    after: f64,
    now: f64,
) -> Result<(), SampleRefusal> {
    if !sample.time.is_finite() || !after.is_finite() || !now.is_finite() {
        return Err(SampleRefusal::Malformed);
    }
    if sample.time <= after {
        return Err(SampleRefusal::Stale);
    }
    if sample.time > now + SAMPLE_CLOCK_SKEW_SECONDS {
        return Err(SampleRefusal::Future);
    }
    match sample.processes.as_slice() {
        [] => Err(SampleRefusal::Empty),
        [(pid, started)] if *pid == pinned.pid && *started == pinned.started => Ok(()),
        [_] => Err(SampleRefusal::WrongIdentity),
        _ => Err(SampleRefusal::Unclassified),
    }
}

#[derive(Clone, Debug, PartialEq)]
pub enum LaunchEvent {
    Queued,
    /// The broker's offer was accepted (`on_slot`); the job limit starts here.
    Admitted,
    /// The guard's pinned child identity.
    ChildStarted {
        worker: ProcessIdentity,
    },
    ChildExited {
        worker: ProcessIdentity,
        exit: ExitInfo,
        stopped_by: Option<StoppedBy>,
    },
    /// The admission owner finished; `receipts` is the guard report folder.
    Finished {
        cleanup: CleanupReceipt,
        receipts: PathBuf,
    },
    /// A running tree receipt of the pinned worker; never cleanup or crash evidence by itself.
    TreeSample(TreeSample),
    /// With checkout custody: the guard's custody monitor's own pinned identity, with the guard
    /// invocation whose cleanup receipt it belongs to. Published once, after `ChildStarted`.
    Monitor {
        monitor: ProcessIdentity,
        invocation: String,
    },
    /// The admission owner broke its event contract. Never cleanup or crash evidence.
    Fault(String),
}

#[derive(Clone, Debug, PartialEq)]
pub struct AttemptEvent {
    pub attempt: u32,
    pub event: LaunchEvent,
}

pub type Pipes = (Box<dyn Read + Send>, Box<dyn Write + Send>);

pub trait WorkerLauncher {
    type Attempt: WorkerAttempt;
    /// @cc [owner:fontanierh,label:safety] launcher-submit-error-means-nothing-started
    /// `Err` MUST mean no admission owner was started: every fallible preparation happens first.
    /// Once an admission owner exists, `submit` MUST return `Ok`, and that attempt MUST end through
    /// its own `Finished` event, unconfirmed unless the owner confirms cleanup.
    /// See tests/guard_adapter.rs.
    ///
    /// Queue one attempt. Only the admission owner starts now; no worker exists until the
    /// launcher reports `Admitted` and then `ChildStarted`. Stopping before that withdraws the
    /// request, so no child is spawned and nothing is charged.
    fn submit(
        &mut self,
        attempt: u32,
        command: &WorkerCommand,
        request: AdmissionRequest,
        events: Sender<AttemptEvent>,
    ) -> io::Result<Self::Attempt>;
}

pub trait WorkerAttempt {
    /// Ask the guard to stop or withdraw this attempt. `Ok(false)` means the admission owner had
    /// already exited and nothing was signalled. Never certifies cleanup or releases capacity.
    fn stop(&mut self) -> io::Result<bool>;
    /// The controller's protocol pipe ends (response reader, request writer), once.
    fn take_pipes(&mut self) -> Option<Pipes>;
}

/// One line on the bridge's event descriptor.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "event", rename_all = "snake_case", deny_unknown_fields)]
pub enum BridgeEvent {
    Queued {},
    Admitted {},
    ChildStarted {
        pid: u32,
        started: String,
        boot: String,
    },
    ChildExited {
        pid: u32,
        started: String,
        boot: String,
        returncode: Option<i32>,
        stopped_by: Option<StoppedBy>,
    },
    TreeSample {
        time: f64,
        processes: Vec<(u32, String)>,
    },
    Monitor {
        pid: u32,
        started: String,
        boot: String,
        invocation: String,
    },
    Fault {
        reason: String,
    },
    Finished {
        cleanup: String,
        reason: Option<String>,
    },
}

fn identity(pid: u32, started: String, boot: String) -> Result<ProcessIdentity, String> {
    if pid == 0 || started.is_empty() || boot.is_empty() {
        return Err("incomplete child identity".into());
    }
    Ok(ProcessIdentity { pid, boot, started })
}

/// Decode one bridge line. Anything malformed is a [`LaunchEvent::Fault`].
pub fn decode_event(line: &str, receipts: &std::path::Path) -> LaunchEvent {
    let event = match serde_json::from_str::<BridgeEvent>(line) {
        Ok(event) => event,
        Err(error) => return LaunchEvent::Fault(format!("malformed bridge event: {error}")),
    };
    let decoded = match event {
        BridgeEvent::Queued {} => Ok(LaunchEvent::Queued),
        BridgeEvent::Admitted {} => Ok(LaunchEvent::Admitted),
        BridgeEvent::ChildStarted { pid, started, boot } => {
            identity(pid, started, boot).map(|worker| LaunchEvent::ChildStarted { worker })
        }
        BridgeEvent::ChildExited {
            pid,
            started,
            boot,
            returncode,
            stopped_by,
        } => identity(pid, started, boot).map(|worker| LaunchEvent::ChildExited {
            worker,
            exit: match returncode {
                Some(code) if code >= 0 => ExitInfo::Code(code),
                Some(code) => ExitInfo::Signal(code.checked_neg().unwrap_or(i32::MAX)),
                None => ExitInfo::Unknown,
            },
            stopped_by,
        }),
        BridgeEvent::TreeSample { time, processes } => {
            Ok(LaunchEvent::TreeSample(TreeSample { time, processes }))
        }
        BridgeEvent::Monitor {
            pid,
            started,
            boot,
            invocation,
        } => {
            let invocation_ok = invocation.len() == 32
                && invocation
                    .bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b));
            identity(pid, started, boot).and_then(|monitor| {
                if invocation_ok {
                    Ok(LaunchEvent::Monitor {
                        monitor,
                        invocation,
                    })
                } else {
                    Err("a monitor identity without its guard invocation".into())
                }
            })
        }
        BridgeEvent::Fault { reason } => Err(format!("the bridge reported a fault: {reason}")),
        BridgeEvent::Finished { cleanup, reason } => match cleanup.as_str() {
            "confirmed" => Ok(LaunchEvent::Finished {
                cleanup: CleanupReceipt::Confirmed,
                receipts: receipts.to_path_buf(),
            }),
            "unconfirmed" => Ok(LaunchEvent::Finished {
                cleanup: CleanupReceipt::Unconfirmed {
                    reason: reason.unwrap_or_else(|| "unconfirmed cleanup".into()),
                },
                receipts: receipts.to_path_buf(),
            }),
            other => Err(format!("unknown cleanup state {other:?}")),
        },
    };
    decoded.unwrap_or_else(LaunchEvent::Fault)
}

/// The worker invocation the bridge reads from its spec descriptor.
#[derive(Serialize)]
struct BridgeSpec<'a> {
    program: &'a std::path::Path,
    args: Vec<String>,
    env: &'a BTreeMap<String, String>,
}

/// Launches each attempt through the existing guard via the bridge program `bridge`
/// (for example the checkout's interpreter with `-m atelier.build_v2.guarded_worker`).
pub struct GuardedLauncher {
    pub bridge: Vec<OsString>,
}

pub struct GuardedAttempt {
    child: Arc<Mutex<Child>>,
    pipes: Option<Pipes>,
    /// Held only to signal controller loss: the bridge stops its run when this closes.
    _liveness: PipeWriter,
}

fn clear_cloexec(fd: RawFd) -> io::Result<()> {
    // SAFETY: fcntl on a descriptor number is async-signal-safe and touches no Rust state.
    if unsafe { libc::fcntl(fd, libc::F_SETFD, 0) } == -1 {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

/// One past the highest descriptor number to sweep before exec: the soft descriptor limit,
/// capped so a huge limit cannot make every launch slow, and always past the bridge's own.
fn sweep_limit(own: &[RawFd]) -> RawFd {
    let mut limit = libc::rlimit {
        rlim_cur: 0,
        rlim_max: 0,
    };
    // SAFETY: getrlimit writes only the struct we pass.
    let soft = if unsafe { libc::getrlimit(libc::RLIMIT_NOFILE, &mut limit) } == 0 {
        RawFd::try_from(limit.rlim_cur.min(1 << 16)).unwrap_or(1 << 16)
    } else {
        1 << 16
    };
    let highest = own.iter().copied().max().unwrap_or(2);
    soft.max(highest.saturating_add(1))
}

fn text(value: &std::ffi::OsStr) -> io::Result<String> {
    value.to_str().map(str::to_owned).ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidInput,
            "worker arguments must be UTF-8",
        )
    })
}

impl WorkerLauncher for GuardedLauncher {
    type Attempt = GuardedAttempt;

    /// @cc [owner:fontanierh,label:safety] guard-adapter-actual-admission
    /// A worker MUST start only as the existing guard's child, after normal admission, through
    /// the bridge's `guarded.run` call. Only the two protocol pipe ends MAY reach the worker;
    /// event, liveness, spec and custody descriptors MUST reach only the bridge. The adapter MUST
    /// signal only its own unreaped bridge, with SIGTERM, and never the worker or a stale PID.
    /// See tests/guard_adapter.rs.
    fn submit(
        &mut self,
        attempt: u32,
        command: &WorkerCommand,
        request: AdmissionRequest,
        events: Sender<AttemptEvent>,
    ) -> io::Result<GuardedAttempt> {
        let Some((program, prefix)) = self.bridge.split_first() else {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "no bridge program",
            ));
        };
        // Everything that can fail happens before the spawn: afterwards `submit` never errs.
        let spec = serde_json::to_vec(&BridgeSpec {
            program: &command.program,
            args: command
                .args
                .iter()
                .map(|arg| text(arg))
                .collect::<io::Result<_>>()?,
            env: &command.env,
        })
        .map_err(io::Error::other)?;
        fs::create_dir(&request.report_dir)?;
        let log = File::create(request.report_dir.join("bridge.log"))?;
        let (request_reader, request_writer) = io::pipe()?;
        let (response_reader, response_writer) = io::pipe()?;
        let (event_reader, event_writer) = io::pipe()?;
        let (liveness_reader, liveness_writer) = io::pipe()?;
        let (spec_reader, mut spec_writer) = io::pipe()?;
        let mut inherited = vec![
            request_reader.as_raw_fd(),
            response_writer.as_raw_fd(),
            event_writer.as_raw_fd(),
            liveness_reader.as_raw_fd(),
            spec_reader.as_raw_fd(),
        ];
        inherited.extend(request.custody.iter().map(AsRawFd::as_raw_fd));
        let mut bridge = Command::new(program);
        bridge
            .args(prefix)
            .arg("--report")
            .arg(&request.report_dir)
            .arg("--purpose")
            .arg(&request.purpose)
            .arg("--memory-gib")
            .arg(request.memory_gib.to_string())
            .arg("--timeout")
            .arg(request.execution_limit.as_secs_f64().to_string())
            .arg("--events-fd")
            .arg(event_writer.as_raw_fd().to_string())
            .arg("--liveness-fd")
            .arg(liveness_reader.as_raw_fd().to_string())
            .arg("--spec-fd")
            .arg(spec_reader.as_raw_fd().to_string())
            .arg("--request-fd")
            .arg(request_reader.as_raw_fd().to_string())
            .arg("--response-fd")
            .arg(response_writer.as_raw_fd().to_string());
        if let Some(limit) = request.queue_limit {
            bridge
                .arg("--queue-wait")
                .arg(limit.as_secs_f64().to_string());
        }
        for file in &request.custody {
            bridge.arg("--custody-fd").arg(file.as_raw_fd().to_string());
        }
        bridge
            .current_dir(&command.cwd)
            .stdin(Stdio::null())
            .stdout(log.try_clone()?)
            .stderr(log);
        let exact = inherited.clone();
        let limit = sweep_limit(&exact);
        // SAFETY: between fork and exec this only calls fcntl (async-signal-safe) and allocates
        // nothing: it clears close-on-exec on exactly the bridge's descriptors and sets it on
        // every other one, so descriptors this process inherited never reach the bridge.
        unsafe {
            bridge.pre_exec(move || {
                for fd in 3..limit {
                    if exact.contains(&fd) {
                        clear_cloexec(fd)?;
                    } else {
                        libc::fcntl(fd, libc::F_SETFD, libc::FD_CLOEXEC);
                    }
                }
                Ok(())
            });
        }
        let child = bridge.spawn()?;
        // The bridge now owns its ends and the custody duplicates; keep none of them here.
        drop((
            request_reader,
            response_writer,
            event_writer,
            liveness_reader,
            spec_reader,
        ));
        drop(request.custody);
        let child = Arc::new(Mutex::new(child));
        let written = spec_writer.write_all(&spec);
        drop(spec_writer);
        let mut handle = GuardedAttempt {
            child: Arc::clone(&child),
            pipes: Some((Box::new(response_reader), Box::new(request_writer))),
            _liveness: liveness_writer,
        };
        if written.is_err() {
            // An admission owner exists, so this is not a submit error. Without its spec the
            // bridge cannot start a worker: withdraw it, offer no protocol pipes, and let the
            // attempt end through its own (unconfirmed) Finished event below.
            handle.pipes = None;
            let _ = handle.stop();
        }
        let reaper = child;
        let receipts = request.report_dir.clone();
        thread::spawn(move || {
            let mut finished = false;
            for line in BufReader::new(event_reader).lines() {
                let event = match line {
                    Ok(line) => decode_event(&line, &receipts),
                    Err(error) => LaunchEvent::Fault(format!("bridge event read failed: {error}")),
                };
                finished |= matches!(event, LaunchEvent::Finished { .. });
                if events.send(AttemptEvent { attempt, event }).is_err() {
                    break;
                }
            }
            if !finished {
                let _ = events.send(AttemptEvent {
                    attempt,
                    event: LaunchEvent::Finished {
                        cleanup: CleanupReceipt::Unconfirmed {
                            reason: "the admission owner ended without a cleanup receipt".into(),
                        },
                        receipts,
                    },
                });
            }
            // Reap our own bridge; stop() then sees the cached status and signals nothing.
            if let Ok(mut child) = reaper.lock() {
                let _ = child.wait();
            }
        });
        Ok(handle)
    }
}

impl GuardedAttempt {
    /// Wait for this attempt's own bridge to exit (it is reaped exactly once either way).
    pub fn wait(&mut self) -> io::Result<std::process::ExitStatus> {
        self.child
            .lock()
            .map_err(|_| io::Error::other("bridge handle poisoned"))?
            .wait()
    }
}

impl WorkerAttempt for GuardedAttempt {
    fn stop(&mut self) -> io::Result<bool> {
        let mut child = self
            .child
            .lock()
            .map_err(|_| io::Error::other("bridge handle poisoned"))?;
        // try_wait reaps and caches an exit; while it reports None the PID is still our own
        // unreaped child, so it cannot have been reused.
        if child.try_wait()?.is_some() {
            return Ok(false);
        }
        let pid = libc::pid_t::try_from(child.id())
            .map_err(|_| io::Error::other("bridge PID out of range"))?;
        // SAFETY: kill with a PID we still hold unreaped and a constant signal number.
        if unsafe { libc::kill(pid, libc::SIGTERM) } == -1 {
            return Err(io::Error::last_os_error());
        }
        Ok(true)
    }

    fn take_pipes(&mut self) -> Option<Pipes> {
        self.pipes.take()
    }
}
