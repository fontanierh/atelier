//! The `plant` and `prop` kinds: still models built from their settings alone, written as `<folder name>.glb`. A
//! model is built in its own frame, x and y level, z up, metres, its foot at the origin; the world places it there,
//! on the ground. Each model reaches below its foot, so it stands on any ground within that depth with no gap.
//!
//! The export holds a node `full`, the model in detail, and may hold a node `middle`, a lighter model for seeing
//! from afar. Each is one mesh, one part per material. A model that casts no shadow, such as grass, says so in each
//! node's extras: `{ "casts_shadows": false }`. A solid prop says `{ "solid": true }` in its full node's extras.
//! A prop may also hold empty nodes `anchor 0`, `anchor 1` and so on,
//! the points other things fasten to, such as cables.

pub mod plant;
pub mod prop;

use std::path::Path;

use anyhow::{Result, bail};
use glam::{DQuat, DVec3};
use serde_json::json;

use crate::glb::{Glb, Material, Mesh, y_up};

/// A model's version: its parts, each its triangles and how they look.
type Version<'a> = Vec<(Mesh, Material<'a>)>;

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
