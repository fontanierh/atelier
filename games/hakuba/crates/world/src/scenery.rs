//! The models standing in the tiles: trees, bushes, grass and poles. A tile holds one data node per model, naming the
//! model and listing where each copy stands. Once the model has loaded, each copy of a large model, such as a tree, is
//! spawned with the model's own meshes and materials, shared by every copy, so Bevy draws them together, in one call
//! across every tile. The copies of a small model, such as a tuft of grass, are merged instead, into one mesh per
//! square: shadow-casting models use 16 m squares and others use 32 m. Thousands of entities would cost more to cull
//! one by one than their few vertices cost together, and squares out of view are not drawn. Merging a large model
//! would not pay: each merged mesh is drawn on its own.
//!
//! A plant in a full tile shows its full version wherever the camera is, so it never changes as the player walks up to
//! it, and casts the shadow of its middle version, which is never seen: the sun's shadow maps draw far fewer leaves.

use std::collections::VecDeque;

use bevy::asset::RenderAssetUsages;
use bevy::camera::primitives::Aabb;
use bevy::camera::visibility::RenderLayers;
use bevy::ecs::system::EntityCommands;
use bevy::ecs::system::SystemParam;
use bevy::gltf::{Gltf, GltfExtras, GltfMesh, GltfNode};
use bevy::light::NotShadowCaster;
use bevy::mesh::{MeshTag, VertexAttributeValues};
use bevy::platform::collections::HashMap;
use bevy::prelude::*;
use bevy::world_serialization::WorldAssetRoot;
use serde::Deserialize;

use crate::ground::built_solid;
use crate::loading::Missing;
use crate::look::SHADOW_ONLY;
use crate::tiles::TILES;
use crate::vertex_paint::{
    MotionProfile, MovingPainted, MovingPaintedMaterials, Painted, PaintedMaterials, Profile, SurfaceProfile,
};
use crate::water::{WaterMaterial, WaterMaterials};
use crate::wind::{ShadowFoliage, SourceFoliage, SourceProfile, Swaying, SwayingMaterials};

/// A model with fewer vertices than this has its copies merged.
const MERGE_BELOW_VERTICES: usize = 256;

/// The side of the squares whose copies of a small model are merged together, in metres: small enough that the camera
/// sees few squares it does not need, since every vertex of grass costs its swaying in the prepass and the main pass,
/// large enough to stay a few hundred meshes.
const MERGED_SQUARE_M: f32 = 16.0;

/// The most vertices one tile's merged copies of a model may hold: past this, merging costs more memory than it saves.
const MERGED_AT_MOST_VERTICES: usize = 500_000;
/// Work issued to the renderer each update while tile scenery is being prepared.
const MERGE_VERTICES_PER_UPDATE: usize = 20_000;
const INSTANCES_PER_UPDATE: usize = 64;

pub struct SceneryPlugin;

impl Plugin for SceneryPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Update, (read, spawn).chain().in_set(Placing)).add_systems(
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
    instances: Vec<f32>,
    jobs: Option<VecDeque<Job>>,
}

struct Job {
    mesh: Handle<Mesh>,
    look: Look,
    role: Role,
    shadows: bool,
    solid: bool,
    merge: bool,
    shadow_distance: Option<f32>,
    vertices: usize,
    transforms: Vec<Transform>,
    cursor: usize,
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
        let waiting = Waiting {
            model: assets.load(model),
            middle: copies.detail == "middle",
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
/// `full` node otherwise. A full tile shows the `full` node, and a model that has a `middle` node casts that one's
/// shadow instead.
fn spawn(
    mut commands: Commands,
    assets: Res<AssetServer>,
    mut waiting: Query<(Entity, &mut Waiting)>,
    models: Models,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: Materials,
) {
    let mut budget = Budget { vertices: MERGE_VERTICES_PER_UPDATE, instances: INSTANCES_PER_UPDATE };
    'copies: for (entity, mut waiting) in &mut waiting {
        if waiting.jobs.is_none() {
            if assets.load_state(&waiting.model).is_failed() {
                commands.entity(entity).remove::<Waiting>();
                continue;
            }
            let Some(gltf) = models.gltfs.get(&waiting.model) else { continue };
            let Some(full_handle) = gltf.named_nodes.get("full") else {
                warn!("a model has no full node");
                commands.entity(entity).remove::<Waiting>();
                continue;
            };
            let Some(full) = models.nodes.get(full_handle) else { continue };
            let collision = gltf.named_nodes.contains_key("collision");
            let solid = !collision && model_extras(full).is_some_and(|extras| extras.solid);
            let mut versions = match (waiting.middle, gltf.named_nodes.contains_key("middle")) {
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
                    let merge = merge && look.can_merge();
                    let shadows = shadows && !matches!(look, Look::Water(_));
                    let vertices = meshes.get(&mesh).map_or(0, Mesh::count_vertices).max(1);
                    if merge {
                        for square in squares(&transforms, if shadows { MERGED_SQUARE_M } else { 32.0 }) {
                            jobs.push_back(Job {
                                mesh: mesh.clone(),
                                look: look.clone(),
                                role,
                                shadows,
                                solid,
                                merge,
                                shadow_distance,
                                vertices,
                                transforms: square,
                                cursor: 0,
                            });
                        }
                    } else {
                        jobs.push_back(Job {
                            mesh,
                            look,
                            role,
                            shadows,
                            solid,
                            merge,
                            shadow_distance,
                            vertices,
                            transforms: transforms.clone(),
                            cursor: 0,
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
}

/// @cc [owner:fontanierh,label:performance] bounded-scenery-placement
/// Each update MUST share one budget across all waiting scenery nodes, limiting merged vertices and unmerged copies.
/// Every valid queued copy MUST eventually be issued while its tile remains resident.
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
            (meshes.add(combined), Transform::IDENTITY, count)
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
                        Look::Swaying(_) | Look::MovingPainted(_, _) => return None,
                    },
                    world: None,
                })
            })
        } else {
            None
        };
        job.cursor += count;
        let mut part = commands.spawn((Mesh3d(mesh), transform, ChildOf(entity)));
        if let Some(bounds) = shadow_bounds {
            part.insert(bounds);
        }
        if let Look::MovingPainted(_, motion) = &job.look
            && let Some(VertexAttributeValues::Float32x3(positions)) =
                meshes.get(&job.mesh).and_then(|mesh| mesh.attribute(Mesh::ATTRIBUTE_POSITION))
            && let Some(mut bounds) = Aabb::enclosing(positions.iter().copied().map(Vec3::from_array))
        {
            // Motion is world-space; bound every direction in local space despite rotation and scale.
            let radius = Vec3::from_array(motion.amplitude).length() / transform.scale.abs().min_element();
            bounds.half_extents += radius;
            part.insert(bounds);
        }
        mark_solid(&mut part, job.solid);
        if !matches!(job.role, Role::Collision) {
            match &job.look {
                Look::Still(material) => part.insert(MeshMaterial3d(material.clone())),
                Look::Swaying(material) => part.insert(MeshMaterial3d(material.clone())),
                Look::SourceFoliage(material, _) => part.insert(MeshMaterial3d(material.clone())),
                Look::ShadowFoliage(material, _) => part.insert(MeshMaterial3d(material.clone())),
                Look::Painted(material) => part.insert(MeshMaterial3d(material.clone())),
                Look::MovingPainted(material, _) => part.insert(MeshMaterial3d(material.clone())),
                Look::Water(material) => part.insert(MeshMaterial3d(material.clone())),
            };
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
                // A mesh without a material is never drawn; visibility components allow active tile raycasts.
                part.insert((Visibility::Inherited, NotShadowCaster));
            }
        }
    }
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
            let Some(painted) = painted_part(
                source,
                &material,
                profile,
                motion_profile.as_ref(),
                &mut materials.painted,
                &mut materials.moving,
            )?
            else {
                return Ok(None);
            };
            match painted {
                PaintedPart::Static(material) => Look::Painted(material),
                PaintedPart::Moving(material, motion) => Look::MovingPainted(material, motion),
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
            if source.contains_attribute(Mesh::ATTRIBUTE_COLOR)
                || source.contains_attribute(Mesh::ATTRIBUTE_UV_1)
                || source.contains_attribute(Mesh::ATTRIBUTE_JOINT_INDEX)
                || source.has_morph_targets()
            {
                return Err("source surface paint requires static uncoloured geometry".into());
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

/// A source-painted mesh and its shared material, with optional authored motion.
pub(crate) enum PaintedPart {
    Static(Handle<Painted>),
    Moving(Handle<MovingPainted>, MotionProfile),
}

/// Prepare the same painted surface for scenery and attachments, waiting for its source material.
pub(crate) fn painted_part(
    mesh: &Mesh,
    material: &Handle<StandardMaterial>,
    profile: &Profile,
    motion: Option<&MotionProfile>,
    painted: &mut PaintedMaterials,
    moving: &mut MovingPaintedMaterials,
) -> Result<Option<PaintedPart>, String> {
    if !profile.valid() || motion.is_some_and(|value| !value.valid()) {
        return Err("invalid painted surface or motion profile".into());
    }
    if profile.texture_mask && !mesh.contains_attribute(Mesh::ATTRIBUTE_UV_0) {
        return Err("textured vertex paint requires UV0".into());
    }
    validate_paint(mesh, motion.is_some())?;
    if let Some(motion) = motion {
        Ok(moving.of(painted, material, profile, motion)?.map(|handle| PaintedPart::Moving(handle, motion.clone())))
    } else {
        Ok(painted.of(material, profile)?.map(PaintedPart::Static))
    }
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
    MovingPainted(Handle<MovingPainted>, MotionProfile),
    Water(Handle<WaterMaterial>),
}

impl Look {
    /// World-space vertex motion must keep its instance transform and phase.
    fn can_merge(&self) -> bool {
        !matches!(self, Self::MovingPainted(_, _))
    }
}

/// The standard material Bevy made from a glTF material: the material's own asset, labelled `<label>/std`.
pub(crate) fn standard_of(
    assets: &AssetServer,
    material: Option<&Handle<bevy::gltf::GltfMaterial>>,
) -> Handle<StandardMaterial> {
    let Some(path) = material.and_then(|material| material.path()) else { return Handle::default() };
    let label = format!("{}/std", path.label().unwrap_or_default());
    assets.load(path.clone().with_label(label))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn moving_paint_keeps_instances_and_expands_bounds() {
        let motion = MotionProfile {
            spatial: [0.3, 0.4],
            rate: 2.1,
            amplitude: [0.024, 0.005, 0.016],
            harmonic: [1.0, 1.4, 0.85],
        };
        let look = Look::MovingPainted(Handle::default(), motion.clone());
        assert!(!look.can_merge());
        assert!(Look::Still(Handle::default()).can_merge());
        let mut app = App::new();
        app.add_plugins(MinimalPlugins).init_resource::<Assets<Mesh>>();
        let mesh = app.world_mut().resource_mut::<Assets<Mesh>>().add(Mesh::from(Cuboid::new(1.0, 1.0, 1.0)));
        let jobs = VecDeque::from([Job {
            mesh,
            look,
            role: Role::Both,
            shadows: true,
            solid: false,
            merge: false,
            shadow_distance: None,
            vertices: 24,
            transforms: vec![Transform::from_scale(Vec3::splat(0.5))],
            cursor: 0,
        }]);
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
        let child = app.world().get::<Children>(owner).unwrap()[0];
        let bound = app.world().get::<Aabb>(child).unwrap();
        let radius = Vec3::from_array(motion.amplitude).length() / 0.5;
        assert!((bound.half_extents.x - (0.5 + radius)).abs() < 1e-6);
        assert!((bound.half_extents.y - (0.5 + radius)).abs() < 1e-6);
        assert!((bound.half_extents.z - (0.5 + radius)).abs() < 1e-6);
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
                look: Look::Still(Handle::default()),
                role: Role::Both,
                shadows: true,
                solid: true,
                merge: true,
                shadow_distance: None,
                vertices,
                transforms,
                cursor: 0,
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
    fn shadow_range_marks_only_shadow_casting_roles() {
        let mut app = App::new();
        app.add_plugins(MinimalPlugins).init_resource::<Assets<Mesh>>();
        let mesh = app.world_mut().resource_mut::<Assets<Mesh>>().add(Mesh::from(Cuboid::new(1.0, 1.0, 1.0)));
        let jobs = [Role::Seen, Role::Shadow, Role::Both]
            .into_iter()
            .map(|role| Job {
                mesh: mesh.clone(),
                look: Look::Still(Handle::default()),
                role,
                shadows: true,
                solid: false,
                merge: false,
                shadow_distance: Some(80.0),
                vertices: 24,
                transforms: vec![Transform::IDENTITY],
                cursor: 0,
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
            look: Look::Still(Handle::default()),
            role: Role::Both,
            shadows: true,
            solid: false,
            merge: false,
            shadow_distance: None,
            vertices: 1,
            transforms,
            cursor: 0,
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
            app.add_plugins(MinimalPlugins).init_resource::<Assets<Mesh>>();
            let mesh = app.world_mut().resource_mut::<Assets<Mesh>>().add(Mesh::from(Cuboid::new(1.0, 1.0, 1.0)));
            let root = app
                .world_mut()
                .spawn(TestJobs(VecDeque::from([Job {
                    mesh,
                    look: Look::Still(Handle::default()),
                    role: Role::Collision,
                    shadows: false,
                    solid: true,
                    merge,
                    shadow_distance: None,
                    vertices: 24,
                    transforms: vec![Transform::from_xyz(4.0, 0.0, 0.0)],
                    cursor: 0,
                }])))
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
            assert!(app.world().get::<crate::ground::PendingSolid>(part).is_some());
            let transform = *app.world().get::<Transform>(part).unwrap();
            app.world_mut().entity_mut(part).insert(GlobalTransform::from(transform));
            app.world_mut().run_system_once(bevy::camera::visibility::calculate_bounds).unwrap();
            assert!(app.world().get::<Aabb>(part).is_some());
            let cast = |mut ground: Ground| ground.cast(Vec3::new(4.0, 5.0, 0.0), Dir3::NEG_Y, 10.0);
            assert!(app.world_mut().run_system_once(cast).unwrap().is_none());
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
            app.world_mut().entity_mut(root).despawn();
            assert!(app.world_mut().run_system_once(cast).unwrap().is_none());
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
