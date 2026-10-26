//! The moves, as Yorimichi has them, with its numbers: walking, running and sprinting; the jump, and in the air a
//! double jump, a forward somersault, then the paraglider; the dodges, a side hop or a backflip; and the landings, hard
//! from high up. The character is moved here, never by its clips: every clip stays in place, and the ground speed the
//! export measured for each sets how fast its feet step.
//!
//! The player stands on what the world calls solid, follows it up and down steps lower than [`STEP_M`], and is
//! stopped by slopes steeper than [`STEEPEST_DEG`], walls and water deeper than [`WADE_M`]. Falling into deep water puts
//! the player back where they last stood.

use bevy::prelude::*;
use hakuba_characters::{Clips, Play, Playing};
use hakuba_world::{Ground, SEA_LEVEL_M};

use crate::input::Controls;
use crate::{Body, Player};

/// Gravity, in metres a second squared: Unreal's, 1.5 times as strong, as Yorimichi's player falls.
const GRAVITY: f32 = 9.8 * 1.5;

/// How fast a jump leaves the ground, and a double jump the air, in metres a second.
const JUMP_SPEED: f32 = 4.9;
const DOUBLE_JUMP_SPEED: f32 = 6.5;

/// How fast the player speeds up and slows down on foot, in metres a second squared, and how much of that the air
/// allows.
const ACCELERATION: f32 = 20.5;
const AIR_CONTROL: f32 = 0.32;

/// How fast the player turns to face where they move, in radians a second.
const TURN_RATE: f32 = 10.0;

/// A stick tilted less than this walks; further, it runs.
const WALK_TILT: f32 = 0.55;

/// A side hop's speed and height, and a backflip's, from Yorimichi's motion library (SideStep and BackJump).
const HOP_SPEED: f32 = 0.18 * 30.0;
const HOP_HEIGHT: f32 = 0.8;
const BACKFLIP_SPEED: f32 = 0.15 * 30.0;
const BACKFLIP_HEIGHT: f32 = 1.11;

/// The double jump's somersault: when the turn starts, how long it takes, and when the body is upright again, in
/// seconds after the jump, as Yorimichi times Cairo's.
const FLIP_START: f32 = 0.08;
const FLIP_TURN: f32 = 0.52;
const FLIP_DONE: f32 = 0.63;

/// How long after leaving the ground a jump still counts as from the ground, and the double jump waits after walking
/// off an edge, in seconds.
const COYOTE_TIME: f32 = 0.12;
const DOUBLE_JUMP_AFTER_EDGE: f32 = 0.10;

/// The paraglider opens only this long after leaving the ground, in seconds, and this high above it, in metres.
const GLIDE_AFTER: f32 = 0.15;
const GLIDE_CLEARANCE_M: f32 = 0.4;

/// Gliding: its speed with the stick at rest, pushed ahead and pulled back, how fast it sinks, all in metres a second,
/// and how fast it turns toward the stick, in radians a second.
const GLIDE_SPEED: f32 = 2.4;
const GLIDE_FAST: f32 = 4.5;
const GLIDE_BRAKE: f32 = 1.3;
const GLIDE_SINK: f32 = 1.5;
const GLIDE_TURN: f32 = 140.0 * std::f32::consts::PI / 180.0;

/// The highest step the player walks up or down without falling, in metres.
const STEP_M: f32 = 0.45;

/// The steepest ground the player walks up.
const STEEPEST_DEG: f32 = 50.0;

/// How deep the player wades into the sea, in metres.
const WADE_M: f32 = 0.6;

/// The player's body, as walls see it: how far from its middle it keeps them, and the heights above the feet it
/// checks for them, in metres, from the ankles to the head: a guardrail's beam stops even a hop.
const RADIUS_M: f32 = 0.3;
const WALL_CHECKS_M: [f32; 5] = [0.15, 0.45, 0.8, 1.2, 1.6];

/// A fall from higher than this lands hard, in metres.
const HARD_LAND_M: f32 = 4.5;

/// Landing faster than this over the ground runs on, in metres a second.
const RUN_LAND_SPEED: f32 = 2.5;

/// How fast the player keeps moving, at most, when the paraglider lands, in metres a second.
const GLIDE_LAND_SPEED: f32 = 2.0;

/// How far below the sea the player can fall before being put back, in metres: a world with no ground there.
const LOST_M: f32 = 50.0;

/// What the player is standing on, if anything.
#[derive(Clone, Copy, PartialEq, Debug, Default)]
pub enum Mode {
    /// Not on the ground yet: the world is loading under the player.
    #[default]
    Arriving,
    Ground,
    Air,
    Glide,
}

/// The move the player is in the middle of, which has a clip of its own.
#[derive(Clone, Copy, PartialEq, Debug, Default)]
pub enum Action {
    /// Moving freely: the clip follows how fast the player moves, or how they fall or glide.
    #[default]
    Free,
    Jump,
    Hop(Side),
    Backflip,
    /// The double jump's somersault, how long since it started, in seconds, and the point it turns about, in the
    /// player's frame, once known.
    Flip(f32, Option<Vec3>),
    Land,
    HopLand(Side),
    BackflipLand,
    HardLand,
    HardLandUp,
    GlideOpen,
    GlideClose,
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Side {
    Left,
    Right,
}

impl Action {
    /// Whether the player stands where they are until the clip ends.
    fn holds(self) -> bool {
        matches!(
            self,
            Action::HopLand(_) | Action::BackflipLand | Action::HardLand | Action::HardLandUp | Action::GlideClose
        )
    }
}

/// How the player moves: what they stand on, what they are doing, and how they got there.
#[derive(Default)]
pub struct Motion {
    pub mode: Mode,
    pub action: Action,
    pub velocity: Vec3,
    /// Which way the player faces, in radians about up, from +Z toward +X.
    pub yaw: f32,
    /// Seconds since the player last stood on the ground.
    since_ground: f32,
    jumped: bool,
    double_jumped: bool,
    /// The height a fall started from.
    fall_from: f32,
    /// A hop's or backflip's speed over the ground, which the stick does not steer.
    leap: Option<Vec3>,
    glide_yaw: f32,
    glide_speed: f32,
    glide_turn: f32,
    /// Whether the player pulls the stick back while gliding.
    braking: bool,
    /// The last place the player stood on dry ground.
    safe: Vec3,
}

impl Motion {
    /// Arriving, facing `yaw`.
    pub fn facing(yaw: f32) -> Self {
        Self { yaw, ..default() }
    }
}

/// The way the camera looks over the ground: turned `camera_yaw` from +Z toward +X, looking along -Z when 0.
fn wish(controls: &Controls, camera_yaw: f32) -> Vec3 {
    let forward = Vec3::new(-camera_yaw.sin(), 0.0, -camera_yaw.cos());
    let right = Vec3::new(camera_yaw.cos(), 0.0, -camera_yaw.sin());
    forward * controls.stick.y + right * controls.stick.x
}

/// The yaw facing along `direction` over the ground.
fn yaw_of(direction: Vec3) -> f32 {
    direction.x.atan2(direction.z)
}

/// `from` turned toward `to` by at most `step` radians, the short way round.
fn turn_toward(from: f32, to: f32, step: f32) -> f32 {
    let delta = (to - from + std::f32::consts::PI).rem_euclid(std::f32::consts::TAU) - std::f32::consts::PI;
    from + delta.clamp(-step, step)
}

/// The speed the stick asks for, given the character's walking, running and sprinting speeds.
fn wanted_speed(controls: &Controls, clips: &Clips) -> f32 {
    let tilt = controls.stick.length().min(1.0);
    if tilt < 0.01 {
        0.0
    } else if controls.sprint {
        clips.speed("sprint")
    } else if controls.walk || tilt < WALK_TILT {
        clips.speed("walk") * (tilt / WALK_TILT).min(1.0)
    } else {
        clips.speed("run")
    }
}

/// What the moves read of the player's body, and its place.
type BodyParts = (Entity, &'static Clips, &'static Playing, &'static mut Transform);

/// Moves the player one frame.
#[allow(clippy::too_many_arguments)]
pub fn advance(
    mut commands: Commands,
    controls: Res<Controls>,
    time: Res<Time>,
    mut ground: Ground,
    mut players: Query<(&mut Player, &mut Transform)>,
    mut bodies: Query<BodyParts, (With<Body>, Without<Player>)>,
    pelvises: Query<(&Name, &GlobalTransform)>,
    children: Query<&Children>,
) {
    let dt = time.delta_secs();
    if dt <= 0.0 {
        return;
    }
    for (mut player, mut transform) in &mut players {
        let Ok((body, clips, playing, mut body_transform)) = bodies.get_mut(player.body) else { continue };
        let camera_yaw = player.camera.yaw;
        let motion = &mut player.motion;
        let wish = wish(&controls, camera_yaw);
        let mut at = transform.translation;
        let play = |commands: &mut Commands, play: Play| commands.trigger(play);

        match motion.mode {
            Mode::Arriving => {
                if let Some(hit) = ground.below(at, 2.0, 50.0) {
                    at.y = hit.point.y;
                    motion.mode = Mode::Ground;
                    motion.safe = at;
                }
            }
            Mode::Ground => {
                motion.since_ground = 0.0;
                if motion.action.holds() {
                    if playing.finished {
                        motion.action = match motion.action {
                            Action::HardLand => {
                                play(&mut commands, Play::once(body, "hard-land-up").fading(0.1));
                                Action::HardLandUp
                            }
                            _ => Action::Free,
                        };
                    }
                } else if controls.jump {
                    jump(&mut commands, motion, body, clips);
                } else if controls.dodge {
                    dodge(&mut commands, motion, body, &controls, camera_yaw);
                }
                if motion.mode == Mode::Ground {
                    let held = motion.action.holds();
                    let target =
                        if held { Vec3::ZERO } else { wish.normalize_or_zero() * wanted_speed(&controls, clips) };
                    let flat = motion.velocity.with_y(0.0);
                    motion.velocity = flat.move_towards(target, ACCELERATION * dt);
                    if !held && wish.length() > 0.05 {
                        motion.yaw = turn_toward(motion.yaw, yaw_of(wish), TURN_RATE * dt);
                    }
                    at = walk(&mut ground, motion, at, dt);
                    if motion.mode == Mode::Ground && at.y > SEA_LEVEL_M {
                        motion.safe = at;
                    }
                }
            }
            Mode::Air => {
                motion.since_ground += dt;
                if controls.jump && can_jump(motion) {
                    jump(&mut commands, motion, body, clips);
                } else if controls.jump && can_double_jump(motion) {
                    double_jump(&mut commands, motion, body, wish);
                } else if controls.jump && can_glide(motion, &mut ground, at) {
                    open_glider(&mut commands, motion, body);
                }
                if motion.mode == Mode::Air {
                    fly(&mut commands, &mut ground, motion, body, clips, &controls, wish, &mut at, dt);
                }
            }
            Mode::Glide => {
                if controls.jump {
                    // Letting go of the paraglider: falling on.
                    motion.mode = Mode::Air;
                    motion.action = Action::Free;
                    motion.fall_from = at.y;
                    motion.since_ground = motion.since_ground.max(GLIDE_AFTER);
                    play(&mut commands, Play::once(body, "fall").fading(0.25));
                } else {
                    glide(&mut commands, &mut ground, motion, body, wish, &mut at, dt);
                }
            }
        }

        // Fell where there is nothing to stand on, or into deep water: back to the last dry ground.
        if at.y < SEA_LEVEL_M - LOST_M || (motion.mode != Mode::Ground && at.y < SEA_LEVEL_M - WADE_M) {
            at = motion.safe;
            *motion = Motion { mode: Mode::Ground, yaw: motion.yaw, safe: motion.safe, ..default() };
            play(&mut commands, Play::looping(body, "idle"));
        }

        transform.translation = at;
        transform.rotation = Quat::from_rotation_y(motion.yaw);
        animate(&mut commands, motion, body, clips, playing);
        *body_transform = flip(motion, dt, body, &children, &pelvises, &transform);
    }
}

/// Walks the player from `at` by their velocity over one frame of `dt` seconds, on the ground or off its edge, and
/// returns where they end up.
fn walk(ground: &mut Ground, motion: &mut Motion, at: Vec3, dt: f32) -> Vec3 {
    let step = motion.velocity.with_y(0.0) * dt;
    if step.length() < 1e-5 {
        return at;
    }
    if blocked(ground, at, step) {
        motion.velocity = Vec3::ZERO;
        return at;
    }
    let next = at + step;
    match ground.below(next, STEP_M, STEP_M) {
        Some(hit) => {
            let steep = hit.normal.y < STEEPEST_DEG.to_radians().cos() && hit.point.y > at.y;
            let deep = hit.point.y < SEA_LEVEL_M - WADE_M;
            if steep || deep {
                motion.velocity = Vec3::ZERO;
                at
            } else {
                next.with_y(hit.point.y)
            }
        }
        None => {
            // Off an edge: falling.
            motion.mode = Mode::Air;
            motion.velocity.y = 0.0;
            motion.fall_from = at.y;
            next
        }
    }
}

/// Whether a wall, rail or slope too steep to climb stands in the way of moving the player by `step` from `at`.
fn blocked(ground: &mut Ground, at: Vec3, step: Vec3) -> bool {
    let Ok(direction) = Dir3::new(step) else { return false };
    WALL_CHECKS_M.into_iter().any(|height| {
        ground
            .cast(at + Vec3::Y * height, direction, step.length() + RADIUS_M)
            .is_some_and(|hit| hit.normal.y < STEEPEST_DEG.to_radians().cos())
    })
}

fn can_jump(motion: &Motion) -> bool {
    motion.mode == Mode::Ground || (!motion.jumped && motion.since_ground < COYOTE_TIME)
}

fn can_double_jump(motion: &Motion) -> bool {
    motion.mode == Mode::Air
        && !motion.double_jumped
        && (motion.jumped || motion.since_ground >= DOUBLE_JUMP_AFTER_EDGE)
        && matches!(motion.action, Action::Free | Action::Jump)
}

fn can_glide(motion: &Motion, ground: &mut Ground, at: Vec3) -> bool {
    motion.mode == Mode::Air
        && motion.since_ground >= GLIDE_AFTER
        && !matches!(motion.action, Action::Hop(_) | Action::Backflip)
        && ground.below(at, 0.0, GLIDE_CLEARANCE_M).is_none()
}

fn jump(commands: &mut Commands, motion: &mut Motion, body: Entity, clips: &Clips) {
    let speed = motion.velocity.with_y(0.0).length();
    motion.velocity.y = JUMP_SPEED;
    motion.mode = Mode::Air;
    motion.action = Action::Jump;
    motion.jumped = true;
    motion.leap = None;
    motion.fall_from = f32::NEG_INFINITY;
    let clip = if speed > RUN_LAND_SPEED && clips.names().any(|name| name == "run-jump") { "run-jump" } else { "jump" };
    commands.trigger(Play::once(body, clip).fading(0.08));
}

/// A fresh launch upward, the speed over the ground turned toward the stick (the stick at rest keeps the heading), and
/// one forward somersault.
fn double_jump(commands: &mut Commands, motion: &mut Motion, body: Entity, wish: Vec3) {
    let flat = motion.velocity.with_y(0.0);
    let mut velocity = flat;
    if wish.length() > 0.1 {
        velocity = wish.normalize() * flat.length();
        motion.yaw = yaw_of(wish);
    }
    motion.velocity = velocity.with_y(DOUBLE_JUMP_SPEED);
    motion.double_jumped = true;
    motion.jumped = true;
    motion.leap = None;
    motion.fall_from = f32::NEG_INFINITY;
    motion.action = Action::Flip(0.0, None);
    commands.trigger(Play::once(body, "tuck").fading(0.08));
}

/// A side hop when the stick points to the side of the camera, a backflip otherwise. The player first turns to face
/// the way the camera looks.
fn dodge(commands: &mut Commands, motion: &mut Motion, body: Entity, controls: &Controls, camera_yaw: f32) {
    motion.yaw = camera_yaw + std::f32::consts::PI;
    let facing = Vec3::new(motion.yaw.sin(), 0.0, motion.yaw.cos());
    let left = Vec3::new(facing.z, 0.0, -facing.x);
    let stick = controls.stick;
    let side = stick.x.abs() > 0.3 && stick.x.abs() >= stick.y.abs();
    let (velocity, height, action, clip) = if side {
        let (direction, side, clip) =
            if stick.x < 0.0 { (left, Side::Left, "hop-left") } else { (-left, Side::Right, "hop-right") };
        (direction * HOP_SPEED, HOP_HEIGHT, Action::Hop(side), clip)
    } else {
        (-facing * BACKFLIP_SPEED, BACKFLIP_HEIGHT, Action::Backflip, "backflip")
    };
    motion.velocity = velocity.with_y((2.0 * GRAVITY * height).sqrt());
    motion.leap = Some(velocity);
    motion.mode = Mode::Air;
    motion.action = action;
    motion.jumped = true;
    motion.fall_from = f32::NEG_INFINITY;
    commands.trigger(Play::once(body, clip).fading(0.05));
}

fn open_glider(commands: &mut Commands, motion: &mut Motion, body: Entity) {
    let facing = Vec3::new(motion.yaw.sin(), 0.0, motion.yaw.cos());
    motion.glide_yaw = motion.yaw;
    motion.glide_speed = motion.velocity.dot(facing).max(0.0);
    motion.glide_turn = 0.0;
    let falling_fast = motion.velocity.y < -5.0;
    motion.mode = Mode::Glide;
    motion.action = Action::GlideOpen;
    motion.leap = None;
    let clip = if falling_fast { "glide-open-falling" } else { "glide-open" };
    commands.trigger(Play::once(body, clip).fading(0.1));
}

/// One frame in the air: gravity, a little steering, and landing.
#[allow(clippy::too_many_arguments)]
fn fly(
    commands: &mut Commands,
    ground: &mut Ground,
    motion: &mut Motion,
    body: Entity,
    clips: &Clips,
    controls: &Controls,
    wish: Vec3,
    at: &mut Vec3,
    dt: f32,
) {
    if motion.velocity.y <= 0.0 && motion.fall_from == f32::NEG_INFINITY {
        motion.fall_from = at.y;
    }
    motion.velocity.y -= GRAVITY * dt;
    if let Some(leap) = motion.leap {
        motion.velocity = leap.with_y(motion.velocity.y);
    } else {
        let flat = motion.velocity.with_y(0.0);
        let target = wish.normalize_or_zero() * wanted_speed(controls, clips).max(flat.length());
        let steered = flat.move_towards(target, ACCELERATION * AIR_CONTROL * dt);
        motion.velocity = steered.with_y(motion.velocity.y);
        if wish.length() > 0.05 && !matches!(motion.action, Action::Flip(..)) {
            motion.yaw = turn_toward(motion.yaw, yaw_of(wish), TURN_RATE * AIR_CONTROL * dt);
        }
    }
    let step = motion.velocity * dt;
    let flat = step.with_y(0.0);
    let mut next = *at + step;
    if blocked(ground, *at, flat) {
        next = *at + Vec3::Y * step.y;
        motion.velocity = Vec3::new(0.0, motion.velocity.y, 0.0);
        if let Some(leap) = motion.leap.as_mut() {
            *leap = Vec3::ZERO;
        }
    }
    if motion.velocity.y <= 0.0
        && let Some(hit) = ground.below(next.with_y(at.y), 0.3, at.y - next.y)
    {
        next.y = hit.point.y;
        *at = next;
        land(commands, motion, body, *at);
        return;
    }
    *at = next;
}

/// Lands the player from the air at `at`.
fn land(commands: &mut Commands, motion: &mut Motion, body: Entity, at: Vec3) {
    let height = motion.fall_from - at.y;
    let speed = motion.velocity.with_y(0.0).length();
    motion.mode = Mode::Ground;
    motion.jumped = false;
    motion.double_jumped = false;
    motion.velocity.y = 0.0;
    let (action, clip, fade) = match motion.action {
        Action::Hop(side) => {
            motion.velocity *= 0.2;
            (Action::HopLand(side), if side == Side::Left { "hop-left-land" } else { "hop-right-land" }, 0.05)
        }
        Action::Backflip => {
            motion.velocity *= 0.2;
            (Action::BackflipLand, "backflip-land", 0.05)
        }
        _ if height > HARD_LAND_M => {
            motion.velocity = Vec3::ZERO;
            (Action::HardLand, "hard-land", 0.05)
        }
        _ if speed > RUN_LAND_SPEED => (Action::Land, "run-land", 0.06),
        _ => (Action::Land, "land", 0.06),
    };
    motion.leap = None;
    motion.action = action;
    commands.trigger(Play::once(body, clip).fading(fade));
}

/// One frame under the paraglider: it turns toward the stick, speeds up when it pushes ahead and slows when it pulls
/// back, and sinks steadily, until it lands.
fn glide(
    commands: &mut Commands,
    ground: &mut Ground,
    motion: &mut Motion,
    body: Entity,
    wish: Vec3,
    at: &mut Vec3,
    dt: f32,
) {
    let push = wish.length().min(1.0);
    let mut turn = 0.0;
    let mut target = GLIDE_SPEED;
    motion.braking = false;
    if push > 0.15 {
        let delta = turn_toward(0.0, yaw_of(wish) - motion.glide_yaw, std::f32::consts::PI);
        if delta.abs() > 150f32.to_radians() {
            motion.braking = true;
            target = GLIDE_BRAKE;
        } else {
            turn = (delta * 3.0).clamp(-GLIDE_TURN, GLIDE_TURN) * push;
            target = GLIDE_SPEED + (GLIDE_FAST - GLIDE_SPEED) * push * delta.cos().max(0.0);
        }
    }
    motion.glide_turn += (turn - motion.glide_turn) * (6.0 * dt).min(1.0);
    motion.glide_yaw += motion.glide_turn * dt;
    motion.glide_speed += (target - motion.glide_speed) * (1.2 * dt).min(1.0);
    let sink = -GLIDE_SINK;
    let rate = if motion.velocity.y < sink { 4.0 } else { 2.0 };
    motion.velocity.y += (sink - motion.velocity.y) * (rate * dt).min(1.0);
    motion.yaw = motion.glide_yaw;
    let facing = Vec3::new(motion.glide_yaw.sin(), 0.0, motion.glide_yaw.cos());
    motion.velocity = (facing * motion.glide_speed).with_y(motion.velocity.y);
    let step = motion.velocity * dt;
    let mut next = *at + step;
    if blocked(ground, *at, step.with_y(0.0)) {
        next = *at + Vec3::Y * step.y;
        motion.glide_speed *= 0.3;
    }
    if let Some(hit) = ground.below(next.with_y(at.y), 0.3, at.y - next.y + 0.06) {
        next.y = hit.point.y;
        *at = next;
        motion.mode = Mode::Ground;
        motion.action = Action::GlideClose;
        motion.jumped = false;
        motion.double_jumped = false;
        motion.velocity = motion.velocity.with_y(0.0).clamp_length_max(GLIDE_LAND_SPEED);
        commands.trigger(Play::once(body, "glide-close").fading(0.1));
        return;
    }
    *at = next;
}

/// Plays the clip for how the player moves, when no move of their own is playing.
fn animate(commands: &mut Commands, motion: &mut Motion, body: Entity, clips: &Clips, playing: &Playing) {
    match (motion.mode, motion.action) {
        (Mode::Arriving, _) => {}
        (Mode::Ground, Action::Land) if playing.finished => motion.action = Action::Free,
        (Mode::Ground, Action::Free) | (Mode::Ground, Action::Land) => {
            let speed = motion.velocity.with_y(0.0).length();
            let moving = speed > 0.15;
            if motion.action == Action::Land && !moving {
                return;
            }
            motion.action = Action::Free;
            let (walk, run, sprint) = (clips.speed("walk"), clips.speed("run"), clips.speed("sprint"));
            let (clip, rate) = if !moving {
                ("idle", 1.0)
            } else if speed < walk * 1.4 {
                ("walk", (speed / walk).max(0.6))
            } else if speed < (run + sprint) / 2.0 {
                ("run", (speed / run).clamp(0.6, 1.3))
            } else {
                ("sprint", (speed / sprint).clamp(0.6, 1.3))
            };
            commands.trigger(Play::looping(body, clip).fading(0.2).at_speed(rate));
        }
        (Mode::Air, Action::Free) if playing.clip != "fall" && motion.since_ground > GLIDE_AFTER => {
            commands.trigger(Play::once(body, "fall").fading(0.2));
        }
        (Mode::Air, Action::Jump) if playing.finished && motion.velocity.y < 0.0 => {
            motion.action = Action::Free;
            commands.trigger(Play::once(body, "fall").fading(0.2));
        }
        (Mode::Glide, Action::GlideOpen) if playing.finished => motion.action = Action::Free,
        (Mode::Glide, Action::Free) => {
            let clip = if motion.glide_turn.abs() > 40f32.to_radians() {
                if motion.glide_turn > 0.0 { "glide-left" } else { "glide-right" }
            } else if motion.braking {
                "glide-back"
            } else if motion.glide_speed > GLIDE_SPEED + 0.5 {
                "glide-forward"
            } else {
                "glide"
            };
            commands.trigger(Play::looping(body, clip).fading(0.3));
        }
        _ => {}
    }
}

/// The body's place in the player's frame: upright, or turning through the double jump's somersault about the middle
/// of the tucked body.
fn flip(
    motion: &mut Motion,
    dt: f32,
    body: Entity,
    children: &Query<&Children>,
    pelvises: &Query<(&Name, &GlobalTransform)>,
    player: &Transform,
) -> Transform {
    let Action::Flip(time, pivot) = &mut motion.action else { return Transform::IDENTITY };
    *time += dt;
    if motion.mode != Mode::Air {
        return Transform::IDENTITY;
    }
    if pivot.is_none() && *time >= FLIP_START {
        let pelvis = children
            .iter_descendants(body)
            .find_map(|node| pelvises.get(node).ok().filter(|(name, _)| name.as_str() == "pelvis"));
        let at = pelvis
            .map_or(Vec3::Y, |(_, global)| player.compute_affine().inverse().transform_point3(global.translation()));
        *pivot = Some(at + Vec3::Y * 0.08);
    }
    if *time >= FLIP_DONE {
        motion.action = Action::Free;
        return Transform::IDENTITY;
    }
    let Some(pivot) = *pivot else { return Transform::IDENTITY };
    let t = ((*time - FLIP_START) / FLIP_TURN).clamp(0.0, 1.0);
    let angle = std::f32::consts::TAU * t * t * (3.0 - 2.0 * t);
    let turn = Quat::from_rotation_x(angle);
    Transform::from_translation(pivot - turn * pivot).with_rotation(turn)
}
