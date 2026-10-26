//! The playable characters. An entity given a [`Character`] gets that character's model and plays its idle in a loop;
//! [`Clips`] then lists every clip the model has and how fast each carries it, [`Play`] switches to one, fading from
//! the last, and [`Playing`] says which is playing and whether it has finished. The model's right hand holds what the
//! character carries at its [`Grip`]; [`Hands`] finds both hands, for what it holds in two.

use std::time::Duration;

use bevy::gltf::{Gltf, GltfExtras};
use bevy::platform::collections::HashMap;
use bevy::prelude::*;
use bevy::world_serialization::WorldInstanceReady;
use serde::Deserialize;

pub struct CharactersPlugin;

impl Plugin for CharactersPlugin {
    fn build(&self, app: &mut App) {
        app.add_observer(load_model)
            .add_observer(start_animating)
            .add_observer(play)
            .add_systems(Update, (spawn_models, follow_playing));
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

/// The model's node whose extras give how fast each clip carries the character over the ground.
const CLIPS_NODE: &str = "clips";

/// The model's node in the right hand's palm, where it holds things.
const GRIP_NODE: &str = "grip_r";

/// The model's hand bones.
const HAND_NODES: [&str; 2] = ["hand_l", "hand_r"];

/// Every clip a character's model has, by name in alphabetical order, and how fast each carries it over the ground.
/// Added once the model has loaded.
#[derive(Component)]
pub struct Clips {
    graph: Handle<AnimationGraph>,
    clips: Vec<(String, AnimationNodeIndex)>,
    /// In metres a second, by clip; clips that stay in place are left out.
    speeds: HashMap<String, f32>,
    /// How high the hips stand at rest, in metres, once the model has spawned.
    pub hips_m: f32,
    /// The model's animation player, once the model has spawned.
    player: Option<Entity>,
}

impl Clips {
    pub fn names(&self) -> impl Iterator<Item = &str> {
        self.clips.iter().map(|(name, _)| name.as_str())
    }

    /// How fast the clip `name` carries the character over the ground when it plays at its own speed, in metres a
    /// second: 0 for a clip that stays in place.
    pub fn speed(&self, name: &str) -> f32 {
        self.speeds.get(name).copied().unwrap_or(0.0)
    }

    fn get(&self, name: &str) -> Option<AnimationNodeIndex> {
        self.clips.iter().find(|(clip, _)| clip == name).map(|(_, index)| *index)
    }
}

/// Makes a character play one of its clips, fading from what it played over `fade`. Playing the clip already playing
/// changes only its speed, unless it has finished, when it starts again.
#[derive(EntityEvent)]
pub struct Play {
    pub entity: Entity,
    pub clip: String,
    /// Whether it plays in a loop, or once and then holds its last pose.
    pub repeat: bool,
    /// How fast it plays, as a share of its own speed.
    pub speed: f32,
    pub fade: Duration,
}

impl Play {
    /// `clip` in a loop, at its own speed, with no fade.
    pub fn looping(entity: Entity, clip: impl Into<String>) -> Self {
        Self { entity, clip: clip.into(), repeat: true, speed: 1.0, fade: Duration::ZERO }
    }

    /// `clip` once, at its own speed, with no fade.
    pub fn once(entity: Entity, clip: impl Into<String>) -> Self {
        Self { repeat: false, ..Self::looping(entity, clip) }
    }

    pub fn fading(self, seconds: f32) -> Self {
        Self { fade: Duration::from_secs_f32(seconds), ..self }
    }

    pub fn at_speed(self, speed: f32) -> Self {
        Self { speed, ..self }
    }
}

/// The clip a character plays, how far into it, in seconds of the clip, and whether it has finished.
#[derive(Component, Default)]
pub struct Playing {
    pub clip: String,
    pub time: f32,
    pub finished: bool,
}

/// The node in a character's right palm where it holds things, such as the paraglider: what it holds is a child of
/// this entity, placed as the holder in the motion library placed it.
#[derive(Component)]
pub struct Grip {
    /// The character it belongs to.
    pub character: Entity,
}

/// A character's left and right hand bones, added once its model has spawned.
#[derive(Component)]
pub struct Hands {
    pub left: Entity,
    pub right: Entity,
}

/// A character whose model is loading.
#[derive(Component)]
struct Loading(Handle<Gltf>);

/// The extras of a model's `clips` node.
#[derive(Deserialize)]
struct ClipExtras {
    speeds: HashMap<String, f32>,
    hips_m: f32,
}

fn load_model(
    add: On<Add<Character>>,
    characters: Query<&Character>,
    assets: Res<AssetServer>,
    mut commands: Commands,
) {
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
            Clips { graph: graphs.add(graph), clips, speeds: HashMap::default(), hips_m: 0.0, player: None },
            Playing::default(),
            WorldAssetRoot(gltf.scenes[0].clone()),
        ));
    }
}

/// Once the model has spawned: finds its animation player, reads its clips' speeds and its hips' height, marks its grip,
/// finds its hands and plays the idle.
fn start_animating(
    ready: On<WorldInstanceReady>,
    mut commands: Commands,
    mut characters: Query<&mut Clips>,
    children: Query<&Children>,
    players: Query<(), With<AnimationPlayer>>,
    names: Query<(&Name, Option<&GltfExtras>)>,
) {
    let Ok(mut clips) = characters.get_mut(ready.entity) else { return };
    let mut hands = [None; 2];
    for node in children.iter_descendants(ready.entity) {
        let Ok((name, extras)) = names.get(node) else { continue };
        match name.as_str() {
            CLIPS_NODE => {
                let read = extras.and_then(|extras| serde_json::from_str::<ClipExtras>(&extras.value).ok());
                let read = read.expect("a character's clips node gives their speeds and its hips' height");
                (clips.speeds, clips.hips_m) = (read.speeds, read.hips_m);
            }
            GRIP_NODE => {
                commands.entity(node).insert(Grip { character: ready.entity });
            }
            name => {
                if let Some(side) = HAND_NODES.iter().position(|hand| *hand == name) {
                    hands[side] = Some(node);
                }
            }
        }
    }
    if let [Some(left), Some(right)] = hands {
        commands.entity(ready.entity).insert(Hands { left, right });
    }
    let Some(player) = children.iter_descendants(ready.entity).find(|child| players.contains(*child)) else { return };
    clips.player = Some(player);
    commands.entity(player).insert((AnimationGraphHandle(clips.graph.clone()), AnimationTransitions::new()));
    commands.trigger(Play::looping(ready.entity, FIRST_CLIP));
}

fn play(
    play: On<Play>,
    mut characters: Query<(&Clips, &mut Playing)>,
    mut players: Query<(&mut AnimationPlayer, &mut AnimationTransitions)>,
) {
    let Ok((clips, mut playing)) = characters.get_mut(play.entity) else { return };
    let (Some(player), Some(clip)) = (clips.player, clips.get(&play.clip)) else { return };
    let Ok((mut player, mut transitions)) = players.get_mut(player) else { return };
    if playing.clip == play.clip
        && !playing.finished
        && let Some(active) = player.animation_mut(clip)
    {
        active.set_speed(play.speed);
        return;
    }
    let active = transitions.play(&mut player, clip, play.fade);
    active.set_speed(play.speed);
    if play.repeat {
        active.repeat();
    }
    *playing = Playing { clip: play.clip.clone(), time: 0.0, finished: false };
}

/// Keeps each character's [`Playing`] up to date with its animation player.
fn follow_playing(mut characters: Query<(&Clips, &mut Playing)>, players: Query<&AnimationPlayer>) {
    for (clips, mut playing) in &mut characters {
        let (Some(player), Some(clip)) = (clips.player, clips.get(&playing.clip)) else { continue };
        let Some(active) = players.get(player).ok().and_then(|player| player.animation(clip)) else { continue };
        playing.time = active.seek_time();
        playing.finished = active.is_finished();
    }
}
