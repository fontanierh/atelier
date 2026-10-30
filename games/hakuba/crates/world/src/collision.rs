//! Immutable collision prepared from the world's own active solids, with predictive full-tile residency.
use crate::ground::Solid;
use crate::tiles::{CollisionActivation, Tile};
use bevy::gltf::GltfMaterialName;
use bevy::mesh::{Indices, PrimitiveTopology};
use bevy::prelude::*;
use bevy::transform::TransformSystems;
use hakuba_screens::Screen;
use hakuba_world_skate_schema::{Metadata, Rail, Zone};
use std::sync::Arc;

pub(crate) struct CollisionPlugin;
impl Plugin for CollisionPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<WorldCollision>().init_resource::<CollisionFocus>().add_systems(
            PostUpdate,
            publish.after(CollisionActivation).after(TransformSystems::Propagate).run_if(in_state(Screen::World)),
        );
    }
}

#[derive(Component)]
pub(crate) struct InitialCoverage;

#[derive(Resource)]
pub(crate) struct SkateMetadata(pub Metadata);
#[derive(Resource, serde::Deserialize)]
pub(crate) struct TileGrid {
    pub tile_m: f32,
}

/// Retains unbatched source instances. Render merge boundaries never change physical triangle order.
#[derive(Component)]
pub(crate) struct CollisionSource {
    pub mesh: Handle<Mesh>,
    pub instances: Vec<Transform>,
    pub material: String,
    pub face_materials: Vec<String>,
}

/// A swept horizontal corridor to keep in full detail before a rider enters it.
#[derive(Resource, Clone, Debug)]
pub struct CollisionFocus {
    pub enabled: bool,
    pub position: Vec3,
    pub velocity: Vec3,
    pub radius_m: f32,
    pub lookahead_s: f32,
    /// An optional remote destination, retained alongside the rider's current corridor until transfer completes.
    pub destination: Option<Vec3>,
}
impl Default for CollisionFocus {
    fn default() -> Self {
        Self {
            enabled: false,
            position: Vec3::ZERO,
            velocity: Vec3::ZERO,
            radius_m: 100.,
            lookahead_s: 2.,
            destination: None,
        }
    }
}
impl CollisionFocus {
    pub fn request(&mut self, position: Vec3, velocity: Vec3) {
        self.enabled = position.is_finite() && velocity.is_finite();
        self.position = position;
        self.velocity = velocity;
    }
    pub fn clear(&mut self) {
        self.enabled = false;
        self.destination = None;
    }
    fn bounds(&self) -> (Vec2, Vec2) {
        let from = self.position.xz();
        let to = (self.position + self.velocity * self.lookahead_s).xz();
        (from.min(to) - Vec2::splat(self.radius_m), from.max(to) + Vec2::splat(self.radius_m))
    }
    pub(crate) fn intersects(&self, centre: Vec3, span: f32) -> bool {
        if !self.enabled {
            return false;
        }
        let overlaps = |low: Vec2, high: Vec2| {
            (centre.xz() - Vec2::splat(span * 0.5)).cmple(high).all()
                && (centre.xz() + Vec2::splat(span * 0.5)).cmpge(low).all()
        };
        let (low, high) = self.bounds();
        overlaps(low, high)
            || self.destination.filter(|p| p.is_finite()).is_some_and(|destination| {
                let radius = Vec2::splat(self.radius_m);
                overlaps(destination.xz() - radius, destination.xz() + radius)
            })
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct CollisionTriangle {
    /// Authored winding, transformed to world metres. No ray-facing normal reversal.
    pub points: [Vec3; 3],
    pub material: String,
    pub surface: u16,
    /// Face index in the owning source primitive.
    pub source_face: usize,
}
#[derive(Clone, Debug, PartialEq)]
pub struct CollisionCoverage {
    pub tile: [u32; 2],
    pub min: Vec2,
    pub max: Vec2,
}
#[derive(Clone, Debug, Default)]
pub struct CollisionSnapshot {
    pub triangles: Vec<CollisionTriangle>,
    pub rails: Vec<Rail>,
    pub assist_zones: Vec<Zone>,
    pub boost_zones: Vec<Zone>,
    pub coverage: Vec<CollisionCoverage>,
    /// Every requested tile has installed complete full-detail collision and metadata is valid.
    pub ready: bool,
}
impl CollisionSnapshot {
    pub fn covers(&self, position: Vec3) -> bool {
        self.coverage.iter().any(|c| position.xz().cmpge(c.min).all() && position.xz().cmple(c.max).all())
    }
}
#[derive(Resource, Clone, Default)]
pub struct WorldCollision {
    pub generation: u64,
    pub snapshot: Arc<CollisionSnapshot>,
}

type SolidData = (
    Entity,
    &'static Solid,
    Option<&'static Mesh3d>,
    Option<&'static GlobalTransform>,
    Option<&'static CollisionSource>,
    Option<&'static GltfMaterialName>,
);

/// @cc [owner:fontanierh,label:correctness] immutable-world-collision
/// Snapshots MUST contain only the world's active solid meshes, including hidden collision, in stable source order.
/// Incomplete requested coverage MUST NOT be reported ready. Each generation owns its triangles beyond entity despawn.
fn publish(
    mut commands: Commands,
    initial: Query<Entity, With<InitialCoverage>>,
    mut output: ResMut<WorldCollision>,
    focus: Res<CollisionFocus>,
    grid: Option<Res<TileGrid>>,
    metadata: Option<Res<SkateMetadata>>,
    tiles: Query<&Tile>,
    children: Query<&Children>,
    solids: Query<SolidData>,
    meshes: Res<Assets<Mesh>>,
    mut previous: Local<Vec<(u32, u32, Option<Entity>, bool)>>,
) {
    let Some(grid) = grid else { return };
    let Some(metadata) = metadata else { return };
    let mut selected: Vec<_> = tiles
        .iter()
        .map(Tile::collision_state)
        .filter(|(_, centre, _, _, _)| focus.intersects(*centre, grid.tile_m))
        .collect();
    selected.sort_by_key(|(tile, _, _, _, _)| *tile);
    let signature: Vec<_> = selected.iter().map(|(id, _, root, full, _)| (id[0], id[1], *root, *full)).collect();
    if signature == *previous && output.generation != 0 {
        return;
    }
    let complete_signature = signature;
    let mut snapshot = CollisionSnapshot {
        ready: focus.enabled && !selected.is_empty(),
        rails: metadata.0.rails.clone(),
        assist_zones: metadata.0.assist_zones.clone(),
        boost_zones: metadata.0.boost_zones.clone(),
        ..Default::default()
    };
    let mut ordered = Vec::new();
    for (tile, centre, root, full, bounds) in selected {
        let Some(root) = root.filter(|_| full) else {
            snapshot.ready = false;
            continue;
        };
        let mut valid = true;
        for entity in children.iter_descendants(root) {
            let Ok((_, solid, mesh, global, source, name)) = solids.get(entity) else { continue };
            let (Some(mesh), Some(global)) = (mesh, global) else {
                valid = false;
                continue;
            };
            let handle = source.map_or(&mesh.0, |s| &s.mesh);
            let Some(mesh) = meshes.get(handle) else {
                valid = false;
                continue;
            };
            let material = source.map(|s| s.material.clone()).or_else(|| name.map(|n| n.0.clone())).unwrap_or_default();
            let surface =
                metadata.0.materials.iter().find(|m| m.material == material).map_or(solid.0.skate(), |m| m.surface)
                    as u16;
            let instances = source.map(|s| s.instances.as_slice()).unwrap_or(&[]);
            let transforms: Vec<_> = if instances.is_empty() {
                vec![global.affine()]
            } else {
                instances.iter().map(|t| global.affine() * t.compute_affine()).collect()
            };
            for transform in transforms {
                let path = handle.path().map(ToString::to_string).unwrap_or_default();
                let key = (tile, path, transform.to_cols_array().map(f32::to_bits), material.clone());
                match triangles(mesh, transform, &material, surface) {
                    Ok(mut triangles) => {
                        if let Some(source) = source {
                            for triangle in &mut triangles {
                                let Some(name) = source.face_materials.get(triangle.source_face) else { continue };
                                if !name.is_empty() {
                                    triangle.material = name.clone();
                                    triangle.surface = metadata
                                        .0
                                        .materials
                                        .iter()
                                        .find(|m| m.material == *name)
                                        .map_or(solid.0.skate(), |m| m.surface)
                                        as u16;
                                }
                            }
                        }
                        ordered.push((key, triangles));
                    }
                    Err(reason) => {
                        error!("incomplete world collision: {reason}");
                        valid = false;
                    }
                }
            }
        }
        if valid {
            let [min, max] = bounds.unwrap_or([
                centre.xz() - Vec2::splat(grid.tile_m * 0.5),
                centre.xz() + Vec2::splat(grid.tile_m * 0.5),
            ]);
            snapshot.coverage.push(CollisionCoverage { tile, min, max });
        } else {
            snapshot.ready = false;
        }
    }
    ordered.sort_by(|a, b| a.0.cmp(&b.0));
    snapshot.triangles = ordered.into_iter().flat_map(|(_, triangles)| triangles).collect();
    if snapshot.ready {
        for entity in &initial {
            commands.entity(entity).despawn();
        }
    }
    *previous = complete_signature;
    output.generation = output.generation.wrapping_add(1);
    output.snapshot = Arc::new(snapshot);
}

fn triangles(
    mesh: &Mesh,
    transform: bevy::math::Affine3A,
    material: &str,
    surface: u16,
) -> Result<Vec<CollisionTriangle>, &'static str> {
    if mesh.primitive_topology() != PrimitiveTopology::TriangleList {
        return Err("unsupported topology");
    }
    let points =
        mesh.try_attribute(Mesh::ATTRIBUTE_POSITION).ok().and_then(|v| v.as_float3()).ok_or("missing positions")?;
    let indices = mesh.try_indices_option().map_err(|_| "inaccessible indices")?;
    let count = match indices {
        Some(Indices::U16(i)) => i.len(),
        Some(Indices::U32(i)) => i.len(),
        None => points.len(),
    };
    if count % 3 != 0 {
        return Err("invalid index count");
    }
    let mirrored = transform.matrix3.determinant() < 0.;
    let mut out = Vec::with_capacity(count / 3);
    for first in (0..count).step_by(3) {
        let mut p = [Vec3::ZERO; 3];
        for i in 0..3 {
            let index = match indices {
                Some(Indices::U16(v)) => usize::from(v[first + i]),
                Some(Indices::U32(v)) => v[first + i] as usize,
                None => first + i,
            };
            p[i] = transform.transform_point3(Vec3::from_array(*points.get(index).ok_or("index outside positions")?));
            if !p[i].is_finite() {
                return Err("non-finite vertex");
            }
        }
        if mirrored {
            p.swap(1, 2)
        }
        if (p[1] - p[0]).cross(p[2] - p[0]).length_squared() == 0. {
            continue;
        }
        out.push(CollisionTriangle { points: p, material: material.into(), surface, source_face: first / 3 });
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn snapshot_keeps_owned_winding_and_material_when_mesh_is_dropped() {
        let mut mesh = Mesh::new(PrimitiveTopology::TriangleList, bevy::asset::RenderAssetUsages::MAIN_WORLD);
        mesh.insert_attribute(Mesh::ATTRIBUTE_POSITION, vec![[0., 0., 0.], [0., 0., 1.], [1., 0., 0.]]);
        let transform = Transform::from_xyz(3., 2., 1.).with_scale(Vec3::new(-1., 1., 1.)).compute_affine();
        let out = triangles(&mesh, transform, "planks", 2).unwrap();
        drop(mesh);
        assert_eq!(out[0].material, "planks");
        assert_eq!(out[0].surface, 2);
        let [a, b, c] = out[0].points;
        assert!((b - a).cross(c - a).y > 0.);
    }
    #[test]
    fn incomplete_coverage_cannot_become_a_ready_snapshot() {
        use bevy::ecs::system::RunSystemOnce;
        let mut app = App::new();
        app.add_plugins(MinimalPlugins)
            .init_resource::<Assets<Mesh>>()
            .init_resource::<WorldCollision>()
            .init_resource::<CollisionFocus>()
            .insert_resource(TileGrid { tile_m: 64. })
            .insert_resource(SkateMetadata(Metadata::default()));
        app.world_mut().resource_mut::<CollisionFocus>().request(Vec3::ZERO, Vec3::ZERO);
        app.world_mut().spawn(Tile::named("tile 1 1", Vec3::ZERO).unwrap());
        app.world_mut().run_system_once(publish).unwrap();
        assert!(!app.world().resource::<WorldCollision>().snapshot.ready);
        assert!(app.world().resource::<WorldCollision>().snapshot.coverage.is_empty());
        let retained = app.world().resource::<WorldCollision>().snapshot.clone();
        app.world_mut().run_system_once(publish).unwrap();
        assert!(!retained.ready);
        assert!(!app.world().resource::<WorldCollision>().snapshot.covers(Vec3::ZERO));
    }
    #[test]
    fn destination_pins_both_ends_without_loading_the_whole_gap() {
        let mut focus = CollisionFocus::default();
        focus.request(Vec3::ZERO, Vec3::X * 20.);
        focus.destination = Some(Vec3::X * 2000.);
        assert!(focus.intersects(Vec3::ZERO, 64.));
        assert!(focus.intersects(Vec3::X * 2100., 64.));
        assert!(!focus.intersects(Vec3::X * 1000., 64.));
        focus.request(Vec3::X * 10., Vec3::ZERO);
        assert!(focus.destination.is_some(), "ordinary corridor updates retain the pending destination");
        focus.destination = None;
        assert!(!focus.intersects(Vec3::X * 2100., 64.));
        focus.destination = Some(Vec3::X * 2000.);
        focus.clear();
        assert!(focus.destination.is_none());
        assert!(!focus.intersects(Vec3::ZERO, 64.));
    }

    #[test]
    fn predictive_focus_pins_a_fast_landing_beyond_the_camera() {
        let mut focus = CollisionFocus::default();
        focus.request(Vec3::ZERO, Vec3::X * 50.);
        assert!(focus.intersects(Vec3::X * 190., 64.));
        assert!(!focus.intersects(Vec3::X * 250., 64.));
        focus.clear();
        assert!(!focus.intersects(Vec3::ZERO, 64.));
    }
}
