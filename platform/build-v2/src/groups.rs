//! Bounded discovery metadata and private validation tokens for opaque D2 payloads.
//! No geometry IR, live directory discovery, publication, dispatch or deletion.
use crate::keys::normalized_mode;
use crate::paths::{Claims, claim, logical_path, relative_path};
use crate::schema::{Destination, Item, OutputFile, StoredFile, StoredItem};
use crate::source_hashes::valid_digest;
use crate::store::PreparedObject;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::io::Read;

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PlanEncoding {
    MeshIr,
    MeshSet,
    EncodedGlb,
}

/// Fixed before execution. Runtime names/membership must never replace this contract.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OutputGroupContract {
    pub id: String,
    /// Relative to the job output directory, exclusive to this group.
    pub root: String,
    /// Declared semantic param containing the worker-visible output/<root> path.
    pub root_param: String,
    /// Relative to root, owned by the group rather than a second fixed Item.
    pub manifest: String,
    pub adapter_version: String,
    pub parent: String,
    pub encoding: PlanEncoding,
    pub class: String,
    pub logical_namespace: String,
    pub max_pieces: u64,
    pub max_manifest_bytes: u64,
    pub max_member_bytes: u64,
    pub max_total_bytes: u64,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MemberProjection {
    pub payload: String,
    pub encoding: PlanEncoding,
    pub role: Option<EncodedRole>,
    /// Only this selected member's validated runtime policy; siblings stay outside its key.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub metadata: Option<Value>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EncodedRole {
    Render,
    Collision,
}

/// Complete immutable result data. Deserialization alone grants no validation token.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StoredOutputGroup {
    pub id: String,
    pub files: Vec<StoredFile>,
    pub projections: BTreeMap<String, MemberProjection>,
}

/// Discovery checks only; the source-specific validator still certifies the payloads.
#[derive(Debug)]
pub struct PlanRoster {
    raw: Value,
    stored: StoredOutputGroup,
}
impl PlanRoster {
    pub fn raw(&self) -> &Value {
        &self.raw
    }
    pub fn stored(&self) -> &StoredOutputGroup {
        &self.stored
    }
}

/// Only frozen-source validation or trusted result restoration can issue this token.
/// It does not publish anything; B2 must match it to its own leased prepared objects.
#[derive(Debug)]
pub struct ValidatedGroup {
    contract: OutputGroupContract,
    stored: StoredOutputGroup,
}
impl ValidatedGroup {
    pub fn contract(&self) -> &OutputGroupContract {
        &self.contract
    }
    pub fn stored(&self) -> &StoredOutputGroup {
        &self.stored
    }
    pub fn project(&self, piece: &str) -> Result<StoredItem, String> {
        project_member(&self.contract, &self.stored, piece)
    }
}

/// Identity evidence from a trusted immutable record, explicitly NOT blob availability.
/// Only B2's exact-key metadata reader constructs it; it cannot become ValidatedGroup.
#[derive(Debug)]
pub struct RecordedGroupIdentity {
    contract: OutputGroupContract,
    stored: StoredOutputGroup,
}
impl RecordedGroupIdentity {
    pub fn contract(&self) -> &OutputGroupContract {
        &self.contract
    }
    pub fn pieces(&self) -> impl Iterator<Item = &str> {
        self.stored.projections.keys().map(String::as_str)
    }
    pub fn projection(&self, piece: &str) -> Result<&MemberProjection, String> {
        self.stored
            .projections
            .get(piece)
            .ok_or_else(|| "unknown projected piece".into())
    }
    /// Selected content view only: no planner input key, roster digest or sibling bytes.
    pub fn project(&self, piece: &str) -> Result<StoredItem, String> {
        project_member(&self.contract, &self.stored, piece)
    }
}

fn project_member(
    contract: &OutputGroupContract,
    stored: &StoredOutputGroup,
    piece: &str,
) -> Result<StoredItem, String> {
    let projection = stored
        .projections
        .get(piece)
        .ok_or("unknown projected piece")?;
    let file = stored
        .files
        .iter()
        .find(|file| file.path == projection.payload)
        .ok_or("projected member is absent")?
        .clone();
    Ok(StoredItem {
        item: Item {
            id: piece.into(),
            logical_path: format!("{}/{piece}", contract.logical_namespace),
            class: contract.class.clone(),
            destination: Destination::Store,
            files: vec![OutputFile {
                path: file.path.clone(),
                install_path: None,
                required: true,
            }],
        },
        files: vec![file],
        external_locator: None,
    })
}

/// @cc [owner:fontanierh,label:correctness] recorded-group-is-not-available
/// B2 may issue identity evidence only after matching the exact prepared record/contract and
/// complete saved projection metadata. This MUST NOT certify payload availability, recreate
/// source validation from an opaque plan, or expose/convert to the available ValidatedGroup.
/// Source adapters requiring missing payloads MUST fail rather than guess. See metadata_only_group_preserves_projection_without_certifying_availability.
pub(crate) fn recorded_identity(
    contract: &OutputGroupContract,
    stored: &StoredOutputGroup,
) -> Result<RecordedGroupIdentity, String> {
    check_recorded(contract, stored)?;
    Ok(RecordedGroupIdentity {
        contract: contract.clone(),
        stored: stored.clone(),
    })
}

pub(crate) fn name(value: &str) -> Result<(), String> {
    if !value
        .as_bytes()
        .first()
        .is_some_and(u8::is_ascii_alphabetic)
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"_-".contains(&byte))
    {
        return Err(format!("invalid authored piece/group name: {value:?}"));
    }
    Ok(())
}
fn text<'a>(value: &'a Value, field: &str) -> Result<&'a str, String> {
    value
        .get(field)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("missing string {field}"))
}
fn integer(value: &Value, field: &str) -> Result<u64, String> {
    value
        .get(field)
        .and_then(Value::as_u64)
        .ok_or_else(|| format!("missing unsigned integer {field}"))
}

impl OutputGroupContract {
    pub fn validate_root_param(&self, params: &crate::schema::Params) -> Result<(), String> {
        if params.get(&self.root_param) != Some(&Value::String(format!("output/{}", self.root))) {
            return Err("output group root differs from explicit keyed worker param".into());
        }
        Ok(())
    }
    pub fn validate(&self) -> Result<(), String> {
        name(&self.id)?;
        name(&self.parent)?;
        name(&self.root_param)?;
        relative_path(&self.root, true)?;
        relative_path(&self.manifest, true)?;
        logical_path(&self.logical_namespace)?;
        if self.adapter_version.trim().is_empty()
            || self.class.trim().is_empty()
            || self.max_pieces == 0
            || self.max_manifest_bytes == 0
            || self.max_member_bytes == 0
            || self.max_total_bytes == 0
            || self.max_manifest_bytes > self.max_member_bytes
            || self.max_member_bytes > self.max_total_bytes
        {
            return Err("invalid bounded output-group contract".into());
        }
        Ok(())
    }
}

/// Share one output-namespace policy with A2, including group/fixed aliases and ancestors.
pub fn validate_ownership(groups: &[OutputGroupContract], fixed: &[String]) -> Result<(), String> {
    let mut claims = Claims::new();
    for path in fixed {
        relative_path(path, true)?;
        claim(&mut claims, path, "fixed output")?;
    }
    let mut ids = BTreeSet::new();
    for group in groups {
        group.validate()?;
        if !ids.insert(&group.id) {
            return Err("duplicate output group id".into());
        }
        claim(&mut claims, &group.root, &group.id)?;
    }
    Ok(())
}

fn check_recorded(
    contract: &OutputGroupContract,
    stored: &StoredOutputGroup,
) -> Result<(), String> {
    contract.validate()?;
    if stored.id != contract.id
        || stored.projections.is_empty()
        || stored.projections.len() as u64 > contract.max_pieces
    {
        return Err("wrong group identity or piece count".into());
    }
    let mut claims = Claims::new();
    let mut by_path = BTreeMap::new();
    let mut total = 0u64;
    for file in &stored.files {
        relative_path(&file.path, true)?;
        claim(&mut claims, &file.path, "group member")?;
        if !valid_digest(&file.digest)
            || ![0o644, 0o755].contains(&file.mode)
            || file.size > contract.max_member_bytes
        {
            return Err("invalid group member digest/mode/size".into());
        }
        total = total.checked_add(file.size).ok_or("group size overflow")?;
        by_path.insert(file.path.as_str(), file);
    }
    if total > contract.max_total_bytes {
        return Err("group byte budget exceeded".into());
    }
    let manifest = by_path
        .get(contract.manifest.as_str())
        .ok_or("missing group manifest")?;
    if manifest.size > contract.max_manifest_bytes {
        return Err("manifest byte budget exceeded".into());
    }
    let mut expected = BTreeSet::from([contract.manifest.as_str()]);
    let mut pieces = Claims::new();
    for (piece, projection) in &stored.projections {
        name(piece)?;
        claim(&mut pieces, piece, "piece")?;
        if projection.encoding != contract.encoding {
            return Err("wrong projected payload type".into());
        }
        if (projection.encoding == PlanEncoding::EncodedGlb) != projection.role.is_some() {
            return Err("wrong projected payload role".into());
        }
        if (projection.encoding == PlanEncoding::MeshSet) != projection.metadata.is_some()
            || projection
                .metadata
                .as_ref()
                .is_some_and(|value| !value.is_object())
        {
            return Err("wrong projected member metadata".into());
        }
        let suffix = match contract.encoding {
            PlanEncoding::EncodedGlb => ".mesh",
            _ => ".npz",
        };
        if projection.payload != format!("{piece}{suffix}")
            || !expected.insert(projection.payload.as_str())
            || !by_path.contains_key(projection.payload.as_str())
        {
            return Err("missing, duplicate or foreign projected payload".into());
        }
    }
    if expected != by_path.keys().copied().collect() {
        return Err("foreign or incomplete group membership".into());
    }
    Ok(())
}

/// Parse the existing plan envelope, never reinterpret its opaque geometry payloads.
/// This alone is not a source-format certificate or a publication token.
pub fn parse_manifest(
    contract: &OutputGroupContract,
    bytes: &[u8],
    files: &[StoredFile],
) -> Result<PlanRoster, String> {
    contract.validate()?;
    if bytes.len() as u64 > contract.max_manifest_bytes {
        return Err("manifest byte budget exceeded".into());
    }
    let raw: Value = serde_json::from_slice(bytes).map_err(|error| error.to_string())?;
    if integer(&raw, "schema")? != 1
        || text(&raw, "parent")? != contract.parent
        || raw.get("complete") != Some(&Value::Bool(true))
        || integer(&raw, "triangle_limit")? != 32768
    {
        return Err("incomplete, foreign or unsupported plan".into());
    }
    let expected_kind = match contract.encoding {
        PlanEncoding::MeshIr => None,
        PlanEncoding::MeshSet => Some("mesh_set"),
        PlanEncoding::EncodedGlb => Some("encoded_glb"),
    };
    if raw.get("kind").and_then(Value::as_str) != expected_kind
        || (expected_kind.is_none() && raw.get("kind").is_some())
    {
        return Err("wrong plan encoding".into());
    }
    let rows = raw
        .get("pieces")
        .and_then(Value::as_array)
        .ok_or("missing pieces")?;
    if rows.is_empty() || rows.len() as u64 > contract.max_pieces {
        return Err("piece count budget exceeded".into());
    }
    let mut projections = BTreeMap::new();
    let mut triangles = 0u64;
    let mut render_triangles = 0u64;
    let mut collision_triangles = 0u64;
    if contract.encoding == PlanEncoding::MeshSet && integer(&raw, "source_collision_hulls")? != 0 {
        return Err("mesh-set cannot duplicate whole collision ownership".into());
    }
    let metadata = if contract.encoding == PlanEncoding::MeshSet {
        let metadata = raw
            .get("metadata")
            .and_then(Value::as_object)
            .ok_or("missing mesh-set member metadata")?;
        let names: BTreeSet<_> = rows
            .iter()
            .map(|row| text(row, "name"))
            .collect::<Result<_, _>>()?;
        if metadata.keys().map(String::as_str).collect::<BTreeSet<_>>() != names
            || metadata.values().any(|value| !value.is_object())
        {
            return Err("mesh-set metadata membership differs".into());
        }
        Some(metadata)
    } else {
        None
    };
    for (index, row) in rows.iter().enumerate() {
        let piece = text(row, "name")?;
        name(piece)?;
        let count = integer(row, "triangles")?;
        if count == 0 || count > 32768 {
            return Err("piece triangle budget exceeded".into());
        }
        triangles = triangles
            .checked_add(count)
            .ok_or("triangle total overflow")?;
        let role = if contract.encoding == PlanEncoding::EncodedGlb {
            match text(row, "role")? {
                "render" => {
                    render_triangles = render_triangles
                        .checked_add(count)
                        .ok_or("render triangle overflow")?;
                    Some(EncodedRole::Render)
                }
                "collision" => {
                    collision_triangles = collision_triangles
                        .checked_add(count)
                        .ok_or("collision triangle overflow")?;
                    Some(EncodedRole::Collision)
                }
                _ => return Err("unsupported encoded payload role".into()),
            }
        } else {
            None
        };
        if contract.encoding != PlanEncoding::EncodedGlb {
            let whole_hulls = integer(&raw, "source_collision_hulls")?;
            if integer(row, "collision_hulls")? != if index == 0 { whole_hulls } else { 0 } {
                return Err("whole collision owner differs".into());
            }
        }
        let payload = text(row, "payload")?;
        let file = files
            .iter()
            .find(|file| file.path == payload)
            .ok_or("missing payload member")?;
        if text(row, "sha256")? != file.digest {
            return Err("payload digest differs from plan".into());
        }
        if projections
            .insert(
                piece.into(),
                MemberProjection {
                    payload: payload.into(),
                    encoding: contract.encoding.clone(),
                    role,
                    metadata: metadata.map(|entries| entries[piece].clone()),
                },
            )
            .is_some()
        {
            return Err("duplicate piece name".into());
        }
    }
    if triangles != integer(&raw, "source_triangles")? {
        return Err("incomplete triangle total".into());
    }
    if contract.encoding == PlanEncoding::EncodedGlb
        && (render_triangles == 0
            || render_triangles != integer(&raw, "source_render_triangles")?
            || collision_triangles != integer(&raw, "source_collision_triangles")?)
    {
        return Err("incomplete encoded role conservation".into());
    }
    let mut files = files.to_vec();
    files.sort_by(|a, b| a.path.cmp(&b.path));
    let stored = StoredOutputGroup {
        id: contract.id.clone(),
        files,
        projections,
    };
    check_recorded(contract, &stored)?;
    Ok(PlanRoster { raw, stored })
}

/// @cc [owner:fontanierh,label:correctness] frozen-group-member-projection
/// A group token MUST follow complete manifest checks and source-specific validation
/// of the same frozen PreparedObjects already hashed by B1. Child projections MUST
/// contain only their named member; no planner key, roster digest or sibling bytes.
/// B2 must retain/match these same prepared objects through publication. See tests/groups.rs.
pub fn validate_frozen(
    contract: &OutputGroupContract,
    objects: &BTreeMap<String, &PreparedObject>,
    validator: impl FnOnce(&PlanRoster, &BTreeMap<String, &PreparedObject>) -> Result<(), String>,
) -> Result<ValidatedGroup, String> {
    contract.validate()?;
    let manifest = objects
        .get(&contract.manifest)
        .ok_or("missing frozen manifest")?;
    if manifest.size() > contract.max_manifest_bytes {
        return Err("manifest byte budget exceeded".into());
    }
    let files: Vec<_> = objects
        .iter()
        .map(|(path, object)| StoredFile {
            path: path.clone(),
            digest: object.digest().to_string(),
            size: object.size(),
            mode: normalized_mode(object.source_mode()),
        })
        .collect();
    let mut bytes = Vec::new();
    manifest
        .reader()
        .map_err(|error| error.to_string())?
        .take(contract.max_manifest_bytes)
        .read_to_end(&mut bytes)
        .map_err(|error| error.to_string())?;
    if bytes.len() as u64 != manifest.size() {
        return Err("frozen manifest size differs".into());
    }
    let roster = parse_manifest(contract, &bytes, &files)?;
    validator(&roster, objects)?;
    Ok(ValidatedGroup {
        contract: contract.clone(),
        stored: roster.stored,
    })
}

/// Only B2's trusted immutable-result reader may restore a token without repeating
/// source validation. Check every named object under the same result/GC lock first.
pub(crate) fn restore_recorded(
    contract: &OutputGroupContract,
    stored: &StoredOutputGroup,
    mut check_object: impl FnMut(&StoredFile) -> Result<(), String>,
) -> Result<ValidatedGroup, String> {
    check_recorded(contract, stored)?;
    for file in &stored.files {
        check_object(file)?;
    }
    Ok(ValidatedGroup {
        contract: contract.clone(),
        stored: stored.clone(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::keys::canonical_bytes;
    use crate::source_hashes::sha256;

    fn fixture() -> (OutputGroupContract, StoredOutputGroup) {
        let contract = OutputGroupContract {
            id: "geometry".into(),
            root: "geometry".into(),
            root_param: "output_root".into(),
            manifest: "plan.json".into(),
            adapter_version: "d2.mesh-plan/1".into(),
            parent: "Village_Edges".into(),
            encoding: PlanEncoding::MeshIr,
            class: "GeometryPayload".into(),
            logical_namespace: "/Internal/Plans/Village_Edges".into(),
            max_pieces: 1024,
            max_manifest_bytes: 4 * 1024 * 1024,
            max_member_bytes: 128 * 1024 * 1024,
            max_total_bytes: 1024 * 1024 * 1024,
        };
        let bytes = include_bytes!("../examples/plans/village_edges.plan.json");
        let files = vec![
            StoredFile {
                path: "plan.json".into(),
                digest: sha256(bytes),
                size: bytes.len() as u64,
                mode: 0o644,
            },
            StoredFile {
                path: "Village_Edges.npz".into(),
                digest: "020a2216fd56fea8992dec94acc335b33704a3c8464c9e8691ab4909272cc539".into(),
                size: 138217,
                mode: 0o644,
            },
        ];
        let roster = parse_manifest(&contract, bytes, &files).unwrap();
        (contract, roster.stored)
    }

    #[test]
    fn recorded_group_projects_only_selected_member_without_output_reads() {
        let (contract, stored) = fixture();
        let mut checked = Vec::new();
        let first = restore_recorded(&contract, &stored, |file| {
            checked.push(file.path.clone());
            Ok(())
        })
        .unwrap();
        assert_eq!(checked, ["Village_Edges.npz", "plan.json"]);
        let selected = first.project("Village_Edges").unwrap();
        let content = serde_json::json!({"domain":"atelier-item-content","version":1,
            "logical_path":selected.item.logical_path,"class":selected.item.class,"files":selected.files});
        assert_eq!(
            sha256(&canonical_bytes(&content).unwrap()),
            "3c4fcd2d192350e7ebdf6a3ce2dcca75284b27671d09949547515b819479232c"
        );
        let mut changed = first.stored.clone();
        changed
            .files
            .iter_mut()
            .find(|file| file.path == "plan.json")
            .unwrap()
            .digest = "a".repeat(64);
        changed.files.push(StoredFile {
            path: "Sibling.npz".into(),
            digest: "b".repeat(64),
            size: 10,
            mode: 0o644,
        });
        changed.projections.insert(
            "Sibling".into(),
            MemberProjection {
                payload: "Sibling.npz".into(),
                encoding: PlanEncoding::MeshIr,
                role: None,
                metadata: None,
            },
        );
        let second = restore_recorded(&contract, &changed, |_| Ok(())).unwrap();
        assert_ne!(first.stored(), second.stored());
        assert_eq!(selected, second.project("Village_Edges").unwrap());
        assert_ne!(selected, second.project("Sibling").unwrap());
        changed
            .files
            .iter_mut()
            .find(|file| file.path == "Village_Edges.npz")
            .unwrap()
            .mode = 0o755;
        assert_ne!(
            selected,
            restore_recorded(&contract, &changed, |_| Ok(()))
                .unwrap()
                .project("Village_Edges")
                .unwrap()
        );
        assert!(restore_recorded(&contract, &changed, |_| Err("blob absent".into())).is_err());
        changed.projections.get_mut("Sibling").unwrap().payload = "missing.npz".into();
        assert!(restore_recorded(&contract, &changed, |_| Ok(())).is_err());
    }
    #[test]
    fn metadata_only_group_preserves_projection_without_certifying_availability() {
        let (contract, mut stored) = fixture();
        let identity = recorded_identity(&contract, &stored).unwrap();
        assert_eq!(identity.pieces().collect::<Vec<_>>(), ["Village_Edges"]);
        assert_eq!(
            identity.projection("Village_Edges").unwrap(),
            &stored.projections["Village_Edges"]
        );
        assert_eq!(identity.project("Village_Edges").unwrap().files.len(), 1);
        assert!(identity.project("unknown").is_err());
        assert!(restore_recorded(&contract, &stored, |_| Err("absent".into())).is_err());
        stored.projections.get_mut("Village_Edges").unwrap().payload = "missing.npz".into();
        assert!(recorded_identity(&contract, &stored).is_err());
    }

    fn key_fixture(
        contract: &OutputGroupContract,
    ) -> (
        crate::schema::Declaration,
        crate::validate::OpRegistry,
        crate::validate::SourceSnapshot,
    ) {
        use crate::schema::*;
        use crate::validate::*;
        let planner = Unit {
            id: "planner".into(),
            op: Op {
                kind: "fixture".into(),
                version: "1".into(),
            },
            script: "ops/plan.py".into(),
            code: vec!["ops/plan.py".into()],
            inputs: vec![],
            params: BTreeMap::from([(
                "output_root".into(),
                Value::String("output/geometry".into()),
            )]),
            outputs: vec![],
            output_groups: vec![contract.clone()],
            conditional: None,
        };
        let child = Unit {
            id: "export.Village_Edges".into(),
            op: planner.op.clone(),
            script: "ops/export.py".into(),
            code: vec!["ops/export.py".into()],
            inputs: vec![Input::Content {
                name: "payload".into(),
                source: ContentSource::GroupMember {
                    unit: "planner".into(),
                    group: "geometry".into(),
                    piece: "Village_Edges".into(),
                },
                whole: None,
                conditional: None,
            }],
            params: BTreeMap::from([
                (
                    "payload_member".into(),
                    Value::String("Village_Edges.npz".into()),
                ),
                ("format".into(), Value::String(".fbx".into())),
            ]),
            outputs: vec![Item {
                id: "mesh".into(),
                logical_path: "/Game/Village/Village_Edges".into(),
                class: "StaticMeshSource".into(),
                files: vec![
                    OutputFile {
                        path: "Village_Edges.fbx".into(),
                        install_path: None,
                        required: true,
                    },
                    OutputFile {
                        path: "export.json".into(),
                        install_path: None,
                        required: true,
                    },
                ],
                destination: Destination::Store,
            }],
            output_groups: vec![],
            conditional: None,
        };
        let registry = BTreeMap::from([(
            ("fixture".into(), "1".into()),
            OpDefinition {
                inputs: BTreeMap::from([(
                    "payload".into(),
                    InputRule {
                        role: InputRole::Content,
                        required: false,
                        allow_absent_file: false,
                        allow_selector: false,
                        require_whole_reason: false,
                        item_classes: BTreeSet::from(["GeometryPayload".into()]),
                    },
                )]),
                output_classes: BTreeSet::from([
                    "GeometryPayload".into(),
                    "StaticMeshSource".into(),
                ]),
                params: ["output_root", "payload_member", "format"]
                    .into_iter()
                    .map(|name| {
                        (
                            name.into(),
                            ParamRule {
                                kind: ParamKind::String,
                                required: false,
                            },
                        )
                    })
                    .collect(),
            },
        )]);
        let snapshot = BTreeMap::from([
            (
                "ops/plan.py".into(),
                SnapshotEntry::File(b"fixture planner v1".to_vec()),
            ),
            (
                "ops/export.py".into(),
                SnapshotEntry::File(b"fixture exporter v1".to_vec()),
            ),
        ]);
        (
            Declaration {
                schema_version: SCHEMA_VERSION,
                cache_version: "fixture-1".into(),
                units: vec![planner, child],
            },
            registry,
            snapshot,
        )
    }

    fn prepared(
        declaration: &crate::schema::Declaration,
        registry: &crate::validate::OpRegistry,
        snapshot: &crate::validate::SourceSnapshot,
        groups: &crate::keys::ProducedGroups,
        unit: &str,
    ) -> Result<crate::keys::PreparedUnit, String> {
        use crate::keys::*;
        let validated = crate::validate::validate(declaration, registry, snapshot, &[])
            .map_err(|e| e.to_string())?;
        let staged = if unit == "planner" {
            BTreeMap::new()
        } else {
            BTreeMap::from([("payload".into(), "inputs/payload".into())])
        };
        let implementation = ImplementationIdentity {
            version: "fixture-worker-1".into(),
            digest: "c".repeat(64),
        };
        prepare(
            declaration,
            &validated,
            unit,
            &KeyContext {
                snapshot,
                versions: &BTreeMap::new(),
                produced: &BTreeMap::new(),
                produced_groups: groups,
                staged_inputs: &staged,
                worker: &implementation,
                validator: &implementation,
            },
            &mut crate::source_hashes::SourceHashCache::default(),
        )
    }

    #[test]
    fn fixed_group_contract_keys_planner_without_runtime_membership() {
        let (contract, stored) = fixture();
        let (mut declaration, registry, snapshot) = key_fixture(&contract);
        let mut groups = BTreeMap::from([(
            ("planner".into(), "geometry".into()),
            restore_recorded(&contract, &stored, |_| Ok(())).unwrap(),
        )]);
        let before = prepared(&declaration, &registry, &snapshot, &groups, "planner").unwrap();
        groups.clear();
        assert_eq!(
            before.key(),
            prepared(&declaration, &registry, &snapshot, &groups, "planner")
                .unwrap()
                .key()
        );
        declaration.units[0].output_groups[0].max_pieces += 1;
        assert_ne!(
            before.key(),
            prepared(&declaration, &registry, &snapshot, &groups, "planner")
                .unwrap()
                .key()
        );
        declaration.units[0].output_groups[0].max_pieces -= 1;
        declaration.units[0].output_groups[0].adapter_version = "d2.mesh-plan/2".into();
        assert_ne!(
            before.key(),
            prepared(&declaration, &registry, &snapshot, &groups, "planner")
                .unwrap()
                .key()
        );
        declaration.schema_version = crate::schema::LEGACY_SCHEMA_VERSION;
        assert!(prepared(&declaration, &registry, &snapshot, &groups, "planner").is_err());
    }

    #[test]
    fn member_keys_cut_off_planner_and_sibling_changes_but_bind_selected_view() {
        let (contract, stored) = fixture();
        let (declaration, registry, mut snapshot) = key_fixture(&contract);
        let mut groups = BTreeMap::from([(
            ("planner".into(), "geometry".into()),
            restore_recorded(&contract, &stored, |_| Ok(())).unwrap(),
        )]);
        let first = prepared(
            &declaration,
            &registry,
            &snapshot,
            &groups,
            "export.Village_Edges",
        )
        .unwrap();
        let planner_before =
            prepared(&declaration, &registry, &snapshot, &groups, "planner").unwrap();
        snapshot.insert(
            "ops/plan.py".into(),
            crate::validate::SnapshotEntry::File(b"fixture planner v1 # comment".to_vec()),
        );
        assert_ne!(
            planner_before.key(),
            prepared(&declaration, &registry, &snapshot, &groups, "planner")
                .unwrap()
                .key()
        );
        assert_eq!(
            first.key(),
            prepared(
                &declaration,
                &registry,
                &snapshot,
                &groups,
                "export.Village_Edges"
            )
            .unwrap()
            .key()
        );
        let mut changed = stored.clone();
        changed
            .files
            .iter_mut()
            .find(|file| file.path == "plan.json")
            .unwrap()
            .digest = "d".repeat(64);
        changed.files.push(StoredFile {
            path: "Sibling.npz".into(),
            digest: "e".repeat(64),
            size: 10,
            mode: 0o644,
        });
        changed.projections.insert(
            "Sibling".into(),
            MemberProjection {
                payload: "Sibling.npz".into(),
                encoding: PlanEncoding::MeshIr,
                role: None,
                metadata: None,
            },
        );
        groups.insert(
            ("planner".into(), "geometry".into()),
            restore_recorded(&contract, &changed, |_| Ok(())).unwrap(),
        );
        assert_eq!(
            first.key(),
            prepared(
                &declaration,
                &registry,
                &snapshot,
                &groups,
                "export.Village_Edges"
            )
            .unwrap()
            .key()
        );
        changed
            .files
            .iter_mut()
            .find(|file| file.path == "Village_Edges.npz")
            .unwrap()
            .digest = "a".repeat(64);
        groups.insert(
            ("planner".into(), "geometry".into()),
            restore_recorded(&contract, &changed, |_| Ok(())).unwrap(),
        );
        let changed_bytes = prepared(
            &declaration,
            &registry,
            &snapshot,
            &groups,
            "export.Village_Edges",
        )
        .unwrap();
        assert_ne!(first.key(), changed_bytes.key());
        changed
            .files
            .iter_mut()
            .find(|file| file.path == "Village_Edges.npz")
            .unwrap()
            .mode = 0o755;
        groups.insert(
            ("planner".into(), "geometry".into()),
            restore_recorded(&contract, &changed, |_| Ok(())).unwrap(),
        );
        assert_ne!(
            changed_bytes.key(),
            prepared(
                &declaration,
                &registry,
                &snapshot,
                &groups,
                "export.Village_Edges"
            )
            .unwrap()
            .key()
        );
        let mut unknown = declaration.clone();
        let crate::schema::Input::Content {
            source: crate::schema::ContentSource::GroupMember { piece, .. },
            ..
        } = &mut unknown.units[1].inputs[0]
        else {
            panic!()
        };
        *piece = "Missing".into();
        assert!(
            prepared(
                &unknown,
                &registry,
                &snapshot,
                &groups,
                "export.Village_Edges"
            )
            .is_err()
        );
        groups.clear();
        assert!(
            prepared(
                &declaration,
                &registry,
                &snapshot,
                &groups,
                "export.Village_Edges"
            )
            .is_err()
        );
    }
    #[test]
    fn mesh_set_policy_keys_only_the_selected_member() {
        let (mut contract, mut stored) = fixture();
        contract.encoding = PlanEncoding::MeshSet;
        for projection in stored.projections.values_mut() {
            projection.encoding = PlanEncoding::MeshSet;
            projection.metadata = Some(serde_json::json!({"collision": true, "lods": false}));
        }
        stored.files.push(StoredFile {
            path: "Sibling.npz".into(),
            digest: "e".repeat(64),
            size: 10,
            mode: 0o644,
        });
        stored.projections.insert(
            "Sibling".into(),
            MemberProjection {
                payload: "Sibling.npz".into(),
                encoding: PlanEncoding::MeshSet,
                role: None,
                metadata: Some(serde_json::json!({"collision": false})),
            },
        );
        let key = |stored: &StoredOutputGroup| {
            let (declaration, registry, snapshot) = key_fixture(&contract);
            let groups = BTreeMap::from([(
                ("planner".into(), "geometry".into()),
                restore_recorded(&contract, stored, |_| Ok(())).unwrap(),
            )]);
            prepared(
                &declaration,
                &registry,
                &snapshot,
                &groups,
                "export.Village_Edges",
            )
            .unwrap()
            .key()
            .to_owned()
        };
        let before = key(&stored);
        stored.projections.get_mut("Sibling").unwrap().metadata =
            Some(serde_json::json!({"collision": true}));
        assert_eq!(before, key(&stored));
        stored
            .projections
            .get_mut("Village_Edges")
            .unwrap()
            .metadata = Some(serde_json::json!({"collision": false, "lods": false}));
        assert_ne!(before, key(&stored));
    }

    #[test]
    fn cached_member_keys_bind_equal_byte_payload_type_and_role_without_plan_reads() {
        let (contract, stored) = fixture();
        let key = |contract: &OutputGroupContract, stored: &StoredOutputGroup| {
            let (declaration, registry, snapshot) = key_fixture(contract);
            let groups = BTreeMap::from([(
                ("planner".into(), "geometry".into()),
                restore_recorded(contract, stored, |_| Ok(())).unwrap(),
            )]);
            prepared(
                &declaration,
                &registry,
                &snapshot,
                &groups,
                "export.Village_Edges",
            )
            .unwrap()
            .key()
            .to_owned()
        };
        let mesh_ir = key(&contract, &stored);
        let mut mesh_set_contract = contract.clone();
        mesh_set_contract.encoding = PlanEncoding::MeshSet;
        let mut mesh_set = stored.clone();
        mesh_set
            .projections
            .get_mut("Village_Edges")
            .unwrap()
            .encoding = PlanEncoding::MeshSet;
        mesh_set
            .projections
            .get_mut("Village_Edges")
            .unwrap()
            .metadata = Some(serde_json::json!({"collision": true}));
        assert_eq!(stored.files, mesh_set.files);
        assert_ne!(mesh_ir, key(&mesh_set_contract, &mesh_set));
        let mut encoded_contract = contract;
        encoded_contract.encoding = PlanEncoding::EncodedGlb;
        let mut encoded = stored;
        encoded
            .files
            .iter_mut()
            .find(|f| f.path == "Village_Edges.npz")
            .unwrap()
            .path = "Village_Edges.mesh".into();
        let projection = encoded.projections.get_mut("Village_Edges").unwrap();
        projection.encoding = PlanEncoding::EncodedGlb;
        projection.payload = "Village_Edges.mesh".into();
        projection.role = Some(EncodedRole::Render);
        let render = key(&encoded_contract, &encoded);
        let mut collision = encoded.clone();
        collision.projections.get_mut("Village_Edges").unwrap().role = Some(EncodedRole::Collision);
        assert_eq!(encoded.files, collision.files);
        assert_ne!(render, key(&encoded_contract, &collision));
        collision.projections.get_mut("Village_Edges").unwrap().role = None;
        assert!(restore_recorded(&encoded_contract, &collision, |_| Ok(())).is_err());
        mesh_set.projections.get_mut("Village_Edges").unwrap().role = Some(EncodedRole::Render);
        assert!(restore_recorded(&mesh_set_contract, &mesh_set, |_| Ok(())).is_err());
    }

    struct Workspace(std::path::PathBuf);
    impl Workspace {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "atelier-v2-group-results-{}-{}",
                std::process::id(),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            ));
            std::fs::create_dir(&path).unwrap();
            Self(path)
        }
    }
    impl Drop for Workspace {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }
    fn begin(
        store: &crate::results::ResultStore,
        unit: &crate::keys::PreparedUnit,
    ) -> crate::results::WriteTransaction {
        store
            .begin(
                unit,
                crate::schema::Provenance {
                    checkout: "fixture".into(),
                    branch: "main".into(),
                    commit: "source".into(),
                    dirty: false,
                    built_at: "fixture".into(),
                },
                crate::leases::ProcessIdentity {
                    pid: std::process::id(),
                    boot: "fixture-boot".into(),
                    started: "fixture-start".into(),
                },
                vec![],
                BTreeSet::new(),
            )
            .unwrap()
    }

    #[test]
    fn complete_output_partition_refuses_unknown_alias_and_ancestor_reports_before_cloning() {
        use crate::results::{ActualOutput, ResultError, ResultStore};
        let (contract, _) = fixture();
        let (declaration, registry, snapshot) = key_fixture(&contract);
        let unit = prepared(
            &declaration,
            &registry,
            &snapshot,
            &BTreeMap::new(),
            "planner",
        )
        .unwrap();
        let workspace = Workspace::new();
        let store = ResultStore::open(workspace.0.join("store")).unwrap();
        for paths in [
            vec!["foreign.bin"],
            vec!["geometry"],
            vec!["../escape"],
            vec!["geometry/plan.json", "geometry/plan.json"],
            vec!["geometry/plan.json", "GEOMETRY/PLAN.JSON"],
            vec!["geometry/payload.npz", "geometry/payload.npz/child"],
        ] {
            let actual = paths
                .into_iter()
                .map(|path| ActualOutput {
                    path: path.into(),
                    source: workspace.0.join("never-opened"),
                })
                .collect();
            assert!(matches!(
                begin(&store, &unit).stage_groups(actual, |_| Ok(()), |_, _, _| Ok(())),
                Err(ResultError::Invalid(_))
            ));
        }
        assert!(
            begin(&store, &unit)
                .stage(BTreeMap::new(), |_| Ok(()))
                .is_err()
        );
        assert!(
            std::fs::read_dir(workspace.0.join("store/objects/sha256"))
                .unwrap()
                .next()
                .is_none()
        );
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn sealed_local_group_stages_selected_bytes_without_cas_and_refuses_missing_frozen_members() {
        for equal_bytes in [false, true] {
            use crate::completion::CompletionWork;
            use crate::install::LeaseIdentity;
            use crate::leases::ProcessIdentity;
            use crate::results::ActualOutput;
            use crate::schema::Provenance;
            use std::{fs, io::Read};
            let (contract, _) = fixture();
            let (declaration, registry, snapshot) = key_fixture(&contract);
            let planner = prepared(
                &declaration,
                &registry,
                &snapshot,
                &BTreeMap::new(),
                "planner",
            )
            .unwrap();
            let workspace = Workspace::new();
            let work = CompletionWork::begin(
                &workspace.0,
                &planner,
                LeaseIdentity {
                    provenance: Provenance {
                        checkout: "fixture".into(),
                        branch: "main".into(),
                        commit: "source".into(),
                        dirty: false,
                        built_at: "fixture".into(),
                    },
                    owner: ProcessIdentity {
                        pid: std::process::id(),
                        boot: "fixture".into(),
                        started: "fixture".into(),
                    },
                    workers: vec![],
                    upstream_result_keys: Default::default(),
                },
            )
            .unwrap();
            let scope = workspace.0.join(&work.lease().staging);
            let payload = b"sealed selected group bytes";
            let sibling_bytes: &[u8] = if equal_bytes {
                payload
            } else {
                b"unneeded sibling payload"
            };
            let plan = serde_json::json!({"schema":1,"parent":"Village_Edges","complete":true,"triangle_limit":32768,"source_triangles":6,"source_collision_hulls":0,"pieces":[{"name":"Village_Edges","payload":"Village_Edges.npz","sha256":sha256(payload),"triangles":3,"collision_hulls":0},{"name":"Sibling","payload":"Sibling.npz","sha256":sha256(sibling_bytes),"triangles":3,"collision_hulls":0}]});
            let source = workspace.0.join("source.npz");
            fs::write(&source, payload).unwrap();
            let sibling = workspace.0.join("sibling.npz");
            fs::write(&sibling, sibling_bytes).unwrap();
            let manifest = workspace.0.join("plan.json");
            fs::write(&manifest, serde_json::to_vec(&plan).unwrap()).unwrap();
            let mut completion = work
                .freeze(
                    vec![
                        ActualOutput {
                            path: "geometry/plan.json".into(),
                            source: manifest,
                        },
                        ActualOutput {
                            path: "geometry/Village_Edges.npz".into(),
                            source: source.clone(),
                        },
                        ActualOutput {
                            path: "geometry/Sibling.npz".into(),
                            source: sibling,
                        },
                    ],
                    |fixed| {
                        assert!(fixed.is_empty());
                        Ok(())
                    },
                    |_, _, objects| {
                        let mut bytes = vec![];
                        objects["Village_Edges.npz"]
                            .reader()
                            .unwrap()
                            .read_to_end(&mut bytes)
                            .unwrap();
                        assert_eq!(bytes, payload);
                        Ok(())
                    },
                )
                .unwrap();
            fs::write(&source, b"changed live output").unwrap();
            let groups = completion.available_groups().unwrap();
            assert_eq!(
                groups["geometry"].stored().projections["Village_Edges"].encoding,
                PlanEncoding::MeshIr
            );
            let produced = groups
                .into_iter()
                .map(|(id, token)| (("planner".into(), id), token))
                .collect();
            let child = prepared(
                &declaration,
                &registry,
                &snapshot,
                &produced,
                "export.Village_Edges",
            )
            .unwrap();
            let objects = completion.objects_for(&[&child.inputs()[0]]).unwrap();
            let staged = crate::staging::stage(
                &child,
                &snapshot,
                &objects,
                &workspace.0.join("child-job"),
                "child",
            )
            .unwrap();
            assert_eq!(
                fs::read(staged.job_dir().join("inputs/payload/Village_Edges.npz")).unwrap(),
                payload
            );
            assert!(!workspace.0.join("objects").exists());
            assert!(!workspace.0.join("results").exists());
            let evidence: Value =
                serde_json::from_slice(&fs::read(scope.join("completion.json")).unwrap()).unwrap();
            let sibling_named = evidence["objects"]
                .as_array()
                .unwrap()
                .iter()
                .find(|object| object["digest"] == sha256(sibling_bytes))
                .unwrap()["path"]
                .as_str()
                .unwrap();
            fs::remove_file(scope.join(sibling_named)).unwrap();
            assert_eq!(completion.available_groups().is_ok(), equal_bytes);
            let selected_only = completion.objects_for(&[&child.inputs()[0]]).unwrap();
            let after_loss = crate::staging::stage(
                &child,
                &snapshot,
                &selected_only,
                &workspace.0.join("after-sibling-loss"),
                "selected",
            )
            .unwrap();
            assert_eq!(
                fs::read(
                    after_loss
                        .job_dir()
                        .join("inputs/payload/Village_Edges.npz")
                )
                .unwrap(),
                payload
            );
            crate::staging::remove_job(after_loss.job_dir()).unwrap();
            drop(selected_only);
            drop(objects);
            if equal_bytes {
                let store = crate::results::ResultStore::open(workspace.0.join("cache")).unwrap();
                assert!(completion.publish(&store, |_| Ok(())).is_ok());
            }
            let named = evidence["objects"]
                .as_array()
                .unwrap()
                .iter()
                .find(|object| {
                    object["digest"] == sha256(payload)
                        && scope.join(object["path"].as_str().unwrap()).is_file()
                })
                .unwrap()["path"]
                .as_str()
                .unwrap();
            fs::remove_file(scope.join(named)).unwrap();
            assert!(completion.available_groups().is_err());
            assert!(completion.objects_for(&[&child.inputs()[0]]).is_err());
            assert_eq!(
                fs::read(staged.job_dir().join("inputs/payload/Village_Edges.npz")).unwrap(),
                payload
            );
            crate::staging::remove_job(staged.job_dir()).unwrap();
        }
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn leased_group_publication_restores_tokens_and_compares_whole_manifest() {
        use crate::results::{ActualOutput, ResultError, ResultStore};
        use std::{fs, io::Read};
        let (contract, _) = fixture();
        let (declaration, registry, snapshot) = key_fixture(&contract);
        let unit = prepared(
            &declaration,
            &registry,
            &snapshot,
            &BTreeMap::new(),
            "planner",
        )
        .unwrap();
        let workspace = Workspace::new();
        let store = ResultStore::open(workspace.0.join("store")).unwrap();
        let output = workspace.0.join("output");
        fs::create_dir(&output).unwrap();
        let payload = b"opaque group fixture payload";
        let plan = serde_json::json!({"schema":1,"parent":"Village_Edges","complete":true,"triangle_limit":32768,
            "source_triangles":3,"source_collision_hulls":0,"pieces":[{"name":"Village_Edges","payload":"Village_Edges.npz",
            "sha256":sha256(payload),"triangles":3,"collision_hulls":0}]});
        let write_actual = |plan: &Value, sibling: bool| {
            if !sibling && output.join("Sibling.npz").exists() {
                fs::remove_file(output.join("Sibling.npz")).unwrap();
            }
            fs::write(output.join("plan.json"), serde_json::to_vec(plan).unwrap()).unwrap();
            fs::write(output.join("Village_Edges.npz"), payload).unwrap();
            let mut actual = vec![
                ActualOutput {
                    path: "geometry/plan.json".into(),
                    source: output.join("plan.json"),
                },
                ActualOutput {
                    path: "geometry/Village_Edges.npz".into(),
                    source: output.join("Village_Edges.npz"),
                },
            ];
            if sibling {
                fs::write(output.join("Sibling.npz"), b"sibling").unwrap();
                actual.push(ActualOutput {
                    path: "geometry/Sibling.npz".into(),
                    source: output.join("Sibling.npz"),
                });
            }
            actual
        };
        let staged = begin(&store, &unit)
            .stage_groups(
                write_actual(&plan, false),
                |fixed| {
                    assert!(fixed.is_empty());
                    Ok(())
                },
                |contract, roster, members| {
                    assert_eq!(contract.id, "geometry");
                    assert_eq!(roster.stored().files.len(), 2);
                    fs::write(output.join("Village_Edges.npz"), b"changed live output").unwrap();
                    let mut bytes = Vec::new();
                    members["Village_Edges.npz"]
                        .reader()
                        .unwrap()
                        .read_to_end(&mut bytes)
                        .unwrap();
                    assert_eq!(bytes, payload);
                    Ok(())
                },
            )
            .unwrap();
        let first = staged.publish(|_| Ok(())).unwrap();
        assert_eq!(first.result.output_groups[0].files.len(), 2);
        fs::remove_dir_all(&output).unwrap(); // Cache restoration cannot depend on the mutable output tree.
        let mut hit = begin(&store, &unit);
        let (envelope, mut tokens) = hit.lookup_groups().unwrap().unwrap();
        assert_eq!(envelope, first);
        for file in envelope.files() {
            assert!(hit.lease().object_digests.contains(&file.digest));
        }
        let token = tokens.remove("geometry").unwrap();
        assert_eq!(
            token.project("Village_Edges").unwrap().files[0].digest,
            sha256(payload)
        );
        let produced = BTreeMap::from([(("planner".into(), "geometry".into()), token)]);
        prepared(
            &declaration,
            &registry,
            &snapshot,
            &produced,
            "export.Village_Edges",
        )
        .unwrap();
        hit.retain_hit(|_| Ok(())).unwrap();
        fs::create_dir(&output).unwrap();
        let mut changed = plan.clone();
        changed["source_triangles"] = 6.into();
        changed["pieces"].as_array_mut().unwrap().push(serde_json::json!({"name":"Sibling","payload":"Sibling.npz","sha256":sha256(b"sibling"),"triangles":3,"collision_hulls":0}));
        let conflict = begin(&store, &unit)
            .stage_groups(write_actual(&changed, true), |_| Ok(()), |_, _, _| Ok(()))
            .unwrap();
        assert!(matches!(
            conflict.publish(|_| panic!("no root for nondeterministic full group")),
            Err(ResultError::Nondeterminism(_))
        ));
        assert_eq!(begin(&store, &unit).lookup().unwrap().unwrap(), first);
        let mut extra = write_actual(&plan, false);
        fs::write(output.join("Foreign.bin"), b"unexpected").unwrap();
        extra.push(ActualOutput {
            path: "geometry/Foreign.bin".into(),
            source: output.join("Foreign.bin"),
        });
        assert!(matches!(
            begin(&store, &unit).stage_groups(
                extra,
                |_| Ok(()),
                |_, _, _| panic!("metadata refusal precedes source validation")
            ),
            Err(ResultError::Validation(_))
        ));
        fs::remove_file(output.join("Foreign.bin")).unwrap();
        let failed = begin(&store, &unit);
        let failed = failed.stage_groups(
            write_actual(&plan, false),
            |_| Ok(()),
            |_, _, _| Err("source validator refused".into()),
        );
        assert!(matches!(failed, Err(ResultError::Validation(_))));
        let manifest = first.result.output_groups[0]
            .files
            .iter()
            .find(|file| file.path == "plan.json")
            .unwrap();
        fs::remove_file(
            workspace
                .0
                .join("store/objects/sha256")
                .join(&manifest.digest),
        )
        .unwrap();
        assert!(begin(&store, &unit).lookup_groups().is_err());
    }
}
