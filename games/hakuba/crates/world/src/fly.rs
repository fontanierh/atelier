//! The world's camera, flying freely:
//!
//! - drag: look around
//! - W A S D: move forward, left, back and right
//! - E and Q: rise and sink
//! - shift: move ten times faster
//! - scroll: change the speed

use bevy::input::mouse::{AccumulatedMouseMotion, AccumulatedMouseScroll, MouseScrollUnit};
use bevy::prelude::*;
use hakuba_screens::Screen;

/// How far a drag across the whole window turns the camera, in turns.
const TURNS_PER_WINDOW: f32 = 0.5;

/// The speed the camera starts at, in metres a second.
const START_SPEED: f32 = 5.0;

/// How much one line of scrolling changes the speed, as a fraction of it.
const SPEED_PER_LINE: f32 = 0.15;

/// Browsers scroll in pixels; this many make a line.
const PIXELS_PER_LINE: f32 = 50.0;

pub struct FlyPlugin;

impl Plugin for FlyPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Update, fly.run_if(in_state(Screen::World)));
    }
}

/// A camera that flies, at `speed` metres a second.
#[derive(Component)]
pub struct Fly {
    speed: f32,
}

impl Default for Fly {
    fn default() -> Self {
        Self { speed: START_SPEED }
    }
}

fn fly(
    time: Res<Time>,
    keys: Res<ButtonInput<KeyCode>>,
    buttons: Res<ButtonInput<MouseButton>>,
    motion: Res<AccumulatedMouseMotion>,
    scroll: Res<AccumulatedMouseScroll>,
    window: Single<&Window>,
    camera: Single<(&mut Transform, &mut Fly)>,
) {
    let (mut transform, mut fly) = camera.into_inner();
    if buttons.pressed(MouseButton::Left) {
        let turn = motion.delta / window.width() * TURNS_PER_WINDOW * std::f32::consts::TAU;
        let (yaw, pitch, _) = transform.rotation.to_euler(EulerRot::YXZ);
        let pitch = (pitch - turn.y).clamp(-1.5, 1.5);
        transform.rotation = Quat::from_euler(EulerRot::YXZ, yaw - turn.x, pitch, 0.0);
    }
    let lines = match scroll.unit {
        MouseScrollUnit::Line => scroll.delta.y,
        MouseScrollUnit::Pixel => scroll.delta.y / PIXELS_PER_LINE,
    };
    fly.speed *= (1.0 + SPEED_PER_LINE).powf(lines);
    let mut direction = Vec3::ZERO;
    for (key, step) in [
        (KeyCode::KeyW, transform.forward().as_vec3()),
        (KeyCode::KeyS, transform.back().as_vec3()),
        (KeyCode::KeyA, transform.left().as_vec3()),
        (KeyCode::KeyD, transform.right().as_vec3()),
        (KeyCode::KeyE, Vec3::Y),
        (KeyCode::KeyQ, Vec3::NEG_Y),
    ] {
        if keys.pressed(key) {
            direction += step;
        }
    }
    let boost = if keys.pressed(KeyCode::ShiftLeft) { 10.0 } else { 1.0 };
    transform.translation += direction.normalize_or_zero() * fly.speed * boost * time.delta_secs();
}
