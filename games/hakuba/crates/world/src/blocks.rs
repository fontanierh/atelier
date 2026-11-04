//! The distant land drawn in blocks, as hierarchical levels of detail do. Beyond `BLOCK_M` from
//! the camera, the meshes of the far tiles in each block of 8 × 8 tiles (512 m) merge into one mesh per look, so
//! the GPU draws a few hundred meshes for the land past half a kilometre instead of tens of thousands; the tiles' own meshes hide
//! meanwhile. A merged mesh holds the very vertices of the meshes it replaces, so nothing changes on screen as a tile
//! joins or leaves its block. Its merges and the blocks the depth grid hides are logged at debug level.

use std::collections::{HashMap, HashSet};

use bevy::asset::{RenderAssetUsages, UntypedAssetId};
use bevy::camera::primitives::Aabb;
use bevy::camera::visibility::{VisibilityRange, VisibilitySystems};
use bevy::light::NotShadowCaster;
use bevy::mesh::{Indices, MeshVertexAttributeId};
use bevy::prelude::*;
use bevy::tasks::{AsyncComputeTaskPool, Task, block_on, futures_lite::future};
use bevy::transform::TransformSystems;
use hakuba_rendering::{DEPTH_GRID, DepthGrid};
use hakuba_screens::Screen;

use crate::scenery::{Look, insert_look};
use crate::tiles::Tile;
use crate::vertex_paint::{MovingPainted, Painted};
use crate::wind::{SourceFoliage, Swaying};

/// How far from the camera, to a tile's centre, a far tile joins its block. From 900 m, the far tiles between 400 m
/// and 900 m were still 5,000 meshes, holding a 68° view over the valley under 60 frames a second.
const BLOCK_M: f32 = 450.0;
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
/// How many grids in a row, about a quarter of a second, must find a block behind nearer things before it hides: a
/// trunk passing in front would otherwise hide and show it again, and each flip costs the renderer work.
const COVERED_GRIDS: u8 = 15;
/// How many degrees one cell of the depth grid spans, about, across the walker's view.
const CELL_DEG: f32 = 1.4;
/// The nearest thing that may hide a block, in metres: the camera's move since the grid shifts it on screen by at most
/// this much over the move.
const NEAREST_COVER_M: f32 = 4.0;
/// Beyond this many cells of margin, the grid says too little and every block shows.
const MOST_MARGIN_CELLS: i32 = 12;

pub struct BlocksPlugin;

impl Plugin for BlocksPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<Blocks>().add_systems(
            PostUpdate,
            (hide, assign, notice, merge, swap, occlude)
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
    looks: [usize; 8],
    /// The ground's triangles before and after simplifying, for the log.
    triangles: [usize; 2],
    /// The ground's area seen from above before and after simplifying, in square kilometres, for the log.
    areas: [f64; 2],
    /// The far trees' triangles before and after thinning, for the log.
    thinned: [usize; 2],
}

#[derive(Default)]
struct Block {
    /// Its member tiles and their shown roots.
    members: HashMap<Entity, Entity>,
    /// The tiles' meshes the merged meshes hold, hidden.
    parts: Vec<Entity>,
    drawn: Vec<Entity>,
    dirty: bool,
    /// Its merge building on a worker: whether it was urgent, how long gathering took in milliseconds, and the task.
    pending: Option<(bool, f32, Task<Merged>)>,
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

/// How a merged mesh looks: a look as scenery places it, or a far plant's source foliage, which scenery keys by its
/// wind as well.
#[derive(Clone)]
enum Drawn {
    Look(Look),
    Source(Handle<SourceFoliage>),
}

impl Drawn {
    fn id(&self) -> UntypedAssetId {
        match self {
            Drawn::Look(look) => look.id(),
            Drawn::Source(material) => material.id().untyped(),
        }
    }

    fn insert(&self, part: &mut EntityCommands) {
        match self {
            Drawn::Look(look) => insert_look(part, look),
            Drawn::Source(material) => {
                part.insert(MeshMaterial3d(material.clone()));
            }
        }
    }
}

/// On a tile's mesh while a block's merged mesh holds it.
#[derive(Component)]
struct InBlock;

/// On a block's merged mesh: past [`BLOCK_M`] the wind moves a leaf less than a pixel, so its vertices skip the sway.
#[derive(Component)]
pub(crate) struct Unswayed;

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
            "BLOCKS {} blocks, {far} far tiles, {members} members, {parts} parts held in {drawn} meshes; looks {:?}, ground triangles {:?}, plan area {:.3?} km², tree triangles {:?}",
            blocks.blocks.len(),
            blocks.looks,
            blocks.triangles,
            blocks.areas,
            blocks.thinned
        );
    }
    let eye = camera.translation().xz();
    let mut seen = HashSet::new();
    for (entity, tile) in &tiles {
        let Some((cell, centre, root)) = tile.far_root() else { continue };
        let block = cell / BLOCK_TILES;
        let member = blocks.blocks.get(&block).and_then(|b| b.members.get(&entity)).copied();
        let edge = BLOCK_M + if member.is_some() { -HYSTERESIS_M } else { HYSTERESIS_M };
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

/// One look's meshes in a block, gathered on the main thread and merged on a worker.
struct Group {
    look: Drawn,
    copies: Vec<(Mesh, Transform)>,
    parts: Vec<Entity>,
}

/// A block's merged meshes, built on a worker, with the parts each holds.
struct Merged {
    meshes: Vec<(Drawn, Mesh, Vec<Entity>)>,
    triangles: [usize; 2],
    areas: [f64; 2],
    thinned: [usize; 2],
    /// How long the merge took on its worker, in milliseconds, for the log.
    ms: f32,
}

/// The most merges building at once.
const MOST_PENDING: usize = 2;

/// Gathers the dirty blocks' meshes and merges them on workers, as level-of-detail proxies are built off the
/// game thread: a block's merge costs tens of milliseconds. A block keeps its old merged meshes until the new ones
/// are ready.
#[allow(clippy::type_complexity)]
fn merge(
    mut blocks: ResMut<Blocks>,
    meshes: Res<Assets<Mesh>>,
    children: Query<&Children>,
    parts: Query<
        (
            &Mesh3d,
            &GlobalTransform,
            Option<&MeshMaterial3d<StandardMaterial>>,
            Option<&MeshMaterial3d<Painted>>,
            Option<&MeshMaterial3d<MovingPainted>>,
            Option<&MeshMaterial3d<Swaying>>,
            Option<&MeshMaterial3d<SourceFoliage>>,
        ),
        Without<VisibilityRange>,
    >,
    mut visibility: Query<&mut Visibility>,
    meshed: Query<(), With<Mesh3d>>,
    standard: Res<Assets<StandardMaterial>>,
    camera: Single<&GlobalTransform, With<Camera3d>>,
    time: Res<Time>,
    mut commands: Commands,
) {
    let eye = camera.translation();
    let now = time.elapsed_secs();
    let Blocks { blocks, alike, looks, .. } = &mut *blocks;
    let pending = blocks.values().filter(|block| block.pending.is_some()).count();
    let mut dirty: Vec<(bool, UVec2)> = blocks
        .iter()
        .filter(|(_, block)| {
            block.pending.is_none() && block.dirty && (block.urgent || now - block.touched >= SETTLE_S)
        })
        .map(|(&key, block)| (!block.urgent, key))
        .collect();
    // Blocks a tile left first: its meshes are hidden until then.
    dirty.sort_unstable_by_key(|&(settled, _)| settled);
    let room = MOST_PENDING.saturating_sub(pending).min(MERGES_PER_FRAME);
    for (_, key) in dirty.into_iter().take(room) {
        let block = blocks.get_mut(&key).expect("a dirty block exists");
        let started = std::time::Instant::now();
        let urgent = block.urgent;
        block.dirty = false;
        block.urgent = false;
        let mut groups: HashMap<Key, Group> = HashMap::new();
        let mut gathered = HashSet::new();
        for &root in block.members.values() {
            for part in children.iter_descendants(root) {
                gathered.insert(part);
                let Ok((mesh, transform, still, painted, moving, swaying, source_foliage)) = parts.get(part) else {
                    looks[7] += usize::from(meshed.contains(part));
                    continue;
                };
                let look = match (still, painted, moving, swaying, source_foliage) {
                    (Some(m), ..) => {
                        looks[0] += 1;
                        let Some(material) = standard.get(&m.0) else { continue };
                        Drawn::Look(Look::Still(
                            alike.entry(format!("{material:?}")).or_insert_with(|| m.0.clone()).clone(),
                        ))
                    }
                    (_, Some(m), ..) => {
                        looks[1] += 1;
                        Drawn::Look(Look::Painted(m.0.clone()))
                    }
                    (_, _, Some(m), ..) => {
                        looks[2] += 1;
                        Drawn::Look(Look::MovingPainted(m.0.clone()))
                    }
                    (_, _, _, Some(m), _) => {
                        looks[3] += 1;
                        Drawn::Look(Look::Swaying(m.0.clone()))
                    }
                    (.., Some(m)) => {
                        looks[4] += 1;
                        Drawn::Source(m.0.clone())
                    }
                    _ => {
                        looks[5] += 1;
                        continue;
                    }
                };
                let Some(source) = meshes.get(&mesh.0) else { continue };
                // A mesh whose data already left for the GPU stays drawn on its own.
                let Ok(_) = source.try_indices_option() else {
                    looks[6] += 1;
                    continue;
                };
                let attributes = source.attributes().map(|(attribute, _)| attribute.id).collect();
                let group = groups.entry((look.id(), attributes)).or_insert_with(|| Group {
                    look,
                    copies: Vec::new(),
                    parts: Vec::new(),
                });
                group.copies.push((source.clone(), transform.compute_transform()));
                group.parts.push(part);
            }
        }
        // A tile that left shows its own meshes again at once, drawn twice until its block's new meshes replace the
        // old ones, rather than missing.
        if urgent {
            for &part in &block.parts {
                if !gathered.contains(&part) {
                    show(&mut commands, &mut visibility, part);
                }
            }
        }
        let groups: Vec<Group> = groups.into_values().collect();
        let gather_ms = started.elapsed().as_secs_f32() * 1000.0;
        block.pending =
            Some((urgent, gather_ms, AsyncComputeTaskPool::get().spawn(async move { merged(groups, eye) })));
    }
}

/// Swaps in each block's merged meshes as its worker finishes: the old ones leave, the parts no longer held show
/// again, and the newly held ones hide from next frame, when the new meshes show.
fn swap(
    mut commands: Commands,
    mut blocks: ResMut<Blocks>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut visibility: Query<&mut Visibility>,
) {
    let Blocks { blocks, to_hide, triangles, areas, thinned, .. } = &mut *blocks;
    for (key, block) in blocks.iter_mut() {
        let Some((_, _, task)) = block.pending.as_mut() else { continue };
        let Some(result) = block_on(future::poll_once(task)) else { continue };
        let (urgent, gather_ms, _) = block.pending.take().expect("a pending merge");
        let started = std::time::Instant::now();
        for i in 0..2 {
            triangles[i] += result.triangles[i];
            areas[i] += result.areas[i];
            thinned[i] += result.thinned[i];
        }
        for drawn in block.drawn.drain(..) {
            commands.entity(drawn).despawn();
        }
        let held: HashSet<Entity> = result.meshes.iter().flat_map(|(_, _, parts)| parts.iter().copied()).collect();
        for part in block.parts.drain(..) {
            if !held.contains(&part) {
                show(&mut commands, &mut visibility, part);
            }
        }
        for (look, mesh, parts) in result.meshes {
            let mut drawn = commands.spawn((
                Name::new("Block"),
                Mesh3d(meshes.add(mesh)),
                Transform::IDENTITY,
                NotShadowCaster,
                Unswayed,
                bevy::mesh::MeshTag::new(0),
                DespawnOnExit(Screen::World),
            ));
            look.insert(&mut drawn);
            drawn.insert(Covered::default());
            block.drawn.push(drawn.id());
            for part in parts {
                commands.entity(part).try_insert(InBlock);
                to_hide.push(part);
                block.parts.push(part);
            }
        }
        {
            debug!(
                "BLOCK merge {key} urgent {urgent}: {} members, {} parts in {} meshes; main thread {gather_ms:.1} ms gathering, {:.1} ms swapping, worker {:.1} ms",
                block.members.len(),
                block.parts.len(),
                block.drawn.len(),
                started.elapsed().as_secs_f32() * 1000.0,
                result.ms
            );
        }
    }
}

/// On a block's merged mesh: how many depth grids in a row found it behind nearer things.
#[derive(Component, Default)]
struct Covered(u8);

/// Hides the blocks the last few depth grids found wholly behind nearer things, and shows them again as soon as one
/// does not. Each block's rectangle grows by as far as the camera's turn and move since the grid can shift nearer
/// things on screen.
fn occlude(
    grid: Res<DepthGrid>,
    camera: Single<&GlobalTransform, With<Camera3d>>,
    mut drawn: Query<(&Aabb, &mut Visibility, &mut Covered)>,
    mut last: Local<u32>,
    time: Res<Time>,
    mut logged: Local<(f32, usize, usize)>,
) {
    if grid.cells.len() != (DEPTH_GRID.x * DEPTH_GRID.y) as usize {
        return;
    }
    let new = grid.count != *last;
    *last = grid.count;
    let (_, rotation, eye) = camera.to_scale_rotation_translation();
    let shift = rotation.angle_between(grid.rotation) + eye.distance(grid.eye) / NEAREST_COVER_M;
    let margin = 1 + (shift.to_degrees() / CELL_DEG).ceil() as i32;
    let mut hiding = 0;
    for (aabb, mut visibility, mut covered) in &mut drawn {
        hiding += (*visibility == Visibility::Hidden) as usize;
        // A shown block hides only behind one more cell than a hidden one needs to stay hidden, so a block at the edge
        // of its cover does not flip each grid, each flip costing the renderer work.
        let hidden = *visibility == Visibility::Hidden;
        let grown = if hidden { margin } else { margin + 1 };
        if grown <= MOST_MARGIN_CELLS && behind(&grid, aabb, grown) {
            if new {
                covered.0 = covered.0.saturating_add(1);
            }
            if covered.0 >= COVERED_GRIDS && *visibility != Visibility::Hidden {
                *visibility = Visibility::Hidden;
                logged.1 += 1;
            }
        } else {
            covered.0 = 0;
            if *visibility == Visibility::Hidden {
                *visibility = Visibility::Inherited;
                logged.2 += 1;
            }
        }
    }
    // Each second, how many blocks the depth grid hides.
    if time.elapsed_secs() - logged.0 > 1.0 {
        let (_, hid, showed) = std::mem::replace(&mut *logged, (time.elapsed_secs(), 0, 0));
        let centre = grid.cell(DEPTH_GRID.x / 2, DEPTH_GRID.y / 2);
        let farthest = grid.cells.iter().copied().fold(1.0f32, f32::min);
        debug!(
            "OCCLUDE grid {} margin {margin}: {hiding} of {} blocks hidden, {hid} hid and {showed} showed; centre depth {centre:.5}, farthest {farthest:.5}",
            grid.count,
            drawn.iter().len()
        );
    }
}

/// Whether the grid saw nearer things everywhere over the box, its rectangle on screen grown by `margin` cells. A box
/// reaching behind the camera or wholly off screen is not behind anything.
fn behind(grid: &DepthGrid, aabb: &Aabb, margin: i32) -> bool {
    let (min, max) = (Vec3::from(aabb.min()), Vec3::from(aabb.max()));
    let (mut lo, mut hi, mut nearest) = (Vec2::MAX, Vec2::MIN, 0.0f32);
    for i in 0..8 {
        let corner = Vec3::select(BVec3::new(i & 1 != 0, i & 2 != 0, i & 4 != 0), max, min);
        let clip = grid.clip_from_world * corner.extend(1.0);
        if clip.w <= 0.1 {
            return false;
        }
        let ndc = clip.truncate() / clip.w;
        lo = lo.min(ndc.truncate());
        hi = hi.max(ndc.truncate());
        // Reversed depth: the box's nearest point is its largest, at a corner since depth is linear across the box.
        nearest = nearest.max(ndc.z);
    }
    let size = DEPTH_GRID.as_vec2();
    let x0 = ((lo.x * 0.5 + 0.5) * size.x).floor() as i32 - margin;
    let x1 = ((hi.x * 0.5 + 0.5) * size.x).floor() as i32 + margin;
    let y0 = ((0.5 - hi.y * 0.5) * size.y).floor() as i32 - margin;
    let y1 = ((0.5 - lo.y * 0.5) * size.y).floor() as i32 + margin;
    let (w, h) = (DEPTH_GRID.x as i32, DEPTH_GRID.y as i32);
    if x1 < 0 || y1 < 0 || x0 >= w || y0 >= h {
        return false;
    }
    (y0.max(0)..=y1.min(h - 1)).all(|y| (x0.max(0)..=x1.min(w - 1)).all(|x| grid.cell(x as u32, y as u32) > nearest))
}

/// Shows a part a block no longer holds.
fn show(commands: &mut Commands, visibility: &mut Query<&mut Visibility>, part: Entity) {
    if let Ok(mut visibility) = visibility.get_mut(part) {
        *visibility = Visibility::Inherited;
        commands.entity(part).try_remove::<InBlock>();
    }
}

/// Merges a block's gathered meshes, on a worker.
fn merged(groups: Vec<Group>, eye: Vec3) -> Merged {
    let started = std::time::Instant::now();
    let mut out = Merged { meshes: Vec::new(), triangles: [0; 2], areas: [0.0; 2], thinned: [0; 2], ms: 0.0 };
    for Group { look, copies, parts } in groups {
        let mut chunks: Vec<(Mesh, Vec<Entity>)> = Vec::new();
        for ((source, transform), part) in copies.into_iter().zip(parts) {
            let mut copy = source.transformed_by(transform);
            if let Some(Indices::U16(indices)) = copy.indices() {
                let wide = indices.iter().map(|&i| i as u32).collect();
                copy.insert_indices(Indices::U32(wide));
            }
            match chunks.last_mut() {
                Some((merged, held)) if merged.count_vertices() + copy.count_vertices() <= MOST_VERTICES => {
                    if merged.merge(&copy).is_ok() {
                        held.push(part);
                    }
                }
                _ => chunks.push((copy, vec![part])),
            }
        }
        for (mut mesh, held) in chunks {
            // The distant plants are the bulk of the distant land's triangles, most smaller than a pixel, which a GPU
            // rasterises at great cost: nearby plants' vertices cluster together, joining their shapes.
            if matches!(look, Drawn::Look(Look::Painted(_))) && PLANT_ERROR_PX > 0.0 {
                let before = mesh.indices().map_or(0, Indices::len) / 3;
                let area = plan_area(&mesh);
                mesh = clustered(mesh, eye, PLANT_ERROR_PX * PIXEL_M_PER_M);
                out.triangles[0] += before;
                out.triangles[1] += mesh.indices().map_or(0, Indices::len) / 3;
                out.areas[0] += area;
                out.areas[1] += plan_area(&mesh);
            }
            // The far trees' cards are millions of triangles past a kilometre: fewer, larger cards cover as much.
            if matches!(look, Drawn::Source(_)) {
                out.thinned[0] += mesh.indices().map_or(0, Indices::len) / 3;
                let distance = nearest(&mesh, eye);
                let keep = thin_keep(distance);
                let before = mesh.indices().map_or(0, Indices::len) / 3;
                if keep < 1.0 {
                    mesh = thinned_cards(mesh, keep);
                }
                out.thinned[1] += mesh.indices().map_or(0, Indices::len) / 3;
                debug!(
                    "BLOCK trees at {distance:.0} m keep {keep:.3}: {before} to {} triangles",
                    mesh.indices().map_or(0, Indices::len) / 3
                );
            }
            mesh.asset_usage = RenderAssetUsages::RENDER_WORLD;
            out.meshes.push((look.clone(), mesh, held));
        }
    }
    out.ms = started.elapsed().as_secs_f32() * 1000.0;
    out
}

/// From how far a block's far trees thin, in metres to its nearest point. From
/// 450 m, the hilltop's GPU frame drops from 13.2 to 11.1 ms and the island 2 km off looks the same from 200 m up; from
/// 250 m it drops to 10.5 ms, but the island's crowns turn visibly puffier.
const THIN_FROM_M: f32 = 450.0;
/// The smallest share of a block's far trees' cards kept.
const THIN_LEAST: f32 = 0.125;

/// The share of its far trees' cards a block keeps at `distance`: as many cards per pixel as at [`THIN_FROM_M`], in
/// halving steps, so a block moving a little nearer or farther keeps the same cards.
fn thin_keep(distance: f32) -> f32 {
    let from = THIN_FROM_M;
    if distance <= from {
        return 1.0;
    }
    let halvings = (2.0 * (distance / from).log2()).floor();
    0.5f32.powf(halvings).max(THIN_LEAST)
}

/// How far `eye` is from the nearest point of `mesh`'s bounds.
fn nearest(mesh: &Mesh, eye: Vec3) -> f32 {
    use bevy::mesh::VertexAttributeValues as V;
    let Some(V::Float32x3(positions)) = mesh.attribute(Mesh::ATTRIBUTE_POSITION) else { return 0.0 };
    let (low, high) = positions.iter().fold((Vec3::MAX, Vec3::MIN), |(l, h), &p| (l.min(p.into()), h.max(p.into())));
    eye.clamp(low, high).distance(eye)
}

/// `mesh` keeping a share `keep` of its cards (the triangles joined by shared vertices), each grown about its centre
/// so the trees cover as much, as tree tools thin distant trees. A card is kept by a hash of where
/// it stands, to a metre, so the cards of one tree, which share a centre, go together, and a block merged again in
/// another order keeps the same cards.
fn thinned_cards(mut mesh: Mesh, keep: f32) -> Mesh {
    use bevy::mesh::VertexAttributeValues as V;
    let (Some(V::Float32x3(positions)), Some(Indices::U32(indices))) =
        (mesh.attribute(Mesh::ATTRIBUTE_POSITION), mesh.indices())
    else {
        return mesh;
    };
    let mut parent: Vec<u32> = (0..positions.len() as u32).collect();
    fn root(parent: &mut [u32], mut x: u32) -> u32 {
        while parent[x as usize] != x {
            parent[x as usize] = parent[parent[x as usize] as usize];
            x = parent[x as usize];
        }
        x
    }
    for t in indices.chunks_exact(3) {
        let a = root(&mut parent, t[0]);
        for &v in &t[1..] {
            let b = root(&mut parent, v);
            parent[b as usize] = a;
        }
    }
    let mut cards: HashMap<u32, (Vec3, u32)> = HashMap::new();
    for v in 0..positions.len() as u32 {
        let card = cards.entry(root(&mut parent, v)).or_default();
        card.0 += Vec3::from(positions[v as usize]);
        card.1 += 1;
    }
    // Only meshes of many small cards are leaves: a trunk or a rock keeps its detail, as scenery's thinning does.
    let small = cards.values().filter(|card| card.1 <= 6).count();
    if cards.len() < 200 || small * 10 < cards.len() * 9 {
        return mesh;
    }
    let kept: HashMap<u32, Vec3> = cards
        .into_iter()
        .filter_map(|(card, (sum, count))| {
            let centre = sum / count as f32;
            let cell = centre.floor().as_ivec3();
            let hash = (cell.x as u32).wrapping_mul(0x9E37_79B1)
                ^ (cell.y as u32).wrapping_mul(0x85EB_CA77)
                ^ (cell.z as u32).wrapping_mul(0xC2B2_AE3D);
            let share = (hash.wrapping_mul(0x27D4_EB2F) >> 8) as f32 / (1u32 << 24) as f32;
            (share < keep).then_some((card, centre))
        })
        .collect();
    let grow = (1.0 / keep).sqrt();
    let moved: Vec<[f32; 3]> = (0..positions.len() as u32)
        .map(|v| {
            let p = Vec3::from(positions[v as usize]);
            kept.get(&root(&mut parent, v)).map_or(p, |&centre| centre + (p - centre) * grow).into()
        })
        .collect();
    let remaining: Vec<u32> =
        indices.chunks_exact(3).filter(|t| kept.contains_key(&root(&mut parent, t[0]))).flatten().copied().collect();
    mesh.insert_attribute(Mesh::ATTRIBUTE_POSITION, moved);
    mesh.insert_indices(Indices::U32(remaining));
    mesh
}

/// `mesh` with its vertices clustered, so that its triangles stray at most `error_per_m` metres per metre between
/// `eye` and the mesh's nearest point (and never nearer than `BLOCK_M`); disjoint shapes may join. In the browser,
/// where the simplifier does not build, the mesh as it is.
#[cfg(target_arch = "wasm32")]
fn clustered(mesh: Mesh, _eye: Vec3, _error_per_m: f32) -> Mesh {
    mesh
}

#[cfg(not(target_arch = "wasm32"))]
fn clustered(mut mesh: Mesh, eye: Vec3, error_per_m: f32) -> Mesh {
    use bevy::mesh::VertexAttributeValues as V;
    let (Some(V::Float32x3(positions)), Some(Indices::U32(indices))) =
        (mesh.attribute(Mesh::ATTRIBUTE_POSITION), mesh.indices())
    else {
        return mesh;
    };
    let (low, high) = positions.iter().fold((Vec3::MAX, Vec3::MIN), |(l, h), &p| (l.min(p.into()), h.max(p.into())));
    let nearest = eye.clamp(low, high).distance(eye).max(BLOCK_M);
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
