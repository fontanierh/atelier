//! The menu the game opens on: go into the world, or into the character viewer.

use bevy::prelude::*;
use bevy::ui_widgets::{Activate, observe};
use hakuba_screens::{Screen, button, text};

pub struct MenuPlugin;

impl Plugin for MenuPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(Screen::Menu), show);
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
        ],
    ));
}

fn go_to(screen: Screen) -> impl Fn(On<Activate>, ResMut<NextState<Screen>>) {
    move |_, mut next| next.set(screen)
}
