//! The world's tiles: each shows its full version near the camera, as far as the Detail setting says, its middle
//! version further out, and nothing beyond. A tile keeps showing its old version until the new one has spawned, so
//! nothing flickers in between. A version that fails to load is dropped, and its tile stays as it is.

use bevy::asset::LoadState;
use bevy::prelude::*;
use bevy::world_serialization::{WorldAssetRoot, WorldInstanceReady};
use hakuba_screens::Screen;
use hakuba_settings::Settings;

/// Up to how far a tile shows its middle version.
const MIDDLE_M: f32 = 2500.0;

/// The folder of the tiles' models, under the assets.
pub const TILES: &str = "world/tiles";

pub struct TilesPlugin;

impl Plugin for TilesPlugin {
    fn build(&self, app: &mut App) {
        app.add_observer(swap).add_systems(Update, (choose, give_up).run_if(in_state(Screen::World)));
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Detail {
    Full,
    Middle,
}

/// One tile of the world, by column and row, and what it shows.
#[derive(Component)]
pub struct Tile {
    column: u32,
    row: u32,
    centre: Vec3,
    /// The detail it shows or is loading, if any.
    detail: Option<Detail>,
    /// The version it shows.
    showing: Option<Entity>,
    /// Whether a version of it failed to load: it then stays as it is, and holds nothing up.
    failed: bool,
}

impl Tile {
    /// The tile a node named `tile <column> <row>` at `centre` stands for.
    pub fn named(name: &str, centre: Vec3) -> Option<Self> {
        let mut words = name.strip_prefix("tile ")?.split(' ');
        let (column, row) = (words.next()?.parse().ok()?, words.next()?.parse().ok()?);
        Some(Self { column, row, centre, detail: None, showing: None, failed: false })
    }

    /// Whether it shows the version it needs, or nothing when it needs none, or has failed to load one.
    pub fn shown(&self) -> bool {
        self.failed || self.detail.is_some() == self.showing.is_some()
    }

    fn path(&self, detail: Detail) -> String {
        let suffix = if detail == Detail::Full { "" } else { ".middle" };
        format!("{TILES}/{}_{}{suffix}.glb", self.column, self.row)
    }
}

/// A tile's version that is spawning, by its tile.
#[derive(Component)]
pub struct Spawning(Entity);

/// Picks each tile's detail from its distance to the camera, and starts spawning the version it needs.
fn choose(
    mut commands: Commands,
    assets: Res<AssetServer>,
    camera: Single<&GlobalTransform, With<Camera3d>>,
    settings: Res<Settings>,
    mut tiles: Query<(Entity, &mut Tile)>,
) {
    let eye = camera.translation();
    for (entity, mut tile) in &mut tiles {
        let distance = (tile.centre - eye).with_y(0.0).length();
        let detail = match distance {
            d if d < settings.detail.full_m() => Some(Detail::Full),
            d if d < MIDDLE_M => Some(Detail::Middle),
            _ => None,
        };
        if detail == tile.detail || tile.failed {
            continue;
        }
        tile.detail = detail;
        match detail {
            Some(detail) => {
                let scene = assets.load(GltfAssetLabel::Scene(0).from_asset(tile.path(detail)));
                commands.spawn((WorldAssetRoot(scene), Spawning(entity), ChildOf(entity)));
            }
            None => {
                if let Some(showing) = tile.showing.take() {
                    commands.entity(showing).despawn();
                }
            }
        }
    }
}

/// Drops a tile's version that failed to load, which the loading splash reports, so the tile no longer waits for it.
fn give_up(
    mut commands: Commands,
    assets: Res<AssetServer>,
    spawning: Query<(Entity, &Spawning, &WorldAssetRoot)>,
    mut tiles: Query<&mut Tile>,
) {
    for (entity, Spawning(tile), root) in &spawning {
        if !matches!(assets.load_state(&root.0), LoadState::Failed(_)) {
            continue;
        }
        commands.entity(entity).despawn();
        if let Ok(mut tile) = tiles.get_mut(*tile) {
            tile.failed = true;
        }
    }
}

/// When a tile's new version has spawned, removes the version it showed before.
fn swap(
    ready: On<WorldInstanceReady>,
    mut commands: Commands,
    spawning: Query<&Spawning>,
    mut tiles: Query<&mut Tile>,
) {
    let Ok(Spawning(tile)) = spawning.get(ready.entity) else { return };
    commands.entity(ready.entity).remove::<Spawning>();
    let Ok(mut tile) = tiles.get_mut(*tile) else { return };
    if let Some(old) = tile.showing.replace(ready.entity) {
        commands.entity(old).despawn();
    }
}
