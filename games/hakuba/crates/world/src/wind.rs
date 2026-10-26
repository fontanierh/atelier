//! The wind: plants lean downwind as gusts roll across the world, their branches sway around that, each part at its
//! own point in the swing, and their leaves flutter. A model's export says how far each vertex bends, in metres, and
//! its leaf's phase, in its second texture coordinates: a plant bends from its foot, so its top and the outside of its
//! crown move most. A part that sways is drawn with its own material and the vertex shader in `wind.wesl`, in every
//! pass, so its shadow sways with it. How strongly the wind blows, the Wind setting, reaches the shader as each swaying
//! mesh's tag, in thousandths, so plants are still drawn together. Leaves and blades also lean away from whatever pushes
//! plants (`push.rs`), however the wind blows. The same shader swaps a plant's full version for its middle one with
//! distance, a card at a time ([`Swap`]).

use bevy::asset::embedded_asset;
use bevy::ecs::system::SystemParam;
use bevy::pbr::{ExtendedMaterial, MaterialExtension};
use bevy::platform::collections::HashMap;
use bevy::prelude::*;
use bevy::render::render_resource::AsBindGroup;
use bevy::render::storage::ShaderBuffer;
use bevy::shader::ShaderRef;

use crate::push::Pushers;

/// Up to how far from the camera, in metres, a plant in a full tile shows its full version, and over how many more it
/// gives way to its middle one. A tree's hundreds of leaf cards cost most of a frame's drawing; beyond this, their
/// detail is too small to see, so the middle version's few larger cards look the same for a sixth of the cost.
pub const FULL_UP_TO_M: f32 = 20.0;
pub const SWAP_M: f32 = 6.0;

/// A plant version that swaps with the other by distance from the camera, over [`SWAP_M`] from [`FULL_UP_TO_M`]: the
/// full version going, the middle one coming. The shader swaps them a whole card or blade at a time, each at its own
/// distance, and the wood halfway: a screen-space dither would shimmer under temporal anti-aliasing.
#[derive(Component, Clone, Copy, PartialEq, Eq, Debug)]
pub enum Swap {
    Going,
    Coming,
}

/// The tag's bits that say how strongly the wind blows; the two above them say how the mesh swaps, as `wind.wesl` reads
/// them.
const STRENGTH: u32 = (1 << 30) - 1;

/// The mesh tag that tells the shader the wind blows `strength` times as strongly as usual, and how the mesh swaps.
pub fn tag(strength: f32, swap: Option<Swap>) -> u32 {
    let strength = ((strength.max(0.0) * 1000.0).round() as u32).min(STRENGTH);
    strength
        | match swap {
            None => 0,
            Some(Swap::Going) => 1 << 30,
            Some(Swap::Coming) => 1 << 31,
        }
}

/// A plant's material, swaying.
pub type Swaying = ExtendedMaterial<StandardMaterial, Wind>;

pub struct WindPlugin;

impl Plugin for WindPlugin {
    fn build(&self, app: &mut App) {
        embedded_asset!(app, "wind.wesl");
        app.add_plugins(MaterialPlugin::<Swaying>::default()).init_resource::<Made>();
    }
}

/// The wind's part of a swaying material: its vertex shader, and where the things that push plants aside are, in a
/// buffer every swaying material shares.
#[derive(Asset, AsBindGroup, Reflect, Clone, Default)]
pub struct Wind {
    #[storage(100, read_only)]
    pushers: Handle<ShaderBuffer>,
    /// Where plants swap versions: from [`FULL_UP_TO_M`], over [`SWAP_M`].
    #[uniform(101)]
    swap: Vec4,
}

impl MaterialExtension for Wind {
    fn vertex_shader() -> ShaderRef {
        "embedded://hakuba_world/wind.wesl".into()
    }

    fn prepass_vertex_shader() -> ShaderRef {
        "embedded://hakuba_world/wind.wesl".into()
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
        let handle = self.swaying.add(Swaying {
            base,
            extension: Wind { pushers: self.pushers.0.clone(), swap: Vec4::new(FULL_UP_TO_M, SWAP_M, 0.0, 0.0) },
        });
        self.made.0.insert(material.id(), handle.clone());
        Some(handle)
    }
}
