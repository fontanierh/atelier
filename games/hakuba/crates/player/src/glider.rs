//! The paraglider: held in both hands above the character while the player glides, its cloth rippling in a loop, and
//! put away as it lands. It sits on the body between the fists, scaled to the character's size, and banks into turns;
//! each fist closes round its handle (`grip.rs`). Each player has one from the start, drawn too small to see while it
//! is put away, so its shaders are ready the first time it opens.

use bevy::app::AnimationSystems;
use bevy::gltf::{Gltf, GltfExtras};
use bevy::prelude::*;
use bevy::transform::TransformSystems;
use bevy::world_serialization::WorldInstanceReady;
use hakuba_characters::{Clips, Hands, Playing};
use serde::Deserialize;

use crate::Player;
use crate::grip::{self, Nodes, in_body};
use crate::moves::{Action, Mode};

/// The exported paraglider, and its clip.
const MODEL: &str = "equipment/glider/glider.glb";
const CLIP: &str = "glider";

/// The model's node whose extras give how high the hips of the skeleton that held it stand, and its handles.
const HOLDER_NODE: &str = "holder";

/// How far into putting it away the paraglider goes, in seconds of the clip.
const PUT_AWAY_S: f32 = 0.1;

/// How far it banks for each radian a second the glide turns, at most `MOST_BANK_DEG`, and how fast it gets there.
const BANK_PER_TURN: f32 = 0.12;
const MOST_BANK_DEG: f32 = 12.0;
const BANK_RATE: f32 = 5.0;

/// How fast the fists close round the handles as it opens, and let go as it is put away: a share of the way a second.
const GRIP_RATE: f32 = 8.0;

/// Its scale while put away: too small to see, yet drawn.
const AWAY_SCALE: f32 = 1e-3;

pub struct GliderPlugin;

impl Plugin for GliderPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, load)
            .add_systems(Update, (spawn, spawn_model))
            .add_systems(PostUpdate, hold.after(AnimationSystems).before(TransformSystems::Propagate))
            .add_observer(ripple);
    }
}

#[derive(Resource)]
struct Model(Handle<Gltf>);

/// A character's paraglider, a child of its body.
#[derive(Component)]
pub(crate) struct Glider {
    character: Entity,
    /// How the skeleton that held it held it: `None` until its model has spawned.
    holder: Option<HolderExtras>,
    /// How far it leans into the turn, in radians.
    bank: f32,
    /// How closed the fists are round the handles, from 0 (as the clip has them) to 1.
    grip: f32,
}

impl Glider {
    pub(crate) fn of(&self, character: Entity) -> bool {
        self.character == character && self.holder.is_some()
    }
}

/// A paraglider waiting for its model to load.
#[derive(Component)]
struct Waiting;

/// The extras of the model's `holder` node: how high the hips of the skeleton that held it stand, its handles in its
/// own frame, left then right, each from its back end to its front end, and their tube's radius, all in metres.
#[derive(Deserialize)]
struct HolderExtras {
    hips_m: f32,
    handles: [[[f32; 3]; 2]; 2],
    handle_radius_m: f32,
}

fn load(mut commands: Commands, assets: Res<AssetServer>) {
    commands.insert_resource(Model(assets.load(MODEL)));
}

/// Gives each player's character its paraglider, put away.
fn spawn(mut commands: Commands, players: Query<&Player, Added<Player>>) {
    for player in &players {
        commands.entity(player.body).with_child((
            Name::new("Glider"),
            Glider { character: player.body, holder: None, bank: 0.0, grip: 0.0 },
            Waiting,
            Transform::from_scale(Vec3::splat(AWAY_SCALE)),
        ));
    }
}

fn spawn_model(
    mut commands: Commands,
    model: Res<Model>,
    gltfs: Res<Assets<Gltf>>,
    waiting: Query<Entity, With<Waiting>>,
) {
    let Some(gltf) = gltfs.get(&model.0) else { return };
    for glider in &waiting {
        commands.entity(glider).remove::<Waiting>().insert(WorldAssetRoot(gltf.scenes[0].clone()));
    }
}

/// Once the animation has posed the character, and before that pose is carried to the screen: shows the paraglider
/// between the fists while the player glides and as it starts putting it away, banking into turns, and closes each
/// fist round its handle; puts it away otherwise. Everything is placed in the body's frame from the pose of this
/// frame, so the paraglider and the hands on it move together.
fn hold(
    time: Res<Time>,
    players: Query<&Player>,
    bodies: Query<(&Clips, &Playing, &Hands)>,
    mut gliders: Query<(Entity, &mut Glider)>,
    mut nodes: Nodes,
) {
    for player in &players {
        let Some((entity, mut glider)) = gliders.iter_mut().find(|(_, glider)| glider.of(player.body)) else {
            continue;
        };
        let Ok((clips, playing, hands)) = bodies.get(player.body) else { continue };
        let motion = &player.motion;
        let held = motion.mode == Mode::Glide || (motion.action == Action::GlideClose && playing.time < PUT_AWAY_S);
        let most = MOST_BANK_DEG.to_radians();
        let bank = if held { (motion.glide_turn() * BANK_PER_TURN).clamp(-most, most) } else { 0.0 };
        let dt = time.delta_secs();
        glider.bank += (bank - glider.bank) * (BANK_RATE * dt).min(1.0);
        glider.grip = if held { (glider.grip + GRIP_RATE * dt).min(1.0) } else { 0.0 };
        let Some(holder) = &glider.holder else { continue };
        let size = clips.hips_m / holder.hips_m;

        // Halfway between the fists as the clip holds them, each where it closes on the bar: the middle of its wrist
        // and middle finger.
        let fists = hands.arms.map(|arm| arm.fist().map(|bone| in_body(bone, player.body, &nodes)));
        let Some(between) =
            fists.iter().flatten().map(|place| place.map(|place| Vec3::from(place.translation))).sum::<Option<Vec3>>()
        else {
            continue;
        };
        let placed = Transform {
            translation: between / 8.0,
            rotation: Quat::from_rotation_z(-glider.bank),
            scale: Vec3::splat(if held { size } else { AWAY_SCALE }),
        };
        let handles = holder.handles.map(|[from, to]| grip::Bar {
            from: placed.transform_point(Vec3::from(from)),
            to: placed.transform_point(Vec3::from(to)),
            radius: holder.handle_radius_m * size,
        });
        if let Ok((mut transform, _)) = nodes.get_mut(entity) {
            *transform = placed;
        }
        if held {
            for (arm, handle) in hands.arms.iter().zip(&handles) {
                grip::close(arm, player.body, handle, Vec3::Z, size, glider.grip, &mut nodes);
            }
        }
    }
}

/// Once a paraglider's model has spawned: reads its holder's size and handles and plays its cloth's ripple in a loop.
#[allow(clippy::too_many_arguments)]
fn ripple(
    ready: On<WorldInstanceReady>,
    mut commands: Commands,
    model: Res<Model>,
    gltfs: Res<Assets<Gltf>>,
    mut gliders: Query<&mut Glider>,
    children: Query<&Children>,
    names: Query<(&Name, &GltfExtras)>,
    mut players: Query<&mut AnimationPlayer>,
    mut graphs: ResMut<Assets<AnimationGraph>>,
) {
    let Ok(mut glider) = gliders.get_mut(ready.entity) else { return };
    let holder = children.iter_descendants(ready.entity).find_map(|node| {
        let (name, extras) = names.get(node).ok()?;
        (name.as_str() == HOLDER_NODE).then(|| serde_json::from_str::<HolderExtras>(&extras.value).ok()).flatten()
    });
    glider.holder = Some(holder.expect("the paraglider's holder node gives its hips' height and its handles"));
    let Some(clip) = gltfs.get(&model.0).and_then(|gltf| gltf.named_animations.get(CLIP)) else { return };
    let Some(node) = children.iter_descendants(ready.entity).find(|node| players.contains(*node)) else { return };
    let (graph, index) = AnimationGraph::from_clip(clip.clone());
    commands.entity(node).insert(AnimationGraphHandle(graphs.add(graph)));
    if let Ok(mut player) = players.get_mut(node) {
        player.play(index).repeat();
    }
}
