//! Complete fixed-step skating simulation and its Bevy presentation.
mod core;
mod data;
mod resources;
pub use resources::PreparedResources;
mod animation;
mod animation_pose;
mod camera;
mod crash_context;
mod difficulty;
mod graph_host;
mod graph_runtime;
mod grind_world;
mod input;
mod physics;
mod scoring_runtime;
mod skate_world;
mod skater_animation;
mod tuning;

pub use physics::bridge;
pub use physics::bridge::{AudioEvent, AudioEventKind, AudioFrame, AudioMode};

mod session_marker;

pub use physics::bridge::{
    CollisionBuilder, CollisionRail, ContactMode, Controls, LimbContact, MarkerSnapshot, MarkerStatus, Pose,
    PreparedCollision, Session, SkateTelemetry, TRANSFER,
};

pub mod feel;
pub use feel::FeelTuning;

#[cfg(test)]
mod test_support;

mod plugin;
pub use plugin::{SkatePlugin, SkateStatus, SkateSystems, StickReading};

#[cfg(test)]
mod session_tests;
