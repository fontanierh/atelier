//! Narrow external-cook authority. A locator is metadata, never proof.
//!
//! Only the independent fixed native verifier job's certified frozen output can
//! issue VerifiedPackage. The verifier body invokes the native library directly;
//! missing native support fails the job. Cook writers cannot issue this token.
use crate::completion::FrozenCompletion;
use crate::keys::{ImplementationIdentity, PreparedUnit, canonical_bytes};
use crate::schema::{Destination, Item, StoredItem};
use crate::source_hashes::{sha256, valid_digest};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::fs;
use std::io::Read;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::Path;

// Keep the authority boundary self-contained while the shared backend owns its
// public native_tools module wiring. Both use this exact source bundle issuer.
#[path = "native_tools.rs"]
mod native_tool_source;

pub fn producer_worker_identity() -> Result<ImplementationIdentity, String> {
    use crate::validate::{SnapshotEntry, SourceSnapshot};
    let snapshot: SourceSnapshot = [
        (
            "protocol.py",
            include_bytes!("../../studio/atelier/build_v2/protocol.py").as_slice(),
        ),
        (
            "recipe_job.py",
            include_bytes!("../../studio/atelier/build_v2/recipe_job.py").as_slice(),
        ),
        (
            "unreal_tool_ops.py",
            include_bytes!("../../studio/atelier/build_v2/unreal_tool_ops.py").as_slice(),
        ),
        (
            "native_tool_worker.py",
            include_bytes!("../../studio/atelier/build_v2/native_tool_worker.py").as_slice(),
        ),
    ]
    .into_iter()
    .map(|(name, bytes)| (name.into(), SnapshotEntry::File(bytes.to_vec())))
    .collect();
    Ok(native_tool_source::NativeToolBundle::from_snapshot(&snapshot)?.identity())
}

fn fixed_producer_worker(version: &str, digest: &str) -> Result<(), String> {
    let expected = producer_worker_identity()?;
    if version != expected.version || digest != expected.digest {
        return Err("source cook was not executed by the exact fixed native tool worker".into());
    }
    Ok(())
}

pub const VERIFY_OP: &str = "unreal.cook.verify";
pub const VERIFY_SCRIPT: &str = "platform/studio/atelier/build_v2/zen_verify.py";
pub const VERIFY_REPORT: &str = "zen-verified.json";
/// This exact body must be declared as project code before the verifier key is
/// computed. It never accepts a writer's success flag or reads a writer report.
pub const VERIFY_BODY: &str = include_str!("../../studio/atelier/build_v2/zen_verify.py");

/// Project-owned native acceptance code only; installed engine/tools stay out.
/// Use this for both the source cook and independent verifier's validator identity.
pub fn validator_identity() -> crate::keys::ImplementationIdentity {
    let files = BTreeMap::from([
        ("zen_cook.rs", sha256(include_bytes!("zen_cook.rs"))),
        ("results.rs", sha256(include_bytes!("results.rs"))),
        ("verify.rs", sha256(include_bytes!("verify.rs"))),
        ("native_tools.rs", sha256(include_bytes!("native_tools.rs"))),
    ]);
    crate::keys::ImplementationIdentity {
        version: "atelier-zen-validator-1".into(),
        digest: sha256(&canonical_bytes(&files).expect("fixed native validator manifest")),
    }
}

/// Exact current C3 implementation, independent of the cook writer's worker.
pub(crate) fn verifier_worker_digest() -> Result<String, String> {
    let files = BTreeMap::from([
        (
            "protocol.py".into(),
            include_bytes!("../../studio/atelier/build_v2/protocol.py").to_vec(),
        ),
        (
            "python_job.py".into(),
            include_bytes!("../../studio/atelier/build_v2/python_job.py").to_vec(),
        ),
        (
            "recipe_job.py".into(),
            include_bytes!("../../studio/atelier/build_v2/recipe_job.py").to_vec(),
        ),
        (
            "unreal_inputs.py".into(),
            include_bytes!("../../studio/atelier/build_v2/unreal_inputs.py").to_vec(),
        ),
        (
            "unreal_worker.py".into(),
            include_bytes!("../../studio/atelier/build_v2/unreal_worker.py").to_vec(),
        ),
    ]);
    crate::unreal::UnrealWorkerBundle::from_files(files)
        .map(|bundle| bundle.digest().to_string())
        .map_err(|error| error.to_string())
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CookLocator {
    pub version: u32,
    pub project: String,
    pub oplog: String,
    pub package: String,
    pub source_key: String,
    pub record_sha256: String,
    /// Unreal FIoHash, not an Atelier SHA256 or guessed dependency fingerprint.
    pub dependency_key: String,
    pub entry_hash: String,
    pub installed_entry_hash: String,
    /// Durable v2-owned Zen oplog marker. The native verifier must compare the
    /// actual server markerpath, not merely test this file's existence.
    pub lifetime_marker: String,
    pub record_path: String,
    pub project_file: String,
}

fn native_hash(value: &str) -> bool {
    value.len() == 40
        && value
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
        && value.bytes().any(|c| c != b'0')
}
impl CookLocator {
    pub fn validate(&self) -> Result<(), String> {
        if self.version != 2
            || !valid_digest(&self.record_sha256)
            || !valid_digest(&self.source_key)
            || !native_hash(&self.dependency_key)
            || !native_hash(&self.entry_hash)
            || !native_hash(&self.installed_entry_hash)
            || self.oplog != "Mac"
            || self.project != format!("AtelierV2_{}", self.source_key)
            || self.project.len() > 100
            || !self
                .project
                .bytes()
                .all(|c| c.is_ascii_alphanumeric() || c == b'_')
            || !self.package.starts_with('/')
            || self.package.starts_with("/Script/")
            || self.package[1..].split('/').any(|part| {
                part.is_empty()
                    || !part
                        .bytes()
                        .all(|c| c.is_ascii_alphanumeric() || c == b'_' || c == b'-')
            })
            || [&self.lifetime_marker, &self.record_path, &self.project_file]
                .iter()
                .any(|p| !Path::new(p).is_absolute())
            || [&self.lifetime_marker, &self.record_path, &self.project_file]
                .iter()
                .flat_map(|p| Path::new(p).components())
                .any(|c| matches!(c, std::path::Component::ParentDir))
        {
            return Err("unsupported or incomplete Zen cook locator".into());
        }
        Ok(())
    }
    pub fn encode(&self) -> Result<String, String> {
        self.validate()?;
        Ok(format!(
            "atelier-zen-cook-v2:{}",
            String::from_utf8(canonical_bytes(self)?).map_err(|e| e.to_string())?
        ))
    }
    pub fn decode(text: &str) -> Result<Self, String> {
        let data = text
            .strip_prefix("atelier-zen-cook-v2:")
            .ok_or("unknown external locator adapter")?;
        if data.len() > 16384 {
            return Err("oversized Zen locator".into());
        }
        let value: Self = serde_json::from_str(data).map_err(|e| e.to_string())?;
        value.validate()?;
        if value.encode()? != text {
            return Err("noncanonical Zen locator".into());
        }
        Ok(value)
    }
    pub fn matches(&self, unit: &PreparedUnit, item: &Item) -> bool {
        item.destination == Destination::External
            && item.class == "CookedPackage"
            && item.files.is_empty()
            && self.package == item.logical_path
            && unit.ingredients().op.kind == "unreal.cook.package"
            && unit.ingredients().op.version == "1"
            && logical_parameters(&unit.ingredients().params, &self.package, true)
            && consumed_input_digest(unit.inputs()).is_ok_and(|digest| digest == self.record_sha256)
    }
}

fn logical_parameters(params: &crate::schema::Params, package: &str, restore_only: bool) -> bool {
    params
        .keys()
        .all(|key| matches!(key.as_str(), "package" | "mode" | "settings"))
        && params.get("package").and_then(|value| value.as_str()) == Some(package)
        && params.get("settings").is_none_or(|value| value.is_array())
        && match params.get("mode").and_then(|value| value.as_str()) {
            Some("restore") => true,
            Some("verify") => !restore_only,
            _ => false,
        }
}

fn consumed_input_digest(inputs: &[crate::keys::PreparedInput]) -> Result<&str, String> {
    let records = inputs
        .iter()
        .filter_map(|input| match &input.payload {
            crate::keys::InputPayload::Item { class, files, .. } if class == "NativeCookRecord" => {
                Some(files)
            }
            _ => None,
        })
        .collect::<Vec<_>>();
    if records.len() != 1 || records[0].len() != 1 || !valid_digest(&records[0][0].digest) {
        return Err("consumer must bind exactly one native CB record file".into());
    }
    Ok(&records[0][0].digest)
}

pub fn verifier_code_digests() -> BTreeMap<String, String> {
    const ROOT: &str = "platform/build-v2/unreal/AtelierBuildWorker/";
    let files: [(&str, &[u8]); 8] = [
        (
            "AtelierBuildWorker.uplugin",
            include_bytes!("../unreal/AtelierBuildWorker/AtelierBuildWorker.uplugin"),
        ),
        (
            "Source/AtelierBuildWorker/AtelierBuildWorker.Build.cs",
            include_bytes!(
                "../unreal/AtelierBuildWorker/Source/AtelierBuildWorker/AtelierBuildWorker.Build.cs"
            ),
        ),
        (
            "Source/AtelierBuildWorker/Private/AtelierBuildWorkerLibrary.cpp",
            include_bytes!(
                "../unreal/AtelierBuildWorker/Source/AtelierBuildWorker/Private/AtelierBuildWorkerLibrary.cpp"
            ),
        ),
        (
            "Source/AtelierBuildWorker/Private/AtelierBuildWorkerModule.cpp",
            include_bytes!(
                "../unreal/AtelierBuildWorker/Source/AtelierBuildWorker/Private/AtelierBuildWorkerModule.cpp"
            ),
        ),
        (
            "Source/AtelierBuildWorker/Private/AtelierZenPackage.cpp",
            include_bytes!(
                "../unreal/AtelierBuildWorker/Source/AtelierBuildWorker/Private/AtelierZenPackage.cpp"
            ),
        ),
        (
            "Source/AtelierBuildWorker/Private/AtelierZenFinalise.cpp",
            include_bytes!(
                "../unreal/AtelierBuildWorker/Source/AtelierBuildWorker/Private/AtelierZenFinalise.cpp"
            ),
        ),
        (
            "Source/AtelierBuildWorker/Public/AtelierBuildWorkerLibrary.h",
            include_bytes!(
                "../unreal/AtelierBuildWorker/Source/AtelierBuildWorker/Public/AtelierBuildWorkerLibrary.h"
            ),
        ),
        (
            "Source/AtelierBuildWorker/Public/AtelierZenFinalise.h",
            include_bytes!(
                "../unreal/AtelierBuildWorker/Source/AtelierBuildWorker/Public/AtelierZenFinalise.h"
            ),
        ),
    ];
    let mut result: BTreeMap<_, _> = files
        .into_iter()
        .map(|(name, bytes)| (format!("{ROOT}{name}"), sha256(bytes)))
        .collect();
    result.insert(VERIFY_SCRIPT.into(), sha256(VERIFY_BODY.as_bytes()));
    result
}

/// Source authority issued only from current local frozen completion or an exact
/// current transaction lookup. Cached origins keep the transaction's lease borrowed.
pub struct SourceCookEvidence<'a> {
    origin: SourceOrigin<'a>,
}
enum SourceOrigin<'a> {
    Local(&'a FrozenCompletion),
    Cached {
        transaction: &'a super::WriteTransaction,
        envelope: super::ResultEnvelope,
    },
}
impl<'a> SourceCookEvidence<'a> {
    pub(crate) fn clone_metadata(&self, destination: &Path) -> Result<(), String> {
        self.check()?;
        let file = crate::native_verify::metadata_file(&self.result().result)?;
        let digest =
            crate::store::ObjectDigest::from_hex(&file.digest).map_err(|e| e.to_string())?;
        match &self.origin {
            SourceOrigin::Local(completion) => completion
                .clone_to(&digest, destination)
                .map_err(|e| e.to_string()),
            SourceOrigin::Cached { transaction, .. } => transaction
                .pinned_objects()
                .clone_to(&digest, destination)
                .map_err(|e| e.to_string()),
        }
    }
    pub fn from_local(completion: &'a FrozenCompletion) -> Result<Self, String> {
        let value = Self {
            origin: SourceOrigin::Local(completion),
        };
        value.check()?;
        Ok(value)
    }
    pub fn from_cached(
        transaction: &'a mut super::WriteTransaction,
    ) -> Result<Option<Self>, String> {
        let Some(envelope) = transaction.lookup().map_err(|error| error.to_string())? else {
            return Ok(None);
        };
        let value = Self {
            origin: SourceOrigin::Cached {
                transaction,
                envelope,
            },
        };
        value.check()?;
        Ok(Some(value))
    }
    pub fn result(&self) -> &super::ResultEnvelope {
        match &self.origin {
            SourceOrigin::Local(value) => value.result(),
            SourceOrigin::Cached { envelope, .. } => envelope,
        }
    }
    pub fn consumed_record_digest(&self, unit: &PreparedUnit) -> Result<&str, String> {
        Ok(&consumed_native_record(&self.result().result.outputs, unit.inputs())?.files[0].digest)
    }
    pub fn lease(&self) -> &crate::leases::LeaseRecord {
        match &self.origin {
            SourceOrigin::Local(value) => value.lease(),
            SourceOrigin::Cached { transaction, .. } => transaction.lease(),
        }
    }
    pub fn worker_identity(&self) -> Result<ImplementationIdentity, String> {
        producer_worker_identity()
    }
    pub fn check(&self) -> Result<(), String> {
        let source = &self.result().result;
        if source.ingredients.op.kind != "unreal.cook.produce"
            || source.ingredients.op.version != "1"
        {
            return Err("source authority requires the fixed normal cook producer".into());
        }
        fixed_producer_worker(
            &source.ingredients.worker_version,
            &source.ingredients.worker_digest,
        )?;
        for (path, digest) in verifier_code_digests()
            .into_iter()
            .filter(|(path, _)| path != VERIFY_SCRIPT)
        {
            if source.ingredients.code.get(&path) != Some(&digest) {
                return Err(
                    "source cook did not key the actual native exporter implementation".into(),
                );
            }
        }
        if !source
            .outputs
            .iter()
            .any(|item| item.item.class == "NativeCookRecord")
        {
            return Err("source producer has no native CB output".into());
        }
        for item in source
            .outputs
            .iter()
            .filter(|item| item.item.class == "NativeCookRecord")
        {
            if item.item.destination != Destination::Store
                || item.external_locator.is_some()
                || item.files.len() != 1
                || !valid_digest(&item.files[0].digest)
                || item.files[0].size == 0
            {
                return Err("source CB has an invalid role or identity".into());
            }
        }
        match &self.origin {
            SourceOrigin::Local(value) => {
                if value.refused {
                    return Err("source completion was refused".into());
                }
                for object in value.certified_objects()? {
                    object.check_frozen().map_err(|error| error.to_string())?;
                }
            }
            SourceOrigin::Cached {
                transaction,
                envelope,
            } => {
                if transaction.unit.key() != envelope.result.key {
                    return Err("cached source is not the current transaction".into());
                }
                for item in source
                    .outputs
                    .iter()
                    .filter(|item| item.item.class == "NativeCookRecord")
                {
                    if item.item.destination != Destination::Store
                        || item.external_locator.is_some()
                        || item.files.len() != 1
                    {
                        return Err("cached source CB has an invalid role".into());
                    }
                    let file = &item.files[0];
                    if !transaction.lease.object_digests.contains(&file.digest) {
                        return Err("cached source CB lacks durable pins".into());
                    }
                    verify_cached_cb(transaction.store.objects.root(), file)?;
                }
            }
        }
        Ok(())
    }
}

fn verify_cached_cb(root: &Path, expected: &crate::schema::StoredFile) -> Result<(), String> {
    use sha2::Digest;
    if !valid_digest(&expected.digest) || expected.size > 512 * 1024 * 1024 {
        return Err("invalid cached CB identity".into());
    }
    let path = root.join("objects/sha256").join(&expected.digest);
    let mut file = fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(&path)
        .map_err(|e| e.to_string())?;
    let before = file.metadata().map_err(|e| e.to_string())?;
    if !before.is_file() || !before.permissions().readonly() || before.len() != expected.size {
        return Err("cached CB is not immutable complete data".into());
    }
    let mut digest = sha2::Sha256::new();
    let mut bytes = [0u8; 64 * 1024];
    let mut count = 0u64;
    loop {
        let read = file.read(&mut bytes).map_err(|e| e.to_string())?;
        if read == 0 {
            break;
        }
        count += read as u64;
        digest.update(&bytes[..read]);
    }
    let after = file.metadata().map_err(|e| e.to_string())?;
    let named = fs::symlink_metadata(&path).map_err(|e| e.to_string())?;
    let stamp = |m: &fs::Metadata| {
        (
            m.dev(),
            m.ino(),
            m.size(),
            m.mtime(),
            m.mtime_nsec(),
            m.ctime(),
            m.ctime_nsec(),
            m.mode(),
        )
    };
    if stamp(&before) != stamp(&after)
        || stamp(&after) != stamp(&named)
        || count != expected.size
        || format!("{:x}", digest.finalize()) != expected.digest
    {
        return Err("cached source CB bytes changed or differ".into());
    }
    Ok(())
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct NativeReport {
    version: u32,
    locator: CookLocator,
    record_io_hash: String,
    record_sha256: String,
    attachments: u64,
    mode: String,
    source_dependency_evaluation: String,
}

fn consumed_native_record<'a>(
    items: &'a [StoredItem],
    inputs: &[crate::keys::PreparedInput],
) -> Result<&'a StoredItem, String> {
    let records = items
        .iter()
        .filter(|item| {
            item.item.class == "NativeCookRecord"
                && item.item.destination == Destination::Store
                && item.files.len() == 1
                && item.external_locator.is_none()
        })
        .filter(|item| {
            inputs.iter().any(|input| match &input.payload {
                crate::keys::InputPayload::Item {
                    logical_path,
                    class,
                    files,
                } => {
                    logical_path == &item.item.logical_path
                        && class == &item.item.class
                        && files == &item.files
                }
                _ => false,
            })
        })
        .collect::<Vec<_>>();
    if records.len() != 1 {
        return Err(
            "source unit must consume exactly one actual completed native cook record".into(),
        );
    }
    Ok(records[0])
}

/// A live borrow of the independently verified frozen native result. There is no
/// Deserialize, boolean constructor, arbitrary callback or writer-report issuer.
pub struct VerifiedPackage<'a> {
    locator: CookLocator,
    proof: &'a FrozenCompletion,
    producer: SourceCookEvidence<'a>,
    item: Item,
    source_unit: String,
    record_sha256: String,
}
impl<'a> VerifiedPackage<'a> {
    pub fn from_verifier(
        unit: &PreparedUnit,
        item: &Item,
        producer: SourceCookEvidence<'a>,
        proof: &'a FrozenCompletion,
    ) -> Result<Self, String> {
        producer.check()?;
        let source_digest = producer.consumed_record_digest(unit)?.to_string();
        let record = &proof.result().result;
        let ingredients = &record.ingredients;
        if proof.refused
            || record.key == unit.key()
            || ingredients.op.kind != VERIFY_OP
            || ingredients.op.version != "1"
            || ingredients.script != VERIFY_SCRIPT
            || ingredients.code != verifier_code_digests()
            || ingredients.worker_version != crate::unreal::UNREAL_JOB_LOOP_VERSION
            || ingredients.worker_digest != verifier_worker_digest()?
            || ingredients.validator_digest != unit.ingredients().validator_digest
            || ingredients.validator_digest != validator_identity().digest
            || ingredients.validator_version != validator_identity().version
            || ingredients.content != unit.ingredients().content
            || !ingredients.references.is_empty()
            || !record.output_groups.is_empty()
            || !logical_parameters(&ingredients.params, &item.logical_path, false)
        {
            return Err("Zen proof is not the independent fixed native verifier".into());
        }
        let p = &ingredients.params;
        let outputs = &record.outputs;
        if outputs.len() != 1
            || outputs[0].item.destination != Destination::Store
            || outputs[0].item.class != "JsonData"
            || outputs[0].files.len() != 1
            || outputs[0].files[0].path != VERIFY_REPORT
            || outputs[0].external_locator.is_some()
        {
            return Err("Zen verifier has an unexpected output inventory".into());
        }
        let file = &outputs[0].files[0];
        if file.size > 8 * 1024 * 1024 {
            return Err("oversized native Zen report".into());
        }
        let objects = proof.certified_objects()?;
        let object = objects
            .iter()
            .find(|object| object.digest().as_hex() == file.digest && object.size() == file.size)
            .ok_or("missing certified native Zen report")?;
        object.check_frozen().map_err(|e| e.to_string())?;
        let report: NativeReport = serde_json::from_slice(&{
            let mut bytes = Vec::new();
            object
                .reader()
                .map_err(|e| e.to_string())?
                .read_to_end(&mut bytes)
                .map_err(|e| e.to_string())?;
            bytes
        })
        .map_err(|e| e.to_string())?;
        let locator = report.locator;
        locator.validate()?;
        if report.version != 1
            || !locator.matches(unit, item)
            || !native_hash(&report.record_io_hash)
            || !valid_digest(&report.record_sha256)
            || report.record_sha256 != source_digest
            || locator.record_sha256 != source_digest
            || report.source_dependency_evaluation != "recorded_only"
            || report.mode != "restore"
            || report.attachments == 0
            || report.attachments > 1_000_000
            || p.get("mode").and_then(|v| v.as_str()) != Some(report.mode.as_str())
        {
            return Err("native Zen report is incomplete or differs".into());
        }
        Ok(Self {
            locator,
            proof,
            producer,
            item: item.clone(),
            source_unit: unit.request("", "").unit,
            record_sha256: report.record_sha256,
        })
    }

    pub(crate) fn validate_store_layout(&self, store_root: &Path) -> Result<(), String> {
        let source = &self.producer.result().result;
        validate_native_layout(
            &self.locator,
            store_root,
            &source.key,
            &source.ingredients.params,
        )
    }
    pub fn locator(&self) -> &CookLocator {
        &self.locator
    }
    pub(crate) fn source_unit(&self) -> &str {
        &self.source_unit
    }
    pub(crate) fn item(&self) -> &Item {
        &self.item
    }
    pub(crate) fn report(&self) -> &super::ResultEnvelope {
        self.proof.result()
    }
    pub(crate) fn producer_report(&self) -> &super::ResultEnvelope {
        self.producer.result()
    }
    pub(crate) fn producer_key(&self) -> &str {
        &self.producer.result().result.key
    }
    pub fn candidate_source_key(&self) -> &str {
        &self.locator.source_key
    }
    pub(crate) fn proof_key(&self) -> &str {
        &self.proof.result().result.key
    }
    pub(crate) fn witness(&self) -> NativeArtifactWitness {
        NativeArtifactWitness {
            locator: self.locator.clone(),
            record_sha256: self.record_sha256.clone(),
        }
    }
    pub(crate) fn check(&self) -> Result<(), String> {
        self.producer.check()?;
        if self.proof.refused {
            return Err("native verifier completion was refused".into());
        }
        for object in self.proof.certified_objects()? {
            object.check_frozen().map_err(|e| e.to_string())?;
        }
        self.witness().check()
    }
}

/// Derive all native paths from the actual fixed producer declaration. Neither
/// locator text nor an unrelated external result key can choose persistence paths.
fn validate_native_layout(
    locator: &CookLocator,
    store_root: &Path,
    producer_key: &str,
    params: &crate::schema::Params,
) -> Result<(), String> {
    if !valid_digest(&locator.source_key) || !valid_digest(producer_key) {
        return Err("invalid current/candidate source identity".into());
    }
    let candidate_key = &locator.source_key;
    let logical_project = params
        .get("project")
        .and_then(|value| value.as_str())
        .ok_or("source producer has no original logical project")?;
    crate::paths::relative_path(logical_project, false)?;
    if Path::new(logical_project)
        .extension()
        .and_then(|part| part.to_str())
        != Some("uproject")
    {
        return Err("source producer project is not a project descriptor".into());
    }
    let packages = params
        .get("packages")
        .and_then(|value| value.as_array())
        .ok_or("source producer has no exact package roster")?;
    let names = packages
        .iter()
        .map(|value| value.as_str().ok_or("non-string cook package"))
        .collect::<Result<Vec<_>, _>>()?;
    if names.is_empty()
        || names.windows(2).any(|pair| pair[0] >= pair[1])
        || !names.contains(&locator.package.as_str())
    {
        return Err("native package is outside the actual producer roster".into());
    }
    let root = store_root.join("zen-cook");
    let project = root
        .join("projects")
        .join(candidate_key)
        .join("view")
        .join(logical_project);
    let marker = project
        .parent()
        .ok_or("source project has no directory")?
        .join("Saved/Cooked/Mac/ue.projectstore");
    let record = root.join("records").join(format!("{candidate_key}.cb"));
    let selected_record = root.join("records").join(format!(
        "{candidate_key}-{}.cb",
        sha256(locator.package.as_bytes())
    ));
    if Path::new(&locator.project_file) != project
        || Path::new(&locator.lifetime_marker) != marker
        || (Path::new(&locator.record_path) != record
            && Path::new(&locator.record_path) != selected_record)
    {
        return Err(
            "native project, marker or record differs from the fixed stock-cook layout".into(),
        );
    }
    Ok(())
}

/// Rechecked at publication, never constructed from external locator text.
pub(crate) struct NativeArtifactWitness {
    locator: CookLocator,
    record_sha256: String,
}
impl NativeArtifactWitness {
    pub(crate) fn check(&self) -> Result<(), String> {
        let marker =
            fs::symlink_metadata(&self.locator.lifetime_marker).map_err(|e| e.to_string())?;
        if !marker.is_file() {
            return Err("Zen lifetime marker is missing or not regular".into());
        }
        let metadata =
            fs::symlink_metadata(&self.locator.record_path).map_err(|e| e.to_string())?;
        if !metadata.is_file()
            || !metadata.permissions().readonly()
            || metadata.len() > 512 * 1024 * 1024
        {
            return Err("native package record is absent, writable, linked or oversized".into());
        }
        let bytes = fs::read(&self.locator.record_path).map_err(|e| e.to_string())?;
        if sha256(&bytes) != self.record_sha256 {
            return Err("native package record changed after verification".into());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn locator() -> CookLocator {
        let key = "a".repeat(64);
        CookLocator {
            version: 2,
            record_sha256: "f".repeat(64),
            project: format!("AtelierV2_{key}"),
            oplog: "Mac".into(),
            package: "/Game/Test/Mesh".into(),
            source_key: key,
            dependency_key: "b".repeat(40),
            entry_hash: "c".repeat(40),
            installed_entry_hash: "d".repeat(40),
            lifetime_marker: "/store/zen-cook/markers/key".into(),
            record_path: "/store/zen-cook/records/key.cb".into(),
            project_file: "/store/zen-cook/projects/key/Atelier.uproject".into(),
        }
    }
    #[test]
    fn external_result_key_is_independent_from_the_completed_source_key() {
        use crate::keys::{KeyContext, prepare};
        use crate::schema::{Declaration, Op, Unit};
        use crate::source_hashes::SourceHashCache;
        use crate::validate::{SnapshotEntry, SourceSnapshot, ValidatedDeclaration};
        let locator = locator();
        let item = Item {
            id: "cooked".into(),
            logical_path: locator.package.clone(),
            class: "CookedPackage".into(),
            destination: Destination::External,
            files: vec![],
        };
        let record = StoredItem {
            item: Item {
                id: "record".into(),
                logical_path: "/CookRecords/Test".into(),
                class: "NativeCookRecord".into(),
                destination: Destination::Store,
                files: vec![crate::schema::OutputFile {
                    path: "record.cb".into(),
                    install_path: None,
                    required: true,
                }],
            },
            files: vec![crate::schema::StoredFile {
                path: "record.cb".into(),
                digest: locator.record_sha256.clone(),
                size: 6,
                mode: 0o644,
            }],
            external_locator: None,
        };
        let produced = BTreeMap::from([(("producer".into(), "record".into()), record.clone())]);
        let mut declaration = Declaration {
            schema_version: 2,
            cache_version: "test".into(),
            units: vec![Unit {
                id: "external".into(),
                op: Op {
                    kind: "unreal.cook.package".into(),
                    version: "1".into(),
                },
                script: "cook.py".into(),
                code: std::iter::once("cook.py".into())
                    .chain(
                        verifier_code_digests()
                            .into_keys()
                            .filter(|name| name != VERIFY_SCRIPT),
                    )
                    .collect(),
                inputs: vec![crate::schema::Input::Content {
                    name: "record".into(),
                    source: crate::schema::ContentSource::Item {
                        unit: "producer".into(),
                        item: "record".into(),
                    },
                    whole: None,
                    conditional: None,
                }],
                params: BTreeMap::from([
                    ("package".into(), serde_json::json!(locator.package)),
                    ("mode".into(), serde_json::json!("restore")),
                ]),
                outputs: vec![item.clone()],
                output_groups: vec![],
                conditional: None,
            }],
        };
        declaration.units.push(Unit {
            id: "producer".into(),
            op: Op {
                kind: "unreal.cook.produce".into(),
                version: "1".into(),
            },
            script: "cook.py".into(),
            code: vec!["cook.py".into()],
            inputs: vec![],
            params: BTreeMap::new(),
            outputs: vec![record.item],
            output_groups: vec![],
            conditional: None,
        });
        let snapshot: SourceSnapshot =
            BTreeMap::from([("cook.py".into(), SnapshotEntry::File(b"# fixed".to_vec()))]);
        let validated = ValidatedDeclaration {
            order: vec!["external".into()],
            files: vec![],
        };
        let identity = validator_identity();
        let context = KeyContext {
            snapshot: &snapshot,
            versions: &BTreeMap::new(),
            produced: &produced,
            produced_groups: &BTreeMap::new(),
            staged_inputs: &BTreeMap::from([("record".into(), "in/record".into())]),
            worker: &identity,
            validator: &identity,
        };
        let prepared = prepare(
            &declaration,
            &validated,
            "external",
            &context,
            &mut SourceHashCache::default(),
        )
        .unwrap();
        assert_ne!(prepared.key(), locator.source_key);
        assert!(locator.matches(&prepared, &item));
        let mut wrong = locator.clone();
        wrong.source_key = prepared.key().into();
        wrong.project = format!("AtelierV2_{}", wrong.source_key);
        assert!(wrong.matches(&prepared, &item));
        wrong.record_sha256 = "e".repeat(64);
        assert!(!wrong.matches(&prepared, &item));
    }
    #[test]
    fn source_producer_requires_exact_fixed_worker_not_an_operation_label() {
        let worker = producer_worker_identity().unwrap();
        assert!(fixed_producer_worker(&worker.version, &worker.digest).is_ok());
        assert!(fixed_producer_worker("arbitrary-writer", &worker.digest).is_err());
        assert!(fixed_producer_worker(&worker.version, &sha256(b"writer spoof")).is_err());
    }
    #[test]
    fn stock_native_paths_derive_from_producer_project_key_and_selected_package() {
        let mut value = locator();
        let key = value.source_key.clone();
        let root = Path::new("/store");
        let project =
            format!("/store/zen-cook/projects/{key}/view/games/test/unreal/Test.uproject");
        value.project_file = project;
        value.lifetime_marker = format!(
            "/store/zen-cook/projects/{key}/view/games/test/unreal/Saved/Cooked/Mac/ue.projectstore"
        );
        value.record_path = format!("/store/zen-cook/records/{key}.cb");
        let mut params = BTreeMap::from([
            (
                "project".into(),
                serde_json::json!("games/test/unreal/Test.uproject"),
            ),
            ("packages".into(), serde_json::json!([value.package])),
        ]);
        assert!(validate_native_layout(&value, root, &key, &params).is_ok());
        let mut wrong = value.clone();
        wrong.lifetime_marker = format!("/store/zen-cook/markers/{key}");
        assert!(validate_native_layout(&wrong, root, &key, &params).is_err());
        assert!(validate_native_layout(&value, root, &"e".repeat(64), &params).is_ok());
        params.insert(
            "project".into(),
            serde_json::json!("../foreign/Test.uproject"),
        );
        assert!(validate_native_layout(&value, root, &key, &params).is_err());
        params.insert(
            "project".into(),
            serde_json::json!("games/test/unreal/Test.uproject"),
        );
        params.insert(
            "packages".into(),
            serde_json::json!(["/Game/Other", value.package]),
        );
        assert!(validate_native_layout(&value, root, &key, &params).is_ok());
        value.record_path = format!(
            "/store/zen-cook/records/{key}-{}.cb",
            sha256(value.package.as_bytes())
        );
        assert!(validate_native_layout(&value, root, &key, &params).is_ok());
        params.insert("packages".into(), serde_json::json!(["/Game/Other"]));
        assert!(validate_native_layout(&value, root, &key, &params).is_err());
    }
    #[test]
    fn producer_origin_requires_exact_consumed_native_bytes_and_role() {
        use crate::keys::{InputPayload, PreparedInput};
        use crate::protocol::StagedInput;
        use crate::schema::{ContentIdentity, OutputFile, StoredFile};
        let item = StoredItem {
            item: Item {
                id: "record".into(),
                logical_path: "/CookRecords/Test".into(),
                class: "NativeCookRecord".into(),
                destination: Destination::Store,
                files: vec![OutputFile {
                    path: "record.cb".into(),
                    install_path: None,
                    required: true,
                }],
            },
            files: vec![StoredFile {
                path: "record.cb".into(),
                digest: "a".repeat(64),
                size: 6,
                mode: 0o644,
            }],
            external_locator: None,
        };
        let input = PreparedInput {
            wire: StagedInput {
                name: "record".into(),
                path: "in/record".into(),
                identity: ContentIdentity::Digest {
                    digest: "b".repeat(64),
                },
            },
            payload: InputPayload::Item {
                logical_path: item.item.logical_path.clone(),
                class: item.item.class.clone(),
                files: item.files.clone(),
            },
        };
        assert!(consumed_native_record(&[item.clone()], &[input.clone()]).is_ok());
        assert!(consumed_native_record(&[item.clone()], &[]).is_err());
        assert!(consumed_native_record(&[item.clone(), item.clone()], &[input.clone()]).is_err());
        let mut wrong = input.clone();
        if let InputPayload::Item { files, .. } = &mut wrong.payload {
            files[0].digest = "c".repeat(64);
        }
        assert!(consumed_native_record(&[item.clone()], &[wrong]).is_err());
        let mut wrong = input.clone();
        if let InputPayload::Item { files, .. } = &mut wrong.payload {
            files[0].mode = 0o755;
        }
        assert!(consumed_native_record(&[item.clone()], &[wrong]).is_err());
        let mut metadata = item.clone();
        metadata.item.class = "JsonData".into();
        assert!(consumed_native_record(&[metadata.clone()], &[input.clone()]).is_err());
        assert!(consumed_native_record(&[metadata, item], &[input]).is_ok());
    }
    #[test]
    fn cached_source_authority_pins_and_hashes_the_current_transaction_cb() {
        use crate::keys::{KeyContext, prepare};
        use crate::schema::*;
        use crate::validate::{SnapshotEntry, SourceSnapshot, ValidatedDeclaration};
        use std::os::unix::fs::PermissionsExt;
        let root = std::env::temp_dir().join(format!("atelier-zen-cached-{}", std::process::id()));
        fs::create_dir(&root).unwrap();
        let store = super::super::ResultStore::open(root.join("store")).unwrap();
        let item = Item {
            id: "record".into(),
            logical_path: "/CookRecords/Test".into(),
            class: "NativeCookRecord".into(),
            destination: Destination::Store,
            files: vec![OutputFile {
                path: "record.cb".into(),
                install_path: None,
                required: true,
            }],
        };
        let declaration = Declaration {
            schema_version: SCHEMA_VERSION,
            cache_version: "test".into(),
            units: vec![Unit {
                id: "producer".into(),
                op: Op {
                    kind: "unreal.cook.produce".into(),
                    version: "1".into(),
                },
                script: "cook.py".into(),
                code: vec!["cook.py".into()],
                inputs: vec![],
                params: BTreeMap::new(),
                outputs: vec![item.clone()],
                output_groups: vec![],
                conditional: None,
            }],
        };
        let mut snapshot: SourceSnapshot =
            BTreeMap::from([("cook.py".into(), SnapshotEntry::File(b"fixed".to_vec()))]);
        let checkout = Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .parent()
            .unwrap();
        for (name, expected) in verifier_code_digests()
            .into_iter()
            .filter(|(name, _)| name != VERIFY_SCRIPT)
        {
            let bytes = fs::read(checkout.join(&name)).unwrap();
            assert_eq!(sha256(&bytes), expected);
            snapshot.insert(name, SnapshotEntry::File(bytes));
        }
        let worker = producer_worker_identity().unwrap();
        let validator = validator_identity();
        let context = KeyContext {
            snapshot: &snapshot,
            versions: &BTreeMap::new(),
            produced: &BTreeMap::new(),
            produced_groups: &BTreeMap::new(),
            staged_inputs: &BTreeMap::new(),
            worker: &worker,
            validator: &validator,
        };
        let unit = prepare(
            &declaration,
            &ValidatedDeclaration {
                order: vec!["producer".into()],
                files: vec![],
            },
            "producer",
            &context,
            &mut crate::source_hashes::SourceHashCache::default(),
        )
        .unwrap();
        let provenance = Provenance {
            checkout: "test".into(),
            branch: "test".into(),
            commit: "test".into(),
            dirty: false,
            built_at: "now".into(),
        };
        let digest = sha256(b"native");
        let object = store.objects.root().join("objects/sha256").join(&digest);
        fs::write(&object, b"native").unwrap();
        fs::set_permissions(&object, fs::Permissions::from_mode(0o444)).unwrap();
        let envelope = super::super::ResultEnvelope {
            version: super::super::ENVELOPE_VERSION,
            result: ResultRecord {
                schema_version: RESULT_SCHEMA_VERSION,
                unit: "producer".into(),
                key: unit.key().into(),
                ingredients: unit.ingredients().clone(),
                outputs: vec![StoredItem {
                    item,
                    files: vec![StoredFile {
                        path: "record.cb".into(),
                        digest: digest.clone(),
                        size: 6,
                        mode: 0o644,
                    }],
                    external_locator: None,
                }],
                output_groups: vec![],
                provenance: provenance.clone(),
            },
            upstream_result_keys: Default::default(),
        };
        let record = store.record_path(unit.key());
        fs::write(&record, serde_json::to_vec(&envelope).unwrap()).unwrap();
        fs::set_permissions(&record, fs::Permissions::from_mode(0o444)).unwrap();
        let mut transaction = store
            .begin(
                &unit,
                provenance,
                crate::leases::ProcessIdentity {
                    pid: std::process::id(),
                    boot: "test".into(),
                    started: "test".into(),
                },
                vec![],
                Default::default(),
            )
            .unwrap();
        {
            let evidence = SourceCookEvidence::from_cached(&mut transaction)
                .unwrap()
                .unwrap();
            assert_eq!(evidence.result(), &envelope);
            assert!(evidence.lease().object_digests.contains(&digest));
            assert!(evidence.check().is_ok());
        }
        // Ordinary lookup checks immutable metadata; source authority additionally
        // rejects same-size corrupted CB bytes before issuing its sealed capability.
        fs::set_permissions(&object, fs::Permissions::from_mode(0o644)).unwrap();
        fs::write(&object, b"mutate").unwrap();
        fs::set_permissions(&object, fs::Permissions::from_mode(0o444)).unwrap();
        assert!(transaction.lookup().unwrap().is_some());
        assert!(SourceCookEvidence::from_cached(&mut transaction).is_err());
        fs::remove_file(&object).unwrap();
        assert!(SourceCookEvidence::from_cached(&mut transaction).is_err());
        drop(transaction);
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn retained_native_record_changes_and_missing_marker_refuse_publication() {
        use std::os::unix::fs::PermissionsExt;
        let root = std::env::temp_dir().join(format!("atelier-zen-witness-{}", std::process::id()));
        fs::create_dir(&root).unwrap();
        let marker = root.join("marker");
        let record = root.join("record.cb");
        fs::write(&marker, b"lifetime").unwrap();
        fs::write(&record, b"native").unwrap();
        fs::set_permissions(&record, fs::Permissions::from_mode(0o444)).unwrap();
        let mut locator = locator();
        locator.lifetime_marker = marker.to_string_lossy().into();
        locator.record_path = record.to_string_lossy().into();
        let witness = NativeArtifactWitness {
            locator,
            record_sha256: sha256(b"native"),
        };
        assert!(witness.check().is_ok());
        fs::set_permissions(&record, fs::Permissions::from_mode(0o644)).unwrap();
        assert!(witness.check().is_err());
        fs::write(&record, b"change").unwrap();
        fs::set_permissions(&record, fs::Permissions::from_mode(0o444)).unwrap();
        assert!(witness.check().is_err());
        fs::set_permissions(&record, fs::Permissions::from_mode(0o644)).unwrap();
        fs::write(&record, b"native").unwrap();
        fs::set_permissions(&record, fs::Permissions::from_mode(0o444)).unwrap();
        fs::remove_file(marker).unwrap();
        assert!(witness.check().is_err());
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn only_exact_canonical_native_locators_are_interpreted() {
        let value = locator();
        assert_eq!(
            CookLocator::decode(&value.encode().unwrap()).unwrap(),
            value
        );
        for unknown in [
            "zen://chunk/abcdef",
            "https://example.test/entry",
            "atelier-zen-cook-v2:{}",
            "atelier-zen-cook-v1:{}",
        ] {
            assert!(CookLocator::decode(unknown).is_err());
        }
        assert!(CookLocator::decode(&value.encode().unwrap().replace("{", "{ ")).is_err());
        let mut negative_cell = locator();
        negative_cell.package = "/Game/Island/Terrain_cell_-1_0".into();
        assert!(negative_cell.validate().is_ok());
        let mut value = locator();
        value.dependency_key = "0".repeat(40);
        assert!(value.encode().is_err());
        let mut value = locator();
        value.project = "AtelierV2_other".into();
        assert!(value.encode().is_err());
        let mut value = locator();
        value.lifetime_marker = "/store/../elsewhere".into();
        assert!(value.encode().is_err());
        let mut value = locator();
        value.package = "/Game/A/../B".into();
        assert!(value.encode().is_err());
    }
}
