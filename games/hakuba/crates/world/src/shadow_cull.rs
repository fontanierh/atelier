//! Culls the sun's shadow casters a whole tile at a time. Bevy tests every shadow-casting mesh against every cascade
//! each frame, and the world is thousands of tiles of meshes, nearly all of them far outside the cascades. Each tile
//! keeps a box around every mesh it has held; a tile whose box misses every cascade marks its casters
//! `NotShadowCaster`, which Bevy's test skips without looking at them, and unmarks them the frame its box meets one.
//! A box that misses a cascade's half-space holds no mesh that meets it, so the shadow maps draw exactly what they
//! drew before.

use bevy::camera::primitives::{Aabb, CascadesFrusta};
use bevy::camera::visibility::{NoFrustumCulling, VisibilitySystems};
use bevy::light::{NotShadowCaster, SimulationLightSystems};
use bevy::math::{Affine3A, Vec3A};
use bevy::prelude::*;

use crate::loading::Loaded;
use crate::scenery::ShadowDistance;

pub struct ShadowCullPlugin;

impl Plugin for ShadowCullPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(
            PostUpdate,
            (grow, cull)
                .chain()
                .after(VisibilitySystems::CalculateBounds)
                .after(TransformSystems::Propagate)
                .after(SimulationLightSystems::UpdateLightFrusta)
                .before(SimulationLightSystems::CheckLightVisibility),
        );
    }
}

/// A tile's box around every mesh it has held, in world space, and whether its casters are marked.
#[derive(Component, Default)]
pub struct TileShadows {
    bounds: Option<(Vec3A, Vec3A)>,
    /// It holds a caster Bevy does not cull or has not bounded, which Bevy draws in every cascade: it casts until a
    /// mesh in it changes.
    blocked: bool,
    /// A caster Bevy draws in every cascade spawned into it while it was culled.
    restore: bool,
    culled: bool,
}

/// A caster this module marked `NotShadowCaster`, and only this module unmarks.
#[derive(Component)]
struct Culled;

type Moved = Or<(Changed<GlobalTransform>, Changed<Aabb>, Added<Mesh3d>)>;

/// Grows each tile's box by its meshes as they spawn or move. Versions replace each other in the same tile, so the box
/// only grows: it stays around every mesh the tile holds.
#[allow(clippy::type_complexity)]
fn grow(
    mut commands: Commands,
    meshes: Query<
        (Entity, &GlobalTransform, Option<&Aabb>, Has<NoFrustumCulling>, Has<NotShadowCaster>),
        (With<Mesh3d>, Without<ShadowDistance>, Moved),
    >,
    parents: Query<&ChildOf>,
    mut tiles: Query<&mut TileShadows>,
) {
    for (entity, transform, aabb, unculled, not_caster) in &meshes {
        let Some(tile) = parents.iter_ancestors(entity).find(|a| tiles.contains(*a)) else { continue };
        let mut shadows = tiles.get_mut(tile).unwrap();
        if let Some(aabb) = aabb {
            let matrix = transform.affine();
            let centre = matrix.transform_point3a(aabb.center);
            let half = matrix.matrix3.x_axis.abs() * aabb.half_extents.x
                + matrix.matrix3.y_axis.abs() * aabb.half_extents.y
                + matrix.matrix3.z_axis.abs() * aabb.half_extents.z;
            let (min, max) = (centre - half, centre + half);
            shadows.bounds = Some(match shadows.bounds {
                Some((lo, hi)) => (lo.min(min), hi.max(max)),
                None => (min, max),
            });
        }
        shadows.blocked = false;
        if not_caster || !shadows.culled {
            continue;
        }
        if unculled || aabb.is_none() {
            shadows.restore = true;
        } else {
            // A caster spawned into a culled tile is marked at once, its box already in the tile's.
            commands.entity(entity).insert((NotShadowCaster, Culled));
        }
    }
}

/// Marks or unmarks each tile's casters as its box leaves or meets the sun's cascades.
#[allow(clippy::type_complexity)]
fn cull(
    mut commands: Commands,
    loaded: Option<Res<Loaded>>,
    lights: Query<(&DirectionalLight, &CascadesFrusta)>,
    mut tiles: Query<(Entity, &mut TileShadows)>,
    children: Query<&Children>,
    casters: Query<
        (Has<NotShadowCaster>, Has<Culled>, Has<NoFrustumCulling>, Has<Aabb>),
        (With<Mesh3d>, Without<ShadowDistance>),
    >,
) {
    // The splash draws every caster while it prepares their pipelines, and a light without shadows tests nothing.
    let active = loaded.is_some() && lights.iter().any(|(light, _)| light.shadow_maps_enabled);
    for (tile, mut shadows) in &mut tiles {
        let cull = active
            && !shadows.restore
            && !shadows.blocked
            && shadows.bounds.is_some_and(|(min, max)| {
                let aabb = Aabb { center: (min + max) / 2.0, half_extents: (max - min) / 2.0 };
                // As Bevy tests casters: a caster may lie before a cascade's near plane.
                !lights.iter().any(|(_, frusta)| {
                    frusta.frusta.values().flatten().any(|f| f.intersects_obb(&aabb, &Affine3A::IDENTITY, false, true))
                })
            });
        shadows.restore = false;
        if cull == shadows.culled {
            continue;
        }
        if cull
            && children
                .iter_descendants(tile)
                .any(|e| casters.get(e).is_ok_and(|(not, _, unculled, bounded)| !not && (unculled || !bounded)))
        {
            shadows.blocked = true;
            continue;
        }
        shadows.culled = cull;
        for entity in children.iter_descendants(tile) {
            let Ok((not_caster, culled, ..)) = casters.get(entity) else { continue };
            if cull && !not_caster {
                commands.entity(entity).insert((NotShadowCaster, Culled));
            } else if !cull && culled {
                commands.entity(entity).remove::<(NotShadowCaster, Culled)>();
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use bevy::camera::primitives::Frustum;
    use bevy::shape::{HalfSpace, ViewFrustum};

    use super::*;

    fn app() -> App {
        let mut app = App::new();
        app.add_systems(Update, (grow, cull).chain());
        app.insert_resource(Loaded::default());
        app
    }

    fn light(app: &mut App, frustum: Frustum) {
        let mut frusta = CascadesFrusta::default();
        frusta.frusta.insert(Entity::PLACEHOLDER, vec![frustum]);
        app.world_mut().spawn((DirectionalLight { shadow_maps_enabled: true, ..default() }, frusta));
    }

    fn mesh(app: &mut App, tile: Entity, at: Vec3) -> Entity {
        app.world_mut()
            .spawn((
                Mesh3d::default(),
                Aabb::from_min_max(Vec3::splat(-1.0), Vec3::splat(1.0)),
                GlobalTransform::from_translation(at),
                ChildOf(tile),
            ))
            .id()
    }

    /// A box-shaped cascade between two corners: left, right, bottom, top, near and far.
    fn boxed(min: Vec3, max: Vec3) -> Frustum {
        let side = |normal: Vec3, at: Vec3| HalfSpace::new(normal.extend(-normal.dot(at)));
        Frustum(ViewFrustum {
            half_spaces: [
                side(Vec3::X, min),
                side(-Vec3::X, max),
                side(Vec3::Y, min),
                side(-Vec3::Y, max),
                side(-Vec3::Z, max),
                side(Vec3::Z, min),
            ],
        })
    }

    fn cube() -> Frustum {
        boxed(Vec3::splat(-10.0), Vec3::splat(10.0))
    }

    #[test]
    fn a_tile_outside_every_cascade_stops_casting_and_casts_again_when_it_meets_one() {
        let mut app = app();
        light(&mut app, cube());
        let far = app.world_mut().spawn(TileShadows::default()).id();
        let near = app.world_mut().spawn(TileShadows::default()).id();
        let far_mesh = mesh(&mut app, far, Vec3::new(100.0, 0.0, 0.0));
        let near_mesh = mesh(&mut app, near, Vec3::ZERO);
        let seen_only = app.world_mut().spawn((Mesh3d::default(), NotShadowCaster, ChildOf(far))).id();
        app.update();
        assert!(app.world().get::<NotShadowCaster>(far_mesh).is_some());
        assert!(app.world().get::<NotShadowCaster>(near_mesh).is_none());

        let mut frusta = app.world_mut().query::<&mut CascadesFrusta>();
        *frusta.single_mut(app.world_mut()).unwrap().frusta.get_mut(&Entity::PLACEHOLDER).unwrap() =
            vec![boxed(Vec3::new(90.0, -10.0, -10.0), Vec3::new(110.0, 10.0, 10.0))];
        app.update();
        assert!(app.world().get::<NotShadowCaster>(far_mesh).is_none());
        assert!(app.world().get::<NotShadowCaster>(seen_only).is_some(), "a mesh that never cast stays as it was");
    }

    #[test]
    fn nothing_is_culled_under_the_splash_or_with_an_unculled_mesh() {
        let mut app = app();
        app.world_mut().remove_resource::<Loaded>();
        light(&mut app, cube());
        let tile = app.world_mut().spawn(TileShadows::default()).id();
        let far_mesh = mesh(&mut app, tile, Vec3::new(100.0, 0.0, 0.0));
        app.update();
        assert!(app.world().get::<NotShadowCaster>(far_mesh).is_none());

        app.world_mut().entity_mut(far_mesh).insert(NoFrustumCulling);
        app.world_mut().get_mut::<GlobalTransform>(far_mesh).unwrap().set_changed();
        app.insert_resource(Loaded::default());
        app.update();
        assert!(app.world().get::<NotShadowCaster>(far_mesh).is_none());
    }
}
