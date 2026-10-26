//! Every animation: the [`Animation`] that each animation's asset folder implements in `src/<name>.rs`, listed in
//! [`ANIMATIONS`].

use anyhow::Result;
use serde_json::Value;

use crate::rig::Bones;
use crate::rig::pose::Pose;

#[path = "../../../../assets/animations/idle/src/idle.rs"]
mod idle;

/// Every animation, each exported with every character.
pub const ANIMATIONS: [&dyn Animation; 1] = [&idle::Idle];

/// What the exporter needs from an animation's own code.
pub trait Animation: Sync {
    /// Its name: its asset folder's name under `animations/`, and the clip's name in every export.
    fn name(&self) -> &'static str;

    /// The skeleton its source clip is on.
    fn source(&self) -> Bones;

    /// Applies a character's `changes` to the animation's `frames`, fitted to the character's `rest` pose. `changes`
    /// is the character's table for this animation in its `asset.toml`, if it has one;
    /// [`changes`](crate::rig::animation::changes) reads it.
    fn change(&self, changes: Option<&Value>, rest: &Pose, frames: &mut [Pose]) -> Result<()>;
}

/// The animation named `name`.
pub fn named(name: &str) -> Option<&'static dyn Animation> {
    ANIMATIONS.into_iter().find(|animation| animation.name() == name)
}
