//! Read-only declaration validation against a caller-owned immutable snapshot.
//! This module never opens live files, hashes bytes, executes code or computes keys.
use crate::schema::*;
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use unicode_casefold::UnicodeCaseFold;
use unicode_normalization::UnicodeNormalization;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum InputRole {
    Content,
    Reference,
}

#[derive(Clone, Debug)]
pub struct InputRule {
    pub role: InputRole,
    pub required: bool,
    pub allow_absent_file: bool,
    pub allow_selector: bool,
    /// Broad/aggregate slots require a whole-input rationale. Bounded items do not.
    pub require_whole_reason: bool,
    /// Accepted classes for producer items and logical references.
    pub item_classes: BTreeSet<String>,
}

/// Op definitions are supplied by their implementation, never inferred from TOML.
#[derive(Clone, Debug)]
pub struct OpDefinition {
    pub inputs: BTreeMap<String, InputRule>,
    pub output_classes: BTreeSet<String>,
    pub params: BTreeMap<String, ParamRule>,
}

#[derive(Clone, Debug)]
pub struct ParamRule {
    pub kind: ParamKind,
    pub required: bool,
}

/// Nested domain constraints remain with the op's validator.
#[derive(Clone, Debug)]
pub enum ParamKind {
    Bool,
    Integer,
    Number,
    String,
    Array,
    Object,
}

impl ParamKind {
    fn accepts(&self, value: &serde_json::Value) -> bool {
        match self {
            Self::Bool => value.is_boolean(),
            Self::Integer => value.is_i64() || value.is_u64(),
            Self::Number => value.is_number(),
            Self::String => value.is_string(),
            Self::Array => value.is_array(),
            Self::Object => value.is_object(),
        }
    }
}

pub type OpRegistry = BTreeMap<(String, String), OpDefinition>;

/// The snapshot provider must distinguish unavailable or non-regular paths from absence.
#[derive(Clone, Debug)]
pub enum SnapshotEntry {
    File(Vec<u8>),
    Directory,
    Symlink,
    Unreadable,
}

/// Exact project-relative names and frozen bytes, including ignored/untracked inputs.
/// Absence is a missing map entry. Construction and physical path validation belong
/// to the snapshot provider; this type is not a live-filesystem safety adapter.
pub type SourceSnapshot = BTreeMap<String, SnapshotEntry>;

#[derive(Clone, Debug, PartialEq)]
pub enum FileSelection {
    Absent,
    Whole,
    Json(serde_json::Value),
}

#[derive(Clone, Debug, PartialEq)]
pub struct ResolvedFile {
    pub unit: String,
    pub input: String,
    pub path: String,
    pub selection: FileSelection,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ValidatedDeclaration {
    /// Deterministic dependency-first order, including producer scheduling links.
    pub order: Vec<String>,
    pub files: Vec<ResolvedFile>,
}

/// Parse wire shape and validate semantics as one operation. No live files are read.
pub fn load(
    source: &str,
    registry: &OpRegistry,
    snapshot: &SourceSnapshot,
    allowed_install_roots: &[String],
) -> Result<(Declaration, ValidatedDeclaration), ValidationError> {
    let declaration =
        parse_declaration(source).map_err(|error| fail(format!("invalid TOML: {error}")))?;
    let validated = validate(&declaration, registry, snapshot, allowed_install_roots)?;
    Ok((declaration, validated))
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ValidationError(pub String);

impl fmt::Display for ValidationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        self.0.fmt(formatter)
    }
}

impl std::error::Error for ValidationError {}

fn fail(message: impl Into<String>) -> ValidationError {
    ValidationError(message.into())
}

fn nonempty(value: &str, label: &str) -> Result<(), ValidationError> {
    if value.trim().is_empty() {
        return Err(fail(format!("empty {label}")));
    }
    Ok(())
}

fn identifier(value: &str, label: &str) -> Result<(), ValidationError> {
    if value.is_empty()
        || !value
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"._-".contains(&c))
        || value == "."
        || value == ".."
    {
        return Err(fail(format!("invalid {label}: {value:?}")));
    }
    Ok(())
}

fn relative_path(value: &str, owned: bool) -> Result<(), ValidationError> {
    if value.is_empty()
        || value
            .chars()
            .any(|c| c.is_control() || c == '\\' || c == ':')
        || value.split('/').any(|part| {
            part.is_empty() || part == "." || part == ".." || part.ends_with(['.', ' '])
        })
    {
        return Err(fail(format!(
            "invalid {} path: {value:?}",
            if owned { "owned" } else { "source" }
        )));
    }
    Ok(())
}

fn logical_path(value: &str) -> Result<(), ValidationError> {
    let path = value
        .strip_prefix('/')
        .ok_or_else(|| fail("logical path must start with /"))?;
    relative_path(path, true)
}

fn folded(path: &str) -> String {
    // Canonical decomposition + full non-Turkic folding conservatively rejects
    // ambiguous aliases. This is not an emulator of every APFS Unicode revision.
    path.nfd().case_fold().nfd().collect()
}

type Claims = BTreeMap<String, (String, String)>;

fn conflict<'a>(claims: &'a Claims, path: &str) -> Option<&'a (String, String)> {
    let key = folded(path);
    if let Some(owner) = claims.get(&key) {
        return Some(owner);
    }
    for (index, _) in key.match_indices('/') {
        if let Some(owner) = claims.get(&key[..index]) {
            return Some(owner);
        }
    }
    let prefix = key + "/";
    if let Some((next, owner)) = claims.range(prefix.clone()..).next() {
        if next.starts_with(&prefix) {
            return Some(owner);
        }
    }
    None
}

fn claim(claims: &mut Claims, path: &str, owner: &str) -> Result<(), ValidationError> {
    if let Some((old, previous)) = conflict(claims, path) {
        return Err(fail(format!(
            "overlapping output owners {previous} ({old}) and {owner} ({path})"
        )));
    }
    claims.insert(folded(path), (path.into(), owner.into()));
    Ok(())
}

fn file<'a>(
    snapshot: &'a SourceSnapshot,
    path: &str,
    optional: bool,
) -> Result<Option<&'a [u8]>, ValidationError> {
    match snapshot.get(path) {
        Some(SnapshotEntry::File(bytes)) => Ok(Some(bytes)),
        None if optional => Ok(None),
        None => Err(fail(format!("missing required source: {path}"))),
        Some(_) => Err(fail(format!(
            "source is not a readable regular file: {path}"
        ))),
    }
}

fn pointer(value: &str) -> Result<(), ValidationError> {
    if !value.is_empty() && !value.starts_with('/') {
        return Err(fail("selector must be an RFC 6901 JSON pointer"));
    }
    let mut chars = value.chars();
    while let Some(character) = chars.next() {
        if character == '~' && !matches!(chars.next(), Some('0' | '1')) {
            return Err(fail("invalid JSON pointer escape"));
        }
    }
    Ok(())
}

fn note(value: &Option<String>, label: &str) -> Result<(), ValidationError> {
    if let Some(value) = value {
        nonempty(value, label)?;
    }
    Ok(())
}

fn dependency_order(
    dependencies: &BTreeMap<String, BTreeSet<String>>,
) -> Result<Vec<String>, ValidationError> {
    let mut remaining: BTreeMap<String, usize> = dependencies
        .iter()
        .map(|(id, parents)| (id.clone(), parents.len()))
        .collect();
    let mut consumers: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for (id, parents) in dependencies {
        for parent in parents {
            consumers
                .entry(parent.clone())
                .or_default()
                .push(id.clone());
        }
    }
    let mut ready: BTreeSet<String> = remaining
        .iter()
        .filter(|(_, count)| **count == 0)
        .map(|(id, _)| id.clone())
        .collect();
    let mut order = Vec::new();
    while let Some(id) = ready.pop_first() {
        for consumer in consumers.get(&id).into_iter().flatten() {
            let count = remaining.get_mut(consumer).unwrap();
            *count -= 1;
            if *count == 0 {
                ready.insert(consumer.clone());
            }
        }
        order.push(id);
    }
    if order.len() != dependencies.len() {
        return Err(fail("dependency cycle"));
    }
    Ok(order)
}

/// @cc [owner:fontanierh,label:correctness] validate-frozen-declarations
/// Validation MUST reject unsupported ops, missing required files/items, missing
/// selector nodes, mismatched input roles, cyclic dependencies and overlapping
/// final output owners before returning an execution order. Missing optional files
/// MUST remain distinct from empty files and missing selector nodes. See tests/validation.rs.
pub fn validate(
    declaration: &Declaration,
    registry: &OpRegistry,
    snapshot: &SourceSnapshot,
    allowed_install_roots: &[String],
) -> Result<ValidatedDeclaration, ValidationError> {
    if declaration.schema_version != SCHEMA_VERSION {
        return Err(fail("unsupported declaration schema version"));
    }
    nonempty(&declaration.cache_version, "cache version")?;
    if declaration.units.is_empty() {
        return Err(fail("declaration has no units"));
    }
    for root in allowed_install_roots {
        relative_path(root, true)?;
    }
    let mut units = BTreeMap::new();
    let mut items = BTreeMap::new();
    let mut installs = Claims::new();
    let mut logical = Claims::new();
    for unit in &declaration.units {
        identifier(&unit.id, "unit id")?;
        if units.insert(unit.id.clone(), unit).is_some() {
            return Err(fail(format!("duplicate unit id: {}", unit.id)));
        }
        let op = registry
            .get(&(unit.op.kind.clone(), unit.op.version.clone()))
            .ok_or_else(|| {
                fail(format!(
                    "unsupported op/version: {}/{}",
                    unit.op.kind, unit.op.version
                ))
            })?;
        for (name, value) in &unit.params {
            let rule = op
                .params
                .get(name)
                .ok_or_else(|| fail(format!("unknown op parameter: {name}")))?;
            if !rule.kind.accepts(value) {
                return Err(fail(format!("wrong type for op parameter: {name}")));
            }
        }
        for (name, rule) in &op.params {
            if rule.required && !unit.params.contains_key(name) {
                return Err(fail(format!("missing required op parameter: {name}")));
            }
        }
        note(&unit.conditional, "unit conditional note")?;
        relative_path(&unit.script, false)?;
        let mut code = BTreeSet::new();
        for path in &unit.code {
            relative_path(path, false)?;
            if !code.insert(path.clone()) {
                return Err(fail(format!("duplicate code file: {path}")));
            }
            file(snapshot, path, false)?;
        }
        if !code.contains(&unit.script) {
            return Err(fail(format!(
                "entry script absent from code closure: {}",
                unit.script
            )));
        }
        if unit.outputs.is_empty() {
            return Err(fail(format!("unit has no outputs: {}", unit.id)));
        }
        let mut job_outputs = Claims::new();
        for item in &unit.outputs {
            identifier(&item.id, "item id")?;
            logical_path(&item.logical_path)?;
            if !op.output_classes.contains(&item.class) {
                return Err(fail(format!("unsupported output class: {}", item.class)));
            }
            if items
                .insert((unit.id.clone(), item.id.clone()), item)
                .is_some()
            {
                return Err(fail(format!("duplicate item id: {}/{}", unit.id, item.id)));
            }
            let owner = format!("{}/{}", unit.id, item.id);
            if item.destination == Destination::Checkout {
                claim(&mut logical, &item.logical_path, &owner)?;
            }
            if item.files.is_empty() && item.destination != Destination::External {
                return Err(fail(format!("item has no file outputs: {owner}")));
            }
            if item.destination != Destination::External
                && !item.files.iter().any(|output| output.required)
            {
                return Err(fail(format!("item has no required file output: {owner}")));
            }
            for output in &item.files {
                relative_path(&output.path, true)?;
                claim(&mut job_outputs, &output.path, &owner)?;
                match (&item.destination, &output.install_path) {
                    (Destination::Checkout, Some(path)) => {
                        relative_path(path, true)?;
                        if !allowed_install_roots
                            .iter()
                            .any(|root| path.starts_with(&(root.clone() + "/")))
                        {
                            return Err(fail(format!(
                                "install path outside allowed roots: {path}"
                            )));
                        }
                        claim(&mut installs, path, &owner)?;
                    }
                    (Destination::Checkout, None) => {
                        return Err(fail(format!("missing checkout install path: {owner}")));
                    }
                    (_, Some(_)) => {
                        return Err(fail(format!("non-checkout item has install path: {owner}")));
                    }
                    (_, None) => {}
                }
            }
        }
    }
    // Refuse a declaration that would install over its own declared code/source.
    for unit in &declaration.units {
        for path in &unit.code {
            if conflict(&installs, path).is_some() {
                return Err(fail(format!("output overlaps declared code: {path}")));
            }
        }
    }
    let mut dependencies: BTreeMap<String, BTreeSet<String>> = units
        .keys()
        .map(|name| (name.clone(), BTreeSet::new()))
        .collect();
    let mut files = vec![];
    for unit in &declaration.units {
        let op = &registry[&(unit.op.kind.clone(), unit.op.version.clone())];
        let mut names = BTreeSet::new();
        for input in &unit.inputs {
            let (name, role) = match input {
                Input::Content { name, .. } => (name, InputRole::Content),
                Input::Reference { name, .. } => (name, InputRole::Reference),
            };
            identifier(name, "input name")?;
            if !names.insert(name.clone()) {
                return Err(fail(format!("duplicate input name: {}/{name}", unit.id)));
            }
            let rule = op
                .inputs
                .get(name)
                .ok_or_else(|| fail(format!("unknown op input: {name}")))?;
            if role != rule.role {
                return Err(fail(format!("wrong role for input: {name}")));
            }
            let producer = match input {
                Input::Content {
                    source,
                    whole,
                    conditional,
                    ..
                } => {
                    note(whole, "whole-input reason")?;
                    note(conditional, "input conditional note")?;
                    let narrowed = matches!(source, ContentSource::File { selector: Some(pointer), .. } if !pointer.is_empty());
                    if rule.require_whole_reason && !narrowed && whole.is_none() {
                        return Err(fail(format!(
                            "broad op input requires a whole reason: {name}"
                        )));
                    }
                    match source {
                        ContentSource::File {
                            path,
                            selector,
                            optional,
                        } => {
                            relative_path(path, false)?;
                            if conflict(&installs, path).is_some() {
                                return Err(fail(format!("output overlaps source input: {path}")));
                            }
                            if *optional && !rule.allow_absent_file {
                                return Err(fail(format!(
                                    "op input does not allow absent file: {name}"
                                )));
                            }
                            if selector.is_some() && !rule.allow_selector {
                                return Err(fail(format!(
                                    "op input does not allow selector: {name}"
                                )));
                            }
                            if let Some(selector) = selector {
                                pointer(selector)?;
                            }
                            let selection = match file(snapshot, path, *optional)? {
                                None => FileSelection::Absent,
                                Some(bytes) => {
                                    match selector {
                                        None => FileSelection::Whole,
                                        Some(selector) => {
                                            let json: serde_json::Value =
                                                serde_json::from_slice(bytes).map_err(|_| {
                                                    fail(format!(
                                                        "selector input is not JSON: {path}"
                                                    ))
                                                })?;
                                            FileSelection::Json(json.pointer(selector).cloned()
                                            .ok_or_else(|| fail(format!("missing selector node: {path}#{selector}")))?)
                                        }
                                    }
                                }
                            };
                            files.push(ResolvedFile {
                                unit: unit.id.clone(),
                                input: name.clone(),
                                path: path.clone(),
                                selection,
                            });
                            None
                        }
                        ContentSource::Item { unit, item } => Some(ItemRef {
                            unit: unit.clone(),
                            item: item.clone(),
                        }),
                    }
                }
                Input::Reference {
                    logical_path: path,
                    class,
                    proof,
                    producer,
                    ..
                } => {
                    logical_path(path)?;
                    nonempty(class, "reference class")?;
                    if !rule.item_classes.contains(class) {
                        return Err(fail(format!("unsupported reference class: {name}")));
                    }
                    nonempty(proof, "reference proof test")?;
                    if let Some(producer) = producer {
                        if let Some(item) =
                            items.get(&(producer.unit.clone(), producer.item.clone()))
                        {
                            if item.logical_path != *path || item.class != *class {
                                return Err(fail(format!(
                                    "reference identity differs from producer: {name}"
                                )));
                            }
                        }
                    }
                    producer.clone()
                }
            };
            if let Some(producer) = producer {
                let item = items
                    .get(&(producer.unit.clone(), producer.item.clone()))
                    .ok_or_else(|| {
                        fail(format!(
                            "missing producer item: {}/{}",
                            producer.unit, producer.item
                        ))
                    })?;
                if !rule.item_classes.contains(&item.class) {
                    return Err(fail(format!("unsupported producer class: {name}")));
                }
                dependencies
                    .get_mut(&unit.id)
                    .unwrap()
                    .insert(producer.unit);
            }
        }
        for (name, rule) in &op.inputs {
            if rule.required && !names.contains(name) {
                return Err(fail(format!(
                    "missing required op input: {}/{name}",
                    unit.id
                )));
            }
        }
    }
    let order = dependency_order(&dependencies)?;
    Ok(ValidatedDeclaration { order, files })
}
