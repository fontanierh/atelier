//! The map. For now it is empty: flat ground, a sun and a camera looking at the origin.

use bevy::prelude::*;

/// Side of the square ground, in metres.
const GROUND_SIZE_M: f32 = 200.0;

pub struct WorldPlugin;

impl Plugin for WorldPlugin {
    fn build(&self, app: &mut App) {
        app.insert_resource(ClearColor(Color::srgb(0.53, 0.72, 0.9)))
            .add_systems(Startup, spawn_empty_map);
    }
}

fn spawn_empty_map(
    mut commands: Commands,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    commands.spawn((
        Name::new("Ground"),
        Mesh3d(meshes.add(Plane3d::default().mesh().size(GROUND_SIZE_M, GROUND_SIZE_M))),
        MeshMaterial3d(materials.add(StandardMaterial {
            base_color: Color::srgb(0.36, 0.5, 0.3),
            perceptual_roughness: 1.0,
            ..default()
        })),
    ));
    commands.spawn((
        Name::new("Sun"),
        DirectionalLight {
            illuminance: light_consts::lux::AMBIENT_DAYLIGHT,
            shadow_maps_enabled: true,
            ..default()
        },
        Transform::from_xyz(30.0, 60.0, 20.0).looking_at(Vec3::ZERO, Vec3::Y),
    ));
    // Stands in until the player crate brings a follow camera.
    commands.spawn((
        Name::new("Overview camera"),
        Camera3d::default(),
        Transform::from_xyz(0.0, 12.0, 24.0).looking_at(Vec3::ZERO, Vec3::Y),
    ));
}
