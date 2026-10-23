//! Durable retention roots and build sessions (B4). See DESIGN section 8.
//!
//! A root records which results a build used, as a map from the unit's scheduling label to
//! that unit's last result key. Each entry keeps the provenance of the session that wrote it.
//! Roots never participate in cache identity, and nothing here deletes payloads, result
//! records or leases; B5 owns traversal and object cleanup.
use crate::leases::{
    LEASE_VERSION, LeaseRecord, LeaseStore, Liveness, MetadataGuard, ProcessIdentity, sync_dir,
};
use crate::results::ResultEnvelope;
use crate::schema::{Declaration, Provenance};
use crate::store::ObjectDigest;
use crate::validate::ValidatedDeclaration;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::fs::{self, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

pub const ROOT_VERSION: u32 = 1;
pub const SESSION_VERSION: u32 = 1;
/// Store-level record of initialized projects, kept beside `roots/`.
pub const PROJECTS_VERSION: u32 = 1;
/// Store-level recent-use and first-observed record, kept beside `roots/`.
pub const USAGE_VERSION: u32 = 1;
/// DESIGN section 8 keeps the three most recent releases.
pub const RELEASES_KEPT: usize = 3;
static NEXT: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RootKind {
    Main,
    Worktree { id: String },
    Release { sequence: u64, label: String },
    Pin { id: String },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RootEntry {
    pub key: String,
    /// The session that last wrote this unit, never the latest session of the whole root.
    pub provenance: Provenance,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RootRecord {
    pub version: u32,
    pub project: String,
    pub kind: RootKind,
    pub entries: BTreeMap<String, RootEntry>,
    /// Describes the session that last replaced or merged this root, not every entry.
    pub provenance: Provenance,
}

/// Every unit of one validated declaration. Only the full validation output can construct it, and
/// its dependency order must cover the declaration's units exactly, so a filtered or partial view
/// cannot ask a commit to prune results for units it never saw.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DeclaredRoster {
    units: BTreeSet<String>,
    digest: String,
}

impl DeclaredRoster {
    pub fn from_validated(
        declaration: &Declaration,
        validated: &ValidatedDeclaration,
    ) -> Result<Self, RootError> {
        let declared: BTreeSet<String> = declaration
            .units
            .iter()
            .map(|unit| unit.id.clone())
            .collect();
        let ordered: BTreeSet<String> = validated.order.iter().cloned().collect();
        if declared.is_empty() || declared != ordered {
            return Err(invalid(
                "validated order must cover exactly the declaration's units",
            ));
        }
        let mut hasher = Sha256::new();
        for unit in &validated.order {
            hasher.update(unit.as_bytes());
            hasher.update([0u8]);
        }
        Ok(Self {
            units: declared,
            digest: format!("{:x}", hasher.finalize()),
        })
    }
    pub fn contains(&self, unit: &str) -> bool {
        self.units.contains(unit)
    }
    pub fn units(&self) -> &BTreeSet<String> {
        &self.units
    }
    /// Identity of the validated unit roster this commit pruned against.
    pub fn digest(&self) -> &str {
        &self.digest
    }
}

#[derive(Debug)]
pub enum RootError {
    Invalid(String),
    /// A root or session journal could not be read completely; callers must retain, never delete.
    Damaged(String),
    Conflict(String),
    Io(io::Error),
}
impl fmt::Display for RootError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Invalid(reason) => write!(formatter, "invalid root metadata: {reason}"),
            Self::Damaged(reason) => write!(formatter, "damaged root metadata: {reason}"),
            Self::Conflict(reason) => write!(formatter, "root conflict: {reason}"),
            Self::Io(error) => error.fmt(formatter),
        }
    }
}
impl std::error::Error for RootError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io(error) => Some(error),
            _ => None,
        }
    }
}
impl From<io::Error> for RootError {
    fn from(value: io::Error) -> Self {
        Self::Io(value)
    }
}

/// Result keys still referenced by any readable root or session, plus every record that could
/// not be read. A non-empty damage list means GC must retain, never delete.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct RetentionView {
    pub keys: BTreeSet<String>,
    pub damaged: Vec<String>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct SessionInfo {
    pub id: String,
    pub kind: RootKind,
    pub provenance: Provenance,
    pub owner: ProcessIdentity,
    pub entries: Vec<(String, String)>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CommitStep {
    JournalRead,
    RootTemporary,
    RootReplaced,
    DirectorySynced,
    SessionRemoved,
}

#[derive(Clone)]
pub struct RootStore {
    root: PathBuf,
    project: String,
    leases: LeaseStore,
    clock: Arc<dyn Clock>,
}

impl fmt::Debug for RootStore {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("RootStore")
            .field("root", &self.root)
            .field("project", &self.project)
            .finish_non_exhaustive()
    }
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct SessionHeader {
    version: u32,
    project: String,
    kind: RootKind,
    provenance: Provenance,
    owner: ProcessIdentity,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct SessionEntry {
    unit: String,
    key: String,
    /// The round-up UTC day this key was last used. Absent in older journals, which read as
    /// unknown age and are retained.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    use_bucket: Option<UseBucket>,
}

/// One build's durable retention. Dropping it without commit or abandon keeps the journal, and
/// with it every key used so far, until an explicit release.
#[derive(Debug)]
pub struct BuildSession {
    store: RootStore,
    kind: RootKind,
    provenance: Provenance,
    id: String,
    journal: PathBuf,
}

/// One initialized project, kept in the store-level registry beside `roots/`.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ProjectRecord {
    /// Unix seconds. Informational only; never part of cache identity.
    created: u64,
    /// Binds the record to this exact project name, so a hand-edited registry cannot move it.
    digest: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ProjectRegistry {
    version: u32,
    projects: BTreeMap<String, ProjectRecord>,
}

fn project_digest(project: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(b"atelier.build-v2.project\0");
    hasher.update(project.as_bytes());
    format!("{:x}", hasher.finalize())
}

fn registry_path(root: &Path) -> PathBuf {
    root.join("meta").join("projects.json")
}

/// Reads the store-level registry. `None` means the store has never initialized a project.
fn read_registry(root: &Path) -> Result<Option<ProjectRegistry>, RootError> {
    let bytes = match fs::read(registry_path(root)) {
        Ok(bytes) => bytes,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(damaged(format!("projects registry is unreadable: {error}"))),
    };
    let registry: ProjectRegistry = serde_json::from_slice(&bytes)
        .map_err(|error| damaged(format!("projects registry is unreadable: {error}")))?;
    if registry.version != PROJECTS_VERSION {
        return Err(damaged(format!(
            "unsupported projects registry version {}",
            registry.version
        )));
    }
    for (name, record) in &registry.projects {
        if !valid_segment(name) || record.digest != project_digest(name) {
            return Err(damaged(format!(
                "projects registry entry {name} is invalid"
            )));
        }
    }
    Ok(Some(registry))
}

fn unix_seconds() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0)
}

/// A UTC day on which a result or an object was last observed, rounded **up**. A coarse bucket
/// that never overstates age is safe for retention; an older bucket would not be.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct UseBucket(String);

impl UseBucket {
    /// The UTC day of `now`, rounded up: anything after midnight is dated the next day.
    pub fn ceil_day(now: SystemTime) -> Result<Self, RootError> {
        let elapsed = now
            .duration_since(UNIX_EPOCH)
            .map_err(|error| invalid(format!("clock is before the unix epoch: {error}")))?;
        let seconds = elapsed.as_secs();
        // Sub-second precision matters: exactly midnight stays on that day, midnight plus one
        // nanosecond is the next day. Truncating first would overstate age by a day.
        let round_up = elapsed.subsec_nanos() != 0 || seconds % 86_400 != 0;
        let days = seconds / 86_400 + u64::from(round_up);
        if days > i64::MAX as u64 {
            return Err(invalid("clock is outside the supported range"));
        }
        let (year, month, day) = civil_from_days(days as i64);
        if !(1..=9999).contains(&year) {
            return Err(invalid("clock is outside the supported range"));
        }
        Ok(Self(format!("{year:04}-{month:02}-{day:02}")))
    }

    /// Parses a strict `YYYY-MM-DD` real calendar date.
    pub fn parse(value: &str) -> Result<Self, RootError> {
        let bytes = value.as_bytes();
        let digits = |range: std::ops::Range<usize>| {
            bytes
                .get(range)
                .is_some_and(|part| part.iter().all(u8::is_ascii_digit))
        };
        if bytes.len() != 10
            || bytes[4] != b'-'
            || bytes[7] != b'-'
            || !digits(0..4)
            || !digits(5..7)
            || !digits(8..10)
        {
            return Err(invalid("use bucket must be YYYY-MM-DD"));
        }
        let year: i64 = value[0..4]
            .parse()
            .map_err(|_| invalid("bad use bucket year"))?;
        let month: u32 = value[5..7]
            .parse()
            .map_err(|_| invalid("bad use bucket month"))?;
        let day: u32 = value[8..10]
            .parse()
            .map_err(|_| invalid("bad use bucket day"))?;
        if !(1..=12).contains(&month)
            || day < 1
            || day > days_in_month(year, month)
            || !(1..=9999).contains(&year)
        {
            return Err(invalid("use bucket is not a real calendar date"));
        }
        Ok(Self(value.to_string()))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl fmt::Display for UseBucket {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        self.0.fmt(formatter)
    }
}

impl Serialize for UseBucket {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.serialize_str(&self.0)
    }
}

impl<'de> Deserialize<'de> for UseBucket {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let value = String::deserialize(deserializer)?;
        Self::parse(&value).map_err(serde::de::Error::custom)
    }
}

/// The clock a store reads for coarse use buckets. Real UTC in production; fixed or steppable
/// in tests, so a session that runs past midnight never records an older age.
pub trait Clock: Send + Sync {
    fn now(&self) -> SystemTime;
}

#[derive(Debug, Default)]
pub struct UtcClock;

impl Clock for UtcClock {
    fn now(&self) -> SystemTime {
        SystemTime::now()
    }
}

fn days_in_month(year: i64, month: u32) -> u32 {
    match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 if (year % 4 == 0 && year % 100 != 0) || year % 400 == 0 => 29,
        2 => 28,
        _ => 0,
    }
}

/// Days since 1970-01-01 to a proleptic Gregorian civil date (Howard Hinnant's algorithm).
fn civil_from_days(days: i64) -> (i64, u32, u32) {
    let shifted = days + 719_468;
    let era = if shifted >= 0 {
        shifted
    } else {
        shifted - 146_096
    } / 146_097;
    let day_of_era = shifted - era * 146_097;
    let year_of_era =
        (day_of_era - day_of_era / 1_460 + day_of_era / 36_524 - day_of_era / 146_096) / 365;
    let year = year_of_era + era * 400;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let mp = (5 * day_of_year + 2) / 153;
    let day = (day_of_year - (153 * mp + 2) / 5 + 1) as u32;
    let month = if mp < 10 { mp + 3 } else { mp - 9 } as u32;
    (year + i64::from(month <= 2), month, day)
}

/// The store-level recent-use record: result key to newest bucket, digest to first-observed day.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct UsageRecord {
    version: u32,
    #[serde(default)]
    results: BTreeMap<String, UseBucket>,
    /// Keys with an unknown-age observation, floored at the day it was seen. Removing that
    /// journal must not let an older dated entry make the key look known again.
    #[serde(default)]
    unknown: BTreeMap<String, UseBucket>,
    #[serde(default)]
    observed: BTreeMap<String, UseBucket>,
}

/// Read-only view of recent use. A key absent from `results` has **unknown** age and must be
/// retained, and a non-empty `damaged` list obliges the caller to refuse destructive work.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct UsageView {
    pub results: BTreeMap<String, UseBucket>,
    /// Keys whose newest observation has an unknown time, floored at the day it was recorded.
    pub unknown: BTreeMap<String, UseBucket>,
    pub observed: BTreeMap<String, UseBucket>,
    pub damaged: Vec<String>,
}

/// Read-only retention across every project in the store, read under the caller's one guard.
#[derive(Clone, Debug, Default)]
pub struct AllProjectsRetention {
    pub projects: BTreeMap<String, RetentionView>,
    pub damaged: Vec<String>,
}

/// What open journals say about recent use, and what could not be read. An entry without a
/// bucket is an unknown observation: it invalidates any stored bucket for that key.
#[derive(Default)]
struct JournalBuckets {
    buckets: Vec<(String, UseBucket)>,
    unknowns: Vec<String>,
    damaged: Vec<String>,
}

fn usage_path(root: &Path) -> PathBuf {
    root.join("usage.json")
}

fn valid_digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn read_usage(root: &Path) -> Result<Option<UsageRecord>, RootError> {
    let bytes = match fs::read(usage_path(root)) {
        Ok(bytes) => bytes,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(damaged(format!("usage record is unreadable: {error}"))),
    };
    let usage: UsageRecord = serde_json::from_slice(&bytes)
        .map_err(|error| damaged(format!("usage record is unreadable: {error}")))?;
    if usage.version != USAGE_VERSION {
        return Err(damaged(format!(
            "unsupported usage record version {}",
            usage.version
        )));
    }
    for key in usage.results.keys() {
        if !valid_key(key) {
            return Err(damaged("usage record has an invalid result key"));
        }
    }
    for key in usage.unknown.keys() {
        if !valid_key(key) {
            return Err(damaged("usage record has an invalid unknown-age key"));
        }
    }
    for digest in usage.observed.keys() {
        if !valid_digest(digest) {
            return Err(damaged("usage record has an invalid object digest"));
        }
    }
    Ok(Some(usage))
}

fn invalid(message: impl Into<String>) -> RootError {
    RootError::Invalid(message.into())
}
fn damaged(message: impl Into<String>) -> RootError {
    RootError::Damaged(message.into())
}

fn valid_segment(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && !value.starts_with('.')
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-'))
}

fn valid_label(value: &str) -> bool {
    !value.is_empty() && value.len() <= 512 && !value.chars().any(char::is_control)
}

fn valid_key(value: &str) -> bool {
    ObjectDigest::from_hex(value).is_ok()
}

fn valid_kind(kind: &RootKind) -> bool {
    match kind {
        RootKind::Main => true,
        RootKind::Worktree { id } | RootKind::Pin { id } => valid_segment(id),
        RootKind::Release { label, .. } => valid_label(label),
    }
}

/// Identity inside one project: a release is its sequence, never its human label.
fn same_target(stored: &RootKind, requested: &RootKind) -> bool {
    match (stored, requested) {
        (RootKind::Main, RootKind::Main) => true,
        (RootKind::Worktree { id: left }, RootKind::Worktree { id: right }) => left == right,
        (
            RootKind::Release { sequence: left, .. },
            RootKind::Release {
                sequence: right, ..
            },
        ) => left == right,
        (RootKind::Pin { id: left }, RootKind::Pin { id: right }) => left == right,
        _ => false,
    }
}

fn checked(kind: &RootKind) -> Result<(), RootError> {
    if valid_kind(kind) {
        Ok(())
    } else {
        Err(invalid("invalid target name or label"))
    }
}

fn checked_entry(unit: &str, key: &str) -> Result<(), RootError> {
    if !valid_label(unit) {
        return Err(invalid(
            "unit label must be non-empty without control characters",
        ));
    }
    if !valid_key(key) {
        return Err(invalid(
            "result key must be 64 lowercase SHA-256 hex characters",
        ));
    }
    Ok(())
}

fn validate_record(record: &RootRecord, project: &str) -> Result<(), String> {
    if record.version != ROOT_VERSION || record.project != project {
        return Err("unsupported or foreign root record".into());
    }
    checked(&record.kind).map_err(|error| error.to_string())?;
    for (unit, entry) in &record.entries {
        checked_entry(unit, &entry.key).map_err(|error| error.to_string())?;
    }
    Ok(())
}

/// Frozen-root identity: the unit-to-key map, never the provenance of the retry.
fn entry_keys(entries: &BTreeMap<String, RootEntry>) -> BTreeMap<&str, &str> {
    entries
        .iter()
        .map(|(unit, entry)| (unit.as_str(), entry.key.as_str()))
        .collect()
}

fn sort_key(kind: &RootKind) -> (u8, String) {
    match kind {
        RootKind::Main => (0, String::new()),
        RootKind::Worktree { id } => (1, id.clone()),
        RootKind::Release { sequence, .. } => (2, format!("{sequence:020}")),
        RootKind::Pin { id } => (3, id.clone()),
    }
}

/// The target a record file must hold, derived from its location.
fn kind_at(path: &Path) -> Result<RootKind, RootError> {
    let name = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or_default();
    let folder = path
        .parent()
        .and_then(|value| value.file_name())
        .and_then(|value| value.to_str())
        .unwrap_or_default();
    if name == "main.json" {
        return Ok(RootKind::Main);
    }
    let stem = name
        .strip_suffix(".json")
        .filter(|stem| !stem.is_empty())
        .ok_or_else(|| damaged(format!("{} is not a root record name", path.display())))?;
    match folder {
        "worktree" => Ok(RootKind::Worktree { id: stem.into() }),
        "pin" => Ok(RootKind::Pin { id: stem.into() }),
        "release" => {
            let sequence: u64 = stem
                .parse()
                .map_err(|_| damaged(format!("{} is not a release sequence", path.display())))?;
            if stem != sequence.to_string() {
                return Err(damaged(format!(
                    "{} is not a canonical release sequence",
                    path.display()
                )));
            }
            Ok(RootKind::Release {
                sequence,
                label: String::new(),
            })
        }
        _ => Err(damaged(format!(
            "{} is not in a root folder",
            path.display()
        ))),
    }
}

fn write_temp(directory: &Path, bytes: &[u8], suffix: &str) -> io::Result<PathBuf> {
    loop {
        let serial = NEXT.fetch_add(1, Ordering::Relaxed);
        let path = directory.join(format!("{}-{serial}.{suffix}", std::process::id()));
        let mut options = OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        match options.open(&path) {
            Ok(mut file) => {
                file.write_all(bytes)?;
                file.sync_all()?;
                return Ok(path);
            }
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(error),
        }
    }
}

fn write_record(
    path: &Path,
    temporary_directory: &Path,
    record: &RootRecord,
    observe: &mut impl FnMut(CommitStep) -> io::Result<()>,
) -> Result<(), RootError> {
    let bytes = serde_json::to_vec(record).map_err(|error| invalid(error.to_string()))?;
    let temporary = write_temp(temporary_directory, &bytes, "tmp")?;
    if let Err(error) = observe(CommitStep::RootTemporary) {
        let _ = fs::remove_file(&temporary);
        return Err(error.into());
    }
    if let Err(error) = fs::rename(&temporary, path) {
        let _ = fs::remove_file(&temporary);
        return Err(error.into());
    }
    observe(CommitStep::RootReplaced)?;
    sync_dir(path.parent().expect("root record has a parent"))?;
    observe(CommitStep::DirectorySynced)?;
    Ok(())
}

/// Temp file, fsync, rename, then both directories' fsync: one small record, never in place.
fn write_atomic_private(directory: &Path, target: &Path, bytes: &[u8]) -> Result<(), RootError> {
    let serial = NEXT.fetch_add(1, Ordering::Relaxed);
    let name = target
        .file_name()
        .map(|name| name.to_string_lossy().to_string())
        .unwrap_or_else(|| "record".to_string());
    let temporary = directory.join(format!(".{name}-{}-{serial}.tmp", std::process::id()));
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(&temporary)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    drop(file);
    if let Err(error) = fs::rename(&temporary, target) {
        let _ = fs::remove_file(&temporary);
        return Err(error.into());
    }
    sync_dir(directory)?;
    if let Some(parent) = target.parent() {
        if parent != directory {
            sync_dir(parent)?;
        }
    }
    Ok(())
}

/// Every key one project's readable roots and journals name, plus what could not be read.
fn retention_of_project(base: &Path) -> Result<RetentionView, RootError> {
    let mut view = RetentionView::default();
    let project_name = base
        .file_name()
        .map(|name| name.to_string_lossy().to_string())
        .unwrap_or_default();
    for (folder, extension) in [
        ("worktree", "json"),
        ("release", "json"),
        ("pin", "json"),
        ("session", "jsonl"),
    ] {
        let Ok(entries) = fs::read_dir(base.join(folder)) else {
            view.damaged.push(base.join(folder).display().to_string());
            continue;
        };
        for entry in entries {
            let entry = entry?;
            let path = entry.path();
            if !entry.file_type()?.is_file()
                || path.extension().is_none_or(|value| value != extension)
            {
                view.damaged.push(path.display().to_string());
                continue;
            }
            if folder == "session" {
                if retention_of_session(&path, &mut view.keys) {
                    view.damaged.push(path.display().to_string());
                }
                continue;
            }
            match fs::read(&path)
                .map_err(|error| error.to_string())
                .and_then(|bytes| {
                    serde_json::from_slice::<RootRecord>(&bytes).map_err(|error| error.to_string())
                }) {
                Ok(record) if record.version == ROOT_VERSION && record.project == project_name => {
                    let mut invalid = false;
                    for entry in record.entries.values() {
                        if valid_key(&entry.key) {
                            view.keys.insert(entry.key.clone());
                        } else {
                            invalid = true;
                        }
                    }
                    if invalid {
                        view.damaged.push(path.display().to_string());
                    }
                }
                _ => view.damaged.push(path.display().to_string()),
            }
        }
    }
    let main = base.join("main.json");
    match fs::symlink_metadata(&main) {
        Ok(_) => match fs::read(&main)
            .map_err(|error| error.to_string())
            .and_then(|bytes| {
                serde_json::from_slice::<RootRecord>(&bytes).map_err(|error| error.to_string())
            }) {
            Ok(record) if record.version == ROOT_VERSION && record.project == project_name => {
                let mut invalid = false;
                for entry in record.entries.values() {
                    if valid_key(&entry.key) {
                        view.keys.insert(entry.key.clone());
                    } else {
                        invalid = true;
                    }
                }
                if invalid {
                    view.damaged.push(main.display().to_string());
                }
            }
            _ => view.damaged.push(main.display().to_string()),
        },
        Err(error) if error.kind() == io::ErrorKind::NotFound => {}
        Err(_) => view.damaged.push(main.display().to_string()),
    }
    match fs::read_dir(base) {
        Ok(entries) => {
            for entry in entries {
                let Ok(entry) = entry else {
                    view.damaged.push(base.display().to_string());
                    continue;
                };
                let name = entry.file_name();
                let name = name.to_string_lossy();
                if !["worktree", "release", "pin", "session", "tmp", "main.json"]
                    .contains(&name.as_ref())
                {
                    view.damaged.push(entry.path().display().to_string());
                }
            }
        }
        Err(_) => view.damaged.push(base.display().to_string()),
    }
    Ok(view)
}

fn parse_journal(
    path: &Path,
    project: &str,
    kind: Option<&RootKind>,
) -> Result<(SessionHeader, Vec<SessionEntry>), RootError> {
    let text = String::from_utf8(fs::read(path)?)
        .map_err(|error| damaged(format!("session is not UTF-8: {error}")))?;
    let mut parts: Vec<&str> = text.split('\n').collect();
    if parts.last() != Some(&"") {
        return Err(damaged("session journal has an unterminated last record"));
    }
    parts.pop();
    let Some(header) = parts.first() else {
        return Err(damaged("session journal is empty"));
    };
    let header: SessionHeader = serde_json::from_str(header)
        .map_err(|error| damaged(format!("session header: {error}")))?;
    if header.version != SESSION_VERSION || header.project != project {
        return Err(damaged("session header does not match this store"));
    }
    if let Some(kind) = kind {
        if !same_target(&header.kind, kind) {
            return Err(damaged("session header does not match its target"));
        }
    }
    let mut entries = vec![];
    for (index, line) in parts.iter().enumerate().skip(1) {
        if line.is_empty() {
            return Err(damaged(format!(
                "blank session record at line {}",
                index + 1
            )));
        }
        let entry: SessionEntry = serde_json::from_str(line)
            .map_err(|error| damaged(format!("session record {}: {error}", index + 1)))?;
        checked_entry(&entry.unit, &entry.key).map_err(|error| damaged(error.to_string()))?;
        entries.push(entry);
    }
    Ok((header, entries))
}

fn retention_of_session(path: &Path, keys: &mut BTreeSet<String>) -> bool {
    let Ok(bytes) = fs::read(path) else {
        return true;
    };
    let Ok(text) = String::from_utf8(bytes) else {
        return true;
    };
    let mut parts: Vec<&str> = text.split('\n').collect();
    let mut damaged = false;
    if parts.last() == Some(&"") {
        parts.pop();
    } else {
        damaged = true;
    }
    let header = parts.first().copied().unwrap_or_default();
    if serde_json::from_str::<SessionHeader>(header).is_err() {
        damaged = true;
    }
    for line in parts.iter().skip(1) {
        match serde_json::from_str::<SessionEntry>(line) {
            Ok(entry) if valid_key(&entry.key) => {
                keys.insert(entry.key);
            }
            _ => damaged = true,
        }
    }
    damaged
}

impl RootStore {
    /// @cc [owner:fontanierh,label:correctness] build-v2-root-store
    /// Opening MUST require an existing trusted store root, refuse a missing one, and name one
    /// explicit project. Initialization MUST run under the shared metadata mutex and MUST fsync
    /// every created ancestor before any publication can root a result. An initialized project is
    /// never recreated: the store records every initialized project beside `roots/`, so a fresh
    /// open after the project directory, all of `roots/` or that record is lost is damage rather
    /// than a silent empty project. Readers MUST be callable with the caller's already-held guard
    /// so GC can read retention, leases and decide deletions under one lock hold. See tests/roots.rs
    /// `missing_store_root_is_refused`, `reopening_a_project_with_missing_metadata_is_damage`,
    /// `a_fresh_open_of_a_deleted_project_is_damage`,
    /// `a_fresh_open_after_roots_is_deleted_is_damage`,
    /// `a_missing_registry_with_roots_present_is_damage`,
    /// `a_first_open_registers_the_project`,
    /// `retention_is_readable_under_the_callers_guard` and
    /// `a_hit_release_is_visible_to_a_guarded_gc_read`.
    pub fn open(
        store_root: impl AsRef<Path>,
        project: impl Into<String>,
    ) -> Result<Self, RootError> {
        Self::open_with_clock(store_root, project, Arc::new(UtcClock))
    }

    /// The same contract with an injected clock, for tests and deterministic replay.
    pub fn open_with_clock(
        store_root: impl AsRef<Path>,
        project: impl Into<String>,
        clock: Arc<dyn Clock>,
    ) -> Result<Self, RootError> {
        Self::observe_project(store_root, project, clock, true)
    }

    /// Opens a project that MUST already be initialized. Never creates a store, registry or
    /// project directory; a missing one is damage. Read-only apart from the observation itself.
    pub fn open_existing(
        store_root: impl AsRef<Path>,
        project: impl Into<String>,
    ) -> Result<Self, RootError> {
        Self::open_existing_with_clock(store_root, project, Arc::new(UtcClock))
    }

    pub fn open_existing_with_clock(
        store_root: impl AsRef<Path>,
        project: impl Into<String>,
        clock: Arc<dyn Clock>,
    ) -> Result<Self, RootError> {
        Self::observe_project(store_root, project, clock, false)
    }

    fn observe_project(
        store_root: impl AsRef<Path>,
        project: impl Into<String>,
        clock: Arc<dyn Clock>,
        create: bool,
    ) -> Result<Self, RootError> {
        let project = project.into();
        if !valid_segment(&project) {
            return Err(invalid("project name must be a safe single path segment"));
        }
        let root = store_root.as_ref();
        if !root.is_dir() {
            return Err(invalid("store root does not exist"));
        }
        let root = root.canonicalize()?;
        if !fs::symlink_metadata(&root)?.is_dir() {
            return Err(invalid("store root is not a real directory"));
        }
        if !create {
            // Reads create nothing: every path a store open would create must already exist, so
            // an uninitialized or partly damaged store stays byte-identical on refusal.
            let registry = read_registry(&root)?;
            if !registry
                .as_ref()
                .is_some_and(|registry| registry.projects.contains_key(&project))
            {
                return Err(damaged(format!(
                    "project {project} has no initialized metadata"
                )));
            }
            for name in ["leases", "staging"] {
                let path = root.join(name);
                match fs::symlink_metadata(&path) {
                    Ok(metadata) if metadata.is_dir() => {}
                    _ => {
                        return Err(damaged(format!(
                            "missing metadata directory {}",
                            path.display()
                        )));
                    }
                }
            }
            let lock = root.join("metadata.lock");
            match fs::symlink_metadata(&lock) {
                Ok(metadata) if metadata.is_file() => {}
                _ => {
                    return Err(damaged(format!(
                        "missing metadata mutex {}",
                        lock.display()
                    )));
                }
            }
        }
        let leases = LeaseStore::open(&root)?;
        let store = Self {
            root,
            project,
            leases,
            clock,
        };
        // Initialization and reopen observation share the metadata mutex with every reader.
        let _guard = store.leases.lock()?;
        let roots = store.root.join("roots");
        let base = store.project_dir();
        let roots_present = match fs::symlink_metadata(&roots) {
            Ok(metadata) if metadata.is_dir() => true,
            Ok(_) => return Err(invalid("roots metadata is not a directory")),
            Err(error) if error.kind() == io::ErrorKind::NotFound => false,
            Err(error) => return Err(error.into()),
        };
        let base_present = match fs::symlink_metadata(&base) {
            Ok(metadata) if metadata.is_dir() => true,
            Ok(_) => return Err(invalid("project metadata is not a directory")),
            Err(error) if error.kind() == io::ErrorKind::NotFound => false,
            Err(error) => return Err(error.into()),
        };
        let registry = read_registry(&store.root)?;
        if let Some(registry) = registry.as_ref() {
            if !roots_present {
                return Err(damaged(
                    "projects registry exists but roots metadata is missing",
                ));
            }
            let registered = registry.projects.contains_key(&store.project);
            if registered && !base_present {
                return Err(damaged(format!(
                    "initialized project {} lost its roots metadata",
                    store.project
                )));
            }
            if !registered && base_present {
                return Err(damaged(format!(
                    "project {} has roots metadata but is not registered",
                    store.project
                )));
            }
            if registered {
                for kind in ["worktree", "release", "pin", "session", "tmp"] {
                    let path = base.join(kind);
                    match fs::symlink_metadata(&path) {
                        Ok(metadata) if metadata.is_dir() => {}
                        _ => {
                            return Err(damaged(format!(
                                "missing metadata directory {}",
                                path.display()
                            )));
                        }
                    }
                }
                return Ok(store);
            }
        } else if roots_present {
            return Err(damaged("roots metadata exists without a projects registry"));
        }
        if !create {
            return Err(damaged(format!(
                "project {} has no initialized metadata",
                store.project
            )));
        }
        // Genuine first use of this project: create its tree, then record it durably.
        if !roots_present {
            fs::create_dir(&roots)?;
            sync_dir(&store.root)?;
        }
        fs::create_dir(&base)?;
        sync_dir(&roots)?;
        for kind in ["worktree", "release", "pin", "session", "tmp"] {
            fs::create_dir(base.join(kind))?;
        }
        sync_dir(&base)?;
        let mut registry = registry.unwrap_or(ProjectRegistry {
            version: PROJECTS_VERSION,
            projects: BTreeMap::new(),
        });
        registry.projects.insert(
            store.project.clone(),
            ProjectRecord {
                created: unix_seconds(),
                digest: project_digest(&store.project),
            },
        );
        store.write_registry(&registry)?;
        Ok(store)
    }

    pub fn project(&self) -> &str {
        &self.project
    }

    /// The same store-root mutex B2 and B5 must hold.
    pub fn leases(&self) -> &LeaseStore {
        &self.leases
    }

    fn project_dir(&self) -> PathBuf {
        self.root.join("roots").join(&self.project)
    }

    /// Publishes the store-level registry under the caller's metadata guard: temp file, fsync,
    /// rename, then the directory fsync, so a registered project is never silently recreated.
    fn write_registry(&self, registry: &ProjectRegistry) -> Result<(), RootError> {
        let meta = self.root.join("meta");
        let created = match fs::create_dir(&meta) {
            Ok(()) => {
                sync_dir(&self.root)?;
                true
            }
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => false,
            Err(error) => return Err(error.into()),
        };
        if !fs::symlink_metadata(&meta)?.is_dir() {
            return Err(invalid(
                "projects registry directory is not a real directory",
            ));
        }
        let bytes = serde_json::to_vec(registry).map_err(|error| invalid(error.to_string()))?;
        write_atomic_private(&meta, &registry_path(&self.root), &bytes)?;
        if created {
            sync_dir(&self.root)?;
        }
        Ok(())
    }

    fn write_usage(&self, usage: &UsageRecord) -> Result<(), RootError> {
        let bytes = serde_json::to_vec(usage).map_err(|error| invalid(error.to_string()))?;
        write_atomic_private(&self.root, &usage_path(&self.root), &bytes)
    }

    /// @cc [owner:fontanierh,label:correctness] build-v2-root-usage
    /// Recent use is coarse, advisory and never a cache-identity input. A session entry MAY carry
    /// a round-up UTC day, written inside the append that already fsyncs; nothing writes per hit.
    /// Folding to `usage.json` MUST happen only at durable boundaries (commit, abandon, dead
    /// session release, snapshot, drop root) and MUST be coalesced to one write, keeping the newest
    /// bucket per result so a clock rollback never ages a result. A result with no bucket, a legacy
    /// entry without the field, an unreadable journal or a damaged record has **unknown** age and
    /// MUST be retained. An unknown observation is persisted as a floor, so removing the journal
    /// that recorded it never lets an older dated entry make the key look known again; only a
    /// dated use whose round-up day is strictly greater than the floor clears it. The fold MUST
    /// fail closed while any scanned journal is damaged, so no caller unlinks after a partial fold.
    /// `UsageView.damaged` and `AllProjectsRetention.damaged` are part of the
    /// answer, and a caller MUST refuse destructive work while either is non-empty rather than
    /// treat a partial view as complete. First-observed digests are write-once and set only by an
    /// explicit call, never from payload metadata. Forgetting is persisted before any unlink, so a
    /// crash leaves unknown age, which retains. `usage_locked`, `open_existing`, `open_existing_with_clock`
    /// and `all_project_retention_locked` MUST NOT create, fold or rewrite anything. See
    /// tests/roots.rs `a_use_bucket_rounds_the_utc_day_up`,
    /// `an_unknown_marker_survives_the_journal_that_created_it`, `usage_keeps_the_newest_bucket_on_rollback`,
    /// `a_legacy_journal_entry_has_unknown_age`, `usage_is_folded_once_per_commit_not_per_append`,
    /// `the_usage_readers_and_open_existing_write_nothing`, `usage_damage_is_visible_to_the_caller`,
    /// `observe_objects_is_write_once`, `forgetting_usage_is_persisted_before_any_unlink`,
    /// `a_dead_sessions_recent_use_survives_its_release`, `the_all_project_reader_sees_every_project`
    /// and `the_usage_readers_refuse_a_foreign_guard`.
    pub fn usage_locked(&self, guard: &MetadataGuard) -> Result<UsageView, RootError> {
        self.check_guard(guard)?;
        let mut view = UsageView::default();
        match read_usage(&self.root) {
            Ok(Some(usage)) => {
                view.results = usage.results;
                view.unknown = usage.unknown;
                view.observed = usage.observed;
            }
            Ok(None) => {}
            Err(error) => {
                view.damaged
                    .push(usage_path(&self.root).display().to_string());
                view.damaged.push(error.to_string());
            }
        }
        let scan = self.journal_buckets();
        view.damaged.extend(scan.damaged);
        let today = UseBucket::ceil_day(self.clock.now())?;
        for (key, bucket) in scan.buckets {
            if let Some(floor) = view.unknown.get(&key) {
                if bucket <= *floor {
                    // An older dated entry cannot make a key with an unknown observation known.
                    view.results.remove(&key);
                    continue;
                }
                view.unknown.remove(&key);
            }
            let newer = view
                .results
                .get(&key)
                .is_none_or(|current| *current < bucket);
            if newer {
                view.results.insert(key, bucket);
            }
        }
        // An entry that used a key at an unknown time invalidates any stored bucket and leaves a
        // floor, so dropping that journal later cannot resurrect an older dated bucket.
        for key in scan.unknowns {
            view.unknown
                .entry(key.clone())
                .or_insert_with(|| today.clone());
            view.results.remove(&key);
        }
        Ok(view)
    }

    /// Records the first observation of each object digest. Write-once: an existing entry is
    /// never refreshed, and this is the only way an orphan gets a grace date.
    pub fn observe_objects_locked(
        &self,
        guard: &MetadataGuard,
        objects: &BTreeSet<ObjectDigest>,
    ) -> Result<(), RootError> {
        self.check_guard(guard)?;
        if objects.is_empty() {
            return Ok(());
        }
        let mut usage = self.usage_record()?;
        let bucket = UseBucket::ceil_day(self.clock.now())?;
        let mut changed = false;
        for digest in objects {
            let key = digest.as_hex().to_string();
            if !usage.observed.contains_key(&key) {
                usage.observed.insert(key, bucket.clone());
                changed = true;
            }
        }
        if changed {
            self.write_usage(&usage)?;
        }
        Ok(())
    }

    /// Forgets result and object age before the caller unlinks them. One coalesced write; a crash
    /// after this call leaves unknown age, which retains rather than deletes.
    pub fn forget_usage_locked(
        &self,
        guard: &MetadataGuard,
        results: &BTreeSet<String>,
        objects: &BTreeSet<ObjectDigest>,
    ) -> Result<(), RootError> {
        self.check_guard(guard)?;
        let Some(mut usage) = read_usage(&self.root)? else {
            return Ok(());
        };
        let mut changed = false;
        for key in results {
            changed |= usage.results.remove(key).is_some();
            changed |= usage.unknown.remove(key).is_some();
        }
        for digest in objects {
            changed |= usage.observed.remove(digest.as_hex()).is_some();
        }
        if changed {
            self.write_usage(&usage)?;
        }
        Ok(())
    }

    fn usage_record(&self) -> Result<UsageRecord, RootError> {
        Ok(read_usage(&self.root)?.unwrap_or(UsageRecord {
            version: USAGE_VERSION,
            results: BTreeMap::new(),
            unknown: BTreeMap::new(),
            observed: BTreeMap::new(),
        }))
    }

    /// Folds every open journal into `usage.json` in one write, and only when a bucket grew.
    fn fold_usage_locked(&self) -> Result<(), RootError> {
        let scan = self.journal_buckets();
        if !scan.damaged.is_empty() {
            // Fail closed: a caller about to unlink its journal must never do so after a fold
            // that skipped damaged evidence.
            return Err(damaged(format!(
                "usage fold refused while a journal is damaged: {}",
                scan.damaged.join(", ")
            )));
        }
        if scan.buckets.is_empty() && scan.unknowns.is_empty() {
            return Ok(());
        }
        let mut usage = self.usage_record()?;
        let today = UseBucket::ceil_day(self.clock.now())?;
        let mut changed = false;
        for (key, bucket) in scan.buckets {
            if let Some(floor) = usage.unknown.get(&key) {
                if bucket <= *floor {
                    // A stale dated journal must not clear an unknown-age floor.
                    continue;
                }
                usage.unknown.remove(&key);
                changed = true;
            }
            let newer = usage
                .results
                .get(&key)
                .is_none_or(|current| *current < bucket);
            if newer {
                usage.results.insert(key, bucket);
                changed = true;
            }
        }
        for key in scan.unknowns {
            let floor = usage
                .unknown
                .get(&key)
                .filter(|floor| **floor >= today)
                .cloned()
                .unwrap_or_else(|| today.clone());
            if usage.unknown.get(&key) != Some(&floor) {
                usage.unknown.insert(key.clone(), floor);
                changed = true;
            }
            changed |= usage.results.remove(&key).is_some();
        }
        // Journals in scan.damaged are deliberately left in place: retention reports each one as
        // damage, so GC retains their keys instead of trusting this partial fold.
        if changed {
            self.write_usage(&usage)?;
        }
        Ok(())
    }

    /// Every `(key, bucket)` in any open journal, plus the paths of journals that could not be
    /// read. Legacy entries without a bucket are unknown age and are not folded.
    fn journal_buckets(&self) -> JournalBuckets {
        let mut scan = JournalBuckets::default();
        let roots = self.root.join("roots");
        let projects = match fs::read_dir(&roots) {
            Ok(projects) => projects,
            Err(_) => {
                scan.damaged.push(roots.display().to_string());
                return scan;
            }
        };
        for project in projects {
            let project = match project {
                Ok(project) => project,
                Err(error) => {
                    scan.damaged
                        .push(format!("unreadable project entry: {error}"));
                    continue;
                }
            };
            let path = project.path();
            match project.file_type() {
                Ok(kind) if kind.is_dir() => {}
                _ => {
                    scan.damaged.push(path.display().to_string());
                    continue;
                }
            }
            let name = project.file_name().to_string_lossy().to_string();
            let sessions = match fs::read_dir(path.join("session")) {
                Ok(sessions) => sessions,
                Err(_) => {
                    scan.damaged
                        .push(path.join("session").display().to_string());
                    continue;
                }
            };
            for session in sessions {
                let session = match session {
                    Ok(session) => session,
                    Err(error) => {
                        scan.damaged
                            .push(format!("unreadable session entry: {error}"));
                        continue;
                    }
                };
                let journal = session.path();
                if journal.extension().is_none_or(|value| value != "jsonl") {
                    scan.damaged.push(journal.display().to_string());
                    continue;
                }
                let entries = match parse_journal(&journal, &name, None) {
                    Ok((_header, entries)) => entries,
                    Err(_) => {
                        scan.damaged.push(journal.display().to_string());
                        continue;
                    }
                };
                for entry in entries {
                    if !valid_key(&entry.key) {
                        scan.damaged.push(journal.display().to_string());
                        continue;
                    }
                    match entry.use_bucket {
                        Some(bucket) => scan.buckets.push((entry.key, bucket)),
                        None => scan.unknowns.push(entry.key),
                    }
                }
            }
        }
        scan
    }

    fn path(&self, kind: &RootKind) -> Result<PathBuf, RootError> {
        checked(kind)?;
        let base = self.project_dir();
        Ok(match kind {
            RootKind::Main => base.join("main.json"),
            RootKind::Worktree { id } => base.join("worktree").join(format!("{id}.json")),
            RootKind::Release { sequence, .. } => {
                base.join("release").join(format!("{sequence}.json"))
            }
            RootKind::Pin { id } => base.join("pin").join(format!("{id}.json")),
        })
    }

    fn root_locked(
        &self,
        _guard: &MetadataGuard,
        kind: &RootKind,
    ) -> Result<Option<RootRecord>, RootError> {
        let path = self.path(kind)?;
        let metadata = match fs::symlink_metadata(&path) {
            Ok(metadata) => metadata,
            Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
            Err(error) => {
                return Err(damaged(format!(
                    "{} could not be inspected: {error}",
                    path.display()
                )));
            }
        };
        if !metadata.is_file() {
            return Err(damaged(format!("{} is not a regular file", path.display())));
        }
        let bytes = fs::read(&path)?;
        let record: RootRecord = serde_json::from_slice(&bytes)
            .map_err(|error| damaged(format!("{}: {error}", path.display())))?;
        validate_record(&record, &self.project).map_err(damaged)?;
        if !same_target(&record.kind, kind) {
            return Err(damaged("root record kind differs from its location"));
        }
        Ok(Some(record))
    }

    pub fn root(&self, kind: &RootKind) -> Result<Option<RootRecord>, RootError> {
        let guard = self.leases.lock()?;
        self.root_locked(&guard, kind)
    }

    pub fn roots(&self) -> Result<Vec<RootRecord>, RootError> {
        let guard = self.leases.lock()?;
        self.roots_locked(&guard)
    }

    pub fn roots_locked(&self, _guard: &MetadataGuard) -> Result<Vec<RootRecord>, RootError> {
        self.check_guard(_guard)?;
        let mut records = vec![];
        let base = self.project_dir();
        let mut paths = vec![base.join("main.json")];
        for folder in ["worktree", "release", "pin"] {
            for entry in fs::read_dir(base.join(folder))? {
                let entry = entry?;
                if !entry.file_type()?.is_file() {
                    return Err(damaged(format!(
                        "unexpected root entry {}",
                        entry.path().display()
                    )));
                }
                paths.push(entry.path());
            }
        }
        for path in paths {
            match fs::symlink_metadata(&path) {
                Ok(_) => {}
                Err(error) if error.kind() == io::ErrorKind::NotFound => continue,
                Err(error) => {
                    return Err(damaged(format!(
                        "{} could not be inspected: {error}",
                        path.display()
                    )));
                }
            }
            let bytes = fs::read(&path)?;
            let record: RootRecord = serde_json::from_slice(&bytes)
                .map_err(|error| damaged(format!("{}: {error}", path.display())))?;
            validate_record(&record, &self.project).map_err(damaged)?;
            if !same_target(&record.kind, &kind_at(&path)?) {
                return Err(damaged(format!(
                    "{} holds a record for another target",
                    path.display()
                )));
            }
            records.push(record);
        }
        records.sort_by(|left, right| sort_key(&left.kind).cmp(&sort_key(&right.kind)));
        Ok(records)
    }

    pub fn begin_session(
        &self,
        kind: RootKind,
        provenance: Provenance,
        owner: ProcessIdentity,
    ) -> Result<BuildSession, RootError> {
        checked(&kind)?;
        if owner.pid == 0 || owner.boot.is_empty() || owner.started.is_empty() {
            return Err(invalid("complete session owner identity is required"));
        }
        let _guard = self.leases.lock()?;
        let base = self.project_dir();
        let session_directory = base.join("session");
        let temporary_directory = base.join("tmp");
        loop {
            let serial = NEXT.fetch_add(1, Ordering::Relaxed);
            let id = format!("{}-{serial}", std::process::id());
            let journal = session_directory.join(format!("{id}.jsonl"));
            if fs::symlink_metadata(&journal).is_ok() {
                continue;
            }
            let header = SessionHeader {
                version: SESSION_VERSION,
                project: self.project.clone(),
                kind: kind.clone(),
                provenance: provenance.clone(),
                owner: owner.clone(),
            };
            let bytes = serde_json::to_vec(&header).map_err(|error| invalid(error.to_string()))?;
            let mut line = bytes;
            line.push(b'\n');
            let temporary = write_temp(&temporary_directory, &line, "jsonl")?;
            match fs::rename(&temporary, &journal) {
                Ok(()) => {}
                Err(error) => {
                    let _ = fs::remove_file(&temporary);
                    if error.kind() == io::ErrorKind::AlreadyExists {
                        continue;
                    }
                    return Err(error.into());
                }
            }
            sync_dir(&session_directory)?;
            return Ok(BuildSession {
                store: self.clone(),
                kind,
                provenance,
                id,
                journal,
            });
        }
    }

    /// Enumerate session headers under the metadata lock. A damaged journal fails closed.
    pub fn sessions(&self) -> Result<Vec<SessionInfo>, RootError> {
        let _guard = self.leases.lock()?;
        self.sessions_locked()
    }

    fn sessions_locked(&self) -> Result<Vec<SessionInfo>, RootError> {
        let mut sessions = vec![];
        for entry in fs::read_dir(self.project_dir().join("session"))? {
            let entry = entry?;
            let path = entry.path();
            if !entry.file_type()?.is_file()
                || path.extension().is_none_or(|value| value != "jsonl")
            {
                return Err(damaged(format!(
                    "unexpected session entry {}",
                    path.display()
                )));
            }
            let (header, entries) = parse_journal(&path, &self.project, None)?;
            sessions.push(SessionInfo {
                id: path
                    .file_stem()
                    .and_then(|value| value.to_str())
                    .unwrap_or_default()
                    .to_string(),
                kind: header.kind,
                provenance: header.provenance,
                owner: header.owner,
                entries: entries
                    .into_iter()
                    .map(|entry| (entry.unit, entry.key))
                    .collect(),
            });
        }
        sessions.sort_by(|left, right| left.id.cmp(&right.id));
        Ok(sessions)
    }

    /// @cc [owner:fontanierh,label:correctness] gc-retains-until-session-cleanup-confirmed
    /// A lease or session MUST be reclaimable only when every owner and worker identity is
    /// positively dead and every registered session custodian's guard cleanup is durably
    /// confirmed. A dead custodian whose cleanup is unconfirmed or unreadable MUST count as
    /// unknown liveness and retain it; a dead monitor process alone MUST NOT prove cleanup.
    /// Unreadable correlation records and unknown liveness always retain, and a correlation answer
    /// of Ok(None) MUST mean authoritatively not a custodian: missing, unreadable or ambiguous
    /// evidence MUST be an error that retains, and no fallback adapter may guess "ordinary".
    /// See tests/roots.rs
    /// `a_dead_custodian_with_unconfirmed_cleanup_is_retained`,
    /// `an_owner_custodian_with_unconfirmed_cleanup_is_retained`,
    /// `a_dead_custodian_with_confirmed_cleanup_is_reclaimable`,
    /// `an_unreadable_custodian_or_cleanup_record_is_retained` and
    /// `alive_or_unknown_identities_still_retain_the_lease`.
    pub fn release_dead_session(
        &self,
        id: &str,
        probe: impl FnMut(&ProcessIdentity) -> Liveness,
        custodians: &impl SessionCustodians,
        cleanup: &impl CustodianCleanup,
    ) -> Result<Reclaim, RootError> {
        if !valid_segment(id) {
            return Err(invalid("invalid session id"));
        }
        let _guard = self.leases.lock()?;
        let path = self
            .project_dir()
            .join("session")
            .join(format!("{id}.jsonl"));
        let (header, _) = parse_journal(&path, &self.project, None)?;
        let lease = LeaseRecord {
            version: LEASE_VERSION,
            id: format!("session-{id}"),
            staging: format!("staging/session-{id}"),
            owner: header.owner,
            workers: vec![],
            result_keys: BTreeSet::new(),
            object_digests: BTreeSet::new(),
            rooted: false,
        };
        let verdict = may_reclaim(&lease, probe, custodians, cleanup);
        if verdict == Reclaim::Reclaimable {
            self.fold_usage_locked()?;
            fs::remove_file(&path)?;
            sync_dir(path.parent().expect("journal has a parent"))?;
        }
        Ok(verdict)
    }

    pub fn drop_root(&self, kind: &RootKind) -> Result<Option<RootRecord>, RootError> {
        let guard = self.leases.lock()?;
        let record = self.root_locked(&guard, kind)?;
        if record.is_some() {
            // Fold before unlinking: a damage refusal must never cost the root's retention.
            self.fold_usage_locked()?;
            let path = self.path(kind)?;
            fs::remove_file(&path)?;
            sync_dir(path.parent().expect("root has a parent"))?;
        }
        Ok(record)
    }

    /// @cc [owner:fontanierh,label:correctness] build-v2-frozen-roots
    /// Release and pin roots MUST be frozen snapshots written whole, never merged. A release is
    /// identified by an explicit sequence; an existing sequence with different entries is a
    /// conflict and MUST NOT be replaced, and only the three greatest sequences survive. A
    /// snapshot target MUST be a release or pin. See tests/roots.rs
    /// `a_release_is_a_frozen_snapshot_and_never_merges`,
    /// `releases_keep_the_three_greatest_sequences_and_refuse_a_different_duplicate`,
    /// `a_sequence_below_the_retained_window_is_refused`,
    /// `an_identical_release_retry_keeps_the_first_record` and
    /// `a_root_can_be_snapshotted_into_a_pin_but_not_into_a_mutable_root`.
    pub fn snapshot(
        &self,
        source: &RootKind,
        target: RootKind,
        provenance: Provenance,
    ) -> Result<RootRecord, RootError> {
        checked(&target)?;
        match &target {
            RootKind::Main | RootKind::Worktree { .. } => {
                return Err(invalid("a snapshot target must be a release or a pin"));
            }
            _ => {}
        }
        let guard = self.leases.lock()?;
        self.sweep_tmp_locked(&guard)?;
        let source_record = self
            .root_locked(&guard, source)?
            .ok_or_else(|| invalid("source root is missing"))?;
        let record = RootRecord {
            version: ROOT_VERSION,
            project: self.project.clone(),
            kind: target.clone(),
            entries: source_record.entries,
            provenance,
        };
        if let Some(existing) = self.root_locked(&guard, &target)? {
            if entry_keys(&existing.entries) != entry_keys(&record.entries) {
                return Err(RootError::Conflict(
                    "snapshot target already exists with different entries".into(),
                ));
            }
        } else {
            self.check_release_window_locked(&target)?;
            let path = self.path(&target)?;
            write_record(&path, &self.project_dir().join("tmp"), &record, &mut |_| {
                Ok(())
            })?;
        }
        if matches!(&target, RootKind::Release { .. }) {
            self.trim_releases_locked()?;
        }
        self.fold_usage_locked()?;
        Ok(record)
    }

    pub fn retention(&self) -> Result<RetentionView, RootError> {
        let guard = self.leases.lock()?;
        self.retention_locked(&guard)
    }

    /// @cc [owner:fontanierh,label:correctness] build-v2-root-retention-read
    /// Retention MUST count every key named by a readable root or session and report every record
    /// it cannot read instead of guessing; a non-empty damage list obliges GC to retain. A missing
    /// metadata directory is damage, not an empty view. This reader MUST be callable under a
    /// caller-held guard so GC reads retention, leases and deletes under one lock hold. See
    /// tests/roots.rs `retention_counts_root_and_open_session_keys`,
    /// `retention_is_readable_under_the_callers_guard`,
    /// `malformed_root_metadata_fails_reads_and_retention_reports_damage` and
    /// `missing_or_unreadable_metadata_is_damage`, including the selected project's own directory
    /// (`retention_reports_a_missing_selected_project`) and every other registered project
    /// (`retention_reports_a_missing_unselected_project`), because a vanished project would hide
    /// its keys from a store-wide view. A wrong-store guard never certifies a
    /// GC snapshot: `retention_locked` and `roots_locked` MUST refuse it,
    /// see `a_guard_from_another_store_is_refused`.
    pub fn retention_locked(&self, _guard: &MetadataGuard) -> Result<RetentionView, RootError> {
        self.check_guard(_guard)?;
        let mut view = RetentionView::default();
        let roots = self.root.join("roots");
        if fs::symlink_metadata(&roots).is_err() {
            view.damaged.push(roots.display().to_string());
            return Ok(view);
        }
        self.check_projects_present_locked(&roots, &self.project, &mut view.damaged);
        for project in fs::read_dir(&roots)? {
            let project = match project {
                Ok(project) => project,
                Err(error) => {
                    view.damaged
                        .push(format!("unreadable project entry: {error}"));
                    continue;
                }
            };
            match project.file_type() {
                Ok(kind) if kind.is_dir() => {}
                _ => {
                    view.damaged.push(project.path().display().to_string());
                    continue;
                }
            }
            match retention_of_project(&project.path()) {
                Ok(inner) => {
                    view.keys.extend(inner.keys);
                    view.damaged.extend(inner.damaged);
                }
                Err(error) => view
                    .damaged
                    .push(format!("{}: {error}", project.path().display())),
            }
        }
        Ok(view)
    }

    /// Presence checks retention needs for the selected project and every registered one. Reads
    /// only: nothing is created, and a missing registered project is damage, never an empty view.
    fn check_projects_present_locked(
        &self,
        roots: &Path,
        selected: &str,
        damaged: &mut Vec<String>,
    ) {
        let selected = roots.join(selected);
        match fs::symlink_metadata(&selected) {
            Ok(metadata) if metadata.is_dir() => {}
            _ => damaged.push(selected.display().to_string()),
        }
        match read_registry(&self.root) {
            Ok(Some(registry)) => {
                for name in registry.projects.keys() {
                    let path = roots.join(name);
                    match fs::symlink_metadata(&path) {
                        Ok(metadata) if metadata.is_dir() => {}
                        _ => damaged.push(path.display().to_string()),
                    }
                }
            }
            Ok(None) => {
                let any = fs::read_dir(roots)
                    .map(|mut entries| entries.next().is_some())
                    .unwrap_or(false);
                if any {
                    damaged.push(registry_path(&self.root).display().to_string());
                }
            }
            Err(_) => damaged.push(registry_path(&self.root).display().to_string()),
        }
    }

    /// Per-project retention for every project in the store, read under the caller's one guard
    /// and creating nothing. A non-empty `damaged` list obliges the caller to refuse destructive
    /// work rather than trust a partial view.
    pub fn all_project_retention_locked(
        &self,
        guard: &MetadataGuard,
    ) -> Result<AllProjectsRetention, RootError> {
        self.check_guard(guard)?;
        let mut all = AllProjectsRetention::default();
        let roots = self.root.join("roots");
        if fs::symlink_metadata(&roots).is_err() {
            all.damaged.push(roots.display().to_string());
            return Ok(all);
        }
        self.check_projects_present_locked(&roots, &self.project, &mut all.damaged);
        let registered = match read_registry(&self.root) {
            Ok(Some(registry)) => Some(registry),
            Ok(None) => None,
            Err(error) => {
                all.damaged.push(error.to_string());
                None
            }
        };
        for entry in fs::read_dir(&roots)? {
            let entry = match entry {
                Ok(entry) => entry,
                Err(error) => {
                    all.damaged
                        .push(format!("unreadable project entry: {error}"));
                    continue;
                }
            };
            match entry.file_type() {
                Ok(kind) if kind.is_dir() => {}
                _ => {
                    all.damaged.push(entry.path().display().to_string());
                    continue;
                }
            }
            let name = entry.file_name().to_string_lossy().to_string();
            if let Some(registry) = registered.as_ref() {
                if !registry.projects.contains_key(&name) {
                    all.damaged.push(entry.path().display().to_string());
                    continue;
                }
            }
            match retention_of_project(&entry.path()) {
                Ok(view) => {
                    all.damaged.extend(view.damaged.clone());
                    all.projects.insert(name, view);
                }
                Err(error) => all
                    .damaged
                    .push(format!("{}: {error}", entry.path().display())),
            }
        }
        Ok(all)
    }

    fn trim_releases_locked(&self) -> Result<Vec<u64>, RootError> {
        let folder = self.project_dir().join("release");
        let mut sequences = vec![];
        for entry in fs::read_dir(&folder)? {
            let entry = entry?;
            if !entry.file_type()?.is_file() {
                continue;
            }
            let name = entry.file_name();
            let name = name.to_string_lossy();
            let Some(stem) = name.strip_suffix(".json") else {
                continue;
            };
            let sequence: u64 = stem.parse().map_err(|_| {
                damaged(format!(
                    "{} is not a release sequence",
                    entry.path().display()
                ))
            })?;
            if stem != sequence.to_string() {
                return Err(damaged(format!(
                    "{} is not a canonical release sequence",
                    entry.path().display()
                )));
            }
            sequences.push(sequence);
        }
        sequences.sort_unstable();
        let mut removed = vec![];
        while sequences.len() > RELEASES_KEPT {
            let oldest = sequences.remove(0);
            fs::remove_file(folder.join(format!("{oldest}.json")))?;
            removed.push(oldest);
        }
        if !removed.is_empty() {
            sync_dir(&folder)?;
        }
        Ok(removed)
    }

    pub fn trim_releases(&self) -> Result<Vec<u64>, RootError> {
        let _guard = self.leases.lock()?;
        self.trim_releases_locked()
    }

    fn check_release_window_locked(&self, kind: &RootKind) -> Result<(), RootError> {
        let RootKind::Release { sequence, .. } = kind else {
            return Ok(());
        };
        let mut sequences = vec![];
        for entry in fs::read_dir(self.project_dir().join("release"))? {
            let entry = entry?;
            let name = entry.file_name();
            let name = name.to_string_lossy();
            if let Some(stem) = name.strip_suffix(".json") {
                if let Ok(value) = stem.parse::<u64>() {
                    sequences.push(value);
                }
            }
        }
        sequences.sort_unstable();
        if sequences.len() >= RELEASES_KEPT && *sequence < sequences[0] {
            return Err(RootError::Conflict(
                "release sequence is outside the retained window".into(),
            ));
        }
        Ok(())
    }

    fn sweep_tmp_locked(&self, _guard: &MetadataGuard) -> Result<(), RootError> {
        let folder = self.project_dir().join("tmp");
        for entry in fs::read_dir(&folder)? {
            let entry = entry?;
            fs::remove_file(entry.path())?;
        }
        sync_dir(&folder)?;
        Ok(())
    }

    /// A guard only certifies metadata of the store whose mutex it holds.
    fn check_guard(&self, guard: &MetadataGuard) -> Result<(), RootError> {
        if guard.store_root() != self.root {
            return Err(invalid("guard belongs to another store"));
        }
        Ok(())
    }
}

impl BuildSession {
    pub fn id(&self) -> &str {
        &self.id
    }

    pub fn target(&self) -> &RootKind {
        &self.kind
    }

    /// @cc [owner:fontanierh,label:correctness] build-v2-session-journal
    /// Every used key MUST be appended and fsynced before a publication callback returns Ok, so a
    /// result is retained before B2 clears its claims. A failed append MUST NOT leave a torn tail.
    /// A damaged or unterminated record MUST fail the commit, leave the previous root and the
    /// journal untouched, and be reported, and a commit MUST remove only its own journal.
    /// See tests/roots.rs `a_torn_journal_tail_fails_the_commit_and_preserves_root_and_journal`,
    /// `a_corrupt_middle_record_fails_closed_and_retention_counts_parseable_keys`,
    /// `a_commit_removes_only_its_own_session_journal`,
    /// `the_session_journal_keeps_every_key_and_the_root_takes_the_last_per_unit`,
    /// `b2_publication_and_hit_callbacks_record_the_caller_unit_binding` and
    /// `a_failed_append_leaves_the_journal_unchanged`.
    pub fn use_result(&mut self, unit: &str, key: &str) -> Result<(), RootError> {
        checked_entry(unit, key)?;
        let _guard = self.store.leases.lock()?;
        let bucket = UseBucket::ceil_day(self.store.clock.now())?;
        let line = serde_json::to_vec(&SessionEntry {
            unit: unit.to_string(),
            key: key.to_string(),
            use_bucket: Some(bucket),
        })
        .map_err(|error| invalid(error.to_string()))?;
        let mut file = OpenOptions::new().append(true).open(&self.journal)?;
        let before = file.metadata()?.len();
        let appended = (|| -> io::Result<()> {
            file.write_all(&line)?;
            file.write_all(b"\n")?;
            file.sync_all()
        })();
        if let Err(error) = appended {
            let _ = file.set_len(before);
            let _ = file.sync_all();
            return Err(error.into());
        }
        Ok(())
    }

    /// The exact callback B2's publish and retain_hit accept. The caller names the unit; the
    /// winning envelope's own unit is diagnostic and may belong to an earlier equivalent producer.
    pub fn root_callback<'a>(
        &'a mut self,
        unit: &str,
    ) -> impl FnOnce(&ResultEnvelope) -> Result<(), String> + 'a {
        let unit = unit.to_string();
        move |envelope| {
            self.use_result(&unit, &envelope.result.key)
                .map_err(|error| error.to_string())
        }
    }

    pub fn commit(self, declared: Option<&DeclaredRoster>) -> Result<RootRecord, RootError> {
        self.commit_observed(declared, |_| Ok(()))
    }

    /// Commit folds the journal into the root. A main or worktree root merges with the current
    /// root inside one lock hold; a release or pin writes its frozen snapshot whole.
    pub fn commit_observed(
        self,
        declared: Option<&DeclaredRoster>,
        mut observe: impl FnMut(CommitStep) -> io::Result<()>,
    ) -> Result<RootRecord, RootError> {
        let guard = self.store.leases.lock()?;
        observe(CommitStep::JournalRead)?;
        self.store.sweep_tmp_locked(&guard)?;
        let entries = parse_journal(&self.journal, &self.store.project, Some(&self.kind))?.1;
        let mut latest: BTreeMap<String, String> = BTreeMap::new();
        for entry in entries {
            latest.insert(entry.unit, entry.key);
        }
        let merged = match self.kind {
            RootKind::Main | RootKind::Worktree { .. } => {
                let mut current = self
                    .store
                    .root_locked(&guard, &self.kind)?
                    .map(|record| record.entries)
                    .unwrap_or_default();
                for (unit, key) in latest {
                    current.insert(
                        unit,
                        RootEntry {
                            key,
                            provenance: self.provenance.clone(),
                        },
                    );
                }
                if let Some(roster) = declared {
                    current.retain(|unit, _| roster.contains(unit));
                }
                current
            }
            RootKind::Release { .. } | RootKind::Pin { .. } => latest
                .into_iter()
                .map(|(unit, key)| {
                    (
                        unit,
                        RootEntry {
                            key,
                            provenance: self.provenance.clone(),
                        },
                    )
                })
                .collect(),
        };
        let record = RootRecord {
            version: ROOT_VERSION,
            project: self.store.project.clone(),
            kind: self.kind.clone(),
            entries: merged,
            provenance: self.provenance.clone(),
        };
        validate_record(&record, &self.store.project).map_err(damaged)?;
        let existing = self.store.root_locked(&guard, &self.kind)?;
        let frozen = matches!(&self.kind, RootKind::Release { .. } | RootKind::Pin { .. });
        if frozen {
            if let Some(existing) = &existing {
                if entry_keys(&existing.entries) != entry_keys(&record.entries) {
                    return Err(RootError::Conflict(
                        "frozen root already exists with different entries".into(),
                    ));
                }
            }
        }
        let write = match &existing {
            None => true,
            Some(existing) if frozen => false,
            Some(existing) => existing != &record,
        };
        if write {
            self.store.check_release_window_locked(&self.kind)?;
            let path = self.store.path(&self.kind)?;
            write_record(
                &path,
                &self.store.project_dir().join("tmp"),
                &record,
                &mut observe,
            )?;
        }
        if matches!(&self.kind, RootKind::Release { .. }) {
            self.store.trim_releases_locked()?;
        }
        self.store.fold_usage_locked()?;
        fs::remove_file(&self.journal)?;
        sync_dir(self.journal.parent().expect("journal has a parent"))?;
        observe(CommitStep::SessionRemoved)?;
        Ok(record)
    }

    /// Release this session's retention without touching any root. Only this journal is removed.
    pub fn abandon(self) -> Result<(), RootError> {
        let _guard = self.store.leases.lock()?;
        // Never erase a damaged journal's evidence: validate its framing before folding or
        // unlinking, so an unreadable journal stays on disk for retention and inspection.
        parse_journal(&self.journal, &self.store.project, Some(&self.kind))?;
        self.store.fold_usage_locked()?;
        fs::remove_file(&self.journal)?;
        sync_dir(self.journal.parent().expect("journal has a parent"))?;
        Ok(())
    }
}

/// C5c's durable custodian registry: which identity is a session custodian, if any.
pub trait SessionCustodians {
    /// Ok(None) MUST mean authoritatively not a custodian. Missing, unreadable or ambiguous
    /// evidence MUST be Err, which retains the lease; never return Ok(None) for missing evidence.
    fn correlation(&self, identity: &ProcessIdentity) -> Result<Option<String>, String>;
}

/// C5c's durable guard-cleanup confirmation for one custodian correlation.
pub trait CustodianCleanup {
    fn cleanup_confirmed(&self, correlation: &str) -> Result<bool, String>;
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Reclaim {
    Reclaimable,
    Retained(RetainReason),
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum RetainReason {
    IdentityNotConfirmedDead,
    /// A dead session custodian whose guard cleanup is not yet durably confirmed.
    CleanupUnconfirmed(String),
    CustodianRecordUnreadable(String),
}

/// The only public reclaim decision. LeaseRecord::identities_all_dead states the base identity
/// rule; this adds the custodian cleanup rule for the owner and every registered worker.
pub fn may_reclaim(
    lease: &LeaseRecord,
    mut probe: impl FnMut(&ProcessIdentity) -> Liveness,
    custodians: &impl SessionCustodians,
    cleanup: &impl CustodianCleanup,
) -> Reclaim {
    if !lease.identities_all_dead(&mut probe) {
        return Reclaim::Retained(RetainReason::IdentityNotConfirmedDead);
    }
    for identity in std::iter::once(&lease.owner).chain(lease.workers.iter()) {
        match custodians.correlation(identity) {
            Ok(None) => {}
            Ok(Some(correlation)) => match cleanup.cleanup_confirmed(&correlation) {
                Ok(true) => {}
                Ok(false) => {
                    return Reclaim::Retained(RetainReason::CleanupUnconfirmed(correlation));
                }
                Err(message) => {
                    return Reclaim::Retained(RetainReason::CustodianRecordUnreadable(message));
                }
            },
            Err(message) => {
                return Reclaim::Retained(RetainReason::CustodianRecordUnreadable(message));
            }
        }
    }
    Reclaim::Reclaimable
}
