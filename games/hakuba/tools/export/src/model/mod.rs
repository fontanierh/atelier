//! The `plant` and `prop` kinds: still models built from their settings alone, written as `<folder name>.glb`. A
//! model is built in its own frame, x and y level, z up, metres, its foot at the origin; the world places it there,
//! on the ground. Each model reaches below its foot, so it stands on any ground within that depth with no gap.
//!
//! The export holds a node `full`, the model in detail, and may hold a node `middle`, a lighter model for seeing
//! from afar. A prop made from a source model writes its middle version as a file of its own, `<folder name>.middle.glb`,
//! its parts simplified to a triangle budget for its size, so a middle tile loads none of its detail. Each is one mesh,
//! one part per material. A model that casts no shadow, such as grass, says so in each
//! node's extras: `{ "casts_shadows": false }`. A solid prop says `{ "solid": true }` in its full node's extras.
//! A prop may also hold empty nodes `anchor 0`, `anchor 1` and so on,
//! the points other things fasten to, such as cables. A source prop names shared texture assets by relative path, and
//! exports the textures only it shows (`own_textures`) beside its own file, as BC7.

pub mod plant;
pub mod prop;
mod source;

use std::path::Path;

use anyhow::{Context, Result, bail, ensure};
use glam::{DQuat, DVec3};
use serde_json::json;

use crate::glb::{Glb, Material, Mesh, y_up};

/// A model's version: its parts, each its triangles and how they look.
type Version<'a> = Vec<(Mesh, Material<'a>)>;

/// Check exported source foliage's primitive mapping and return the required alpha texture paths.
pub fn required_outputs(output: &Path) -> Result<Vec<String>> {
    let bytes = std::fs::read(output)?;
    let header = bytes.get(12..20).context("truncated model")?;
    ensure!(&header[4..] == b"JSON", "model needs a JSON chunk");
    let length = u32::from_le_bytes(header[..4].try_into().unwrap()) as usize;
    let value: serde_json::Value = serde_json::from_slice(bytes.get(20..20 + length).context("truncated model JSON")?)?;
    let mut paths = Vec::new();
    if let Some(nodes) = value["nodes"].as_array() {
        for (index, node) in nodes.iter().enumerate() {
            if node["name"] != "middle" || node["extras"].get("source_foliage").is_none() {
                continue;
            }
            let expected = source::shadow_alpha_textures(&value, index)?;
            ensure!(node["extras"]["shadow_alpha_textures"] == expected, "shadow alpha mapping is missing or stale");
            paths.extend(expected.as_array().unwrap().iter().filter_map(|p| p.as_str().map(str::to_owned)));
        }
    }
    Ok(paths)
}

/// Writes the model to `output`: `full`, then `middle` if any, then `anchors`. Fails if a version does not reach
/// below the model's foot.
fn write(
    full: Version,
    middle: Option<Version>,
    shadows: bool,
    solid: bool,
    anchors: &[DVec3],
    output: &Path,
) -> Result<()> {
    let mut glb = Glb::from_json(json!({ "asset": { "version": "2.0" } }));
    for (name, version) in [("full", Some(full)), ("middle", middle)] {
        let Some(mut version) = version else { continue };
        // glTF's y is the model's z.
        let lowest = version.iter().flat_map(|(mesh, _)| &mesh.positions).map(|p| p[1]).fold(f32::INFINITY, f32::min);
        if lowest >= 0.0 {
            bail!("the {name} model does not reach below its foot: its lowest point is {lowest} m above it");
        }
        for (mesh, material) in &mut version {
            mesh.material = glb.add_material(material);
        }
        let node = glb.add_mesh(name, &version.iter().map(|(mesh, _)| mesh).collect::<Vec<_>>());
        let mut extras = serde_json::Map::new();
        if !shadows {
            extras.insert("casts_shadows".into(), json!(false));
        }
        if solid && name == "full" {
            extras.insert("solid".into(), json!(true));
        }
        if !extras.is_empty() {
            glb.set_extras(node, extras.into());
        }
    }
    for (k, anchor) in anchors.iter().enumerate() {
        glb.add_marker(&format!("anchor {k}"), y_up(*anchor), DQuat::IDENTITY);
    }
    glb.write(output)
}

#[cfg(test)]
mod shadow_tests {
    use super::*;

    #[test]
    fn shadow_dependencies_reject_missing_or_mismatched_primitive_metadata() {
        let mut value = json!({
            "nodes": [{"name": "middle", "mesh": 0, "extras": {"source_foliage": {}, "shadow_alpha_textures": ["textures/leaf/leaf.alpha.ktx2"]}}],
            "meshes": [{"primitives": [{"material": 0}]}],
            "materials": [{"alphaMode": "MASK", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
            "textures": [{"source": 0}], "images": [{"uri": "../../textures/leaf/leaf.ktx2"}]
        });
        let path = std::env::temp_dir().join(format!("hakuba-shadow-metadata-{}.glb", std::process::id()));
        let save = |value: &serde_json::Value| {
            let json = serde_json::to_vec(value).unwrap();
            let mut bytes = vec![0; 12];
            bytes.extend((json.len() as u32).to_le_bytes());
            bytes.extend(b"JSON");
            bytes.extend(json);
            std::fs::write(&path, bytes).unwrap();
        };
        save(&value);
        assert_eq!(required_outputs(&path).unwrap(), ["textures/leaf/leaf.alpha.ktx2"]);
        value["nodes"][0]["extras"]["shadow_alpha_textures"] = json!(["textures/wrong/wrong.alpha.ktx2"]);
        save(&value);
        assert!(required_outputs(&path).is_err());
        value["nodes"][0]["extras"].as_object_mut().unwrap().remove("shadow_alpha_textures");
        save(&value);
        assert!(required_outputs(&path).is_err());
        std::fs::remove_file(path).unwrap();
    }
}
