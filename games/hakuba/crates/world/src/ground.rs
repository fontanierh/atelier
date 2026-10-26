//! What the player stands on and walks into: every mesh of the tiles shown, the ground, roads and rails, but their
//! cables, which hang overhead, and what each is made of. Models marked solid in their export use the same rays.

use bevy::ecs::system::SystemParam;
use bevy::picking::mesh_picking::ray_cast::{MeshRayCast, MeshRayCastSettings, RayCastBackfaces, RayCastVisibility};
use bevy::prelude::*;
use bevy::world_serialization::WorldInstanceReady;

use crate::tiles::Spawning;

/// The sea's surface, in metres above the world's zero.
pub const SEA_LEVEL_M: f32 = 0.0;

/// A tile node whose name starts with this is a cable.
const CABLE: &str = "cable";

/// The tile node that is the ground, and the end of the name of a tile node that is a road.
const GROUND: &str = "ground";
const ROAD: &str = "road";

pub struct GroundPlugin;

impl Plugin for GroundPlugin {
    fn build(&self, app: &mut App) {
        app.add_observer(mark);
    }
}

/// What a solid mesh is made of, as the feet hear it.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Surface {
    /// The ground itself: grass and earth.
    Ground,
    /// A road's asphalt.
    Road,
    /// Anything built, such as a guardrail and its posts.
    Built,
}

impl Surface {
    /// What a tile node named `name` is made of, if its name says.
    fn named(name: &str) -> Option<Self> {
        if name == GROUND {
            Some(Surface::Ground)
        } else if name.ends_with(ROAD) {
            Some(Surface::Road)
        } else {
            None
        }
    }
}

/// A mesh the player stands on and cannot pass through, and what it is made of.
#[derive(Component)]
struct Solid(Surface);

/// Marks a visible scenery mesh as built, including its back faces in ground rays.
pub(crate) fn built_solid() -> impl Bundle {
    (Solid(Surface::Built), RayCastBackfaces)
}

/// When a tile's version spawns, marks its meshes solid, but its cables, with what each is made of: what the nearest
/// node above it that names a surface says, or built. Rays meet them from either side: a guardrail is a single sheet.
fn mark(
    ready: On<WorldInstanceReady>,
    mut commands: Commands,
    spawning: Query<(), With<Spawning>>,
    children: Query<&Children>,
    parents: Query<&ChildOf>,
    meshes: Query<(), With<Mesh3d>>,
    names: Query<&Name>,
) {
    if !spawning.contains(ready.entity) {
        return;
    }
    let cables: Vec<Entity> = children
        .iter_descendants(ready.entity)
        .filter(|node| names.get(*node).is_ok_and(|name| name.starts_with(CABLE)))
        .flat_map(|cable| std::iter::once(cable).chain(children.iter_descendants(cable)))
        .collect();
    for node in children.iter_descendants(ready.entity) {
        if meshes.contains(node) && !cables.contains(&node) {
            let surface = std::iter::once(node)
                .chain(parents.iter_ancestors(node))
                .take_while(|above| *above != ready.entity)
                .find_map(|above| names.get(above).ok().and_then(|name| Surface::named(name)))
                .unwrap_or(Surface::Built);
            commands.entity(node).insert((Solid(surface), RayCastBackfaces));
        }
    }
}

/// Where a ray met something solid.
#[derive(Clone, Copy, Debug)]
pub struct Hit {
    pub point: Vec3,
    /// The surface's normal there, facing the ray.
    pub normal: Vec3,
    pub distance: f32,
    /// What it is made of.
    pub surface: Surface,
}

/// Casting rays at what is solid.
#[derive(SystemParam)]
pub struct Ground<'w, 's> {
    cast: MeshRayCast<'w, 's>,
    solids: Query<'w, 's, &'static Solid>,
}

impl Ground<'_, '_> {
    /// The first solid thing a ray from `from` toward `direction` meets within `reach` metres.
    pub fn cast(&mut self, from: Vec3, direction: Dir3, reach: f32) -> Option<Hit> {
        let solids = &self.solids;
        let solid = |entity: Entity| solids.contains(entity);
        let settings = MeshRayCastSettings::default()
            .with_visibility(RayCastVisibility::Any)
            .with_filter(&solid)
            .always_early_exit();
        let (entity, hit) = self.cast.cast_ray(Ray3d::new(from, direction), &settings).first()?;
        let normal = if hit.normal.dot(*direction) > 0.0 { -hit.normal } else { hit.normal };
        let surface = solids.get(*entity).map_or(Surface::Built, |solid| solid.0);
        (hit.distance <= reach).then_some(Hit { point: hit.point, normal, distance: hit.distance, surface })
    }

    /// The solid ground below `at`, from up to `above` metres over it to `below` metres under it.
    pub fn below(&mut self, at: Vec3, above: f32, below: f32) -> Option<Hit> {
        self.cast(at + Vec3::Y * above, Dir3::NEG_Y, above + below)
    }
}
