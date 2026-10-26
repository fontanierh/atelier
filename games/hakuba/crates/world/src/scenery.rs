//! The models standing in the tiles: trees, bushes, grass and poles. A tile holds one data node per model, naming the
//! model and listing where each copy stands. Once the model has loaded, each copy of a large model, such as a tree, is
//! spawned with the model's own meshes and materials, shared by every copy, so Bevy draws them together, in one call
//! across every tile. The copies of a small model, such as a tuft of grass, are merged into one mesh per tile
//! instead: thousands of entities would cost more to cull one by one than their few vertices cost together. Merging a
//! large model would not pay: each tile's merged mesh is drawn on its own.

use bevy::asset::RenderAssetUsages;
use bevy::camera::visibility::{VisibilityRange, VisibilitySystems};
use bevy::ecs::system::SystemParam;
use bevy::gltf::{Gltf, GltfExtras, GltfMesh, GltfNode};
use bevy::light::NotShadowCaster;
use bevy::prelude::*;
use bevy::world_serialization::WorldAssetRoot;
use serde::Deserialize;

use crate::tiles::TILES;
use crate::wind::{FULL_UP_TO_M, SWAP_M, Swap, Swaying, SwayingMaterials};

/// A model with fewer vertices than this has its copies merged.
const MERGE_BELOW_VERTICES: usize = 256;

/// The most vertices one tile's merged copies of a model may hold: past this, merging costs more memory than it saves.
const MERGED_AT_MOST_VERTICES: usize = 500_000;

pub struct SceneryPlugin;

impl Plugin for SceneryPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Update, (read, spawn).chain().in_set(Placing))
            .add_systems(PostUpdate, no_crossfades.before(VisibilitySystems::CheckVisibility));
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
        // Only the tiles' data nodes: other models, such as the characters, carry extras of their own.
        let Some(path) = parents.iter_ancestors(entity).find_map(|e| roots.get(e).ok()).and_then(|r| r.0.path()) else {
            continue;
        };
        if !path.path().starts_with(TILES) {
            continue;
        }
        let copies: Copies = match serde_json::from_str(&extras.value) {
            Ok(copies) => copies,
            Err(error) => {
                warn!("a tile's data node is not a model's copies: {error}");
                continue;
            }
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

/// The models' parts, as Bevy loads them from glTF.
#[derive(SystemParam)]
struct Models<'w> {
    gltfs: Res<'w, Assets<Gltf>>,
    nodes: Res<'w, Assets<GltfNode>>,
    meshes: Res<'w, Assets<GltfMesh>>,
}

/// Spawns the copies whose model has loaded. A middle tile shows the model's `middle` node, if it has one, and its
/// `full` node otherwise. A full tile shows a model that has a `middle` node as both: the full version near the camera,
/// giving way to the middle one from [`FULL_UP_TO_M`], so the leaves' detail is drawn only where it is seen up close.
fn spawn(
    mut commands: Commands,
    assets: Res<AssetServer>,
    waiting: Query<(Entity, &Waiting)>,
    models: Models,
    mut meshes: ResMut<Assets<Mesh>>,
    mut swaying: SwayingMaterials,
) {
    'copies: for (entity, waiting) in &waiting {
        let Some(gltf) = models.gltfs.get(&waiting.model) else { continue };
        let versions = match (waiting.middle, gltf.named_nodes.contains_key("middle")) {
            (true, true) => vec![("middle", None)],
            (false, true) => vec![("full", Some(Swap::Going)), ("middle", Some(Swap::Coming))],
            (_, false) => vec![("full", None)],
        };
        let mut shown = Vec::with_capacity(versions.len());
        for (name, swap) in versions {
            let Some(node) = gltf.named_nodes.get(name).and_then(|node| models.nodes.get(node)) else {
                warn!("a model has no {name} node");
                commands.entity(entity).remove::<Waiting>();
                continue 'copies;
            };
            let Some(parts) = parts(&assets, &models, &meshes, &mut swaying, node) else { continue 'copies };
            shown.push((node, parts, swap));
        }
        commands.entity(entity).remove::<Waiting>().insert(Placed(waiting.model.clone()));
        let transforms: Vec<Transform> = waiting
            .instances
            .chunks_exact(5)
            .map(|copy| {
                let &[x, y, z, yaw, scale] = copy else { unreachable!() };
                Transform::from_xyz(x, y, z).with_rotation(Quat::from_rotation_y(yaw)).with_scale(Vec3::splat(scale))
            })
            .collect();
        for (node, parts, swap) in shown {
            let shadows = node
                .extras
                .as_ref()
                .and_then(|extras| serde_json::from_str::<ModelExtras>(&extras.value).ok())
                .is_none_or(|extras| extras.casts_shadows);
            let vertices = vertices(&models.meshes, &meshes, node);
            // A merged mesh stands at the tile's origin, not at each copy, so copies that swap by distance stay apart.
            let merge = swap.is_none()
                && vertices < MERGE_BELOW_VERTICES
                && vertices * transforms.len() <= MERGED_AT_MOST_VERTICES;
            for (mesh, look) in &parts {
                let shapes: Vec<(Handle<Mesh>, Transform)> =
                    match merge.then(|| merged(&meshes, mesh, &transforms)).flatten() {
                        Some(merged) => vec![(meshes.add(merged), Transform::IDENTITY)],
                        None => transforms.iter().map(|&transform| (mesh.clone(), transform)).collect(),
                    };
                for (mesh, transform) in shapes {
                    let mut part = commands.spawn((Mesh3d(mesh), transform, ChildOf(entity)));
                    match look {
                        Look::Still(material) => part.insert(MeshMaterial3d(material.clone())),
                        Look::Swaying(material) => part.insert(MeshMaterial3d(material.clone())),
                    };
                    let sways = matches!(look, Look::Swaying(_));
                    if !shadows {
                        part.insert(NotShadowCaster);
                    }
                    if let Some(swap) = swap {
                        part.insert(range(swap, sways));
                        if sways {
                            part.insert(swap);
                        }
                    }
                }
            }
        }
    }
}

/// Where a version that swaps by distance is drawn at all. A swaying part is drawn wherever it may show and its shader
/// swaps it a card at a time (`wind.wesl`); a still one swaps whole, halfway. Either way at once, never a crossfade:
/// Bevy's dithers its pixels in screen space, which shimmers under temporal anti-aliasing.
fn range(swap: Swap, sways: bool) -> VisibilityRange {
    let halfway = FULL_UP_TO_M + SWAP_M / 2.0;
    let (from, to) = if sways { (FULL_UP_TO_M, FULL_UP_TO_M + SWAP_M) } else { (halfway, halfway) };
    match swap {
        Swap::Going => VisibilityRange::abrupt(0.0, to),
        Swap::Coming => VisibilityRange::abrupt(from, f32::MAX),
    }
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

/// `node`'s meshes, each with its look: a part whose vertices say how far they sway is drawn with the swaying version
/// of its material. None while a mesh or material is still loading.
fn parts(
    assets: &AssetServer,
    models: &Models,
    meshes: &Assets<Mesh>,
    swaying: &mut SwayingMaterials,
    node: &GltfNode,
) -> Option<Vec<(Handle<Mesh>, Look)>> {
    let mesh = node.mesh.as_ref().and_then(|mesh| models.meshes.get(mesh))?;
    mesh.primitives
        .iter()
        .map(|primitive| {
            let material = standard_of(assets, primitive.material.as_ref());
            let sways = meshes.get(&primitive.mesh).is_some_and(|mesh| mesh.contains_attribute(Mesh::ATTRIBUTE_UV_1));
            let look = if sways { Look::Swaying(swaying.of(&material)?) } else { Look::Still(material) };
            Some((primitive.mesh.clone(), look))
        })
        .collect()
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

/// How a part looks: its material as the model has it, or its swaying version.
enum Look {
    Still(Handle<StandardMaterial>),
    Swaying(Handle<Swaying>),
}

/// The standard material Bevy made from a glTF material: the material's own asset, labelled `<label>/std`.
fn standard_of(assets: &AssetServer, material: Option<&Handle<bevy::gltf::GltfMaterial>>) -> Handle<StandardMaterial> {
    let Some(path) = material.and_then(|material| material.path()) else { return Handle::default() };
    let label = format!("{}/std", path.label().unwrap_or_default());
    assets.load(path.clone().with_label(label))
}
