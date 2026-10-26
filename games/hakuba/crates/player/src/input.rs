//! What the player asks for this frame, from the keyboard and mouse or a controller:
//!
//! | | keyboard and mouse | controller |
//! |---|---|---|
//! | move | W A S D | left stick (tilt it a little to walk) |
//! | walk | hold Alt | |
//! | sprint | hold Shift | hold East (B on Xbox, Circle on PlayStation) |
//! | jump, double jump, paraglider | Space | South (A, Cross) |
//! | dodge | C | West (X, Square) or the right bumper |
//! | look around | drag, or the arrow keys | right stick |
//! | camera nearer or further | scroll | |

use bevy::input::mouse::{AccumulatedMouseMotion, AccumulatedMouseScroll, MouseScrollUnit};
use bevy::prelude::*;
use bevy::window::PrimaryWindow;

/// How far a drag across the whole window turns the camera, in turns.
const TURNS_PER_WINDOW: f32 = 0.6;

/// How fast the arrow keys and a full tilt of the right stick turn the camera, in radians a second: around, and up and
/// down.
const LOOK_SPEED: Vec2 = Vec2::new(2.6, 1.6);

/// A stick tilted less than this counts as at rest.
const DEAD_ZONE: f32 = 0.15;

/// Browsers scroll in pixels; this many make a line.
const PIXELS_PER_LINE: f32 = 50.0;

/// What the player asks for this frame.
#[derive(Resource, Default)]
pub struct Controls {
    /// Where to move, relative to the camera: x to the right, y ahead, at most 1 long. Shorter means slower.
    pub stick: Vec2,
    pub walk: bool,
    pub sprint: bool,
    /// Pressed this frame.
    pub jump: bool,
    pub dodge: bool,
    /// How far to turn the camera this frame, in radians: around (positive to the right), and up.
    pub look: Vec2,
    /// Lines of scrolling toward the screen this frame, which bring the camera nearer.
    pub zoom: f32,
}

/// Reads the keyboard, the mouse and every controller.
#[allow(clippy::too_many_arguments)]
pub fn read(
    mut controls: ResMut<Controls>,
    keys: Res<ButtonInput<KeyCode>>,
    buttons: Res<ButtonInput<MouseButton>>,
    motion: Res<AccumulatedMouseMotion>,
    scroll: Res<AccumulatedMouseScroll>,
    window: Single<&Window, With<PrimaryWindow>>,
    gamepads: Query<&Gamepad>,
    time: Res<Time<Real>>,
) {
    let dt = time.delta_secs();
    let key = |code: KeyCode| if keys.pressed(code) { 1.0 } else { 0.0 };
    let mut stick = Vec2::new(key(KeyCode::KeyD) - key(KeyCode::KeyA), key(KeyCode::KeyW) - key(KeyCode::KeyS));
    stick = stick.normalize_or_zero();
    let mut look =
        Vec2::new(key(KeyCode::ArrowRight) - key(KeyCode::ArrowLeft), key(KeyCode::ArrowUp) - key(KeyCode::ArrowDown))
            * LOOK_SPEED
            * dt;
    if buttons.pressed(MouseButton::Left) || buttons.pressed(MouseButton::Right) {
        let turn = std::f32::consts::TAU * TURNS_PER_WINDOW / window.width().max(1.0);
        look += Vec2::new(motion.delta.x, -motion.delta.y) * turn;
    }
    let mut walk = keys.any_pressed([KeyCode::AltLeft, KeyCode::AltRight]);
    let mut sprint = keys.any_pressed([KeyCode::ShiftLeft, KeyCode::ShiftRight]);
    let mut jump = keys.just_pressed(KeyCode::Space);
    let mut dodge = keys.just_pressed(KeyCode::KeyC);
    for gamepad in &gamepads {
        let left = dead(gamepad.left_stick());
        if left != Vec2::ZERO {
            stick = left;
        }
        look += dead(gamepad.right_stick()) * LOOK_SPEED * dt;
        sprint |= gamepad.pressed(GamepadButton::East);
        jump |= gamepad.just_pressed(GamepadButton::South);
        dodge |= gamepad.just_pressed(GamepadButton::West) || gamepad.just_pressed(GamepadButton::RightTrigger);
    }
    if sprint {
        walk = false;
    }
    let lines = match scroll.unit {
        MouseScrollUnit::Line => scroll.delta.y,
        MouseScrollUnit::Pixel => scroll.delta.y / PIXELS_PER_LINE,
    };
    *controls = Controls { stick, walk, sprint, jump, dodge, look, zoom: lines };
}

/// The stick's tilt, rescaled so it grows from 0 at the edge of the dead zone to 1 at full tilt.
fn dead(stick: Vec2) -> Vec2 {
    let length = stick.length().min(1.0);
    if length < DEAD_ZONE { Vec2::ZERO } else { stick / stick.length() * (length - DEAD_ZONE) / (1.0 - DEAD_ZONE) }
}
