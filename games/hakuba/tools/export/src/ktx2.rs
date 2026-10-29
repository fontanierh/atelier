//! KTX2 files, which the texture kind and props' own textures write: an image's full mipmap chain, each level
//! averaged in linear light, stored as 8-bit sRGB or sRGB BC7 blocks and compressed with zstd.

use std::fs;
use std::path::Path;

use anyhow::{Context, Result, bail};
use ktx2::dfd::{Basic, Block};
use ktx2::{Format, Header, Index, LevelIndex, SupercompressionScheme};
use ruzstd::encoding::{CompressionLevel, compress_to_vec};
use serde::{Deserialize, Serialize};

/// How a level's colours average the texels it covers.
#[derive(Clone, Copy, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MipColour {
    #[default]
    OpacityWeighted,
    Average,
}

/// Writes the image `file`, whose sides must be powers of two, to `output` as BC7 with every mipmap level, each the
/// plain average of the one above.
pub fn write_bc7(file: &Path, output: &Path) -> Result<()> {
    let image = image::open(file).with_context(|| format!("reading {}", file.display()))?.to_rgba8();
    let (width, height) = image.dimensions();
    if !width.is_power_of_two() || !height.is_power_of_two() {
        bail!("{} is {width} × {height}: each side must be a power of two", file.display());
    }
    let mut levels = vec![Level { width, height, rgba: image.into_raw() }];
    while let Some(smaller) = levels.last().unwrap().halved(MipColour::Average) {
        levels.push(smaller);
    }
    fs::write(output, bc7_ktx2(width, height, &levels)?)?;
    Ok(())
}

/// One mipmap level: its size in pixels, and its pixels row by row, four sRGB bytes each.
pub struct Level {
    pub width: u32,
    pub height: u32,
    pub rgba: Vec<u8>,
}

impl Level {
    /// The next level, half as wide and high (a side already one pixel stays one), each pixel the average of those it
    /// covers in linear light, using the selected colour averaging mode; none past one pixel.
    pub fn halved(&self, mode: MipColour) -> Option<Level> {
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
}

/// An sRGB byte in linear light, from 0 to 1.
pub fn linear(byte: u8) -> f32 {
    let c = byte as f32 / 255.0;
    if c <= 0.04045 { c / 12.92 } else { ((c + 0.055) / 1.055).powf(2.4) }
}

/// A linear value from 0 to 1 as an sRGB byte.
pub fn srgb(c: f32) -> u8 {
    let c = if c <= 0.0031308 { c * 12.92 } else { 1.055 * c.powf(1.0 / 2.4) - 0.055 };
    (c.clamp(0.0, 1.0) * 255.0).round() as u8
}

/// The KTX2 file holding `levels`, largest first: the header, the index of levels, the format's description, then
/// each level compressed, smallest first.
pub fn ktx2(width: u32, height: u32, levels: &[Level]) -> Result<Vec<u8>> {
    let bytes: Vec<&[u8]> = levels.iter().map(|level| level.rgba.as_slice()).collect();
    encode_ktx2(width, height, Format::R8G8B8A8_SRGB, &bytes)
}

/// As [`ktx2`], each level stored as sRGB BC7 blocks of 4 × 4 texels; a level smaller than a block repeats its edge
/// texels to fill one. A level with clear texels keeps its alpha; an opaque one spends every bit on colour.
pub fn bc7_ktx2(width: u32, height: u32, levels: &[Level]) -> Result<Vec<u8>> {
    let blocks: Vec<Vec<u8>> = levels.iter().map(bc7).collect();
    let bytes: Vec<&[u8]> = blocks.iter().map(Vec::as_slice).collect();
    encode_ktx2(width, height, Format::BC7_SRGB_BLOCK, &bytes)
}

fn bc7(level: &Level) -> Vec<u8> {
    let (width, height) = (level.width.next_multiple_of(4), level.height.next_multiple_of(4));
    let mut rgba = Vec::with_capacity((width * height * 4) as usize);
    for y in 0..height {
        for x in 0..width {
            let at = ((y.min(level.height - 1) * level.width + x.min(level.width - 1)) * 4) as usize;
            rgba.extend_from_slice(&level.rgba[at..at + 4]);
        }
    }
    let opaque = level.rgba.chunks_exact(4).all(|pixel| pixel[3] == 255);
    let settings =
        if opaque { intel_tex_2::bc7::opaque_basic_settings() } else { intel_tex_2::bc7::alpha_basic_settings() };
    let surface = intel_tex_2::RgbaSurface { data: &rgba, width, height, stride: width * 4 };
    intel_tex_2::bc7::compress_blocks(&settings, &surface)
}

pub fn encode_ktx2(width: u32, height: u32, format: Format, levels: &[&[u8]]) -> Result<Vec<u8>> {
    let (basic, type_size) = Basic::from_format(format).map_err(|e| anyhow::anyhow!("{e:?}"))?;
    let block = Block::Basic(basic).to_vec();
    let mut dfd = ((4 + block.len()) as u32).to_le_bytes().to_vec();
    dfd.extend(block);

    let compressed: Vec<Vec<u8>> =
        levels.iter().map(|level| compress_to_vec(*level, CompressionLevel::Fastest)).collect();
    let dfd_offset = Header::LENGTH + levels.len() * LevelIndex::LENGTH;
    let mut offset = dfd_offset + dfd.len();
    let mut index = vec![None; levels.len()];
    for k in (0..levels.len()).rev() {
        index[k] = Some(LevelIndex {
            byte_offset: offset as u64,
            byte_length: compressed[k].len() as u64,
            uncompressed_byte_length: levels[k].len() as u64,
        });
        offset += compressed[k].len();
    }

    let header = Header {
        format: Some(format),
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
