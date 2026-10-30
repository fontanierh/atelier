//! Post-physics grind tolerance regression cases.
use super::*;
use crate::core::physics::skeleton_animation_record::IDENTITY;

fn stock() -> Settings {
    Settings {
        max_arm_contact_164: 30.,
        max_body_contact_168: 8.5,
        xz_acceleration_204: 6.,
        max_displacement_208: 2.,
        max_angular_deck_error_212: 1.3,
        y_acceleration: 100.,
    }
}
fn input() -> Frame {
    Frame {
        flags_2468: 0,
        flags_2472: 0,
        flags_2476: 0,
        flags_2480: 0,
        flags_2484: 0,
        category: 100,
        timestep: 1.0 / 60.0,
        time_on_ground: 1.0,
        speed: 0.0,
        animation_up: [0.0, 1.0, 0.0, 0.0],
        landing_angle: 0.0,
        deck_velocity: [0.0; 4],
        com_velocity: [0.0; 4],
        jump_fix_frames: 1000,
        deck: IDENTITY,
        input_board: IDENTITY,
        world_to_animation: IDENTITY,
        closing_velocity: [0.0; 4],
        board_material_flags: 0,
        board_contact: true,
        wheel_contact: true,
        board_contact_normal: [0.0, 1.0, 0.0, 0.0],
        opposing_contact: 0.0,
        regions_force: [0.0; 8],
        maximum_skater_force: 0.0,
        vehicle_force: 0.0,
        group_8: false,
        conflicting: false,
        compliant: false,
        highest_normal: [0.0, 1.0, 0.0, 0.0],
        pose_error: [0.0; 4],
        maximum_pose_error: 0.0,
        flip_active: false,
        flip_requested_speed: 0.0,
        system_up_y: 1.0,
        grind_selected: false,
        grind_normal_valid: false,
        grind_normal: [0.0, 1.0, 0.0, 0.0],
    }
}

fn bails(frame: &Frame, factor: f32) -> bool {
    let mut requests = Requests::new();
    check(&mut requests, tolerance(stock(), factor), frame);
    requests.reasons.iter().any(|&active| active)
}
#[test]
fn tolerance_scales_all_authored_limits_and_restores_stock_bits() {
    let stock = stock();
    let words = |s: Settings| {
        [
            s.max_arm_contact_164,
            s.max_body_contact_168,
            s.xz_acceleration_204,
            s.max_displacement_208,
            s.max_angular_deck_error_212,
            s.y_acceleration,
        ]
        .map(f32::to_bits)
    };
    assert_eq!(words(tolerance(stock, 1.)), words(stock));
    for factor in [0.5, 2., 3.] {
        let expected = words(stock).map(|w| (f32::from_bits(w) * factor).to_bits());
        assert_eq!(words(tolerance(stock, factor)), expected);
    }
}
#[test]
fn tolerance_changes_real_pose_contact_closing_speed_and_twist_limits() {
    let mut frame = input();
    assert!(!bails(&frame, 1.));
    frame.pose_error = [3., 0., 0., 0.];
    assert!(bails(&frame, 1.));
    assert!(!bails(&frame, 2.));
    frame.pose_error[0] = 5.;
    assert!(bails(&frame, 2.));
    frame.pose_error = [0.; 4];
    let (sin, cos) = 1.57_f32.sin_cos();
    frame.deck[0] = [cos, 0., -sin, 0.];
    frame.deck[2] = [sin, 0., cos, 0.];
    assert!(bails(&frame, 1.));
    assert!(!bails(&frame, 2.));
    frame.deck = IDENTITY;
    for velocity in [[9., 0., 0., 0.], [0., 150., 0., 0.]] {
        frame.closing_velocity = velocity;
        assert!(bails(&frame, 1.));
        assert!(!bails(&frame, 2.));
        assert!(bails(&frame, 0.5));
    }
    frame.closing_velocity = [0.; 4];
    frame.regions_force[0] = 12.;
    assert!(bails(&frame, 1.));
    assert!(!bails(&frame, 2.));
}
