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
use parry3d::{
    math::Pose,
    query::{ShapeCastOptions, ShapeCastStatus, cast_shapes},
    shape::{Capsule, Triangle},
};

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

/// A solid belonging to a hidden tile until its complete version is activated.
#[derive(Component)]
pub(crate) struct PendingSolid(Surface);

pub(crate) fn promote(
    root: Entity,
    children: &Query<&Children>,
    pending: &Query<&PendingSolid>,
    commands: &mut Commands,
) {
    for entity in children.iter_descendants(root) {
        if let Ok(surface) = pending.get(entity) {
            commands.entity(entity).remove::<PendingSolid>().insert(Solid(surface.0));
        }
    }
}

/// Marks a scenery mesh as built when its tile activates, including back faces in ground rays.
pub(crate) fn built_solid() -> impl Bundle {
    (PendingSolid(Surface::Built), RayCastBackfaces)
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
            commands.entity(node).insert((PendingSolid(surface), RayCastBackfaces));
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
type MaybeSolidMesh = (
    &'static Solid,
    Option<&'static Mesh3d>,
    Option<&'static Aabb>,
    Option<&'static GlobalTransform>,
    Option<&'static InheritedVisibility>,
    Option<&'static ViewVisibility>,
);

/// Casting rays at what is solid.
#[derive(SystemParam)]
pub struct Ground<'w, 's> {
    meshes: Res<'w, Assets<Mesh>>,
    solids: Query<'w, 's, SolidMesh, RayVisible>,
    sweep_solids: Query<'w, 's, MaybeSolidMesh>,
}

impl Ground<'_, '_> {
    /// @cc [owner:fontanierh,label:correctness] capsule-sweep-keeps-solid-geometry
    /// A capsule sweep MUST use every intersecting solid triangle in its actual world transform and MUST fail closed
    /// on unavailable, unsupported or invalid mesh data. The broad phase MUST NOT discard a possible swept contact.
    ///
    /// Sweeps a vertical capsule from its feet by `delta`. Unsupported collision data returns an error.
    pub fn sweep_capsule(
        &self,
        feet: Vec3,
        radius: f32,
        height: f32,
        delta: Vec3,
    ) -> Result<Option<Hit>, &'static str> {
        if !feet.is_finite()
            || !delta.is_finite()
            || !radius.is_finite()
            || !height.is_finite()
            || radius <= 0.0
            || height < 2.0 * radius
        {
            return Err("invalid capsule");
        }
        let extent = Vec3::new(radius, height * 0.5, radius);
        let centre = feet + Vec3::Y * (height * 0.5);
        let margin = (centre.abs().max_element() + delta.abs().max_element() + height).max(1.0) * 1e-5;
        let low = centre.min(centre + delta) - extent - Vec3::splat(margin);
        let high = centre.max(centre + delta) + extent + Vec3::splat(margin);
        if !centre.is_finite() || !low.is_finite() || !high.is_finite() {
            return Err("invalid swept bounds");
        }
        let capsule = Capsule::new_y(height * 0.5 - radius, radius);
        let pose = Pose::translation(centre.x, centre.y, centre.z);
        let options = ShapeCastOptions { max_time_of_impact: 1.0, stop_at_penetration: false, ..Default::default() };
        let overlaps = |a: Vec3, b: Vec3| a.cmple(high).all() && b.cmpge(low).all();
        let mut best: Option<Hit> = None;
        for (solid, mesh, bounds, transform, inherited, visible) in &self.sweep_solids {
            let (Some(mesh), Some(bounds), Some(transform), Some(_), Some(_)) =
                (mesh, bounds, transform, inherited, visible)
            else {
                return Err("solid missing collision components");
            };
            let affine = transform.affine();
            let bounds_low = Vec3::from(bounds.center - bounds.half_extents);
            let bounds_high = Vec3::from(bounds.center + bounds.half_extents);
            let mut world_low = Vec3::splat(f32::INFINITY);
            let mut world_high = Vec3::splat(f32::NEG_INFINITY);
            for x in [bounds_low.x, bounds_high.x] {
                for y in [bounds_low.y, bounds_high.y] {
                    for z in [bounds_low.z, bounds_high.z] {
                        let p = affine.transform_point3(Vec3::new(x, y, z));
                        world_low = world_low.min(p);
                        world_high = world_high.max(p);
                    }
                }
            }
            if !world_low.is_finite() || !world_high.is_finite() {
                return Err("invalid solid transform");
            }
            if !overlaps(world_low, world_high) {
                continue;
            }
            let mesh = self.meshes.get(&mesh.0).ok_or("solid mesh unavailable")?;
            if mesh.primitive_topology() != PrimitiveTopology::TriangleList {
                return Err("unsupported solid topology");
            }
            let positions = mesh
                .try_attribute(Mesh::ATTRIBUTE_POSITION)
                .ok()
                .and_then(|v| v.as_float3())
                .ok_or("unsupported solid positions")?;
            let indices = mesh.try_indices_option().map_err(|_| "solid indices inaccessible")?;
            let count = match indices {
                Some(Indices::U16(v)) => v.len(),
                Some(Indices::U32(v)) => v.len(),
                None => positions.len(),
            };
            if count % 3 != 0 {
                return Err("invalid triangle indices");
            }
            for first in (0..count).step_by(3) {
                let mut p = [Vec3::ZERO; 3];
                for i in 0..3 {
                    let index = match indices {
                        Some(Indices::U16(v)) => usize::from(v[first + i]),
                        Some(Indices::U32(v)) => v[first + i] as usize,
                        None => first + i,
                    };
                    p[i] = affine.transform_point3(Vec3::from_array(*positions.get(index).ok_or("invalid index")?));
                    if !p[i].is_finite() {
                        return Err("invalid solid vertex");
                    }
                }
                let min = p[0].min(p[1]).min(p[2]);
                let max = p[0].max(p[1]).max(p[2]);
                if !overlaps(min, max) || (p[1] - p[0]).cross(p[2] - p[0]).length_squared() == 0.0 {
                    continue;
                }
                let triangle = Triangle::new(p[0], p[1], p[2]);
                let hit = cast_shapes(&pose, delta, &capsule, &Pose::IDENTITY, Vec3::ZERO, &triangle, options)
                    .map_err(|_| "unsupported capsule collision")?;
                if let Some(hit) = hit {
                    if hit.status != ShapeCastStatus::Converged
                        || !hit.time_of_impact.is_finite()
                        || !(0.0..=1.0).contains(&hit.time_of_impact)
                        || !hit.witness2.is_finite()
                        || !hit.normal2.is_finite()
                    {
                        return Err("uncertain capsule contact");
                    }
                    let distance = hit.time_of_impact * delta.length();
                    if best.is_none_or(|previous| distance < previous.distance) {
                        best = Some(Hit { point: hit.witness2, normal: hit.normal2, distance, surface: solid.0 });
                    }
                }
            }
        }
        Ok(best)
    }
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
    fn capsule_can_lift_from_a_tangent_floor() {
        let mut app = App::new();
        app.add_plugins(MinimalPlugins).init_resource::<Assets<Mesh>>();
        let mesh = app.world_mut().resource_mut::<Assets<Mesh>>().add(Mesh::from(Cuboid::new(4.0, 1.0, 4.0)));
        let transform = Transform::from_xyz(0.0, -0.5, 0.0);
        app.world_mut().spawn((
            Mesh3d(mesh),
            transform,
            GlobalTransform::from(transform),
            Aabb::from_min_max(Vec3::new(-2.0, -0.5, -2.0), Vec3::new(2.0, 0.5, 2.0)),
            Visibility::default(),
            Solid(Surface::Ground),
        ));
        app.world_mut()
            .run_system_once(|ground: Ground| {
                assert!(matches!(ground.sweep_capsule(Vec3::ZERO, 0.3, 1.6, Vec3::Y * 0.2), Ok(None)));
            })
            .unwrap();
    }

    #[test]
    fn capsule_can_lift_along_a_tangent_riser() {
        let mut app = App::new();
        app.add_plugins(MinimalPlugins).init_resource::<Assets<Mesh>>();
        let mesh = app.world_mut().resource_mut::<Assets<Mesh>>().add(Mesh::from(Cuboid::new(1.0, 0.18, 2.0)));
        let transform = Transform::from_xyz(0.8, 0.09, 0.0);
        app.world_mut().spawn((
            Mesh3d(mesh),
            transform,
            GlobalTransform::from(transform),
            Aabb::from_min_max(Vec3::new(-0.5, -0.09, -1.0), Vec3::new(0.5, 0.09, 1.0)),
            Visibility::default(),
            Solid(Surface::Built),
        ));
        app.world_mut()
            .run_system_once(|ground: Ground| {
                assert!(matches!(ground.sweep_capsule(Vec3::ZERO, 0.3, 1.6, Vec3::Y * 0.2), Ok(None)));
            })
            .unwrap();
    }

    #[test]
    fn capsule_drop_can_hit_a_ledge_before_its_centre_is_supported() {
        let mut app = App::new();
        app.add_plugins(MinimalPlugins).init_resource::<Assets<Mesh>>();
        let mesh = app.world_mut().resource_mut::<Assets<Mesh>>().add(Mesh::from(Cuboid::new(1.0, 0.18, 2.0)));
        let transform = Transform::from_xyz(0.8, 0.09, 0.0);
        app.world_mut().spawn((
            Mesh3d(mesh),
            transform,
            GlobalTransform::from(transform),
            Aabb::from_min_max(Vec3::new(-0.5, -0.09, -1.0), Vec3::new(0.5, 0.09, 1.0)),
            Visibility::default(),
            Solid(Surface::Built),
        ));
        app.world_mut()
            .run_system_once(|mut ground: Ground| {
                let from = Vec3::new(0.1, 0.3, 0.0);
                assert!(ground.sweep_capsule(from, 0.3, 1.6, Vec3::NEG_Y * 0.3).unwrap().is_some());
                assert!(ground.below(from, 0.0, 0.3).is_none());
            })
            .unwrap();
    }

    #[test]
    fn capsule_step_path_clears_a_low_block_but_hits_a_wall_and_ceiling() {
        fn scene(block_height: f32, ceiling: bool) -> App {
            let mut app = App::new();
            app.add_plugins(MinimalPlugins).init_resource::<Assets<Mesh>>();
            let mut add_box = |center: Vec3, size: Vec3| {
                let mesh =
                    app.world_mut().resource_mut::<Assets<Mesh>>().add(Mesh::from(Cuboid::new(size.x, size.y, size.z)));
                let transform = Transform::from_translation(center);
                app.world_mut().spawn((
                    Mesh3d(mesh),
                    transform,
                    GlobalTransform::from(transform),
                    Aabb::from_min_max(-size / 2.0, size / 2.0),
                    Visibility::default(),
                    Solid(Surface::Built),
                ));
            };
            add_box(Vec3::new(0.8, block_height / 2.0, 0.0), Vec3::new(1.0, block_height, 2.0));
            if ceiling {
                add_box(Vec3::new(0.0, 1.85, 0.0), Vec3::new(1.0, 0.1, 2.0));
            }
            app
        }
        let feet = Vec3::new(-0.02, 0.01, 0.0);
        let lift = Vec3::Y * 0.22;
        let forward = Vec3::X * 0.4;
        for (height, ceiling, lift_clear, forward_clear) in
            [(0.18, false, true, true), (0.6, false, true, false), (0.18, true, false, true)]
        {
            let mut app = scene(height, ceiling);
            app.world_mut()
                .run_system_once(move |ground: Ground| {
                    assert_eq!(ground.sweep_capsule(feet, 0.3, 1.6, lift).unwrap().is_none(), lift_clear);
                    if lift_clear {
                        assert_eq!(
                            ground.sweep_capsule(feet + lift, 0.3, 1.6, forward).unwrap().is_none(),
                            forward_clear
                        );
                    }
                })
                .unwrap();
        }
    }

    #[test]
    fn capsule_sweep_uses_transformed_solid_mesh_and_rejects_incomplete_solid() {
        let mut app = App::new();
        app.add_plugins(MinimalPlugins).init_resource::<Assets<Mesh>>();
        let cube = app.world_mut().resource_mut::<Assets<Mesh>>().add(Mesh::from(Cuboid::new(1.0, 2.0, 1.0)));
        let transform = Transform::from_xyz(3.0, 0.0, 0.0).with_scale(Vec3::new(2.0, 1.0, -0.5));
        app.world_mut().spawn((
            Mesh3d(cube),
            transform,
            GlobalTransform::from(transform),
            Aabb::from_min_max(Vec3::new(-0.5, -1.0, -0.5), Vec3::new(0.5, 1.0, 0.5)),
            Visibility::default(),
            Solid(Surface::Built),
        ));
        app.world_mut()
            .run_system_once(|ground: Ground| {
                let hit = ground.sweep_capsule(Vec3::ZERO, 0.3, 1.6, Vec3::X * 4.0).unwrap().unwrap();
                assert!((hit.distance - 1.7).abs() < 0.01, "{hit:?}");
            })
            .unwrap();
        app.world_mut().spawn(Solid(Surface::Built));
        app.world_mut()
            .run_system_once(|ground: Ground| {
                assert!(ground.sweep_capsule(Vec3::ZERO, 0.3, 1.6, Vec3::X).is_err());
            })
            .unwrap();
    }

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
