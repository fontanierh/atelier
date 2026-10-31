//! Skate 3 TU3 `PhysicalPlayerHiLOD::Input` (`0x82DB4048`).
//!
//! The phase is split into direct field publication and an ordered runtime.
//! Separate native subsystems remain mandatory service calls; none have a
//! fallback implementation here.

mod air_output;
mod grind_input;
mod grind_output;
mod motion_math;
mod pose_output;
mod publication;
mod requests;
mod runtime;
mod types;

pub use air_output::AirOutputFields;
pub use pose_output::SkeletonOutputFields;
pub use runtime::{InputContinuation, InputPhaseServices, finish_input, process_input, start_input};
pub use types::*;

pub use grind_input::GrindInvestigationFields;
pub use grind_output::GrindOutputFields;

#[cfg(test)]
mod tests;
