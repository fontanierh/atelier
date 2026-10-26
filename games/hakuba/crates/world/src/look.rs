//! How the world looks: a sky dome, a low warm sun behind the traveller, a blue haze that thickens with distance,
//! and the camera's colour grade (tone curve, bloom, vignette) and painterly filter.

use bevy::core_pipeline::tonemapping::Tonemapping;
use bevy::mesh::VertexAttributeValues;
use bevy::pbr::{DistanceFog, FogFalloff};
use bevy::post_process::bloom::Bloom;
use bevy::post_process::effect_stack::Vignette;
use bevy::prelude::*;
use hakuba_screens::Screen;

use crate::painterly::Painterly;

/// The sky's colour straight up, at the horizon, and below it, in sRGB.
const ZENITH: [f32; 3] = [0.14, 0.32, 0.66];
const HORIZON: [f32; 3] = [0.34, 0.52, 0.76];
const BELOW: [f32; 3] = [0.34, 0.48, 0.70];

/// How much brighter than its colours the sky shows.
const SKY_BRIGHTNESS: f32 = 1.35;

/// The sky dome's radius: past everything else in the world.
const SKY_RADIUS_M: f32 = 20000.0;

/// How far the camera sees, for culling.
const FAR_M: f32 = 30000.0;

/// The sun's height above the horizon, and the way it shines, as a compass bearing east of north.
const SUN_ELEVATION_DEG: f32 = 26.0;
const SUN_BEARING_DEG: f32 = 60.0;

/// The sun's light, in lux, and its warm colour.
const SUN_LUX: f32 = 6000.0;
const SUN_COLOUR: [f32; 3] = [1.0, 0.76, 0.53];

/// The light from the sky that fills the shadows.
const AMBIENT: [f32; 3] = [0.95, 0.96, 1.0];
const AMBIENT_BRIGHTNESS: f32 = 1800.0;

/// The haze's colour, linear, and how fast it thickens: at 9 km it hides 63 % of what is behind it.
const HAZE: [f32; 3] = [0.0932, 0.2301, 0.5328];
const HAZE_DENSITY: f32 = 1.0 / 9000.0;

pub struct LookPlugin;

impl Plugin for LookPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(Screen::World), spawn_sky_and_sun)
            .add_systems(PostUpdate, follow_camera.before(TransformSystems::Propagate).run_if(in_state(Screen::World)));
    }
}

/// What the world's camera needs for the world's look.
pub fn camera() -> impl Bundle {
    (
        Projection::Perspective(PerspectiveProjection { far: FAR_M, ..default() }),
        Tonemapping::AcesFitted,
        Bloom::NATURAL,
        Vignette { intensity: 0.16, ..default() },
        Painterly::default(),
        AmbientLight { color: Color::srgb_from_array(AMBIENT), brightness: AMBIENT_BRIGHTNESS, ..default() },
        DistanceFog {
            color: Color::linear_rgb(HAZE[0], HAZE[1], HAZE[2]),
            falloff: FogFalloff::Exponential { density: HAZE_DENSITY },
            ..default()
        },
    )
}

/// The sky dome, which stays centred on the camera.
#[derive(Component)]
struct Sky;

fn spawn_sky_and_sun(
    mut commands: Commands,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    commands.spawn((
        Name::new("Sky"),
        Sky,
        DespawnOnExit(Screen::World),
        Mesh3d(meshes.add(sky_dome())),
        MeshMaterial3d(materials.add(StandardMaterial {
            base_color: Color::linear_rgb(SKY_BRIGHTNESS, SKY_BRIGHTNESS, SKY_BRIGHTNESS),
            unlit: true,
            fog_enabled: false,
            cull_mode: None,
            ..default()
        })),
        Transform::from_scale(Vec3::splat(SKY_RADIUS_M)),
        bevy::light::NotShadowCaster,
    ));
    let (elevation, bearing) = (SUN_ELEVATION_DEG.to_radians(), SUN_BEARING_DEG.to_radians());
    // East is +X and north is -Z; the light shines downward.
    let shining = Vec3::new(elevation.cos() * bearing.sin(), -elevation.sin(), -elevation.cos() * bearing.cos());
    commands.spawn((
        Name::new("Sun"),
        DespawnOnExit(Screen::World),
        DirectionalLight {
            illuminance: SUN_LUX,
            color: Color::linear_rgb(SUN_COLOUR[0], SUN_COLOUR[1], SUN_COLOUR[2]),
            shadow_maps_enabled: true,
            ..default()
        },
        Transform::default().looking_to(shining, Vec3::Y),
    ));
}

/// A sphere of radius one whose vertex colours paint the sky: from the horizon's colour to the zenith's above, and
/// one colour below.
fn sky_dome() -> Mesh {
    let mut mesh = Sphere::new(1.0).mesh().uv(64, 32);
    let Some(VertexAttributeValues::Float32x3(positions)) = mesh.attribute(Mesh::ATTRIBUTE_POSITION) else {
        unreachable!("a sphere has positions");
    };
    let linear = |c: [f32; 3]| Color::srgb_from_array(c).to_linear();
    let (zenith, horizon, below) = (linear(ZENITH), linear(HORIZON), linear(BELOW));
    let colours: Vec<[f32; 4]> = positions
        .iter()
        .map(|p| {
            let height = p[1].clamp(-1.0, 1.0).asin() / std::f32::consts::FRAC_PI_2;
            let colour = if height < 0.0 { below } else { horizon.mix(&zenith, height.powf(0.6)) };
            colour.to_f32_array()
        })
        .collect();
    mesh.insert_attribute(Mesh::ATTRIBUTE_COLOR, colours);
    mesh
}

fn follow_camera(camera: Single<&Transform, (With<Camera3d>, Without<Sky>)>, mut sky: Single<&mut Transform, With<Sky>>) {
    sky.translation = camera.translation;
}
