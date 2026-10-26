//! The game program, what runs when the game opens: it builds the app, adds every feature's plugin and opens on the
//! menu (crates/menu).

use bevy::asset::AssetMetaCheck;
use bevy::gltf::GltfPlugin;
use bevy::image::{ImageFilterMode, ImageSamplerDescriptor};
use bevy::prelude::*;
use bevy::winit::{UpdateMode, WinitSettings};
use hakuba_characters::CharactersPlugin;
use hakuba_menu::MenuPlugin;
use hakuba_screens::ScreensPlugin;
use hakuba_viewer::ViewerPlugin;
use hakuba_world::WorldPlugin;
use std::time::Duration;

/// The most frames the game draws a second.
const MAX_FPS: f64 = 60.0;

fn main() {
    App::new()
        .add_plugins(
            DefaultPlugins
                .set(WindowPlugin {
                    primary_window: Some(Window {
                        title: "Hakuba".into(),
                        // In the browser the game draws into index.html's canvas and fills the page.
                        canvas: Some("#hakuba".into()),
                        fit_canvas_to_parent: true,
                        ..default()
                    }),
                    ..default()
                })
                // Load assets without looking for a .meta file next to each: in the browser, the server answers a
                // missing file with index.html, which Bevy cannot read.
                .set(AssetPlugin { meta_check: AssetMetaCheck::Never, ..default() })
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
        // The game draws at most MAX_FPS frames a second, even on faster screens, and only that many while in the
        // background. Input waits for the next frame rather than drawing one of its own.
        .insert_resource(WinitSettings { focused_mode: capped(), unfocused_mode: capped() })
        .add_plugins((ScreensPlugin, MenuPlugin, WorldPlugin, CharactersPlugin, ViewerPlugin))
        .run();
}

/// Updating once every 1 / MAX_FPS seconds, and on nothing else.
fn capped() -> UpdateMode {
    UpdateMode::Reactive {
        wait: Duration::from_secs_f64(1.0 / MAX_FPS),
        react_to_device_events: false,
        react_to_user_events: false,
        react_to_window_events: false,
    }
}
