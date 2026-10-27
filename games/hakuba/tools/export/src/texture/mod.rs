//! The `texture` kind: an image other assets name, written as `<folder name>.ktx2` with every mipmap level, so it
//! draws smoothly both near and far. Each level averages the one above it in linear light, with either opacity-weighted
//! or plain colours as the asset declares, and is stored as 8-bit sRGB, compressed with zstd. In an image with clear
//! parts, every level preserves coverage at the asset's declared alpha cutoff (0.5 by default). A texture's sides must
//! be powers of two.

use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use ktx2::dfd::{Basic, Block};
use ktx2::{Format, Header, Index, LevelIndex, SupercompressionScheme};
use ruzstd::encoding::{CompressionLevel, compress_to_vec};
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Settings {
    /// The image, relative to the asset folder.
    source: PathBuf,
    /// Alpha threshold used to preserve masked coverage in lower mip levels.
    #[serde(default = "default_cutoff")]
    alpha_cutoff: f32,
    /// Colour averaging method for mipmaps; defaults to opacity-weighted.
    #[serde(default)]
    mip_colour: MipColour,
}

#[derive(Clone, Copy, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
enum MipColour {
    #[default]
    OpacityWeighted,
    Average,
}

fn default_cutoff() -> f32 {
    0.5
}

pub fn export(folder: &Path, settings: &Settings, output: &Path) -> Result<()> {
    if !settings.alpha_cutoff.is_finite() || !(0.0 < settings.alpha_cutoff && settings.alpha_cutoff <= 1.0) {
        bail!("alpha cutoff must be finite and greater than 0 and at most 1");
    }
    let file = folder.join(&settings.source);
    let image = image::open(&file).with_context(|| format!("reading {}", file.display()))?.to_rgba8();
    let (width, height) = image.dimensions();
    if !width.is_power_of_two() || !height.is_power_of_two() {
        bail!("{} is {width} × {height}: each side must be a power of two", file.display());
    }
    let mut levels = vec![Level { width, height, rgba: image.into_raw() }];
    while let Some(smaller) = levels.last().unwrap().halved(settings.mip_colour) {
        levels.push(smaller);
    }
    let coverage = levels[0].coverage(1.0, settings.alpha_cutoff);
    if coverage < 1.0 {
        for level in &mut levels[1..] {
            level.keep_coverage(coverage, settings.alpha_cutoff);
        }
    }
    fs::write(output, ktx2(width, height, &levels)?)?;
    Ok(())
}

/// One mipmap level: its size in pixels, and its pixels row by row, four sRGB bytes each.
struct Level {
    width: u32,
    height: u32,
    rgba: Vec<u8>,
}

impl Level {
    /// The next level, half as wide and high (a side already one pixel stays one), each pixel the average of those it
    /// covers in linear light, using the selected colour averaging mode; none past one pixel.
    fn halved(&self, mode: MipColour) -> Option<Level> {
        if self.width == 1 && self.height == 1 {
            return None;
        }
        let (width, height) = ((self.width / 2).max(1), (self.height / 2).max(1));
        let (step_x, step_y) = (self.width / width, self.height / height);
        let mut rgba = Vec::with_capacity((width * height * 4) as usize);
        for y in 0..height {
            for x in 0..width {
                // The colours weighted by opacity, the plain colours (for a pixel clear all over), and the opacity.
                let (mut weighted, mut plain, mut opacity) = ([0.0f32; 3], [0.0f32; 3], 0.0);
                for (dx, dy) in (0..step_x).flat_map(|dx| (0..step_y).map(move |dy| (dx, dy))) {
                    let at = (((y * step_y + dy) * self.width + x * step_x + dx) * 4) as usize;
                    let alpha = self.rgba[at + 3] as f32 / 255.0;
                    for c in 0..3 {
                        weighted[c] += linear(self.rgba[at + c]) * alpha;
                        plain[c] += linear(self.rgba[at + c]);
                    }
                    opacity += alpha;
                }
                let n = (step_x * step_y) as f32;
                let colour = |c: usize| match mode {
                    MipColour::OpacityWeighted if opacity > 0.0 => weighted[c] / opacity,
                    _ => plain[c] / n,
                };
                rgba.extend([srgb(colour(0)), srgb(colour(1)), srgb(colour(2)), (opacity / n * 255.0).round() as u8]);
            }
        }
        Some(Level { width, height, rgba })
    }

    /// The share of pixels at least as opaque as the cutoff once every opacity is multiplied by `scale`.
    fn coverage(&self, scale: f32, cutoff: f32) -> f32 {
        let pixels = self.rgba.len() / 4;
        let covered = self.rgba.chunks(4).filter(|p| p[3] as f32 / 255.0 * scale >= cutoff).count();
        covered as f32 / pixels as f32
    }

    /// Scales every opacity by the least factor that makes the level cover at least `share` of its pixels at the cutoff.
    fn keep_coverage(&mut self, share: f32, cutoff: f32) {
        let (mut low, mut high) = (0.0f32, 4.0f32);
        for _ in 0..24 {
            let middle = (low + high) / 2.0;
            if self.coverage(middle, cutoff) < share { low = middle } else { high = middle }
        }
        for pixel in self.rgba.chunks_mut(4) {
            pixel[3] = (pixel[3] as f32 * high).round().min(255.0) as u8;
        }
    }
}

/// An sRGB byte in linear light, from 0 to 1.
fn linear(byte: u8) -> f32 {
    let c = byte as f32 / 255.0;
    if c <= 0.04045 { c / 12.92 } else { ((c + 0.055) / 1.055).powf(2.4) }
}

/// A linear value from 0 to 1 as an sRGB byte.
fn srgb(c: f32) -> u8 {
    let c = if c <= 0.0031308 { c * 12.92 } else { 1.055 * c.powf(1.0 / 2.4) - 0.055 };
    (c.clamp(0.0, 1.0) * 255.0).round() as u8
}

/// The KTX2 file holding `levels`, largest first: the header, the index of levels, the format's description, then
/// each level compressed, smallest first.
fn ktx2(width: u32, height: u32, levels: &[Level]) -> Result<Vec<u8>> {
    let (basic, type_size) = Basic::from_format(Format::R8G8B8A8_SRGB).map_err(|e| anyhow::anyhow!("{e:?}"))?;
    let block = Block::Basic(basic).to_vec();
    let mut dfd = ((4 + block.len()) as u32).to_le_bytes().to_vec();
    dfd.extend(block);

    let compressed: Vec<Vec<u8>> =
        levels.iter().map(|level| compress_to_vec(level.rgba.as_slice(), CompressionLevel::Fastest)).collect();
    let dfd_offset = Header::LENGTH + levels.len() * LevelIndex::LENGTH;
    let mut offset = dfd_offset + dfd.len();
    let mut index = vec![None; levels.len()];
    for k in (0..levels.len()).rev() {
        index[k] = Some(LevelIndex {
            byte_offset: offset as u64,
            byte_length: compressed[k].len() as u64,
            uncompressed_byte_length: levels[k].rgba.len() as u64,
        });
        offset += compressed[k].len();
    }

    let header = Header {
        format: Some(Format::R8G8B8A8_SRGB),
        type_size,
        pixel_width: width,
        pixel_height: height,
        pixel_depth: 0,
        layer_count: 0,
        face_count: 1,
        level_count: levels.len() as u32,
        supercompression_scheme: Some(SupercompressionScheme::Zstandard),
        index: Index {
            dfd_byte_offset: dfd_offset as u32,
            dfd_byte_length: dfd.len() as u32,
            kvd_byte_offset: 0,
            kvd_byte_length: 0,
            sgd_byte_offset: 0,
            sgd_byte_length: 0,
        },
    };
    let mut file = header.as_bytes().to_vec();
    for level in index.into_iter().flatten() {
        file.extend(level.as_bytes());
    }
    file.extend(dfd);
    for level in compressed.iter().rev() {
        file.extend(level);
    }
    Ok(file)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The file reads back with the reader the game uses: every level, smallest last, each pixel as written.
    #[test]
    fn reads_back() {
        let rgba: Vec<u8> = (0..4 * 2 * 4).map(|k| (k * 7) as u8).collect();
        let mut levels = vec![Level { width: 4, height: 2, rgba }];
        while let Some(smaller) = levels.last().unwrap().halved(MipColour::OpacityWeighted) {
            levels.push(smaller);
        }
        assert_eq!(levels.iter().map(|l| (l.width, l.height)).collect::<Vec<_>>(), [(4, 2), (2, 1), (1, 1)]);
        let file = ktx2(4, 2, &levels).unwrap();
        let reader = ktx2::Reader::new(file.as_slice()).unwrap();
        assert_eq!(reader.header().format, Some(Format::R8G8B8A8_SRGB));
        assert!(reader.basic_dfd().is_some());
        for (read, level) in reader.levels().zip(&levels) {
            let pixels = ruzstd::decoding::StreamingDecoder::new(read.data).unwrap();
            let pixels: Vec<u8> = std::io::Read::bytes(pixels).map(|b| b.unwrap()).collect();
            assert_eq!(pixels, level.rgba);
        }
    }

    /// A clear pixel adds no colour to the level below it: an opaque red beside a clear white stays red.
    #[test]
    fn clear_pixels_add_no_colour() {
        let level = Level { width: 2, height: 1, rgba: vec![255, 0, 0, 255, 255, 255, 255, 0] };
        assert_eq!(level.halved(MipColour::OpacityWeighted).unwrap().rgba, [255, 0, 0, 128]);
    }

    #[test]
    fn plain_mips_average_colour_even_for_clear_pixels() {
        let level = Level { width: 2, height: 1, rgba: vec![255, 0, 0, 255, 255, 255, 255, 0] };
        assert_eq!(level.halved(MipColour::Average).unwrap().rgba, [255, 188, 188, 128]);
    }

    /// A sparse cut-out does not fade away as it shrinks: one opaque pixel in four averages to a quarter opacity,
    /// below the cutoff, and is raised back above it, while clear parts stay clear.
    #[test]
    fn keeps_coverage() {
        let opaque = |k: u32| k.is_multiple_of(2) && (k / 8).is_multiple_of(2) && k % 8 < 4;
        let rgba = (0..64).flat_map(|k| [0, 0, 0, if opaque(k) { 255 } else { 0 }]).collect();
        let full = Level { width: 8, height: 8, rgba };
        let mut level = full.halved(MipColour::OpacityWeighted).unwrap();
        assert_eq!(level.coverage(1.0, 0.5), 0.0);
        level.keep_coverage(full.coverage(1.0, 0.5), 0.5);
        assert!(level.coverage(1.0, 0.5) >= full.coverage(1.0, 0.5));
        assert!(level.rgba.chunks(4).filter(|p| p[3] == 0).count() == 8);
    }

    #[test]
    fn coverage_uses_asset_cutoff() {
        let level = Level { width: 2, height: 1, rgba: vec![0, 0, 0, 110, 0, 0, 0, 130] };
        assert_eq!(level.coverage(1.0, 0.4), 1.0);
        assert_eq!(level.coverage(1.0, 0.5), 0.5);
    }

    /// A mipmap averages in linear light: black and white make a mid grey of 188, not 128.
    #[test]
    fn averages_in_linear_light() {
        let level = Level { width: 2, height: 1, rgba: vec![0, 0, 0, 255, 255, 255, 255, 255] };
        assert_eq!(level.halved(MipColour::OpacityWeighted).unwrap().rgba, [188, 188, 188, 255]);
    }
}
