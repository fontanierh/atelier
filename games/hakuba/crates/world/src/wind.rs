//! The wind: plants lean downwind as gusts roll across the world, their branches sway around that, each part at its
//! own point in the swing, and their leaves flutter. A model's export says how far each vertex bends, in metres, and
//! its leaf's phase, in its second texture coordinates: a plant bends from its foot, so its top and the outside of its
//! crown move most. A part that sways is drawn with its own material and the vertex shader in `wind.wesl`, in every
//! pass, so its shadow sways with it. How strongly the wind blows, the Wind setting, reaches the shader as each swaying
//! mesh's tag, in thousandths, so plants are still drawn together. Leaves and blades also lean away from whatever pushes
//! plants (`push.rs`), however the wind blows. Its fragment shader, in `leaves.wesl`, lights only the texels a leaf card
//! keeps; anything else cut out with the standard material is reported, since it pays the lighting of every texel.

use bevy::asset::embedded_asset;
use bevy::ecs::system::SystemParam;
use bevy::pbr::{ExtendedMaterial, MaterialExtension};
use bevy::platform::collections::{HashMap, HashSet};
use bevy::prelude::*;
use bevy::render::render_resource::{AsBindGroup, ShaderType};
use bevy::render::storage::ShaderBuffer;
use bevy::shader::ShaderRef;
use serde::{Deserialize, Serialize};

use crate::push::Pushers;

/// The mesh tag that tells the shader the wind blows `strength` times as strongly as usual.
pub fn tag(strength: f32) -> u32 {
    (strength.max(0.0) * 1000.0).round() as u32
}

/// A plant's material, swaying.
pub type Swaying = ExtendedMaterial<StandardMaterial, Wind>;

/// Original per-vertex foliage weights, distinct from generated-plant bend and phase.
pub type SourceFoliage = ExtendedMaterial<StandardMaterial, SourceWind>;

pub struct WindPlugin;

impl Plugin for WindPlugin {
    fn build(&self, app: &mut App) {
        embedded_asset!(app, "wind.wesl");
        embedded_asset!(app, "leaves.wesl");
        embedded_asset!(app, "source_foliage.wesl");
        embedded_asset!(app, "source_leaves.wesl");
        app.add_plugins((MaterialPlugin::<Swaying>::default(), MaterialPlugin::<SourceFoliage>::default()))
            .init_resource::<Made>()
            .add_systems(PostUpdate, cut_out_in_full);
    }
}

/// The wind's part of a swaying material: its shaders, and where the things that push plants aside are, in a
/// buffer every swaying material shares.
#[derive(Asset, AsBindGroup, Reflect, Clone, Default)]
pub struct Wind {
    #[storage(100, read_only)]
    pushers: Handle<ShaderBuffer>,
}

impl MaterialExtension for Wind {
    fn vertex_shader() -> ShaderRef {
        "embedded://hakuba_world/wind.wesl".into()
    }

    fn prepass_vertex_shader() -> ShaderRef {
        "embedded://hakuba_world/wind.wesl".into()
    }

    fn fragment_shader() -> ShaderRef {
        "embedded://hakuba_world/leaves.wesl".into()
    }
}

/// Asset-owned motion and atmospheric coefficients for a source foliage material.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SourceProfile {
    pub direction_amplitude_shade: [f32; 4],
    pub slow: [f32; 4],
    pub fast: [f32; 4],
    pub global_slow: [f32; 4],
    pub global_fast: [f32; 4],
    /// Third global gust: frequency and amplitude; final two components are reserved.
    pub global_tail: [f32; 4],
    pub push_haze: [f32; 4],
    pub haze_colour: [f32; 3],
    #[serde(default = "unit_wind")]
    pub wind_scale: f32,
    #[serde(default)]
    pub up_normal: bool,
}

fn unit_wind() -> f32 {
    1.0
}

impl SourceProfile {
    /// Maximum horizontal source-shader displacement, as (wind coefficient, player push).
    pub(crate) fn shadow_motion_bound(&self, weight: f32) -> (f32, f32) {
        let gust = self.fast[3].abs() + self.slow[3].abs() + self.fast[2].abs();
        let global = self.global_fast[3]
            .abs()
            .max(
                self.global_slow[3].abs()
                    + self.global_slow[2].abs()
                    + self.global_fast[2].abs()
                    + self.global_tail[1].abs(),
            )
            .max(1.0);
        let scale = self.wind_scale * weight;
        (scale * self.direction_amplitude_shade[2].abs() * gust * global, scale * self.push_haze[1].abs())
    }

    pub fn valid(&self) -> bool {
        self.direction_amplitude_shade
            .iter()
            .chain(&self.slow)
            .chain(&self.fast)
            .chain(&self.global_slow)
            .chain(&self.global_fast)
            .chain(&self.global_tail)
            .chain(&self.push_haze)
            .chain(&self.haze_colour)
            .all(|x| x.is_finite())
            && (self.direction_amplitude_shade[0].powi(2) + self.direction_amplitude_shade[1].powi(2)) > 0.0
            && self.global_tail[2] == 0.0
            && self.global_tail[3] == 0.0
            && self.wind_scale.is_finite()
            && self.wind_scale >= 0.0
            && self.push_haze[0] > 0.0
            && self.push_haze[3] > 0.0
    }
}

#[derive(Clone, Debug, Default, Reflect, ShaderType)]
struct SourceUniform {
    direction: Vec4,
    slow: Vec4,
    fast: Vec4,
    global_slow: Vec4,
    global_fast: Vec4,
    global_tail: Vec4,
    push_haze: Vec4,
    haze_colour: Vec4,
}

/// Wind driven by source vertex colours, shared by the main and shadow passes.
#[derive(Asset, AsBindGroup, Reflect, Clone, Default)]
pub struct SourceWind {
    #[storage(100, read_only)]
    pushers: Handle<ShaderBuffer>,
    #[uniform(101)]
    profile: SourceUniform,
}

impl MaterialExtension for SourceWind {
    fn vertex_shader() -> ShaderRef {
        "embedded://hakuba_world/source_foliage.wesl".into()
    }
    fn prepass_vertex_shader() -> ShaderRef {
        "embedded://hakuba_world/source_foliage.wesl".into()
    }
    fn fragment_shader() -> ShaderRef {
        "embedded://hakuba_world/source_leaves.wesl".into()
    }
}

/// The swaying version of each plant material, made once, so every copy of a plant shares it and is drawn with the
/// others.
#[derive(Resource, Default)]
struct Made {
    generated: HashMap<AssetId<StandardMaterial>, Handle<Swaying>>,
    source: HashMap<(AssetId<StandardMaterial>, String), Handle<SourceFoliage>>,
}

/// Makes the swaying versions of plant materials.
#[derive(SystemParam)]
pub struct SwayingMaterials<'w> {
    made: ResMut<'w, Made>,
    standard: Res<'w, Assets<StandardMaterial>>,
    swaying: ResMut<'w, Assets<Swaying>>,
    source: ResMut<'w, Assets<SourceFoliage>>,
    pushers: Res<'w, Pushers>,
}

impl SwayingMaterials<'_> {
    /// The source-foliage material, or None while its base is loading.
    pub fn source_of(
        &mut self,
        material: &Handle<StandardMaterial>,
        profile: &SourceProfile,
    ) -> Option<Handle<SourceFoliage>> {
        let key = (material.id(), serde_json::to_string(profile).ok()?);
        if let Some(handle) = self.made.source.get(&key) {
            return Some(handle.clone());
        }
        let mut base = self.standard.get(material)?.clone();
        base.fog_enabled = false;
        base.reflectance = 0.0;
        let moving = if matches!(base.alpha_mode, AlphaMode::Mask(_)) { 1.0 } else { 0.0 };
        let params = SourceUniform {
            direction: Vec4::from_array(profile.direction_amplitude_shade),
            slow: Vec4::from_array(profile.slow),
            fast: Vec4::from_array(profile.fast),
            global_slow: Vec4::from_array(profile.global_slow),
            global_fast: Vec4::from_array(profile.global_fast),
            global_tail: Vec4::new(
                profile.global_tail[0],
                profile.global_tail[1],
                profile.wind_scale,
                if profile.up_normal { 1.0 } else { 0.0 },
            ),
            push_haze: Vec4::from_array(profile.push_haze),
            haze_colour: Vec4::new(profile.haze_colour[0], profile.haze_colour[1], profile.haze_colour[2], moving),
        };
        let handle = self
            .source
            .add(SourceFoliage { base, extension: SourceWind { pushers: self.pushers.0.clone(), profile: params } });
        self.made.source.insert(key, handle.clone());
        Some(handle)
    }

    /// The swaying version of `material`, or None while it is still loading.
    pub fn of(&mut self, material: &Handle<StandardMaterial>) -> Option<Handle<Swaying>> {
        if let Some(handle) = self.made.generated.get(&material.id()) {
            return Some(handle.clone());
        }
        let base = self.standard.get(material)?.clone();
        let handle = self.swaying.add(Swaying { base, extension: Wind { pushers: self.pushers.0.clone() } });
        self.made.generated.insert(material.id(), handle.clone());
        Some(handle)
    }
}

/// Reports, once each, the standard materials that cut out what they draw: Bevy's shader lights every texel they
/// discard in the browser, so anything cut out belongs with the plants' fragment shader.
fn cut_out_in_full(
    drawn: Query<&MeshMaterial3d<StandardMaterial>, Added<MeshMaterial3d<StandardMaterial>>>,
    materials: Res<Assets<StandardMaterial>>,
    mut reported: Local<HashSet<AssetId<StandardMaterial>>>,
) {
    for material in &drawn {
        let cut_out =
            materials.get(&material.0).is_some_and(|standard| matches!(standard.alpha_mode, AlphaMode::Mask(_)));
        if cut_out && reported.insert(material.id()) {
            error!(
                "{:?} cuts out with the standard shader, which lights what it discards: draw it with the plants' material",
                material.0.path()
            );
        }
    }
}

#[cfg(test)]
mod shadow_motion_tests {
    use super::SourceProfile;

    #[test]
    fn source_shadow_motion_includes_gust_push_and_weight() {
        let profile = SourceProfile {
            direction_amplitude_shade: [1.0, 0.0, 0.2, 0.0],
            slow: [0.0, 0.0, 0.0, 0.6],
            fast: [0.0, 0.0, 0.3, 0.5],
            global_slow: [0.0, 0.0, 0.45, 1.0],
            global_fast: [0.0, 0.0, 0.3, 0.15],
            global_tail: [0.0, 0.15, 0.0, 0.0],
            push_haze: [1.0, 0.7, 0.0, 1.0],
            haze_colour: [0.0; 3],
            wind_scale: 2.0,
            up_normal: false,
        };
        let (wind, push) = profile.shadow_motion_bound(0.5);
        assert!((wind - 0.532).abs() < 1e-6);
        assert!((push - 0.7).abs() < 1e-6);
    }
}
