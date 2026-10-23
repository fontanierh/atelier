//! Validated local outputs remain independent of cache publication availability.
use crate::groups::{
    OutputGroupContract, PlanRoster, ValidatedGroup, recorded_identity, restore_recorded,
};
use crate::install::LeaseIdentity;
use crate::keys::{InputPayload, PreparedInput, PreparedUnit, normalized_mode};
use crate::leases::{LeaseRecord, LeaseStore, ProcessIdentity, sync_dir};
use crate::results::{
    ActualOutput, ENVELOPE_VERSION, FrozenOutput, ResultEnvelope, ResultError, ResultStore,
    WriteTransaction, freeze_partitioned, partition_outputs,
};
use crate::schema::StoredFile;
use crate::schema::{RESULT_SCHEMA_VERSION, ResultRecord};
use crate::staging::{ObjectSource, SourceError, SourceErrorKind};
use crate::store::{ObjectDigest, PreparedObject, StoreError};
use std::collections::BTreeMap;
use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};

/// Durable local work custody created before the job or unknown-digest snapshots write.
/// Drop preserves the scope and its real owner/worker identities; no clock-only cleanup.
pub struct CompletionWork {
    pub(crate) root: PathBuf,
    pub(crate) leases: LeaseStore,
    pub(crate) lease: LeaseRecord,
    unit: PreparedUnit,
    identity: LeaseIdentity,
}

/// Private verified byte snapshots and complete validated manifest, never a StoredHit.
/// Dropping it retains local evidence and its lease; it cannot certify cache availability.
pub struct FrozenCompletion {
    pub(crate) work: CompletionWork,
    pub(crate) envelope: ResultEnvelope,
    pub(crate) objects: Vec<PreparedObject>,
    pub(crate) refused: bool,
}

impl CompletionWork {
    pub(crate) fn begin(
        root: &Path,
        unit: &PreparedUnit,
        identity: LeaseIdentity,
    ) -> Result<Self, ResultError> {
        for process in std::iter::once(&identity.owner).chain(&identity.workers) {
            if process.pid == 0 || process.boot.is_empty() || process.started.is_empty() {
                return Err(ResultError::Invalid(
                    "complete local process identity required".into(),
                ));
            }
        }
        let root = root.canonicalize()?;
        let leases = LeaseStore::open(&root)?;
        let mut keys = identity.upstream_result_keys.clone();
        keys.insert(unit.key().into());
        for key in &keys {
            ObjectDigest::from_hex(key)?;
        }
        let lease = leases.begin(keys, identity.owner.clone(), identity.workers.clone())?;
        Ok(Self {
            root,
            leases,
            lease,
            unit: unit.clone(),
            identity,
        })
    }
    pub fn lease(&self) -> &LeaseRecord {
        &self.lease
    }
    pub fn job_dir(&self) -> PathBuf {
        self.root.join(&self.lease.staging).join("job")
    }
    pub fn add_worker(&mut self, worker: ProcessIdentity) -> Result<(), ResultError> {
        if worker.pid == 0 || worker.boot.is_empty() || worker.started.is_empty() {
            return Err(ResultError::Invalid(
                "complete local worker identity required".into(),
            ));
        }
        if !self.lease.workers.contains(&worker) {
            let mut updated = self.lease.clone();
            updated.workers.push(worker);
            self.leases.lock()?.save(&updated)?;
            self.lease = updated;
        }
        Ok(())
    }
    /// @cc [owner:fontanierh,label:correctness;safety] local-completion-freeze-once
    /// The complete authoritative worker manifest MUST pass the same fixed/group validators as B2.
    /// Validators MUST read the exact independent snapshots hashed once here; no live reread or
    /// unchecked digest may certify local install or subsequent cache publication. The durable
    /// local lease precedes every snapshot; failure/drop MUST preserve local evidence and ownership.
    pub fn freeze(
        self,
        actual: Vec<ActualOutput>,
        fixed: impl FnOnce(&[FrozenOutput<'_>]) -> Result<(), String>,
        groups: impl FnMut(
            &OutputGroupContract,
            &PlanRoster,
            &BTreeMap<String, &PreparedObject>,
        ) -> Result<(), String>,
    ) -> Result<FrozenCompletion, ResultError> {
        let (fixed_sources, group_sources) = partition_outputs(&self.unit, actual)?;
        let scope = self.root.join(&self.lease.staging);
        let (outputs, output_groups, objects) = freeze_partitioned(
            &self.unit,
            fixed_sources,
            group_sources,
            fixed,
            groups,
            |source| PreparedObject::freeze_local(source, &scope).map_err(ResultError::Store),
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
                provenance: self.identity.provenance.clone(),
            },
            upstream_result_keys: self.identity.upstream_result_keys.clone(),
        };
        // Persist a complete evidence record before allowing the job folder to be retired.
        let path = scope.join("completion.json");
        let mut file = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&path)?;
        use std::io::Write;
        let members: Vec<_> = objects.iter().map(|object| Ok(serde_json::json!({"path": object.local_path(&scope)?, "digest":object.digest().as_hex(), "size":object.size(), "source_mode":object.source_mode(),"observation":object.observation_json()}))).collect::<Result<_, StoreError>>()?;
        let record = serde_json::json!({"version":1, "envelope":envelope, "objects":members});
        file.write_all(&crate::keys::canonical_bytes(&record).map_err(ResultError::Invalid)?)?;
        use std::os::unix::fs::PermissionsExt;
        file.set_permissions(fs::Permissions::from_mode(0o444))?;
        file.sync_all()?;
        sync_dir(&scope)?;
        Ok(FrozenCompletion {
            work: self,
            envelope,
            objects,
            refused: false,
        })
    }
}
impl FrozenCompletion {
    pub fn result(&self) -> &ResultEnvelope {
        &self.envelope
    }
    pub fn lease(&self) -> &LeaseRecord {
        &self.work.lease
    }
    /// Cache admission/publication consumes independent clones of verified snapshots, never this proof.
    /// Validation and nondeterminism errors stay hard; the caller may retain locally on cache I/O failure.
    pub fn publish(
        &mut self,
        store: &ResultStore,
        root: impl FnOnce(&ResultEnvelope) -> Result<(), String>,
    ) -> Result<ResultEnvelope, ResultError> {
        if self.refused {
            return Err(ResultError::Invalid(
                "completion already refused a semantic publication conflict".into(),
            ));
        }
        let transaction = store.begin(
            &self.work.unit,
            self.work.identity.provenance.clone(),
            self.work.lease.owner.clone(),
            self.work.lease.workers.clone(),
            self.envelope.upstream_result_keys.clone(),
        )?;
        self.publish_with(transaction, root)
    }

    /// Normal A5/A9 publication consumes the original miss lease held through staging/run.
    /// The store convenience above is only for late availability when no original CAS ticket exists.
    pub fn publish_with(
        &mut self,
        transaction: WriteTransaction,
        root: impl FnOnce(&ResultEnvelope) -> Result<(), String>,
    ) -> Result<ResultEnvelope, ResultError> {
        if self.refused {
            return Err(ResultError::Invalid(
                "completion already refused semantic publication conflict".into(),
            ));
        }
        let outcome = transaction
            .stage_completion(self)
            .and_then(|staged| staged.publish(root));
        if matches!(
            &outcome,
            Err(ResultError::Validation(_) | ResultError::Nondeterminism(_))
        ) {
            self.refused = true;
        }
        outcome
    }
    fn checked_object(&self, file: &StoredFile) -> Result<&PreparedObject, String> {
        self.objects
            .iter()
            .filter(|object| {
                object.digest().as_hex() == file.digest
                    && object.size() == file.size
                    && normalized_mode(object.source_mode()) == file.mode
            })
            .find(|object| object.check_frozen().is_ok())
            .ok_or_else(|| "no surviving certified frozen completion object".into())
    }
    pub(crate) fn certified_objects(&self) -> Result<Vec<&PreparedObject>, String> {
        let mut selected = BTreeMap::new();
        for file in self.envelope.files() {
            selected
                .entry((file.digest.clone(), file.size, file.mode))
                .or_insert(self.checked_object(file)?);
        }
        Ok(selected.into_values().collect())
    }
    /// Available local groups require every named sealed snapshot, not merely recorded metadata.
    /// This does not make them CAS hits or permit unchecked recorded identities to become available.
    pub fn available_groups(&self) -> Result<BTreeMap<String, ValidatedGroup>, ResultError> {
        if self.refused {
            return Err(ResultError::Nondeterminism(
                self.envelope.result.key.clone(),
            ));
        }
        self.envelope
            .result
            .ingredients
            .output_groups
            .iter()
            .zip(&self.envelope.result.output_groups)
            .map(|(contract, stored)| {
                let group = restore_recorded(contract, stored, |file| {
                    self.checked_object(file).map(|_| ())
                })
                .map_err(ResultError::Validation)?;
                Ok((contract.id.clone(), group))
            })
            .collect()
    }
    /// @cc [owner:fontanierh,label:correctness] frozen-selected-source-is-not-full-group-availability
    /// Source selection MUST bind exact selected metadata from this sealed complete validation,
    /// check only selected payload snapshots and clone without copying/rehashing. Missing unrelated
    /// members MUST NOT block a surviving selected source or mint a full available group token.
    /// See sealed_local_group_stages_selected_bytes_without_cas_and_refuses_missing_frozen_members.
    pub fn objects_for<'a>(
        &'a self,
        inputs: &[&PreparedInput],
    ) -> Result<FrozenObjects<'a>, ResultError> {
        if self.refused {
            return Err(ResultError::Nondeterminism(
                self.envelope.result.key.clone(),
            ));
        }
        let mut views = self.envelope.result.outputs.clone();
        // Source selection needs only already-validated recorded views, not full-group availability.
        for (contract, stored) in self
            .envelope
            .result
            .ingredients
            .output_groups
            .iter()
            .zip(&self.envelope.result.output_groups)
        {
            let group = recorded_identity(contract, stored).map_err(ResultError::Invalid)?;
            for piece in group.pieces() {
                views.push(group.project(piece).map_err(ResultError::Invalid)?);
            }
        }
        let mut allowed = BTreeSet::new();
        for input in inputs {
            let InputPayload::Item {
                logical_path,
                class,
                files,
            } = &input.payload
            else {
                return Err(ResultError::Invalid(
                    "local source requires typed item input".into(),
                ));
            };
            if files
                .iter()
                .map(|file| &file.path)
                .collect::<BTreeSet<_>>()
                .len()
                != files.len()
            {
                return Err(ResultError::Invalid("duplicate local input member".into()));
            }
            if !views.iter().any(|item| {
                item.item.logical_path == *logical_path
                    && item.item.class == *class
                    && item.files.len() == files.len()
                    && files.iter().all(|file| item.files.contains(file))
            }) {
                return Err(ResultError::Invalid(
                    "local input content/mode differs from sealed completion".into(),
                ));
            }
            for file in files {
                self.checked_object(file).map_err(ResultError::Validation)?;
                allowed.insert(ObjectDigest::from_hex(&file.digest)?);
            }
        }
        Ok(FrozenObjects {
            completion: self,
            allowed,
        })
    }
    pub(crate) fn clone_to(
        &self,
        digest: &ObjectDigest,
        destination: &Path,
    ) -> Result<(), StoreError> {
        self.objects
            .iter()
            .filter(|object| object.digest() == digest)
            .find(|object| object.check_frozen().is_ok())
            .ok_or(StoreError::InvalidFile("uncertified local digest"))?
            .clone_to(destination)
    }
}

/// Borrowed byte availability from fully validated local work, independent of CAS.
pub struct FrozenObjects<'a> {
    completion: &'a FrozenCompletion,
    allowed: BTreeSet<ObjectDigest>,
}
impl ObjectSource for FrozenObjects<'_> {
    fn clone_object(&self, digest: &ObjectDigest, destination: &Path) -> Result<(), SourceError> {
        let error = |kind, message: String| SourceError {
            kind,
            digest: digest.clone(),
            message,
        };
        if !self.allowed.contains(digest) {
            return Err(error(
                SourceErrorKind::Unavailable,
                "uncertified frozen completion digest".into(),
            ));
        }
        self.completion
            .clone_to(digest, destination)
            .map_err(|failure| {
                let kind = match &failure {
                    StoreError::InvalidFile(_) => SourceErrorKind::Changed,
                    StoreError::Io(error) if error.kind() == std::io::ErrorKind::NotFound => {
                        SourceErrorKind::Changed
                    }
                    StoreError::Clone(error)
                        if error.kind() == std::io::ErrorKind::Unsupported
                            || matches!(
                                error.raw_os_error(),
                                Some(libc::ENOTSUP) | Some(libc::EXDEV)
                            ) =>
                    {
                        SourceErrorKind::CloneUnsupported
                    }
                    _ => SourceErrorKind::Io,
                };
                error(kind, failure.to_string())
            })
    }
}
