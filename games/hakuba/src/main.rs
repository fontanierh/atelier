use bevy::prelude::*;
use hakuba_world::WorldPlugin;

fn main() {
    App::new()
        .add_plugins(DefaultPlugins.set(WindowPlugin {
            primary_window: Some(Window {
                title: "Hakuba".into(),
                // In the browser the game draws into index.html's canvas and fills the page.
                canvas: Some("#hakuba".into()),
                fit_canvas_to_parent: true,
                ..default()
            }),
            ..default()
        }))
        .add_plugins(WorldPlugin)
        .run();
}
