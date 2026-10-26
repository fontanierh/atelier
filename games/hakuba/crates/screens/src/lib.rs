//! What every screen shares: which screen is showing, Escape back to the menu (or pausing the world), how buttons look
//! and the frame rate.

use bevy::picking::hover::Hovered;
use bevy::prelude::*;
use bevy::ui_widgets::{ActivateOnPress, Button};

pub struct ScreensPlugin;

impl Plugin for ScreensPlugin {
    fn build(&self, app: &mut App) {
        app.init_state::<Screen>()
            .add_sub_state::<Pause>()
            .add_systems(Startup, spawn_fps)
            .add_systems(Update, (back, hover, show_fps))
            .add_systems(OnEnter(Pause::Paused), |mut time: ResMut<Time<Virtual>>| time.pause())
            .add_systems(OnExit(Pause::Paused), |mut time: ResMut<Time<Virtual>>| time.unpause());
    }
}

/// The screen showing. The game opens on the menu.
#[derive(States, Clone, Copy, PartialEq, Eq, Hash, Debug, Default)]
pub enum Screen {
    #[default]
    Menu,
    World,
    Viewer,
    Settings,
}

/// Whether the world is paused. While it is, its time stands still and the pause screen shows over it.
#[derive(SubStates, Clone, Copy, PartialEq, Eq, Hash, Debug, Default)]
#[source(Screen = Screen::World)]
pub enum Pause {
    #[default]
    Playing,
    Paused,
}

const BUTTON: Color = Color::srgb(0.15, 0.15, 0.17);
const BUTTON_HOVERED: Color = Color::srgb(0.27, 0.27, 0.32);
const TEXT: Color = Color::srgb(0.92, 0.92, 0.92);

/// A button showing `label`. It acts as soon as it is pressed: react with `observe(|_: On<Activate>| ...)` next to it.
pub fn button(label: impl Into<String>) -> impl Bundle {
    (
        Button,
        ActivateOnPress,
        Hovered::default(),
        Node {
            padding: UiRect::axes(px(18), px(10)),
            justify_content: JustifyContent::Center,
            border_radius: BorderRadius::all(px(6)),
            ..default()
        },
        BackgroundColor(BUTTON),
        children![text(label, 20.0)],
    )
}

/// A line of text, `size` pixels high.
pub fn text(content: impl Into<String>, size: f32) -> impl Bundle {
    (Text::new(content), TextFont { font_size: FontSize::Px(size), ..default() }, TextColor(TEXT))
}

/// Escape, or a controller's Start button: pauses or resumes the world, and from any other screen goes back to the
/// menu.
fn back(
    keys: Res<ButtonInput<KeyCode>>,
    gamepads: Query<&Gamepad>,
    screen: Res<State<Screen>>,
    pause: Option<Res<State<Pause>>>,
    mut next_screen: ResMut<NextState<Screen>>,
    mut next_pause: ResMut<NextState<Pause>>,
) {
    let start = gamepads.iter().any(|gamepad| gamepad.just_pressed(GamepadButton::Start));
    if !keys.just_pressed(KeyCode::Escape) && !start {
        return;
    }
    match (screen.get(), pause.map(|pause| *pause.get())) {
        (Screen::World, Some(Pause::Playing)) => next_pause.set(Pause::Paused),
        (Screen::World, _) => next_pause.set(Pause::Playing),
        (Screen::Menu, _) => {}
        _ => next_screen.set(Screen::Menu),
    }
}

/// Buttons the pointer has just moved onto or off.
type HoverChanged = (Changed<Hovered>, With<Button>);

fn hover(mut buttons: Query<(&Hovered, &mut BackgroundColor), HoverChanged>) {
    for (hovered, mut color) in &mut buttons {
        *color = BackgroundColor(if hovered.get() { BUTTON_HOVERED } else { BUTTON });
    }
}

/// The frame rate, shown small in the top right corner of every screen, above what the screen puts there: how many
/// frames the last whole second drew, and how long the slowest of them took, since a hitch shows only in the slowest.
#[derive(Component)]
struct Fps;

fn spawn_fps(mut commands: Commands) {
    commands.spawn((
        Fps,
        text("", 12.0),
        Node { position_type: PositionType::Absolute, top: px(1), right: px(4), ..default() },
        GlobalZIndex(i32::MAX),
    ));
}

/// The frames counted so far this second, and the longest of them.
#[derive(Default)]
struct Second {
    elapsed: f32,
    frames: u32,
    slowest: f32,
}

fn show_fps(time: Res<Time<Real>>, mut second: Local<Second>, mut shown: Single<&mut Text, With<Fps>>) {
    let frame = time.delta_secs();
    second.elapsed += frame;
    second.frames += 1;
    second.slowest = second.slowest.max(frame);
    if second.elapsed >= 1.0 {
        shown.0 = format!("{} FPS  {:.0} ms", second.frames, second.slowest * 1000.0);
        *second = Second::default();
    }
}
