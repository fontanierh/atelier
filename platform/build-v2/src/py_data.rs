//! D1 plain-Python data op definition, implementation identities and class-driven output validator.
//!
//! Execution, worker dispatch and store publication belong to C1b/C2a, B2 and A9; this module
//! defines only the py_data op schema rules (PyDataSpec -> OpDefinition), the validator and
//! worker implementation identities, and the frozen-snapshot output validator (validate_py_data_outputs
//! and validate_py_data_unit_outputs).
use crate::keys::{ImplementationIdentity, PreparedUnit};
use crate::launch::PYTHON_JOB_LOOP_VERSION;
use crate::results::FrozenOutput;
use crate::source_hashes::{sha256, valid_digest};
use crate::validate::{InputRole, InputRule, OpDefinition, OpRegistry, ParamKind, ParamRule};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::io::Read;

pub const PY_DATA_OP_KIND: &str = "py_data";
pub const PY_DATA_OP_VERSION: &str = "1";
pub const PY_DATA_VALIDATOR_VERSION: &str = "atelier-py-data-validator-1";
pub const RUNTIME_BINARY_MAGIC: &[u8; 4] = b"ATD1";
pub const RUNTIME_BINARY_VERSION: u8 = 1;

/// Data-only output classes owned by py_data. Geometry (StaticMeshSource) and native
/// Material products belong to D2/D6 and are refused here.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum PyDataClass {
    Data,
    JsonData,
    RouteData,
    RuntimeData,
}

impl PyDataClass {
    pub const ALL: [Self; 4] = [
        Self::Data,
        Self::JsonData,
        Self::RouteData,
        Self::RuntimeData,
    ];

    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Data => "Data",
            Self::JsonData => "JsonData",
            Self::RouteData => "RouteData",
            Self::RuntimeData => "RuntimeData",
        }
    }

    pub fn parse(value: &str) -> Result<Self, String> {
        match value {
            "Data" => Ok(Self::Data),
            "JsonData" => Ok(Self::JsonData),
            "RouteData" => Ok(Self::RouteData),
            "RuntimeData" => Ok(Self::RuntimeData),
            other => Err(format!(
                "unsupported py_data output class {other:?}; allowed classes are Data, JsonData, RouteData, RuntimeData"
            )),
        }
    }
}

pub fn py_data_validator_identity() -> ImplementationIdentity {
    let domain = format!(
        "atelier-py-data-validator:{PY_DATA_OP_KIND}:{PY_DATA_OP_VERSION}:{PY_DATA_VALIDATOR_VERSION}"
    );
    ImplementationIdentity {
        version: PY_DATA_VALIDATOR_VERSION.into(),
        digest: sha256(domain.as_bytes()),
    }
}

pub fn py_data_worker_identity(worker_code_digest: &str) -> Result<ImplementationIdentity, String> {
    if !valid_digest(worker_code_digest) {
        return Err(
            "py_data worker code digest must be 64 lowercase SHA-256 hex characters".into(),
        );
    }
    Ok(ImplementationIdentity {
        version: PYTHON_JOB_LOOP_VERSION.into(),
        digest: worker_code_digest.into(),
    })
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ContentSlotSpec {
    pub required: bool,
    pub allow_absent_file: bool,
    pub allow_selector: bool,
    pub require_whole_reason: bool,
    pub item_classes: BTreeSet<PyDataClass>,
}

impl ContentSlotSpec {
    pub fn bounded(required: bool) -> Self {
        Self {
            required,
            allow_absent_file: !required,
            allow_selector: true,
            require_whole_reason: false,
            item_classes: PyDataClass::ALL.into_iter().collect(),
        }
    }

    pub fn broad(required: bool) -> Self {
        Self {
            required,
            allow_absent_file: !required,
            allow_selector: true,
            require_whole_reason: true,
            item_classes: PyDataClass::ALL.into_iter().collect(),
        }
    }

    pub fn with_allow_absent_file(mut self, allow: bool) -> Self {
        self.allow_absent_file = allow;
        self
    }

    pub fn with_allow_selector(mut self, allow: bool) -> Self {
        self.allow_selector = allow;
        self
    }

    pub fn with_item_classes(mut self, classes: impl IntoIterator<Item = PyDataClass>) -> Self {
        self.item_classes = classes.into_iter().collect();
        self
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ReferenceSlotSpec {
    pub required: bool,
    pub item_classes: BTreeSet<String>,
}

#[derive(Clone, Debug)]
pub struct PyDataSpec {
    content_slots: BTreeMap<String, ContentSlotSpec>,
    reference_slots: BTreeMap<String, ReferenceSlotSpec>,
    params: BTreeMap<String, ParamRule>,
    output_classes: BTreeSet<PyDataClass>,
}

impl Default for PyDataSpec {
    fn default() -> Self {
        Self::new()
    }
}

impl PyDataSpec {
    pub fn new() -> Self {
        Self {
            content_slots: BTreeMap::new(),
            reference_slots: BTreeMap::new(),
            params: BTreeMap::from([(
                "seed".into(),
                ParamRule {
                    kind: ParamKind::Integer,
                    required: false,
                },
            )]),
            output_classes: PyDataClass::ALL.into_iter().collect(),
        }
    }

    pub fn with_content_slot(mut self, name: impl Into<String>, spec: ContentSlotSpec) -> Self {
        self.content_slots.insert(name.into(), spec);
        self
    }

    pub fn with_reference_slot(
        mut self,
        name: impl Into<String>,
        required: bool,
        allowed_classes: impl IntoIterator<Item = impl Into<String>>,
    ) -> Self {
        self.reference_slots.insert(
            name.into(),
            ReferenceSlotSpec {
                required,
                item_classes: allowed_classes.into_iter().map(Into::into).collect(),
            },
        );
        self
    }

    pub fn with_param(mut self, name: impl Into<String>, kind: ParamKind, required: bool) -> Self {
        self.params
            .insert(name.into(), ParamRule { kind, required });
        self
    }

    pub fn with_output_classes(mut self, classes: impl IntoIterator<Item = PyDataClass>) -> Self {
        self.output_classes = classes.into_iter().collect();
        self
    }

    /// @cc [owner:fontanierh,label:correctness] py-data-explicit-slot-and-class-contract
    /// The py_data OpDefinition MUST declare explicit named content and reference slots, typed
    /// parameters with an integer seed rule, and only data output classes (Data, JsonData,
    /// RouteData, RuntimeData). Geometry and material output classes, catch-all wildcard slots,
    /// overlapping content/reference slot names and non-integer seed parameters MUST be refused.
    /// See tests/py_data.rs.
    pub fn build(&self) -> Result<OpDefinition, String> {
        if self.output_classes.is_empty() {
            return Err("py_data spec requires at least one allowed data output class".into());
        }
        if let Some(seed_rule) = self.params.get("seed") {
            if !matches!(seed_rule.kind, ParamKind::Integer) {
                return Err("py_data seed parameter must have Integer kind".into());
            }
        }
        for name in self.params.keys() {
            if name.trim().is_empty() {
                return Err("py_data parameter name must not be empty".into());
            }
        }

        let mut inputs = BTreeMap::new();
        for (name, spec) in &self.content_slots {
            if name.trim().is_empty() {
                return Err("py_data content slot name must not be empty".into());
            }
            if self.reference_slots.contains_key(name) {
                return Err(format!(
                    "py_data slot {name:?} cannot be both content and reference"
                ));
            }
            inputs.insert(
                name.clone(),
                InputRule {
                    role: InputRole::Content,
                    required: spec.required,
                    allow_absent_file: spec.allow_absent_file,
                    allow_selector: spec.allow_selector,
                    require_whole_reason: spec.require_whole_reason,
                    item_classes: spec
                        .item_classes
                        .iter()
                        .map(|class| class.as_str().to_string())
                        .collect(),
                },
            );
        }

        for (name, spec) in &self.reference_slots {
            if name.trim().is_empty() {
                return Err("py_data reference slot name must not be empty".into());
            }
            if spec.item_classes.is_empty()
                || spec
                    .item_classes
                    .iter()
                    .any(|class| class.trim().is_empty())
            {
                return Err(format!(
                    "py_data reference slot {name:?} requires non-empty allowed classes"
                ));
            }
            inputs.insert(
                name.clone(),
                InputRule {
                    role: InputRole::Reference,
                    required: spec.required,
                    allow_absent_file: false,
                    allow_selector: false,
                    require_whole_reason: false,
                    item_classes: spec.item_classes.clone(),
                },
            );
        }

        Ok(OpDefinition {
            inputs,
            output_classes: self
                .output_classes
                .iter()
                .map(|class| class.as_str().to_string())
                .collect(),
            params: self.params.clone(),
        })
    }

    pub fn register(&self, registry: &mut OpRegistry) -> Result<(), String> {
        let definition = self.build()?;
        registry.insert(
            (PY_DATA_OP_KIND.into(), PY_DATA_OP_VERSION.into()),
            definition,
        );
        Ok(())
    }
}

/// @cc [owner:fontanierh,label:correctness] py-data-class-driven-frozen-validation
/// Output validation for py_data MUST verify that the PreparedUnit is keyed with py_data/1 and
/// PY_DATA_VALIDATOR_VERSION, read only B1-frozen PreparedObject snapshots, and validate each
/// output by its declared item class rather than file extension alone. JSON validation for
/// JsonData and RouteData is semantic and finite, not lexical against Rust re-serialization: it
/// MUST accept valid UTF-8 JSON objects/arrays with finite numbers (including Python exponent
/// forms, signed zeros and 64-bit integers) while refusing duplicate object keys at any nesting
/// depth, non-finite numbers, lone-surrogate escapes and top-level scalars. RouteData additionally
/// requires a route object with at least two
/// finite 3D waypoints and monotone non-decreasing positive distances, RuntimeData requires a
/// framed ATD1 v1 binary payload with complete non-empty records, and Data requires non-empty
/// bytes. See tests/py_data.rs::validator_and_staging_refuse_missing_extra_links_and_malformed_domain_data
/// and tests/py_data.rs::clean_rebuild_byte_equality_across_workspaces_and_locators.
pub fn check_py_data_unit_identity(unit: &PreparedUnit) -> Result<(), String> {
    let ingredients = unit.ingredients();
    if ingredients.op.kind != PY_DATA_OP_KIND || ingredients.op.version != PY_DATA_OP_VERSION {
        return Err(format!(
            "unit op {}/{} is not {PY_DATA_OP_KIND}/{PY_DATA_OP_VERSION}",
            ingredients.op.kind, ingredients.op.version
        ));
    }
    let expected_validator = py_data_validator_identity();
    if ingredients.validator_version != expected_validator.version
        || ingredients.validator_digest != expected_validator.digest
    {
        return Err(format!(
            "unit validator identity {}/{} does not match {}",
            ingredients.validator_version, ingredients.validator_digest, expected_validator.version
        ));
    }
    if !ingredients.output_groups.is_empty() {
        return Err("py_data units do not support dynamic output_groups".into());
    }
    for item in &ingredients.logical_outputs {
        PyDataClass::parse(&item.class)?;
    }
    Ok(())
}

pub fn validate_py_data_payload(class: &str, path: &str, bytes: &[u8]) -> Result<(), String> {
    let parsed_class = PyDataClass::parse(class)?;
    if bytes.is_empty() {
        return Err(format!("{path}: py_data output is empty"));
    }
    match parsed_class {
        PyDataClass::Data => Ok(()),
        PyDataClass::JsonData => {
            let _ = validate_json_payload(bytes, path, false)?;
            Ok(())
        }
        PyDataClass::RouteData => validate_route_data(bytes, path),
        PyDataClass::RuntimeData => validate_runtime_binary(bytes, path),
    }
}

pub fn validate_py_data_unit_outputs(
    unit: &PreparedUnit,
    outputs: &[FrozenOutput<'_>],
) -> Result<(), String> {
    check_py_data_unit_identity(unit)?;
    validate_py_data_outputs(outputs)
}

pub fn validate_py_data_outputs(outputs: &[FrozenOutput<'_>]) -> Result<(), String> {
    if outputs.is_empty() {
        return Err("py_data unit produced no outputs".into());
    }
    for output in outputs {
        let mut bytes = Vec::new();
        output
            .object
            .reader()
            .map_err(|error| format!("{}: {error}", output.path))?
            .read_to_end(&mut bytes)
            .map_err(|error| format!("{}: {error}", output.path))?;
        if bytes.len() as u64 != output.object.size() {
            return Err(format!(
                "{}: frozen object size {} differs from recorded size {}",
                output.path,
                bytes.len(),
                output.object.size()
            ));
        }
        validate_py_data_payload(&output.item.class, output.path, &bytes)?;
    }
    Ok(())
}

struct StrictJsonSeed;

impl<'de> serde::de::DeserializeSeed<'de> for StrictJsonSeed {
    type Value = Value;

    fn deserialize<D>(self, deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: serde::de::Deserializer<'de>,
    {
        deserializer.deserialize_any(StrictJsonVisitor)
    }
}

struct StrictJsonVisitor;

impl<'de> serde::de::Visitor<'de> for StrictJsonVisitor {
    type Value = Value;

    fn expecting(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str("any valid finite JSON value without duplicate object keys")
    }

    fn visit_bool<E>(self, value: bool) -> Result<Self::Value, E> {
        Ok(Value::Bool(value))
    }

    fn visit_i64<E>(self, value: i64) -> Result<Self::Value, E> {
        Ok(Value::Number(value.into()))
    }

    fn visit_u64<E>(self, value: u64) -> Result<Self::Value, E> {
        Ok(Value::Number(value.into()))
    }

    fn visit_f64<E>(self, value: f64) -> Result<Self::Value, E>
    where
        E: serde::de::Error,
    {
        serde_json::Number::from_f64(value)
            .map(Value::Number)
            .ok_or_else(|| E::custom("non-finite JSON float"))
    }

    fn visit_str<E>(self, value: &str) -> Result<Self::Value, E> {
        Ok(Value::String(value.to_owned()))
    }

    fn visit_string<E>(self, value: String) -> Result<Self::Value, E> {
        Ok(Value::String(value))
    }

    fn visit_none<E>(self) -> Result<Self::Value, E> {
        Ok(Value::Null)
    }

    fn visit_unit<E>(self) -> Result<Self::Value, E> {
        Ok(Value::Null)
    }

    fn visit_seq<A>(self, mut seq: A) -> Result<Self::Value, A::Error>
    where
        A: serde::de::SeqAccess<'de>,
    {
        let mut elements = Vec::new();
        while let Some(elem) = seq.next_element_seed(StrictJsonSeed)? {
            elements.push(elem);
        }
        Ok(Value::Array(elements))
    }

    fn visit_map<A>(self, mut map: A) -> Result<Self::Value, A::Error>
    where
        A: serde::de::MapAccess<'de>,
    {
        let mut object = serde_json::Map::new();
        let mut seen = BTreeSet::new();
        while let Some(key) = map.next_key::<String>()? {
            if !seen.insert(key.clone()) {
                return Err(serde::de::Error::custom(format!(
                    "duplicate JSON object key {key:?}"
                )));
            }
            let value = map.next_value_seed(StrictJsonSeed)?;
            object.insert(key, value);
        }
        Ok(Value::Object(object))
    }
}

fn validate_json_payload(bytes: &[u8], path: &str, require_object: bool) -> Result<Value, String> {
    let text = std::str::from_utf8(bytes)
        .map_err(|error| format!("{path}: JSON payload is not valid UTF-8: {error}"))?;
    let mut deserializer = serde_json::Deserializer::from_str(text);
    let value = serde::de::DeserializeSeed::deserialize(StrictJsonSeed, &mut deserializer)
        .map_err(|error| format!("{path}: invalid JSON payload: {error}"))?;
    deserializer
        .end()
        .map_err(|error| format!("{path}: trailing content after JSON payload: {error}"))?;
    if require_object && !value.is_object() {
        return Err(format!("{path}: expected a JSON object"));
    }
    if !value.is_object() && !value.is_array() {
        return Err(format!(
            "{path}: top-level JsonData payload must be an object or array"
        ));
    }
    Ok(value)
}

fn validate_route_data(bytes: &[u8], path: &str) -> Result<(), String> {
    let value = validate_json_payload(bytes, path, true)?;
    let object = value.as_object().unwrap();
    let route_id = object
        .get("route_id")
        .and_then(Value::as_str)
        .ok_or_else(|| format!("{path}: RouteData requires string route_id"))?;
    if route_id.trim().is_empty() {
        return Err(format!("{path}: RouteData route_id must not be empty"));
    }
    let waypoints = object
        .get("waypoints")
        .and_then(Value::as_array)
        .ok_or_else(|| format!("{path}: RouteData requires waypoints array"))?;
    if waypoints.len() < 2 {
        return Err(format!(
            "{path}: RouteData requires at least 2 waypoints, got {}",
            waypoints.len()
        ));
    }
    for (index, point) in waypoints.iter().enumerate() {
        let coords = point.as_array().ok_or_else(|| {
            format!("{path}: waypoint {index} must be an [x, y, z] coordinate array")
        })?;
        if coords.len() != 3 || coords.iter().any(|c| c.as_f64().is_none()) {
            return Err(format!(
                "{path}: waypoint {index} must contain exactly 3 finite numbers"
            ));
        }
    }
    let distances = object
        .get("distances_m")
        .and_then(Value::as_array)
        .ok_or_else(|| format!("{path}: RouteData requires distances_m array"))?;
    if distances.len() != waypoints.len() {
        return Err(format!(
            "{path}: distances_m length {} differs from waypoints length {}",
            distances.len(),
            waypoints.len()
        ));
    }
    let mut parsed_distances = Vec::with_capacity(distances.len());
    for (index, item) in distances.iter().enumerate() {
        let d = item
            .as_f64()
            .ok_or_else(|| format!("{path}: distances_m[{index}] is not a finite number"))?;
        parsed_distances.push(d);
    }
    if parsed_distances[0] != 0.0 {
        return Err(format!(
            "{path}: distances_m[0] must be 0.0, got {}",
            parsed_distances[0]
        ));
    }
    for window in parsed_distances.windows(2) {
        if window[1] < window[0] {
            return Err(format!(
                "{path}: distances_m must be monotone non-decreasing ({} < {})",
                window[1], window[0]
            ));
        }
    }
    if *parsed_distances.last().unwrap() <= 0.0 {
        return Err(format!(
            "{path}: RouteData total distance must be positive, got {}",
            parsed_distances.last().unwrap()
        ));
    }
    Ok(())
}

fn validate_runtime_binary(bytes: &[u8], path: &str) -> Result<(), String> {
    if bytes.len() < 9 {
        return Err(format!(
            "{path}: RuntimeData payload is shorter than the 9-byte ATD1 header"
        ));
    }
    if &bytes[0..4] != RUNTIME_BINARY_MAGIC {
        return Err(format!("{path}: RuntimeData payload lacks ATD1 magic"));
    }
    if bytes[4] != RUNTIME_BINARY_VERSION {
        return Err(format!(
            "{path}: unsupported RuntimeData binary version {}",
            bytes[4]
        ));
    }
    let count = u32::from_be_bytes([bytes[5], bytes[6], bytes[7], bytes[8]]) as usize;
    if count == 0 {
        return Err(format!(
            "{path}: RuntimeData binary must contain at least 1 record"
        ));
    }
    let mut cursor = 9usize;
    for index in 0..count {
        if cursor + 4 > bytes.len() {
            return Err(format!(
                "{path}: truncated RuntimeData record length at index {index}"
            ));
        }
        let len = u32::from_be_bytes([
            bytes[cursor],
            bytes[cursor + 1],
            bytes[cursor + 2],
            bytes[cursor + 3],
        ]) as usize;
        cursor += 4;
        if len == 0 {
            return Err(format!(
                "{path}: RuntimeData record {index} must not be empty"
            ));
        }
        if cursor + len > bytes.len() {
            return Err(format!(
                "{path}: truncated RuntimeData record payload at index {index}"
            ));
        }
        cursor += len;
    }
    if cursor != bytes.len() {
        return Err(format!(
            "{path}: RuntimeData binary has {} trailing bytes after {count} records",
            bytes.len() - cursor
        ));
    }
    Ok(())
}
