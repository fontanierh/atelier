//! Declared planar surfaces that own their footprints above the ground.

use anyhow::{Result, bail};
use glam::{DVec2, DVec3};
use serde::Serialize;
use std::collections::BTreeSet;

use super::game;
use super::overlay::Overlay;
use super::surface::{Surface, cut, weights};
use crate::glb::Mesh;

/// The haze response of a textured surface, stored with its tile node.
#[derive(Clone, Serialize)]
pub struct SurfacePaint {
    pub haze_start_m: f32,
    pub haze_length_m: f32,
    pub haze_colour: [f32; 3],
}

impl SurfacePaint {
    fn valid(&self) -> bool {
        self.haze_start_m.is_finite()
            && self.haze_start_m >= 0.0
            && self.haze_length_m.is_finite()
            && self.haze_length_m > 0.0
            && self.haze_colour.iter().all(|v| v.is_finite() && *v >= 0.0)
    }
}

/// A planar surface, in map coordinates. Triangles share one height and carry their own texture coordinates.
/// The declaring region must supply and verify any enclosing source geometry needed to keep the underside out of
/// reachable camera views; the surface alone is only a one-sided top.
pub struct Raised {
    pub name: String,
    pub texture: String,
    /// Whether footsteps use the ground sound, rather than the built-surface sound.
    pub ground: bool,
    pub paint: Option<SurfacePaint>,
    pub height: f64,
    /// Minimum separation from the drawn ground, in metres.
    pub clearance: f64,
    pub triangles: Vec<[(DVec2, DVec2); 3]>,
}

/// Map coordinates as stored in the exported 32-bit mesh.
pub fn stored(p: DVec2) -> DVec2 {
    p.as_vec2().as_dvec2()
}

/// @cc [owner:fontanierh,label:correctness] raised-owner-matches-stored-surface
/// Before querying, `check` MUST reject invalid, overlapping or conflicting footprints at stored mesh precision;
/// export MUST verify each drawn ground stays below its owner by the declared clearance in both tile details.
/// Select the declared owner first, then the caller's ground query. Never select by height.
/// Stored tile triangles used to select the same owner as the rendered geometry.
pub struct Prepared<'a> {
    raised: &'a [Raised],
    south_west: DVec2,
    tile_m: f64,
    tiles: BTreeSet<(usize, usize)>,
    full: Vec<Vec<((usize, usize), Surface)>>,
    middle: Vec<Vec<((usize, usize), Surface)>>,
}

impl<'a> Prepared<'a> {
    pub fn new(raised: &'a [Raised], south_west: DVec2, tile_m: f64) -> Self {
        Self {
            raised,
            south_west,
            tile_m,
            tiles: BTreeSet::new(),
            full: (0..raised.len()).map(|_| Vec::new()).collect(),
            middle: (0..raised.len()).map(|_| Vec::new()).collect(),
        }
    }

    pub fn add_tile(&mut self, tile: (usize, usize), drawn: &Surface, middle: bool) -> Result<()> {
        self.tiles.insert(tile);
        let target = if middle { &mut self.middle } else { &mut self.full };
        for (surface, prepared) in self.raised.iter().zip(target) {
            let mesh = surface.mesh(drawn, false)?;
            if !mesh.indices.is_empty() {
                prepared.push((tile, Surface::new(&mesh)));
            }
        }
        Ok(())
    }

    fn tile(&self, p: DVec2) -> (usize, usize) {
        let k = ((p - self.south_west) / self.tile_m).floor();
        (k.x as usize, k.y as usize)
    }

    fn owner_at(&self, p: DVec2, middle: bool, id: (usize, usize)) -> Option<f64> {
        let triangles = if middle { &self.middle } else { &self.full };
        self.raised.iter().zip(triangles).find_map(|(raised, tiles)| {
            tiles
                .iter()
                .any(|(tile_id, tile)| *tile_id == id && tile.contains_exact(p))
                .then_some(raised.height as f32 as f64)
        })
    }

    fn owner(&self, p: DVec2, middle: bool) -> Option<f64> {
        self.owner_at(p, middle, self.tile(p))
    }

    pub fn height(&self, p: DVec2, ground: impl FnOnce(DVec2) -> Option<f64>) -> Option<f64> {
        self.owner(p, false).or_else(|| ground(p))
    }

    /// Position used by emitted f32 geometry; keep old coordinates when no raised surfaces exist.
    pub fn emitted_at(&self, p: DVec2) -> DVec2 {
        if self.raised.is_empty() { p } else { stored(p) }
    }

    pub fn has_surfaces(&self) -> bool {
        !self.raised.is_empty()
    }

    pub fn emitted_point(&self, p: DVec3) -> DVec3 {
        if self.raised.is_empty() { p } else { p.as_vec3().as_dvec3() }
    }

    pub fn check_point(&self, p: DVec2) -> Result<()> {
        let (column, row) = self.tile(p);
        for dx in -1_isize..=1 {
            for dy in -1_isize..=1 {
                if dx == 0 && dy == 0 {
                    continue;
                }
                let (Some(x), Some(y)) = (column.checked_add_signed(dx), row.checked_add_signed(dy)) else {
                    continue;
                };
                let adjacent = (x, y);
                if !self.tiles.contains(&adjacent) {
                    continue;
                }
                for middle in [false, true] {
                    let surfaces = if middle { &self.middle } else { &self.full };
                    let owner = self.owner(p, middle);
                    if self.raised.iter().zip(surfaces).any(|(raised, tiles)| {
                        tiles.iter().any(|(id, tile)| *id == adjacent && tile.contains_exact(p))
                            && Some(raised.height as f32 as f64) != owner
                    }) {
                        bail!("raised ownership differs between adjacent tiles at {p}");
                    }
                }
            }
        }
        for tiles in [&self.full, &self.middle] {
            let mut heights = self.raised.iter().zip(tiles).filter_map(|(raised, tiles)| {
                tiles
                    .iter()
                    .any(|(id, tile)| *id == self.tile(p) && tile.contains_exact(p))
                    .then_some(raised.height as f32)
            });
            if let Some(first) = heights.next()
                && heights.any(|height| height != first)
            {
                bail!("stored raised surfaces disagree at {p}");
            }
        }
        if self.owner(p, false) != self.owner(p, true) {
            bail!("raised ownership differs between tile details at {p}");
        }
        Ok(())
    }
}

impl Raised {
    /// The runtime identifies ground and built surfaces from the tile mesh name.
    pub fn node_name(&self) -> String {
        if self.ground { "ground".into() } else { format!("built {} built", self.name) }
    }

    /// Whether this authored footprint owns a point, before it is clipped for export.
    #[cfg(test)]
    fn contains(&self, p: DVec2) -> bool {
        self.triangles
            .iter()
            .any(|triangle| weights(triangle.map(|(p, _)| stored(p)), p).is_some_and(|w| w.min_element() >= -1e-10))
    }

    /// Cuts the surface against each drawn ground triangle, checking clearance at every intersection vertex.
    /// Both surfaces are planar on each intersection, so these vertices bound clearance everywhere in it.
    pub fn mesh(&self, drawn: &Surface, require_coverage: bool) -> Result<Mesh> {
        let mut mesh = Mesh::default();
        let height = self.height as f32 as f64;
        for triangle in &self.triangles {
            let mut covered = 0.0;
            let outline = triangle.map(|(p, _)| stored(p));
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
                    if height - z < self.clearance - 1e-6 {
                        bail!(
                            "{} is {:.3} m above ground at {p}, below its {:.3} m clearance",
                            self.name,
                            height - z,
                            self.clearance
                        );
                    }
                    let w = weights(outline, p).expect("raised triangle has area");
                    let uv = w.x * triangle[0].1 + w.y * triangle[1].1 + w.z * triangle[2].1;
                    if !stored(uv).is_finite() {
                        bail!("{} produces an unrepresentable texture coordinate", self.name);
                    }
                    mesh.positions.push(game(p.extend(height)).as_vec3().to_array());
                    mesh.normals.push(game(DVec3::Z).as_vec3().to_array());
                    mesh.uvs.push(uv.as_vec2().to_array());
                }
                let count = mesh.positions.len() as u32 - first;
                for n in 1..count - 1 {
                    mesh.indices.extend([first, first + n, first + n + 1]);
                }
            }
            if require_coverage && (covered - area(&outline)).abs() > 1e-5 * area(&outline) {
                bail!("{} runs off the drawn ground", self.name);
            }
        }
        check_stored_clearance(drawn, &mesh, self.clearance, &self.name)?;
        Ok(mesh)
    }
}

/// Recheck after vertex rounding: clipping vertices can move across ground triangle edges in f32 storage.
fn check_stored_clearance(drawn: &Surface, mesh: &Mesh, clearance: f64, name: &str) -> Result<()> {
    for top in Surface::new(mesh).triangles {
        let outline = top.map(DVec3::truncate);
        for ground in drawn.under(outline) {
            let flat = ground.map(DVec3::truncate);
            for p in cut(outline.to_vec(), flat) {
                let w = weights(flat, p).expect("ground triangle has area");
                let z = w.x * ground[0].z + w.y * ground[1].z + w.z * ground[2].z;
                if top[0].z - z < clearance - 1e-6 {
                    bail!(
                        "{name} is {:.3} m above ground at stored point {p}, below its {clearance:.3} m clearance",
                        top[0].z - z
                    );
                }
            }
        }
    }
    Ok(())
}

fn area(polygon: &[DVec2]) -> f64 {
    (1..polygon.len().saturating_sub(1))
        .map(|i| (polygon[i] - polygon[0]).perp_dot(polygon[i + 1] - polygon[0]))
        .sum::<f64>()
        .abs()
        * 0.5
}

#[cfg(test)]
fn height(raised: &[Raised], p: DVec2, ground: impl FnOnce(DVec2) -> Option<f64>) -> Option<f64> {
    raised.iter().find(|surface| surface.contains(p)).map(|surface| surface.height as f32 as f64).or_else(|| ground(p))
}

/// Whether closed triangle boundaries meet, including a shared corner or collinear edge.
fn boundaries_touch(a: [DVec2; 3], b: [DVec2; 3]) -> bool {
    fn segment(a: DVec2, b: DVec2, c: DVec2, d: DVec2) -> bool {
        const EPS: f64 = 1e-9;
        let cross = |p: DVec2, q: DVec2, r: DVec2| (q - p).perp_dot(r - p);
        let on = |p: DVec2, q: DVec2, r: DVec2| {
            cross(p, q, r).abs() <= EPS
                && r.cmpge(p.min(q) - DVec2::splat(EPS)).all()
                && r.cmple(p.max(q) + DVec2::splat(EPS)).all()
        };
        let (ab_c, ab_d, cd_a, cd_b) = (cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b));
        (ab_c * ab_d < 0.0 && cd_a * cd_b < 0.0) || on(a, b, c) || on(a, b, d) || on(c, d, a) || on(c, d, b)
    }
    (0..3).any(|i| (0..3).any(|j| segment(a[i], a[(i + 1) % 3], b[j], b[(j + 1) % 3])))
}

/// Refuse invalid or overlapping ownership, including overlapping draped overlays.
pub fn check(raised: &[Raised], overlays: &[Overlay]) -> Result<()> {
    for (i, surface) in raised.iter().enumerate() {
        if !surface.height.is_finite()
            || !(surface.height as f32).is_finite()
            || !surface.clearance.is_finite()
            || surface.clearance <= 0.0
            || surface.triangles.is_empty()
            || surface.paint.as_ref().is_some_and(|paint| !paint.valid())
        {
            bail!("{} has an invalid height, clearance or footprint", surface.name);
        }
        for other in raised.iter().skip(i + 1) {
            if surface.height as f32 != other.height as f32
                && surface.triangles.iter().any(|a| {
                    other
                        .triangles
                        .iter()
                        .any(|b| boundaries_touch(a.map(|(p, _)| stored(p)), b.map(|(p, _)| stored(p))))
                })
            {
                bail!("{} meets another raised surface at a different height", surface.name);
            }
        }
        for overlay in overlays {
            if surface.triangles.iter().any(|a| {
                overlay.triangles.iter().any(|b| boundaries_touch(a.map(|(p, _)| stored(p)), b.map(|(p, _)| stored(p))))
            }) {
                bail!("{} touches an overlay without a shared seam", surface.name);
            }
        }
        for (j, triangle) in surface.triangles.iter().enumerate() {
            let outline = *triangle;
            if outline.iter().any(|(p, uv)| !stored(*p).is_finite() || !stored(*uv).is_finite())
                || weights(outline.map(|(p, _)| stored(p)), DVec2::ZERO).is_none()
            {
                bail!("{} has an invalid triangle", surface.name);
            }
            let a = outline.map(|(p, _)| stored(p));
            if (a[1] - a[0]).perp_dot(a[2] - a[0]) <= 1e-8 {
                bail!("{} has a reversed or too-small triangle", surface.name);
            }
            for other in surface
                .triangles
                .iter()
                .skip(j + 1)
                .chain(raised.iter().skip(i + 1).flat_map(|s| &s.triangles))
                .chain(overlays.iter().flat_map(|o| &o.triangles))
            {
                if !cut(a.to_vec(), other.map(|(p, _)| stored(p))).is_empty() {
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
            ground: true,
            paint: None,
            height: 3.0,
            clearance: 0.1,
            triangles: vec![[p(3.0, 2.0), p(7.0, 2.0), p(7.0, 6.0)], [p(3.0, 2.0), p(7.0, 6.0), p(3.0, 6.0)]],
        }
    }

    #[test]
    fn owner_follows_the_stored_clipped_edge() {
        let mut ground = Mesh::default();
        for y in 0..=5 {
            for x in 199..=204 {
                ground.positions.push(game(DVec3::new(x as f64, y as f64, 0.0)).as_vec3().to_array());
            }
        }
        for y in 0..5_u32 {
            for x in 0..5_u32 {
                let a = y * 6 + x;
                ground.indices.extend([a, a + 1, a + 7, a, a + 7, a + 6]);
            }
        }
        let drawn = Surface::new(&ground);
        let p = |x, y| (DVec2::new(x, y), DVec2::ZERO);
        let raised = [Raised {
            name: "edge".into(),
            texture: "earth".into(),
            ground: true,
            paint: None,
            height: 3.0,
            clearance: 0.1,
            triangles: vec![[p(199.1, 0.1), p(203.2, 2.3), p(199.2, 4.7)]],
        }];
        let mut prepared = Prepared::new(&raised, DVec2::new(199.0, 0.0), 5.0);
        prepared.add_tile((0, 0), &drawn, false).unwrap();
        prepared.add_tile((0, 0), &drawn, true).unwrap();
        let edge = DVec2::new(200.0, 0.5829246044158936);
        assert!(!raised[0].contains(edge));
        assert!(prepared.full[0].iter().flat_map(|(_, s)| &s.triangles).flatten().any(|p| p.truncate() == edge));
        assert_eq!(prepared.height(edge, |_| Some(0.0)), Some(3.0));
        prepared.check_point(edge).unwrap();
        assert_eq!(prepared.height(DVec2::new(200.0, 0.5828), |_| Some(0.0)), Some(0.0));
        let mut mismatched = Prepared::new(&raised, DVec2::new(199.0, 0.0), 5.0);
        mismatched.add_tile((0, 0), &drawn, false).unwrap();
        assert!(mismatched.check_point(edge).is_err());
    }

    #[test]
    fn owner_uses_the_half_open_streaming_tile_at_a_boundary() {
        let ground = Ground::page(2, 1.0, |_, _| 0.0);
        let p = |x, y| (DVec2::new(x, y), DVec2::ZERO);
        let raised = [Raised {
            name: "edge".into(),
            texture: "earth".into(),
            ground: true,
            paint: None,
            height: 3.0,
            clearance: 0.1,
            triangles: vec![[p(0.2, 0.1), p(1.0, 0.1), p(1.0, 0.9)], [p(0.2, 0.1), p(1.0, 0.9), p(0.2, 0.9)]],
        }];
        let mut prepared = Prepared::new(&raised, DVec2::ZERO, 1.0);
        for x in 0..2 {
            let drawn = Surface::new(&Tile { columns: (x, x + 1), rows: (0, 1) }.ground(&ground, Detail::Full, 0, 1.0));
            prepared.add_tile((x, 0), &drawn, false).unwrap();
            prepared.add_tile((x, 0), &drawn, true).unwrap();
        }
        assert_eq!(prepared.height(DVec2::new(0.9, 0.5), |_| Some(0.0)), Some(3.0));
        let edge = DVec2::new(1.0, 0.5);
        assert_eq!(prepared.height(edge, |_| Some(0.0)), Some(0.0));
        assert!(prepared.check_point(edge).is_err());
        let mut crossing = square();
        let p = |x, y| (DVec2::new(x, y), DVec2::ZERO);
        crossing.triangles = vec![[p(0.2, 0.1), p(1.8, 0.1), p(1.8, 0.9)], [p(0.2, 0.1), p(1.8, 0.9), p(0.2, 0.9)]];
        let raised = [crossing];
        let mut prepared = Prepared::new(&raised, DVec2::ZERO, 1.0);
        for x in 0..2 {
            let drawn = Surface::new(&Tile { columns: (x, x + 1), rows: (0, 1) }.ground(&ground, Detail::Full, 0, 1.0));
            prepared.add_tile((x, 0), &drawn, false).unwrap();
            prepared.add_tile((x, 0), &drawn, true).unwrap();
        }
        assert_eq!(prepared.height(edge, |_| Some(0.0)), Some(3.0));
        prepared.check_point(edge).unwrap();
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
            ground: true,
            paint: None,
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
    fn clearance_is_checked_again_after_clipped_vertices_are_stored() {
        let ground = Mesh {
            positions: [DVec3::new(199.0, 0.0, 0.0), DVec3::new(201.0, 0.0, 2.0), DVec3::new(199.0, 2.0, 0.0)]
                .map(|p| game(p).as_vec3().to_array())
                .to_vec(),
            indices: vec![0, 1, 2],
            ..Default::default()
        };
        let drawn = Surface::new(&ground);
        let x = 200.0000078;
        let clearance = 0.999989;
        assert!(2.0 - (x - 199.0) >= clearance);
        let top = Mesh {
            positions: [DVec3::new(x, 0.1, 2.0), DVec3::new(x, 0.2, 2.0), DVec3::new(199.9, 0.1, 2.0)]
                .map(|p| game(p).as_vec3().to_array())
                .to_vec(),
            indices: vec![0, 1, 2],
            ..Default::default()
        };
        assert!(check_stored_clearance(&drawn, &top, clearance, "paving").is_err());
    }

    #[test]
    fn storage_precision_controls_contacts_and_ownership() {
        let p = |x, y| (DVec2::new(x, y), DVec2::ZERO);
        let first = Raised {
            name: "first".into(),
            texture: "earth".into(),
            ground: true,
            paint: None,
            height: 3.0,
            clearance: 0.1,
            triangles: vec![[p(199.0, 0.0), p(200.0, 0.0), p(200.0, 1.0)]],
        };
        let second = Raised {
            name: "second".into(),
            texture: "earth".into(),
            ground: true,
            paint: None,
            height: 4.0,
            clearance: 0.1,
            triangles: vec![[p(200.000001, 0.0), p(201.0, 0.0), p(200.000001, 1.0)]],
        };
        assert_eq!(stored(DVec2::new(200.000001, 0.0)).x, 200.0);
        assert!(check(&[first, second], &[]).is_err());
        let shifted = Raised {
            name: "shifted".into(),
            texture: "earth".into(),
            ground: true,
            paint: None,
            height: 3.0,
            clearance: 0.1,
            triangles: vec![[p(200.000001, 0.0), p(201.0, 0.0), p(200.000001, 1.0)]],
        };
        assert_eq!(height(&[shifted], DVec2::new(200.0, 0.5), |_| None), Some(3.0));
    }

    #[test]
    fn rejects_values_that_cannot_be_stored_and_collapsed_triangles() {
        let mut surface = square();
        surface.triangles[0][0].1.x = f64::MAX;
        assert!(check(&[surface], &[]).is_err());
        let mut surface = square();
        surface.triangles[0][0].0.x = f64::MAX;
        assert!(check(&[surface], &[]).is_err());
        let p = |x, y| (DVec2::new(x, y), DVec2::ZERO);
        let mut surface = square();
        surface.triangles = vec![[p(200.0, 0.0), p(200.000001, 0.0), p(200.0, 1.0)]];
        assert!(check(&[surface], &[]).is_err());
        let mut tiny = square();
        tiny.triangles = vec![[p(0.0, 0.0), p(0.00005, 0.0), p(0.0, 0.00005)]];
        assert!(check(&[tiny], &[]).is_err());
    }

    #[test]
    fn overlapping_owners_are_rejected_and_checksums_stay_local() {
        assert!(check(&[square(), square()], &[]).is_err());
        let mut adjoining = square();
        for triangle in &mut adjoining.triangles {
            for (p, _) in triangle {
                p.x += 4.0;
            }
        }
        let first = [square(), adjoining];
        assert!(check(&first, &[]).is_ok());
        let mut adjoining = square();
        for triangle in &mut adjoining.triangles {
            for (p, _) in triangle {
                p.x += 4.0;
            }
        }
        let reversed = [adjoining, square()];
        let seam = DVec2::new(7.0, 3.0);
        assert_eq!(height(&first, seam, |_| None), height(&reversed, seam, |_| None));
        let mut adjoining = square();
        adjoining.height += 1.0;
        for triangle in &mut adjoining.triangles {
            for (p, _) in triangle {
                p.x += 4.0;
            }
        }
        assert!(check(&[square(), adjoining], &[]).is_err());
        let mut adjoining = square();
        adjoining.height += 1.0;
        for triangle in &mut adjoining.triangles {
            for (p, _) in triangle {
                p.x += 4.0;
            }
        }
        assert!(check(&[adjoining, square()], &[]).is_err());
        let mut touch = square();
        for triangle in &mut touch.triangles {
            for (p, _) in triangle {
                p.x += 4.0;
            }
        }
        let touching_overlay = Overlay { name: "path".into(), texture: "earth".into(), triangles: touch.triangles };
        assert!(check(&[square()], &[touching_overlay]).is_err());
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
        let mut changed = square();
        changed.height += 0.2;
        assert_ne!(checksum(&near, &[square()]), checksum(&near, &[changed]));
        let mut painted = square();
        painted.paint =
            Some(SurfacePaint { haze_start_m: 30.0, haze_length_m: 9000.0, haze_colour: [0.0932, 0.2301, 0.5328] });
        assert_ne!(checksum(&near, &[square()]), checksum(&near, &[painted]));
        let mut invalid = square();
        invalid.paint = Some(SurfacePaint { haze_start_m: 0.0, haze_length_m: 0.0, haze_colour: [0.0; 3] });
        assert!(check(&[invalid], &[]).is_err());
        let mut changed = square();
        changed.height += 0.2;
        assert_eq!(checksum(&far, &[square()]), checksum(&far, &[changed]));
        assert_eq!(square().node_name(), "ground");
        let mut built = square();
        built.ground = false;
        assert_eq!(built.node_name(), "built paving built");
        built.name = "cable road".into();
        let name = built.node_name();
        assert!(!name.starts_with("cable"));
        assert!(!name.ends_with("road"));
    }
}
