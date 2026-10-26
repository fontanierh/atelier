//! Every animation: the [`Animation`] that each animation's asset folder implements in `src/<name>.rs`, listed in
//! [`ANIMATIONS`].

use std::path::{Path, PathBuf};

use anyhow::Result;
use serde::Deserialize;
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
    /// is the character's table for this animation in its `asset.toml`, if it has one; [`changes`] reads it.
    fn change(&self, changes: Option<&Value>, rest: &Pose, frames: &mut [Pose]) -> Result<()>;
}

/// The animation named `name`.
pub fn named(name: &str) -> Option<&'static dyn Animation> {
    ANIMATIONS.into_iter().find(|animation| animation.name() == name)
}

/// The animation's asset folder, relative to `assets/`.
pub fn folder(animation: &dyn Animation) -> String {
    format!("animations/{}", animation.name())
}

/// The animation's exported clip on the rig.
pub fn output(animation: &dyn Animation) -> PathBuf {
    Path::new(crate::ASSETS).join(folder(animation)).join(format!("{}.glb", animation.name()))
}

/// A character's changes to one animation, read into the form that animation defines; no change if it has none.
pub fn changes<T: Default + for<'de> Deserialize<'de>>(changes: Option<&Value>) -> Result<T> {
    Ok(changes.map(T::deserialize).transpose()?.unwrap_or_default())
}
