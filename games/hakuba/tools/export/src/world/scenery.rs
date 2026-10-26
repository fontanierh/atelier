//! Scenery: the models regions stand on the ground, such as trees, bushes, grass and poles, the cables strung between
//! their anchors, and the rails run along roads.
//!
//! Each model stands in the tile its foot is in, seated on the ground that tile's version draws: one data node per
//! model and version, named after the model's folder, whose extras hold
//! `{ "model": <its .glb, relative to the tile>, "detail": "full" | "middle", "instances": [x, y, z, yaw, scale, ...] }`
//! in the game's frame, yaw turning about y. A middle tile holds only the models seen from afar. Rails and cables are
//! meshes of full tiles only: a rail follows the ground drawn under it, eased along its whole length so that it bends
//! smoothly over the ground's small bumps, then is cut at each tile's edge; a cable
//! belongs to the tile of the model it starts from.

use std::collections::BTreeMap;
use std::path::Path;

use anyhow::{Context, Result, bail};
use glam::{DMat3, DVec2, DVec3};
use serde::Serialize;
use serde_json::json;

use super::game;
use super::ground::Ground;
use super::overlay::Overlay;
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
    /// Its linear colour, and its posts'.
    pub colour: [f64; 3],
}

/// The land a region fills: the ground, and the part of the map the world exports.
pub struct Land<'a> {
    pub ground: &'a Ground,
    pub low: DVec2,
    pub high: DVec2,
}

impl Land<'_> {
    /// The ground's height at `p`, if there is ground there.
    pub fn height(&self, p: DVec2) -> Option<f64> {
        self.ground.height(p)
    }

    /// How steep the ground is at `p`: how far it rises per metre across, going straight uphill.
    pub fn slope(&self, p: DVec2) -> f64 {
        let up = self.ground.normal(p);
        up.truncate().length() / up.z
    }

    /// A point scattered in each square of a grid of `side` metres (see [`Land::squares`]), up to `jitter` of a side
    /// from the square's centre either way, with the square's own stream of random numbers, drawn from `seed`.
    pub fn scatter(&self, seed: u64, side: f64, jitter: f64) -> impl Iterator<Item = (DVec2, Random)> {
        self.squares(side).map(move |(column, row, corner)| {
            let mut random = Random::at(seed, column, row);
            let offset = DVec2::new(random.range([-jitter, jitter]), random.range([-jitter, jitter]));
            (corner + (DVec2::splat(0.5) + offset) * side, random)
        })
    }

    /// The squares of a grid of `side` metres, counted from the map's origin, whose lower-left corners lie in the
    /// exported part of the map: each square's column, row and lower-left corner. A grid anchored at the origin
    /// keeps every square in its place, however much of the map is exported.
    pub fn squares(&self, side: f64) -> impl Iterator<Item = (i64, i64, DVec2)> {
        let (low, high) = ((self.low / side).ceil(), (self.high / side).floor());
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
type Placed = ([f64; 2], f64, f64, bool);

/// A piece of a rail: its points with the height of its foot, the rail's direction at each, its profile and colour.
type RailPiece = (Vec<([f64; 3], [f64; 2])>, Vec<[f64; 2]>, [f64; 3]);

/// A piece of a path within one tile: the tile, and each point with the path's direction there, in plan.
type PathPiece = ((usize, usize), Vec<(DVec3, DVec2)>);

/// What one tile holds of the scenery, ready to write. Its checksum covers all of it.
#[derive(Serialize, Default)]
pub struct TileScenery {
    /// The models standing in the tile, by folder.
    models: BTreeMap<&'static str, Vec<Placed>>,
    /// The pieces of rails in the tile.
    rails: Vec<RailPiece>,
    /// The rails' posts standing in the tile: each its foot on the eased rail, its height above that, its radius and
    /// colour. Each reaches down past the ground the tile draws, wherever the rail runs.
    posts: Vec<([f64; 3], f64, f64, [f64; 3])>,
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
/// exported part of the map, which seats each cable's ends and the rails. Fails if a model has no asset, stands on an overlay or
/// on no ground, or if a cable fastens to a model the world does not read or comes too close to the ground.
pub fn share(
    sceneries: Vec<(Scenery, Vec<&'static str>)>,
    land: &Land,
    grid: &Grid,
    overlays: &[Overlay],
    drawn: &Surface,
) -> Result<BTreeMap<(usize, usize), TileScenery>> {
    let inside = |p: DVec2| p.cmpge(land.low).all() && p.cmplt(land.high).all();
    let mut tiles: BTreeMap<(usize, usize), TileScenery> = BTreeMap::new();
    for (scenery, fastened) in sceneries {
        for placement in scenery.placements.iter().filter(|placement| inside(placement.at)) {
            crate::uri_of_asset(placement.model, "glb")?;
            if let Some(overlay) = on_overlay(overlays, placement.at) {
                bail!("{} at {} stands on the overlay {overlay}", placement.model, placement.at);
            }
            let entry = tiles.entry(grid.tile(placement.at)).or_default().models.entry(placement.model).or_default();
            entry.push((placement.at.to_array(), placement.yaw, placement.scale, placement.afar));
        }
        let mut anchors: BTreeMap<&str, Vec<DVec3>> = BTreeMap::new();
        for model in &fastened {
            anchors.insert(model, read_anchors(model)?);
        }
        for cable in &scenery.cables {
            let ends = [cable.from, cable.to].map(|(placement, _)| &scenery.placements[placement]);
            if !ends.iter().all(|end| inside(end.at)) {
                continue;
            }
            let [from, to] = [(ends[0], cable.from.1), (ends[1], cable.to.1)].map(|(placement, anchor)| {
                let model_anchors = anchors.get(placement.model).with_context(|| {
                    format!("a cable fastens to {}, which the world does not read", placement.model)
                })?;
                let local =
                    model_anchors.get(anchor).with_context(|| format!("{} has no anchor {anchor}", placement.model))?;
                let seat =
                    drawn.height(placement.at).with_context(|| format!("{} stands on no ground", placement.model))?;
                Ok::<_, anyhow::Error>(
                    placement.at.extend(seat) + DMat3::from_rotation_z(placement.yaw) * *local * placement.scale,
                )
            });
            let (from, to) = (from?, to?);
            let span = from.distance(to);
            let mut points = Vec::new();
            for k in 0..=CABLE_PIECES {
                let t = k as f64 / CABLE_PIECES as f64;
                let p = from.lerp(to, t) - DVec3::Z * cable.sag * span * 4.0 * t * (1.0 - t);
                if p.z < drawn.height(p.truncate()).unwrap_or(f64::NEG_INFINITY) + CABLE_CLEARANCE_M {
                    bail!("a cable from {} comes within {CABLE_CLEARANCE_M} m of the ground at {p}", ends[0].model);
                }
                points.push(p.to_array());
            }
            tiles.entry(grid.tile(ends[0].at)).or_default().cables.push((points, cable.radius_m, cable.colour));
        }
        for rail in &scenery.rails {
            // The rail is eased along each stretch with ground drawn under it: past the exported part of the map, it
            // is left out.
            for stretch in rail.path.chunk_by(|&p, &q| drawn.height(p).is_some() == drawn.height(q).is_some()) {
                let Some(heights) = stretch.iter().map(|&p| drawn.height(p)).collect::<Option<Vec<f64>>>() else {
                    continue;
                };
                if stretch.len() < 2 {
                    continue;
                }
                let path: Vec<DVec3> = stretch.iter().zip(ease(stretch, &heights)).map(|(p, z)| p.extend(z)).collect();
                let top = rail.profile.iter().map(|&[_, height]| height).fold(0.0, f64::max) + POST_CAP_M;
                for &foot in path.iter().step_by(rail.post_every).filter(|foot| inside(foot.truncate())) {
                    let post = (foot.to_array(), top, rail.post_radius_m, rail.colour);
                    tiles.entry(grid.tile(foot.truncate())).or_default().posts.push(post);
                }
                for (tile, piece) in cut(&path, grid) {
                    if inside(piece[0].0.truncate()) {
                        let piece = piece.iter().map(|(p, d)| (p.to_array(), d.to_array())).collect();
                        tiles.entry(tile).or_default().rails.push((piece, rail.profile.clone(), rail.colour));
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
/// there, in plan. A point where the path crosses an edge ends one piece and starts the next, so the pieces meet
/// exactly.
fn cut(path: &[DVec3], grid: &Grid) -> Vec<PathPiece> {
    let direction = |k: usize| (path[(k + 1).min(path.len() - 1)] - path[k.saturating_sub(1)]).truncate().normalize();
    let mut pieces: Vec<PathPiece> = Vec::new();
    for k in 0..path.len() - 1 {
        let (a, b) = (path[k], path[k + 1]);
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
                0.0 => (p, direction(k)),
                1.0 => (p, direction(k + 1)),
                _ => (p, (b - a).truncate().normalize()),
            };
            match pieces.last_mut() {
                Some((last, points)) if *last == tile => points.push(at(t1, end)),
                _ => pieces.push((tile, vec![at(t0, start), at(t1, end)])),
            }
        }
    }
    pieces
}

impl TileScenery {
    /// Adds what the tile holds to `glb`, its models seated on `surface`, the ground this version draws.
    pub fn write(&self, glb: &mut Glb, surface: &Surface, middle: bool, path: &Path) -> Result<()> {
        for (model, instances) in &self.models {
            let mut numbers = Vec::new();
            for &(at, yaw, scale, afar) in instances {
                if middle && !afar {
                    continue;
                }
                let at = DVec2::from_array(at);
                let seat = surface
                    .height(at)
                    .with_context(|| format!("{}: {model} at {at} stands on no ground", path.display()))?;
                let p = game(at.extend(seat));
                numbers.extend([p.x, p.y, p.z, yaw, scale].map(|v| (v * 1000.0).round() / 1000.0));
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
        for (k, (piece, profile, colour)) in self.rails.iter().enumerate() {
            let mut mesh = Mesh::default();
            rail(&mut mesh, piece, profile, surface).with_context(|| path.display().to_string())?;
            mesh.material = glb.add_material(&plain("rail", *colour, true));
            glb.add_mesh(&format!("rail {k}"), &[&mesh]);
        }
        for (k, &(foot, top, radius, colour)) in self.posts.iter().enumerate() {
            let foot = DVec3::from_array(foot);
            let at = foot.truncate();
            let ground = surface
                .height(at)
                .with_context(|| format!("{}: a rail's post at {at} stands on no ground", path.display()))?;
            let mut mesh = Mesh::default();
            tube(&mut mesh, &[(at.extend(ground - POST_DEPTH_M), radius), (at.extend(foot.z + top), radius)], 6, 1.0);
            mesh.material = glb.add_material(&plain("post", colour, false));
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

/// Adds to `mesh` a rail through `piece`, its cross-section `profile` standing on each point's foot. Fails where the
/// foot is more than [`RAIL_SETTLE_M`] from `surface`, the ground drawn under it.
fn rail(mesh: &mut Mesh, piece: &[([f64; 3], [f64; 2])], profile: &[[f64; 2]], surface: &Surface) -> Result<()> {
    let mut rows = Vec::new();
    for &(foot, direction) in piece {
        let (foot, direction) = (DVec3::from_array(foot), DVec2::from_array(direction));
        let (at, ground) = (foot.truncate(), foot.z);
        let drawn = surface.height(at).with_context(|| format!("a rail runs off the ground at {at}"))?;
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
                let uv = DVec2::new(k as f64, 0.0);
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
