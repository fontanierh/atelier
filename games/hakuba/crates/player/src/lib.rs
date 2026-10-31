//! The player: the character the player controls in the world, spawned where the world says the player starts. It
//! walks, runs and sprints, jumps and double jumps, dodges, and glides; the camera follows it. Nothing moves while the
//! game is paused, nor in dev mode, whose camera flies free.

mod camera;
mod glider;
mod input;
mod moves;

use bevy::prelude::*;
use hakuba_characters::Character;
use hakuba_glider::Glider;
use hakuba_screens::{DevMode, Pause, Screen};
use hakuba_world::{Ground, PushesPlants, Spawn, Unready};

pub use input::Controls;
pub use moves::{Action, Mode};

/// Walking systems, ordered so another movement owner can take over before they run.
#[derive(SystemSet, Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum PlayerSystems {
    Input,
    Movement,
    Camera,
}

/// Which controller owns the player's root, camera and pose. External owners must return all three together.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum MovementOwner {
    #[default]
    Walking,
    Skating,
}

pub struct PlayerPlugin;

impl Plugin for PlayerPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<Controls>()
            .add_systems(Update, (spawn, glider::spawn, arrive).run_if(in_state(Screen::World)))
            .add_systems(OnEnter(DevMode::On), hide)
            .add_systems(OnExit(DevMode::On), land_under_camera)
            .add_systems(
                Update,
                (
                    input::read.in_set(PlayerSystems::Input),
                    moves::advance.in_set(PlayerSystems::Movement),
                    glider::steer,
                    camera::follow.in_set(PlayerSystems::Camera),
                )
                    .chain()
                    .run_if(in_state(Pause::Playing))
                    .run_if(in_state(DevMode::Off)),
            );
    }
}

/// The player's place in the world: on the ground, between the feet, facing along +Z turned by its rotation. Its
/// [`Body`] is a child.
#[derive(Component)]
pub struct Player {
    /// The character's model.
    pub body: Entity,
    pub owner: MovementOwner,
    pub camera: camera::Orbit,
    pub motion: moves::Motion,
}

impl Player {
    /// Returns movement and camera ownership, preserving the rider's current place and momentum.
    pub fn resume_walking(&mut self, at: Vec3, yaw: f32, velocity: Vec3, grounded: bool) {
        self.owner = MovementOwner::Walking;
        self.motion = moves::Motion::resuming(at, yaw, velocity, grounded);
        self.camera = camera::Orbit::behind(yaw);
    }
}

/// The character's model under the [`Player`].
#[derive(Component)]
pub struct Body;

/// Once the world knows where the player starts: spawns the first character there, facing the way the spawn faces,
/// with the camera behind it. The player holds the splash over the world until they have [arrived](arrive).
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
            Player { body, owner: MovementOwner::Walking, camera: camera::Orbit::behind(yaw), motion },
            Transform::from_translation(start.0.translation).with_rotation(Quat::from_rotation_y(yaw)),
            Visibility::default(),
            Unready,
            PushesPlants::default(),
        ))
        .add_child(body);
}

/// Lifts the player's hold on the splash once they stand on the ground with their paraglider ready.
fn arrive(mut commands: Commands, players: Query<(Entity, &Player), With<Unready>>, gliders: Query<&Glider>) {
    for (entity, player) in &players {
        if player.motion.mode != Mode::Arriving && gliders.iter().any(|glider| glider.ready_for(player.body)) {
            commands.entity(entity).remove::<Unready>();
        }
    }
}

/// Hides the player while dev mode's camera flies free of them.
fn hide(mut players: Query<&mut Visibility, With<Player>>) {
    for mut visibility in &mut players {
        *visibility = Visibility::Hidden;
    }
}

/// Leaving dev mode, stands the player on whatever is solid under the camera, or where they were if nothing is, facing
/// the way the camera looks, with the camera behind them.
fn land_under_camera(
    mut ground: Ground,
    camera: Single<&Transform, (With<Camera3d>, Without<Player>)>,
    mut players: Query<(&mut Player, &mut Transform, &mut Visibility)>,
) {
    for (mut player, mut transform, mut visibility) in &mut players {
        *visibility = Visibility::Inherited;
        let ahead = camera.forward();
        let yaw = ahead.x.atan2(ahead.z);
        if let Some(hit) = ground.cast(camera.translation, Dir3::NEG_Y, 5000.0) {
            transform.translation = hit.point;
        }
        transform.rotation = Quat::from_rotation_y(yaw);
        player.resume_walking(transform.translation, yaw, Vec3::ZERO, true);
    }
}
