//! Every animation, each from its asset folder's `src/<name>.rs`: the skeleton its source clip is on, and the trait a
//! character implements to change it.

use std::path::{Path, PathBuf};

use anyhow::Result;
use serde::{Deserialize, Serialize};

use crate::pose::Pose;
use crate::rig::{Bones, Skeleton};

#[path = "../../../assets/animations/idle/src/idle.rs"]
pub mod idle;

#[derive(Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Name {
    Idle,
}

/// A character's changes to every animation: one trait per animation.
pub trait Changes: idle::Idle {}

impl<T: idle::Idle> Changes for T {}

impl Name {
    /// Every animation, each exported with every character.
    pub const ALL: [Name; 1] = [Name::Idle];

    /// Applies `character`'s changes to the animation's `frames`, fitted to its `rest` pose.
    pub fn change(self, character: &impl Changes, rest: &Pose, frames: &mut [Pose]) -> Result<()> {
        match self {
            Name::Idle => idle::apply(&character.stance(), rest, frames),
        }
    }

    /// The skeleton the animation's source clip is on.
    pub fn source_skeleton(self) -> Bones {
        match self {
            Name::Idle => idle::Source.bones(),
        }
    }

    /// The animation's asset folder, relative to `assets/`.
    pub fn folder(self) -> &'static str {
        match self {
            Name::Idle => "animations/idle",
        }
    }

    /// The animation's name: its asset folder's name, and the clip's name in every export.
    pub fn name(self) -> &'static str {
        self.folder().rsplit('/').next().expect("a folder has a name")
    }

    /// The animation's exported clip on the rig.
    pub fn output(self) -> PathBuf {
        Path::new(crate::ASSETS).join(self.folder()).join(format!("{}.glb", self.name()))
    }
}
