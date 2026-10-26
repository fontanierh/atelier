//! The world: the ground, the road and what stands around it from `assets/world`, the sea, the sky, sun and haze, and a camera that
//! starts at the spawn and flies.

mod fly;
mod loading;
mod look;
mod painterly;
mod pixels;
mod scenery;
mod tiles;
mod wind;

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
        app.add_plugins((
            fly::FlyPlugin,
            loading::LoadingPlugin,
            look::LookPlugin,
            painterly::PainterlyPlugin,
            pixels::PixelsPlugin,
            scenery::SceneryPlugin,
            tiles::TilesPlugin,
            wind::WindPlugin,
        ))
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
    mut images: ResMut<Assets<Image>>,
) {
    commands.insert_resource(Index(assets.load(INDEX)));
    commands.spawn((
        Name::new("Sea"),
        DespawnOnExit(Screen::World),
        Mesh3d(meshes.add(Plane3d::default().mesh().size(SEA_SIZE_M, SEA_SIZE_M))),
        MeshMaterial3d(materials.add(StandardMaterial {
            base_color: Color::srgb(0.30, 0.44, 0.58),
            perceptual_roughness: 1.0,
            ..default()
        })),
    ));
    let drawn = pixels::spawn(&mut commands, &mut images);
    commands.spawn((
        Name::new("Camera"),
        DespawnOnExit(Screen::World),
        Camera3d::default(),
        Fly::default(),
        look::camera(),
        drawn,
    ));
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
            commands.spawn((
                Name::new(name.to_string()),
                DespawnOnExit(Screen::World),
                tile,
                Transform::default(),
                Visibility::default(),
            ));
        }
    }
    commands.remove_resource::<Index>();
}
