//! Declared planar surfaces that own their footprints above the ground.

use anyhow::{Result, bail};
use glam::{DVec2, DVec3};

use super::game;
use super::overlay::Overlay;
use super::surface::{Surface, cut, weights};
use crate::glb::Mesh;

/// A planar surface, in map coordinates. Triangles share one height and carry their own texture coordinates.
pub struct Raised {
    pub name: String,
    pub texture: String,
    pub height: f64,
    /// Minimum separation from the drawn ground, in metres.
    pub clearance: f64,
    pub triangles: Vec<[(DVec2, DVec2); 3]>,
}

impl Raised {
    /// Whether this footprint owns a point. Edges belong to the raised surface too.
    fn contains(&self, p: DVec2) -> bool {
        self.triangles
            .iter()
            .any(|triangle| weights(triangle.map(|(p, _)| p), p).is_some_and(|w| w.min_element() >= -1e-10))
    }

    /// Cuts the surface against each drawn ground triangle, checking clearance at every intersection vertex.
    /// Both surfaces are planar on each intersection, so these vertices bound clearance everywhere in it.
    pub fn mesh(&self, drawn: &Surface, require_coverage: bool) -> Result<Mesh> {
        let mut mesh = Mesh::default();
        for triangle in &self.triangles {
            let mut covered = 0.0;
            let outline = triangle.map(|(p, _)| p);
            for under in drawn.under(outline) {
                let flat = under.map(DVec3::truncate);
                let piece = cut(outline.to_vec(), flat);
                if piece.len() < 3 {
                    continue;
                }
                covered += area(&piece);
                let first = mesh.positions.len() as u32;
                for p in piece {
                    let g = weights(flat, p).expect("ground triangle has area");
                    let z = g.x * under[0].z + g.y * under[1].z + g.z * under[2].z;
                    if self.height - z < self.clearance - 1e-6 {
                        bail!(
                            "{} is {:.3} m above ground at {p}, below its {:.3} m clearance",
                            self.name,
                            self.height - z,
                            self.clearance
                        );
                    }
                    let w = weights(outline, p).expect("raised triangle has area");
                    let uv = w.x * triangle[0].1 + w.y * triangle[1].1 + w.z * triangle[2].1;
                    mesh.positions.push(game(p.extend(self.height)).as_vec3().to_array());
                    mesh.normals.push(game(DVec3::Z).as_vec3().to_array());
                    mesh.uvs.push(uv.as_vec2().to_array());
                }
                let count = mesh.positions.len() as u32 - first;
                for n in 1..count - 1 {
                    mesh.indices.extend([first, first + n, first + n + 1]);
                }
            }
            if require_coverage && (covered - area(&outline)).abs() > 1e-5 * area(&outline).max(1.0) {
                bail!("{} runs off the drawn ground", self.name);
            }
        }
        Ok(mesh)
    }
}

fn area(polygon: &[DVec2]) -> f64 {
    (1..polygon.len().saturating_sub(1))
        .map(|i| (polygon[i] - polygon[0]).perp_dot(polygon[i + 1] - polygon[0]))
        .sum::<f64>()
        .abs()
        * 0.5
}

/// Select the declared owner first, then the caller's ground query. Never select by height.
pub fn height(raised: &[Raised], p: DVec2, ground: impl FnOnce(DVec2) -> Option<f64>) -> Option<f64> {
    raised.iter().find(|surface| surface.contains(p)).map(|surface| surface.height).or_else(|| ground(p))
}

/// Refuse invalid or overlapping ownership, including overlapping draped overlays.
pub fn check(raised: &[Raised], overlays: &[Overlay]) -> Result<()> {
    for (i, surface) in raised.iter().enumerate() {
        if !surface.height.is_finite()
            || !surface.clearance.is_finite()
            || surface.clearance <= 0.0
            || surface.triangles.is_empty()
        {
            bail!("{} has an invalid height, clearance or footprint", surface.name);
        }
        for (j, triangle) in surface.triangles.iter().enumerate() {
            let outline = triangle.map(|(p, uv)| (p, uv));
            if outline.iter().any(|(p, uv)| !p.is_finite() || !uv.is_finite())
                || weights(outline.map(|(p, _)| p), DVec2::ZERO).is_none()
            {
                bail!("{} has an invalid triangle", surface.name);
            }
            let a = outline.map(|(p, _)| p);
            if (a[1] - a[0]).perp_dot(a[2] - a[0]) <= 0.0 {
                bail!("{} has a reversed triangle", surface.name);
            }
            for other in surface
                .triangles
                .iter()
                .skip(j + 1)
                .chain(raised.iter().skip(i + 1).flat_map(|s| &s.triangles))
                .chain(overlays.iter().flat_map(|o| &o.triangles))
            {
                if !cut(a.to_vec(), other.map(|(p, _)| p)).is_empty() {
                    bail!("{} overlaps another surface", surface.name);
                }
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::world::{Detail, Tile, ground::Ground, scenery::TileScenery};

    fn square() -> Raised {
        let p = |x, y| (DVec2::new(x, y), DVec2::new(x, y) / 6.0);
        Raised {
            name: "paving".into(),
            texture: "earth".into(),
            height: 3.0,
            clearance: 0.1,
            triangles: vec![[p(3.0, 2.0), p(7.0, 2.0), p(7.0, 6.0)], [p(3.0, 2.0), p(7.0, 6.0), p(3.0, 6.0)]],
        }
    }

    #[test]
    fn owner_clearance_and_both_tile_details() {
        let ground = Ground::page(8, 1.0, |i, j| (i + j) as f32 * 0.05);
        let raised = [square()];
        check(&raised, &[]).unwrap();
        assert_eq!(height(&raised, DVec2::new(4.0, 4.0), |_| Some(100.0)), Some(3.0));
        assert_eq!(height(&raised, DVec2::new(2.0, 4.0), |_| Some(1.0)), Some(1.0));
        for detail in [Detail::Full, Detail::Middle] {
            let mut total_area = 0.0;
            for columns in [(0, 4), (4, 8)] {
                let tile = Tile { columns, rows: (0, 8) };
                let drawn = Surface::new(&tile.ground(&ground, detail, 0, 1.0));
                let mesh = raised[0].mesh(&drawn, false).unwrap();
                for triangle in Surface::new(&mesh).triangles {
                    assert!(triangle.iter().all(|p| (p.z - 3.0).abs() < 1e-6));
                    total_area += area(&triangle.map(DVec3::truncate));
                }
            }
            assert!((total_area - 16.0).abs() < 1e-5);
        }
        let whole = Surface::new(&Tile { columns: (0, 8), rows: (0, 8) }.ground(&ground, Detail::Full, 0, 1.0));
        raised[0].mesh(&whole, true).unwrap();
        let mut too_low = square();
        too_low.height = 0.5;
        assert!(too_low.mesh(&whole, true).is_err());
        let partial = Surface::new(&Tile { columns: (0, 4), rows: (0, 8) }.ground(&ground, Detail::Full, 0, 1.0));
        assert!(raised[0].mesh(&partial, true).is_err());
    }

    #[test]
    fn coarse_ground_cannot_poke_through_a_surface_clear_of_full_ground() {
        let ground = Ground::page(8, 1.0, |i, j| if i == 0 && j == 0 { 10.0 } else { 0.0 });
        let tile = Tile { columns: (0, 8), rows: (0, 8) };
        let p = |x, y| (DVec2::new(x, y), DVec2::ZERO);
        let surface = Raised {
            name: "paving".into(),
            texture: "earth".into(),
            height: 1.0,
            clearance: 0.1,
            triangles: vec![[p(1.2, 1.2), p(1.7, 1.2), p(1.7, 1.7)], [p(1.2, 1.2), p(1.7, 1.7), p(1.2, 1.7)]],
        };
        let full = Surface::new(&tile.ground(&ground, Detail::Full, 0, 1.0));
        let middle = Surface::new(&tile.ground(&ground, Detail::Middle, 0, 1.0));
        assert!(surface.mesh(&full, true).is_ok());
        assert!(surface.mesh(&middle, true).is_err());
    }

    #[test]
    fn adjacent_tiles_share_the_entire_raised_edge_at_both_details() {
        let ground = Ground::page(8, 1.0, |i, j| (i + j) as f32 * 0.05);
        let edge = |columns, detail| {
            let tile = Tile { columns, rows: (0, 8) };
            let drawn = Surface::new(&tile.ground(&ground, detail, 0, 1.0));
            let mesh = square().mesh(&drawn, false).unwrap();
            let mut edges = Vec::new();
            for triangle in mesh.indices.chunks(3) {
                for k in 0..3 {
                    let [a, b] = [triangle[k], triangle[(k + 1) % 3]].map(|v| mesh.positions[v as usize]);
                    if a[0] == 4.0 && b[0] == 4.0 && a != b {
                        let mut pair = [a, b].map(|p| p.map(f32::to_bits));
                        pair.sort();
                        edges.push(pair);
                    }
                }
            }
            edges.sort();
            edges.dedup();
            edges
        };
        let expected = edge((0, 4), Detail::Full);
        assert!(!expected.is_empty());
        for detail in [Detail::Full, Detail::Middle] {
            assert_eq!(edge((0, 4), detail), expected);
            assert_eq!(edge((4, 8), detail), expected);
        }
    }

    #[test]
    fn overlapping_owners_are_rejected_and_checksums_stay_local() {
        assert!(check(&[square(), square()], &[]).is_err());
        let overlay = Overlay { name: "path".into(), texture: "earth".into(), triangles: square().triangles };
        assert!(check(&[square()], &[overlay]).is_err());
        let mut reversed = square();
        reversed.triangles[0].swap(0, 1);
        assert!(check(&[reversed], &[]).is_err());
        let ground = Ground::page(16, 1.0, |_, _| 0.0);
        let near = Tile { columns: (0, 8), rows: (0, 8) };
        let far = Tile { columns: (8, 16), rows: (8, 16) };
        let scenery = TileScenery::default();
        let checksum = |tile: &Tile, surfaces: &[Raised]| tile.checksum(&[], &[], &ground, &[], surfaces, &scenery);
        assert_ne!(checksum(&near, &[]), checksum(&near, &[square()]));
        assert_eq!(checksum(&far, &[]), checksum(&far, &[square()]));
    }
}
