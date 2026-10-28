//! Per-unit immutable result publication. B3 installs and B4 root policy are separate.
#[path = "zen_cook.rs"]
pub mod zen_cook;
use crate::groups::{
    OutputGroupContract, PlanRoster, RecordedGroupIdentity, StoredOutputGroup, ValidatedGroup,
    recorded_identity, restore_recorded, validate_frozen,
};
use crate::keys::{PreparedUnit, canonical_bytes, normalized_mode};
use crate::leases::{LeaseRecord, LeaseStore, ProcessIdentity, directory, sync_dir};
use crate::paths::{Claims, claim, relative_path};
use crate::schema::{
    Destination, Item, Provenance, RESULT_SCHEMA_VERSION, ResultRecord, StoredFile, StoredItem,
};
use crate::store::{ObjectDigest, ObjectStore, PreparedObject, StoreError};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::fs::{self, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};

pub const ENVELOPE_VERSION: u32 = 1;
pub type OutputSources = BTreeMap<(String, String), PathBuf>;
pub(crate) type GroupSources = BTreeMap<(String, String), PathBuf>;
pub type GroupHit = (ResultEnvelope, BTreeMap<String, ValidatedGroup>);
#[derive(Clone, Debug)]
pub struct ActualOutput {
    pub path: String,
    pub source: PathBuf,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ResultEnvelope {
    pub version: u32,
    pub result: ResultRecord,
    /// Retention links, never semantic inputs or winner-comparison ingredients.
    /// First-winner lineage remains immutable alongside its original provenance.
    pub upstream_result_keys: BTreeSet<String>,
}

impl ResultEnvelope {
    pub fn files(&self) -> impl Iterator<Item = &StoredFile> {
        self.result
            .outputs
            .iter()
            .flat_map(|item| &item.files)
            .chain(
                self.result
                    .output_groups
                    .iter()
                    .flat_map(|group| &group.files),
            )
    }
}

/// Complete exact-key record identities, not a StoredHit or byte/staging capability.
#[derive(Debug)]
pub struct RecordedIdentities {
    envelope: ResultEnvelope,
    groups: BTreeMap<String, RecordedGroupIdentity>,
    store_root: PathBuf,
}
impl RecordedIdentities {
    pub fn result(&self) -> &ResultEnvelope {
        &self.envelope
    }
    pub fn groups(&self) -> &BTreeMap<String, RecordedGroupIdentity> {
        &self.groups
    }
}

#[derive(Debug)]
pub enum ResultError {
    Invalid(String),
    Validation(String),
    Root(String),
    Nondeterminism(String),
    Io(io::Error),
    Store(StoreError),
}
impl fmt::Display for ResultError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Invalid(reason) => write!(formatter, "invalid result: {reason}"),
            Self::Validation(reason) => write!(formatter, "output validation: {reason}"),
            Self::Root(reason) => write!(formatter, "root publication: {reason}"),
            Self::Nondeterminism(key) => {
                write!(formatter, "different outputs for result key {key}")
            }
            Self::Io(error) => error.fmt(formatter),
            Self::Store(error) => error.fmt(formatter),
        }
    }
}
impl std::error::Error for ResultError {}
impl From<io::Error> for ResultError {
    fn from(value: io::Error) -> Self {
        Self::Io(value)
    }
}
impl From<StoreError> for ResultError {
    fn from(value: StoreError) -> Self {
        Self::Store(value)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PublicationStep {
    Prepared,
    Claimed,
    ObjectPublished,
    RecordPublished,
    Rooted,
    Released,
}

#[derive(Clone, Debug)]
pub struct ResultStore {
    objects: ObjectStore,
    leases: LeaseStore,
}

/// Dropping a transaction preserves its durable claims. Recovery/GC may reclaim
/// only under the shared mutex and positive death evidence for owner AND workers.
pub struct WriteTransaction {
    store: ResultStore,
    lease: LeaseRecord,
    unit: PreparedUnit,
    provenance: Provenance,
    upstream: BTreeSet<String>,
}

/// Selected object authority borrowed from a transaction with durable digest claims.
pub struct SelectedItems<'a> {
    transaction: &'a WriteTransaction,
    allowed: BTreeSet<String>,
}
impl SelectedItems<'_> {
    pub fn clone_to(
        &self,
        digest: &ObjectDigest,
        destination: &Path,
    ) -> Result<(), crate::staging::SourceError> {
        use crate::staging::{SourceError, SourceErrorKind};
        if !self.allowed.contains(digest.as_hex()) {
            return Err(SourceError {
                kind: SourceErrorKind::Unavailable,
                digest: digest.clone(),
                message: "digest is outside selected durable claims".into(),
            });
        }
        self.transaction
            .store
            .objects
            .clone_to(digest, destination)
            .map_err(|error| {
                let kind = match &error {
                    StoreError::Io(error) if error.kind() == io::ErrorKind::NotFound => {
                        SourceErrorKind::Unavailable
                    }
                    StoreError::InvalidFile(_) => SourceErrorKind::Changed,
                    StoreError::Clone(_) => SourceErrorKind::CloneUnsupported,
                    _ => SourceErrorKind::Io,
                };
                SourceError {
                    kind,
                    digest: digest.clone(),
                    message: error.to_string(),
                }
            })
    }
}

pub struct FrozenOutput<'a> {
    pub item: &'a Item,
    pub path: &'a str,
    pub object: &'a PreparedObject,
}

/// Only stage() constructs this token, after schema and caller format validation
/// of the exact frozen snapshots which are subsequently published.
pub struct StagedResult {
    transaction: WriteTransaction,
    envelope: ResultEnvelope,
    objects: Vec<PreparedObject>,
    external_verified: bool,
    external_records: Vec<zen_cook::NativeArtifactWitness>,
}

fn invalid(reason: impl Into<String>) -> ResultError {
    ResultError::Invalid(reason.into())
}
fn digest(value: &str) -> Result<(), ResultError> {
    ObjectDigest::from_hex(value)?;
    Ok(())
}

impl ResultStore {
    pub fn open(root: impl AsRef<Path>) -> Result<Self, ResultError> {
        let objects = ObjectStore::open(root)?;
        directory(&objects.root().join("results"))?;
        let leases = LeaseStore::open(objects.root())?;
        sync_dir(objects.root())?;
        Ok(Self { objects, leases })
    }
    pub fn leases(&self) -> &LeaseStore {
        &self.leases
    }

    pub fn begin(
        &self,
        unit: &PreparedUnit,
        provenance: Provenance,
        owner: ProcessIdentity,
        workers: Vec<ProcessIdentity>,
        upstream_result_keys: BTreeSet<String>,
    ) -> Result<WriteTransaction, ResultError> {
        digest(unit.key())?;
        for key in &upstream_result_keys {
            digest(key)?;
        }
        for identity in std::iter::once(&owner).chain(workers.iter()) {
            if identity.pid == 0 || identity.boot.is_empty() || identity.started.is_empty() {
                return Err(invalid("complete process identity is required"));
            }
        }
        // The incomplete consumer record cannot yet retain its producers by traversal.
        // Protect upstream records before work starts, not just after record publication.
        let mut claimed_results = upstream_result_keys.clone();
        claimed_results.insert(unit.key().into());
        let lease = self.leases.begin(claimed_results, owner, workers)?;
        Ok(WriteTransaction {
            store: self.clone(),
            lease,
            unit: unit.clone(),
            provenance,
            upstream: upstream_result_keys,
        })
    }

    fn record_path(&self, key: &str) -> PathBuf {
        self.objects
            .root()
            .join("results")
            .join(format!("{key}.json"))
    }

    // Caller holds the metadata lock. Direct record/object lookups only; no output walk/hash.
    fn read(&self, unit: &PreparedUnit) -> Result<Option<ResultEnvelope>, ResultError> {
        Ok(self.read_validated(unit)?.map(|(envelope, _)| envelope))
    }

    // Caller holds the same result/GC mutex and a durable result-key claim.
    fn read_metadata(
        &self,
        unit: &PreparedUnit,
    ) -> Result<Option<RecordedIdentities>, ResultError> {
        let path = self.record_path(unit.key());
        match fs::symlink_metadata(&path) {
            Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
            Err(error) => return Err(error.into()),
            Ok(metadata) if !metadata.is_file() || !metadata.permissions().readonly() => {
                return Err(invalid("stored result must be regular and read-only"));
            }
            _ => {}
        }
        let envelope: ResultEnvelope =
            serde_json::from_slice(&fs::read(path)?).map_err(|e| invalid(e.to_string()))?;
        if envelope.version != ENVELOPE_VERSION
            || envelope.result.schema_version != RESULT_SCHEMA_VERSION
            || envelope.result.key != unit.key()
            || &envelope.result.ingredients != unit.ingredients()
        {
            return Err(invalid("stored result version/key/ingredients differ"));
        }
        if envelope.result.output_groups.len() != unit.ingredients().output_groups.len() {
            return Err(invalid("wrong output group count"));
        }
        let mut groups = BTreeMap::new();
        for (contract, stored) in unit
            .ingredients()
            .output_groups
            .iter()
            .zip(&envelope.result.output_groups)
        {
            groups.insert(
                contract.id.clone(),
                recorded_identity(contract, stored).map_err(invalid)?,
            );
        }
        check_manifest(unit, &envelope.result.outputs)?;
        for key in &envelope.upstream_result_keys {
            digest(key)?;
        }
        Ok(Some(RecordedIdentities {
            envelope,
            groups,
            store_root: self.objects.root().to_path_buf(),
        }))
    }

    fn read_validated(&self, unit: &PreparedUnit) -> Result<Option<GroupHit>, ResultError> {
        let Some(recorded) = self.read_metadata(unit)? else {
            return Ok(None);
        };
        let envelope = recorded.envelope;
        if envelope
            .result
            .outputs
            .iter()
            .any(|item| item.item.destination == Destination::External)
        {
            return Err(invalid(
                "external Zen lookup requires independent native verification",
            ));
        }
        let mut groups = BTreeMap::new();
        for (contract, stored) in unit
            .ingredients()
            .output_groups
            .iter()
            .zip(&envelope.result.output_groups)
        {
            let token = restore_recorded(contract, stored, |file| {
                let digest = ObjectDigest::from_hex(&file.digest).map_err(|e| e.to_string())?;
                self.objects
                    .check_recorded(&digest, file.size)
                    .map_err(|e| e.to_string())
            })
            .map_err(invalid)?;
            groups.insert(contract.id.clone(), token);
        }
        for file in envelope.result.outputs.iter().flat_map(|item| &item.files) {
            self.objects
                .check_recorded(&ObjectDigest::from_hex(&file.digest)?, file.size)?;
        }
        Ok(Some((envelope, groups)))
    }
}

pub(crate) fn partition_outputs(
    unit: &PreparedUnit,
    actual: Vec<ActualOutput>,
) -> Result<(OutputSources, GroupSources), ResultError> {
    let mut fixed = BTreeMap::new();
    for item in &unit.ingredients().logical_outputs {
        for file in &item.files {
            if fixed.insert(file.path.clone(), item.id.clone()).is_some() {
                return Err(invalid("duplicate fixed output owners"));
            }
        }
    }
    crate::groups::validate_ownership(
        &unit.ingredients().output_groups,
        &fixed.keys().cloned().collect::<Vec<_>>(),
    )
    .map_err(invalid)?;
    let mut claims = Claims::new();
    let mut fixed_sources = BTreeMap::new();
    let mut group_sources = BTreeMap::new();
    for output in actual {
        relative_path(&output.path, true).map_err(invalid)?;
        claim(&mut claims, &output.path, "actual output").map_err(invalid)?;
        if let Some(item) = fixed.get(&output.path) {
            fixed_sources.insert((item.clone(), output.path), output.source);
            continue;
        }
        let mut owner = None;
        for contract in &unit.ingredients().output_groups {
            let prefix = contract.root.clone() + "/";
            if let Some(member) = output.path.strip_prefix(prefix.as_str()) {
                if owner.is_some() {
                    return Err(invalid("actual output has multiple group owners"));
                }
                owner = Some((contract.id.clone(), member.to_string()));
            }
        }
        let owner = owner.ok_or_else(|| invalid("unknown actual output path"))?;
        group_sources.insert(owner, output.source);
    }
    Ok((fixed_sources, group_sources))
}

fn check_manifest(unit: &PreparedUnit, outputs: &[StoredItem]) -> Result<(), ResultError> {
    let expected = &unit.ingredients().logical_outputs;
    if outputs.len() != expected.len() {
        return Err(invalid("wrong output item count"));
    }
    for (item, stored) in expected.iter().zip(outputs) {
        if item.destination == Destination::External {
            let locator = zen_cook::CookLocator::decode(
                stored
                    .external_locator
                    .as_deref()
                    .ok_or_else(|| invalid("missing native Zen locator"))?,
            )
            .map_err(invalid)?;
            if item != &stored.item || !stored.files.is_empty() || !locator.matches(unit, item) {
                return Err(invalid(
                    "external cook manifest differs from its declared source/package",
                ));
            }
            continue;
        }
        if item != &stored.item || stored.external_locator.is_some() {
            return Err(invalid(
                "output declaration differs or requires external adapter",
            ));
        }
        let mut seen = BTreeSet::new();
        for file in &stored.files {
            digest(&file.digest)?;
            if !seen.insert(file.path.clone())
                || !item.files.iter().any(|expected| expected.path == file.path)
                || ![0o644, 0o755].contains(&file.mode)
            {
                return Err(invalid("undeclared/duplicate output or invalid mode"));
            }
        }
        if item
            .files
            .iter()
            .any(|file| file.required && !seen.contains(&file.path))
        {
            return Err(invalid("missing required output"));
        }
    }
    Ok(())
}

pub(crate) type FrozenParts = (Vec<StoredItem>, Vec<StoredOutputGroup>, Vec<PreparedObject>);

// Both local completion and cache staging use exactly the same full membership/format checks.
pub(crate) fn freeze_partitioned(
    unit: &PreparedUnit,
    mut sources: OutputSources,
    mut group_sources: GroupSources,
    validator: impl FnOnce(&[FrozenOutput<'_>]) -> Result<(), String>,
    mut group_validator: impl FnMut(
        &OutputGroupContract,
        &PlanRoster,
        &BTreeMap<String, &PreparedObject>,
    ) -> Result<(), String>,
    mut freeze: impl FnMut(&Path) -> Result<PreparedObject, ResultError>,
) -> Result<FrozenParts, ResultError> {
    let mut outputs = vec![];
    let mut objects = vec![];
    let mut labels = vec![];
    for item in &unit.ingredients().logical_outputs {
        if item.destination == Destination::External {
            return Err(invalid("external result needs its adapter"));
        }
        let mut files = vec![];
        for file in &item.files {
            let key = (item.id.clone(), file.path.clone());
            let Some(source) = sources.remove(&key) else {
                if file.required {
                    return Err(invalid(format!("missing output {}", file.path)));
                }
                continue;
            };
            let object = freeze(&source)?;
            files.push(StoredFile {
                path: file.path.clone(),
                digest: object.digest().to_string(),
                size: object.size(),
                mode: normalized_mode(object.source_mode()),
            });
            labels.push((item, file.path.as_str()));
            objects.push(object);
        }
        outputs.push(StoredItem {
            item: item.clone(),
            files,
            external_locator: None,
        });
    }
    if !sources.is_empty() {
        return Err(invalid("undeclared output sources"));
    }
    let frozen: Vec<_> = labels
        .iter()
        .zip(&objects)
        .map(|((item, path), object)| FrozenOutput { item, path, object })
        .collect();
    validator(&frozen).map_err(ResultError::Validation)?;
    drop(frozen);
    drop(labels);
    let mut output_groups = Vec::new();
    for contract in &unit.ingredients().output_groups {
        let names: Vec<_> = group_sources
            .keys()
            .filter(|(group, _)| group == &contract.id)
            .cloned()
            .collect();
        if names.len() as u64
            > contract
                .max_pieces
                .checked_add(1)
                .ok_or_else(|| invalid("group member count overflow"))?
        {
            return Err(invalid("group member count budget exceeded"));
        }
        let mut declared_bytes = 0u64;
        for key in &names {
            let size = fs::symlink_metadata(&group_sources[key])?.len();
            if size > contract.max_member_bytes {
                return Err(invalid("group member byte budget exceeded"));
            }
            declared_bytes = declared_bytes
                .checked_add(size)
                .ok_or_else(|| invalid("group byte count overflow"))?;
        }
        if declared_bytes > contract.max_total_bytes {
            return Err(invalid("group byte budget exceeded"));
        }
        let mut indices = BTreeMap::new();
        for (group, path) in names {
            let source = group_sources.remove(&(group, path.clone())).unwrap();
            let object = freeze(&source)?;
            indices.insert(path, objects.len());
            objects.push(object);
        }
        let members: BTreeMap<_, _> = indices
            .iter()
            .map(|(path, index)| (path.clone(), &objects[*index]))
            .collect();
        let token = validate_frozen(contract, &members, |roster, objects| {
            group_validator(contract, roster, objects)
        })
        .map_err(ResultError::Validation)?;
        output_groups.push(token.stored().clone());
    }
    if !group_sources.is_empty() {
        return Err(invalid("unknown output group sources"));
    }
    Ok((outputs, output_groups, objects))
}

impl WriteTransaction {
    pub(crate) fn objects_root(&self) -> &Path {
        self.store.objects.root()
    }
    pub fn lease(&self) -> &LeaseRecord {
        &self.lease
    }

    /// A lifecycle adapter must persist a newly launched worker's full identity
    /// before allowing that worker to write. Startup barriers/process probing are C5b/C7.
    pub fn add_worker(&mut self, worker: ProcessIdentity) -> Result<(), ResultError> {
        if worker.pid == 0 || worker.boot.is_empty() || worker.started.is_empty() {
            return Err(invalid("complete worker identity is required"));
        }
        if !self.lease.workers.contains(&worker) {
            let guard = self.store.leases.lock()?;
            let mut updated = self.lease.clone();
            updated.workers.push(worker);
            guard.save(&updated)?;
            self.lease = updated;
        }
        Ok(())
    }

    /// Pin every named object under the GC mutex before returning a hit.
    /// Complete with retain_hit(); dropping this handle conservatively retains claims.
    pub fn lookup(&mut self) -> Result<Option<ResultEnvelope>, ResultError> {
        Ok(self.lookup_groups()?.map(|(envelope, _)| envelope))
    }

    /// @cc [owner:fontanierh,label:correctness] recorded-identities-before-availability
    /// An exact-key metadata lookup MUST reuse complete record/ingredient/manifest checks and
    /// hold the existing result-key claim under the shared GC mutex. It MUST NOT open/check
    /// payload objects, mint StoredHit/available groups, substitute producer keys for content,
    /// or bypass adapter metadata validation. Strict lookup_groups remains unchanged.
    /// See tests/results.rs; A9 still chooses when real bytes must be materialized.
    pub fn lookup_recorded(&mut self) -> Result<Option<RecordedIdentities>, ResultError> {
        let _guard = self.store.leases.lock()?;
        self.store.read_metadata(&self.unit)
    }

    fn check_recorded_token(&self, recorded: &RecordedIdentities) -> Result<(), ResultError> {
        if recorded.store_root != self.store.objects.root()
            || recorded.envelope.result.key != self.unit.key()
            || &recorded.envelope.result.ingredients != self.unit.ingredients()
        {
            return Err(invalid(
                "recorded token belongs to another store or prepared unit",
            ));
        }
        Ok(())
    }

    /// Pin only requested fixed items. Unselected producer objects are never probed.
    /// Claims MUST be durable under the shared GC mutex before selected authority escapes.
    pub fn pin_recorded_items(
        &mut self,
        recorded: &RecordedIdentities,
        item_ids: &[&str],
    ) -> Result<SelectedItems<'_>, ResultError> {
        self.check_recorded_token(recorded)?;
        let guard = self.store.leases.lock()?;
        let mut allowed = BTreeSet::new();
        let mut selected = BTreeSet::new();
        for id in item_ids {
            if !selected.insert(*id) {
                return Err(invalid("duplicate selected item"));
            }
            let item = recorded
                .envelope
                .result
                .outputs
                .iter()
                .find(|item| item.item.id == *id)
                .ok_or_else(|| invalid("selected item is absent from recorded result"))?;
            if item.external_locator.is_some() {
                return Err(invalid("external item has no CAS source"));
            }
            for file in &item.files {
                self.store
                    .objects
                    .check_recorded(&ObjectDigest::from_hex(&file.digest)?, file.size)?;
                allowed.insert(file.digest.clone());
            }
        }
        let mut updated = self.lease.clone();
        updated.object_digests.extend(allowed.iter().cloned());
        guard.save(&updated)?;
        self.lease = updated;
        Ok(SelectedItems {
            transaction: self,
            allowed,
        })
    }

    /// Expose only digest claims already held by this transaction, without reopening another store.
    pub fn pinned_objects(&self) -> SelectedItems<'_> {
        SelectedItems {
            transaction: self,
            allowed: self.lease.object_digests.clone(),
        }
    }

    /// Root checked metadata without claiming that any payload is available.
    /// Root failure MUST retain claims; successful rooting precedes claim release.
    pub fn retain_recorded(
        mut self,
        recorded: &RecordedIdentities,
        root: impl FnOnce(&ResultEnvelope) -> Result<(), String>,
    ) -> Result<ResultEnvelope, ResultError> {
        self.check_recorded_token(recorded)?;
        root(&recorded.envelope).map_err(ResultError::Root)?;
        self.release()?;
        Ok(recorded.envelope.clone())
    }

    pub(crate) fn release_sources(&mut self) -> Result<(), ResultError> {
        self.release()
    }

    /// Private tokens escape only after all named blobs are checked and durably pinned
    /// under the same GC mutex. No plan bytes, hash or output-tree walk on a hit.
    pub fn lookup_groups(&mut self) -> Result<Option<GroupHit>, ResultError> {
        let guard = self.store.leases.lock()?;
        let result = self.store.read_validated(&self.unit)?;
        if let Some((envelope, _)) = &result {
            let mut updated = self.lease.clone();
            updated
                .object_digests
                .extend(envelope.files().map(|file| file.digest.clone()));
            guard.save(&updated)?;
            self.lease = updated;
        }
        Ok(result)
    }

    /// @cc [owner:fontanierh,label:correctness] independently-verified-external-cook
    /// External cook publication MUST require an actual fixed normal cook producer's
    /// sealed completion consumed as a typed NativeCookRecord, plus the independent
    /// native restore verifier's sealed completion and exact record-byte/source/package/
    /// native-key binding. Recorded dependency keys or input-key echoes alone MUST NOT
    /// prove source origin. Both producer and verifier records MUST be complete and
    /// persisted, with the retained native record immutable and owned by v2.
    /// Unknown locators and generic writer reports MUST NOT grant lookup or publication.
    /// The retained native bytes and lifetime marker MUST be rechecked at publication.
    /// Stage one independently native-verified external package result. No files or
    /// opaque locator/report callbacks are accepted on this boundary.
    pub fn stage_external(
        mut self,
        proofs: &[zen_cook::VerifiedPackage<'_>],
    ) -> Result<StagedResult, ResultError> {
        if !self.unit.ingredients().output_groups.is_empty()
            || proofs.len() != self.unit.ingredients().logical_outputs.len()
            || proofs.is_empty()
        {
            return Err(invalid("external cook requires an exact fixed package set"));
        }
        let mut outputs = Vec::new();
        for (item, proof) in self.unit.ingredients().logical_outputs.iter().zip(proofs) {
            proof.check().map_err(ResultError::Validation)?;
            proof
                .validate_store_layout(self.store.objects.root())
                .map_err(ResultError::Validation)?;
            if proof.item() != item || !proof.locator().matches(&self.unit, item) {
                return Err(invalid(
                    "independent native proof binds another source/package",
                ));
            }
            // The native verification record must already be durably stored. A
            // local writer report or a lost report publication grants no locator.
            for expected in [proof.producer_report(), proof.report()] {
                let proof_path = self.store.record_path(&expected.result.key);
                let metadata = fs::symlink_metadata(&proof_path)?;
                if !metadata.is_file() || !metadata.permissions().readonly() {
                    return Err(invalid(
                        "native producer/verification record is not immutable",
                    ));
                }
                let persisted: ResultEnvelope = serde_json::from_slice(&fs::read(proof_path)?)
                    .map_err(|error| invalid(error.to_string()))?;
                if persisted.version != ENVELOPE_VERSION
                    || persisted.result.schema_version != RESULT_SCHEMA_VERSION
                    || persisted.result.key != expected.result.key
                    || persisted.result.outputs != expected.result.outputs
                    || persisted.result.ingredients != expected.result.ingredients
                {
                    return Err(invalid(
                        "native producer/verification record differs from its frozen proof",
                    ));
                }
                for file in persisted.files() {
                    self.store
                        .objects
                        .check_recorded(&ObjectDigest::from_hex(&file.digest)?, file.size)?;
                }
            }
            self.upstream.insert(proof.proof_key().to_string());
            self.upstream.insert(proof.producer_key().to_string());
            outputs.push(StoredItem {
                item: item.clone(),
                files: Vec::new(),
                external_locator: Some(proof.locator().encode().map_err(invalid)?),
            });
        }
        // Retain the independently verified report before publishing its consumer.
        {
            let guard = self.store.leases.lock()?;
            let mut lease = self.lease.clone();
            lease.result_keys.extend(self.upstream.iter().cloned());
            guard.save(&lease)?;
            self.lease = lease;
        }
        check_manifest(&self.unit, &outputs)?;
        let envelope = ResultEnvelope {
            version: ENVELOPE_VERSION,
            result: ResultRecord {
                schema_version: RESULT_SCHEMA_VERSION,
                unit: self.unit.request("", "").unit,
                key: self.unit.key().into(),
                ingredients: self.unit.ingredients().clone(),
                outputs,
                output_groups: Vec::new(),
                provenance: self.provenance.clone(),
            },
            upstream_result_keys: self.upstream.clone(),
        };
        Ok(StagedResult {
            transaction: self,
            envelope,
            objects: Vec::new(),
            external_verified: true,
            external_records: proofs.iter().map(|proof| proof.witness()).collect(),
        })
    }

    /// Generic lookup keeps external records unavailable. The caller must supply
    /// the fixed native verifier's current independently certified package proof.
    pub fn lookup_external(
        &mut self,
        proofs: &[zen_cook::VerifiedPackage<'_>],
    ) -> Result<Option<ResultEnvelope>, ResultError> {
        let guard = self.store.leases.lock()?;
        let Some(recorded) = self.store.read_metadata(&self.unit)? else {
            return Ok(None);
        };
        drop(guard);
        let envelope = recorded.envelope;
        if envelope.result.outputs.len() != proofs.len() || proofs.is_empty() {
            return Err(invalid("missing exact independent Zen proofs"));
        }
        for (output, proof) in envelope.result.outputs.iter().zip(proofs) {
            proof.check().map_err(ResultError::Validation)?;
            proof
                .validate_store_layout(self.store.objects.root())
                .map_err(ResultError::Validation)?;
            if &output.item != proof.item()
                || !proof.locator().matches(&self.unit, &output.item)
                || output.external_locator.as_deref()
                    != Some(proof.locator().encode().map_err(invalid)?.as_str())
            {
                return Err(invalid("native Zen lookup differs from the stored result"));
            }
        }
        Ok(Some(envelope))
    }

    /// Validates exact output membership, freezes each file once, then asks the op
    /// validator to inspect those same bytes. No publication happens on validation failure.
    /// Fixed-only compatibility entrypoint. Group units require the complete actual list.
    pub fn stage(
        self,
        sources: OutputSources,
        validator: impl FnOnce(&[FrozenOutput<'_>]) -> Result<(), String>,
    ) -> Result<StagedResult, ResultError> {
        if !self.unit.ingredients().output_groups.is_empty() {
            return Err(invalid(
                "group outputs require stage_groups with complete actual membership",
            ));
        }
        self.stage_partitioned(sources, BTreeMap::new(), validator, |_, _, _| {
            Err("undeclared group".into())
        })
    }

    /// C1b supplies ALL actual fixed+group files, including unexpected members.
    /// Partition exactly once; this controller does not rescan a live output tree.
    pub fn stage_groups(
        self,
        actual: Vec<ActualOutput>,
        fixed_validator: impl FnOnce(&[FrozenOutput<'_>]) -> Result<(), String>,
        group_validator: impl FnMut(
            &OutputGroupContract,
            &PlanRoster,
            &BTreeMap<String, &PreparedObject>,
        ) -> Result<(), String>,
    ) -> Result<StagedResult, ResultError> {
        let (fixed, groups) = partition_outputs(&self.unit, actual)?;
        self.stage_partitioned(fixed, groups, fixed_validator, group_validator)
    }

    fn stage_partitioned(
        self,
        sources: OutputSources,
        group_sources: GroupSources,
        validator: impl FnOnce(&[FrozenOutput<'_>]) -> Result<(), String>,
        group_validator: impl FnMut(
            &OutputGroupContract,
            &PlanRoster,
            &BTreeMap<String, &PreparedObject>,
        ) -> Result<(), String>,
    ) -> Result<StagedResult, ResultError> {
        let (outputs, output_groups, objects) = freeze_partitioned(
            &self.unit,
            sources,
            group_sources,
            validator,
            group_validator,
            |source| {
                self.store
                    .objects
                    .prepare_in(source, &self.store.objects.root().join(&self.lease.staging))
                    .map_err(ResultError::Store)
            },
        )?;
        let envelope = ResultEnvelope {
            version: ENVELOPE_VERSION,
            result: ResultRecord {
                schema_version: RESULT_SCHEMA_VERSION,
                unit: self.unit.request("", "").unit,
                key: self.unit.key().into(),
                ingredients: self.unit.ingredients().clone(),
                outputs,
                output_groups,
                provenance: self.provenance.clone(),
            },
            upstream_result_keys: self.upstream.clone(),
        };
        check_manifest(&self.unit, &envelope.result.outputs)?;
        Ok(StagedResult {
            transaction: self,
            envelope,
            objects,
            external_verified: false,
            external_records: Vec::new(),
        })
    }

    #[cfg(any(target_os = "macos", target_os = "linux"))]
    pub(crate) fn stage_completion(
        self,
        completion: &crate::completion::FrozenCompletion,
    ) -> Result<StagedResult, ResultError> {
        let envelope = completion.result();
        if envelope.result.key != self.unit.key()
            || &envelope.result.ingredients != self.unit.ingredients()
        {
            return Err(ResultError::Validation(
                "original cache ticket differs from sealed completion key/ingredients".into(),
            ));
        }
        let certified = completion
            .certified_objects()
            .map_err(ResultError::Validation)?;
        // Detect known nondeterminism from complete recorded metadata even when winner blobs vanished.
        let winner = {
            let _guard = self.store.leases.lock()?;
            self.store.read_metadata(&self.unit)?
        };
        if let Some(winner) = winner {
            if winner.envelope.result.outputs != envelope.result.outputs
                || winner.envelope.result.output_groups != envelope.result.output_groups
            {
                return Err(ResultError::Nondeterminism(self.unit.key().into()));
            }
        }
        let mut objects = vec![];
        for object in certified {
            match self
                .store
                .objects
                .adopt_in(object, &self.store.objects.root().join(&self.lease.staging))
            {
                Ok(adopted) => objects.push(adopted),
                Err(error) => {
                    object.check_frozen().map_err(|source| {
                        ResultError::Validation(format!(
                            "local snapshot lost certification: {source}"
                        ))
                    })?;
                    return Err(ResultError::Store(error));
                }
            }
        }
        let mut envelope = envelope.clone();
        // Retention is nonsemantic; preserve the original miss ticket's already-protected lineage.
        envelope.upstream_result_keys = self.upstream.clone();
        Ok(StagedResult {
            transaction: self,
            envelope,
            objects,
            external_verified: false,
            external_records: Vec::new(),
        })
    }

    pub fn retain_hit(
        mut self,
        root: impl FnOnce(&ResultEnvelope) -> Result<(), String>,
    ) -> Result<ResultEnvelope, ResultError> {
        let winner = self
            .lookup()?
            .ok_or_else(|| invalid("result is not a hit"))?;
        root(&winner).map_err(ResultError::Root)?;
        self.release()?;
        Ok(winner)
    }

    fn release(&mut self) -> Result<(), ResultError> {
        let guard = self.store.leases.lock()?;
        let mut updated = self.lease.clone();
        updated.result_keys.clear();
        updated.object_digests.clear();
        updated.rooted = true;
        guard.save(&updated)?;
        self.lease = updated;
        Ok(())
    }
}

impl StagedResult {
    pub fn envelope(&self) -> &ResultEnvelope {
        &self.envelope
    }

    pub fn publish(
        self,
        root: impl FnOnce(&ResultEnvelope) -> Result<(), String>,
    ) -> Result<ResultEnvelope, ResultError> {
        self.publish_observed(root, |_| Ok(()))
    }

    /// @cc [owner:fontanierh,label:correctness] leased-result-publication
    /// Publication MUST durably claim object names under the shared GC mutex before
    /// publishing objects, then publish the immutable first-winner record, call the
    /// required durable root callback, and only then release per-unit claims. Faults
    /// before durable rooting MUST preserve claims; no fault may erase earlier results.
    /// Equality MUST compare complete fixed and group manifests/projections, but ignore unit
    /// labels, provenance and upstream retention links. See tests/results.rs.
    pub fn publish_observed(
        mut self,
        root: impl FnOnce(&ResultEnvelope) -> Result<(), String>,
        mut observe: impl FnMut(PublicationStep) -> io::Result<()>,
    ) -> Result<ResultEnvelope, ResultError> {
        observe(PublicationStep::Prepared)?;
        for witness in &self.external_records {
            witness.check().map_err(ResultError::Validation)?;
        }
        {
            let guard = self.transaction.store.leases.lock()?;
            let mut updated = self.transaction.lease.clone();
            updated.object_digests.extend(
                self.objects
                    .iter()
                    .map(|object| object.digest().to_string()),
            );
            guard.save(&updated)?;
            self.transaction.lease = updated;
        }
        observe(PublicationStep::Claimed)?;
        for object in self.objects.drain(..) {
            {
                let _guard = self.transaction.store.leases.lock()?;
                self.transaction.store.objects.publish(object)?;
            }
            observe(PublicationStep::ObjectPublished)?;
        }
        let winner = {
            let _guard = self.transaction.store.leases.lock()?;
            let previous = if self.external_verified {
                self.transaction
                    .store
                    .read_metadata(&self.transaction.unit)?
                    .map(|recorded| recorded.envelope)
            } else {
                self.transaction.store.read(&self.transaction.unit)?
            };
            match previous {
                Some(winner) => {
                    // The producing input key is equal; compare full semantic output view.
                    if winner.result.outputs != self.envelope.result.outputs
                        || winner.result.output_groups != self.envelope.result.output_groups
                    {
                        return Err(ResultError::Nondeterminism(
                            self.envelope.result.key.clone(),
                        ));
                    }
                    winner
                }
                None => {
                    for witness in &self.external_records {
                        witness.check().map_err(ResultError::Validation)?;
                    }
                    self.save_record()?;
                    self.envelope.clone()
                }
            }
        };
        observe(PublicationStep::RecordPublished)?;
        root(&winner).map_err(ResultError::Root)?;
        observe(PublicationStep::Rooted)?;
        self.transaction.release()?;
        observe(PublicationStep::Released)?;
        Ok(winner)
    }

    fn save_record(&self) -> Result<(), ResultError> {
        let scope = self
            .transaction
            .store
            .objects
            .root()
            .join(&self.transaction.lease.staging);
        let path = scope.join("result.json");
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&path)?;
        file.write_all(&canonical_bytes(&self.envelope).map_err(invalid)?)?;
        let mut permissions = file.metadata()?.permissions();
        permissions.set_readonly(true);
        file.set_permissions(permissions)?;
        file.sync_all()?;
        let destination = self
            .transaction
            .store
            .record_path(&self.envelope.result.key);
        // Same filesystem, atomic no-replace link. Unlike rename, existing names never
        // change. This links immutable metadata only, never mutable payload/output files.
        fs::hard_link(&path, &destination)?;
        sync_dir(destination.parent().unwrap())?;
        fs::remove_file(&path)?;
        sync_dir(&scope)?;
        Ok(())
    }
}
