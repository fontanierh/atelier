//! Leaning back under the paraglider to slow down, a loop. A character cannot change it.

use crate::rig::Bones;
use crate::rig::animation::no_changes;
use crate::rig::animations::Animation;
use crate::rig::pose::Pose;
use anyhow::Result;
use serde_json::Value;

pub struct GlideBack;

impl Animation for GlideBack {
    fn name(&self) -> &'static str {
        "glide-back"
    }

    fn source(&self) -> Bones {
        Bones::library()
    }

    fn change(&self, changes: Option<&Value>, _: &Pose, _: &mut [Pose]) -> Result<()> {
        no_changes(changes)
    }
}
