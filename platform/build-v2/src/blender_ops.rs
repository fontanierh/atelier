//! Unused D2 op contracts. Dispatch and native acceptance belong to later integration.
use crate::groups::{OutputGroupContract, PlanEncoding};
use crate::keys::{ImplementationIdentity, PreparedUnit, canonical_bytes};
use crate::launch::BLENDER_JOB_LOOP_VERSION;
use crate::schema::{Destination, IdentityIngredients, Item};
use crate::source_hashes::{sha256, valid_digest};
use crate::validate::{
    InputRole, InputRule, OpDefinition, OpRegistry, ParamKind, ParamRule, SnapshotEntry,
    SourceSnapshot,
};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::io::Read;

pub const BLENDER_PLAN_KIND: &str = "blender_plan";
pub const BLENDER_EXPORT_KIND: &str = "blender_export_piece";
pub const BLENDER_OP_VERSION: &str = "1";
pub const BLENDER_VALIDATOR_VERSION: &str = "atelier-blender-ops-validator-1";
pub const MESH_PAYLOAD_CLASS: &str = "GeometryPayload";
pub const MESH_EXPORT_CLASS: &str = "StaticMeshSource";
pub const MAX_MESH_IR_BYTES: u64 = 128 * 1024 * 1024;

/// The executed decoder closure; installed Python/NumPy/Blender versions are platform.
pub const DECODER_FILES: [&str; 9] = [
    "platform/studio/atelier/__init__.py",
    "platform/studio/atelier/build_v2/__init__.py",
    "platform/studio/atelier/build_v2/blender_validate.py",
    "platform/studio/atelier/mesh_ir.py",
    "platform/studio/atelier/mesh_collision.py",
    "platform/studio/atelier/mesh_materials.py",
    "platform/studio/atelier/export_manifest.py",
    "platform/studio/atelier/atomic_files.py",
    "platform/studio/atelier/model_files.py",
];

/// Minimum project-code closure; recipe entry and planner helpers are additional.
/// C2b's five startup files remain its separate frozen worker bundle.
pub fn blender_code_files(kind: &str) -> Result<Vec<&'static str>, String> {
    let mut files = DECODER_FILES.to_vec();
    files.push("platform/studio/atelier/build_v2/blender_ops.py");
    match kind {
        BLENDER_PLAN_KIND => {}
        BLENDER_EXPORT_KIND => files.extend([
            "platform/studio/atelier/build_v2/blender_geometry.py",
            "platform/studio/atelier/blender/__init__.py",
            "platform/studio/atelier/blender/fbx.py",
            "platform/studio/atelier/blender/gltf.py",
            "platform/studio/atelier/gltf.py",
        ]),
        _ => return Err("unsupported Blender op kind".into()),
    }
    Ok(files)
}

pub(crate) fn decoder_identity(
    files: &BTreeMap<&str, String>,
) -> Result<ImplementationIdentity, String> {
    Ok(ImplementationIdentity {
        version: BLENDER_VALIDATOR_VERSION.into(),
        digest: sha256(&canonical_bytes(&serde_json::json!({
            "domain":"atelier-blender-ops-validator", "version":BLENDER_VALIDATOR_VERSION,
            "op_version":BLENDER_OP_VERSION, "mesh_ir_limit":MAX_MESH_IR_BYTES, "files":files,
        }))?),
    })
}

pub fn blender_validator_identity(
    snapshot: &SourceSnapshot,
) -> Result<ImplementationIdentity, String> {
    let mut files = BTreeMap::new();
    for path in DECODER_FILES {
        let Some(SnapshotEntry::File(bytes)) = snapshot.get(path) else {
            return Err(format!(
                "decoder implementation is not frozen regular code: {path}"
            ));
        };
        files.insert(path, sha256(bytes));
    }
    decoder_identity(&files)
}

fn rule(kind: ParamKind, required: bool) -> ParamRule {
    ParamRule { kind, required }
}

/// A recipe supplies explicit slots and additional semantic parameters, never wildcard reads.
#[derive(Clone, Debug)]
pub struct BlenderPlanSpec {
    pub group: OutputGroupContract,
    pub inputs: BTreeMap<String, InputRule>,
    pub params: BTreeMap<String, ParamRule>,
}
impl BlenderPlanSpec {
    pub fn new(group: OutputGroupContract) -> Self {
        Self {
            group,
            inputs: BTreeMap::new(),
            params: BTreeMap::new(),
        }
    }
    pub fn definition(&self) -> Result<OpDefinition, String> {
        self.group.validate()?;
        if self.group.encoding != PlanEncoding::MeshIr
            || self.group.class != MESH_PAYLOAD_CLASS
            || self.group.manifest != "plan.json"
            || self.group.root_param != "output_root"
        {
            return Err("first blender_plan contract supports GeometryPayload mesh_ir only".into());
        }
        if self.group.max_member_bytes > MAX_MESH_IR_BYTES {
            return Err("mesh_ir member bound exceeds the existing decoder limit".into());
        }
        for (name, input) in &self.inputs {
            if name.trim().is_empty() || name.contains('*') {
                return Err("Blender inputs require explicit nonempty slot names".into());
            }
            if input.role == InputRole::Reference
                && (input.item_classes.is_empty()
                    || input.allow_absent_file
                    || input.allow_selector)
            {
                return Err(
                    "Blender references require explicit classes and no file selectors".into(),
                );
            }
        }
        let mut params = self.params.clone();
        if ["output_root", "parent", "plan_limits"]
            .iter()
            .any(|key| params.contains_key(*key))
        {
            return Err(
                "planner root/parent/limits parameters are reserved by its group contract".into(),
            );
        }
        if params
            .get("seed")
            .is_some_and(|p| !matches!(p.kind, ParamKind::Integer))
        {
            return Err("Blender seed must be an integer".into());
        }
        params
            .entry("seed".into())
            .or_insert_with(|| rule(ParamKind::Integer, false));
        params.insert(self.group.root_param.clone(), rule(ParamKind::String, true));
        params.insert("parent".into(), rule(ParamKind::String, true));
        params.insert("plan_limits".into(), rule(ParamKind::Object, true));
        Ok(OpDefinition {
            inputs: self.inputs.clone(),
            params,
            output_classes: BTreeSet::from([MESH_PAYLOAD_CLASS.into()]),
        })
    }
    pub fn register(&self, registry: &mut OpRegistry) -> Result<(), String> {
        let key = (BLENDER_PLAN_KIND.into(), BLENDER_OP_VERSION.into());
        if registry.contains_key(&key) {
            return Err("duplicate blender_plan definition".into());
        }
        registry.insert(key, self.definition()?);
        Ok(())
    }
    pub fn validate_ingredients(&self, ingredients: &IdentityIngredients) -> Result<(), String> {
        self.definition()?;
        if !ingredients.logical_outputs.is_empty()
            || ingredients.output_groups.len() != 1
            || ingredients.output_groups[0] != self.group
        {
            return Err(
                "blender_plan requires exactly its fixed store-only group and no fixed files"
                    .into(),
            );
        }
        self.group.validate_root_param(&ingredients.params)?;
        if ingredients
            .params
            .get("parent")
            .and_then(|value| value.as_str())
            != Some(self.group.parent.as_str())
            || ingredients.params.get("plan_limits")
                != Some(&serde_json::json!({
                    "max_pieces":self.group.max_pieces,
                    "max_manifest_bytes":self.group.max_manifest_bytes,
                    "max_member_bytes":self.group.max_member_bytes,
                    "max_total_bytes":self.group.max_total_bytes,
                }))
        {
            return Err(
                "worker-visible planner parent/limits differ from the fixed contract".into(),
            );
        }
        Ok(())
    }
}

#[derive(Clone, Debug)]
pub struct BlenderExportSpec {
    pub payload_slot: String,
}
impl Default for BlenderExportSpec {
    fn default() -> Self {
        Self {
            payload_slot: "payload".into(),
        }
    }
}
impl BlenderExportSpec {
    pub fn definition(&self) -> Result<OpDefinition, String> {
        if self.payload_slot != "payload" {
            return Err("the first piece exporter uses the explicit payload slot".into());
        }
        let inputs = BTreeMap::from([(
            self.payload_slot.clone(),
            InputRule {
                role: InputRole::Content,
                required: true,
                allow_absent_file: false,
                allow_selector: false,
                require_whole_reason: false,
                item_classes: BTreeSet::from([MESH_PAYLOAD_CLASS.into()]),
            },
        )]);
        let mut params: BTreeMap<_, _> = [
            "format",
            "payload_member",
            "payload_encoding",
            "payload_role",
        ]
        .into_iter()
        .map(|name| (name.into(), rule(ParamKind::String, true)))
        .collect();
        params.insert("seed".into(), rule(ParamKind::Integer, false));
        params.insert("options".into(), rule(ParamKind::Object, false));
        Ok(OpDefinition {
            inputs,
            params,
            output_classes: BTreeSet::from([MESH_EXPORT_CLASS.into()]),
        })
    }
    pub fn register(&self, registry: &mut OpRegistry) -> Result<(), String> {
        let key = (BLENDER_EXPORT_KIND.into(), BLENDER_OP_VERSION.into());
        if registry.contains_key(&key) {
            return Err("duplicate blender_export_piece definition".into());
        }
        registry.insert(key, self.definition()?);
        Ok(())
    }
    /// @cc [owner:fontanierh,label:correctness] blender-piece-selected-contract
    /// A first-slice export MUST consume exactly one present MeshIR projection and own one complete
    /// store-only FBX or GLB plus receipt, matching its explicit format parameter. A planner key,
    /// roster or sibling MUST NOT become a child input.
    /// Unsupported encodings, roles and formats MUST refuse, never silently drop materials/collision.
    /// See tests/blender_ops.rs and the Python decoder/contract fixtures.
    pub fn validate_ingredients(&self, ingredients: &IdentityIngredients) -> Result<(), String> {
        self.definition()?;
        if ingredients.content.len() != 1
            || !ingredients.content.contains_key(&self.payload_slot)
            || !ingredients.references.is_empty()
            || !ingredients.output_groups.is_empty()
        {
            return Err(
                "piece exporter requires only its selected payload, no references or groups".into(),
            );
        }
        if matches!(
            ingredients.content[&self.payload_slot],
            crate::schema::ContentIdentity::Absent {}
        ) {
            return Err("piece payload must be present".into());
        }
        if ingredients.input_kinds.get(&self.payload_slot) != Some(&crate::schema::InputKind::Item)
        {
            return Err("piece exporter requires one selected Item directory".into());
        }
        for (name, expected) in [
            ("payload_encoding", "mesh_ir"),
            ("payload_role", "geometry"),
        ] {
            if ingredients.params.get(name).and_then(|v| v.as_str()) != Some(expected) {
                return Err(format!("unsupported piece {name}; expected {expected}"));
            }
        }
        let format = ingredients
            .params
            .get("format")
            .and_then(Value::as_str)
            .filter(|value| matches!(*value, "fbx" | "glb"))
            .ok_or("unsupported piece export format")?;
        let member = ingredients
            .params
            .get("payload_member")
            .and_then(|v| v.as_str())
            .ok_or("missing selected payload member")?;
        crate::paths::relative_path(member, false)?;
        if !member.ends_with(".npz") || member.contains('/') {
            return Err("MeshIR payload member must be .npz".into());
        }
        if ingredients.logical_outputs.len() != 1 {
            return Err("piece exporter owns exactly one Item".into());
        }
        let item = &ingredients.logical_outputs[0];
        validate_export_item(item)?;
        if !export_primary_path(item)?.ends_with(&format!(".{format}")) {
            return Err("piece primary differs from its explicit export format".into());
        }
        Ok(())
    }
}

fn atomic_name(value: &str) -> bool {
    !value.is_empty()
        && value.chars().enumerate().all(|(i, c)| {
            (i > 0 && (c.is_ascii_digit() || c == '_' || c == '-')) || c.is_ascii_alphabetic()
        })
}

fn export_primary_path(item: &Item) -> Result<&str, String> {
    if item.files.len() != 2
        || item
            .files
            .iter()
            .any(|f| !f.required || f.install_path.is_some())
        || item
            .files
            .iter()
            .filter(|f| f.path == "export.json")
            .count()
            != 1
    {
        return Err("piece export must own exactly one required FBX and export.json".into());
    }
    let primary = item
        .files
        .iter()
        .find(|f| f.path != "export.json")
        .ok_or("missing FBX primary")?;
    let stem = primary
        .path
        .strip_suffix(".fbx")
        .or_else(|| primary.path.strip_suffix(".glb"))
        .ok_or("primary must be FBX or GLB")?;
    if !atomic_name(stem) {
        return Err("FBX primary must be one canonical flat filename".into());
    }
    Ok(&primary.path)
}

pub fn validate_export_item(item: &Item) -> Result<(), String> {
    if item.destination != Destination::Store || item.class != MESH_EXPORT_CLASS {
        return Err("piece exports are store-only StaticMeshSource items".into());
    }
    export_primary_path(item)?;
    Ok(())
}

pub fn check_blender_identity(
    unit: &PreparedUnit,
    kind: &str,
    validator: &ImplementationIdentity,
) -> Result<(), String> {
    let i = unit.ingredients();
    if ![BLENDER_PLAN_KIND, BLENDER_EXPORT_KIND].contains(&kind)
        || i.op.kind != kind
        || i.op.version != BLENDER_OP_VERSION
    {
        return Err("unsupported Blender op/version".into());
    }
    if blender_code_files(kind)?
        .iter()
        .any(|path| !i.code.contains_key(*path))
    {
        return Err("declared Blender job code omits a required body/decoder/export helper".into());
    }
    let decoder_files = DECODER_FILES
        .into_iter()
        .map(|path| (path, i.code[path].clone()))
        .collect();
    let declared_validator = decoder_identity(&decoder_files)?;
    if declared_validator.digest != validator.digest {
        return Err("validator identity differs from the exact declared decoder code".into());
    }
    if i.worker_version != BLENDER_JOB_LOOP_VERSION
        || !valid_digest(&i.worker_digest)
        || i.validator_version != validator.version
        || i.validator_digest != validator.digest
        || validator.version != BLENDER_VALIDATOR_VERSION
        || !valid_digest(&validator.digest)
    {
        return Err(
            "Blender worker/validator identity differs from the frozen implementation".into(),
        );
    }
    Ok(())
}

fn unsigned<'a>(value: &'a Value, field: &str) -> Result<u64, String> {
    value
        .get(field)
        .and_then(Value::as_u64)
        .ok_or_else(|| format!("missing unsigned {field}"))
}
fn vector(value: &Value, width: usize) -> bool {
    value.as_array().is_some_and(|values| {
        values.len() == width
            && values
                .iter()
                .all(|v| v.as_f64().is_some_and(f64::is_finite))
    })
}
fn strings(value: &Value) -> bool {
    value.as_array().is_some_and(|values| {
        !values.is_empty()
            && values
                .iter()
                .all(|v| v.as_str().is_some_and(|s| !s.is_empty()))
    })
}

const PLAN_FIELDS: [&str; 12] = [
    "schema",
    "parent",
    "complete",
    "triangle_limit",
    "partition",
    "source_triangles",
    "source_polygons",
    "source_collision_hulls",
    "collision_owner",
    "slots",
    "matrix",
    "pieces",
];
const MEMBER_FIELDS: [&str; 11] = [
    "name",
    "payload",
    "sha256",
    "triangles",
    "polygons",
    "source_faces",
    "min",
    "max",
    "collision_hulls",
    "slots",
    "source_material_indices",
];

#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
#[allow(dead_code)]
struct PlanWire {
    schema: u32,
    parent: String,
    complete: bool,
    triangle_limit: u64,
    partition: String,
    source_triangles: u64,
    source_polygons: u64,
    source_collision_hulls: u64,
    collision_owner: Option<String>,
    slots: Vec<String>,
    matrix: [[f64; 4]; 4],
    pieces: Vec<PlanMemberWire>,
}
#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
#[allow(dead_code)]
struct PlanMemberWire {
    name: String,
    payload: String,
    sha256: String,
    triangles: u64,
    polygons: u64,
    source_faces: Vec<u64>,
    min: [f64; 3],
    max: [f64; 3],
    collision_hulls: u64,
    slots: Vec<String>,
    source_material_indices: Vec<u64>,
}

/// D2's closed metadata schema and duplicate-field refusal over exact frozen manifest bytes.
/// This parses discovery metadata only, not another mesh IR or payload decoder.
pub fn parse_blender_plan_metadata(raw: &[u8], max_bytes: u64) -> Result<Value, String> {
    if raw.len() as u64 > max_bytes {
        return Err("plan manifest byte bound exceeded".into());
    }
    let value: Value = serde_json::from_slice(raw).map_err(|e| e.to_string())?;
    validate_plan_metadata(&value)?;
    let _: PlanWire = serde_json::from_slice(raw).map_err(|e| e.to_string())?;
    Ok(value)
}

/// Metadata checks only. Geometry semantics are verified by the keyed in-job producer/consumer.
pub fn validate_plan_metadata(raw: &Value) -> Result<(), String> {
    let fields: BTreeSet<_> = raw
        .as_object()
        .ok_or("plan must be an object")?
        .keys()
        .map(String::as_str)
        .collect();
    if fields != BTreeSet::from(PLAN_FIELDS)
        || unsigned(raw, "schema")? != 1
        || raw["complete"] != true
        || unsigned(raw, "triangle_limit")? != 32768
        || unsigned(raw, "source_triangles")? == 0
    {
        return Err("unknown, missing or unsupported D2 plan fields".into());
    }
    let polygons = unsigned(raw, "source_polygons")?;
    if polygons == 0
        || !strings(&raw["slots"])
        || !raw["matrix"]
            .as_array()
            .is_some_and(|rows| rows.len() == 4 && rows.iter().all(|r| vector(r, 4)))
    {
        return Err("incomplete plan polygon/material/frame metadata".into());
    }
    let rows = raw["pieces"].as_array().ok_or("missing plan pieces")?;
    if rows.is_empty() {
        return Err("empty plan".into());
    }
    let mut owned = BTreeSet::new();
    let mut total = 0u64;
    for row in rows {
        let fields: BTreeSet<_> = row
            .as_object()
            .ok_or("member must be an object")?
            .keys()
            .map(String::as_str)
            .collect();
        if fields != BTreeSet::from(MEMBER_FIELDS)
            || unsigned(row, "triangles")? == 0
            || unsigned(row, "collision_hulls").is_err()
        {
            return Err("unknown, missing or unsupported D2 member fields/role".into());
        }
        if !vector(&row["min"], 3)
            || !vector(&row["max"], 3)
            || row["min"]
                .as_array()
                .unwrap()
                .iter()
                .zip(row["max"].as_array().unwrap())
                .any(|(a, b)| a.as_f64().unwrap() > b.as_f64().unwrap())
        {
            return Err("invalid planned bounds".into());
        }
        let count = unsigned(row, "polygons")?;
        let faces = row["source_faces"]
            .as_array()
            .ok_or("missing source-face inventory")?;
        if count == 0 || faces.len() as u64 != count {
            return Err("incomplete piece face inventory".into());
        }
        let mut previous = None;
        for face in faces {
            let id = face.as_u64().ok_or("invalid source face")?;
            if id >= polygons || previous.is_some_and(|p| p >= id) || !owned.insert(id) {
                return Err("overlapping, out-of-range or reordered source faces".into());
            }
            previous = Some(id);
        }
        total = total.checked_add(count).ok_or("polygon total overflow")?;
        if let Some(slots) = row.get("slots") {
            if !strings(slots) {
                return Err("invalid piece material table".into());
            }
            let indices = row["source_material_indices"]
                .as_array()
                .ok_or("missing piece material ownership")?;
            let parent = raw["slots"].as_array().unwrap();
            if indices.len() != slots.as_array().unwrap().len() {
                return Err("piece material mapping differs".into());
            }
            let mut prior = None;
            for (index, slot) in indices.iter().zip(slots.as_array().unwrap()) {
                let i = index.as_u64().ok_or("invalid material index")?;
                if i >= parent.len() as u64
                    || prior.is_some_and(|p| p >= i)
                    || parent[i as usize] != *slot
                {
                    return Err("piece material mapping differs".into());
                }
                prior = Some(i);
            }
        }
    }
    if total != polygons || owned.len() as u64 != polygons {
        return Err("incomplete polygon conservation".into());
    }
    let hulls = unsigned(raw, "source_collision_hulls")?;
    if (hulls == 0 && !raw["collision_owner"].is_null())
        || (hulls > 0 && raw["collision_owner"] != rows[0]["name"])
    {
        return Err("whole collision owner differs from its explicit first piece".into());
    }
    match raw["partition"].as_str() {
        Some("whole") if rows.len() == 1 && rows[0]["name"] == raw["parent"] => Ok(()),
        Some("logical" | "spatial") => Ok(()),
        _ => Err("unsupported/inconsistent whole partition policy".into()),
    }
}

/// @cc [owner:fontanierh,label:correctness] d2-frozen-plan-binding
/// B2 validation MUST inspect only its supplied certified frozen objects, checking complete
/// inventory/schema/roles/limits/bounds and digest bindings independently. It MUST NOT claim a
/// second semantic geometry decode: the keyed producer verifies emitted bytes before Completed
/// and the consumer fully decodes its selected payload. No live producer path is read here.
/// See tests/blender_ops.rs and test_build_v2_blender_ops.py.
pub fn validate_blender_plan_outputs(
    unit: &PreparedUnit,
    spec: &BlenderPlanSpec,
    validator: &ImplementationIdentity,
    objects: &BTreeMap<String, &crate::store::PreparedObject>,
) -> Result<crate::groups::ValidatedGroup, String> {
    check_blender_identity(unit, BLENDER_PLAN_KIND, validator)?;
    spec.validate_ingredients(unit.ingredients())?;
    validate_geometry_outputs(&spec.group, objects)
}

pub fn validate_geometry_outputs(
    contract: &OutputGroupContract,
    objects: &BTreeMap<String, &crate::store::PreparedObject>,
) -> Result<crate::groups::ValidatedGroup, String> {
    crate::groups::validate_frozen(contract, objects, |roster, objects| {
        if objects
            .values()
            .any(|o| crate::keys::normalized_mode(o.source_mode()) != 0o644)
        {
            return Err("plan data members must not be executable".into());
        }
        let manifest = objects
            .get(&contract.manifest)
            .ok_or("missing frozen manifest")?;
        let mut bytes = Vec::new();
        manifest
            .reader()
            .map_err(|e| e.to_string())?
            .take(contract.max_manifest_bytes)
            .read_to_end(&mut bytes)
            .map_err(|e| e.to_string())?;
        if bytes.len() as u64 != manifest.size() {
            return Err("frozen manifest size differs".into());
        }
        let strict = if contract.encoding == PlanEncoding::MeshIr {
            parse_blender_plan_metadata(&bytes, contract.max_manifest_bytes)?
        } else if contract.encoding == PlanEncoding::EncodedGlb {
            crate::py_data::validate_py_data_payload("JsonData", "plan.json", &bytes)?;
            serde_json::from_slice(&bytes).map_err(|e| e.to_string())?
        } else {
            return Err("unsupported producer geometry encoding".into());
        };
        if &strict != roster.raw() {
            return Err("frozen metadata views differ".into());
        }
        Ok(())
    })
}

/// The digest comes from A3's sealed selected member metadata, not the producer input key.
pub fn selected_payload(unit: &PreparedUnit) -> Result<&crate::schema::StoredFile, String> {
    let member = unit
        .ingredients()
        .params
        .get("payload_member")
        .and_then(Value::as_str)
        .ok_or("missing selected member")?;
    let input = unit
        .inputs()
        .iter()
        .find(|i| i.wire.name == "payload")
        .ok_or("missing payload slot")?;
    let crate::keys::InputPayload::Item { class, files, .. } = &input.payload else {
        return Err("selected payload must be one typed member Item".into());
    };
    if class != MESH_PAYLOAD_CLASS
        || files.len() != 1
        || files[0].path != member
        || files[0].mode != 0o644
    {
        return Err("selected payload identity or membership differs".into());
    }
    Ok(&files[0])
}

#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
#[allow(dead_code)]
struct ReceiptWire {
    schema: u32,
    asset: String,
    primary: String,
    triangles: u64,
    bounds: [[f64; 3]; 2],
    sha256: String,
    metadata: ReceiptMetadataWire,
}
#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
#[allow(dead_code)]
struct ReceiptMetadataWire {
    geometry_sha256: String,
    slots: Vec<String>,
    polygons: u64,
    collision_hulls: u64,
    uv_channels: Vec<String>,
}

/// Strict bounded receipt schema, including duplicate typed fields at both object levels.
pub fn parse_export_receipt(raw: &[u8]) -> Result<Value, String> {
    if raw.len() > 1024 * 1024 {
        return Err("receipt byte bound exceeded".into());
    }
    let value: Value = serde_json::from_slice(raw).map_err(|e| e.to_string())?;
    if !value.is_object() || !value["metadata"].is_object() {
        return Err("receipt and metadata must be objects".into());
    }
    let _: ReceiptWire = serde_json::from_slice(raw).map_err(|e| e.to_string())?;
    Ok(value)
}

pub fn validate_receipt_metadata(
    receipt: &Value,
    item: &Item,
    selected_asset: &str,
    primary_digest: &str,
    payload_digest: &str,
) -> Result<(), String> {
    validate_export_item(item)?;
    let object = receipt.as_object().ok_or("receipt must be an object")?;
    let fields: BTreeSet<_> = object.keys().map(String::as_str).collect();
    if fields
        != BTreeSet::from([
            "schema",
            "asset",
            "primary",
            "triangles",
            "bounds",
            "sha256",
            "metadata",
        ])
        || unsigned(receipt, "schema")? != 1
        || !atomic_name(selected_asset)
        || receipt["asset"] != selected_asset
        || receipt["primary"] != export_primary_path(item)?
        || receipt["sha256"] != primary_digest
        || !valid_digest(primary_digest)
        || !valid_digest(payload_digest)
    {
        return Err("foreign, malformed or mismatched export receipt".into());
    }
    let triangles = unsigned(receipt, "triangles")?;
    let bounds = receipt["bounds"]
        .as_array()
        .ok_or("missing receipt bounds")?;
    if triangles == 0
        || triangles > 32768
        || bounds.len() != 2
        || !bounds.iter().all(|r| vector(r, 3))
        || bounds[0]
            .as_array()
            .unwrap()
            .iter()
            .zip(bounds[1].as_array().unwrap())
            .any(|(a, b)| a.as_f64().unwrap() > b.as_f64().unwrap())
    {
        return Err("invalid export triangle/bounds metadata".into());
    }
    let metadata = &receipt["metadata"];
    let fields = metadata
        .as_object()
        .ok_or("receipt metadata must be an object")?
        .keys()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    if fields
        != BTreeSet::from([
            "geometry_sha256",
            "slots",
            "polygons",
            "collision_hulls",
            "uv_channels",
        ])
        || metadata["geometry_sha256"] != payload_digest
        || !strings(&metadata["slots"])
        || unsigned(metadata, "polygons")? == 0
        || unsigned(metadata, "collision_hulls").is_err()
        || !metadata["uv_channels"]
            .as_array()
            .is_some_and(|v| v.iter().all(|x| x.is_string()))
    {
        return Err(
            "receipt is not bound to its selected payload/material/collision inventory".into(),
        );
    }
    Ok(())
}

pub fn validate_blender_export_outputs(
    unit: &PreparedUnit,
    validator: &ImplementationIdentity,
    outputs: &[crate::results::FrozenOutput<'_>],
) -> Result<(), String> {
    check_blender_identity(unit, BLENDER_EXPORT_KIND, validator)?;
    BlenderExportSpec::default().validate_ingredients(unit.ingredients())?;
    let payload = selected_payload(unit)?;
    let item = &unit.ingredients().logical_outputs[0];
    if outputs.len() != 2
        || outputs.iter().any(|o| {
            o.item != item || crate::keys::normalized_mode(o.object.source_mode()) != 0o644
        })
    {
        return Err("incomplete or foreign frozen export set".into());
    }
    let primary_name = export_primary_path(item)?;
    let primary = outputs
        .iter()
        .find(|o| o.path == primary_name)
        .ok_or("missing frozen FBX")?;
    let receipt = outputs
        .iter()
        .find(|o| o.path == "export.json")
        .ok_or("missing frozen receipt")?;
    if receipt.object.size() > 1024 * 1024 {
        return Err("receipt byte bound exceeded".into());
    }
    let mut raw = Vec::new();
    receipt
        .object
        .reader()
        .map_err(|e| e.to_string())?
        .take(1024 * 1024 + 1)
        .read_to_end(&mut raw)
        .map_err(|e| e.to_string())?;
    if raw.len() as u64 != receipt.object.size() {
        return Err("frozen receipt size differs".into());
    }
    let value = parse_export_receipt(&raw)?;
    validate_receipt_metadata(
        &value,
        item,
        payload
            .path
            .strip_suffix(".npz")
            .ok_or("selected payload must be MeshIR")?,
        primary.object.digest().as_hex(),
        &payload.digest,
    )?;
    if primary_name.ends_with(".glb") {
        let mut header = [0u8; 12];
        primary
            .object
            .reader()
            .map_err(|e| e.to_string())?
            .read_exact(&mut header)
            .map_err(|e| e.to_string())?;
        if &header[..4] != b"glTF"
            || u32::from_le_bytes(header[4..8].try_into().unwrap()) != 2
            || u32::from_le_bytes(header[8..12].try_into().unwrap()) as u64 != primary.object.size()
        {
            return Err("frozen primary is not complete GLB2 framing".into());
        }
        return Ok(());
    }
    let header = b"Kaydara FBX Binary  \x00\x1a\x00";
    let mut actual = vec![0; header.len()];
    primary
        .object
        .reader()
        .map_err(|e| e.to_string())?
        .read_exact(&mut actual)
        .map_err(|e| e.to_string())?;
    if actual.as_slice() != header || primary.object.size() <= header.len() as u64 + 4 {
        return Err("frozen primary is not binary FBX framing".into());
    }
    Ok(())
}
