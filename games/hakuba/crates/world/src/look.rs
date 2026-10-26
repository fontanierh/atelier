//! How the world looks: a sky dome painted with clouds, light from that sky above and from the ground below, a low
//! warm sun behind the traveller, a blue haze that thickens with distance, and the camera's colour grade (tone curve,
//! bloom, vignette) and painterly filter. How far the sun casts shadows and how edges are smoothed are settings
//! (`settings.rs` applies them). By default edges are smoothed by temporal anti-aliasing, as in Yorimichi: the camera
//! shifts by part of a pixel each frame and each pixel blends the frames, so grass and other edges thinner than a
//! pixel stay whole and steady as the camera moves. It costs about as little as no smoothing at all. By default shadows reach 60 m, in one cascade: the trees and bushes along the road. Further
//! out, the haze and the painterly filter soften what shadows would show, and each cascade draws the world again.

use std::f32::consts::FRAC_PI_2;

use bevy::core_pipeline::tonemapping::Tonemapping;
use bevy::pbr::{DistanceFog, FogFalloff};
use bevy::post_process::bloom::Bloom;
use bevy::post_process::effect_stack::Vignette;
use bevy::prelude::*;
use hakuba_screens::Screen;

use crate::painterly::Painterly;

/// The painted sky, from the zenith in its top row to below the horizon, all the way round.
const SKY: &str = "textures/sky/sky.ktx2";

/// How much brighter than its colours the sky shows, so the clouds' tops go past white.
const SKY_BRIGHTNESS: f32 = 1.35;

/// The sky dome's radius: past everything else in the world.
const SKY_RADIUS_M: f32 = 20000.0;

/// How far the camera sees, for culling.
const FAR_M: f32 = 30000.0;

/// The sun's height above the horizon, and the way it shines, as a compass bearing east of north.
const SUN_ELEVATION_DEG: f32 = 26.0;
const SUN_BEARING_DEG: f32 = 60.0;

/// The sun's light, in lux, and its colour: Yorimichi's late-afternoon sun.
const SUN_LUX: f32 = 6000.0;
const SUN_COLOUR: [f32; 3] = [1.0, 0.86, 0.68];

/// The light that fills the shadows, linear: blue from the sky above, pale at the horizon and warm green from the
/// grass below, as Yorimichi's sky light captures its painted dome, and how bright it is.
const SKY_LIGHT: [f32; 3] = [0.62, 0.78, 1.0];
const HORIZON_LIGHT: [f32; 3] = [0.95, 0.96, 1.0];
const GROUND_LIGHT: [f32; 3] = [0.42, 0.42, 0.24];
const FILL_BRIGHTNESS: f32 = 1900.0;

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
pub fn camera(images: &mut Assets<Image>) -> impl Bundle {
    let linear = |c: [f32; 3]| Color::linear_rgb(c[0], c[1], c[2]);
    (
        Projection::Perspective(PerspectiveProjection { far: FAR_M, ..default() }),
        Tonemapping::AcesFitted,
        Msaa::Off,
        Bloom::NATURAL,
        Vignette { intensity: 0.16, ..default() },
        Painterly::default(),
        EnvironmentMapLight::hemispherical_gradient(
            images,
            linear(SKY_LIGHT),
            linear(HORIZON_LIGHT),
            linear(GROUND_LIGHT),
        )
        .with_intensity(FILL_BRIGHTNESS),
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
    assets: Res<AssetServer>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    commands.spawn((
        Name::new("Sky"),
        Sky,
        DespawnOnExit(Screen::World),
        Mesh3d(meshes.add(Sphere::new(1.0).mesh().uv(64, 32))),
        MeshMaterial3d(materials.add(StandardMaterial {
            base_color: Color::linear_rgb(SKY_BRIGHTNESS, SKY_BRIGHTNESS, SKY_BRIGHTNESS),
            base_color_texture: Some(assets.load(SKY)),
            unlit: true,
            fog_enabled: false,
            cull_mode: None,
            ..default()
        })),
        // A UV sphere's poles are on its Z axis: turned so its first row, the zenith, is straight up.
        Transform::from_scale(Vec3::splat(SKY_RADIUS_M)).with_rotation(Quat::from_rotation_x(-FRAC_PI_2)),
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
            ..default()
        },
        Transform::default().looking_to(shining, Vec3::Y),
    ));
}

fn follow_camera(
    camera: Single<&Transform, (With<Camera3d>, Without<Sky>)>,
    mut sky: Single<&mut Transform, With<Sky>>,
) {
    sky.translation = camera.translation;
}
