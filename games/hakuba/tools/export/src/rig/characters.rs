//! Every character: the [`Character`] that each character's asset folder implements in `src/<name>.rs`, listed in
//! [`CHARACTERS`].

use crate::rig::Skeleton;

#[path = "../../../../assets/characters/camp-visitor/src/camp_visitor.rs"]
mod camp_visitor;
#[path = "../../../../assets/characters/nox/src/nox.rs"]
mod nox;
#[path = "../../../../assets/characters/wanderer/src/wanderer.rs"]
mod wanderer;

/// Every character.
pub const CHARACTERS: [&dyn Character; 3] = [&camp_visitor::CampVisitor, &nox::Nox, &wanderer::Wanderer];

/// What the exporter needs from a character's own code: its name, and which of its bones plays each rig bone.
pub trait Character: Sync {
    /// Its name: its asset folder's name under `characters/`.
    fn name(&self) -> &'static str;

    /// A skeleton map for models fitted to the shared library, absent for authored clips.
    fn skeleton(&self) -> Option<&dyn Skeleton>;
}

/// The character named `name`.
pub fn named(name: &str) -> Option<&'static dyn Character> {
    CHARACTERS.into_iter().find(|character| character.name() == name)
}
