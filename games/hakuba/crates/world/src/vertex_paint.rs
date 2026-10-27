//! Vertex-painted opaque models: source colour, bounded paper glow and asset-owned aerial perspective.

use bevy::asset::embedded_asset;
use bevy::ecs::system::SystemParam;
use bevy::pbr::{ExtendedMaterial, MaterialExtension};
use bevy::platform::collections::HashMap;
use bevy::prelude::*;
use bevy::render::render_resource::{AsBindGroup, ShaderType};
use bevy::shader::ShaderRef;
use serde::Deserialize;

/// @cc [owner:fontanierh,label:correctness] vertex-paint-preserves-static-colour
/// A painted model MUST use its linear vertex RGB and asset-owned profile. Zero alpha is a static motion weight,
/// never opacity; nonzero weights and unsupported animated meshes MUST be reported instead of silently made static.
/// Its profile MUST apply its haze once, while models without a profile keep their existing material path.
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

pub struct VertexPaintPlugin;
impl Plugin for VertexPaintPlugin {
    fn build(&self, app: &mut App) {
        embedded_asset!(app, "vertex_paint.wesl");
        app.add_plugins(MaterialPlugin::<Painted>::default()).init_resource::<Made>();
    }
}

#[derive(Resource, Default)]
struct Made(HashMap<AssetId<StandardMaterial>, Vec<(Profile, Handle<Painted>)>>);

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
        if let Some((_, handle)) =
            self.made.0.get(&material.id()).and_then(|items| items.iter().find(|(p, _)| p == profile))
        {
            return Ok(Some(handle.clone()));
        }
        let Some(mut base) = self.standard.get(material).cloned() else { return Ok(None) };
        if base.alpha_mode != AlphaMode::Opaque {
            return Err("vertex paint requires an opaque source material".into());
        }
        if base.base_color.to_linear() != LinearRgba::WHITE
            || base.base_color_texture.is_some()
            || base.emissive_texture.is_some()
            || base.metallic_roughness_texture.is_some()
            || base.normal_map_texture.is_some()
            || base.occlusion_texture.is_some()
            || base.unlit
        {
            return Err("vertex paint requires an untextured lit white source material".into());
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
        self.made.0.entry(material.id()).or_default().push((profile.clone(), handle.clone()));
        Ok(Some(handle))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

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
