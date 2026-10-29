//! The `texture` kind: an image other assets name, written as `<folder name>.ktx2` with every mipmap level, so it
//! draws smoothly both near and far. Each level averages the one above it in linear light, with either opacity-weighted
//! or plain colours as the asset declares, and is stored as 8-bit sRGB, or with `compression = "bc7"` as sRGB BC7
//! blocks, a quarter of the size in memory and on the wire, then compressed with zstd. In an image with clear parts,
//! every level preserves coverage at the asset's declared alpha cutoff (0.5 by default). A texture's sides must be
//! powers of two. `alpha_shadow = true` also writes `<name>.alpha.ktx2`, a linear R8 copy of each final mip’s alpha.

use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail, ensure};
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
    /// Also export the exact final mip alpha as a linear R8 shadow texture.
    #[serde(default)]
    pub alpha_shadow: bool,
    /// How each level's texels are stored: plain 8-bit RGBA, or BC7 blocks.
    #[serde(default)]
    compression: Compression,
}

#[derive(Clone, Copy, Default, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
enum Compression {
    #[default]
    None,
    Bc7,
}

impl Settings {
    pub fn outputs(&self, output: &Path) -> Vec<PathBuf> {
        let mut files = vec![output.to_path_buf()];
        if self.alpha_shadow {
            files.push(shadow_file(output));
        }
        files
    }

    pub fn output_problems(&self, output: &Path) -> Vec<String> {
        if self.alpha_shadow
            && let Err(error) = validate_shadow(output)
        {
            return vec![format!("shadow alpha export missing or invalid: {error}")];
        }
        Vec::new()
    }
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
    if !(settings.alpha_cutoff.is_finite() && 0.0 < settings.alpha_cutoff && settings.alpha_cutoff <= 1.0) {
        bail!("alpha cutoff must be finite and greater than 0 and at most 1");
    }
    if settings.alpha_shadow && settings.compression != Compression::None {
        bail!("an alpha shadow needs an uncompressed texture");
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
    let file = match settings.compression {
        Compression::None => ktx2(width, height, &levels)?,
        Compression::Bc7 => bc7_ktx2(width, height, &levels)?,
    };
    fs::write(output, file)?;
    let shadow = shadow_file(output);
    if settings.alpha_shadow {
        fs::write(shadow, alpha_ktx2(width, height, &levels)?)?;
    } else if shadow.is_file() {
        fs::remove_file(shadow)?;
    }
    Ok(())
}

/// The declared alpha companion beside a texture's colour export.
pub fn shadow_file(output: &Path) -> PathBuf {
    output.with_extension("alpha.ktx2")
}

/// @cc [owner:fontanierh,label:correctness] shadow-alpha-mips
/// An alpha companion MUST be linear R8 with the colour export's dimensions and complete mip chain. Every decoded
/// byte MUST equal the corresponding final colour mip's alpha, including coverage correction.
pub fn validate_shadow(output: &Path) -> Result<()> {
    let colour = fs::read(output).with_context(|| format!("reading {}", output.display()))?;
    let shadow_path = shadow_file(output);
    let shadow = fs::read(&shadow_path).with_context(|| format!("reading {}", shadow_path.display()))?;
    let colour = ktx2::Reader::new(colour.as_slice()).context("invalid colour KTX2")?;
    let shadow = ktx2::Reader::new(shadow.as_slice()).context("invalid shadow KTX2")?;
    let a = colour.header();
    let b = shadow.header();
    ensure!(a.format == Some(Format::R8G8B8A8_SRGB), "shadow source must be RGBA8 sRGB");
    ensure!(b.format == Some(Format::R8_UNORM), "shadow companion must be linear R8");
    ensure!(
        a.pixel_width.is_power_of_two()
            && a.pixel_height.is_power_of_two()
            && a.pixel_width == b.pixel_width
            && a.pixel_height == b.pixel_height,
        "shadow companion dimensions differ from colour"
    );
    let mip_count = a.pixel_width.max(a.pixel_height).ilog2() + 1;
    ensure!(a.level_count == mip_count && b.level_count == mip_count, "shadow companion mip chain differs from colour");
    for header in [a, b] {
        ensure!(
            header.type_size == 1
                && header.pixel_depth == 0
                && header.layer_count == 0
                && header.face_count == 1
                && header.supercompression_scheme == Some(SupercompressionScheme::Zstandard),
            "shadow textures must be two-dimensional Zstandard KTX2"
        );
    }
    for (mip, (colour, shadow)) in colour.levels().zip(shadow.levels()).enumerate() {
        let size = ((a.pixel_width >> mip).max(1) as usize)
            .checked_mul((a.pixel_height >> mip).max(1) as usize)
            .context("shadow mip dimensions overflow")?;
        let colour_size = size.checked_mul(4).context("colour mip dimensions overflow")?;
        let decode = |level: ktx2::Level<'_>, expected| -> Result<Vec<u8>> {
            ensure!(level.uncompressed_byte_length == expected as u64, "wrong uncompressed shadow mip length");
            let mut bytes = Vec::new();
            ruzstd::decoding::StreamingDecoder::new(level.data)?.take(expected as u64 + 1).read_to_end(&mut bytes)?;
            ensure!(bytes.len() == expected, "wrong decoded shadow mip length");
            Ok(bytes)
        };
        let colour = decode(colour, colour_size).with_context(|| format!("colour mip {mip}"))?;
        let shadow = decode(shadow, size).with_context(|| format!("shadow mip {mip}"))?;
        ensure!(
            colour.chunks_exact(4).map(|pixel| pixel[3]).eq(shadow),
            "shadow alpha differs from colour at mip {mip}"
        );
    }
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
    let bytes: Vec<&[u8]> = levels.iter().map(|level| level.rgba.as_slice()).collect();
    encode_ktx2(width, height, Format::R8G8B8A8_SRGB, &bytes)
}

/// As [`ktx2`], each level stored as sRGB BC7 blocks of 4 × 4 texels; a level smaller than a block repeats its edge
/// texels to fill one. A level with clear texels keeps its alpha; an opaque one spends every bit on colour.
fn bc7_ktx2(width: u32, height: u32, levels: &[Level]) -> Result<Vec<u8>> {
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

fn alpha_ktx2(width: u32, height: u32, levels: &[Level]) -> Result<Vec<u8>> {
    let alpha: Vec<Vec<u8>> = levels.iter().map(|level| level.rgba.chunks_exact(4).map(|p| p[3]).collect()).collect();
    let bytes: Vec<&[u8]> = alpha.iter().map(Vec::as_slice).collect();
    encode_ktx2(width, height, Format::R8_UNORM, &bytes)
}

fn encode_ktx2(width: u32, height: u32, format: Format, levels: &[&[u8]]) -> Result<Vec<u8>> {
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

    /// A BC7 file reads back as BC7 with every level's blocks, down to the 1 × 1 level's one block.
    #[test]
    fn bc7_reads_back() {
        let rgba: Vec<u8> = (0..8 * 4).flat_map(|k| [(k * 8) as u8, (255 - k * 8) as u8, (k * 3) as u8, 255]).collect();
        let mut levels = vec![Level { width: 8, height: 4, rgba }];
        while let Some(smaller) = levels.last().unwrap().halved(MipColour::OpacityWeighted) {
            levels.push(smaller);
        }
        let file = bc7_ktx2(8, 4, &levels).unwrap();
        let reader = ktx2::Reader::new(file.as_slice()).unwrap();
        assert_eq!(reader.header().format, Some(Format::BC7_SRGB_BLOCK));
        assert_eq!(reader.header().level_count, 4);
        let lengths: Vec<u64> = reader.levels().map(|level| level.uncompressed_byte_length).collect();
        assert_eq!(lengths, [32, 16, 16, 16]);
    }

    fn alpha_fixture() -> (PathBuf, Settings) {
        use std::sync::atomic::{AtomicUsize, Ordering};
        static NEXT: AtomicUsize = AtomicUsize::new(0);
        let id = NEXT.fetch_add(1, Ordering::Relaxed);
        let folder = std::env::temp_dir().join(format!("hakuba-shadow-alpha-{}-{id}", std::process::id()));
        fs::create_dir_all(&folder).unwrap();
        image::RgbaImage::from_fn(32, 16, |x, y| {
            image::Rgba([(x * 3 + y * 5) as u8, (x * 7 + y) as u8, (x + y * 11) as u8, (x * 37 + y * 53) as u8])
        })
        .save(folder.join("input.png"))
        .unwrap();
        let settings = Settings {
            source: "input.png".into(),
            alpha_cutoff: 0.4,
            mip_colour: MipColour::Average,
            alpha_shadow: true,
            compression: Compression::None,
        };
        (folder, settings)
    }

    fn decoded(bytes: &[u8]) -> Vec<Vec<u8>> {
        ktx2::Reader::new(bytes)
            .unwrap()
            .levels()
            .map(|level| {
                let mut bytes = Vec::new();
                ruzstd::decoding::StreamingDecoder::new(level.data).unwrap().read_to_end(&mut bytes).unwrap();
                bytes
            })
            .collect()
    }

    #[test]
    fn shadow_export_keeps_every_final_mip_alpha() {
        let (folder, mut settings) = alpha_fixture();
        let output = folder.join("texture.ktx2");
        for mode in [MipColour::Average, MipColour::OpacityWeighted] {
            settings.mip_colour = mode;
            export(&folder, &settings, &output).unwrap();
            let colour = fs::read(&output).unwrap();
            let alpha = fs::read(shadow_file(&output)).unwrap();
            let colour_header = ktx2::Reader::new(colour.as_slice()).unwrap().header();
            let alpha_header = ktx2::Reader::new(alpha.as_slice()).unwrap().header();
            assert_eq!(alpha_header.format, Some(Format::R8_UNORM));
            assert_eq!(
                (colour_header.pixel_width, colour_header.pixel_height, colour_header.level_count),
                (alpha_header.pixel_width, alpha_header.pixel_height, alpha_header.level_count)
            );
            let colour = decoded(&colour);
            let alpha = decoded(&alpha);
            assert!(colour.len() > 1);
            assert_eq!(colour.len(), alpha.len());
            for (rgba, alpha) in colour.iter().zip(&alpha) {
                let expected: Vec<_> = rgba.chunks_exact(4).map(|p| p[3]).collect();
                assert_eq!(*alpha, expected);
            }
            validate_shadow(&output).unwrap();
        }
        fs::remove_dir_all(folder).unwrap();
    }

    #[test]
    fn missing_or_changed_companion_is_stale_and_disabling_removes_it() {
        let (folder, mut settings) = alpha_fixture();
        let output = folder.join("texture.ktx2");
        export(&folder, &settings, &output).unwrap();
        let colour = fs::read(&output).unwrap();
        let path = shadow_file(&output);
        let original = fs::read(&path).unwrap();
        let header = ktx2::Reader::new(original.as_slice()).unwrap().header();
        let mut alpha = decoded(&original);
        // A stale lower mip must fail even when the full-resolution level still matches.
        alpha.last_mut().unwrap()[0] ^= 1;
        let refs: Vec<_> = alpha.iter().map(Vec::as_slice).collect();
        fs::write(&path, encode_ktx2(header.pixel_width, header.pixel_height, Format::R8_UNORM, &refs).unwrap())
            .unwrap();
        assert!(validate_shadow(&output).is_err());
        fs::write(&path, &colour).unwrap();
        assert!(validate_shadow(&output).is_err());
        fs::write(&path, &original[..original.len() / 2]).unwrap();
        assert!(validate_shadow(&output).is_err());
        fs::remove_file(&path).unwrap();
        assert!(validate_shadow(&output).is_err());
        export(&folder, &settings, &output).unwrap();
        validate_shadow(&output).unwrap();
        settings.alpha_shadow = false;
        export(&folder, &settings, &output).unwrap();
        assert!(!path.exists());
        assert_eq!(fs::read(&output).unwrap(), colour);
        fs::remove_dir_all(folder).unwrap();
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
