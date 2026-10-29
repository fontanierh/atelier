//! The `world` kind: the ground, and what each region lays over it, cut into square tiles.
//!
//! The ground is one grid of heights across the world, stored in square pages under `src/ground/`. Each region
//! lives in its own folder under `src/regions/`; its `layout.rs` says what it adds (`regions.rs` lists them). The
//! strips regions level are applied to the heights once, after reading the pages, so the tiles, the overlays and
//! the scenery all stand on the same ground. Raised planar surfaces may own a footprint over that grid;
//! their declared clearance keeps the underlying ground below them. Each
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

mod actors;
mod authored;
mod checksums;
mod curve;
mod ground;
mod levelling;
mod overlay;
mod placed;
mod published;
mod raised;
mod regions;
mod scenery;
mod surface;
mod underlay;

use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use glam::{DQuat, DVec2, DVec3};
use serde::{Deserialize, Serialize};
use serde_json::json;
use sha2::{Digest, Sha256};

use crate::glb::{Glb, Material, Mesh, y_up as game};
use ground::Ground;
use overlay::Overlay;
use raised::Raised;
use scenery::{Grid, Land, TileScenery};
use surface::Surface;

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Settings {
    /// The folder of the ground's pages.
    ground: PathBuf,
    /// Optional source-authored fine terrain diagonals, relative to this asset.
    #[serde(default)]
    terrain_diagonals: Option<PathBuf>,
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
    /// The first and the last tile that may hold scenery past the ground, a range around `tiles`. A tile there but
    /// outside `tiles` holds only models at their own heights, and is exported only if it holds any.
    #[serde(default)]
    scenery_tiles: Option<[[usize; 2]; 2]>,
    /// Optional map rectangle, aligned to ground samples, clipping the boundary tiles.
    #[serde(default)]
    extent_m: Option<[[f64; 2]; 2]>,
    /// Keep fine source terrain in middle detail as well as full detail.
    #[serde(default)]
    middle_uses_fine_ground: bool,
    /// The texture the ground shows, by its folder name under `assets/textures/`.
    ground_texture: String,
    /// How far apart the ground's texture repeats, in metres.
    ground_texture_m: f64,
    /// The ground texture's mean linear colour. Where the ground's pages give a colour, the ground is tinted by that
    /// colour over this mean, so the texture keeps its grain and shows the colour on average.
    #[serde(default)]
    ground_texture_mean: Option<[f64; 3]>,
    /// A grain-only texture, and its mean linear lightness, that a tile whose ground is coloured everywhere shows
    /// instead, so the colour shows true and only the grain is the texture's.
    #[serde(default)]
    coloured_ground_texture: Option<String>,
    #[serde(default)]
    coloured_ground_texture_mean: Option<f64>,
    /// Where the player starts, on the map.
    spawn_m: [f64; 2],
    /// Which way the player faces at the start, as a compass bearing east of north.
    spawn_bearing_deg: f64,
}

/// How many fine steps one coarse step of a middle tile spans.
const COARSE: usize = 4;

impl Settings {
    fn extent(&self) -> Result<Tile> {
        let [[first_x, first_y], [last_x, last_y]] = self.tiles;
        if first_x > last_x
            || first_y > last_y
            || self.tile_steps == 0
            || !self.ground_step_m.is_finite()
            || self.ground_step_m <= 0.0
        {
            bail!("invalid tile range or ground step");
        }
        let span = |k: usize| k.checked_mul(self.tile_steps).context("tile bounds overflow");
        let full = Tile {
            columns: (span(first_x)?, span(last_x.checked_add(1).context("tile bounds overflow")?)?),
            rows: (span(first_y)?, span(last_y.checked_add(1).context("tile bounds overflow")?)?),
        };
        let Some(extent) = self.extent_m else {
            return Ok(full);
        };
        let grid = |coordinate: f64, origin: f64| -> Result<usize> {
            let value = (coordinate - origin) / self.ground_step_m;
            if !value.is_finite() || value < 0.0 || value > usize::MAX as f64 || (value - value.round()).abs() > 1e-8 {
                bail!("world extent must align with finite ground samples");
            }
            Ok(value.round() as usize)
        };
        let x0 = grid(extent[0][0], self.south_west_m[0])?;
        let y0 = grid(extent[0][1], self.south_west_m[1])?;
        let x1 = grid(extent[1][0], self.south_west_m[0])?;
        let y1 = grid(extent[1][1], self.south_west_m[1])?;
        if x0 < full.columns.0
            || x1 > full.columns.1
            || y0 < full.rows.0
            || y1 > full.rows.1
            || x0 >= span(first_x + 1)?
            || x1 <= span(last_x)?
            || y0 >= span(first_y + 1)?
            || y1 <= span(last_y)?
            || x0 >= x1
            || y0 >= y1
        {
            bail!("world extent must intersect each declared tile");
        }
        Ok(Tile { columns: (x0, x1), rows: (y0, y1) })
    }
}

/// The model outputs the world reads while exporting: none, since placements name models without reading them.
pub fn reads(_settings: &Settings) -> Vec<String> {
    Vec::new()
}

fn source_path(folder: &Path, path: &Path) -> Result<PathBuf> {
    if !path.starts_with("src") || path.components().any(|part| matches!(part, std::path::Component::ParentDir)) {
        bail!("world source file must be inside src/");
    }
    let root = folder.join("src").canonicalize().context("reading world src")?;
    let file = folder.join(path).canonicalize().context("reading world source file")?;
    if !file.starts_with(root) {
        bail!("world source file must stay inside src/");
    }
    Ok(file)
}

pub fn export(folder: &Path, settings: &Settings, output: &Path) -> Result<()> {
    let [x, y] = settings.south_west_m;
    let mut ground =
        Ground::read(&folder.join(&settings.ground), settings.page_steps, settings.ground_step_m, DVec2::new(x, y))?;
    if let Some(path) = &settings.terrain_diagonals {
        ground.read_diagonals(&source_path(folder, path)?)?;
    }
    let strips: Vec<_> = regions::REGIONS.iter().flat_map(|region| region.levelled()).collect();
    let pads: Vec<_> = regions::REGIONS.iter().flat_map(|region| region.pads()).collect();
    for strip in &strips {
        strip.level(&mut ground).context("levelling a strip")?;
    }
    levelling::level_pads(&mut ground, &pads).context("levelling pads")?;
    let mut overlays = Vec::new();
    for region in regions::REGIONS {
        for mut overlay in region.overlays() {
            overlay.name = format!("{} {}", region.name(), overlay.name);
            overlays.push(overlay);
        }
    }
    let authored: Vec<_> = regions::REGIONS.iter().flat_map(|region| region.authored_surfaces()).collect();
    for surface in &authored {
        surface.validate()?;
    }
    let raised: Vec<_> = regions::REGIONS.iter().flat_map(|region| region.raised()).collect();
    let authored_footprints: Vec<Overlay> = authored
        .iter()
        .map(|surface| Overlay {
            name: surface.name.into(),
            texture: surface.texture.unwrap_or_default().into(),
            triangles: surface
                .triangles
                .iter()
                .map(|triangle| {
                    std::array::from_fn(|i| {
                        (DVec2::new(triangle.xyz[i][0], triangle.xyz[i][1]), DVec2::from_array(triangle.uv[i]))
                    })
                })
                .collect(),
        })
        .collect();
    // Existing overlay/raised ownership rules still apply to the source surface's footprint.
    for footprint in &authored_footprints {
        raised::check(&raised, std::slice::from_ref(footprint))?;
    }
    raised::check(&raised, &overlays)?;
    for texture in overlays
        .iter()
        .map(|overlay| &overlay.texture)
        .chain(raised.iter().map(|surface| &surface.texture))
        .chain([&settings.ground_texture])
        .chain(&settings.coloured_ground_texture)
    {
        crate::uri_of_texture(texture)?;
    }
    let [[first_column, first_row], [last_column, last_row]] = settings.tiles;
    let span = |k: usize| (k * settings.tile_steps, (k + 1) * settings.tile_steps);
    let whole = settings.extent()?;
    if !ground.covers_diagonals(whole.columns, whole.rows) {
        bail!("world extent is outside the source terrain diagonal coverage");
    }
    // The means come from the settings alone, which every tile's checksum covers, never from colour pages elsewhere.
    let grain = match (&settings.coloured_ground_texture, settings.coloured_ground_texture_mean) {
        (Some(_), Some(mean)) if mean > 0.0 && mean.is_finite() => Some(mean),
        (None, None) => None,
        _ => bail!("a grain-only ground texture needs its positive mean lightness"),
    };
    match settings.ground_texture_mean {
        Some(mean) if mean.iter().all(|&c| c > 0.0 && c.is_finite()) => ground.set_texture_means(mean, grain),
        None if !ground.has_colours() && grain.is_none() => {}
        _ => bail!("a coloured ground needs the ground texture's positive mean colour"),
    }
    let tile_m = settings.tile_steps as f64 * settings.ground_step_m;
    let collars = raised.iter().map(|surface| underlay::owner_collar(surface, tile_m)).collect::<Result<Vec<_>>>()?;
    let mut unions: [Vec<underlay::Underlay>; 2] = [Vec::new(), Vec::new()];
    for (surface, &collar) in raised.iter().zip(&collars).filter(|(surface, _)| surface.cut_ground) {
        for (di, detail) in [Detail::Full, Detail::Middle].into_iter().enumerate() {
            if let Some(union) = underlay_for_owner(&ground, surface, settings, detail, collar, &authored)? {
                unions[di].push(union);
            }
        }
    }
    let mut prepared =
        raised::Prepared::new(&raised, DVec2::new(x, y), settings.tile_steps as f64 * settings.ground_step_m);
    prepared.set_underlays(&unions);
    if !raised.is_empty() {
        for column in first_column..=last_column {
            for row in first_row..=last_row {
                let tile = whole.clip_tile(span(column), span(row)).expect("declared tiles intersect extent");
                for detail in [Detail::Full, Detail::Middle] {
                    let mesh = tile.ground(
                        &ground,
                        tile.detail_for(&ground, detail, &authored, settings.middle_uses_fine_ground),
                        0,
                        1.0,
                    );
                    let drawn = Surface::new(&mesh);
                    let di = usize::from(detail == Detail::Middle);
                    let cut_mesh =
                        if unions[di].is_empty() { mesh } else { underlay::remove_covered(&mesh, &unions[di]) };
                    let cut = Surface::new(&cut_mesh);
                    prepared.add_tile_with_cut((column, row), &drawn, &cut, detail == Detail::Middle)?;
                }
            }
        }
    }
    let whole_mesh = whole.ground(&ground, Detail::Full, 0, 1.0);
    let low = ground.position(whole.columns.0 as f64, whole.rows.0 as f64);
    let high = ground.position(whole.columns.1 as f64, whole.rows.1 as f64);
    let source_meshes: Vec<Mesh> = authored.iter().map(|surface| surface.mesh(low, high)).collect::<Result<_>>()?;
    let drawn = Surface::with_crossings(&whole_mesh, &source_meshes);
    for surface in &authored {
        if let Some(texture) = surface.texture {
            crate::uri_of_texture(texture)?;
        }
    }
    let land = Land {
        ground: &ground,
        rendered: (!authored.is_empty()).then_some(&drawn),
        raised: &prepared,
        middle: false,
        low: ground.position(whole.columns.0 as f64, whole.rows.0 as f64),
        high: ground.position(whole.columns.1 as f64, whole.rows.1 as f64),
        regions: regions::REGIONS,
    };
    let grid = Grid { south_west: DVec2::new(x, y), tile_m: settings.tile_steps as f64 * settings.ground_step_m };
    let sceneries: Vec<_> = regions::REGIONS.iter().map(|region| region.scenery(&land)).collect();
    let waters: Vec<_> = regions::REGIONS.iter().flat_map(|region| region.water()).collect();
    hakuba_water_schema::validate(&waters).map_err(anyhow::Error::msg)?;
    validate_water_models(&waters, sceneries.iter().flat_map(|s| s.placements.iter().map(|p| p.model)))?;

    let mut scenery = scenery::share(sceneries, &land, &grid, &overlays, &prepared, &drawn)?;
    let [[scenery_first_column, scenery_first_row], [scenery_last_column, scenery_last_row]] =
        settings.scenery_tiles.unwrap_or(settings.tiles);
    if scenery_first_column > first_column
        || scenery_first_row > first_row
        || scenery_last_column < last_column
        || scenery_last_row < last_row
    {
        bail!("the scenery tiles must surround the ground's tiles");
    }
    for region in regions::REGIONS {
        for placement in region.beyond(&land) {
            let past = placement.at - grid.south_west;
            let (column, row) = grid.tile(placement.at);
            if past.min_element() < 0.0
                || !(scenery_first_column..=scenery_last_column).contains(&column)
                || !(scenery_first_row..=scenery_last_row).contains(&row)
            {
                bail!("{} at {} stands past the scenery tiles", placement.model, placement.at);
            }
            if placement.origin_height_m.is_none() {
                bail!("{} at {} stands past the ground without its own height", placement.model, placement.at);
            }
            crate::uri_of_asset(placement.model, "glb")?;
            scenery.entry((column, row)).or_default().add(&placement);
        }
    }

    let tiles = folder.join("tiles");
    fs::create_dir_all(&tiles)?;
    let previous = checksums::read(&tiles)?;
    let mut current = BTreeMap::new();
    let code = checksums::code()?;
    let tile_settings = serde_json::to_vec(&json!([
        settings.south_west_m,
        settings.ground_step_m,
        settings.tile_steps,
        settings.middle_uses_fine_ground,
        settings.ground_texture,
        settings.ground_texture_m,
        settings.ground_texture_mean,
        settings.coloured_ground_texture,
        settings.coloured_ground_texture_mean
    ]))?;
    // A tile past the ground draws no ground, so only the grid placing it is among its settings.
    let scenery_settings =
        serde_json::to_vec(&json!([settings.south_west_m, settings.ground_step_m, settings.tile_steps]))?;
    let mut rebuilt = 0;
    let mut index = Glb::from_json(json!({ "asset": { "version": "2.0" } }));
    if !waters.is_empty() {
        index.add_data("water bodies", json!({ "waters": waters }));
    }
    for column in first_column..=last_column {
        for row in first_row..=last_row {
            let tile = whole.clip_tile(span(column), span(row)).expect("declared tiles intersect extent");
            let tile_scenery = scenery.remove(&(column, row)).unwrap_or_default();
            // A tile out at sea, with no ground and nothing standing in it, is not exported.
            if tile_scenery.is_empty() && !ground.touches(tile.columns, tile.rows) {
                continue;
            }
            let stem = format!("{column}_{row}");
            let files = [
                (Detail::Full, tiles.join(format!("{stem}.glb"))),
                (Detail::Middle, tiles.join(format!("{stem}.middle.glb"))),
            ];
            let checksum = tile.checksum(
                &code,
                &tile_settings,
                &ground,
                (&overlays, &raised, &authored),
                (&tile_scenery, &collars),
            );
            if previous.get(&stem) != Some(&checksum) || files.iter().any(|(_, file)| !file.is_file()) {
                for (detail, file) in &files {
                    tile.write(
                        &ground,
                        (&overlays, &raised, &prepared, &unions[usize::from(*detail == Detail::Middle)], &authored),
                        &tile_scenery,
                        settings,
                        *detail,
                        file,
                    )?;
                }
                rebuilt += 1;
            }
            current.insert(stem, checksum);
            let middle = ground
                .position((tile.columns.0 + tile.columns.1) as f64 / 2.0, (tile.rows.0 + tile.rows.1) as f64 / 2.0);
            let centre = middle.extend(ground.height(middle).unwrap_or(0.0));
            index.add_marker(&format!("tile {column} {row}"), game(centre), DQuat::IDENTITY);
        }
    }
    // Tiles past the ground hold only the models standing there.
    for column in scenery_first_column..=scenery_last_column {
        for row in scenery_first_row..=scenery_last_row {
            if (first_column..=last_column).contains(&column) && (first_row..=last_row).contains(&row) {
                continue;
            }
            let Some(tile_scenery) = scenery.remove(&(column, row)) else {
                continue;
            };
            let stem = format!("{column}_{row}");
            let files = [(false, tiles.join(format!("{stem}.glb"))), (true, tiles.join(format!("{stem}.middle.glb")))];
            let mut digest = Sha256::new();
            digest.update(&code);
            digest.update(&scenery_settings);
            digest.update(stem.as_bytes());
            digest.update(scenery::checksum_bytes(&tile_scenery));
            let checksum = format!("{:x}", digest.finalize());
            if previous.get(&stem) != Some(&checksum) || files.iter().any(|(_, file)| !file.is_file()) {
                for (middle, file) in &files {
                    // A tile with nothing seen from afar still holds a scene, empty, for the game to load.
                    let mut glb = Glb::from_json(
                        json!({ "asset": { "version": "2.0" }, "scene": 0, "scenes": [{ "nodes": [] }] }),
                    );
                    tile_scenery.write_beyond(&mut glb, *middle, file)?;
                    glb.write(file)?;
                }
                rebuilt += 1;
            }
            current.insert(stem, checksum);
            let centre = grid.south_west + (DVec2::new(column as f64, row as f64) + 0.5) * grid.tile_m;
            index.add_marker(&format!("tile {column} {row}"), game(centre.extend(0.0)), DQuat::IDENTITY);
        }
    }
    let [x, y] = settings.spawn_m;
    let spawn = spawn_position(DVec2::new(x, y), &ground, &prepared, (!authored.is_empty()).then_some(&drawn))?;
    let facing = DQuat::from_rotation_y(-settings.spawn_bearing_deg.to_radians());
    index.add_marker("spawn", game(spawn), facing);
    for (i, actor) in regions::REGIONS.iter().flat_map(|region| region.actors()).enumerate() {
        actor.validate()?;
        let inside = |position: [f64; 3]| {
            let [x, y, _] = position;
            let [west, south] = settings.south_west_m;
            let step = settings.ground_step_m;
            x >= west + whole.columns.0 as f64 * step
                && x <= west + whole.columns.1 as f64 * step
                && y >= south + whole.rows.0 as f64 * step
                && y <= south + whole.rows.1 as f64 * step
        };
        if inside(actor.position) {
            if actor.route.as_ref().is_some_and(|route| !inside(route.destination)) {
                bail!("actor route leaves the exported world");
            }
            index.add_data(&format!("actor {i}"), serde_json::to_value(actor)?);
        }
    }

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

/// @cc [owner:fontanierh,label:correctness] water-model-association
/// Every water material association MUST name placed scenery. Missing associations MUST fail the export rather than
/// silently render an ordinary material. The shared water schema rejects ambiguous body associations.
fn validate_water_models<'a>(waters: &[serde_json::Value], placements: impl Iterator<Item = &'a str>) -> Result<()> {
    let placed: std::collections::HashSet<_> = placements.collect();
    for water in waters {
        let models = water
            .get("water_models")
            .and_then(serde_json::Value::as_array)
            .context("bounded water needs its model associations")?;
        if models.is_empty() {
            bail!("bounded water has no model associations");
        }
        for entry in models {
            let model = entry
                .get("model")
                .and_then(serde_json::Value::as_str)
                .context("bounded water has an invalid model association")?;
            if !placed.contains(model) {
                bail!("bounded water model {model} has no scenery placement");
            }
        }
    }
    Ok(())
}

// Prepare from the complete authored bounds and the fixed grid, independent of the exported tile range.
fn underlay_for_owner(
    ground: &Ground,
    surface: &Raised,
    settings: &Settings,
    detail: Detail,
    collar: f64,
    authored: &[authored::AuthoredSurface],
) -> Result<Option<underlay::Underlay>> {
    let origin = DVec2::from_array(settings.south_west_m);
    let (low, high) = surface
        .triangles
        .iter()
        .flatten()
        .map(|(p, _)| *p)
        .fold((DVec2::splat(f64::INFINITY), DVec2::splat(f64::NEG_INFINITY)), |(low, high), p| {
            (low.min(p), high.max(p))
        });
    let grid_low = (low - origin) / settings.ground_step_m;
    let grid_high = (high - origin) / settings.ground_step_m;
    let (max_x, max_y) = ground.max_steps().context("underlay requires finite loaded ground bounds")?;
    if !grid_low.is_finite()
        || !grid_high.is_finite()
        || grid_low.min_element() < 0.0
        || grid_high.x > max_x as f64
        || grid_high.y > max_y as f64
        || settings.tile_steps == 0
        || max_x < settings.tile_steps
        || max_y < settings.tile_steps
    {
        bail!("{} underlay is outside the loaded ground", surface.name);
    }
    let first = (grid_low / settings.tile_steps as f64).floor();
    let last = (grid_high / settings.tile_steps as f64).floor();
    let max_column = (max_x - 1) / settings.tile_steps;
    let max_row = (max_y - 1) / settings.tile_steps;
    let span = |k: usize| (k * settings.tile_steps, (k + 1) * settings.tile_steps);
    let mut tops = Vec::new();
    for column in (first.x.max(0.0) as usize).saturating_sub(1)..=(last.x as usize).saturating_add(1).min(max_column) {
        for row in (first.y.max(0.0) as usize).saturating_sub(1)..=(last.y as usize).saturating_add(1).min(max_row) {
            let tile = Tile { columns: span(column), rows: span(row) };
            let tile = if settings.extent_m.is_some() {
                let Some(tile) = settings.extent()?.clip_tile(tile.columns, tile.rows) else {
                    continue;
                };
                tile
            } else {
                tile
            };
            if ground.covers(tile.columns, tile.rows) {
                let mesh = tile.ground(
                    ground,
                    tile.detail_for(ground, detail, authored, settings.middle_uses_fine_ground),
                    0,
                    1.0,
                );
                tops.push(surface.mesh_before_cut(&Surface::new(&mesh), false)?);
            }
        }
    }
    Ok(underlay::union(&tops, collar))
}

/// Match the runtime's stored XY before selecting a raised owner, retaining the old empty-world export.
fn spawn_position(
    at: DVec2,
    ground: &Ground,
    prepared: &raised::Prepared<'_>,
    rendered: Option<&Surface>,
) -> Result<DVec3> {
    let at = prepared.emitted_at(at);
    prepared.check_point(at)?;
    let Some(height) = rendered.map_or_else(
        || prepared.height(at, |p| ground.height(p)),
        |surface| {
            prepared.height_with_crossing(
                at,
                false,
                |p| surface.ground_height(p),
                |p, base| surface.crossing_over(p, base),
            )
        },
    ) else {
        bail!("the spawn is off the ground")
    };
    Ok(at.extend(height))
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
    /// Intersect a fixed-grid tile with the declared world extent, retaining its grid identity.
    fn clip_tile(&self, columns: (usize, usize), rows: (usize, usize)) -> Option<Tile> {
        let columns = (columns.0.max(self.columns.0), columns.1.min(self.columns.1));
        let rows = (rows.0.max(self.rows.0), rows.1.min(self.rows.1));
        (columns.0 < columns.1 && rows.0 < rows.1).then_some(Tile { columns, rows })
    }

    /// Keep the source terrain's fine triangles wherever an authored crossing reaches the tile in either detail.
    fn detail_for(
        &self,
        ground: &Ground,
        requested: Detail,
        authored: &[authored::AuthoredSurface],
        fine_middle: bool,
    ) -> Detail {
        if requested == Detail::Full || fine_middle {
            return Detail::Full;
        }
        let low = ground.position(self.columns.0 as f64, self.rows.0 as f64);
        let high = ground.position(self.columns.1 as f64, self.rows.1 as f64);
        let touches = authored.iter().flat_map(|surface| &surface.triangles).any(|triangle| {
            let p = triangle.xyz.map(|p| DVec2::new(p[0], p[1]));
            let min = p[0].min(p[1]).min(p[2]);
            let max = p[0].max(p[1]).max(p[2]);
            min.cmple(high).all() && max.cmpge(low).all()
        });
        if touches { Detail::Full } else { requested }
    }

    fn write(
        &self,
        ground: &Ground,
        surfaces: (&[Overlay], &[Raised], &raised::Prepared<'_>, &[underlay::Underlay], &[authored::AuthoredSurface]),
        scenery: &TileScenery,
        settings: &Settings,
        detail: Detail,
        path: &Path,
    ) -> Result<()> {
        let (overlays, raised, prepared, underlay, authored) = surfaces;
        let mut glb = Glb::from_json(json!({ "asset": { "version": "2.0" } }));
        let texture = match &settings.coloured_ground_texture {
            Some(texture) if ground.wholly_coloured(self.columns, self.rows) => texture,
            _ => &settings.ground_texture,
        };
        let ground_material = glb.add_material(&Material::textured("ground", &crate::uri_of_texture(texture)?));
        let texture_steps = settings.ground_texture_m / settings.ground_step_m;
        let ground_mesh = self.ground(
            ground,
            self.detail_for(ground, detail, authored, settings.middle_uses_fine_ground),
            ground_material,
            texture_steps,
        );
        let drawn = Surface::new(&ground_mesh);
        let low = ground.position(self.columns.0 as f64, self.rows.0 as f64);
        let high = ground.position(self.columns.1 as f64, self.rows.1 as f64);
        let source_meshes: Vec<Mesh> = authored.iter().map(|surface| surface.mesh(low, high)).collect::<Result<_>>()?;
        let visible = Surface::with_crossings(&ground_mesh, &source_meshes);
        let cut_mesh = if underlay.is_empty() { ground_mesh } else { underlay::remove_covered(&ground_mesh, underlay) };
        let cut = Surface::new(&cut_mesh);
        if !cut_mesh.indices.is_empty() {
            glb.add_mesh("ground", &[&cut_mesh]);
        }
        for overlay in overlays {
            let mut mesh = overlay.mesh(ground, &drawn);
            if mesh.indices.is_empty() {
                continue;
            }
            overlay::check_above(&drawn, &mesh)
                .with_context(|| format!("writing {}: {}", path.display(), overlay.name))?;
            if detail == Detail::Full {
                overlay::check_smooth(&mesh)
                    .with_context(|| format!("writing {}: {}", path.display(), overlay.name))?;
            }
            mesh.material =
                glb.add_material(&Material::textured(&overlay.name, &crate::uri_of_texture(&overlay.texture)?));
            glb.add_mesh(&overlay.name, &[&mesh]);
        }
        for (surface, source_mesh) in authored.iter().zip(&source_meshes) {
            if source_mesh.indices.is_empty() {
                continue;
            }
            let mut mesh = source_mesh.clone();
            let texture = surface.texture.map(crate::uri_of_texture).transpose()?;
            mesh.material = glb.add_material(&Material {
                name: surface.name,
                texture: texture.as_deref(),
                colour: surface.tint,
                cut_out: false,
                two_sided: false,
            });
            let node = glb.add_mesh(surface.name, &[&mesh]);
            if let Some(paint) = &surface.paint {
                glb.set_extras(node, json!({"surface_paint": paint}));
            }
            if let Some(paint) = &surface.vertex_paint {
                glb.set_extras(node, json!({"vertex_paint": paint}));
            }
        }
        for surface in raised {
            let mut mesh =
                surface.mesh_prepared(&drawn, &cut, false).with_context(|| format!("writing {}", path.display()))?;
            if !mesh.indices.is_empty() {
                mesh.material =
                    glb.add_material(&Material::textured(&surface.name, &crate::uri_of_texture(&surface.texture)?));
                let node = glb.add_mesh(&surface.node_name(), &[&mesh]);
                if let Some(paint) = &surface.paint {
                    glb.set_extras(node, json!({"surface_paint": paint}));
                }
            }
        }
        scenery.write(&mut glb, &visible, prepared, detail == Detail::Middle, path)?;
        glb.write(path)
    }

    /// The ground in this tile. In full detail every grid square is two triangles. In middle detail the squares are
    /// `COARSE` steps wide; each is a fan around its centre through its corners and, on the tile's edges, every fine
    /// point along them. A grid square with a corner off the ground, out at sea, is left out, and a coarse square
    /// holding one draws its fine squares. Its texture repeats every
    /// `texture_steps` grid steps, counted from the world's south-west corner, so it runs on unbroken across tiles
    /// and both versions; where the ground has colours, each vertex carries its tint.
    fn ground(&self, ground: &Ground, detail: Detail, material: usize, texture_steps: f64) -> Mesh {
        let mut mesh = Mesh { material, ..Mesh::default() };
        let grain = ground.wholly_coloured(self.columns, self.rows);
        // Only a tile with a colour of its own carries vertex colours, so a colour elsewhere changes nothing here.
        let coloured = ground.any_coloured(self.columns, self.rows);
        let mut points: HashMap<(usize, usize), u32> = HashMap::new();
        let vertex = |mesh: &mut Mesh, i: f64, j: f64| {
            let p = ground.at(i, j);
            mesh.positions.push(game(p).as_vec3().to_array());
            mesh.normals.push(game(ground.normal(p.truncate())).as_vec3().to_array());
            mesh.uvs.push([(i / texture_steps) as f32, (-j / texture_steps) as f32]);
            if coloured {
                mesh.colours.push(ground.tint(i.round() as usize, j.round() as usize, grain));
            }
            (mesh.positions.len() - 1) as u32
        };
        let mut point = |mesh: &mut Mesh, i: usize, j: usize| {
            *points.entry((i, j)).or_insert_with(|| vertex(mesh, i as f64, j as f64))
        };
        // The fine squares from (`i0`, `j0`) to (`i1`, `j1`) that are on the ground, two triangles each.
        let fine = |mesh: &mut Mesh, point: &mut dyn FnMut(&mut Mesh, usize, usize) -> u32, (i0, i1), (j0, j1)| {
            for j in j0..j1 {
                for i in i0..i1 {
                    if !ground.covers((i, i + 1), (j, j + 1)) {
                        continue;
                    }
                    let [a, b, c, d] = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)].map(|(i, j)| point(mesh, i, j));
                    if ground.alternate_diagonal(i, j) {
                        mesh.indices.extend([a, b, d, b, c, d]);
                    } else {
                        mesh.indices.extend([a, b, c, a, c, d]);
                    }
                }
            }
        };
        if detail == Detail::Full {
            fine(&mut mesh, &mut point, self.columns, self.rows);
            return mesh;
        }
        let coarse = |(first, last): (usize, usize)| {
            let mut stops: Vec<usize> = (first..last).step_by(COARSE).collect();
            stops.push(last);
            stops
        };
        let (columns, rows) = (coarse(self.columns), coarse(self.rows));
        // A coarse square with a corner off the ground draws its fine squares instead, so the coast keeps the full
        // detail's edge; a whole neighbour then meets it through every fine point on their shared side.
        let partial = |a: usize, b: usize| {
            a + 1 < columns.len()
                && b + 1 < rows.len()
                && !ground.covers((columns[a], columns[a + 1]), (rows[b], rows[b + 1]))
                && ground.touches((columns[a], columns[a + 1]), (rows[b], rows[b + 1]))
        };
        for b in 0..rows.len() - 1 {
            for a in 0..columns.len() - 1 {
                let ((i0, i1), (j0, j1)) = ((columns[a], columns[a + 1]), (rows[b], rows[b + 1]));
                if !ground.covers((i0, i1), (j0, j1)) {
                    fine(&mut mesh, &mut point, (i0, i1), (j0, j1));
                    continue;
                }
                // The square's outline, counter-clockwise seen from above, through every fine point on a tile edge
                // or beside a square drawn fine.
                let mut outline = Vec::new();
                let side = |fine: bool, from: usize, to: usize| -> Vec<usize> {
                    if !fine {
                        return vec![from];
                    }
                    if from < to { (from..to).collect() } else { (to + 1..=from).rev().collect() }
                };
                let south = b == 0 || partial(a, b - 1);
                let east = a + 2 == columns.len() || partial(a + 1, b);
                let north = b + 2 == rows.len() || partial(a, b + 1);
                let west = a == 0 || partial(a - 1, b);
                outline.extend(side(south, i0, i1).into_iter().map(|i| (i, j0)));
                outline.extend(side(east, j0, j1).into_iter().map(|j| (i1, j)));
                outline.extend(side(north, i1, i0).into_iter().map(|i| (i, j1)));
                outline.extend(side(west, j1, j0).into_iter().map(|j| (i0, j)));
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

    #[test]
    fn a_square_off_the_ground_draws_nothing_and_its_coast_meets_without_a_seam() {
        let ground = Ground::page(8, 1.0, |i, j| if i == 0 && j == 0 { f32::NAN } else { 1.0 });
        let tile = Tile { columns: (0, 8), rows: (0, 8) };
        assert_eq!(tile.ground(&ground, Detail::Full, 0, 1.0).indices.len(), (64 - 1) * 6);
        let middle = tile.ground(&ground, Detail::Middle, 0, 1.0);
        let at = |east: f32, north: f32| middle.positions.iter().any(|p| p[0] == east && -p[2] == north);
        assert!(!at(0.0, 0.0), "no triangle reaches the missing point");
        assert!((1..4).all(|j| at(1.0, j as f32) && at(4.0, j as f32)), "the partial square is drawn fine");
        let triangles = middle.indices.len() / 3;
        // The partial square's 15 fine squares, then each coarse fan through one point a side, or every fine point
        // on a tile edge or beside the partial square: 4 + 4 + 1 + 4, 4 + 1 + 4 + 4 and 1 + 4 + 4 + 1 triangles.
        assert_eq!(triangles, 15 * 2 + 13 + 13 + 10, "the coarse fans meet the fine squares point for point");
        assert!(!ground.touches((20, 28), (20, 28)), "past the page there is no ground");
    }

    #[test]
    fn bounded_water_requires_placed_models() {
        let water = json!({"water_models": [{"model": "props/water-a"}, {"model": "props/water-b"}]});
        assert!(
            validate_water_models(std::slice::from_ref(&water), ["props/water-a", "props/water-b"].into_iter()).is_ok()
        );
        assert!(validate_water_models(std::slice::from_ref(&water), ["props/water-a"].into_iter()).is_err());
    }

    #[test]
    fn authored_diagonal_drives_surface_query_and_local_checksum() {
        let mut ground = Ground::page(4, 1.0, |i, j| if i == 1 && j == 1 { 1.0 } else { 0.0 });
        let tile = Tile { columns: (0, 1), rows: (0, 1) };
        let other = Tile { columns: (2, 3), rows: (2, 3) };
        let checksum = |tile: &Tile, ground: &Ground| {
            tile.checksum(&[], &[], ground, (&[], &[], &[]), (&TileScenery::default(), &[]))
        };
        let old = checksum(&tile, &ground);
        let untouched = checksum(&other, &ground);
        let path = std::env::temp_dir().join(format!("hakuba-diagonals-{}.json", std::process::id()));
        fs::write(
            &path,
            r#"{"extent_m":[[0,0],[4,4]],"native_extent_m":[[0,0],[4,4]],"step_m":1,"alternate_cells_m":[[0,0]]}"#,
        )
        .unwrap();
        ground.read_diagonals(&path).unwrap();
        fs::remove_file(path).unwrap();
        let at = DVec2::new(0.25, 0.25);
        let surface = Surface::new(&tile.ground(&ground, Detail::Full, 0, 1.0));
        assert_eq!(ground.height(at), Some(0.0));
        assert_eq!(surface.ground_height(at), Some(0.0));
        assert_ne!(checksum(&tile, &ground), old);
        assert_eq!(checksum(&other, &ground), untouched);
    }

    #[test]
    fn neighboring_diagonal_invalidates_edge_overlay_normal() {
        let mut ground = Ground::page(8, 1.0, |i, j| if i == 5 && j == 3 { 1.0 } else { 0.0 });
        let tile = Tile { columns: (2, 4), rows: (2, 4) };
        let far = Tile { columns: (6, 7), rows: (6, 7) };
        let overlay = Overlay {
            name: "edge".into(),
            texture: "ground".into(),
            triangles: vec![[
                (DVec2::new(3.75, 2.25), DVec2::ZERO),
                (DVec2::new(3.5, 2.5), DVec2::X),
                (DVec2::new(3.5, 2.25), DVec2::Y),
            ]],
        };
        let path = std::env::temp_dir().join(format!("hakuba-edge-diagonals-{}.json", std::process::id()));
        let load = |ground: &mut Ground, cells: &str| {
            fs::write(&path, format!(r#"{{"extent_m":[[0,0],[8,8]],"native_extent_m":[[0,0],[8,8]],"step_m":1,"alternate_cells_m":{cells}}}"#)).unwrap();
            ground.read_diagonals(&path).unwrap();
        };
        let checksum = |tile: &Tile, ground: &Ground| {
            tile.checksum(&[], &[], ground, (std::slice::from_ref(&overlay), &[], &[]), (&TileScenery::default(), &[]))
        };
        let normals = |ground: &Ground| {
            let surface = Surface::new(&tile.ground(ground, Detail::Full, 0, 1.0));
            overlay.mesh(ground, &surface).normals
        };
        load(&mut ground, "[]");
        let before = checksum(&tile, &ground);
        let far_before = checksum(&far, &ground);
        let before_normals = normals(&ground);
        assert!(!before_normals.is_empty());
        load(&mut ground, "[[4,2]]");
        assert_ne!(before_normals, normals(&ground));
        assert_ne!(before, checksum(&tile, &ground));
        assert_eq!(far_before, checksum(&far, &ground));
        fs::remove_file(path).unwrap();
    }

    #[test]
    fn aligned_extent_clips_boundary_tile_at_both_details() {
        let mut settings = Settings {
            terrain_diagonals: None,
            ground: PathBuf::new(),
            south_west_m: [0.0, 0.0],
            ground_step_m: 2.0,
            page_steps: 64,
            tile_steps: 32,
            tiles: [[0, 0], [1, 0]],
            scenery_tiles: None,
            extent_m: Some([[0.0, 0.0], [88.0, 64.0]]),
            middle_uses_fine_ground: false,
            ground_texture: "ground".into(),
            ground_texture_m: 24.0,
            ground_texture_mean: None,
            coloured_ground_texture: None,
            coloured_ground_texture_mean: None,
            spawn_m: [0.0, 0.0],
            spawn_bearing_deg: 0.0,
        };
        let extent = settings.extent().unwrap();
        let tile = extent.clip_tile((32, 64), (0, 32)).unwrap();
        assert_eq!(tile.columns, (32, 44));
        let ground = Ground::page(64, 2.0, |i, j| (i + j) as f32);
        assert!(ground.covers(extent.columns, extent.rows));
        let broken = Ground::page(64, 2.0, |i, j| if i == 40 && j == 8 { f32::NAN } else { 0.0 });
        assert!(!broken.covers(extent.columns, extent.rows));
        assert_eq!(ground.at(38.0, 16.0).x, 76.0); // centre of the actual partial tile
        for detail in [Detail::Full, Detail::Middle] {
            let mesh = tile.ground(&ground, detail, 0, 12.0);
            assert!(mesh.positions.iter().all(|p| p[0] >= 64.0 && p[0] <= 88.0));
            assert!(mesh.positions.iter().any(|p| p[0] == 88.0));
            assert!(mesh.positions.iter().any(|p| p[0] == 64.0));
        }
        settings.extent_m = Some([[0.0, 0.0], [89.0, 64.0]]);
        assert!(settings.extent().is_err());
        settings.extent_m = Some([[0.0, 0.0], [64.0, 64.0]]);
        assert!(settings.extent().is_err());
    }

    #[test]
    fn distant_crossing_detail_policy_does_not_change_neighboring_owner_tile() {
        let ground = Ground::page(32, 1.0, |i, j| ((i * i + j * j + i * j) % 17) as f32 / 100.0);
        let tile = Tile { columns: (0, 8), rows: (0, 8) };
        let settings = Settings {
            terrain_diagonals: None,
            ground: PathBuf::new(),
            south_west_m: [0.0, 0.0],
            ground_step_m: 1.0,
            page_steps: 32,
            tile_steps: 8,
            tiles: [[0, 0], [1, 1]],
            scenery_tiles: None,
            extent_m: None,
            middle_uses_fine_ground: false,
            ground_texture: "ground".into(),
            ground_texture_m: 6.0,
            ground_texture_mean: None,
            coloured_ground_texture: None,
            coloured_ground_texture_mean: None,
            spawn_m: [0.0, 0.0],
            spawn_bearing_deg: 0.0,
        };
        let p = |x, y| (DVec2::new(x, y), DVec2::ZERO);
        let raised = [Raised {
            name: "owner".into(),
            texture: "ground".into(),
            ground: true,
            paint: None,
            height: 2.0,
            clearance: 0.1,
            cut_ground: true,
            triangles: vec![[p(6.0, 2.0), p(10.0, 2.0), p(6.0, 5.0)]],
        }];
        let road = [authored::AuthoredSurface {
            name: "road",
            texture: Some("road"),
            tint: [1.0; 3],
            paint: None,
            vertex_paint: None,
            triangles: vec![authored::Triangle {
                xyz: [[13.0, 5.0, 1.0], [14.0, 5.0, 1.0], [13.0, 6.0, 1.0]],
                uv: [[0.0; 2]; 3],
                normal: [[0.0, 0.0, 1.0]; 3],
                colour: None,
            }],
        }];
        let emit = |authored: &[authored::AuthoredSurface], tag: &str| {
            let collar = underlay::owner_collar(&raised[0], 8.0).unwrap();
            let unions = [Detail::Full, Detail::Middle].map(|detail| {
                vec![underlay_for_owner(&ground, &raised[0], &settings, detail, collar, authored).unwrap().unwrap()]
            });
            let mut prepared = raised::Prepared::new(&raised, DVec2::ZERO, 8.0);
            prepared.set_underlays(&unions);
            for (di, detail) in [Detail::Full, Detail::Middle].into_iter().enumerate() {
                let mesh = tile.ground(
                    &ground,
                    tile.detail_for(&ground, detail, authored, settings.middle_uses_fine_ground),
                    0,
                    1.0,
                );
                let drawn = Surface::new(&mesh);
                let cut = Surface::new(&underlay::remove_covered(&mesh, &unions[di]));
                prepared.add_tile_with_cut((0, 0), &drawn, &cut, di == 1).unwrap();
            }
            let path = std::env::temp_dir().join(format!("authored-neighbor-{}-{tag}.glb", std::process::id()));
            tile.write(
                &ground,
                (&[], &raised, &prepared, &unions[1], authored),
                &TileScenery::default(),
                &settings,
                Detail::Middle,
                &path,
            )
            .unwrap();
            let bytes = std::fs::read(&path).unwrap();
            std::fs::remove_file(path).unwrap();
            (bytes, tile.checksum(&[], &[], &ground, (&[], &raised, authored), (&TileScenery::default(), &[collar])))
        };
        let (without, checksum_without) = emit(&[], "without");
        let (with, checksum_with) = emit(&road, "with");
        assert_eq!(without, with, "road far in neighboring tile changed owner output");
        assert_eq!(checksum_without, checksum_with);
    }

    #[test]
    fn authored_crossings_keep_fine_ground_only_in_touched_middle_tiles() {
        let ground = Ground::page(24, 1.0, |i, j| (i * j) as f32 / 100.0);
        let near = Tile { columns: (0, 8), rows: (0, 8) };
        let far = Tile { columns: (16, 24), rows: (16, 24) };
        let authored = [authored::AuthoredSurface {
            name: "road",
            texture: Some("road"),
            tint: [1.0; 3],
            paint: None,
            vertex_paint: None,
            triangles: vec![authored::Triangle {
                xyz: [[1.0, 1.0, 0.0], [2.0, 1.0, 0.0], [1.0, 2.0, 0.0]],
                uv: [[0.0; 2]; 3],
                normal: [[0.0, 0.0, 1.0]; 3],
                colour: None,
            }],
        }];
        assert!(near.detail_for(&ground, Detail::Middle, &authored, false) == Detail::Full);
        assert!(far.detail_for(&ground, Detail::Middle, &authored, false) == Detail::Middle);
        assert!(near.detail_for(&ground, Detail::Middle, &[], false) == Detail::Middle);
        assert!(far.detail_for(&ground, Detail::Middle, &[], true) == Detail::Full);
        let full = near.ground(&ground, Detail::Full, 0, 1.0);
        let effective = near.ground(&ground, near.detail_for(&ground, Detail::Middle, &authored, false), 0, 1.0);
        assert_eq!(effective.positions, full.positions);
        assert_eq!(effective.indices, full.indices);
    }

    #[test]
    fn underlay_outside_loaded_ground_is_rejected() {
        let ground = Ground::page(8, 1.0, |_, _| 0.0);
        let settings = Settings {
            terrain_diagonals: None,
            ground: PathBuf::new(),
            south_west_m: [0.0, 0.0],
            ground_step_m: 1.0,
            page_steps: 8,
            tile_steps: 8,
            tiles: [[0, 0], [0, 0]],
            scenery_tiles: None,
            extent_m: None,
            middle_uses_fine_ground: false,
            ground_texture: "ground".into(),
            ground_texture_m: 6.0,
            ground_texture_mean: None,
            coloured_ground_texture: None,
            coloured_ground_texture_mean: None,
            spawn_m: [0.0, 0.0],
            spawn_bearing_deg: 0.0,
        };
        let p = |x, y| (DVec2::new(x, y), DVec2::ZERO);
        let owner = Raised {
            name: "outside".into(),
            texture: "ground".into(),
            ground: true,
            paint: None,
            height: 2.0,
            clearance: 0.1,
            cut_ground: true,
            triangles: vec![[p(100.0, 1.0), p(101.0, 1.0), p(100.0, 2.0)]],
        };
        let collar = underlay::owner_collar(&owner, 8.0).unwrap();
        assert!(underlay_for_owner(&ground, &owner, &settings, Detail::Full, collar, &[]).is_err());
    }

    #[test]
    fn owner_local_cut_emits_identical_tiles_with_distant_owner_and_expanded_map() {
        let ground = Ground::page(32, 1.0, |_, _| 0.0);
        let tile = Tile { columns: (0, 8), rows: (0, 8) };
        let owner = |x: f64| {
            let p = |x, y| (DVec2::new(x, y), DVec2::ZERO);
            Raised {
                name: "terrace".into(),
                texture: "ground".into(),
                ground: true,
                paint: None,
                height: 2.0,
                clearance: 0.1,
                cut_ground: true,
                triangles: vec![[p(x, 2.0), p(x + 3.0, 2.0), p(x, 5.0)]],
            }
        };
        for detail in [Detail::Full, Detail::Middle] {
            let emit = |expanded: bool| {
                let settings = Settings {
                    terrain_diagonals: None,
                    ground: PathBuf::new(),
                    south_west_m: [0.0, 0.0],
                    ground_step_m: 1.0,
                    page_steps: 32,
                    tile_steps: 8,
                    tiles: [[0, 0], if expanded { [3, 3] } else { [0, 0] }],
                    scenery_tiles: None,
                    extent_m: None,
                    middle_uses_fine_ground: false,
                    ground_texture: "ground".into(),
                    ground_texture_m: 6.0,
                    ground_texture_mean: None,
                    coloured_ground_texture: None,
                    coloured_ground_texture_mean: None,
                    spawn_m: [0.0, 0.0],
                    spawn_bearing_deg: 0.0,
                };
                let mut raised = vec![owner(6.0)];
                if expanded {
                    raised.push(owner(24.0));
                }
                let unions: [Vec<underlay::Underlay>; 2] = std::array::from_fn(|di| {
                    raised
                        .iter()
                        .map(|surface| {
                            let detail = if di == 0 { Detail::Full } else { Detail::Middle };
                            underlay_for_owner(
                                &ground,
                                surface,
                                &settings,
                                detail,
                                underlay::owner_collar(surface, 8.0).unwrap(),
                                &[],
                            )
                            .unwrap()
                            .unwrap()
                        })
                        .collect()
                });
                let mut prepared = raised::Prepared::new(&raised, DVec2::ZERO, 8.0);
                prepared.set_underlays(&unions);
                for (di, d) in [Detail::Full, Detail::Middle].into_iter().enumerate() {
                    let mesh = tile.ground(&ground, d, 0, 6.0);
                    let drawn = Surface::new(&mesh);
                    let cut = Surface::new(&underlay::remove_covered(&mesh, &unions[di]));
                    prepared.add_tile_with_cut((0, 0), &drawn, &cut, di == 1).unwrap();
                }
                let di = usize::from(detail == Detail::Middle);
                let path = std::env::temp_dir().join(format!("owner-local-{}-{di}-{expanded}.glb", std::process::id()));
                tile.write(
                    &ground,
                    (&[], &raised, &prepared, &unions[di], &[]),
                    &TileScenery::default(),
                    &settings,
                    detail,
                    &path,
                )
                .unwrap();
                let bytes = std::fs::read(&path).unwrap();
                std::fs::remove_file(path).unwrap();
                bytes
            };
            assert_eq!(emit(false), emit(true));
        }
    }

    #[test]
    fn spawn_selects_the_owner_at_its_runtime_position() {
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
        let mut prepared = raised::Prepared::new(&raised, DVec2::ZERO, 8.0);
        prepared.add_tile((0, 0), &drawn, false).unwrap();
        prepared.add_tile((0, 0), &drawn, true).unwrap();
        let at = DVec2::new(0.99999999, 0.25);
        assert_eq!(spawn_position(at, &ground, &prepared, None).unwrap(), DVec3::new(1.0, 0.25, 3.0));
        let empty = raised::Prepared::new(&[], DVec2::ZERO, 8.0);
        assert_eq!(spawn_position(at, &ground, &empty, None).unwrap(), at.extend(0.0));
    }

    #[test]
    fn raised_paint_profile_is_written_on_both_surface_nodes() {
        let ground = Ground::page(8, 1.0, |_, _| 0.0);
        let tile = Tile { columns: (0, 8), rows: (0, 8) };
        let settings = Settings {
            terrain_diagonals: None,
            ground: PathBuf::new(),
            south_west_m: [0.0, 0.0],
            ground_step_m: 1.0,
            page_steps: 8,
            tile_steps: 8,
            tiles: [[0, 0], [0, 0]],
            scenery_tiles: None,
            extent_m: None,
            middle_uses_fine_ground: false,
            ground_texture: "ground".into(),
            ground_texture_m: 6.0,
            ground_texture_mean: None,
            coloured_ground_texture: None,
            coloured_ground_texture_mean: None,
            spawn_m: [0.0, 0.0],
            spawn_bearing_deg: 0.0,
        };
        let p = |x, y| (DVec2::new(x, y), DVec2::new(x, y));
        let raised = [Raised {
            name: "paving".into(),
            texture: "ground".into(),
            ground: true,
            height: 2.0,
            clearance: 0.1,
            cut_ground: false,
            paint: Some(raised::SurfacePaint {
                haze_start_m: 30.0,
                haze_length_m: 9000.0,
                haze_colour: [0.0932, 0.2301, 0.5328],
            }),
            triangles: vec![[p(1.0, 1.0), p(3.0, 1.0), p(1.0, 3.0)]],
        }];
        let drawn = Surface::new(&tile.ground(&ground, Detail::Full, 0, 1.0));
        let mut prepared = raised::Prepared::new(&raised, DVec2::ZERO, 8.0);
        prepared.add_tile((0, 0), &drawn, false).unwrap();
        prepared.add_tile((0, 0), &drawn, true).unwrap();
        for (detail, suffix) in [(Detail::Full, "full"), (Detail::Middle, "middle")] {
            let path = std::env::temp_dir().join(format!("raised-paint-{}-{suffix}.glb", std::process::id()));
            tile.write(&ground, (&[], &raised, &prepared, &[], &[]), &TileScenery::default(), &settings, detail, &path)
                .unwrap();
            let bytes = std::fs::read(&path).unwrap();
            std::fs::remove_file(&path).unwrap();
            let len = u32::from_le_bytes(bytes[12..16].try_into().unwrap()) as usize;
            let value: serde_json::Value = serde_json::from_slice(&bytes[20..20 + len]).unwrap();
            let painted: Vec<_> = value["nodes"]
                .as_array()
                .unwrap()
                .iter()
                .filter(|node| node["extras"].get("surface_paint").is_some())
                .collect();
            assert_eq!(painted.len(), 1);
            assert_eq!(painted[0]["name"], "ground");
            assert_eq!(painted[0]["extras"]["surface_paint"]["haze_start_m"], 30.0);
            assert_eq!(painted[0]["extras"]["surface_paint"]["haze_length_m"], 9000.0);
        }
    }

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
