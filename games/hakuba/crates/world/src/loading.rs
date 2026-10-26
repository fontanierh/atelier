//! A curtain over the world until it has loaded: the index, every tile in sight and every model standing in them, with
//! their textures, so the world shows whole rather than filling in. What other crates add to the world holds the
//! curtain too while it is [`Unready`], such as the player until their character stands on the ground.

use bevy::asset::{RecursiveDependencyLoadState, UntypedAssetId};
use bevy::prelude::*;
use bevy::world_serialization::WorldAssetRoot;
use hakuba_screens::{Screen, text};

use crate::scenery::{Placed, Placing, Waiting};
use crate::tiles::{Spawning, Tile};

pub struct LoadingPlugin;

impl Plugin for LoadingPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(Screen::World), spawn).add_systems(
            Update,
            lift.after(Placing).run_if(in_state(Screen::World)).run_if(any_with_component::<Curtain>),
        );
    }
}

#[derive(Component)]
struct Curtain;

/// Holds the curtain down while any entity has it. The world draws under the curtain, so what is spawned meanwhile
/// has its models loaded and its shaders compiled before the player sees it.
#[derive(Component)]
pub struct Unready;

fn spawn(mut commands: Commands) {
    commands.spawn((
        Curtain,
        DespawnOnExit(Screen::World),
        Node {
            position_type: PositionType::Absolute,
            width: percent(100),
            height: percent(100),
            align_items: AlignItems::Center,
            justify_content: JustifyContent::Center,
            ..default()
        },
        BackgroundColor(Color::srgb(0.07, 0.07, 0.09)),
        GlobalZIndex(i32::MAX - 1),
        children![text("Loading the world…", 20.0)],
    ));
}

/// Lifts the curtain once every tile shows the version it needs, every model in them has spawned and nothing else is
/// [`Unready`].
#[allow(clippy::too_many_arguments)]
fn lift(
    mut commands: Commands,
    assets: Res<AssetServer>,
    curtain: Single<Entity, With<Curtain>>,
    tiles: Query<&Tile>,
    spawning: Query<(), With<Spawning>>,
    waiting: Query<(), With<Waiting>>,
    roots: Query<&WorldAssetRoot>,
    placed: Query<&Placed>,
    unready: Query<(), With<Unready>>,
) {
    let loaded = |id: UntypedAssetId| {
        matches!(
            assets.recursive_dependency_load_state(id),
            RecursiveDependencyLoadState::Loaded | RecursiveDependencyLoadState::Failed(_)
        )
    };
    let ready = unready.is_empty()
        && !tiles.is_empty()
        && tiles.iter().all(Tile::shown)
        && spawning.is_empty()
        && waiting.is_empty()
        && roots.iter().all(|root| loaded(root.0.id().untyped()))
        && placed.iter().all(|placed| loaded(placed.0.id().untyped()));
    if ready {
        commands.entity(*curtain).despawn();
    }
}
