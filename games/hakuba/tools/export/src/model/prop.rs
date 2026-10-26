//! The `prop` kind: a made object, such as a pole, built from closed tubes and boxes, each of a named plain colour,
//! with the anchors other things fasten to.

use std::collections::BTreeMap;
use std::path::Path;

use anyhow::{Context, Result};
use glam::DVec3;
use serde::{Deserialize, Serialize};

use super::{Version, write};
use crate::glb::{Material, Mesh};
use crate::shapes::{cuboid, tube};

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Settings {
    /// Each material's linear colour, by its name.
    materials: BTreeMap<String, [f64; 3]>,
    #[serde(default)]
    tubes: Vec<Tube>,
    #[serde(default)]
    boxes: Vec<Cuboid>,
    /// The points other things fasten to, in the prop's frame, written as `anchor 0`, `anchor 1` and so on.
    #[serde(default)]
    anchors: Vec<[f64; 3]>,
}

/// A straight tube, closed at both ends.
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Tube {
    from: [f64; 3],
    to: [f64; 3],
    /// Its radius at `from` and at `to`, in metres.
    radius_m: [f64; 2],
    sides: usize,
    material: String,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Cuboid {
    centre: [f64; 3],
    /// Its length along x, y and z, in metres.
    size: [f64; 3],
    material: String,
}

pub fn export(settings: &Settings, output: &Path) -> Result<()> {
    // Each material's mesh, holding every part made of it.
    let mut meshes: BTreeMap<&str, Mesh> = BTreeMap::new();
    for t in &settings.tubes {
        let points = [(DVec3::from_array(t.from), t.radius_m[0]), (DVec3::from_array(t.to), t.radius_m[1])];
        tube(meshes.entry(&t.material).or_default(), &points, t.sides, 1.0);
    }
    for b in &settings.boxes {
        cuboid(meshes.entry(&b.material).or_default(), DVec3::from_array(b.centre), DVec3::from_array(b.size));
    }
    let mut full: Version = Vec::new();
    for (name, mesh) in meshes {
        let colour = *settings.materials.get(name).with_context(|| format!("there is no material {name}"))?;
        full.push((mesh, Material { name, texture: None, colour, cut_out: false, two_sided: false }));
    }
    let anchors: Vec<DVec3> = settings.anchors.iter().copied().map(DVec3::from_array).collect();
    write(full, None, true, &anchors, output)
}
