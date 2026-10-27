//! Scenery: the models regions stand on the ground, such as trees, bushes, grass and poles, the cables strung between
//! their anchors, and the rails run along roads.
//!
//! Each model stands in the tile its foot is in, seated on the ground that tile's version draws: one data node per
//! model and version, named after the model's folder, whose extras hold
//! `{ "model": <its .glb, relative to the tile>, "detail": "full" | "middle", "instances": [x, y, z, yaw, scale, ...] }`
//! in the game's frame, yaw turning about y. A middle tile holds only the models seen from afar. Rails and cables are
//! meshes of full tiles only: a rail follows the ground drawn under it, eased along its whole length so that it bends
//! smoothly over the ground's small bumps, then is cut at each tile's edge; a cable
//! belongs to the tile of the model it starts from. A rail and its posts show a texture asset, named and never held,
//! laid in metres: one repeat of its image is a metre a side.

use std::collections::BTreeMap;
use std::f64::consts::TAU;
use std::path::Path;

use anyhow::{Context, Result, bail};
use glam::{DMat3, DVec2, DVec3};
use serde::Serialize;
use serde_json::json;

use super::game;
use super::ground::Ground;
use super::overlay::Overlay;
use super::raised::{self, Raised};
use super::surface::{Surface, weights};
use crate::glb::{Glb, Material, Mesh};
use crate::random::Random;
use crate::shapes::{tube, vertex};

/// What a region stands on the ground and runs along it. Positions are on the map, in metres.
#[derive(Default)]
pub struct Scenery {
    pub placements: Vec<Placement>,
    pub cables: Vec<Cable>,
    pub rails: Vec<Rail>,
}

/// A model standing on the ground.
pub struct Placement {
    /// The model, by its folder under `assets/`, such as `plants/maple-a`.
    pub model: &'static str,
    /// Where its foot is.
    pub at: DVec2,
    /// How far it is turned counter-clockwise seen from above, in radians.
    pub yaw: f64,
    pub scale: f64,
    /// Whether middle tiles show it too.
    pub afar: bool,
}

/// A cable hanging between two anchors, each given as a placement (by its index in the region's placements) and
/// the anchor's number in that placement's model.
pub struct Cable {
    pub from: (usize, usize),
    pub to: (usize, usize),
    /// How far its middle hangs below the straight line between its ends, as a share of its length.
    pub sag: f64,
    pub radius_m: f64,
    /// Its linear colour.
    pub colour: [f64; 3],
}

/// A rail along a line on the ground: its cross-section is a line through `profile`, each point an offset to the
/// left of the line and a height above the ground, in metres. It shows from both sides. A post stands on the line at
/// every `post_every`th point of the path, from just above the rail down into the ground.
pub struct Rail {
    pub path: Vec<DVec2>,
    pub profile: Vec<[f64; 2]>,
    pub post_every: usize,
    pub post_radius_m: f64,
    /// Its linear colour, and its posts', which tints its texture.
    pub colour: [f64; 3],
    /// The texture it and its posts show, by its folder under `assets/textures/`: along the rail by the distance
    /// travelled and across it by the distance around its profile, and on a post along it and around it, in metres.
    pub texture: &'static str,
}

/// The kind of scattered scenery a clearance applies to.
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum ScatterKind {
    Tree,
    Bush,
    Grass,
}

/// A clearance shared by regions. Courses use the same sampled curve and distance as scenery placement.
pub struct Exclusion {
    line: Vec<(DVec2, DVec2)>,
    radius: f64,
    kinds: Vec<ScatterKind>,
}

impl Exclusion {
    pub fn corridor(course: &[[f64; 2]], radius: f64, kinds: &[ScatterKind]) -> Self {
        assert!(course.len() >= 2 && radius.is_finite() && radius > 0.0);
        Self { line: super::curve::curve(course), radius, kinds: kinds.to_vec() }
    }

    fn excludes(&self, at: DVec2, kind: ScatterKind) -> bool {
        self.kinds.contains(&kind) && super::curve::nearest(&self.line, at).0 < self.radius
    }
}

/// The land a region fills: the ground, and the part of the map the world exports.
pub struct Land<'a> {
    pub ground: &'a Ground,
    pub raised: &'a [Raised],
    pub low: DVec2,
    pub high: DVec2,
    pub exclusions: &'a [Exclusion],
}

impl Land<'_> {
    /// Whether scattered scenery of this kind may stand here; explicit placements do not use this test.
    pub fn allows_scatter(&self, at: DVec2, kind: ScatterKind) -> bool {
        !self.exclusions.iter().any(|exclusion| exclusion.excludes(at, kind))
    }

    /// The ground's height at `p`, if there is ground there.
    pub fn height(&self, p: DVec2) -> Option<f64> {
        raised::height(self.raised, p, |p| self.ground.height(p))
    }

    /// How steep the ground is at `p`: how far it rises per metre across, going straight uphill.
    pub fn slope(&self, p: DVec2) -> f64 {
        if raised::height(self.raised, p, |_| None).is_some() {
            return 0.0;
        }
        let up = self.ground.normal(p);
        up.truncate().length() / up.z
    }

    /// A point scattered in each square of a grid of `side` metres (see [`Land::squares`]), up to `jitter` of a side
    /// from the square's centre either way, with the square's own stream of random numbers, drawn from `seed`.
    pub fn scatter(
        &self,
        seed: u64,
        side: f64,
        jitter: f64,
        kind: ScatterKind,
    ) -> impl Iterator<Item = (DVec2, Random)> {
        self.squares(side).filter_map(move |(column, row, corner)| {
            let mut random = Random::at(seed, column, row);
            let offset = DVec2::new(random.range([-jitter, jitter]), random.range([-jitter, jitter]));
            let at = corner + (DVec2::splat(0.5) + offset) * side;
            self.allows_scatter(at, kind).then_some((at, random))
        })
    }

    /// @cc [owner:fontanierh,label:correctness] scatter-survives-map-expansion
    /// Growing the exported map MUST preserve every origin-anchored grid cell intersecting the original bounds,
    /// so candidates contained in those cells and clipped to the bounds stay the same.
    /// Returns each cell's column, row and lower-left corner.
    pub fn squares(&self, side: f64) -> impl Iterator<Item = (i64, i64, DVec2)> {
        let (low, high) = ((self.low / side).floor(), (self.high / side).ceil());
        (low.y as i64..high.y as i64).flat_map(move |row| {
            (low.x as i64..high.x as i64).map(move |column| (column, row, DVec2::new(column as f64, row as f64) * side))
        })
    }
}

/// How far a cable must stay above the ground under it.
const CABLE_CLEARANCE_M: f64 = 2.0;

/// How many straight pieces a cable is made of.
const CABLE_PIECES: usize = 14;

/// A rail's height at each point follows the ground's along this many metres of the rail either side: it keeps the
/// ground's slope and long rises, and runs straight over its bumps.
const RAIL_EASE_M: f64 = 10.0;

/// How far above or below the ground under it a rail's foot may run once eased.
const RAIL_SETTLE_M: f64 = 0.35;

/// How far a rail's posts reach into the ground, and above the rail's top.
const POST_DEPTH_M: f64 = 0.4;
const POST_CAP_M: f64 = 0.03;

/// A copy of a model: its foot's position, yaw, scale, and whether it shows afar.
type Placed = ([f64; 2], f64, f64, bool, bool);

/// A point of a rail: its foot, the rail's direction there in plan, and how far along the rail it is, in metres.
type RailPoint = ([f64; 3], [f64; 2], f64);

/// A piece of a rail: its points, its profile, its colour and its texture.
type RailPiece = (Vec<RailPoint>, Vec<[f64; 2]>, [f64; 3], &'static str);

/// A rail's post: its foot on the eased rail, its height above that, its radius, colour and texture.
type Post = ([f64; 3], f64, f64, [f64; 3], &'static str);

/// A piece of a path within one tile: the tile, and each point with the path's direction there, in plan, and how far
/// along the whole path it is.
type PathPiece = ((usize, usize), Vec<(DVec3, DVec2, f64)>);

/// What one tile holds of the scenery, ready to write. Its checksum covers all of it.
#[derive(Serialize, Default)]
pub struct TileScenery {
    /// The models standing in the tile, by folder.
    models: BTreeMap<&'static str, Vec<Placed>>,
    /// The pieces of rails in the tile.
    rails: Vec<RailPiece>,
    /// The rails' posts standing in the tile. Each reaches down past the ground the tile draws, wherever the rail runs.
    posts: Vec<Post>,
    /// The cables starting in the tile: each its points on the map, its radius and colour.
    cables: Vec<(Vec<[f64; 3]>, f64, [f64; 3])>,
}

/// The world's tiles, as the scenery needs them: where the first starts on the map, and their side in metres.
pub struct Grid {
    pub south_west: DVec2,
    pub tile_m: f64,
}

impl Grid {
    fn tile(&self, p: DVec2) -> (usize, usize) {
        let k = ((p - self.south_west) / self.tile_m).floor();
        (k.x as usize, k.y as usize)
    }
}

/// Shares each region's scenery out between the tiles. `drawn` is the ground the full tiles draw, across the whole
/// exported part of the map, which seats each cable's ends and the rails. Fails if a model or a rail's texture has no
/// asset, if a model stands on an overlay or on no ground, or if a cable fastens to a model the world does not read or
/// comes too close to the ground.
pub fn share(
    sceneries: Vec<(Scenery, Vec<&'static str>)>,
    land: &Land,
    grid: &Grid,
    overlays: &[Overlay],
    raised: &[Raised],
    drawn: &Surface,
) -> Result<BTreeMap<(usize, usize), TileScenery>> {
    let inside = |p: DVec2| p.cmpge(land.low).all() && p.cmplt(land.high).all();
    let mut tiles: BTreeMap<(usize, usize), TileScenery> = BTreeMap::new();
    for (scenery, fastened) in sceneries {
        for placement in &scenery.placements {
            let (at, yaw, scale, precise) = effective_pose(raised, placement);
            if !inside(at) {
                continue;
            }
            crate::uri_of_asset(placement.model, "glb")?;
            if let Some(overlay) = on_overlay(overlays, at) {
                bail!("{} at {} stands on the overlay {overlay}", placement.model, at);
            }
            let entry = tiles.entry(grid.tile(at)).or_default().models.entry(placement.model).or_default();
            entry.push((at.to_array(), yaw, scale, placement.afar, precise));
        }
        let mut anchors: BTreeMap<&str, Vec<DVec3>> = BTreeMap::new();
        for model in &fastened {
            anchors.insert(model, read_anchors(model)?);
        }
        for cable in &scenery.cables {
            let ends = [cable.from, cable.to].map(|(placement, _)| &scenery.placements[placement]);
            if !ends.iter().all(|end| inside(effective_pose(raised, end).0)) {
                continue;
            }
            let [from, to] = [(ends[0], cable.from.1), (ends[1], cable.to.1)].map(|(placement, anchor)| {
                let model_anchors = anchors.get(placement.model).with_context(|| {
                    format!("a cable fastens to {}, which the world does not read", placement.model)
                })?;
                let local =
                    model_anchors.get(anchor).with_context(|| format!("{} has no anchor {anchor}", placement.model))?;
                cable_anchor(placement, *local, drawn, raised)
            });
            let (from, to) = (from?, to?);
            let span = from.distance(to);
            let mut points = Vec::new();
            for k in 0..=CABLE_PIECES {
                let t = k as f64 / CABLE_PIECES as f64;
                let p = from.lerp(to, t) - DVec3::Z * cable.sag * span * 4.0 * t * (1.0 - t);
                if p.z
                    < raised::height(raised, p.truncate(), |p| drawn.height(p)).unwrap_or(f64::NEG_INFINITY)
                        + CABLE_CLEARANCE_M
                {
                    bail!("a cable from {} comes within {CABLE_CLEARANCE_M} m of the ground at {p}", ends[0].model);
                }
                points.push(p.to_array());
            }
            tiles.entry(grid.tile(effective_pose(raised, ends[0]).0)).or_default().cables.push((
                points,
                cable.radius_m,
                cable.colour,
            ));
        }
        for rail in &scenery.rails {
            crate::uri_of_texture(rail.texture)?;
            // The rail is eased along each stretch with ground drawn under it: past the exported part of the map, it
            // is left out.
            for stretch in rail.path.chunk_by(|&p, &q| {
                raised::height(raised, p, |p| drawn.height(p)).is_some()
                    == raised::height(raised, q, |p| drawn.height(p)).is_some()
            }) {
                let Some(heights) = stretch
                    .iter()
                    .map(|&p| raised::height(raised, p, |p| drawn.height(p)))
                    .collect::<Option<Vec<f64>>>()
                else {
                    continue;
                };
                if stretch.len() < 2 {
                    continue;
                }
                let path: Vec<DVec3> = stretch.iter().zip(ease(stretch, &heights)).map(|(p, z)| p.extend(z)).collect();
                let top = rail.profile.iter().map(|&[_, height]| height).fold(0.0, f64::max) + POST_CAP_M;
                for &foot in path.iter().step_by(rail.post_every).filter(|foot| inside(foot.truncate())) {
                    let post = (foot.to_array(), top, rail.post_radius_m, rail.colour, rail.texture);
                    tiles.entry(grid.tile(foot.truncate())).or_default().posts.push(post);
                }
                for (tile, piece) in cut(&path, grid) {
                    if inside(piece[0].0.truncate()) {
                        let piece = piece.iter().map(|(p, d, along)| (p.to_array(), d.to_array(), *along)).collect();
                        let piece = (piece, rail.profile.clone(), rail.colour, rail.texture);
                        tiles.entry(tile).or_default().rails.push(piece);
                    }
                }
            }
        }
    }
    Ok(tiles)
}

/// The anchors of `model`, read from its export, in its own frame.
fn read_anchors(model: &str) -> Result<Vec<DVec3>> {
    let name = model.rsplit('/').next().unwrap_or(model);
    let glb = Glb::read(&Path::new(crate::ASSETS).join(model).join(format!("{name}.glb")))?;
    let rest = glb.rest()?;
    let mut anchors = Vec::new();
    while let Ok(node) = glb.node(&format!("anchor {}", anchors.len())) {
        let p = rest[node].translation;
        anchors.push(DVec3::new(p.x, -p.z, p.y));
    }
    Ok(anchors)
}

/// Preserve authored f32 poses near raised ownership; elsewhere keep the existing export behavior.
fn effective_pose(raised: &[Raised], placement: &Placement) -> (DVec2, f64, f64, bool) {
    let at = placement.at;
    let legacy = raised::stored((at * 1000.0).round() / 1000.0);
    let authored = raised::stored(at);
    let precise = [at, legacy, authored].into_iter().any(|p| raised::height(raised, p, |_| None).is_some());
    if precise {
        (authored, placement.yaw as f32 as f64, placement.scale as f32 as f64, true)
    } else {
        (at, placement.yaw, placement.scale, false)
    }
}

/// The world position of a cable anchor, seated on the surface owning its placement.
fn cable_anchor(placement: &Placement, local: DVec3, drawn: &Surface, raised: &[Raised]) -> Result<DVec3> {
    let (at, yaw, scale, _) = effective_pose(raised, placement);
    let seat = raised::height(raised, at, |p| drawn.height(p))
        .with_context(|| format!("{} stands on no ground", placement.model))?;
    Ok(at.extend(seat) + DMat3::from_rotation_z(yaw) * local * scale)
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

/// `heights` along `path`, each eased onto the straight line that best fits the heights within [`RAIL_EASE_M`] of it
/// along the path, the nearer weighing more. A steady slope stays as it is, up to the path's ends.
fn ease(path: &[DVec2], heights: &[f64]) -> Vec<f64> {
    let mut along = vec![0.0];
    for pair in path.windows(2) {
        along.push(along.last().unwrap() + pair[0].distance(pair[1]));
    }
    (0..path.len())
        .map(|k| {
            // Weighted least squares of height against distance from this point: the fitted height here is the
            // line's value at zero.
            let (mut w, mut wx, mut wxx, mut wy, mut wxy) = (0.0, 0.0, 0.0, 0.0, 0.0);
            for (n, &height) in heights.iter().enumerate() {
                let x = along[n] - along[k];
                let weight = 1.0 - x.abs() / (RAIL_EASE_M + 1.0);
                if x.abs() <= RAIL_EASE_M {
                    (w, wx, wxx, wy, wxy) = (
                        w + weight,
                        wx + weight * x,
                        wxx + weight * x * x,
                        wy + weight * height,
                        wxy + weight * x * height,
                    );
                }
            }
            let det = w * wxx - wx * wx;
            if det.abs() < 1e-9 { wy / w } else { (wxx * wy - wx * wxy) / det }
        })
        .collect()
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
    pub fn write(&self, glb: &mut Glb, surface: &Surface, raised: &[Raised], middle: bool, path: &Path) -> Result<()> {
        for (model, instances) in &self.models {
            let mut numbers = Vec::new();
            for &(at, yaw, scale, afar, precise) in instances {
                if middle && !afar {
                    continue;
                }
                let at = DVec2::from_array(at);
                let seat = raised::height(raised, at, |p| surface.height(p))
                    .with_context(|| format!("{}: {model} at {at} stands on no ground", path.display()))?;
                let p = game(at.extend(seat));
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
            let extras = json!({
                "model": crate::uri_of_asset(model, "glb")?,
                "detail": if middle { "middle" } else { "full" },
                "instances": numbers,
            });
            glb.add_data(model, extras);
        }
        if middle {
            return Ok(());
        }
        for (k, (piece, profile, colour, texture)) in self.rails.iter().enumerate() {
            let mut mesh = Mesh::default();
            rail(&mut mesh, piece, profile, surface, raised).with_context(|| path.display().to_string())?;
            mesh.material = glb.add_material(&painted("rail", *colour, &crate::uri_of_texture(texture)?, true));
            glb.add_mesh(&format!("rail {k}"), &[&mesh]);
        }
        for (k, &(foot, top, radius, colour, texture)) in self.posts.iter().enumerate() {
            let foot = DVec3::from_array(foot);
            let at = foot.truncate();
            let ground = raised::height(raised, at, |p| surface.height(p))
                .with_context(|| format!("{}: a rail's post at {at} stands on no ground", path.display()))?;
            let mut mesh = Mesh::default();
            tube(&mut mesh, &[(at.extend(ground - POST_DEPTH_M), radius), (at.extend(foot.z + top), radius)], 6, 1.0);
            in_metres(&mut mesh, 6, radius);
            mesh.material = glb.add_material(&painted("post", colour, &crate::uri_of_texture(texture)?, false));
            glb.add_mesh(&format!("post {k}"), &[&mesh]);
        }
        for (k, (points, radius, colour)) in self.cables.iter().enumerate() {
            let mut mesh = Mesh::default();
            let points: Vec<(DVec3, f64)> = points.iter().map(|&p| (DVec3::from_array(p), *radius)).collect();
            tube(&mut mesh, &points, 4, 1.0);
            mesh.material = glb.add_material(&plain("cable", *colour, false));
            glb.add_mesh(&format!("cable {k}"), &[&mesh]);
        }
        Ok(())
    }
}

/// A matte material of one colour.
fn plain(name: &str, colour: [f64; 3], two_sided: bool) -> Material<'_> {
    Material { name, texture: None, colour, cut_out: false, two_sided }
}

/// A matte material showing the image at `uri`, tinted by `colour`.
fn painted<'a>(name: &'a str, colour: [f64; 3], uri: &'a str, two_sided: bool) -> Material<'a> {
    Material { name, texture: Some(uri), colour, cut_out: false, two_sided }
}

/// Turns the texture positions of `mesh`, a straight two-ring [`tube`] with `sides` faces around and `radius`, into
/// metres: its sides' run along it already, and wrap once around it, so they stretch to its circumference; its caps'
/// span its diameter once, so they stretch to the diameter.
fn in_metres(mesh: &mut Mesh, sides: usize, radius: f64) {
    let rings = 2 * (sides + 1);
    for (k, uv) in mesh.uvs.iter_mut().enumerate() {
        if k < rings {
            uv[0] *= (TAU * radius) as f32;
        } else {
            *uv = uv.map(|c| c * (2.0 * radius) as f32);
        }
    }
}

/// Adds to `mesh` a rail through `piece`, its cross-section `profile` standing on each point's foot. Its texture runs
/// along it by each point's distance along the rail and across it by the distance around the profile, in metres, less
/// the whole metres before the piece starts, so the numbers stay small and the texture runs on across a cut. Fails
/// where the foot is more than [`RAIL_SETTLE_M`] from `surface`, the ground drawn under it.
fn rail(
    mesh: &mut Mesh,
    piece: &[RailPoint],
    profile: &[[f64; 2]],
    surface: &Surface,
    raised: &[Raised],
) -> Result<()> {
    let start = piece[0].2.floor();
    let mut around = vec![0.0];
    for pair in profile.windows(2) {
        around.push(around.last().unwrap() + DVec2::from_array(pair[0]).distance(DVec2::from_array(pair[1])));
    }
    let mut rows = Vec::new();
    for &(foot, direction, along) in piece {
        let (foot, direction) = (DVec3::from_array(foot), DVec2::from_array(direction));
        let (at, ground) = (foot.truncate(), foot.z);
        let drawn = raised::height(raised, at, |p| surface.height(p))
            .with_context(|| format!("a rail runs off the ground at {at}"))?;
        if (ground - drawn).abs() > RAIL_SETTLE_M {
            bail!("a rail at {at} runs {:.2} m from the ground, past {RAIL_SETTLE_M} m", ground - drawn);
        }
        let left = direction.perp();
        let row: Vec<u32> = profile
            .iter()
            .enumerate()
            .map(|(k, &[offset, height])| {
                // The normal is square to the profile's line here, in the plane across the rail.
                let [o0, h0] = profile[k.saturating_sub(1)];
                let [o1, h1] = profile[(k + 1).min(profile.len() - 1)];
                let normal = (left * (h1 - h0)).extend(o0 - o1);
                let p = (at + left * offset).extend(ground + height);
                let uv = DVec2::new(along - start, around[k]);
                vertex(mesh, p, if normal == DVec3::ZERO { DVec3::Z } else { normal }, uv, None)
            })
            .collect();
        rows.push(row);
    }
    for pair in rows.windows(2) {
        for k in 0..profile.len() - 1 {
            let (a, b, c, d) = (pair[0][k], pair[0][k + 1], pair[1][k + 1], pair[1][k]);
            mesh.indices.extend([a, d, c, a, c, b]);
        }
    }
    Ok(())
}

/// What a tile's checksum covers of its scenery.
pub fn checksum_bytes(scenery: &TileScenery) -> Vec<u8> {
    serde_json::to_vec(scenery).expect("scenery serializes")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cable_anchor_uses_the_declared_owner() {
        use crate::world::{Detail, Tile};
        let ground = Ground::page(8, 1.0, |_, _| 0.0);
        let drawn = Surface::new(&Tile { columns: (0, 8), rows: (0, 8) }.ground(&ground, Detail::Full, 0, 1.0));
        let p = |x, y| (DVec2::new(x, y), DVec2::ZERO);
        let raised = [Raised {
            name: "paving".into(),
            texture: "earth".into(),
            ground: true,
            height: 3.0,
            clearance: 0.1,
            triangles: vec![[p(1.0, 1.0), p(4.0, 1.0), p(1.0, 4.0)]],
        }];
        let mut placement = Placement { model: "pole", at: DVec2::new(2.0, 2.0), yaw: 0.0, scale: 1.0, afar: true };
        assert_eq!(cable_anchor(&placement, DVec3::Z * 2.0, &drawn, &raised).unwrap().z, 5.0);
        placement.at = DVec2::new(6.0, 6.0);
        assert_eq!(cable_anchor(&placement, DVec3::Z * 2.0, &drawn, &raised).unwrap().z, 2.0);
        placement.at = DVec2::new(0.9996, 1.0);
        placement.yaw = -163.6_f64.to_radians();
        let (at, yaw, _, precise) = effective_pose(&raised, &placement);
        assert!(precise);
        assert_eq!(at, raised::stored(placement.at));
        assert!(at.x < 1.0);
        assert_eq!(yaw, placement.yaw as f32 as f64);
        assert_eq!(cable_anchor(&placement, DVec3::Z * 2.0, &drawn, &raised).unwrap().z, 2.0);
        assert!(!effective_pose(&[], &placement).3);
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
            height: 3.0,
            clearance: 0.1,
            triangles: vec![[p(1.0, 1.0), p(4.0, 1.0), p(1.0, 4.0)]],
        }];
        let land =
            Land { ground: &ground, raised: &raised, low: DVec2::ZERO, high: DVec2::splat(8.0), exclusions: &[] };
        let grid = Grid { south_west: DVec2::ZERO, tile_m: 1.0 };
        let scenery = || Scenery {
            placements: vec![Placement {
                model: "props/utility-pole",
                at: DVec2::new(0.9996, 1.0),
                yaw: -163.6_f64.to_radians(),
                scale: 1.0,
                afar: true,
            }],
            ..Default::default()
        };
        let tiles = share(vec![(scenery(), vec![])], &land, &grid, &[], &raised, &drawn).unwrap();
        assert!(tiles.contains_key(&(0, 1)));
        assert!(!tiles.contains_key(&(1, 1)));
        let placed = &tiles[&(0, 1)].models["props/utility-pole"][0];
        assert_eq!(placed.0[0], 0.9996_f32 as f64);
        assert_eq!(placed.1, (-163.6_f64.to_radians()) as f32 as f64);
        assert!(placed.4);
        let mut glb = Glb::from_json(json!({"asset": {"version": "2.0"}}));
        tiles[&(0, 1)].write(&mut glb, &drawn, &raised, false, Path::new("test.glb")).unwrap();
        let numbers = glb.extras("props/utility-pole").unwrap()["instances"].as_array().unwrap();
        assert_eq!(numbers[0].as_f64().unwrap(), 0.9996_f32 as f64);
        assert_eq!(numbers[3].as_f64().unwrap(), (-163.6_f64.to_radians()) as f32 as f64);
        let overlay = Overlay {
            name: "path".into(),
            texture: "earth".into(),
            triangles: vec![[p(0.9, 1.0), p(1.0, 1.0), p(0.9, 2.0)]],
        };
        assert!(share(vec![(scenery(), vec![])], &land, &grid, &[overlay], &raised, &drawn).is_err());
    }

    #[test]
    fn clearances_filter_only_the_named_scatter_kind_and_are_local() {
        let ground = Ground::page(64, 2.0, |_, _| 0.0);
        let exclusion = Exclusion::corridor(&[[10.0, 20.0], [100.0, 20.0]], 5.0, &[ScatterKind::Tree]);
        let land = Land {
            ground: &ground,
            raised: &[],
            low: DVec2::ZERO,
            high: DVec2::splat(128.0),
            exclusions: &[exclusion],
        };
        assert!(!land.allows_scatter(DVec2::new(40.0, 22.0), ScatterKind::Tree));
        assert!(land.allows_scatter(DVec2::new(40.0, 22.0), ScatterKind::Bush));
        assert!(land.allows_scatter(DVec2::new(40.0, 30.0), ScatterKind::Tree));
        let clear = Land { exclusions: &[], ..land };
        let before: Vec<_> =
            clear.scatter(42, 5.0, 0.4, ScatterKind::Tree).filter(|(p, _)| p.y > 40.0).map(|(p, _)| p).collect();
        let after: Vec<_> =
            land.scatter(42, 5.0, 0.4, ScatterKind::Tree).filter(|(p, _)| p.y > 40.0).map(|(p, _)| p).collect();
        assert_eq!(before, after);
    }

    #[test]
    fn expanding_map_preserves_scatter_inside_original_bounds() {
        let ground = Ground::page(64, 2.0, |_, _| 0.0);
        let small =
            Land { ground: &ground, raised: &[], low: DVec2::splat(11.0), high: DVec2::splat(93.0), exclusions: &[] };
        let large = Land { ground: &ground, raised: &[], low: DVec2::ZERO, high: DVec2::splat(128.0), exclusions: &[] };
        let within = |p: &DVec2| p.cmpge(small.low).all() && p.cmplt(small.high).all();
        for side in [3.2, 5.0] {
            let candidates = |land: &Land| {
                land.scatter(42, side, 0.5, ScatterKind::Tree).map(|(p, _)| p).filter(within).collect::<Vec<_>>()
            };
            assert_eq!(candidates(&small), candidates(&large));
        }
    }

    /// A rail over bumpy ground bends gently, while still following the ground's slope.
    #[test]
    fn rails_ease_over_bumps() {
        let path: Vec<DVec2> = (0..60).map(|k| DVec2::new(k as f64, 0.0)).collect();
        let heights: Vec<f64> = (0..60).map(|k| 0.05 * k as f64 + if k % 2 == 0 { 0.1 } else { -0.1 }).collect();
        let eased = ease(&path, &heights);
        let bends = eased.windows(3).map(|h| (h[2] - 2.0 * h[1] + h[0]).abs());
        assert!(bends.fold(0.0, f64::max) < 0.05, "a rail bends more than 5 cm over a metre");
        for (k, (eased, height)) in eased.iter().zip(&heights).enumerate() {
            assert!((eased - height).abs() <= RAIL_SETTLE_M, "the rail leaves the ground at {k}");
        }
    }
}
