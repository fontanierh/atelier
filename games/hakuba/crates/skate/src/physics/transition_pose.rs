//! Publishes an owned continuous physical transition into the one skater assembly.
use super::{GamePhysics, SkaterRuntime};
use crate::core::{
    animation::output::NativeMatrix, math::Vector3, physics::skeleton_animation_record::map_animation_parts,
};
use bevy::prelude::*;
fn matrix(m: NativeMatrix) -> Mat4 {
    crate::animation::native_matrix(m)
}
fn native(m: Mat4) -> NativeMatrix {
    let mut n = m.to_cols_array_2d();
    n[3][3] = 0.;
    n
}
fn point(v: Vec3) -> [f32; 4] {
    [v.x, v.y, v.z, 0.]
}
fn zero_rates(r: &mut crate::core::physics::rigid_body::RetailBodyRates) {
    r.linear_velocity = Vector3::ZERO;
    r.angular_velocity = Vector3::ZERO;
    r.force_acceleration = Vector3::ZERO;
    r.torque_acceleration = Vector3::ZERO;
}
pub(super) fn publish(
    physics: &GamePhysics,
    skater: &mut SkaterRuntime,
    root: Mat4,
    pose: Vec<NativeMatrix>,
) -> Result<(), String> {
    let s = &mut skater.animated_skeleton;
    let parts = map_animation_parts(&pose, &s.bone_indices, &s.physics_frames).map_err(str::to_owned)?;
    s.roots.animation_to_world = native(root);
    s.roots.world_to_animation = native(root.inverse());
    s.record.update(&parts, &s.roots.animation_to_board, &s.masses);
    s.animation_hips = parts[23];
    s.animation_board = parts[0];
    let com = root.transform_point3(Vec3::from_slice(&s.record.centre_of_mass[..3]));
    s.board_frames.update_com_lift(&native(root), point(com), 0.24);
    s.board_frames.centre_of_mass = point(com);
    s.board_frames.previous_centre_of_mass = point(com);
    s.board_frames.com_velocity = [0.; 4];
    for (i, p) in parts.iter().enumerate() {
        skater.skeleton.set_part_transform(i, native(root * matrix(*p)));
    }
    // The two auxiliary COM bodies participate in the same constraints as the
    // visible bones. Leaving them at takeoff causes a false collision impulse.
    skater.skeleton.set_part_transform(24, s.board_frames.lifted_com_frame);
    skater.skeleton.set_part_transform(25, s.board_frames.com_frame);
    skater.skeleton_drives.targets.reset(native(root * matrix(parts[23])), native(root * matrix(parts[0])));
    let targets = skater.skeleton_drives.targets.update_extra_targets(
        &mut skater.skeleton,
        &s.board_frames.com_frame,
        &s.board_frames.lifted_com_frame,
    );
    skater.skeleton_input.extra_target_positions = [targets.com, targets.lifted_com, targets.following_com];
    skater.pose_errors.set_targets(targets);
    skater.skeleton_input.drive_frames = parts;
    for b in skater.skeleton.bodies_mut() {
        zero_rates(&mut b.rates);
    }
    skater.skeleton.animation_to_world = native(root);
    skater.skeleton_input.previous_root_position = point(root.w_axis.truncate());
    skater.skeleton_input.root_velocity = [0.; 4];
    skater.skeleton_output.correction = Default::default();
    skater.skeleton.publish_physical_record(native(root * matrix(parts[0])));
    let p = &mut skater.player_input.processed;
    p.effective_anim_transform_192 = native(root).map(|v| v.map(f32::to_bits));
    p.vectors_544_560_592_608[2] = point(com).map(f32::to_bits);
    p.vectors_544_560_592_608[3] = [0; 4];
    p.flags_2472 &= !(1 << 10);
    let physical = &mut skater.player_input.physical;
    physical.skeleton.anim_to_world_11920 = native(root).map(|v| v.map(f32::to_bits));
    physical.reckoning.vector_64 = point(com).map(f32::to_bits);
    physical.reckoning.vector_16 = [0; 4];
    physical.reckoning.vector_96 = [0., 1., 0., 0.].map(f32::to_bits);
    physical.air.flag_441 = 0;
    physical.air.use_air_reckoning_452 = 0;
    skater.centre_of_mass_output = skater.centre_of_mass_filter.update(point(com), [0.; 4]);
    skater.render_pose = pose;
    skater.pose_generation = skater.pose_generation.wrapping_add(1);
    skater.player_input.player.update_count_1316 = skater.player_input.player.update_count_1316.wrapping_add(1);
    let _ = physics;
    Ok(())
}
