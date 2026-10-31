//! Static canonical-world adapter for OffboardGroundAnalyzer.
//! The runtime must supply actual mesh metadata; neither a board contact nor
//! a synthetic ground ray can provide it.
mod world;
pub use crate::core::player::offboard::contact_toolkit::Owner;
pub use world::StaticScene;
