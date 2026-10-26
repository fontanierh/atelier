//! The settings: how the world looks and sounds, and how fast the game draws. The game keeps them between visits, and holds
//! itself to the chosen frame rate. The Settings screen, from the menu, shows the [`panel`] of them.

mod panel;

use std::time::Duration;

use bevy::prelude::*;
use bevy::ui_widgets::{Activate, observe};
use bevy::winit::{UpdateMode, WinitSettings};
use hakuba_screens::{Screen, button, text};
use serde::{Deserialize, Serialize};

pub use panel::panel;

pub struct SettingsPlugin;

impl Plugin for SettingsPlugin {
    fn build(&self, app: &mut App) {
        app.insert_resource(load())
            .add_plugins(panel::PanelPlugin)
            .add_systems(Startup, hold_frame_rate)
            .add_systems(OnEnter(Screen::Settings), show)
            .add_systems(
                Update,
                (save, hold_frame_rate).run_if(resource_changed::<Settings>).run_if(not(resource_added::<Settings>)),
            );
    }
}

/// Every setting.
#[derive(Resource, Clone, PartialEq, Debug, Serialize, Deserialize)]
#[serde(default)]
pub struct Settings {
    /// How much of the painterly filter shows over the image, from 0 to 1.
    pub painterly: f32,
    /// How strongly the wind moves the plants, from 0 (still) to 2; 1 is the usual wind.
    pub wind: f32,
    pub resolution: Resolution,
    pub shadows: Shadows,
    pub anti_aliasing: AntiAliasing,
    pub detail: Detail,
    pub frame_rate: FrameRate,
    /// How loud every sound plays, from 0 (silent) to 1 (as recorded).
    pub volume: f32,
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            painterly: 0.7,
            wind: 1.0,
            resolution: Resolution::Auto,
            shadows: Shadows::Near,
            anti_aliasing: AntiAliasing::Temporal,
            detail: Detail::Normal,
            frame_rate: FrameRate::Sixty,
            volume: 1.0,
        }
    }
}

/// How many pixels the world draws.
#[derive(Clone, Copy, PartialEq, Eq, Debug, Serialize, Deserialize)]
pub enum Resolution {
    /// As many as the window has, up to [`Resolution::AUTO_PIXELS`]: a frame stays under 14 ms in a large retina
    /// window.
    Auto,
    /// A share of the window's width and height, in percent.
    Percent(u32),
}

impl Resolution {
    /// The most pixels `Auto` draws.
    pub const AUTO_PIXELS: f32 = 3.0e6;

    /// The choices, in order.
    const ALL: [Resolution; 5] = [
        Resolution::Auto,
        Resolution::Percent(50),
        Resolution::Percent(67),
        Resolution::Percent(85),
        Resolution::Percent(100),
    ];

    /// The size of the image the world draws into a window of `window` pixels.
    pub fn image_size(self, window: Vec2) -> UVec2 {
        let scale = match self {
            Resolution::Auto => (Self::AUTO_PIXELS / (window.x * window.y)).sqrt().min(1.0),
            Resolution::Percent(percent) => percent as f32 / 100.0,
        };
        (window * scale).round().as_uvec2().max(UVec2::ONE)
    }
}

/// How far the sun casts shadows.
#[derive(Clone, Copy, PartialEq, Eq, Debug, Serialize, Deserialize)]
pub enum Shadows {
    Off,
    /// Over 60 m, in one cascade: the trees and bushes along the road.
    Near,
    /// Over 150 m, in two cascades.
    Far,
}

impl Shadows {
    /// How far from the camera shadows reach, in metres, and in how many cascades; None for no shadows.
    pub fn reach(self) -> Option<(f32, usize)> {
        match self {
            Shadows::Off => None,
            Shadows::Near => Some((60.0, 1)),
            Shadows::Far => Some((150.0, 2)),
        }
    }
}

/// How edges are smoothed.
#[derive(Clone, Copy, PartialEq, Eq, Debug, Serialize, Deserialize)]
pub enum AntiAliasing {
    /// Each pixel blends the last frames, so grass and other edges thinner than a pixel stay whole and steady.
    Temporal,
    /// Edges found in each frame on its own are blended: sharper, but thin edges flicker as the camera moves.
    Smaa,
    Off,
}

/// How far from the camera tiles show in full detail.
#[derive(Clone, Copy, PartialEq, Eq, Debug, Serialize, Deserialize)]
pub enum Detail {
    Near,
    Normal,
    Far,
}

impl Detail {
    /// Up to how far from the camera, to the tile's centre, a tile shows its full version, in metres.
    pub fn full_m(self) -> f32 {
        match self {
            Detail::Near => 100.0,
            Detail::Normal => 160.0,
            Detail::Far => 320.0,
        }
    }
}

/// The most frames the game draws a second.
#[derive(Clone, Copy, PartialEq, Eq, Debug, Serialize, Deserialize)]
pub enum FrameRate {
    Thirty,
    Sixty,
    Unlimited,
}

impl FrameRate {
    fn most(self) -> Option<f64> {
        match self {
            FrameRate::Thirty => Some(30.0),
            FrameRate::Sixty => Some(60.0),
            FrameRate::Unlimited => None,
        }
    }
}

/// The game draws at most the chosen frames a second, even on faster screens, and only that many while in the
/// background. Input waits for the next frame rather than drawing one of its own.
fn hold_frame_rate(settings: Res<Settings>, mut commands: Commands) {
    let mode = match settings.frame_rate.most() {
        Some(most) => UpdateMode::Reactive {
            wait: Duration::from_secs_f64(1.0 / most),
            react_to_device_events: false,
            react_to_user_events: false,
            react_to_window_events: false,
        },
        None => UpdateMode::Continuous,
    };
    commands.insert_resource(WinitSettings { focused_mode: mode, unfocused_mode: mode });
}

/// The Settings screen: the panel, and a button back to the menu.
fn show(mut commands: Commands) {
    commands.insert_resource(ClearColor(Color::srgb(0.07, 0.07, 0.09)));
    commands.spawn((Camera2d, DespawnOnExit(Screen::Settings)));
    commands.spawn((
        DespawnOnExit(Screen::Settings),
        Node {
            width: percent(100),
            height: percent(100),
            flex_direction: FlexDirection::Column,
            align_items: AlignItems::Center,
            justify_content: JustifyContent::Center,
            row_gap: px(18),
            ..default()
        },
        children![
            text("Settings", 36.0),
            panel(),
            (button("Back"), observe(|_: On<Activate>, mut next: ResMut<NextState<Screen>>| next.set(Screen::Menu))),
        ],
    ));
}

/// Where the settings are kept: the page's local storage in the browser, a file in the home folder on the desktop.
#[cfg(target_arch = "wasm32")]
mod kept {
    const KEY: &str = "hakuba.settings";

    fn storage() -> Option<web_sys::Storage> {
        web_sys::window()?.local_storage().ok()?
    }

    pub fn read() -> Option<String> {
        storage()?.get_item(KEY).ok()?
    }

    pub fn write(text: &str) {
        if let Some(storage) = storage() {
            let _ = storage.set_item(KEY, text);
        }
    }
}

#[cfg(not(target_arch = "wasm32"))]
mod kept {
    use std::path::PathBuf;

    fn path() -> Option<PathBuf> {
        Some(PathBuf::from(std::env::var_os("HOME")?).join(".config/hakuba/settings.json"))
    }

    pub fn read() -> Option<String> {
        std::fs::read_to_string(path()?).ok()
    }

    pub fn write(text: &str) {
        let Some(path) = path() else { return };
        if let Some(folder) = path.parent() {
            let _ = std::fs::create_dir_all(folder);
        }
        let _ = std::fs::write(path, text);
    }
}

/// The kept settings, or the defaults if none are kept or they cannot be read. A setting missing from what was kept
/// takes its default.
fn load() -> Settings {
    kept::read().and_then(|text| serde_json::from_str(&text).ok()).unwrap_or_default()
}

fn save(settings: Res<Settings>) {
    if let Ok(text) = serde_json::to_string(&*settings) {
        kept::write(&text);
    }
}
