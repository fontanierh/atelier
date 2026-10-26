//! Overlays: flat shapes that regions lay over the ground, such as roads and paths.

use std::collections::HashMap;

use anyhow::{Result, bail};
use glam::{DVec2, DVec3};

use super::game;
use super::ground::Ground;
use super::surface::{Surface, cut, weights};
use crate::glb::Mesh;

/// How far an overlay sits above the ground under it.
const LIFT_M: f64 = 0.06;

/// How close an overlay may come to the ground under it before the export fails.
const CLEARANCE_M: f64 = 0.01;

/// A flat shape laid over the ground: triangles on the map, each corner with its texture position.
pub struct Overlay {
    pub name: String,
    /// The texture it shows, by its folder name under `assets/textures/`.
    pub texture: String,
    pub triangles: Vec<[(DVec2, DVec2); 3]>,
}

impl Overlay {
    /// The overlay over the ground `drawn` in one tile. Each triangle is cut along the edges of the ground triangles
    /// under it, and each cut piece lies `LIFT_M` above its ground triangle, so the overlay follows the ground exactly
    /// and stops at the tile's edge.
    pub fn mesh(&self, ground: &Ground, drawn: &Surface) -> Mesh {
        let mut mesh = Mesh::default();
        for piece in &self.triangles {
            let outline = piece.map(|(p, _)| p);
            for under in drawn.under(outline) {
                let flat = under.map(DVec3::truncate);
                let cut = cut(outline.to_vec(), flat);
                if cut.len() < 3 {
                    continue;
                }
                let first = mesh.positions.len() as u32;
                for &p in &cut {
                    let on_ground = weights(flat, p).expect("a ground triangle has area");
                    let on_overlay = weights(outline, p).expect("an overlay triangle has area");
                    let height = on_ground.x * under[0].z + on_ground.y * under[1].z + on_ground.z * under[2].z;
                    let uv = on_overlay.x * piece[0].1 + on_overlay.y * piece[1].1 + on_overlay.z * piece[2].1;
                    mesh.positions.push(game(p.extend(height + LIFT_M)).as_vec3().to_array());
                    mesh.normals.push(game(ground.normal(p)).as_vec3().to_array());
                    mesh.uvs.push(uv.as_vec2().to_array());
                }
                for n in 1..cut.len() as u32 - 1 {
                    mesh.indices.extend([first, first + n, first + n + 1]);
                }
            }
        }
        mesh
    }
}

/// The sharpest crease an overlay may have over the full-detail ground, in degrees. An overlay is flat: laid on a
/// levelled strip it creases by well under this, while one draped over a sharp cut on the 2 m grid kinks by tens of
/// degrees at every ground triangle's edge.
const CREASE_DEG: f64 = 1.5;

/// Fails if `overlay` creases by more than `CREASE_DEG` anywhere: the ground under it needs levelling.
pub fn check_smooth(overlay: &Mesh) -> Result<()> {
    let crease = crease_deg(overlay);
    if crease > CREASE_DEG {
        bail!("it creases by {crease:.1}°: level the ground under it");
    }
    Ok(())
}

/// The sharpest crease in `overlay`: the largest angle, in degrees, between two of its triangles that meet at a
/// corner. Slivers narrower than `SLIVER_M` are left out: their 32-bit corners give them no reliable slope.
pub fn crease_deg(overlay: &Mesh) -> f64 {
    const SLIVER_M: f64 = 0.05;
    let mut normals: HashMap<[i64; 3], Vec<DVec3>> = HashMap::new();
    for triangle in overlay.indices.chunks(3) {
        let [a, b, c] = [0, 1, 2].map(|k| DVec3::from(overlay.positions[triangle[k] as usize].map(f64::from)));
        let normal = (b - a).cross(c - a);
        let longest = (b - a).length().max((c - b).length()).max((a - c).length());
        if normal.length() < SLIVER_M * longest {
            continue;
        }
        for p in [a, b, c] {
            // Corners within a millimetre are one corner: pieces cut from neighbouring ground triangles compute their
            // shared corners apart.
            let key = (p * 1000.0).round().as_i64vec3().to_array();
            normals.entry(key).or_default().push(normal.normalize());
        }
    }
    let mut sharpest: f64 = 0.0;
    for around in normals.values() {
        for (n, a) in around.iter().enumerate() {
            for b in &around[n + 1..] {
                sharpest = sharpest.max(a.angle_between(*b).to_degrees());
            }
        }
    }
    sharpest
}

/// Fails if `overlay` comes closer than `CLEARANCE_M` to the ground drawn under it anywhere, checking points spread
/// over each of its triangles.
pub fn check_above(drawn: &Surface, overlay: &Mesh) -> Result<()> {
    const SPLITS: u32 = 4;
    for [a, b, c] in Surface::new(overlay).triangles {
        for s in 0..=SPLITS {
            for t in 0..=SPLITS - s {
                let p = a + (b - a) * (s as f64 / SPLITS as f64) + (c - a) * (t as f64 / SPLITS as f64);
                let Some(under) = drawn.height(p.truncate()) else {
                    bail!("it runs off the tile's ground at ({:.1}, {:.1})", p.x, p.y);
                };
                if p.z - under < CLEARANCE_M {
                    bail!("it comes within {:.3} m of the ground at ({:.1}, {:.1})", p.z - under, p.x, p.y);
                }
            }
        }
    }
    Ok(())
}
