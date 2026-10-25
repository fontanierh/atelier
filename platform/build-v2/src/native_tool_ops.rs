//! Fixed guarded native tool operations over the existing recipe view and result store.
use crate::keys::{ImplementationIdentity, PreparedUnit};
use crate::py_data::{ContentSlotSpec, PyDataClass, PyDataSpec};
use crate::results::FrozenOutput;
use crate::source_hashes::sha256;
use crate::validate::{OpRegistry, ParamKind, ParamRule};
use serde_json::Value;
use std::collections::BTreeMap;

pub const ENTRY: &str = "platform/studio/atelier/build_v2/native_tool_worker.py";
pub const KINDS: [&str; 5] = [
    "unreal.compile",
    "unreal.game",
    "unreal.cook.produce",
    "unreal.package",
    "package.archive",
];
pub fn supports(kind: &str) -> bool {
    KINDS.contains(&kind)
}
pub fn validator() -> ImplementationIdentity {
    ImplementationIdentity {
        version: "native-tool-fixed-1".into(),
        digest: sha256(include_bytes!("native_tool_ops.rs")),
    }
}
pub fn register(registry: &mut OpRegistry, slots: &BTreeMap<String, bool>) -> Result<(), String> {
    let mut spec = PyDataSpec::new().with_output_classes([PyDataClass::Data]);
    for (name, required) in slots {
        spec = spec.with_content_slot(name, ContentSlotSpec::broad(*required));
    }
    let mut definition = spec.build()?;
    definition.params.clear();
    for (name, kind, required) in [
        ("recipe", ParamKind::Object, true),
        ("project", ParamKind::String, false),
        ("target", ParamKind::String, false),
        ("configuration", ParamKind::String, false),
        ("archive", ParamKind::String, false),
        ("cooked_files", ParamKind::Object, false),
        ("packages", ParamKind::Array, false),
        ("record_outputs", ParamKind::Object, false),
        ("cook_root", ParamKind::String, false),
        ("native_global", ParamKind::String, false),
        ("global_data", ParamKind::String, false),
    ] {
        definition
            .params
            .insert(name.into(), ParamRule { kind, required });
    }
    for rule in definition.inputs.values_mut() {
        rule.item_classes.extend(
            [
                "StaticMeshSource",
                "RawStaticMesh",
                "StaticMesh",
                "RawTexture",
                "Texture",
                "RawSkeletalMesh",
                "SkeletalMesh",
                "RawAnimation",
                "Animation",
                "RawSound",
                "Sound",
                "Skeleton",
                "PhysicsAsset",
                "Material",
                "MaterialInstance",
                "MaterialParameterCollection",
                "Blueprint",
                "BlendSpace1D",
                "AdventureMoveSet",
                "WandererDefinition",
                "AnimBoneCompressionSettings",
                "SoundAttenuation",
                "DataAsset",
                "JsonData",
                "Map",
                "NativeCookRecord",
            ]
            .map(str::to_string),
        );
    }
    for kind in KINDS {
        let mut op = definition.clone();
        if kind == "unreal.package" {
            for rule in op.inputs.values_mut() {
                rule.item_classes.insert("CookedPackage".into());
            }
        }
        if kind == "unreal.cook.produce" {
            op.output_classes.insert("NativeCookRecord".into());
        }
        registry.insert((kind.into(), "1".into()), op);
    }
    Ok(())
}
pub fn validate_params(kind: &str, params: &BTreeMap<String, Value>) -> Result<(), String> {
    if !supports(kind)
        || params.keys().any(|key| {
            !matches!(
                key.as_str(),
                "recipe"
                    | "project"
                    | "target"
                    | "configuration"
                    | "archive"
                    | "cooked_files"
                    | "packages"
                    | "record_outputs"
                    | "cook_root"
                    | "native_global"
                    | "global_data"
            )
        })
    {
        return Err("unknown native tool operation/parameter".into());
    }
    if params.contains_key("native_global") && kind != "unreal.package" {
        return Err("native global selector is restricted to package composition".into());
    }
    if params.contains_key("global_data") && kind != "unreal.cook.produce" {
        return Err("semantic global output is restricted to the fixed source cooker".into());
    }
    let recipe = params
        .get("recipe")
        .and_then(Value::as_object)
        .ok_or("missing native recipe")?;
    if recipe.get("version").and_then(Value::as_u64) != Some(1)
        || !recipe.get("paths").is_some_and(Value::is_object)
        || !recipe.get("commands").is_some_and(Value::is_array)
        || !recipe
            .get("outputs")
            .and_then(Value::as_array)
            .is_some_and(|rows| !rows.is_empty())
    {
        return Err("incomplete native recipe view".into());
    }
    if kind != "package.archive" {
        let project = params
            .get("project")
            .and_then(Value::as_str)
            .ok_or("missing native project")?;
        crate::paths::relative_path(project, false)?;
        if !project.ends_with(".uproject") {
            return Err("native project must be a descriptor".into());
        }
    }
    Ok(())
}
pub fn check(unit: &PreparedUnit) -> Result<(), String> {
    let i = unit.ingredients();
    let expected = validator();
    if !supports(&i.op.kind)
        || i.op.version != "1"
        || i.script != ENTRY
        || i.worker_version != crate::native_tools::NATIVE_TOOL_VERSION
        || i.validator_version != expected.version
        || i.validator_digest != expected.digest
        || !i.output_groups.is_empty()
        || i.logical_outputs.iter().any(|item| {
            item.class != "Data"
                && !(i.op.kind == "unreal.cook.produce" && item.class == "NativeCookRecord")
        })
    {
        return Err("native tool implementation/output identity differs".into());
    }
    validate_params(&i.op.kind, &i.params)
}
pub fn validate_outputs(unit: &PreparedUnit, outputs: &[FrozenOutput<'_>]) -> Result<(), String> {
    check(unit)?;
    if outputs.is_empty() {
        return Err("native producer returned no files".into());
    }
    for output in outputs {
        let count = std::io::copy(
            &mut output.object.reader().map_err(|e| e.to_string())?,
            &mut std::io::sink(),
        )
        .map_err(|e| e.to_string())?;
        if count != output.object.size() {
            return Err("native frozen output size differs".into());
        }
    }
    Ok(())
}
