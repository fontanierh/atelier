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
use bevy::render::render_resource::AsBindGroup;
use bevy::render::storage::ShaderBuffer;
use bevy::shader::ShaderRef;

use crate::push::Pushers;

/// The mesh tag that tells the shader the wind blows `strength` times as strongly as usual.
pub fn tag(strength: f32) -> u32 {
    (strength.max(0.0) * 1000.0).round() as u32
}

/// A plant's material, swaying.
pub type Swaying = ExtendedMaterial<StandardMaterial, Wind>;

pub struct WindPlugin;

impl Plugin for WindPlugin {
    fn build(&self, app: &mut App) {
        embedded_asset!(app, "wind.wesl");
        embedded_asset!(app, "leaves.wesl");
        app.add_plugins(MaterialPlugin::<Swaying>::default())
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

/// The swaying version of each plant material, made once, so every copy of a plant shares it and is drawn with the
/// others.
#[derive(Resource, Default)]
struct Made(HashMap<AssetId<StandardMaterial>, Handle<Swaying>>);

/// Makes the swaying versions of plant materials.
#[derive(SystemParam)]
pub struct SwayingMaterials<'w> {
    made: ResMut<'w, Made>,
    standard: Res<'w, Assets<StandardMaterial>>,
    swaying: ResMut<'w, Assets<Swaying>>,
    pushers: Res<'w, Pushers>,
}

impl SwayingMaterials<'_> {
    /// The swaying version of `material`, or None while it is still loading.
    pub fn of(&mut self, material: &Handle<StandardMaterial>) -> Option<Handle<Swaying>> {
        if let Some(handle) = self.made.0.get(&material.id()) {
            return Some(handle.clone());
        }
        let base = self.standard.get(material)?.clone();
        let handle = self.swaying.add(Swaying { base, extension: Wind { pushers: self.pushers.0.clone() } });
        self.made.0.insert(material.id(), handle.clone());
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
