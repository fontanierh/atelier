//! Dormant operational fencing, distinct from install transactions and cache authority.
//! There is deliberately no production finite-plan/evidence issuer in this slice.
//! A future qualified adapter must be reviewed before these private capabilities can be issued.
#![allow(dead_code)]

pub(crate) mod selection;

use crate::checkout_locks::{BuildGuard, ContentWriteGuard, LEGACY_EPOCH};
use crate::install_fs::{FileObservation, RootFs};
use crate::paths::{Claims, claim, relative_path};
use crate::source_hashes::{sha256, valid_digest};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use std::fmt;
use std::fs::OpenOptions;
use std::io::{self, Read};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::Path;

const MAX_BYTES: usize = 256 * 1024;
const MAX_TASKS: usize = 64;
const INSTALL_JOURNAL: &str = "build/build-v2/install/journal.json";

#[derive(Debug)]
pub(crate) enum EpochError {
    Unsupported,
    Invalid,
    Changed,
    CleanupUnknown,
    Pending,
    Io(io::Error),
}
impl fmt::Display for EpochError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::Unsupported => "no qualified production legacy plan adapter",
            Self::Invalid => "invalid legacy epoch control state",
            Self::Changed => "legacy epoch identity, source or scope changed",
            Self::CleanupUnknown => "legacy epoch cleanup is not positively established",
            Self::Pending => "legacy epoch still has unverified work",
            Self::Io(_) => "legacy epoch control I/O failed",
        })
    }
}
impl std::error::Error for EpochError {}
impl From<io::Error> for EpochError {
    fn from(value: io::Error) -> Self {
        Self::Io(value)
    }
}
type Result<T> = std::result::Result<T, EpochError>;

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct RootIdentity {
    device: u64,
    inode: u64,
}
fn root_identity(path: &Path) -> Result<RootIdentity> {
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)?;
    let meta = file.metadata()?;
    Ok(RootIdentity {
        device: meta.dev(),
        inode: meta.ino(),
    })
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
enum RepairKind {
    ClosedReplay,
    VerifiedRestore,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Task {
    id: String,
    repair: RepairKind,
    writes: Vec<String>,
}

/// Structural data is never, by itself, qualification for arbitrary legacy work.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Plan {
    project: String,
    roots: Vec<String>,
    source_plan: String,
    ownership: String,
    order_fulfillment: Option<String>,
    tasks: Vec<Task>,
}
impl Plan {
    fn validate(&self) -> Result<()> {
        if !label(&self.project)
            || !valid_digest(&self.source_plan)
            || !valid_digest(&self.ownership)
            || self
                .order_fulfillment
                .as_ref()
                .is_some_and(|v| !valid_digest(v))
            || self.roots.is_empty()
            || self.roots.len() > 16
            || self.tasks.is_empty()
            || self.tasks.len() > MAX_TASKS
        {
            return Err(EpochError::Invalid);
        }
        let mut roots = Claims::new();
        for root in &self.roots {
            safe_path(root)?;
            claim(&mut roots, root, "epoch root").map_err(|_| EpochError::Invalid)?;
        }
        let mut ids = BTreeSet::new();
        let mut writes = Claims::new();
        claim(&mut writes, "build/build-v2", "protected control metadata")
            .map_err(|_| EpochError::Invalid)?;
        for task in &self.tasks {
            if !label(&task.id)
                || !ids.insert(&task.id)
                || task.writes.is_empty()
                || task.writes.len() > 128
            {
                return Err(EpochError::Invalid);
            }
            for path in &task.writes {
                safe_path(path)?;
                if !self
                    .roots
                    .iter()
                    .any(|r| path.starts_with(&(r.clone() + "/")))
                {
                    return Err(EpochError::Invalid);
                }
                claim(&mut writes, path, &task.id).map_err(|_| EpochError::Invalid)?;
            }
        }
        Ok(())
    }
}
fn label(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|v| v.is_ascii_alphanumeric() || b"._-".contains(&v))
}
fn safe_path(value: &str) -> Result<()> {
    if value.len() > 1024 {
        return Err(EpochError::Invalid);
    }
    relative_path(value, true).map_err(|_| EpochError::Invalid)
}

/// Private, fresh named observations. Issuing this requires the future adapter's
/// source/ownership/output validation; deserialization can never issue one.
struct Witness {
    path: String,
    observation: FileObservation,
}
struct VerifiedFinitePlan {
    root: RootIdentity,
    plan: Plan,
    sources: Vec<Witness>,
}

/// The production default cannot turn a declaration, JSON record or boolean into authority.
pub(crate) fn qualify_production_plan() -> Result<()> {
    Err(EpochError::Unsupported)
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Attempt {
    task: String,
    id: String,
    report: String,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Settlement {
    task: String,
    stamp: String,
    inputs: String,
    outputs: String,
    cleanup: Vec<String>,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Record {
    version: u32,
    epoch: String,
    root: RootIdentity,
    plan: Plan,
    pending: Vec<String>,
    settled: Vec<Settlement>,
    attempts: Vec<Attempt>,
    verified_complete: bool,
}
fn encoded(record: &Record) -> Result<Vec<u8>> {
    let bytes = serde_json::to_vec(record).map_err(|_| EpochError::Invalid)?;
    if bytes.len() > MAX_BYTES {
        return Err(EpochError::Invalid);
    }
    Ok(bytes)
}
fn object(value: &serde_json::Value) -> Result<()> {
    if value.is_object() {
        Ok(())
    } else {
        Err(EpochError::Invalid)
    }
}
fn decode(bytes: &[u8]) -> Result<Record> {
    if bytes.len() > MAX_BYTES {
        return Err(EpochError::Invalid);
    }
    let v: serde_json::Value = serde_json::from_slice(bytes).map_err(|_| EpochError::Invalid)?;
    object(&v)?;
    object(&v["root"])?;
    object(&v["plan"])?;
    for key in ["settled", "attempts"] {
        for entry in v[key].as_array().ok_or(EpochError::Invalid)? {
            object(entry)?;
        }
    }
    for entry in v["plan"]["tasks"].as_array().ok_or(EpochError::Invalid)? {
        object(entry)?;
    }
    // Deserialize ORIGINAL bytes: deny_unknown_fields structs reject duplicate fields,
    // including nested records. Collections contain no untyped object maps.
    let r: Record = serde_json::from_slice(bytes).map_err(|_| EpochError::Invalid)?;
    validate_record(&r)?;
    Ok(r)
}
fn validate_record(r: &Record) -> Result<()> {
    r.plan.validate()?;
    if r.version != 1
        || !label(&r.epoch)
        || r.pending.len() > MAX_TASKS
        || r.settled.len() > MAX_TASKS
        || r.attempts.len() > 256
    {
        return Err(EpochError::Invalid);
    }
    let task_ids: BTreeSet<_> = r.plan.tasks.iter().map(|t| t.id.as_str()).collect();
    let mut membership = BTreeSet::new();
    for id in &r.pending {
        if !task_ids.contains(id.as_str()) || !membership.insert(id.as_str()) {
            return Err(EpochError::Invalid);
        }
    }
    for item in &r.settled {
        if !task_ids.contains(item.task.as_str())
            || !membership.insert(item.task.as_str())
            || ![&item.stamp, &item.inputs, &item.outputs]
                .iter()
                .all(|v| valid_digest(v))
            || item.cleanup.len() > 256
            || item.cleanup.iter().any(|v| !valid_digest(v))
        {
            return Err(EpochError::Invalid);
        }
    }
    let mut attempts = BTreeSet::new();
    let mut reports = Claims::new();
    for attempt in &r.attempts {
        safe_path(&attempt.report)?;
        claim(&mut reports, &attempt.report, &attempt.id).map_err(|_| EpochError::Invalid)?;
        if !task_ids.contains(attempt.task.as_str())
            || !label(&attempt.id)
            || !attempts.insert(&attempt.id)
        {
            return Err(EpochError::Invalid);
        }
    }
    for settlement in &r.settled {
        if settlement.cleanup.len()
            != r.attempts
                .iter()
                .filter(|v| v.task == settlement.task)
                .count()
        {
            return Err(EpochError::Invalid);
        }
    }
    if membership != task_ids || (r.verified_complete && !r.pending.is_empty()) {
        return Err(EpochError::Invalid);
    }
    Ok(())
}

/// These evidence types have no production issuer yet. Their constructors remain
/// module-private; a future adapter cannot substitute public report fields or flags.
struct FreshEvidence {
    record: String,
    witnesses: Vec<Witness>,
    cleanup: Vec<(String, String)>,
}
struct ValidatedSettlement {
    fresh: FreshEvidence,
    settlement: Settlement,
}
struct ValidatedFinalization {
    fresh: FreshEvidence,
    settlements: Vec<Settlement>,
}
struct ValidatedRepair {
    fresh: FreshEvidence,
}
struct ValidatedRevalidation {
    fresh: FreshEvidence,
    failed_tasks: BTreeSet<String>,
}

#[derive(Debug, PartialEq, Eq)]
enum RepairDemand {
    ClosedReplay(String),
    VerifiedRestore(String),
    RevalidateIndependent(String),
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Cut {
    Begun,
    AttemptRecorded,
    Settled,
    Requeued,
    CompleteRecorded,
    BarrierRemoved,
}

/// Only this module constructs permits; their lifetime retains real build AND EX guards.
pub(crate) struct EpochPermit<'permit, 'guards> {
    epoch: &'permit Epoch<'guards>,
}
pub(crate) struct Epoch<'a> {
    build: &'a BuildGuard,
    write: &'a ContentWriteGuard,
    fs: RootFs,
    qualified: &'a VerifiedFinitePlan,
    record: Record,
    observation: FileObservation,
}
impl<'a> Epoch<'a> {
    fn guards(
        build: &BuildGuard,
        write: &ContentWriteGuard,
        plan: &VerifiedFinitePlan,
    ) -> Result<RootFs> {
        if !build.owns_writer(write) || root_identity(build.root())? != plan.root {
            return Err(EpochError::Changed);
        }
        plan.plan.validate()?;
        let fs = RootFs::open(build.root())?;
        if fs.occupied(INSTALL_JOURNAL)? {
            return Err(EpochError::Invalid);
        }
        check_witnesses(&fs, &plan.sources)?;
        Ok(fs)
    }

    /// @cc [owner:fontanierh,label:correctness;safety] legacy-epoch-durable-state
    /// An epoch MUST publish all pending tasks before mutation under real same-root build+EX.
    /// Every durable transition MUST verify the exact previous record and assign memory only
    /// after persistence. Faults BEFORE verified barrier removal MUST retain a reader fence;
    /// no old stamp or boolean issues proof.
    /// See tests beginning with durable_cuts and strict_records in this module.
    fn begin(
        build: &'a BuildGuard,
        write: &'a ContentWriteGuard,
        plan: &'a VerifiedFinitePlan,
        id: &str,
        mut cut: impl FnMut(Cut) -> io::Result<()>,
    ) -> Result<Self> {
        let fs = Self::guards(build, write, plan)?;
        let record = Record {
            version: 1,
            epoch: id.into(),
            root: plan.root.clone(),
            plan: plan.plan.clone(),
            pending: plan.plan.tasks.iter().map(|t| t.id.clone()).collect(),
            settled: vec![],
            attempts: vec![],
            verified_complete: false,
        };
        validate_record(&record)?;
        fs.publish_metadata(LEGACY_EPOCH, &encoded(&record)?)?;
        cut(Cut::Begun)?;
        let observation = fs.observe(LEGACY_EPOCH)?.ok_or(EpochError::Changed)?;
        Ok(Self {
            build,
            write,
            fs,
            qualified: plan,
            record,
            observation,
        })
    }
    fn load(fs: &RootFs) -> Result<(Record, FileObservation)> {
        let mut file = fs.file(LEGACY_EPOCH)?;
        let observation = FileObservation::from_metadata(&file.metadata()?);
        if observation.size > MAX_BYTES as u64 {
            return Err(EpochError::Invalid);
        }
        let mut bytes = Vec::new();
        file.by_ref()
            .take((MAX_BYTES + 1) as u64)
            .read_to_end(&mut bytes)?;
        if FileObservation::from_metadata(&file.metadata()?) != observation {
            return Err(EpochError::Changed);
        }
        Ok((decode(&bytes)?, observation))
    }
    fn resume(
        build: &'a BuildGuard,
        write: &'a ContentWriteGuard,
        plan: &'a VerifiedFinitePlan,
        evidence: &ValidatedRepair,
    ) -> Result<Self> {
        let fs = Self::guards(build, write, plan)?;
        let (record, observation) = Self::load(&fs)?;
        if record.root != plan.root || record.plan != plan.plan {
            return Err(EpochError::Changed);
        }
        let epoch = Self {
            build,
            write,
            fs,
            qualified: plan,
            record,
            observation,
        };
        epoch.check_fresh(&evidence.fresh)?;
        Ok(epoch)
    }
    fn current(&self) -> Result<()> {
        Self::guards(self.build, self.write, self.qualified)?;
        let (record, observation) = Self::load(&self.fs)?;
        if record != self.record || observation != self.observation {
            return Err(EpochError::Changed);
        }
        Ok(())
    }
    fn check_fresh(&self, evidence: &FreshEvidence) -> Result<()> {
        self.current()?;
        if evidence.record != sha256(&encoded(&self.record)?) {
            return Err(EpochError::Changed);
        }
        check_witnesses(&self.fs, &evidence.witnesses)?;
        let expected: BTreeSet<_> = self.record.attempts.iter().map(|v| v.id.as_str()).collect();
        let actual: BTreeSet<_> = evidence.cleanup.iter().map(|v| v.0.as_str()).collect();
        if actual.len() != evidence.cleanup.len()
            || actual != expected
            || evidence
                .cleanup
                .iter()
                .any(|(_, digest)| !valid_digest(digest))
        {
            return Err(EpochError::CleanupUnknown);
        }
        Ok(())
    }
    fn save(&mut self, record: Record) -> Result<()> {
        self.current()?;
        validate_record(&record)?;
        self.fs.replace_metadata(LEGACY_EPOCH, &encoded(&record)?)?;
        let observation = self.fs.observe(LEGACY_EPOCH)?.ok_or(EpochError::Changed)?;
        self.record = record;
        self.observation = observation;
        Ok(())
    }
    fn begin_attempt(
        &mut self,
        intent: Attempt,
        mut cut: impl FnMut(Cut) -> io::Result<()>,
    ) -> Result<()> {
        if self.record.verified_complete || !self.record.pending.contains(&intent.task) {
            return Err(EpochError::Invalid);
        }
        let mut next = self.record.clone();
        next.attempts.push(intent);
        self.save(next)?;
        cut(Cut::AttemptRecorded)?;
        Ok(())
    }
    fn settle(
        &mut self,
        proof: ValidatedSettlement,
        mut cut: impl FnMut(Cut) -> io::Result<()>,
    ) -> Result<()> {
        self.check_fresh(&proof.fresh)?;
        if self.record.verified_complete || !self.record.pending.contains(&proof.settlement.task) {
            return Err(EpochError::Invalid);
        }
        let cleanup: Vec<_> = self
            .record
            .attempts
            .iter()
            .filter(|v| v.task == proof.settlement.task)
            .map(|attempt| {
                proof
                    .fresh
                    .cleanup
                    .iter()
                    .find(|v| v.0 == attempt.id)
                    .map(|v| v.1.clone())
                    .ok_or(EpochError::CleanupUnknown)
            })
            .collect::<Result<_>>()?;
        if cleanup != proof.settlement.cleanup {
            return Err(EpochError::CleanupUnknown);
        }
        let mut next = self.record.clone();
        next.pending.retain(|v| v != &proof.settlement.task);
        next.settled.push(proof.settlement);
        self.save(next)?;
        cut(Cut::Settled)?;
        Ok(())
    }
    fn demands(&self) -> Vec<RepairDemand> {
        self.record
            .plan
            .tasks
            .iter()
            .map(|t| {
                if self.record.pending.contains(&t.id) {
                    match t.repair {
                        RepairKind::ClosedReplay => RepairDemand::ClosedReplay(t.id.clone()),
                        RepairKind::VerifiedRestore => RepairDemand::VerifiedRestore(t.id.clone()),
                    }
                } else {
                    RepairDemand::RevalidateIndependent(t.id.clone())
                }
            })
            .collect()
    }
    fn requeue_failed(
        &mut self,
        proof: ValidatedRevalidation,
        mut cut: impl FnMut(Cut) -> io::Result<()>,
    ) -> Result<()> {
        self.check_fresh(&proof.fresh)?;
        if proof.failed_tasks.is_empty()
            || proof
                .failed_tasks
                .iter()
                .any(|task| !self.record.settled.iter().any(|v| &v.task == task))
        {
            return Err(EpochError::Invalid);
        }
        let mut next = self.record.clone();
        next.verified_complete = false;
        next.settled
            .retain(|v| !proof.failed_tasks.contains(&v.task));
        next.pending.extend(proof.failed_tasks);
        self.save(next)?;
        cut(Cut::Requeued)?;
        Ok(())
    }
    fn finish(
        &mut self,
        proof: ValidatedFinalization,
        mut cut: impl FnMut(Cut) -> io::Result<()>,
    ) -> Result<()> {
        self.check_fresh(&proof.fresh)?;
        if !self.record.pending.is_empty() {
            return Err(EpochError::Pending);
        }
        if proof.settlements != self.record.settled {
            return Err(EpochError::Changed);
        }
        let mut complete = self.record.clone();
        complete.verified_complete = true;
        self.save(complete)?;
        cut(Cut::CompleteRecorded)?;
        self.current()?;
        check_witnesses(&self.fs, &proof.fresh.witnesses)?;
        self.fs.remove_owned(LEGACY_EPOCH, &self.observation)?;
        cut(Cut::BarrierRemoved)?;
        Ok(())
    }
    fn permit(&self) -> EpochPermit<'_, 'a> {
        EpochPermit { epoch: self }
    }
}
impl EpochPermit<'_, '_> {
    pub(crate) fn verify(&self, build: &BuildGuard, write: &ContentWriteGuard) -> Result<()> {
        if !std::ptr::eq(build, self.epoch.build) || !std::ptr::eq(write, self.epoch.write) {
            return Err(EpochError::Changed);
        }
        self.epoch.current()
    }
}
fn check_witnesses(fs: &RootFs, witnesses: &[Witness]) -> Result<()> {
    if witnesses.is_empty() || witnesses.len() > 1024 {
        return Err(EpochError::Invalid);
    }
    let mut paths = BTreeSet::new();
    for witness in witnesses {
        safe_path(&witness.path)?;
        if !paths.insert(&witness.path)
            || fs.observe(&witness.path)? != Some(witness.observation.clone())
        {
            return Err(EpochError::Changed);
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::checkout_locks::{CheckoutLocks, LockError};
    use crate::install::{
        CurrentStatus, InstallError, InstallPolicy, OwnershipSnapshot, ProjectNamespace,
        ReceiptReader,
    };
    use std::collections::BTreeMap;
    use std::fs;
    use std::path::PathBuf;
    use std::sync::atomic::{AtomicU64, Ordering};
    static NEXT: AtomicU64 = AtomicU64::new(0);

    struct Fixture {
        root: PathBuf,
    }
    impl Fixture {
        fn new() -> Self {
            let root = std::env::temp_dir().join(format!(
                "atelier-epoch-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&root).unwrap();
            for folder in ["products", "stamps", "reports"] {
                fs::create_dir(root.join(folder)).unwrap();
            }
            fs::write(root.join("source"), b"closed fixture input").unwrap();
            Self { root }
        }
        fn locks(&self) -> CheckoutLocks {
            CheckoutLocks::open(&self.root).unwrap()
        }
        fn fs(&self) -> RootFs {
            RootFs::open(&self.root).unwrap()
        }
        fn witness(&self, path: &str) -> Witness {
            Witness {
                path: path.into(),
                observation: self.fs().observe(path).unwrap().unwrap(),
            }
        }
        // This issuer exists ONLY in tests and certifies this concrete closed file-copy fixture.
        // No generic production Step/Call/native qualification is inferred from it.
        fn qualify(&self) -> VerifiedFinitePlan {
            let bytes = fs::read(self.root.join("source")).unwrap();
            assert_eq!(bytes, b"closed fixture input");
            VerifiedFinitePlan {
                root: root_identity(&self.root).unwrap(),
                sources: vec![self.witness("source")],
                plan: Plan {
                    project: "fixture".into(),
                    roots: vec!["products".into()],
                    source_plan: sha256(&bytes),
                    ownership: sha256(b"fixture exact a/b ownership"),
                    order_fulfillment: None,
                    tasks: vec![
                        Task {
                            id: "a".into(),
                            repair: RepairKind::ClosedReplay,
                            writes: vec!["products/a".into()],
                        },
                        Task {
                            id: "b".into(),
                            repair: RepairKind::VerifiedRestore,
                            writes: vec!["products/b".into()],
                        },
                    ],
                },
            }
        }
        fn replay(&self, task: &str) {
            fs::copy(
                self.root.join("source"),
                self.root.join(format!("products/{task}")),
            )
            .unwrap();
            let stamp = format!(
                "{task}:{}",
                sha256(&fs::read(self.root.join(format!("products/{task}"))).unwrap())
            );
            fs::write(self.root.join(format!("stamps/{task}")), stamp).unwrap();
        }
        fn fresh(&self, record: &Record) -> Result<FreshEvidence> {
            let mut witnesses = vec![self.witness("source")];
            for task in &record.plan.tasks {
                for path in [
                    format!("products/{}", task.id),
                    format!("stamps/{}", task.id),
                ] {
                    if self.root.join(&path).exists() {
                        witnesses.push(self.witness(&path));
                    }
                }
            }
            let mut cleanup = vec![];
            for intent in &record.attempts {
                let raw = fs::read(self.root.join(&intent.report))
                    .map_err(|_| EpochError::CleanupUnknown)?;
                let v: serde_json::Value =
                    serde_json::from_slice(&raw).map_err(|_| EpochError::CleanupUnknown)?;
                if v != serde_json::json!({"invocation":intent.id,"cleanup_complete":true,"processes":[]})
                {
                    return Err(EpochError::CleanupUnknown);
                }
                witnesses.push(self.witness(&intent.report));
                cleanup.push((intent.id.clone(), sha256(&raw)));
            }
            Ok(FreshEvidence {
                record: sha256(&encoded(record)?),
                witnesses,
                cleanup,
            })
        }
        fn prove_task(&self, record: &Record, task: &str) -> ValidatedSettlement {
            let bytes = fs::read(self.root.join(format!("products/{task}"))).unwrap();
            assert_eq!(bytes, fs::read(self.root.join("source")).unwrap());
            let stamp = fs::read(self.root.join(format!("stamps/{task}"))).unwrap();
            assert_eq!(stamp, format!("{task}:{}", sha256(&bytes)).into_bytes());
            let fresh = self.fresh(record).unwrap();
            let cleanup = record
                .attempts
                .iter()
                .filter(|v| v.task == task)
                .map(|a| {
                    fresh
                        .cleanup
                        .iter()
                        .find(|v| v.0 == a.id)
                        .unwrap()
                        .1
                        .clone()
                })
                .collect();
            ValidatedSettlement {
                settlement: Settlement {
                    task: task.into(),
                    stamp: sha256(&stamp),
                    inputs: sha256(&fs::read(self.root.join("source")).unwrap()),
                    outputs: sha256(&bytes),
                    cleanup,
                },
                fresh,
            }
        }
        fn final_proof(&self, record: &Record) -> ValidatedFinalization {
            let mut settlements = vec![];
            for prior in &record.settled {
                settlements.push(self.prove_task(record, &prior.task).settlement);
            }
            assert_eq!(settlements, record.settled);
            ValidatedFinalization {
                fresh: self.fresh(record).unwrap(),
                settlements,
            }
        }
        fn repair_proof(&self) -> Result<ValidatedRepair> {
            let (r, _) = Epoch::load(&self.fs())?;
            Ok(ValidatedRepair {
                fresh: self.fresh(&r)?,
            })
        }
        fn reader(&self) -> ReceiptReader {
            ReceiptReader::open(
                &self.root,
                InstallPolicy {
                    project: ProjectNamespace::new("fixture").unwrap(),
                    allowed_install_roots: vec!["products".into()],
                },
            )
            .unwrap()
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.root);
        }
    }
    fn ok(_: Cut) -> io::Result<()> {
        Ok(())
    }
    fn fault(at: Cut) -> impl FnMut(Cut) -> io::Result<()> {
        move |cut| {
            if cut == at {
                Err(io::Error::other("injected durable cut"))
            } else {
                Ok(())
            }
        }
    }
    fn settle_both(f: &Fixture, e: &mut Epoch<'_>) {
        for task in ["a", "b"] {
            f.replay(task);
            let proof = f.prove_task(&e.record, task);
            e.settle(proof, ok).unwrap();
        }
    }

    #[test]
    fn durable_begin_cut_fences_readers_and_default_recovery() {
        let f = Fixture::new();
        f.replay("a"); // Pre-epoch stamps never remove pending repair work.
        let locks = f.locks();
        let build = locks.try_build_exclusive().unwrap();
        let plan = f.qualify();
        {
            let write = build.try_legacy_write_content().unwrap();
            assert!(Epoch::begin(&build, &write, &plan, "epoch", fault(Cut::Begun)).is_err());
        }
        let (record, _) = Epoch::load(&f.fs()).unwrap();
        assert_eq!(record.pending, ["a", "b"]);
        assert!(f.root.join("stamps/a").is_file());
        assert!(matches!(
            locks.try_read_content(),
            Err(LockError::LegacyEpochIncomplete)
        ));
        assert!(matches!(
            build.try_write_content(),
            Err(LockError::LegacyEpochIncomplete)
        ));
        let view = OwnershipSnapshot::from_projects(std::iter::empty::<(
            ProjectNamespace,
            &crate::graph::BuildGraph,
        )>())
        .unwrap();
        assert!(matches!(
            f.reader().recover(&build, &view),
            Err(InstallError::Lock(LockError::LegacyEpochIncomplete))
        ));
        assert!(!f.root.join(INSTALL_JOURNAL).exists());
        assert!(matches!(
            qualify_production_plan(),
            Err(EpochError::Unsupported)
        ));
    }

    #[test]
    fn durable_settlement_cut_preserves_independent_work_and_repair_demands() {
        let f = Fixture::new();
        let locks = f.locks();
        let build = locks.try_build_exclusive().unwrap();
        let write = build.try_legacy_write_content().unwrap();
        let plan = f.qualify();
        {
            let mut e = Epoch::begin(&build, &write, &plan, "epoch", ok).unwrap();
            f.replay("a");
            let proof = f.prove_task(&e.record, "a");
            assert!(e.settle(proof, fault(Cut::Settled)).is_err());
        }
        let before = fs::metadata(f.root.join("products/a")).unwrap().ino();
        let mut e = Epoch::resume(&build, &write, &plan, &f.repair_proof().unwrap()).unwrap();
        assert_eq!(
            e.demands(),
            [
                RepairDemand::RevalidateIndependent("a".into()),
                RepairDemand::VerifiedRestore("b".into())
            ]
        );
        let proof = f.final_proof(&e.record);
        assert!(matches!(e.finish(proof, ok), Err(EpochError::Pending)));
        f.replay("b");
        let proof = f.prove_task(&e.record, "b");
        e.settle(proof, ok).unwrap();
        let proof = f.final_proof(&e.record);
        e.finish(proof, ok).unwrap();
        assert_eq!(
            before,
            fs::metadata(f.root.join("products/a")).unwrap().ino()
        );
        assert!(!f.root.join(LEGACY_EPOCH).exists());
    }

    #[test]
    fn durable_finish_cuts_resume_or_leave_only_verified_absence() {
        for cut in [Cut::CompleteRecorded, Cut::BarrierRemoved] {
            let f = Fixture::new();
            let locks = f.locks();
            let build = locks.try_build_exclusive().unwrap();
            let write = build.try_legacy_write_content().unwrap();
            let plan = f.qualify();
            {
                let mut e = Epoch::begin(&build, &write, &plan, "epoch", ok).unwrap();
                settle_both(&f, &mut e);
                let proof = f.final_proof(&e.record);
                assert!(e.finish(proof, fault(cut)).is_err());
            }
            if cut == Cut::CompleteRecorded {
                let mut e =
                    Epoch::resume(&build, &write, &plan, &f.repair_proof().unwrap()).unwrap();
                assert!(e.record.verified_complete);
                let proof = f.final_proof(&e.record);
                e.finish(proof, ok).unwrap();
            }
            assert!(!f.root.join(LEGACY_EPOCH).exists());
            assert_eq!(
                fs::read(f.root.join("products/a")).unwrap(),
                b"closed fixture input"
            );
        }
    }

    #[test]
    fn repair_requires_unchanged_source_plan_root_and_positive_attempt_cleanup() {
        let f = Fixture::new();
        let locks = f.locks();
        let build = locks.try_build_exclusive().unwrap();
        let write = build.try_legacy_write_content().unwrap();
        let plan = f.qualify();
        {
            let mut e = Epoch::begin(&build, &write, &plan, "epoch", ok).unwrap();
            assert!(
                e.begin_attempt(
                    Attempt {
                        task: "a".into(),
                        id: "attempt-a".into(),
                        report: "reports/a.json".into()
                    },
                    fault(Cut::AttemptRecorded)
                )
                .is_err()
            );
        }
        assert!(matches!(f.repair_proof(), Err(EpochError::CleanupUnknown)));
        fs::write(
            f.root.join("reports/a.json"),
            br#"{"invocation":"attempt-a","cleanup_complete":false,"processes":[]}"#,
        )
        .unwrap();
        assert!(matches!(f.repair_proof(), Err(EpochError::CleanupUnknown)));
        fs::write(
            f.root.join("reports/a.json"),
            br#"{"invocation":"attempt-a","cleanup_complete":true,"processes":[]}"#,
        )
        .unwrap();
        let evidence = f.repair_proof().unwrap();
        let e = Epoch::resume(&build, &write, &plan, &evidence).unwrap();
        assert_eq!(e.record.pending.len(), 2);
        drop(e);
        let mut wrong = f.qualify();
        wrong.plan.source_plan = sha256(b"different plan");
        assert!(matches!(
            Epoch::resume(&build, &write, &wrong, &evidence),
            Err(EpochError::Changed)
        ));
        let other = Fixture::new();
        let other_locks = other.locks();
        let other_build = other_locks.try_build_exclusive().unwrap();
        let other_write = other_build.try_legacy_write_content().unwrap();
        assert!(matches!(
            Epoch::resume(&other_build, &other_write, &plan, &evidence),
            Err(EpochError::Changed)
        ));
        fs::write(f.root.join("source"), b"changed source").unwrap();
        assert!(matches!(
            Epoch::resume(&build, &write, &plan, &evidence),
            Err(EpochError::Changed)
        ));
    }

    #[test]
    fn fresh_settlement_and_finalization_refuse_late_source_output_and_record_changes() {
        let f = Fixture::new();
        let locks = f.locks();
        let build = locks.try_build_exclusive().unwrap();
        let write = build.try_legacy_write_content().unwrap();
        let plan = f.qualify();
        let mut e = Epoch::begin(&build, &write, &plan, "epoch", ok).unwrap();
        settle_both(&f, &mut e);
        let proof = f.final_proof(&e.record);
        fs::write(f.root.join("products/a"), b"foreign late bytes").unwrap();
        assert!(matches!(e.finish(proof, ok), Err(EpochError::Changed)));
        assert!(f.root.join(LEGACY_EPOCH).exists());
        f.replay("a");
        let proof = f.final_proof(&e.record);
        assert!(matches!(
            e.finish(proof, |cut| {
                if cut == Cut::CompleteRecorded {
                    fs::write(f.root.join("products/b"), b"late")?;
                }
                Ok(())
            }),
            Err(EpochError::Changed)
        ));
        let retained = f.fs().read(LEGACY_EPOCH).unwrap();
        assert!(decode(&retained).unwrap().verified_complete);
        f.fs()
            .replace_metadata(LEGACY_EPOCH, b"foreign record")
            .unwrap();
        assert!(e.current().is_err());
        assert_eq!(f.fs().read(LEGACY_EPOCH).unwrap(), b"foreign record");
    }

    #[test]
    fn settled_drift_requeues_before_replay_without_rerunning_valid_independent_outputs() {
        let f = Fixture::new();
        let locks = f.locks();
        let build = locks.try_build_exclusive().unwrap();
        let write = build.try_legacy_write_content().unwrap();
        let plan = f.qualify();
        let mut e = Epoch::begin(&build, &write, &plan, "epoch", ok).unwrap();
        settle_both(&f, &mut e);
        let independent = fs::metadata(f.root.join("products/b")).unwrap().ino();
        fs::write(f.root.join("products/a"), b"partial later drift").unwrap();
        // Concrete fixture revalidation, not a caller-provided changed flag.
        assert_ne!(
            sha256(&fs::read(f.root.join("products/a")).unwrap()),
            e.record.settled[0].outputs
        );
        let proof = ValidatedRevalidation {
            fresh: f.fresh(&e.record).unwrap(),
            failed_tasks: BTreeSet::from(["a".into()]),
        };
        assert!(e.requeue_failed(proof, fault(Cut::Requeued)).is_err());
        drop(e);
        let mut e = Epoch::resume(&build, &write, &plan, &f.repair_proof().unwrap()).unwrap();
        assert_eq!(
            e.demands(),
            [
                RepairDemand::ClosedReplay("a".into()),
                RepairDemand::RevalidateIndependent("b".into())
            ]
        );
        assert_eq!(Epoch::load(&f.fs()).unwrap().0.pending, ["a"]);
        f.replay("a");
        let proof = f.prove_task(&e.record, "a");
        e.settle(proof, ok).unwrap();
        let proof = f.final_proof(&e.record);
        e.finish(proof, ok).unwrap();
        assert_eq!(
            fs::metadata(f.root.join("products/b")).unwrap().ino(),
            independent
        );
    }

    #[test]
    fn strict_records_refuse_positional_duplicate_unknown_and_unbounded_state() {
        let f = Fixture::new();
        let locks = f.locks();
        let build = locks.try_build_exclusive().unwrap();
        let write = build.try_legacy_write_content().unwrap();
        let plan = f.qualify();
        let mut empty = f.qualify();
        empty.sources.clear();
        assert!(matches!(
            Epoch::begin(&build, &write, &empty, "empty", ok),
            Err(EpochError::Invalid)
        ));
        let e = Epoch::begin(&build, &write, &plan, "epoch", ok).unwrap();
        let raw = encoded(&e.record).unwrap();
        assert!(decode(&raw).is_ok());
        let text = String::from_utf8(raw.clone()).unwrap();
        for bad in [
            text.replacen("\"version\":1", "\"version\":1,\"version\":1", 1),
            text.replacen(
                "\"project\":\"fixture\"",
                "\"project\":\"fixture\",\"project\":\"fixture\"",
                1,
            ),
            text.replacen("\"version\":1", "\"version\":2", 1),
            "[]".into(),
        ] {
            assert!(decode(bad.as_bytes()).is_err());
        }
        let mut value: serde_json::Value = serde_json::from_slice(&raw).unwrap();
        value["plan"]["tasks"][0] = serde_json::json!(["a", "closed_replay", ["products/a"]]);
        assert!(decode(&serde_json::to_vec(&value).unwrap()).is_err());
        assert!(decode(&vec![b' '; MAX_BYTES + 1]).is_err());
        let mut bad = e.record.clone();
        bad.pending.push("a".into());
        assert!(validate_record(&bad).is_err());
        let mut bad = e.record.clone();
        bad.plan.tasks[1].writes = vec!["products/A".into()];
        assert!(validate_record(&bad).is_err());
        let mut bad = e.record.clone();
        bad.plan.tasks[0].writes = vec!["../escape".into()];
        assert!(validate_record(&bad).is_err());
        for path in [
            "build/build-v2",
            "build/BUILD-V2",
            "build/build-v2/install/journal.json",
        ] {
            let mut bad = e.record.clone();
            bad.plan.roots = vec!["build".into()];
            bad.plan.tasks[0].writes = vec![path.into()];
            bad.plan.tasks[1].writes = vec!["build/other".into()];
            assert!(validate_record(&bad).is_err());
        }
        let mut bad = e.record.clone();
        bad.attempts = vec![
            Attempt {
                task: "a".into(),
                id: "first".into(),
                report: "reports/A.json".into(),
            },
            Attempt {
                task: "b".into(),
                id: "second".into(),
                report: "reports/a.json".into(),
            },
        ];
        assert!(validate_record(&bad).is_err());
    }

    #[test]
    fn occupied_epoch_names_are_never_overwritten_or_implicitly_adopted() {
        use std::os::unix::fs::symlink;
        for linked in [false, true] {
            let f = Fixture::new();
            let locks = f.locks();
            let build = locks.try_build_exclusive().unwrap();
            let plan = f.qualify();
            fs::write(f.root.join("foreign"), b"preserve").unwrap();
            if linked {
                symlink(f.root.join("foreign"), f.root.join(LEGACY_EPOCH)).unwrap();
            } else {
                f.fs().replace_metadata(LEGACY_EPOCH, b"malformed").unwrap();
            }
            {
                let write = build.try_legacy_write_content().unwrap();
                assert!(Epoch::begin(&build, &write, &plan, "epoch", ok).is_err());
            }
            assert!(matches!(
                locks.try_read_content(),
                Err(LockError::LegacyEpochIncomplete)
            ));
            assert_eq!(fs::read(f.root.join("foreign")).unwrap(), b"preserve");
            assert!(f.root.join(LEGACY_EPOCH).symlink_metadata().is_ok());
        }
    }

    pub(super) fn prepared() -> crate::keys::PreparedUnit {
        use crate::{keys::*, schema::*, source_hashes::SourceHashCache, validate::*};
        let declaration: Declaration = serde_json::from_value(serde_json::json!({
            "schema_version":2,"cache_version":"fixture","units":[{"id":"v2","op":{"kind":"blob","version":"1"},
            "script":"run.py","code":["run.py"],"inputs":[],"params":{},"outputs":[{"id":"stored","logical_path":"/Data/Fixed",
            "class":"Blob","destination":"store","files":[{"path":"payload","required":true}]}]}]})).unwrap();
        let registry = BTreeMap::from([(
            ("blob".into(), "1".into()),
            OpDefinition {
                inputs: BTreeMap::new(),
                output_classes: BTreeSet::from(["Blob".into()]),
                params: BTreeMap::new(),
            },
        )]);
        let snapshot =
            BTreeMap::from([("run.py".into(), SnapshotEntry::File(b"fixture".to_vec()))]);
        let validated = validate(&declaration, &registry, &snapshot, &["products".into()]).unwrap();
        let implementation = ImplementationIdentity {
            version: "1".into(),
            digest: sha256(b"fixture"),
        };
        crate::keys::prepare(
            &declaration,
            &validated,
            "v2",
            &KeyContext {
                snapshot: &snapshot,
                versions: &BTreeMap::new(),
                produced: &BTreeMap::new(),
                produced_groups: &BTreeMap::new(),
                staged_inputs: &BTreeMap::new(),
                worker: &implementation,
                validator: &implementation,
            },
            &mut SourceHashCache::default(),
        )
        .unwrap()
    }

    #[test]
    fn exact_own_permit_reuses_receipt_validation_without_sh_or_install_journal_bypass() {
        let f = Fixture::new();
        let reader = f.reader();
        let locks = f.locks();
        let build = locks.try_build_exclusive().unwrap();
        let write = build.try_legacy_write_content().unwrap();
        let plan = f.qualify();
        let mut e = Epoch::begin(&build, &write, &plan, "epoch", ok).unwrap();
        let unit = prepared();
        assert!(matches!(
            reader.receipt_status(&build, &unit),
            Err(InstallError::Lock(LockError::LegacyEpochIncomplete))
        ));
        let other = Fixture::new();
        let other_locks = other.locks();
        let other_build = other_locks.try_build_exclusive().unwrap();
        let other_write = other_build.try_legacy_write_content().unwrap();
        {
            let permit = e.permit();
            assert!(matches!(
                reader.receipt_status_exclusive(&build, &write, &permit, &unit),
                Ok(CurrentStatus::NotMaterialized)
            ));
            assert!(permit.verify(&other_build, &other_write).is_err());
            f.fs()
                .replace_metadata(INSTALL_JOURNAL, b"damaged install journal")
                .unwrap();
            assert!(
                reader
                    .receipt_status_exclusive(&build, &write, &permit, &unit)
                    .is_err()
            );
        }
        assert_eq!(
            f.fs().read(INSTALL_JOURNAL).unwrap(),
            b"damaged install journal"
        );
        // Fixture-only removal of its own injected journal; production never bypasses it.
        let own = f.fs().observe(INSTALL_JOURNAL).unwrap().unwrap();
        f.fs().remove_owned(INSTALL_JOURNAL, &own).unwrap();
        settle_both(&f, &mut e);
        let proof = f.final_proof(&e.record);
        e.finish(proof, ok).unwrap();
    }
}
