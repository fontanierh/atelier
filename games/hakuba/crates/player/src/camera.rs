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
    /// Set when another owner hands the camera back: the orbit first takes its yaw, pitch and distance from where the
    /// camera is, so walking goes on from the ride's view rather than cutting behind the player.
    from_view: bool,
}

impl Orbit {
    /// Behind a player facing `yaw` (from +Z toward +X), looking the way they face.
    pub fn behind(yaw: f32) -> Self {
        Self { yaw: yaw + std::f32::consts::PI, pitch: START_PITCH, distance: START_M, target: None, from_view: false }
    }

    /// Wherever the camera is when walking next places it.
    pub fn from_view() -> Self {
        Self { from_view: true, ..Self::behind(0.0) }
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
    if player.owner != crate::MovementOwner::Walking {
        return;
    }
    let orbit = &mut player.camera;
    let wanted = at.translation + Vec3::Y * TARGET_M;
    if std::mem::take(&mut orbit.from_view) {
        let back = camera.translation - wanted;
        let distance = back.length();
        if distance > 1e-3 {
            orbit.yaw = back.x.atan2(back.z);
            orbit.pitch = (-back.y / distance).asin().clamp(LOWEST, HIGHEST);
            orbit.distance = distance.clamp(NEAREST_M, FURTHEST_M);
        }
    }
    orbit.yaw -= controls.look.x;
    orbit.pitch = (orbit.pitch + controls.look.y).clamp(LOWEST, HIGHEST);
    orbit.distance = (orbit.distance * (1.0 - controls.zoom * ZOOM_PER_LINE)).clamp(NEAREST_M, FURTHEST_M);
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

/// How long the camera takes to ease from one owner's view to the next, in seconds.
const HANDOVER_S: f32 = 0.45;

/// The view the camera eases from, carried along with the player, and how far into the ease it is.
#[derive(Default)]
pub struct Handover {
    owner: Option<crate::MovementOwner>,
    shown: Option<(Transform, f32, Vec3)>,
    from: Option<(Transform, f32, f32)>,
    /// The field of view the owner asked for: owners set it only when it changes, so the ease keeps it here rather
    /// than easing from its own last output.
    wanted_fov: Option<f32>,
}

/// When the camera changes owner, as on stepping on or off the board, eases it over [`HANDOVER_S`] from the view last
/// shown to the one the new owner places, as Unreal blends between view targets, instead of cutting: position, turn
/// and field of view together. The view eased from moves with the player, so a fast rider does not leave it behind.
pub fn hand_over(
    time: Res<Time>,
    players: Query<(&Player, &Transform), Without<Camera3d>>,
    mut camera: Single<(&mut Transform, &mut Projection), (With<Camera3d>, Without<Player>)>,
    mut handover: Local<Handover>,
) {
    let Ok((player, at)) = players.single() else { return };
    let (transform, projection) = &mut *camera;
    let Projection::Perspective(perspective) = &mut **projection else { return };
    let here = at.translation;
    // An owner set the field of view since the last frame unless it is still the one shown.
    if handover.shown.is_none_or(|(_, fov, _)| fov != perspective.fov) {
        handover.wanted_fov = Some(perspective.fov);
    }
    perspective.fov = handover.wanted_fov.unwrap_or(perspective.fov);
    if handover.owner.is_some_and(|owner| owner != player.owner)
        && let Some((shown, fov, _)) = handover.shown
    {
        handover.from = Some((shown, fov, 0.0));
    }
    handover.owner = Some(player.owner);
    let moved = here - handover.shown.map_or(here, |(_, _, there)| there);
    if let Some((from, fov, elapsed)) = &mut handover.from {
        *elapsed += time.delta_secs();
        let t = (*elapsed / HANDOVER_S).min(1.0);
        let eased = t * t * (3.0 - 2.0 * t);
        from.translation += moved;
        transform.translation = from.translation.lerp(transform.translation, eased);
        transform.rotation = from.rotation.slerp(transform.rotation, eased);
        perspective.fov = *fov + (perspective.fov - *fov) * eased;
        if t >= 1.0 {
            handover.from = None;
        }
    }
    handover.shown = Some((**transform, perspective.fov, here));
}
