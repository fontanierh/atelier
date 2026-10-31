//! What each tile is made from, as one checksum per tile, so an export rebuilds only the tiles whose inputs changed.
//!
//! A tile's checksum covers the code that writes tiles, the settings it uses, the heights it reads (its own and one
//! step around it, which its edge slopes read), the overlay triangles that reach into it, and its scenery: the models
//! standing in it, its pieces of rails and the cables starting in it, with their ends. The checksums are kept
//! in `tiles/checksums.toml`.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use sha2::{Digest, Sha256};

use super::Tile;
use super::authored::AuthoredSurface;
use super::ground::Ground;
use super::overlay::Overlay;
use super::raised::{Raised, stored};
use super::scenery::{self, TileScenery};
use crate::EXPORTER;
use glam::DVec2;

/// The file, under `tiles/`, holding each tile's checksum.
pub const FILE: &str = "checksums.toml";

/// A checksum of the code that writes tiles, which goes into every tile's: the world's code but the regions list,
/// whose regions' overlays a tile's checksum covers instead, and the shared code but the command.
pub fn code() -> Result<Vec<u8>> {
    let code = tile_code(crate::code("src/world")?);
    let mut digest = Sha256::new();
    crate::add_files(&mut digest, Path::new(EXPORTER), &code)?;
    Ok(digest.finalize().to_vec())
}

fn tile_code(code: Vec<PathBuf>) -> Vec<PathBuf> {
    let schema = Path::new(EXPORTER).join("../../schemas/water");
    let skate_schema = Path::new(EXPORTER).join("../../schemas/world-skate");
    code.into_iter()
        .filter(|file| {
            !file.ends_with("src/world/regions.rs")
                && !file.ends_with("src/world/skate.rs")
                && !file.ends_with("src/main.rs")
                && !file.starts_with(&schema)
                && !file.starts_with(&skate_schema)
        })
        .collect()
}

impl Tile {
    /// The checksum of everything this tile is made from. `code` is [`code`], and `settings` the settings that tiles
    /// use, serialized.
    pub fn checksum(
        &self,
        code: &[u8],
        settings: &[u8],
        ground: &Ground,
        surfaces: (&[Overlay], &[Raised], &[AuthoredSurface]),
        scenery_and_collar: (&TileScenery, &[f64]),
    ) -> String {
        let (scenery, collars) = scenery_and_collar;
        let (overlays, raised, authored) = surfaces;
        let mut digest = Sha256::new();
        digest.update(code);
        digest.update(settings);
        for k in [self.columns.0, self.columns.1, self.rows.0, self.rows.1] {
            digest.update((k as u64).to_le_bytes());
        }
        // Overlay normals sample ground one step beyond the tile, including the diagonals there.
        for j in self.rows.0.saturating_sub(1)..=self.rows.1 {
            for i in self.columns.0.saturating_sub(1)..=self.columns.1 {
                digest.update([u8::from(ground.alternate_diagonal(i, j))]);
            }
        }
        for j in self.rows.0.saturating_sub(1)..=self.rows.1 + 1 {
            for i in self.columns.0.saturating_sub(1)..=self.columns.1 + 1 {
                digest.update(ground.sample(i, j).unwrap_or(f64::NAN).to_bits().to_le_bytes());
            }
        }
        // A point's colour tints the ground there and chooses the tile's texture; only the tile's own points do.
        for j in self.rows.0..=self.rows.1 {
            for i in self.columns.0..=self.columns.1 {
                for c in ground.colour(i, j).unwrap_or([f32::NAN; 3]) {
                    digest.update(c.to_bits().to_le_bytes());
                }
            }
        }
        let (low, high) = (
            ground.position(self.columns.0 as f64, self.rows.0 as f64),
            ground.position(self.columns.1 as f64, self.rows.1 as f64),
        );
        for surface in authored {
            let triangles: Vec<_> = surface
                .triangles
                .iter()
                .filter(|triangle| {
                    let points = triangle.xyz.map(|p| DVec2::new(p[0], p[1]));
                    let from = points[0].min(points[1]).min(points[2]);
                    let to = points[0].max(points[1]).max(points[2]);
                    from.cmple(high).all() && to.cmpge(low).all()
                })
                .collect();
            if triangles.is_empty() {
                continue;
            }
            digest.update(surface.name.as_bytes());
            digest.update([0]);
            if let Some(texture) = surface.texture {
                digest.update(texture.as_bytes());
            }
            digest.update([0]);
            for value in surface.tint {
                digest.update(value.to_bits().to_le_bytes());
            }
            digest.update(serde_json::to_vec(&surface.paint).expect("paint serializes"));
            if let Some(paint) = &surface.vertex_paint {
                digest.update(serde_json::to_vec(paint).expect("vertex paint serializes"));
            }
            digest.update(serde_json::to_vec(&triangles).expect("source triangles serialize"));
        }
        for overlay in overlays {
            let inside: Vec<_> = overlay
                .triangles
                .iter()
                .filter(|triangle| {
                    let corners = triangle.map(|(p, _)| p);
                    let (from, to) =
                        (corners[0].min(corners[1]).min(corners[2]), corners[0].max(corners[1]).max(corners[2]));
                    from.cmple(high).all() && to.cmpge(low).all()
                })
                .collect();
            if inside.is_empty() {
                continue;
            }
            digest.update(overlay.name.as_bytes());
            digest.update([0]);
            digest.update(overlay.texture.as_bytes());
            digest.update([0]);
            for triangle in inside {
                for (p, uv) in triangle {
                    for v in [p.x, p.y, uv.x, uv.y] {
                        digest.update(v.to_bits().to_le_bytes());
                    }
                }
            }
        }
        for (index, surface) in raised.iter().enumerate() {
            let collar = collars.get(index).copied().unwrap_or(0.0);
            let triangles: Vec<_> = surface
                .triangles
                .iter()
                .filter(|triangle| {
                    let [a, b, c] = triangle.map(|(p, _)| stored(p));
                    let padding = if surface.cut_ground { collar * 4.0 } else { 0.0 };
                    a.min(b).min(c).cmple(high + DVec2::splat(padding)).all()
                        && a.max(b).max(c).cmpge(low - DVec2::splat(padding)).all()
                })
                .collect();
            if triangles.is_empty() {
                continue;
            }
            digest.update(surface.name.as_bytes());
            digest.update([0]);
            digest.update(surface.texture.as_bytes());
            digest.update([0]);
            digest.update(surface.node_name().as_bytes());
            digest.update([0]);
            digest.update(serde_json::to_vec(&surface.paint).expect("paint serializes"));
            digest.update(surface.height.to_bits().to_le_bytes());
            digest.update(surface.clearance.to_bits().to_le_bytes());
            if surface.cut_ground {
                digest.update([1]);
                digest.update(collar.to_bits().to_le_bytes());
            }
            for triangle in triangles {
                for (p, uv) in triangle {
                    for value in [p.x, p.y, uv.x, uv.y] {
                        digest.update(value.to_bits().to_le_bytes());
                    }
                }
            }
        }
        digest.update(scenery::checksum_bytes(scenery));
        format!("{:x}", digest.finalize())
    }
}

/// The checksums in `tiles/`, by tile file stem; none if it has none.
pub fn read(tiles: &Path) -> Result<BTreeMap<String, String>> {
    let file = tiles.join(FILE);
    if !file.is_file() {
        return Ok(BTreeMap::new());
    }
    let text = fs::read_to_string(&file)?;
    toml_edit::de::from_str(&text).with_context(|| format!("reading {}", file.display()))
}

pub fn write(tiles: &Path, checksums: &BTreeMap<String, String>) -> Result<()> {
    let mut text = String::from("# Each tile's inputs checksum, written by the export.\n");
    for (tile, checksum) in checksums {
        text.push_str(&format!("{tile} = \"{checksum}\"\n"));
    }
    Ok(fs::write(tiles.join(FILE), text)?)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn index_only_skating_schema_and_assembly_do_not_invalidate_tiles() {
        let world = crate::code("src/world").unwrap();
        let schema = Path::new(EXPORTER).join("../../schemas/world-skate/src/lib.rs");
        let assembly = Path::new(EXPORTER).join("src/world/skate.rs");
        assert!(world.contains(&schema));
        assert!(world.contains(&assembly.to_path_buf()));
        let tiles = tile_code(world);
        assert!(!tiles.contains(&schema));
        assert!(!tiles.contains(&assembly.to_path_buf()));
    }
    #[test]
    fn water_schema_invalidates_world_input_but_not_tile_code() {
        let world = crate::code("src/world").unwrap();
        let schema = Path::new(EXPORTER).join("../../schemas/water/src/lib.rs");
        assert!(world.contains(&schema));
        assert!(!tile_code(world).contains(&schema));
        assert!(!crate::code("src/model").unwrap().contains(&schema));
    }
}
