//! The game program, what runs when the game opens: it builds the app, adds every feature's plugin and opens on the
//! menu (crates/menu).

use bevy::asset::AssetMetaCheck;
use bevy::gltf::GltfPlugin;
use bevy::image::{ImageFilterMode, ImageSamplerDescriptor};
use bevy::prelude::*;
use bevy::window::{MonitorSelection, WindowMode};
use hakuba_audio::SoundsPlugin;
use hakuba_characters::CharactersPlugin;
use hakuba_dev::DevPlugin;
use hakuba_gamepad::GamepadPlugin;
use hakuba_glider::GliderPlugin;
use hakuba_menu::MenuPlugin;
use hakuba_pacing::PacingPlugin;
use hakuba_player::PlayerPlugin;
use hakuba_rendering::RenderingPlugin;
use hakuba_screens::ScreensPlugin;
use hakuba_settings::SettingsPlugin;
use hakuba_skate::SkatePlugin;
use hakuba_viewer::ViewerPlugin;
use hakuba_world::WorldPlugin;

fn main() {
    App::new()
        // A command on an entity that is already gone warns instead of closing the game.
        .set_error_handler(bevy::ecs::error::warn)
        .add_plugins(
            DefaultPlugins
                .set(WindowPlugin {
                    primary_window: Some(Window {
                        title: "Hakuba".into(),
                        // In the browser the game draws into index.html's canvas and fills the page.
                        canvas: Some("#hakuba".into()),
                        fit_canvas_to_parent: true,
                        // HAKUBA_FULLSCREEN opens borderless fullscreen on the main screen; with HAKUBA_SCREEN=other the
                        // window opens and then goes fullscreen on the other screen (crates/screens).
                        mode: if hakuba_screens::switch("HAKUBA_FULLSCREEN").is_some()
                            && !hakuba_screens::switch("HAKUBA_SCREEN").is_some_and(|value| value == "other")
                        {
                            WindowMode::BorderlessFullscreen(MonitorSelection::Primary)
                        } else {
                            WindowMode::Windowed
                        },
                        ..default()
                    }),
                    ..default()
                })
                // Load assets without looking for a .meta file next to each: in the browser, the server answers a
                // missing file with index.html, which Bevy cannot read.
                .set(AssetPlugin { file_path: asset_folder(), meta_check: AssetMetaCheck::Never, ..default() })
                // The world's textures, named by its glTF files, are filtered across their mipmaps and along the view,
                // so the ground and the road stay sharp as they recede. Anisotropic filtering needs every filter linear.
                .set(GltfPlugin {
                    default_sampler: ImageSamplerDescriptor {
                        mag_filter: ImageFilterMode::Linear,
                        min_filter: ImageFilterMode::Linear,
                        mipmap_filter: ImageFilterMode::Linear,
                        anisotropy_clamp: 16,
                        ..default()
                    },
                    ..default()
                }),
        )
        // A frame that comes late moves the world on by at most a 15th of a second, as Unreal clamps its frame time: the
        // game slows through a hitch rather than jumping over it, the rider and the camera with it.
        .insert_resource(Time::<Virtual>::from_max_delta(std::time::Duration::from_secs_f64(1.0 / 15.0)))
        .add_plugins((
            ScreensPlugin,
            SettingsPlugin,
            MenuPlugin,
            WorldPlugin,
            RenderingPlugin,
            CharactersPlugin,
            GliderPlugin,
            PlayerPlugin,
            SkatePlugin,
            DevPlugin,
            ViewerPlugin,
            SoundsPlugin,
            PacingPlugin,
            GamepadPlugin,
        ))
        .run();
}

/// Where the assets are, from the folder beside the program: `assets`, but `../Resources/assets` in a macOS app,
/// which keeps its program in `Contents/MacOS` and everything else in `Contents/Resources`.
fn asset_folder() -> String {
    let program = std::env::current_exe().ok();
    let bundled = program.as_deref().and_then(|program| Some(program.parent()?.parent()?.join("Resources/assets")));
    if bundled.is_some_and(|folder| folder.is_dir()) { "../Resources/assets".into() } else { "assets".into() }
}
