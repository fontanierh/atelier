//! The list of settings: on each row its name, and its value between a button that steps it down (<) and one that steps
//! it up.

use bevy::prelude::*;
use bevy::ui_widgets::{Activate, observe};
use hakuba_screens::{button, text};

use crate::{AntiAliasing, Detail, FrameRate, Resolution, Settings, Shadows};

#[path = "skate_panel.rs"]
mod skate_panel;

pub struct PanelPlugin;

impl Plugin for PanelPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Update, (show_values, skate_panel::show_pages));
    }
}

/// One row of the panel.
#[derive(Clone, Copy, PartialEq, Eq)]
enum Row {
    Painterly,
    Wind,
    Resolution,
    Shadows,
    AntiAliasing,
    Detail,
    FrameRate,
    Volume,
    Skate(skate_panel::Row),
}

impl Row {
    const ALL: [Row; 8] = [
        Row::Painterly,
        Row::Wind,
        Row::Resolution,
        Row::Shadows,
        Row::AntiAliasing,
        Row::Detail,
        Row::FrameRate,
        Row::Volume,
    ];

    fn name(self) -> &'static str {
        match self {
            Row::Painterly => "Painterly",
            Row::Wind => "Wind",
            Row::Resolution => "Resolution",
            Row::Shadows => "Shadows",
            Row::AntiAliasing => "Anti-aliasing",
            Row::Detail => "Detail",
            Row::FrameRate => "Frame rate",
            Row::Volume => "Volume",
            Row::Skate(row) => row.name(),
        }
    }

    fn value(self, settings: &Settings) -> String {
        match self {
            Row::Painterly => format!("{:.0} %", settings.painterly * 100.0),
            Row::Wind => format!("{:.0} %", settings.wind * 100.0),
            Row::Resolution => match settings.resolution {
                Resolution::Auto => "Auto".into(),
                Resolution::Percent(percent) => format!("{percent} %"),
            },
            Row::Shadows => match settings.shadows {
                Shadows::Off => "Off",
                Shadows::Near => "Near",
                Shadows::Far => "Far",
            }
            .into(),
            Row::AntiAliasing => match settings.anti_aliasing {
                AntiAliasing::Temporal => "Temporal",
                AntiAliasing::Smaa => "SMAA",
                AntiAliasing::Off => "Off",
            }
            .into(),
            Row::Detail => match settings.detail {
                Detail::Near => "Near",
                Detail::Normal => "Normal",
                Detail::Far => "Far",
            }
            .into(),
            Row::FrameRate => match settings.frame_rate {
                FrameRate::Thirty => "30 FPS",
                FrameRate::Sixty => "60 FPS",
                FrameRate::Unlimited => "Unlimited",
            }
            .into(),
            Row::Volume => format!("{:.0} %", settings.volume * 100.0),
            Row::Skate(row) => row.value(&settings.skate),
        }
    }

    /// Steps the setting one choice up (`by` 1) or down (`by` -1), stopping at the ends.
    fn step(self, settings: &mut Settings, by: i32) {
        match self {
            Row::Painterly => settings.painterly = stepped(settings.painterly, by as f32 * 0.05, 0.0, 1.0),
            Row::Wind => settings.wind = stepped(settings.wind, by as f32 * 0.1, 0.0, 2.0),
            Row::Resolution => settings.resolution = next(&Resolution::ALL, settings.resolution, by),
            Row::Shadows => settings.shadows = next(&[Shadows::Off, Shadows::Near, Shadows::Far], settings.shadows, by),
            Row::AntiAliasing => {
                let all = [AntiAliasing::Off, AntiAliasing::Smaa, AntiAliasing::Temporal];
                settings.anti_aliasing = next(&all, settings.anti_aliasing, by);
            }
            Row::Detail => settings.detail = next(&[Detail::Near, Detail::Normal, Detail::Far], settings.detail, by),
            Row::FrameRate => {
                let all = [FrameRate::Thirty, FrameRate::Sixty, FrameRate::Unlimited];
                settings.frame_rate = next(&all, settings.frame_rate, by);
            }
            Row::Volume => settings.volume = stepped(settings.volume, by as f32 * 0.1, 0.0, 1.0),
            Row::Skate(row) => row.step(&mut settings.skate, by),
        }
    }
}

/// `value` moved by `by`, kept between `low` and `high` and rounded to hundredths, so steps add up exactly.
fn stepped(value: f32, by: f32, low: f32, high: f32) -> f32 {
    ((value + by).clamp(low, high) * 100.0).round() / 100.0
}

/// The choice `by` places after `now` in `all`, stopping at the ends.
fn next<T: Copy + PartialEq>(all: &[T], now: T, by: i32) -> T {
    let at = all.iter().position(|choice| *choice == now).unwrap_or(0) as i32;
    all[(at + by).clamp(0, all.len() as i32 - 1) as usize]
}

/// The text showing a row's value.
#[derive(Component)]
struct Value(Row);
#[derive(Component)]
struct StepButton(Row);

fn disabled(row: Row, settings: &Settings) -> bool {
    matches!(row, Row::Skate(row) if settings.skate.mode != crate::SkateMode::Custom && !row.always())
}

/// General settings and grouped skating pages, shared by the menu and the pause screen.
pub fn panel() -> impl Bundle {
    skate_panel::panel()
}

fn row(row: Row) -> impl Bundle {
    let step = move |by: i32| move |_: On<Activate>, mut settings: ResMut<Settings>| row.step(&mut settings, by);
    (
        Node { align_items: AlignItems::Center, column_gap: px(10), ..default() },
        children![
            (Node { width: px(230), flex_shrink: 1.0, ..default() }, children![text(row.name(), 20.0)]),
            (StepButton(row), button("<"), observe(step(-1))),
            (
                Node { width: px(130), flex_shrink: 0.0, justify_content: JustifyContent::Center, ..default() },
                children![(Value(row), text("", 20.0))],
            ),
            (StepButton(row), button(">"), observe(step(1))),
        ],
    )
}

fn show_values(
    mut commands: Commands,
    settings: Res<Settings>,
    mut values: Query<(&Value, &mut Text, &mut TextColor)>,
    buttons: Query<(Entity, &StepButton)>,
    added: Query<(), Added<Value>>,
) {
    if !settings.is_changed() && added.is_empty() {
        return;
    }
    for (Value(row), mut shown, mut color) in &mut values {
        shown.0 = row.value(&settings);
        color.0 = if disabled(*row, &settings) { Color::srgb(0.45, 0.45, 0.47) } else { Color::srgb(0.92, 0.92, 0.92) };
    }
    for (entity, StepButton(row)) in &buttons {
        if disabled(*row, &settings) {
            commands.entity(entity).insert(bevy::ui::InteractionDisabled);
        } else {
            commands.entity(entity).remove::<bevy::ui::InteractionDisabled>();
        }
    }
}
