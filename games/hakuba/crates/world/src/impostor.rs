//! Impostors: a tree seen from afar is a quad facing the camera that shows its full version as it looks from there.
//! The exporter bakes each tree's full version from many directions over the upper half of the sky into two atlases
//! beside its export (`<name>.impostor.ktx2`, colour and coverage; `<name>.impostor-normal.ktx2`, normal and depth),
//! and the full node's extras say how: `{ "impostor": { "grid", "frame", "radius", "centre" } }`. The shader in
//! `impostor.wesl` blends the three views nearest the camera's direction and lights the result as the foliage shader
//! lights the tree, so a tree keeps its shape at every distance instead of swapping to a simpler one.
//!
//! An impostor mesh holds one quad a tree, four vertices, whatever its detail: each vertex is the tree's foot moved
//! out to one corner of the box around its bounding sphere, so Bevy's bounds hold the whole tree, with the quad's
//! corner in its first texture coordinates and the tree's yaw and scale in its second.

use bevy::asset::{RenderAssetUsages, embedded_asset};
use bevy::image::{ImageLoaderSettings, ImageSampler};
use bevy::mesh::{Indices, PrimitiveTopology};
use bevy::pbr::{ExtendedMaterial, MaterialExtension};
use bevy::platform::collections::HashMap;
use bevy::prelude::*;
use bevy::render::render_resource::{AsBindGroup, ShaderType};
use bevy::shader::ShaderRef;
use serde::Deserialize;

use crate::wind::SourceProfile;

pub type Impostor = ExtendedMaterial<StandardMaterial, ImpostorViews>;

pub struct ImpostorPlugin;

impl Plugin for ImpostorPlugin {
    fn build(&self, app: &mut App) {
        embedded_asset!(app, "impostor.wesl");
        app.add_plugins(MaterialPlugin::<Impostor>::default()).init_resource::<Made>();
    }
}

/// What a tree's full node says of its impostor.
#[derive(Clone, Debug, Deserialize)]
pub struct Baked {
    grid: u32,
    frame: u32,
    radius: f32,
    centre: [f32; 3],
}

impl Baked {
    /// The tree's impostor, if its full node's extras describe one.
    pub fn of(extras: &serde_json::Value) -> Option<Baked> {
        let baked: Baked = serde_json::from_value(extras.get("impostor")?.clone()).ok()?;
        (baked.grid >= 2 && baked.frame > 0 && baked.radius > 0.0 && baked.centre.iter().all(|v| v.is_finite()))
            .then_some(baked)
    }
}

#[derive(Clone, Debug, Default, Reflect, ShaderType)]
struct ImpostorParams {
    grid: Vec4,
    centre: Vec4,
    push_haze: Vec4,
    haze_colour: Vec4,
}

/// The impostor's part of its material: its atlases and how they were baked.
#[derive(Asset, AsBindGroup, Reflect, Clone, Default)]
pub struct ImpostorViews {
    #[texture(100)]
    #[sampler(101)]
    albedo: Handle<Image>,
    #[texture(102)]
    #[sampler(103)]
    normal: Handle<Image>,
    #[uniform(104)]
    params: ImpostorParams,
}

impl MaterialExtension for ImpostorViews {
    fn vertex_shader() -> ShaderRef {
        "embedded://hakuba_world/impostor.wesl".into()
    }

    fn fragment_shader() -> ShaderRef {
        "embedded://hakuba_world/impostor.wesl".into()
    }

    // An impostor is only seen: its tree's middle version casts its shadow.
    fn enable_prepass() -> bool {
        false
    }

    fn enable_shadows() -> bool {
        false
    }
}

/// Each tree's impostor material and quad, made once and shared by every copy.
#[derive(Resource, Default)]
struct Made(HashMap<String, (Handle<Impostor>, Handle<Mesh>)>);

/// Makes the materials and quads of impostors.
#[derive(bevy::ecs::system::SystemParam)]
pub struct Impostors<'w> {
    assets: Res<'w, AssetServer>,
    materials: ResMut<'w, Assets<Impostor>>,
    made: ResMut<'w, Made>,
}

impl Impostors<'_> {
    /// The material and one-tree quad of the tree exported at `model` (its path in the assets), as `baked` says.
    pub fn of(
        &mut self,
        model: &str,
        baked: &Baked,
        profile: &SourceProfile,
        meshes: &mut Assets<Mesh>,
    ) -> (Handle<Impostor>, Handle<Mesh>) {
        if let Some(made) = self.made.0.get(model) {
            return made.clone();
        }
        let stem = model.strip_suffix(".glb").unwrap_or(model);
        let load = |path: String, srgb: bool| {
            self.assets
                .load_builder()
                .with_settings(move |settings: &mut ImageLoaderSettings| {
                    settings.is_srgb = srgb;
                    settings.sampler = ImageSampler::linear();
                })
                .load(path)
        };
        let albedo = load(format!("{stem}.impostor.ktx2"), true);
        let normal = load(format!("{stem}.impostor-normal.ktx2"), false);
        let base = StandardMaterial {
            alpha_mode: AlphaMode::Mask(0.5),
            cull_mode: None,
            fog_enabled: false,
            reflectance: 0.0,
            perceptual_roughness: 1.0,
            ..default()
        };
        let params = ImpostorParams {
            grid: Vec4::new(baked.grid as f32, baked.frame as f32, baked.radius, 0.0),
            centre: Vec3::from_array(baked.centre).extend(0.0),
            push_haze: Vec4::from_array(profile.push_haze),
            haze_colour: Vec3::from_array(profile.haze_colour).extend(0.0),
        };
        let material = self.materials.add(Impostor { base, extension: ImpostorViews { albedo, normal, params } });
        let quad = meshes.add(quads(baked, &[Transform::IDENTITY], RenderAssetUsages::default()));
        self.made.0.insert(model.to_string(), (material.clone(), quad.clone()));
        (material, quad)
    }
}

/// Where each corner's vertex sits on the box around the tree's sphere, a share of its radius on each axis: two
/// opposite corners of the box, so the mesh's bounds hold it, and its foot for the others.
const CORNERS: [([f32; 2], f32); 4] = [([0.0, 0.0], -1.0), ([1.0, 0.0], 0.0), ([1.0, 1.0], 1.0), ([0.0, 1.0], 0.0)];

/// The quads of the trees standing at `transforms`, each turned only about the vertical and scaled evenly.
pub fn quads(baked: &Baked, transforms: &[Transform], usage: RenderAssetUsages) -> Mesh {
    let mut positions = Vec::with_capacity(transforms.len() * 4);
    let mut corners = Vec::with_capacity(transforms.len() * 4);
    let mut placements = Vec::with_capacity(transforms.len() * 4);
    let mut indices = Vec::with_capacity(transforms.len() * 6);
    let centre = Vec3::from_array(baked.centre);
    for transform in transforms {
        let (axis, angle) = transform.rotation.to_axis_angle();
        let yaw = angle * axis.y.signum();
        let scale = transform.scale.x;
        let middle = transform.translation + transform.rotation * centre * scale;
        let first = positions.len() as u32;
        for (corner, side) in CORNERS {
            positions.push((middle + Vec3::splat(side * baked.radius * scale)).to_array());
            corners.push(corner);
            placements.push([yaw, scale]);
        }
        indices.extend([first, first + 1, first + 2, first, first + 2, first + 3]);
    }
    let mut mesh = Mesh::new(PrimitiveTopology::TriangleList, usage);
    mesh.insert_attribute(Mesh::ATTRIBUTE_POSITION, positions);
    mesh.insert_attribute(Mesh::ATTRIBUTE_UV_0, corners);
    mesh.insert_attribute(Mesh::ATTRIBUTE_UV_1, placements);
    mesh.insert_indices(Indices::U32(indices));
    mesh
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_quad_bounds_its_tree_and_carries_its_placement() {
        let baked = Baked { grid: 8, frame: 128, radius: 5.0, centre: [0.0, 4.0, 0.0] };
        let transform =
            Transform::from_xyz(10.0, 1.0, -3.0).with_rotation(Quat::from_rotation_y(0.7)).with_scale(Vec3::splat(1.2));
        let mesh = quads(&baked, &[transform], RenderAssetUsages::MAIN_WORLD);
        let positions = mesh.attribute(Mesh::ATTRIBUTE_POSITION).unwrap().as_float3().unwrap();
        let centre = Vec3::new(10.0, 1.0 + 4.8, -3.0);
        assert!((Vec3::from(positions[0]) - (centre - Vec3::splat(6.0))).length() < 1e-4);
        assert!((Vec3::from(positions[2]) - (centre + Vec3::splat(6.0))).length() < 1e-4);
        let Some(bevy::mesh::VertexAttributeValues::Float32x2(placements)) = mesh.attribute(Mesh::ATTRIBUTE_UV_1)
        else {
            panic!("no placements")
        };
        assert!((placements[0][0] - 0.7).abs() < 1e-5 && (placements[0][1] - 1.2).abs() < 1e-6);
    }
}
