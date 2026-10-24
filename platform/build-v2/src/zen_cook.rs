//! Narrow external-cook authority. A locator is metadata, never proof.
//!
//! Only the independent fixed native verifier job's certified frozen output can
//! issue VerifiedPackage. The verifier body invokes the native library directly;
//! missing native support fails the job. Cook writers cannot issue this token.
use crate::completion::FrozenCompletion;
use crate::keys::{PreparedUnit, canonical_bytes};
use crate::schema::{Destination, Item};
use crate::source_hashes::{sha256, valid_digest};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::fs;
use std::io::Read;
use std::path::Path;

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
                   source_key=p['source_key'], dependency_key=report['native_stored_key'], entry_hash=report['root_hash'],
                   lifetime_marker=request['marker_path'], record_path=request['record_path'], project_file=request['project_file'])
    record_path = Path(request['record_path'])
    record_path.chmod(0o444)
    with record_path.open('rb') as source:
        record_sha256 = hashlib.file_digest(source, 'sha256').hexdigest()
    result = dict(version=1, locator=locator, record_io_hash=report['record_io_hash'], record_sha256=record_sha256, attachments=report['attachments'], mode=p['mode'])
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
            || self.oplog != "Mac"
            || self.project != format!("AtelierV2_{}", self.source_key)
            || self.project.len() > 100
            || !self
                .project
                .bytes()
                .all(|c| c.is_ascii_alphanumeric() || c == b'_')
            || !self.package.starts_with("/Game/")
            || self.package[6..].split('/').any(|part| {
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
        self.source_key == unit.key()
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
}

/// A live borrow of the independently verified frozen native result. There is no
/// Deserialize, boolean constructor, arbitrary callback or writer-report issuer.
pub struct VerifiedPackage<'a> {
    locator: CookLocator,
    proof: &'a FrozenCompletion,
    item: Item,
    source_unit: String,
    record_sha256: String,
}
impl<'a> VerifiedPackage<'a> {
    pub fn from_verifier(
        unit: &PreparedUnit,
        item: &Item,
        proof: &'a FrozenCompletion,
    ) -> Result<Self, String> {
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
        if p.get("source_key").and_then(|v| v.as_str()) != Some(unit.key())
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
            || !locator.matches(unit, item)
            || !native_hash(&report.record_io_hash)
            || !valid_digest(&report.record_sha256)
            || report.attachments == 0
            || report.attachments > 1_000_000
            || p.get("mode").and_then(|v| v.as_str()) != Some(report.mode.as_str())
        {
            return Err("native Zen report is incomplete or differs".into());
        }
        Ok(Self {
            locator,
            proof,
            item: item.clone(),
            source_unit: unit.request("", "").unit,
            record_sha256: report.record_sha256,
        })
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
        if self.proof.refused {
            return Err("native verifier completion was refused".into());
        }
        for object in self.proof.certified_objects()? {
            object.check_frozen().map_err(|e| e.to_string())?;
        }
        self.witness().check()
    }
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
            lifetime_marker: "/store/zen-cook/markers/key".into(),
            record_path: "/store/zen-cook/records/key.cb".into(),
            project_file: "/store/zen-cook/projects/key/Atelier.uproject".into(),
        }
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
