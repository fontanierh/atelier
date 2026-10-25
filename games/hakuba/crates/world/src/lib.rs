//! The world: the ground and the road from `assets/world`, the sea, a sun, and a camera that starts at the spawn
//! and flies.

mod fly;
mod tiles;

use bevy::gltf::{Gltf, GltfNode};
use bevy::prelude::*;
use hakuba_screens::Screen;

use fly::Fly;
use tiles::Tile;

/// The world's index: one node per tile, and the spawn.
const INDEX: &str = "world/world.glb";

/// How high the camera starts above the spawn: a standing person's eyes.
const EYE_HEIGHT_M: f32 = 1.7;

/// Side of the square sea, in metres: wide enough that its edge stays out of sight.
const SEA_SIZE_M: f32 = 20000.0;

pub struct WorldPlugin;

impl Plugin for WorldPlugin {
    fn build(&self, app: &mut App) {
        app.add_plugins((fly::FlyPlugin, tiles::TilesPlugin))
            .add_systems(OnEnter(Screen::World), spawn_world)
            .add_systems(Update, read_index.run_if(in_state(Screen::World)));
    }
}

/// The world's index, while it loads.
#[derive(Resource)]
struct Index(Handle<Gltf>);

fn spawn_world(
    mut commands: Commands,
    assets: Res<AssetServer>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    commands.insert_resource(Index(assets.load(INDEX)));
    commands.insert_resource(ClearColor(Color::srgb(0.53, 0.72, 0.9)));
    commands.spawn((
        Name::new("Sea"),
        DespawnOnExit(Screen::World),
        Mesh3d(meshes.add(Plane3d::default().mesh().size(SEA_SIZE_M, SEA_SIZE_M))),
        MeshMaterial3d(materials.add(StandardMaterial {
            base_color: Color::srgb(0.18, 0.36, 0.52),
            perceptual_roughness: 0.4,
            ..default()
        })),
    ));
    commands.spawn((
        Name::new("Sun"),
        DespawnOnExit(Screen::World),
        DirectionalLight { illuminance: light_consts::lux::AMBIENT_DAYLIGHT, shadow_maps_enabled: true, ..default() },
        Transform::from_xyz(30.0, 60.0, 20.0).looking_at(Vec3::ZERO, Vec3::Y),
    ));
    commands.spawn((Name::new("Camera"), DespawnOnExit(Screen::World), Camera3d::default(), Fly::default()));
}

/// Once the index has loaded: puts the camera at the spawn and adds a [`Tile`] for each tile.
fn read_index(
    mut commands: Commands,
    index: Option<Res<Index>>,
    gltfs: Res<Assets<Gltf>>,
    nodes: Res<Assets<GltfNode>>,
    mut camera: Single<&mut Transform, With<Fly>>,
) {
    let Some(index) = index else { return };
    let Some(gltf) = gltfs.get(&index.0) else { return };
    for (name, node) in &gltf.named_nodes {
        let node = nodes.get(node).expect("a loaded glTF's nodes are loaded");
        if &**name == "spawn" {
            **camera = node.transform.with_translation(node.transform.translation + Vec3::Y * EYE_HEIGHT_M);
        } else if let Some(tile) = Tile::named(name, node.transform.translation) {
            commands.spawn((Name::new(name.to_string()), DespawnOnExit(Screen::World), tile, Transform::default(), Visibility::default()));
        }
    }
    commands.remove_resource::<Index>();
}
