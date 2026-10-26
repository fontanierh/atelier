//! The viewer's camera, circling a point above the origin:
//!
//! - drag: spin around it
//! - scroll: zoom in and out
//! - shift + drag: move the point up and down

use bevy::input::mouse::{AccumulatedMouseMotion, AccumulatedMouseScroll, MouseScrollUnit};
use bevy::prelude::*;

/// How far a drag across the whole window spins the camera, in turns.
const SPIN_PER_WINDOW: f32 = 1.0;
/// How far the camera may get from the point it circles, in metres.
const DISTANCE_M: (f32, f32) = (0.2, 8.0);
/// How high the point it circles may go, in metres.
const HEIGHT_M: (f32, f32) = (0.0, 2.2);
/// How much one line of scrolling zooms, as a fraction of the distance.
const ZOOM_PER_LINE: f32 = 0.12;
/// Browsers scroll in pixels; this many make a line.
const PIXELS_PER_LINE: f32 = 50.0;

/// A camera circling `focus`.
#[derive(Component)]
pub struct Orbit {
    pub focus: Vec3,
    /// The turn around the vertical, in radians; 0 looks along -Z, at a character's front.
    pub yaw: f32,
    /// The angle above the horizontal, in radians.
    pub pitch: f32,
    pub distance: f32,
}

pub fn orbit(
    buttons: Res<ButtonInput<MouseButton>>,
    keys: Res<ButtonInput<KeyCode>>,
    motion: Res<AccumulatedMouseMotion>,
    scroll: Res<AccumulatedMouseScroll>,
    window: Single<&Window>,
    camera: Single<(&mut Orbit, &mut Transform)>,
) {
    let (mut state, mut transform) = camera.into_inner();
    if buttons.pressed(MouseButton::Left) {
        if keys.any_pressed([KeyCode::ShiftLeft, KeyCode::ShiftRight]) {
            // Dragging up raises the point, by as much as the drag covers at its distance.
            let metres_per_pixel = state.distance / window.height();
            state.focus.y = (state.focus.y - motion.delta.y * metres_per_pixel).clamp(HEIGHT_M.0, HEIGHT_M.1);
        } else {
            let radians_per_pixel = SPIN_PER_WINDOW * std::f32::consts::TAU / window.width();
            state.yaw -= motion.delta.x * radians_per_pixel;
            state.pitch = (state.pitch + motion.delta.y * radians_per_pixel).clamp(-1.5, 1.5);
        }
    }
    let lines = match scroll.unit {
        MouseScrollUnit::Line => scroll.delta.y,
        MouseScrollUnit::Pixel => scroll.delta.y / PIXELS_PER_LINE,
    };
    state.distance = (state.distance * (1.0 - ZOOM_PER_LINE).powf(lines)).clamp(DISTANCE_M.0, DISTANCE_M.1);

    let direction = Quat::from_euler(EulerRot::YXZ, state.yaw, -state.pitch, 0.0) * Vec3::Z;
    *transform = Transform::from_translation(state.focus + direction * state.distance).looking_at(state.focus, Vec3::Y);
}
