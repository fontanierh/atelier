//! Pure unit identity and explicit worker-input staging plans. No scheduling/store I/O.
use crate::groups::ValidatedGroup;
use crate::paths::{Claims, claim, relative_path};
use crate::protocol::{JobRequest, StagedInput};
use crate::schema::*;
use crate::source_hashes::{FileVersion, SourceHashCache, sha256, valid_digest};
use crate::validate::{FileSelection, SnapshotEntry, SourceSnapshot, ValidatedDeclaration};
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};

/// @cc [owner:fontanierh,label:correctness] fixed-plan-input-identity
/// Key encoding v2 MUST bind fixed group contracts before execution and MUST NOT
/// include runtime group membership, plan/roster digests or producer input keys in
/// a selected member consumer key. See groups::tests::fixed_group_contract_keys_planner_without_runtime_membership
/// and member_keys_cut_off_planner_and_sibling_changes_but_bind_selected_view;
/// actual scheduler/worker cutoff remains pending A9/D2 integration.
pub const KEY_ENCODING_VERSION: u32 = 2;
pub const CANONICAL_JSON_VERSION: u32 = 1;
pub type ProducedItems = BTreeMap<(String, String), StoredItem>;
pub type ProducedGroups = BTreeMap<(String, String), ValidatedGroup>;
pub type SourceVersions = BTreeMap<String, FileVersion>;

#[derive(Clone, Debug)]
pub struct ImplementationIdentity {
    pub version: String,
    /// Declared implementation-code digest, never an installed tool fingerprint.
    pub digest: String,
}

pub struct KeyContext<'a> {
    pub snapshot: &'a SourceSnapshot,
    pub versions: &'a SourceVersions,
    pub produced: &'a ProducedItems,
    pub produced_groups: &'a ProducedGroups,
    /// Exact worker-visible file names, or directory roots for multi-file items.
    pub staged_inputs: &'a BTreeMap<String, String>,
    pub worker: &'a ImplementationIdentity,
    pub validator: &'a ImplementationIdentity,
}

#[derive(Clone, Debug, PartialEq)]
pub enum InputPayload {
    Absent,
    /// Raw file bytes, selected JSON bytes, or a reference descriptor; no locator.
    Bytes(Vec<u8>),
    /// C1 resolves these byte-addressed blobs and preserves this exact membership.
    Item {
        logical_path: String,
        class: String,
        files: Vec<StoredFile>,
    },
}

#[derive(Clone, Debug, PartialEq)]
pub struct PreparedInput {
    pub wire: StagedInput,
    pub payload: InputPayload,
}

#[derive(Clone, Debug)]
pub struct PreparedUnit {
    key: String,
    ingredients: IdentityIngredients,
    inputs: Vec<PreparedInput>,
    template: JobRequest,
}

impl PreparedUnit {
    /// Derive only the fixed independent native verifier, preserving exact consumed CB identity.
    /// The report has its own key/lease and never impersonates the external package completion.
    pub(crate) fn native_verifier(&self) -> Result<Self, String> {
        crate::native_verify::check_package(self)?;
        let mut value = self.clone();
        value.ingredients.op.kind = crate::results::zen_cook::VERIFY_OP.into();
        value.ingredients.logical_outputs = vec![Item {
            id: "verification".into(),
            logical_path: format!(
                "/Internal/NativeCookVerification{}",
                self.ingredients.logical_outputs[0].logical_path
            ),
            class: "JsonData".into(),
            destination: Destination::Store,
            files: vec![OutputFile {
                path: crate::results::zen_cook::VERIFY_REPORT.into(),
                install_path: None,
                required: true,
            }],
        }];
        value.key = sha256(&canonical_bytes(&serde_json::json!({
            "domain":"atelier-unit-key", "version":KEY_ENCODING_VERSION,
            "ingredients":value.ingredients,
        }))?);
        value.template.unit = format!("{}.native-verifier", self.template.unit);
        value.template.op = value.ingredients.op.clone();
        value.template.outputs = value
            .ingredients
            .logical_outputs
            .iter()
            .flat_map(|item| item.files.clone())
            .collect();
        crate::unreal_controller::check_unit(&value)?;
        Ok(value)
    }
    pub fn key(&self) -> &str {
        &self.key
    }
    pub fn ingredients(&self) -> &IdentityIngredients {
        &self.ingredients
    }
    pub fn inputs(&self) -> &[PreparedInput] {
        &self.inputs
    }
    /// Control metadata is not semantic op input. C1 must enforce that separation.
    pub fn request(&self, job_id: &str, job_dir: &str) -> JobRequest {
        let mut request = self.template.clone();
        request.job_id = job_id.into();
        request.job_dir = job_dir.into();
        request
    }
}

/// Recursive object ordering is explicit even if serde_json's map feature changes.
pub fn canonical_bytes<T: Serialize>(value: &T) -> Result<Vec<u8>, String> {
    fn ordered(value: serde_json::Value) -> serde_json::Value {
        match value {
            serde_json::Value::Object(object) => {
                let sorted: BTreeMap<_, _> = object.into_iter().collect();
                serde_json::Value::Object(
                    sorted
                        .into_iter()
                        .map(|(key, value)| (key, ordered(value)))
                        .collect(),
                )
            }
            serde_json::Value::Array(array) => {
                serde_json::Value::Array(array.into_iter().map(ordered).collect())
            }
            value => value,
        }
    }
    serde_json::to_vec(&ordered(
        serde_json::to_value(value).map_err(|error| error.to_string())?,
    ))
    .map_err(|error| error.to_string())
}

fn normalized_item(item: &Item) -> Item {
    let mut item = item.clone();
    item.files.sort_by(|a, b| a.path.cmp(&b.path));
    item
}

pub(crate) fn safe_staged_paths(
    paths: &BTreeMap<String, String>,
    code: &[String],
) -> Result<(), String> {
    let mut claims = Claims::new();
    claim(&mut claims, "output", "writable output root")?;
    for path in code.iter().collect::<BTreeSet<_>>() {
        relative_path(path, false)?;
        claim(&mut claims, path, "project code")?;
    }
    for (slot, path) in paths {
        relative_path(path, true)?;
        claim(&mut claims, path, &format!("staged input {slot}"))?;
    }
    Ok(())
}

fn source<'a>(snapshot: &'a SourceSnapshot, path: &str) -> Result<Option<&'a [u8]>, String> {
    match snapshot.get(path) {
        Some(SnapshotEntry::File(bytes)) => Ok(Some(bytes)),
        None => Ok(None),
        Some(_) => Err(format!("source is not a frozen regular file: {path}")),
    }
}

/// Normalized result modes are semantic metadata, separate from byte-only blobs.
pub fn normalized_mode(source_mode: u32) -> u32 {
    if source_mode & 0o111 != 0 {
        0o755
    } else {
        0o644
    }
}

fn item_payload(expected: &Item, stored: &StoredItem) -> Result<InputPayload, String> {
    if expected.destination == Destination::External
        || normalized_item(expected) != normalized_item(&stored.item)
        || stored.external_locator.is_some()
    {
        return Err("producer item differs from declaration or needs an external adapter".into());
    }
    let allowed: BTreeMap<_, _> = expected
        .files
        .iter()
        .map(|file| (file.path.clone(), file.required))
        .collect();
    let mut actual = BTreeSet::new();
    let mut files = stored.files.clone();
    for file in &files {
        if !valid_digest(&file.digest)
            || !matches!(file.mode, 0o644 | 0o755)
            || !allowed.contains_key(&file.path)
            || !actual.insert(file.path.clone())
        {
            return Err("invalid or duplicate producer file identity/mode".into());
        }
    }
    if expected
        .files
        .iter()
        .any(|file| file.required && !actual.contains(&file.path))
    {
        return Err("producer item lacks a required file".into());
    }
    files.sort_by(|a, b| a.path.cmp(&b.path));
    Ok(InputPayload::Item {
        logical_path: expected.logical_path.clone(),
        class: expected.class.clone(),
        files,
    })
}

#[derive(Serialize)]
struct ContentItem<'a> {
    domain: &'static str,
    version: u32,
    logical_path: &'a str,
    class: &'a str,
    files: &'a [StoredFile],
}

fn item_identity(payload: &InputPayload) -> Result<ContentIdentity, String> {
    let InputPayload::Item {
        logical_path,
        class,
        files,
    } = payload
    else {
        return Err("expected typed item payload".into());
    };
    Ok(ContentIdentity::Digest {
        digest: sha256(&canonical_bytes(&ContentItem {
            domain: "atelier-item-content",
            version: 1,
            logical_path,
            class,
            files,
        })?),
    })
}

/// @cc [owner:fontanierh,label:correctness] key-exact-visible-ingredients
/// Unit keys MUST bind explicit versions, declared code/params/logical outputs,
/// exact content views, file/item shapes and disjoint worker-visible staging paths.
/// Producer input keys and
/// provenance MUST NOT substitute for output content. Reference bytes and ambient
/// platform versions MUST NOT enter keys. See tests/keys.rs; worker isolation and
/// output-cutoff execution proof remain C1/A4/A6/A9 responsibilities.
pub fn prepare(
    declaration: &Declaration,
    validated: &ValidatedDeclaration,
    unit_id: &str,
    context: &KeyContext<'_>,
    hashes: &mut SourceHashCache,
) -> Result<PreparedUnit, String> {
    if !validated.order.iter().any(|id| id == unit_id) {
        return Err("unit was not validated".into());
    }
    let unit = declaration
        .units
        .iter()
        .find(|unit| unit.id == unit_id)
        .ok_or("unknown unit")?;
    if !unit.code.contains(&unit.script) {
        return Err("entry script is outside declared code closure".into());
    }
    for identity in [context.worker, context.validator] {
        if identity.version.trim().is_empty() || !valid_digest(&identity.digest) {
            return Err("implementation identity needs a version and SHA-256 code digest".into());
        }
    }
    let names: BTreeSet<_> = unit
        .inputs
        .iter()
        .map(|input| match input {
            Input::Content { name, .. } | Input::Reference { name, .. } => name.clone(),
        })
        .collect();
    if names != context.staged_inputs.keys().cloned().collect() {
        return Err("staged input map must cover exactly the declared slots".into());
    }
    safe_staged_paths(context.staged_inputs, &unit.code)?;
    let mut code = BTreeMap::new();
    for path in &unit.code {
        let bytes =
            source(context.snapshot, path)?.ok_or_else(|| format!("missing code: {path}"))?;
        code.insert(
            path.clone(),
            hashes.digest(context.versions.get(path), bytes)?,
        );
    }
    let mut content = BTreeMap::new();
    let mut references = BTreeMap::new();
    let mut inputs = Vec::new();
    for input in &unit.inputs {
        let (name, identity, payload) = match input {
            Input::Content {
                name,
                source:
                    ContentSource::File {
                        path,
                        selector,
                        optional,
                    },
                ..
            } => {
                let observation = validated
                    .files
                    .iter()
                    .find(|file| file.unit == unit_id && file.input == *name)
                    .ok_or("file selection was not validated")?;
                if observation.path != *path {
                    return Err("validated source locator changed".into());
                }
                let bytes = source(context.snapshot, path)?;
                let (identity, payload) = match (&observation.selection, selector, bytes) {
                    (FileSelection::Absent, _, None) if *optional => {
                        (ContentIdentity::Absent {}, InputPayload::Absent)
                    }
                    (FileSelection::Whole, None, Some(bytes)) => (
                        ContentIdentity::Digest {
                            digest: hashes.digest(context.versions.get(path), bytes)?,
                        },
                        InputPayload::Bytes(bytes.to_vec()),
                    ),
                    (FileSelection::Json(selected), Some(pointer), Some(bytes)) => {
                        let actual: serde_json::Value = serde_json::from_slice(bytes)
                            .map_err(|_| "selector source stopped being JSON")?;
                        if actual.pointer(pointer) != Some(selected) {
                            return Err("selected source changed after validation".into());
                        }
                        let selected = canonical_bytes(selected)?;
                        let digest = hashes.digest_selected(
                            context.versions.get(path),
                            bytes.len() as u64,
                            pointer,
                            CANONICAL_JSON_VERSION,
                            &selected,
                        )?;
                        (
                            ContentIdentity::Digest { digest },
                            InputPayload::Bytes(selected),
                        )
                    }
                    _ => return Err("source presence/view changed after validation".into()),
                };
                content.insert(name.clone(), identity.clone());
                (name, identity, payload)
            }
            Input::Content {
                name,
                source:
                    ContentSource::Item {
                        unit: producer,
                        item,
                    },
                ..
            } => {
                let expected = declaration
                    .units
                    .iter()
                    .find(|unit| unit.id == *producer)
                    .and_then(|unit| unit.outputs.iter().find(|output| output.id == *item))
                    .ok_or("unknown producer item")?;
                let stored = context
                    .produced
                    .get(&(producer.clone(), item.clone()))
                    .ok_or("producer has no validated saved content")?;
                let payload = item_payload(expected, stored)?;
                let identity = item_identity(&payload)?;
                content.insert(name.clone(), identity.clone());
                (name, identity, payload)
            }
            Input::Content {
                name,
                source:
                    ContentSource::GroupMember {
                        unit: producer,
                        group,
                        piece,
                    },
                ..
            } => {
                let expected = declaration
                    .units
                    .iter()
                    .find(|unit| unit.id == *producer)
                    .and_then(|unit| {
                        unit.output_groups
                            .iter()
                            .find(|contract| contract.id == *group)
                    })
                    .ok_or("unknown producer group")?;
                let validated_group = context
                    .produced_groups
                    .get(&(producer.clone(), group.clone()))
                    .ok_or("validated producer group is unavailable")?;
                if validated_group.contract() != expected {
                    return Err("group contract differs from validated result".into());
                }
                let selected = validated_group.project(piece)?;
                let payload = item_payload(&selected.item, &selected)?;
                // Only the selected certified type/role joins its Item content view.
                // The runtime roster, planner contract and planner input key stay out.
                let identity = ContentIdentity::Digest {
                    digest: sha256(&canonical_bytes(&serde_json::json!({
                        "domain": "atelier-group-member-content", "version": 1,
                        "item": item_identity(&payload)?,
                        "projection": validated_group.stored().projections[piece],
                    }))?),
                };
                content.insert(name.clone(), identity.clone());
                (name, identity, payload)
            }
            Input::Reference {
                name,
                logical_path,
                class,
                ..
            } => {
                let reference = ReferenceIdentity {
                    logical_path: logical_path.clone(),
                    class: class.clone(),
                };
                let bytes = canonical_bytes(&reference)?;
                let identity = ContentIdentity::Digest {
                    digest: sha256(&bytes),
                };
                references.insert(name.clone(), reference);
                (name, identity, InputPayload::Bytes(bytes))
            }
        };
        inputs.push(PreparedInput {
            wire: StagedInput {
                name: name.clone(),
                path: context.staged_inputs[name].clone(),
                identity,
            },
            payload,
        });
    }
    inputs.sort_by(|a, b| a.wire.name.cmp(&b.wire.name));
    let mut outputs: Vec<_> = unit.outputs.iter().map(normalized_item).collect();
    outputs.sort_by(|a, b| a.id.cmp(&b.id));
    let mut output_groups = unit.output_groups.clone();
    output_groups.sort_by(|a, b| a.id.cmp(&b.id));
    for contract in &output_groups {
        contract.validate()?;
        contract.validate_root_param(&unit.params)?;
    }
    let ingredients = IdentityIngredients {
        cache_version: declaration.cache_version.clone(),
        op: unit.op.clone(),
        script: unit.script.clone(),
        code,
        worker_version: context.worker.version.clone(),
        worker_digest: context.worker.digest.clone(),
        validator_version: context.validator.version.clone(),
        validator_digest: context.validator.digest.clone(),
        params: unit.params.clone(),
        content,
        references,
        staged_inputs: context.staged_inputs.clone(),
        input_kinds: inputs
            .iter()
            .map(|input| {
                (
                    input.wire.name.clone(),
                    match &input.payload {
                        InputPayload::Item { .. } => InputKind::Item,
                        InputPayload::Absent | InputPayload::Bytes(_) => InputKind::File,
                    },
                )
            })
            .collect(),
        logical_outputs: outputs.clone(),
        output_groups,
    };
    #[derive(Serialize)]
    struct Encoding<'a> {
        domain: &'static str,
        version: u32,
        ingredients: &'a IdentityIngredients,
    }
    let key = sha256(&canonical_bytes(&Encoding {
        domain: "atelier-unit-key",
        version: KEY_ENCODING_VERSION,
        ingredients: &ingredients,
    })?);
    let template = JobRequest {
        job_id: String::new(),
        unit: unit.id.clone(),
        op: unit.op.clone(),
        job_dir: String::new(),
        script: unit.script.clone(),
        code: unit
            .code
            .iter()
            .cloned()
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect(),
        inputs: inputs.iter().map(|input| input.wire.clone()).collect(),
        params: unit.params.clone(),
        outputs: outputs.into_iter().flat_map(|item| item.files).collect(),
    };
    Ok(PreparedUnit {
        key,
        ingredients,
        inputs,
        template,
    })
}
