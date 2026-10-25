//! Registered whole-producer recipe operations; scheduling, keys and storage remain A9/B3.
use crate::keys::{ImplementationIdentity, PreparedUnit};
use crate::py_data::{ContentSlotSpec, PyDataClass, PyDataSpec};
use crate::results::FrozenOutput;
use crate::source_hashes::sha256;
use crate::validate::{OpRegistry, ParamKind};
use serde::Deserialize;
use serde_json::Value;
use std::collections::BTreeMap;

pub const PYTHON_VERSION: &str = "atelier-recipe-python-job-1";
pub const BLENDER_VERSION: &str = "atelier-recipe-blender-job-1";
pub const FILES: [&str; 7] = [
    "protocol.py",
    "python_job.py",
    "python_worker.py",
    "recipe_job.py",
    "recipe_worker.py",
    "recipe_node.py",
    "recipe_media.py",
];
pub const BLENDER_FILES: [&str; 9] = [
    "protocol.py",
    "python_job.py",
    "python_worker.py",
    "blender_job.py",
    "blender_worker.py",
    "recipe_job.py",
    "recipe_worker.py",
    "recipe_node.py",
    "recipe_media.py",
];

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Recipe {
    version: u32,
    commands: Vec<Value>,
    paths: BTreeMap<String, String>,
    outputs: Vec<Output>,
    verify: Option<Value>,
    #[serde(default)]
    deferred: Vec<Value>,
    #[serde(default)]
    geometry: Option<Value>,
    #[serde(default)]
    tools: Vec<Tool>,
}
#[derive(Deserialize)]
#[serde(tag = "kind", deny_unknown_fields)]
enum Tool {
    #[serde(rename = "node.frontend")]
    Node { entry: String, sources: Vec<String> },
    #[serde(rename = "media.audio")]
    Media {
        inputs: Vec<String>,
        writes: Vec<String>,
    },
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Output {
    path: String,
    kind: String,
    file: String,
    #[serde(default = "yes")]
    required: bool,
}
fn yes() -> bool {
    true
}
fn relative(path: &str) -> bool {
    !path.is_empty()
        && !path.contains('\\')
        && path
            .split('/')
            .all(|p| !p.is_empty() && p != "." && p != "..")
}
pub fn validate_params(params: &BTreeMap<String, Value>) -> Result<(), String> {
    if params.keys().any(|name| {
        !matches!(
            name.as_str(),
            "recipe" | "geometry_root" | "parent" | "plan_limits"
        )
    }) {
        return Err("recipe requires its sole typed recipe object".into());
    }
    let recipe: Recipe =
        serde_json::from_value(params.get("recipe").ok_or("missing recipe")?.clone())
            .map_err(|e| e.to_string())?;
    if recipe.version != 1 || recipe.commands.is_empty() || recipe.outputs.is_empty() {
        return Err("empty or unknown recipe".into());
    }
    for (logical, staged) in recipe.paths {
        if !relative(&logical) || !relative(&staged) {
            return Err("nonrelative recipe mapping".into());
        }
    }
    for output in recipe.outputs {
        if !relative(&output.path)
            || !relative(&output.file)
            || !matches!(output.kind.as_str(), "file" | "tree")
        {
            return Err("invalid recipe output".into());
        }
        let _ = output.required;
    }
    if recipe.tools.len() > 1 {
        return Err("a recipe has more than one fixed tool role".into());
    }
    for tool in recipe.tools {
        match tool {
            Tool::Node { entry, sources } => {
                if !relative(&entry)
                    || sources.len() != 3
                    || !sources.contains(&entry)
                    || sources
                        .iter()
                        .collect::<std::collections::BTreeSet<_>>()
                        .len()
                        != 3
                    || sources.iter().any(|p| !relative(p) || !p.ends_with(".cjs"))
                {
                    return Err("unsupported nested Node descriptor".into());
                }
            }
            Tool::Media { inputs, writes } => {
                if inputs.is_empty()
                    || inputs.iter().any(|path| !relative(path))
                    || writes.len() != 1
                    || !relative(&writes[0])
                    || !writes[0].ends_with("/audio/.tmp")
                {
                    return Err("unsupported nested audio descriptor".into());
                }
            }
        }
    }
    for command in recipe.commands {
        let object = command
            .as_object()
            .ok_or("recipe command is not an object")?;
        let kind = object
            .get("kind")
            .and_then(Value::as_str)
            .ok_or("missing command kind")?;
        let fields: &[&str] = if kind == "call" {
            &["kind", "call"]
        } else if matches!(kind, "python" | "blender") {
            &["kind", "script", "args", "env", "threads"]
        } else {
            return Err("unsupported recipe command".into());
        };
        if object.len() != fields.len() || fields.iter().any(|k| !object.contains_key(*k)) {
            return Err("unknown/incomplete recipe command".into());
        }
    }
    let _ = (recipe.verify, recipe.deferred, recipe.geometry);
    Ok(())
}
pub fn register(registry: &mut OpRegistry, slots: &BTreeMap<String, bool>) -> Result<(), String> {
    let mut spec = PyDataSpec::new()
        .with_param("recipe", ParamKind::Object, true)
        .with_output_classes([PyDataClass::Data]);
    for (name, required) in slots {
        spec = spec.with_content_slot(name, ContentSlotSpec::broad(*required));
    }
    let mut definition = spec.build()?;
    for rule in definition.inputs.values_mut() {
        rule.item_classes
            .insert(crate::blender_ops::MESH_EXPORT_CLASS.into());
        // These are opaque, already-certified inputs here; recipe outputs remain Data.
        // External cooked packages require their separate native adapter.
        rule.item_classes.extend(
            [
                "StaticMesh",
                "SkeletalMesh",
                "Skeleton",
                "PhysicsAsset",
                "Animation",
                "Texture",
                "Sound",
                "Material",
                "MaterialInstance",
                "MaterialParameterCollection",
                "Map",
            ]
            .into_iter()
            .map(Into::into),
        );
    }
    definition.params.remove("seed");
    for (name, kind) in [
        ("geometry_root", ParamKind::String),
        ("parent", ParamKind::String),
        ("plan_limits", ParamKind::Object),
    ] {
        definition.params.insert(
            name.into(),
            crate::validate::ParamRule {
                kind,
                required: false,
            },
        );
    }
    for kind in ["recipe.python", "recipe.blender"] {
        let mut definition = definition.clone();
        if matches!(kind, "recipe.blender" | "recipe.python") {
            definition
                .output_classes
                .insert(crate::blender_ops::MESH_PAYLOAD_CLASS.into());
        }
        registry.insert((kind.into(), "1".into()), definition);
    }
    Ok(())
}
pub fn validator() -> ImplementationIdentity {
    ImplementationIdentity {
        version: "recipe-root-1".into(),
        digest: sha256(b"recipe-root-1:complete-opaque-data:declared-fixed-output-partition"),
    }
}
pub fn group_validator(
    code: &BTreeMap<String, String>,
    encoding: &crate::groups::PlanEncoding,
) -> Result<ImplementationIdentity, String> {
    if *encoding == crate::groups::PlanEncoding::EncodedGlb {
        return crate::encoded_ops::identity_from_code(code);
    }
    let mut files = BTreeMap::new();
    for name in crate::blender_ops::DECODER_FILES {
        files.insert(
            name,
            code.get(name)
                .ok_or("recipe group decoder source missing")?
                .clone(),
        );
    }
    let decoder = crate::blender_ops::decoder_identity(&files)?;
    Ok(ImplementationIdentity {
        version: "recipe-geometry-1".into(),
        digest: sha256(format!("recipe-geometry-1:{}", decoder.digest).as_bytes()),
    })
}
pub fn check(unit: &PreparedUnit) -> Result<(), String> {
    let i = unit.ingredients();
    let expected = if i.output_groups.is_empty() {
        validator()
    } else {
        group_validator(&i.code, &i.output_groups[0].encoding)?
    };
    if !matches!(i.op.kind.as_str(), "recipe.python" | "recipe.blender")
        || i.op.version != "1"
        || i.validator_version != expected.version
        || i.validator_digest != expected.digest
        || (i.output_groups.len() > 1
            || (!i.output_groups.is_empty()
                && i.op.kind != "recipe.blender"
                && i.output_groups[0].encoding != crate::groups::PlanEncoding::EncodedGlb))
        || i.logical_outputs.iter().any(|item| item.class != "Data")
    {
        return Err("unsupported recipe runtime identity".into());
    }
    validate_params(&i.params)
}
pub fn validate_outputs(unit: &PreparedUnit, outputs: &[FrozenOutput<'_>]) -> Result<(), String> {
    check(unit)?;
    crate::py_data::validate_py_data_outputs(outputs)
}
