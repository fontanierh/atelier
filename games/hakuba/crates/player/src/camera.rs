//! The camera: it orbits the player, looking at their shoulders, turned by the mouse or the right stick and brought
//! nearer by scrolling. It comes in front of anything solid between it and the player rather than see through it.

use bevy::prelude::*;
use hakuba_world::Ground;

use crate::Player;
use crate::input::Controls;

/// The point the camera looks at, above the player's feet, in metres.
const TARGET_M: f32 = 1.45;

/// How near and far the camera keeps from that point, and where it starts, in metres.
const NEAREST_M: f32 = 2.0;
const FURTHEST_M: f32 = 8.0;
const START_M: f32 = 4.5;

/// How far a line of scrolling brings the camera nearer, as a share of its distance.
const ZOOM_PER_LINE: f32 = 0.1;

/// How far the camera looks down, at most, and up, in radians, and how far down it starts.
const LOWEST: f32 = -1.3;
const HIGHEST: f32 = 0.6;
const START_PITCH: f32 = -0.25;

/// How close in front of something solid the camera stays, in metres.
const CLEARANCE_M: f32 = 0.25;

/// How fast the point the camera looks at catches up with the player: the share of the way it closes each second.
const FOLLOW_RATE: f32 = 12.0;

/// Where the camera is about the player.
pub struct Orbit {
    /// Which way it looks over the ground, in radians about up: along -Z at 0, turning toward -X.
    pub yaw: f32,
    /// How far it looks up (positive) or down, in radians.
    pub pitch: f32,
    /// How far it keeps from the point it looks at, unless something solid comes between, in metres.
    pub distance: f32,
    /// The point it looks at, which follows the player's shoulders smoothly.
    target: Option<Vec3>,
}

impl Orbit {
    /// Behind a player facing `yaw` (from +Z toward +X), looking the way they face.
    pub fn behind(yaw: f32) -> Self {
        Self { yaw: yaw + std::f32::consts::PI, pitch: START_PITCH, distance: START_M, target: None }
    }
}

pub fn follow(
    controls: Res<Controls>,
    time: Res<Time>,
    mut ground: Ground,
    mut players: Query<(&mut Player, &Transform)>,
    mut camera: Single<&mut Transform, (With<Camera3d>, Without<Player>)>,
) {
    let Ok((mut player, at)) = players.single_mut() else { return };
    let orbit = &mut player.camera;
    orbit.yaw -= controls.look.x;
    orbit.pitch = (orbit.pitch + controls.look.y).clamp(LOWEST, HIGHEST);
    orbit.distance = (orbit.distance * (1.0 - controls.zoom * ZOOM_PER_LINE)).clamp(NEAREST_M, FURTHEST_M);
    let wanted = at.translation + Vec3::Y * TARGET_M;
    let share = 1.0 - (-FOLLOW_RATE * time.delta_secs()).exp();
    let target = orbit.target.map_or(wanted, |target| target.lerp(wanted, share));
    orbit.target = Some(target);
    let rotation = Quat::from_rotation_y(orbit.yaw) * Quat::from_rotation_x(orbit.pitch);
    let back = rotation * Vec3::Z;
    let mut distance = orbit.distance;
    if let Ok(direction) = Dir3::new(back)
        && let Some(hit) = ground.cast(target, direction, distance + CLEARANCE_M)
    {
        distance = (hit.distance - CLEARANCE_M).max(0.3);
    }
    **camera = Transform::from_translation(target + back * distance).with_rotation(rotation);
}
