//! The `sound` kind: one sound the game plays, in one or more takes, written as `<folder name>.ogg` (Ogg Vorbis, which
//! every browser and the desktop build decode) and `<folder name>.takes.json`, where each take starts and how long it
//! lasts. The takes are WAV files in `src/`, all at one sample rate and channel count, placed one after the other with
//! [`GAP_S`] of silence between, so the game plays a take by playing that stretch of the file.

use std::fs;
use std::num::{NonZeroU8, NonZeroU32};
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use serde::{Deserialize, Serialize};
use vorbis_rs::{VorbisBitrateManagementStrategy, VorbisEncoderBuilder};

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Settings {
    /// Each take, a WAV file relative to the asset folder.
    takes: Vec<PathBuf>,
    /// Whether the game loops each take, which then must join end to start without a click.
    #[serde(default)]
    looped: bool,
    /// The Vorbis quality, from -0.1 (smallest) to 1 (best).
    quality: f32,
}

/// The silence between two takes, in seconds: more than a decoder's block, so no take bleeds into the next.
const GAP_S: f32 = 0.05;

/// The Ogg stream's serial number, fixed so the same inputs export the same bytes.
const SERIAL: i32 = 1;

/// The takes' file, which the game reads.
#[derive(Serialize)]
struct Takes {
    looped: bool,
    /// Each take's start and length, in seconds.
    takes: Vec<Take>,
}

#[derive(Serialize)]
struct Take {
    start: f32,
    seconds: f32,
}

/// The file beside the `.ogg` export that lists its takes.
pub fn takes_file(output: &Path) -> PathBuf {
    output.with_extension("takes.json")
}

pub fn export(folder: &Path, settings: &Settings, output: &Path) -> Result<()> {
    if settings.takes.is_empty() {
        bail!("a sound needs at least one take");
    }
    let mut format = None;
    let mut channels: Vec<Vec<f32>> = Vec::new();
    let mut takes = Vec::new();
    for take in &settings.takes {
        let file = folder.join(take);
        let (spec, samples) = read(&file)?;
        let this = (spec.sample_rate, spec.channels);
        if *format.get_or_insert(this) != this {
            bail!("{} is {} Hz in {} channels, unlike the first take", file.display(), this.0, this.1);
        }
        if channels.is_empty() {
            channels = vec![Vec::new(); spec.channels as usize];
        } else {
            let gap = (GAP_S * spec.sample_rate as f32).round() as usize;
            channels.iter_mut().for_each(|channel| channel.extend(std::iter::repeat_n(0.0, gap)));
        }
        let start = channels[0].len() as f32 / spec.sample_rate as f32;
        for (index, sample) in samples.iter().enumerate() {
            channels[index % spec.channels as usize].push(*sample);
        }
        let frames = samples.len() / spec.channels as usize;
        takes.push(Take { start, seconds: frames as f32 / spec.sample_rate as f32 });
    }
    let (rate, count) = format.expect("there is a take");
    let mut ogg = Vec::new();
    let mut encoder = VorbisEncoderBuilder::new_with_serial(
        NonZeroU32::new(rate).context("a sample rate of 0")?,
        NonZeroU8::new(count as u8).context("no channels")?,
        &mut ogg,
        SERIAL,
    )
    .bitrate_management_strategy(VorbisBitrateManagementStrategy::QualityVbr { target_quality: settings.quality })
    .build()?;
    const BLOCK: usize = 1024;
    for start in (0..channels[0].len()).step_by(BLOCK) {
        let end = (start + BLOCK).min(channels[0].len());
        let block: Vec<&[f32]> = channels.iter().map(|channel| &channel[start..end]).collect();
        encoder.encode_audio_block(block)?;
    }
    encoder.finish()?;
    fs::write(output, ogg)?;
    let list = Takes { looped: settings.looped, takes };
    fs::write(takes_file(output), serde_json::to_string_pretty(&list)? + "\n")?;
    Ok(())
}

/// A WAV file's format and its samples, interleaved, from -1 to 1.
fn read(file: &Path) -> Result<(hound::WavSpec, Vec<f32>)> {
    let reader = hound::WavReader::open(file).with_context(|| format!("reading {}", file.display()))?;
    let spec = reader.spec();
    let samples = match spec.sample_format {
        hound::SampleFormat::Float => reader.into_samples::<f32>().collect::<Result<Vec<_>, _>>()?,
        hound::SampleFormat::Int => {
            let scale = 1.0 / (1u32 << (spec.bits_per_sample - 1)) as f32;
            reader.into_samples::<i32>().map(|sample| sample.map(|s| s as f32 * scale)).collect::<Result<_, _>>()?
        }
    };
    Ok((spec, samples))
}
