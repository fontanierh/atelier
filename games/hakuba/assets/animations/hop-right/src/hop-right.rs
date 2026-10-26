//! The side hop to the right, from frame 4. A character cannot change it.

use crate::rig::Bones;
use crate::rig::animation::no_changes;
use crate::rig::animations::Animation;
use crate::rig::pose::Pose;
use anyhow::Result;
use serde_json::Value;

pub struct HopRight;

impl Animation for HopRight {
    fn name(&self) -> &'static str {
        "hop-right"
    }

    fn source(&self) -> Bones {
        Bones::library()
    }

    fn change(&self, changes: Option<&Value>, _: &Pose, _: &mut [Pose]) -> Result<()> {
        no_changes(changes)
    }
}
