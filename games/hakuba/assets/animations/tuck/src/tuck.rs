//! The body tucked into a ball, one pose, which the game turns through the double jump's somersault. A character cannot change it.

use crate::rig::Bones;
use crate::rig::animation::no_changes;
use crate::rig::animations::Animation;
use crate::rig::pose::Pose;
use anyhow::Result;
use serde_json::Value;

pub struct Tuck;

impl Animation for Tuck {
    fn name(&self) -> &'static str {
        "tuck"
    }

    fn source(&self) -> Bones {
        Bones::library()
    }

    fn change(&self, changes: Option<&Value>, _: &Pose, _: &mut [Pose]) -> Result<()> {
        no_changes(changes)
    }
}
