//! Vertex-painted opaque models: source colour, bounded paper glow and asset-owned aerial perspective.

use crate::scenery::{Placing, validate_static_paint};
use crate::tiles::TILES;
use bevy::asset::{LoadState, embedded_asset};
use bevy::ecs::system::SystemParam;
use bevy::gltf::GltfExtras;
use bevy::pbr::{ExtendedMaterial, MaterialExtension};
use bevy::platform::collections::HashMap;
use bevy::prelude::*;
use bevy::render::render_resource::{AsBindGroup, ShaderType};
use bevy::shader::ShaderRef;
use bevy::world_serialization::WorldAssetRoot;
use serde::Deserialize;

/// @cc [owner:fontanierh,label:correctness] vertex-paint-preserves-static-colour
/// A painted model MUST use its linear vertex RGB and asset-owned profile. Alpha is a motion weight, never opacity;
/// nonzero weights without valid declared motion and unsupported animated meshes MUST be reported instead of silently
/// made static. Declared motion MUST agree across visible and prepass vertices. Its profile MUST apply its haze once,
/// while models without a profile keep their existing material path.
#[derive(Clone, Debug, Deserialize, PartialEq)]
pub struct Profile {
    pub fill: f32,
    pub glow: f32,
    pub glow_min: [f32; 3],
    pub glow_max: [f32; 3],
    pub haze_start_m: f32,
    pub haze_length_m: f32,
    pub haze_colour: [f32; 3],
}

impl Profile {
    pub fn valid(&self) -> bool {
        self.fill.is_finite()
            && self.fill >= 0.0
            && self.glow.is_finite()
            && self.glow >= 0.0
            && self.haze_start_m.is_finite()
            && self.haze_start_m >= 0.0
            && self.haze_length_m.is_finite()
            && self.haze_length_m > 0.0
            && self.haze_colour.iter().all(|v| v.is_finite() && *v >= 0.0)
            && self.glow_min.iter().zip(self.glow_max).all(|(a, b)| a.is_finite() && b.is_finite() && *a <= b)
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq)]
pub struct SurfaceProfile {
    pub haze_start_m: f32,
    pub haze_length_m: f32,
    pub haze_colour: [f32; 3],
}

impl SurfaceProfile {
    pub(crate) fn profile(&self) -> Profile {
        Profile {
            fill: 0.0,
            glow: 0.0,
            glow_min: [0.0; 3],
            glow_max: [0.0; 3],
            haze_start_m: self.haze_start_m,
            haze_length_m: self.haze_length_m,
            haze_colour: self.haze_colour,
        }
    }
}

#[derive(Clone, Default, ShaderType)]
struct PaintUniform {
    lower: Vec4,
    upper: Vec4,
    haze: Vec4,
    colour: Vec4,
}

#[derive(Asset, AsBindGroup, Reflect, Clone)]
pub struct Paint {
    #[uniform(100)]
    #[reflect(ignore)]
    data: PaintUniform,
}

impl MaterialExtension for Paint {
    fn vertex_shader() -> ShaderRef {
        "embedded://hakuba_world/vertex_paint.wesl".into()
    }
    fn fragment_shader() -> ShaderRef {
        "embedded://hakuba_world/vertex_paint.wesl".into()
    }
}

pub type Painted = ExtendedMaterial<StandardMaterial, Paint>;

/// Source-authored motion of a painted vertex, in world metres.
#[derive(Clone, Debug, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct MotionProfile {
    pub spatial: [f32; 2],
    pub rate: f32,
    pub amplitude: [f32; 3],
    pub harmonic: [f32; 3],
}

impl MotionProfile {
    pub fn valid(&self) -> bool {
        self.rate.is_finite()
            && self.rate.abs() <= 10_000.0
            && self
                .spatial
                .iter()
                .chain(&self.amplitude)
                .chain(&self.harmonic)
                .all(|x| x.is_finite() && x.abs() <= 10_000.0)
    }
}

#[derive(Clone, Default, ShaderType)]
struct MovingUniform {
    lower: Vec4,
    upper: Vec4,
    haze: Vec4,
    colour: Vec4,
    phase: Vec4,
    amplitude: Vec4,
    harmonic: Vec4,
}

#[derive(Asset, AsBindGroup, Reflect, Clone)]
pub struct MovingPaint {
    #[uniform(100)]
    #[reflect(ignore)]
    data: MovingUniform,
}

impl MaterialExtension for MovingPaint {
    fn vertex_shader() -> ShaderRef {
        "embedded://hakuba_world/paint_motion.wesl".into()
    }
    fn prepass_vertex_shader() -> ShaderRef {
        "embedded://hakuba_world/paint_motion.wesl".into()
    }
    fn fragment_shader() -> ShaderRef {
        "embedded://hakuba_world/vertex_paint.wesl".into()
    }
}

pub type MovingPainted = ExtendedMaterial<StandardMaterial, MovingPaint>;

pub struct VertexPaintPlugin;
impl Plugin for VertexPaintPlugin {
    fn build(&self, app: &mut App) {
        embedded_asset!(app, "vertex_paint.wesl");
        embedded_asset!(app, "paint_motion.wesl");
        app.add_plugins((MaterialPlugin::<Painted>::default(), MaterialPlugin::<MovingPainted>::default()))
            .init_resource::<Made>()
            .init_resource::<MovingMade>()
            .add_systems(Update, (read_surfaces, prepare_surfaces).chain().before(Placing));
    }
}

type MadeEntries = Vec<(Profile, u8, Handle<Painted>)>;

#[derive(Resource, Default)]
struct Made(HashMap<AssetId<StandardMaterial>, MadeEntries>);

type MovingEntries = Vec<(Profile, MotionProfile, Handle<MovingPainted>)>;

#[derive(Resource, Default)]
struct MovingMade(HashMap<AssetId<StandardMaterial>, MovingEntries>);

#[derive(SystemParam)]
pub struct MovingPaintedMaterials<'w> {
    made: ResMut<'w, MovingMade>,
    moving: ResMut<'w, Assets<MovingPainted>>,
}

impl MovingPaintedMaterials<'_> {
    pub fn of(
        &mut self,
        painted: &mut PaintedMaterials,
        material: &Handle<StandardMaterial>,
        profile: &Profile,
        motion: &MotionProfile,
    ) -> Result<Option<Handle<MovingPainted>>, String> {
        if let Some((_, _, handle)) =
            self.made.0.get(&material.id()).and_then(|items| items.iter().find(|(p, m, _)| p == profile && m == motion))
        {
            return Ok(Some(handle.clone()));
        }
        let Some(handle) = painted.of(material, profile)? else { return Ok(None) };
        let source = painted.painted.get(&handle).expect("new painted material is present");
        let data = &source.extension.data;
        let uniform = MovingUniform {
            lower: data.lower,
            upper: data.upper,
            haze: data.haze,
            colour: data.colour,
            phase: Vec4::new(motion.spatial[0], motion.spatial[1], motion.rate, 0.0),
            amplitude: Vec3::from_array(motion.amplitude).extend(0.0),
            harmonic: Vec3::from_array(motion.harmonic).extend(0.0),
        };
        let handle =
            self.moving.add(MovingPainted { base: source.base.clone(), extension: MovingPaint { data: uniform } });
        self.made.0.entry(material.id()).or_default().push((profile.clone(), motion.clone(), handle.clone()));
        Ok(Some(handle))
    }
}

#[derive(SystemParam)]
pub struct PaintedMaterials<'w> {
    made: ResMut<'w, Made>,
    standard: Res<'w, Assets<StandardMaterial>>,
    painted: ResMut<'w, Assets<Painted>>,
}

impl PaintedMaterials<'_> {
    pub fn of(
        &mut self,
        material: &Handle<StandardMaterial>,
        profile: &Profile,
    ) -> Result<Option<Handle<Painted>>, String> {
        self.make(material, profile, 0)
    }

    pub(crate) fn of_surface(
        &mut self,
        material: &Handle<StandardMaterial>,
        profile: &Profile,
    ) -> Result<Option<Handle<Painted>>, String> {
        self.make(material, profile, 2)
    }

    fn make(
        &mut self,
        material: &Handle<StandardMaterial>,
        profile: &Profile,
        mode: u8,
    ) -> Result<Option<Handle<Painted>>, String> {
        if let Some((_, _, handle)) =
            self.made.0.get(&material.id()).and_then(|items| items.iter().find(|(p, t, _)| p == profile && *t == mode))
        {
            return Ok(Some(handle.clone()));
        }
        let Some(mut base) = self.standard.get(material).cloned() else { return Ok(None) };
        if base.alpha_mode != AlphaMode::Opaque {
            return Err("vertex paint requires an opaque source material".into());
        }
        if (mode == 0 && (base.base_color.to_linear() != LinearRgba::WHITE || base.base_color_texture.is_some()))
            || (mode == 1 && base.base_color_texture.is_none())
            || (mode == 3 && base.base_color_texture.is_some())
            || base.emissive_texture.is_some()
            || base.metallic_roughness_texture.is_some()
            || base.normal_map_texture.is_some()
            || base.occlusion_texture.is_some()
            || base.unlit
        {
            return Err("vertex paint requires a compatible lit source material".into());
        }
        base.alpha_mode = AlphaMode::Opaque;
        base.metallic = 0.0;
        base.fog_enabled = false;
        base.perceptual_roughness = 1.0;
        base.reflectance = 0.0;
        let data = PaintUniform {
            lower: Vec3::from_array(profile.glow_min).extend(profile.fill),
            upper: Vec3::from_array(profile.glow_max).extend(profile.glow),
            haze: Vec4::new(profile.haze_start_m, profile.haze_length_m, 0.0, 0.0),
            colour: Vec3::from_array(profile.haze_colour).extend(0.0),
        };
        let handle = self.painted.add(Painted { base, extension: Paint { data } });
        self.made.0.entry(material.id()).or_default().push((profile.clone(), mode, handle.clone()));
        Ok(Some(handle))
    }
}

/// @cc [owner:fontanierh,label:correctness] painted-surface-before-tile-activation
/// A profiled tile surface MUST retain its source texture and UVs or its static vertex colours, apply its asset-owned
/// haze once, and finish preparation before its tile is activated. Invalid profiles or unsupported geometry MUST fail
/// the pending tile, preserving any previous visible version; unprofiled surfaces MUST keep their original material.
///
/// A tile surface waits for its source material and mesh before receiving the shared paint response.
#[derive(Component)]
pub(crate) struct SurfaceWaiting(Profile, u8);

#[derive(Component)]
pub(crate) struct SurfaceFailed;

pub(crate) fn read_surfaces(
    mut commands: Commands,
    added: Query<(Entity, &GltfExtras), Added<GltfExtras>>,
    parents: Query<&ChildOf>,
    roots: Query<&WorldAssetRoot>,
) {
    for (entity, extras) in &added {
        if !parents
            .iter_ancestors(entity)
            .any(|e| roots.get(e).ok().and_then(|r| r.0.path()).is_some_and(|p| p.path().starts_with(TILES)))
        {
            continue;
        }
        let Ok(value) = serde_json::from_str::<serde_json::Value>(&extras.value) else { continue };
        if let Some(raw) = value.get("vertex_paint") {
            if value.get("surface_paint").is_some()
                || value.get("surface_untextured").is_some()
                || value.get("vertex_motion").is_some()
            {
                error!("conflicting paint profiles on tile node {entity}");
                commands.entity(entity).insert(SurfaceFailed);
                continue;
            }
            match serde_json::from_value::<Profile>(raw.clone()) {
                Ok(profile) if profile.valid() => {
                    commands.entity(entity).insert(SurfaceWaiting(profile, 0));
                }
                _ => {
                    error!("invalid vertex paint profile on tile node {entity}");
                    commands.entity(entity).insert(SurfaceFailed);
                }
            }
            continue;
        }
        let Some(raw) = value.get("surface_paint") else { continue };
        let untextured = match value.get("surface_untextured") {
            None => false,
            Some(serde_json::Value::Bool(value)) => *value,
            _ => {
                error!("invalid untextured surface flag on tile node {entity}");
                commands.entity(entity).insert(SurfaceFailed);
                continue;
            }
        };
        match serde_json::from_value::<SurfaceProfile>(raw.clone()) {
            Ok(profile) if profile.profile().valid() => {
                commands.entity(entity).insert(SurfaceWaiting(profile.profile(), if untextured { 3 } else { 1 }));
            }
            _ => {
                error!("invalid surface paint profile on tile node {entity}");
                commands.entity(entity).insert(SurfaceFailed);
            }
        }
    }
}

pub(crate) fn prepare_surfaces(
    mut commands: Commands,
    waiting: Query<(Entity, &SurfaceWaiting)>,
    children: Query<&Children>,
    parts: Query<(&Mesh3d, &MeshMaterial3d<StandardMaterial>)>,
    meshes: Res<Assets<Mesh>>,
    assets: Res<AssetServer>,
    mut painted: PaintedMaterials,
) {
    for (node, profile) in &waiting {
        if !profile.0.valid() {
            continue;
        }
        let mut replacements = Vec::new();
        let mut pending = false;
        let mut failed = false;
        for entity in std::iter::once(node).chain(children.iter_descendants(node)) {
            let Ok((mesh, material)) = parts.get(entity) else { continue };
            let Some(mesh) = meshes.get(&mesh.0) else {
                if matches!(assets.load_state(&mesh.0), LoadState::Failed(_)) {
                    failed = true;
                } else {
                    pending = true;
                }
                break;
            };
            if profile.1 == 0 {
                if let Err(error) = validate_static_paint(mesh) {
                    error!("vertex paint: {error}");
                    failed = true;
                    break;
                }
            } else if !mesh.contains_attribute(Mesh::ATTRIBUTE_POSITION)
                || !mesh.contains_attribute(Mesh::ATTRIBUTE_NORMAL)
                || !mesh.contains_attribute(Mesh::ATTRIBUTE_UV_0)
                || mesh.contains_attribute(Mesh::ATTRIBUTE_COLOR)
                || mesh.contains_attribute(Mesh::ATTRIBUTE_UV_1)
                || mesh.contains_attribute(Mesh::ATTRIBUTE_JOINT_INDEX)
                || mesh.has_morph_targets()
            {
                error!("surface paint requires static position, normal and UV0 without vertex colors");
                failed = true;
                break;
            }
            match painted.make(&material.0, &profile.0, profile.1) {
                Ok(Some(handle)) => replacements.push((entity, handle)),
                Ok(None) => {
                    if matches!(assets.load_state(&material.0), LoadState::Failed(_)) {
                        failed = true;
                    } else {
                        pending = true;
                    }
                    break;
                }
                Err(error) => {
                    error!("surface paint: {error}");
                    failed = true;
                    break;
                }
            }
        }
        if failed || (!pending && replacements.is_empty()) {
            error!("surface paint could not prepare tile node {node}");
            commands.entity(node).remove::<SurfaceWaiting>().insert(SurfaceFailed);
        } else if !pending {
            for (entity, handle) in replacements {
                commands.entity(entity).remove::<MeshMaterial3d<StandardMaterial>>().insert(MeshMaterial3d(handle));
            }
            commands.entity(node).remove::<SurfaceWaiting>();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use bevy::ecs::system::RunSystemOnce;

    #[test]
    fn vertex_painted_tile_prepares_static_colours_and_rejects_motion_weights() {
        use bevy::asset::RenderAssetUsages;
        use bevy::mesh::PrimitiveTopology;
        let mut app = App::new();
        app.add_plugins((MinimalPlugins, bevy::asset::AssetPlugin::default()))
            .init_asset::<Mesh>()
            .init_resource::<Assets<StandardMaterial>>()
            .init_resource::<Assets<Painted>>()
            .init_resource::<Made>();
        let material = app.world_mut().resource_mut::<Assets<StandardMaterial>>().add(StandardMaterial::default());
        let profile = Profile {
            fill: 0.06,
            glow: 0.8,
            glow_min: [0.8, 0.35, 0.0],
            glow_max: [1.0, 0.72, 0.3],
            haze_start_m: 30.0,
            haze_length_m: 9000.0,
            haze_colour: [0.0932, 0.2301, 0.5328],
        };
        let mut nodes = Vec::new();
        for weight in [0.0, 1.0] {
            let mesh = Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::default())
                .with_inserted_attribute(Mesh::ATTRIBUTE_POSITION, vec![[0., 0., 0.]; 3])
                .with_inserted_attribute(Mesh::ATTRIBUTE_NORMAL, vec![[0., 1., 0.]; 3])
                .with_inserted_attribute(Mesh::ATTRIBUTE_COLOR, vec![[0.2, 0.3, 0.4, weight]; 3]);
            let mesh = app.world_mut().resource_mut::<Assets<Mesh>>().add(mesh);
            nodes.push(
                app.world_mut()
                    .spawn((Mesh3d(mesh), MeshMaterial3d(material.clone()), SurfaceWaiting(profile.clone(), 0)))
                    .id(),
            );
        }
        app.world_mut().run_system_once(prepare_surfaces).unwrap();
        assert!(app.world().get::<MeshMaterial3d<Painted>>(nodes[0]).is_some());
        assert!(app.world().get::<SurfaceFailed>(nodes[1]).is_some());
    }

    #[test]
    fn moving_paint_uses_the_same_material_response_and_declared_motion() {
        use bevy::ecs::system::SystemState;
        let mut world = World::new();
        world.insert_resource(Assets::<StandardMaterial>::default());
        world.insert_resource(Assets::<Painted>::default());
        world.insert_resource(Assets::<MovingPainted>::default());
        world.insert_resource(Made::default());
        world.insert_resource(MovingMade::default());
        let source = world.resource_mut::<Assets<StandardMaterial>>().add(StandardMaterial::default());
        let profile = Profile {
            fill: 0.06,
            glow: 0.8,
            glow_min: [0.8, 0.35, 0.0],
            glow_max: [1.0, 0.72, 0.3],
            haze_start_m: 30.0,
            haze_length_m: 9000.0,
            haze_colour: [0.0932, 0.2301, 0.5328],
        };
        let motion = MotionProfile {
            spatial: [0.2, 0.3],
            rate: 1.7,
            amplitude: [0.022, 0.004, 0.013],
            harmonic: [1.0, 1.3, 0.81],
        };
        assert!(motion.valid());
        let mut state = SystemState::<(PaintedMaterials, MovingPaintedMaterials)>::new(&mut world);
        let (first, again) = {
            let (mut painted, mut moving) = state.get_mut(&mut world).unwrap();
            (
                moving.of(&mut painted, &source, &profile, &motion).unwrap().unwrap(),
                moving.of(&mut painted, &source, &profile, &motion).unwrap().unwrap(),
            )
        };
        assert_eq!(first, again);
        let material = world.resource::<Assets<MovingPainted>>().get(&first).unwrap();
        assert!(!material.base.fog_enabled);
        assert_eq!(material.base.reflectance, 0.0);
        assert_eq!(material.extension.data.phase, Vec4::new(0.2, 0.3, 1.7, 0.0));
        assert_eq!(material.extension.data.amplitude, Vec4::new(0.022, 0.004, 0.013, 0.0));
        assert!(!MotionProfile { rate: f32::NAN, ..motion }.valid());
    }

    #[test]
    fn source_surface_preserves_textured_and_tinted_parts() {
        let mut app = App::new();
        app.add_plugins(MinimalPlugins)
            .init_resource::<Assets<StandardMaterial>>()
            .init_resource::<Assets<Painted>>()
            .init_resource::<Made>();
        let mut assets = app.world_mut().resource_mut::<Assets<StandardMaterial>>();
        let texture = Handle::<Image>::default();
        let concrete = assets.add(StandardMaterial { base_color_texture: Some(texture.clone()), ..default() });
        let tint = Color::linear_rgb(0.18, 0.11, 0.07);
        let wood = assets.add(StandardMaterial { base_color: tint, ..default() });
        let c = concrete.clone();
        let w = wood.clone();
        let result = app
            .world_mut()
            .run_system_once(move |mut painted: PaintedMaterials| {
                let profile =
                    SurfaceProfile { haze_start_m: 30.0, haze_length_m: 9000.0, haze_colour: [0.1, 0.2, 0.3] }
                        .profile();
                assert!(painted.of(&w, &profile).is_err());
                (painted.of_surface(&c, &profile).unwrap().unwrap(), painted.of_surface(&w, &profile).unwrap().unwrap())
            })
            .unwrap();
        let assets = app.world().resource::<Assets<Painted>>();
        let concrete = assets.get(&result.0).unwrap();
        let wood = assets.get(&result.1).unwrap();
        assert_eq!(concrete.base.base_color_texture, Some(texture));
        assert_eq!(wood.base.base_color, tint);
        assert_eq!(wood.base.reflectance, 0.0);
        assert!(!wood.base.fog_enabled);
    }

    #[test]
    fn textured_tile_surface_replaces_only_its_own_material() {
        use bevy::asset::RenderAssetUsages;
        use bevy::mesh::PrimitiveTopology;
        let mut app = App::new();
        app.add_plugins((MinimalPlugins, bevy::asset::AssetPlugin::default()));
        app.init_resource::<Assets<Mesh>>()
            .init_resource::<Assets<StandardMaterial>>()
            .init_resource::<Assets<Painted>>()
            .init_resource::<Made>()
            .add_systems(Update, prepare_surfaces);
        let mesh = Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::default())
            .with_inserted_attribute(Mesh::ATTRIBUTE_POSITION, vec![[0., 0., 0.]; 3])
            .with_inserted_attribute(Mesh::ATTRIBUTE_NORMAL, vec![[0., 1., 0.]; 3])
            .with_inserted_attribute(Mesh::ATTRIBUTE_UV_0, vec![[0., 0.]; 3]);
        let mesh = app.world_mut().resource_mut::<Assets<Mesh>>().add(mesh);
        let source = app
            .world_mut()
            .resource_mut::<Assets<StandardMaterial>>()
            .add(StandardMaterial { base_color_texture: Some(Handle::<Image>::default()), ..default() });
        let original = app.world_mut().spawn((Mesh3d(mesh.clone()), MeshMaterial3d(source.clone()))).id();
        let surface = app
            .world_mut()
            .spawn((
                Mesh3d(mesh),
                MeshMaterial3d(source.clone()),
                SurfaceWaiting(
                    SurfaceProfile { haze_start_m: 30., haze_length_m: 9000., haze_colour: [0.1, 0.2, 0.3] }.profile(),
                    1,
                ),
            ))
            .id();
        app.update();
        let world = app.world();
        assert!(world.get::<SurfaceWaiting>(surface).is_none());
        assert!(world.get::<MeshMaterial3d<StandardMaterial>>(surface).is_none());
        let handle = &world.get::<MeshMaterial3d<Painted>>(surface).unwrap().0;
        let painted = world.resource::<Assets<Painted>>().get(handle).unwrap();
        assert_eq!(painted.base.base_color_texture, Some(Handle::<Image>::default()));
        assert_eq!(painted.extension.data.lower.w, 0.0);
        assert_eq!(painted.extension.data.upper.w, 0.0);
        assert_eq!(painted.base.reflectance, 0.0);
        assert!(!painted.base.fog_enabled);
        assert_eq!(world.get::<MeshMaterial3d<StandardMaterial>>(original).unwrap().0, source);
    }

    #[test]
    fn untextured_tile_surface_keeps_its_tint_and_receives_haze() {
        use bevy::asset::RenderAssetUsages;
        use bevy::mesh::PrimitiveTopology;
        let mut app = App::new();
        app.add_plugins((MinimalPlugins, bevy::asset::AssetPlugin::default()));
        app.init_resource::<Assets<Mesh>>()
            .init_resource::<Assets<StandardMaterial>>()
            .init_resource::<Assets<Painted>>()
            .init_resource::<Made>()
            .add_systems(Update, prepare_surfaces);
        let mesh = Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::default())
            .with_inserted_attribute(Mesh::ATTRIBUTE_POSITION, vec![[0., 0., 0.]; 3])
            .with_inserted_attribute(Mesh::ATTRIBUTE_NORMAL, vec![[0., 1., 0.]; 3])
            .with_inserted_attribute(Mesh::ATTRIBUTE_UV_0, vec![[0., 0.]; 3]);
        let mesh = app.world_mut().resource_mut::<Assets<Mesh>>().add(mesh);
        let source = app
            .world_mut()
            .resource_mut::<Assets<StandardMaterial>>()
            .add(StandardMaterial { base_color: Color::linear_rgb(0.85, 0.85, 0.82), ..default() });
        let original = app.world_mut().spawn((Mesh3d(mesh.clone()), MeshMaterial3d(source.clone()))).id();
        let surface = app
            .world_mut()
            .spawn((
                Mesh3d(mesh),
                MeshMaterial3d(source.clone()),
                SurfaceWaiting(
                    SurfaceProfile { haze_start_m: 30., haze_length_m: 9000., haze_colour: [0.1, 0.2, 0.3] }.profile(),
                    3,
                ),
            ))
            .id();
        app.update();
        let world = app.world();
        assert!(world.get::<SurfaceWaiting>(surface).is_none());
        assert!(world.get::<MeshMaterial3d<StandardMaterial>>(surface).is_none());
        let handle = &world.get::<MeshMaterial3d<Painted>>(surface).unwrap().0;
        let painted = world.resource::<Assets<Painted>>().get(handle).unwrap();
        assert_eq!(painted.base.base_color_texture, None);
        assert_eq!(painted.base.base_color, Color::linear_rgb(0.85, 0.85, 0.82));
        assert_eq!(painted.extension.data.lower.w, 0.0);
        assert_eq!(painted.extension.data.upper.w, 0.0);
        assert_eq!(painted.base.reflectance, 0.0);
        assert!(!painted.base.fog_enabled);
        assert_eq!(world.get::<MeshMaterial3d<StandardMaterial>>(original).unwrap().0, source);
    }

    #[test]
    fn surface_with_wind_weights_is_rejected() {
        use bevy::asset::RenderAssetUsages;
        use bevy::mesh::PrimitiveTopology;
        let mut app = App::new();
        app.add_plugins((MinimalPlugins, bevy::asset::AssetPlugin::default()));
        app.init_resource::<Assets<Mesh>>()
            .init_resource::<Assets<StandardMaterial>>()
            .init_resource::<Assets<Painted>>()
            .init_resource::<Made>();
        let mesh = Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::default())
            .with_inserted_attribute(Mesh::ATTRIBUTE_POSITION, vec![[0., 0., 0.]; 3])
            .with_inserted_attribute(Mesh::ATTRIBUTE_NORMAL, vec![[0., 1., 0.]; 3])
            .with_inserted_attribute(Mesh::ATTRIBUTE_UV_0, vec![[0., 0.]; 3])
            .with_inserted_attribute(Mesh::ATTRIBUTE_UV_1, vec![[0.5, 0.0]; 3]);
        let mesh = app.world_mut().resource_mut::<Assets<Mesh>>().add(mesh);
        let material = app.world_mut().resource_mut::<Assets<StandardMaterial>>().add(StandardMaterial::default());
        let node = app
            .world_mut()
            .spawn((
                Mesh3d(mesh),
                MeshMaterial3d(material),
                SurfaceWaiting(
                    SurfaceProfile { haze_start_m: 30., haze_length_m: 9000., haze_colour: [0.1, 0.2, 0.3] }.profile(),
                    1,
                ),
            ))
            .id();
        app.world_mut().run_system_once(prepare_surfaces).unwrap();
        assert!(app.world().get::<SurfaceFailed>(node).is_some());
        assert!(app.world().get::<MeshMaterial3d<Painted>>(node).is_none());
    }

    #[test]
    fn failed_surface_mesh_reaches_terminal_failure() {
        use bevy::asset::AssetApp;
        let mut app = App::new();
        app.add_plugins((MinimalPlugins, bevy::asset::AssetPlugin::default()));
        app.init_asset::<Mesh>()
            .init_resource::<Assets<StandardMaterial>>()
            .init_resource::<Assets<Painted>>()
            .init_resource::<Made>();
        let missing: Handle<Mesh> = app.world().resource::<AssetServer>().load("missing-surface-for-test.no-loader");
        let material = app.world_mut().resource_mut::<Assets<StandardMaterial>>().add(StandardMaterial::default());
        let node = app
            .world_mut()
            .spawn((
                Mesh3d(missing.clone()),
                MeshMaterial3d(material),
                SurfaceWaiting(
                    SurfaceProfile { haze_start_m: 30., haze_length_m: 9000., haze_colour: [0.1, 0.2, 0.3] }.profile(),
                    1,
                ),
            ))
            .id();
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(3);
        while !matches!(app.world().resource::<AssetServer>().load_state(&missing), LoadState::Failed(_)) {
            assert!(std::time::Instant::now() < deadline);
            app.update();
            std::thread::sleep(std::time::Duration::from_millis(1));
        }
        app.world_mut().run_system_once(prepare_surfaces).unwrap();
        assert!(app.world().get::<SurfaceFailed>(node).is_some());
        assert!(app.world().get::<SurfaceWaiting>(node).is_none());
    }

    #[test]
    fn profile_rejects_nonfinite_or_invalid_haze_and_thresholds() {
        let mut profile = Profile {
            fill: 0.06,
            glow: 0.8,
            glow_min: [0.8, 0.35, 0.0],
            glow_max: [1.0, 0.72, 0.3],
            haze_start_m: 30.0,
            haze_length_m: 9000.0,
            haze_colour: [0.0932, 0.2301, 0.5328],
        };
        assert!(profile.valid());
        profile.haze_length_m = 0.0;
        assert!(!profile.valid());
        profile.haze_length_m = 9000.0;
        profile.glow_min[0] = f32::NAN;
        assert!(!profile.valid());
    }
    #[test]
    fn painted_material_reuses_profile_and_keeps_standard_material_unchanged() {
        use bevy::ecs::system::SystemState;
        let mut world = World::new();
        world.insert_resource(Assets::<StandardMaterial>::default());
        world.insert_resource(Assets::<Painted>::default());
        world.insert_resource(Made::default());
        let source = world.resource_mut::<Assets<StandardMaterial>>().add(StandardMaterial::default());
        let profile = Profile {
            fill: 0.06,
            glow: 0.8,
            glow_min: [0.8, 0.35, 0.0],
            glow_max: [1.0, 0.72, 0.3],
            haze_start_m: 30.0,
            haze_length_m: 9000.0,
            haze_colour: [0.0932, 0.2301, 0.5328],
        };
        let mut state = SystemState::<PaintedMaterials>::new(&mut world);
        let (first, again) = {
            let mut materials = state.get_mut(&mut world).unwrap();
            (materials.of(&source, &profile).unwrap().unwrap(), materials.of(&source, &profile).unwrap().unwrap())
        };
        assert_eq!(first, again);
        let original = world.resource::<Assets<StandardMaterial>>().get(&source).unwrap();
        assert!(original.fog_enabled);
        let painted = world.resource::<Assets<Painted>>().get(&first).unwrap();
        assert!(!painted.base.fog_enabled);
        assert_eq!(painted.base.alpha_mode, AlphaMode::Opaque);
        assert_eq!(painted.base.reflectance, 0.0);
        assert_eq!(painted.base.perceptual_roughness, 1.0);
    }
}
