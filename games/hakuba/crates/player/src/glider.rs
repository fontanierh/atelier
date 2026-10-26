//! The paraglider: held in both hands above the character while the player glides, its cloth rippling in a loop, and
//! put away as it lands. It sits on the body between the palms, scaled to the character's size, and banks into
//! turns. Each player has one from the start, drawn too small to see while it is put away, so its shaders are ready the
//! first time it opens.

use bevy::gltf::{Gltf, GltfExtras};
use bevy::prelude::*;
use bevy::world_serialization::WorldInstanceReady;
use hakuba_characters::{Clips, Hands, Playing};
use serde::Deserialize;

use crate::Player;
use crate::moves::{Action, Mode};

/// The exported paraglider, and its clip.
const MODEL: &str = "equipment/glider/glider.glb";
const CLIP: &str = "glider";

/// The model's node whose extras give how high the hips of the skeleton that held it stand.
const HOLDER_NODE: &str = "holder";

/// How far into putting it away the paraglider goes, in seconds of the clip.
const PUT_AWAY_S: f32 = 0.1;

/// How far it banks for each radian a second the glide turns, at most `MOST_BANK_DEG`, and how fast it gets there.
const BANK_PER_TURN: f32 = 0.12;
const MOST_BANK_DEG: f32 = 12.0;
const BANK_RATE: f32 = 5.0;

/// Its scale while put away: too small to see, yet drawn.
const AWAY_SCALE: f32 = 1e-3;

pub struct GliderPlugin;

impl Plugin for GliderPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, load).add_systems(Update, (spawn, spawn_model)).add_observer(ripple);
    }
}

#[derive(Resource)]
struct Model(Handle<Gltf>);

/// A character's paraglider, a child of its body.
#[derive(Component)]
pub(crate) struct Glider {
    character: Entity,
    /// How high the hips of the skeleton that held it stand, in metres: 0 until its model has spawned.
    holder_hips_m: f32,
    /// How far it leans into the turn, in radians.
    bank: f32,
}

impl Glider {
    pub(crate) fn of(&self, character: Entity) -> bool {
        self.character == character && self.holder_hips_m > 0.0
    }
}

/// A paraglider waiting for its model to load.
#[derive(Component)]
struct Waiting;

/// The extras of the model's `holder` node.
#[derive(Deserialize)]
struct HolderExtras {
    hips_m: f32,
}

fn load(mut commands: Commands, assets: Res<AssetServer>) {
    commands.insert_resource(Model(assets.load(MODEL)));
}

/// Gives each player's character its paraglider, put away.
fn spawn(mut commands: Commands, players: Query<&Player, Added<Player>>) {
    for player in &players {
        commands.entity(player.body).with_child((
            Name::new("Glider"),
            Glider { character: player.body, holder_hips_m: 0.0, bank: 0.0 },
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

/// Shows the paraglider between the palms while the player glides and as it starts putting it away, banking into
/// turns, and puts it away otherwise.
pub fn show(
    time: Res<Time>,
    players: Query<&Player>,
    bodies: Query<(&Clips, &Playing, &Hands, &GlobalTransform)>,
    hands: Query<&GlobalTransform>,
    mut gliders: Query<(&mut Glider, &mut Transform)>,
) {
    for player in &players {
        let Some((mut glider, mut transform)) = gliders.iter_mut().find(|(glider, _)| glider.of(player.body)) else {
            continue;
        };
        let Ok((clips, playing, body_hands, body)) = bodies.get(player.body) else { continue };
        let (wrists, knuckles) = (body_hands.wrists, body_hands.knuckles);
        let Ok(ends) = hands.get_many([wrists[0], knuckles[0], wrists[1], knuckles[1]]) else { continue };
        let motion = &player.motion;
        let held = motion.mode == Mode::Glide || (motion.action == Action::GlideClose && playing.time < PUT_AWAY_S);
        let most = MOST_BANK_DEG.to_radians();
        let bank = if held { (motion.glide_turn() * BANK_PER_TURN).clamp(-most, most) } else { 0.0 };
        glider.bank += (bank - glider.bank) * (BANK_RATE * time.delta_secs()).min(1.0);
        // Halfway between the palms' centres, each halfway from its wrist to its knuckle.
        let between = ends.iter().map(|end| end.translation()).sum::<Vec3>() * 0.25;
        transform.translation = body.affine().inverse().transform_point3(between);
        transform.rotation = Quat::from_rotation_z(-glider.bank);
        let scale = if held { clips.hips_m / glider.holder_hips_m } else { AWAY_SCALE };
        transform.scale = Vec3::splat(scale);
    }
}

/// Once a paraglider's model has spawned: reads its holder's size and plays its cloth's ripple in a loop.
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
    glider.holder_hips_m = holder.expect("the paraglider's holder node gives its hips' height").hips_m;
    let Some(clip) = gltfs.get(&model.0).and_then(|gltf| gltf.named_animations.get(CLIP)) else { return };
    let Some(node) = children.iter_descendants(ready.entity).find(|node| players.contains(*node)) else { return };
    let (graph, index) = AnimationGraph::from_clip(clip.clone());
    commands.entity(node).insert(AnimationGraphHandle(graphs.add(graph)));
    if let Ok(mut player) = players.get_mut(node) {
        player.play(index).repeat();
    }
}
