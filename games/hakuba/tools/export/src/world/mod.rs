//! The `world` kind: the ground, and what each region lays over it, cut into square tiles.
//!
//! The ground is one grid of heights across the world, stored in square pages under `src/ground/`. Each region
//! lives in its own folder under `src/regions/`; its `layout.rs` says what it adds (`regions.rs` lists them). Each
//! tile is written twice under `tiles/`: `<column>_<row>.glb` in full detail, and `<column>_<row>.middle.glb` with a
//! coarser ground for seeing from afar. The coarse ground keeps every fine point on the tile's edges, so neighbouring tiles meet exactly
//! whichever version each one shows. `<folder name>.glb` holds one empty node per tile, named
//! `tile <column> <row>` and placed at the tile's centre, and one named `spawn`, where the player starts.
//!
//! An export rewrites only the tiles whose inputs changed since the last one ([`checksums`]), so an edit costs the
//! tiles it touches.
//!
//! Pages and tiles count columns east and rows north from the world's south-west corner. The map's frame (x east,
//! y north, z up) becomes the game's (x east, y up, z south).

mod checksums;
mod curve;
mod ground;
mod overlay;
mod regions;
mod ribbon;
mod scenery;
mod surface;

use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use glam::{DQuat, DVec2, DVec3};
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::glb::{Glb, Material, Mesh, y_up as game};
use ground::Ground;
use overlay::Overlay;
use scenery::{Grid, Land, TileScenery};
use surface::Surface;

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Settings {
    /// The folder of the ground's pages.
    ground: PathBuf,
    /// The world's south-west corner on the map, where the first page and the first tile start.
    south_west_m: [f64; 2],
    /// The distance between neighbouring heights, in metres.
    ground_step_m: f64,
    /// How many steps each page spans.
    page_steps: usize,
    /// How many steps each tile spans.
    tile_steps: usize,
    /// The first and the last tile exported, each as [column, row].
    tiles: [[usize; 2]; 2],
    /// The texture the ground shows, by its folder name under `assets/textures/`.
    ground_texture: String,
    /// How far apart the ground's texture repeats, in metres.
    ground_texture_m: f64,
    /// Where the player starts, on the map.
    spawn_m: [f64; 2],
    /// Which way the player faces at the start, as a compass bearing east of north.
    spawn_bearing_deg: f64,
}

/// How many fine steps one coarse step of a middle tile spans.
const COARSE: usize = 4;

/// The assets the world reads: the models whose anchors the regions' cables fasten to.
pub fn reads() -> Vec<String> {
    let mut reads: Vec<String> =
        regions::REGIONS.iter().flat_map(|region| region.fastens_to()).map(String::from).collect();
    reads.sort();
    reads.dedup();
    reads
}

pub fn export(folder: &Path, settings: &Settings, output: &Path) -> Result<()> {
    let [x, y] = settings.south_west_m;
    let ground =
        Ground::read(&folder.join(&settings.ground), settings.page_steps, settings.ground_step_m, DVec2::new(x, y))?;
    let mut overlays = Vec::new();
    for region in regions::REGIONS {
        for mut overlay in region.overlays() {
            overlay.name = format!("{} {}", region.name(), overlay.name);
            overlays.push(overlay);
        }
    }
    for texture in overlays.iter().map(|overlay| &overlay.texture).chain([&settings.ground_texture]) {
        crate::uri_of_texture(texture)?;
    }
    let [[first_column, first_row], [last_column, last_row]] = settings.tiles;
    let span = |k: usize| (k * settings.tile_steps, (k + 1) * settings.tile_steps);
    let whole =
        Tile { columns: (span(first_column).0, span(last_column).1), rows: (span(first_row).0, span(last_row).1) };
    if !ground.covers(whole.columns, whole.rows) {
        bail!("the tiles reach past the ground");
    }
    let land = Land {
        ground: &ground,
        low: ground.position(whole.columns.0 as f64, whole.rows.0 as f64),
        high: ground.position(whole.columns.1 as f64, whole.rows.1 as f64),
    };
    let grid = Grid { south_west: DVec2::new(x, y), tile_m: settings.tile_steps as f64 * settings.ground_step_m };
    // The full tiles' ground across the whole exported map, which seats the cables' ends.
    let drawn = Surface::new(&whole.ground(&ground, Detail::Full, 0, 1.0));
    let sceneries = regions::REGIONS.iter().map(|region| (region.scenery(&land), region.fastens_to())).collect();
    let mut scenery = scenery::share(sceneries, &land, &grid, &overlays, &drawn)?;

    let tiles = folder.join("tiles");
    fs::create_dir_all(&tiles)?;
    let previous = checksums::read(&tiles)?;
    let mut current = BTreeMap::new();
    let code = checksums::code()?;
    let tile_settings = serde_json::to_vec(&json!([
        settings.south_west_m,
        settings.ground_step_m,
        settings.tile_steps,
        settings.ground_texture,
        settings.ground_texture_m
    ]))?;
    let mut rebuilt = 0;
    let mut index = Glb::from_json(json!({ "asset": { "version": "2.0" } }));
    for column in first_column..=last_column {
        for row in first_row..=last_row {
            let tile = Tile { columns: span(column), rows: span(row) };
            let tile_scenery = scenery.remove(&(column, row)).unwrap_or_default();
            let stem = format!("{column}_{row}");
            let files = [
                (Detail::Full, tiles.join(format!("{stem}.glb"))),
                (Detail::Middle, tiles.join(format!("{stem}.middle.glb"))),
            ];
            let checksum = tile.checksum(&code, &tile_settings, &ground, &overlays, &tile_scenery);
            if previous.get(&stem) != Some(&checksum) || files.iter().any(|(_, file)| !file.is_file()) {
                for (detail, file) in &files {
                    tile.write(&ground, &overlays, &tile_scenery, settings, *detail, file)?;
                }
                rebuilt += 1;
            }
            current.insert(stem, checksum);
            let centre =
                ground.at((tile.columns.0 + tile.columns.1) as f64 / 2.0, (tile.rows.0 + tile.rows.1) as f64 / 2.0);
            index.add_marker(&format!("tile {column} {row}"), game(centre), DQuat::IDENTITY);
        }
    }
    let [x, y] = settings.spawn_m;
    let Some(height) = ground.height(DVec2::new(x, y)) else { bail!("the spawn is off the ground") };
    let facing = DQuat::from_rotation_y(-settings.spawn_bearing_deg.to_radians());
    index.add_marker("spawn", game(DVec3::new(x, y, height)), facing);

    // Files of tiles no longer exported go.
    for entry in fs::read_dir(&tiles)? {
        let path = entry?.path();
        let name = path.file_name().unwrap_or_default().to_string_lossy();
        let stem = name.split('.').next().unwrap_or_default();
        if name != checksums::FILE && !current.contains_key(stem) {
            fs::remove_file(&path)?;
        }
    }
    checksums::write(&tiles, &current)?;
    println!("{}: rebuilt {rebuilt} of {} tiles", folder.display(), current.len());
    index.write(output)
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
    fn write(
        &self,
        ground: &Ground,
        overlays: &[Overlay],
        scenery: &TileScenery,
        settings: &Settings,
        detail: Detail,
        path: &Path,
    ) -> Result<()> {
        let mut glb = Glb::from_json(json!({ "asset": { "version": "2.0" } }));
        let ground_material =
            glb.add_material(&Material::textured("ground", &crate::uri_of_texture(&settings.ground_texture)?));
        let texture_steps = settings.ground_texture_m / settings.ground_step_m;
        let ground_mesh = self.ground(ground, detail, ground_material, texture_steps);
        let drawn = Surface::new(&ground_mesh);
        glb.add_mesh("ground", &[&ground_mesh]);
        for overlay in overlays {
            let mut mesh = overlay.mesh(ground, &drawn);
            if mesh.indices.is_empty() {
                continue;
            }
            overlay::check_above(&drawn, &mesh)
                .with_context(|| format!("writing {}: {}", path.display(), overlay.name))?;
            mesh.material =
                glb.add_material(&Material::textured(&overlay.name, &crate::uri_of_texture(&overlay.texture)?));
            glb.add_mesh(&overlay.name, &[&mesh]);
        }
        scenery.write(&mut glb, &drawn, detail == Detail::Middle, path)?;
        glb.write(path)
    }

    /// The ground in this tile. In full detail every grid square is two triangles. In middle detail the squares are
    /// `COARSE` steps wide; each is a fan around its centre through its corners and, on the tile's edges, every fine
    /// point along them. Its texture repeats every `texture_steps` grid steps, counted from the world's south-west
    /// corner, so it runs on unbroken across tiles and both versions.
    fn ground(&self, ground: &Ground, detail: Detail, material: usize, texture_steps: f64) -> Mesh {
        let mut mesh = Mesh { material, ..Mesh::default() };
        let mut points: HashMap<(usize, usize), u32> = HashMap::new();
        let vertex = |mesh: &mut Mesh, i: f64, j: f64| {
            let p = ground.at(i, j);
            mesh.positions.push(game(p).as_vec3().to_array());
            mesh.normals.push(game(ground.normal(p.truncate())).as_vec3().to_array());
            mesh.uvs.push([(i / texture_steps) as f32, (-j / texture_steps) as f32]);
            (mesh.positions.len() - 1) as u32
        };
        let mut point = |mesh: &mut Mesh, i: usize, j: usize| {
            *points.entry((i, j)).or_insert_with(|| vertex(mesh, i as f64, j as f64))
        };
        if detail == Detail::Full {
            for j in self.rows.0..self.rows.1 {
                for i in self.columns.0..self.columns.1 {
                    let [a, b, c, d] =
                        [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)].map(|(i, j)| point(&mut mesh, i, j));
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
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Neighbouring tiles meet exactly along their whole shared edge, whichever version each one shows: both draw
    /// the same edges between the same points there, so there is no step, slit or sliver.
    #[test]
    fn neighbouring_tiles_meet_exactly() {
        let steps = 2 * COARSE;
        let ground = Ground::page(2 * steps, 2.0, |i, j| (i as f32 * 0.7).sin() * 3.0 + (j as f32 * 1.3).cos() * 2.0);
        let span = |k: usize| (k * steps, (k + 1) * steps);
        let tile = |column, row| Tile { columns: span(column), rows: span(row) };
        // The edges a ground mesh draws along the line where `along` of a point (in the game's frame) is `at`.
        let edges = |mesh: &Mesh, along: fn(&[f32; 3]) -> f32, at: f32| {
            let mut edges: Vec<[[u32; 3]; 2]> = Vec::new();
            for triangle in mesh.indices.chunks(3) {
                for k in 0..3 {
                    let [a, b] = [triangle[k], triangle[(k + 1) % 3]].map(|v| mesh.positions[v as usize]);
                    if along(&a) == at && along(&b) == at {
                        let mut edge = [a, b].map(|p| p.map(f32::to_bits));
                        edge.sort();
                        edges.push(edge);
                    }
                }
            }
            edges.sort();
            edges
        };
        let x = |p: &[f32; 3]| p[0];
        let z = |p: &[f32; 3]| p[2];
        let east_edge = (steps as f64 * ground.step) as f32;
        // The edge two tiles share runs north to south at x = east_edge in the game's frame, and west to east at
        // z = -east_edge (north is -z).
        let pairs =
            [(tile(0, 0), tile(1, 0), x as fn(&[f32; 3]) -> f32, east_edge), (tile(0, 0), tile(0, 1), z, -east_edge)];
        for (first, second, along, at) in pairs {
            for a in [Detail::Full, Detail::Middle] {
                for b in [Detail::Full, Detail::Middle] {
                    let (one, other) = (first.ground(&ground, a, 0, 1.0), second.ground(&ground, b, 0, 1.0));
                    let shared = edges(&one, along, at);
                    assert_eq!(shared.len(), steps, "every fine step of the edge is drawn");
                    assert_eq!(shared, edges(&other, along, at));
                }
            }
        }
    }
}
