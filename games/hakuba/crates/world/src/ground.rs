//! What the player stands on and walks into: every mesh of the tiles shown, the ground, roads and rails, but their
//! cables, which hang overhead, and what each is made of. Models marked solid in their export use the same rays.

use bevy::camera::primitives::Aabb;
use bevy::camera::visibility::{InheritedVisibility, ViewVisibility};
use bevy::ecs::system::SystemParam;
use bevy::mesh::{Indices, PrimitiveTopology};
use bevy::picking::mesh_picking::ray_cast::{
    Backfaces, RayCastBackfaces, RayMeshHit, ray_aabb_intersection_3d, ray_mesh_intersection,
};
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

type SolidMesh = (&'static Solid, &'static Mesh3d, &'static Aabb, &'static GlobalTransform, Has<RayCastBackfaces>);
type RayVisible = (With<InheritedVisibility>, With<ViewVisibility>);

/// Casting rays at what is solid.
#[derive(SystemParam)]
pub struct Ground<'w, 's> {
    meshes: Res<'w, Assets<Mesh>>,
    solids: Query<'w, 's, SolidMesh, RayVisible>,
}

impl Ground<'_, '_> {
    /// @cc [owner:fontanierh,label:performance] bounded-solid-rays
    /// Ground rays MUST consider only solid meshes and skip triangle tests for bounds beyond the requested reach.
    ///
    /// The first solid thing a ray from `from` toward `direction` meets within `reach` metres.
    pub fn cast(&mut self, from: Vec3, direction: Dir3, reach: f32) -> Option<Hit> {
        let ray = Ray3d::new(from, direction);
        // Allow for rounding at the boundary; the final mesh hit still enforces the exact reach.
        let margin = reach.abs().max(1.0) * 1e-5;
        let mut candidates: Vec<_> = self
            .solids
            .iter()
            .filter_map(|(solid, mesh, bounds, transform, backfaces)| {
                let bounds = Aabb3d::new(bounds.center, bounds.half_extents);
                ray_aabb_intersection_3d(ray, &bounds, &transform.affine())
                    .filter(|distance| *distance <= reach + margin)
                    .map(|distance| (distance, solid, mesh, transform, backfaces))
            })
            .collect();
        candidates.sort_unstable_by(|a, b| a.0.total_cmp(&b.0));
        let mut nearest: Option<Hit> = None;
        for (entry, solid, mesh, transform, backfaces) in candidates {
            if nearest.is_some_and(|hit| entry > hit.distance + margin) {
                break;
            }
            let Some(mesh) = self.meshes.get(&mesh.0) else { continue };
            let Some(hit) = intersect(mesh, transform, ray, backfaces) else { continue };
            if hit.distance <= reach && nearest.is_none_or(|previous| hit.distance < previous.distance) {
                let normal = if hit.normal.dot(*direction) > 0.0 { -hit.normal } else { hit.normal };
                nearest = Some(Hit { point: hit.point, normal, distance: hit.distance, surface: solid.0 });
            }
        }
        nearest
    }

    /// The solid ground below `at`, from up to `above` metres over it to `below` metres under it.
    pub fn below(&mut self, at: Vec3, above: f32, below: f32) -> Option<Hit> {
        self.cast(at + Vec3::Y * above, Dir3::NEG_Y, above + below)
    }
}

/// Adapts Bevy's mesh data to its public triangle intersection routine.
fn intersect(mesh: &Mesh, transform: &GlobalTransform, ray: Ray3d, backfaces: bool) -> Option<RayMeshHit> {
    if mesh.primitive_topology() != PrimitiveTopology::TriangleList {
        return None;
    }
    let positions = mesh.try_attribute(Mesh::ATTRIBUTE_POSITION).ok()?.as_float3()?;
    let normals = mesh.try_attribute(Mesh::ATTRIBUTE_NORMAL).ok().and_then(|values| values.as_float3());
    let cull = if backfaces { Backfaces::Include } else { Backfaces::Cull };
    let transform = transform.affine();
    match mesh.try_indices().ok() {
        Some(Indices::U16(indices)) => {
            ray_mesh_intersection(ray, &transform, positions, normals, Some(indices), None, cull)
        }
        Some(Indices::U32(indices)) => {
            ray_mesh_intersection(ray, &transform, positions, normals, Some(indices), None, cull)
        }
        None => ray_mesh_intersection::<u32>(ray, &transform, positions, normals, None, None, cull),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use bevy::ecs::system::RunSystemOnce;

    #[test]
    fn bounded_rays_keep_nearest_transformed_hits_and_reject_distant_ones() {
        let mut app = App::new();
        app.add_plugins(MinimalPlugins).init_resource::<Assets<Mesh>>();
        let cube = app.world_mut().resource_mut::<Assets<Mesh>>().add(Mesh::from(Cuboid::new(1.0, 1.0, 1.0)));
        let bounds = Aabb::from_min_max(Vec3::splat(-0.5), Vec3::splat(0.5));
        let near = Transform::from_xyz(5.0, 0.0, 0.0)
            .with_rotation(Quat::from_rotation_y(std::f32::consts::FRAC_PI_4))
            .with_scale(Vec3::new(2.0, 1.0, 0.75));
        let far = Transform::from_xyz(20.0, 0.0, 0.0);
        for (transform, surface) in [(near, Surface::Built), (far, Surface::Road)] {
            app.world_mut().spawn((
                Mesh3d(cube.clone()),
                transform,
                GlobalTransform::from(transform),
                bounds,
                Visibility::default(),
                Solid(surface),
                RayCastBackfaces,
            ));
        }
        app.world_mut()
            .run_system_once(move |mut ground: Ground| {
                let cast = |ground: &mut Ground, from, reach| ground.cast(from, Dir3::X, reach);
                assert!(cast(&mut ground, Vec3::ZERO, 2.0).is_none());
                let near_hit = cast(&mut ground, Vec3::ZERO, 10.0).expect("rotated and scaled solid is within reach");
                assert_eq!(near_hit.surface, Surface::Built);
                let long_hit = cast(&mut ground, Vec3::ZERO, 30.0).unwrap();
                assert_eq!(long_hit.surface, near_hit.surface);
                assert!((long_hit.distance - near_hit.distance).abs() < 1e-5);
                assert!(cast(&mut ground, Vec3::new(12.0, 0.0, 0.0), 4.0).is_none());
                assert_eq!(cast(&mut ground, Vec3::new(12.0, 0.0, 0.0), 10.0).unwrap().surface, Surface::Road);
                assert_eq!(cast(&mut ground, near.translation, 3.0).unwrap().surface, Surface::Built);
            })
            .unwrap();
    }
}
