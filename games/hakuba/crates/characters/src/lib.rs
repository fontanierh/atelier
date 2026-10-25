//! The playable characters. For now Nox stands at the origin in his rest pose.

use bevy::prelude::*;

pub struct CharactersPlugin;

impl Plugin for CharactersPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, spawn_nox);
    }
}

fn spawn_nox(mut commands: Commands, assets: Res<AssetServer>) {
    commands.spawn((
        Name::new("Nox"),
        WorldAssetRoot(assets.load(GltfAssetLabel::Scene(0).from_asset("characters/nox/nox.glb"))),
    ));
}
