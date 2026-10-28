//! Texture dye profile shared by character exports and runtime.
use serde::{Deserialize, Serialize};

/// A sampled texture's colour mask and dye, applied only to the named mesh.
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TextureDye {
    pub mesh: String,
    pub mask: [f32; 4],
    pub luma: [f32; 3],
    pub green_scale: f32,
    pub reference: f32,
    pub exponent: f32,
    pub emission: f32,
    pub roughness: f32,
    pub reflectance: f32,
}

impl TextureDye {
    pub fn valid(&self) -> bool {
        !self.mesh.is_empty()
            && self.mask.iter().chain(self.luma.iter()).all(|v| v.is_finite())
            && self.green_scale.is_finite()
            && self.green_scale > 0.0
            && self.reference.is_finite()
            && self.reference > 0.0
            && self.exponent.is_finite()
            && self.exponent > 0.0
            && self.emission.is_finite()
            && self.emission >= 0.0
            && (0.0..=1.0).contains(&self.roughness)
            && (0.0..=1.0).contains(&self.reflectance)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_invalid_surface_values() {
        let mut profile = TextureDye {
            mesh: "body".into(),
            mask: [0.0; 4],
            luma: [0.0; 3],
            green_scale: 1.0,
            reference: 1.0,
            exponent: 1.0,
            emission: 0.0,
            roughness: 0.7,
            reflectance: 0.38,
        };
        assert!(profile.valid());
        profile.roughness = f32::NAN;
        assert!(!profile.valid());
        profile.roughness = 0.7;
        profile.reflectance = 1.1;
        assert!(!profile.valid());
    }
}
