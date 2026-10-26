//! The world's tiles: each shows its full version near the camera, its middle version further out, and nothing
//! beyond. A tile keeps showing its old version until the new one has spawned, so nothing flickers in between.

use bevy::prelude::*;
use bevy::world_serialization::WorldInstanceReady;
use hakuba_screens::Screen;

/// Up to how far from the camera, to the tile's centre, a tile shows its full version.
const FULL_M: f32 = 160.0;

/// Up to how far a tile shows its middle version.
const MIDDLE_M: f32 = 2500.0;

pub struct TilesPlugin;

impl Plugin for TilesPlugin {
    fn build(&self, app: &mut App) {
        app.add_observer(swap).add_systems(Update, choose.run_if(in_state(Screen::World)));
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
}

impl Tile {
    /// The tile a node named `tile <column> <row>` at `centre` stands for.
    pub fn named(name: &str, centre: Vec3) -> Option<Self> {
        let mut words = name.strip_prefix("tile ")?.split(' ');
        let (column, row) = (words.next()?.parse().ok()?, words.next()?.parse().ok()?);
        Some(Self { column, row, centre, detail: None, showing: None })
    }

    fn path(&self, detail: Detail) -> String {
        let suffix = if detail == Detail::Full { "" } else { ".middle" };
        format!("world/tiles/{}_{}{suffix}.glb", self.column, self.row)
    }
}

/// A tile's version that is spawning, by its tile.
#[derive(Component)]
struct Spawning(Entity);

/// Picks each tile's detail from its distance to the camera, and starts spawning the version it needs.
fn choose(
    mut commands: Commands,
    assets: Res<AssetServer>,
    camera: Single<&GlobalTransform, With<Camera3d>>,
    mut tiles: Query<(Entity, &mut Tile)>,
) {
    let eye = camera.translation();
    for (entity, mut tile) in &mut tiles {
        let distance = (tile.centre - eye).with_y(0.0).length();
        let detail = match distance {
            d if d < FULL_M => Some(Detail::Full),
            d if d < MIDDLE_M => Some(Detail::Middle),
            _ => None,
        };
        if detail == tile.detail {
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
