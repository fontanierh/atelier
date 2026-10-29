//! Tile versions prepare under a hidden root and replace the visible version only when all scenery is ready.

use bevy::asset::{LoadState, RecursiveDependencyLoadState};
use bevy::camera::visibility::VisibilitySystems;
use bevy::diagnostic::FrameCount;
use bevy::prelude::*;
use bevy::transform::TransformSystems;
use bevy::world_serialization::{WorldAssetRoot, WorldInstanceReady};
use hakuba_screens::Screen;
use hakuba_settings::Settings;

use crate::ground::{self, PendingSolid};
use crate::loading::{Loaded, Missing};
use crate::scenery::{Placed, Placing, Waiting};
use crate::vertex_paint::{SurfaceFailed, SurfaceWaiting};

const MIDDLE_M: f32 = 2500.0;
/// The most tiles that load at once, so the nearest are not kept waiting behind the far.
const LOADING: usize = 16;
pub const TILES: &str = "world/tiles";

pub struct TilesPlugin;
impl Plugin for TilesPlugin {
    fn build(&self, app: &mut App) {
        app.add_observer(scene_ready)
            .add_systems(
                Update,
                (choose, give_up, failed_surface, prepare).chain().after(Placing).run_if(in_state(Screen::World)),
            )
            .add_systems(
                PostUpdate,
                activate
                    .after(TransformSystems::Propagate)
                    .before(VisibilitySystems::VisibilityPropagate)
                    .run_if(in_state(Screen::World)),
            );
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Detail {
    Full,
    Middle,
}

#[derive(Component)]
pub struct Tile {
    column: u32,
    row: u32,
    centre: Vec3,
    detail: Option<Detail>,
    showing: Option<Entity>,
    shown_detail: Option<Detail>,
    pending: Option<Entity>,
    failed: bool,
}

impl Tile {
    pub fn named(name: &str, centre: Vec3) -> Option<Self> {
        let mut words = name.strip_prefix("tile ")?.split(' ');
        let (column, row) = (words.next()?.parse().ok()?, words.next()?.parse().ok()?);
        Some(Self {
            column,
            row,
            centre,
            detail: None,
            showing: None,
            shown_detail: None,
            pending: None,
            failed: false,
        })
    }
    pub fn shown(&self) -> bool {
        self.failed || (self.detail == self.shown_detail && self.pending.is_none())
    }
    fn path(&self, detail: Detail) -> String {
        let suffix = if detail == Detail::Full { "" } else { ".middle" };
        format!("{TILES}/{}_{}{suffix}.glb", self.column, self.row)
    }
}

#[derive(Component)]
pub struct Spawning(Entity, Detail);
#[derive(Component)]
struct SceneReady(u32);
#[derive(Component)]
struct Prepared;

/// Picks each tile's version by its distance from the camera, as Unreal's world partition streams its cells: full
/// detail near, middle detail out to [`MIDDLE_M`], nothing beyond. Until the world has loaded only full detail loads,
/// so the splash waits for the world around the player alone; afterwards at most [`LOADING`] tiles load at once, the
/// nearest first. A tile leaving every version is dropped at once.
fn choose(
    mut commands: Commands,
    assets: Res<AssetServer>,
    camera: Single<&GlobalTransform, With<Camera3d>>,
    settings: Res<Settings>,
    loaded: Option<Res<Loaded>>,
    mut tiles: Query<(Entity, &mut Tile)>,
) {
    let eye = camera.translation();
    let mut wanted = Vec::new();
    let mut loading = 0;
    for (entity, mut tile) in &mut tiles {
        let distance = (tile.centre - eye).with_y(0.0).length();
        let detail = match distance {
            d if d < settings.detail.full_m() => Some(Detail::Full),
            d if d < MIDDLE_M && loaded.is_some() => Some(Detail::Middle),
            _ => None,
        };
        loading += usize::from(tile.pending.is_some());
        if detail == tile.detail {
            continue;
        }
        if detail.is_none() {
            tile.detail = None;
            if let Some(pending) = tile.pending.take() {
                commands.entity(pending).despawn();
            }
            if let Some(old) = tile.showing.take() {
                commands.entity(old).despawn();
            }
            tile.shown_detail = None;
            tile.failed = false;
            continue;
        }
        wanted.push((distance, entity, detail));
    }
    wanted.sort_by(|a, b| a.0.total_cmp(&b.0));
    // The splash counts a tile not yet loading as shown, so until the world has loaded every near tile starts at once.
    let free = if loaded.is_some() { LOADING.saturating_sub(loading) } else { usize::MAX };
    for (_, entity, detail) in wanted.into_iter().take(free) {
        let Ok((_, mut tile)) = tiles.get_mut(entity) else { continue };
        tile.detail = detail;
        if let Some(pending) = tile.pending.take() {
            commands.entity(pending).despawn();
        }
        if tile.failed || detail == tile.shown_detail {
            continue;
        }
        let detail = detail.unwrap();
        let scene = assets.load(GltfAssetLabel::Scene(0).from_asset(tile.path(detail)));
        tile.pending = Some(
            commands.spawn((WorldAssetRoot(scene), Spawning(entity, detail), ChildOf(entity), Visibility::Hidden)).id(),
        );
    }
}

fn give_up(
    mut commands: Commands,
    assets: Res<AssetServer>,
    spawning: Query<(Entity, &Spawning, &WorldAssetRoot)>,
    mut tiles: Query<&mut Tile>,
) {
    for (root, Spawning(owner, _), scene) in &spawning {
        if !matches!(assets.load_state(&scene.0), LoadState::Failed(_)) {
            continue;
        }
        if let Ok(mut tile) = tiles.get_mut(*owner)
            && tile.pending == Some(root)
        {
            tile.pending = None;
            tile.failed = true;
        }
        commands.entity(root).despawn();
    }
}

fn failed_surface(
    mut commands: Commands,
    failed: Query<Entity, Added<SurfaceFailed>>,
    parents: Query<&ChildOf>,
    spawning: Query<(&Spawning, &WorldAssetRoot)>,
    mut tiles: Query<&mut Tile>,
) {
    for entity in &failed {
        if let Some((root, owner, scene)) =
            parents.iter_ancestors(entity).find_map(|root| spawning.get(root).ok().map(|(s, scene)| (root, s.0, scene)))
            && let Ok(mut tile) = tiles.get_mut(owner)
            && tile.pending == Some(root)
        {
            tile.pending = None;
            tile.failed = true;
            let name = scene.0.path().map_or_else(|| format!("tile {root}"), |path| path.to_string());
            commands.insert_resource(Missing(name));
            commands.entity(root).despawn();
        }
    }
}

fn scene_ready(
    ready: On<WorldInstanceReady>,
    spawning: Query<&Spawning>,
    frame: Res<FrameCount>,
    mut commands: Commands,
) {
    if spawning.contains(ready.entity) {
        commands.entity(ready.entity).insert(SceneReady(frame.0));
    }
}

type PendingScene = (Entity, &'static SceneReady, &'static WorldAssetRoot);
type WaitingForContent = Or<(With<Waiting>, With<SurfaceWaiting>)>;

/// Only a later Update can observe every data node read by Placing after the scene-spawn schedule.
fn prepare(
    mut commands: Commands,
    frame: Res<FrameCount>,
    assets: Res<AssetServer>,
    roots: Query<PendingScene, (With<Spawning>, Without<Prepared>)>,
    children: Query<&Children>,
    waiting: Query<(), WaitingForContent>,
    placed: Query<&Placed>,
) {
    for (root, ready, scene) in &roots {
        if frame.0 <= ready.0
            || !matches!(
                assets.recursive_dependency_load_state(scene.0.id()),
                RecursiveDependencyLoadState::Loaded | RecursiveDependencyLoadState::Failed(_)
            )
        {
            continue;
        }
        let descendants: Vec<_> = children.iter_descendants(root).collect();
        if descendants.iter().any(|&entity| waiting.contains(entity)) {
            continue;
        }
        if descendants.iter().filter_map(|&entity| placed.get(entity).ok()).any(|placed| {
            !matches!(
                assets.recursive_dependency_load_state(placed.0.id()),
                RecursiveDependencyLoadState::Loaded | RecursiveDependencyLoadState::Failed(_)
            )
        }) {
            continue;
        }
        commands.entity(root).insert(Prepared);
    }
}

/// @cc [owner:fontanierh,label:correctness] whole-tile-activation
/// A pending tile MUST stay hidden and non-solid until its scene and scenery are ready and dependencies have either
/// loaded or reported failure. Activation MUST promote its solid meshes and replace the previous visible, solid version
/// together; a failed version keeps the old one.
///
/// Promote all collision and switch the complete version before visibility propagates.
fn activate(
    mut commands: Commands,
    roots: Query<(Entity, &Spawning), With<Prepared>>,
    mut tiles: Query<&mut Tile>,
    children: Query<&Children>,
    pending: Query<&PendingSolid>,
) {
    for (root, Spawning(owner, detail)) in &roots {
        let Ok(mut tile) = tiles.get_mut(*owner) else { continue };
        if tile.pending != Some(root) || tile.detail != Some(*detail) {
            continue;
        }
        ground::promote(root, &children, &pending, &mut commands);
        if let Some(old) = tile.showing.replace(root) {
            commands.entity(old).despawn();
        }
        tile.pending = None;
        tile.shown_detail = Some(*detail);
        commands.entity(root).remove::<(Spawning, SceneReady, Prepared)>().insert(Visibility::Inherited);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ground::Ground;
    use bevy::asset::AssetApp;
    use bevy::camera::primitives::Aabb;
    use bevy::ecs::system::RunSystemOnce;

    #[test]
    fn pending_tile_keeps_old_visible_and_solid_until_complete_swap() {
        let mut app = App::new();
        app.add_plugins(MinimalPlugins).init_resource::<Assets<Mesh>>();
        let mesh = app.world_mut().resource_mut::<Assets<Mesh>>().add(Mesh::from(Cuboid::new(1.0, 1.0, 1.0)));
        let owner = app.world_mut().spawn(Tile::named("tile 1 2", Vec3::ZERO).unwrap()).id();
        let old = app.world_mut().spawn((ChildOf(owner), Visibility::Inherited)).id();
        let next = app.world_mut().spawn((ChildOf(owner), Visibility::Hidden, Spawning(owner, Detail::Full))).id();
        let bounds = Aabb::from_min_max(Vec3::splat(-0.5), Vec3::splat(0.5));
        for (root, x) in [(old, 0.0), (next, 5.0)] {
            app.world_mut().spawn((
                ChildOf(root),
                Mesh3d(mesh.clone()),
                bounds,
                GlobalTransform::from(Transform::from_xyz(x, 0.0, 0.0)),
                Visibility::Inherited,
                ground::built_solid(),
            ));
        }
        app.world_mut()
            .run_system_once(
                move |mut commands: Commands, children: Query<&Children>, pending: Query<&PendingSolid>| {
                    ground::promote(old, &children, &pending, &mut commands);
                },
            )
            .unwrap();
        {
            let mut tile = app.world_mut().get_mut::<Tile>(owner).unwrap();
            tile.detail = Some(Detail::Full);
            tile.showing = Some(old);
            tile.pending = Some(next);
        }
        app.world_mut().run_system_once(activate).unwrap();
        assert!(app.world().get_entity(old).is_ok());
        assert_eq!(*app.world().get::<Visibility>(next).unwrap(), Visibility::Hidden);
        app.world_mut()
            .run_system_once(|mut ground: Ground| {
                assert!(ground.below(Vec3::ZERO, 2.0, 2.0).is_some());
                assert!(ground.below(Vec3::new(5.0, 0.0, 0.0), 2.0, 2.0).is_none());
            })
            .unwrap();
        app.world_mut().entity_mut(next).insert(Prepared);
        app.world_mut().run_system_once(activate).unwrap();
        assert!(app.world().get_entity(old).is_err());
        assert_eq!(*app.world().get::<Visibility>(next).unwrap(), Visibility::Inherited);
        app.world_mut()
            .run_system_once(|mut ground: Ground| {
                assert!(ground.below(Vec3::ZERO, 2.0, 2.0).is_none());
                assert!(ground.below(Vec3::new(5.0, 0.0, 0.0), 2.0, 2.0).is_some());
            })
            .unwrap();
    }

    #[test]
    fn changing_back_cancels_pending_work_and_keeps_existing_tile() {
        let mut app = App::new();
        app.add_plugins(MinimalPlugins).add_plugins(bevy::asset::AssetPlugin::default());
        app.init_resource::<Settings>().init_resource::<Loaded>();
        app.world_mut().spawn((Camera3d::default(), GlobalTransform::from(Transform::from_xyz(1000.0, 0.0, 0.0))));
        let owner = app.world_mut().spawn(Tile::named("tile 1 2", Vec3::ZERO).unwrap()).id();
        let old = app.world_mut().spawn((ChildOf(owner), Visibility::Inherited)).id();
        let pending = app.world_mut().spawn((ChildOf(owner), Visibility::Hidden, Spawning(owner, Detail::Full))).id();
        let child = app.world_mut().spawn(ChildOf(pending)).id();
        {
            let mut tile = app.world_mut().get_mut::<Tile>(owner).unwrap();
            tile.detail = Some(Detail::Full);
            tile.shown_detail = Some(Detail::Middle);
            tile.showing = Some(old);
            tile.pending = Some(pending);
        }
        app.world_mut().run_system_once(choose).unwrap();
        let tile = app.world().get::<Tile>(owner).unwrap();
        assert!(tile.shown());
        assert_eq!(tile.showing, Some(old));
        assert!(app.world().get_entity(pending).is_err());
        assert!(app.world().get_entity(child).is_err());
        assert_eq!(*app.world().get::<Visibility>(old).unwrap(), Visibility::Inherited);
    }

    #[test]
    fn middle_tiles_wait_until_the_world_has_loaded() {
        let mut app = App::new();
        app.add_plugins(MinimalPlugins).add_plugins(bevy::asset::AssetPlugin::default());
        app.init_asset::<bevy::world_serialization::WorldAsset>();
        app.init_resource::<Settings>();
        app.world_mut().spawn((Camera3d::default(), GlobalTransform::from(Transform::from_xyz(1000.0, 0.0, 0.0))));
        let near = app.world_mut().spawn(Tile::named("tile 1 2", Vec3::new(1000.0, 0.0, 10.0)).unwrap()).id();
        let far = app.world_mut().spawn(Tile::named("tile 2 2", Vec3::ZERO).unwrap()).id();
        app.world_mut().run_system_once(choose).unwrap();
        assert_eq!(app.world().get::<Tile>(near).unwrap().detail, Some(Detail::Full));
        assert!(app.world().get::<Tile>(far).unwrap().pending.is_none());
        app.init_resource::<Loaded>();
        app.world_mut().run_system_once(choose).unwrap();
        assert_eq!(app.world().get::<Tile>(far).unwrap().detail, Some(Detail::Middle));
        assert!(app.world().get::<Tile>(far).unwrap().pending.is_some());
    }

    #[test]
    fn failed_scene_releases_pending_and_keeps_old_tile() {
        use bevy::world_serialization::WorldAsset;
        let mut app = App::new();
        app.add_plugins(MinimalPlugins).add_plugins(bevy::asset::AssetPlugin::default());
        app.init_asset::<WorldAsset>();
        let scene: Handle<WorldAsset> = app.world().resource::<AssetServer>().load("missing-tile-for-test.no-loader");
        let owner = app.world_mut().spawn(Tile::named("tile 1 2", Vec3::ZERO).unwrap()).id();
        let old = app.world_mut().spawn((ChildOf(owner), Visibility::Inherited)).id();
        let pending = app
            .world_mut()
            .spawn((ChildOf(owner), WorldAssetRoot(scene.clone()), Spawning(owner, Detail::Full), Visibility::Hidden))
            .id();
        {
            let mut tile = app.world_mut().get_mut::<Tile>(owner).unwrap();
            tile.detail = Some(Detail::Full);
            tile.shown_detail = Some(Detail::Middle);
            tile.showing = Some(old);
            tile.pending = Some(pending);
        }
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(3);
        while !matches!(app.world().resource::<AssetServer>().load_state(&scene), LoadState::Failed(_)) {
            assert!(std::time::Instant::now() < deadline, "failed asset must reach a terminal state");
            app.update();
            std::thread::sleep(std::time::Duration::from_millis(1));
        }
        app.world_mut().run_system_once(give_up).unwrap();
        let tile = app.world().get::<Tile>(owner).unwrap();
        assert!(tile.shown());
        assert_eq!(tile.showing, Some(old));
        assert!(tile.pending.is_none());
        assert!(app.world().get_entity(pending).is_err());
    }

    #[test]
    fn invalid_surface_profile_fails_tile_and_reports_its_asset() {
        use bevy::gltf::GltfExtras;
        use bevy::world_serialization::WorldAsset;
        let mut app = App::new();
        app.add_plugins(MinimalPlugins).add_plugins(bevy::asset::AssetPlugin::default());
        app.init_asset::<WorldAsset>();
        let scene = app.world().resource::<AssetServer>().load("world/tiles/invalid-paint.glb");
        let owner = app.world_mut().spawn(Tile::named("tile 1 2", Vec3::ZERO).unwrap()).id();
        let old = app.world_mut().spawn((ChildOf(owner), Visibility::Inherited)).id();
        let root = app.world_mut().spawn((ChildOf(owner), WorldAssetRoot(scene), Spawning(owner, Detail::Full))).id();
        app.world_mut()
            .spawn((ChildOf(root), GltfExtras { value: r#"{ "surface_paint": { "haze_length_m": 0 } }"#.into() }));
        {
            let mut tile = app.world_mut().get_mut::<Tile>(owner).unwrap();
            tile.showing = Some(old);
            tile.pending = Some(root);
        }
        app.world_mut().run_system_once(crate::vertex_paint::read_surfaces).unwrap();
        app.world_mut().run_system_once(failed_surface).unwrap();
        let tile = app.world().get::<Tile>(owner).unwrap();
        assert_eq!(tile.showing, Some(old));
        assert!(tile.failed && tile.pending.is_none());
        assert!(app.world().get_entity(root).is_err());
        assert!(app.world().resource::<Missing>().0.contains("invalid-paint.glb"));
    }

    #[test]
    fn default_ui_schedule_accepts_activation_order() {
        let mut app = App::new();
        app.add_plugins(bevy::asset::AssetPlugin::default()).init_asset::<bevy::shader::Shader>();
        app.add_plugins(
            DefaultPlugins
                .build()
                .disable::<bevy::asset::AssetPlugin>()
                .disable::<bevy::render::RenderPlugin>()
                .disable::<bevy::winit::WinitPlugin>(),
        );
        app.add_plugins(TilesPlugin);
        app.finish();
        app.cleanup();
        app.world_mut().schedule_scope(PostUpdate, |world, schedule| {
            schedule.initialize(world).expect("activation must fit the default PostUpdate schedule");
        });
    }
}
