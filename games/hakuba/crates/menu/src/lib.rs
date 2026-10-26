//! The menu the game opens on: go into the world, into the character viewer or to the settings. A controller's South
//! button goes into the world.

use bevy::prelude::*;
use bevy::ui_widgets::{Activate, observe};
use hakuba_screens::{Screen, button, text};

pub struct MenuPlugin;

impl Plugin for MenuPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(Screen::Menu), show).add_systems(Update, play.run_if(in_state(Screen::Menu)));
    }
}

fn show(mut commands: Commands) {
    commands.insert_resource(ClearColor(Color::srgb(0.07, 0.07, 0.09)));
    commands.spawn((Camera2d, DespawnOnExit(Screen::Menu)));
    commands.spawn((
        DespawnOnExit(Screen::Menu),
        Node {
            width: percent(100),
            height: percent(100),
            flex_direction: FlexDirection::Column,
            align_items: AlignItems::Center,
            justify_content: JustifyContent::Center,
            row_gap: px(14),
            ..default()
        },
        children![
            text("Hakuba", 48.0),
            (button("World"), observe(go_to(Screen::World))),
            (button("Character viewer"), observe(go_to(Screen::Viewer))),
            (button("Settings"), observe(go_to(Screen::Settings))),
        ],
    ));
}

fn go_to(screen: Screen) -> impl Fn(On<Activate>, ResMut<NextState<Screen>>) {
    move |_, mut next| next.set(screen)
}

fn play(gamepads: Query<&Gamepad>, mut next: ResMut<NextState<Screen>>) {
    if gamepads.iter().any(|gamepad| gamepad.just_pressed(GamepadButton::South)) {
        next.set(Screen::World);
    }
}
