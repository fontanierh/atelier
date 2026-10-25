//! Every animation, each from its asset folder's `src/<name>.rs`: the skeleton its source clip is on, and the trait a
//! character implements to change it.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::rig::{Bones, Skeleton};

#[path = "../../../assets/animations/idle/src/idle.rs"]
pub mod idle;

#[derive(Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Name {
    Idle,
}

impl Name {
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

    /// The animation's exported clip on the rig.
    pub fn output(self) -> PathBuf {
        let folder = Path::new(crate::ASSETS).join(self.folder());
        let name = folder.file_name().unwrap().to_string_lossy().into_owned();
        folder.join(format!("{name}.glb"))
    }
}
