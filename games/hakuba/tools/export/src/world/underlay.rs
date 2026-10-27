//! Remove a declared surface's footprint from the ground it owns.

use super::surface::weights;
use crate::glb::Mesh;
use glam::{DVec2, DVec3};

// Convex combinations preserve the L-infinity bound on rounding each point.
fn hull(mut points: Vec<DVec2>) -> Vec<DVec2> {
    points.sort_by(|a, b| a.x.total_cmp(&b.x).then(a.y.total_cmp(&b.y)));
    points.dedup();
    if points.len() < 3 {
        return points;
    }
    fn half<'a>(points: impl Iterator<Item = &'a DVec2>) -> Vec<DVec2> {
        let mut part: Vec<DVec2> = Vec::new();
        for &p in points {
            while part.len() >= 2
                && (part[part.len() - 1] - part[part.len() - 2]).perp_dot(p - part[part.len() - 1]) <= 0.0
            {
                part.pop();
            }
            part.push(p);
        }
        part
    }
    let mut lower = half(points.iter());
    let mut upper = half(points.iter().rev());
    lower.pop();
    upper.pop();
    lower.extend(upper);
    lower
}

// The complete stored owner bounds and fixed tile span bound all touched
// tile coordinates; unlike map-wide extrema this does not change with distant owners.
pub fn owner_collar(surface: &super::raised::Raised, tile_m: f64) -> anyhow::Result<f64> {
    if !surface.cut_ground {
        return Ok(0.0);
    }
    if !tile_m.is_finite() || tile_m <= 0.0 {
        anyhow::bail!("invalid tile span for underlay");
    }
    let m =
        surface.triangles.iter().flatten().flat_map(|(p, _)| [p.x.abs(), p.y.abs()]).fold(0.0_f64, f64::max) + tile_m;
    let m = m as f32;
    if !m.is_finite() {
        anyhow::bail!("{} has unrepresentable underlay bounds", surface.name);
    }
    let upper = f32::from_bits(m.to_bits() + 1);
    let next = f32::from_bits(m.to_bits() + 2);
    let collar = f64::from(next) - f64::from(upper);
    if !collar.is_finite() || collar <= 0.0 {
        anyhow::bail!("{} has unrepresentable underlay precision", surface.name);
    }
    Ok(collar)
}

// Use the same two endpoint attributes on both sides of a stored ground edge.
fn ground_weights(corners: [DVec2; 3], p: DVec2) -> DVec3 {
    for (i, j) in [(0, 1), (1, 2), (2, 0)] {
        let (i, j) = if corners[i].x.total_cmp(&corners[j].x).then(corners[i].y.total_cmp(&corners[j].y)).is_gt() {
            (j, i)
        } else {
            (i, j)
        };
        let (a, b) = (corners[i], corners[j]);
        let d = b - a;
        if (p - a).perp_dot(d) == 0.0 {
            let t = if d.x.abs() >= d.y.abs() { (p.x - a.x) / d.x } else { (p.y - a.y) / d.y };
            if (0.0..=1.0).contains(&t) {
                let mut w = [0.0; 3];
                w[i] = 1.0 - t;
                w[j] = t;
                return DVec3::from_array(w);
            }
        }
    }
    weights(corners, p).expect("ground triangle must have area")
}

fn expanded(triangle: [DVec2; 3], collar: f64) -> Vec<DVec2> {
    hull(
        triangle
            .into_iter()
            .flat_map(|p| {
                [-collar, collar]
                    .into_iter()
                    .flat_map(move |x| [-collar, collar].into_iter().map(move |y| p + DVec2::new(x, y)))
            })
            .collect(),
    )
}

pub struct Underlay {
    pub polygon: geo::MultiPolygon<f64>,
    pub query: geo::MultiPolygon<f64>,
}

pub fn union(tops: &[Mesh], collar: f64) -> Option<Underlay> {
    if tops.iter().all(|top| top.indices.is_empty()) {
        return None;
    }
    let triangles = tops
        .iter()
        .flat_map(|top| super::surface::Surface::new(top).triangles)
        .map(|triangle| triangle.map(DVec3::truncate))
        .filter(|triangle| {
            let signed = (triangle[1] - triangle[0]).perp_dot(triangle[2] - triangle[0]);
            assert!(signed >= 0.0, "stored top triangle reversed");
            signed > 0.0
        })
        .collect::<Vec<_>>();
    let make = |width| {
        let polys = triangles
            .iter()
            .map(|&triangle| {
                let points = expanded(triangle, width);
                geo::Polygon::new(
                    geo::LineString::new(points.iter().map(|p| geo::Coord { x: p.x, y: p.y }).collect()),
                    vec![],
                )
            })
            .collect::<Vec<_>>();
        geo::unary_union(&polys)
    };
    Some(Underlay { polygon: make(collar), query: make(collar * 2.0) })
}

/// Subtract one globally unioned footprint from each original terrain triangle.
pub fn remove_covered(mesh: &Mesh, owners: &[Underlay]) -> Mesh {
    use geo::{BooleanOps, Coord, Intersects, LineString, Polygon, TriangulateEarcut, Validation};
    let ring = |points: &[DVec2]| LineString::new(points.iter().map(|p| Coord { x: p.x, y: p.y }).collect());
    let mut result = mesh.clone();
    result.indices.clear();
    for ids in mesh.indices.chunks_exact(3) {
        let positions = [ids[0], ids[1], ids[2]].map(|i| DVec3::from_array(mesh.positions[i as usize].map(f64::from)));
        let corners = positions.map(|p| DVec2::new(p.x, -p.z));
        let original = Polygon::new(ring(&corners), vec![]);
        let relevant = owners.iter().filter(|owner| owner.polygon.intersects(&original)).collect::<Vec<_>>();
        if relevant.is_empty() {
            result.indices.extend_from_slice(ids);
            continue;
        }
        let mut diff = geo::MultiPolygon(vec![original]);
        for owner in relevant {
            diff = diff.difference(&owner.polygon);
        }
        for polygon in diff {
            let snap = |ring: &LineString<f64>| {
                let mut points =
                    ring.0.iter().map(|p| Coord { x: p.x as f32 as f64, y: p.y as f32 as f64 }).collect::<Vec<_>>();
                points.dedup();
                assert!(points.len() >= 4, "stored ring collapsed");
                LineString::new(points)
            };
            let stored = Polygon::new(snap(polygon.exterior()), polygon.interiors().iter().map(snap).collect());
            assert!(stored.is_valid(), "stored polygon invalid: {:?}", stored.validation_errors());
            for t in stored.earcut_triangles() {
                let original_points = [t.v1(), t.v2(), t.v3()].map(|p| DVec2::new(p.x, p.y));
                let original_signed =
                    (original_points[1] - original_points[0]).perp_dot(original_points[2] - original_points[0]);
                let mut points = original_points.map(|p| p.as_vec2().as_dvec2());
                let signed = (points[1] - points[0]).perp_dot(points[2] - points[0]);
                if signed == 0.0 {
                    continue;
                }
                assert!(original_signed * signed > 0.0, "stored earcut triangle reversed");
                if signed < 0.0 {
                    points.swap(1, 2);
                }
                let first = result.positions.len() as u32;
                for p in points {
                    let w = ground_weights(corners, p);
                    let pos = positions[0] * w.x + positions[1] * w.y + positions[2] * w.z;
                    let normal = ids.iter().zip(w.to_array()).fold(DVec3::ZERO, |sum, (i, weight)| {
                        sum + DVec3::from_array(mesh.normals[*i as usize].map(f64::from)) * weight
                    });
                    let uv = ids.iter().zip(w.to_array()).fold(DVec2::ZERO, |sum, (i, weight)| {
                        sum + DVec2::from_array(mesh.uvs[*i as usize].map(f64::from)) * weight
                    });
                    result.positions.push([p.x as f32, pos.y as f32, -p.y as f32]);
                    result.normals.push(normal.as_vec3().to_array());
                    result.uvs.push(uv.as_vec2().to_array());
                }
                result.indices.extend([first, first + 1, first + 2]);
            }
        }
    }
    result
}
