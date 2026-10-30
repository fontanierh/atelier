//! Resource-backed feel restoration and default-path replay checks.
use super::*;
fn package() -> Vec<u8> {
    std::fs::read(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../assets/simulations/skate-simulation/skate-simulation.skatepack"
    ))
    .expect("export skating data before session tests")
}
fn session() -> Session {
    let triangles = vec![
        [[-500.0, 0.0, -500.0], [-500.0, 0.0, 500.0], [500.0, 0.0, -500.0]],
        [[500.0, 0.0, -500.0], [-500.0, 0.0, 500.0], [500.0, 0.0, 500.0]],
    ];
    Session::from_resources(
        &crate::PreparedResources::from_bytes(package()).unwrap(),
        triangles,
        vec![1 << 7; 2],
        vec![],
        [0.0; 3],
        0.0,
    )
    .unwrap()
}
fn tuning_snapshot(s: &Session) -> Vec<u32> {
    let mut out =
        vec![s.physics.settings.step.simulation.gravity_acceleration.y.to_bits(), s.camera.anchor_speed().to_bits()];
    out.extend(s.skater.air_settings.grind_lock_distance.map(f32::to_bits));
    for mode in &s.skater.ground.pumping_settings.modes {
        out.extend([
            mode.controller.acceleration_factor.to_bits(),
            mode.controller.maximum_acceleration_per_second.to_bits(),
        ]);
    }
    for (surface, _) in &s.skater.slide_state.surfaces {
        out.extend(surface.speed_to_force.y.map(f32::to_bits));
    }
    out.extend(s.skater.wipeout.modes.map(|m| m.bad_landing_scale.to_bits()));
    let w = &s.skater.wipeout.settings;
    out.extend(
        [
            w.ground.y_acceleration,
            w.air.xz_acceleration,
            w.air.y_acceleration,
            w.air.xz_trick,
            w.air.y_trick,
            w.air.max_grind_speed,
        ]
        .map(f32::to_bits),
    );
    out
}
#[test]
fn live_feel_edits_restore_authored_values_without_compounding() {
    let mut s = session();
    let authored = tuning_snapshot(&s);
    let custom = crate::feel::FeelTuning {
        gravity: 0.8,
        rail_magnetism: 2.0,
        pump: 2.0,
        powerslide: 0.5,
        impact: 2.0,
        landing: 1.5,
        camera_follow: 2.0,
        grind_tolerance: 2.0,
        tight_flicks: true,
        ..Default::default()
    };
    s.set_feel(custom).unwrap();
    let first = tuning_snapshot(&s);
    s.set_feel(custom).unwrap();
    assert_eq!(first, tuning_snapshot(&s));
    s.set_feel(Default::default()).unwrap();
    assert_eq!(authored, tuning_snapshot(&s));
    let before = s.feel();
    assert!(s.set_feel(crate::feel::FeelTuning { gravity: f32::NAN, ..before }).is_err());
    assert_eq!(before, s.feel());
}
#[test]
fn explicitly_stock_feel_keeps_fixed_input_session_bits() {
    let mut a = session();
    let mut b = session();
    b.set_feel(Default::default()).unwrap();
    for i in 0..120 {
        let input = Controls { buttons: if i < 60 { 0x1000 } else { 0 }, ..Default::default() };
        a.tick(input).unwrap();
        b.tick(input).unwrap();
        let pa = a.pose();
        let pb = b.pose();
        assert_eq!(pa.root.to_cols_array().map(f32::to_bits), pb.root.to_cols_array().map(f32::to_bits));
        assert_eq!(pa.velocity.to_array().map(f32::to_bits), pb.velocity.to_array().map(f32::to_bits));
        assert_eq!(
            pa.bones.iter().map(|m| m.to_cols_array().map(f32::to_bits)).collect::<Vec<_>>(),
            pb.bones.iter().map(|m| m.to_cols_array().map(f32::to_bits)).collect::<Vec<_>>()
        );
    }
}

#[test]
fn fine_sticks_use_the_same_pad_conditioning_and_mismatched_packets_fall_back() {
    let mut s = session();
    let input = Controls { left: [7000, -21000], right: [25000, 8000], ..Default::default() };
    s.tick(input).unwrap();
    let actual = s.controls.gesture_axes(input.left, input.right);
    let words = s.controls.controller.words();
    assert_eq!(actual, [[words[7], words[8]], [words[9], words[10]]].map(|pair| pair.map(f32::from_bits)));
    s.tick_with_sticks(input, input, Controls::default()).unwrap();
    assert!(s.fine_sticks.is_none());
}
