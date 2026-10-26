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
mod ground;
mod overlay;
mod regions;
mod ribbon;
mod surface;

use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use glam::{DQuat, DVec2, DVec3};
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::glb::{Glb, Mesh};
use ground::Ground;
use overlay::Overlay;
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
        texture_uri(texture)?;
    }
    let [[first_column, first_row], [last_column, last_row]] = settings.tiles;

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
            let span = |k: usize| (k * settings.tile_steps, (k + 1) * settings.tile_steps);
            let tile = Tile { columns: span(column), rows: span(row) };
            if !ground.covers(tile.columns, tile.rows) {
                bail!("tile {column} {row} reaches past the ground");
            }
            let stem = format!("{column}_{row}");
            let files = [
                (Detail::Full, tiles.join(format!("{stem}.glb"))),
                (Detail::Middle, tiles.join(format!("{stem}.middle.glb"))),
            ];
            let checksum = tile.checksum(&code, &tile_settings, &ground, &overlays);
            if previous.get(&stem) != Some(&checksum) || files.iter().any(|(_, file)| !file.is_file()) {
                for (detail, file) in &files {
                    tile.write(&ground, &overlays, settings, *detail, file)?;
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
        settings: &Settings,
        detail: Detail,
        path: &Path,
    ) -> Result<()> {
        let mut glb = Glb::from_json(json!({ "asset": { "version": "2.0" } }));
        let ground_material = glb.add_texture_material("ground", &texture_uri(&settings.ground_texture)?);
        let texture_steps = settings.ground_texture_m / settings.ground_step_m;
        let ground_mesh = self.ground(ground, detail, ground_material, texture_steps);
        let drawn = Surface::new(&ground_mesh);
        glb.add_mesh("ground", &ground_mesh);
        for overlay in overlays {
            let mut mesh = overlay.mesh(ground, &drawn);
            if mesh.indices.is_empty() {
                continue;
            }
            overlay::check_above(&drawn, &mesh)
                .with_context(|| format!("writing {}: {}", path.display(), overlay.name))?;
            mesh.material = glb.add_texture_material(&overlay.name, &texture_uri(&overlay.texture)?);
            glb.add_mesh(&overlay.name, &mesh);
        }
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
            mesh.normals.push(game_direction(ground.normal(p.truncate())).as_vec3().to_array());
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

/// A map position in the game's frame.
pub fn game(p: DVec3) -> DVec3 {
    DVec3::new(p.x, p.z, -p.y)
}

/// A map direction in the game's frame.
pub fn game_direction(d: DVec3) -> DVec3 {
    DVec3::new(d.x, d.z, -d.y)
}

/// Where a tile finds the texture asset `name`, relative to its file. A tile names its textures and never holds
/// them, so repainting a texture rebuilds no tile. Fails if there is no such texture asset.
fn texture_uri(name: &str) -> Result<String> {
    if !Path::new(crate::ASSETS).join("textures").join(name).join("asset.toml").is_file() {
        bail!("there is no texture asset named {name} in assets/textures/");
    }
    Ok(format!("../../textures/{name}/{name}.ktx2"))
}
