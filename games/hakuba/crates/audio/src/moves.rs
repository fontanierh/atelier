//! The player's sounds: a footstep each time a foot plants, on what it lands on; both feet at
//! once on landing, louder the faster the fall; a burst of air for the double jump, the dodges and the paraglider
//! opening; and rushing air while gliding, rising with the speed.
//!
//! A foot plants when, having swung clear of the ground, it comes back down: the clips need no
//! marks, and every clip, speed and character steps right. A footstep's sound is what the world says the foot landed
//! on.

use bevy::audio::Volume;
use bevy::prelude::*;
use hakuba_player::{Action, Mode, Player};
use hakuba_screens::Pause;
use hakuba_settings::Settings;
use hakuba_world::{Ground, Surface};

use crate::Sounds;
use crate::sound::{Dice, Sound, Takes};

/// The rig's ankle bones, which every character has, left then right.
const FEET: [&str; 2] = ["foot_l", "foot_r"];

/// A foot has swung clear once it is this high above where it rests, and planted again once it comes down to this
/// height, in metres.
const CLEAR_M: f32 = 0.058;
const PLANT_M: f32 = 0.023;

/// The shortest time between two steps of one foot, in seconds.
const STRIDE_S: f32 = 0.1;

/// Slower than this the feet shuffle on the spot and no step sounds, in metres a second.
const STEP_SPEED: f32 = 0.4;

/// How fast where a foot rests rises again after the lowest it has been, in metres a second: the clips move it.
const REST_RISE: f32 = 0.02;

/// A footstep's volume and pitch from a walk to a sprint: from the slower speed to the faster, in metres a second, the
/// volume goes from the first to the second, and the pitch likewise.
const STEP_SPEEDS: (f32, f32) = (0.6, 3.2);
const STEP_VOLUME: (f32, f32) = (0.32, 1.0);
const STEP_PITCH: (f32, f32) = (0.96, 1.06);

/// A landing's volume from how fast the player fell, in metres a second: from the slower fall to the faster, the
/// volume goes from the first to the second, and stays between [`LAND_LOUDNESS`]. Gliding down lands at
/// [`GLIDE_LAND_VOLUME`]. Both land lower than a step, between [`LAND_PITCH`].
const LAND_FALLS: (f32, f32) = (2.0, 11.0);
const LAND_VOLUME: (f32, f32) = (0.55, 1.4);
const LAND_LOUDNESS: (f32, f32) = (0.4, 1.4);
const GLIDE_LAND_VOLUME: f32 = 0.6;
const LAND_PITCH: (f32, f32) = (0.82, 0.9);

/// A jump pushes off with a soft step.
const JUMP_VOLUME: f32 = 0.45;

/// The burst of air: its volume, and how far its pitch strays either way, for the double jump, a dodge, and the
/// paraglider opening.
const DOUBLE_JUMP_DASH: (f32, f32) = (0.5, 0.1);
const DODGE_DASH: (f32, f32) = (0.55, 0.1);
const GLIDE_DASH: (f32, f32) = (0.5, 0.08);

/// The paraglider's wind: from the slower airspeed to the faster, in metres a second, it moves through its takes from
/// the slowest to the fastest, its volume goes from the first to the second and its pitch likewise. It fades in and
/// out over [`WIND_FADE_S`].
const WIND_SPEEDS: (f32, f32) = (2.0, 4.7);
const WIND_VOLUME: (f32, f32) = (0.2, 0.6);
const WIND_PITCH: (f32, f32) = (0.9, 1.1);
const WIND_FADE_S: f32 = 0.3;

/// `low` to `high` as `t` goes from 0 to 1.
fn lerp((low, high): (f32, f32), t: f32) -> f32 {
    low + (high - low) * t
}

/// How far `value` is from `low` to `high`, from 0 to 1.
fn progress(value: f32, (low, high): (f32, f32)) -> f32 {
    ((value - low) / (high - low)).clamp(0.0, 1.0)
}

/// One foot, as the footsteps follow it.
#[derive(Default)]
struct Foot {
    node: Option<Entity>,
    /// Whether it has stepped and not yet swung clear.
    planted: bool,
    /// Its height above the player's feet, last frame.
    height: f32,
    /// The lowest it rests.
    rest: Option<f32>,
    since_step: f32,
}

/// What the sounds last heard of the player.
#[derive(Default)]
pub struct Heard {
    player: Option<Entity>,
    mode: Mode,
    action: Option<Action>,
    /// How fast the player was falling, while in the air, in metres a second.
    fall: f32,
    feet: [Foot; 2],
}

/// What the sounds read of the player.
type Players<'w, 's> = Query<'w, 's, (Entity, &'static Player, &'static GlobalTransform)>;

/// Plays the player's footsteps and the sounds of their moves.
#[allow(clippy::too_many_arguments)]
pub fn hear(
    mut commands: Commands,
    mut heard: Local<Heard>,
    time: Res<Time>,
    pause: Option<Res<State<Pause>>>,
    settings: Res<Settings>,
    mut sounds: ResMut<Sounds>,
    takes: Res<Assets<Takes>>,
    mut dice: ResMut<Dice>,
    mut ground: Ground,
    players: Players,
    children: Query<&Children>,
    nodes: Query<(&Name, &GlobalTransform)>,
) {
    let Ok((entity, player, place)) = players.single() else { return };
    if heard.player != Some(entity) {
        *heard = Heard { player: Some(entity), ..default() };
    }
    if pause.is_some_and(|pause| *pause.get() == Pause::Paused) {
        return;
    }
    if player.owner != hakuba_player::MovementOwner::Walking {
        *heard = Heard { player: Some(entity), ..default() };
        return;
    }
    let motion = &player.motion;
    let at = place.translation();
    let volume = settings.volume;
    let mut out = Out { commands: &mut commands, takes: &takes, dice: &mut dice, volume };

    // The moves' sounds, as each starts.
    let started = heard.action.is_none_or(|was| std::mem::discriminant(&was) != std::mem::discriminant(&motion.action));
    if started {
        match motion.action {
            Action::Jump => {
                let surface = ground.below(at, 0.3, 0.3).map_or(Surface::Ground, |hit| hit.surface);
                let pitch = out.dice.between(STEP_PITCH.0, STEP_PITCH.1);
                out.play(footstep(&mut sounds, surface), JUMP_VOLUME, pitch);
            }
            Action::Flip => out.dash(&mut sounds.dash, DOUBLE_JUMP_DASH),
            Action::Hop(_) | Action::Backflip => out.dash(&mut sounds.dash, DODGE_DASH),
            Action::GlideOpen => out.dash(&mut sounds.dash, GLIDE_DASH),
            _ => {}
        }
    }

    // Landing: both feet at once.
    let landed = motion.mode == Mode::Ground && matches!(heard.mode, Mode::Air | Mode::Glide);
    if landed {
        let loudness = if heard.mode == Mode::Glide {
            GLIDE_LAND_VOLUME
        } else {
            lerp(LAND_VOLUME, progress(heard.fall, LAND_FALLS)).clamp(LAND_LOUDNESS.0, LAND_LOUDNESS.1)
        };
        let surface = ground.below(at, 0.3, 0.3).map_or(Surface::Ground, |hit| hit.surface);
        let pitch = out.dice.between(LAND_PITCH.0, LAND_PITCH.1);
        out.play(footstep(&mut sounds, surface), loudness, pitch);
        for foot in &mut heard.feet {
            foot.planted = true;
            foot.since_step = 0.0;
        }
    }
    heard.fall = if motion.mode == Mode::Air { (-motion.velocity.y).max(0.0) } else { 0.0 };
    heard.mode = motion.mode;
    heard.action = Some(motion.action);

    // Footsteps.
    let speed = motion.velocity.with_y(0.0).length();
    let walking = motion.mode == Mode::Ground && speed >= STEP_SPEED;
    let dt = time.delta_secs();
    for (foot, name) in heard.feet.iter_mut().zip(FEET) {
        if foot.node.is_none_or(|node| !nodes.contains(node)) {
            foot.node = children
                .iter_descendants(player.body)
                .find(|node| nodes.get(*node).is_ok_and(|(n, _)| n.as_str() == name));
        }
        let Some((_, bone)) = foot.node.and_then(|node| nodes.get(node).ok()) else { continue };
        let bone = bone.translation();
        let was = foot.height;
        foot.height = bone.y - at.y;
        foot.since_step += dt;
        if !walking {
            foot.planted = true;
            continue;
        }
        let rest = foot.rest.map_or(foot.height, |rest| (rest + REST_RISE * dt).min(foot.height));
        foot.rest = Some(rest);
        if foot.planted {
            if foot.height > rest + CLEAR_M {
                foot.planted = false;
            }
        } else if foot.height < rest + PLANT_M && foot.height <= was && foot.since_step > STRIDE_S {
            foot.planted = true;
            foot.since_step = 0.0;
            let Some(hit) = ground.below(bone.with_y(at.y), 0.45, 0.5) else { continue };
            let drive = progress(speed, STEP_SPEEDS);
            let loudness = lerp(STEP_VOLUME, drive) * out.dice.between(0.88, 1.0);
            let pitch = lerp(STEP_PITCH, drive) * out.dice.between(0.94, 1.06);
            out.play(footstep(&mut sounds, hit.surface), loudness, pitch);
        }
    }
}

/// The footstep on `surface`, by its material: grass on the ground, gravel on a road, stone on
/// anything built.
fn footstep(sounds: &mut Sounds, surface: Surface) -> &mut Sound {
    match surface {
        Surface::Ground => &mut sounds.grass,
        Surface::Road => &mut sounds.gravel,
        Surface::Built => &mut sounds.stone,
    }
}

/// Where the sounds go.
struct Out<'a, 'w, 's> {
    commands: &'a mut Commands<'w, 's>,
    takes: &'a Assets<Takes>,
    dice: &'a mut Dice,
    /// The settings' volume.
    volume: f32,
}

impl Out<'_, '_, '_> {
    fn play(&mut self, sound: &mut Sound, volume: f32, pitch: f32) {
        sound.play(self.commands, self.takes, self.dice, volume * self.volume, pitch);
    }

    /// The burst of air at its volume, its pitch straying by up to `spread` either way.
    fn dash(&mut self, sound: &mut Sound, (volume, spread): (f32, f32)) {
        let pitch = 1.0 + self.dice.between(-spread, spread);
        self.play(sound, volume, pitch);
    }
}

/// One take of the paraglider's wind, by its place from the slowest.
#[derive(Component)]
pub struct Wind(pub usize);

/// Sets the paraglider's wind as the player glides: louder, higher and through faster takes as they speed up, fading
/// out when they land or the game pauses.
pub fn wind(
    mut level: Local<f32>,
    time: Res<Time>,
    pause: Option<Res<State<Pause>>>,
    settings: Res<Settings>,
    players: Query<&Player>,
    mut takes: Query<(&Wind, &mut AudioSink)>,
) {
    let player = players.single().ok();
    let playing = pause.is_none_or(|pause| *pause.get() == Pause::Playing);
    let gliding = playing
        && player.is_some_and(|player| {
            player.owner == hakuba_player::MovementOwner::Walking && player.motion.mode == Mode::Glide
        });
    let step = time.delta_secs() / WIND_FADE_S;
    *level = if gliding { (*level + step).min(1.0) } else { (*level - step).max(0.0) };
    let speed = player.map_or(0.0, |player| player.motion.velocity.length());
    let t = progress(speed, WIND_SPEEDS);
    let count = takes.iter().count();
    let at = t * count.saturating_sub(1) as f32;
    for (Wind(index), mut sink) in &mut takes {
        // Each take is heard most at its own speed and fades into its neighbours, keeping the power even.
        let share = (1.0 - (at - *index as f32).abs()).max(0.0).sqrt();
        sink.set_volume(Volume::Linear(lerp(WIND_VOLUME, t) * share * *level * settings.volume));
        sink.set_speed(lerp(WIND_PITCH, t));
    }
}
