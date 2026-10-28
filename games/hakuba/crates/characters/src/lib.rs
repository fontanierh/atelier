//! The playable characters. An entity given a [`Character`] gets that character's model and plays its idle in a loop;
//! [`Clips`] then lists every clip the model has and how fast each carries it, [`Play`] switches to one, fading from
//! the last, and [`Playing`] says which is playing and whether it has finished. The model's right hand holds what the
//! character carries at its [`Grip`]; [`Hands`] finds both arms' bones, for what it holds in two hands.

mod attachment;
mod emission;

pub use attachment::AttachmentPose;
pub use emission::{DyeReady, DyeTint, MaterialFailed, MaterialReady};

use std::time::Duration;

use bevy::gltf::{Gltf, GltfExtras};
use bevy::platform::collections::HashMap;
use bevy::prelude::*;
use bevy::world_serialization::WorldInstanceReady;
use serde::Deserialize;

pub struct CharactersPlugin;

impl Plugin for CharactersPlugin {
    fn build(&self, app: &mut App) {
        app.add_plugins(emission::EmissionPlugin)
            .add_observer(load_model)
            .add_observer(load_source)
            .add_observer(start_animating)
            .add_observer(play)
            .add_observer(blend)
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

/// The sides of the model's bones, left then right, as their names end.
const SIDES: [&str; 2] = ["l", "r"];

/// The model's fingers but the thumb, each three bones named `<finger>_1` to `<finger>_3` from the knuckle out.
const FINGERS: [&str; 4] = ["index", "middle", "ring", "pinky"];

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
    /// Whether the scene's animation player is ready to accept clip requests.
    pub fn is_ready(&self) -> bool {
        self.player.is_some()
    }

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
    /// Starting position in the clip, in seconds.
    pub phase_s: f32,
}

impl Play {
    /// `clip` in a loop, at its own speed, with no fade.
    pub fn looping(entity: Entity, clip: impl Into<String>) -> Self {
        Self { entity, clip: clip.into(), repeat: true, speed: 1.0, fade: Duration::ZERO, phase_s: 0.0 }
    }

    /// `clip` once, at its own speed, with no fade.
    pub fn once(entity: Entity, clip: impl Into<String>) -> Self {
        Self { repeat: false, ..Self::looping(entity, clip) }
    }

    pub fn fading(self, seconds: f32) -> Self {
        Self { fade: Duration::from_secs_f32(seconds), ..self }
    }

    pub fn at_phase(self, phase_s: f32) -> Self {
        Self { phase_s, ..self }
    }

    pub fn at_speed(self, speed: f32) -> Self {
        Self { speed, ..self }
    }
}

/// Plays two looping clips together at the given share of the second clip.
#[derive(EntityEvent)]
pub struct Blend {
    pub entity: Entity,
    pub first: String,
    pub second: String,
    pub amount: f32,
}

/// The clip a character plays, how far into it, in seconds of the clip, and whether it has finished.
#[derive(Component, Default)]
pub struct Playing {
    pub clip: String,
    pub time: f32,
    pub finished: bool,
}

/// The node in a character's right palm where it holds things in one hand: what it holds is a child of
/// this entity, placed as the holder in the motion library placed it.
#[derive(Component)]
pub struct Grip {
    /// The character it belongs to.
    pub character: Entity,
}

/// A character's arms, left then right, added once its model has spawned, for what it holds in both hands.
#[derive(Component)]
pub struct Hands {
    pub arms: [Arm; 2],
}

/// One arm's bones, from the shoulder to the fingers.
#[derive(Clone, Copy)]
pub struct Arm {
    /// The upper arm's bone, at the shoulder.
    pub upper_arm: Entity,
    /// The forearm's, at the elbow.
    pub forearm: Entity,
    /// The hand's, at the wrist.
    pub hand: Entity,
    /// Each finger's three bones from the knuckle out, the index, middle, ring and little fingers'.
    pub fingers: [[Entity; 3]; 4],
}

/// A model with the character export's clips, supplied by path for world actors.
#[derive(Component)]
pub struct Model(pub String);

/// A character whose model is loading.
#[derive(Component)]
struct Loading(Handle<Gltf>);

/// The extras of a model's `clips` node.
#[derive(Deserialize)]
struct ClipExtras {
    speeds: HashMap<String, f32>,
    hips_m: f32,
}

fn load_model(add: On<Add<Character>>, characters: Query<&Character>, mut commands: Commands) {
    let character = characters.get(add.entity).expect("the character was just added");
    commands.entity(add.entity).insert(Model(character.model().into()));
}

fn load_source(add: On<Add<Model>>, models: Query<&Model>, assets: Res<AssetServer>, mut commands: Commands) {
    let model = models.get(add.entity).expect("the model was just added");
    commands.entity(add.entity).insert(Loading(assets.load(model.0.clone())));
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

/// Once the model has spawned: finds its animation player, reads its clips' speeds and its hips' height, marks its
/// grip, finds its hands and plays the idle.
fn start_animating(
    ready: On<WorldInstanceReady>,
    mut commands: Commands,
    mut characters: Query<&mut Clips>,
    children: Query<&Children>,
    players: Query<(), With<AnimationPlayer>>,
    names: Query<(&Name, Option<&GltfExtras>)>,
) {
    let Ok(mut clips) = characters.get_mut(ready.entity) else { return };
    let mut bones: HashMap<String, Entity> = HashMap::default();
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
                bones.insert(name.to_string(), node);
            }
        }
    }
    let arm = |side: &str| -> Option<Arm> {
        let bone = |part: &str| bones.get(&format!("{part}_{side}")).copied();
        let finger = |finger: &str| {
            Some([bone(&format!("{finger}_1"))?, bone(&format!("{finger}_2"))?, bone(&format!("{finger}_3"))?])
        };
        let [index, middle, ring, pinky] = FINGERS.map(finger);
        Some(Arm {
            upper_arm: bone("upper_arm")?,
            forearm: bone("forearm")?,
            hand: bone("hand")?,
            fingers: [index?, middle?, ring?, pinky?],
        })
    };
    if let [Some(left), Some(right)] = SIDES.map(arm) {
        commands.entity(ready.entity).insert(Hands { arms: [left, right] });
    }
    let Some(player) = children.iter_descendants(ready.entity).find(|child| players.contains(*child)) else { return };
    clips.player = Some(player);
    commands.entity(player).insert((AnimationGraphHandle(clips.graph.clone()), AnimationTransitions::new()));
    commands.trigger(Play::looping(ready.entity, FIRST_CLIP));
}

fn play(
    play: On<Play>,
    mut characters: Query<(&Clips, &mut Playing)>,
    mut players: Query<(&mut AnimationPlayer, Option<&mut AnimationTransitions>)>,
    mut commands: Commands,
) {
    let Ok((clips, mut playing)) = characters.get_mut(play.entity) else { return };
    let (Some(player), Some(clip)) = (clips.player, clips.get(&play.clip)) else { return };
    let Ok((mut player_state, transitions)) = players.get_mut(player) else { return };
    let Some(mut transitions) = transitions else {
        player_state.stop_all();
        let mut transitions = AnimationTransitions::new();
        let active = transitions.play(&mut player_state, clip, Duration::ZERO);
        active.set_speed(play.speed).set_seek_time(play.phase_s);
        if play.repeat {
            active.repeat();
        }
        commands.entity(player).insert(transitions);
        *playing = Playing { clip: play.clip.clone(), time: 0.0, finished: false };
        return;
    };
    if playing.clip == play.clip
        && !playing.finished
        && let Some(active) = player_state.animation_mut(clip)
    {
        active.set_speed(play.speed);
        if play.phase_s > 0.0 {
            active.set_seek_time(play.phase_s);
        }
        return;
    }
    let active = transitions.play(&mut player_state, clip, play.fade);
    active.set_speed(play.speed).set_seek_time(play.phase_s);
    if play.repeat {
        active.repeat();
    }
    *playing = Playing { clip: play.clip.clone(), time: 0.0, finished: false };
}

/// Uses the same graph and player as single-clip playback. A later Play returns it to single-clip playback.
fn blend(
    blend: On<Blend>,
    characters: Query<&Clips>,
    mut players: Query<&mut AnimationPlayer>,
    mut commands: Commands,
) {
    let Ok(clips) = characters.get(blend.entity) else { return };
    let (Some(player), Some(first), Some(second)) = (clips.player, clips.get(&blend.first), clips.get(&blend.second))
    else {
        return;
    };
    let Ok(mut player_state) = players.get_mut(player) else { return };
    commands.entity(player).remove::<AnimationTransitions>();
    let amount = blend.amount.clamp(0.0, 1.0);
    player_state.play(first).repeat().set_weight(1.0 - amount);
    player_state.play(second).repeat().set_weight(amount);
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn blend_weights_clips_and_play_returns_to_single_animation() {
        let mut app = App::new();
        app.add_observer(blend).add_observer(play);
        let mut graph = AnimationGraph::new();
        let idle = graph.add_clip(Handle::default(), 1.0, graph.root);
        let walk = graph.add_clip(Handle::default(), 1.0, graph.root);
        let player = app.world_mut().spawn((AnimationPlayer::default(), AnimationTransitions::new())).id();
        let character = app
            .world_mut()
            .spawn((
                Clips {
                    graph: Handle::default(),
                    clips: vec![("idle".into(), idle), ("walk".into(), walk)],
                    speeds: HashMap::default(),
                    hips_m: 1.0,
                    player: Some(player),
                },
                Playing::default(),
            ))
            .id();
        app.world_mut().trigger(Blend { entity: character, first: "idle".into(), second: "walk".into(), amount: 0.4 });
        app.world_mut().flush();
        let player_state = app.world().get::<AnimationPlayer>(player).unwrap();
        assert!((player_state.animation(idle).unwrap().weight() - 0.6).abs() < 1e-6);
        assert!((player_state.animation(walk).unwrap().weight() - 0.4).abs() < 1e-6);
        assert!(app.world().get::<AnimationTransitions>(player).is_none());
        app.world_mut().trigger(Play::looping(character, "idle"));
        app.world_mut().flush();
        let player_state = app.world().get::<AnimationPlayer>(player).unwrap();
        assert!(player_state.animation(idle).is_some());
        assert!(player_state.animation(walk).is_none());
        assert!(app.world().get::<AnimationTransitions>(player).is_some());
    }
}
