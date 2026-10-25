//! Every character, each with its implementation of [`crate::character::Character`] from its asset folder's `src/`.

use anyhow::Result;
use serde::{Deserialize, Serialize};

use crate::character::animate;
use crate::glb::Glb;

#[path = "../../../assets/characters/nox/src/nox.rs"]
mod nox;

#[derive(Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Name {
    Nox,
}

impl Name {
    /// Fits every animation to the character and adds it to its model.
    pub fn animate(self, glb: &mut Glb) -> Result<()> {
        match self {
            Name::Nox => animate(glb, &nox::Nox),
        }
    }
}
