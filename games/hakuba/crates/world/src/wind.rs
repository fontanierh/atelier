//! The wind: leaves and grass sway as two slow waves roll across the world, as in Yorimichi, so neighbouring plants
//! lean together and far ones move out of step. A model's export says how far each vertex sways at a full gust, in
//! metres, in its second texture coordinates: the tips of blades and the tops of crowns most, roots and trunks not at
//! all. A part that sways is drawn with its own material and this vertex shader, in every pass, so its shadow sways
//! with it and temporal anti-aliasing follows it. Yorimichi also pushed plants away from the player; Hakuba has no one
//! walking yet.

use bevy::asset::embedded_asset;
use bevy::ecs::system::SystemParam;
use bevy::pbr::{ExtendedMaterial, MaterialExtension};
use bevy::platform::collections::HashMap;
use bevy::prelude::*;
use bevy::render::render_resource::AsBindGroup;
use bevy::shader::ShaderRef;

/// A plant's material, swaying.
pub type Swaying = ExtendedMaterial<StandardMaterial, Wind>;

pub struct WindPlugin;

impl Plugin for WindPlugin {
    fn build(&self, app: &mut App) {
        embedded_asset!(app, "wind.wesl");
        app.add_plugins(MaterialPlugin::<Swaying>::default()).init_resource::<Made>();
    }
}

/// The wind's part of a swaying material: its vertex shader.
#[derive(Asset, AsBindGroup, Reflect, Clone, Default)]
pub struct Wind {}

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
}

impl SwayingMaterials<'_> {
    /// The swaying version of `material`, or None while it is still loading.
    pub fn of(&mut self, material: &Handle<StandardMaterial>) -> Option<Handle<Swaying>> {
        if let Some(handle) = self.made.0.get(&material.id()) {
            return Some(handle.clone());
        }
        let base = self.standard.get(material)?.clone();
        let handle = self.swaying.add(Swaying { base, extension: Wind {} });
        self.made.0.insert(material.id(), handle.clone());
        Some(handle)
    }
}
