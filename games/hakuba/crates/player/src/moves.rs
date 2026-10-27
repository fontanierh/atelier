//! The moves: walking, running and sprinting; the jump, and in the air a
//! double jump, a forward somersault, then the paraglider; the dodges, a side hop or a backflip; and the landings, hard
//! from high up. The character is moved here, never by its clips: every clip stays in place, and the ground speed the
//! export measured for each sets how fast its feet step.
//!
//! The player stands on what the world calls solid, follows it up and down steps lower than [`STEP_M`], and is
//! stopped by slopes steeper than [`STEEPEST_DEG`], walls and water deeper than [`WADE_M`]. Falling into deep water puts
//! the player back where they last stood.

use bevy::prelude::*;
use hakuba_characters::{Clips, Play, Playing};
use hakuba_world::{Ground, Hit, SEA_LEVEL_M};

use crate::input::Controls;
use crate::{Body, Player};

/// Gravity, in metres a second squared: 1.5 times the Earth's, so falls feel quick.
const GRAVITY: f32 = 9.8 * 1.5;

/// How fast a jump leaves the ground, and a double jump the air, in metres a second: a double jump
/// rises 2.2 m.
const JUMP_SPEED: f32 = 4.9;
const DOUBLE_JUMP_SPEED: f32 = 8.0;

/// How fast the player speeds up and slows down on foot, in metres a second squared, and how much of that the air
/// allows.
const ACCELERATION: f32 = 20.5;
const AIR_CONTROL: f32 = 0.32;

/// How fast the player turns to face where they move, in radians a second.
const TURN_RATE: f32 = 10.0;

/// A stick tilted less than this walks; further, it runs.
const WALK_TILT: f32 = 0.55;

/// A side hop's speed and height, and a backflip's, as the motion library's side step and back jump move.
const HOP_SPEED: f32 = 0.18 * 30.0;
const HOP_HEIGHT: f32 = 0.8;
const BACKFLIP_SPEED: f32 = 0.15 * 30.0;
const BACKFLIP_HEIGHT: f32 = 1.11;

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
/// A capsule containing the existing 0.3 m radius at every checked height, including the 1.6 m head ray.
const BODY_HEIGHT_M: f32 = WALL_CHECKS_M[4] + RADIUS_M;
const STEP_CLEARANCE_M: f32 = 0.002;

/// A checked step is crossed over several frames; its original foot position remains the cancellation point.
#[derive(Clone, Copy)]
struct StepCrossing {
    direction: Vec3,
    rise: f32,
    distance: f32,
    progress: f32,
    returning: bool,
}

/// How far the body is pushed out of a wall in one frame, at most, in metres.
const MOST_PUSH_M: f32 = 0.02;

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
    /// The double jump's somersault, until its clip ends.
    Flip,
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
    step_crossing: Option<StepCrossing>,
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

    /// How fast the paraglider turns, in radians a second toward the left: 0 off it.
    pub fn glide_turn(&self) -> f32 {
        if self.mode == Mode::Glide { self.glide_turn } else { 0.0 }
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

/// Moves the player one frame.
#[allow(clippy::too_many_arguments)]
pub fn advance(
    mut commands: Commands,
    controls: Res<Controls>,
    time: Res<Time>,
    mut ground: Ground,
    mut players: Query<(&mut Player, &mut Transform)>,
    bodies: Query<(Entity, &Clips, &Playing), With<Body>>,
) {
    let dt = time.delta_secs();
    if dt <= 0.0 {
        return;
    }
    for (mut player, mut transform) in &mut players {
        let Ok((body, clips, playing)) = bodies.get(player.body) else { continue };
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
                    if leave_step_for_air(&ground, motion, at, JUMP_SPEED * JUMP_SPEED / (2.0 * GRAVITY)) {
                        jump(&mut commands, motion, body, clips);
                    }
                } else if controls.dodge {
                    let height = if is_side_dodge(&controls) { HOP_HEIGHT } else { BACKFLIP_HEIGHT };
                    if leave_step_for_air(&ground, motion, at, height) {
                        dodge(&mut commands, motion, body, &controls, camera_yaw);
                    }
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
                    at = walk(&mut ground, motion, at, wish, dt);
                    if motion.mode == Mode::Ground && motion.step_crossing.is_none() && at.y > SEA_LEVEL_M {
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
    }
}

trait WalkingGround {
    fn cast(&mut self, from: Vec3, direction: Dir3, reach: f32) -> Option<Hit>;
    fn below(&mut self, at: Vec3, above: f32, below: f32) -> Option<Hit>;
    fn sweep_capsule(&self, feet: Vec3, radius: f32, height: f32, delta: Vec3) -> Result<Option<Hit>, &'static str>;
}

impl WalkingGround for Ground<'_, '_> {
    fn cast(&mut self, from: Vec3, direction: Dir3, reach: f32) -> Option<Hit> {
        Ground::cast(self, from, direction, reach)
    }
    fn below(&mut self, at: Vec3, above: f32, below: f32) -> Option<Hit> {
        Ground::below(self, at, above, below)
    }
    fn sweep_capsule(&self, feet: Vec3, radius: f32, height: f32, delta: Vec3) -> Result<Option<Hit>, &'static str> {
        Ground::sweep_capsule(self, feet, radius, height, delta)
    }
}

/// Leaving a checked crossing for an air action must have room to rise to its usual height.
fn leave_step_for_air(ground: &impl WalkingGround, motion: &mut Motion, at: Vec3, height: f32) -> bool {
    if motion.step_crossing.is_none() {
        return true;
    }
    if !matches!(ground.sweep_capsule(at, RADIUS_M, BODY_HEIGHT_M, Vec3::Y * height), Ok(None)) {
        return false;
    }
    motion.step_crossing = None;
    true
}

/// Walks the player from `at` by their velocity over one frame of `dt` seconds, on the ground or off its edge, and
/// returns where they end up.
fn walk(ground: &mut impl WalkingGround, motion: &mut Motion, at: Vec3, intent: Vec3, dt: f32) -> Vec3 {
    let step = motion.velocity.with_y(0.0) * dt;
    if let Some(crossing) = motion.step_crossing {
        return advance_step(ground, motion, crossing, at, step, intent, dt);
    }
    if step.length() < 1e-5 {
        return at;
    }
    let (moved, push) = slide(ground, at, step);
    if intent.length_squared() >= 0.0025
        && intent.dot(step) > 0.00001
        && moved.length_squared() + 1e-8 < step.length_squared()
        && let Some(crossing) = prepare_step(ground, at, step)
    {
        let raised = at + Vec3::Y * crossing.rise;
        motion.step_crossing = Some(crossing);
        return advance_step(ground, motion, crossing, raised, step, intent, dt);
    }
    motion.velocity = moved / dt;
    let next = at + moved + push;
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

/// Checks the complete lift and approach before entering a step, without moving the character ahead.
fn prepare_step(ground: &mut impl WalkingGround, at: Vec3, step: Vec3) -> Option<StepCrossing> {
    let direction = step.with_y(0.0).normalize_or_zero();
    if direction == Vec3::ZERO {
        return None;
    }
    let distance = RADIUS_M + 0.05;
    let landing = at + direction * distance;
    let across = Vec3::new(-direction.z, 0.0, direction.x) * (RADIUS_M * 0.65);
    let support = ground.below(landing, STEP_M, STEP_M)?;
    let rise = support.point.y - at.y;
    if !(0.001..=STEP_M).contains(&rise) || support.normal.y < STEEPEST_DEG.to_radians().cos() {
        return None;
    }
    for point in [landing + across, landing - across, landing + direction * (RADIUS_M * 0.5)] {
        let side = ground.below(point, STEP_M, STEP_M)?;
        if (side.point.y - support.point.y).abs() > 0.01 || side.normal.y < STEEPEST_DEG.to_radians().cos() {
            return None;
        }
    }
    // Reject a sustained steep ramp: its slope cannot become walkable by repeatedly starting short steps.
    let mut steep_samples = 0;
    for k in 1..=7 {
        let point = at + direction * (distance * k as f32 / 7.0);
        let hit = ground.below(point, STEP_M, STEP_M)?;
        if hit.point.y > at.y + 0.001 && hit.normal.y < STEEPEST_DEG.to_radians().cos() {
            steep_samples += 1;
            if steep_samples >= 2 {
                return None;
            }
        } else {
            steep_samples = 0;
        }
    }
    let lift = rise + STEP_CLEARANCE_M;
    let clear = |from, delta| matches!(ground.sweep_capsule(from, RADIUS_M, BODY_HEIGHT_M, delta), Ok(None));
    if !clear(at, Vec3::Y * lift) || !clear(at + Vec3::Y * lift, direction * distance) {
        return None;
    }
    Some(StepCrossing { direction, rise: lift, distance, progress: 0.0, returning: false })
}

/// Settles only when the centre is supported and the capsule can descend to that same surface.
fn settle_step(ground: &mut impl WalkingGround, at: Vec3) -> Option<Vec3> {
    let support = ground.below(at, STEP_M, STEP_M + STEP_CLEARANCE_M)?;
    let drop = at.y - support.point.y;
    if !(0.0..=STEP_M + STEP_CLEARANCE_M).contains(&drop) || support.normal.y < STEEPEST_DEG.to_radians().cos() {
        return None;
    }
    if drop <= 1e-6
        || match ground.sweep_capsule(at, RADIUS_M, BODY_HEIGHT_M, Vec3::NEG_Y * drop) {
            Ok(None) => true,
            Ok(Some(hit)) => (hit.distance - drop).abs() <= STEP_CLEARANCE_M,
            Err(_) => false,
        }
    {
        return Some(at.with_y(support.point.y));
    }
    None
}

/// Advances only by the requested frame's travel, or retraces the swept route if input is cancelled.
fn advance_step(
    ground: &mut impl WalkingGround,
    motion: &mut Motion,
    mut crossing: StepCrossing,
    at: Vec3,
    step: Vec3,
    intent: Vec3,
    dt: f32,
) -> Vec3 {
    let cancel = intent.length_squared() < 0.0025 || intent.dot(crossing.direction) <= 0.00001;
    if cancel {
        let forward_speed = motion.velocity.dot(crossing.direction).max(0.0);
        motion.velocity -= crossing.direction * forward_speed;
    }
    if intent.length_squared() >= 0.0025 && intent.dot(crossing.direction) <= 0.00001 {
        if let Some(settled) = settle_step(ground, at) {
            motion.step_crossing = None;
            return settled;
        }
        crossing.returning = true;
    }
    if intent.length_squared() < 0.0025 {
        if let Some(settled) = settle_step(ground, at) {
            motion.step_crossing = None;
            return settled;
        }
        // A ledge may prevent a vertical drop before the centre is supported. Retrace the already swept path
        // slowly, rather than leaving the player suspended or pushing them forward without input.
        crossing.returning = true;
    }
    let amount = if crossing.returning {
        let speed = if intent.length_squared() < 0.0025 { 0.5 * dt } else { step.length() };
        -speed.min(crossing.progress)
    } else {
        step.dot(crossing.direction).max(0.0).min(crossing.distance - crossing.progress)
    };
    let delta = crossing.direction * amount;
    if !matches!(ground.sweep_capsule(at, RADIUS_M, BODY_HEIGHT_M, delta), Ok(None)) {
        motion.velocity = Vec3::ZERO;
        motion.step_crossing = Some(crossing);
        return at;
    }
    let next = at + delta;
    crossing.progress += amount;
    let finished = if crossing.returning {
        crossing.progress <= 0.00001
    } else {
        crossing.progress >= crossing.distance - 0.00001
    };
    if finished {
        if let Some(settled) = settle_step(ground, next) {
            motion.step_crossing = None;
            return settled;
        }
        crossing.returning = true;
    }
    motion.step_crossing = Some(crossing);
    next
}

/// Moves the player's body from `at` by the horizontal `step`, sliding along any wall, rail or slope too steep to climb
/// in the way. Returns how far the step carried it, and how far it is then pushed out of anything closer than its
/// radius on any side: the push moves the body but adds nothing to its speed.
fn slide(ground: &mut impl WalkingGround, at: Vec3, step: Vec3) -> (Vec3, Vec3) {
    let mut moved = Vec3::ZERO;
    let mut left = step;
    // A step that meets one wall slides along it; one that meets a second, in a corner, stops there.
    for _ in 0..2 {
        let Ok(direction) = Dir3::new(left) else { break };
        let length = left.length();
        let Some(hit) = sweep(ground, at + moved, direction, length + RADIUS_M) else {
            moved += left;
            break;
        };
        let free = (hit.distance - RADIUS_M).max(0.0).min(length);
        moved += *direction * free;
        let wall = hit.normal.with_y(0.0).normalize_or_zero();
        let rest = left - *direction * free;
        left = rest - wall * rest.dot(wall);
    }
    (moved, clear(ground, at + moved))
}

/// The nearest wall a ray from the body's checked heights meets along `direction` within `reach`.
fn sweep(ground: &mut impl WalkingGround, at: Vec3, direction: Dir3, reach: f32) -> Option<Hit> {
    WALL_CHECKS_M
        .into_iter()
        .filter_map(|height| ground.cast(at + Vec3::Y * height, direction, reach))
        .filter(|hit| hit.normal.y < STEEPEST_DEG.to_radians().cos())
        .min_by(|a, b| a.distance.total_cmp(&b.distance))
}

/// How far to move the body at `at` so that no wall is closer than its radius, looking around it in eight directions,
/// at most [`MOST_PUSH_M`] a frame.
fn clear(ground: &mut impl WalkingGround, at: Vec3) -> Vec3 {
    let mut push = Vec3::ZERO;
    for k in 0..8 {
        let angle = k as f32 * std::f32::consts::TAU / 8.0;
        let direction = Dir3::new_unchecked(Vec3::new(angle.sin(), 0.0, angle.cos()));
        if let Some(hit) = sweep(ground, at, direction, RADIUS_M) {
            push -= *direction * (RADIUS_M - hit.distance);
        }
    }
    push.clamp_length_max(MOST_PUSH_M)
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
    motion.action = Action::Flip;
    commands.trigger(Play::once(body, "double-jump").fading(0.05));
}

fn is_side_dodge(controls: &Controls) -> bool {
    let stick = controls.stick;
    stick.x.abs() > 0.3 && stick.x.abs() >= stick.y.abs()
}

/// A side hop when the stick points to the side of the camera, a backflip otherwise. The player first turns to face
/// the way the camera looks.
fn dodge(commands: &mut Commands, motion: &mut Motion, body: Entity, controls: &Controls, camera_yaw: f32) {
    motion.yaw = camera_yaw + std::f32::consts::PI;
    let facing = Vec3::new(motion.yaw.sin(), 0.0, motion.yaw.cos());
    let left = Vec3::new(facing.z, 0.0, -facing.x);
    let stick = controls.stick;
    let side = is_side_dodge(controls);
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
        if wish.length() > 0.05 && !matches!(motion.action, Action::Flip) {
            motion.yaw = turn_toward(motion.yaw, yaw_of(wish), TURN_RATE * AIR_CONTROL * dt);
        }
    }
    let step = motion.velocity * dt;
    let (moved, push) = slide(ground, *at, step.with_y(0.0));
    let mut next = *at + moved + push + Vec3::Y * step.y;
    motion.velocity = (moved / dt).with_y(motion.velocity.y);
    if let Some(leap) = motion.leap.as_mut() {
        *leap = moved / dt;
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
    let (moved, push) = slide(ground, *at, step.with_y(0.0));
    let mut next = *at + moved + push + Vec3::Y * step.y;
    motion.glide_speed = motion.glide_speed.min(moved.length() / dt);
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
        (Mode::Air, Action::Flip) if playing.finished => {
            motion.action = Action::Free;
            commands.trigger(Play::once(body, "fall").fading(0.15));
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

#[cfg(test)]
mod step_tests {
    use super::*;
    use hakuba_world::Surface;

    struct Fixture {
        rise: f32,
        half_width: f32,
        depth: f32,
        ceiling: bool,
        steep: bool,
        block_return: bool,
        block_drop: bool,
        clear_drop: bool,
    }
    fn hit(point: Vec3, normal: Vec3, distance: f32) -> Hit {
        Hit { point, normal, distance, surface: Surface::Built }
    }
    impl WalkingGround for Fixture {
        fn cast(&mut self, from: Vec3, direction: Dir3, reach: f32) -> Option<Hit> {
            if direction.x > 0.0 && from.x <= 0.3 && from.y < 2.0 + self.rise && from.y >= 2.0 {
                let distance = (0.3 - from.x) / direction.x;
                (distance <= reach).then(|| hit(from + *direction * distance, Vec3::NEG_X, distance))
            } else {
                None
            }
        }
        fn below(&mut self, at: Vec3, above: f32, below: f32) -> Option<Hit> {
            let on_step = at.x >= 0.3 && at.x <= 0.3 + self.depth && at.z.abs() <= self.half_width;
            let y = 2.0 + if on_step { self.rise } else { 0.0 };
            let normal = if self.steep && at.x > 0.05 { Vec3::new(-0.9, 0.436, 0.0) } else { Vec3::Y };
            (y <= at.y + above && y >= at.y - below).then(|| hit(at.with_y(y), normal, at.y + above - y))
        }
        fn sweep_capsule(
            &self,
            feet: Vec3,
            _radius: f32,
            _height: f32,
            delta: Vec3,
        ) -> Result<Option<Hit>, &'static str> {
            if delta.x < 0.0 && self.block_return {
                return Ok(Some(hit(feet, Vec3::X, 0.0)));
            }
            if delta.y < 0.0 && self.block_drop && feet.x > 0.001 {
                return Ok(Some(hit(feet, Vec3::Y, 0.0)));
            }
            if delta.y > 0.0 && self.ceiling {
                return Ok(Some(hit(feet, Vec3::NEG_Y, 0.0)));
            }
            if delta.x > 0.0 && feet.y < 2.0 + self.rise && feet.x + delta.x + RADIUS_M >= 0.3 {
                return Ok(Some(hit(feet, Vec3::NEG_X, 0.0)));
            }
            if delta.y < 0.0 && self.clear_drop {
                return Ok(None);
            }
            if delta.y < 0.0 {
                let y = 2.0
                    + if feet.x >= 0.3 && feet.x <= 0.3 + self.depth && feet.z.abs() <= self.half_width {
                        self.rise
                    } else {
                        0.0
                    };
                let d = feet.y - y;
                if d >= 0.0 && d <= -delta.y {
                    return Ok(Some(hit(feet.with_y(y), Vec3::Y, d)));
                }
            }
            Ok(None)
        }
    }
    fn fixture(rise: f32) -> Fixture {
        Fixture {
            rise,
            half_width: 1.0,
            depth: 1.0,
            ceiling: false,
            steep: false,
            block_return: false,
            block_drop: false,
            clear_drop: false,
        }
    }
    fn drive(ground: &mut Fixture, motion: &mut Motion, mut at: Vec3, speed: f32, frames: usize) -> Vec3 {
        for _ in 0..frames {
            motion.velocity = Vec3::X * speed;
            let crossing = motion.step_crossing.is_some();
            let next = walk(ground, motion, at, Vec3::X * speed, 0.05);
            let ordinary_push = if crossing || motion.step_crossing.is_some() { 0.0 } else { MOST_PUSH_M };
            assert!((next.x - at.x).abs() <= speed.abs() * 0.05 + ordinary_push + 0.001);
            at = next;
        }
        at
    }
    #[test]
    fn clear_sweep_settles_onto_ray_confirmed_support() {
        let mut ground = fixture(0.18);
        ground.clear_drop = true;
        let at = Vec3::new(0.35, 2.20, 0.0);
        let settled = settle_step(&mut ground, at).unwrap();
        assert!((settled.y - 2.18).abs() < 0.00001);
        ground.block_drop = true;
        assert!(settle_step(&mut ground, at).is_none());
    }

    #[test]
    fn flat_walking_keeps_its_normal_frame_distance() {
        let mut ground = fixture(0.0);
        let mut motion = Motion { mode: Mode::Ground, ..default() };
        let end = drive(&mut ground, &mut motion, Vec3::Y * 2.0, 1.0, 4);
        assert!((end.x - 0.2).abs() < 0.001 && (end.y - 2.0).abs() < 0.001);
        assert!(motion.step_crossing.is_none());
    }

    #[test]
    fn low_step_is_walked_both_ways_without_a_horizontal_jump() {
        let mut ground = fixture(0.18);
        let mut motion = Motion { mode: Mode::Ground, ..default() };
        let end = drive(&mut ground, &mut motion, Vec3::Y * 2.0, 1.0, 8);
        assert!(end.x > 0.3 && (end.y - 2.18).abs() < 0.001 && motion.step_crossing.is_none());
        let back = drive(&mut ground, &mut motion, end, -1.0, 8);
        assert!(back.x < 0.3 && (back.y - 2.0).abs() < 0.001 && motion.step_crossing.is_none());
    }
    #[test]
    fn tall_wall_ceiling_narrow_ledge_and_steep_ramp_do_not_start_a_step() {
        let mut high = fixture(0.6);
        let mut ceiling = fixture(0.18);
        ceiling.ceiling = true;
        let mut narrow = fixture(0.18);
        narrow.half_width = 0.1;
        let mut lip = fixture(0.18);
        lip.depth = 0.1;
        let mut ramp = fixture(0.18);
        ramp.steep = true;
        for ground in [&mut high, &mut ceiling, &mut narrow, &mut lip, &mut ramp] {
            assert!(prepare_step(ground, Vec3::Y * 2.0, Vec3::X * 0.05).is_none());
        }
    }
    #[test]
    fn cancelled_step_returns_to_its_start_without_snapping_forward() {
        let mut ground = fixture(0.18);
        let mut motion = Motion { mode: Mode::Ground, ..default() };
        let raised = drive(&mut ground, &mut motion, Vec3::Y * 2.0, 1.0, 3);
        assert!(motion.step_crossing.is_some());
        ground.block_drop = true;
        let returned = drive(&mut ground, &mut motion, raised, -1.0, 3);
        assert!(returned.x.abs() < 0.001 && (returned.y - 2.0).abs() < 0.001 && motion.step_crossing.is_none());
    }

    #[test]
    fn released_input_retraces_only_when_the_drop_is_blocked() {
        let mut ground = fixture(0.18);
        let mut motion = Motion { mode: Mode::Ground, ..default() };
        let at = drive(&mut ground, &mut motion, Vec3::Y * 2.0, 1.0, 3);
        ground.block_drop = true;
        let mut current = at;
        for _ in 0..10 {
            // The stick is released while velocity may still be positive during deceleration.
            motion.velocity = Vec3::X;
            let next = walk(&mut ground, &mut motion, current, Vec3::ZERO, 0.05);
            assert!(next.x <= current.x && current.x - next.x <= 0.026);
            current = next;
        }
        assert!(current.x.abs() < 0.001 && (current.y - 2.0).abs() < 0.001);
        assert!(motion.step_crossing.is_none());
    }

    #[test]
    fn released_input_cannot_reenter_a_step_with_residual_velocity() {
        let mut ground = fixture(0.18);
        let mut motion = Motion { mode: Mode::Ground, ..default() };
        let at = drive(&mut ground, &mut motion, Vec3::Y * 2.0, 1.0, 3);
        motion.velocity = Vec3::X;
        let settled = walk(&mut ground, &mut motion, at, Vec3::ZERO, 0.05);
        assert!((settled.x - at.x).abs() < 0.001 && (settled.y - 2.0).abs() < 0.001);
        assert!(motion.velocity.x.abs() < 1e-6 && motion.step_crossing.is_none());
        let still = walk(&mut ground, &mut motion, settled, Vec3::ZERO, 0.05);
        assert_eq!(still, settled);
        assert!(motion.step_crossing.is_none());
    }

    #[test]
    fn perpendicular_input_cancels_the_crossing_without_forward_motion() {
        let mut ground = fixture(0.18);
        let mut motion = Motion { mode: Mode::Ground, ..default() };
        let at = drive(&mut ground, &mut motion, Vec3::Y * 2.0, 1.0, 3);
        ground.block_drop = true;
        motion.velocity = Vec3::Z;
        let next = walk(&mut ground, &mut motion, at, Vec3::Z, 0.05);
        assert!(next.x < at.x && next.z == at.z);
        assert!(motion.step_crossing.is_some_and(|step| step.returning));
    }

    #[test]
    fn sideways_or_reverse_input_settles_in_place_when_the_drop_is_clear() {
        for intent in [Vec3::Z, Vec3::NEG_X] {
            let mut ground = fixture(0.18);
            let mut motion = Motion { mode: Mode::Ground, ..default() };
            let at = drive(&mut ground, &mut motion, Vec3::Y * 2.0, 1.0, 3);
            motion.velocity = intent;
            let next = walk(&mut ground, &mut motion, at, intent, 0.05);
            assert!((next.x - at.x).abs() < 0.001 && (next.y - 2.0).abs() < 0.001);
            assert!(motion.step_crossing.is_none());
        }
    }

    #[test]
    fn cancellation_at_max_step_height_finds_the_original_floor() {
        let mut ground = fixture(0.449);
        let mut motion = Motion { mode: Mode::Ground, ..default() };
        let mut at = drive(&mut ground, &mut motion, Vec3::Y * 2.0, 1.0, 3);
        assert!(motion.step_crossing.is_some());
        ground.block_drop = true;
        for _ in 0..10 {
            motion.velocity = Vec3::X;
            at = walk(&mut ground, &mut motion, at, Vec3::ZERO, 0.05);
        }
        assert!(at.x.abs() < 0.001 && (at.y - 2.0).abs() < 0.001);
        assert!(motion.step_crossing.is_none());
    }

    #[test]
    fn low_ceiling_keeps_a_crossing_from_starting_an_air_action() {
        let mut ground = fixture(0.18);
        let mut motion = Motion { mode: Mode::Ground, ..default() };
        let at = drive(&mut ground, &mut motion, Vec3::Y * 2.0, 1.0, 3);
        ground.ceiling = true;
        assert!(!leave_step_for_air(&ground, &mut motion, at, 0.8));
        assert!(motion.step_crossing.is_some());
    }

    #[test]
    fn blocked_rollback_can_be_left_by_jumping_when_headroom_is_clear() {
        let mut ground = fixture(0.18);
        let mut motion = Motion { mode: Mode::Ground, ..default() };
        let at = drive(&mut ground, &mut motion, Vec3::Y * 2.0, 1.0, 3);
        ground.block_return = true;
        ground.block_drop = true;
        motion.velocity = Vec3::NEG_X;
        assert_eq!(walk(&mut ground, &mut motion, at, Vec3::NEG_X, 0.05), at);
        assert!(motion.step_crossing.is_some());
        assert!(leave_step_for_air(&ground, &mut motion, at, 0.8));
        assert!(motion.step_crossing.is_none());
    }
}
