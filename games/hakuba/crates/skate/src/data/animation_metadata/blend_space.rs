//! Andale type6: construction82D1B8D0, layout82D22DA0, simplex82D23898.
use super::validate_name;
use serde::Deserialize;

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BlendSimplexMetadata {
    pub children: Vec<usize>,
    /// Spatial coordinates only; the serialized matrix also has a final column.
    pub vertex_bits: Vec<Vec<u32>>,
    pub normal_bits: Vec<Vec<u32>>,
    pub scale_bits: Vec<u32>,
}
#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BlendSpaceMetadata {
    pub name: String,
    pub source_offset: u64,
    pub parameters: Vec<String>,
    pub children: Vec<String>,
    pub simplexes: Vec<BlendSimplexMetadata>,
}
impl BlendSpaceMetadata {
    pub(super) fn validate(&self, bytes: u64) -> std::result::Result<(), String> {
        validate_name(&self.name, 36)?;
        let d = self.parameters.len();
        if self.source_offset >= bytes || d == 0 || d > 4 || self.children.len() < d + 1 || self.simplexes.is_empty() {
            return Err(format!("{}: invalid BlendSpace dimensions/offset", self.name));
        }
        for name in &self.parameters {
            validate_name(name, 30)?;
        }
        for name in &self.children {
            validate_name(name, 36)?;
        }
        for s in &self.simplexes {
            if s.children.len() != d + 1
                || s.scale_bits.len() != d + 1
                || s.vertex_bits.len() != d + 1
                || s.normal_bits.len() != d + 1
                || s.children.iter().any(|&i| i >= self.children.len())
                || s.vertex_bits.iter().chain(&s.normal_bits).any(|v| v.len() != d)
                || s.vertex_bits
                    .iter()
                    .chain(&s.normal_bits)
                    .flatten()
                    .chain(&s.scale_bits)
                    .any(|&v| !f32::from_bits(v).is_finite())
            {
                return Err(format!("{}: invalid BlendSpace simplex", self.name));
            }
        }
        Ok(())
    }
}
