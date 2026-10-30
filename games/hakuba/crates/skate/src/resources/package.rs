//! Assemble the current validated project payloads into a reusable simulation resource set.
use super::*;
use crate::{
    animation_pose::PoseEvaluator,
    data::{animation_frames::AnimationFrames, camera, gesture_patterns, physics_skeleton},
};

pub(super) fn load(bytes: Arc<Vec<u8>>) -> Result<Resources, String> {
    let package = Package::parse(&bytes).map_err(|e| e.to_string())?;
    let get = |path: &str| package.get(path).map_err(|e| e.to_string());
    let settings = Arc::new(Collections::from_bytes(get("settings.skate")?)?);
    let mut metadata = AnimationMetadata::from_bytes(get("metadata/bank-0.skate")?)?;
    metadata.merge(AnimationMetadata::from_bytes(get("metadata/bank-1.skate")?)?)?;
    let metadata = Arc::new(metadata);
    let frames = AnimationFrames::from_package(&package, Arc::clone(&bytes), &metadata)?;
    let physical_identity = metadata.source_sha256.clone();
    let physical = physics_skeleton::from_bytes(get("physics-skeletons.skate")?, &physical_identity)?;
    let source =
        AnimationSource { metadata: metadata.clone(), evaluator: Arc::new(PoseEvaluator::from_frames(frames)) };
    let camera = camera::from_bytes(get("camera.skate")?)?;
    let shots = crate::camera::shot_data::StockShots::from_definitions(camera.shots)?;
    Ok(Resources {
        settings,
        metadata,
        physical,
        physical_identity,
        action: StateGraph::from_bytes(get("action.graph")?).map_err(|e| e.to_string())?,
        motion: StateGraph::from_bytes(get("motion.graph")?).map_err(|e| e.to_string())?,
        camera_graph: StateGraph::from_bytes(get("camera.graph")?).map_err(|e| e.to_string())?,
        shakes: camera.shakes,
        shots,
        gestures: gesture_patterns::from_bytes(get("gestures.skate")?)?
            .into_iter()
            .map(|s| (s.stick, s.patterns))
            .collect(),
        animation: Arc::new(source),
    })
}
