//! Package-backed local bail recovery and real slope clearance regressions.
use super::*;
fn session(slope: f32) -> Session {
    let bytes = std::fs::read(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../assets/simulations/skate-simulation/skate-simulation.skatepack"
    ))
    .unwrap();
    let floor = vec![
        [[-500., -500. * slope, -500.], [-500., 500. * slope, 500.], [500., 500. * slope, 500.]],
        [[-500., -500. * slope, -500.], [500., 500. * slope, 500.], [500., -500. * slope, -500.]],
    ];
    let prepared = Session::preload(bytes).unwrap();
    Session::from_resources(&prepared, floor, vec![129; 2], vec![], [0.; 3], 0.).unwrap()
}
#[test]
fn local_recovery_moving_and_sloped_bails_ride_away_without_checkpoint() {
    let mut s = session(0.);
    for slope in [0., 0.15, -0.15] {
        let p = [50., 40. * slope, 40.];
        let floor = vec![
            [[-500., -500. * slope, -500.], [-500., 500. * slope, 500.], [500., 500. * slope, 500.]],
            [[-500., -500. * slope, -500.], [500., 500. * slope, 500.], [500., -500. * slope, -500.]],
        ];
        let collision = s.collision_builder().build(floor, vec![129; 2], vec![]).unwrap();
        s.install_collision(collision).unwrap();
        s.activate(p, 0.).unwrap();
        for _ in 0..30 {
            s.tick(Controls::default()).unwrap();
        }
        s.launch([0., 8. * slope, 8.]);
        s.request_bail().unwrap();
        let start = s.pose();
        let mut previous = start.root.w_axis.truncate();
        let mut saw_getup = false;
        let mut ground_ticks = 0;
        for tick in 0..900 {
            s.tick(Controls { buttons: if tick > 180 { 0x1000 } else { 0 }, ..Default::default() }).unwrap();
            let pose = s.pose();
            let root = pose.root.w_axis.truncate();
            assert!(root.is_finite() && pose.bones.iter().all(|m| m.is_finite()));
            assert_ne!(pose.physical_state, 702, "checkpoint recovery is not a local get-up");
            assert!(root.distance(previous) < 1.5, "slope={slope} tick={tick} jumped {:?}->{root:?}", previous);
            assert!(root.x > 40., "returned to historical spawn");
            previous = root;
            saw_getup |= s.recovering();
            if saw_getup
                && !s.recovering()
                && pose.physical_state == 100
                && pose.surface.wheels >= 2
                && pose.velocity.length() > 1.
            {
                ground_ticks += 1;
            } else {
                ground_ticks = 0;
            }
            if ground_ticks >= 30 {
                break;
            }
            if tick % 60 == 0 {
                eprintln!(
                    "recovery slope={slope} tick={tick} state={} recovering={} root={root:?} speed={} quiet={} elapsed={}",
                    pose.state,
                    s.recovering(),
                    pose.velocity.length(),
                    s.skater.recovery.quiet_time(),
                    s.skater.recovery.elapsed_time()
                );
            }
        }
        assert!(saw_getup && ground_ticks >= 30, "slope={slope} did not ride away: {}", s.pose().state);
    }
}

#[test]
fn local_bail_restores_the_last_shown_assembly_and_high_speed_momentum() {
    let mut s = session(0.);
    s.activate([80., 0., 30.], 0.).unwrap();
    for _ in 0..30 {
        s.tick(Controls::default()).unwrap();
    }
    s.launch([0., -18., 40.]);
    let shown = s.pose();
    // Represents a solver frame rejected by the host; never display its root.
    s.skater.animated_skeleton.roots.animation_to_world[3] = [1000., -200., -1000., 0.];
    s.physics.board.bodies_mut()[6].rates.linear_velocity.x = f32::NAN;
    s.bail_in_place(&shown).unwrap();
    let pose = s.pose();
    assert_eq!(pose.physical_state, 300);
    assert!(pose.root.abs_diff_eq(shown.root, 1e-5));
    assert!(pose.velocity.abs_diff_eq(shown.velocity, 1e-5));
    assert!(pose.bones.iter().zip(&shown.bones).all(|(a, b)| a.abs_diff_eq(*b, 1e-5)));
    assert!(s.skater.skeleton.bodies().iter().all(|b| b.rates.linear_velocity.z == 40.));
    let mut previous = pose.root.w_axis.truncate();
    for tick in 0..60 {
        s.tick(Controls::default()).unwrap();
        let pose = s.pose();
        let root = pose.root.w_axis.truncate();
        assert!(
            root.is_finite() && root.distance(previous) < 2.,
            "tick={tick} previous={previous:?} root={root:?} velocity={:?}",
            pose.velocity
        );
        assert_ne!(pose.physical_state, 702);
        previous = root;
    }
}

#[test]
fn native_south_request_starts_safe_local_get_up_before_automatic_quiet_dwell() {
    let mut automatic = session(0.);
    let mut manual = session(0.);
    for s in [&mut automatic, &mut manual] {
        s.activate([50., 0., 40.], 0.).unwrap();
        for _ in 0..30 {
            s.tick(Controls::default()).unwrap();
        }
        s.launch([0., 0., 8.]);
        s.request_bail().unwrap();
    }
    let mut manual_request_seen = false;
    let mut manual_start = None;
    let mut automatic_start = None;
    for tick in 0..360 {
        automatic.tick(Controls::default()).unwrap();
        manual.tick(Controls { buttons: if tick >= 90 { 0x1000 } else { 0 }, ..Default::default() }).unwrap();
        let native = &manual.skater.wipeout_state.state;
        manual_request_seen |=
            native.reset_ever && native.recovery_eligible && !native.ignore_reset && !native.prevent_manual;
        if tick >= 90 && (tick % 5 == 0 || manual.recovering()) && manual_start.is_none() {
            eprintln!(
                "manual recovery tick={tick} elapsed={} quiet={} requested={} native_reset={} eligible={} over={} ignore={} prevent={} auto_recovering={}",
                manual.skater.recovery.elapsed_time(),
                manual.skater.recovery.quiet_time(),
                manual.skater.recovery.requested,
                native.reset_ever,
                native.recovery_eligible,
                native.over,
                native.ignore_reset,
                native.prevent_manual,
                automatic.recovering()
            );
        }
        for s in [&automatic, &manual] {
            assert_ne!(s.pose().physical_state, 702);
            assert!(s.pose().root.is_finite());
            assert!(s.pose().root.w_axis.x > 40., "get-up returned to a checkpoint");
        }
        if manual.recovering() && manual_start.is_none() {
            assert!(manual.skater.recovery.elapsed_time() > 1.6);
            assert!(manual.skater.recovery.quiet_time() > 0.);
            manual_start = Some(tick);
        }
        if automatic.recovering() && automatic_start.is_none() {
            automatic_start = Some(tick);
        }
        if manual_start.is_some() && automatic_start.is_some() {
            break;
        }
    }
    assert!(manual_request_seen, "raw South never reached the native recovery request");
    assert!(manual_start.is_some() && automatic_start.is_some());
    assert!(manual_start < automatic_start, "manual={manual_start:?} automatic={automatic_start:?}");
}
