//! __Title__: a lit cube on a ground, seen from a camera, to start from.

use bevy::prelude::*;

fn main() {
    App::new()
        .add_plugins(DefaultPlugins.set(WindowPlugin {
            primary_window: Some(Window { title: "__Title__".into(), ..default() }),
            ..default()
        }))
        .add_systems(Startup, setup)
        .add_systems(Update, spin)
        .run();
}

/// What turns.
#[derive(Component)]
struct Spins;

fn setup(mut commands: Commands, mut meshes: ResMut<Assets<Mesh>>, mut materials: ResMut<Assets<StandardMaterial>>) {
    commands.spawn((
        Mesh3d(meshes.add(Plane3d::default().mesh().size(20.0, 20.0))),
        MeshMaterial3d(materials.add(Color::srgb(0.35, 0.5, 0.3))),
    ));
    commands.spawn((
        Spins,
        Mesh3d(meshes.add(Cuboid::new(1.0, 1.0, 1.0))),
        MeshMaterial3d(materials.add(Color::srgb(0.8, 0.55, 0.3))),
        Transform::from_xyz(0.0, 0.5, 0.0),
    ));
    commands.spawn((DirectionalLight { shadows_enabled: true, ..default() }, Transform::from_xyz(4.0, 8.0, 4.0).looking_at(Vec3::ZERO, Vec3::Y)));
    commands.spawn((Camera3d::default(), Transform::from_xyz(-3.0, 3.0, 6.0).looking_at(Vec3::new(0.0, 0.5, 0.0), Vec3::Y)));
}

fn spin(time: Res<Time>, mut spinning: Query<&mut Transform, With<Spins>>) {
    for mut at in &mut spinning {
        at.rotate_y(time.delta_secs());
    }
}
