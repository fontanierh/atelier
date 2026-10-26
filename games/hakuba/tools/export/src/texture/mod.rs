//! The `texture` kind: an image other assets name, written as `<folder name>.ktx2` with every mipmap level, so it
//! draws smoothly both near and far. Each level averages the one above it in linear light, and is stored as 8-bit
//! sRGB, compressed with zstd. A texture's sides must be powers of two.

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
}

pub fn export(folder: &Path, settings: &Settings, output: &Path) -> Result<()> {
    let file = folder.join(&settings.source);
    let image = image::open(&file).with_context(|| format!("reading {}", file.display()))?.to_rgba8();
    let (width, height) = image.dimensions();
    if !width.is_power_of_two() || !height.is_power_of_two() {
        bail!("{} is {width} × {height}: each side must be a power of two", file.display());
    }
    let mut levels = vec![Level { width, height, rgba: image.into_raw() }];
    while let Some(smaller) = levels.last().unwrap().halved() {
        levels.push(smaller);
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
    /// covers in linear light; none past one pixel.
    fn halved(&self) -> Option<Level> {
        if self.width == 1 && self.height == 1 {
            return None;
        }
        let (width, height) = ((self.width / 2).max(1), (self.height / 2).max(1));
        let (step_x, step_y) = (self.width / width, self.height / height);
        let mut rgba = Vec::with_capacity((width * height * 4) as usize);
        for y in 0..height {
            for x in 0..width {
                let mut sum = [0.0f32; 4];
                for (dx, dy) in (0..step_x).flat_map(|dx| (0..step_y).map(move |dy| (dx, dy))) {
                    let at = (((y * step_y + dy) * self.width + x * step_x + dx) * 4) as usize;
                    for (c, total) in sum.iter_mut().enumerate() {
                        let byte = self.rgba[at + c];
                        *total += if c < 3 { linear(byte) } else { byte as f32 / 255.0 };
                    }
                }
                let n = (step_x * step_y) as f32;
                rgba.extend([srgb(sum[0] / n), srgb(sum[1] / n), srgb(sum[2] / n), (sum[3] / n * 255.0).round() as u8]);
            }
        }
        Some(Level { width, height, rgba })
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
        while let Some(smaller) = levels.last().unwrap().halved() {
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

    /// A mipmap averages in linear light: black and white make a mid grey of 188, not 128.
    #[test]
    fn averages_in_linear_light() {
        let level = Level { width: 2, height: 1, rgba: vec![0, 0, 0, 255, 255, 255, 255, 255] };
        assert_eq!(level.halved().unwrap().rgba, [188, 188, 188, 255]);
    }
}
