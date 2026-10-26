//! Nox: which of his bones plays each rig bone.

use crate::rig::characters::Character;
use crate::rig::{Bones, Skeleton};

pub struct Nox;

impl Skeleton for Nox {
    fn bones(&self) -> Bones {
        Bones::mixamo()
    }
}

impl Character for Nox {
    fn name(&self) -> &'static str {
        "nox"
    }
}
