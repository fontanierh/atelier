//! Private operational authority parent for the existing legacy Python scheduler.
//! This is neither a scheduler nor an admitted native job. Its captured provider is
//! the explicit semantic trust boundary; file witnesses alone do not prove Call semantics.
use crate::checkout_locks::CheckoutLocks;
use crate::install_fs::{FileObservation, RootFs};
use crate::leases::ProcessIdentity;
use crate::legacy_epoch::{EpochError, selection as epoch};
use crate::legacy_host_launch::{self as launch, LockIdentity, SchedulerChild, TripleCustody};
use crate::legacy_host_launch::{CLOCK_DOMAIN, Deadline};
use crate::paths::relative_path;
use crate::source_hashes::{sha256, valid_digest};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs::File;
use std::io::{self, Read};
use std::os::fd::AsRawFd;
use std::path::{Path, PathBuf};

const VERSION: u32 = 2;
pub const MAX_MESSAGE_BYTES: usize = 64 * 1024;
const SOURCE_MANIFEST: &str = "platform/build-v2/controller-sources.json";
const BOOTSTRAP: &str = "platform/studio/atelier/build_v2/legacy_bootstrap.py";
const PROVIDER: &str = "platform/studio/atelier/build_v2/legacy_qualification.py";

/// Startup/config data is not an epoch proof. The compiled distribution identity,
/// owned spawn and captured issuer are independently verified before authority exists.
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HostConfig {
    pub version: u32,
    pub nonce: String,
    pub selection: String,
    pub checkout: PathBuf,
    pub output: PathBuf,
    pub distribution: PathBuf,
    pub source_identity: String,
    pub interpreter: PathBuf,
    pub interpreter_digest: String,
    pub interpreter_role: PathBuf,
    pub python_context: PythonContext,
    pub operational_environment: OperationalEnvironment,
    pub game_issuer: GameIssuer,
    pub control_directory: String,
    pub deadline_ns: u64,
    pub startup_budget_ns: u64,
    pub cleanup_budget_ns: u64,
    pub boot: String,
    pub clock_domain: String,
    pub scheduler_request: SchedulerRequest,
}
/// Installed interpreter context observed by the captured original constructor.
/// These paths are platform context, not game inputs or a new semantic issuer.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PythonContext {
    pub platform_roots: Vec<PathBuf>,
    pub purelib: PathBuf,
    pub platlib: PathBuf,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct OperationalEnvironment {
    #[serde(deserialize_with = "required_optional")]
    pub agent: Option<String>,
    #[serde(deserialize_with = "required_optional")]
    pub cache: Option<PathBuf>,
    #[serde(deserialize_with = "required_optional")]
    pub build_root: Option<PathBuf>,
    pub path: String,
}
fn required_optional<'de, D, T>(deserializer: D) -> Result<Option<T>, D::Error>
where
    D: serde::Deserializer<'de>,
    T: Deserialize<'de>,
{
    Option::<T>::deserialize(deserializer)
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SchedulerRequest {
    pub path: String,
    pub digest: String,
    pub size: u64,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct OrdinaryRequest {
    version: u32,
    game: String,
    wanted: Vec<String>,
    options: OrdinaryOptions,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct OrdinaryOptions {
    verify: bool,
    max_heavy_commands: Option<u32>,
    fail_fast: bool,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GameIssuer {
    pub project: String,
    pub root: PathBuf,
    pub files: Vec<String>,
    pub digest: String,
    pub profile: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SourceManifest {
    version: u32,
    files: Vec<String>,
}
/// Only actual verified captured bytes mint this. Never Deserialize a proof capability.
struct FrozenIssuer {
    controller: String,
    game: String,
    project: String,
    profile: String,
    distribution: RootFs,
    request_digest: String,
    selector: Vec<String>,
    required_sources: Vec<epoch::Witness>,
}
fn error(message: impl ToString) -> io::Error {
    launch::invalid(message)
}
fn read_bounded(fs: &RootFs, path: &str, maximum: usize, readonly: bool) -> io::Result<Vec<u8>> {
    let mut f = fs.file(path)?;
    let before = FileObservation::from_metadata(&f.metadata()?);
    if before.size > maximum as u64 || (readonly && before.mode & 0o222 != 0) {
        return Err(error("captured source not bounded/readonly"));
    }
    let mut bytes = vec![];
    f.by_ref()
        .take(maximum as u64 + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() > maximum
        || before != FileObservation::from_metadata(&f.metadata()?)
        || fs.observe(path)?.as_ref() != Some(&before)
    {
        return Err(error("captured source changed"));
    }
    Ok(bytes)
}
fn capture_digest(
    fs: &RootFs,
    names: &[String],
    manifest: Option<(&str, Vec<u8>)>,
) -> io::Result<String> {
    if names.is_empty() || names.len() > 256 {
        return Err(error("source closure count"));
    }
    let mut files = BTreeMap::new();
    if let Some((name, bytes)) = manifest {
        files.insert(name.to_string(), bytes);
    }
    let mut total = files.values().map(Vec::len).sum::<usize>();
    for name in names {
        relative_path(name, false).map_err(error)?;
        if files.contains_key(name) {
            return Err(error("duplicate captured source name"));
        }
        let bytes = read_bounded(fs, name, 8 * 1024 * 1024, true)?;
        total = total
            .checked_add(bytes.len())
            .ok_or_else(|| error("source closure size"))?;
        if total > 32 * 1024 * 1024 {
            return Err(error("source closure size"));
        }
        files.insert(name.clone(), bytes);
    }
    let mut digest = Sha256::new();
    for (name, bytes) in files {
        digest.update((name.len() as u64).to_be_bytes());
        digest.update(name.as_bytes());
        digest.update((bytes.len() as u64).to_be_bytes());
        digest.update(bytes);
    }
    Ok(format!("{:x}", digest.finalize()))
}
/// A private capsule hash is not original-source authority. Bind every named game
/// helper to stable actual checkout bytes and retain those exact freshness witnesses.
fn verify_game_sources(config: &GameIssuer, checkout: &Path) -> io::Result<Vec<epoch::Witness>> {
    if config.profile != format!("games/{}/legacy_qualification.py", config.project) {
        return Err(error("unsupported game issuer entry"));
    }
    let live = RootFs::open(checkout)?;
    let captured = RootFs::open(&config.root)?;
    let mut sources = Vec::new();
    for name in &config.files {
        let frozen = read_bounded(&captured, name, 8 * 1024 * 1024, true)?;
        let actual = read_bounded(&live, name, 8 * 1024 * 1024, false)?;
        if frozen != actual {
            return Err(error(
                "game issuer capsule differs from original declared source",
            ));
        }
        let observed = live
            .observe(name)?
            .ok_or_else(|| error("game issuer source vanished"))?;
        sources.push(epoch::Witness {
            path: name.clone(),
            fact: epoch::Fact::File {
                digest: sha256(&actual),
                size: actual.len() as u64,
                mode: observed.mode,
            },
        });
    }
    if sources.is_empty() || !config.files.contains(&config.profile) {
        return Err(error("missing original game issuer source"));
    }
    Ok(sources)
}
impl FrozenIssuer {
    fn verify(config: &HostConfig, original: &OrdinaryRequest) -> io::Result<Self> {
        if config.version != VERSION
            || !valid_digest(&config.source_identity)
            || !valid_digest(&config.game_issuer.digest)
        {
            return Err(error("invalid host version/source identity"));
        }
        if crate::controller::source_identity() != Some(config.source_identity.as_str()) {
            return Err(error("host binary has a different frozen distribution"));
        }
        let fs = RootFs::open(&config.distribution)?;
        let manifest = read_bounded(&fs, SOURCE_MANIFEST, 2 * 1024 * 1024, true)?;
        let parsed: SourceManifest = strict_record(&manifest)?;
        if parsed.version != 1
            || !parsed.files.iter().any(|p| p == BOOTSTRAP)
            || !parsed.files.iter().any(|p| p == PROVIDER)
        {
            return Err(error("host source closure missing bootstrap/provider"));
        }
        let actual = capture_digest(&fs, &parsed.files, Some((SOURCE_MANIFEST, manifest)))?;
        if actual != config.source_identity {
            return Err(error("captured controller source identity mismatch"));
        }
        let gamefs = RootFs::open(&config.game_issuer.root)?;
        if capture_digest(&gamefs, &config.game_issuer.files, None)? != config.game_issuer.digest {
            return Err(error("captured game issuer identity mismatch"));
        }
        if !config
            .game_issuer
            .files
            .contains(&config.game_issuer.profile)
        {
            return Err(error("game semantic provider not captured"));
        }
        relative_path(&config.game_issuer.profile, false).map_err(error)?;
        let required_sources = verify_game_sources(&config.game_issuer, &config.checkout)?;
        Ok(Self {
            controller: actual,
            game: config.game_issuer.digest.clone(),
            project: config.game_issuer.project.clone(),
            profile: config.game_issuer.profile.clone(),
            distribution: fs,
            request_digest: config.scheduler_request.digest.clone(),
            selector: original.wanted.clone(),
            required_sources,
        })
    }
    fn selection(
        &self,
        mut observation: epoch::SelectionObservation,
        fs: &RootFs,
        deadline: Deadline,
    ) -> Result<epoch::QualifiedSelection, EpochError> {
        if observation.issuer != self.game
            || observation.project != self.project
            || observation.request_digest != self.request_digest
            || observation.selector != self.selector
            || observation.controller_source != self.controller
        {
            return Err(EpochError::Unsupported);
        }
        for required in &self.required_sources {
            if let Some(found) = observation.sources.iter().find(|s| s.path == required.path) {
                if found != required {
                    return Err(EpochError::Changed);
                }
            } else {
                observation.sources.push(required.clone());
            }
        }
        epoch::qualify_selection(observation, fs, deadline)
    }
    fn frame(
        &self,
        observation: epoch::FrameObservation,
        binding: &epoch::SelectionObservation,
        fs: &RootFs,
        deadline: Deadline,
    ) -> Result<epoch::QualifiedFrame, EpochError> {
        // Semantics are delegated ONLY to this exact authenticated captured provider.
        // Unknown variants/settings never select a caller callback or issue a proof.
        let qualified = epoch::qualify_selection(binding.clone(), fs, deadline)?;
        epoch::qualify_frame(observation, &qualified, fs, deadline)
    }
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Hello {
    version: u32,
    r#type: String,
    nonce: String,
    process: ProcessIdentity,
    parent: ProcessIdentity,
    source_digest: String,
    issuer_digest: String,
    clock_domain: String,
    root: RootIdentity,
    locks: Vec<LockIdentity>,
}
#[derive(Clone, Debug, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct RootIdentity {
    device: u64,
    inode: u64,
}
#[derive(Serialize)]
struct Ready<'a> {
    version: u32,
    r#type: &'static str,
    nonce: &'a str,
    host: &'a ProcessIdentity,
    deadline_ns: u64,
    clock_domain: &'static str,
    work_deadline_ns: u64,
    selection: &'a str,
    record_digest: Option<&'a str>,
    frame: Option<u64>,
    transition_count: u64,
}
/// A captured-provider observed normal return is DATA until the host independently
/// checks source, original intent, actual raw guards and its own live lock identities.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct GuardReturnObservation {
    directory: String,
    invocation: String,
    child: ProcessIdentity,
    monitor: ProcessIdentity,
    controller_source: String,
    issuer_source: String,
    request_digest: String,
    returncode: i32,
    process_digest: String,
    tree_digest: String,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Request {
    version: u32,
    nonce: String,
    selection: String,
    sequence: u64,
    frame: Option<u64>,
    previous_digest: Option<String>,
    operation: Operation,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
enum Operation {
    Observe {
        witnesses: Vec<epoch::Witness>,
        record_offset: Option<u32>,
    },
    PrepareSelection {
        observation: epoch::SelectionObservation,
    },
    Advance {
        observation: epoch::FrameObservation,
    },
    BeginAttempt {
        attempt: epoch::GuardAttempt,
    },
    GuardReturned {
        attempt: String,
        observation: GuardReturnObservation,
    },
    Settle {
        observation: epoch::SettlementObservation,
    },
    Requeue {
        members: Vec<String>,
    },
    Supersede {
        observation: epoch::SelectionObservation,
        initial_frame: Option<epoch::FrameObservation>,
    },
    Finish {
        sources: Vec<epoch::Witness>,
        outputs: Vec<epoch::Witness>,
        topology: String,
    },
    Stop,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Reply {
    version: u32,
    nonce: String,
    selection: String,
    r#type: String,
    sequence: u64,
    record_digest: Option<String>,
    frame: Option<u64>,
    transition_count: u64,
    permission: String,
    record_page: Option<RecordPage>,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct RecordPage {
    offset: u32,
    next: u32,
    total: u32,
    hex: String,
}
/// Require every serde record position to be an object before ORIGINAL-byte decoding.
fn strict_record<T: serde::de::DeserializeOwned>(bytes: &[u8]) -> io::Result<T> {
    let v: serde_json::Value = serde_json::from_slice(bytes).map_err(error)?;
    if !v.is_object() {
        return Err(error("control record must be an object"));
    }
    fn walk(v: &serde_json::Value, key: &str) -> io::Result<()> {
        match v {
            serde_json::Value::Object(m) => {
                for (k, value) in m {
                    walk(value, k)?;
                }
            }
            serde_json::Value::Array(values) => {
                let strings = [
                    "files",
                    "selector",
                    "roots",
                    "members",
                    "args",
                    "platform_roots",
                ];
                if !strings.contains(&key) {
                    for value in values {
                        if !value.is_object() {
                            return Err(error("positional control record"));
                        }
                    }
                }
                for value in values {
                    walk(value, "")?;
                }
            }
            _ => {}
        }
        if [
            "operation",
            "observation",
            "initial_frame",
            "attempt",
            "root",
            "process",
            "parent",
            "game_issuer",
            "fact",
            "anchor",
            "execution",
            "guard",
            "child",
            "monitor",
            "launch",
            "scheduler",
            "python_context",
            "operational_environment",
        ]
        .contains(&key)
            && !v.is_null()
            && !v.is_object()
        {
            return Err(error("positional control record"));
        }
        Ok(())
    }
    walk(&v, "")?;
    serde_json::from_slice(bytes).map_err(error)
}
fn read_message(child: &SchedulerChild, deadline: Deadline) -> io::Result<Vec<u8>> {
    let mut header = [0u8; 4];
    launch::read_exact(child.requests.as_raw_fd(), &mut header, deadline)?;
    let n = u32::from_be_bytes(header) as usize;
    if n == 0 || n > MAX_MESSAGE_BYTES {
        return Err(error("host message size"));
    }
    let mut bytes = vec![0; n];
    launch::read_exact(child.requests.as_raw_fd(), &mut bytes, deadline)?;
    Ok(bytes)
}
fn send_message(
    child: &SchedulerChild,
    value: &impl Serialize,
    deadline: Deadline,
) -> io::Result<()> {
    let bytes = serde_json::to_vec(value).map_err(error)?;
    if bytes.len() > MAX_MESSAGE_BYTES {
        return Err(error("host reply size"));
    }
    launch::write_all(
        child
            .replies
            .as_ref()
            .ok_or_else(|| error("permission channel closed"))?
            .as_raw_fd(),
        &(bytes.len() as u32).to_be_bytes(),
        deadline,
    )?;
    launch::write_all(
        child
            .replies
            .as_ref()
            .ok_or_else(|| error("permission channel closed"))?
            .as_raw_fd(),
        &bytes,
        deadline,
    )
}
/// Exact per-channel state; it is deliberately not serializable or reconnectable.
struct ChannelState {
    next: u64,
    last: Option<(Vec<u8>, Reply)>,
    finished: bool,
}
impl ChannelState {
    fn new() -> Self {
        Self {
            next: 1,
            last: None,
            finished: false,
        }
    }
    fn duplicate(&self, raw: &[u8]) -> Option<Reply> {
        self.last
            .as_ref()
            .filter(|(bytes, _)| bytes == raw)
            .map(|(_, reply)| reply.clone())
    }
    fn remember(&mut self, raw: Vec<u8>, reply: Reply) -> io::Result<Reply> {
        self.next = self
            .next
            .checked_add(1)
            .ok_or_else(|| error("channel sequence overflow"))?;
        self.last = Some((raw, reply.clone()));
        Ok(reply)
    }
}
#[derive(Serialize)]
struct StartupManifest<'a> {
    version: u32,
    nonce: &'a str,
    selection: &'a str,
    checkout: &'a Path,
    output: &'a Path,
    distribution: &'a Path,
    source_digest: &'a str,
    issuer_digest: &'a str,
    issuer_root: &'a Path,
    issuer_profile: &'a str,
    issuer_files: &'a [String],
    host: &'a ProcessIdentity,
    root: &'a RootIdentity,
    locks: &'a [LockIdentity; 3],
    deadline_ns: u64,
    clock_domain: &'static str,
    work_deadline_ns: u64,
    scheduler_request: &'a SchedulerRequest,
    interpreter: &'a Path,
    interpreter_digest: &'a str,
    interpreter_role: &'a Path,
    python_context: &'a PythonContext,
    operational_environment: &'a OperationalEnvironment,
}
fn absolute_context_path(path: &Path) -> io::Result<()> {
    use std::path::Component;
    if !path.is_absolute()
        || path.as_os_str().len() > 4096
        || path.to_str().is_none_or(|s| s.contains('\0'))
        || path
            .components()
            .any(|p| matches!(p, Component::ParentDir | Component::CurDir))
    {
        return Err(error("installed context requires bounded absolute paths"));
    }
    Ok(())
}
impl PythonContext {
    fn validate(&self) -> io::Result<()> {
        if self.platform_roots.is_empty() || self.platform_roots.len() > 32 {
            return Err(error("invalid installed interpreter roots"));
        }
        let mut roots = std::collections::BTreeSet::new();
        for root in &self.platform_roots {
            absolute_context_path(root)?;
            let real = root.canonicalize()?;
            if !real.is_dir() || real.parent().is_none() || !roots.insert(root) {
                return Err(error(
                    "installed platform root is missing, broad or duplicated",
                ));
            }
        }
        // Match C2c: retain the original scheme spelling, but validate the real
        // directory against real approved roots. Missing schemes never disappear.
        let real_roots: Vec<_> = self
            .platform_roots
            .iter()
            .map(|p| p.canonicalize())
            .collect::<io::Result<_>>()?;
        for library in [&self.purelib, &self.platlib] {
            absolute_context_path(library)?;
            let real = library.canonicalize()?;
            if !real.is_dir() || !real_roots.iter().any(|root| real.starts_with(root)) {
                return Err(error(
                    "installed library is absent or outside interpreter roots",
                ));
            }
        }
        Ok(())
    }
}
impl OperationalEnvironment {
    fn validate(&self) -> io::Result<()> {
        if self
            .agent
            .as_ref()
            .is_some_and(|s| s.len() > 128 || s.contains('\0') || s.contains('\n'))
            || self.path.len() > 16384
            || self.path.contains('\0')
        {
            return Err(error("invalid closed operational environment"));
        }
        for path in [&self.cache, &self.build_root].into_iter().flatten() {
            absolute_context_path(path)?;
        }
        let entries: Vec<_> = std::env::split_paths(&self.path).collect();
        if entries.is_empty() || entries.len() > 64 {
            return Err(error("invalid operational PATH"));
        }
        for path in entries {
            absolute_context_path(&path)?;
            if !path.canonicalize()?.is_dir() {
                return Err(error(
                    "operational PATH entry is not an installed directory",
                ));
            }
        }
        Ok(())
    }
    pub(crate) fn apply(&self, command: &mut std::process::Command) -> io::Result<()> {
        self.validate()?;
        command.env_clear().env("PATH", &self.path);
        if let Some(value) = &self.agent {
            command.env("ATELIER_AGENT", value);
        }
        if let Some(value) = &self.cache {
            command.env("ATELIER_CACHE", value);
        }
        if let Some(value) = &self.build_root {
            command.env("ATELIER_BUILD_ROOT", value);
        }
        Ok(())
    }
}
fn validate_interpreter_role(role: &Path, image: &Path) -> io::Result<()> {
    absolute_context_path(role)?;
    if role.canonicalize()? != image || !image.is_file() {
        return Err(error(
            "original interpreter role does not name the pinned image",
        ));
    }
    Ok(())
}
fn validate_config(c: &HostConfig) -> io::Result<Deadline> {
    if c.nonce.is_empty()
        || c.nonce.len() > 128
        || c.selection.is_empty()
        || c.selection.len() > 128
        || c.nonce.len() != 32
        || !c.nonce.bytes().all(|b| b.is_ascii_hexdigit())
        || c.control_directory != format!("build/build-v2/legacy-host/{}", c.nonce)
        || !valid_digest(&c.scheduler_request.digest)
        || c.scheduler_request.size > 2 * 1024 * 1024
        || c.scheduler_request.path != format!("{}/request.json", c.control_directory)
        || !valid_digest(&c.interpreter_digest)
    {
        return Err(error("invalid host invocation identity"));
    }
    relative_path(&c.control_directory, true).map_err(error)?;
    validate_interpreter_role(&c.interpreter_role, &c.interpreter)?;
    c.python_context.validate()?;
    c.operational_environment.validate()?;
    if c.clock_domain != CLOCK_DOMAIN {
        return Err(error("incompatible absolute clock domain"));
    }
    let now = launch::monotonic_ns()?;
    if c.startup_budget_ns > 60_000_000_000
        || c.cleanup_budget_ns > 600_000_000_000
        || c.deadline_ns
            .checked_sub(now)
            .is_none_or(|v| v > 48 * 3600 * 1_000_000_000)
    {
        return Err(error("legacy operational deadline cap exceeded"));
    }

    let budget = c
        .startup_budget_ns
        .checked_add(c.cleanup_budget_ns)
        .filter(|_| c.startup_budget_ns > 0 && c.cleanup_budget_ns > 0)
        .ok_or_else(|| error("missing host startup/cleanup budget"))?;
    if c.deadline_ns
        .checked_sub(now)
        .is_none_or(|remaining| remaining <= budget)
    {
        return Err(error("host deadline cannot cover startup/work/cleanup"));
    }
    let actual = launch::process_identity(std::process::id())?;
    if actual.boot != c.boot {
        return Err(error("host deadline belongs to another boot"));
    }
    for path in [
        &c.checkout,
        &c.distribution,
        &c.interpreter,
        &c.game_issuer.root,
    ] {
        if !path.is_absolute() || path.canonicalize()? != *path {
            return Err(error(
                "host roots/interpreter must be exact canonical paths",
            ));
        }
    }
    let mut python = File::open(&c.interpreter)?;
    let before = FileObservation::from_metadata(&python.metadata()?);
    let mut hasher = Sha256::new();
    let mut chunk = [0u8; 65536];
    loop {
        let n = python.read(&mut chunk)?;
        if n == 0 {
            break;
        }
        hasher.update(&chunk[..n]);
    }
    if format!("{:x}", hasher.finalize()) != c.interpreter_digest
        || before != FileObservation::from_metadata(&python.metadata()?)
    {
        return Err(error("installed interpreter identity changed"));
    }
    launch::deadline_absolute(c.deadline_ns)
}
/// @cc [owner:fontanierh,label:safety] legacy-host-owned-authority
/// The host MUST retain real build/EX/writer guards, authenticate its owned captured child,
/// persist permission before ACK and never infer cleanup from reap, EOF or missing files.
/// Its protocol MUST remain single-channel/nonreconnecting; unknown retains the epoch.
/// No outer capacity reservation, worker guard adoption or group kill is introduced.
fn run(config: HostConfig) -> Result<(), String> {
    run_inner(config).map_err(|e| e.to_string())
}
fn run_inner(config: HostConfig) -> io::Result<()> {
    launch::install_cancellation()?;
    let deadline = validate_config(&config)?;
    let work_deadline = Deadline::new(
        config
            .deadline_ns
            .checked_sub(config.cleanup_budget_ns)
            .ok_or_else(|| error("cleanup budget exceeds overall"))?,
        CLOCK_DOMAIN,
    )?;

    let request_fs = RootFs::open(&config.checkout)?;
    let request_bytes = read_bounded(
        &request_fs,
        &config.scheduler_request.path,
        2 * 1024 * 1024,
        true,
    )?;
    if request_bytes.len() as u64 != config.scheduler_request.size
        || sha256(&request_bytes) != config.scheduler_request.digest
    {
        return Err(error("original scheduler request changed"));
    }
    let original: OrdinaryRequest = strict_record(&request_bytes)?;
    if original.version != 2
        || original.game != config.game_issuer.project
        || original.wanted.len() > 64
        || original
            .wanted
            .iter()
            .any(|name| name.is_empty() || name.len() > 256 || name.contains('\0'))
        || original.options.max_heavy_commands == Some(0)
    {
        return Err(error(
            "unsupported original scheduler project/selection/options",
        ));
    }
    // Full option/profile semantics are checked by the exact captured Python provider;
    // these are request values, never semantic qualification flags.
    crate::py_data::validate_py_data_payload("JsonData", "scheduler-request.json", &request_bytes)
        .map_err(error)?;
    let issuer = FrozenIssuer::verify(&config, &original)?;
    deadline.remaining()?;
    let locks = CheckoutLocks::open(&config.checkout).map_err(error)?;
    let build = locks.try_build_exclusive().map_err(error)?;
    let write = build.try_legacy_write_content().map_err(error)?;
    let fs = RootFs::open(&config.checkout)?;
    if fs.occupied("build/build-v2/install/journal.json")? {
        return Err(error("install journal blocks legacy authority"));
    }
    let existing = epoch::Selection::inspect(&build, &write).map_err(error)?;
    let selection_id = existing
        .as_ref()
        .map_or(config.selection.as_str(), |old| old.selection.as_str());
    launch::prepare_default_output(&build, &write, &config.output, &config.game_issuer.project)?;
    let custody = TripleCustody::acquire(&build, &write, &config.output)?;
    fs.mkdirs(&config.control_directory, 0o700)?;
    let host = launch::process_identity(std::process::id())?;
    let metadata = fs.root_metadata()?;
    use std::os::unix::fs::MetadataExt;
    let root = RootIdentity {
        device: metadata.dev(),
        inode: metadata.ino(),
    };
    let manifest = StartupManifest {
        version: VERSION,
        nonce: &config.nonce,
        selection: selection_id,
        checkout: &config.checkout,
        output: &config.output,
        distribution: &config.distribution,
        source_digest: &issuer.controller,
        issuer_digest: &issuer.game,
        issuer_root: &config.game_issuer.root,
        issuer_profile: &issuer.profile,
        issuer_files: &config.game_issuer.files,
        host: &host,
        root: &root,
        locks: custody.identities(),
        deadline_ns: config.deadline_ns,
        scheduler_request: &config.scheduler_request,
        clock_domain: CLOCK_DOMAIN,
        work_deadline_ns: config.deadline_ns - config.cleanup_budget_ns,
        interpreter: &config.interpreter,
        interpreter_digest: &config.interpreter_digest,
        interpreter_role: &config.interpreter_role,
        python_context: &config.python_context,
        operational_environment: &config.operational_environment,
    };
    let manifest_path = format!("{}/startup.json", config.control_directory);
    fs.publish_metadata(
        &manifest_path,
        &serde_json::to_vec(&manifest).map_err(error)?,
    )?;
    let bootstrap = config.distribution.join(BOOTSTRAP);
    validate_interpreter_role(&config.interpreter_role, &config.interpreter)?;
    config.python_context.validate()?;
    let mut child = SchedulerChild::spawn(
        &config.interpreter_role,
        &bootstrap,
        &fs.absolute(&manifest_path),
        &config.checkout,
        &fs.absolute(&format!("{}/scheduler.log", config.control_directory)),
        custody,
        deadline,
        &config.operational_environment,
    )?;
    let result = (|| {
        let startup = work_deadline.cap(config.startup_budget_ns)?;
        let hello: Hello = strict_record(&read_message(&child, startup)?)?;
        if hello.version != VERSION
            || hello.r#type != "hello"
            || hello.nonce != config.nonce
            || hello.process != *child.identity()
            || hello.parent != host
            || hello.source_digest != issuer.controller
            || hello.issuer_digest != issuer.game
            || hello.clock_domain != CLOCK_DOMAIN
            || hello.root != root
            || hello.locks != child.locks().to_vec()
            || launch::process_identity(child.identity().pid)? != *child.identity()
        {
            return Err(error(
                "legacy child startup identity/source/custody mismatch",
            ));
        }
        send_message(
            &child,
            &Ready {
                version: VERSION,
                r#type: "ready",
                nonce: &config.nonce,
                host: &host,
                deadline_ns: config.deadline_ns,
                clock_domain: CLOCK_DOMAIN,
                work_deadline_ns: config.deadline_ns - config.cleanup_budget_ns,
                selection: selection_id,
                record_digest: existing.as_ref().map(|old| old.digest.as_str()),
                frame: existing.as_ref().and_then(|old| old.frame),
                transition_count: existing.as_ref().map_or(0, |old| old.count),
            },
            startup,
        )?;
        let mut selection: Option<epoch::Selection<'_>> = None;
        let mut channel = ChannelState::new();
        loop {
            let raw = read_message(&child, work_deadline)?;
            if let Some(reply) = channel.duplicate(&raw) {
                send_message(&child, &reply, work_deadline)?;
                continue;
            }
            let request: Request = strict_record(&raw)?;
            if channel.finished
                || request.version != VERSION
                || request.nonce != config.nonce
                || request.selection != selection_id
                || request.sequence != channel.next
            {
                return Err(error("stale/foreign legacy request"));
            }
            child.verify_custody()?;
            let current = if let Some(s) = selection.as_ref() {
                Some(s.digest().map_err(error)?)
            } else {
                existing.as_ref().map(|old| old.digest.clone())
            };
            if request.previous_digest != current
                || request.frame
                    != selection.as_ref().and_then(|s| s.frame()).or_else(|| {
                        if selection.is_none() {
                            existing.as_ref().and_then(|old| old.frame)
                        } else {
                            None
                        }
                    })
            {
                return Err(error("legacy record/frame correlation mismatch"));
            }
            let mut record_page = None;
            let permission = match request.operation {
                Operation::Observe {
                    witnesses,
                    record_offset,
                } => {
                    if let Some(offset) = record_offset {
                        let current = epoch::Selection::inspect(&build, &write)
                            .map_err(error)?
                            .ok_or_else(|| error("no prior selection record"))?;
                        if Some(&current.digest) != request.previous_digest.as_ref() {
                            return Err(error("record changed during paged observation"));
                        }
                        let offset = offset as usize;
                        if offset > current.bytes.len() {
                            return Err(error("record offset outside bound"));
                        }
                        let next = (offset + 16384).min(current.bytes.len());
                        let hex = current.bytes[offset..next]
                            .iter()
                            .map(|b| format!("{b:02x}"))
                            .collect::<String>();
                        record_page = Some(RecordPage {
                            offset: offset as u32,
                            next: next as u32,
                            total: current.bytes.len() as u32,
                            hex,
                        });
                    }
                    epoch::check_witnesses(&fs, &witnesses, work_deadline).map_err(error)?;
                    "observed"
                }
                Operation::PrepareSelection { observation } => {
                    if selection.is_some() {
                        return Err(error("selection already prepared"));
                    }
                    let qualified = issuer
                        .selection(observation.clone(), &fs, work_deadline)
                        .map_err(error)?;
                    selection = Some(if fs.occupied(crate::checkout_locks::LEGACY_EPOCH)? {
                        epoch::Selection::resume(&build, &write, &qualified, work_deadline)
                            .map_err(error)?
                    } else {
                        epoch::Selection::prepare(
                            &build,
                            &write,
                            qualified,
                            selection_id,
                            work_deadline,
                            |_| Ok(()),
                        )
                        .map_err(error)?
                    });
                    "prepared"
                }
                Operation::Advance { observation } => {
                    let s = selection
                        .as_mut()
                        .ok_or_else(|| error("selection not prepared"))?;
                    let frame = issuer
                        .frame(observation, s.binding(), &fs, work_deadline)
                        .map_err(error)?;
                    s.advance(frame, |_| Ok(())).map_err(error)?;
                    "frame"
                }
                Operation::BeginAttempt { attempt } => {
                    if let epoch::AttemptKind::Guarded {
                        directory, launch, ..
                    } = &attempt.execution
                    {
                        let prefix = format!("{}/guards/", config.control_directory);
                        if !directory.starts_with(&prefix)
                            || launch.scheduler != *child.identity()
                            || launch
                                .queue_deadline_ns
                                .checked_add(launch.execution_ns)
                                .is_none_or(|ns| ns > config.deadline_ns - config.cleanup_budget_ns)
                        {
                            return Err(error(
                                "launch intent is not this scheduler/private guard scope/work_deadline",
                            ));
                        }
                    }
                    selection
                        .as_mut()
                        .ok_or_else(|| error("selection not prepared"))?
                        .begin_attempt(attempt, |_| Ok(()))
                        .map_err(error)?;
                    "mutation"
                }
                Operation::GuardReturned {
                    attempt,
                    observation,
                } => {
                    if observation.controller_source != issuer.controller
                        || observation.issuer_source != issuer.game
                        || observation.request_digest != issuer.request_digest
                        || observation.child.boot != host.boot
                        || observation.monitor.boot != host.boot
                    {
                        return Err(error(
                            "guard return provenance/source/scheduler/custody mismatch",
                        ));
                    }
                    let observation = epoch::GuardBinding {
                        directory: observation.directory,
                        invocation: observation.invocation,
                        child: observation.child,
                        monitor: observation.monitor,
                        controller: child.identity().clone(),
                        locks: child.locks().to_vec(),
                        controller_source: observation.controller_source,
                        issuer_source: observation.issuer_source,
                        request_digest: observation.request_digest,
                        returncode: observation.returncode,
                        process_digest: observation.process_digest,
                        tree_digest: observation.tree_digest,
                    };
                    launch::verify_raw_guard(&fs, &observation, child.locks(), child.identity())
                        .map_err(error)?;
                    selection
                        .as_mut()
                        .ok_or_else(|| error("selection not prepared"))?
                        .bind_guard(&attempt, observation, |_| Ok(()))
                        .map_err(error)?;
                    "guard_observed"
                }
                Operation::Settle { observation } => {
                    selection
                        .as_mut()
                        .ok_or_else(|| error("selection not prepared"))?
                        .settle(observation, |_| Ok(()))
                        .map_err(error)?;
                    "settled"
                }
                Operation::Requeue { members } => {
                    selection
                        .as_mut()
                        .ok_or_else(|| error("selection not prepared"))?
                        .requeue(&members, |_| Ok(()))
                        .map_err(error)?;
                    "requeued"
                }
                Operation::Supersede {
                    observation,
                    initial_frame,
                } => {
                    if selection.is_some() {
                        return Err(error("Supersede is a fresh-host repair entry only"));
                    }
                    let qualified = issuer
                        .selection(observation.clone(), &fs, work_deadline)
                        .map_err(error)?;
                    let initial = initial_frame
                        .map(|frame| issuer.frame(frame, &observation, &fs, work_deadline))
                        .transpose()
                        .map_err(error)?;
                    selection = Some(
                        epoch::Selection::supersede(
                            &build,
                            &write,
                            qualified,
                            initial,
                            work_deadline,
                            |_| Ok(()),
                        )
                        .map_err(error)?,
                    );
                    "superseded"
                }
                Operation::Finish {
                    sources,
                    outputs,
                    topology,
                } => {
                    selection
                        .as_mut()
                        .ok_or_else(|| error("selection not prepared"))?
                        .finish(&sources, &outputs, &topology, |_| Ok(()))
                        .map_err(error)?;
                    channel.finished = true;
                    "finished"
                }
                Operation::Stop => {
                    return Err(error("legacy scheduler stopped without finalization"));
                }
            };
            let reply = Reply {
                version: VERSION,
                nonce: config.nonce.clone(),
                selection: selection_id.into(),
                r#type: "ack".into(),
                sequence: request.sequence,
                record_digest: if let Some(s) = selection.as_ref() {
                    Some(s.digest().map_err(error)?)
                } else {
                    existing.as_ref().map(|old| old.digest.clone())
                },
                frame: selection.as_ref().and_then(|s| s.frame()).or_else(|| {
                    if selection.is_none() {
                        existing.as_ref().and_then(|old| old.frame)
                    } else {
                        None
                    }
                }),
                transition_count: selection.as_ref().map_or_else(
                    || existing.as_ref().map_or(0, |old| old.count),
                    |s| s.count(),
                ),
                permission: permission.into(),
                record_page,
            };
            let reply = channel.remember(raw, reply)?;
            send_message(&child, &reply, work_deadline)?;
            if channel.finished {
                break;
            }
        }
        Ok(())
    })();
    // A partial transport frame cannot be repaired by another Refused frame.
    // Closing permission immediately preserves the entire reserved drain interval.
    let shutdown = child.begin_drain(config.cleanup_budget_ns);
    while !shutdown.expired() {
        if let Some(status) = child.wait()? {
            return if result.is_ok() && status.success() {
                Ok(())
            } else {
                Err(result
                    .err()
                    .unwrap_or_else(|| error("legacy scheduler failed after finalization")))
            };
        }
        let mut p = libc::pollfd {
            fd: child.requests.as_raw_fd(),
            events: 0,
            revents: 0,
        };
        unsafe { libc::poll(&mut p, 1, 10) };
    }
    child.stop_owned()?;
    // No reap/kill or deadline fabricates descendant cleanup; any unfinished epoch remains.
    Err(result
        .err()
        .unwrap_or_else(|| error("legacy child shutdown unconfirmed")))
}
/// Private inherited config only; no path fallback or arbitrary proof constructor.
pub fn run_config(mut inherited: File) -> Result<(), String> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() != 2
        || args[0] != "--legacy-config-fd"
        || args[1].to_string_lossy().parse::<i32>().ok() != Some(inherited.as_raw_fd())
    {
        return Err("legacy host requires its exact standalone binary entry".into());
    }

    let metadata = inherited.metadata().map_err(|e| e.to_string())?;
    use std::os::unix::fs::MetadataExt;
    if metadata.uid() != unsafe { libc::geteuid() } || metadata.mode() & 0o077 != 0 {
        return Err("legacy config must be private and owned".into());
    }
    if !metadata.is_file() || metadata.len() > 2 * 1024 * 1024 {
        return Err("legacy config must be a bounded private regular file".into());
    }
    let mut bytes = vec![];
    inherited
        .by_ref()
        .take((2 * 1024 * 1024 + 1) as u64)
        .read_to_end(&mut bytes)
        .map_err(|e| e.to_string())?;
    if bytes.len() > 2 * 1024 * 1024 {
        return Err("legacy startup config exceeds bound".into());
    }
    let config: HostConfig = strict_record(&bytes).map_err(|e| e.to_string())?;
    run(config)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn installed_context_fixture(label: &str) -> PathBuf {
        static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
        let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "atelier-host-startup-{}-{}-{}",
            label,
            std::process::id(),
            NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
        ));
        std::fs::create_dir(&root).unwrap();
        root
    }
    #[test]
    fn startup_manifest_relays_exact_host_verified_issuer_roster_without_discovery() {
        let files = vec![
            "games/fixture/build.py".into(),
            "games/fixture/legacy_qualification.py".into(),
        ];
        let identity = ProcessIdentity {
            pid: 1,
            boot: "fixture-boot".into(),
            started: "fixture-start".into(),
        };
        let root = RootIdentity {
            device: 1,
            inode: 2,
        };
        let locks = [
            LockIdentity {
                role: "build".into(),
                device: 1,
                inode: 3,
            },
            LockIdentity {
                role: "content".into(),
                device: 1,
                inode: 4,
            },
            LockIdentity {
                role: "writer".into(),
                device: 1,
                inode: 5,
            },
        ];
        let request = SchedulerRequest {
            path: "request.json".into(),
            digest: sha256(b"request"),
            size: 7,
        };
        let context = PythonContext {
            platform_roots: vec!["/installed".into()],
            purelib: "/installed/site".into(),
            platlib: "/installed/site".into(),
        };
        let environment = OperationalEnvironment {
            agent: None,
            cache: None,
            build_root: None,
            path: "/usr/bin".into(),
        };
        let manifest = StartupManifest {
            version: VERSION,
            nonce: "fixture-nonce",
            selection: "fixture-selection",
            checkout: Path::new("/checkout"),
            output: Path::new("/checkout/build/fixture"),
            distribution: Path::new("/frozen"),
            source_digest: "controller",
            issuer_digest: "issuer",
            issuer_root: Path::new("/issuer"),
            issuer_profile: "games/fixture/legacy_qualification.py",
            issuer_files: &files,
            host: &identity,
            root: &root,
            locks: &locks,
            deadline_ns: 3,
            clock_domain: CLOCK_DOMAIN,
            work_deadline_ns: 2,
            scheduler_request: &request,
            interpreter: Path::new("/image/python"),
            interpreter_digest: "image",
            interpreter_role: Path::new("/role/python"),
            python_context: &context,
            operational_environment: &environment,
        };
        let encoded = serde_json::to_value(&manifest).unwrap();
        assert_eq!(
            encoded["issuer_files"],
            serde_json::to_value(&files).unwrap()
        );
        assert_eq!(encoded["issuer_profile"], files[1]);
        assert_eq!(manifest.issuer_files.as_ptr(), files.as_ptr());
    }
    #[test]
    fn original_interpreter_role_is_preserved_and_retargeted_image_refuses() {
        let root = installed_context_fixture("role");
        let image = root.join("installed-python");
        let other = root.join("other-python");
        std::fs::write(&image, b"installed identity").unwrap();
        std::fs::write(&other, b"different identity").unwrap();
        let bin = root.join("venv/bin");
        std::fs::create_dir_all(&bin).unwrap();
        let role = bin.join("python");
        std::os::unix::fs::symlink(&image, &role).unwrap();
        validate_interpreter_role(&role, &image).unwrap();
        let environment = OperationalEnvironment {
            agent: None,
            cache: None,
            build_root: None,
            path: bin.to_str().unwrap().into(),
        };
        let command =
            launch::isolated_command(&role, &root.join("frozen-bootstrap.py"), &environment)
                .unwrap();
        assert_eq!(command.get_program(), role.as_os_str());
        let args: Vec<_> = command.get_args().collect();
        assert_eq!(
            args,
            [
                std::ffi::OsStr::new("-I"),
                std::ffi::OsStr::new("-S"),
                root.join("frozen-bootstrap.py").as_os_str()
            ]
        );
        std::fs::remove_file(&role).unwrap();
        std::os::unix::fs::symlink(&other, &role).unwrap();
        assert!(validate_interpreter_role(&role, &image).is_err());
        assert!(validate_interpreter_role(Path::new("relative/python"), &image).is_err());
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn installed_scheme_folders_keep_lexical_roles_but_require_real_vetted_containment() {
        let root = installed_context_fixture("libraries");
        let platform = root.join("venv");
        let site = platform.join("lib/python3/site-packages");
        std::fs::create_dir_all(&site).unwrap();
        let alias = root.join("venv-role");
        std::os::unix::fs::symlink(&platform, &alias).unwrap();
        let lexical = alias.join("lib/python3/site-packages");
        let mut context = PythonContext {
            platform_roots: vec![platform],
            purelib: lexical.clone(),
            platlib: lexical.clone(),
        };
        context.validate().unwrap();
        let encoded = serde_json::to_value(&context).unwrap();
        assert_eq!(encoded["purelib"], lexical.to_str().unwrap());
        assert_eq!(encoded["platlib"], lexical.to_str().unwrap());
        context.platlib = root.join("missing");
        assert!(context.validate().is_err());
        std::fs::create_dir(root.join("outside")).unwrap();
        context.platlib = root.join("outside");
        assert!(context.validate().is_err());
        context.platlib = lexical;
        context.platform_roots = vec![PathBuf::from("/")];
        assert!(context.validate().is_err());
        for bad in [
            br#"{"platform_roots":[],"purelib":"/a","platlib":"/a","site":true}"#.as_slice(),
            br#"{"platform_roots":[],"purelib":"/a","platlib":"/a","purelib":"/b"}"#.as_slice(),
            br#"[[],"/a","/a"]"#.as_slice(),
        ] {
            assert!(strict_record::<PythonContext>(bad).is_err());
        }
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn closed_operational_environment_sets_only_vetted_values_without_inheritance() {
        let root = installed_context_fixture("environment");
        let environment = OperationalEnvironment {
            agent: Some("hosted-issuer".into()),
            cache: Some(root.join("cache")),
            build_root: Some(root.join("build")),
            path: root.to_str().unwrap().into(),
        };
        let mut command = std::process::Command::new("unused-no-spawn");
        command
            .env("PYTHONPATH", "/untrusted")
            .env("DYLD_INSERT_LIBRARIES", "/untrusted");
        environment.apply(&mut command).unwrap();
        let values: BTreeMap<_, _> = command
            .get_envs()
            .map(|(k, v)| (k.to_str().unwrap(), v.unwrap().to_str().unwrap()))
            .collect();
        assert_eq!(values.len(), 4);
        assert_eq!(values["ATELIER_AGENT"], "hosted-issuer");
        assert_eq!(
            values["ATELIER_CACHE"],
            root.join("cache").to_str().unwrap()
        );
        assert_eq!(
            values["ATELIER_BUILD_ROOT"],
            root.join("build").to_str().unwrap()
        );
        assert_eq!(values["PATH"], root.to_str().unwrap());
        let absent = OperationalEnvironment {
            agent: None,
            cache: None,
            build_root: None,
            path: environment.path.clone(),
        };
        absent.apply(&mut command).unwrap();
        assert_eq!(command.get_envs().count(), 1);
        for bad in ["", ":/usr/bin", "relative", "/usr/bin:"] {
            let value = OperationalEnvironment {
                path: bad.into(),
                ..absent.clone()
            };
            assert!(value.validate().is_err());
        }
        assert!(strict_record::<OperationalEnvironment>(br#"{"agent":null,"cache":null,"build_root":null,"path":"/usr/bin","PYTHONPATH":"/bad"}"#).is_err());
        // Nested positional records cannot exploit serde's tuple-compatible struct decoder.
        assert!(
            strict_record::<serde_json::Value>(br#"{"python_context":[[],"/a","/a"]}"#).is_err()
        );
        assert!(
            strict_record::<serde_json::Value>(
                br#"{"operational_environment":[null,null,null,"/usr/bin"]}"#
            )
            .is_err()
        );
        assert!(
            strict_record::<OperationalEnvironment>(
                br#"{"cache":null,"build_root":null,"path":"/usr/bin"}"#
            )
            .is_err()
        );
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn closed_host_codec_refuses_duplicate_unknown_positional_and_unbound_launch_records() {
        let good=br#"{"version":2,"nonce":"nonce","selection":"selection","sequence":1,"frame":null,"previous_digest":null,"operation":{"type":"observe","witnesses":[],"record_offset":null}}"#;
        assert!(strict_record::<Request>(good).is_ok());
        for bad in [
            String::from_utf8(good.to_vec())
                .unwrap()
                .replace("\"version\":2", "\"version\":2,\"version\":2"),
            String::from_utf8(good.to_vec())
                .unwrap()
                .replace("\"sequence\":1", "\"sequence\":1,\"grant\":true"),
            String::from_utf8(good.to_vec()).unwrap().replace(
                "\"witnesses\":[]",
                "\"witnesses\":[[\"source\",{\"kind\":\"absent\"}]]",
            ),
            "[2,\"nonce\",\"selection\",1,null,null,{}]".into(),
        ] {
            assert!(strict_record::<Request>(bad.as_bytes()).is_err(), "{bad}");
        }
    }
    #[test]
    fn live_exact_duplicate_reuses_one_ack_without_reexecuting_or_cross_host_resumption() {
        let mut channel = ChannelState::new();
        let mut executions = 0;
        let reply = Reply {
            version: 2,
            nonce: "nonce".into(),
            selection: "selection".into(),
            r#type: "ack".into(),
            sequence: 1,
            record_digest: Some(sha256(b"persisted intent")),
            frame: Some(1),
            transition_count: 3,
            permission: "mutation".into(),
            record_page: None,
        };
        executions += 1;
        channel
            .remember(b"exact request".to_vec(), reply.clone())
            .unwrap();
        assert_eq!(
            channel.duplicate(b"exact request").unwrap().record_digest,
            reply.record_digest
        );
        assert_eq!(channel.next, 2);
        assert_eq!(executions, 1);
        assert!(channel.duplicate(b"changed request").is_none());
        assert!(ChannelState::new().duplicate(b"exact request").is_none());
    }
    #[test]
    fn capture_digest_checks_actual_readonly_named_bytes_and_changes_with_helper_bytes() {
        use std::os::unix::fs::PermissionsExt;
        use std::sync::atomic::{AtomicU64, Ordering};
        static NEXT: AtomicU64 = AtomicU64::new(0);
        let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "atelier-host-capture-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        std::fs::create_dir(&root).unwrap();
        std::fs::write(root.join("provider.py"), b"# captured first\n").unwrap();
        let fs = RootFs::open(&root).unwrap();
        let names = vec!["provider.py".to_string()];
        assert!(capture_digest(&fs, &names, None).is_err());
        std::fs::set_permissions(
            root.join("provider.py"),
            std::fs::Permissions::from_mode(0o400),
        )
        .unwrap();
        let first = capture_digest(&fs, &names, None).unwrap();
        std::fs::set_permissions(
            root.join("provider.py"),
            std::fs::Permissions::from_mode(0o600),
        )
        .unwrap();
        std::fs::write(root.join("provider.py"), b"# captured changed\n").unwrap();
        std::fs::set_permissions(
            root.join("provider.py"),
            std::fs::Permissions::from_mode(0o400),
        )
        .unwrap();
        assert_ne!(first, capture_digest(&fs, &names, None).unwrap());
        assert!(capture_digest(&fs, &["provider.py".into(), "provider.py".into()], None).is_err());
        std::os::unix::fs::symlink("provider.py", root.join("alias.py")).unwrap();
        assert!(capture_digest(&fs, &["alias.py".into()], None).is_err());
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn game_issuer_private_capsule_cannot_substitute_different_original_profile_bytes() {
        use std::os::unix::fs::PermissionsExt;
        let base = std::env::temp_dir()
            .canonicalize()
            .unwrap()
            .join(format!("atelier-host-original-{}", std::process::id()));
        std::fs::create_dir(&base).unwrap();
        let live = base.join("live");
        let captured = base.join("captured");
        for root in [&live, &captured] {
            std::fs::create_dir_all(root.join("games/fixture")).unwrap();
        }
        let name = "games/fixture/legacy_qualification.py";
        std::fs::write(
            live.join(name),
            b"# actual original provider
",
        )
        .unwrap();
        std::fs::write(
            captured.join(name),
            b"# different private provider
",
        )
        .unwrap();
        std::fs::set_permissions(captured.join(name), std::fs::Permissions::from_mode(0o400))
            .unwrap();
        let game = GameIssuer {
            project: "fixture".into(),
            root: captured.clone(),
            files: vec![name.into()],
            digest: sha256(b"capsule is not proof"),
            profile: name.into(),
        };
        assert!(verify_game_sources(&game, &live).is_err());
        std::fs::set_permissions(captured.join(name), std::fs::Permissions::from_mode(0o600))
            .unwrap();
        std::fs::write(captured.join(name), std::fs::read(live.join(name)).unwrap()).unwrap();
        std::fs::set_permissions(captured.join(name), std::fs::Permissions::from_mode(0o400))
            .unwrap();
        let sources = verify_game_sources(&game, &live).unwrap();
        assert_eq!(sources.len(), 1);
        assert_eq!(sources[0].path, name);
        std::fs::write(
            live.join(name),
            b"# live edit
",
        )
        .unwrap();
        assert!(
            epoch::check_witnesses(
                &RootFs::open(&live).unwrap(),
                &sources,
                Deadline::after(std::time::Duration::from_secs(1))
            )
            .is_err()
        );
        std::fs::remove_dir_all(base).unwrap();
    }
}
