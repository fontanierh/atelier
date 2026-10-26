//! Every character: the [`Character`] that each character's asset folder implements in `src/<name>.rs`, listed in
//! [`CHARACTERS`].

use crate::rig::Skeleton;

#[path = "../../../../assets/characters/nox/src/nox.rs"]
mod nox;

/// Every character.
pub const CHARACTERS: [&dyn Character; 1] = [&nox::Nox];

/// What the exporter needs from a character's own code: its name, and which of its bones plays each rig bone.
pub trait Character: Skeleton + Sync {
    /// Its name: its asset folder's name under `characters/`.
    fn name(&self) -> &'static str;
}

/// The character named `name`.
pub fn named(name: &str) -> Option<&'static dyn Character> {
    CHARACTERS.into_iter().find(|character| character.name() == name)
}
