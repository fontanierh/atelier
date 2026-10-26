//! The paraglider: in the character's right hand while the player glides, its cloth rippling in a loop, and put away
//! as it lands. Every character holds it at its [`Grip`], so it fits each one's hand.

use bevy::gltf::Gltf;
use bevy::prelude::*;
use bevy::world_serialization::WorldInstanceReady;
use hakuba_characters::Grip;

use crate::Player;
use crate::moves::{Action, Mode};

/// The exported paraglider, and its clip.
const MODEL: &str = "equipment/glider/glider.glb";
const CLIP: &str = "glider";

pub struct GliderPlugin;

impl Plugin for GliderPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, load).add_systems(Update, spawn_model).add_observer(ripple);
    }
}

#[derive(Resource)]
struct Model(Handle<Gltf>);

/// A paraglider in a character's hand, and the character it belongs to.
#[derive(Component)]
pub(crate) struct Glider {
    character: Entity,
}

/// A paraglider waiting for its model to load.
#[derive(Component)]
struct Waiting;

fn load(mut commands: Commands, assets: Res<AssetServer>) {
    commands.insert_resource(Model(assets.load(MODEL)));
}

/// Shows the paraglider while the player glides and as it lands, and takes it away otherwise.
pub fn show(
    mut commands: Commands,
    players: Query<&Player>,
    grips: Query<(Entity, &Grip)>,
    gliders: Query<(Entity, &Glider)>,
) {
    for player in &players {
        let motion = &player.motion;
        let held = motion.mode == Mode::Glide || motion.action == Action::GlideClose;
        let shown = gliders.iter().find(|(_, glider)| glider.character == player.body);
        match (held, shown) {
            (true, None) => {
                let Some((grip, _)) = grips.iter().find(|(_, grip)| grip.character == player.body) else { continue };
                commands.entity(grip).with_child((
                    Name::new("Glider"),
                    Glider { character: player.body },
                    Waiting,
                    Transform::IDENTITY,
                ));
            }
            (false, Some((glider, _))) => commands.entity(glider).despawn(),
            _ => {}
        }
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

/// Once a paraglider's model has spawned, plays its cloth's ripple in a loop.
#[allow(clippy::too_many_arguments)]
fn ripple(
    ready: On<WorldInstanceReady>,
    mut commands: Commands,
    model: Res<Model>,
    gltfs: Res<Assets<Gltf>>,
    gliders: Query<(), With<Glider>>,
    children: Query<&Children>,
    mut players: Query<&mut AnimationPlayer>,
    mut graphs: ResMut<Assets<AnimationGraph>>,
) {
    if !gliders.contains(ready.entity) {
        return;
    }
    let Some(clip) = gltfs.get(&model.0).and_then(|gltf| gltf.named_animations.get(CLIP)) else { return };
    let Some(node) = children.iter_descendants(ready.entity).find(|node| players.contains(*node)) else { return };
    let (graph, index) = AnimationGraph::from_clip(clip.clone());
    commands.entity(node).insert(AnimationGraphHandle(graphs.add(graph)));
    if let Ok(mut player) = players.get_mut(node) {
        player.play(index).repeat();
    }
}
