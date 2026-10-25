//! Nox's skeleton and his changes to the animations.

use crate::animations::idle::{Idle, Stance};
use crate::rig::{Bones, Skeleton};

pub struct Nox;

impl Skeleton for Nox {
    fn bones(&self) -> Bones {
        Bones::mixamo()
    }
}

impl Idle for Nox {
    /// Hips back, a slight forward lean with the upper back held up, narrower feet, knees out and arms back.
    fn stance(&self) -> Stance {
        Stance {
            hips_forward_cm: -9.0,
            foot_spacing_cm: -8.0,
            lean_deg: 10.0,
            upper_back_deg: -5.0,
            knees_out_deg: 21.0,
            arm_swing_deg: [-20.0, -20.0],
        }
    }
}
