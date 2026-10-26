//! What each tile is made from, as one checksum per tile, so an export rebuilds only the tiles whose inputs changed.
//!
//! A tile's checksum covers the code that writes tiles, the settings it uses, the heights it reads (its own and one
//! step around it, which its edge slopes read), and the overlay triangles that reach into it. The checksums are kept
//! in `tiles/checksums.toml`.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use sha2::{Digest, Sha256};

use super::Tile;
use super::ground::Ground;
use super::overlay::Overlay;
use crate::{EXPORTER, files};

/// The file, under `tiles/`, holding each tile's checksum.
pub const FILE: &str = "checksums.toml";

/// The exporter's files that tiles are written by: `world/` but the regions list, whose regions' overlays a tile's
/// checksum covers instead, the glTF writer, and the crate versions they are built with.
fn tile_code() -> Result<Vec<PathBuf>> {
    let root = Path::new(EXPORTER);
    let mut code: Vec<PathBuf> =
        files(&root.join("src/world"))?.into_iter().filter(|file| !file.ends_with("regions.rs")).collect();
    code.extend([root.join("src/glb.rs"), root.join("Cargo.toml"), root.join("../../Cargo.lock")]);
    Ok(code)
}

/// A checksum of the code that writes tiles, which goes into every tile's.
pub fn code() -> Result<Vec<u8>> {
    let mut digest = Sha256::new();
    for file in tile_code()? {
        digest.update(file.strip_prefix(EXPORTER)?.to_string_lossy().as_bytes());
        digest.update([0]);
        digest.update(Sha256::digest(fs::read(&file).with_context(|| format!("reading {}", file.display()))?));
    }
    Ok(digest.finalize().to_vec())
}

impl Tile {
    /// The checksum of everything this tile is made from. `code` is [`code`], and `settings` the settings that tiles
    /// use, serialized.
    pub fn checksum(&self, code: &[u8], settings: &[u8], ground: &Ground, overlays: &[Overlay]) -> String {
        let mut digest = Sha256::new();
        digest.update(code);
        digest.update(settings);
        for k in [self.columns.0, self.columns.1, self.rows.0, self.rows.1] {
            digest.update((k as u64).to_le_bytes());
        }
        for j in self.rows.0.saturating_sub(1)..=self.rows.1 + 1 {
            for i in self.columns.0.saturating_sub(1)..=self.columns.1 + 1 {
                digest.update(ground.sample(i, j).unwrap_or(f64::NAN).to_bits().to_le_bytes());
            }
        }
        let (low, high) = (
            ground.position(self.columns.0 as f64, self.rows.0 as f64),
            ground.position(self.columns.1 as f64, self.rows.1 as f64),
        );
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
            for c in overlay.colour {
                digest.update(c.to_bits().to_le_bytes());
            }
            for triangle in inside {
                for (p, uv) in triangle {
                    for v in [p.x, p.y, uv.x, uv.y] {
                        digest.update(v.to_bits().to_le_bytes());
                    }
                }
            }
        }
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
