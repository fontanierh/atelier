//! The models standing in the tiles: trees, bushes, grass and poles. A tile holds one data node per model, naming the
//! model and listing where each copy stands. Once the model has loaded, each copy of a large model, such as a tree, is
//! spawned with the model's own meshes and materials, shared by every copy, so Bevy draws them together, in one call
//! across every tile. The copies of a small model, such as a tuft of grass or a tree's middle version, are merged
//! instead, into one mesh per square: shadow-casting models use 32 m squares and others a whole tile. Thousands of
//! entities would cost more to cull and draw one by one than their few vertices cost together, and squares out of view
//! are not drawn. Merging a large model would not pay: each merged mesh is drawn on its own. A far tile shows a plant's
//! few-triangle far version instead, and the far versions share one texture, so a far tile merges all its plants
//! together, whatever their model: one mesh a tile, where the browser would otherwise issue a draw for each model in
//! each of thousands of far tiles.
//!
//! A plant in a full tile shows its full version wherever the camera is, so it never changes as the player walks up to
//! it, and casts the shadow of its middle version, which is never seen: the sun's shadow maps draw far fewer leaves.

use std::collections::VecDeque;

use bevy::asset::{RenderAssetUsages, UntypedAssetId};
use bevy::camera::primitives::Aabb;
use bevy::camera::visibility::RenderLayers;
use bevy::ecs::system::EntityCommands;
use bevy::ecs::system::SystemParam;
use bevy::gltf::{Gltf, GltfExtras, GltfMesh, GltfNode};
use bevy::light::NotShadowCaster;
use bevy::mesh::{MeshTag, MeshVertexAttributeId, VertexAttributeValues};
use bevy::platform::collections::HashMap;
use bevy::prelude::*;
use bevy::world_serialization::WorldAssetRoot;
use serde::Deserialize;

use crate::collision::CollisionSource;
use crate::ground::built_solid;
use crate::loading::{Loaded, Missing};
use crate::look::SHADOW_ONLY;
use crate::tiles::{Spawning, TILES};
use crate::vertex_paint::{
    MotionProfile, MovingPainted, MovingPaintedMaterials, Painted, PaintedMaterials, Profile, SurfaceProfile,
};
use crate::water::{WaterMaterial, WaterMaterials};
use crate::wind::{ShadowFoliage, SourceFoliage, SourceProfile, Swaying, SwayingMaterials};

/// A model with fewer vertices than this has its copies merged: a bush, a fern, a tuft of grass, and a tree's middle
/// version, which a middle tile shows and a full tile's trees cast their shadows with. A forest seen from its edge is
/// thousands of these, each its own entity to cull and draw otherwise; a tree's full version is never merged.
const MERGE_BELOW_VERTICES: usize = 1024;

/// The side of the squares whose copies of a small, shadow-casting model are merged together, in metres: small enough
/// that each shadow cascade draws few squares it does not need, large enough to stay a few hundred meshes. In the
/// browser each mesh costs its draw's preparation in the prepass and the main pass, far more than its vertices.
const MERGED_SQUARE_M: f32 = 32.0;

/// The most vertices one tile's merged copies of a model may hold: past this, merging costs more memory than it saves.
const MERGED_AT_MOST_VERTICES: usize = 500_000;
/// Work issued to the renderer each update while tile scenery is being prepared.
const MERGE_VERTICES_PER_UPDATE: usize = 20_000;
const INSTANCES_PER_UPDATE: usize = 64;
/// How many times that work each update while the splash is up, when no frame is drawn for the player to stutter.
const UNDER_SPLASH: usize = 8;

pub struct SceneryPlugin;

impl Plugin for SceneryPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<FarTiles>().add_systems(Update, (read, spawn).chain().in_set(Placing)).add_systems(
            PostUpdate,
            cull_shadows
                .after(TransformSystems::Propagate)
                .before(bevy::camera::visibility::VisibilitySystems::CheckVisibility),
        );
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

/// A model's extras: whether it casts shadows and whether its visible meshes are solid.
#[derive(Deserialize)]
struct ModelExtras {
    #[serde(default = "default_shadows")]
    casts_shadows: bool,
    #[serde(default)]
    solid: bool,
}

fn default_shadows() -> bool {
    true
}

/// Copies waiting for their model to load.
#[derive(Component)]
pub struct Waiting {
    model: Handle<Gltf>,
    middle: bool,
    /// Its tile's root, if the tile shows plants' far versions.
    far: Option<Entity>,
    instances: Vec<f32>,
    jobs: Option<VecDeque<Job>>,
}

struct Job {
    mesh: Handle<Mesh>,
    material: String,
    face_materials: Vec<String>,
    look: Look,
    role: Role,
    shadows: bool,
    solid: bool,
    merge: bool,
    shadow_distance: Option<f32>,
    vertices: usize,
    transforms: Vec<Transform>,
    cursor: usize,
    /// A non-solid group's geometry while its copies are merged over several updates.
    combined: Option<Mesh>,
}

/// Copies spawned from their model, which may still be loading its textures.
#[derive(Component)]
pub struct Placed(pub Handle<Gltf>);

/// A data node whose plants' far versions wait to be merged with the rest of its tile's.
#[derive(Component)]
pub struct FarMerging;

/// Data nodes whose copies are not all spawned yet.
pub type Unplaced = Or<(With<Waiting>, With<FarMerging>)>;

/// The far tiles still merging their plants, by tile root.
#[derive(Resource, Default)]
struct FarTiles(HashMap<Entity, FarTile>);

#[derive(Default)]
struct FarTile {
    /// The tile's data nodes, which may hold plants with far versions.
    nodes: Vec<Entity>,
    /// The node the merged meshes are spawned under.
    anchor: Option<Entity>,
    groups: Vec<FarGroup>,
}

/// A far tile's copies drawn alike, merging into one mesh.
struct FarGroup {
    key: FarKey,
    look: Look,
    vertices: usize,
    copies: VecDeque<FarCopies>,
    mesh: Option<Mesh>,
}

/// What lets far parts merge: their texture and wind, or their material, and their vertex attributes.
type FarKey = (UntypedAssetId, String, Vec<MeshVertexAttributeId>);

struct FarCopies {
    mesh: Handle<Mesh>,
    vertices: usize,
    transforms: Vec<Transform>,
    cursor: usize,
}

/// Reads each data node of a tile as it spawns, and starts loading its model.
fn read(
    mut commands: Commands,
    assets: Res<AssetServer>,
    added: Query<(Entity, &GltfExtras), Added<GltfExtras>>,
    parents: Query<&ChildOf>,
    roots: Query<(&WorldAssetRoot, Option<&Spawning>)>,
    mut far_tiles: ResMut<FarTiles>,
) {
    for (entity, extras) in &added {
        // Only the tiles' data nodes: other models, such as the characters, carry extras of their own.
        let Some((tile, (root, spawning))) =
            parents.iter_ancestors(entity).find_map(|e| roots.get(e).ok().map(|root| (e, root)))
        else {
            continue;
        };
        let Some(path) = root.0.path() else { continue };
        if !path.path().starts_with(TILES) {
            continue;
        }
        if serde_json::from_str::<serde_json::Value>(&extras.value)
            .ok()
            .is_some_and(|v| v.get("surface_paint").is_some() || v.get("vertex_paint").is_some())
        {
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
        let far = (copies.detail == "middle" && spawning.is_some_and(Spawning::far)).then_some(tile);
        if far.is_some() {
            far_tiles.0.entry(tile).or_default().nodes.push(entity);
        }
        let waiting = Waiting {
            model: assets.load(model),
            middle: copies.detail == "middle",
            far,
            instances: copies.instances,
            jobs: None,
        };
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

#[derive(SystemParam)]
struct Materials<'w> {
    swaying: SwayingMaterials<'w>,
    painted: PaintedMaterials<'w>,
    moving: MovingPaintedMaterials<'w>,
    water: WaterMaterials<'w>,
}

/// @cc [owner:fontanierh,label:correctness] solid-scenery-matches-visible-mesh
/// A model with an explicit collision node MUST use only that node for solid rays. Otherwise, a model marked solid
/// on its full node MUST collide with its shown meshes, including merged copies, and never with shadow-only copies.
/// A model without either declaration MUST remain non-solid.
///
/// Spawns the copies whose model has loaded. A middle tile shows the model's `middle` node, if it has one, and its
/// `full` node otherwise, but a far one shows a plant's `far` node, if it has one, merged with the tile's other far
/// versions that look alike and casting no shadow; a prop's middle version is a file of its own holding only that
/// node. A full tile shows the `full` node, and a model that has a `middle` node casts that one's shadow instead.
#[allow(clippy::too_many_arguments)]
fn spawn(
    mut commands: Commands,
    assets: Res<AssetServer>,
    mut waiting: Query<(Entity, &mut Waiting)>,
    models: Models,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: Materials,
    mut far_tiles: ResMut<FarTiles>,
    roots: Query<(), With<WorldAssetRoot>>,
    loaded: Option<Res<Loaded>>,
) {
    let times = if loaded.is_some() { 1 } else { UNDER_SPLASH };
    let mut budget = Budget { vertices: MERGE_VERTICES_PER_UPDATE * times, instances: INSTANCES_PER_UPDATE * times };
    'copies: for (entity, mut waiting) in &mut waiting {
        if waiting.jobs.is_none() {
            if assets.load_state(&waiting.model).is_failed() {
                commands.entity(entity).remove::<Waiting>();
                continue;
            }
            let Some(gltf) = models.gltfs.get(&waiting.model) else { continue };
            let has_middle = gltf.named_nodes.contains_key("middle");
            let far = waiting.far.filter(|_| gltf.named_nodes.contains_key("far"));
            // A prop's separate middle version holds only its `middle` node, which a middle tile shows.
            let main = if far.is_some() {
                "far"
            } else if waiting.middle && has_middle {
                "middle"
            } else {
                "full"
            };
            let Some(main_handle) = gltf.named_nodes.get(main) else {
                warn!("a model has no {main} node");
                commands.entity(entity).remove::<Waiting>();
                continue;
            };
            let Some(main_node) = models.nodes.get(main_handle) else { continue };
            let collision = gltf.named_nodes.contains_key("collision");
            let solid = !collision && model_extras(main_node).is_some_and(|extras| extras.solid);
            let mut versions = match (waiting.middle, has_middle) {
                _ if far.is_some() => vec![("far", Role::Both)],
                (true, true) => vec![("middle", Role::Both)],
                (false, true) => vec![("full", Role::Seen), ("middle", Role::Shadow)],
                (_, false) => vec![("full", Role::Both)],
            };
            if collision {
                versions.push(("collision", Role::Collision));
            }
            let mut shown = Vec::with_capacity(versions.len());
            for (name, role) in versions {
                let Some(node) = gltf.named_nodes.get(name).and_then(|node| models.nodes.get(node)) else {
                    warn!("a model has no {name} node");
                    commands.entity(entity).remove::<Waiting>();
                    continue 'copies;
                };
                let mut parts = if matches!(role, Role::Collision) {
                    let Some(mesh) = node.mesh.as_ref().and_then(|mesh| models.meshes.get(mesh)) else {
                        continue 'copies;
                    };
                    let Some(parts) = mesh
                        .primitives
                        .iter()
                        .map(|part| {
                            meshes.get(&part.mesh)?;
                            Some((part.mesh.clone(), Look::Still(Handle::default())))
                        })
                        .collect::<Option<Vec<_>>>()
                    else {
                        continue 'copies;
                    };
                    parts
                } else {
                    match parts(&assets, &models, &meshes, &mut materials, node, role) {
                        Ok(Some(parts)) => parts,
                        Ok(None) => continue 'copies,
                        Err(reason) => {
                            let asset = waiting.model.path().map_or_else(|| "model".to_string(), |p| p.to_string());
                            error!("invalid {asset} node {name}: {reason}");
                            commands.insert_resource(Missing(format!("{asset}: {reason}")));
                            commands.entity(entity).remove::<Waiting>();
                            continue 'copies;
                        }
                    }
                };
                if !matches!(role, Role::Collision)
                    && let Some(material) =
                        waiting.model.path().and_then(|path| materials.water.for_model(&path.path().to_string_lossy()))
                {
                    for (_, look) in &mut parts {
                        *look = Look::Water(material.clone());
                    }
                }
                shown.push((node, parts, role));
            }
            let transforms: Vec<Transform> = waiting
                .instances
                .chunks_exact(5)
                .map(|copy| {
                    let &[x, y, z, yaw, scale] = copy else { unreachable!() };
                    Transform::from_xyz(x, y, z)
                        .with_rotation(Quat::from_rotation_y(yaw))
                        .with_scale(Vec3::splat(scale))
                })
                .collect();
            let mut jobs = VecDeque::new();
            for (node, parts, role) in shown {
                let shadows = model_extras(node).is_none_or(|extras| extras.casts_shadows);
                let shadow_distance = match shadow_distance(node) {
                    Ok(distance) => distance,
                    Err(reason) => {
                        let asset = waiting.model.path().map_or_else(|| "model".to_string(), |p| p.to_string());
                        error!("invalid {asset} node: {reason}");
                        commands.insert_resource(Missing(asset));
                        commands.entity(entity).remove::<Waiting>();
                        continue 'copies;
                    }
                };
                let solid = matches!(role, Role::Collision) || role.is_solid(solid);
                if matches!(role, Role::Shadow) && !shadows {
                    continue;
                }
                let vertices = vertices(&models.meshes, &meshes, node);
                let merge = vertices < MERGE_BELOW_VERTICES && vertices * transforms.len() <= MERGED_AT_MOST_VERTICES;
                for (mesh, look) in parts {
                    let material = node
                        .mesh
                        .as_ref()
                        .and_then(|m| models.meshes.get(m))
                        .and_then(|m| m.primitives.iter().find(|p| p.mesh == mesh))
                        .and_then(|p| p.material.as_ref())
                        .and_then(|handle| {
                            gltf.named_materials.iter().find(|(_, h)| *h == handle).map(|(n, _)| n.to_string())
                        })
                        .unwrap_or_default();
                    let face_materials = if matches!(role, Role::Collision) {
                        collision_materials(gltf, &models, &meshes, &mesh)
                    } else {
                        Vec::new()
                    };
                    let shadows = shadows && !matches!(look, Look::Water(_));
                    let Some(source) = meshes.get(&mesh) else { continue };
                    let vertices = source.count_vertices().max(1);
                    // A far tile is seen whole or not at all, so its alike far versions merge as one.
                    if let Some(tile) = far
                        && merge
                        && !solid
                        && let Some(far_tile) = far_tiles.0.get_mut(&tile)
                    {
                        let key = far_key(&materials, &look, source);
                        far_tile.anchor.get_or_insert(entity);
                        commands.entity(entity).insert(FarMerging);
                        far_tile.add(
                            key,
                            look,
                            FarCopies { mesh, vertices, transforms: transforms.clone(), cursor: 0 },
                        );
                        continue;
                    }
                    if merge {
                        let squares: Vec<Vec<Transform>> = if shadows {
                            squares(&transforms, MERGED_SQUARE_M).collect()
                        } else {
                            vec![transforms.clone()]
                        };
                        for square in squares {
                            jobs.push_back(Job {
                                mesh: mesh.clone(),
                                material: material.clone(),
                                face_materials: face_materials.clone(),
                                look: look.clone(),
                                role,
                                shadows,
                                solid,
                                merge,
                                shadow_distance,
                                vertices,
                                transforms: square,
                                cursor: 0,
                                combined: None,
                            });
                        }
                    } else {
                        jobs.push_back(Job {
                            mesh,
                            material,
                            face_materials,
                            look,
                            role,
                            shadows,
                            solid,
                            merge,
                            shadow_distance,
                            vertices,
                            transforms: transforms.clone(),
                            cursor: 0,
                            combined: None,
                        });
                    }
                }
            }
            waiting.jobs = Some(jobs);
        }
        let jobs = waiting.jobs.as_mut().unwrap();
        place(jobs, entity, &mut meshes, &mut commands, &mut budget);
        if jobs.is_empty() {
            commands.entity(entity).remove::<Waiting>().insert(Placed(waiting.model.clone()));
        }
    }
    far_tiles.0.retain(|root, _| roots.contains(*root));
    let mut done = Vec::new();
    for (&root, tile) in &mut far_tiles.0 {
        let merging = tile.merge(&mut meshes, &mut budget);
        // A node whose model has not loaded yet may still bring far versions.
        if merging || tile.nodes.iter().any(|&node| waiting.get(node).is_ok_and(|(_, w)| w.jobs.is_none())) {
            continue;
        }
        for group in tile.groups.drain(..) {
            let (Some(anchor), Some(mesh)) = (tile.anchor, group.mesh) else { continue };
            let mut part = commands.spawn((Mesh3d(meshes.add(mesh)), Transform::IDENTITY, ChildOf(anchor)));
            insert_look(&mut part, &group.look);
            part.insert(NotShadowCaster);
        }
        for &node in &tile.nodes {
            if let Ok(mut node) = commands.get_entity(node) {
                node.remove::<FarMerging>();
            }
        }
        done.push(root);
    }
    for root in done {
        far_tiles.0.remove(&root);
    }
}

impl FarTile {
    /// Adds copies to the group they merge with, keeping each group's mesh within `MERGED_AT_MOST_VERTICES`.
    fn add(&mut self, key: FarKey, look: Look, copies: FarCopies) {
        let vertices = copies.vertices * copies.transforms.len();
        let group = match self
            .groups
            .iter_mut()
            .position(|group| group.key == key && group.vertices + vertices <= MERGED_AT_MOST_VERTICES)
        {
            Some(k) => &mut self.groups[k],
            None => {
                self.groups.push(FarGroup { key, look, vertices: 0, copies: VecDeque::new(), mesh: None });
                self.groups.last_mut().unwrap()
            }
        };
        group.vertices += vertices;
        group.copies.push_back(copies);
    }

    /// Merges what the budget allows of the tile's waiting copies; whether any are left.
    fn merge(&mut self, meshes: &mut Assets<Mesh>, budget: &mut Budget) -> bool {
        for group in &mut self.groups {
            while let Some(copies) = group.copies.front_mut() {
                if copies.cursor == copies.transforms.len() {
                    group.copies.pop_front();
                    continue;
                }
                let count = (budget.vertices / copies.vertices).min(copies.transforms.len() - copies.cursor);
                if count == 0 {
                    return true;
                }
                let range = copies.cursor..copies.cursor + count;
                copies.cursor += count;
                budget.vertices -= count * copies.vertices;
                let Some(chunk) = merged(meshes, &copies.mesh, &copies.transforms[range], false) else { continue };
                match &mut group.mesh {
                    Some(mesh) => {
                        if let Err(error) = mesh.merge(&chunk) {
                            warn!("far plants could not merge: {error}");
                        }
                    }
                    None => group.mesh = Some(chunk),
                }
            }
        }
        false
    }
}

/// Far parts merge when they show the same texture with the same wind, or the same material, and have the same vertex
/// attributes: each model's file has a material of its own, though the far versions all show one texture.
fn far_key(materials: &Materials, look: &Look, mesh: &Mesh) -> FarKey {
    let attributes = mesh.attributes().map(|(attribute, _)| attribute.id).collect();
    match look {
        Look::SourceFoliage(material, profile) => match materials.swaying.texture_of(material) {
            Some(texture) => (texture.untyped(), serde_json::to_string(profile).unwrap_or_default(), attributes),
            None => (material.id().untyped(), String::new(), attributes),
        },
        look => (look.id(), String::new(), attributes),
    }
}

/// @cc [owner:fontanierh,label:performance] bounded-scenery-placement
/// Each update MUST share one budget across all waiting scenery nodes, limiting merged vertices and unmerged copies.
/// Every valid queued copy MUST eventually be issued while its tile remains resident. A merged non-solid group without
/// per-chunk shadow range culling MUST become one mesh even when its preparation spans updates.
struct Budget {
    vertices: usize,
    instances: usize,
}

/// Issues a bounded part of a node's prepared work; the owner keeps its Waiting until the queue is empty.
fn place(
    jobs: &mut VecDeque<Job>,
    entity: Entity,
    meshes: &mut Assets<Mesh>,
    commands: &mut Commands,
    budget: &mut Budget,
) {
    while let Some(job) = jobs.front_mut() {
        if job.cursor == job.transforms.len() {
            jobs.pop_front();
            continue;
        }
        let (mesh, transform, count) = if job.merge {
            let count = (budget.vertices / job.vertices).min(job.transforms.len() - job.cursor);
            if count == 0 {
                break;
            }
            let range = job.cursor..job.cursor + count;
            let Some(combined) = merged(meshes, &job.mesh, &job.transforms[range], job.solid) else {
                job.cursor += count;
                budget.vertices -= count * job.vertices;
                continue;
            };
            budget.vertices -= count * job.vertices;
            // Keep each range-culled caster's existing chunk bounds: joining them could change which shadows it casts.
            let accumulate = !job.solid
                && !(job.shadows && matches!(job.role, Role::Both | Role::Shadow) && job.shadow_distance.is_some());
            if accumulate {
                match &mut job.combined {
                    Some(mesh) => mesh.merge(&combined).expect("chunks of the same mesh have matching attributes"),
                    None => job.combined = Some(combined),
                }
                job.cursor += count;
                if job.cursor < job.transforms.len() {
                    continue;
                }
                (meshes.add(job.combined.take().unwrap()), Transform::IDENTITY, 0)
            } else {
                (meshes.add(combined), Transform::IDENTITY, count)
            }
        } else {
            if budget.instances == 0 {
                break;
            }
            budget.instances -= 1;
            (job.mesh.clone(), job.transforms[job.cursor], 1)
        };
        let shadow_bounds = if job.shadows && matches!(job.role, Role::Both | Role::Shadow) {
            job.shadow_distance.and_then(|distance| {
                let VertexAttributeValues::Float32x3(positions) =
                    meshes.get(&mesh)?.attribute(Mesh::ATTRIBUTE_POSITION)?
                else {
                    return None;
                };
                Some(ShadowDistance {
                    distance,
                    bounds: Aabb::enclosing(positions.iter().copied().map(Vec3::from_array))?,
                    motion: match &job.look {
                        Look::SourceFoliage(_, profile) | Look::ShadowFoliage(_, profile) => {
                            let VertexAttributeValues::Float32x4(colours) =
                                meshes.get(&mesh)?.attribute(Mesh::ATTRIBUTE_COLOR)?
                            else {
                                return None;
                            };
                            let weight = colours.iter().map(|c| c[0].abs()).fold(0.0, f32::max);
                            Some(profile.shadow_motion_bound(weight))
                        }
                        Look::Still(_) | Look::Painted(_) | Look::Water(_) => Some((0.0, 0.0)),
                        // Unbounded motion cannot safely be range-culled.
                        Look::Swaying(_) | Look::MovingPainted(_) => return None,
                    },
                    world: None,
                })
            })
        } else {
            None
        };
        let source = if job.solid {
            Some(CollisionSource {
                mesh: job.mesh.clone(),
                material: job.material.clone(),
                face_materials: job.face_materials.clone(),
                // A merged mesh has identity placement. Retain each original instance, in source order.
                instances: if job.merge {
                    job.transforms[job.cursor..job.cursor + count].to_vec()
                } else {
                    vec![Transform::IDENTITY]
                },
            })
        } else {
            None
        };
        job.cursor += count;
        let mut part = commands.spawn((Mesh3d(mesh), transform, ChildOf(entity)));
        if let Some(source) = source {
            part.insert(source);
        }
        if let Some(bounds) = shadow_bounds {
            part.insert(bounds);
        }
        mark_solid(&mut part, job.solid);
        if !matches!(job.role, Role::Collision) {
            insert_look(&mut part, &job.look);
        }
        match job.role {
            Role::Both if job.shadows => {}
            Role::Both | Role::Seen => {
                part.insert(NotShadowCaster);
            }
            Role::Shadow => {
                part.insert(RenderLayers::layer(SHADOW_ONLY));
            }
            Role::Collision => {
                // Collision needs the visibility components but not a renderable view of this material-free mesh.
                part.insert((Visibility::Hidden, NotShadowCaster));
            }
        }
    }
}

/// Collision-only exports can omit materials. Recover each face's material only from an identical drawn face,
/// never a nearest surface: neighbouring layers and hidden contact faces keep their independent geometry.
fn collision_materials(gltf: &Gltf, models: &Models, meshes: &Assets<Mesh>, collision: &Handle<Mesh>) -> Vec<String> {
    let Some(full) = gltf
        .named_nodes
        .get("full")
        .and_then(|h| models.nodes.get(h))
        .and_then(|n| n.mesh.as_ref())
        .and_then(|h| models.meshes.get(h))
    else {
        return Vec::new();
    };
    let mut materials = std::collections::BTreeMap::new();
    for part in &full.primitives {
        let name = part
            .material
            .as_ref()
            .and_then(|h| gltf.named_materials.iter().find(|(_, m)| *m == h).map(|(n, _)| n.to_string()))
            .unwrap_or_default();
        if let Some(mesh) = meshes.get(&part.mesh) {
            for key in triangle_keys(mesh) {
                materials.entry(key).or_insert_with(|| name.clone());
            }
        }
    }
    meshes
        .get(collision)
        .map(|mesh| {
            triangle_keys(mesh).into_iter().map(|key| materials.get(&key).cloned().unwrap_or_default()).collect()
        })
        .unwrap_or_default()
}

fn triangle_keys(mesh: &Mesh) -> Vec<[[u32; 3]; 3]> {
    use bevy::mesh::{Indices, PrimitiveTopology};
    if mesh.primitive_topology() != PrimitiveTopology::TriangleList {
        return Vec::new();
    }
    let Some(points) = mesh.try_attribute(Mesh::ATTRIBUTE_POSITION).ok().and_then(|v| v.as_float3()) else {
        return Vec::new();
    };
    let Ok(indices) = mesh.try_indices_option() else { return Vec::new() };
    let count = match indices {
        Some(Indices::U16(v)) => v.len(),
        Some(Indices::U32(v)) => v.len(),
        None => points.len(),
    };
    (0..count / 3)
        .filter_map(|face| {
            let mut key = [[0; 3]; 3];
            for (i, p) in key.iter_mut().enumerate() {
                let index = match indices {
                    Some(Indices::U16(v)) => usize::from(v[face * 3 + i]),
                    Some(Indices::U32(v)) => v[face * 3 + i] as usize,
                    None => face * 3 + i,
                };
                *p = points.get(index)?.map(|f| if f == 0. { 0 } else { f.to_bits() });
            }
            key.sort();
            Some(key)
        })
        .collect()
}

fn insert_look(part: &mut EntityCommands, look: &Look) {
    match look {
        Look::Still(material) => part.insert(MeshMaterial3d(material.clone())),
        Look::Swaying(material) => part.insert(MeshMaterial3d(material.clone())),
        Look::SourceFoliage(material, _) => part.insert(MeshMaterial3d(material.clone())),
        Look::ShadowFoliage(material, _) => part.insert(MeshMaterial3d(material.clone())),
        Look::Painted(material) => part.insert(MeshMaterial3d(material.clone())),
        Look::MovingPainted(material) => part.insert(MeshMaterial3d(material.clone())),
        Look::Water(material) => part.insert(MeshMaterial3d(material.clone())),
    };
}

fn model_extras(node: &GltfNode) -> Option<ModelExtras> {
    node.extras.as_ref().and_then(|extras| serde_json::from_str(&extras.value).ok())
}

fn shadow_distance(node: &GltfNode) -> Result<Option<f32>, String> {
    let Some(extras) = &node.extras else { return Ok(None) };
    let value: serde_json::Value = serde_json::from_str(&extras.value).map_err(|e| e.to_string())?;
    let Some(raw) = value.get("shadow_distance_m") else { return Ok(None) };
    let distance = raw.as_f64().ok_or("shadow distance must be a number")? as f32;
    if !distance.is_finite() || distance <= 0.0 {
        return Err("shadow distance must be positive and finite".into());
    }
    Ok(Some(distance))
}

/// A declared caster range, independent of visible geometry and detail.
#[derive(Component)]
struct ShadowDistance {
    distance: f32,
    bounds: Aabb,
    // World-space horizontal motion: wind coefficient and maximum player push.
    motion: Option<(f32, f32)>,
    world: Option<(Vec3, Vec3)>,
}

type ShadowPart = (
    Entity,
    Ref<'static, GlobalTransform>,
    &'static mut ShadowDistance,
    Option<&'static MeshTag>,
    Has<NotShadowCaster>,
);

/// @cc [owner:fontanierh,label:correctness] scenery-shadow-range
/// A declared shadow range MUST affect only eligible casters, use the world camera and conservative world bounds,
/// and leave all casters enabled while the splash prepares their pipelines.
fn cull_shadows(
    mut commands: Commands,
    loaded: Option<Res<crate::loading::Loaded>>,
    camera: Query<&GlobalTransform, With<crate::WorldCamera>>,
    mut parts: Query<ShadowPart>,
) {
    let Ok(camera) = camera.single() else { return };
    for (entity, transform, mut range, tag, disabled) in &mut parts {
        if transform.is_changed() || range.world.is_none() {
            let matrix = transform.affine();
            let centre = matrix.transform_point3(Vec3::from(range.bounds.center));
            let extent = Vec3::from(range.bounds.half_extents);
            let world_extent = matrix.transform_vector3(Vec3::X * extent.x).abs()
                + matrix.transform_vector3(Vec3::Y * extent.y).abs()
                + matrix.transform_vector3(Vec3::Z * extent.z).abs();
            range.world = Some((centre, world_extent));
        }
        let (centre, extent) = range.world.unwrap();
        let (wind, push) = range.motion.unwrap_or((0.0, 0.0));
        let strength = tag.map_or(0.0, |tag| tag.value as f32 / 1000.0);
        let motion = wind * strength + push;
        let extent = extent + Vec3::new(motion, 0.0, motion);
        let outside = (camera.translation() - centre).abs() - extent;
        let should_disable = loaded.is_some() && outside.max(Vec3::ZERO).length_squared() > range.distance.powi(2);
        if should_disable && !disabled {
            commands.entity(entity).insert(NotShadowCaster);
        } else if !should_disable && disabled {
            commands.entity(entity).remove::<NotShadowCaster>();
        }
    }
}

fn mark_solid(part: &mut EntityCommands, solid: bool) {
    if solid {
        part.insert(built_solid());
    }
}

/// What a version of a model is spawned for.
#[derive(Clone, Copy)]
enum Role {
    /// To be seen and, if the model's extras let it, to cast its shadow.
    Both,
    /// To be seen only: a plant's full version, whose shadow its middle version casts.
    Seen,
    /// To cast its shadow only, never seen: a plant's middle version beside its full one. The sun's shadows are cast by
    /// far fewer leaves, and hold still as the camera moves.
    Shadow,
    /// An invisible, collision-only mesh, active only with its owning tile version.
    Collision,
}

impl Role {
    fn is_solid(self, model_is_solid: bool) -> bool {
        model_is_solid && !matches!(self, Role::Shadow | Role::Collision)
    }
}

type Parts = Vec<(Handle<Mesh>, Look)>;

/// `node`'s meshes, each with its look: a part whose vertices say how far they sway is drawn with the swaying version
/// of its material. None while a mesh or material is still loading.
fn parts(
    assets: &AssetServer,
    models: &Models,
    meshes: &Assets<Mesh>,
    materials: &mut Materials,
    node: &GltfNode,
    role: Role,
) -> Result<Option<Parts>, String> {
    let Some(mesh) = node.mesh.as_ref().and_then(|mesh| models.meshes.get(mesh)) else { return Ok(None) };
    let mut surface_profile = None;
    let mut motion_profile = None;
    let profile = if let Some(extras) = &node.extras {
        let value: serde_json::Value = serde_json::from_str(&extras.value).map_err(|e| e.to_string())?;
        motion_profile = value
            .get("vertex_motion")
            .map(|p| serde_json::from_value::<MotionProfile>(p.clone()))
            .transpose()
            .map_err(|e| e.to_string())?;
        surface_profile = value
            .get("surface_paint")
            .map(|p| serde_json::from_value::<SurfaceProfile>(p.clone()))
            .transpose()
            .map_err(|e| e.to_string())?
            .map(|p| p.profile());
        value
            .get("vertex_paint")
            .map(|p| serde_json::from_value::<Profile>(p.clone()))
            .transpose()
            .map_err(|e| e.to_string())?
    } else {
        None
    };
    if profile.as_ref().is_some_and(|p| !p.valid()) {
        return Err("invalid vertex paint parameters".into());
    }
    if motion_profile.as_ref().is_some_and(|p| !p.valid()) || (motion_profile.is_some() && profile.is_none()) {
        return Err("invalid painted motion parameters".into());
    }
    let source_foliage = if let Some(extras) = &node.extras {
        let value: serde_json::Value = serde_json::from_str(&extras.value).map_err(|e| e.to_string())?;
        value
            .get("source_foliage")
            .map(|p| serde_json::from_value::<SourceProfile>(p.clone()))
            .transpose()
            .map_err(|e| e.to_string())?
    } else {
        None
    };
    if source_foliage.as_ref().is_some_and(|p| !p.valid()) {
        return Err("invalid source foliage profile".into());
    }
    if surface_profile.as_ref().is_some_and(|p| !p.valid())
        || [profile.is_some(), surface_profile.is_some(), source_foliage.is_some()].into_iter().filter(|v| *v).count()
            > 1
    {
        return Err("invalid source surface paint parameters".into());
    }
    let shadow_textures: Option<Vec<Option<String>>> = if matches!(role, Role::Shadow) && source_foliage.is_some() {
        let extras = node.extras.as_ref().ok_or("shadow foliage needs texture metadata")?;
        let value: serde_json::Value = serde_json::from_str(&extras.value).map_err(|e| e.to_string())?;
        let entries: Vec<Option<String>> = serde_json::from_value(
            value.get("shadow_alpha_textures").cloned().ok_or("shadow foliage needs texture metadata")?,
        )
        .map_err(|e| e.to_string())?;
        if entries.len() != mesh.primitives.len() {
            return Err("shadow texture count does not match primitives".into());
        }
        Some(entries)
    } else {
        None
    };
    let mut parts = Vec::with_capacity(mesh.primitives.len());
    for (index, primitive) in mesh.primitives.iter().enumerate() {
        let Some(source) = meshes.get(&primitive.mesh) else { return Ok(None) };
        let material = standard_of(assets, primitive.material.as_ref());
        let look = if let Some(profile) = &profile {
            if let Some(motion) = &motion_profile {
                validate_paint(source, true)?;
                let Some(material) = materials.moving.of(&mut materials.painted, &material, profile, motion)? else {
                    return Ok(None);
                };
                Look::MovingPainted(material)
            } else {
                validate_static_paint(source)?;
                let Some(material) = materials.painted.of(&material, profile)? else { return Ok(None) };
                Look::Painted(material)
            }
        } else if let Some(profile) = &source_foliage {
            if !source.contains_attribute(Mesh::ATTRIBUTE_COLOR) || !source.contains_attribute(Mesh::ATTRIBUTE_UV_0) {
                return Err("source foliage needs colors and UVs".into());
            }
            let Some(material) = materials.swaying.source_of(&material, profile) else { return Ok(None) };
            if matches!(role, Role::Shadow) && materials.swaying.is_masked(&material) {
                let uri = shadow_textures
                    .as_ref()
                    .and_then(|v| v[index].as_deref())
                    .ok_or("masked shadow needs an alpha texture")?;
                if !uri.starts_with("textures/")
                    || !uri.ends_with(".alpha.ktx2")
                    || uri.split('/').any(|part| part == "..")
                {
                    return Err("invalid shadow alpha texture path".into());
                }
                let Some(shadow) = materials.swaying.shadow_of(&material, uri)? else { return Ok(None) };
                Look::ShadowFoliage(shadow, profile.clone())
            } else {
                Look::SourceFoliage(material, profile.clone())
            }
        } else if let Some(profile) = &surface_profile {
            // A source surface's vertex colour, if any, only shades its material's texture and colour.
            if source.contains_attribute(Mesh::ATTRIBUTE_UV_1)
                || source.contains_attribute(Mesh::ATTRIBUTE_JOINT_INDEX)
                || source.has_morph_targets()
            {
                return Err("source surface paint requires static geometry".into());
            }
            let Some(material) = materials.painted.of_surface(&material, profile)? else { return Ok(None) };
            Look::Painted(material)
        } else if source.contains_attribute(Mesh::ATTRIBUTE_UV_1) {
            let Some(material) = materials.swaying.of(&material) else { return Ok(None) };
            Look::Swaying(material)
        } else {
            Look::Still(material)
        };
        parts.push((primitive.mesh.clone(), look));
    }
    Ok(Some(parts))
}

/// Static painted assets must retain opaque RGB and cannot silently discard a motion-bearing alpha channel.
pub(crate) fn validate_static_paint(source: &Mesh) -> Result<(), String> {
    validate_paint(source, false)
}

fn validate_paint(source: &Mesh, motion: bool) -> Result<(), String> {
    use bevy::mesh::VertexAttributeValues;
    let Some(VertexAttributeValues::Float32x4(colors)) = source.attribute(Mesh::ATTRIBUTE_COLOR) else {
        return Err("vertex paint requires RGBA vertex colors".into());
    };
    if colors.iter().any(|c| {
        (!motion && c[3] != 0.0)
            || !c[3].is_finite()
            || !(0.0..=1.0).contains(&c[3])
            || c[..3].iter().any(|v| !v.is_finite() || !(0.0..=1.0).contains(v))
    }) {
        return Err("vertex paint requires valid RGB and declared motion weights in [0, 1]".into());
    }
    if !source.contains_attribute(Mesh::ATTRIBUTE_POSITION)
        || !source.contains_attribute(Mesh::ATTRIBUTE_NORMAL)
        || source.contains_attribute(Mesh::ATTRIBUTE_UV_1)
        || source.contains_attribute(Mesh::ATTRIBUTE_JOINT_INDEX)
        || source.has_morph_targets()
    {
        return Err("vertex paint requires static meshes with positions and normals".into());
    }
    Ok(())
}

/// How many vertices `node`'s meshes have, counting those loaded.
fn vertices(gltf_meshes: &Assets<GltfMesh>, meshes: &Assets<Mesh>, node: &GltfNode) -> usize {
    let Some(mesh) = node.mesh.as_ref().and_then(|mesh| gltf_meshes.get(mesh)) else { return 0 };
    mesh.primitives.iter().filter_map(|primitive| meshes.get(&primitive.mesh)).map(Mesh::count_vertices).sum()
}

/// Groups transforms into squares of the requested side length.
fn squares(transforms: &[Transform], side: f32) -> impl Iterator<Item = Vec<Transform>> {
    let mut squares: HashMap<IVec2, Vec<Transform>> = HashMap::default();
    for &transform in transforms {
        let square = (transform.translation.xz() / side).floor().as_ivec2();
        squares.entry(square).or_default().push(transform);
    }
    squares.into_values()
}

/// One mesh holding `mesh` once per transform. Solid meshes also stay on the CPU for raycasts.
fn merged(meshes: &Assets<Mesh>, mesh: &Handle<Mesh>, transforms: &[Transform], solid: bool) -> Option<Mesh> {
    let mesh = meshes.get(mesh)?;
    let mut merged = mesh.clone().transformed_by(*transforms.first()?);
    for &transform in &transforms[1..] {
        merged.merge(&mesh.clone().transformed_by(transform)).ok()?;
    }
    merged.asset_usage = if solid { RenderAssetUsages::default() } else { RenderAssetUsages::RENDER_WORLD };
    Some(merged)
}

/// How a part looks: its material as the model has it, or its swaying version.
#[derive(Clone)]
enum Look {
    Still(Handle<StandardMaterial>),
    Swaying(Handle<Swaying>),
    SourceFoliage(Handle<SourceFoliage>, SourceProfile),
    ShadowFoliage(Handle<ShadowFoliage>, SourceProfile),
    Painted(Handle<Painted>),
    MovingPainted(Handle<MovingPainted>),
    Water(Handle<WaterMaterial>),
}

impl Look {
    fn id(&self) -> UntypedAssetId {
        match self {
            Look::Still(material) => material.id().untyped(),
            Look::Swaying(material) => material.id().untyped(),
            Look::SourceFoliage(material, _) => material.id().untyped(),
            Look::ShadowFoliage(material, _) => material.id().untyped(),
            Look::Painted(material) => material.id().untyped(),
            Look::MovingPainted(material) => material.id().untyped(),
            Look::Water(material) => material.id().untyped(),
        }
    }
}

/// The standard material Bevy made from a glTF material: the material's own asset, labelled `<label>/std`.
fn standard_of(assets: &AssetServer, material: Option<&Handle<bevy::gltf::GltfMaterial>>) -> Handle<StandardMaterial> {
    let Some(path) = material.and_then(|material| material.path()) else { return Handle::default() };
    let label = format!("{}/std", path.label().unwrap_or_default());
    assets.load(path.clone().with_label(label))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn collision_material_keys_match_reordered_drawn_faces_not_nearby_layers() {
        use bevy::mesh::{Indices, PrimitiveTopology};
        let mut drawn = Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::MAIN_WORLD);
        drawn.insert_attribute(
            Mesh::ATTRIBUTE_POSITION,
            vec![[0., 0., 0.], [0., 0., 1.], [1., 0., 0.], [0., 0.01, 0.], [0., 0.01, 1.], [1., 0.01, 0.]],
        );
        drawn.insert_indices(Indices::U32(vec![0, 1, 2, 3, 4, 5]));
        let mut collision = drawn.clone();
        collision.insert_indices(Indices::U32(vec![2, 0, 1]));
        let keys = triangle_keys(&drawn);
        assert_eq!(triangle_keys(&collision)[0], keys[0]);
        assert_ne!(keys[0], keys[1], "a separate sheet cannot borrow this material");
    }

    #[test]
    fn static_paint_keeps_zero_weight_and_rejects_cloth() {
        let mut mesh = Mesh::from(Cuboid::new(1.0, 1.0, 1.0));
        let count = mesh.count_vertices();
        mesh.insert_attribute(Mesh::ATTRIBUTE_COLOR, vec![[0.25, 0.1, 0.05, 0.0]; count]);
        assert!(validate_static_paint(&mesh).is_ok());
        let mut colors = vec![[0.25, 0.1, 0.05, 0.0]; count];
        colors[0][3] = 0.5;
        mesh.insert_attribute(Mesh::ATTRIBUTE_COLOR, colors);
        assert!(validate_static_paint(&mesh).is_err());
        assert!(validate_paint(&mesh, true).is_ok());
        let mut colors = vec![[0.25, 0.1, 0.05, 0.0]; count];
        colors[0][3] = 1.5;
        mesh.insert_attribute(Mesh::ATTRIBUTE_COLOR, colors);
        assert!(validate_paint(&mesh, true).is_err());
        mesh.insert_attribute(Mesh::ATTRIBUTE_COLOR, vec![[0.25, 0.1, 0.05, 0.0]; count]);
        mesh.insert_attribute(Mesh::ATTRIBUTE_UV_1, vec![[0.5, 0.0]; count]);
        assert!(validate_static_paint(&mesh).is_err());
    }

    use crate::ground::{Ground, Surface};
    use bevy::camera::primitives::Aabb;
    use bevy::ecs::system::RunSystemOnce;

    #[derive(Component)]
    struct TestJobs(VecDeque<Job>);

    #[test]
    fn far_tile_merges_alike_models_into_one_mesh_across_updates() {
        let mut meshes = Assets::<Mesh>::default();
        let cube = meshes.add(Mesh::from(Cuboid::new(1.0, 1.0, 1.0)));
        let wedge = meshes.add(Mesh::from(Cuboid::new(2.0, 1.0, 1.0)));
        let vertices = meshes.get(&cube).unwrap().count_vertices();
        let copies = |mesh: &Handle<Mesh>, n: usize| FarCopies {
            mesh: mesh.clone(),
            vertices,
            transforms: (0..n).map(|x| Transform::from_xyz(x as f32, 0.0, 0.0)).collect(),
            cursor: 0,
        };
        let alike: FarKey = (AssetId::<Image>::default().untyped(), String::new(), vec![Mesh::ATTRIBUTE_POSITION.id]);
        let other: FarKey = (AssetId::<Image>::default().untyped(), String::new(), vec![Mesh::ATTRIBUTE_NORMAL.id]);
        let mut tile = FarTile::default();
        tile.add(alike.clone(), Look::Still(Handle::default()), copies(&cube, 30));
        tile.add(alike, Look::Still(Handle::default()), copies(&wedge, 20));
        tile.add(other, Look::Still(Handle::default()), copies(&cube, 5));
        assert_eq!(tile.groups.len(), 2);
        let mut updates = 0;
        loop {
            let mut budget = Budget { vertices: 10 * vertices, instances: INSTANCES_PER_UPDATE };
            updates += 1;
            if !tile.merge(&mut meshes, &mut budget) {
                break;
            }
            assert!(updates < 10, "merging must make progress");
        }
        assert!(updates > 1);
        let counts: Vec<_> = tile.groups.iter().map(|group| group.mesh.as_ref().unwrap().count_vertices()).collect();
        assert_eq!(counts, [50 * vertices, 5 * vertices]);
    }

    #[test]
    fn placement_budget_spreads_real_geometry_without_losing_copies() {
        for limit in [MERGE_VERTICES_PER_UPDATE / 2, MERGE_VERTICES_PER_UPDATE] {
            let mut app = App::new();
            app.add_plugins(MinimalPlugins).init_resource::<Assets<Mesh>>();
            let mesh = app.world_mut().resource_mut::<Assets<Mesh>>().add(Mesh::from(Cuboid::new(1.0, 1.0, 1.0)));
            let vertices = app.world().resource::<Assets<Mesh>>().get(&mesh).unwrap().count_vertices();
            let transforms: Vec<_> = (0..1200).map(|x| Transform::from_xyz(x as f32, 0.0, 0.0)).collect();
            let expected = merged(app.world().resource::<Assets<Mesh>>(), &mesh, &transforms, true).unwrap();
            let jobs = VecDeque::from([Job {
                mesh,
                material: String::new(),
                face_materials: Vec::new(),
                look: Look::Still(Handle::default()),
                role: Role::Both,
                shadows: true,
                solid: true,
                merge: true,
                shadow_distance: None,
                vertices,
                transforms,
                cursor: 0,
                combined: None,
            }]);
            let owner = app.world_mut().spawn(TestJobs(jobs)).id();
            let step = move |mut commands: Commands,
                             mut meshes: ResMut<Assets<Mesh>>,
                             mut nodes: Query<(Entity, &mut TestJobs)>| {
                let mut budget = Budget { vertices: limit, instances: INSTANCES_PER_UPDATE };
                for (entity, mut jobs) in &mut nodes {
                    place(&mut jobs.0, entity, &mut meshes, &mut commands, &mut budget);
                }
            };
            let mut updates = 0;
            while !app.world().get::<TestJobs>(owner).unwrap().0.is_empty() {
                app.world_mut().run_system_once(step).unwrap();
                updates += 1;
                assert!(updates <= 10, "placement must make progress");
            }
            assert!(updates > 1);
            let mut positions = Vec::new();
            for part in app.world().get::<Children>(owner).unwrap().iter() {
                let mesh = app.world().get::<Mesh3d>(part).unwrap();
                let chunk = app.world().resource::<Assets<Mesh>>().get(&mesh.0).unwrap();
                assert!(chunk.count_vertices() <= limit);
                positions.extend_from_slice(chunk.attribute(Mesh::ATTRIBUTE_POSITION).unwrap().as_float3().unwrap());
            }
            assert_eq!(positions, expected.attribute(Mesh::ATTRIBUTE_POSITION).unwrap().as_float3().unwrap());
        }
    }

    #[test]
    fn non_solid_merge_keeps_one_group_across_updates() {
        for (role, shadows) in [(Role::Seen, true), (Role::Shadow, true), (Role::Both, true), (Role::Both, false)] {
            let mut app = App::new();
            app.add_plugins(MinimalPlugins).init_resource::<Assets<Mesh>>().init_resource::<Assets<StandardMaterial>>();
            let mesh = app.world_mut().resource_mut::<Assets<Mesh>>().add(Mesh::from(Cuboid::new(1.0, 2.0, 3.0)));
            let material = app.world_mut().resource_mut::<Assets<StandardMaterial>>().add(StandardMaterial::default());
            let vertices = app.world().resource::<Assets<Mesh>>().get(&mesh).unwrap().count_vertices();
            let transforms: Vec<_> = (0..5)
                .map(|x| {
                    Transform::from_xyz(x as f32, 1.0, -2.0)
                        .with_rotation(Quat::from_rotation_y(x as f32 * 0.3))
                        .with_scale(Vec3::splat(0.5 + x as f32 * 0.1))
                })
                .collect();
            let expected = merged(app.world().resource::<Assets<Mesh>>(), &mesh, &transforms, false).unwrap();
            let owner = app
                .world_mut()
                .spawn(TestJobs(VecDeque::from([Job {
                    mesh,
                    material: String::new(),
                    face_materials: Vec::new(),
                    look: Look::Still(material.clone()),
                    role,
                    shadows,
                    solid: false,
                    merge: true,
                    shadow_distance: None,
                    vertices,
                    transforms,
                    cursor: 0,
                    combined: None,
                }])))
                .id();
            let step = move |mut commands: Commands,
                             mut meshes: ResMut<Assets<Mesh>>,
                             mut nodes: Query<(Entity, &mut TestJobs)>| {
                let mut budget = Budget { vertices: 2 * vertices, instances: INSTANCES_PER_UPDATE };
                for (entity, mut jobs) in &mut nodes {
                    place(&mut jobs.0, entity, &mut meshes, &mut commands, &mut budget);
                }
                budget.vertices
            };
            for expected_cursor in [2, 4] {
                assert_eq!(app.world_mut().run_system_once(step).unwrap(), 0);
                let job = app.world().get::<TestJobs>(owner).unwrap().0.front().unwrap();
                assert_eq!(job.cursor, expected_cursor);
                assert_eq!(job.combined.as_ref().unwrap().count_vertices(), expected_cursor * vertices);
                assert!(app.world().get::<Children>(owner).is_none());
            }
            assert_eq!(app.world_mut().run_system_once(step).unwrap(), vertices);
            assert!(app.world().get::<TestJobs>(owner).unwrap().0.is_empty());
            let children = app.world().get::<Children>(owner).unwrap();
            assert_eq!(children.len(), 1);
            let part = children[0];
            assert_eq!(app.world().get::<Transform>(part).unwrap(), &Transform::IDENTITY);
            assert_eq!(app.world().get::<MeshMaterial3d<StandardMaterial>>(part).unwrap().0, material);
            assert_eq!(app.world().get::<NotShadowCaster>(part).is_some(), !shadows || matches!(role, Role::Seen));
            assert_eq!(app.world().get::<RenderLayers>(part).is_some(), matches!(role, Role::Shadow));
            if matches!(role, Role::Shadow) {
                assert_eq!(app.world().get::<RenderLayers>(part).unwrap(), &RenderLayers::layer(SHADOW_ONLY));
            }
            assert!(app.world().get::<CollisionSource>(part).is_none());
            let result =
                app.world().resource::<Assets<Mesh>>().get(&app.world().get::<Mesh3d>(part).unwrap().0).unwrap();
            assert_eq!(result.primitive_topology(), expected.primitive_topology());
            assert_eq!(result.asset_usage, expected.asset_usage);
            for (attribute, values) in expected.attributes() {
                assert_eq!(result.attribute(attribute.id), Some(values));
            }
            assert_eq!(
                result.indices().unwrap().iter().collect::<Vec<_>>(),
                expected.indices().unwrap().iter().collect::<Vec<_>>()
            );
        }
    }

    #[test]
    fn range_limited_casters_keep_chunk_bounds() {
        let mut app = App::new();
        app.add_plugins(MinimalPlugins).init_resource::<Assets<Mesh>>();
        let mesh = app.world_mut().resource_mut::<Assets<Mesh>>().add(Mesh::from(Cuboid::new(1.0, 1.0, 1.0)));
        let vertices = app.world().resource::<Assets<Mesh>>().get(&mesh).unwrap().count_vertices();
        let owner = app
            .world_mut()
            .spawn(TestJobs(VecDeque::from([Job {
                mesh,
                material: String::new(),
                face_materials: Vec::new(),
                look: Look::Still(Handle::default()),
                role: Role::Shadow,
                shadows: true,
                solid: false,
                merge: true,
                shadow_distance: Some(80.0),
                vertices,
                transforms: vec![Transform::IDENTITY, Transform::from_xyz(5.0, 0.0, 0.0)],
                cursor: 0,
                combined: None,
            }])))
            .id();
        let step = move |mut commands: Commands,
                         mut meshes: ResMut<Assets<Mesh>>,
                         mut nodes: Query<(Entity, &mut TestJobs)>| {
            let mut budget = Budget { vertices, instances: INSTANCES_PER_UPDATE };
            for (entity, mut jobs) in &mut nodes {
                place(&mut jobs.0, entity, &mut meshes, &mut commands, &mut budget);
            }
        };
        app.world_mut().run_system_once(step).unwrap();
        app.world_mut().run_system_once(step).unwrap();
        let children = app.world().get::<Children>(owner).unwrap();
        assert_eq!(children.len(), 2);
        for (index, child) in children.iter().enumerate() {
            let bounds = &app.world().get::<ShadowDistance>(child).unwrap().bounds;
            assert!((bounds.center.x - index as f32 * 5.0).abs() < 0.001);
            assert_eq!(app.world().get::<RenderLayers>(child).unwrap(), &RenderLayers::layer(SHADOW_ONLY));
        }
    }

    #[test]
    fn shadow_range_marks_only_shadow_casting_roles() {
        let mut app = App::new();
        app.add_plugins(MinimalPlugins).init_resource::<Assets<Mesh>>();
        let mesh = app.world_mut().resource_mut::<Assets<Mesh>>().add(Mesh::from(Cuboid::new(1.0, 1.0, 1.0)));
        let jobs = [Role::Seen, Role::Shadow, Role::Both]
            .into_iter()
            .map(|role| Job {
                mesh: mesh.clone(),
                material: String::new(),
                face_materials: Vec::new(),
                look: Look::Still(Handle::default()),
                role,
                shadows: true,
                solid: false,
                merge: false,
                shadow_distance: Some(80.0),
                vertices: 24,
                transforms: vec![Transform::IDENTITY],
                cursor: 0,
                combined: None,
            })
            .collect();
        let owner = app.world_mut().spawn(TestJobs(jobs)).id();
        app.world_mut()
            .run_system_once(
                |mut commands: Commands,
                 mut meshes: ResMut<Assets<Mesh>>,
                 mut nodes: Query<(Entity, &mut TestJobs)>| {
                    let mut budget = Budget { vertices: MERGE_VERTICES_PER_UPDATE, instances: INSTANCES_PER_UPDATE };
                    for (entity, mut jobs) in &mut nodes {
                        place(&mut jobs.0, entity, &mut meshes, &mut commands, &mut budget);
                    }
                },
            )
            .unwrap();
        let children = app.world().get::<Children>(owner).unwrap();
        assert!(app.world().get::<NotShadowCaster>(children[0]).is_some());
        assert!(app.world().get::<ShadowDistance>(children[0]).is_none());
        for child in &children[1..] {
            assert!(app.world().get::<ShadowDistance>(*child).is_some());
            assert!(app.world().get::<NotShadowCaster>(*child).is_none());
        }
    }

    #[test]
    fn shadow_range_preserves_visibility_and_warms_before_culling() {
        let mut app = App::new();
        let camera = app.world_mut().spawn((crate::WorldCamera, GlobalTransform::IDENTITY)).id();
        let bounds = Aabb { center: Vec3::new(2.0, 0.0, 0.0).into(), half_extents: Vec3::splat(1.0).into() };
        let part = app
            .world_mut()
            .spawn((
                ShadowDistance { distance: 80.0, bounds, motion: Some((0.0, 0.0)), world: None },
                GlobalTransform::from(Transform::from_xyz(100.0, 0.0, 0.0)),
                Visibility::Inherited,
            ))
            .id();
        app.world_mut().run_system_once(cull_shadows).unwrap();
        assert!(app.world().get::<NotShadowCaster>(part).is_none());
        app.insert_resource(crate::loading::Loaded::default());
        app.world_mut().run_system_once(cull_shadows).unwrap();
        assert!(app.world().get::<NotShadowCaster>(part).is_some());
        assert_eq!(*app.world().get::<Visibility>(part).unwrap(), Visibility::Inherited);
        app.world_mut().entity_mut(camera).insert(GlobalTransform::from(Transform::from_xyz(25.0, 0.0, 0.0)));
        app.world_mut().run_system_once(cull_shadows).unwrap();
        assert!(app.world().get::<NotShadowCaster>(part).is_none());
    }

    #[test]
    fn shadow_range_uses_transformed_bounds_and_motion_at_boundary() {
        let mut app = App::new();
        app.insert_resource(crate::loading::Loaded::default());
        let camera = app.world_mut().spawn((crate::WorldCamera, GlobalTransform::IDENTITY)).id();
        let part = app
            .world_mut()
            .spawn((
                ShadowDistance {
                    distance: 80.0,
                    bounds: Aabb { center: Vec3::ZERO.into(), half_extents: Vec3::new(2.0, 1.0, 4.0).into() },
                    motion: Some((1.0, 0.5)),
                    world: None,
                },
                GlobalTransform::from(
                    Transform::from_xyz(0.0, 0.0, 0.0)
                        .with_rotation(Quat::from_rotation_y(std::f32::consts::FRAC_PI_2))
                        .with_scale(Vec3::new(2.0, 1.0, 0.5)),
                ),
                MeshTag::new(1000),
            ))
            .id();
        // Rotated extent along X is 2 m; wind and push add 1.5 m.
        app.world_mut().entity_mut(camera).insert(GlobalTransform::from(Transform::from_xyz(83.5, 0.0, 0.0)));
        app.world_mut().run_system_once(cull_shadows).unwrap();
        assert!(app.world().get::<NotShadowCaster>(part).is_none());
        app.world_mut().entity_mut(camera).insert(GlobalTransform::from(Transform::from_xyz(83.51, 0.0, 0.0)));
        app.world_mut().run_system_once(cull_shadows).unwrap();
        assert!(app.world().get::<NotShadowCaster>(part).is_some());
        // Wind changes update the padding without changing the cached geometry.
        app.world_mut().entity_mut(part).insert(MeshTag::new(2000));
        app.world_mut().run_system_once(cull_shadows).unwrap();
        assert!(app.world().get::<NotShadowCaster>(part).is_none());
        app.world_mut().entity_mut(part).insert(MeshTag::new(1000));
        app.world_mut().run_system_once(cull_shadows).unwrap();
        assert!(app.world().get::<NotShadowCaster>(part).is_some());
        // Changed transforms invalidate the cached bounds.
        app.world_mut().entity_mut(part).insert(GlobalTransform::from(
            Transform::from_xyz(1.0, 0.0, 0.0)
                .with_rotation(Quat::from_rotation_y(std::f32::consts::FRAC_PI_2))
                .with_scale(Vec3::new(2.0, 1.0, 0.5)),
        ));
        app.world_mut().run_system_once(cull_shadows).unwrap();
        assert!(app.world().get::<NotShadowCaster>(part).is_none());
    }

    #[test]
    fn unmerged_copies_obey_shared_update_budget() {
        let mut app = App::new();
        app.add_plugins(MinimalPlugins).init_resource::<Assets<Mesh>>();
        let mesh = app.world_mut().resource_mut::<Assets<Mesh>>().add(Mesh::from(Cuboid::new(1.0, 1.0, 1.0)));
        let count = INSTANCES_PER_UPDATE * 2 + 3;
        let transforms: Vec<_> = (0..count).map(|x| Transform::from_xyz(x as f32, 0.0, 0.0)).collect();
        let jobs = VecDeque::from([Job {
            mesh,
            material: String::new(),
            face_materials: Vec::new(),
            look: Look::Still(Handle::default()),
            role: Role::Both,
            shadows: true,
            solid: false,
            merge: false,
            shadow_distance: None,
            vertices: 1,
            transforms,
            cursor: 0,
            combined: None,
        }]);
        let owner = app.world_mut().spawn(TestJobs(jobs)).id();
        let step =
            |mut commands: Commands, mut meshes: ResMut<Assets<Mesh>>, mut nodes: Query<(Entity, &mut TestJobs)>| {
                let mut budget = Budget { vertices: MERGE_VERTICES_PER_UPDATE, instances: INSTANCES_PER_UPDATE };
                for (entity, mut jobs) in &mut nodes {
                    place(&mut jobs.0, entity, &mut meshes, &mut commands, &mut budget);
                }
            };
        let mut previous = 0;
        while !app.world().get::<TestJobs>(owner).unwrap().0.is_empty() {
            app.world_mut().run_system_once(step).unwrap();
            let current = app.world().get::<Children>(owner).map_or(0, |children| children.len());
            assert!(current > previous && current - previous <= INSTANCES_PER_UPDATE);
            previous = current;
        }
        assert_eq!(previous, count);
        for (index, child) in app.world().get::<Children>(owner).unwrap().iter().enumerate() {
            assert_eq!(app.world().get::<Transform>(child).unwrap().translation.x, index as f32);
        }
    }

    #[test]
    fn collision_only_parts_are_invisible_and_follow_tile_activation() {
        for merge in [false, true] {
            let mut app = App::new();
            app.add_plugins((MinimalPlugins, bevy::camera::visibility::VisibilityPlugin))
                .init_resource::<Assets<Mesh>>()
                .init_resource::<Assets<bevy::mesh::skinning::SkinnedMeshInverseBindposes>>();
            let mesh = app.world_mut().resource_mut::<Assets<Mesh>>().add(Mesh::from(Cuboid::new(1.0, 1.0, 1.0)));
            app.world_mut().spawn((Camera::default(), bevy::camera::visibility::NoCpuCulling));
            let root = app
                .world_mut()
                .spawn((
                    Visibility::Visible,
                    TestJobs(VecDeque::from([Job {
                        mesh,
                        material: String::new(),
                        face_materials: Vec::new(),
                        look: Look::Still(Handle::default()),
                        role: Role::Collision,
                        shadows: false,
                        solid: true,
                        merge,
                        shadow_distance: None,
                        vertices: 24,
                        transforms: vec![Transform::from_xyz(4.0, 0.0, 0.0)],
                        cursor: 0,
                        combined: None,
                    }])),
                ))
                .id();
            app.world_mut()
                .run_system_once(
                    |mut commands: Commands,
                     mut meshes: ResMut<Assets<Mesh>>,
                     mut owners: Query<(Entity, &mut TestJobs)>| {
                        let mut budget =
                            Budget { vertices: MERGE_VERTICES_PER_UPDATE, instances: INSTANCES_PER_UPDATE };
                        for (owner, mut jobs) in &mut owners {
                            place(&mut jobs.0, owner, &mut meshes, &mut commands, &mut budget);
                        }
                    },
                )
                .unwrap();
            let part = app.world().get::<Children>(root).unwrap()[0];
            assert!(app.world().get::<MeshMaterial3d<StandardMaterial>>(part).is_none());
            assert!(app.world().get::<NotShadowCaster>(part).is_some());
            assert_eq!(app.world().get::<Visibility>(part), Some(&Visibility::Hidden));
            assert!(app.world().get::<crate::ground::PendingSolid>(part).is_some());
            let transform = *app.world().get::<Transform>(part).unwrap();
            app.world_mut().entity_mut(part).insert(GlobalTransform::from(transform));
            app.world_mut().run_system_once(bevy::camera::visibility::calculate_bounds).unwrap();
            assert!(app.world().get::<Aabb>(part).is_some());
            app.world_mut().run_schedule(PostUpdate);
            use bevy::camera::visibility::{InheritedVisibility, ViewVisibility};
            // These remain present for physics, even after Bevy propagates hidden visibility.
            assert!(!app.world().get::<InheritedVisibility>(part).unwrap().get());
            assert!(!app.world().get::<ViewVisibility>(part).unwrap().get());
            let cast = |mut ground: Ground| ground.cast(Vec3::new(4.0, 5.0, 0.0), Dir3::NEG_Y, 10.0);
            let sweep = |ground: Ground| ground.sweep_capsule(Vec3::new(4.0, 2.0, 0.0), 0.25, 1.0, Vec3::NEG_Y * 3.0);
            assert!(app.world_mut().run_system_once(cast).unwrap().is_none());
            assert!(app.world_mut().run_system_once(sweep).unwrap().unwrap().is_none());
            app.world_mut()
                .run_system_once(
                    move |mut commands: Commands,
                          children: Query<&Children>,
                          pending: Query<&crate::ground::PendingSolid>| {
                        crate::ground::promote(root, &children, &pending, &mut commands);
                    },
                )
                .unwrap();
            assert!(app.world_mut().run_system_once(cast).unwrap().is_some());
            assert!(app.world_mut().run_system_once(sweep).unwrap().unwrap().is_some());
            app.world_mut().entity_mut(root).despawn();
            assert!(app.world_mut().run_system_once(cast).unwrap().is_none());
            assert!(app.world_mut().run_system_once(sweep).unwrap().unwrap().is_none());
        }
    }

    #[test]
    fn scenery_rays_hit_merged_and_transformed_visible_copies_only() {
        let mut app = App::new();
        app.add_plugins(MinimalPlugins).init_resource::<Assets<Mesh>>();
        let (cube, combined) = {
            let mut meshes = app.world_mut().resource_mut::<Assets<Mesh>>();
            let cube = meshes.add(Mesh::from(Cuboid::new(1.0, 1.0, 1.0)));
            let copies = [Transform::from_xyz(4.0, 0.0, 0.0), Transform::from_xyz(6.0, 0.0, 0.0)];
            let combined = merged(&meshes, &cube, &copies, true).unwrap();
            assert!(combined.asset_usage.contains(RenderAssetUsages::MAIN_WORLD));
            (cube, meshes.add(combined))
        };

        let root = app.world_mut().spawn_empty().id();
        let mut commands = app.world_mut().commands();
        for (mesh, transform, bounds, role, solid) in [
            (
                combined,
                Transform::IDENTITY,
                Aabb::from_min_max(Vec3::new(3.5, -0.5, -0.5), Vec3::new(6.5, 0.5, 0.5)),
                Role::Both,
                true,
            ),
            (
                cube.clone(),
                Transform::from_xyz(10.0, 0.0, 0.0),
                Aabb::from_min_max(Vec3::splat(-0.5), Vec3::splat(0.5)),
                Role::Seen,
                true,
            ),
            (
                cube.clone(),
                Transform::from_xyz(14.0, 0.0, 0.0),
                Aabb::from_min_max(Vec3::splat(-0.5), Vec3::splat(0.5)),
                Role::Both,
                false,
            ),
            (
                cube,
                Transform::from_xyz(18.0, 0.0, 0.0),
                Aabb::from_min_max(Vec3::splat(-0.5), Vec3::splat(0.5)),
                Role::Shadow,
                true,
            ),
        ] {
            let mut part = commands.spawn((
                Mesh3d(mesh),
                transform,
                GlobalTransform::from(transform),
                bounds,
                Visibility::default(),
                ChildOf(root),
            ));
            mark_solid(&mut part, role.is_solid(solid));
        }
        app.world_mut().flush();
        app.world_mut()
            .run_system_once(
                move |mut commands: Commands,
                      children: Query<&Children>,
                      pending: Query<&crate::ground::PendingSolid>| {
                    crate::ground::promote(root, &children, &pending, &mut commands);
                },
            )
            .unwrap();
        let hits = app
            .world_mut()
            .run_system_once(|mut ground: Ground| {
                [4.0, 6.0, 10.0, 14.0, 18.0].map(|x| ground.cast(Vec3::new(x, 5.0, 0.0), Dir3::NEG_Y, 10.0))
            })
            .unwrap();
        for hit in &hits[..3] {
            let hit = hit.expect("visible solid copy should collide");
            assert_eq!(hit.surface, Surface::Built);
            assert!((hit.point.y - 0.5).abs() < 1e-5);
        }
        assert!(hits[3].is_none(), "non-solid copy must not collide");
        assert!(hits[4].is_none(), "shadow-only copy must not collide");
    }
}
