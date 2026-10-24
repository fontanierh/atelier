//! Versioned continuous operational selection fence; never cache/output authority.
use super::{
    EpochError, INSTALL_JOURNAL, MAX_BYTES, RootIdentity, label, object, root_identity, safe_path,
};
use crate::checkout_locks::{BuildGuard, ContentWriteGuard, LEGACY_EPOCH};
use crate::install_fs::{FileObservation, RootFs};
use crate::leases::ProcessIdentity;
use crate::legacy_host_launch::Deadline;
use crate::paths::{Claims, claim};
use crate::source_hashes::{sha256, valid_digest};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::io::{self, Read};

pub(crate) const MAX_TRANSITIONS: u64 = 65_536;
pub(crate) const MAX_WITNESSES: usize = 1024;

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub(crate) enum Fact {
    Absent,
    File {
        digest: String,
        size: u64,
        mode: u32,
    },
    Directory {
        device: u64,
        inode: u64,
    },
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Witness {
    pub path: String,
    pub fact: Fact,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Anchor {
    pub path: String,
    pub device: u64,
    pub inode: u64,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct WriteClaim {
    pub path: String,
    pub canonical: String,
    pub anchor: Anchor,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum Profile {
    DiscoveryControl,
    ControlPreparation,
    ControlRecovery,
    DataStageCopies,
    VerifiedActionRestore,
    RegionDiscovery,
    NamedAssembly,
    NativeBatch,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum Replay {
    ClosedReplay,
    VerifiedRestore,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct TaskScope {
    pub id: String,
    pub replay: Replay,
    pub writes: Vec<WriteClaim>,
}
/// Untrusted observations. Only the bound host issuer can qualify them.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct SelectionObservation {
    pub project: String,
    pub selector: Vec<String>,
    pub source_plan: String,
    pub request_digest: String,
    pub issuer: String,
    pub controller_source: String,
    pub roots: Vec<String>,
    pub sources: Vec<Witness>,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct FrameObservation {
    pub profile: Profile,
    pub topology: String,
    pub tasks: Vec<TaskScope>,
    pub inputs: Vec<Witness>,
}
/// Private qualification: the host's fixed frozen semantic provider plus independent named checks.
pub(crate) struct QualifiedSelection(SelectionObservation);
pub(crate) struct QualifiedFrame(FrameObservation);

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct GuardBinding {
    pub invocation: String,
    pub directory: String,
    pub child: ProcessIdentity,
    pub monitor: ProcessIdentity,
    pub controller: ProcessIdentity,
    pub locks: Vec<crate::legacy_host_launch::LockIdentity>,
    pub controller_source: String,
    pub issuer_source: String,
    pub request_digest: String,
    pub returncode: i32,
    pub process_digest: String,
    pub tree_digest: String,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub(crate) enum AttemptKind {
    InProcess,
    Guarded {
        directory: String,
        invocation: String,
        launch: LaunchDescription,
    },
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct LaunchDescription {
    pub scheduler: ProcessIdentity,
    pub program: String,
    pub args: Vec<String>,
    pub environment_digest: String,
    pub kind: String,
    pub threads: u32,
    pub memory_bytes: u64,
    pub execution_ns: u64,
    pub queue_deadline_ns: u64,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct GuardAttempt {
    pub id: String,
    pub members: Vec<String>,
    pub execution: AttemptKind,
    pub guard: Option<GuardBinding>,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct SettlementObservation {
    pub task: String,
    pub attempt: String,
    pub inputs: String,
    pub outputs: Vec<Witness>,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Frame {
    number: u64,
    scope: FrameObservation,
    pending: Vec<String>,
    settled: Vec<SettlementObservation>,
    attempts: Vec<GuardAttempt>,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Record {
    version: u32,
    selection: String,
    root: RootIdentity,
    binding: SelectionObservation,
    transition_count: u64,
    permissions_issued: u64,
    frame: Option<Frame>,
    /// Dirty claims carried by Supersede cannot disappear on a later frame advance.
    dirty: Vec<WriteClaim>,
    verified_complete: bool,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Cut {
    Prepared,
    Intent,
    GuardBound,
    Settled,
    Requeued,
    Advanced,
    Superseded,
    Complete,
    Removed,
}
fn invalid<T>() -> Result<T, EpochError> {
    Err(EpochError::Invalid)
}
fn unique(values: &[String]) -> bool {
    values.iter().all(|v| label(v)) && values.iter().collect::<BTreeSet<_>>().len() == values.len()
}
fn witness_shape(witnesses: &[Witness], required: bool) -> Result<(), EpochError> {
    if witnesses.len() > MAX_WITNESSES || (required && witnesses.is_empty()) {
        return invalid();
    }
    let mut names = BTreeSet::new();
    for witness in witnesses {
        safe_path(&witness.path)?;
        if !names.insert(&witness.path) {
            return invalid();
        }
        if let Fact::File { digest, mode, .. } = &witness.fact {
            if !valid_digest(digest) || *mode > 0o777 {
                return invalid();
            }
        }
    }
    Ok(())
}
fn binding_shape(binding: &SelectionObservation) -> Result<(), EpochError> {
    if !label(&binding.project)
        || binding.selector.len() > 64
        || !unique(&binding.selector)
        || !valid_digest(&binding.source_plan)
        || !valid_digest(&binding.request_digest)
        || !valid_digest(&binding.issuer)
        || !valid_digest(&binding.controller_source)
        || binding.roots.is_empty()
        || binding.roots.len() > 16
    {
        return invalid();
    }
    let mut roots = Claims::new();
    for root in &binding.roots {
        safe_path(root)?;
        claim(&mut roots, root, "selection root").map_err(|_| EpochError::Invalid)?;
    }
    witness_shape(&binding.sources, true)
}
fn claim_shape(item: &WriteClaim, binding: &SelectionObservation) -> Result<(), EpochError> {
    safe_path(&item.path)?;
    safe_path(&item.canonical)?;
    if item.path != item.canonical
        || !binding
            .roots
            .iter()
            .any(|r| item.path.starts_with(&(r.clone() + "/")))
    {
        return invalid();
    }
    if !item.anchor.path.is_empty() {
        safe_path(&item.anchor.path)?;
    }
    if !item.anchor.path.is_empty() && !item.path.starts_with(&(item.anchor.path.clone() + "/")) {
        return invalid();
    }
    // An anchor inside an owned claim cannot establish unchanged ownership after replay.
    if item.anchor.path == item.path {
        return invalid();
    }
    Ok(())
}
fn frame_shape(scope: &FrameObservation, binding: &SelectionObservation) -> Result<(), EpochError> {
    if !valid_digest(&scope.topology) || scope.tasks.is_empty() || scope.tasks.len() > 64 {
        return invalid();
    }
    let mut ids = BTreeSet::new();
    let mut writes = Claims::new();
    claim(
        &mut writes,
        "build/build-v2",
        "protected epoch/install authority",
    )
    .map_err(|_| EpochError::Invalid)?;
    for task in &scope.tasks {
        if !label(&task.id)
            || !ids.insert(&task.id)
            || task.writes.is_empty()
            || task.writes.len() > 128
        {
            return invalid();
        }
        for item in &task.writes {
            claim_shape(item, binding)?;
            claim(&mut writes, &item.path, &task.id).map_err(|_| EpochError::Invalid)?;
        }
    }
    witness_shape(&scope.inputs, false)
}
fn check_anchor(fs: &RootFs, item: &WriteClaim) -> Result<(), EpochError> {
    let metadata = if item.anchor.path.is_empty() {
        let m = fs.root_metadata()?;
        (m.dev(), m.ino())
    } else {
        let m = fs
            .directory_identity(&item.anchor.path)?
            .ok_or(EpochError::Changed)?;
        (m.device, m.inode)
    };
    if metadata != (item.anchor.device, item.anchor.inode) {
        return Err(EpochError::Changed);
    }
    // Traverse every existing component without following links, even for a future leaf.
    let mut prefix = String::new();
    let parts: Vec<_> = item.path.split('/').collect();
    for component in &parts[..parts.len() - 1] {
        if !prefix.is_empty() {
            prefix.push('/');
        }
        prefix.push_str(component);
        match fs.directory_identity(&prefix) {
            Ok(Some(_)) => {}
            Ok(None) => break,
            Err(e) if e.kind() == io::ErrorKind::NotFound => break,
            Err(e) => return Err(e.into()),
        }
    }
    Ok(())
}
use std::os::unix::fs::MetadataExt;
pub(crate) fn check_witnesses(
    fs: &RootFs,
    values: &[Witness],
    deadline: Deadline,
) -> Result<(), EpochError> {
    witness_shape(values, false)?;
    for value in values {
        if deadline.expired() {
            return Err(EpochError::Changed);
        }
        match &value.fact {
            Fact::Absent => match fs.occupied(&value.path) {
                Ok(false) => {}
                Err(e) if e.kind() == io::ErrorKind::NotFound => {}
                Ok(true) => return Err(EpochError::Changed),
                Err(e) => return Err(e.into()),
            },
            Fact::Directory { device, inode } => {
                let d = fs
                    .directory_identity(&value.path)?
                    .ok_or(EpochError::Changed)?;
                if (d.device, d.inode) != (*device, *inode) {
                    return Err(EpochError::Changed);
                }
            }
            Fact::File { digest, size, mode } => {
                let mut file = fs.file(&value.path)?;
                let before = FileObservation::from_metadata(&file.metadata()?);
                if before.size != *size || before.mode != *mode {
                    return Err(EpochError::Changed);
                }
                let mut hasher = Sha256::new();
                let mut buffer = [0u8; 65536];
                let mut total = 0u64;
                loop {
                    if deadline.expired() {
                        return Err(EpochError::Changed);
                    }
                    let n = file.read(&mut buffer)?;
                    if n == 0 {
                        break;
                    }
                    total = total.checked_add(n as u64).ok_or(EpochError::Invalid)?;
                    if total > *size {
                        return Err(EpochError::Changed);
                    }
                    hasher.update(&buffer[..n]);
                }
                let actual = format!("{:x}", hasher.finalize());
                if actual != *digest
                    || total != *size
                    || before != FileObservation::from_metadata(&file.metadata()?)
                    || fs.observe(&value.path)?.as_ref() != Some(&before)
                {
                    return Err(EpochError::Changed);
                }
            }
        }
    }
    Ok(())
}
/// Called only by legacy_host after it authenticates the frozen provider and profile.
pub(crate) fn qualify_selection(
    binding: SelectionObservation,
    fs: &RootFs,
    deadline: Deadline,
) -> Result<QualifiedSelection, EpochError> {
    binding_shape(&binding)?;
    check_witnesses(fs, &binding.sources, deadline)?;
    Ok(QualifiedSelection(binding))
}
pub(crate) fn qualify_frame(
    scope: FrameObservation,
    selection: &QualifiedSelection,
    fs: &RootFs,
    deadline: Deadline,
) -> Result<QualifiedFrame, EpochError> {
    frame_shape(&scope, &selection.0)?;
    check_witnesses(fs, &scope.inputs, deadline)?;
    for task in &scope.tasks {
        for item in &task.writes {
            check_anchor(fs, item)?;
        }
    }
    Ok(QualifiedFrame(scope))
}
fn encode(record: &Record) -> Result<Vec<u8>, EpochError> {
    let bytes = serde_json::to_vec(record).map_err(|_| EpochError::Invalid)?;
    if bytes.len() > MAX_BYTES {
        return invalid();
    }
    Ok(bytes)
}
fn validate(record: &Record) -> Result<(), EpochError> {
    if record.version != 2
        || !label(&record.selection)
        || record.transition_count == 0
        || record.transition_count > MAX_TRANSITIONS
        || record.permissions_issued > record.transition_count
    {
        return invalid();
    }
    binding_shape(&record.binding)?;
    if record.dirty.len() > 8192 {
        return invalid();
    }
    for dirty in &record.dirty {
        claim_shape(dirty, &record.binding)?;
    }
    if let Some(frame) = &record.frame {
        frame_shape(&frame.scope, &record.binding)?;
        if frame.number == 0 || frame.number > record.transition_count || frame.attempts.len() > 256
        {
            return invalid();
        }
        let tasks: BTreeSet<_> = frame.scope.tasks.iter().map(|t| t.id.as_str()).collect();
        let mut members = BTreeSet::new();
        for task in &frame.pending {
            if !tasks.contains(task.as_str()) || !members.insert(task.as_str()) {
                return invalid();
            }
        }
        for settled in &frame.settled {
            if !tasks.contains(settled.task.as_str())
                || !members.insert(settled.task.as_str())
                || !valid_digest(&settled.inputs)
            {
                return invalid();
            }
            witness_shape(&settled.outputs, true)?;
            if !frame
                .attempts
                .iter()
                .any(|a| a.id == settled.attempt && a.members.contains(&settled.task))
            {
                return invalid();
            }
        }
        if members != tasks {
            return invalid();
        }
        let mut attempts = BTreeSet::new();
        let mut reports = Claims::new();
        for a in &frame.attempts {
            if !label(&a.id)
                || !attempts.insert(&a.id)
                || a.members.is_empty()
                || a.members.len() > 64
                || !unique(&a.members)
                || a.members.iter().any(|m| !tasks.contains(m.as_str()))
            {
                return invalid();
            }
            match &a.execution {
                AttemptKind::InProcess => {
                    if a.guard.is_some() {
                        return invalid();
                    }
                }
                AttemptKind::Guarded {
                    directory,
                    invocation,
                    launch,
                } => {
                    safe_path(directory)?;
                    if invocation.len() != 32
                        || !invocation.bytes().all(|c| c.is_ascii_hexdigit())
                        || !std::path::Path::new(&launch.program).is_absolute()
                        || launch.args.len() > 256
                        || launch
                            .args
                            .iter()
                            .any(|a| a.len() > 4096 || a.contains('\0'))
                        || !valid_digest(&launch.environment_digest)
                        || !label(&launch.kind)
                        || launch.threads == 0
                        || launch.memory_bytes == 0
                        || launch.execution_ns == 0
                        || launch.queue_deadline_ns == 0
                        || launch.scheduler.pid == 0
                        || launch.scheduler.started.is_empty()
                        || launch.scheduler.boot.is_empty()
                    {
                        return invalid();
                    }
                    claim(&mut reports, directory, &a.id).map_err(|_| EpochError::Invalid)?;
                    if let Some(g) = &a.guard {
                        if [
                            &g.controller_source,
                            &g.issuer_source,
                            &g.request_digest,
                            &g.process_digest,
                            &g.tree_digest,
                        ]
                        .iter()
                        .any(|v| !valid_digest(v))
                        {
                            return invalid();
                        }

                        if g.directory != *directory
                            || g.invocation != *invocation
                            || g.child.boot != g.monitor.boot
                            || g.child.pid == g.monitor.pid
                            || g.controller != launch.scheduler
                            || g.child.boot != launch.scheduler.boot
                            || g.controller_source != record.binding.controller_source
                            || g.issuer_source != record.binding.issuer
                            || g.request_digest != record.binding.request_digest
                            || g.locks.len() != 3
                        {
                            return invalid();
                        }
                    }
                }
            }
        }
        if record.verified_complete && !frame.pending.is_empty() {
            return invalid();
        }
    } else if record.verified_complete {
        return invalid();
    }
    Ok(())
}
/// All object-record positions are checked; ORIGINAL bytes retain duplicate detection.
fn records(value: &serde_json::Value) -> Result<(), EpochError> {
    match value {
        serde_json::Value::Object(map) => {
            for item in map.values() {
                records(item)?;
            }
        }
        serde_json::Value::Array(values) => {
            for item in values {
                if item.is_array() {
                    return invalid();
                }
                records(item)?;
            }
        }
        _ => {}
    }
    Ok(())
}
fn decode(bytes: &[u8]) -> Result<Record, EpochError> {
    if bytes.len() > MAX_BYTES {
        return invalid();
    }
    let value: serde_json::Value =
        serde_json::from_slice(bytes).map_err(|_| EpochError::Invalid)?;
    object(&value)?;
    records(&value)?;
    // Explicit struct positions reject serde's positional sequences.
    fn record_positions(v: &serde_json::Value) -> Result<(), EpochError> {
        match v {
            serde_json::Value::Object(m) => {
                for (key, item) in m {
                    if [
                        "root",
                        "binding",
                        "frame",
                        "scope",
                        "anchor",
                        "fact",
                        "execution",
                        "guard",
                        "child",
                        "monitor",
                    ]
                    .contains(&key.as_str())
                        && !item.is_null()
                    {
                        object(item)?;
                    }
                    if [
                        "sources", "inputs", "outputs", "writes", "tasks", "attempts", "settled",
                        "dirty",
                    ]
                    .contains(&key.as_str())
                        && item.is_array()
                    {
                        for entry in item.as_array().unwrap() {
                            object(entry)?;
                        }
                    }
                    record_positions(item)?;
                }
            }
            serde_json::Value::Array(a) => {
                for e in a {
                    record_positions(e)?;
                }
            }
            _ => {}
        }
        Ok(())
    }
    record_positions(&value)?;
    let record: Record = serde_json::from_slice(bytes).map_err(|_| EpochError::Invalid)?;
    validate(&record)?;
    Ok(record)
}

/// Read-only control context, NOT a qualification/permission. Bounded pages pin one digest.
#[derive(Clone, Debug)]
pub(crate) struct Existing {
    pub selection: String,
    pub digest: String,
    pub frame: Option<u64>,
    pub count: u64,
    pub bytes: Vec<u8>,
}
pub(crate) struct SelectionPermit<'permit, 'guards> {
    selection: &'permit Selection<'guards>,
}
impl SelectionPermit<'_, '_> {
    pub(crate) fn verify(
        &self,
        build: &BuildGuard,
        write: &ContentWriteGuard,
    ) -> Result<(), EpochError> {
        if !std::ptr::eq(build, self.selection.build) || !std::ptr::eq(write, self.selection.write)
        {
            return Err(EpochError::Changed);
        }
        self.selection.current()
    }
}
pub(crate) struct Selection<'a> {
    build: &'a BuildGuard,
    write: &'a ContentWriteGuard,
    fs: RootFs,
    record: Record,
    observation: FileObservation,
    deadline: Deadline,
}
impl<'a> Selection<'a> {
    fn guards(build: &BuildGuard, write: &ContentWriteGuard) -> Result<RootFs, EpochError> {
        if !build.owns_writer(write) {
            return Err(EpochError::Changed);
        }
        let fs = RootFs::open(build.root())?;
        if fs.occupied(INSTALL_JOURNAL)? {
            return invalid();
        }
        Ok(fs)
    }
    pub(crate) fn prepare(
        build: &'a BuildGuard,
        write: &'a ContentWriteGuard,
        qualified: QualifiedSelection,
        id: &str,
        deadline: Deadline,
        mut cut: impl FnMut(Cut) -> io::Result<()>,
    ) -> Result<Self, EpochError> {
        let fs = Self::guards(build, write)?;
        if !label(id) {
            return invalid();
        }
        check_witnesses(&fs, &qualified.0.sources, deadline)?;
        let record = Record {
            version: 2,
            selection: id.into(),
            root: root_identity(build.root())?,
            binding: qualified.0,
            transition_count: 1,
            permissions_issued: 0,
            frame: None,
            dirty: vec![],
            verified_complete: false,
        };
        validate(&record)?;
        fs.publish_metadata(LEGACY_EPOCH, &encode(&record)?)?;
        cut(Cut::Prepared)?;
        let observation = fs.observe(LEGACY_EPOCH)?.ok_or(EpochError::Changed)?;
        Ok(Self {
            build,
            write,
            fs,
            record,
            observation,
            deadline,
        })
    }
    fn load(fs: &RootFs) -> Result<(Record, FileObservation), EpochError> {
        let mut file = fs.file(LEGACY_EPOCH)?;
        let before = FileObservation::from_metadata(&file.metadata()?);
        if before.size > MAX_BYTES as u64 {
            return invalid();
        }
        let mut bytes = vec![];
        file.by_ref()
            .take(MAX_BYTES as u64 + 1)
            .read_to_end(&mut bytes)?;
        if FileObservation::from_metadata(&file.metadata()?) != before
            || fs.observe(LEGACY_EPOCH)?.as_ref() != Some(&before)
        {
            return Err(EpochError::Changed);
        }
        Ok((decode(&bytes)?, before))
    }
    pub(crate) fn inspect(
        build: &BuildGuard,
        write: &ContentWriteGuard,
    ) -> Result<Option<Existing>, EpochError> {
        let fs = Self::guards(build, write)?;
        if !fs.occupied(LEGACY_EPOCH)? {
            return Ok(None);
        }
        let (record, _) = Self::load(&fs)?;
        if record.root != root_identity(build.root())? {
            return Err(EpochError::Changed);
        }
        let bytes = encode(&record)?;
        Ok(Some(Existing {
            selection: record.selection.clone(),
            digest: sha256(&bytes),
            frame: record.frame.as_ref().map(|f| f.number),
            count: record.transition_count,
            bytes,
        }))
    }
    pub(crate) fn resume(
        build: &'a BuildGuard,
        write: &'a ContentWriteGuard,
        qualified: &QualifiedSelection,
        deadline: Deadline,
    ) -> Result<Self, EpochError> {
        let fs = Self::guards(build, write)?;
        let (record, observation) = Self::load(&fs)?;
        if record.root != root_identity(build.root())? || record.binding != qualified.0 {
            return Err(EpochError::Changed);
        }
        let s = Self {
            build,
            write,
            fs,
            record,
            observation,
            deadline,
        };
        s.current()?;
        s.cleanup_all()?;
        Ok(s)
    }
    fn current(&self) -> Result<(), EpochError> {
        Self::guards(self.build, self.write)?;
        if root_identity(self.build.root())? != self.record.root {
            return Err(EpochError::Changed);
        }
        let (record, observation) = Self::load(&self.fs)?;
        if record != self.record || observation != self.observation {
            return Err(EpochError::Changed);
        }
        check_witnesses(&self.fs, &self.record.binding.sources, self.deadline)
    }
    fn save(
        &mut self,
        mut next: Record,
        point: Cut,
        mut cut: impl FnMut(Cut) -> io::Result<()>,
    ) -> Result<(), EpochError> {
        self.current()?;
        next.transition_count = self
            .record
            .transition_count
            .checked_add(1)
            .filter(|v| *v <= MAX_TRANSITIONS)
            .ok_or(EpochError::Invalid)?;
        validate(&next)?;
        self.fs.replace_metadata(LEGACY_EPOCH, &encode(&next)?)?;
        let observation = self.fs.observe(LEGACY_EPOCH)?.ok_or(EpochError::Changed)?;
        self.record = next;
        self.observation = observation;
        cut(point)?;
        Ok(())
    }
    pub(crate) fn permit(&self) -> SelectionPermit<'_, 'a> {
        SelectionPermit { selection: self }
    }
    pub(crate) fn digest(&self) -> Result<String, EpochError> {
        Ok(sha256(&encode(&self.record)?))
    }
    pub(crate) fn frame(&self) -> Option<u64> {
        self.record.frame.as_ref().map(|f| f.number)
    }
    pub(crate) fn count(&self) -> u64 {
        self.record.transition_count
    }
    pub(crate) fn binding(&self) -> &SelectionObservation {
        &self.record.binding
    }
    pub(crate) fn advance(
        &mut self,
        qualified: QualifiedFrame,
        cut: impl FnMut(Cut) -> io::Result<()>,
    ) -> Result<(), EpochError> {
        self.current()?;
        if self.record.verified_complete {
            return invalid();
        }
        if let Some(frame) = &self.record.frame {
            if !frame.pending.is_empty() {
                return Err(EpochError::Pending);
            }
            self.cleanup_all()?;
        }
        frame_shape(&qualified.0, &self.record.binding)?;
        check_witnesses(&self.fs, &qualified.0.inputs, self.deadline)?;
        for task in &qualified.0.tasks {
            for c in &task.writes {
                check_anchor(&self.fs, c)?;
            }
        }
        let mut next = self.record.clone();
        let number = self
            .frame()
            .unwrap_or(0)
            .checked_add(1)
            .ok_or(EpochError::Invalid)?;
        next.frame = Some(Frame {
            number,
            pending: qualified.0.tasks.iter().map(|t| t.id.clone()).collect(),
            scope: qualified.0,
            settled: vec![],
            attempts: vec![],
        });
        self.save(next, Cut::Advanced, cut)
    }
    pub(crate) fn begin_attempt(
        &mut self,
        attempt: GuardAttempt,
        cut: impl FnMut(Cut) -> io::Result<()>,
    ) -> Result<(), EpochError> {
        let mut next = self.record.clone();
        let frame = next.frame.as_mut().ok_or(EpochError::Invalid)?;
        if next.verified_complete
            || attempt.guard.is_some()
            || attempt.members.iter().any(|m| !frame.pending.contains(m))
        {
            return invalid();
        }
        if matches!(attempt.execution, AttemptKind::InProcess)
            && matches!(frame.scope.profile, Profile::NativeBatch)
        {
            return invalid();
        }
        check_witnesses(&self.fs, &frame.scope.inputs, self.deadline)?;
        for old in &frame.attempts {
            if old.members.iter().any(|m| attempt.members.contains(m)) {
                self.cleanup_attempt(old)?;
            }
        }
        if let AttemptKind::Guarded { directory, .. } = &attempt.execution {
            match self.fs.occupied(directory) {
                Ok(false) => {}
                Err(e) if e.kind() == io::ErrorKind::NotFound => {}
                _ => return Err(EpochError::Changed),
            }
        }
        frame.attempts.push(attempt);
        next.permissions_issued = next
            .permissions_issued
            .checked_add(1)
            .ok_or(EpochError::Invalid)?;
        self.save(next, Cut::Intent, cut)
    }
    pub(crate) fn bind_guard(
        &mut self,
        id: &str,
        guard: GuardBinding,
        cut: impl FnMut(Cut) -> io::Result<()>,
    ) -> Result<(), EpochError> {
        let mut next = self.record.clone();
        let frame = next.frame.as_mut().ok_or(EpochError::Invalid)?;
        let a = frame
            .attempts
            .iter_mut()
            .find(|a| a.id == id)
            .ok_or(EpochError::Invalid)?;
        if a.guard.is_some() {
            return invalid();
        }
        if let AttemptKind::Guarded { launch, .. } = &a.execution {
            if guard.child.boot != launch.scheduler.boot
                || guard.monitor.boot != launch.scheduler.boot
            {
                return Err(EpochError::CleanupUnknown);
            }
        } else {
            return Err(EpochError::Invalid);
        }
        // Raw authoritative receipt/provenance checks occurred in FrozenIssuer; this
        // method only persists that validated observation under exact attempt membership.
        a.guard = Some(guard);
        self.save(next, Cut::GuardBound, cut)
    }
    fn cleanup_attempt(&self, attempt: &GuardAttempt) -> Result<(), EpochError> {
        match &attempt.execution {
            AttemptKind::InProcess => Ok(()),
            AttemptKind::Guarded { .. } => {
                let binding = attempt.guard.as_ref().ok_or(EpochError::CleanupUnknown)?;
                crate::legacy_host_launch::verify_persisted_guard(&self.fs, binding)
            }
        }
    }
    fn cleanup_all(&self) -> Result<(), EpochError> {
        if let Some(frame) = &self.record.frame {
            for a in &frame.attempts {
                self.cleanup_attempt(a)?;
            }
        }
        Ok(())
    }
    pub(crate) fn settle(
        &mut self,
        settled: SettlementObservation,
        cut: impl FnMut(Cut) -> io::Result<()>,
    ) -> Result<(), EpochError> {
        self.current()?;
        let frame = self.record.frame.as_ref().ok_or(EpochError::Invalid)?;
        let task = frame
            .scope
            .tasks
            .iter()
            .find(|t| t.id == settled.task)
            .ok_or(EpochError::Invalid)?;
        let attempt = frame
            .attempts
            .iter()
            .find(|a| a.id == settled.attempt && a.members.contains(&task.id))
            .ok_or(EpochError::Invalid)?;
        self.cleanup_attempt(attempt)?;
        if attempt.guard.as_ref().is_some_and(|g| g.returncode != 0)
            && frame.scope.profile != Profile::NativeBatch
        {
            return Err(EpochError::Pending);
        }

        for old in &frame.attempts {
            if old.members.contains(&task.id) {
                self.cleanup_attempt(old)?;
            }
        }
        if !frame.pending.contains(&task.id) {
            return invalid();
        }
        witness_shape(&settled.outputs, true)?;
        if settled.outputs.iter().any(|w| {
            !task
                .writes
                .iter()
                .any(|c| w.path == c.path || w.path.starts_with(&(c.path.clone() + "/")))
        }) {
            return invalid();
        }
        check_witnesses(&self.fs, &frame.scope.inputs, self.deadline)?;
        check_witnesses(&self.fs, &settled.outputs, self.deadline)?;
        // A repaired directory cannot be certified by one arbitrary descendant.
        // EVERY declared write (including carried old claims) needs complete disposition.
        for item in &task.writes {
            complete_disposition(&self.fs, item, &settled.outputs, self.deadline)?;
        }
        for dirty in &self.record.dirty {
            if task.writes.iter().any(|w| covers(w, dirty)) {
                complete_disposition(&self.fs, dirty, &settled.outputs, self.deadline)?;
            }
        }
        let mut next = self.record.clone();
        next.dirty
            .retain(|d| !task.writes.iter().any(|w| covers(w, d)));
        let f = next.frame.as_mut().unwrap();
        f.pending.retain(|p| p != &settled.task);
        f.settled.push(settled);
        self.save(next, Cut::Settled, cut)
    }
    pub(crate) fn requeue(
        &mut self,
        members: &[String],
        cut: impl FnMut(Cut) -> io::Result<()>,
    ) -> Result<(), EpochError> {
        self.cleanup_all()?;
        if members.is_empty() || !unique(members) {
            return invalid();
        }
        let mut next = self.record.clone();
        let f = next.frame.as_mut().ok_or(EpochError::Invalid)?;
        if members
            .iter()
            .any(|m| !f.settled.iter().any(|s| &s.task == m))
        {
            return invalid();
        }
        f.settled.retain(|s| !members.contains(&s.task));
        f.pending.extend_from_slice(members);
        next.verified_complete = false;
        self.save(next, Cut::Requeued, cut)
    }
    /// A changed source never hides prior dirty authority. Exact coverage and all cleanup first.
    pub(crate) fn supersede(
        build: &'a BuildGuard,
        write: &'a ContentWriteGuard,
        new: QualifiedSelection,
        initial: Option<QualifiedFrame>,
        deadline: Deadline,
        cut: impl FnMut(Cut) -> io::Result<()>,
    ) -> Result<Self, EpochError> {
        let fs = Self::guards(build, write)?;
        let (record, observation) = Self::load(&fs)?;
        if record.root != root_identity(build.root())? {
            return Err(EpochError::Changed);
        }
        // Deliberately do not check OLD source bytes: Supersede exists for a source fix.
        let mut old = Self {
            build,
            write,
            fs,
            record,
            observation,
            deadline,
        };
        old.cleanup_all()?;
        let mut dirty = old.record.dirty.clone();
        if let Some(frame) = &old.record.frame {
            for task in &frame.scope.tasks {
                if frame.pending.contains(&task.id)
                    && frame.attempts.iter().any(|a| a.members.contains(&task.id))
                {
                    for c in &task.writes {
                        if !dirty.contains(c) {
                            dirty.push(c.clone());
                        }
                    }
                }
            }
        }
        for c in &dirty {
            check_anchor(&old.fs, c)?;
        }
        binding_shape(&new.0)?;
        check_witnesses(&old.fs, &new.0.sources, deadline)?;
        let frame = match initial {
            None => {
                if old.record.permissions_issued != 0
                    || !dirty.is_empty()
                    || old
                        .record
                        .frame
                        .as_ref()
                        .is_some_and(|f| !f.attempts.is_empty())
                {
                    return Err(EpochError::Pending);
                }
                None
            }
            Some(q) => {
                frame_shape(&q.0, &new.0)?;
                if dirty.iter().any(|d| {
                    !q.0.tasks.iter().any(|t| {
                        t.replay == Replay::ClosedReplay && t.writes.iter().any(|c| covers(c, d))
                    })
                }) {
                    return Err(EpochError::Pending);
                }
                check_witnesses(&old.fs, &q.0.inputs, deadline)?;
                for t in &q.0.tasks {
                    for c in &t.writes {
                        check_anchor(&old.fs, c)?;
                    }
                }
                Some(Frame {
                    number: old
                        .frame()
                        .unwrap_or(0)
                        .checked_add(1)
                        .ok_or(EpochError::Invalid)?,
                    pending: q.0.tasks.iter().map(|t| t.id.clone()).collect(),
                    scope: q.0,
                    settled: vec![],
                    attempts: vec![],
                })
            }
        };
        let mut next = old.record.clone();
        next.binding = new.0;
        next.frame = frame;
        next.dirty = dirty;
        next.verified_complete = false;
        // Normal save would validate OLD sources. Supersede verifies only exact old record/root,
        // new qualification, complete claims and authoritative cleanup, under retained guards.
        let (now, obs) = Self::load(&old.fs)?;
        if now != old.record || obs != old.observation {
            return Err(EpochError::Changed);
        }
        next.transition_count = old
            .count()
            .checked_add(1)
            .filter(|v| *v <= MAX_TRANSITIONS)
            .ok_or(EpochError::Invalid)?;
        validate(&next)?;
        old.fs.replace_metadata(LEGACY_EPOCH, &encode(&next)?)?;
        old.observation = old.fs.observe(LEGACY_EPOCH)?.ok_or(EpochError::Changed)?;
        old.record = next;
        let mut cut = cut;
        cut(Cut::Superseded)?;
        Ok(old)
    }
    /// Only the bound fixed provider's PURE full graph traversal may call this after finalizers.
    pub(crate) fn finish(
        &mut self,
        final_sources: &[Witness],
        final_outputs: &[Witness],
        topology: &str,
        mut cut: impl FnMut(Cut) -> io::Result<()>,
    ) -> Result<(), EpochError> {
        self.current()?;
        self.cleanup_all()?;
        let frame = self.record.frame.as_ref().ok_or(EpochError::Pending)?;
        if !frame.pending.is_empty()
            || !self.record.dirty.is_empty()
            || topology != frame.scope.topology
        {
            return Err(EpochError::Pending);
        }
        witness_shape(final_sources, true)?;
        witness_shape(final_outputs, true)?;
        check_witnesses(&self.fs, final_sources, self.deadline)?;
        check_witnesses(&self.fs, final_outputs, self.deadline)?;
        let mut next = self.record.clone();
        next.verified_complete = true;
        self.save(next, Cut::Complete, &mut cut)?;
        self.current()?;
        check_witnesses(&self.fs, final_outputs, self.deadline)?;
        self.fs.remove_owned(LEGACY_EPOCH, &self.observation)?;
        cut(Cut::Removed)?;
        Ok(())
    }
}
fn complete_disposition(
    fs: &RootFs,
    claim: &WriteClaim,
    outputs: &[Witness],
    deadline: Deadline,
) -> Result<(), EpochError> {
    let exact = outputs
        .iter()
        .find(|w| w.path == claim.path)
        .ok_or(EpochError::Pending)?;
    match &exact.fact {
        Fact::Absent | Fact::File { .. } => {
            check_witnesses(fs, std::slice::from_ref(exact), deadline)
        }
        Fact::Directory { .. } => {
            let expected: BTreeSet<_> = outputs
                .iter()
                .filter(|w| w.path == claim.path || w.path.starts_with(&(claim.path.clone() + "/")))
                .map(|w| w.path.clone())
                .collect();
            let mut pending = vec![claim.path.clone()];
            let mut actual = BTreeSet::new();
            let mut folded = BTreeSet::new();
            while let Some(path) = pending.pop() {
                if deadline.expired() {
                    return Err(EpochError::Changed);
                }
                if actual.len() >= MAX_WITNESSES
                    || !actual.insert(path.clone())
                    || !folded.insert(crate::paths::folded(&path))
                {
                    return Err(EpochError::Invalid);
                }
                match fs.directory_identity(&path) {
                    Ok(Some(_)) => {
                        for name in fs.metadata_names(&path, MAX_WITNESSES)? {
                            pending.push(format!("{path}/{name}"));
                        }
                    }
                    Err(e) if e.raw_os_error() == Some(libc::ENOTDIR) => {
                        fs.file(&path)?;
                    }
                    Ok(None) => return Err(EpochError::Changed),
                    Err(e) => return Err(e.into()),
                }
            }
            if actual != expected {
                return Err(EpochError::Pending);
            }
            let witnesses: Vec<_> = outputs
                .iter()
                .filter(|w| expected.contains(&w.path))
                .cloned()
                .collect();
            if witnesses.iter().any(|w| matches!(w.fact, Fact::Absent)) {
                return Err(EpochError::Invalid);
            }
            check_witnesses(fs, &witnesses, deadline)
        }
    }
}

fn covers(new: &WriteClaim, old: &WriteClaim) -> bool {
    new.anchor == old.anchor
        && (new.canonical == old.canonical
            || old.canonical.starts_with(&(new.canonical.clone() + "/")))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::checkout_locks::{CheckoutLocks, LockError};
    use std::fs;
    use std::os::unix::fs::PermissionsExt;
    use std::path::PathBuf;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::time::Duration;
    static NEXT: AtomicU64 = AtomicU64::new(0);
    struct Fixture {
        root: PathBuf,
        locks: CheckoutLocks,
    }
    impl Fixture {
        fn new() -> Self {
            let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
                "atelier-selection-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&root).unwrap();
            fs::create_dir(root.join("out")).unwrap();
            fs::write(root.join("source"), b"first").unwrap();
            fs::set_permissions(root.join("source"), fs::Permissions::from_mode(0o600)).unwrap();
            let locks = CheckoutLocks::open(&root).unwrap();
            Self { root, locks }
        }
        fn fs(&self) -> RootFs {
            RootFs::open(&self.root).unwrap()
        }
        fn deadline(&self) -> Deadline {
            Deadline::after(Duration::from_secs(30))
        }
        fn witness(&self, path: &str) -> Witness {
            let bytes = fs::read(self.root.join(path)).unwrap();
            let m = fs::metadata(self.root.join(path)).unwrap();
            Witness {
                path: path.into(),
                fact: Fact::File {
                    digest: sha256(&bytes),
                    size: bytes.len() as u64,
                    mode: m.mode() & 0o777,
                },
            }
        }
        fn binding(&self) -> SelectionObservation {
            SelectionObservation {
                project: "fixture".into(),
                selector: vec!["copy".into()],
                source_plan: sha256(&fs::read(self.root.join("source")).unwrap()),
                request_digest: sha256(b"request"),
                issuer: sha256(b"fixed-test-provider"),
                controller_source: sha256(b"fixed-test-controller"),
                roots: vec!["out".into()],
                sources: vec![self.witness("source")],
            }
        }
        fn qualified(&self) -> QualifiedSelection {
            qualify_selection(self.binding(), &self.fs(), self.deadline()).unwrap()
        }
        fn frame_observation(&self, path: &str) -> FrameObservation {
            let m = fs::metadata(&self.root).unwrap();
            FrameObservation {
                profile: Profile::DataStageCopies,
                topology: sha256(b"existing graph fixture copy"),
                tasks: vec![TaskScope {
                    id: "copy".into(),
                    replay: Replay::ClosedReplay,
                    writes: vec![WriteClaim {
                        path: path.into(),
                        canonical: path.into(),
                        anchor: Anchor {
                            path: String::new(),
                            device: m.dev(),
                            inode: m.ino(),
                        },
                    }],
                }],
                inputs: vec![self.witness("source")],
            }
        }
        fn frame(&self, path: &str) -> QualifiedFrame {
            qualify_frame(
                self.frame_observation(path),
                &self.qualified(),
                &self.fs(),
                self.deadline(),
            )
            .unwrap()
        }
        fn copy(&self) {
            fs::write(
                self.root.join("out/a"),
                fs::read(self.root.join("source")).unwrap(),
            )
            .unwrap();
            fs::set_permissions(self.root.join("out/a"), fs::Permissions::from_mode(0o600))
                .unwrap();
        }
        fn attempt(&self) -> GuardAttempt {
            GuardAttempt {
                id: "attempt1".into(),
                members: vec!["copy".into()],
                execution: AttemptKind::InProcess,
                guard: None,
            }
        }
        fn settled(&self) -> SettlementObservation {
            SettlementObservation {
                task: "copy".into(),
                attempt: "attempt1".into(),
                inputs: sha256(b"normal input identity"),
                outputs: vec![self.witness("out/a")],
            }
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            fs::remove_dir_all(&self.root).unwrap();
        }
    }
    fn fault(point: Cut) -> impl FnMut(Cut) -> io::Result<()> {
        move |actual| {
            if actual == point {
                Err(io::Error::other("injected durable cut"))
            } else {
                Ok(())
            }
        }
    }

    #[test]
    fn continuous_selection_survives_each_durable_cut_and_finishes_only_after_fresh_validation() {
        let f = Fixture::new();
        let build = f.locks.try_build_exclusive().unwrap();
        let write = build.try_legacy_write_content().unwrap();
        assert!(
            Selection::prepare(
                &build,
                &write,
                f.qualified(),
                "selection",
                f.deadline(),
                fault(Cut::Prepared)
            )
            .is_err()
        );
        let mut s = Selection::resume(&build, &write, &f.qualified(), f.deadline()).unwrap();
        assert!(s.advance(f.frame("out/a"), fault(Cut::Advanced)).is_err());
        assert!(f.fs().occupied(LEGACY_EPOCH).unwrap());
        assert!(s.begin_attempt(f.attempt(), fault(Cut::Intent)).is_err());
        f.copy();
        assert!(s.settle(f.settled(), fault(Cut::Settled)).is_err());
        let source = [f.witness("source")];
        let output = [f.witness("out/a")];
        assert!(
            s.finish(
                &source,
                &output,
                &sha256(b"existing graph fixture copy"),
                fault(Cut::Complete)
            )
            .is_err()
        );
        assert!(f.fs().occupied(LEGACY_EPOCH).unwrap());
        s.finish(
            &source,
            &output,
            &sha256(b"existing graph fixture copy"),
            |_| Ok(()),
        )
        .unwrap();
        assert!(!f.fs().occupied(LEGACY_EPOCH).unwrap());
        drop(s);
        drop(write);
        drop(build);
        assert!(f.locks.try_read_content().is_ok());
    }
    #[test]
    fn source_fix_supersede_carries_exact_dirty_claims_count_and_no_settled_credit() {
        let f = Fixture::new();
        fs::write(f.root.join("out/independent"), b"keep").unwrap();
        let build = f.locks.try_build_exclusive().unwrap();
        let write = build.try_legacy_write_content().unwrap();
        let mut s = Selection::prepare(
            &build,
            &write,
            f.qualified(),
            "selection",
            f.deadline(),
            |_| Ok(()),
        )
        .unwrap();
        s.advance(f.frame("out/a"), |_| Ok(())).unwrap();
        s.begin_attempt(f.attempt(), |_| Ok(())).unwrap();
        fs::write(f.root.join("out/a"), b"partial").unwrap();
        let count = s.count();
        drop(s);
        fs::write(f.root.join("source"), b"fixed").unwrap();
        assert!(
            Selection::supersede(
                &build,
                &write,
                f.qualified(),
                Some(f.frame("out/new")),
                f.deadline(),
                |_| Ok(())
            )
            .is_err()
        );
        let mut repaired = Selection::supersede(
            &build,
            &write,
            f.qualified(),
            Some(f.frame("out/a")),
            f.deadline(),
            |_| Ok(()),
        )
        .unwrap();
        assert_eq!(repaired.count(), count + 1);
        assert_eq!(repaired.record.dirty.len(), 1);
        assert!(repaired.record.frame.as_ref().unwrap().settled.is_empty());
        repaired.begin_attempt(f.attempt(), |_| Ok(())).unwrap();
        f.copy();
        repaired.settle(f.settled(), |_| Ok(())).unwrap();
        assert!(repaired.record.dirty.is_empty());
        assert_eq!(fs::read(f.root.join("out/independent")).unwrap(), b"keep");
        repaired
            .finish(
                &[f.witness("source")],
                &[f.witness("out/a")],
                &sha256(b"existing graph fixture copy"),
                |_| Ok(()),
            )
            .unwrap();
    }
    #[test]
    fn prepared_only_shortcut_never_hides_prior_permission_across_frames() {
        let f = Fixture::new();
        let build = f.locks.try_build_exclusive().unwrap();
        let write = build.try_legacy_write_content().unwrap();
        let mut s = Selection::prepare(
            &build,
            &write,
            f.qualified(),
            "selection",
            f.deadline(),
            |_| Ok(()),
        )
        .unwrap();
        s.advance(f.frame("out/a"), |_| Ok(())).unwrap();
        s.begin_attempt(f.attempt(), |_| Ok(())).unwrap();
        f.copy();
        s.settle(f.settled(), |_| Ok(())).unwrap();
        s.advance(f.frame("out/a"), |_| Ok(())).unwrap();
        assert!(s.record.frame.as_ref().unwrap().attempts.is_empty());
        drop(s);
        fs::write(f.root.join("source"), b"fixed").unwrap();
        assert!(
            Selection::supersede(
                &build,
                &write,
                f.qualified(),
                None,
                f.deadline(),
                |_| Ok(())
            )
            .is_err()
        );
        assert!(f.fs().occupied(LEGACY_EPOCH).unwrap());
    }
    #[test]
    fn missing_guard_cleanup_is_unknown_and_cannot_be_hidden_by_source_change() {
        let f = Fixture::new();
        let build = f.locks.try_build_exclusive().unwrap();
        let write = build.try_legacy_write_content().unwrap();
        let mut s = Selection::prepare(
            &build,
            &write,
            f.qualified(),
            "selection",
            f.deadline(),
            |_| Ok(()),
        )
        .unwrap();
        s.advance(f.frame("out/a"), |_| Ok(())).unwrap();
        let identity = ProcessIdentity {
            pid: 1,
            boot: "boot".into(),
            started: "start".into(),
        };
        let attempt = GuardAttempt {
            id: "guarded".into(),
            members: vec!["copy".into()],
            guard: None,
            execution: AttemptKind::Guarded {
                directory: "reports/fresh".into(),
                invocation: "0123456789abcdef0123456789abcdef".into(),
                launch: LaunchDescription {
                    scheduler: identity,
                    program: "/installed/program".into(),
                    args: vec!["job".into()],
                    environment_digest: sha256(b"env"),
                    kind: "blender".into(),
                    threads: 3,
                    memory_bytes: 10 * 1024 * 1024 * 1024,
                    execution_ns: 120_000_000_000,
                    queue_deadline_ns: 200_000_000_000,
                },
            },
        };
        s.begin_attempt(attempt, |_| Ok(())).unwrap();
        drop(s);
        fs::write(f.root.join("source"), b"fixed").unwrap();
        assert!(
            Selection::supersede(
                &build,
                &write,
                f.qualified(),
                Some(f.frame("out/a")),
                f.deadline(),
                |_| Ok(())
            )
            .is_err()
        );
        drop(write);
        drop(build);
        assert!(matches!(
            f.locks.try_read_content(),
            Err(LockError::LegacyEpochIncomplete)
        ));
    }
    #[test]
    fn strict_v2_state_caps_and_transition_overflow_refuse_without_removing_barrier() {
        let f = Fixture::new();
        let build = f.locks.try_build_exclusive().unwrap();
        let write = build.try_legacy_write_content().unwrap();
        let mut s = Selection::prepare(
            &build,
            &write,
            f.qualified(),
            "selection",
            f.deadline(),
            |_| Ok(()),
        )
        .unwrap();
        let raw = encode(&s.record).unwrap();
        let mut v: serde_json::Value = serde_json::from_slice(&raw).unwrap();
        v["binding"]["selector"] = serde_json::json!(["copy", "copy"]);
        assert!(decode(&serde_json::to_vec(&v).unwrap()).is_err());
        let duplicate = String::from_utf8(raw.clone()).unwrap().replacen(
            "\"version\":2",
            "\"version\":2,\"version\":2",
            1,
        );
        assert!(decode(duplicate.as_bytes()).is_err());
        let mut scope = f.frame_observation("out/a");
        scope.tasks = vec![scope.tasks[0].clone(); 65];
        assert!(qualify_frame(scope, &f.qualified(), &f.fs(), f.deadline()).is_err());
        s.record.transition_count = MAX_TRANSITIONS;
        f.fs()
            .replace_metadata(LEGACY_EPOCH, &encode(&s.record).unwrap())
            .unwrap();
        s.observation = f.fs().observe(LEGACY_EPOCH).unwrap().unwrap();
        assert!(s.advance(f.frame("out/a"), |_| Ok(())).is_err());
        assert!(f.fs().occupied(LEGACY_EPOCH).unwrap());
    }
    #[test]
    fn actual_ex_receipt_verifier_keeps_install_journal_and_short_permit_barriers() {
        use crate::install::{CurrentStatus, InstallPolicy, ProjectNamespace, ReceiptReader};
        let f = Fixture::new();
        let reader = ReceiptReader::open(
            &f.root,
            InstallPolicy {
                project: ProjectNamespace::new("fixture").unwrap(),
                allowed_install_roots: vec!["out".into()],
            },
        )
        .unwrap();
        let build = f.locks.try_build_exclusive().unwrap();
        let write = build.try_legacy_write_content().unwrap();
        let mut s = Selection::prepare(
            &build,
            &write,
            f.qualified(),
            "selection",
            f.deadline(),
            |_| Ok(()),
        )
        .unwrap();
        let unit = crate::legacy_epoch::tests::prepared();
        {
            let permit = s.permit();
            assert!(matches!(
                reader.receipt_status_selection(&build, &write, &permit, &unit),
                Ok(CurrentStatus::NotMaterialized)
            ));
            f.fs()
                .replace_metadata(INSTALL_JOURNAL, b"invalid journal")
                .unwrap();
            assert!(
                reader
                    .receipt_status_selection(&build, &write, &permit, &unit)
                    .is_err()
            );
        }
        let own = f.fs().observe(INSTALL_JOURNAL).unwrap().unwrap();
        f.fs().remove_owned(INSTALL_JOURNAL, &own).unwrap();
        // Ending the short permit must permit a subsequent mutation of this SAME authority.
        s.advance(f.frame("out/a"), |_| Ok(())).unwrap();
        s.begin_attempt(f.attempt(), |_| Ok(())).unwrap();
        f.copy();
        s.settle(f.settled(), |_| Ok(())).unwrap();
        s.finish(
            &[f.witness("source")],
            &[f.witness("out/a")],
            &sha256(b"existing graph fixture copy"),
            |_| Ok(()),
        )
        .unwrap();
    }
    #[test]
    fn dirty_directory_requires_complete_tree_or_exact_absence_not_one_child() {
        let f = Fixture::new();
        let build = f.locks.try_build_exclusive().unwrap();
        let write = build.try_legacy_write_content().unwrap();
        let mut s = Selection::prepare(
            &build,
            &write,
            f.qualified(),
            "selection",
            f.deadline(),
            |_| Ok(()),
        )
        .unwrap();
        s.advance(f.frame("out/tree"), |_| Ok(())).unwrap();
        s.begin_attempt(f.attempt(), |_| Ok(())).unwrap();
        fs::create_dir(f.root.join("out/tree")).unwrap();
        fs::write(f.root.join("out/tree/a"), b"a").unwrap();
        fs::write(f.root.join("out/tree/leftover"), b"old partial").unwrap();
        let partial = SettlementObservation {
            task: "copy".into(),
            attempt: "attempt1".into(),
            inputs: sha256(b"inputs"),
            outputs: vec![f.witness("out/tree/a")],
        };
        assert!(s.settle(partial.clone(), |_| Ok(())).is_err());
        let m = fs::metadata(f.root.join("out/tree")).unwrap();
        let root = Witness {
            path: "out/tree".into(),
            fact: Fact::Directory {
                device: m.dev(),
                inode: m.ino(),
            },
        };
        let mut incomplete = partial.clone();
        incomplete.outputs.push(root.clone());
        assert!(s.settle(incomplete, |_| Ok(())).is_err());
        let mut complete = partial;
        complete
            .outputs
            .extend([root, f.witness("out/tree/leftover")]);
        s.settle(complete, |_| Ok(())).unwrap();
        s.requeue(&["copy".into()], |_| Ok(())).unwrap();
        let mut attempt = f.attempt();
        attempt.id = "attempt2".into();
        s.begin_attempt(attempt, |_| Ok(())).unwrap();
        fs::remove_dir_all(f.root.join("out/tree")).unwrap();
        s.settle(
            SettlementObservation {
                task: "copy".into(),
                attempt: "attempt2".into(),
                inputs: sha256(b"inputs"),
                outputs: vec![Witness {
                    path: "out/tree".into(),
                    fact: Fact::Absent,
                }],
            },
            |_| Ok(()),
        )
        .unwrap();
        assert!(s.record.frame.as_ref().unwrap().pending.is_empty());
    }
}
