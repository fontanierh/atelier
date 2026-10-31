//! Validated compact animation component tracks backed by one immutable package allocation.
use crate::data::animation_metadata::AnimationMetadata;
use std::{collections::BTreeMap, sync::Arc};
mod package;
/// Scale xyz, quaternion xyzw and translation xyz, as exact binary32 words.
pub type SampleWords = [u32; 10];

pub struct ClipFrames {
    pub name: String,
    pub source_offset: u64,
    pub fps_bits: u32,
    pub loop_translation_bits: [u32; 3],
    pub loop_rotation_bits: [u32; 4],
    pub channel_animation: bool,
    pub channel_weights: Vec<u32>,
    bank: usize,
    archive: Arc<Vec<u8>>,
    tracks: Vec<[(usize, usize); 10]>,
    frame_count: usize,
}
impl ClipFrames {
    pub fn frame_count(&self) -> usize {
        self.frame_count
    }
    pub fn bone_count(&self) -> usize {
        self.tracks.len()
    }
    #[cfg(test)]
    pub(crate) fn archive(&self) -> &Arc<Vec<u8>> {
        &self.archive
    }
    #[cfg(test)]
    pub(crate) fn index_bytes(&self) -> usize {
        self.tracks.capacity() * std::mem::size_of::<[(usize, usize); 10]>()
    }
    /// Reads one complete decoded key without expanding constant component tracks.
    pub fn key(&self, frame: usize, bone: usize) -> SampleWords {
        assert!(frame < self.frame_count);
        self.tracks[bone].map(|(start, count)| {
            let at = start + 4 * if count == 1 { 0 } else { frame };
            u32::from_le_bytes(self.archive[at..at + 4].try_into().unwrap())
        })
    }
}
pub struct ReferencePose {
    pub name: String,
    pub source_offset: u64,
    pub samples: Vec<SampleWords>,
}
pub struct AnimationFrames {
    pub source_sha256: String,
    pub parents: Vec<i32>,
    pub bone_names: Vec<String>,
    pub mirror_indices: Vec<i32>,
    pub has_trajectory: bool,
    project: package::ProjectFrames,
}
impl AnimationFrames {
    pub fn clip(&self, name: &str) -> Result<&ClipFrames, String> {
        self.project.clip(name)
    }
    pub fn reference_pose(&self, offset: u64) -> Result<&ReferencePose, String> {
        self.project.reference_pose(0, offset)
    }
    pub fn named_pose(&self, name: &str) -> Result<&ReferencePose, String> {
        self.project.named_pose(0, name)
    }
    pub fn named_pose_in(&self, bank: usize, name: &str) -> Result<&ReferencePose, String> {
        self.project.named_pose(bank, name)
    }
    pub fn clip_count(&self) -> usize {
        self.project.clip_count()
    }
    pub fn clip_names(&self) -> impl Iterator<Item = &str> {
        self.project.clip_names()
    }
    pub fn clip_bank(&self, name: &str) -> Result<usize, String> {
        self.project.clip_bank(name)
    }
}
fn validate_samples(samples: &[SampleWords], bones: usize) -> Result<(), String> {
    if samples.len() != bones || samples.iter().flatten().any(|&w| !f32::from_bits(w).is_finite()) {
        return Err("Animation sample incomplete or nonfinite".into());
    }
    Ok(())
}
