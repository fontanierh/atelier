//! The playable characters. An entity given a [`Character`] gets that character's model and plays its idle in a loop;
//! [`Clips`] then lists every clip the model has, and [`Play`] switches to one.

use bevy::gltf::Gltf;
use bevy::prelude::*;
use bevy::world_serialization::WorldInstanceReady;

pub struct CharactersPlugin;

impl Plugin for CharactersPlugin {
    fn build(&self, app: &mut App) {
        app.add_observer(load_model)
            .add_observer(start_animating)
            .add_observer(play)
            .add_systems(Update, spawn_models);
    }
}

/// Every playable character.
#[derive(Component, Clone, Copy, PartialEq, Eq, Debug)]
pub enum Character {
    Nox,
}

impl Character {
    pub const ALL: [Character; 1] = [Character::Nox];

    pub fn name(self) -> &'static str {
        match self {
            Character::Nox => "Nox",
        }
    }

    /// The exported model, with every clip the character has.
    fn model(self) -> &'static str {
        match self {
            Character::Nox => "characters/nox/nox.glb",
        }
    }
}

/// The clip a character plays when it appears.
const FIRST_CLIP: &str = "idle";

/// Every clip a character's model has, by name in alphabetical order. Added once the model has loaded.
#[derive(Component)]
pub struct Clips {
    graph: Handle<AnimationGraph>,
    clips: Vec<(String, AnimationNodeIndex)>,
    /// The model's animation player, once the model has spawned.
    player: Option<Entity>,
}

impl Clips {
    pub fn names(&self) -> impl Iterator<Item = &str> {
        self.clips.iter().map(|(name, _)| name.as_str())
    }

    fn get(&self, name: &str) -> Option<AnimationNodeIndex> {
        self.clips.iter().find(|(clip, _)| clip == name).map(|(_, index)| *index)
    }
}

/// Makes a character play one of its clips in a loop.
#[derive(EntityEvent)]
pub struct Play {
    pub entity: Entity,
    pub clip: String,
}

/// A character whose model is loading.
#[derive(Component)]
struct Loading(Handle<Gltf>);

fn load_model(add: On<Add<Character>>, characters: Query<&Character>, assets: Res<AssetServer>, mut commands: Commands) {
    let character = characters.get(add.entity).expect("the character was just added");
    commands.entity(add.entity).insert(Loading(assets.load(character.model())));
}

fn spawn_models(
    mut commands: Commands,
    loading: Query<(Entity, &Loading)>,
    gltfs: Res<Assets<Gltf>>,
    mut graphs: ResMut<Assets<AnimationGraph>>,
) {
    for (entity, Loading(model)) in &loading {
        let Some(gltf) = gltfs.get(model) else { continue };
        let mut named: Vec<_> = gltf.named_animations.iter().collect();
        named.sort_by_key(|(name, _)| name.to_string());
        let (graph, indices) = AnimationGraph::from_clips(named.iter().map(|(_, clip)| (*clip).clone()));
        let clips = named.iter().zip(indices).map(|((name, _), index)| (name.to_string(), index)).collect();
        commands.entity(entity).remove::<Loading>().insert((
            Clips { graph: graphs.add(graph), clips, player: None },
            WorldAssetRoot(gltf.scenes[0].clone()),
        ));
    }
}

fn start_animating(
    ready: On<WorldInstanceReady>,
    mut commands: Commands,
    mut characters: Query<&mut Clips>,
    children: Query<&Children>,
    players: Query<(), With<AnimationPlayer>>,
) {
    let Ok(mut clips) = characters.get_mut(ready.entity) else { return };
    let Some(player) = children.iter_descendants(ready.entity).find(|child| players.contains(*child)) else { return };
    clips.player = Some(player);
    commands.entity(player).insert(AnimationGraphHandle(clips.graph.clone()));
    commands.trigger(Play { entity: ready.entity, clip: FIRST_CLIP.into() });
}

fn play(play: On<Play>, characters: Query<&Clips>, mut players: Query<&mut AnimationPlayer>) {
    let Ok(clips) = characters.get(play.entity) else { return };
    let (Some(player), Some(clip)) = (clips.player, clips.get(&play.clip)) else { return };
    if let Ok(mut player) = players.get_mut(player) {
        player.stop_all().play(clip).repeat();
    }
}
