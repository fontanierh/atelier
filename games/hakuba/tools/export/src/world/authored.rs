//! Independent source-authored triangle surfaces. Unlike draped overlays these may cross terrain.

use anyhow::{Result, bail};
use glam::{DVec2, DVec3};
use serde::{Deserialize, Serialize};

use super::game;
use super::raised::SurfacePaint;
use super::surface::{Surface, weights};
use crate::glb::Mesh;

#[derive(Deserialize, Serialize)]
pub struct Triangle {
    pub xyz: [[f64; 3]; 3],
    pub uv: [[f64; 2]; 3],
    pub normal: [[f64; 3]; 3],
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub colour: Option<[[f64; 4]; 3]>,
}

#[derive(Serialize)]
pub struct VertexPaint {
    pub fill: f32,
    pub glow: f32,
    pub glow_min: [f32; 3],
    pub glow_max: [f32; 3],
    pub haze_start_m: f32,
    pub haze_length_m: f32,
    pub haze_colour: [f32; 3],
}

/// How far an authored surface must lie above or below the ground to be the one drawn there. Closer, the two draw the
/// same pixels and flicker.
pub const CLEARANCE_M: f64 = 0.02;

/// How finely [`AuthoredSurface::check_owned`] samples each triangle: the steps along each of its sides.
const OWNED_STEPS: usize = 4;

pub struct AuthoredSurface {
    pub name: &'static str,
    pub texture: Option<&'static str>,
    pub tint: [f64; 3],
    pub paint: Option<SurfacePaint>,
    pub vertex_paint: Option<VertexPaint>,
    pub triangles: Vec<Triangle>,
}

impl AuthoredSurface {
    /// Source triangles retain their own elevations and attributes, including source-proven terrain crossings.
    pub fn validate(&self) -> Result<()> {
        if self.texture.is_some() == self.vertex_paint.is_some() || (self.paint.is_some() && self.texture.is_none()) {
            bail!("authored surface needs exactly one textured or vertex-painted material");
        }
        if self.vertex_paint.is_some() && self.tint != [1.0; 3] {
            bail!("vertex-painted surfaces require a white base");
        }
        if let Some(paint) = &self.vertex_paint
            && (!paint.fill.is_finite()
                || paint.fill < 0.0
                || !paint.glow.is_finite()
                || paint.glow < 0.0
                || !paint.haze_start_m.is_finite()
                || paint.haze_start_m < 0.0
                || !paint.haze_length_m.is_finite()
                || paint.haze_length_m <= 0.0
                || paint.haze_colour.iter().any(|x| !x.is_finite() || *x < 0.0)
                || paint.glow_min.iter().zip(paint.glow_max).any(|(a, b)| !a.is_finite() || !b.is_finite() || *a > b))
        {
            bail!("invalid vertex-painted surface profile");
        }
        if self.paint.as_ref().is_some_and(|paint| !paint.valid()) {
            bail!("invalid authored surface paint");
        }
        if !self.tint.iter().all(|x| x.is_finite() && *x >= 0.0) {
            bail!("invalid surface tint");
        }
        for tri in &self.triangles {
            if tri.colour.is_some() != self.vertex_paint.is_some()
                || tri.colour.is_some_and(|c| {
                    c.iter().any(|v| v[3] != 0.0 || v[..3].iter().any(|x| !x.is_finite() || !(0.0..=1.0).contains(x)))
                })
            {
                bail!("invalid authored surface colours");
            }
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

    /// Every triangle must own its footprint or leave it to the ground: it fails when every point sampled on it lies
    /// within [`CLEARANCE_M`] of `ground`, the drawn ground alone. A triangle where the surface crosses the ground
    /// passes, since part of it lies clear of the ground, above or below.
    pub fn check_owned(&self, ground: &Surface) -> Result<()> {
        let mut flat = 0;
        let mut first = None;
        for triangle in &self.triangles {
            let xyz = triangle.xyz.map(DVec3::from_array);
            let (mut sampled, mut near) = (0, 0);
            for i in 0..=OWNED_STEPS {
                for j in 0..=OWNED_STEPS - i {
                    let k = OWNED_STEPS - i - j;
                    let p = (xyz[0] * i as f64 + xyz[1] * j as f64 + xyz[2] * k as f64) / OWNED_STEPS as f64;
                    if let Some(height) = ground.ground_height(p.truncate()) {
                        sampled += 1;
                        near += usize::from((p.z - height).abs() < CLEARANCE_M);
                    }
                }
            }
            if sampled > 0 && near == sampled {
                flat += 1;
                first.get_or_insert((xyz[0] + xyz[1] + xyz[2]) / 3.0);
            }
        }
        if let Some(at) = first {
            bail!(
                "{}: {flat} triangles lie within {CLEARANCE_M} m of the ground over their whole area, the first at \
                 ({:.1}, {:.1}): the surface and the ground draw the same pixels",
                self.name,
                at.x,
                at.y
            );
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
                    if let Some(c) = source.colour {
                        let encode =
                            |x: f64| if x <= 0.0031308 { 12.92 * x } else { 1.055 * x.powf(1.0 / 2.4) - 0.055 };
                        let decode = |x: f64| if x <= 0.04045 { x / 12.92 } else { ((x + 0.055) / 1.055).powf(2.4) };
                        let mut colour = [0.0_f32; 4];
                        for i in 0..3 {
                            colour[i] =
                                decode(w.x * encode(c[0][i]) + w.y * encode(c[1][i]) + w.z * encode(c[2][i])) as f32;
                        }
                        mesh.colours.push(colour);
                    }
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
            texture: Some("road"),
            tint: [1.0; 3],
            paint: None,
            vertex_paint: None,
            triangles: vec![Triangle {
                xyz: [[0.0, 0.0, -1.0], [2.0, 0.0, 1.0], [0.0, 2.0, -1.0]],
                uv: [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]],
                normal: [[0.0, 0.0, 1.0], [0.02, 0.0, 1.0], [0.0, 0.02, 1.0]],
                colour: None,
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
    fn painted_clipping_preserves_encoded_colour_interpolation() {
        let mut surface = source();
        surface.texture = None;
        surface.vertex_paint = Some(VertexPaint {
            fill: 0.06,
            glow: 0.8,
            glow_min: [0.8, 0.35, 0.0],
            glow_max: [1.0, 0.72, 0.3],
            haze_start_m: 30.0,
            haze_length_m: 9000.0,
            haze_colour: [0.0932, 0.2301, 0.5328],
        });
        surface.triangles[0].colour = Some([[0.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0]]);
        surface.validate().unwrap();
        let mesh = surface.mesh(DVec2::ZERO, DVec2::new(1.0, 2.0)).unwrap();
        let index = mesh.positions.iter().position(|v| v[0] == 1.0 && v[2] == 0.0).unwrap();
        // Halfway in the original encoded colour is about 0.214 linear, not 0.5 linear.
        assert!((mesh.colours[index][0] - 0.21404114).abs() < 1e-6);
        assert_eq!(mesh.colours[index][3], 0.0);
    }
    #[test]
    fn a_triangle_on_the_ground_fails_and_a_crossing_or_a_clear_one_passes() {
        let ground = Mesh {
            positions: vec![[-1.0, 0.0, 1.0], [3.0, 0.0, 1.0], [-1.0, 0.0, -3.0], [3.0, 0.0, -3.0]],
            indices: vec![0, 1, 2, 2, 1, 3],
            ..Default::default()
        };
        let ground = Surface::new(&ground);
        let at = |z: [f64; 3]| {
            let mut surface = source();
            surface.triangles[0].xyz = [[0.0, 0.0, z[0]], [2.0, 0.0, z[1]], [0.0, 2.0, z[2]]];
            surface.check_owned(&ground)
        };
        assert!(at([0.01, 0.005, 0.01]).is_err());
        assert!(at([-0.01, 0.0, -0.005]).is_err());
        assert!(at([-1.0, 1.0, -1.0]).is_ok());
        assert!(at([0.05, 0.05, 0.05]).is_ok());
        assert!(at([-0.05, -0.05, -0.05]).is_ok());
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
