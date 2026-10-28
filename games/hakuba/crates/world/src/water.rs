//! Bounded, source-authored water in map coordinates.

use bevy::prelude::*;
use serde::Deserialize;

#[derive(Resource, Default, Deserialize)]
pub struct WaterBodies {
    waters: Vec<WaterBody>,
}

#[derive(Deserialize)]
struct WaterBody {
    center_m: [f32; 2],
    radii_m: [f32; 2],
    water_height_m: f32,
    shore_harmonics: Vec<(f32, f32, String)>,
    recovery_depth_m: f32,
    safe_shore_m: [f32; 3],
    #[serde(default)]
    water_models: Vec<WaterModel>,
    material: Option<Profile>,
}

impl WaterBodies {
    /// The source safe shore when feet are below the recovery depth inside a body's shoreline.
    pub fn recovery(&self, feet: Vec3) -> Option<Vec3> {
        self.waters.iter().find_map(|water| {
            let x = (feet.x - water.center_m[0]) / water.radii_m[0];
            // The map's north is the negative game z axis.
            let y = (-feet.z - water.center_m[1]) / water.radii_m[1];
            let angle = y.atan2(x);
            let shore = 1.0
                + water
                    .shore_harmonics
                    .iter()
                    .map(|(frequency, amplitude, kind)| {
                        let phase = frequency * angle;
                        amplitude * if kind == "sin" { phase.sin() } else { phase.cos() }
                    })
                    .sum::<f32>();
            if x * x + y * y < shore * shore && feet.y < water.water_height_m - water.recovery_depth_m {
                let [x, y, z] = water.safe_shore_m;
                Some(Vec3::new(x, z, -y))
            } else {
                None
            }
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lake_recovers_only_below_depth_and_inside_authored_shore() {
        let waters: WaterBodies = serde_json::from_str(r#"{"waters":[{"center_m":[-90,235],"radii_m":[34,23],"water_height_m":75,"shore_harmonics":[[3,0.045,"sin"],[5,0.035,"cos"]],"recovery_depth_m":0.45,"safe_shore_m":[-54,223,75.65]}]}"#).unwrap();
        let safe = Some(Vec3::new(-54.0, 75.65, -223.0));
        assert_eq!(waters.recovery(Vec3::new(-90.0, 74.54, -235.0)), safe);
        assert_eq!(waters.recovery(Vec3::new(-90.0, 75.0 - 0.45, -235.0)), None);
        assert_eq!(waters.recovery(Vec3::new(-90.0, 74.56, -235.0)), None);
        assert_eq!(waters.recovery(Vec3::new(-54.0, 74.0, -235.0)), None);
        // At angle zero the source cosine extends the shore by 3.5%.
        assert_eq!(waters.recovery(Vec3::new(-55.5, 74.0, -235.0)), safe);
        assert_eq!(WaterBodies::default().recovery(Vec3::new(0.0, -2.0, 0.0)), None);
    }
}

// The world owns one profile per body; its tile chunks share one material.
use bevy::asset::embedded_asset;
use bevy::ecs::system::SystemParam;
use bevy::pbr::{ExtendedMaterial, MaterialExtension};
use bevy::render::render_resource::{AsBindGroup, ShaderType};
use bevy::shader::ShaderRef;

#[derive(Clone, Deserialize, PartialEq)]
struct WaterModel {
    model: String,
}

#[derive(Clone, Deserialize, PartialEq)]
struct Profile {
    waves: u32,
    direction_start_radians: f32,
    direction_step_radians: f32,
    wavenumber_start: f32,
    wavenumber_ratio: f32,
    amplitude_start: f32,
    amplitude_ratio: f32,
    footprint_fade: f32,
    warp_frequency: f32,
    warp_speed: f32,
    warp_amplitude: f32,
    phase_step: f32,
    gravity_factor: f32,
    shore_calm_start: f32,
    shore_calm_end: f32,
    shore_calm_reduction: f32,
    deep_colour_min: [f32; 3],
    deep_colour_max: [f32; 3],
    shallows_colour: [f32; 3],
    glint_colour: [f32; 3],
    metallic: f32,
    specular: f32,
    roughness_range: [f32; 2],
    drift_x: [f32; 3],
    drift_y: [f32; 3],
    crest_direction: [f32; 2],
    crest_scale: f32,
    crest_strength: f32,
    glint_range: [f32; 2],
    drift_strength: f32,
    drift_colour: [f32; 3],
    fetch: [f32; 3],
    chop_scale: f32,
    fetch_mix: f32,
    chop_mix: f32,
}

#[derive(Clone, Default, ShaderType)]
struct WaterUniform {
    bounds: Vec4,
    shore: Vec4,
    waves: Vec4,
    spectrum: Vec4,
    warp: Vec4,
    calm: Vec4,
    deep: Vec4,
    deep2: Vec4,
    shallows: Vec4,
    glint: Vec4,
    drift_x: Vec4,
    drift_y: Vec4,
    crest: Vec4,
    glint_range: Vec4,
    drift_colour: Vec4,
    fetch: Vec4,
    roughness: Vec4,
}

#[derive(Asset, AsBindGroup, Reflect, Clone)]
pub struct Water {
    #[uniform(100)]
    #[reflect(ignore)]
    data: WaterUniform,
}
impl MaterialExtension for Water {
    fn fragment_shader() -> ShaderRef {
        "embedded://hakuba_world/water.wesl".into()
    }
}
pub type WaterMaterial = ExtendedMaterial<StandardMaterial, Water>;

pub struct WaterPlugin;
impl Plugin for WaterPlugin {
    fn build(&self, app: &mut App) {
        embedded_asset!(app, "water.wesl");
        app.add_plugins(MaterialPlugin::<WaterMaterial>::default()).init_resource::<Made>();
    }
}

#[derive(Resource, Default)]
struct Made(Vec<(Vec4, Vec4, Profile, Handle<WaterMaterial>)>);

#[derive(SystemParam)]
pub struct WaterMaterials<'w> {
    bodies: Option<Res<'w, WaterBodies>>,
    made: ResMut<'w, Made>,
    materials: ResMut<'w, Assets<WaterMaterial>>,
}

impl WaterMaterials<'_> {
    pub fn for_model(&mut self, path: &str) -> Option<Handle<WaterMaterial>> {
        let body = self.bodies.as_ref()?.waters.iter().find(|body| {
            body.water_models.iter().any(|m| {
                let name = m.model.rsplit('/').next().unwrap_or_default();
                path == format!("{}/{name}.glb", m.model)
            })
        })?;
        let p = body.material.as_ref()?;
        let bounds = Vec4::new(body.center_m[0], body.center_m[1], body.radii_m[0], body.radii_m[1]);
        // Up to two source harmonics, supplied by the body rather than its tile chunks.
        let mut h = [0.0; 4];
        for (i, (frequency, amplitude, kind)) in body.shore_harmonics.iter().enumerate() {
            if i >= 2 {
                return None;
            }
            h[i * 2] = *frequency * if kind == "sin" { 1.0 } else { -1.0 };
            h[i * 2 + 1] = *amplitude;
        }
        let shore = Vec4::from_array(h);
        if let Some((_, _, _, material)) =
            self.made.0.iter().find(|(b, s, profile, _)| *b == bounds && *s == shore && profile == p)
        {
            return Some(material.clone());
        }
        let data = WaterUniform {
            bounds,
            shore,
            waves: Vec4::new(p.waves as f32, p.direction_start_radians, p.direction_step_radians, p.wavenumber_start),
            spectrum: Vec4::new(p.wavenumber_ratio, p.amplitude_start, p.amplitude_ratio, p.footprint_fade),
            warp: Vec4::new(p.warp_frequency, p.warp_speed, p.warp_amplitude, p.phase_step),
            calm: Vec4::new(p.shore_calm_start, p.shore_calm_end, p.shore_calm_reduction, p.gravity_factor),
            deep: Vec3::from_array(p.deep_colour_min).extend(0.0),
            deep2: Vec3::from_array(p.deep_colour_max).extend(0.0),
            shallows: Vec3::from_array(p.shallows_colour).extend(0.0),
            glint: Vec3::from_array(p.glint_colour).extend(0.0),
            drift_x: Vec3::from_array(p.drift_x).extend(0.0),
            drift_y: Vec3::from_array(p.drift_y).extend(0.0),
            crest: Vec4::new(p.crest_direction[0], p.crest_direction[1], p.crest_scale, p.crest_strength),
            glint_range: Vec4::new(p.glint_range[0], p.glint_range[1], p.drift_strength, 0.0),
            drift_colour: Vec3::from_array(p.drift_colour).extend(0.0),
            fetch: Vec3::from_array(p.fetch).extend(p.chop_scale),
            roughness: Vec4::new(p.roughness_range[0], p.roughness_range[1], p.fetch_mix, p.chop_mix),
        };
        let material = self.materials.add(WaterMaterial {
            base: StandardMaterial { metallic: p.metallic, reflectance: p.specular, ..default() },
            extension: Water { data },
        });
        self.made.0.push((bounds, shore, p.clone(), material.clone()));
        Some(material)
    }
}
