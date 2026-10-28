//! A camp visitor with its own skinned idle and practice clips.

use crate::rig::Skeleton;
use crate::rig::characters::Character;

pub struct CampVisitor;

impl Character for CampVisitor {
    fn name(&self) -> &'static str {
        "camp-visitor"
    }

    fn skeleton(&self) -> Option<&dyn Skeleton> {
        None
    }
}
