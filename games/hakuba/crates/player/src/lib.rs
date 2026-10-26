//! The player: the character the player controls in the world, spawned where the world says the player starts. It
//! walks, runs and sprints, jumps and double jumps, dodges, and glides; the camera follows it. Nothing moves while the
//! game is paused.

mod camera;
mod glider;
mod input;
mod moves;

use bevy::prelude::*;
use hakuba_characters::Character;
use hakuba_screens::{Pause, Screen};
use hakuba_world::{PushesPlants, Spawn, Unready};

pub use input::Controls;
pub use moves::{Action, Mode};

pub struct PlayerPlugin;

impl Plugin for PlayerPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<Controls>()
            .add_plugins(glider::GliderPlugin)
            .add_systems(Update, (spawn, arrive).run_if(in_state(Screen::World)))
            .add_systems(
                Update,
                (input::read, moves::advance, camera::follow, glider::show).chain().run_if(in_state(Pause::Playing)),
            );
    }
}

/// The player's place in the world: on the ground, between the feet, facing along +Z turned by its rotation. Its
/// [`Body`] is a child.
#[derive(Component)]
pub struct Player {
    /// The character's model.
    pub body: Entity,
    pub camera: camera::Orbit,
    pub motion: moves::Motion,
}

/// The character's model under the [`Player`].
#[derive(Component)]
pub struct Body;

/// Once the world knows where the player starts: spawns the first character there, facing the way the spawn faces,
/// with the camera behind it. The player holds the curtain over the world until they have [arrived](arrive).
fn spawn(mut commands: Commands, start: Option<Res<Spawn>>, players: Query<(), With<Player>>) {
    let Some(start) = start else { return };
    if !players.is_empty() {
        return;
    }
    let ahead = start.0.rotation * Vec3::NEG_Z;
    let yaw = ahead.x.atan2(ahead.z);
    let body =
        commands.spawn((Name::new("Body"), Body, Character::ALL[0], Transform::IDENTITY, Visibility::default())).id();
    let motion = moves::Motion::facing(yaw);
    commands
        .spawn((
            Name::new("Player"),
            DespawnOnExit(Screen::World),
            Player { body, camera: camera::Orbit::behind(yaw), motion },
            Transform::from_translation(start.0.translation).with_rotation(Quat::from_rotation_y(yaw)),
            Visibility::default(),
            Unready,
            PushesPlants::default(),
        ))
        .add_child(body);
}

/// Lifts the player's hold on the curtain once they stand on the ground with their paraglider ready.
fn arrive(mut commands: Commands, players: Query<(Entity, &Player), With<Unready>>, gliders: Query<&glider::Glider>) {
    for (entity, player) in &players {
        if player.motion.mode != Mode::Arriving && gliders.iter().any(|glider| glider.of(player.body)) {
            commands.entity(entity).remove::<Unready>();
        }
    }
}
