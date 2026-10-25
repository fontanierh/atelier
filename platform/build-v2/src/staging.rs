//! Frozen-input staging and output collection for one worker job (C1b).
//!
//! [`stage`] turns an A3 [`PreparedUnit`] into a fresh, owned job folder holding exactly the
//! declared code and inputs at their declared job-relative paths, read-only, plus an empty writable
//! `output/`. Code bytes come from the frozen snapshot that was keyed, checked against the keyed
//! digests; live sources are never reread. Item inputs are cloned from the object store, never
//! copied. [`collect_outputs`] turns a finished job's `output/` tree into the complete manifest
//! that B2 consumes.
use crate::keys::{InputPayload, PreparedUnit};
use crate::protocol::JobRequest;
use crate::results::{ActualOutput, OutputSources, WriteTransaction};
use crate::schema::{InputKind, StoredFile};
use crate::source_hashes::sha256;
use crate::store::{ObjectDigest, ObjectStore};
use crate::validate::{SnapshotEntry, SourceSnapshot};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::fs::{self, OpenOptions};
use std::io::{self, Write};
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::{Component, Path, PathBuf};

/// Where staging gets stored object bytes. Implementations clone, never copy.
pub trait ObjectSource {
    /// Create `destination` (which must not exist) as an independent clone of the object `digest`; staging applies its keyed read-only mode.
    fn clone_object(&self, digest: &ObjectDigest, destination: &Path) -> Result<(), SourceError>;
}

/// Why an [`ObjectSource`] could not provide one object. The controller classifies staging
/// failures by this kind; nothing travels in a side channel.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SourceErrorKind {
    /// The source does not hold this digest, or cannot reach it now.
    Unavailable,
    /// The source's bytes for this digest changed or were replaced after they were certified.
    Changed,
    /// The destination cannot be a clone of the source; there is no copy fallback.
    CloneUnsupported,
    /// Any other I/O failure while cloning.
    Io,
}

/// One object an [`ObjectSource`] could not clone, with the digest staging asked for.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SourceError {
    pub kind: SourceErrorKind,
    pub digest: ObjectDigest,
    pub message: String,
}

impl fmt::Display for SourceError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "cannot clone object {}: {}",
            self.digest, self.message
        )
    }
}

impl std::error::Error for SourceError {}

/// Why [`stage`] failed: an object source's typed refusal, or any other staging error.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum StageError {
    Source(SourceError),
    Staging(String),
}

impl fmt::Display for StageError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Source(error) => error.fmt(formatter),
            Self::Staging(message) => formatter.write_str(message),
        }
    }
}

impl std::error::Error for StageError {}

impl From<String> for StageError {
    fn from(message: String) -> Self {
        Self::Staging(message)
    }
}

impl From<&str> for StageError {
    fn from(message: &str) -> Self {
        Self::Staging(message.into())
    }
}

impl From<StageError> for String {
    fn from(error: StageError) -> Self {
        error.to_string()
    }
}

/// Store objects read while a live B2 write transaction pins them. The transaction's lease claims
/// the consumer key and every upstream result key, so producer objects stay protected from GC for
/// as long as this borrow lives. Restores are B1 clone-only and hash nothing.
pub struct PinnedObjects<'a> {
    objects: &'a ObjectStore,
    _pin: &'a WriteTransaction,
}

impl<'a> PinnedObjects<'a> {
    pub fn new(objects: &'a ObjectStore, pin: &'a WriteTransaction) -> Self {
        Self { objects, _pin: pin }
    }
}

impl ObjectSource for PinnedObjects<'_> {
    fn clone_object(&self, digest: &ObjectDigest, destination: &Path) -> Result<(), SourceError> {
        self.objects
            .clone_to(digest, destination)
            .map_err(|error| SourceError {
                kind: SourceErrorKind::Io,
                digest: digest.clone(),
                message: error.to_string(),
            })
    }
}

impl ObjectSource for crate::results::SelectedItems<'_> {
    fn clone_object(&self, digest: &ObjectDigest, destination: &Path) -> Result<(), SourceError> {
        self.clone_to(digest, destination)
    }
}

/// A staged job folder and the request that names it. Only [`stage`] builds one.
#[derive(Debug)]
pub struct StagedJob {
    job_dir: PathBuf,
    request: JobRequest,
}

impl StagedJob {
    pub fn job_dir(&self) -> &Path {
        &self.job_dir
    }
    pub fn output_dir(&self) -> PathBuf {
        self.job_dir.join("output")
    }
    /// The worker request: control metadata (job ID and folder) plus declared names only.
    pub fn request(&self) -> &JobRequest {
        &self.request
    }
}

fn io_error(path: &Path, error: io::Error) -> String {
    format!("{}: {error}", path.display())
}

/// Lexically safe, still-relative join; `relative` was validated by A2/A3 and is checked again.
fn inside(root: &Path, relative: &str) -> Result<PathBuf, String> {
    let path = Path::new(relative);
    let safe = !relative.is_empty()
        && !relative.contains(['\\', '\0'])
        && path
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
        && relative.split('/').all(|part| !part.is_empty());
    if !safe {
        return Err(format!("unsafe job-relative path: {relative:?}"));
    }
    Ok(root.join(path))
}

/// Create every missing parent of `path` below `root` as a real directory; refuse links.
fn parents(root: &Path, path: &Path) -> Result<(), String> {
    let parent = path.parent().ok_or("staged path has no parent")?;
    let relative = parent
        .strip_prefix(root)
        .map_err(|_| "staged path escapes the job folder")?;
    let mut current = root.to_path_buf();
    for component in relative.components() {
        current.push(component);
        match fs::symlink_metadata(&current) {
            Ok(metadata) if metadata.is_dir() => {}
            Ok(_) => return Err(format!("{} is not a real directory", current.display())),
            Err(error) if error.kind() == io::ErrorKind::NotFound => {
                fs::create_dir(&current).map_err(|error| io_error(&current, error))?
            }
            Err(error) => return Err(io_error(&current, error)),
        }
    }
    Ok(())
}

/// @cc [owner:fontanierh,label:correctness;performance] ephemeral-job-input-writes
/// Job inputs MUST be written completely into fresh read-only files before dispatch, but MUST NOT
/// require a per-file durable flush: these disposable copies never certify results or recovery.
/// Durable leases, frozen result publication and checkout-install journals remain separate authorities.
fn write_new(path: &Path, bytes: &[u8]) -> Result<(), String> {
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o444)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)
        .map_err(|error| io_error(path, error))?;
    file.write_all(bytes).map_err(|error| io_error(path, error))
}

fn set_mode(path: &Path, mode: u32) -> Result<(), String> {
    fs::set_permissions(path, fs::Permissions::from_mode(mode))
        .map_err(|error| io_error(path, error))
}

fn stage_item(
    root: &Path,
    directory: &Path,
    files: &[StoredFile],
    objects: &dyn ObjectSource,
) -> Result<(), StageError> {
    let mut seen = BTreeSet::new();
    for file in files {
        if !seen.insert(file.path.as_str()) {
            return Err(format!("duplicate item member {}", file.path).into());
        }
        let mode = match file.mode {
            0o644 => 0o444,
            0o755 => 0o555,
            other => return Err(format!("item member {} has mode {other:o}", file.path).into()),
        };
        let destination = inside(directory, &file.path)?;
        parents(root, &destination)?;
        let digest = ObjectDigest::from_hex(&file.digest).map_err(|error| error.to_string())?;
        objects
            .clone_object(&digest, &destination)
            .map_err(StageError::Source)?;
        let metadata =
            fs::symlink_metadata(&destination).map_err(|error| io_error(&destination, error))?;
        if !metadata.is_file() || metadata.len() != file.size {
            return Err(format!(
                "item member {} is not the recorded {}-byte file",
                file.path, file.size
            )
            .into());
        }
        set_mode(&destination, mode)?;
    }
    Ok(())
}

/// Every directory below `root` except `output/`, deepest first.
fn staged_directories(root: &Path, scratch: Option<&Path>) -> Result<Vec<PathBuf>, String> {
    let mut found = vec![];
    let mut pending = vec![root.to_path_buf()];
    while let Some(directory) = pending.pop() {
        for entry in fs::read_dir(&directory).map_err(|error| io_error(&directory, error))? {
            let entry = entry.map_err(|error| io_error(&directory, error))?;
            let path = entry.path();
            if path != root.join("output")
                && scratch != Some(path.as_path())
                && entry
                    .file_type()
                    .map_err(|error| io_error(&path, error))?
                    .is_dir()
            {
                pending.push(path);
            }
        }
        found.push(directory);
    }
    found.reverse();
    Ok(found)
}

/// @cc [owner:fontanierh,label:correctness] staged-frozen-inputs
/// Staging MUST create a fresh job folder holding only the unit's declared code and inputs at their
/// exact declared job-relative paths, plus an empty writable `output/`. Code bytes MUST come from the
/// keyed frozen snapshot and match the keyed digests; live sources are never reread. `Bytes` inputs
/// are files and `Item` inputs directories of exactly their recorded members, cloned (never copied)
/// from certified sources with their recorded size and executable bit: pinned CAS objects, checkout
/// descriptors under read custody, or sealed local snapshots. Checkout read custody MUST end after
/// independent job clones are staged, before worker execution; absent optional inputs
/// create nothing. The fixed Blender worker additionally receives one empty private
/// `.blender-runtime/` directory for isolated native startup state. Every other staged
/// file and directory except `output/` MUST be read-only. Unsafe
/// paths, links, shape mismatches and incomplete items MUST fail the staging. An object source's
/// refusal MUST reach the caller as `StageError::Source` with its typed kind and the digest asked
/// for, never flattened or retried by copying; every other failure is `StageError::Staging`. The
/// request MUST carry no install path, locator or source path. See tests/staging.rs.
pub fn stage(
    prepared: &PreparedUnit,
    frozen_code: &SourceSnapshot,
    objects: &dyn ObjectSource,
    job_dir: &Path,
    job_id: &str,
) -> Result<StagedJob, StageError> {
    let job_dir = fresh_job_dir(job_dir)?;
    let staged = stage_into(prepared, frozen_code, objects, &job_dir, job_id);
    if staged.is_err() {
        // Only this call's own fresh folder is removed; nothing else is touched.
        let _ = remove_job(&job_dir);
    }
    staged
}

/// Create the job folder, which must not exist, under the real path of its existing parent.
fn fresh_job_dir(job_dir: &Path) -> Result<PathBuf, String> {
    if !job_dir.is_absolute() {
        return Err("the job folder must be an absolute path".into());
    }
    let parent = job_dir.parent().ok_or("the job folder has no parent")?;
    let parent = parent
        .canonicalize()
        .map_err(|error| io_error(parent, error))?;
    let job_dir = parent.join(job_dir.file_name().ok_or("the job folder has no name")?);
    fs::create_dir(&job_dir).map_err(|error| io_error(&job_dir, error))?;
    Ok(job_dir)
}

fn stage_into(
    prepared: &PreparedUnit,
    frozen_code: &SourceSnapshot,
    objects: &dyn ObjectSource,
    job_dir: &Path,
    job_id: &str,
) -> Result<StagedJob, StageError> {
    let ingredients = prepared.ingredients();
    for (path, digest) in &ingredients.code {
        let Some(SnapshotEntry::File(bytes)) = frozen_code.get(path) else {
            return Err(format!("declared code {path} is not a frozen regular file").into());
        };
        if &sha256(bytes) != digest {
            return Err(format!("declared code {path} changed after keying").into());
        }
        let destination = inside(job_dir, path)?;
        parents(job_dir, &destination)?;
        write_new(&destination, bytes)?;
    }
    for input in prepared.inputs() {
        let name = &input.wire.name;
        let destination = inside(job_dir, &input.wire.path)?;
        let kind = ingredients.input_kinds.get(name);
        match (&input.payload, kind) {
            (InputPayload::Absent, Some(InputKind::File)) => {}
            (InputPayload::Bytes(bytes), Some(InputKind::File)) => {
                parents(job_dir, &destination)?;
                write_new(&destination, bytes)?;
            }
            (InputPayload::NativeCooked(identity), Some(InputKind::Item)) => {
                parents(job_dir, &destination)?;
                fs::create_dir(&destination).map_err(|error| io_error(&destination, error))?;
                write_new(
                    &destination.join("native.json"),
                    &crate::keys::canonical_bytes(identity)?,
                )?;
            }
            (InputPayload::Item { files, .. }, Some(InputKind::Item)) => {
                parents(job_dir, &destination)?;
                fs::create_dir(&destination).map_err(|error| io_error(&destination, error))?;
                stage_item(job_dir, &destination, files, objects)?;
            }
            _ => {
                return Err(format!("input {name} payload does not match its keyed shape").into());
            }
        }
    }
    let output = job_dir.join("output");
    fs::create_dir(&output).map_err(|error| io_error(&output, error))?;
    let runtime_name = match ingredients.worker_version.as_str() {
        crate::launch::BLENDER_JOB_LOOP_VERSION => Some(".blender-runtime"),
        crate::unreal::UNREAL_JOB_LOOP_VERSION => Some(".unreal-runtime"),
        crate::recipe_ops::PYTHON_VERSION
        | crate::recipe_ops::BLENDER_VERSION
        | "atelier-native-tool-job-1" => Some(".recipe-runtime"),
        _ => None,
    };
    let scratch = if let Some(name) = runtime_name {
        let path = job_dir.join(name);
        fs::create_dir(&path).map_err(|error| io_error(&path, error))?;
        set_mode(&path, 0o700)?;
        Some(path)
    } else {
        None
    };
    let evidence = if ingredients.worker_version == crate::unreal::UNREAL_JOB_LOOP_VERSION {
        let path = job_dir.join("evidence");
        fs::create_dir(&path).map_err(|error| io_error(&path, error))?;
        Some(path)
    } else {
        None
    };
    for directory in staged_directories(job_dir, scratch.as_deref())? {
        set_mode(&directory, 0o555)?;
    }
    if let Some(path) = evidence {
        set_mode(&path, 0o700)?;
    }
    let folder = job_dir.to_str().ok_or("the job folder is not UTF-8")?;
    let mut request = prepared.request(job_id, folder);
    // Install paths are checkout locators for B3; the worker never needs them.
    for output in &mut request.outputs {
        output.install_path = None;
    }
    Ok(StagedJob {
        job_dir: job_dir.to_path_buf(),
        request,
    })
}

/// @cc [owner:fontanierh,label:correctness] collected-output-manifest
/// Collection MUST walk the job's `output/` tree without following links, refuse anything but
/// regular files and directories, and require the worker's reported file list to equal the files
/// found. It MUST return every actual file, declared or not (fixed outputs and group members alike),
/// as A4b's `stage_groups` requires, so the result store decides membership; [`fixed_sources`] maps a fixed-only unit's files to their
/// items and refuses any other file. Neither hashes: B2 freezes and hashes the sources once. See
/// tests/staging.rs.
pub fn collect_outputs(
    staged: &StagedJob,
    reported: &[String],
) -> Result<Vec<ActualOutput>, String> {
    let root = staged.output_dir();
    let mut found = BTreeMap::new();
    let mut pending = vec![root.clone()];
    while let Some(directory) = pending.pop() {
        for entry in fs::read_dir(&directory).map_err(|error| io_error(&directory, error))? {
            let entry = entry.map_err(|error| io_error(&directory, error))?;
            let path = entry.path();
            let kind = fs::symlink_metadata(&path)
                .map_err(|error| io_error(&path, error))?
                .file_type();
            let relative = path
                .strip_prefix(&root)
                .map_err(|_| "output escapes output/")?
                .to_str()
                .ok_or("output name is not UTF-8")?
                .to_string();
            if kind.is_dir() {
                pending.push(path);
            } else if kind.is_file() {
                found.insert(relative, path);
            } else {
                return Err(format!("output {relative} is not a regular file"));
            }
        }
    }
    let reported_set: BTreeSet<_> = reported.iter().map(String::as_str).collect();
    if reported_set.len() != reported.len()
        || !reported_set
            .iter()
            .copied()
            .eq(found.keys().map(String::as_str))
    {
        return Err("the worker's reported outputs differ from the files in output/".into());
    }
    Ok(found
        .into_iter()
        .map(|(path, source)| ActualOutput { path, source })
        .collect())
}

/// The B2 fixed-result manifest for a unit without output groups: each actual file keyed by its
/// declaring item. A file no fixed output declares fails; required membership is B2's check.
pub fn fixed_sources(
    prepared: &PreparedUnit,
    actual: &[ActualOutput],
) -> Result<OutputSources, String> {
    let mut sources = OutputSources::new();
    for file in actual {
        let item = prepared
            .ingredients()
            .logical_outputs
            .iter()
            .find(|item| item.files.iter().any(|output| output.path == file.path))
            .ok_or_else(|| format!("output {} is not declared", file.path))?;
        sources.insert((item.id.clone(), file.path.clone()), file.source.clone());
    }
    Ok(sources)
}

/// Remove a job folder that staging created, restoring write permission on the way. Call it only
/// after B2 has staged or refused the outputs: completed results live in the store, not here.
pub fn remove_job(job_dir: &Path) -> Result<(), String> {
    let metadata = fs::symlink_metadata(job_dir).map_err(|error| io_error(job_dir, error))?;
    if !metadata.is_dir() {
        return Err(format!("{} is not a job folder", job_dir.display()));
    }
    let mut pending = vec![job_dir.to_path_buf()];
    while let Some(directory) = pending.pop() {
        set_mode(&directory, 0o755)?;
        for entry in fs::read_dir(&directory).map_err(|error| io_error(&directory, error))? {
            let entry = entry.map_err(|error| io_error(&directory, error))?;
            if entry
                .file_type()
                .map_err(|error| io_error(&entry.path(), error))?
                .is_dir()
            {
                pending.push(entry.path());
            }
        }
    }
    fs::remove_dir_all(job_dir).map_err(|error| io_error(job_dir, error))
}
