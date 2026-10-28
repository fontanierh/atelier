//! The `plant` kind: a tree, bush or tuft of grass imported from a static source mesh whose vertices carry their
//! original foliage weights, with the material's wind, push and atmospheric response as its profile.

use std::path::Path;

use anyhow::{Result, bail};
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Settings {
    /// The static source mesh, under this asset's src folder.
    source: String,
    /// Named textures referenced by the source mesh.
    textures: Vec<String>,
    source_profile: SourceProfile,
    /// For a source surface intentionally above its origin, its exact lowest height in metres.
    surface_height_m: Option<f32>,
    /// Maximum caster distance in metres, with conservative bounds padding.
    shadow_distance_m: Option<f32>,
}

/// The source material's wind, push and atmospheric response.
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct SourceProfile {
    direction_amplitude_shade: [f32; 4],
    slow: [f32; 4],
    fast: [f32; 4],
    global_slow: [f32; 4],
    global_fast: [f32; 4],
    /// Third global gust: frequency and amplitude; final two components are reserved.
    global_tail: [f32; 4],
    push_haze: [f32; 4],
    haze_colour: [f32; 3],
    #[serde(default = "unit_wind")]
    wind_scale: f32,
    #[serde(default)]
    up_normal: bool,
}

fn unit_wind() -> f32 {
    1.0
}

impl SourceProfile {
    fn valid(&self) -> bool {
        self.direction_amplitude_shade
            .iter()
            .chain(&self.slow)
            .chain(&self.fast)
            .chain(&self.global_slow)
            .chain(&self.global_fast)
            .chain(&self.global_tail)
            .chain(&self.push_haze)
            .chain(&self.haze_colour)
            .all(|x| x.is_finite())
            && (self.direction_amplitude_shade[0].powi(2) + self.direction_amplitude_shade[1].powi(2)) > 0.0
            && self.global_tail[2] == 0.0
            && self.global_tail[3] == 0.0
            && self.wind_scale.is_finite()
            && self.wind_scale >= 0.0
            && self.push_haze[0] > 0.0
            && self.push_haze[3] > 0.0
    }
}

pub fn export(settings: &Settings, output: &Path) -> Result<()> {
    if settings.textures.is_empty() {
        bail!("a plant needs declared textures");
    }
    if !settings.source_profile.valid() {
        bail!("invalid source foliage profile");
    }
    if settings.shadow_distance_m.is_some_and(|d| !d.is_finite() || d <= 0.0) {
        bail!("source shadow distance must be positive and finite");
    }
    super::source::export_foliage(
        &settings.source,
        &settings.textures,
        serde_json::to_value(&settings.source_profile)?,
        settings.surface_height_m,
        settings.shadow_distance_m,
        output,
    )
}
