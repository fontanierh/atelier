//! A splash over the world until it has loaded, so the player steps into a whole world around them, not one filling in:
//! the index, every tile in full detail around the player and every model standing in them (the middle tiles beyond
//! stream in afterwards), every texture the materials use, and every shader
//! the renderer needs to draw them, whichever way the camera turns. What other crates add to the world holds the splash
//! too while it is [`Unready`], such as the player until their character stands on the ground. A file that fails to
//! load is reported as an error and named on the splash. What the world can show without, such as a texture, a tile, a
//! plant or the paraglider, then stops holding it; what it cannot, such as its index or the player's character, keeps
//! it up, saying which file failed.

use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};

use bevy::asset::{LoadState, RecursiveDependencyLoadState, UntypedAssetId, UntypedAssetLoadFailedEvent};
use bevy::camera::primitives::{Aabb, MeshAabb};
use bevy::camera::visibility::NoFrustumCulling;
use bevy::prelude::*;
use bevy::render::render_resource::PipelineCache;
use bevy::render::{Render, RenderApp, RenderSystems};
use bevy::world_serialization::WorldAssetRoot;
use hakuba_screens::{Screen, text};

use crate::scenery::{Placed, Placing, Unplaced};
use crate::tiles::{Spawning, Tile};

/// How many frames in a row the renderer must start no new pipeline and wait on none before the splash lifts: what a
/// frame draws for the first time has its pipelines made over the next few.
const SETTLED_FRAMES: u32 = 10;

const BACKGROUND: Color = Color::srgb(0.07, 0.07, 0.09);
const TRACK: Color = Color::srgba(1.0, 1.0, 1.0, 0.12);
const FILL: Color = Color::srgba(1.0, 1.0, 1.0, 0.85);
const QUIET: Color = Color::srgb(0.6, 0.6, 0.64);

pub struct LoadingPlugin;

impl Plugin for LoadingPlugin {
    fn build(&self, app: &mut App) {
        let pipelines = Pipelines::default();
        app.insert_resource(pipelines.clone())
            .add_observer(uncull)
            .add_systems(OnEnter(Screen::World), spawn)
            .add_systems(Update, report.run_if(in_state(Screen::World)))
            .add_systems(
                Update,
                (lift.after(Placing).run_if(any_with_component::<Splash>), watch.run_if(resource_exists::<Loaded>))
                    .run_if(in_state(Screen::World)),
            );
        if let Some(render) = app.get_sub_app_mut(RenderApp) {
            render.insert_resource(pipelines).add_systems(Render, count.in_set(RenderSystems::Cleanup));
        }
    }
}

/// The splash, and how far along it shows the loading.
#[derive(Component, Default)]
struct Splash {
    /// When it showed, in seconds.
    since: f32,
    shown: f32,
    /// How many pipelines the renderer had last frame, and for how many frames in a row it has started none.
    pipelines: usize,
    settled: u32,
}

/// The splash's bar, which fills as the world loads.
#[derive(Component)]
struct Bar;

/// The splash's line saying what is loading.
#[derive(Component)]
struct Stage;

/// Holds the splash while any entity has it. The world draws under the splash, so what is spawned meanwhile has its
/// models loaded and its shaders compiled before the player sees it.
#[derive(Component)]
pub struct Unready;

/// A mesh drawn while the splash shows even where the camera does not look, so the renderer makes the pipelines it
/// would need when the camera turns to it.
#[derive(Component)]
struct Unculled;

/// The renderer's pipelines as of its last frame: how many it has made or started, and how many it is still making.
/// The render world writes them, the splash reads them.
#[derive(Resource, Clone, Default)]
struct Pipelines {
    all: Arc<AtomicUsize>,
    waiting: Arc<AtomicUsize>,
}

fn count(cache: Res<PipelineCache>, pipelines: Res<Pipelines>) {
    pipelines.all.store(cache.pipelines().count(), Ordering::Relaxed);
    pipelines.waiting.store(cache.waiting_pipelines().count(), Ordering::Relaxed);
}

/// How many pipelines the renderer had made once the world had loaded, and since.
#[derive(Resource, Default)]
pub(crate) struct Loaded {
    pipelines: usize,
}

fn spawn(mut commands: Commands, time: Res<Time>) {
    commands.remove_resource::<Loaded>();
    commands.spawn((
        Splash { since: time.elapsed_secs(), ..default() },
        DespawnOnExit(Screen::World),
        Node {
            position_type: PositionType::Absolute,
            width: percent(100),
            height: percent(100),
            flex_direction: FlexDirection::Column,
            align_items: AlignItems::Center,
            justify_content: JustifyContent::Center,
            row_gap: px(18),
            ..default()
        },
        BackgroundColor(BACKGROUND),
        GlobalZIndex(i32::MAX - 1),
        children![
            text("Hakuba", 64.0),
            (
                Node { width: px(280), height: px(3), border_radius: BorderRadius::all(px(2)), ..default() },
                BackgroundColor(TRACK),
                children![(
                    Bar,
                    Node {
                        width: percent(0),
                        height: percent(100),
                        border_radius: BorderRadius::all(px(2)),
                        ..default()
                    },
                    BackgroundColor(FILL),
                )],
            ),
            (
                Stage,
                Text::new("Loading the world"),
                TextFont { font_size: FontSize::Px(15.0), ..default() },
                TextColor(QUIET),
            ),
        ],
    ));
}

/// While the splash shows, draws every mesh spawned whichever way the camera looks. Bevy bounds only culled meshes,
/// and rays find solids by their bounds, so an unculled mesh is bounded here: the player arriving on scenery, such as
/// a ported town's street, would otherwise find no ground and hold the splash forever.
fn uncull(
    add: On<Add<Mesh3d>>,
    mut commands: Commands,
    splash: Query<(), With<Splash>>,
    culled: Query<(&Mesh3d, Has<NoFrustumCulling>, Has<Aabb>)>,
    meshes: Res<Assets<Mesh>>,
) {
    let Ok((mesh, already, bounded)) = culled.get(add.entity) else { return };
    if splash.is_empty() || already {
        return;
    }
    let mut entity = commands.entity(add.entity);
    entity.insert((NoFrustumCulling, Unculled));
    if !bounded && let Some(bounds) = meshes.get(&mesh.0).and_then(MeshAabb::get_aabb) {
        entity.insert(bounds);
    }
}

/// Fills the bar, and lifts the splash once every tile shows the version it needs, every model in them has spawned
/// with its textures, nothing else is [`Unready`] and the renderer has settled.
#[allow(clippy::too_many_arguments)]
fn lift(
    mut commands: Commands,
    assets: Res<AssetServer>,
    pipelines: Res<Pipelines>,
    materials: Res<Assets<StandardMaterial>>,
    images: Res<Assets<Image>>,
    splash: Single<(Entity, &mut Splash)>,
    mut bar: Single<&mut Node, With<Bar>>,
    (mut stage, missing): (Single<&mut Text, With<Stage>>, Option<Res<Missing>>),
    tiles: Query<&Tile>,
    spawning: Query<(), With<Spawning>>,
    waiting: Query<(), Unplaced>,
    roots: Query<&WorldAssetRoot>,
    placed: Query<&Placed>,
    unready: Query<(), With<Unready>>,
    unculled: Query<Entity, With<Unculled>>,
    time: Res<Time>,
) {
    let (entity, mut splash) = splash.into_inner();
    let loaded = |id: UntypedAssetId| {
        matches!(
            assets.recursive_dependency_load_state(id),
            RecursiveDependencyLoadState::Loaded | RecursiveDependencyLoadState::Failed(_)
        )
    };
    let done = tiles.iter().filter(|tile| tile.shown()).count()
        + roots.iter().filter(|root| loaded(root.0.id().untyped())).count()
        + placed.iter().filter(|placed| loaded(placed.0.id().untyped())).count();
    let all = tiles.iter().len()
        + roots.iter().len()
        + placed.iter().len()
        + spawning.iter().len()
        + waiting.iter().len()
        + unready.iter().len();
    let world = all > 0 && done == all;
    // A long load names what it still waits for, every ten seconds.
    let waited = time.elapsed_secs() - splash.since;
    if !world && waited > 30.0 && (waited / 10.0).floor() != ((waited - time.delta_secs()) / 10.0).floor() {
        warn!(
            "the world still waits after {waited:.0} s: {} of {} tiles, {} of {} scenes, {} of {} placed models, {} tiles \
             spawning, {} models waiting, {} unready",
            tiles.iter().filter(|tile| !tile.shown()).count(),
            tiles.iter().len(),
            roots.iter().filter(|root| !loaded(root.0.id().untyped())).count(),
            roots.iter().len(),
            placed.iter().filter(|placed| !loaded(placed.0.id().untyped())).count(),
            placed.iter().len(),
            spawning.iter().len(),
            waiting.iter().len(),
            unready.iter().len(),
        );
    }
    let textured = world && materials.iter().all(|(_, material)| textured(material, &images, &assets));
    let made = pipelines.all.load(Ordering::Relaxed);
    let settling = textured && pipelines.waiting.load(Ordering::Relaxed) == 0 && made == splash.pipelines;
    splash.settled = if settling { splash.settled + 1 } else { 0 };
    splash.pipelines = made;

    let progress = 0.8 * done as f32 / all.max(1) as f32
        + if textured { 0.1 } else { 0.0 }
        + 0.1 * splash.settled as f32 / SETTLED_FRAMES as f32;
    splash.shown += (progress.max(splash.shown) - splash.shown) * (8.0 * time.delta_secs()).min(1.0);
    bar.width = percent(100.0 * splash.shown);
    let says = match (world, textured) {
        (false, _) => "Loading the world",
        (true, false) => "Loading its textures",
        (true, true) => "Preparing its shaders",
    };
    let says = match missing {
        Some(missing) => format!("{says}. {} failed to load", missing.0),
        None => says.to_string(),
    };
    if stage.0 != says {
        stage.0 = says;
    }

    if splash.settled >= SETTLED_FRAMES {
        info!("the world loaded in {:.1} s, needing {made} pipelines", time.elapsed_secs() - splash.since);
        commands.insert_resource(Loaded { pipelines: made });
        commands.entity(entity).despawn();
        for mesh in &unculled {
            commands.entity(mesh).remove::<(NoFrustumCulling, Unculled)>();
        }
    }
}

/// Says when the renderer makes pipelines once the world has loaded: something was drawn for the first time, and
/// the frame it was made in may have stalled. The splash should have drawn it, unless a setting changed.
fn watch(pipelines: Res<Pipelines>, mut loaded: ResMut<Loaded>) {
    let made = pipelines.all.load(Ordering::Relaxed);
    if made > loaded.pipelines {
        info!("the renderer made {} pipelines after the world loaded", made - loaded.pipelines);
        loaded.pipelines = made;
    }
}

/// Reports each file that fails to load while the world shows: it no longer holds the splash, and is missing.
fn report(mut commands: Commands, mut failed: MessageReader<UntypedAssetLoadFailedEvent>) {
    for failed in failed.read() {
        error!("{} failed to load: {}", failed.path, failed.error);
        commands.insert_resource(Missing(failed.path.to_string()));
    }
}

/// The last file that failed to load, which the splash names while it stays up: a file the world cannot show without,
/// such as its index or the player's character, keeps it up.
#[derive(Resource)]
pub(crate) struct Missing(pub String);

/// Whether every texture `material` uses has loaded, or failed to, which [`report`] says.
fn textured(material: &StandardMaterial, images: &Assets<Image>, assets: &AssetServer) -> bool {
    [
        &material.base_color_texture,
        &material.emissive_texture,
        &material.metallic_roughness_texture,
        &material.normal_map_texture,
        &material.occlusion_texture,
    ]
    .into_iter()
    .flatten()
    .all(|image| images.contains(image) || matches!(assets.load_state(image), LoadState::Failed(_)))
}
