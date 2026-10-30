//! Read-only marker telemetry and exact saved-marker import; travel remains the native held-return action.
use super::Session;

/// Exact native animation-to-world basis and the state restored by marker travel.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct MarkerSnapshot {
    pub transform: [[f32; 4]; 4],
    pub on_board: bool,
    pub foot_forward: bool,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct MarkerStatus {
    pub visible: bool,
    pub can_place: bool,
    pub can_return: bool,
    pub progress: f32,
    /// Increments only when the native held-return accepts a teleport request.
    pub returns: u64,
    /// Increments only when a raw set action passes native placement validation.
    pub placements: u64,
}

impl Session {
    pub fn marker(&self) -> Option<MarkerSnapshot> {
        self.markers.snapshot()
    }
    pub fn marker_status(&self) -> MarkerStatus {
        self.markers.status()
    }
    /// Select a saved destination, without moving or resetting the rider. The next raw held return uses it.
    pub fn restore_marker(&mut self, marker: Option<MarkerSnapshot>) -> Result<(), String> {
        self.markers.restore(marker)
    }
}
