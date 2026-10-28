//! Metadata shared by painted models and their runtime materials.

use serde::Deserialize;

#[derive(Clone, Debug, Deserialize, PartialEq)]
pub struct Profile {
    #[serde(default)]
    pub texture_mask: bool,
    #[serde(default)]
    pub reflectance: Option<f32>,
    pub fill: f32,
    pub glow: f32,
    pub glow_min: [f32; 3],
    pub glow_max: [f32; 3],
    pub haze_start_m: f32,
    pub haze_length_m: f32,
    pub haze_colour: [f32; 3],
}

impl Profile {
    pub fn valid(&self) -> bool {
        self.reflectance.is_none_or(|v| v.is_finite() && (0.0..=1.0).contains(&v))
            && self.fill.is_finite()
            && self.fill >= 0.0
            && self.glow.is_finite()
            && self.glow >= 0.0
            && self.haze_start_m.is_finite()
            && self.haze_start_m >= 0.0
            && self.haze_length_m.is_finite()
            && self.haze_length_m > 0.0
            && self.haze_colour.iter().all(|v| v.is_finite() && *v >= 0.0)
            && self.glow_min.iter().zip(self.glow_max).all(|(a, b)| a.is_finite() && b.is_finite() && *a <= b)
    }
}

/// Source-authored motion of a painted vertex, in world metres.
#[derive(Clone, Debug, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct MotionProfile {
    pub spatial: [f32; 2],
    pub rate: f32,
    pub amplitude: [f32; 3],
    pub harmonic: [f32; 3],
}

impl MotionProfile {
    pub fn valid(&self) -> bool {
        self.rate.is_finite()
            && self.rate.abs() <= 10_000.0
            && self
                .spatial
                .iter()
                .chain(&self.amplitude)
                .chain(&self.harmonic)
                .all(|x| x.is_finite() && x.abs() <= 10_000.0)
    }
}
