//! The C5c resident window's setup sequence, shared by `examples/resident_window.rs` (which then
//! launches real guarded sessions) and `tests/resident_window_setup.rs` (which runs the same
//! sequence on any host and stops before any launch). Included by `#[path]` in both; it is not
//! part of the library API and is deliberately not declared in `tests/support/mod.rs`.
#![allow(dead_code)]

use atelier_build_v2::checkout_locks::{BuildGuard, CheckoutLocks, ContentReadGuard};
use atelier_build_v2::completion::CompletionWork;
use atelier_build_v2::failure_policy::{Limits, MonoTime};
use atelier_build_v2::guard_adapter::WorkerCommand;
use atelier_build_v2::install::{InstallPolicy, LeaseIdentity, ProjectNamespace, ReceiptReader};
use atelier_build_v2::keys::{ImplementationIdentity, KeyContext, PreparedUnit, prepare};
use atelier_build_v2::launch::{self, PYTHON_JOB_LOOP_VERSION};
use atelier_build_v2::leases::{LeaseStore, ProcessIdentity};
use atelier_build_v2::python_worker::{PYTHON_WORKER_FILES, PythonWorkerBundle};
use atelier_build_v2::results::{ResultStore, WriteTransaction};
use atelier_build_v2::schema::{
    Declaration, Destination, Item, Op, OutputFile, Provenance, SCHEMA_VERSION, Unit,
};
use atelier_build_v2::session_lifecycle::{
    Refusal, SessionCommand, SessionConfig, SessionInput, SessionLifecycle, UnitPlan, UnitRecord,
};
use atelier_build_v2::source_hashes::SourceHashCache;
use atelier_build_v2::validate::{OpDefinition, SnapshotEntry, SourceSnapshot, validate};
use atelier_build_v2::worker_lifecycle::{CustodyIdentity, JobSandbox, LockScope, SessionKey};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File};
use std::os::fd::AsRawFd;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::time::Duration;

/// Per-unit limits: work, cleanup, and the unit's own deadline from submission (its queue wait
/// included). The cleanup limit covers the quiescence bound plus the session's own cleanup limit,
/// as the session lifecycle requires (`Refusal::CleanupBelowQuiescence`).
pub const UNIT_LIMITS: Limits = Limits {
    job: Duration::from_secs(120),
    cleanup: Duration::from_secs(80),
    overall: Some(Duration::from_secs(300)),
};
/// The session's own cleanup limit, after it stops or shuts down.
pub const SESSION_CLEANUP: Duration = Duration::from_secs(60);
/// How long one session may live.
pub const SESSION_LIFETIME: Duration = Duration::from_secs(600);
/// How long an idle, open session keeps its worker.
pub const IDLE: Duration = Duration::from_secs(3);
/// Quiescence evidence must arrive within this bound of a unit's terminal reply.
pub const QUIESCENCE: Duration = Duration::from_secs(10);
/// Each case's name and its units in submission order, as (unit id, declared unit).
pub const CASE_UNITS: [(&str, &[(&str, &str)]); 5] = [
    ("s1-single", &[("a", "a")]),
    ("s2-reuse", &[("b", "b"), ("a", "a")]),
    ("s3-aba", &[("a1", "a"), ("b", "b"), ("a2", "a")]),
    ("s5-cancel", &[("spin", "spin")]),
    ("s6-originals", &[("a", "a")]),
];

/// The session configuration every case runs with.
pub fn session_config() -> SessionConfig {
    SessionConfig {
        cleanup: SESSION_CLEANUP,
        lifetime: SESSION_LIFETIME,
        idle: IDLE,
        quiescence: Some(QUIESCENCE),
        custodian: true,
    }
}

/// The plan every case submits for `unit`.
pub fn unit_plan(unit: &str) -> UnitPlan {
    UnitPlan {
        id: unit.to_string(),
        limits: UNIT_LIMITS,
    }
}

/// The job's output root inside its attempt folder (`jobs/<unit>-<attempt>`): the Python job
/// loop writes every declared output path relative to it.
pub const OUTPUT_ROOT: &str = "output";
/// Every unit's one declared output, relative to the job's output root. The spin op writes it as
/// its first action, so it is also the running marker.
pub const MARKER_PATH: &str = "output/piece.txt";

/// Where the attempt staged in `job` (a `jobs/<unit>-<attempt>` folder) writes its declared
/// output.
pub fn job_output(job: &Path) -> PathBuf {
    job.join(OUTPUT_ROOT).join(MARKER_PATH)
}

/// The running marker of `unit`'s job in `jobs`: its declared output, once it starts with
/// `started`.
pub fn running_marker(jobs: &Path, unit: &str) -> Option<PathBuf> {
    let prefix = format!("{unit}-");
    fs::read_dir(jobs)
        .ok()?
        .flatten()
        .filter(|entry| entry.file_name().to_string_lossy().starts_with(&prefix))
        .map(|entry| job_output(&entry.path()))
        .find(|path| fs::read(path).is_ok_and(|bytes| bytes.starts_with(b"started")))
}

/// Every case's plans, in submission order.
pub fn case_plans(units: &[(&str, &str)]) -> Vec<UnitPlan> {
    units.iter().map(|(unit, _)| unit_plan(unit)).collect()
}

/// One unit the session lifecycle would refuse, as the session reports it.
#[derive(Clone, Debug, PartialEq)]
pub struct Refused {
    pub unit: String,
    /// The typed reason; `None` when the lifecycle failed instead of refusing.
    pub reason: Option<Refusal>,
    /// The refusal's own text (the record's `abort`), or the lifecycle error.
    pub text: String,
}

/// The preflight both the example (before any case folder or launch) and the hosted test run:
/// the exact limits (unit cleanup 80 s, session cleanup 60 s, quiescence 10 s), then every plan
/// submitted in order to the pure production session lifecycle with `config`, through its own
/// refusal path. Returns every refusal, verbatim.
pub fn preflight(config: SessionConfig, plans: &[UnitPlan]) -> Result<(), Vec<Refused>> {
    let mut refused = vec![];
    let tuple = |text: String| Refused {
        unit: String::new(),
        reason: None,
        text,
    };
    if config.cleanup != Duration::from_secs(60)
        || config.quiescence != Some(Duration::from_secs(10))
    {
        refused.push(tuple(format!(
            "session limits are not cleanup 60 s and quiescence 10 s: {config:?}"
        )));
    }
    for plan in plans {
        if plan.limits.cleanup != Duration::from_secs(80) {
            refused.push(Refused {
                unit: plan.id.clone(),
                reason: None,
                text: format!("unit cleanup is not 80 s: {:?}", plan.limits),
            });
        }
    }
    let at = MonoTime::from_elapsed(Duration::ZERO);
    let mut lifecycle = SessionLifecycle::new(config);
    for plan in plans {
        match lifecycle.on(at, SessionInput::Submit(plan.clone())) {
            Ok(commands) => {
                for command in commands {
                    if let SessionCommand::Refused { unit, reason } = command {
                        let record = UnitRecord::refused(unit.clone(), reason);
                        refused.push(Refused {
                            unit,
                            reason: Some(reason),
                            text: record.abort.unwrap_or_default(),
                        });
                    }
                }
            }
            Err(error) => refused.push(Refused {
                unit: plan.id.clone(),
                reason: None,
                text: format!("{error:?}"),
            }),
        }
    }
    if refused.is_empty() {
        Ok(())
    } else {
        Err(refused)
    }
}

/// The admission ceiling of one session: the full job profile, as in the C5b/C7 window.
pub const MEMORY_GIB: u32 = 10;
/// The proof's install-owner namespace.
pub const PROJECT: &str = "resident-window";
/// The proof's one install root, relative to its checkout. Every unit stores its output only in
/// the cache (`Destination::Store`), so nothing is ever written here; the B3 reader still requires
/// a non-empty, valid install policy, and `validate` checks the declaration against the same one.
pub const INSTALL_ROOTS: [&str; 1] = ["games/resident-window/Content"];
/// The declared units: `a` and `b` write their one output; `spin` writes it, then runs until
/// cancelled.
pub const UNITS: [&str; 3] = ["a", "b", "spin"];

/// The op sources, as the job's code closure sees them.
pub fn op_sources() -> BTreeMap<&'static str, &'static [u8]> {
    BTreeMap::from([
        (
            "ops/a.py",
            b"def run(context):\n    context.output(context.outputs[0]).write_text('A\\n')\n"
                as &[u8],
        ),
        (
            "ops/b.py",
            b"def run(context):\n    context.output(context.outputs[0]).write_text('B\\n')\n",
        ),
        (
            "ops/spin.py",
            b"def run(context):\n    context.output(context.outputs[0]).write_text('started\\n')\n    n = 0\n    while True:\n        n += 1\n",
        ),
    ])
}

pub fn declaration() -> Declaration {
    let unit = |id: &str| Unit {
        id: id.into(),
        op: Op {
            kind: "resident-proof".into(),
            version: "1".into(),
        },
        script: format!("ops/{id}.py"),
        code: vec![format!("ops/{id}.py")],
        inputs: vec![],
        params: BTreeMap::new(),
        conditional: None,
        output_groups: vec![],
        outputs: vec![Item {
            id: "piece".into(),
            logical_path: format!("/Data/resident/{id}"),
            class: "Blob".into(),
            destination: Destination::Store,
            files: vec![OutputFile {
                path: MARKER_PATH.into(),
                install_path: None,
                required: true,
            }],
        }],
    };
    Declaration {
        schema_version: SCHEMA_VERSION,
        cache_version: "resident-window-1".into(),
        units: UNITS.iter().map(|id| unit(id)).collect(),
    }
}

pub fn install_roots() -> Vec<String> {
    INSTALL_ROOTS.iter().map(|root| root.to_string()).collect()
}

pub fn install_policy() -> Result<InstallPolicy, String> {
    Ok(InstallPolicy {
        project: ProjectNamespace::new(PROJECT).map_err(|error| error.to_string())?,
        allowed_install_roots: install_roots(),
    })
}

pub fn provenance() -> Provenance {
    Provenance {
        checkout: PROJECT.into(),
        branch: PROJECT.into(),
        commit: PROJECT.into(),
        dirty: false,
        built_at: PROJECT.into(),
    }
}

pub fn lease_identity(owner: &ProcessIdentity) -> LeaseIdentity {
    LeaseIdentity {
        provenance: provenance(),
        owner: owner.clone(),
        workers: vec![],
        upstream_result_keys: BTreeSet::new(),
    }
}

/// The three frozen real worker files, read once.
pub fn worker_snapshot(source: &Path) -> Result<SourceSnapshot, String> {
    PYTHON_WORKER_FILES
        .into_iter()
        .map(|name| {
            fs::read(source.join(name))
                .map(|bytes| (name.to_string(), SnapshotEntry::File(bytes)))
                .map_err(|error| format!("cannot read worker file {name}: {error}"))
        })
        .collect()
}

/// Materialize the frozen worker bytes read-only and build the production loop command.
/// `python` must be absolute: the loop runs with `/` as its working folder.
pub fn worker_command(
    python: &Path,
    snapshot: &SourceSnapshot,
    folder: &Path,
) -> Result<WorkerCommand, String> {
    if !python.is_absolute() || !folder.is_absolute() {
        return Err("the interpreter and worker folder must be absolute paths".into());
    }
    let error = |error: std::io::Error| error.to_string();
    fs::create_dir(folder).map_err(error)?;
    for (name, entry) in snapshot {
        let SnapshotEntry::File(bytes) = entry else {
            return Err(format!("{name} is not a file"));
        };
        let path = folder.join(name);
        fs::write(&path, bytes).map_err(error)?;
        fs::set_permissions(&path, fs::Permissions::from_mode(0o444)).map_err(error)?;
    }
    fs::set_permissions(folder, fs::Permissions::from_mode(0o555)).map_err(error)?;
    let command = launch::WorkerCommand::python_job_loop(
        python.to_path_buf(),
        folder.join("python_worker.py"),
    )
    .map_err(error)?;
    Ok(WorkerCommand {
        program: command.program,
        args: command.args.into_iter().map(Into::into).collect(),
        env: command.env,
        cwd: command.cwd,
    })
}

/// What every case shares.
pub struct World {
    pub command: WorkerCommand,
    pub worker: ImplementationIdentity,
    pub prepared: BTreeMap<String, PreparedUnit>,
    pub sources: BTreeMap<&'static str, &'static [u8]>,
}

/// The real worker identity and command, and every declared unit validated and prepared.
pub fn world(python: &Path, worker_source: &Path, worker_folder: &Path) -> Result<World, String> {
    let snapshot = worker_snapshot(worker_source)?;
    let worker = PythonWorkerBundle::from_snapshot(&snapshot)?.identity();
    let command = worker_command(python, &snapshot, worker_folder)?;
    let declaration = declaration();
    let sources = op_sources();
    let ops: SourceSnapshot = sources
        .iter()
        .map(|(name, bytes)| (name.to_string(), SnapshotEntry::File(bytes.to_vec())))
        .collect();
    let registry = BTreeMap::from([(
        ("resident-proof".to_string(), "1".to_string()),
        OpDefinition {
            inputs: BTreeMap::new(),
            output_classes: BTreeSet::from(["Blob".to_string()]),
            params: BTreeMap::new(),
        },
    )]);
    let validated = validate(&declaration, &registry, &ops, &install_roots())
        .map_err(|error| format!("validation failed: {error}"))?;
    let validator = ImplementationIdentity {
        version: "resident-window-1".into(),
        digest: "0".repeat(64),
    };
    let mut prepared = BTreeMap::new();
    for unit in UNITS {
        let unit_prepared = prepare(
            &declaration,
            &validated,
            unit,
            &KeyContext {
                snapshot: &ops,
                versions: &BTreeMap::new(),
                produced: &BTreeMap::new(),
                produced_groups: &BTreeMap::new(),
                staged_inputs: &BTreeMap::new(),
                worker: &worker,
                validator: &validator,
            },
            &mut SourceHashCache::default(),
        )?;
        prepared.insert(unit.to_string(), unit_prepared);
    }
    Ok(World {
        command,
        worker,
        prepared,
        sources,
    })
}

/// The two real leases of one unit, bound before any Run.
pub struct Leases {
    pub local: CompletionWork,
    pub cas: WriteTransaction,
}

/// One case's real B3 locks, custody, stores and leases, all bound before any launch.
pub struct CaseSetup {
    pub checkout: PathBuf,
    pub reports: PathBuf,
    pub jobs: PathBuf,
    /// The controller's original guards, distinct from the custody duplicates.
    pub originals: Option<(BuildGuard, ContentReadGuard)>,
    /// The custodian duplicates that become the session's custody.
    pub custody: Vec<File>,
    pub custody_set: BTreeSet<CustodyIdentity>,
    pub lock_files: BTreeSet<(u64, u64)>,
    pub lock_paths: Vec<PathBuf>,
    pub session_fds: BTreeSet<String>,
    pub store: ResultStore,
    pub local_leases: LeaseStore,
    pub leases: BTreeMap<String, Leases>,
    pub lease_ids: BTreeMap<String, (String, String)>,
    pub key: SessionKey,
}

/// Locks, custody, stores and leases for `units` (unit id, declared unit) under a fresh `root`.
pub fn case_setup(
    world: &World,
    owner: &ProcessIdentity,
    root: &Path,
    units: &[(&str, &str)],
) -> Result<CaseSetup, String> {
    let io = |error: std::io::Error| error.to_string();
    let lock = |error: atelier_build_v2::checkout_locks::LockError| error.to_string();
    let install = |error: atelier_build_v2::install::InstallError| error.to_string();
    let result = |error: atelier_build_v2::results::ResultError| error.to_string();
    let checkout = root.join("checkout");
    let reports = root.join("reports");
    let jobs = root.join("jobs");
    for folder in [&checkout, &reports, &jobs] {
        fs::create_dir_all(folder).map_err(io)?;
    }
    let checkout = checkout.canonicalize().map_err(io)?;
    let locks = CheckoutLocks::open(&checkout).map_err(lock)?;
    let build = locks.try_build_exclusive().map_err(lock)?;
    let read = locks.try_read_content().map_err(lock)?;
    let custody = vec![
        build.duplicate_for_custodian().map_err(io)?,
        read.duplicate_for_custodian().map_err(io)?,
    ];
    let custody_set: BTreeSet<CustodyIdentity> = [
        CustodyIdentity::of(&custody[0], LockScope::Exclusive).map_err(io)?,
        CustodyIdentity::of(&custody[1], LockScope::Shared).map_err(io)?,
    ]
    .into();
    let lock_files = custody_set
        .iter()
        .map(|identity| (identity.device, identity.inode))
        .collect();
    let lock_paths = ["build.lock", "content.lock"]
        .iter()
        .map(|name| checkout.join("build/build-v2/install").join(name))
        .collect();
    let session_fds = custody
        .iter()
        .map(|file| file.as_raw_fd().to_string())
        .collect();

    let reader = ReceiptReader::open(&checkout, install_policy()?).map_err(install)?;
    let store = ResultStore::open(root.join("cache")).map_err(result)?;
    let mut leases = BTreeMap::new();
    for (unit, declared) in units {
        let prepared = world
            .prepared
            .get(*declared)
            .ok_or_else(|| format!("unknown declared unit {declared}"))?;
        let local = reader
            .begin_completion(&build, prepared, lease_identity(owner))
            .map_err(install)?;
        let cas = store
            .begin(
                prepared,
                provenance(),
                owner.clone(),
                vec![],
                BTreeSet::new(),
            )
            .map_err(result)?;
        leases.insert(unit.to_string(), Leases { local, cas });
    }
    // The completions folder exists only once `begin_completion` has created it.
    let local_leases =
        LeaseStore::open(checkout.join("build/build-v2/install/completions")).map_err(io)?;
    let lease_ids = leases
        .iter()
        .map(|(unit, leases)| {
            (
                unit.clone(),
                (
                    leases.local.lease().id.clone(),
                    leases.cas.lease().id.clone(),
                ),
            )
        })
        .collect();
    let key = SessionKey {
        worker_version: PYTHON_JOB_LOOP_VERSION.into(),
        command: world.command.clone(),
        memory_gib: MEMORY_GIB,
        sandbox: JobSandbox::NoFork,
        custody: custody_set.clone(),
    };
    Ok(CaseSetup {
        checkout,
        reports,
        jobs,
        originals: Some((build, read)),
        custody,
        custody_set,
        lock_files,
        lock_paths,
        session_fds,
        store,
        local_leases,
        leases,
        lease_ids,
        key,
    })
}

/// Whether the lease `id` in `store` records `identity`, read from disk under the store's
/// metadata mutex, as every lease reader does.
pub fn lease_holds(store: &LeaseStore, id: &str, identity: &ProcessIdentity) -> Result<(), String> {
    let records = store
        .lock()
        .and_then(|guard| guard.leases())
        .map_err(|error| error.to_string())?;
    let record = records
        .iter()
        .find(|record| record.id == id)
        .ok_or_else(|| format!("lease {id} is not on disk"))?;
    if record.workers.contains(identity) {
        Ok(())
    } else {
        Err(format!("lease {id} does not record {identity:?}"))
    }
}

/// Whether a second open of the same checkout's B3 locks is refused the build lock, which every
/// installer needs.
pub fn installer_busy(checkout: &Path) -> bool {
    CheckoutLocks::open(checkout).is_ok_and(|locks| {
        matches!(
            locks.try_build_exclusive(),
            Err(atelier_build_v2::checkout_locks::LockError::Busy)
        )
    })
}

/// Whether a second reader of the same checkout is admitted (content custody is shared).
pub fn reader_admitted(checkout: &Path) -> bool {
    CheckoutLocks::open(checkout).is_ok_and(|locks| locks.try_read_content().is_ok())
}
