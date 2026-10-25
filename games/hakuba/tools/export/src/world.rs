//! The `world` kind: the ground and the road, cut into square tiles.
//!
//! The ground's shape is a heightmap; the road follows a smooth curve through the points in the asset's
//! `src/layout.rs`. Each tile is written twice under `tiles/`: `<column>_<row>.glb` in full detail, and
//! `<column>_<row>.middle.glb` with a coarser ground for seeing from afar. The coarse ground keeps every fine point on
//! the tile's edges, so neighbouring tiles meet exactly whichever version each one shows. `<folder name>.glb` holds
//! one empty node per tile, named `tile <column> <row>` and placed at the tile's centre, and one named `spawn`, where
//! the player starts, turned to face along the road.
//!
//! Columns count east from the map's west edge and rows count north from its south edge. The map's frame (x east,
//! y north, z up) becomes the game's (x east, y up, z south).

#[path = "../../../assets/world/src/layout.rs"]
mod layout;

use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use glam::{DQuat, DVec2, DVec3};
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::glb::{Glb, Mesh};

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Settings {
    /// The ground's heights in metres, as little-endian 32-bit floats, row by row from the south-west corner.
    heightmap: PathBuf,
    /// How many heights each row and column has.
    heightmap_samples: usize,
    /// The distance between neighbouring heights, in metres.
    heightmap_step_m: f64,
    /// How many heights apart tile edges are.
    tile_steps: usize,
    /// The first and the last tile exported, each as [column, row].
    tiles: [[usize; 2]; 2],
}

/// How many fine steps one coarse step of a middle tile spans.
const COARSE: usize = 4;

/// How far the road sits above the ground under it.
const ROAD_LIFT_M: f64 = 0.06;

/// How close the road may come to the ground under it before the export fails.
const ROAD_CLEARANCE_M: f64 = 0.01;

/// How often the road's texture repeats along it.
const ROAD_TEXTURE_M: f64 = 8.0;

pub fn export(folder: &Path, settings: &Settings, output: &Path) -> Result<()> {
    let ground = Ground::read(&folder.join(&settings.heightmap), settings.heightmap_samples, settings.heightmap_step_m)?;
    let road = road(&ground);
    let last = ground.samples - 1;
    let [[first_column, first_row], [last_column, last_row]] = settings.tiles;
    if last_column * settings.tile_steps >= last || last_row * settings.tile_steps >= last {
        bail!("the tiles run past the heightmap");
    }

    let tiles = folder.join("tiles");
    if tiles.exists() {
        fs::remove_dir_all(&tiles)?;
    }
    fs::create_dir(&tiles)?;
    let mut index = Glb::from_json(json!({ "asset": { "version": "2.0" } }));
    for column in first_column..=last_column {
        for row in first_row..=last_row {
            let span = |k: usize| (k * settings.tile_steps, ((k + 1) * settings.tile_steps).min(last));
            let tile = Tile { columns: span(column), rows: span(row) };
            for (detail, name) in [(Detail::Full, format!("{column}_{row}.glb")), (Detail::Middle, format!("{column}_{row}.middle.glb"))] {
                tile.write(&ground, &road, detail, &tiles.join(name))?;
            }
            let centre = ground.at((tile.columns.0 + tile.columns.1) as f64 / 2.0, (tile.rows.0 + tile.rows.1) as f64 / 2.0);
            index.add_marker(&format!("tile {column} {row}"), game(centre), DQuat::IDENTITY);
        }
    }
    let spawn = road.points[layout::SPAWN_ALONG_ROAD_M];
    let heading = road.tangents[layout::SPAWN_ALONG_ROAD_M];
    let facing = DQuat::from_rotation_y((-heading.x).atan2(heading.y));
    index.add_marker("spawn", game(spawn), facing);
    index.write(output)
}

/// The ground's heights on a square grid centred on the map's origin.
struct Ground {
    heights: Vec<f32>,
    samples: usize,
    step: f64,
}

impl Ground {
    fn read(path: &Path, samples: usize, step: f64) -> Result<Self> {
        let bytes = fs::read(path).with_context(|| format!("reading {}", path.display()))?;
        if bytes.len() != samples * samples * 4 {
            bail!("{}: expected {samples} × {samples} heights", path.display());
        }
        let heights = bytes.chunks(4).map(|b| f32::from_le_bytes(b.try_into().unwrap())).collect();
        Ok(Self { heights, samples, step })
    }

    /// The map position of the grid point `i` columns and `j` rows from the south-west corner, which may fall
    /// between points.
    fn position(&self, i: f64, j: f64) -> DVec2 {
        let half = (self.samples - 1) as f64 * self.step / 2.0;
        DVec2::new(i * self.step - half, j * self.step - half)
    }

    /// The point on the ground at grid position (`i`, `j`).
    fn at(&self, i: f64, j: f64) -> DVec3 {
        let p = self.position(i, j);
        p.extend(self.height(p))
    }

    /// The ground's height at `p`, blended between the four nearest heights.
    fn height(&self, p: DVec2) -> f64 {
        let half = (self.samples - 1) as f64 * self.step / 2.0;
        let (fx, fy) = ((p.x + half) / self.step, (p.y + half) / self.step);
        let last = self.samples - 2;
        let (i, j) = ((fx.max(0.0) as usize).min(last), (fy.max(0.0) as usize).min(last));
        let (u, v) = (fx - i as f64, fy - j as f64);
        let h = |i: usize, j: usize| self.heights[j * self.samples + i] as f64;
        h(i, j) * (1.0 - u) * (1.0 - v) + h(i + 1, j) * u * (1.0 - v) + h(i, j + 1) * (1.0 - u) * v + h(i + 1, j + 1) * u * v
    }

    /// The ground's up direction at `p`.
    fn normal(&self, p: DVec2) -> DVec3 {
        let (dx, dy) = (DVec2::X * self.step, DVec2::Y * self.step);
        let slope_x = (self.height(p + dx) - self.height(p - dx)) / (2.0 * self.step);
        let slope_y = (self.height(p + dy) - self.height(p - dy)) / (2.0 * self.step);
        DVec3::new(-slope_x, -slope_y, 1.0).normalize()
    }
}

/// The road's centre line, one point a metre, with the direction it runs at each.
struct Road {
    points: Vec<DVec3>,
    tangents: Vec<DVec2>,
}

/// The road on `ground`: a Catmull-Rom curve through the layout's points, one point every metre along it. The
/// heightmap already holds the road's cut, so the road takes its heights from the ground.
fn road(ground: &Ground) -> Road {
    let control: Vec<DVec2> = layout::ROAD.iter().map(|&[x, y]| DVec2::new(x, y)).collect();
    let padded: Vec<DVec2> = [control[0]].into_iter().chain(control.iter().copied()).chain([control[control.len() - 1]]).collect();
    let mut curve = Vec::new();
    for k in 1..padded.len() - 2 {
        let (p0, p1, p2, p3) = (padded[k - 1], padded[k], padded[k + 1], padded[k + 2]);
        for step in 0..60 {
            let s = step as f64 / 60.0;
            curve.push(0.5 * (2.0 * p1 + (p2 - p0) * s + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * s * s + (3.0 * p1 - p0 - 3.0 * p2 + p3) * s * s * s));
        }
    }
    let mut lengths = vec![0.0];
    for pair in curve.windows(2) {
        lengths.push(lengths.last().unwrap() + pair[0].distance(pair[1]));
    }
    let mut flat = Vec::new();
    let mut segment = 0;
    let mut along = 0.0;
    while along < *lengths.last().unwrap() {
        while lengths[segment + 1] < along {
            segment += 1;
        }
        let t = (along - lengths[segment]) / (lengths[segment + 1] - lengths[segment]);
        flat.push(curve[segment].lerp(curve[segment + 1], t));
        along += 1.0;
    }
    let last = flat.len() - 1;
    let tangents = (0..flat.len()).map(|i| (flat[(i + 1).min(last)] - flat[i.saturating_sub(1)]).normalize()).collect();
    Road { points: flat.iter().map(|&p| p.extend(ground.height(p))).collect(), tangents }
}

#[derive(Clone, Copy, PartialEq)]
enum Detail {
    Full,
    Middle,
}

/// One tile: the grid columns and rows it spans, first and last.
struct Tile {
    columns: (usize, usize),
    rows: (usize, usize),
}

impl Tile {
    fn write(&self, ground: &Ground, road: &Road, detail: Detail, path: &Path) -> Result<()> {
        let mut glb = Glb::from_json(json!({ "asset": { "version": "2.0" } }));
        let ground_material = glb.add_material("ground", linear(layout::GROUND));
        let road_material = glb.add_material("road", linear(layout::ROAD_COLOUR));
        let ground_mesh = self.ground(ground, detail, ground_material);
        let drawn = Surface::new(&ground_mesh);
        let road_mesh = self.road(ground, &drawn, road, road_material);
        check_road_above(&drawn, &road_mesh).with_context(|| format!("writing {}", path.display()))?;
        glb.add_mesh("ground", &ground_mesh);
        if !road_mesh.indices.is_empty() {
            glb.add_mesh("road", &road_mesh);
        }
        glb.write(path)
    }

    /// The ground in this tile. In full detail every grid square is two triangles. In middle detail the squares are
    /// `COARSE` steps wide; each is a fan around its centre through its corners and, on the tile's edges, every fine
    /// point along them.
    fn ground(&self, ground: &Ground, detail: Detail, material: usize) -> Mesh {
        let mut mesh = Mesh { material, ..Mesh::default() };
        let mut points: HashMap<(usize, usize), u32> = HashMap::new();
        let vertex = |mesh: &mut Mesh, i: f64, j: f64| {
            let p = ground.at(i, j);
            mesh.positions.push(game(p).as_vec3().to_array());
            mesh.normals.push(game_direction(ground.normal(p.truncate())).as_vec3().to_array());
            (mesh.positions.len() - 1) as u32
        };
        let mut point = |mesh: &mut Mesh, i: usize, j: usize| *points.entry((i, j)).or_insert_with(|| vertex(mesh, i as f64, j as f64));
        if detail == Detail::Full {
            for j in self.rows.0..self.rows.1 {
                for i in self.columns.0..self.columns.1 {
                    let [a, b, c, d] = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)].map(|(i, j)| point(&mut mesh, i, j));
                    mesh.indices.extend([a, b, c, a, c, d]);
                }
            }
            return mesh;
        }
        let coarse = |(first, last): (usize, usize)| {
            let mut stops: Vec<usize> = (first..last).step_by(COARSE).collect();
            stops.push(last);
            stops
        };
        let (columns, rows) = (coarse(self.columns), coarse(self.rows));
        for pair_j in rows.windows(2) {
            for pair_i in columns.windows(2) {
                let ((i0, i1), (j0, j1)) = ((pair_i[0], pair_i[1]), (pair_j[0], pair_j[1]));
                // The square's outline, counter-clockwise seen from above, through every fine point on a tile edge.
                let mut outline = Vec::new();
                let side = |on_edge: bool, from: usize, to: usize| -> Vec<usize> {
                    if !on_edge {
                        return vec![from];
                    }
                    if from < to { (from..to).collect() } else { (to + 1..=from).rev().collect() }
                };
                outline.extend(side(j0 == self.rows.0, i0, i1).into_iter().map(|i| (i, j0)));
                outline.extend(side(i1 == self.columns.1, j0, j1).into_iter().map(|j| (i1, j)));
                outline.extend(side(j1 == self.rows.1, i1, i0).into_iter().map(|i| (i, j1)));
                outline.extend(side(i0 == self.columns.0, j1, j0).into_iter().map(|j| (i0, j)));
                let centre = vertex(&mut mesh, (i0 + i1) as f64 / 2.0, (j0 + j1) as f64 / 2.0);
                let outline: Vec<u32> = outline.into_iter().map(|(i, j)| point(&mut mesh, i, j)).collect();
                for k in 0..outline.len() {
                    mesh.indices.extend([centre, outline[k], outline[(k + 1) % outline.len()]]);
                }
            }
        }
        mesh
    }


    /// The road over this tile's ground. Each metre of road is two triangles, cut along the edges of the ground
    /// triangles under them. Each cut piece lies `ROAD_LIFT_M` above its ground triangle, so the road follows the
    /// ground exactly and stops at the tile's edge. The texture spans the road's width and repeats every
    /// `ROAD_TEXTURE_M` along it.
    fn road(&self, ground: &Ground, drawn: &Surface, road: &Road, material: usize) -> Mesh {
        let mut mesh = Mesh { material, ..Mesh::default() };
        let half = layout::ROAD_WIDTH_M / 2.0;
        let corner = |i: usize, u: f64| {
            let p = road.points[i].truncate() + road.tangents[i].perp() * half * (2.0 * u - 1.0);
            (p, DVec2::new(u, i as f64 / ROAD_TEXTURE_M))
        };
        for k in 0..road.points.len() - 1 {
            let [right, left, next_right, next_left] = [corner(k, 0.0), corner(k, 1.0), corner(k + 1, 0.0), corner(k + 1, 1.0)];
            for piece in [[next_right, next_left, left], [next_right, left, right]] {
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
                        let on_road = weights(outline, p).expect("a road triangle has area");
                        let height = on_ground.x * under[0].z + on_ground.y * under[1].z + on_ground.z * under[2].z;
                        let uv = on_road.x * piece[0].1 + on_road.y * piece[1].1 + on_road.z * piece[2].1;
                        mesh.positions.push(game(p.extend(height + ROAD_LIFT_M)).as_vec3().to_array());
                        mesh.normals.push(game_direction(ground.normal(p)).as_vec3().to_array());
                        mesh.uvs.push(uv.as_vec2().to_array());
                    }
                    for n in 1..cut.len() as u32 - 1 {
                        mesh.indices.extend([first, first + n, first + n + 1]);
                    }
                }
            }
        }
        mesh
    }
}

/// A mesh's triangles in the map's frame, to find what lies under a point.
struct Surface {
    triangles: Vec<[DVec3; 3]>,
    /// The triangles that reach into each square of `SURFACE_CELL_M`, by square.
    cells: HashMap<(i64, i64), Vec<usize>>,
}

/// The side of the squares a [`Surface`] sorts its triangles into.
const SURFACE_CELL_M: f64 = 4.0;

/// How far outside a triangle a point may be, as a share of the triangle, and still count as on it. Meshes store
/// positions in 32-bit floats, so points on a shared edge can land a hair to either side.
const ON_TRIANGLE: f64 = 1e-4;

impl Surface {
    fn new(mesh: &Mesh) -> Self {
        let corner = |k: u32| {
            let [x, y, z] = mesh.positions[k as usize].map(f64::from);
            DVec3::new(x, -z, y)
        };
        let triangles: Vec<[DVec3; 3]> = mesh.indices.chunks(3).map(|t| [corner(t[0]), corner(t[1]), corner(t[2])]).collect();
        let mut cells: HashMap<(i64, i64), Vec<usize>> = HashMap::new();
        for (n, triangle) in triangles.iter().enumerate() {
            for square in squares(triangle.map(DVec3::truncate)) {
                cells.entry(square).or_default().push(n);
            }
        }
        Self { triangles, cells }
    }

    /// The triangles that may lie under any part of `outline`.
    fn under(&self, outline: [DVec2; 3]) -> Vec<[DVec3; 3]> {
        let mut found: Vec<usize> = squares(outline).filter_map(|square| self.cells.get(&square)).flatten().copied().collect();
        found.sort();
        found.dedup();
        found.into_iter().map(|n| self.triangles[n]).collect()
    }

    /// The height of the triangle under `p`, if any.
    fn height(&self, p: DVec2) -> Option<f64> {
        let square = ((p.x / SURFACE_CELL_M).floor() as i64, (p.y / SURFACE_CELL_M).floor() as i64);
        self.cells.get(&square)?.iter().find_map(|&n| {
            let [a, b, c] = self.triangles[n];
            let w = weights([a, b, c].map(DVec3::truncate), p)?;
            (w.min_element() >= -ON_TRIANGLE).then_some(w.x * a.z + w.y * b.z + w.z * c.z)
        })
    }
}

/// The squares of `SURFACE_CELL_M` that the box around `triangle` reaches into.
fn squares(triangle: [DVec2; 3]) -> impl Iterator<Item = (i64, i64)> {
    let [a, b, c] = triangle;
    let square = |x: f64| (x / SURFACE_CELL_M).floor() as i64;
    let (low, high) = (a.min(b).min(c), a.max(b).max(c));
    (square(low.x)..=square(high.x)).flat_map(move |i| (square(low.y)..=square(high.y)).map(move |j| (i, j)))
}

/// How much each corner of `triangle` weighs in `p`; the three weights add up to one. None if the triangle has no
/// area.
fn weights(triangle: [DVec2; 3], p: DVec2) -> Option<DVec3> {
    let [a, b, c] = triangle;
    let area = (b - a).perp_dot(c - a);
    if area.abs() < 1e-12 {
        return None;
    }
    let (s, t) = ((p - a).perp_dot(c - a) / area, (b - a).perp_dot(p - a) / area);
    Some(DVec3::new(1.0 - s - t, s, t))
}

/// The part of the convex `polygon` inside `triangle`, its corners in the polygon's order.
fn cut(mut polygon: Vec<DVec2>, triangle: [DVec2; 3]) -> Vec<DVec2> {
    let turn = (triangle[1] - triangle[0]).perp_dot(triangle[2] - triangle[0]).signum();
    for k in 0..3 {
        let (a, b) = (triangle[k], triangle[(k + 1) % 3]);
        let side = |p: DVec2| turn * (b - a).perp_dot(p - a);
        let mut kept = Vec::new();
        for n in 0..polygon.len() {
            let (p, q) = (polygon[n], polygon[(n + 1) % polygon.len()]);
            let (sp, sq) = (side(p), side(q));
            if sp >= 0.0 {
                kept.push(p);
            }
            if (sp >= 0.0) != (sq >= 0.0) {
                kept.push(p + (q - p) * (sp / (sp - sq)));
            }
        }
        polygon = kept;
        if polygon.is_empty() {
            break;
        }
    }
    let area: f64 = (1..polygon.len().saturating_sub(1)).map(|n| (polygon[n] - polygon[0]).perp_dot(polygon[n + 1] - polygon[0])).sum();
    if area.abs() < 1e-8 { Vec::new() } else { polygon }
}

/// Fails if the road comes closer than `ROAD_CLEARANCE_M` to the ground drawn under it anywhere, checking points
/// spread over each of its triangles.
fn check_road_above(drawn: &Surface, road: &Mesh) -> Result<()> {
    const SPLITS: u32 = 4;
    for [a, b, c] in Surface::new(road).triangles {
        for s in 0..=SPLITS {
            for t in 0..=SPLITS - s {
                let p = a + (b - a) * (s as f64 / SPLITS as f64) + (c - a) * (t as f64 / SPLITS as f64);
                let Some(under) = drawn.height(p.truncate()) else {
                    bail!("the road runs off the tile's ground at ({:.1}, {:.1})", p.x, p.y);
                };
                if p.z - under < ROAD_CLEARANCE_M {
                    bail!("the road comes within {:.3} m of the ground at ({:.1}, {:.1})", p.z - under, p.x, p.y);
                }
            }
        }
    }
    Ok(())
}

/// A map position in the game's frame.
fn game(p: DVec3) -> DVec3 {
    DVec3::new(p.x, p.z, -p.y)
}

/// A map direction in the game's frame.
fn game_direction(d: DVec3) -> DVec3 {
    DVec3::new(d.x, d.z, -d.y)
}

/// An sRGB colour as the linear colour glTF stores.
fn linear(srgb: [f64; 3]) -> [f32; 3] {
    srgb.map(|c| (if c <= 0.04045 { c / 12.92 } else { ((c + 0.055) / 1.055).powf(2.4) }) as f32)
}
