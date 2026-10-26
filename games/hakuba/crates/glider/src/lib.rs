//! The paraglider, and how a character holds it. A [`Glider`] spawned as a child of a character's model loads the
//! paraglider, its cloth rippling in a loop. While it is [`held`](Glider::held) it sits on the body over the wrists,
//! where the holder's were, scaled to the character's size, leaning as far as it is told to [bank](Glider::bank), and each hand holds its handle
//! exactly as the skeleton that held it in the motion library did (`grip.rs`). Put away, it is drawn too small to see,
//! so its shaders are ready the first time it opens.

mod grip;

use bevy::app::AnimationSystems;
use bevy::gltf::{Gltf, GltfExtras};
use bevy::prelude::*;
use bevy::transform::TransformSystems;
use bevy::world_serialization::WorldInstanceReady;
use hakuba_characters::{Clips, Hands};
use serde::Deserialize;

use crate::grip::{Handle as Bar, Nodes, Palm, in_body};

/// The exported paraglider, and its clip.
const MODEL: &str = "equipment/glider/glider.glb";
const CLIP: &str = "glider";

/// The model's node whose extras say how the skeleton that held it held it.
const HOLDER_NODE: &str = "holder";

/// How fast it leans into a turn: a share of the way a second.
const BANK_RATE: f32 = 5.0;

/// How fast the hands close on the handles as it opens: a share of the way a second.
const GRIP_RATE: f32 = 8.0;

/// Its scale while put away: too small to see, yet drawn.
const AWAY_SCALE: f32 = 1e-3;

/// How far a closed fist may miss what the holder did before the game says so: its cavity off the handle's axis and
/// its wrist off the holder's, in metres for a character the holder's size, and its palm turned off the holder's.
const MOST_CAVITY_OFF_M: f32 = 0.015;
const MOST_WRIST_OFF_M: f32 = 0.005;
const MOST_PALM_OFF_DEG: f32 = 3.0;

pub struct GliderPlugin;

impl Plugin for GliderPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, load)
            .add_systems(Update, spawn_model)
            .add_systems(PostUpdate, hold.after(AnimationSystems).before(TransformSystems::Propagate))
            .add_observer(ripple);
    }
}

/// A character's paraglider: spawn it as a child of the character's model with [`Glider::of`]. The character's
/// screen says whether it is held and how far it banks.
#[derive(Component)]
#[require(Name::new("Glider"), Transform::from_scale(Vec3::splat(AWAY_SCALE)), Visibility)]
pub struct Glider {
    character: Entity,
    /// Whether the character holds it open above it; it is put away otherwise.
    pub held: bool,
    /// How far it leans into the turn, in radians, its left side up for a positive bank. It eases there.
    pub bank: f32,
    /// How the skeleton that held it held it: `None` until its model has spawned.
    holder: Option<HolderExtras>,
    /// How far it leans now.
    leaning: f32,
    /// How closed the hands are on the handles, from 0 (as the clip has them) to 1.
    grip: f32,
    /// Whether each fist, left then right, missed its handle when last fully closed, so a miss is told once.
    missed: [bool; 2],
}

impl Glider {
    /// The paraglider of `character`, put away.
    pub fn of(character: Entity) -> Self {
        Self { character, held: false, bank: 0.0, holder: None, leaning: 0.0, grip: 0.0, missed: [false; 2] }
    }

    /// Whether this is `character`'s paraglider and its model has spawned.
    pub fn ready_for(&self, character: Entity) -> bool {
        self.character == character && self.holder.is_some()
    }
}

/// The extras of the model's `holder` node, in its own frame and in metres: how high the hips of the skeleton that held
/// it stand; its handles, left then right, each from its back end to its front end, and their tube's radius; and the
/// skeleton's palms as it held them, left then right.
#[derive(Deserialize)]
struct HolderExtras {
    hips_m: f32,
    handles: [[[f32; 3]; 2]; 2],
    handle_radius_m: f32,
    palms: [PalmExtras; 2],
}

/// A palm's frame (`pose::palm` in the exporter): its origin at the wrist, and its rotation `[x, y, z, w]`.
#[derive(Deserialize)]
struct PalmExtras {
    wrist_m: [f32; 3],
    rotation: [f32; 4],
}

#[derive(Resource)]
struct Model(Handle<Gltf>);

fn load(mut commands: Commands, assets: Res<AssetServer>) {
    commands.insert_resource(Model(assets.load(MODEL)));
}

fn spawn_model(
    mut commands: Commands,
    model: Res<Model>,
    gltfs: Res<Assets<Gltf>>,
    waiting: Query<Entity, (With<Glider>, Without<WorldAssetRoot>)>,
) {
    let Some(gltf) = gltfs.get(&model.0) else { return };
    for glider in &waiting {
        commands.entity(glider).insert(WorldAssetRoot(gltf.scenes[0].clone()));
    }
}

/// Once the animation has posed the character, and before that pose is carried to the screen: shows each held
/// paraglider over the wrists, leaning into the turn, and puts each hand on its handle as the holder's was; puts it
/// away otherwise. Everything is placed in the body's frame from this frame's pose, so the paraglider and the hands on
/// it move together.
fn hold(time: Res<Time>, bodies: Query<(&Clips, &Hands)>, mut gliders: Query<(Entity, &mut Glider)>, mut nodes: Nodes) {
    let dt = time.delta_secs();
    for (entity, mut glider) in &mut gliders {
        let target = if glider.held { glider.bank } else { 0.0 };
        glider.leaning += (target - glider.leaning) * (BANK_RATE * dt).min(1.0);
        glider.grip = if glider.held { (glider.grip + GRIP_RATE * dt).min(1.0) } else { 0.0 };
        let (character, held, grip, leaning) = (glider.character, glider.held, glider.grip, glider.leaning);
        let Some(holder) = &glider.holder else { continue };
        let Ok((clips, hands)) = bodies.get(character) else { continue };
        let size = clips.hips_m / holder.hips_m;

        // Laid over the wrists as the clip holds them: the line between the holder's wrists turned onto the line
        // between the character's, their middles together, then leaning about that middle into the turn.
        let Some([left, right]) = hands
            .arms
            .iter()
            .map(|arm| in_body(arm.hand, character, &nodes).map(|place| Vec3::from(place.translation)))
            .collect::<Option<Vec<_>>>()
            .and_then(|wrists| <[Vec3; 2]>::try_from(wrists).ok())
        else {
            continue;
        };
        let [held_left, held_right] = holder.palms.each_ref().map(|palm| Vec3::from(palm.wrist_m) * size);
        let onto = Quat::from_rotation_arc((held_left - held_right).normalize(), (left - right).normalize());
        let rotation = Quat::from_rotation_z(-leaning) * onto;
        let placed = Transform {
            translation: (left + right) * 0.5 - rotation * (held_left + held_right) * 0.5,
            rotation,
            scale: Vec3::splat(if held { size } else { AWAY_SCALE }),
        };
        if let Ok((mut transform, _)) = nodes.get_mut(entity) {
            *transform = placed;
        }
        if !held {
            continue;
        }
        let mut missed = [false; 2];
        for (side, arm) in hands.arms.iter().enumerate() {
            let [from, to] = holder.handles[side].map(|end| placed.transform_point(Vec3::from(end)));
            let handle = Bar { from, to, radius: holder.handle_radius_m * size };
            let palm = &holder.palms[side];
            let palm = Palm {
                wrist: placed.transform_point(Vec3::from(palm.wrist_m)),
                rotation: placed.rotation * Quat::from_array(palm.rotation).normalize(),
            };
            let Some(fit) = grip::close(arm, character, &handle, &palm, size, grip, &mut nodes) else { continue };
            if grip < 1.0 {
                continue;
            }
            missed[side] = fit.cavity_off_m > MOST_CAVITY_OFF_M * size
                || fit.wrist_off_m > MOST_WRIST_OFF_M * size
                || fit.palm_off_deg > MOST_PALM_OFF_DEG;
            if missed[side] && !glider.missed[side] {
                error!(
                    "the {} fist misses the paraglider's handle: its cavity {:.1} cm off the handle's axis, its wrist \
                     {:.1} cm and its palm {:.1}° off the holder's",
                    ["left", "right"][side],
                    fit.cavity_off_m * 100.0,
                    fit.wrist_off_m * 100.0,
                    fit.palm_off_deg,
                );
            }
        }
        if grip >= 1.0 {
            glider.missed = missed;
        }
    }
}

/// Once a paraglider's model has spawned: reads how its holder held it and plays its cloth's ripple in a loop.
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
    glider.holder = Some(holder.expect("the paraglider's holder node gives its hips' height, handles and palms"));
    let Some(clip) = gltfs.get(&model.0).and_then(|gltf| gltf.named_animations.get(CLIP)) else { return };
    let Some(node) = children.iter_descendants(ready.entity).find(|node| players.contains(*node)) else { return };
    let (graph, index) = AnimationGraph::from_clip(clip.clone());
    commands.entity(node).insert(AnimationGraphHandle(graphs.add(graph)));
    if let Ok(mut player) = players.get_mut(node) {
        player.play(index).repeat();
    }
}
