//! Dev mode: a free camera for exploring the world and taking notes on what is wrong with it. While it is on, the
//! player waits (`hakuba_player` stops them) and the camera flies wherever it is steered; the tiles load round it.

mod notes;
mod zip;

use bevy::input::mouse::{AccumulatedMouseMotion, AccumulatedMouseScroll, MouseScrollUnit};
use bevy::prelude::*;
use bevy::window::PrimaryWindow;
use hakuba_screens::{DevMode, Pause};

/// How fast the camera flies at first, and held fast, in metres a second.
const START_SPEED: f32 = 20.0;
const FAST: f32 = 5.0;
const SLOWEST: f32 = 2.0;
const FASTEST: f32 = 400.0;
/// How much one line of scroll changes the speed by.
const SPEED_PER_LINE: f32 = 1.15;
const PIXELS_PER_LINE: f32 = 50.0;
/// As the player's camera: a drag across the window turns it this many times round; the arrows and the stick turn
/// it this many radians a second.
const TURNS_PER_WINDOW: f32 = 0.6;
const LOOK_SPEED: Vec2 = Vec2::new(2.6, 1.6);
const DEAD_ZONE: f32 = 0.15;
/// How far the camera looks up or down at most, short of straight.
const STEEPEST: f32 = 1.55;

pub struct DevPlugin;

impl Plugin for DevPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<notes::Notes>()
            .add_systems(Update, toggle.run_if(in_state(Pause::Playing)))
            .add_systems(OnEnter(DevMode::On), (take_off, show_keys))
            .add_systems(
                Update,
                (fly, notes::take, notes::export, label_keys)
                    .run_if(in_state(DevMode::On))
                    .run_if(in_state(Pause::Playing)),
            );
    }
}

/// Where the camera looks: about up from -Z toward -X, and up (positive) or down; and how fast it flies.
#[derive(Resource)]
struct Flight {
    yaw: f32,
    pitch: f32,
    speed: f32,
}

/// The backquote key, left of 1, turns dev mode on or off.
fn toggle(keys: Res<ButtonInput<KeyCode>>, mode: Res<State<DevMode>>, mut next: ResMut<NextState<DevMode>>) {
    if keys.just_pressed(KeyCode::Backquote) {
        next.set(if *mode.get() == DevMode::On { DevMode::Off } else { DevMode::On });
    }
}

/// Flies on from where the player's camera is, looking the way it looks.
fn take_off(mut commands: Commands, camera: Single<&Transform, With<Camera3d>>, flight: Option<Res<Flight>>) {
    let ahead = camera.forward();
    let speed = flight.map_or(START_SPEED, |flight| flight.speed);
    commands.insert_resource(Flight { yaw: (-ahead.x).atan2(-ahead.z), pitch: ahead.y.clamp(-1.0, 1.0).asin(), speed });
}

#[allow(clippy::too_many_arguments)]
fn fly(
    mut flight: ResMut<Flight>,
    mut camera: Single<&mut Transform, With<Camera3d>>,
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
    let mut rise = key(KeyCode::KeyE) + key(KeyCode::Space) - key(KeyCode::KeyQ) - key(KeyCode::KeyC);
    let mut look =
        Vec2::new(key(KeyCode::ArrowRight) - key(KeyCode::ArrowLeft), key(KeyCode::ArrowUp) - key(KeyCode::ArrowDown))
            * LOOK_SPEED
            * dt;
    if buttons.pressed(MouseButton::Left) || buttons.pressed(MouseButton::Right) {
        let turn = std::f32::consts::TAU * TURNS_PER_WINDOW / window.width().max(1.0);
        look += Vec2::new(motion.delta.x, -motion.delta.y) * turn;
    }
    let mut fast = keys.any_pressed([KeyCode::ShiftLeft, KeyCode::ShiftRight]);
    for gamepad in &gamepads {
        let left = dead(gamepad.left_stick());
        if left != Vec2::ZERO {
            stick = left;
        }
        look += dead(gamepad.right_stick()) * LOOK_SPEED * dt;
        rise += gamepad.get(GamepadButton::RightTrigger2).unwrap_or(0.0)
            - gamepad.get(GamepadButton::LeftTrigger2).unwrap_or(0.0);
        fast |= gamepad.pressed(GamepadButton::LeftTrigger);
    }
    let lines = match scroll.unit {
        MouseScrollUnit::Line => scroll.delta.y,
        MouseScrollUnit::Pixel => scroll.delta.y / PIXELS_PER_LINE,
    };
    flight.speed = (flight.speed * SPEED_PER_LINE.powf(lines)).clamp(SLOWEST, FASTEST);
    flight.yaw -= look.x;
    flight.pitch = (flight.pitch + look.y).clamp(-STEEPEST, STEEPEST);
    let rotation = Quat::from_rotation_y(flight.yaw) * Quat::from_rotation_x(flight.pitch);
    let (ahead, right) = (rotation * Vec3::NEG_Z, rotation * Vec3::X);
    let heading = ahead * stick.y.clamp(-1.0, 1.0) + right * stick.x.clamp(-1.0, 1.0) + Vec3::Y * rise.clamp(-1.0, 1.0);
    let speed = flight.speed * if fast { FAST } else { 1.0 };
    camera.translation += heading.clamp_length_max(1.0) * speed * dt;
    camera.rotation = rotation;
}

fn dead(stick: Vec2) -> Vec2 {
    let length = stick.length().min(1.0);
    if length < DEAD_ZONE { Vec2::ZERO } else { stick / stick.length() * (length - DEAD_ZONE) / (1.0 - DEAD_ZONE) }
}

/// The keys, in the corner while dev mode is on.
#[derive(Component)]
struct Keys;

fn show_keys(mut commands: Commands) {
    commands.spawn((
        DespawnOnExit(DevMode::On),
        Keys,
        Node {
            position_type: PositionType::Absolute,
            left: px(12),
            bottom: px(12),
            padding: UiRect::axes(px(12), px(8)),
            border_radius: BorderRadius::all(px(6)),
            ..default()
        },
        BackgroundColor(Color::srgba(0.04, 0.04, 0.06, 0.6)),
        GlobalZIndex(i32::MAX - 3),
        children![(
            Text::default(),
            TextFont { font_size: FontSize::Px(15.0), ..default() },
            TextColor(Color::srgb(0.95, 0.95, 0.92)),
        )],
    ));
}

fn label_keys(
    mut keys: Single<(&mut Visibility, &Children), With<Keys>>,
    mut texts: Query<&mut Text>,
    flight: Res<Flight>,
    notes: Res<notes::Notes>,
    camera: Single<&Transform, With<Camera3d>>,
) {
    let (visibility, children) = &mut *keys;
    // Not in the screenshot a note is taking.
    **visibility = if notes.taking { Visibility::Hidden } else { Visibility::Inherited };
    let Some(mut text) = children.first().and_then(|&child| texts.get_mut(child).ok()) else { return };
    let at = notes::map(camera.translation);
    let count = notes::counted(notes.taken.len());
    let mut line = format!(
        "DEV MODE   {:.0}, {:.0}, {:.0} m   {:.0} m/s\nWASD fly | E or Space up | Q or C down | Shift fast | scroll \
         speed | drag look\nN note | X export {count} | ` leave",
        at.x, at.y, at.z, flight.speed,
    );
    if let Some(flash) = &notes.flash {
        line = format!("{flash}\n{line}");
    }
    if text.0 != line {
        text.0 = line;
    }
}
