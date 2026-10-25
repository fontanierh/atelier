//! The world: flat ground to the horizon, a sun and a camera looking at the origin.

use bevy::prelude::*;
use hakuba_screens::Screen;

/// Side of the square ground, in metres: wide enough that its edge stays out of sight.
const GROUND_SIZE_M: f32 = 4000.0;

pub struct WorldPlugin;

impl Plugin for WorldPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(Screen::World), spawn_world);
    }
}

fn spawn_world(
    mut commands: Commands,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    commands.insert_resource(ClearColor(Color::srgb(0.53, 0.72, 0.9)));
    commands.spawn((
        Name::new("Ground"),
        DespawnOnExit(Screen::World),
        Mesh3d(meshes.add(Plane3d::default().mesh().size(GROUND_SIZE_M, GROUND_SIZE_M))),
        MeshMaterial3d(materials.add(StandardMaterial {
            base_color: Color::srgb(0.36, 0.5, 0.3),
            perceptual_roughness: 1.0,
            ..default()
        })),
    ));
    commands.spawn((
        Name::new("Sun"),
        DespawnOnExit(Screen::World),
        DirectionalLight {
            illuminance: light_consts::lux::AMBIENT_DAYLIGHT,
            shadow_maps_enabled: true,
            ..default()
        },
        Transform::from_xyz(30.0, 60.0, 20.0).looking_at(Vec3::ZERO, Vec3::Y),
    ));
    commands.spawn((
        Name::new("Camera"),
        DespawnOnExit(Screen::World),
        Camera3d::default(),
        Transform::from_xyz(0.0, 1.6, 4.0).looking_at(Vec3::new(0.0, 0.9, 0.0), Vec3::Y),
    ));
}
