//! What every screen shares: which screen is showing, Escape back to the menu, and how buttons look.

use bevy::picking::hover::Hovered;
use bevy::prelude::*;
use bevy::ui_widgets::{ActivateOnPress, Button};

pub struct ScreensPlugin;

impl Plugin for ScreensPlugin {
    fn build(&self, app: &mut App) {
        app.init_state::<Screen>().add_systems(Update, (back_to_menu, hover));
    }
}

/// The screen showing. The game opens on the menu.
#[derive(States, Clone, Copy, PartialEq, Eq, Hash, Debug, Default)]
pub enum Screen {
    #[default]
    Menu,
    World,
    Viewer,
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

fn back_to_menu(keys: Res<ButtonInput<KeyCode>>, mut next: ResMut<NextState<Screen>>) {
    if keys.just_pressed(KeyCode::Escape) {
        next.set(Screen::Menu);
    }
}

/// Buttons the pointer has just moved onto or off.
type HoverChanged = (Changed<Hovered>, With<Button>);

fn hover(mut buttons: Query<(&Hovered, &mut BackgroundColor), HoverChanged>) {
    for (hovered, mut color) in &mut buttons {
        *color = BackgroundColor(if hovered.get() { BUTTON_HOVERED } else { BUTTON });
    }
}
