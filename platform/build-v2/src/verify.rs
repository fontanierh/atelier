//! Read-only offline verification of stored result records, output manifests and payload objects.
//!
//! Normal lookup (results::WriteTransaction::lookup) and restoration (store::ObjectStore::clone_to)
//! check metadata and clone without rehashing payload bytes. This verifier is opt-in: it pins
//! inspected result keys and object digests through leases::LeaseStore under the shared metadata
//! mutex, rehashes actual object bytes from disk bypassing hints, and classifies missing, corrupt,
//! malformed, incomplete, unsupported, external and unverified entries separately.
use crate::keys::{KEY_ENCODING_VERSION, PreparedUnit, canonical_bytes};
use crate::leases::{LeaseRecord, LeaseStore, ProcessIdentity, directory};
use crate::paths::{Claims, claim, logical_path, relative_path};
use crate::results::{ENVELOPE_VERSION, ResultEnvelope};
use crate::schema::{
    ContentIdentity, Destination, IdentityIngredients, InputKind, Item, StoredItem,
};

/// Fixed-manifest verifier schema version. A future bump of RESULT_SCHEMA_VERSION (e.g. v3
/// dynamic output_groups) must not be inherited silently without updating group verification.
use crate::schema::RESULT_SCHEMA_VERSION;
use crate::source_hashes::{sha256, valid_digest};
use crate::store::{OBJECT_ALGORITHM, ObjectDigest, ObjectStore, StoreError};
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::fs::{self, File};
use std::io::{self, Read};
use std::path::{Path, PathBuf};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SampleSpec {
    pub seed: u64,
    pub max_results: usize,
    pub max_objects: usize,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum VerificationMode {
    Full,
    Sampled(SampleSpec),
}

#[derive(Clone, Debug, Default)]
pub struct VerificationTarget<'a> {
    pub units: Vec<&'a PreparedUnit>,
    pub result_keys: BTreeSet<String>,
    pub objects: BTreeMap<String, Option<u64>>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SamplePlan {
    pub seed: u64,
    pub candidate_records: Vec<String>,
    pub selected_records: Vec<String>,
    pub skipped_records: Vec<String>,
    pub candidate_objects: Vec<String>,
    pub selected_objects: Vec<String>,
    pub skipped_objects: Vec<String>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ObjectCorruption {
    NotRegularFile,
    WritableObject,
    Truncated {
        expected_size: u64,
        actual_size: u64,
        actual_digest: String,
    },
    SizeMismatch {
        expected_size: u64,
        actual_size: u64,
        actual_digest: String,
    },
    DigestMismatch {
        expected_digest: String,
        actual_digest: String,
        size: u64,
    },
    ReadFailed(String),
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum UnverifiedReason {
    SampleSkipped,
    ExternalDestination {
        item_id: String,
        logical_path: String,
        locator: Option<String>,
    },
    UnverifiedObjects {
        digests: Vec<String>,
    },
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ObjectOutcome {
    Verified {
        digest: String,
        size: u64,
    },
    Missing {
        digest: String,
    },
    Corrupt {
        digest: String,
        reason: ObjectCorruption,
    },
    Malformed {
        digest: String,
        reason: String,
    },
    Unverified {
        digest: String,
        reason: UnverifiedReason,
    },
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ManifestDefect {
    ItemCountMismatch { expected: usize, actual: usize },
    ItemDeclarationMismatch { item_id: String },
    EmptyItemFiles { item_id: String },
    MissingRequiredFile { item_id: String, path: String },
    UndeclaredFile { item_id: String, path: String },
    DuplicateFile { item_id: String, path: String },
    OverlappingCheckoutInstall { first: String, second: String },
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum UnsupportedReason {
    EnvelopeVersion(u32),
    ResultSchemaVersion(u32),
    OutputGroupsUnsupported,
    ExternalWithoutLocator {
        item_id: String,
        logical_path: String,
    },
    ExternalFilesPresent {
        item_id: String,
    },
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum RecordCorruption {
    NotRegularOrWritableRecord,
    ReadFailed(String),
    KeyMismatch {
        requested_key: String,
        record_key: String,
    },
    IngredientsKeyMismatch {
        record_key: String,
        computed_key: String,
    },
    PreparedUnitMismatch {
        reason: String,
    },
    CorruptObjects {
        digests: Vec<String>,
    },
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ExternalItemReport {
    pub item_id: String,
    pub logical_path: String,
    pub locator: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum RecordOutcome {
    Verified {
        key: String,
        unit: String,
        objects_verified: usize,
        bytes_hashed: u64,
    },
    Missing {
        key: String,
    },
    MissingObjects {
        key: String,
        missing_digests: Vec<String>,
    },
    Corrupt {
        key: String,
        reason: RecordCorruption,
    },
    Malformed {
        key: String,
        reason: String,
    },
    IncompleteManifest {
        key: String,
        defect: ManifestDefect,
    },
    Unsupported {
        key: String,
        reason: UnsupportedReason,
    },
    External {
        key: String,
        items: Vec<ExternalItemReport>,
    },
    Unverified {
        key: String,
        reason: UnverifiedReason,
    },
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct VerificationCounts {
    pub verified_records: usize,
    pub missing_records: usize,
    pub corrupt_records: usize,
    pub malformed_records: usize,
    pub incomplete_manifests: usize,
    pub unsupported_records: usize,
    pub external_records: usize,
    pub unverified_records: usize,
    pub verified_objects: usize,
    pub missing_objects: usize,
    pub corrupt_objects: usize,
    pub malformed_objects: usize,
    pub unverified_objects: usize,
    pub bytes_hashed: u64,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct VerificationReport {
    pub lease_id: String,
    pub mode: VerificationMode,
    pub sample: Option<SamplePlan>,
    pub records: BTreeMap<String, RecordOutcome>,
    pub objects: BTreeMap<String, ObjectOutcome>,
    pub counts: VerificationCounts,
}

impl VerificationReport {
    /// @cc [owner:fontanierh,label:correctness] build-v2-unknown-integrity-not-verified
    /// Sample-skipped entries, external Zen locators lacking the fixed independent native
    /// verifier's sealed proof, and unsupported versions MUST be reported separately as
    /// Unverified, External or Unsupported and MUST NEVER be treated as verified success. Only a non-empty audit where every inspected record and object is
    /// Verified may report overall verification success.
    pub fn is_all_verified(&self) -> bool {
        if self.records.is_empty() && self.objects.is_empty() {
            return false;
        }
        self.counts.missing_records == 0
            && self.counts.corrupt_records == 0
            && self.counts.malformed_records == 0
            && self.counts.incomplete_manifests == 0
            && self.counts.unsupported_records == 0
            && self.counts.external_records == 0
            && self.counts.unverified_records == 0
            && self.counts.missing_objects == 0
            && self.counts.corrupt_objects == 0
            && self.counts.malformed_objects == 0
            && self.counts.unverified_objects == 0
            && (self.counts.verified_records > 0 || self.counts.verified_objects > 0)
    }
}

#[derive(Debug)]
pub enum VerifyError {
    InvalidOwner,
    Io(io::Error),
    Store(StoreError),
}

impl fmt::Display for VerifyError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidOwner => {
                formatter.write_str("complete owner process identity is required for verification")
            }
            Self::Io(error) => error.fmt(formatter),
            Self::Store(error) => error.fmt(formatter),
        }
    }
}

impl std::error::Error for VerifyError {}

impl From<io::Error> for VerifyError {
    fn from(value: io::Error) -> Self {
        Self::Io(value)
    }
}

impl From<StoreError> for VerifyError {
    fn from(value: StoreError) -> Self {
        Self::Store(value)
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum VerifyStep<'a> {
    LeasePinned(&'a LeaseRecord),
    ManifestObjectsPinned {
        result_key: &'a str,
        lease: &'a LeaseRecord,
    },
    ObjectHashed {
        digest: &'a str,
        size: u64,
    },
    Released(&'a LeaseRecord),
}

struct PinGuard<'a> {
    leases: &'a LeaseStore,
    root: &'a Path,
    lease: LeaseRecord,
    released: bool,
}

impl<'a> PinGuard<'a> {
    fn new(leases: &'a LeaseStore, root: &'a Path, lease: LeaseRecord) -> Self {
        Self {
            leases,
            root,
            lease,
            released: false,
        }
    }

    fn pin_objects(&mut self, digests: impl IntoIterator<Item = String>) -> io::Result<()> {
        let guard = self.leases.lock()?;
        let mut changed = false;
        for digest in digests {
            if valid_digest(&digest) && self.lease.object_digests.insert(digest) {
                changed = true;
            }
        }
        if changed {
            guard.save(&self.lease)?;
        }
        Ok(())
    }

    fn release(&mut self) -> io::Result<()> {
        if self.released {
            return Ok(());
        }
        let guard = self.leases.lock()?;
        self.lease.result_keys.clear();
        self.lease.object_digests.clear();
        self.lease.rooted = true;
        guard.save(&self.lease)?;
        // LeaseStore::begin reserves an empty staging/<id> directory for lease validation.
        // The read-only verifier never writes inside it and removes the empty directory on release.
        let _ = fs::remove_dir(self.root.join(&self.lease.staging));
        self.released = true;
        Ok(())
    }
}

impl Drop for PinGuard<'_> {
    fn drop(&mut self) {
        let _ = self.release();
    }
}

#[derive(Clone, Debug)]
pub struct Verifier {
    objects: ObjectStore,
    leases: LeaseStore,
}

impl Verifier {
    pub fn open(root: impl AsRef<Path>) -> Result<Self, VerifyError> {
        let objects = ObjectStore::open(root)?;
        directory(&objects.root().join("results"))?;
        let leases = LeaseStore::open(objects.root())?;
        Ok(Self { objects, leases })
    }

    pub fn objects(&self) -> &ObjectStore {
        &self.objects
    }

    pub fn leases(&self) -> &LeaseStore {
        &self.leases
    }

    pub fn verify(
        &self,
        target: &VerificationTarget<'_>,
        mode: VerificationMode,
        owner: ProcessIdentity,
    ) -> Result<VerificationReport, VerifyError> {
        self.verify_observed(target, mode, owner, |_| Ok(()))
    }

    /// @cc [owner:fontanierh,label:correctness] sealed-native-external-audit
    /// A Zen audit MUST upgrade only an exact source-key/item/path/canonical-locator
    /// match with one fixed independent native verifier proof whose frozen report,
    /// immutable retained native bytes and owned lifetime marker still validate.
    /// Unknown locators, duplicate proofs, report strings and missing proof MUST
    /// remain External; offline verification MUST retain its original refusal.
    /// Explicit native audit. Default/offline verification continues to classify
    /// external records separately; only the fixed independent verifier's sealed
    /// proof can upgrade an exact canonical Zen record.
    pub fn verify_with_zen(
        &self,
        target: &VerificationTarget<'_>,
        mode: VerificationMode,
        owner: ProcessIdentity,
        proofs: &[crate::results::zen_cook::VerifiedPackage<'_>],
    ) -> Result<VerificationReport, VerifyError> {
        let mut report = self.verify(target, mode, owner)?;
        for (key, outcome) in report.records.iter_mut() {
            let RecordOutcome::External { items, .. } = outcome else {
                continue;
            };
            let mut complete = !items.is_empty();
            for item in items.iter() {
                let matching = proofs
                    .iter()
                    .filter(|proof| {
                        proof.locator().source_key == *key
                            && proof.item().id == item.item_id
                            && proof.item().logical_path == item.logical_path
                            && proof.locator().encode().ok().as_deref()
                                == Some(item.locator.as_str())
                    })
                    .collect::<Vec<_>>();
                if matching.len() != 1 || matching[0].check().is_err() {
                    complete = false;
                    break;
                }
            }
            if complete {
                let unit = proofs
                    .iter()
                    .find(|proof| proof.locator().source_key == *key)
                    .expect("complete nonempty native proof set")
                    .source_unit()
                    .to_string();
                *outcome = RecordOutcome::Verified {
                    key: key.clone(),
                    unit,
                    objects_verified: 0,
                    bytes_hashed: 0,
                };
            }
        }
        report.counts = tally_counts(&report.records, &report.objects, report.counts.bytes_hashed);
        Ok(report)
    }

    /// @cc [owner:fontanierh,label:correctness] build-v2-explicit-audit-bypasses-hints
    /// Explicit verification MUST stream and SHA-256 hash the actual stored object bytes from disk,
    /// bypassing stat/version hash hints and recorded size/mtime metadata. It MUST detect byte
    /// changes that preserve file size and modification time, truncated or oversized files,
    /// writable or non-regular entries, and object-name versus content-digest mismatches.
    pub fn verify_observed(
        &self,
        target: &VerificationTarget<'_>,
        mode: VerificationMode,
        owner: ProcessIdentity,
        mut observe: impl FnMut(VerifyStep<'_>) -> io::Result<()>,
    ) -> Result<VerificationReport, VerifyError> {
        if owner.pid == 0 || owner.boot.is_empty() || owner.started.is_empty() {
            return Err(VerifyError::InvalidOwner);
        }

        let mut expected_units: BTreeMap<String, &PreparedUnit> = BTreeMap::new();
        let mut candidate_records: BTreeSet<String> = target.result_keys.clone();
        for unit in &target.units {
            expected_units.insert(unit.key().to_string(), *unit);
            candidate_records.insert(unit.key().to_string());
        }

        let valid_initial_records: BTreeSet<String> = candidate_records
            .iter()
            .filter(|key| valid_digest(key))
            .cloned()
            .collect();
        let valid_initial_objects: BTreeSet<String> = target
            .objects
            .keys()
            .filter(|digest| valid_digest(digest))
            .cloned()
            .collect();

        let lease = self
            .leases
            .begin(valid_initial_records, owner, Vec::new())?;
        let lease_id = lease.id.clone();
        let mut pin = PinGuard::new(&self.leases, self.objects.root(), lease);
        if !valid_initial_objects.is_empty() {
            pin.pin_objects(valid_initial_objects)?;
        }
        observe(VerifyStep::LeasePinned(&pin.lease))?;

        let (selected_records_set, skipped_records_set) = match mode {
            VerificationMode::Full => (candidate_records.clone(), BTreeSet::new()),
            VerificationMode::Sampled(spec) => {
                deterministic_sample(&candidate_records, "record", spec.seed, spec.max_results)
            }
        };

        let mut records_out = BTreeMap::new();
        let mut parsed_manifests: BTreeMap<
            String,
            (String, Vec<(String, u64)>, Vec<ExternalItemReport>),
        > = BTreeMap::new();
        let mut all_candidate_objects: BTreeSet<String> = target.objects.keys().cloned().collect();

        for key in &candidate_records {
            if skipped_records_set.contains(key) {
                records_out.insert(
                    key.clone(),
                    RecordOutcome::Unverified {
                        key: key.clone(),
                        reason: UnverifiedReason::SampleSkipped,
                    },
                );
                continue;
            }
            match self.inspect_record_metadata(key, expected_units.get(key).copied()) {
                RecordInspection::Ready {
                    unit,
                    manifest_objects,
                    external_items,
                } => {
                    let digests: Vec<String> =
                        manifest_objects.iter().map(|(d, _)| d.clone()).collect();
                    if !digests.is_empty() {
                        pin.pin_objects(digests.iter().cloned())?;
                    }
                    observe(VerifyStep::ManifestObjectsPinned {
                        result_key: key,
                        lease: &pin.lease,
                    })?;
                    for (digest, _) in &manifest_objects {
                        all_candidate_objects.insert(digest.clone());
                    }
                    parsed_manifests.insert(key.clone(), (unit, manifest_objects, external_items));
                }
                RecordInspection::Terminal(outcome) => {
                    records_out.insert(key.clone(), outcome);
                }
            }
        }

        let (selected_objects_set, skipped_objects_set) = match mode {
            VerificationMode::Full => (all_candidate_objects.clone(), BTreeSet::new()),
            VerificationMode::Sampled(spec) => deterministic_sample(
                &all_candidate_objects,
                "object",
                spec.seed,
                spec.max_objects,
            ),
        };

        let mut objects_out: BTreeMap<String, ObjectOutcome> = BTreeMap::new();
        let mut hashed_cache: BTreeMap<String, Result<(u64, String), ObjectOutcome>> =
            BTreeMap::new();
        let mut total_bytes_hashed: u64 = 0;

        for (digest, expected_size) in &target.objects {
            if skipped_objects_set.contains(digest) {
                objects_out.insert(
                    digest.clone(),
                    ObjectOutcome::Unverified {
                        digest: digest.clone(),
                        reason: UnverifiedReason::SampleSkipped,
                    },
                );
                continue;
            }
            let outcome = self.evaluate_object(
                digest,
                *expected_size,
                &mut hashed_cache,
                &mut total_bytes_hashed,
                &mut observe,
            )?;
            objects_out.insert(digest.clone(), outcome);
        }

        for (key, (unit, manifest_objects, external_items)) in parsed_manifests {
            let mut missing_digests = Vec::new();
            let mut corrupt_digests = Vec::new();
            let mut unverified_digests = Vec::new();
            let mut record_bytes: u64 = 0;
            let mut verified_count: usize = 0;

            for (digest, expected_size) in &manifest_objects {
                if skipped_objects_set.contains(digest) {
                    objects_out.entry(digest.clone()).or_insert_with(|| {
                        ObjectOutcome::Unverified {
                            digest: digest.clone(),
                            reason: UnverifiedReason::SampleSkipped,
                        }
                    });
                    unverified_digests.push(digest.clone());
                    continue;
                }
                let outcome = self.evaluate_object(
                    digest,
                    Some(*expected_size),
                    &mut hashed_cache,
                    &mut total_bytes_hashed,
                    &mut observe,
                )?;
                match &outcome {
                    ObjectOutcome::Verified { size, .. } => {
                        verified_count += 1;
                        record_bytes = record_bytes.saturating_add(*size);
                    }
                    ObjectOutcome::Missing { .. } => missing_digests.push(digest.clone()),
                    ObjectOutcome::Corrupt { .. } | ObjectOutcome::Malformed { .. } => {
                        corrupt_digests.push(digest.clone());
                    }
                    ObjectOutcome::Unverified { .. } => unverified_digests.push(digest.clone()),
                }
                merge_object_outcome(&mut objects_out, digest.clone(), outcome);
            }

            let record_outcome = if !corrupt_digests.is_empty() {
                corrupt_digests.sort();
                corrupt_digests.dedup();
                RecordOutcome::Corrupt {
                    key: key.clone(),
                    reason: RecordCorruption::CorruptObjects {
                        digests: corrupt_digests,
                    },
                }
            } else if !missing_digests.is_empty() {
                missing_digests.sort();
                missing_digests.dedup();
                RecordOutcome::MissingObjects {
                    key: key.clone(),
                    missing_digests,
                }
            } else if !external_items.is_empty() {
                RecordOutcome::External {
                    key: key.clone(),
                    items: external_items,
                }
            } else if !unverified_digests.is_empty() {
                unverified_digests.sort();
                unverified_digests.dedup();
                RecordOutcome::Unverified {
                    key: key.clone(),
                    reason: UnverifiedReason::UnverifiedObjects {
                        digests: unverified_digests,
                    },
                }
            } else {
                RecordOutcome::Verified {
                    key: key.clone(),
                    unit,
                    objects_verified: verified_count,
                    bytes_hashed: record_bytes,
                }
            };
            records_out.insert(key, record_outcome);
        }

        let sample = match mode {
            VerificationMode::Full => None,
            VerificationMode::Sampled(spec) => Some(SamplePlan {
                seed: spec.seed,
                candidate_records: candidate_records.into_iter().collect(),
                selected_records: selected_records_set.into_iter().collect(),
                skipped_records: skipped_records_set.into_iter().collect(),
                candidate_objects: all_candidate_objects.into_iter().collect(),
                selected_objects: selected_objects_set.into_iter().collect(),
                skipped_objects: skipped_objects_set.into_iter().collect(),
            }),
        };

        let counts = tally_counts(&records_out, &objects_out, total_bytes_hashed);

        pin.release()?;
        observe(VerifyStep::Released(&pin.lease))?;

        Ok(VerificationReport {
            lease_id,
            mode,
            sample,
            records: records_out,
            objects: objects_out,
            counts,
        })
    }

    fn record_path(&self, key: &str) -> PathBuf {
        self.objects
            .root()
            .join("results")
            .join(format!("{key}.json"))
    }

    fn object_path(&self, digest: &str) -> PathBuf {
        self.objects
            .root()
            .join("objects")
            .join(OBJECT_ALGORITHM)
            .join(digest)
    }

    fn inspect_record_metadata(
        &self,
        key: &str,
        expected_unit: Option<&PreparedUnit>,
    ) -> RecordInspection {
        if !valid_digest(key) {
            return RecordInspection::Terminal(RecordOutcome::Malformed {
                key: key.into(),
                reason: "result key must be 64 lowercase SHA-256 hex characters".into(),
            });
        }
        let path = self.record_path(key);
        let metadata = match fs::symlink_metadata(&path) {
            Err(error) if error.kind() == io::ErrorKind::NotFound => {
                return RecordInspection::Terminal(RecordOutcome::Missing { key: key.into() });
            }
            Err(error) => {
                return RecordInspection::Terminal(RecordOutcome::Corrupt {
                    key: key.into(),
                    reason: RecordCorruption::ReadFailed(error.to_string()),
                });
            }
            Ok(metadata) => metadata,
        };
        if !is_regular_readonly(&metadata) {
            return RecordInspection::Terminal(RecordOutcome::Corrupt {
                key: key.into(),
                reason: RecordCorruption::NotRegularOrWritableRecord,
            });
        }
        let bytes = match fs::read(&path) {
            Ok(bytes) => bytes,
            Err(error) => {
                return RecordInspection::Terminal(RecordOutcome::Corrupt {
                    key: key.into(),
                    reason: RecordCorruption::ReadFailed(error.to_string()),
                });
            }
        };
        let raw: serde_json::Value = match serde_json::from_slice::<serde_json::Value>(&bytes) {
            Ok(value) if value.is_object() => value,
            Ok(_) => {
                return RecordInspection::Terminal(RecordOutcome::Malformed {
                    key: key.into(),
                    reason: "result record JSON must be an object".into(),
                });
            }
            Err(error) => {
                return RecordInspection::Terminal(RecordOutcome::Malformed {
                    key: key.into(),
                    reason: format!("invalid result JSON: {error}"),
                });
            }
        };
        if let Some(version) = raw.get("version").and_then(|v| v.as_u64()) {
            if version != u64::from(ENVELOPE_VERSION) {
                return RecordInspection::Terminal(RecordOutcome::Unsupported {
                    key: key.into(),
                    reason: UnsupportedReason::EnvelopeVersion(version as u32),
                });
            }
        }
        if let Some(schema_version) = raw
            .get("result")
            .and_then(|r| r.get("schema_version"))
            .and_then(|v| v.as_u64())
        {
            if schema_version != u64::from(RESULT_SCHEMA_VERSION) {
                return RecordInspection::Terminal(RecordOutcome::Unsupported {
                    key: key.into(),
                    reason: UnsupportedReason::ResultSchemaVersion(schema_version as u32),
                });
            }
        }
        if raw
            .get("result")
            .and_then(|r| r.get("output_groups"))
            .and_then(|g| g.as_array())
            .is_some_and(|arr| !arr.is_empty())
            || raw
                .get("result")
                .and_then(|r| r.get("ingredients"))
                .and_then(|i| i.get("output_groups"))
                .and_then(|g| g.as_array())
                .is_some_and(|arr| !arr.is_empty())
        {
            return RecordInspection::Terminal(RecordOutcome::Unsupported {
                key: key.into(),
                reason: UnsupportedReason::OutputGroupsUnsupported,
            });
        }

        let envelope: ResultEnvelope = match serde_json::from_slice(&bytes) {
            Ok(envelope) => envelope,
            Err(error) => {
                return RecordInspection::Terminal(RecordOutcome::Malformed {
                    key: key.into(),
                    reason: format!("result schema violation: {error}"),
                });
            }
        };

        if envelope.version != ENVELOPE_VERSION {
            return RecordInspection::Terminal(RecordOutcome::Unsupported {
                key: key.into(),
                reason: UnsupportedReason::EnvelopeVersion(envelope.version),
            });
        }
        if envelope.result.schema_version != RESULT_SCHEMA_VERSION {
            return RecordInspection::Terminal(RecordOutcome::Unsupported {
                key: key.into(),
                reason: UnsupportedReason::ResultSchemaVersion(envelope.result.schema_version),
            });
        }
        if !envelope.result.output_groups.is_empty()
            || !envelope.result.ingredients.output_groups.is_empty()
        {
            return RecordInspection::Terminal(RecordOutcome::Unsupported {
                key: key.into(),
                reason: UnsupportedReason::OutputGroupsUnsupported,
            });
        }
        if envelope.result.unit.trim().is_empty() {
            return RecordInspection::Terminal(RecordOutcome::Malformed {
                key: key.into(),
                reason: "result unit identifier must not be empty".into(),
            });
        }
        if envelope
            .upstream_result_keys
            .iter()
            .any(|upstream| !valid_digest(upstream))
        {
            return RecordInspection::Terminal(RecordOutcome::Malformed {
                key: key.into(),
                reason: "upstream result key must be 64 lowercase hex characters".into(),
            });
        }
        if !valid_digest(&envelope.result.key) {
            return RecordInspection::Terminal(RecordOutcome::Malformed {
                key: key.into(),
                reason: "record key field must be 64 lowercase hex characters".into(),
            });
        }
        if let Err(reason) = validate_ingredients(&envelope.result.ingredients) {
            return RecordInspection::Terminal(RecordOutcome::Malformed {
                key: key.into(),
                reason,
            });
        }
        if envelope.result.key != key {
            return RecordInspection::Terminal(RecordOutcome::Corrupt {
                key: key.into(),
                reason: RecordCorruption::KeyMismatch {
                    requested_key: key.into(),
                    record_key: envelope.result.key,
                },
            });
        }
        let computed_key = match compute_unit_key(&envelope.result.ingredients) {
            Ok(computed) => computed,
            Err(reason) => {
                return RecordInspection::Terminal(RecordOutcome::Malformed {
                    key: key.into(),
                    reason,
                });
            }
        };
        if computed_key != envelope.result.key {
            return RecordInspection::Terminal(RecordOutcome::Corrupt {
                key: key.into(),
                reason: RecordCorruption::IngredientsKeyMismatch {
                    record_key: envelope.result.key,
                    computed_key,
                },
            });
        }
        if let Some(unit) = expected_unit {
            if unit.key() != key || unit.ingredients() != &envelope.result.ingredients {
                return RecordInspection::Terminal(RecordOutcome::Corrupt {
                    key: key.into(),
                    reason: RecordCorruption::PreparedUnitMismatch {
                        reason: "stored record ingredients differ from prepared unit".into(),
                    },
                });
            }
        }

        match validate_manifest(
            &envelope.result.ingredients.logical_outputs,
            &envelope.result.outputs,
        ) {
            Ok((manifest_objects, external_items)) => RecordInspection::Ready {
                unit: envelope.result.unit,
                manifest_objects,
                external_items,
            },
            Err(ManifestCheckError::Incomplete(defect)) => {
                RecordInspection::Terminal(RecordOutcome::IncompleteManifest {
                    key: key.into(),
                    defect,
                })
            }
            Err(ManifestCheckError::Malformed(reason)) => {
                RecordInspection::Terminal(RecordOutcome::Malformed {
                    key: key.into(),
                    reason,
                })
            }
            Err(ManifestCheckError::Unsupported(reason)) => {
                RecordInspection::Terminal(RecordOutcome::Unsupported {
                    key: key.into(),
                    reason,
                })
            }
        }
    }

    fn evaluate_object(
        &self,
        digest: &str,
        expected_size: Option<u64>,
        hashed_cache: &mut BTreeMap<String, Result<(u64, String), ObjectOutcome>>,
        total_bytes_hashed: &mut u64,
        observe: &mut impl FnMut(VerifyStep<'_>) -> io::Result<()>,
    ) -> Result<ObjectOutcome, VerifyError> {
        if ObjectDigest::from_hex(digest).is_err() {
            return Ok(ObjectOutcome::Malformed {
                digest: digest.into(),
                reason: "object digest must be 64 lowercase SHA-256 hex characters".into(),
            });
        }

        let raw_observation = if let Some(cached) = hashed_cache.get(digest) {
            cached.clone()
        } else {
            let result = self.read_and_hash_object(digest, total_bytes_hashed, observe)?;
            hashed_cache.insert(digest.into(), result.clone());
            result
        };

        let (actual_size, actual_digest) = match raw_observation {
            Ok(pair) => pair,
            Err(outcome) => return Ok(outcome),
        };

        if let Some(expected) = expected_size {
            if actual_size < expected {
                return Ok(ObjectOutcome::Corrupt {
                    digest: digest.into(),
                    reason: ObjectCorruption::Truncated {
                        expected_size: expected,
                        actual_size,
                        actual_digest,
                    },
                });
            }
            if actual_size > expected {
                return Ok(ObjectOutcome::Corrupt {
                    digest: digest.into(),
                    reason: ObjectCorruption::SizeMismatch {
                        expected_size: expected,
                        actual_size,
                        actual_digest,
                    },
                });
            }
        }

        if actual_digest != digest {
            return Ok(ObjectOutcome::Corrupt {
                digest: digest.into(),
                reason: ObjectCorruption::DigestMismatch {
                    expected_digest: digest.into(),
                    actual_digest,
                    size: actual_size,
                },
            });
        }

        Ok(ObjectOutcome::Verified {
            digest: digest.into(),
            size: actual_size,
        })
    }

    fn read_and_hash_object(
        &self,
        digest: &str,
        total_bytes_hashed: &mut u64,
        observe: &mut impl FnMut(VerifyStep<'_>) -> io::Result<()>,
    ) -> Result<Result<(u64, String), ObjectOutcome>, VerifyError> {
        let path = self.object_path(digest);
        let metadata = match fs::symlink_metadata(&path) {
            Err(error) if error.kind() == io::ErrorKind::NotFound => {
                return Ok(Err(ObjectOutcome::Missing {
                    digest: digest.into(),
                }));
            }
            Err(error) => {
                return Ok(Err(ObjectOutcome::Corrupt {
                    digest: digest.into(),
                    reason: ObjectCorruption::ReadFailed(error.to_string()),
                }));
            }
            Ok(metadata) => metadata,
        };
        if !metadata.file_type().is_file() {
            return Ok(Err(ObjectOutcome::Corrupt {
                digest: digest.into(),
                reason: ObjectCorruption::NotRegularFile,
            }));
        }
        if !is_regular_readonly(&metadata) {
            return Ok(Err(ObjectOutcome::Corrupt {
                digest: digest.into(),
                reason: ObjectCorruption::WritableObject,
            }));
        }

        let mut file = match File::open(&path) {
            Ok(file) => file,
            Err(error) => {
                return Ok(Err(ObjectOutcome::Corrupt {
                    digest: digest.into(),
                    reason: ObjectCorruption::ReadFailed(error.to_string()),
                }));
            }
        };
        let mut hasher = sha2::Sha256::new();
        use sha2::Digest;
        let mut buffer = [0u8; 64 * 1024];
        let mut actual_size: u64 = 0;
        loop {
            let count = match file.read(&mut buffer) {
                Ok(count) => count,
                Err(error) => {
                    return Ok(Err(ObjectOutcome::Corrupt {
                        digest: digest.into(),
                        reason: ObjectCorruption::ReadFailed(error.to_string()),
                    }));
                }
            };
            if count == 0 {
                break;
            }
            hasher.update(&buffer[..count]);
            actual_size = actual_size.saturating_add(count as u64);
        }
        *total_bytes_hashed = total_bytes_hashed.saturating_add(actual_size);
        let actual_digest = format!("{:x}", hasher.finalize());
        observe(VerifyStep::ObjectHashed {
            digest,
            size: actual_size,
        })?;
        Ok(Ok((actual_size, actual_digest)))
    }
}

enum RecordInspection {
    Ready {
        unit: String,
        manifest_objects: Vec<(String, u64)>,
        external_items: Vec<ExternalItemReport>,
    },
    Terminal(RecordOutcome),
}

enum ManifestCheckError {
    Incomplete(ManifestDefect),
    Malformed(String),
    Unsupported(UnsupportedReason),
}

fn is_regular_readonly(metadata: &fs::Metadata) -> bool {
    if !metadata.file_type().is_file() {
        return false;
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        metadata.permissions().mode() & 0o222 == 0
    }
    #[cfg(not(unix))]
    {
        metadata.permissions().readonly()
    }
}

fn normalized_item(item: &Item) -> Item {
    let mut item = item.clone();
    item.files.sort_by(|a, b| a.path.cmp(&b.path));
    item
}

fn compute_unit_key(ingredients: &IdentityIngredients) -> Result<String, String> {
    #[derive(Serialize)]
    struct Encoding<'a> {
        domain: &'static str,
        version: u32,
        ingredients: &'a IdentityIngredients,
    }
    Ok(sha256(&canonical_bytes(&Encoding {
        domain: "atelier-unit-key",
        version: KEY_ENCODING_VERSION,
        ingredients,
    })?))
}

fn validate_ingredients(ingredients: &IdentityIngredients) -> Result<(), String> {
    if ingredients.cache_version.trim().is_empty()
        || ingredients.op.kind.trim().is_empty()
        || ingredients.op.version.trim().is_empty()
        || ingredients.worker_version.trim().is_empty()
        || ingredients.validator_version.trim().is_empty()
    {
        return Err("ingredients version or op identifier is empty".into());
    }
    if !valid_digest(&ingredients.worker_digest) || !valid_digest(&ingredients.validator_digest) {
        return Err("worker or validator digest is not 64 lowercase hex characters".into());
    }
    relative_path(&ingredients.script, false)?;
    if !ingredients.code.contains_key(&ingredients.script) {
        return Err("entry script is missing from ingredients code map".into());
    }
    let mut staged_claims = Claims::new();
    claim(&mut staged_claims, "output", "writable output root")?;
    for (path, digest) in &ingredients.code {
        relative_path(path, false)?;
        if !valid_digest(digest) {
            return Err(format!("invalid code digest for {path}"));
        }
        claim(&mut staged_claims, path, "project code")?;
    }
    let mut expected_slots = BTreeSet::new();
    for (slot, identity) in &ingredients.content {
        if slot.trim().is_empty() || !expected_slots.insert(slot.clone()) {
            return Err("empty or duplicate content slot".into());
        }
        if let ContentIdentity::Digest { digest } = identity {
            if !valid_digest(digest) {
                return Err(format!("invalid content digest for slot {slot}"));
            }
        }
    }
    for (slot, reference) in &ingredients.references {
        if slot.trim().is_empty() || !expected_slots.insert(slot.clone()) {
            return Err("empty or duplicate reference slot".into());
        }
        logical_path(&reference.logical_path)?;
        if reference.class.trim().is_empty() {
            return Err(format!("empty reference class for slot {slot}"));
        }
        if ingredients.input_kinds.get(slot) != Some(&InputKind::File) {
            return Err(format!("reference slot {slot} must have File input kind"));
        }
    }
    let staged_slots: BTreeSet<String> = ingredients.staged_inputs.keys().cloned().collect();
    let kind_slots: BTreeSet<String> = ingredients.input_kinds.keys().cloned().collect();
    if staged_slots != expected_slots || kind_slots != expected_slots {
        return Err("staged_inputs and input_kinds must match declared input slots".into());
    }
    for (slot, path) in &ingredients.staged_inputs {
        relative_path(path, true)?;
        claim(&mut staged_claims, path, &format!("staged input {slot}"))?;
    }
    Ok(())
}

/// @cc [owner:fontanierh,label:correctness] build-v2-complete-valid-manifest
/// Result verification MUST require a regular read-only record with supported envelope and result
/// schema versions, a canonical unit key matching its serialized ingredients, and a complete
/// output manifest covering every declared item and required file with valid relative paths,
/// normalized semantic modes and 64-character lowercase hex SHA-256 digests. Undeclared, duplicate
/// or missing required outputs and overlapping checkout install paths MUST be rejected.
fn validate_manifest(
    expected_items: &[Item],
    stored_items: &[StoredItem],
) -> Result<(Vec<(String, u64)>, Vec<ExternalItemReport>), ManifestCheckError> {
    if expected_items.is_empty() || stored_items.len() != expected_items.len() {
        return Err(ManifestCheckError::Incomplete(
            ManifestDefect::ItemCountMismatch {
                expected: expected_items.len(),
                actual: stored_items.len(),
            },
        ));
    }

    let mut manifest_objects = Vec::new();
    let mut external_items = Vec::new();
    let mut job_output_claims = Claims::new();
    let mut checkout_claims = Claims::new();
    let mut logical_claims = Claims::new();
    let mut seen_item_ids = BTreeSet::new();

    for (expected, stored) in expected_items.iter().zip(stored_items) {
        if expected.id.trim().is_empty()
            || expected.class.trim().is_empty()
            || !seen_item_ids.insert(expected.id.clone())
        {
            return Err(ManifestCheckError::Malformed(
                "item id or class is empty or duplicated".into(),
            ));
        }
        logical_path(&expected.logical_path).map_err(ManifestCheckError::Malformed)?;
        if claim(
            &mut logical_claims,
            expected.logical_path.trim_start_matches('/'),
            &expected.id,
        )
        .is_err()
        {
            return Err(ManifestCheckError::Incomplete(
                ManifestDefect::ItemDeclarationMismatch {
                    item_id: expected.id.clone(),
                },
            ));
        }
        if normalized_item(expected) != normalized_item(&stored.item) {
            return Err(ManifestCheckError::Incomplete(
                ManifestDefect::ItemDeclarationMismatch {
                    item_id: expected.id.clone(),
                },
            ));
        }

        if expected.destination == Destination::External {
            if !stored.files.is_empty() {
                return Err(ManifestCheckError::Unsupported(
                    UnsupportedReason::ExternalFilesPresent {
                        item_id: expected.id.clone(),
                    },
                ));
            }
            match stored.external_locator.as_deref().map(str::trim) {
                Some(locator) if !locator.is_empty() => {
                    external_items.push(ExternalItemReport {
                        item_id: expected.id.clone(),
                        logical_path: expected.logical_path.clone(),
                        locator: locator.into(),
                    });
                    continue;
                }
                _ => {
                    return Err(ManifestCheckError::Unsupported(
                        UnsupportedReason::ExternalWithoutLocator {
                            item_id: expected.id.clone(),
                            logical_path: expected.logical_path.clone(),
                        },
                    ));
                }
            }
        }

        if stored.external_locator.is_some() {
            return Err(ManifestCheckError::Incomplete(
                ManifestDefect::ItemDeclarationMismatch {
                    item_id: expected.id.clone(),
                },
            ));
        }

        if expected.files.is_empty() {
            return Err(ManifestCheckError::Incomplete(
                ManifestDefect::EmptyItemFiles {
                    item_id: expected.id.clone(),
                },
            ));
        }

        let mut declared_paths = BTreeSet::new();
        for declared in &expected.files {
            relative_path(&declared.path, true).map_err(ManifestCheckError::Malformed)?;
            if !declared_paths.insert(declared.path.clone())
                || claim(&mut job_output_claims, &declared.path, &expected.id).is_err()
            {
                return Err(ManifestCheckError::Incomplete(
                    ManifestDefect::DuplicateFile {
                        item_id: expected.id.clone(),
                        path: declared.path.clone(),
                    },
                ));
            }
            match (&expected.destination, &declared.install_path) {
                (Destination::Checkout, Some(install_path)) => {
                    relative_path(install_path, true).map_err(ManifestCheckError::Malformed)?;
                    if let Err(msg) = claim(&mut checkout_claims, install_path, &expected.id) {
                        return Err(ManifestCheckError::Incomplete(
                            ManifestDefect::OverlappingCheckoutInstall {
                                first: expected.id.clone(),
                                second: msg,
                            },
                        ));
                    }
                }
                (Destination::Checkout, None) => {
                    return Err(ManifestCheckError::Malformed(format!(
                        "checkout item {} file {} lacks install_path",
                        expected.id, declared.path
                    )));
                }
                (Destination::Store, Some(_)) => {
                    return Err(ManifestCheckError::Malformed(format!(
                        "store item {} file {} must not set install_path",
                        expected.id, declared.path
                    )));
                }
                (Destination::Store, None) | (Destination::External, _) => {}
            }
        }

        let mut seen_stored_paths = BTreeSet::new();
        for file in &stored.files {
            relative_path(&file.path, true).map_err(ManifestCheckError::Malformed)?;
            if !valid_digest(&file.digest) {
                return Err(ManifestCheckError::Malformed(format!(
                    "stored file {} has invalid digest",
                    file.path
                )));
            }
            if !matches!(file.mode, 0o644 | 0o755) {
                return Err(ManifestCheckError::Malformed(format!(
                    "stored file {} has invalid mode {:o}",
                    file.path, file.mode
                )));
            }
            if !seen_stored_paths.insert(file.path.clone()) {
                return Err(ManifestCheckError::Incomplete(
                    ManifestDefect::DuplicateFile {
                        item_id: expected.id.clone(),
                        path: file.path.clone(),
                    },
                ));
            }
            if !declared_paths.contains(&file.path) {
                return Err(ManifestCheckError::Incomplete(
                    ManifestDefect::UndeclaredFile {
                        item_id: expected.id.clone(),
                        path: file.path.clone(),
                    },
                ));
            }
            manifest_objects.push((file.digest.clone(), file.size));
        }

        for declared in &expected.files {
            if declared.required && !seen_stored_paths.contains(&declared.path) {
                return Err(ManifestCheckError::Incomplete(
                    ManifestDefect::MissingRequiredFile {
                        item_id: expected.id.clone(),
                        path: declared.path.clone(),
                    },
                ));
            }
        }
    }

    Ok((manifest_objects, external_items))
}

fn deterministic_sample(
    candidates: &BTreeSet<String>,
    domain: &str,
    seed: u64,
    limit: usize,
) -> (BTreeSet<String>, BTreeSet<String>) {
    if limit >= candidates.len() {
        return (candidates.clone(), BTreeSet::new());
    }
    let mut ranked: Vec<(String, String)> = candidates
        .iter()
        .map(|id| {
            let rank = sha256(format!("atelier-verify-sample:v1:{domain}:{seed}:{id}").as_bytes());
            (rank, id.clone())
        })
        .collect();
    ranked.sort();
    let mut selected = BTreeSet::new();
    let mut skipped = BTreeSet::new();
    for (index, (_, id)) in ranked.into_iter().enumerate() {
        if index < limit {
            selected.insert(id);
        } else {
            skipped.insert(id);
        }
    }
    (selected, skipped)
}

fn merge_object_outcome(
    objects: &mut BTreeMap<String, ObjectOutcome>,
    digest: String,
    outcome: ObjectOutcome,
) {
    match objects.get(&digest) {
        Some(ObjectOutcome::Corrupt { .. } | ObjectOutcome::Malformed { .. }) => {}
        Some(ObjectOutcome::Missing { .. })
            if matches!(
                outcome,
                ObjectOutcome::Verified { .. } | ObjectOutcome::Unverified { .. }
            ) => {}
        _ => {
            objects.insert(digest, outcome);
        }
    }
}

fn tally_counts(
    records: &BTreeMap<String, RecordOutcome>,
    objects: &BTreeMap<String, ObjectOutcome>,
    bytes_hashed: u64,
) -> VerificationCounts {
    let mut counts = VerificationCounts {
        bytes_hashed,
        ..VerificationCounts::default()
    };
    for outcome in records.values() {
        match outcome {
            RecordOutcome::Verified { .. } => counts.verified_records += 1,
            RecordOutcome::Missing { .. } | RecordOutcome::MissingObjects { .. } => {
                counts.missing_records += 1
            }
            RecordOutcome::Corrupt { .. } => counts.corrupt_records += 1,
            RecordOutcome::Malformed { .. } => counts.malformed_records += 1,
            RecordOutcome::IncompleteManifest { .. } => counts.incomplete_manifests += 1,
            RecordOutcome::Unsupported { .. } => counts.unsupported_records += 1,
            RecordOutcome::External { .. } => {
                counts.external_records += 1;
                counts.unverified_records += 1;
            }
            RecordOutcome::Unverified { .. } => counts.unverified_records += 1,
        }
    }
    for outcome in objects.values() {
        match outcome {
            ObjectOutcome::Verified { .. } => counts.verified_objects += 1,
            ObjectOutcome::Missing { .. } => counts.missing_objects += 1,
            ObjectOutcome::Corrupt { .. } => counts.corrupt_objects += 1,
            ObjectOutcome::Malformed { .. } => counts.malformed_objects += 1,
            ObjectOutcome::Unverified { .. } => counts.unverified_objects += 1,
        }
    }
    counts
}
