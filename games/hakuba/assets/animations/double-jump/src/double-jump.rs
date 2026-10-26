//! The double jump's somersault, on its source's Mixamo skeleton. A character cannot change it.

use crate::rig::Bones;
use crate::rig::animation::no_changes;
use crate::rig::animations::Animation;
use crate::rig::pose::Pose;
use anyhow::Result;
use serde_json::Value;

pub struct DoubleJump;

impl Animation for DoubleJump {
    fn name(&self) -> &'static str {
        "double-jump"
    }

    fn source(&self) -> Bones {
        Bones::mixamo()
    }

    fn change(&self, changes: Option<&Value>, _: &Pose, _: &mut [Pose]) -> Result<()> {
        no_changes(changes)
    }
}
