//! Actor metadata shared by world exports and runtime.
use serde::{Deserialize, Serialize};

/// A rigid model positioned and rotated from the character's bones.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Attachment<N, S> {
    pub model: S,
    pub position_bone: S,
    pub rotation_bone: S,
    pub offset: [N; 3],
    pub rotation: [N; 4],
}

/// A visual clip played periodically between idle loops.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Practice<N, S> {
    pub clip: S,
    pub rate: N,
    pub duration_s: N,
    pub interval_s: [N; 2],
    pub delay_s: N,
}

/// Stationary scan around the home bearing, in degrees and radians per second.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Scan<N> {
    pub amplitude_deg: N,
    pub frequency: N,
    pub max_speed_deg: N,
}
