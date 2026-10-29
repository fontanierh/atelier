//! The `prop` kind: a made object, such as a pole, built from closed tubes, boxes and prisms, each of a named plain colour,
//! with the anchors other things fasten to.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use glam::{DVec2, DVec3};
use serde::{Deserialize, Serialize};

use super::{Version, write};
use crate::glb::{Material, Mesh};
use crate::shapes::{cuboid, tube, vertex};

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Settings {
    /// Each material's linear colour, by its name.
    #[serde(default)]
    materials: BTreeMap<String, [f64; 3]>,
    /// An optional embedded static model under this asset's src folder.
    #[serde(default)]
    source: Option<String>,
    /// Texture assets referenced by the source model.
    #[serde(default)]
    textures: Vec<String>,
    /// Images only this prop shows, each `src/<name>.png`, exported beside it as `<name>.ktx2` in BC7 blocks; the
    /// source model names each as `<name>.ktx2`.
    #[serde(default)]
    own_textures: Vec<String>,
    #[serde(default)]
    tubes: Vec<Tube>,
    #[serde(default)]
    boxes: Vec<Cuboid>,
    #[serde(default)]
    prisms: Vec<Prism>,
    /// Whether the full visual mesh is solid to scenery raycasts.
    #[serde(default)]
    solid: bool,
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

/// A strictly convex profile in x/z, extruded between two y coordinates, in metres.
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Prism {
    profile: Vec<[f64; 2]>,
    y: [f64; 2],
    material: String,
}

/// @cc [owner:fontanierh,label:correctness] convex-prism-closed
/// A prism MUST reject non-finite, degenerate or non-convex input and produce a closed, outward-facing solid.
fn prism(mesh: &mut Mesh, profile: &[[f64; 2]], y: [f64; 2]) -> Result<()> {
    if profile.len() < 3
        || !y.iter().all(|v| v.is_finite())
        || y[0] >= y[1]
        || profile.iter().flatten().any(|v| !v.is_finite())
    {
        bail!("prism needs a finite profile of at least three points and increasing finite y endpoints");
    }
    // Validate at the precision stored in the GLB, so rounding cannot collapse a valid-looking face.
    let stored = |v: f64| f64::from(v as f32);
    let y = y.map(stored);
    let p: Vec<DVec2> = profile.iter().map(|point| DVec2::from_array(point.map(stored))).collect();
    if !y.iter().all(|v| v.is_finite()) || y[0] >= y[1] || p.iter().any(|v| !v.is_finite()) {
        bail!("prism coordinates must remain finite and distinct at GLB precision");
    }
    // Every other point must lie strictly on the same side of each edge. This also rejects crossings and repeats.
    let mut orientation = 0.0_f64;
    for i in 0..p.len() {
        let a = p[i];
        let edge = p[(i + 1) % p.len()] - a;
        for (j, point) in p.iter().enumerate() {
            if j == i || j == (i + 1) % p.len() {
                continue;
            }
            let cross = edge.perp_dot(*point - a);
            if !cross.is_finite() || cross == 0.0 {
                bail!("prism profile must be strictly convex");
            }
            if orientation == 0.0 {
                orientation = cross.signum();
            }
            if cross.signum() != orientation {
                bail!("prism profile must be strictly convex");
            }
        }
    }
    let centre = p.iter().copied().sum::<DVec2>() / p.len() as f64;
    let inside = DVec3::new(centre.x, (y[0] + y[1]) / 2.0, centre.y);
    let point = |i: usize, side: usize| DVec3::new(p[i].x, y[side], p[i].y);
    let mut face = |mut points: Vec<DVec3>| {
        let mut normal = (points[1] - points[0]).cross(points[2] - points[0]);
        if normal.dot(points[0] - inside) < 0.0 {
            points.reverse();
            normal = -normal;
        }
        let indices: Vec<u32> = points.into_iter().map(|at| vertex(mesh, at, normal, DVec2::ZERO, None)).collect();
        for i in 1..indices.len() - 1 {
            mesh.indices.extend([indices[0], indices[i], indices[i + 1]]);
        }
    };
    for side in 0..2 {
        face((0..p.len()).map(|i| point(i, side)).collect());
    }
    for i in 0..p.len() {
        let j = (i + 1) % p.len();
        face(vec![point(i, 0), point(j, 0), point(j, 1), point(i, 1)]);
    }
    Ok(())
}

impl Settings {
    /// Every prop also exports its middle version, which middle tiles show, and the textures only it shows.
    pub fn outputs(&self, output: &Path) -> Vec<PathBuf> {
        let mut files = vec![output.to_path_buf(), super::source::middle_path(output)];
        files.extend(self.own_textures.iter().map(|name| own_texture(output, name)));
        files
    }
}

/// Where a prop's own texture `name` is exported: beside the prop's export.
fn own_texture(output: &Path, name: &str) -> PathBuf {
    output.with_file_name(format!("{name}.ktx2"))
}

pub fn export(settings: &Settings, output: &Path) -> Result<()> {
    if let Some(source) = &settings.source {
        if !settings.materials.is_empty()
            || !settings.tubes.is_empty()
            || !settings.boxes.is_empty()
            || !settings.prisms.is_empty()
        {
            bail!("a source model cannot also specify generated geometry or materials");
        }
        let folder = output.parent().context("a prop has an asset folder")?;
        let mut own = Vec::new();
        for name in &settings.own_textures {
            if name.is_empty() || !name.bytes().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-') {
                bail!("own texture name must be kebab case");
            }
            crate::texture::export_bc7(folder, &format!("src/{name}.png"), &own_texture(output, name))?;
            own.push(format!("{name}.ktx2"));
        }
        return super::source::export(source, settings.solid, &settings.textures, &own, &settings.anchors, output);
    }
    if !settings.textures.is_empty() || !settings.own_textures.is_empty() {
        bail!("textures require a source model");
    }
    // Each material's mesh, holding every part made of it.
    let mut meshes: BTreeMap<&str, Mesh> = BTreeMap::new();
    for t in &settings.tubes {
        let points = [(DVec3::from_array(t.from), t.radius_m[0]), (DVec3::from_array(t.to), t.radius_m[1])];
        tube(meshes.entry(&t.material).or_default(), &points, t.sides, 1.0);
    }
    for b in &settings.boxes {
        cuboid(meshes.entry(&b.material).or_default(), DVec3::from_array(b.centre), DVec3::from_array(b.size));
    }
    for p in &settings.prisms {
        prism(meshes.entry(&p.material).or_default(), &p.profile, p.y)?;
    }
    let mut full: Version = Vec::new();
    for (name, mesh) in meshes {
        let colour = *settings.materials.get(name).with_context(|| format!("there is no material {name}"))?;
        full.push((mesh, Material { name, texture: None, colour, cut_out: false, two_sided: false }));
    }
    let anchors: Vec<DVec3> = settings.anchors.iter().copied().map(DVec3::from_array).collect();
    write(full, None, true, settings.solid, &anchors, output)?;
    // A made prop is a few boxes and tubes already, so its middle version is its export.
    std::fs::copy(output, super::source::middle_path(output)).context("writing the middle version")?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;

    #[test]
    fn prism_is_closed_and_faces_out_for_either_profile_order() {
        let mut profile = vec![[-1.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 2.0], [-1.0, 1.0]];
        for _ in 0..2 {
            let mut mesh = Mesh::default();
            prism(&mut mesh, &profile, [-2.0, 2.0]).unwrap();
            let mut edges = BTreeMap::new();
            let mut volume = 0.0;
            // glTF coordinates are a rotation of the authoring frame; the interior point is (0, 0.75, 0).
            let inside = DVec3::new(0.0, 0.75, 0.0);
            for t in mesh.indices.chunks_exact(3) {
                let p = [0, 1, 2].map(|k| DVec3::from_array(mesh.positions[t[k] as usize].map(f64::from)));
                let normal = (p[1] - p[0]).cross(p[2] - p[0]);
                assert!(normal.dot(p[0] - inside) > 0.0);
                volume += p[0].dot(p[1].cross(p[2])) / 6.0;
                for (a, b) in [(0, 1), (1, 2), (2, 0)] {
                    let key = |v: DVec3| v.to_array().map(|x| (x * 1000.0).round() as i64);
                    let (a, b) = (key(p[a]), key(p[b]));
                    *edges.entry(if a < b { (a, b) } else { (b, a) }).or_insert(0) += 1;
                }
            }
            assert!(edges.values().all(|count| *count == 2));
            assert!((volume - 12.0).abs() < 1e-6);
            profile.reverse();
        }
    }

    #[test]
    fn prism_rejects_invalid_profiles_and_extrusions() {
        let valid = [[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]];
        for profile in [
            vec![[0.0, 0.0], [1.0, 1.0]],
            vec![[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]],
            vec![[0.0, 0.0], [2.0, 0.0], [1.0, 0.5], [2.0, 2.0], [0.0, 2.0]],
            vec![[0.0, 0.0], [2.0, 2.0], [2.0, 0.0], [0.0, 2.0]],
            vec![[0.0, 0.0], [f64::NAN, 0.0], [0.0, 1.0]],
        ] {
            assert!(prism(&mut Mesh::default(), &profile, [0.0, 1.0]).is_err());
        }
        for y in [[1.0, 1.0], [1.0, 0.0], [0.0, f64::INFINITY], [1.0, 1.0 + f64::EPSILON]] {
            assert!(prism(&mut Mesh::default(), &valid, y).is_err());
        }
    }

    /// A prop publishes the textures only it shows beside its export and middle version.
    #[test]
    fn own_textures_are_outputs() {
        let settings: Settings =
            toml_edit::de::from_str("source = \"src/model.glb\"\nown_textures = [\"parasol\"]").unwrap();
        let output = Path::new("props/cafe/cafe.glb");
        assert_eq!(
            settings.outputs(output),
            [
                PathBuf::from("props/cafe/cafe.glb"),
                "props/cafe/cafe.middle.glb".into(),
                "props/cafe/parasol.ktx2".into()
            ]
        );
    }
}
