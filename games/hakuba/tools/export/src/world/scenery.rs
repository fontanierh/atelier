//! Scenery: models stood on the ground, cables between authored world endpoints, and authored rails.
//!
//! Each model stands in the tile its foot is in, seated on the ground that tile's version draws: one data node per
//! model and version, named after the model's folder, whose extras hold
//! `{ "model": <its .glb, relative to the tile>, "detail": "full" | "middle", "instances": [x, y, z, yaw, scale, ...] }`
//! in the game's frame, yaw turning about y. A middle tile holds only the models seen from afar. Rails and cables are
//! meshes of full tiles only: rails are cut at tile edges, and each cable belongs to its starting tile.

use std::collections::BTreeMap;
use std::path::Path;

use anyhow::{Context, Result, bail};
use glam::{DVec2, DVec3};
use serde::Serialize;
use serde_json::json;

use super::game;
use super::ground::Ground;
use super::overlay::Overlay;
use super::raised::{self, Prepared, SurfacePaint};
use super::regions::Region;
use super::surface::{Surface, weights};
use crate::glb::{Glb, Material, Mesh};
use crate::shapes::vertex;

/// What a region stands on the ground and runs along it. Positions are on the map, in metres.
#[derive(Default)]
pub struct Scenery {
    pub placements: Vec<Placement>,
    /// Cables whose endpoints are published world coordinates instead of model anchors.
    pub cables: Vec<Cable>,
    /// Rails with authored map-frame points and outward directions.
    pub rails: Vec<Rail>,
}

/// A cable whose two ends have explicit map-frame positions.
pub struct Cable {
    pub from: DVec3,
    pub to: DVec3,
    pub sag: f64,
    pub radius_m: f64,
    pub colour: [f64; 3],
    pub paint: Option<SurfacePaint>,
}

/// A rail following explicit 3D points; post heights are relative to each authored point.
pub struct Rail {
    pub points: Vec<(DVec3, DVec2)>,
    pub profile: Vec<[f64; 2]>,
    pub post_every: usize,
    pub post_half_width: f64,
    pub post_bottom: f64,
    pub post_top: f64,
    pub colour: [f64; 3],
    pub paint: Option<SurfacePaint>,
}

/// @cc [owner:fontanierh,label:correctness] placement-offset-is-authored
/// An origin offset MUST be finite authored placement data relative to the drawn owning ground, and every consumer
/// MUST use the same offset. An offset does not prove contact: the real model's grounding and declared embedment
/// MUST be independently checked against its owning surface.
/// An explicit authored world height MUST remain identical across detail versions and MUST NOT be combined with an
/// offset. It also requires an independent check that the model's source placement is valid for the drawn world.
///
/// A model standing on the ground.
pub struct Placement {
    /// The model, by its folder under `assets/`, such as `plants/maple-a`.
    pub model: &'static str,
    /// Where its foot is.
    pub at: DVec2,
    /// How far it is turned counter-clockwise seen from above, in radians.
    pub yaw: f64,
    pub scale: f64,
    /// Signed authored origin offset from its owning ground, in metres.
    pub origin_offset_m: f64,
    /// Explicit authored world height, shared by all detail versions when present.
    pub origin_height_m: Option<f64>,
    /// Whether middle tiles show it too.
    pub afar: bool,
}

/// The kind of scattered scenery a clearance applies to.
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum ScatterKind {
    Tree,
    Bush,
    Grass,
}

/// The land a region fills: the ground, and the part of the map the world exports.
pub struct Land<'a> {
    pub ground: &'a Ground,
    pub rendered: Option<&'a Surface>,
    pub raised: &'a Prepared<'a>,
    pub middle: bool,
    pub low: DVec2,
    pub high: DVec2,
    pub regions: &'a [&'a dyn Region],
}

impl Land<'_> {
    /// Whether every region permits an already-selected scatter candidate.
    pub fn allows_candidate(&self, kind: ScatterKind, placement: &Placement) -> bool {
        self.regions.iter().all(|region| region.allows_scatter_candidate(kind, placement))
    }

    /// The ground's height at `p`, if there is ground there.
    pub fn height(&self, p: DVec2) -> Option<f64> {
        match self.rendered {
            Some(surface) => self.raised.height_with_crossing(
                p,
                self.middle,
                |p| surface.ground_height(p),
                |p, base| surface.crossing_over(p, base),
            ),
            None => self.raised.height_for_detail(p, self.middle, |p| self.ground.height(p)),
        }
    }

    /// The same effective position used when a candidate becomes a placement.
    pub fn placement_at(&self, p: DVec2) -> DVec2 {
        effective_at(self.raised, self.rendered, p).0
    }

    /// How steep the ground is at `p`: how far it rises per metre across, going straight uphill.
    pub fn slope(&self, p: DVec2) -> f64 {
        if self.raised.owner_height(p).is_some() {
            return 0.0;
        }
        if let Some(surface) = self.rendered {
            let terrain = self.raised.height(p, |p| surface.ground_height(p));
            if let Some(slope) = surface.crossing_slope_over(p, terrain) {
                return slope;
            }
        }
        let up = self.ground.normal(p);
        up.truncate().length() / up.z
    }
}

/// How far a cable must stay above the ground under it.
const CABLE_CLEARANCE_M: f64 = 2.0;

/// How many straight pieces a cable is made of.
const CABLE_PIECES: usize = 14;

/// How far an authored rail may cross above or below a raised owner.
const RAIL_SETTLE_M: f64 = 0.35;

/// A copy of a model: its foot's position, yaw, scale, and whether it shows afar.
type Placed = ([f64; 2], f64, f64, bool, bool, f64, Option<f64>);

/// A point of a rail: its foot, the rail's direction there in plan, and how far along the rail it is, in metres.
type RailPoint = ([f64; 3], [f64; 2], f64);
type RailPiece = (Vec<RailPoint>, Vec<[f64; 2]>, [f64; 3], Option<SurfacePaint>);
type RailPost = ([f64; 3], f64, f64, f64, [f64; 3], Option<SurfacePaint>);
type CablePiece = (Vec<[f64; 3]>, f64, [f64; 3], Option<SurfacePaint>);

/// A piece of a path within one tile: the tile, and each point with the path's direction there, in plan, and how far
/// along the whole path it is.
type PathPiece = ((usize, usize), Vec<(DVec3, DVec2, f64)>);

/// What one tile holds of the scenery, ready to write. Its checksum covers all of it.
#[derive(Serialize, Default)]
pub struct TileScenery {
    /// The models standing in the tile, by folder.
    models: BTreeMap<&'static str, Vec<Placed>>,
    /// The cables starting in the tile: each its points on the map, its radius and colour.
    cables: Vec<CablePiece>,
    /// Authored rail pieces and their posts in this tile.
    rails: Vec<RailPiece>,
    posts: Vec<RailPost>,
}

/// The world's tiles, as the scenery needs them: where the first starts on the map, and their side in metres.
pub struct Grid {
    pub south_west: DVec2,
    pub tile_m: f64,
}

impl Grid {
    pub fn tile(&self, p: DVec2) -> (usize, usize) {
        let k = ((p - self.south_west) / self.tile_m).floor();
        (k.x as usize, k.y as usize)
    }
}

/// Shares each region's scenery out between the tiles. `drawn` is the ground the full tiles draw, across the whole
/// exported part of the map, which validates cables. Fails if a model has no asset, stands on an overlay or no ground,
/// or a cable comes too close to the ground.
pub fn share(
    sceneries: Vec<Scenery>,
    land: &Land,
    grid: &Grid,
    overlays: &[Overlay],
    raised: &Prepared<'_>,
    drawn: &Surface,
) -> Result<BTreeMap<(usize, usize), TileScenery>> {
    let inside = |p: DVec2| p.cmpge(land.low).all() && p.cmplt(land.high).all();
    let mut tiles: BTreeMap<(usize, usize), TileScenery> = BTreeMap::new();
    for scenery in sceneries {
        for placement in &scenery.placements {
            let (at, yaw, scale, precise) = effective_pose(raised, land.rendered, placement);
            if !placement.origin_offset_m.is_finite()
                || !(placement.origin_offset_m as f32).is_finite()
                || placement.origin_height_m.is_some_and(|h| !h.is_finite() || !(h as f32).is_finite())
                || (placement.origin_height_m.is_some() && placement.origin_offset_m != 0.0)
                || !at.is_finite()
                || !yaw.is_finite()
                || !(yaw as f32).is_finite()
                || !scale.is_finite()
                || !(scale as f32).is_finite()
                || scale <= 0.0
            {
                bail!("{} has an invalid scale or origin offset", placement.model);
            }
            raised.check_point(at)?;
            if !precise {
                raised.check_point(raised::stored((at * 1000.0).round() / 1000.0))?;
            }
            if !inside(at) {
                continue;
            }
            crate::uri_of_asset(placement.model, "glb")?;
            if let Some(overlay) = on_overlay(overlays, at) {
                bail!("{} at {} stands on the overlay {overlay}", placement.model, at);
            }
            let entry = tiles.entry(grid.tile(at)).or_default().models.entry(placement.model).or_default();
            entry.push((
                at.to_array(),
                yaw,
                scale,
                placement.afar,
                precise,
                placement.origin_offset_m,
                placement.origin_height_m,
            ));
        }
        for cable in &scenery.cables {
            if !cable.from.is_finite()
                || !cable.to.is_finite()
                || !cable.sag.is_finite()
                || !cable.radius_m.is_finite()
                || cable.radius_m <= 0.0
                || (cable.to - cable.from).truncate().length_squared() == 0.0
                || !cable.from.as_vec3().is_finite()
                || !cable.to.as_vec3().is_finite()
                || cable.colour.iter().any(|c| !c.is_finite())
                || cable.paint.as_ref().is_some_and(|p| !p.valid())
            {
                bail!("a fixed cable has invalid endpoints or material");
            }
            if !inside(cable.from.truncate()) || !inside(cable.to.truncate()) {
                continue;
            }
            let span = cable.from.distance(cable.to);
            let mut points = Vec::new();
            for k in 0..=CABLE_PIECES {
                let t = k as f64 / CABLE_PIECES as f64;
                let p = cable.from.lerp(cable.to, t) - DVec3::Z * cable.sag * span * 4.0 * t * (1.0 - t);
                if !cable_is_clear(p, drawn, raised)? {
                    bail!("a fixed cable comes too close to ground at {p}");
                }
                if let Some(previous) = points.last().copied() {
                    check_cable_segment(
                        DVec3::from_array(previous).as_vec3().as_dvec3(),
                        p.as_vec3().as_dvec3(),
                        raised,
                        "fixed cable",
                    )?;
                }
                points.push(p.to_array());
            }
            tiles.entry(grid.tile(cable.from.truncate())).or_default().cables.push((
                points,
                cable.radius_m,
                cable.colour,
                cable.paint.clone(),
            ));
        }
        for rail in &scenery.rails {
            if rail.points.len() < 2
                || rail.profile.len() < 2
                || rail.post_every == 0
                || !rail.post_half_width.is_finite()
                || rail.post_half_width <= 0.0
                || !rail.post_bottom.is_finite()
                || !rail.post_top.is_finite()
                || rail.post_bottom >= rail.post_top
                || rail.points.iter().any(|(p, n)| !p.is_finite() || !n.is_finite() || n.length_squared() == 0.0)
                || rail.points.iter().any(|(p, n)| !p.as_vec3().is_finite() || !n.as_vec2().is_finite())
                || rail.points.windows(2).any(|pair| pair[0].0 == pair[1].0)
                || rail.profile.iter().flatten().chain(rail.colour.iter()).any(|x| !x.is_finite())
                || rail.paint.as_ref().is_some_and(|p| !p.valid())
            {
                bail!("an authored rail has invalid geometry");
            }
            let path: Vec<_> = rail.points.iter().map(|(p, _)| *p).collect();
            for &point in &path {
                raised.check_point(raised.emitted_at(point.truncate()))?;
            }
            for pair in path.windows(2) {
                check_rail_segment(raised.emitted_point(pair[0]), raised.emitted_point(pair[1]), raised)?;
            }
            for &(foot, _) in rail.points.iter().step_by(rail.post_every).filter(|(p, _)| inside(p.truncate())) {
                tiles.entry(grid.tile(foot.truncate())).or_default().posts.push((
                    foot.to_array(),
                    rail.post_half_width,
                    rail.post_bottom,
                    rail.post_top,
                    rail.colour,
                    rail.paint.clone(),
                ));
            }
            for (tile, piece) in cut(&path, grid) {
                if !inside(piece[0].0.truncate()) {
                    continue;
                }
                let mut lengths = vec![0.0];
                for pair in path.windows(2) {
                    lengths.push(lengths.last().unwrap() + pair[0].distance(pair[1]));
                }
                let points = piece
                    .iter()
                    .map(|(p, _, along)| {
                        let k = lengths.partition_point(|x| x < along).saturating_sub(1).min(path.len() - 2);
                        let t = (along - lengths[k]) / (lengths[k + 1] - lengths[k]);
                        let normal = rail.points[k].1.lerp(rail.points[k + 1].1, t);
                        (p.to_array(), normal.to_array(), *along)
                    })
                    .collect();
                tiles.entry(tile).or_default().rails.push((
                    points,
                    rail.profile.clone(),
                    rail.colour,
                    rail.paint.clone(),
                ));
            }
        }
    }
    Ok(tiles)
}

fn check_cable_segment(previous: DVec3, next: DVec3, raised: &Prepared<'_>, model: &str) -> Result<()> {
    for (start, end) in raised.segment_intervals(previous.truncate(), next.truncate()) {
        let middle = previous.lerp(next, (start + end) * 0.5);
        raised.check_point(middle.truncate())?;
        let owner = raised.owner_height(middle.truncate());
        let retained = [false, true].map(|detail| raised.retained_cut_at(middle.truncate(), detail));
        for t in [start, end] {
            let sample = previous.lerp(next, t);
            raised.check_point(sample.truncate())?;
            let boundary = raised.owner_height(sample.truncate());
            if owner.into_iter().chain(boundary).any(|height| sample.z < height + CABLE_CLEARANCE_M) {
                bail!("a cable from {model} crosses a raised surface without clearance at {sample}");
            }
            for (detail, active) in [false, true].into_iter().zip(retained) {
                if active
                    && raised
                        .stored_cut_height(sample.truncate(), detail)
                        .is_some_and(|height| sample.z < height + CABLE_CLEARANCE_M)
                {
                    bail!("a cable from {model} crosses retained ground without clearance at {sample}");
                }
            }
        }
    }
    Ok(())
}

fn cable_is_clear(p: DVec3, drawn: &Surface, raised: &Prepared<'_>) -> Result<bool> {
    let emitted = raised.emitted_point(p);
    let at = emitted.truncate();
    raised.check_point(at)?;
    Ok(emitted.z
        >= raised
            .height_with_crossing(at, false, |p| drawn.ground_height(p), |p, base| drawn.crossing_over(p, base))
            .unwrap_or(f64::NEG_INFINITY)
            + CABLE_CLEARANCE_M)
}

fn check_rail_segment(a: DVec3, b: DVec3, raised: &Prepared<'_>) -> Result<()> {
    let [a, b] = [a, b].map(|p| p.as_vec3().as_dvec3());
    for (start, end) in raised.segment_intervals(a.truncate(), b.truncate()) {
        let middle = a.lerp(b, (start + end) * 0.5);
        raised.check_point(middle.truncate())?;
        let owner = raised.owner_height(middle.truncate());
        for t in [start, end] {
            let foot = a.lerp(b, t);
            let at = foot.truncate();
            raised.check_point(at)?;
            let boundary = raised.owner_height(at);
            if owner.into_iter().chain(boundary).any(|height| (foot.z - height).abs() > RAIL_SETTLE_M) {
                bail!("a rail crosses a raised surface at {at} away from its owning height");
            }
        }
    }
    Ok(())
}

/// Preserve authored f32 poses near raised ownership; elsewhere keep the existing export behavior.
fn effective_at(raised: &Prepared<'_>, rendered: Option<&Surface>, at: DVec2) -> (DVec2, bool) {
    let legacy = raised::stored((at * 1000.0).round() / 1000.0);
    let authored = raised::stored(at);
    let precise = [at, legacy, authored].into_iter().any(|p| {
        raised.owner_height(p).is_some()
            || raised.touches_cut(p)
            || rendered.is_some_and(|surface| surface.crossing_contains(p))
    });
    (if precise { authored } else { at }, precise)
}

pub(super) fn effective_pose(
    raised: &Prepared<'_>,
    rendered: Option<&Surface>,
    placement: &Placement,
) -> (DVec2, f64, f64, bool) {
    let (at, precise) = effective_at(raised, rendered, placement.at);
    let precise = precise || placement.origin_offset_m != 0.0 || placement.origin_height_m.is_some();
    let at = if precise { raised::stored(placement.at) } else { at };
    if precise {
        (at, placement.yaw as f32 as f64, placement.scale as f32 as f64, true)
    } else {
        (at, placement.yaw, placement.scale, false)
    }
}

/// The name of the overlay that covers `p`, if any.
fn on_overlay(overlays: &[Overlay], p: DVec2) -> Option<&str> {
    overlays.iter().find_map(|overlay| {
        let covers = overlay.triangles.iter().any(|triangle| {
            let corners = triangle.map(|(q, _)| q);
            weights(corners, p).is_some_and(|w| w.min_element() >= 0.0)
        });
        covers.then_some(overlay.name.as_str())
    })
}

/// `path` cut where it crosses a tile's edge, as pieces each within one tile: each point with the path's direction
/// there, in plan, and how far along the whole path it is. A point where the path crosses an edge ends one piece and
/// starts the next, so the pieces meet exactly, and their distances along run on across the edge.
fn cut(path: &[DVec3], grid: &Grid) -> Vec<PathPiece> {
    let direction = |k: usize| (path[(k + 1).min(path.len() - 1)] - path[k.saturating_sub(1)]).truncate().normalize();
    let mut pieces: Vec<PathPiece> = Vec::new();
    let mut along = 0.0;
    for k in 0..path.len() - 1 {
        let (a, b) = (path[k], path[k + 1]);
        let length = a.distance(b);
        // Where along a to b the segment crosses a line between tiles, and the point there, exactly on the line.
        let mut stops = vec![(0.0, a), (1.0, b)];
        for axis in 0..2 {
            let (from, to) =
                ((a[axis] - grid.south_west[axis]) / grid.tile_m, (b[axis] - grid.south_west[axis]) / grid.tile_m);
            for line in from.min(to).ceil() as i64..=from.max(to).floor() as i64 {
                let t = (line as f64 - from) / (to - from);
                if t > 0.0 && t < 1.0 {
                    let mut p = a.lerp(b, t);
                    p[axis] = grid.south_west[axis] + line as f64 * grid.tile_m;
                    stops.push((t, p));
                }
            }
        }
        stops.sort_by(|p, q| p.0.total_cmp(&q.0));
        for pair in stops.windows(2) {
            let ((t0, start), (t1, end)) = (pair[0], pair[1]);
            let tile = grid.tile(start.lerp(end, 0.5).truncate());
            let at = |t: f64, p: DVec3| match t {
                0.0 => (p, direction(k), along),
                1.0 => (p, direction(k + 1), along + length),
                _ => (p, (b - a).truncate().normalize(), along + t * length),
            };
            match pieces.last_mut() {
                Some((last, points)) if *last == tile => points.push(at(t1, end)),
                _ => pieces.push((tile, vec![at(t0, start), at(t1, end)])),
            }
        }
        along += length;
    }
    pieces
}

impl TileScenery {
    /// Adds what the tile holds to `glb`, its models seated on `surface`, the ground this version draws.
    pub fn write(
        &self,
        glb: &mut Glb,
        surface: &Surface,
        raised: &Prepared<'_>,
        middle: bool,
        path: &Path,
    ) -> Result<()> {
        self.write_models(glb, middle, path, |at| {
            raised.check_point(at)?;
            Ok(raised.height_with_crossing(
                at,
                middle,
                |p| surface.ground_height(p),
                |p, base| surface.crossing_over(p, base),
            ))
        })?;
        self.write_fixed(glb, middle)
    }

    /// Adds a model standing at its own explicit height, such as one past the ground.
    pub fn add(&mut self, placement: &Placement) {
        let entry = self.models.entry(placement.model).or_default();
        entry.push((
            placement.at.to_array(),
            placement.yaw,
            placement.scale,
            placement.afar,
            false,
            placement.origin_offset_m,
            placement.origin_height_m,
        ));
    }

    /// Adds what a tile past the ground holds to `glb`: only models, each at its own explicit height.
    pub fn write_beyond(&self, glb: &mut Glb, middle: bool, path: &Path) -> Result<()> {
        if !self.cables.is_empty() || !self.rails.is_empty() || !self.posts.is_empty() {
            bail!("{}: cables and rails need ground", path.display());
        }
        self.write_models(glb, middle, path, |_| Ok(None))
    }

    /// Adds the models, each instance's origin at its explicit height or on `seat`, the ground under it if any.
    fn write_models(
        &self,
        glb: &mut Glb,
        middle: bool,
        path: &Path,
        seat: impl Fn(DVec2) -> Result<Option<f64>>,
    ) -> Result<()> {
        for (model, instances) in &self.models {
            let mut numbers = Vec::new();
            for &(at, yaw, scale, afar, precise, origin_offset_m, origin_height_m) in instances {
                if middle && !afar {
                    continue;
                }
                let at = DVec2::from_array(at);
                let ground = seat(at)?;
                let origin = match origin_height_m {
                    Some(height) => height,
                    None => {
                        ground.with_context(|| format!("{}: {model} at {at} stands on no ground", path.display()))?
                            + origin_offset_m
                    }
                };
                if !origin.is_finite() || (precise && !(origin as f32).is_finite()) {
                    bail!("{model} has an invalid origin height");
                }
                let p = game(at.extend(origin));
                let values = [p.x, p.y, p.z, yaw, scale];
                numbers.extend(if precise {
                    values.map(|v| v as f32 as f64)
                } else {
                    values.map(|v| (v * 1000.0).round() / 1000.0)
                });
            }
            if numbers.is_empty() {
                continue;
            }
            // A middle tile shows a prop's lighter middle version, which every prop exports.
            let extension = if middle && model.starts_with("props/") { "middle.glb" } else { "glb" };
            let extras = json!({
                "model": crate::uri_of_asset(model, extension)?,
                "detail": if middle { "middle" } else { "full" },
                "instances": numbers,
            });
            glb.add_data(model, extras);
        }
        Ok(())
    }

    /// Adds the cables, rails and rail posts, which only full detail draws.
    fn write_fixed(&self, glb: &mut Glb, middle: bool) -> Result<()> {
        if middle {
            return Ok(());
        }
        for (k, (points, radius, colour, paint)) in self.cables.iter().enumerate() {
            let mut mesh = Mesh::default();
            let points: Vec<DVec3> = points.iter().map(|&p| DVec3::from_array(p)).collect();
            fixed_wire(&mut mesh, &points, *radius);
            mesh.material = glb.add_material(&plain("cable", *colour, false));
            let node = glb.add_mesh(&format!("cable fixed {k}"), &[&mesh]);
            if let Some(paint) = paint {
                glb.set_extras(node, json!({"surface_paint": paint, "surface_untextured": true}));
            }
        }
        for (k, (piece, profile, colour, paint)) in self.rails.iter().enumerate() {
            let mut mesh = Mesh::default();
            fixed_rail(&mut mesh, piece, profile);
            mesh.material = glb.add_material(&plain("rail", *colour, true));
            let node = glb.add_mesh(&format!("fixed rail {k}"), &[&mesh]);
            if let Some(paint) = paint {
                glb.set_extras(node, json!({"surface_paint": paint, "surface_untextured": true}));
            }
        }
        for (k, (foot, half, bottom, top, colour, paint)) in self.posts.iter().enumerate() {
            let mut mesh = Mesh::default();
            fixed_post(&mut mesh, DVec3::from_array(*foot), *half, *bottom, *top);
            mesh.material = glb.add_material(&plain("rail post", *colour, false));
            let node = glb.add_mesh(&format!("fixed post {k}"), &[&mesh]);
            if let Some(paint) = paint {
                glb.set_extras(node, json!({"surface_paint": paint, "surface_untextured": true}));
            }
        }
        Ok(())
    }
}

/// A four-sided open cable with a fixed world-vertical cross-section along its span.
fn fixed_wire(mesh: &mut Mesh, points: &[DVec3], radius: f64) {
    let side = (points[points.len() - 1] - points[0]).cross(DVec3::Z).normalize();
    let offsets = [side, DVec3::Z, -side, -DVec3::Z];
    let mut rows = Vec::new();
    for &point in points {
        rows.push(offsets.map(|out| vertex(mesh, point + out * radius, out, DVec2::ZERO, None)));
    }
    for pair in rows.windows(2) {
        for k in 0..4 {
            let (a, b, c, d) = (pair[0][k], pair[0][(k + 1) % 4], pair[1][(k + 1) % 4], pair[1][k]);
            mesh.indices.extend([a, c, b, a, d, c]);
        }
    }
}

fn fixed_rail(mesh: &mut Mesh, piece: &[RailPoint], profile: &[[f64; 2]]) {
    let mut rows = Vec::new();
    for &(foot, outward, _) in piece {
        let foot = DVec3::from_array(foot);
        let outward = DVec2::from_array(outward);
        let row: Vec<_> = profile
            .iter()
            .enumerate()
            .map(|(k, &[offset, height])| {
                let [o0, h0] = profile[k.saturating_sub(1)];
                let [o1, h1] = profile[(k + 1).min(profile.len() - 1)];
                vertex(
                    mesh,
                    (foot.truncate() + outward * offset).extend(foot.z + height),
                    (outward * (h1 - h0)).extend(o0 - o1),
                    DVec2::ZERO,
                    None,
                )
            })
            .collect();
        rows.push(row);
    }
    for pair in rows.windows(2) {
        for k in 0..profile.len() - 1 {
            let (a, b, c, d) = (pair[0][k], pair[0][k + 1], pair[1][k + 1], pair[1][k]);
            mesh.indices.extend([a, b, c, a, c, d]);
        }
    }
}

fn fixed_post(mesh: &mut Mesh, foot: DVec3, half: f64, bottom: f64, top: f64) {
    let corners = [(-half, -half), (half, -half), (half, half), (-half, half)];
    for k in 0..4 {
        let (a, b) = (corners[k], corners[(k + 1) % 4]);
        let normal = DVec3::new(b.1 - a.1, a.0 - b.0, 0.0);
        let points = [(a.0, a.1, bottom), (b.0, b.1, bottom), (b.0, b.1, top), (a.0, a.1, top)];
        let ids = points.map(|(x, y, z)| vertex(mesh, foot + DVec3::new(x, y, z), normal, DVec2::ZERO, None));
        mesh.indices.extend([ids[0], ids[1], ids[2], ids[0], ids[2], ids[3]]);
    }
    let ids = corners.map(|(x, y)| vertex(mesh, foot + DVec3::new(x, y, top), DVec3::Z, DVec2::ZERO, None));
    mesh.indices.extend([ids[0], ids[1], ids[2], ids[0], ids[2], ids[3]]);
}

/// A matte material of one colour.
fn plain(name: &str, colour: [f64; 3], two_sided: bool) -> Material<'_> {
    Material { name, texture: None, colour, cut_out: false, two_sided }
}

/// What a tile's checksum covers of its scenery.
pub fn checksum_bytes(scenery: &TileScenery) -> Vec<u8> {
    serde_json::to_vec(scenery).expect("scenery serializes")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cable_faces_wind_outward() {
        let mut mesh = Mesh::default();
        fixed_wire(&mut mesh, &[DVec3::ZERO, DVec3::new(4.0, 1.0, -0.2)], 0.03);
        for triangle in mesh.indices.chunks_exact(3) {
            let [a, b, c] = std::array::from_fn(|k| glam::Vec3::from_array(mesh.positions[triangle[k] as usize]));
            let normal = glam::Vec3::from_array(mesh.normals[triangle[0] as usize]);
            assert!((b - a).cross(c - a).dot(normal) > 0.0);
        }
    }
    use crate::world::raised::Raised;
    use geo::polygon;

    #[test]
    fn authored_origin_is_identical_over_different_detail_ground() {
        use crate::world::{Detail, Tile};
        let mut tile = TileScenery::default();
        tile.models.entry("props/utility-pole").or_default().push(([1.0, 1.0], 0.0, 1.0, true, true, 0.0, Some(4.25)));
        let raised = Prepared::new(&[], DVec2::ZERO, 8.0);
        for (middle, height) in [(false, 1.0_f32), (true, 2.0)] {
            let ground = Ground::page(8, 1.0, |_, _| height);
            let mesh = Tile { columns: (0, 8), rows: (0, 8) }.ground(&ground, Detail::Full, 0, 1.0);
            let surface = Surface::new(&mesh);
            let mut glb = Glb::from_json(json!({"asset": {"version": "2.0"}}));
            tile.write(&mut glb, &surface, &raised, middle, Path::new("test.glb")).unwrap();
            let instances = glb.extras("props/utility-pole").unwrap()["instances"].as_array().unwrap();
            assert_eq!(instances[1].as_f64(), Some(4.25));
        }
    }

    #[test]
    fn fixed_wire_uses_vertical_diamond_rings_without_caps() {
        let mut mesh = Mesh::default();
        fixed_wire(&mut mesh, &[DVec3::ZERO, DVec3::new(4.0, 0.0, -1.0)], 0.03);
        let expected = [
            DVec3::new(0.0, -0.03, 0.0),
            DVec3::new(0.0, 0.0, 0.03),
            DVec3::new(0.0, 0.03, 0.0),
            DVec3::new(0.0, 0.0, -0.03),
        ];
        for (position, point) in mesh.positions.iter().take(4).zip(expected) {
            assert_eq!(*position, crate::glb::y_up(point).as_vec3().to_array());
        }
        assert_eq!(mesh.positions.len(), 8);
        assert_eq!(mesh.indices.len(), 24);
    }

    #[test]
    fn emitted_wire_node_uses_the_runtime_non_solid_prefix() {
        let mut tile = TileScenery::default();
        tile.cables.push((vec![[0.0, 0.0, 4.0], [1.0, 0.0, 4.0]], 0.03, [0.08; 3], None));
        let mut glb = Glb::from_json(json!({"asset": {"version": "2.0"}}));
        let surface = Surface::new(&Mesh::default());
        let raised = Prepared::new(&[], DVec2::ZERO, 8.0);
        tile.write(&mut glb, &surface, &raised, false, Path::new("test.glb")).unwrap();
        assert!(glb.node("cable fixed 0").is_ok());
    }

    #[test]
    fn fixed_rail_and_posts_use_authored_height_and_outward_direction() {
        let mut beam = Mesh::default();
        let piece = [([1.0, 2.0, 3.0], [0.0, 1.0], 0.0), ([2.0, 2.0, 4.0], [0.0, 1.0], 1.0)];
        fixed_rail(&mut beam, &piece, &[[0.0, 0.85], [0.06, 0.8]]);
        assert_eq!(beam.positions[1], crate::glb::y_up(DVec3::new(1.0, 2.06, 3.8)).as_vec3().to_array());
        assert_eq!(beam.positions[3], crate::glb::y_up(DVec3::new(2.0, 2.06, 4.8)).as_vec3().to_array());
        let mut post = Mesh::default();
        fixed_post(&mut post, DVec3::new(1.0, 2.0, 3.0), 0.05, -0.3, 0.72);
        assert_eq!(post.indices.len(), 30); // four sides and the top, with no bottom
        assert_eq!(post.positions[0], crate::glb::y_up(DVec3::new(0.95, 1.95, 2.7)).as_vec3().to_array());
    }

    fn cut_envelope() -> [Vec<crate::world::underlay::Underlay>; 2] {
        let area = geo::MultiPolygon(vec![polygon![
            (x: 3.7, y: 1.0), (x: 4.3, y: 1.0), (x: 4.3, y: 5.0),
            (x: 3.7, y: 5.0), (x: 3.7, y: 1.0),
        ]]);
        std::array::from_fn(|_| vec![crate::world::underlay::Underlay { polygon: area.clone(), query: area.clone() }])
    }

    #[test]
    fn cable_checks_retained_cut_ground_between_samples() {
        use crate::world::{Detail, Tile};
        let ground = Ground::page(8, 1.0, |_, _| 0.0);
        let middle_ground = Ground::page(8, 1.0, |i, _| if i == 4 { 1.0 } else { 0.0 });
        let tile = Tile { columns: (0, 8), rows: (0, 8) };
        let drawn = Surface::new(&tile.ground(&ground, Detail::Full, 0, 1.0));
        let middle = Surface::new(&tile.ground(&middle_ground, Detail::Full, 0, 1.0));
        let mut prepared = Prepared::new(&[], DVec2::ZERO, 8.0);
        prepared.set_underlays(&cut_envelope());
        prepared.add_tile_with_cut((0, 0), &drawn, &drawn, false).unwrap();
        prepared.add_tile_with_cut((0, 0), &drawn, &middle, true).unwrap();
        let a = DVec3::new(3.8, 4.0, 2.9).as_vec3().as_dvec3();
        let b = DVec3::new(4.2, 4.0, 2.9).as_vec3().as_dvec3();
        assert!(cable_is_clear(a, &drawn, &prepared).unwrap());
        assert!(cable_is_clear(b, &drawn, &prepared).unwrap());
        assert!(check_cable_segment(a, b, &prepared, "pole").is_err());
    }

    #[test]
    fn placement_uses_retained_ground_of_emitted_detail() {
        use crate::world::{Detail, Tile};
        let full_ground = Ground::page(8, 1.0, |_, _| 2.0);
        let middle_ground = Ground::page(8, 1.0, |_, _| 1.0);
        let tile = Tile { columns: (0, 8), rows: (0, 8) };
        let full = Surface::new(&tile.ground(&full_ground, Detail::Full, 0, 1.0));
        let middle = Surface::new(&tile.ground(&middle_ground, Detail::Full, 0, 1.0));
        let mut prepared = Prepared::new(&[], DVec2::ZERO, 8.0);
        prepared.set_underlays(&cut_envelope());
        prepared.add_tile_with_cut((0, 0), &full, &full, false).unwrap();
        prepared.add_tile_with_cut((0, 0), &middle, &middle, true).unwrap();
        let mut scenery = TileScenery::default();
        scenery.models.insert("props/utility-pole", vec![([4.0, 2.0], 0.0, 1.0, true, true, 0.25, None)]);
        for (is_middle, surface, expected) in [(false, &full, 2.25), (true, &middle, 1.25)] {
            let mut glb = Glb::from_json(json!({"asset": {"version": "2.0"}}));
            scenery.write(&mut glb, surface, &prepared, is_middle, Path::new("test.glb")).unwrap();
            let instances = glb.extras("props/utility-pole").unwrap()["instances"].as_array().unwrap();
            assert_eq!(instances[1].as_f64().unwrap(), expected);
        }
    }

    #[test]
    fn retained_cut_collar_uses_the_emitted_pose_and_tile() {
        use crate::world::{Detail, Tile};
        let ground = Ground::page(8, 1.0, |i, _| i as f32);
        let mut prepared = Prepared::new(&[], DVec2::ZERO, 4.0);
        prepared.set_underlays(&cut_envelope());
        for x in 0..2 {
            let tile = Tile { columns: (4 * x, 4 * x + 4), rows: (0, 4) };
            for detail in [Detail::Full, Detail::Middle] {
                let drawn = Surface::new(&tile.ground(&ground, detail, 0, 1.0));
                prepared.add_tile_with_cut((x, 0), &drawn, &drawn, detail == Detail::Middle).unwrap();
            }
        }
        let drawn = Surface::new(&Tile { columns: (0, 8), rows: (0, 8) }.ground(&ground, Detail::Full, 0, 1.0));
        let land = Land {
            ground: &ground,
            rendered: None,
            raised: &prepared,
            middle: false,
            low: DVec2::ZERO,
            high: DVec2::splat(8.0),
            regions: &[],
        };
        let at = DVec2::new(3.9996, 2.0);
        let scenery = Scenery {
            placements: vec![Placement {
                model: "props/utility-pole",
                at,
                yaw: 0.0,
                scale: 1.0,
                origin_offset_m: 0.0,
                origin_height_m: None,
                afar: true,
            }],
            ..Default::default()
        };
        let grid = Grid { south_west: DVec2::ZERO, tile_m: 4.0 };
        let tiles = share(vec![scenery], &land, &grid, &[], &prepared, &drawn).unwrap();
        let placed = &tiles[&(0, 0)].models["props/utility-pole"][0];
        assert!(placed.4);
        assert_eq!(placed.0[0], 3.9996_f32 as f64);
        let mut glb = Glb::from_json(json!({"asset": {"version": "2.0"}}));
        tiles[&(0, 0)].write(&mut glb, &drawn, &prepared, false, Path::new("test.glb")).unwrap();
        let numbers = glb.extras("props/utility-pole").unwrap()["instances"].as_array().unwrap();
        assert_eq!(numbers[0].as_f64().unwrap(), 3.9996_f32 as f64);
        assert_eq!(numbers[1].as_f64().unwrap(), 3.9996_f32 as f64);
    }

    #[test]
    fn emitted_candidate_rail_and_cable_positions_select_the_owner() {
        use crate::world::{Detail, Tile};
        let ground = Ground::page(8, 1.0, |_, _| 0.0);
        let drawn = Surface::new(&Tile { columns: (0, 8), rows: (0, 8) }.ground(&ground, Detail::Full, 0, 1.0));
        let p = |x, y| (DVec2::new(x, y), DVec2::ZERO);
        let raised = [Raised {
            name: "paving".into(),
            texture: "earth".into(),
            ground: true,
            paint: None,
            height: 3.0,
            clearance: 0.1,
            cut_ground: false,
            triangles: vec![[p(1.0, 0.0), p(2.0, 0.0), p(1.0, 1.0)]],
        }];
        let mut prepared = Prepared::new(&raised, DVec2::ZERO, 8.0);
        prepared.add_tile((0, 0), &drawn, false).unwrap();
        prepared.add_tile((0, 0), &drawn, true).unwrap();
        let land = Land {
            ground: &ground,
            rendered: None,
            raised: &prepared,
            middle: false,
            low: DVec2::ZERO,
            high: DVec2::splat(8.0),
            regions: &[],
        };
        let at = DVec2::new(0.99999999, 0.25);
        assert_eq!(land.placement_at(at), DVec2::new(1.0, 0.25));
        assert_eq!(land.height(land.placement_at(at)), Some(3.0));
        let start = prepared.emitted_at(at).extend(0.0);
        assert!(check_rail_segment(start, start + DVec3::X * 0.01, &prepared).is_err());
        assert!(!cable_is_clear(at.extend(4.0), &drawn, &prepared).unwrap());
        let empty = Prepared::new(&[], DVec2::ZERO, 8.0);
        assert_eq!(empty.emitted_at(at), at);
        assert!(cable_is_clear(at.extend(4.0), &drawn, &empty).unwrap());
    }

    #[test]
    fn emitted_pose_and_seat_agree_across_authored_road_edge() {
        let terrain = Mesh {
            positions: vec![[-1.0, 0.0, 1.0], [2.0, 0.0, 1.0], [-1.0, 0.0, -2.0]],
            indices: vec![0, 1, 2],
            ..Default::default()
        };
        let road = Mesh {
            positions: vec![[0.0, 1.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, -1.0]],
            indices: vec![0, 1, 2],
            ..Default::default()
        };
        let drawn = Surface::with_crossings(&terrain, &[road]);
        let prepared = Prepared::new(&[], DVec2::ZERO, 8.0);
        let placement = Placement {
            model: "props/utility-pole",
            at: DVec2::new(-0.0004, 0.5),
            yaw: 0.0,
            scale: 1.0,
            origin_offset_m: 0.0,
            origin_height_m: None,
            afar: true,
        };
        let (at, yaw, scale, precise) = effective_pose(&prepared, Some(&drawn), &placement);
        assert!(precise && at.x < 0.0);
        let mut tile = TileScenery::default();
        tile.models.entry(placement.model).or_default().push((at.to_array(), yaw, scale, true, precise, 0.0, None));
        let mut glb = Glb::from_json(json!({"asset": {"version": "2.0"}}));
        tile.write(&mut glb, &drawn, &prepared, false, Path::new("test.glb")).unwrap();
        let path = std::env::temp_dir().join(format!("road-edge-{}.glb", std::process::id()));
        glb.write(&path).unwrap();
        let bytes = std::fs::read(&path).unwrap();
        std::fs::remove_file(path).unwrap();
        let n = u32::from_le_bytes(bytes[12..16].try_into().unwrap()) as usize;
        let data: serde_json::Value = serde_json::from_slice(&bytes[20..20 + n]).unwrap();
        let node = data["nodes"].as_array().unwrap().iter().find(|n| n["name"] == placement.model).unwrap();
        let instance = node["extras"]["instances"].as_array().unwrap();
        assert_eq!(instance[0].as_f64().unwrap(), at.x);
        assert_eq!(instance[1].as_f64().unwrap(), drawn.height(at).unwrap());
        assert_eq!(instance[1].as_f64().unwrap(), 0.0);
    }

    #[test]
    fn authored_pose_selects_its_actual_tile_and_overlay() {
        use crate::world::{Detail, Tile};
        let ground = Ground::page(8, 1.0, |_, _| 0.0);
        let drawn = Surface::new(&Tile { columns: (0, 8), rows: (0, 8) }.ground(&ground, Detail::Full, 0, 1.0));
        let p = |x, y| (DVec2::new(x, y), DVec2::ZERO);
        let raised = [Raised {
            name: "paving".into(),
            texture: "earth".into(),
            ground: true,
            paint: None,
            height: 3.0,
            clearance: 0.1,
            cut_ground: false,
            triangles: vec![[p(1.0, 1.0), p(4.0, 1.0), p(1.0, 4.0)]],
        }];
        let mut prepared = Prepared::new(&raised, DVec2::ZERO, 1.0);
        for x in 0..8 {
            for y in 0..8 {
                prepared.add_tile((x, y), &drawn, false).unwrap();
                prepared.add_tile((x, y), &drawn, true).unwrap();
            }
        }
        let land = Land {
            ground: &ground,
            rendered: None,
            raised: &prepared,
            middle: false,
            low: DVec2::ZERO,
            high: DVec2::splat(8.0),
            regions: &[],
        };
        let grid = Grid { south_west: DVec2::ZERO, tile_m: 1.0 };
        let scenery = || Scenery {
            placements: vec![Placement {
                model: "props/utility-pole",
                at: DVec2::new(0.9996, 1.0),
                yaw: -163.6_f64.to_radians(),
                scale: 1.0,
                origin_offset_m: 0.0,
                origin_height_m: None,
                afar: true,
            }],
            ..Default::default()
        };
        let tiles = share(vec![scenery()], &land, &grid, &[], &prepared, &drawn).unwrap();
        assert!(tiles.contains_key(&(0, 1)));
        assert!(!tiles.contains_key(&(1, 1)));
        let placed = &tiles[&(0, 1)].models["props/utility-pole"][0];
        assert_eq!(placed.0[0], 0.9996_f32 as f64);
        assert_eq!(placed.1, (-163.6_f64.to_radians()) as f32 as f64);
        assert!(placed.4);
        let mut glb = Glb::from_json(json!({"asset": {"version": "2.0"}}));
        tiles[&(0, 1)].write(&mut glb, &drawn, &prepared, false, Path::new("test.glb")).unwrap();
        let numbers = glb.extras("props/utility-pole").unwrap()["instances"].as_array().unwrap();
        assert_eq!(numbers[0].as_f64().unwrap(), 0.9996_f32 as f64);
        assert_eq!(numbers[3].as_f64().unwrap(), (-163.6_f64.to_radians()) as f32 as f64);
        let mut shifted = scenery();
        shifted.placements[0].at = DVec2::new(2.0, 2.0);
        shifted.placements[0].origin_offset_m = 0.03;
        let shifted = share(vec![shifted], &land, &grid, &[], &prepared, &drawn).unwrap();
        for middle in [false, true] {
            let mut glb = Glb::from_json(json!({"asset": {"version": "2.0"}}));
            shifted[&(2, 2)].write(&mut glb, &drawn, &prepared, middle, Path::new("test.glb")).unwrap();
            let numbers = glb.extras("props/utility-pole").unwrap()["instances"].as_array().unwrap();
            assert_eq!(numbers[1].as_f64().unwrap(), 3.03_f32 as f64);
        }
        let mut boundary = scenery();
        boundary.placements[0].at = DVec2::new(7.0 - 1e-8, 1.0);
        boundary.placements[0].origin_offset_m = -0.06;
        let boundary = share(vec![boundary], &land, &grid, &[], &prepared, &drawn).unwrap();
        let placed = &boundary[&(7, 1)].models["props/utility-pole"][0];
        assert_eq!(placed.0[0], 7.0);
        assert_eq!(placed.1, (-163.6_f64.to_radians()) as f32 as f64);
        let mut invalid = scenery();
        invalid.placements[0].origin_offset_m = f64::NAN;
        assert!(share(vec![invalid], &land, &grid, &[], &prepared, &drawn).is_err());
        let mut overflow = scenery();
        overflow.placements[0].origin_offset_m = f64::MAX;
        assert!(share(vec![overflow], &land, &grid, &[], &prepared, &drawn).is_err());
        let overlay = Overlay {
            name: "path".into(),
            texture: "earth".into(),
            triangles: vec![[p(0.9, 1.0), p(1.0, 1.0), p(0.9, 2.0)]],
        };
        assert!(share(vec![scenery()], &land, &grid, &[overlay], &prepared, &drawn).is_err());
    }

    #[test]
    fn boundary_placement_uses_its_streaming_tiles_surface() {
        use crate::world::{Detail, Tile};
        let ground = Ground::page(2, 1.0, |_, _| 0.0);
        let p = |x, y| (DVec2::new(x, y), DVec2::ZERO);
        let raised = [Raised {
            name: "paving".into(),
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
            let tile = Tile { columns: (x, x + 1), rows: (0, 1) };
            let drawn = Surface::new(&tile.ground(&ground, Detail::Full, 0, 1.0));
            prepared.add_tile((x, 0), &drawn, false).unwrap();
            prepared.add_tile((x, 0), &drawn, true).unwrap();
        }
        let whole = Surface::new(&Tile { columns: (0, 2), rows: (0, 2) }.ground(&ground, Detail::Full, 0, 1.0));
        let land = Land {
            ground: &ground,
            rendered: None,
            raised: &prepared,
            middle: false,
            low: DVec2::ZERO,
            high: DVec2::splat(2.0),
            regions: &[],
        };
        let grid = Grid { south_west: DVec2::ZERO, tile_m: 1.0 };
        let scenery = Scenery {
            placements: vec![Placement {
                model: "props/utility-pole",
                at: DVec2::new(1.0, 0.5),
                yaw: 0.0,
                scale: 1.0,
                origin_offset_m: 0.0,
                origin_height_m: None,
                afar: true,
            }],
            ..Default::default()
        };
        let error = share(vec![scenery], &land, &grid, &[], &prepared, &whole).err().unwrap();
        assert!(error.to_string().contains("raised ownership differs between adjacent tiles"));
    }
}
