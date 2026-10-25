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
pub const VERIFY_BODY: &str = r#"import hashlib
import json
from pathlib import Path
import unreal

def run(context):
    p = context.params
    if set(p) != {'source_key', 'package', 'dependency_key', 'mode'} or p['mode'] not in ('capture', 'restore'):
        raise ValueError('Expected fixed logical native verification parameters')
    request = dict(context.zen_request)
    fields = {'version', 'mode', 'project', 'oplog', 'source_package', 'expected_stored_key', 'expected_root_hash',
              'record_path', 'project_file', 'marker_path', 'input_key', 'runtime_project_file'}
    if set(request) != fields or request['version'] != 1 or request['mode'] != p['mode']:
        raise ValueError('Missing trusted native execution context')
    if (request['input_key'] != p['source_key'] or request['source_package'] != p['package']
            or request['expected_stored_key'] != p['dependency_key']
            or request['project'] != 'AtelierV2_' + p['source_key'] or request['oplog'] != 'Mac'):
        raise ValueError('Native execution context differs from the logical source/package identity')
    runtime = Path(context.content_dir).parent / 'Atelier.uproject'
    if Path(request['runtime_project_file']) != runtime:
        raise ValueError('Native verification must run in the owned C3 scratch project')
    raw = json.dumps(request, sort_keys=True, separators=(',', ':'))
    report = json.loads(unreal.AtelierBuildWorkerLibrary.zen_package_request(raw))
    wanted_status = 'restored' if p['mode'] == 'restore' else 'verified'
    if (report.get('version') != 1 or report.get('status') != wanted_status
            or any(report.get(k) != request[k] for k in ('mode', 'project', 'oplog', 'source_package', 'input_key', 'runtime_project_file'))
            or report.get('native_stored_key') != p['dependency_key']
            or (request['expected_root_hash'] and report.get('root_hash') != request['expected_root_hash'])):
        raise ValueError('Independent native package verification refused or differed')
    locator = dict(version=1, project=request['project'], oplog=request['oplog'], package=p['package'],
                   source_key=p['source_key'], dependency_key=report['native_stored_key'], entry_hash=report['root_hash'], installed_entry_hash=report['installed_root_hash'],
                   lifetime_marker=request['marker_path'], record_path=request['record_path'], project_file=request['project_file'])
    record_path = Path(request['record_path'])
    record_path.chmod(0o444)
    with record_path.open('rb') as source:
        record_sha256 = hashlib.file_digest(source, 'sha256').hexdigest()
    result = dict(version=1, locator=locator, record_io_hash=report['record_io_hash'], record_sha256=record_sha256, attachments=report['attachments'], mode=p['mode'], source_dependency_evaluation=report['source_dependency_evaluation'])
    target = Path(context.job_dir) / 'output' / 'zen-verified.json'
    target.write_text(json.dumps(result, sort_keys=True, separators=(',', ':')), encoding='utf-8')
"#;

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
fn verifier_worker_digest() -> Result<String, String> {
    let files = BTreeMap::from([
        (
            "protocol.py".into(),
            include_bytes!("../../studio/atelier/build_v2/protocol.py").to_vec(),
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
        if self.version != 1
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
                part.is_empty() || !part.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'_')
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
            "atelier-zen-cook-v1:{}",
            String::from_utf8(canonical_bytes(self)?).map_err(|e| e.to_string())?
        ))
    }
    pub fn decode(text: &str) -> Result<Self, String> {
        let data = text
            .strip_prefix("atelier-zen-cook-v1:")
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
        unit.ingredients()
            .params
            .get("source_key")
            .and_then(|value| value.as_str())
            == Some(self.source_key.as_str())
            && item.destination == Destination::External
            && item.class == "CookedPackage"
            && item.files.is_empty()
            && self.package == item.logical_path
            && unit.ingredients().op.kind == "unreal.cook.package"
            && unit.ingredients().op.version == "1"
            && unit
                .ingredients()
                .params
                .get("dependency_key")
                .and_then(|v| v.as_str())
                == Some(&self.dependency_key)
    }
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
    producer: &'a FrozenCompletion,
    item: Item,
    source_unit: String,
    record_sha256: String,
}
impl<'a> VerifiedPackage<'a> {
    pub fn from_verifier(
        unit: &PreparedUnit,
        item: &Item,
        producer: &'a FrozenCompletion,
        proof: &'a FrozenCompletion,
    ) -> Result<Self, String> {
        let source = &producer.result().result;
        if producer.refused
            || source.ingredients.op.kind != "unreal.cook.produce"
            || source.ingredients.op.version != "1"
        {
            return Err(
                "source origin requires an actual fixed normal cook producer completion".into(),
            );
        }
        fixed_producer_worker(
            &source.ingredients.worker_version,
            &source.ingredients.worker_digest,
        )?;
        let source_item = consumed_native_record(&source.outputs, unit.inputs())?;
        let source_digest = &source_item.files[0].digest;
        for object in producer.certified_objects()? {
            object.check_frozen().map_err(|e| e.to_string())?;
        }
        let record = &proof.result().result;
        let ingredients = &record.ingredients;
        if proof.refused
            || record.key == unit.key()
            || ingredients.op.kind != VERIFY_OP
            || ingredients.op.version != "1"
            || ingredients.script != VERIFY_SCRIPT
            || ingredients.code.len() != 1
            || ingredients.code.get(VERIFY_SCRIPT) != Some(&sha256(VERIFY_BODY.as_bytes()))
            || ingredients.worker_version != crate::unreal::UNREAL_JOB_LOOP_VERSION
            || ingredients.worker_digest != verifier_worker_digest()?
            || ingredients.validator_digest != unit.ingredients().validator_digest
            || ingredients.validator_digest != validator_identity().digest
            || ingredients.validator_version != validator_identity().version
            || ingredients.content != unit.ingredients().content
            || !ingredients.references.is_empty()
            || !record.output_groups.is_empty()
            || ingredients.params.len() != 4
        {
            return Err("Zen proof is not the independent fixed native verifier".into());
        }
        let p = &ingredients.params;
        if p.get("source_key").and_then(|v| v.as_str()) != Some(source.key.as_str())
            || p.get("package").and_then(|v| v.as_str()) != Some(item.logical_path.as_str())
            || p.get("dependency_key") != unit.ingredients().params.get("dependency_key")
            || !matches!(
                p.get("mode").and_then(|v| v.as_str()),
                Some("capture" | "restore")
            )
        {
            return Err("native verifier parameters bind another source/package".into());
        }
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
            || locator.source_key != source.key
            || !locator.matches(unit, item)
            || !native_hash(&report.record_io_hash)
            || !valid_digest(&report.record_sha256)
            || report.record_sha256 != *source_digest
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
        if self.proof.refused || self.producer.refused {
            return Err("native verifier completion was refused".into());
        }
        for object in self
            .producer
            .certified_objects()?
            .into_iter()
            .chain(self.proof.certified_objects()?)
        {
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
    if locator.source_key != producer_key {
        return Err("native namespace does not bind the completed source producer".into());
    }
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
        .join(producer_key)
        .join("view")
        .join(logical_project);
    let marker = project
        .parent()
        .ok_or("source project has no directory")?
        .join("Saved/Cooked/Mac/ue.projectstore");
    let suffix = if names.len() == 1 {
        String::new()
    } else {
        format!("-{}", sha256(locator.package.as_bytes()))
    };
    let record = root
        .join("records")
        .join(format!("{producer_key}{suffix}.cb"));
    if Path::new(&locator.project_file) != project
        || Path::new(&locator.lifetime_marker) != marker
        || Path::new(&locator.record_path) != record
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
            version: 1,
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
        let declaration = Declaration {
            schema_version: 2,
            cache_version: "test".into(),
            units: vec![Unit {
                id: "external".into(),
                op: Op {
                    kind: "unreal.cook.package".into(),
                    version: "1".into(),
                },
                script: "cook.py".into(),
                code: vec!["cook.py".into()],
                inputs: vec![],
                params: BTreeMap::from([
                    ("source_key".into(), serde_json::json!(locator.source_key)),
                    (
                        "dependency_key".into(),
                        serde_json::json!(locator.dependency_key),
                    ),
                ]),
                outputs: vec![item.clone()],
                output_groups: vec![],
                conditional: None,
            }],
        };
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
            produced: &BTreeMap::new(),
            produced_groups: &BTreeMap::new(),
            staged_inputs: &BTreeMap::new(),
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
        assert!(validate_native_layout(&value, root, &"e".repeat(64), &params).is_err());
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
        assert!(validate_native_layout(&value, root, &key, &params).is_err());
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
        ] {
            assert!(CookLocator::decode(unknown).is_err());
        }
        assert!(CookLocator::decode(&value.encode().unwrap().replace("{", "{ ")).is_err());
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
