//! Standing up after a hard landing. A character cannot change it.

use crate::rig::Bones;
use crate::rig::animation::no_changes;
use crate::rig::animations::Animation;
use crate::rig::pose::Pose;
use anyhow::Result;
use serde_json::Value;

pub struct HardLandUp;

impl Animation for HardLandUp {
    fn name(&self) -> &'static str {
        "hard-land-up"
    }

    fn source(&self) -> Bones {
        Bones::library()
    }

    fn change(&self, changes: Option<&Value>, _: &Pose, _: &mut [Pose]) -> Result<()> {
        no_changes(changes)
    }
}
