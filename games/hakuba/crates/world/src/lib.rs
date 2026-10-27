//! The world: the ground, the road and what stands around it from `assets/world`, the sea, the sky, sun and haze, and
//! a camera that starts at the spawn. It publishes where the player starts ([`Spawn`]) and what the player can stand
//! on ([`Ground`]), and [`PushesPlants`], which makes the plants around whatever carries it lean away; the player
//! crate moves the camera.

mod actors;
mod ground;
mod loading;
mod look;
mod painterly;
mod pause;
mod pixels;
mod push;
mod scenery;
mod settings;
mod tiles;
mod vertex_paint;
mod wind;

use bevy::camera::visibility::{VisibilityRange, VisibilitySystems};
use bevy::gltf::{Gltf, GltfNode};
use bevy::prelude::*;
use hakuba_screens::Screen;

use tiles::Tile;

pub use ground::{Ground, Hit, SEA_LEVEL_M, Surface};
pub use loading::Unready;
pub use push::PushesPlants;

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
            actors::ActorsPlugin,
            ground::GroundPlugin,
            loading::LoadingPlugin,
            look::LookPlugin,
            painterly::PainterlyPlugin,
            pause::PausePlugin,
            pixels::PixelsPlugin,
            push::PushPlugin,
            scenery::SceneryPlugin,
            settings::SettingsPlugin,
            tiles::TilesPlugin,
            vertex_paint::VertexPaintPlugin,
            wind::WindPlugin,
        ))
        .add_systems(OnEnter(Screen::World), spawn_world)
        .add_systems(Update, read_index.run_if(in_state(Screen::World)))
        .add_systems(PostUpdate, no_crossfades.before(VisibilitySystems::CheckVisibility));
    }
}

#[derive(Component)]
struct WorldCamera;

/// The world's index, while it loads.
#[derive(Resource)]
struct Index(Handle<Gltf>);

/// Where the player starts, on the ground, facing the way the world's export says. Inserted once the world's index
/// has loaded.
#[derive(Resource, Clone, Copy)]
pub struct Spawn(pub Transform);

fn spawn_world(
    mut commands: Commands,
    assets: Res<AssetServer>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    mut images: ResMut<Assets<Image>>,
) {
    commands.insert_resource(Index(assets.load(INDEX)));
    commands.remove_resource::<Spawn>();
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
        WorldCamera,
        DespawnOnExit(Screen::World),
        Camera3d::default(),
        look::camera(&mut images),
        drawn,
    ));
}

/// Once the index has loaded: records the spawn, puts the camera there and adds a [`Tile`] for each tile.
fn read_index(
    mut commands: Commands,
    index: Option<Res<Index>>,
    gltfs: Res<Assets<Gltf>>,
    nodes: Res<Assets<GltfNode>>,
    assets: Res<AssetServer>,
    mut camera: Single<&mut Transform, With<Camera3d>>,
) {
    let Some(index) = index else { return };
    let Some(gltf) = gltfs.get(&index.0) else { return };
    for (name, node) in &gltf.named_nodes {
        let node = nodes.get(node).expect("a loaded glTF's nodes are loaded");
        if &**name == "spawn" {
            commands.insert_resource(Spawn(node.transform));
            **camera = node.transform.with_translation(node.transform.translation + Vec3::Y * EYE_HEIGHT_M);
        } else if name.starts_with("actor ") {
            if let Some(actor) =
                node.extras.as_ref().and_then(|extras| serde_json::from_str::<actors::Actor>(&extras.value).ok())
            {
                actors::spawn(&mut commands, &assets, actor);
            } else {
                error!("invalid actor declaration: {name}");
            }
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

/// Makes every visibility range in the game abrupt, saying so, should one crossfade: Bevy dithers a crossfade's pixels
/// in screen space, which shimmers under temporal anti-aliasing, so it is never shown.
fn no_crossfades(mut ranges: Query<(Entity, &mut VisibilityRange), Changed<VisibilityRange>>) {
    for (entity, mut range) in &mut ranges {
        if range.is_abrupt() {
            continue;
        }
        error!("{entity} crossfades between versions, which shimmers: it swaps at once, halfway, instead");
        let start = (range.start_margin.start + range.start_margin.end) / 2.0;
        let end = (range.end_margin.start + range.end_margin.end) / 2.0;
        *range = VisibilityRange::abrupt(start, end);
    }
}
