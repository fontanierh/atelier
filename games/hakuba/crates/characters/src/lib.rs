//! The playable characters: Nox stands at the origin, playing his idle in a loop.

use bevy::{prelude::*, world_serialization::WorldInstanceReady};

pub struct CharactersPlugin;

impl Plugin for CharactersPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, spawn_nox);
    }
}

const NOX: &str = "characters/nox/nox.glb";

/// The animation a character plays once its model has spawned.
#[derive(Component)]
struct Idle {
    graph: Handle<AnimationGraph>,
    clip: AnimationNodeIndex,
}

fn spawn_nox(mut commands: Commands, assets: Res<AssetServer>, mut graphs: ResMut<Assets<AnimationGraph>>) {
    // The idle is the model's only animation.
    let (graph, clip) = AnimationGraph::from_clip(assets.load(GltfAssetLabel::Animation(0).from_asset(NOX)));
    commands
        .spawn((
            Name::new("Nox"),
            Idle { graph: graphs.add(graph), clip },
            WorldAssetRoot(assets.load(GltfAssetLabel::Scene(0).from_asset(NOX))),
        ))
        .observe(play_idle);
}

fn play_idle(
    ready: On<WorldInstanceReady>,
    mut commands: Commands,
    idles: Query<&Idle>,
    children: Query<&Children>,
    mut players: Query<&mut AnimationPlayer>,
) {
    let Ok(idle) = idles.get(ready.entity) else { return };
    for child in children.iter_descendants(ready.entity) {
        if let Ok(mut player) = players.get_mut(child) {
            player.play(idle.clip).repeat();
            commands.entity(child).insert(AnimationGraphHandle(idle.graph.clone()));
        }
    }
}
