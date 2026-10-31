//! Immutable resources decoded from the exported simulation package, without filesystem access.
use crate::{
    data::{
        animation_metadata::AnimationMetadata, collections::Collections, physics_skeleton::PhysicsSkeleton,
        state_graph::StateGraph,
    },
    skater_animation::AnimationSource,
};
use hakuba_skate_schema::Package;
use std::sync::Arc;
mod package;

pub(crate) struct Resources {
    pub settings: Arc<Collections>,
    pub metadata: Arc<AnimationMetadata>,
    pub physical: Vec<PhysicsSkeleton>,
    pub physical_identity: String,
    pub action: StateGraph,
    pub motion: StateGraph,
    pub camera_graph: StateGraph,
    pub shakes: [crate::core::camera::ShakeSamples; 2],
    pub shots: crate::camera::shot_data::StockShots,
    pub gestures: Vec<(usize, Vec<crate::core::input::gesture::Pattern>)>,
    pub animation: Arc<AnimationSource>,
}
impl Resources {
    pub fn from_bytes(bytes: Vec<u8>) -> Result<Self, String> {
        package::load(Arc::new(bytes)).map_err(|e| format!("Invalid skating simulation package: {e}"))
    }
}

/// Validated immutable simulation assets. Clone this handle across sessions and world activations.
/// Preparation owns the archive and completes before a host reports its assets ready.
#[derive(Clone)]
pub struct PreparedResources(pub(crate) Arc<Resources>);
impl PreparedResources {
    pub fn from_bytes(bytes: Vec<u8>) -> Result<Self, String> {
        Resources::from_bytes(bytes).map(|resources| Self(Arc::new(resources)))
    }
}
