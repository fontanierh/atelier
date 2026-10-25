//! The inspect camera, for checking a model up close. `I` turns it on and off; while it is on, the camera circles a
//! point above the origin:
//!
//! - drag: spin around it
//! - scroll: zoom in and out
//! - shift + drag: move the point up and down
//!
//! Turning it off puts the camera back where it was.

use bevy::input::mouse::{AccumulatedMouseMotion, AccumulatedMouseScroll, MouseScrollUnit};
use bevy::prelude::*;

pub struct InspectPlugin;

impl Plugin for InspectPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Update, (toggle, orbit.run_if(resource_exists::<Inspecting>)).chain());
    }
}

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

/// The inspect camera's state while it is on.
#[derive(Resource)]
struct Inspecting {
    /// Where the camera was before, to go back to.
    overview: Transform,
    /// The point the camera circles.
    focus: Vec3,
    /// The turn around the vertical, in radians.
    yaw: f32,
    /// The angle above the horizontal, in radians.
    pitch: f32,
    distance: f32,
}

fn toggle(
    mut commands: Commands,
    keys: Res<ButtonInput<KeyCode>>,
    inspecting: Option<Res<Inspecting>>,
    mut camera: Single<&mut Transform, With<Camera3d>>,
) {
    if !keys.just_pressed(KeyCode::KeyI) {
        return;
    }
    if let Some(inspecting) = inspecting {
        **camera = inspecting.overview;
        commands.remove_resource::<Inspecting>();
        return;
    }
    // Start from where the camera is, circling a point at chest height above the origin.
    let focus = Vec3::new(0.0, 1.2, 0.0);
    let offset = camera.translation - focus;
    commands.insert_resource(Inspecting {
        overview: **camera,
        focus,
        yaw: offset.x.atan2(offset.z),
        pitch: (offset.y / offset.length()).asin(),
        distance: offset.length().clamp(DISTANCE_M.0, DISTANCE_M.1),
    });
}

fn orbit(
    mut inspecting: ResMut<Inspecting>,
    buttons: Res<ButtonInput<MouseButton>>,
    keys: Res<ButtonInput<KeyCode>>,
    motion: Res<AccumulatedMouseMotion>,
    scroll: Res<AccumulatedMouseScroll>,
    window: Single<&Window>,
    mut camera: Single<&mut Transform, With<Camera3d>>,
) {
    let state = &mut *inspecting;
    if buttons.pressed(MouseButton::Left) {
        let shift = keys.any_pressed([KeyCode::ShiftLeft, KeyCode::ShiftRight]);
        if shift {
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
    **camera = Transform::from_translation(state.focus + direction * state.distance).looking_at(state.focus, Vec3::Y);
}
