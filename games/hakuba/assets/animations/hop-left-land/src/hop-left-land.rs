//! Landing from the side hop to the left, frames 2 to 12 at 0.8 of their speed as Yorimichi plays them. A character cannot change it.

use crate::rig::Bones;
use crate::rig::animation::no_changes;
use crate::rig::animations::Animation;
use crate::rig::pose::Pose;
use anyhow::Result;
use serde_json::Value;

pub struct HopLeftLand;

impl Animation for HopLeftLand {
    fn name(&self) -> &'static str {
        "hop-left-land"
    }

    fn source(&self) -> Bones {
        Bones::library()
    }

    fn change(&self, changes: Option<&Value>, _: &Pose, _: &mut [Pose]) -> Result<()> {
        no_changes(changes)
    }
}
