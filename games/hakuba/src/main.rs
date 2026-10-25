//! The game program, what runs when the game opens: it builds the app, adds every feature's plugin and opens on the
//! menu (crates/menu).

use bevy::asset::AssetMetaCheck;
use bevy::prelude::*;
use hakuba_characters::CharactersPlugin;
use hakuba_menu::MenuPlugin;
use hakuba_screens::ScreensPlugin;
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
                .set(AssetPlugin {
                    meta_check: AssetMetaCheck::Never,
                    ..default()
                }),
        )
        .add_plugins((ScreensPlugin, MenuPlugin, WorldPlugin, CharactersPlugin, ViewerPlugin))
        .run();
}
