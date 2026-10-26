//! The models standing in the tiles: trees, bushes, grass and poles. A tile holds one data node per model, naming the
//! model and listing where each copy stands. Once the model has loaded, each copy of a large model, such as a tree, is
//! spawned with the model's own meshes and materials, shared by every copy, so Bevy draws them together, in one call
//! across every tile. The copies of a small model, such as a tuft of grass, are merged into one mesh per tile
//! instead: thousands of entities would cost more to cull one by one than their few vertices cost together. Merging a
//! large model would not pay: each tile's merged mesh is drawn on its own.

use bevy::asset::RenderAssetUsages;
use bevy::gltf::{Gltf, GltfExtras, GltfMesh, GltfNode};
use bevy::light::NotShadowCaster;
use bevy::prelude::*;
use bevy::world_serialization::WorldAssetRoot;
use serde::Deserialize;

/// A model with fewer vertices than this has its copies merged.
const MERGE_BELOW_VERTICES: usize = 256;

/// The most vertices one tile's merged copies of a model may hold: past this, merging costs more memory than it saves.
const MERGED_AT_MOST_VERTICES: usize = 500_000;

pub struct SceneryPlugin;

impl Plugin for SceneryPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Update, (read, spawn).chain().in_set(Placing));
    }
}

/// Reading tiles' data nodes and spawning their copies.
#[derive(SystemSet, Clone, PartialEq, Eq, Hash, Debug)]
pub struct Placing;

/// A tile's data node: the model, relative to the tile's file, the tile's version, and five numbers per copy: its
/// position, its turn about y and its scale.
#[derive(Deserialize)]
struct Copies {
    model: String,
    detail: String,
    instances: Vec<f32>,
}

/// A model's extras: whether it casts shadows.
#[derive(Deserialize)]
struct ModelExtras {
    casts_shadows: bool,
}

/// Copies waiting for their model to load.
#[derive(Component)]
pub struct Waiting {
    model: Handle<Gltf>,
    middle: bool,
    instances: Vec<f32>,
}

/// Copies spawned from their model, which may still be loading its textures.
#[derive(Component)]
pub struct Placed(pub Handle<Gltf>);

/// Reads each data node of a tile as it spawns, and starts loading its model.
fn read(
    mut commands: Commands,
    assets: Res<AssetServer>,
    added: Query<(Entity, &GltfExtras), Added<GltfExtras>>,
    parents: Query<&ChildOf>,
    roots: Query<&WorldAssetRoot>,
) {
    for (entity, extras) in &added {
        let copies: Copies = match serde_json::from_str(&extras.value) {
            Ok(copies) => copies,
            Err(error) => {
                warn!("a tile's data node is not a model's copies: {error}");
                continue;
            }
        };
        let Some(path) = parents.iter_ancestors(entity).find_map(|e| roots.get(e).ok()).and_then(|r| r.0.path()) else {
            continue;
        };
        let model = match path.resolve_embed_str(&copies.model) {
            Ok(model) => model,
            Err(error) => {
                warn!("{path} names a model at {}: {error}", copies.model);
                continue;
            }
        };
        let waiting =
            Waiting { model: assets.load(model), middle: copies.detail == "middle", instances: copies.instances };
        commands.entity(entity).insert(waiting);
    }
}

/// Spawns the copies whose model has loaded: its `middle` node in a middle tile, if it has one, and its `full` node
/// otherwise.
fn spawn(
    mut commands: Commands,
    assets: Res<AssetServer>,
    waiting: Query<(Entity, &Waiting)>,
    gltfs: Res<Assets<Gltf>>,
    nodes: Res<Assets<GltfNode>>,
    gltf_meshes: Res<Assets<GltfMesh>>,
    mut meshes: ResMut<Assets<Mesh>>,
) {
    for (entity, waiting) in &waiting {
        let Some(gltf) = gltfs.get(&waiting.model) else { continue };
        commands.entity(entity).remove::<Waiting>().insert(Placed(waiting.model.clone()));
        let name = if waiting.middle && gltf.named_nodes.contains_key("middle") { "middle" } else { "full" };
        let Some(node) = gltf.named_nodes.get(name).and_then(|node| nodes.get(node)) else {
            warn!("a model has no {name} node");
            continue;
        };
        let Some(mesh) = node.mesh.as_ref().and_then(|mesh| gltf_meshes.get(mesh)) else { continue };
        let shadows = node
            .extras
            .as_ref()
            .and_then(|extras| serde_json::from_str::<ModelExtras>(&extras.value).ok())
            .is_none_or(|extras| extras.casts_shadows);
        let parts: Vec<(Handle<Mesh>, Handle<StandardMaterial>)> = mesh
            .primitives
            .iter()
            .map(|primitive| (primitive.mesh.clone(), standard(&assets, primitive.material.as_ref())))
            .collect();
        let transforms: Vec<Transform> = waiting
            .instances
            .chunks_exact(5)
            .map(|copy| {
                let &[x, y, z, yaw, scale] = copy else { unreachable!() };
                Transform::from_xyz(x, y, z).with_rotation(Quat::from_rotation_y(yaw)).with_scale(Vec3::splat(scale))
            })
            .collect();
        let vertices = vertices(&gltf_meshes, &meshes, node);
        let merge = vertices < MERGE_BELOW_VERTICES && vertices * transforms.len() <= MERGED_AT_MOST_VERTICES;
        for (mesh, material) in &parts {
            let shapes: Vec<(Handle<Mesh>, Transform)> =
                match merge.then(|| merged(&meshes, mesh, &transforms)).flatten() {
                    Some(merged) => vec![(meshes.add(merged), Transform::IDENTITY)],
                    None => transforms.iter().map(|&transform| (mesh.clone(), transform)).collect(),
                };
            for (mesh, transform) in shapes {
                let mut part =
                    commands.spawn((Mesh3d(mesh), MeshMaterial3d(material.clone()), transform, ChildOf(entity)));
                if !shadows {
                    part.insert(NotShadowCaster);
                }
            }
        }
    }
}

/// How many vertices `node`'s meshes have, counting those loaded.
fn vertices(gltf_meshes: &Assets<GltfMesh>, meshes: &Assets<Mesh>, node: &GltfNode) -> usize {
    let Some(mesh) = node.mesh.as_ref().and_then(|mesh| gltf_meshes.get(mesh)) else { return 0 };
    mesh.primitives.iter().filter_map(|primitive| meshes.get(&primitive.mesh)).map(Mesh::count_vertices).sum()
}

/// One mesh holding `mesh` once per transform, kept only on the GPU. None if the mesh is not loaded or cannot merge.
fn merged(meshes: &Assets<Mesh>, mesh: &Handle<Mesh>, transforms: &[Transform]) -> Option<Mesh> {
    let mesh = meshes.get(mesh)?;
    let mut merged = mesh.clone().transformed_by(*transforms.first()?);
    for &transform in &transforms[1..] {
        merged.merge(&mesh.clone().transformed_by(transform)).ok()?;
    }
    merged.asset_usage = RenderAssetUsages::RENDER_WORLD;
    Some(merged)
}

/// The standard material Bevy made from a glTF material: the material's own asset, labelled `<label>/std`.
fn standard(assets: &AssetServer, material: Option<&Handle<bevy::gltf::GltfMaterial>>) -> Handle<StandardMaterial> {
    let Some(path) = material.and_then(|material| material.path()) else { return Handle::default() };
    let label = format!("{}/std", path.label().unwrap_or_default());
    assets.load(path.clone().with_label(label))
}
