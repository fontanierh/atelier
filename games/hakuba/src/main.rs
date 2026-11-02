//! The game program, what runs when the game opens: it builds the app, adds every feature's plugin and opens on the
//! menu (crates/menu).

use bevy::asset::AssetMetaCheck;
use bevy::gltf::GltfPlugin;
use bevy::image::{ImageFilterMode, ImageSamplerDescriptor};
use bevy::prelude::*;
use hakuba_audio::SoundsPlugin;
use hakuba_characters::CharactersPlugin;
use hakuba_dev::DevPlugin;
use hakuba_glider::GliderPlugin;
use hakuba_menu::MenuPlugin;
use hakuba_player::PlayerPlugin;
use hakuba_rendering::RenderingPlugin;
use hakuba_screens::ScreensPlugin;
use hakuba_settings::SettingsPlugin;
use hakuba_skate::SkatePlugin;
use hakuba_viewer::ViewerPlugin;
use hakuba_world::WorldPlugin;

#[cfg(target_os = "macos")]
mod dualsense;
#[cfg(not(target_arch = "wasm32"))]
mod playtest;

fn main() {
    let mut app = App::new();
    // Playtest: a command on an entity that is already gone warns instead of closing the game.
    app.set_error_handler(bevy::ecs::error::warn);
    app
        .add_plugins(
            DefaultPlugins
                .set(WindowPlugin {
                    primary_window: Some(Window {
                        title: "Hakuba".into(),
                        // In the browser the game draws into index.html's canvas and fills the page.
                        canvas: Some("#hakuba".into()),
                        fit_canvas_to_parent: true,
                        // Playtest: HAKUBA_PRESENT=immediate|mailbox|fifo, HAKUBA_LATENCY=1|2.
                        present_mode: match std::env::var("HAKUBA_PRESENT").as_deref() {
                            Ok("immediate") => bevy::window::PresentMode::Immediate,
                            Ok("mailbox") => bevy::window::PresentMode::Mailbox,
                            Ok("fifo") => bevy::window::PresentMode::Fifo,
                            _ => bevy::window::PresentMode::AutoVsync,
                        },
                        desired_maximum_frame_latency: std::env::var("HAKUBA_LATENCY")
                            .ok()
                            .and_then(|v| v.parse().ok())
                            .and_then(std::num::NonZeroU32::new),
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
        ));
    #[cfg(target_os = "macos")]
    app.add_plugins(dualsense::DualSensePlugin);
    #[cfg(not(target_arch = "wasm32"))]
    app.add_plugins(playtest::PlaytestPlugin);
    app.run();
}

/// Where the assets are, from the folder beside the program: `assets`, but `../Resources/assets` in a macOS app,
/// which keeps its program in `Contents/MacOS` and everything else in `Contents/Resources`.
fn asset_folder() -> String {
    let program = std::env::current_exe().ok();
    let bundled = program.as_deref().and_then(|program| Some(program.parent()?.parent()?.join("Resources/assets")));
    if bundled.is_some_and(|folder| folder.is_dir()) { "../Resources/assets".into() } else { "assets".into() }
}
