//! Playtest: the distant land drawn in blocks, as Unreal's hierarchical levels of detail do. Beyond `BLOCK_M` from
//! the camera, the meshes of the far tiles in each block of 8 × 8 tiles (512 m) merge into one mesh per look, so
//! the GPU draws a few hundred meshes for the land past a kilometre instead of thousands; the tiles' own meshes hide
//! meanwhile. A merged mesh holds the very vertices of the meshes it replaces, so nothing changes on screen as a tile
//! joins or leaves its block.
//!
//! `HAKUBA_BLOCK_M=0` turns it off.

use std::collections::{HashMap, HashSet};

use bevy::asset::{RenderAssetUsages, UntypedAssetId};
use bevy::camera::visibility::{VisibilityRange, VisibilitySystems};
use bevy::light::NotShadowCaster;
use bevy::mesh::{Indices, MeshVertexAttributeId};
use bevy::prelude::*;
use bevy::transform::TransformSystems;
use hakuba_screens::Screen;

use crate::scenery::{Look, insert_look};
use crate::tiles::Tile;
use crate::vertex_paint::{MovingPainted, Painted};
use crate::wind::Swaying;

/// How far from the camera, to a tile's centre, a far tile joins its block.
const BLOCK_M: f32 = 900.0;
/// A block's side, in tiles.
const BLOCK_TILES: u32 = 8;
/// A tile stays in or out of its block for this many metres past `BLOCK_M`, so a camera moving to and fro there
/// does not rebuild the block each frame.
const HYSTERESIS_M: f32 = 8.0;
/// The most blocks merged in one frame.
const MERGES_PER_FRAME: usize = 1;
/// A block merges again only once its tiles have stopped changing for this long: they stream their plants in over
/// many frames, and each merge costs milliseconds.
const SETTLE_S: f32 = 0.5;
/// The most vertices in one merged mesh.
const MOST_VERTICES: usize = 1 << 20;
/// How many pixels a block's clustered plants may stray from their own shapes, seen from its nearest point.
const PLANT_ERROR_PX: f32 = 1.0;
/// How many metres one pixel spans per metre away, 1440 pixels tall in the walker's 68° view.
const PIXEL_M_PER_M: f32 = 0.00094;

fn plant_error_px() -> f32 {
    static V: std::sync::OnceLock<f32> = std::sync::OnceLock::new();
    *V.get_or_init(|| std::env::var("HAKUBA_BLOCK_PX").ok().and_then(|v| v.parse().ok()).unwrap_or(PLANT_ERROR_PX))
}

fn block_m() -> f32 {
    static V: std::sync::OnceLock<f32> = std::sync::OnceLock::new();
    *V.get_or_init(|| std::env::var("HAKUBA_BLOCK_M").ok().and_then(|v| v.parse().ok()).unwrap_or(BLOCK_M))
}

pub struct BlocksPlugin;

impl Plugin for BlocksPlugin {
    fn build(&self, app: &mut App) {
        if block_m() <= 0.0 {
            return;
        }
        app.init_resource::<Blocks>().add_systems(
            PostUpdate,
            (hide, assign, notice, merge)
                .chain()
                .after(TransformSystems::Propagate)
                .before(VisibilitySystems::VisibilityPropagate)
                .run_if(in_state(Screen::World)),
        );
    }
}

#[derive(Resource, Default)]
struct Blocks {
    blocks: HashMap<UVec2, Block>,
    /// Each member tile's shown root, and its block.
    roots: HashMap<Entity, UVec2>,
    /// Parts to hide next frame, once the merged meshes holding them show.
    to_hide: Vec<Entity>,
    /// One material for each alike set: every tile's file loads its own copy of the same material.
    alike: HashMap<String, Handle<StandardMaterial>>,
    /// How many parts of each look the last merges saw, for the log.
    looks: [usize; 4],
    /// The ground's triangles before and after simplifying, for the log.
    triangles: [usize; 2],
    /// The ground's area seen from above before and after simplifying, in square kilometres, for the log.
    areas: [f64; 2],
}

#[derive(Default)]
struct Block {
    /// Its member tiles and their shown roots.
    members: HashMap<Entity, Entity>,
    /// The tiles' meshes the merged meshes hold, hidden.
    parts: Vec<Entity>,
    drawn: Vec<Entity>,
    dirty: bool,
    /// When its tiles last changed, in seconds.
    touched: f32,
    /// Whether a tile left it, whose meshes stay hidden until it merges again: it merges at once.
    urgent: bool,
}

impl Block {
    fn touch(&mut self, now: f32) {
        self.dirty = true;
        self.touched = now;
    }
}

/// On a tile's mesh while a block's merged mesh holds it.
#[derive(Component)]
struct InBlock;

/// What lets meshes merge: their material and vertex attributes.
type Key = (UntypedAssetId, Vec<MeshVertexAttributeId>);

/// Hides the parts whose merged meshes were spawned last frame, and so show from this one.
fn hide(mut blocks: ResMut<Blocks>, mut visibility: Query<&mut Visibility, With<InBlock>>) {
    for part in std::mem::take(&mut blocks.to_hide) {
        if let Ok(mut visibility) = visibility.get_mut(part) {
            *visibility = Visibility::Hidden;
        }
    }
}

/// Puts each far tile past `BLOCK_M` in its block, and takes out the others.
fn assign(
    mut blocks: ResMut<Blocks>,
    tiles: Query<(Entity, &Tile)>,
    camera: Single<&GlobalTransform, With<Camera3d>>,
    time: Res<Time>,
    mut logged: Local<f32>,
) {
    if time.elapsed_secs() - *logged > 2.0 {
        *logged = time.elapsed_secs();
        let far = tiles.iter().filter(|(_, tile)| tile.far_root().is_some()).count();
        let b = blocks.blocks.values();
        let (members, parts, drawn) =
            b.fold((0, 0, 0), |(m, p, d), b| (m + b.members.len(), p + b.parts.len(), d + b.drawn.len()));
        info!(
            "BLOCKS {} blocks, {far} far tiles, {members} members, {parts} parts held in {drawn} meshes; looks {:?}, ground triangles {:?}, plan area {:.3?} km²",
            blocks.blocks.len(),
            blocks.looks,
            blocks.triangles,
            blocks.areas
        );
    }
    let eye = camera.translation().xz();
    let mut seen = HashSet::new();
    for (entity, tile) in &tiles {
        let Some((cell, centre, root)) = tile.far_root() else { continue };
        let block = cell / BLOCK_TILES;
        let member = blocks.blocks.get(&block).and_then(|b| b.members.get(&entity)).copied();
        let edge = block_m() + if member.is_some() { -HYSTERESIS_M } else { HYSTERESIS_M };
        if centre.xz().distance(eye) < edge {
            continue;
        }
        seen.insert(entity);
        if member != Some(root) {
            if let Some(old) = member {
                blocks.roots.remove(&old);
            }
            blocks.roots.insert(root, block);
            let b = blocks.blocks.entry(block).or_default();
            b.members.insert(entity, root);
            b.touch(time.elapsed_secs());
        }
    }
    let now = time.elapsed_secs();
    let Blocks { blocks, roots, .. } = &mut *blocks;
    for block in blocks.values_mut() {
        let before = block.members.len();
        block.members.retain(|tile, root| {
            let keep = seen.contains(tile);
            if !keep {
                roots.remove(root);
            }
            keep
        });
        if block.members.len() != before {
            block.touch(now);
            block.urgent = true;
        }
    }
}

/// Marks a block to merge again when a mesh appears under one of its tiles: a tile's plants spawn over frames.
fn notice(mut blocks: ResMut<Blocks>, added: Query<Entity, Added<Mesh3d>>, parents: Query<&ChildOf>, time: Res<Time>) {
    if blocks.roots.is_empty() {
        return;
    }
    for entity in &added {
        let Some(&block) = parents.iter_ancestors(entity).find_map(|ancestor| blocks.roots.get(&ancestor)) else {
            continue;
        };
        if let Some(block) = blocks.blocks.get_mut(&block) {
            block.touch(time.elapsed_secs());
        }
    }
}

#[allow(clippy::type_complexity)]
fn merge(
    mut commands: Commands,
    mut blocks: ResMut<Blocks>,
    mut meshes: ResMut<Assets<Mesh>>,
    children: Query<&Children>,
    parts: Query<
        (
            &Mesh3d,
            &GlobalTransform,
            Option<&MeshMaterial3d<StandardMaterial>>,
            Option<&MeshMaterial3d<Painted>>,
            Option<&MeshMaterial3d<MovingPainted>>,
            Option<&MeshMaterial3d<Swaying>>,
        ),
        Without<VisibilityRange>,
    >,
    mut visibility: Query<&mut Visibility>,
    standard: Res<Assets<StandardMaterial>>,
    camera: Single<&GlobalTransform, With<Camera3d>>,
    time: Res<Time>,
) {
    let eye = camera.translation();
    let now = time.elapsed_secs();
    let Blocks { blocks, to_hide, alike, looks, triangles, areas, .. } = &mut *blocks;
    let mut dirty: Vec<(bool, UVec2)> = blocks
        .iter()
        .filter(|(_, block)| block.dirty && (block.urgent || now - block.touched >= SETTLE_S))
        .map(|(&key, block)| (!block.urgent, key))
        .collect();
    // Blocks a tile left first: its meshes are hidden until then.
    dirty.sort_unstable_by_key(|&(settled, _)| settled);
    let dirty: Vec<UVec2> = dirty.into_iter().take(MERGES_PER_FRAME).map(|(_, key)| key).collect();
    for key in dirty {
        let block = blocks.get_mut(&key).expect("a dirty block exists");
        block.dirty = false;
        block.urgent = false;
        // The old merged meshes leave next frame, when the new ones show; the parts no longer held show again now.
        for drawn in block.drawn.drain(..) {
            commands.entity(drawn).despawn();
        }
        for part in block.parts.drain(..) {
            if let Ok(mut visibility) = visibility.get_mut(part) {
                *visibility = Visibility::Inherited;
                commands.entity(part).try_remove::<InBlock>();
            }
        }
        let mut groups: HashMap<Key, (Look, Vec<Mesh>, Vec<Entity>)> = HashMap::new();
        for &root in block.members.values() {
            for part in children.iter_descendants(root) {
                let Ok((mesh, transform, still, painted, moving, swaying)) = parts.get(part) else { continue };
                let look = match (still, painted, moving, swaying) {
                    (Some(m), ..) => {
                        looks[0] += 1;
                        let Some(material) = standard.get(&m.0) else { continue };
                        Look::Still(alike.entry(format!("{material:?}")).or_insert_with(|| m.0.clone()).clone())
                    }
                    (_, Some(m), ..) => {
                        looks[1] += 1;
                        Look::Painted(m.0.clone())
                    }
                    (_, _, Some(m), _) => {
                        looks[2] += 1;
                        Look::MovingPainted(m.0.clone())
                    }
                    (.., Some(m)) => {
                        looks[3] += 1;
                        Look::Swaying(m.0.clone())
                    }
                    _ => continue,
                };
                let Some(source) = meshes.get(&mesh.0) else { continue };
                // A mesh whose data already left for the GPU stays drawn on its own.
                let Ok(_) = source.try_indices_option() else { continue };
                let attributes = source.attributes().map(|(attribute, _)| attribute.id).collect();
                let mut copy = source.clone().transformed_by(transform.compute_transform());
                if let Some(Indices::U16(indices)) = copy.indices() {
                    let wide = indices.iter().map(|&i| i as u32).collect();
                    copy.insert_indices(Indices::U32(wide));
                }
                let group = groups.entry((look.id(), attributes)).or_insert_with(|| (look, Vec::new(), Vec::new()));
                group.1.push(copy);
                group.2.push(part);
            }
        }
        for (_, (look, copies, held)) in groups {
            let mut merged: Option<Mesh> = None;
            let mut holding = Vec::new();
            let mut flush = |merged: &mut Option<Mesh>, holding: &mut Vec<Entity>, commands: &mut Commands| {
                let Some(mut mesh) = merged.take() else { return };
                // The distant plants are the bulk of the distant land's triangles, most smaller than a pixel, which a
                // GPU rasterises at great cost: nearby plants' vertices cluster together, joining their shapes.
                if matches!(look, Look::Painted(_)) && plant_error_px() > 0.0 {
                    let before = mesh.indices().map_or(0, Indices::len) / 3;
                    let area = plan_area(&mesh);
                    mesh = clustered(mesh, eye, plant_error_px() * PIXEL_M_PER_M);
                    triangles[0] += before;
                    triangles[1] += mesh.indices().map_or(0, Indices::len) / 3;
                    areas[0] += area;
                    areas[1] += plan_area(&mesh);
                }
                mesh.asset_usage = RenderAssetUsages::RENDER_WORLD;
                let mut drawn = commands.spawn((
                    Name::new("Block"),
                    Mesh3d(meshes.add(mesh)),
                    Transform::IDENTITY,
                    NotShadowCaster,
                    DespawnOnExit(Screen::World),
                ));
                insert_look(&mut drawn, &look);
                // Playtest: HAKUBA_BLOCK_HIDE=still or painted hides that look's merged meshes, to measure them.
                let hide = std::env::var("HAKUBA_BLOCK_HIDE").unwrap_or_default();
                if matches!((&look, hide.as_str()), (Look::Still(_), "still") | (Look::Painted(_), "painted")) {
                    drawn.insert(Visibility::Hidden);
                }
                block.drawn.push(drawn.id());
                for part in holding.drain(..) {
                    commands.entity(part).try_insert(InBlock);
                    to_hide.push(part);
                    block.parts.push(part);
                }
            };
            for (copy, part) in copies.into_iter().zip(held) {
                let fits = merged.as_ref().is_none_or(|m| m.count_vertices() + copy.count_vertices() <= MOST_VERTICES);
                if !fits {
                    flush(&mut merged, &mut holding, &mut commands);
                }
                match merged.as_mut() {
                    None => merged = Some(copy),
                    Some(m) => {
                        if m.merge(&copy).is_err() {
                            continue;
                        }
                    }
                }
                holding.push(part);
            }
            flush(&mut merged, &mut holding, &mut commands);
        }
    }
}

/// `mesh` with its vertices clustered, so that its triangles stray at most `error_per_m` metres per metre between
/// `eye` and the mesh's nearest point (and never nearer than `BLOCK_M`); disjoint shapes may join.
fn clustered(mut mesh: Mesh, eye: Vec3, error_per_m: f32) -> Mesh {
    use bevy::mesh::VertexAttributeValues as V;
    let (Some(V::Float32x3(positions)), Some(Indices::U32(indices))) =
        (mesh.attribute(Mesh::ATTRIBUTE_POSITION), mesh.indices())
    else {
        return mesh;
    };
    let (low, high) = positions.iter().fold((Vec3::MAX, Vec3::MIN), |(l, h), &p| (l.min(p.into()), h.max(p.into())));
    let nearest = eye.clamp(low, high).distance(eye).max(block_m());
    let extent = (high - low).max_element().max(1.0);
    let Ok(adapter) = meshopt::VertexDataAdapter::new(meshopt::typed_to_bytes(positions), 12, 0) else { return mesh };
    let reduced = meshopt::simplify_sloppy(indices, &adapter, 0, nearest * error_per_m / extent, None);
    mesh.insert_indices(Indices::U32(reduced));
    mesh
}

/// The area `mesh`'s triangles cover seen from above, in square kilometres.
fn plan_area(mesh: &Mesh) -> f64 {
    use bevy::mesh::VertexAttributeValues as V;
    let (Some(V::Float32x3(p)), Some(Indices::U32(indices))) =
        (mesh.attribute(Mesh::ATTRIBUTE_POSITION), mesh.indices())
    else {
        return 0.0;
    };
    let area: f64 = indices
        .chunks_exact(3)
        .map(|t| {
            let [a, b, c] = [p[t[0] as usize], p[t[1] as usize], p[t[2] as usize]];
            let (u, v) = ([b[0] - a[0], b[2] - a[2]], [c[0] - a[0], c[2] - a[2]]);
            ((u[0] * v[1] - u[1] * v[0]) as f64).abs() / 2.0
        })
        .sum();
    area / 1e6
}
