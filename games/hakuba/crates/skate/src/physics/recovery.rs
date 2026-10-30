//! Continuous same-location recovery of the existing native rider and board.
//! The stock wipeout runs limp until grounded/quiet. A local rebase seeds the
//! native ground controller, then the same physical body rises from its solved
//! snapshot. No checkpoint history, second solver or forced animation is used.
use super::{GamePhysics, PlayerControls, SkaterRuntime};
use crate::{
    core::{
        animation::output::NativeMatrix,
        math::{Basis3, Vector3},
        physics::{drive_frames::RetailAffineTransform, mass::MassShape},
        player::state::PhysicalStateId as State,
    },
    graph_runtime::StockGraphs,
};
use bevy::prelude::*;
const BAIL_SETTLE: f32 = 2.2;
const GET_UP_TIME: f32 = 0.7;
const BOARD_REACH: f32 = 0.6;

pub(crate) struct Runtime {
    pub delay: f32,
    settings: Option<std::sync::Arc<crate::data::collections::Collections>>,
    pub requested: bool,
    pub board_visibility: f32,
    elapsed: f32,
    quiet: f32,
    rebase: Option<NativeMatrix>,
    rising: Option<Rising>,
    was_bailing: bool,
}
impl Default for Runtime {
    fn default() -> Self {
        Self {
            delay: 1.,
            settings: None,
            requested: false,
            board_visibility: 1.,
            elapsed: 0.,
            quiet: 0.,
            rebase: None,
            rising: None,
            was_bailing: false,
        }
    }
}
struct Rising {
    time: f32,
    snapshot: Vec<Mat4>,
    root: Mat4,
    target: Vec<Mat4>,
    target_root: Mat4,
    board: Mat4,
    target_board: Mat4,
    step_on: bool,
    prepared: bool,
    warmup: u32,
    native_roots: Option<crate::core::physics::skeleton_root::SkeletonRootFrames>,
}
impl Runtime {
    #[cfg(test)]
    pub fn quiet_time(&self) -> f32 {
        self.quiet
    }
    #[cfg(test)]
    pub fn elapsed_time(&self) -> f32 {
        self.elapsed
    }
    pub fn bind(&mut self, settings: std::sync::Arc<crate::data::collections::Collections>) {
        self.settings = Some(settings);
    }
    pub fn getting_up(&self) -> bool {
        self.rising.is_some()
    }
    pub fn take_rebase(&mut self) -> Option<NativeMatrix> {
        self.rebase.take()
    }
    pub fn shown_board(&self) -> Option<Mat4> {
        self.rising.as_ref().filter(|up| !up.prepared).map(|up| up.board)
    }
}
fn native(m: Mat4) -> NativeMatrix {
    let mut n = m.to_cols_array_2d();
    n[3][3] = 0.;
    n
}
fn mat(n: NativeMatrix) -> Mat4 {
    crate::animation::native_matrix(n)
}
fn affine(m: Mat4) -> RetailAffineTransform {
    RetailAffineTransform {
        basis: Basis3 { columns: Mat3::from_mat4(m).to_cols_array_2d() },
        translation: Vector3::new(m.w_axis.x, m.w_axis.y, m.w_axis.z),
    }
}
fn blend(a: Mat4, b: Mat4, t: f32) -> Mat4 {
    let (sa, qa, pa) = a.to_scale_rotation_translation();
    let (sb, qb, pb) = b.to_scale_rotation_translation();
    Mat4::from_scale_rotation_translation(sa.lerp(sb, t), qa.slerp(qb, t), pa.lerp(pb, t))
}
fn ground(physics: &GamePhysics, p: Vec3) -> Result<Option<Vec3>, String> {
    use super::offboard::contact_queries::{Probe, query};
    Ok(query(&physics.world, Probe { start: [p.x, p.y + 0.5, p.z, 0.], end: [p.x, p.y - 3., p.z, 0.], radius: 0. }, 0)?
        .filter(|h| h.geometry.normal.y > 0.2)
        .map(|h| {
            let p = h.geometry.position;
            Vec3::new(p.x, p.y, p.z)
        }))
}

pub(super) fn bail(physics: &mut GamePhysics, skater: &mut SkaterRuntime) -> Result<(), String> {
    if skater.player_state.current() == State::WipeoutGround {
        return Ok(());
    }
    skater.recovery =
        Runtime { delay: skater.recovery.delay, settings: skater.recovery.settings.clone(), ..Default::default() };
    let velocities = skater.skeleton.bodies().map(|b| (b.rates.linear_velocity, b.rates.angular_velocity));
    super::player_state::set_local(physics, skater, State::WipeoutGround)?;
    // Local bail keeps the body's already-solved momentum. Source entry's
    // historical 20m/s clamp remains unchanged for reference in its owner.
    for (b, (linear, angular)) in skater.skeleton.bodies_mut().iter_mut().zip(velocities) {
        b.rates.linear_velocity = linear;
        b.rates.angular_velocity = angular;
    }
    super::player_state::publish(physics, skater)
}
pub(super) fn restore_and_bail(
    physics: &mut GamePhysics,
    skater: &mut SkaterRuntime,
    shown: &super::bridge::Pose,
) -> Result<(), String> {
    if !shown.root.is_finite()
        || !shown.velocity.is_finite()
        || shown.bones.len() != skater.render_pose.len()
        || shown.bones.iter().chain(&shown.board).any(|m| !m.is_finite())
    {
        return Err("Local bail requires a finite displayed physical pose".into());
    }
    let deck = *shown.board.get(6).ok_or("Local bail needs all board parts")?;
    physics.board.reset_physical(
        physics.settings.authored,
        affine(deck),
        skater.player_input.processed.flags_2468,
        physics.settings.step.simulation.gravity_acceleration,
    );
    super::transition_pose::publish(physics, skater, shown.root, shown.bones.iter().copied().map(native).collect())?;
    let velocity = Vector3::new(shown.velocity.x, shown.velocity.y, shown.velocity.z);
    for b in physics.board.bodies_mut().iter_mut().chain(skater.skeleton.bodies_mut()) {
        b.rates.linear_velocity = velocity;
        b.rates.angular_velocity = Vector3::ZERO;
        b.rates.force_acceleration = physics.settings.step.simulation.gravity_acceleration;
        b.rates.torque_acceleration = Vector3::ZERO;
    }
    skater.player_state.selector.request_teleport = false;
    skater.player_input.physical.state.flag_69 = 0;
    skater.player_input.processed.flags_2468 &= !2;
    skater.player_input.processed.flags_2472 &= !0x40000;
    skater.player_input.toolkit = None;
    bail(physics, skater)
}

/// Observe the completed native solve. During a rebase the shown body remains
/// the fallen snapshot, while the native controller prepares its real target.
pub(super) fn observe(physics: &mut GamePhysics, skater: &mut SkaterRuntime) -> Result<(), String> {
    let mut r = std::mem::take(&mut skater.recovery);
    let result = (|| {
        if let Some(up) = r.rising.as_mut() {
            if !up.prepared && r.rebase.is_none() {
                up.warmup += 1;
                if up.warmup >= 8 {
                    up.target_root = mat(skater.animated_skeleton.roots.animation_to_world);
                    up.target = skater.render_pose.iter().copied().map(mat).collect();
                    up.target_board = mat(super::solve::deck_frame(&physics.board));
                    up.prepared = true;
                    physics.board.set_transform(affine(up.board));
                }
                up.native_roots = Some(skater.animated_skeleton.roots.clone());
                skater.animated_skeleton.roots.animation_to_world = native(up.root);
                skater.animated_skeleton.roots.world_to_animation = native(up.root.inverse());
                skater.render_pose = up.snapshot.iter().map(|m| native(up.root.inverse() * *m)).collect();
            }
            return Ok(());
        }
        if skater.player_state.current() != State::WipeoutGround {
            r.was_bailing = false;
            r.elapsed = 0.;
            r.quiet = 0.;
            r.board_visibility = 1.;
            return Ok(());
        }
        if !r.was_bailing {
            r.elapsed = 0.;
            r.quiet = 0.;
            r.was_bailing = true;
        }
        // The stock wipeout root predicts hips and COM separately. At high speed
        // that advances the actor by multiple ticks although the solved body moved
        // only once. Follow the completed physical hips, preserving every shown
        // world-space bone while changing its reference frame.
        let old_root = mat(skater.animated_skeleton.roots.animation_to_world);
        let root = mat(skater.skeleton.part_transforms()[23]) * mat(skater.animated_skeleton.animation_hips).inverse();
        let rebase = root.inverse() * old_root;
        for bone in &mut skater.render_pose {
            *bone = native(rebase * mat(*bone));
        }
        skater.animated_skeleton.roots.animation_to_world = native(root);
        skater.animated_skeleton.roots.world_to_animation = native(root.inverse());
        let dt = physics.settings.step.simulation.time_step;
        r.elapsed += dt;
        let v = skater.skeleton.bodies()[23].rates.linear_velocity;
        let speed = (v.x * v.x + v.y * v.y + v.z * v.z).sqrt();
        r.quiet = if speed < 0.4 { r.quiet + dt } else { 0. };
        let hips = mat(skater.skeleton.part_transforms()[23]).w_axis.truncate();
        let Some(floor) = ground(physics, hips)? else {
            return Ok(());
        };
        let near_ground = hips.y - floor.y < 1.0;
        let wipeout = &skater.wipeout_state.state;
        // Consume the approved native manual intent before its historical
        // checkpoint countdown. Waiting for request69/over can outlast the
        // local automatic quiet dwell, making Enter ineffective.
        let native_manual =
            wipeout.recovery_eligible && wipeout.reset_ever && !wipeout.ignore_reset && !wipeout.prevent_manual;
        r.requested |= native_manual;
        let manual = r.requested && native_manual;
        // The native manual request skips only the extra quiet dwell. It still
        // needs the minimum bail time, current low speed and actual ground.
        let settled = recovery_ready(r.elapsed, r.quiet, r.delay, near_ground, manual);
        if !settled {
            return Ok(());
        }
        let root = mat(skater.animated_skeleton.roots.animation_to_world);
        let snapshot = skater.render_pose.iter().map(|m| root * mat(*m)).collect();
        let board = mat(super::solve::deck_frame(&physics.board));
        let step_on = board.w_axis.truncate().distance(floor) <= BOARD_REACH && board.y_axis.y > 0.5;
        let forward = root.z_axis.truncate() * Vec3::new(1., 0., 1.);
        let yaw = if forward.length_squared() > 0.0001 { forward.x.atan2(forward.z) } else { 0. };
        let mut target = Mat4::from_rotation_translation(Quat::from_rotation_y(yaw), floor);
        // Board reset's target is the deck, not the floor anchor. Keep authored wheel height.
        target.w_axis.y += physics.settings.wheel_radius - physics.settings.authored[0].translation.y;
        if step_on {
            target = board;
        }
        r.rebase = Some(native(target));
        r.rising = Some(Rising {
            time: 0.,
            snapshot,
            root,
            target: Vec::new(),
            target_root: root,
            board,
            target_board: target,
            step_on,
            prepared: false,
            warmup: 0,
            native_roots: None,
        });
        r.requested = false;
        Ok(())
    })();
    skater.recovery = r;
    result
}

pub(super) fn advance(
    physics: &mut GamePhysics,
    skater: &mut SkaterRuntime,
    _controls: &PlayerControls,
    _graphs: &StockGraphs,
    camera: &mut crate::camera::CameraRuntime,
) -> Result<bool, String> {
    let mut r = std::mem::take(&mut skater.recovery);
    let result = (|| {
        let Some(up) = r.rising.as_mut() else {
            return Ok(false);
        };
        if !up.prepared {
            if let Some(roots) = up.native_roots.take() {
                skater.animated_skeleton.roots = roots;
            }
            if r.rebase.is_some() {
                let settings = r.settings.as_ref().ok_or("Local recovery needs bound settings")?;
                let stance = skater.animation.checkpoint_stance();
                skater.animation = crate::skater_animation::SkaterAnimation::from_source(
                    settings,
                    _graphs,
                    b"",
                    skater.animation.source.clone(),
                )?;
                skater.animation.request_checkpoint_stance(stance);
                skater.animation.evaluate_initial_pose()?;
                skater.animation_feedback.reset();
                skater.wipeout.state.clear_after_selection();
                skater.wipeout.state.reset_systems();
                skater.player_input.processed.flags_2480 &= !8;
                super::player_state::set_local(physics, skater, State::PhysicsGround)?;
                super::player_state::publish(physics, skater)?;
            }
            return Ok(false);
        }
        let dt = physics.settings.step.simulation.time_step;
        up.time += dt;
        let t = (up.time / GET_UP_TIME).min(1.);
        let a = t * t * (3. - 2. * t);
        let mut root = blend(up.root, up.target_root, a);
        let world: Vec<_> =
            up.snapshot.iter().zip(&up.target).map(|(&from, &to)| blend(from, up.target_root * to, a)).collect();
        let mut lift = 0.0f32;
        // Keep endpoint world height AND endpoint terrain clearance for every native
        // collision hull, including uphill corners between the two endpoint locations.
        for (part, &bone) in skater.animated_skeleton.bone_indices.iter().enumerate().skip(1) {
            let frame = mat(skater.animated_skeleton.physics_frames[part]);
            let from = up.snapshot[bone] * frame;
            let to = up.target_root * up.target[bone] * frame;
            let now = world[bone] * frame;
            for point in shape_points(skater.skeleton.definition.parts[part].shape) {
                let p0 = from.transform_point3(point);
                let p1 = to.transform_point3(point);
                let p = now.transform_point3(point);
                lift = lift.max(p0.y.min(p1.y) - p.y);
                if let (Some(g0), Some(g1), Some(g)) = (ground(physics, p0)?, ground(physics, p1)?, ground(physics, p)?)
                {
                    lift = lift.max((p0.y - g0.y).min(p1.y - g1.y) - (p.y - g.y));
                }
            }
        }
        root.w_axis.y += lift;
        let inverse = root.inverse();
        let pose = world
            .into_iter()
            .map(|mut m| {
                m.w_axis.y += lift;
                native(inverse * m)
            })
            .collect();
        // The loose board is the original assembly. Only move it while invisible
        // when it cannot be stepped onto; never invent a second board solver.
        if up.step_on {
            physics.board.set_transform(affine(blend(up.board, up.target_board, a)));
        } else if t < 0.4 {
            r.board_visibility = (1. - t / 0.3).max(0.);
        } else {
            physics.board.set_transform(affine(up.target_board));
            r.board_visibility = ((t - 0.5) / 0.3).clamp(0., 1.);
        }
        super::transition_pose::publish(physics, skater, root, pose)?;
        let deck = physics.board.bodies()[6].rates;
        let rider = skater.skeleton.bodies()[23].rates;
        physics.exchange.publish_output(crate::core::physics::phase::PhysicalOutputSnapshot {
            tick: physics.ticks,
            state: skater.player_state.current(),
            board_position: deck.position,
            board_linear_velocity: deck.linear_velocity,
            rider_root_position: rider.position,
            rider_linear_velocity: rider.linear_velocity,
            ground_normal: physics.riding.ground.wheel_normal,
            contact_count: physics.riding.ground.part_contact_count as u32,
            predicted_position: deck.position,
            grounded: false,
            wiping_out: false,
            landed: false,
            events: Vec::new(),
        });
        physics.ticks += 1;
        let feedback = skater.physical_feedback;
        super::camera_output::advance(physics, skater, &feedback, camera)?;
        physics.clock.finish_tick();
        if t >= 1. {
            r.rising = None;
            r.board_visibility = 1.;
            r.was_bailing = false;
        }
        Ok(true)
    })();
    skater.recovery = r;
    result
}

fn settled(elapsed: f32, quiet: f32, delay: f32, near_ground: bool) -> bool {
    elapsed > 1.6 && near_ground && (quiet > 0.4 || elapsed > BAIL_SETTLE * delay + 2.)
}
fn recovery_ready(elapsed: f32, quiet: f32, delay: f32, near_ground: bool, manual: bool) -> bool {
    settled(elapsed, quiet, delay, near_ground) || (manual && elapsed > 1.6 && near_ground && quiet > 0.)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn manual_request_skips_only_quiet_dwell_after_native_settle() {
        assert!(!recovery_ready(1.7, 0.1, 2., true, false));
        assert!(recovery_ready(1.7, 0.1, 2., true, true));
        assert!(!recovery_ready(1.6, 0.1, 2., true, true));
        assert!(!recovery_ready(1.7, 0., 2., true, true));
        assert!(!recovery_ready(1.7, 0.1, 2., false, true));
        // Without a manual request, both existing automatic branches survive.
        assert!(recovery_ready(1.7, 0.5, 2., true, false));
        assert!(recovery_ready(6.5, 0., 2., true, false));
    }
    #[test]
    fn local_settle_delay_scales_timeout_but_never_lifts_an_airborne_body() {
        assert!(settled(3., 0., 0.25, true));
        assert!(!settled(3., 0., 2., true));
        assert!(settled(6.5, 0., 2., true));
        assert!(!settled(20., 1., 0.25, false));
        assert!(!settled(1.6, 1., 0.25, true));
        assert!(settled(1.7, 0.5, 2., true));
    }
}

fn shape_points(shape: MassShape) -> Vec<Vec3> {
    match shape {
        MassShape::Sphere { radius } => vec![Vec3::NEG_Y * radius],
        MassShape::Capsule { radius, half_length } => {
            vec![Vec3::new(0., -radius, -half_length), Vec3::new(0., -radius, half_length)]
        }
        MassShape::RoundedBox { half_extents: e, radius } => [-1., 1.]
            .into_iter()
            .flat_map(|x| {
                [-1., 1.].into_iter().flat_map(move |y| {
                    [-1., 1.]
                        .into_iter()
                        .map(move |z| Vec3::new(x * (e.x + radius), y * (e.y + radius), z * (e.z + radius)))
                })
            })
            .collect(),
        _ => Vec::new(),
    }
}
