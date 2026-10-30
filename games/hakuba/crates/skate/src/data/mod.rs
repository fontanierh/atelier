//! Exported simulation records and validation. Stateless codec math is in core.
#![forbid(unsafe_code)]
mod manifest;
pub use manifest::AssetError;
pub mod animation_frames;
pub mod animation_metadata;
pub mod attrib_hash;
pub mod camera;
pub mod collections;
pub mod gesture_patterns;
#[cfg(test)]
#[path = "tests/package_readers.rs"]
mod package_readers;
pub mod physics_skeleton;
pub mod retail_collision;
pub mod scoring;
mod scoring_fields;
#[cfg(test)]
mod sha256;
pub mod skate_map;
pub mod state_graph;
