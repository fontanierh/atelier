//! Every animation: the [`Animation`] that each animation's asset folder implements in `src/<name>.rs`, listed in
//! [`ANIMATIONS`].

use anyhow::Result;
use serde_json::Value;

use crate::rig::Bones;
use crate::rig::pose::Pose;

#[path = "../../../../assets/animations/backflip/src/backflip.rs"]
mod backflip;
#[path = "../../../../assets/animations/backflip-land/src/backflip-land.rs"]
mod backflip_land;
#[path = "../../../../assets/animations/double-jump/src/double-jump.rs"]
mod double_jump;
#[path = "../../../../assets/animations/fall/src/fall.rs"]
mod fall;
#[path = "../../../../assets/animations/glide/src/glide.rs"]
mod glide;
#[path = "../../../../assets/animations/glide-back/src/glide-back.rs"]
mod glide_back;
#[path = "../../../../assets/animations/glide-close/src/glide-close.rs"]
mod glide_close;
#[path = "../../../../assets/animations/glide-forward/src/glide-forward.rs"]
mod glide_forward;
#[path = "../../../../assets/animations/glide-left/src/glide-left.rs"]
mod glide_left;
#[path = "../../../../assets/animations/glide-open/src/glide-open.rs"]
mod glide_open;
#[path = "../../../../assets/animations/glide-open-falling/src/glide-open-falling.rs"]
mod glide_open_falling;
#[path = "../../../../assets/animations/glide-right/src/glide-right.rs"]
mod glide_right;
#[path = "../../../../assets/animations/hard-land/src/hard-land.rs"]
mod hard_land;
#[path = "../../../../assets/animations/hard-land-up/src/hard-land-up.rs"]
mod hard_land_up;
#[path = "../../../../assets/animations/hop-left/src/hop-left.rs"]
mod hop_left;
#[path = "../../../../assets/animations/hop-left-land/src/hop-left-land.rs"]
mod hop_left_land;
#[path = "../../../../assets/animations/hop-right/src/hop-right.rs"]
mod hop_right;
#[path = "../../../../assets/animations/hop-right-land/src/hop-right-land.rs"]
mod hop_right_land;
#[path = "../../../../assets/animations/idle/src/idle.rs"]
mod idle;
#[path = "../../../../assets/animations/jump/src/jump.rs"]
mod jump;
#[path = "../../../../assets/animations/land/src/land.rs"]
mod land;
#[path = "../../../../assets/animations/run/src/run.rs"]
mod run;
#[path = "../../../../assets/animations/run-jump/src/run-jump.rs"]
mod run_jump;
#[path = "../../../../assets/animations/run-land/src/run-land.rs"]
mod run_land;
#[path = "../../../../assets/animations/sprint/src/sprint.rs"]
mod sprint;
#[path = "../../../../assets/animations/walk/src/walk.rs"]
mod walk;

/// Every animation, each exported with every character.
pub const ANIMATIONS: [&dyn Animation; 26] = [
    &idle::Idle,
    &walk::Walk,
    &run::Run,
    &sprint::Sprint,
    &jump::Jump,
    &run_jump::RunJump,
    &fall::Fall,
    &land::Land,
    &run_land::RunLand,
    &hard_land::HardLand,
    &hard_land_up::HardLandUp,
    &hop_left::HopLeft,
    &hop_right::HopRight,
    &hop_left_land::HopLeftLand,
    &hop_right_land::HopRightLand,
    &backflip::Backflip,
    &backflip_land::BackflipLand,
    &double_jump::DoubleJump,
    &glide_open::GlideOpen,
    &glide_open_falling::GlideOpenFalling,
    &glide::Glide,
    &glide_forward::GlideForward,
    &glide_back::GlideBack,
    &glide_left::GlideLeft,
    &glide_right::GlideRight,
    &glide_close::GlideClose,
];

/// What the exporter needs from an animation's own code.
pub trait Animation: Sync {
    /// Its name: its asset folder's name under `animations/`, and the clip's name in every export.
    fn name(&self) -> &'static str;

    /// The skeleton its source clip is on.
    fn source(&self) -> Bones;

    /// Applies a character's `changes` to the animation's `frames`, fitted to the character's `rest` pose. `changes`
    /// is the character's table for this animation in its `asset.toml`, if it has one;
    /// [`changes`](crate::rig::animation::changes) reads it.
    fn change(&self, changes: Option<&Value>, rest: &Pose, frames: &mut [Pose]) -> Result<()>;
}

/// The animation named `name`.
pub fn named(name: &str) -> Option<&'static dyn Animation> {
    ANIMATIONS.into_iter().find(|animation| animation.name() == name)
}
