//! The pause screen over the world: the settings, so their effect shows at once, and buttons to play on, to turn dev
//! mode on or off, or to go back to the menu.

use bevy::prelude::*;
use bevy::ui_widgets::{Activate, observe};
use hakuba_screens::{DevMode, Pause, Screen, button, text};
use hakuba_settings::panel;

pub struct PausePlugin;

impl Plugin for PausePlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(Pause::Paused), show);
    }
}

fn show(mut commands: Commands, dev: Res<State<DevMode>>) {
    let dev_label = match dev.get() {
        DevMode::Off => "Dev mode: fly and take notes",
        DevMode::On => "Leave dev mode",
    };
    commands.spawn((
        DespawnOnExit(Pause::Paused),
        Node {
            position_type: PositionType::Absolute,
            width: percent(100),
            height: percent(100),
            flex_direction: FlexDirection::Column,
            align_items: AlignItems::Center,
            justify_content: JustifyContent::Center,
            row_gap: px(18),
            ..default()
        },
        BackgroundColor(Color::srgba(0.04, 0.04, 0.06, 0.55)),
        GlobalZIndex(i32::MAX - 2),
        children![
            text("Paused", 36.0),
            panel(),
            (
                Node { column_gap: px(14), ..default() },
                children![
                    (
                        button("Play on"),
                        observe(|_: On<Activate>, mut next: ResMut<NextState<Pause>>| next.set(Pause::Playing))
                    ),
                    (
                        button(dev_label),
                        observe(
                            |_: On<Activate>,
                             dev: Res<State<DevMode>>,
                             mut next_dev: ResMut<NextState<DevMode>>,
                             mut next_pause: ResMut<NextState<Pause>>| {
                                next_dev.set(if *dev.get() == DevMode::On { DevMode::Off } else { DevMode::On });
                                next_pause.set(Pause::Playing);
                            }
                        )
                    ),
                    (
                        button("Menu"),
                        observe(|_: On<Activate>, mut next: ResMut<NextState<Screen>>| next.set(Screen::Menu))
                    ),
                ],
            ),
        ],
    ));
}
