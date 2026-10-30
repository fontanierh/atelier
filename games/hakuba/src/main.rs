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
use hakuba_viewer::ViewerPlugin;
use hakuba_world::WorldPlugin;

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
        .add_plugins((
            ScreensPlugin,
            SettingsPlugin,
            MenuPlugin,
            WorldPlugin,
            RenderingPlugin,
            CharactersPlugin,
            GliderPlugin,
            PlayerPlugin,
            DevPlugin,
            ViewerPlugin,
            SoundsPlugin,
        ))
        .run();
}
