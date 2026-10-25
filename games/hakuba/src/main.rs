use bevy::asset::AssetMetaCheck;
use bevy::prelude::*;
use hakuba_characters::CharactersPlugin;
use hakuba_inspect::InspectPlugin;
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
                // Bevy would ask for a .meta file next to each asset. There are none, and in the browser the server
                // answers a missing file with index.html, which Bevy cannot read.
                .set(AssetPlugin {
                    meta_check: AssetMetaCheck::Never,
                    ..default()
                }),
        )
        .add_plugins((WorldPlugin, CharactersPlugin, InspectPlugin))
        .run();
}
