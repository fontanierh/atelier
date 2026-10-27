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
    pub(crate) fn valid(&self) -> bool {
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
    /// Explicit source footprint owns its ground underlay.
    pub cut_ground: bool,
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
    cut_ground: [Vec<((usize, usize), Surface)>; 2],
    cut_areas: [Vec<geo::MultiPolygon<f64>>; 2],
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
            cut_ground: [Vec::new(), Vec::new()],
            cut_areas: [Vec::new(), Vec::new()],
        }
    }

    pub fn set_underlays(&mut self, unions: &[Vec<super::underlay::Underlay>; 2]) {
        self.cut_areas = std::array::from_fn(|i| unions[i].iter().map(|u| u.query.clone()).collect());
    }

    fn is_cut(&self, p: DVec2, middle: bool) -> bool {
        use geo::Intersects;
        self.cut_areas[usize::from(middle)].iter().any(|area| area.intersects(&geo::Point::new(p.x, p.y)))
    }

    pub fn touches_cut(&self, p: DVec2) -> bool {
        self.is_cut(p, false) || self.is_cut(p, true)
    }

    pub fn retained_cut_at(&self, p: DVec2, middle: bool) -> bool {
        self.is_cut(p, middle) && self.owner(p, middle).is_none()
    }

    pub fn stored_cut_height(&self, p: DVec2, middle: bool) -> Option<f64> {
        self.cut_height(p, middle)
    }

    fn cut_height(&self, p: DVec2, middle: bool) -> Option<f64> {
        let tile = self.tile(p);
        self.cut_ground[usize::from(middle)].iter().find(|(id, _)| *id == tile)?.1.height_exact(p)
    }

    #[cfg(test)]
    pub fn add_tile(&mut self, tile: (usize, usize), drawn: &Surface, middle: bool) -> Result<()> {
        self.add_tile_with_cut(tile, drawn, drawn, middle)
    }

    pub fn add_tile_with_cut(
        &mut self,
        tile: (usize, usize),
        drawn: &Surface,
        cut: &Surface,
        middle: bool,
    ) -> Result<()> {
        self.tiles.insert(tile);
        if !self.cut_areas[usize::from(middle)].is_empty() {
            self.cut_ground[usize::from(middle)].push((tile, cut.clone()));
        }
        let target = if middle { &mut self.middle } else { &mut self.full };
        for (surface, prepared) in self.raised.iter().zip(target) {
            let mesh = surface.mesh_prepared(drawn, cut, false)?;
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
        self.height_for_detail(p, false, ground)
    }

    pub fn height_for_detail(&self, p: DVec2, middle: bool, ground: impl FnOnce(DVec2) -> Option<f64>) -> Option<f64> {
        self.owner(p, middle).or_else(|| if self.is_cut(p, middle) { self.cut_height(p, middle) } else { ground(p) })
    }

    /// An explicit crossing can cover retained cut-ground outside the raised footprint. The raised owner itself
    /// still takes precedence; elsewhere, resolve the crossing over the exact terrain selected for this detail.
    pub fn height_with_crossing(
        &self,
        p: DVec2,
        middle: bool,
        ground: impl FnOnce(DVec2) -> Option<f64>,
        crossing: impl FnOnce(DVec2, Option<f64>) -> Option<f64>,
    ) -> Option<f64> {
        if let Some(owner) = self.owner(p, middle) {
            return Some(owner);
        }
        let terrain = if self.is_cut(p, middle) { self.cut_height(p, middle) } else { ground(p) };
        crossing(p, terrain)
    }

    pub fn owner_height(&self, p: DVec2) -> Option<f64> {
        self.owner(p, false)
    }

    /// Position used by emitted f32 geometry where it can touch a raised owner.
    pub fn emitted_at(&self, p: DVec2) -> DVec2 {
        if self.needs_precision(p) { stored(p) } else { p }
    }

    fn needs_precision(&self, p: DVec2) -> bool {
        let touches =
            |point: DVec2| {
                let (column, row) = self.tile(point);
                [&self.full, &self.middle].into_iter().flatten().flatten().any(|(id, tile)| {
                    id.0.abs_diff(column) <= 1 && id.1.abs_diff(row) <= 1 && tile.contains_exact(point)
                })
            };
        touches(p)
            || touches(stored(p))
            || self.is_cut(p, false)
            || self.is_cut(stored(p), false)
            || self.is_cut(p, true)
            || self.is_cut(stored(p), true)
    }

    pub fn emitted_point(&self, p: DVec3) -> DVec3 {
        if self.needs_precision(p.truncate()) { p.as_vec3().as_dvec3() } else { p }
    }

    /// Intervals split at every stored raised triangle boundary along a segment.
    pub fn segment_intervals(&self, a: DVec2, b: DVec2) -> Vec<(f64, f64)> {
        let direction = b - a;
        let length2 = direction.length_squared();
        if length2 == 0.0 {
            return Vec::new();
        }
        let mut points = Vec::new();
        let mut touches = false;
        for surface in [&self.full, &self.middle].into_iter().flatten().flatten().map(|(_, surface)| surface) {
            if surface.contains_exact(a) || surface.contains_exact(b) {
                touches = true;
            }
            for triangle in surface.under([a, b, a]) {
                let corners = triangle.map(DVec3::truncate);
                for i in 0..3 {
                    let c = corners[i];
                    let edge = corners[(i + 1) % 3] - c;
                    let denominator = direction.perp_dot(edge);
                    if denominator == 0.0 {
                        if (c - a).perp_dot(direction) == 0.0 {
                            for p in [c, c + edge] {
                                let t = (p - a).dot(direction) / length2;
                                if (0.0..=1.0).contains(&t) {
                                    points.push(t);
                                    touches = true;
                                }
                            }
                        }
                    } else {
                        let t = (c - a).perp_dot(edge) / denominator;
                        let u = (c - a).perp_dot(direction) / denominator;
                        if (0.0..=1.0).contains(&t) && (0.0..=1.0).contains(&u) {
                            points.push(t);
                            touches = true;
                        }
                    }
                }
            }
        }
        // Also split where a segment enters the cut query envelope or a stored
        // cut-ground triangle, so a narrow unsupported collar cannot be skipped.
        let mut edge_points = Vec::new();
        let mut add_edge = |c: DVec2, d: DVec2, filter: bool| {
            let edge = d - c;
            let denominator = direction.perp_dot(edge);
            if denominator == 0.0 {
                if (c - a).perp_dot(direction) == 0.0 {
                    for p in [c, d] {
                        let t = (p - a).dot(direction) / length2;
                        if (0.0..=1.0).contains(&t) && (!filter || self.is_cut(p, false) || self.is_cut(p, true)) {
                            edge_points.push(t);
                        }
                    }
                }
            } else {
                let t = (c - a).perp_dot(edge) / denominator;
                let u = (c - a).perp_dot(direction) / denominator;
                let p = a + direction * t;
                if (0.0..=1.0).contains(&t)
                    && (0.0..=1.0).contains(&u)
                    && (!filter || self.is_cut(p, false) || self.is_cut(p, true))
                {
                    edge_points.push(t);
                }
            }
        };
        for area in self.cut_areas.iter().flatten() {
            for polygon in &area.0 {
                for ring in std::iter::once(polygon.exterior()).chain(polygon.interiors()) {
                    for edge in ring.0.windows(2) {
                        add_edge(DVec2::new(edge[0].x, edge[0].y), DVec2::new(edge[1].x, edge[1].y), false);
                    }
                }
            }
        }
        for (_, surface) in self.cut_ground.iter().flatten() {
            for triangle in surface.under([a, b, a]) {
                let points = triangle.map(DVec3::truncate);
                for i in 0..3 {
                    add_edge(points[i], points[(i + 1) % 3], true);
                }
            }
        }
        if !edge_points.is_empty()
            || self.is_cut(a, false)
            || self.is_cut(b, false)
            || self.is_cut(a, true)
            || self.is_cut(b, true)
        {
            touches = true;
            points.extend(edge_points);
        }
        if !touches {
            return Vec::new();
        }
        points.extend([0.0, 1.0]);
        points.sort_by(f64::total_cmp);
        points.dedup();
        points.windows(2).map(|pair| (pair[0], pair[1])).collect()
    }

    pub fn check_point(&self, p: DVec2) -> Result<()> {
        for middle in [false, true] {
            if self.owner(p, middle).is_none() && self.is_cut(p, middle) && self.cut_height(p, middle).is_none() {
                bail!("no stored surface under point {p} after cutting the ground");
            }
        }
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
        self.mesh_inner(drawn, require_coverage, false)
    }

    pub fn mesh_prepared(&self, original: &Surface, cut: &Surface, require_coverage: bool) -> Result<Mesh> {
        if !self.cut_ground {
            return self.mesh(original, require_coverage);
        }
        let mesh = self.mesh_inner(original, require_coverage, true)?;
        check_stored_clearance(cut, &mesh, self.clearance, &self.name)?;
        Ok(mesh)
    }

    pub fn mesh_before_cut(&self, drawn: &Surface, require_coverage: bool) -> Result<Mesh> {
        self.mesh_inner(drawn, require_coverage, self.cut_ground)
    }

    fn mesh_inner(&self, drawn: &Surface, require_coverage: bool, is_cut: bool) -> Result<Mesh> {
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
                    if !is_cut && height - z < self.clearance - 1e-6 {
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
        if !is_cut {
            check_stored_clearance(drawn, &mesh, self.clearance, &self.name)?;
        }
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
            cut_ground: false,
            triangles: vec![[p(3.0, 2.0), p(7.0, 2.0), p(7.0, 6.0)], [p(3.0, 2.0), p(7.0, 6.0), p(3.0, 6.0)]],
        }
    }

    #[test]
    fn cut_collar_never_falls_back_to_the_removed_grid() {
        let mut owner = square();
        owner.cut_ground = true;
        let mut extreme = square();
        extreme.cut_ground = true;
        extreme.triangles[0][0].0.x = f32::MAX as f64;
        assert!(super::super::underlay::owner_collar(&extreme, 8.0).is_err());
        let raised = [owner];
        let ground = Ground::page(8, 1.0, |_, _| 0.0);
        let tile = Tile { columns: (0, 8), rows: (0, 8) };
        let mesh = tile.ground(&ground, Detail::Full, 0, 1.0);
        let drawn = Surface::new(&mesh);
        let top = raised[0].mesh_before_cut(&drawn, false).unwrap();
        let collar = super::super::underlay::owner_collar(&raised[0], 8.0).unwrap();
        let unions = [
            vec![super::super::underlay::union(std::slice::from_ref(&top), collar).unwrap()],
            vec![super::super::underlay::union(&[top], collar).unwrap()],
        ];
        let cut = Surface::new(&super::super::underlay::remove_covered(&mesh, &unions[0]));
        let mut prepared = Prepared::new(&raised, DVec2::ZERO, 8.0);
        prepared.set_underlays(&unions);
        prepared.add_tile_with_cut((0, 0), &drawn, &cut, false).unwrap();
        prepared.add_tile_with_cut((0, 0), &drawn, &cut, true).unwrap();
        let gap = DVec2::new(3.0 - collar * 0.5, 3.0);
        assert!(prepared.is_cut(gap, false));
        assert!(prepared.owner_height(gap).is_none());
        assert!(prepared.height(gap, |_| Some(123.0)).is_none());
        // The removed raw grid is not considered, but an explicit source crossing can cover the collar.
        assert_eq!(
            prepared.height_with_crossing(
                gap,
                false,
                |_| Some(123.0),
                |_, terrain| {
                    assert_eq!(terrain, None);
                    Some(2.0)
                }
            ),
            Some(2.0)
        );
        let inside = DVec2::new(4.0, 3.0);
        assert_eq!(prepared.height_with_crossing(inside, false, |_| Some(123.0), |_, _| Some(456.0)), Some(3.0));
        assert!(prepared.check_point(gap).is_err());
        let a = DVec2::new(3.0 - collar * 3.0, 3.0);
        let b = DVec2::new(3.0 + collar, 3.0);
        assert!(
            prepared
                .segment_intervals(a, b)
                .iter()
                .any(|&(lo, hi)| { prepared.check_point(a.lerp(b, (lo + hi) * 0.5)).is_err() })
        );
        assert_eq!(prepared.height(DVec2::new(1.0, 1.0), |_| Some(123.0)), Some(123.0));
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
            cut_ground: false,
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
            cut_ground: false,
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
            cut_ground: false,
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
            cut_ground: false,
            triangles: vec![[p(199.0, 0.0), p(200.0, 0.0), p(200.0, 1.0)]],
        };
        let second = Raised {
            name: "second".into(),
            texture: "earth".into(),
            ground: true,
            paint: None,
            height: 4.0,
            clearance: 0.1,
            cut_ground: false,
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
            cut_ground: false,
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
        let checksum =
            |tile: &Tile, surfaces: &[Raised]| tile.checksum(&[], &[], &ground, (&[], surfaces, &[]), (&scenery, &[]));
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
        let mut bordering = square();
        bordering.cut_ground = true;
        for triangle in &mut bordering.triangles {
            for (p, _) in triangle {
                p.x += 5.000002;
            }
        }
        let padded_checksum = |tile: &Tile, surfaces: &[Raised], collar| {
            tile.checksum(&[], &[], &ground, (&[], surfaces, &[]), (&scenery, &[collar]))
        };
        let surfaces = [bordering];
        assert_ne!(padded_checksum(&near, &[], 0.000008), padded_checksum(&near, &surfaces, 0.000008));
        assert_ne!(padded_checksum(&near, &surfaces, 0.000008), padded_checksum(&near, &surfaces, 0.000016));
        assert_eq!(padded_checksum(&far, &[], 0.000008), padded_checksum(&far, &surfaces, 0.000008));
        let mut distant = square();
        distant.cut_ground = true;
        for triangle in &mut distant.triangles {
            for (p, _) in triangle {
                p.x += 1000.0;
            }
        }
        let near_collar = super::super::underlay::owner_collar(&surfaces[0], 8.0).unwrap();
        let distant_collar = super::super::underlay::owner_collar(&distant, 8.0).unwrap();
        let local = near.checksum(&[], &[], &ground, (&[], &surfaces, &[]), (&scenery, &[near_collar]));
        let combined = [surfaces.into_iter().next().unwrap(), distant];
        assert_eq!(
            local,
            near.checksum(&[], &[], &ground, (&[], &combined, &[]), (&scenery, &[near_collar, distant_collar]))
        );
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
