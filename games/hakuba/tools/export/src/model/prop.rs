//! The `prop` kind: a made object, such as a pole, built from closed tubes, boxes, prisms and polygon slabs, each of a named plain colour,
//! with the anchors other things fasten to.

use std::collections::BTreeMap;
use std::path::Path;

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
    materials: BTreeMap<String, [f64; 3]>,
    #[serde(default)]
    tubes: Vec<Tube>,
    #[serde(default)]
    boxes: Vec<Cuboid>,
    #[serde(default)]
    prisms: Vec<Prism>,
    #[serde(default)]
    slabs: Vec<Slab>,
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

/// A convex planar polygon extruded by a vector, in metres.
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Slab {
    polygon: Vec<[f64; 3]>,
    extrusion: [f64; 3],
    material: String,
}

/// @cc [owner:fontanierh,label:correctness] convex-slab-closed
/// A slab MUST reject invalid or non-convex polygons and zero-volume extrusions at stored precision, and produce
/// a closed solid with outward-facing triangles.
fn slab(mesh: &mut Mesh, polygon: &[[f64; 3]], extrusion: [f64; 3]) -> Result<()> {
    if polygon.len() < 3 || polygon.iter().flatten().chain(extrusion.iter()).any(|v| !v.is_finite()) {
        bail!("slab needs a finite polygon with at least three vertices and a finite extrusion");
    }
    let stored = |p: DVec3| DVec3::from_array(p.to_array().map(|v| f64::from(v as f32)));
    let p: Vec<DVec3> = polygon.iter().map(|&p| stored(DVec3::from_array(p))).collect();
    let shift = DVec3::from_array(extrusion);
    let q: Vec<DVec3> = polygon.iter().map(|&p| stored(DVec3::from_array(p) + shift)).collect();
    if p.iter().chain(&q).any(|v| !v.is_finite()) {
        bail!("slab coordinates must remain finite at GLB precision");
    }
    let normal = (p[1] - p[0]).cross(p[2] - p[0]);
    let size = p.iter().map(|v| (*v - p[0]).length()).fold(0.0_f64, f64::max);
    if size == 0.0 || normal.length() == 0.0 {
        bail!("slab polygon must have area");
    }
    // Allow plane error up to one millionth of the stored polygon extent in metres for f32 rounding.
    let unit = normal.normalize();
    let tolerance = size * 1e-6;
    let validate = |points: &[DVec3]| -> Result<()> {
        if points.iter().any(|p| (*p - points[0]).dot(unit).abs() > tolerance) {
            bail!("slab polygon must be planar at GLB precision");
        }
        for i in 0..points.len() {
            let edge = points[(i + 1) % points.len()] - points[i];
            for (j, point) in points.iter().enumerate() {
                if j != i && j != (i + 1) % points.len() && edge.cross(*point - points[i]).dot(unit) <= 0.0 {
                    bail!("slab polygon must be strictly convex at GLB precision");
                }
            }
        }
        Ok(())
    };
    validate(&p)?;
    validate(&q)?;
    let depth = (q[0] - p[0]).dot(unit);
    if shift.dot(unit).abs() <= shift.length() * 1e-12 || depth == 0.0 || !depth.is_finite() {
        bail!("slab extrusion must have nonzero volume at GLB precision");
    }
    for i in 0..p.len() {
        let j = (i + 1) % p.len();
        let first = (p[j] - p[i]).cross(q[j] - p[i]);
        let second = (q[j] - p[i]).cross(q[i] - p[i]);
        if first.length_squared() == 0.0 || second.length_squared() == 0.0 || first.dot(second) <= 0.0 {
            bail!("slab side collapses or folds at GLB precision");
        }
    }
    let inside = (p.iter().copied().sum::<DVec3>() + q.iter().copied().sum::<DVec3>()) / (2 * p.len()) as f64;
    // At very small depths, rounding can put the interior on the wrong side of a cap or twist a side. Check the
    // same triangle fans the writer will emit, and require neighbouring faces to traverse shared edges oppositely.
    let winding = |points: &[DVec3]| -> Result<f64> {
        let side = (points[1] - points[0]).cross(points[2] - points[0]).dot(points[0] - inside);
        if side == 0.0 || !side.is_finite() {
            bail!("slab face collapses at GLB precision");
        }
        let mut points = points.to_vec();
        if side < 0.0 {
            points.reverse();
        }
        for i in 1..points.len() - 1 {
            let n = (points[i] - points[0]).cross(points[i + 1] - points[0]);
            if n.dot(points[0] - inside) <= 0.0 {
                bail!("slab face folds at GLB precision");
            }
        }
        Ok(side.signum())
    };
    let cap = winding(&p)?;
    if winding(&q)? == cap {
        bail!("slab caps do not enclose an interior at GLB precision");
    }
    for i in 0..p.len() {
        let j = (i + 1) % p.len();
        if winding(&[p[i], p[j], q[j], q[i]])? == cap {
            bail!("slab side does not enclose an interior at GLB precision");
        }
    }
    closed_extrusion(mesh, &p, &q, inside);
    Ok(())
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
    let first: Vec<DVec3> = (0..p.len()).map(|i| point(i, 0)).collect();
    let second: Vec<DVec3> = (0..p.len()).map(|i| point(i, 1)).collect();
    closed_extrusion(mesh, &first, &second, inside);
    Ok(())
}

/// Writes both caps and the sides of an already validated extrusion.
fn closed_extrusion(mesh: &mut Mesh, first: &[DVec3], second: &[DVec3], inside: DVec3) {
    let mut face = |mut points: Vec<DVec3>| {
        let mut n = (points[1] - points[0]).cross(points[2] - points[0]);
        if n.dot(points[0] - inside) < 0.0 {
            points.reverse();
            n = -n;
        }
        let indices: Vec<u32> = points.into_iter().map(|at| vertex(mesh, at, n, DVec2::ZERO, None)).collect();
        for i in 1..indices.len() - 1 {
            mesh.indices.extend([indices[0], indices[i], indices[i + 1]]);
        }
    };
    face(first.to_vec());
    face(second.to_vec());
    for i in 0..first.len() {
        let j = (i + 1) % first.len();
        face(vec![first[i], first[j], second[j], second[i]]);
    }
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
    for p in &settings.prisms {
        prism(meshes.entry(&p.material).or_default(), &p.profile, p.y)?;
    }
    for p in &settings.slabs {
        slab(meshes.entry(&p.material).or_default(), &p.polygon, p.extrusion)?;
    }
    let mut full: Version = Vec::new();
    for (name, mesh) in meshes {
        let colour = *settings.materials.get(name).with_context(|| format!("there is no material {name}"))?;
        full.push((mesh, Material { name, texture: None, colour, cut_out: false, two_sided: false }));
    }
    let anchors: Vec<DVec3> = settings.anchors.iter().copied().map(DVec3::from_array).collect();
    write(full, None, true, settings.solid, &anchors, output)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;

    #[test]
    fn slab_settings_export_a_closed_mesh_with_its_material() {
        let text = r#"
            [materials]
            paint = [0.2, 0.3, 0.4]
            [[slabs]]
            polygon = [[0, 0, 0], [2, 0, 1], [2, 2, 1], [0, 2, 0]]
            extrusion = [0, 0, -0.5]
            material = "paint"
        "#;
        let settings: Settings = toml_edit::de::from_str(text).unwrap();
        let path = std::env::temp_dir().join(format!("hakuba-slab-export-{}.glb", std::process::id()));
        export(&settings, &path).unwrap();
        let bytes = std::fs::read(&path).unwrap();
        std::fs::remove_file(path).unwrap();
        let length = u32::from_le_bytes(bytes[12..16].try_into().unwrap()) as usize;
        let json: serde_json::Value = serde_json::from_slice(&bytes[20..20 + length]).unwrap();
        let primitive = &json["meshes"][0]["primitives"][0];
        let material = primitive["material"].as_u64().unwrap() as usize;
        assert_eq!(json["materials"][material]["name"], "paint");
        let accessor = |index: usize| {
            let a = &json["accessors"][index];
            let view = &json["bufferViews"][a["bufferView"].as_u64().unwrap() as usize];
            let start = 20
                + length
                + 8
                + view["byteOffset"].as_u64().unwrap_or(0) as usize
                + a["byteOffset"].as_u64().unwrap_or(0) as usize;
            (start, a["count"].as_u64().unwrap() as usize)
        };
        let (pos_start, pos_count) = accessor(primitive["attributes"]["POSITION"].as_u64().unwrap() as usize);
        let (index_start, index_count) = accessor(primitive["indices"].as_u64().unwrap() as usize);
        let points: Vec<DVec3> = bytes[pos_start..pos_start + pos_count * 12]
            .chunks_exact(12)
            .map(|p| {
                let f = |i: usize| f32::from_le_bytes(p[i..i + 4].try_into().unwrap()) as f64;
                DVec3::new(f(0), f(4), f(8))
            })
            .collect();
        let indices: Vec<usize> = bytes[index_start..index_start + index_count * 4]
            .chunks_exact(4)
            .map(|p| u32::from_le_bytes(p.try_into().unwrap()) as usize)
            .collect();
        let mut edges = BTreeMap::new();
        let mut volume = 0.0;
        for t in indices.chunks_exact(3) {
            let p = [points[t[0]], points[t[1]], points[t[2]]];
            volume += p[0].dot(p[1].cross(p[2])) / 6.0;
            for (a, b) in [(0, 1), (1, 2), (2, 0)] {
                let key = |v: DVec3| v.to_array().map(|x| (x * 1000.0).round() as i64);
                let (a, b) = (key(p[a]), key(p[b]));
                *edges.entry(if a < b { (a, b) } else { (b, a) }).or_insert(0) += 1;
            }
        }
        assert!(edges.values().all(|count| *count == 2));
        assert!((volume - 2.0).abs() < 1e-6);
    }

    #[test]
    fn slab_is_closed_and_outward_for_both_orders_and_extrusion_sides() {
        let mut polygon = vec![[0.0, 0.0, 0.0], [2.0, 0.0, 1.0], [2.0, 2.0, 1.0], [0.0, 2.0, 0.0]];
        for _ in 0..2 {
            for depth in [-0.5, 0.5] {
                let mut mesh = Mesh::default();
                slab(&mut mesh, &polygon, [0.0, 0.0, depth]).unwrap();
                let inside = DVec3::new(1.0, 0.5 + depth / 2.0, -1.0);
                let mut edges = BTreeMap::new();
                let mut volume = 0.0;
                for triangle in mesh.indices.chunks_exact(3) {
                    let p = [0, 1, 2].map(|i| DVec3::from_array(mesh.positions[triangle[i] as usize].map(f64::from)));
                    assert!((p[1] - p[0]).cross(p[2] - p[0]).dot(p[0] - inside) > 0.0);
                    volume += p[0].dot(p[1].cross(p[2])) / 6.0;
                    for (a, b) in [(0, 1), (1, 2), (2, 0)] {
                        let key = |v: DVec3| v.to_array().map(|x| (x * 1000.0).round() as i64);
                        let (a, b) = (key(p[a]), key(p[b]));
                        *edges.entry(if a < b { (a, b) } else { (b, a) }).or_insert(0) += 1;
                    }
                }
                assert!(edges.values().all(|count| *count == 2));
                assert!((volume - 2.0).abs() < 1e-6);
            }
            polygon.reverse();
        }
    }

    #[test]
    fn slab_rejects_invalid_faces_and_collapsed_extrusions() {
        let valid = [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [2.0, 2.0, 0.0], [0.0, 2.0, 0.0]];
        for polygon in [
            vec![[0.0, 0.0, 0.0], [1.0, 1.0, 0.0]],
            vec![[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [1.0, 0.5, 0.0], [2.0, 2.0, 0.0], [0.0, 2.0, 0.0]],
            vec![[0.0, 0.0, 0.0], [2.0, 2.0, 0.0], [2.0, 0.0, 0.0], [0.0, 2.0, 0.0]],
            vec![[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [2.0, 2.0, 0.1], [0.0, 2.0, 0.0]],
            vec![[0.0, 0.0, 0.0], [f64::NAN, 0.0, 0.0], [0.0, 1.0, 0.0]],
        ] {
            assert!(slab(&mut Mesh::default(), &polygon, [0.0, 0.0, 0.2]).is_err());
        }
        for extrusion in [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, f64::INFINITY]] {
            assert!(slab(&mut Mesh::default(), &valid, extrusion).is_err());
        }
        let rounded = [[0.0, 0.0, 0.1], [2.0, 0.0, 0.3], [2.0, 2.0, 0.7], [0.0, 2.0, 0.5]];
        assert!(slab(&mut Mesh::default(), &rounded, [1.0, 1.0, 0.30000001]).is_err());
        let sloped = [[0.0, 0.0, 0.0], [2.0, 0.0, 1.0], [2.0, 2.0, 1.0], [0.0, 2.0, 0.0]];
        assert!(slab(&mut Mesh::default(), &sloped, [2.0, 0.0, 1.0]).is_err());
        let high = [[0.0, 0.0, 1.0], [2.0, 0.0, 1.0], [2.0, 2.0, 1.0], [0.0, 2.0, 1.0]];
        assert!(slab(&mut Mesh::default(), &high, [0.0, 0.0, f64::EPSILON]).is_err());
    }

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
}
