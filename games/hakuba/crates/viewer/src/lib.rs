//! The character viewer: one character at a time on a plain stage, a camera that circles it, and buttons to pick the
//! character and the clip it plays.

mod orbit;

use bevy::prelude::*;
use bevy::ui_widgets::{Activate, observe};
use hakuba_characters::{Character, Clips, Play};
use hakuba_screens::{Screen, button, text};
use orbit::{Orbit, orbit};

pub struct ViewerPlugin;

impl Plugin for ViewerPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(Screen::Viewer), show)
            .add_systems(Update, (orbit, list_clips).run_if(in_state(Screen::Viewer)));
    }
}

/// The column the clip buttons go in.
#[derive(Component)]
struct ClipList;

fn show(mut commands: Commands, mut meshes: ResMut<Assets<Mesh>>, mut materials: ResMut<Assets<StandardMaterial>>) {
    let on_screen = DespawnOnExit(Screen::Viewer);
    commands.insert_resource(ClearColor(Color::srgb(0.22, 0.23, 0.25)));
    commands.spawn((
        on_screen.clone(),
        Mesh3d(meshes.add(Circle::new(1.5))),
        MeshMaterial3d(materials.add(StandardMaterial {
            base_color: Color::srgb(0.4, 0.4, 0.42),
            perceptual_roughness: 1.0,
            ..default()
        })),
        Transform::from_rotation(Quat::from_rotation_x(-std::f32::consts::FRAC_PI_2)),
    ));
    commands.spawn((
        on_screen.clone(),
        DirectionalLight { illuminance: light_consts::lux::AMBIENT_DAYLIGHT, shadow_maps_enabled: true, ..default() },
        Transform::from_xyz(2.0, 4.0, 3.0).looking_at(Vec3::ZERO, Vec3::Y),
    ));
    commands.spawn((
        on_screen.clone(),
        Camera3d::default(),
        Orbit { focus: Vec3::new(0.0, 1.0, 0.0), yaw: 0.0, pitch: 0.1, distance: 3.0 },
        Transform::default(),
    ));
    let mut characters = commands.spawn((
        on_screen.clone(),
        Node { flex_direction: FlexDirection::Column, row_gap: px(8), margin: UiRect::all(px(16)), ..default() },
        children![text("Characters", 24.0)],
    ));
    for character in Character::ALL {
        characters.with_child((button(character.name()), observe(show_character(character))));
    }
    characters.with_child((
        button("Menu"),
        observe(|_: On<Activate>, mut next: ResMut<NextState<Screen>>| {
            next.set(Screen::Menu);
        }),
    ));
    commands.spawn((
        on_screen.clone(),
        ClipList,
        Node {
            position_type: PositionType::Absolute,
            right: px(16),
            top: px(16),
            flex_direction: FlexDirection::Column,
            row_gap: px(8),
            ..default()
        },
    ));
    commands.spawn((on_screen, Character::ALL[0]));
}

/// Replaces the character on the stage with `character`.
fn show_character(character: Character) -> impl Fn(On<Activate>, Commands, Query<Entity, With<Character>>) {
    move |_, mut commands, shown| {
        for entity in &shown {
            commands.entity(entity).despawn();
        }
        commands.spawn((DespawnOnExit(Screen::Viewer), character));
    }
}

/// Fills the clip column once a character's clips have loaded.
fn list_clips(
    mut commands: Commands,
    loaded: Query<(Entity, &Clips), Added<Clips>>,
    list: Single<Entity, With<ClipList>>,
) {
    let Some((character, clips)) = loaded.iter().next() else { return };
    commands.entity(*list).despawn_children().with_child(text("Clips", 24.0));
    for name in clips.names() {
        let clip = name.to_owned();
        commands.entity(*list).with_child((
            button(name),
            observe(move |_: On<Activate>, mut commands: Commands| {
                commands.trigger(Play { entity: character, clip: clip.clone() });
            }),
        ));
    }
}
