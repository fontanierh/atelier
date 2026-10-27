//! Wanderer carries its own animation on its compact skeleton.

use crate::rig::Skeleton;
use crate::rig::characters::Character;

pub struct Wanderer;

impl Character for Wanderer {
    fn name(&self) -> &'static str {
        "wanderer"
    }

    fn skeleton(&self) -> Option<&dyn Skeleton> {
        None
    }
}
