//! Independent source-authored triangle surfaces. Unlike draped overlays these may cross terrain.

use anyhow::{Result, bail};
use glam::{DVec2, DVec3};
use serde::{Deserialize, Serialize};

use super::game;
use super::raised::SurfacePaint;
use super::surface::weights;
use crate::glb::Mesh;

#[derive(Deserialize, Serialize)]
pub struct Triangle {
    pub xyz: [[f64; 3]; 3],
    pub uv: [[f64; 2]; 3],
    pub normal: [[f64; 3]; 3],
}

pub struct AuthoredSurface {
    pub name: &'static str,
    pub texture: &'static str,
    pub tint: [f64; 3],
    pub paint: Option<SurfacePaint>,
    pub triangles: Vec<Triangle>,
}

impl AuthoredSurface {
    /// Source triangles retain their own elevations and attributes, including source-proven terrain crossings.
    pub fn validate(&self) -> Result<()> {
        if self.paint.as_ref().is_some_and(|paint| !paint.valid()) {
            bail!("invalid authored surface paint");
        }
        if !self.tint.iter().all(|x| x.is_finite() && *x >= 0.0) {
            bail!("invalid surface tint");
        }
        for tri in &self.triangles {
            if !tri
                .xyz
                .iter()
                .flatten()
                .chain(tri.uv.iter().flatten())
                .chain(tri.normal.iter().flatten())
                .all(|v| v.is_finite() && (*v as f32).is_finite())
            {
                bail!("invalid authored surface coordinate");
            }
            let points = tri.xyz.map(DVec3::from_array);
            let cross = (points[1] - points[0]).cross(points[2] - points[0]);
            if cross.z <= 1e-12 || tri.normal.iter().any(|n| DVec3::from_array(*n).dot(cross) <= 0.0) {
                bail!("authored surface must have nondegenerate upward triangles and normals");
            }
        }
        Ok(())
    }

    /// Clip only at tile boundaries, interpolating the unnormalized source normal field and other attributes.
    pub fn mesh(&self, low: DVec2, high: DVec2) -> Result<Mesh> {
        let mut mesh = Mesh::default();
        for source in &self.triangles {
            let xyz = source.xyz.map(DVec3::from_array);
            let outline = xyz.map(DVec3::truncate);
            let normals = source.normal.map(DVec3::from_array);
            let uvs = source.uv.map(DVec2::from_array);
            {
                let clip = clip_rectangle(outline.to_vec(), low, high);
                if clip.len() < 3 {
                    continue;
                }
                let first = mesh.positions.len() as u32;
                for p in clip.iter().copied() {
                    let w = weights(outline, p).expect("validated triangle");
                    let z = w.x * xyz[0].z + w.y * xyz[1].z + w.z * xyz[2].z;
                    let normal = normals[0] * w.x + normals[1] * w.y + normals[2] * w.z;
                    let uv = uvs[0] * w.x + uvs[1] * w.y + uvs[2] * w.z;
                    mesh.positions.push(game(p.extend(z)).as_vec3().to_array());
                    mesh.normals.push(game(normal).as_vec3().to_array());
                    mesh.uvs.push(uv.as_vec2().to_array());
                }
                for n in 1..clip.len() as u32 - 1 {
                    let indices = [first, first + n, first + n + 1];
                    let [a, b, c] = indices.map(|i| DVec3::from_array(mesh.positions[i as usize].map(f64::from)));
                    let area = (b - a).cross(c - a).y;
                    if area < 0.0 {
                        bail!("stored authored surface triangle reverses winding");
                    }
                    if area > 0.0 {
                        mesh.indices.extend(indices);
                    }
                }
            }
        }
        Ok(mesh)
    }
}

fn clip_rectangle(mut polygon: Vec<DVec2>, low: DVec2, high: DVec2) -> Vec<DVec2> {
    for (axis, bound, sign) in [(0, low.x, 1.0), (0, high.x, -1.0), (1, low.y, 1.0), (1, high.y, -1.0)] {
        let mut out = Vec::new();
        for n in 0..polygon.len() {
            let p = polygon[n];
            let q = polygon[(n + 1) % polygon.len()];
            let dp = sign * (p[axis] - bound);
            let dq = sign * (q[axis] - bound);
            if dp >= 0.0 {
                out.push(p);
            }
            if (dp >= 0.0) != (dq >= 0.0) {
                let mut intersection = p + (q - p) * (dp / (dp - dq));
                intersection[axis] = bound;
                out.push(intersection);
            }
        }
        polygon = out;
        if polygon.is_empty() {
            break;
        }
    }
    let area: f64 = (1..polygon.len().saturating_sub(1))
        .map(|n| (polygon[n] - polygon[0]).perp_dot(polygon[n + 1] - polygon[0]))
        .sum();
    if area == 0.0 { Vec::new() } else { polygon }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn source() -> AuthoredSurface {
        AuthoredSurface {
            name: "test road",
            texture: "road",
            tint: [1.0; 3],
            paint: None,
            triangles: vec![Triangle {
                xyz: [[0.0, 0.0, -1.0], [2.0, 0.0, 1.0], [0.0, 2.0, -1.0]],
                uv: [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]],
                normal: [[0.0, 0.0, 1.0], [0.02, 0.0, 1.0], [0.0, 0.02, 1.0]],
            }],
        }
    }
    #[test]
    fn clipping_preserves_source_height_uv_normals_and_shared_boundary() {
        let surface = source();
        surface.validate().unwrap();
        let left = surface.mesh(DVec2::ZERO, DVec2::new(1.0, 2.0)).unwrap();
        let right = surface.mesh(DVec2::new(1.0, 0.0), DVec2::splat(2.0)).unwrap();
        for mesh in [&left, &right] {
            for (i, [x, height, neg_y]) in mesh.positions.iter().copied().enumerate() {
                assert!((height - (x - 1.0)).abs() < 1e-6);
                assert!((mesh.uvs[i][0] - x / 2.0).abs() < 1e-6);
                assert!((mesh.uvs[i][1] + neg_y / 2.0).abs() < 1e-6);
                assert!((mesh.normals[i][0] - x * 0.01).abs() < 1e-6);
                assert!((mesh.normals[i][2] - neg_y * 0.01).abs() < 1e-6);
            }
        }
        let edge = |mesh: &Mesh| {
            let mut vertices: Vec<_> = mesh.positions.iter().filter(|p| p[0] == 1.0).copied().collect();
            vertices.sort_by(|a, b| a[2].total_cmp(&b[2]));
            vertices.dedup();
            vertices
        };
        assert_eq!(edge(&left), edge(&right));
    }
    #[test]
    fn explicit_crossing_queries_visible_surface_and_keeps_default_ground() {
        let ground = Mesh {
            positions: vec![[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 0.0, -2.0]],
            indices: vec![0, 1, 2],
            ..Default::default()
        };
        let road = source().mesh(DVec2::ZERO, DVec2::splat(2.0)).unwrap();
        let plain = super::super::surface::Surface::with_crossings(&ground, &[]);
        let crossed = super::super::surface::Surface::with_crossings(&ground, &[road]);
        assert_eq!(plain.height(DVec2::new(0.25, 0.25)), Some(0.0));
        assert_eq!(crossed.height(DVec2::new(0.25, 0.25)), Some(0.0));
        assert_eq!(crossed.height(DVec2::new(1.5, 0.25)), Some(0.5));
        assert_eq!(crossed.crossing_slope_over(DVec2::new(0.25, 0.25), Some(0.0)), None);
        assert_eq!(crossed.crossing_slope_over(DVec2::new(1.5, 0.25), Some(0.0)), Some(1.0));
    }
}
