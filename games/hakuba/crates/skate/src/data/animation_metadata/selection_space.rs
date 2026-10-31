//! Type11 layout from original 82D1BEA0, 82D26CC0 and 82D26FF8.
use super::validate_name;
use serde::Deserialize;

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SelectionParameterMetadata {
    pub name: String,
    pub mode: u32,
    pub weight_bits: u32,
    pub minimum_bits: u32,
    pub maximum_bits: u32,
}
#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SelectionCandidateMetadata {
    pub child: String,
    pub value_bits: Vec<u32>,
}
#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SelectionSpaceMetadata {
    pub name: String,
    pub source_offset: u64,
    pub parameters: Vec<SelectionParameterMetadata>,
    pub candidates: Vec<SelectionCandidateMetadata>,
}
impl SelectionSpaceMetadata {
    pub(super) fn validate(&self, bytes: u64) -> std::result::Result<(), String> {
        validate_name(&self.name, 36)?;
        if self.source_offset >= bytes || self.parameters.len() > 10 || self.candidates.is_empty() {
            return Err(format!("{}: invalid selection space dimensions", self.name));
        }
        for p in &self.parameters {
            validate_name(&p.name, 30)?;
            if [p.weight_bits, p.minimum_bits, p.maximum_bits].into_iter().any(|v| !f32::from_bits(v).is_finite()) {
                return Err(format!("{}: nonfinite selection metric", self.name));
            }
        }
        for c in &self.candidates {
            validate_name(&c.child, 36)?;
            if c.value_bits.len() != self.parameters.len()
                || c.value_bits.iter().any(|v| !f32::from_bits(*v).is_finite())
            {
                return Err(format!("{}: invalid selection candidate", self.name));
            }
        }
        Ok(())
    }
}
