//! Full-session regression rides using the exported simulation package and raw controller packets.
use super::*;

fn session() -> Session {
    let bytes = std::fs::read(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../assets/simulations/skate-simulation/skate-simulation.skatepack"
    ))
    .expect("committed exported skating simulation package");
    let floor = vec![
        [[-500., 0., -500.], [-500., 0., 500.], [500., 0., 500.]],
        [[-500., 0., -500.], [500., 0., 500.], [500., 0., -500.]],
    ];
    Session::from_resources(
        &crate::PreparedResources::from_bytes(bytes).unwrap(),
        floor,
        vec![1 << 7; 2],
        vec![],
        [0.; 3],
        0.,
    )
    .expect("complete session from exported resources")
}

fn assert_pose(pose: &Pose) {
    assert!(pose.root.is_finite());
    assert!(pose.velocity.is_finite());
    assert!(!pose.bones.is_empty());
    assert_eq!(pose.bones.len(), pose.names.len());
    assert_eq!(pose.bones.len(), pose.parents.len());
    assert_eq!(pose.board.len(), 7);
    assert!(pose.bones.iter().chain(&pose.board).all(|bone| bone.is_finite()));
    let (position, basis, fov) = pose.camera.expect("solved camera frame");
    assert!(position.is_finite() && basis.is_finite() && fov.is_finite());
}

fn assert_pose_board_matches_legacy(session: &Session) {
    let board = &session.physics.board;
    let physical_board = crate::animation::native_matrix(super::super::solve::deck_frame(board));
    let board_delta =
        session.skater.recovery.shown_board().map_or(Mat4::IDENTITY, |shown| shown * physical_board.inverse());
    let expected_board: Vec<_> = board
        .part_transforms()
        .iter()
        .map(|t| {
            board_delta
                * Mat4::from_mat3_translation(
                    Mat3::from_cols_array_2d(&t.basis.columns),
                    Vec3::new(t.translation.x, t.translation.y, t.translation.z),
                )
        })
        .collect();
    let parts = board.part_transforms();
    let center =
        parts[..4].iter().map(|t| Vec3::new(t.translation.x, t.translation.y, t.translation.z)).sum::<Vec3>() * 0.25;
    let up = Vec3::from_array(parts[crate::core::physics::board::BodyId::Deck.index()].basis.columns[1]);
    let expected_ground = center - up * session.physics.settings.wheel_radius;
    let pose = session.pose();
    for (actual, expected) in pose.board.iter().zip(&expected_board) {
        assert_eq!(actual.to_cols_array().map(f32::to_bits), expected.to_cols_array().map(f32::to_bits));
    }
    assert_eq!(pose.board.len(), expected_board.len());
    assert_eq!(pose.ground_point.to_array().map(f32::to_bits), expected_ground.to_array().map(f32::to_bits));
}

#[test]
fn shared_pose_board_parts_match_legacy_separate_computations() {
    let mut session = session();
    session.activate_on_foot([7., 0., -11.], 0.7).unwrap();
    assert_pose_board_matches_legacy(&session);
    session.activate([7., 0., -11.], 0.7).unwrap();
    assert_pose_board_matches_legacy(&session);
    session.launch([2., 0., 5.]);
    for tick in 0..120 {
        session.tick(Controls { buttons: if tick < 45 { 0x1000 } else { 0 }, ..Default::default() }).unwrap();
        assert_pose_board_matches_legacy(&session);
    }
    session.request_bail().unwrap();
    let mut saw_unprepared_recovery = false;
    for _ in 0..900 {
        session.tick(Controls::default()).unwrap();
        saw_unprepared_recovery |= session.skater.recovery.shown_board().is_some();
        assert_pose_board_matches_legacy(&session);
        if saw_unprepared_recovery && session.skater.recovery.shown_board().is_none() {
            break;
        }
    }
    assert!(saw_unprepared_recovery, "test must cover the shown-board recovery delta");
}

#[test]
fn both_stances_push_ollie_and_land_from_raw_packets() {
    let mut session = session();
    for goofy in [false, true] {
        session.configure("normal", goofy, 0.5).unwrap();
        let initial = session.activate([0.; 3], 0.).unwrap();
        let mut saw_air = false;
        let mut changed_pose = false;
        let mut maximum_speed = 0.0f32;
        // The original deterministic check sent these packets twice each at 30 Hz.
        for tick in 0..480 {
            let frame = tick / 2;
            let right = if (100..112).contains(&frame) {
                [0, -32767]
            } else if frame == 112 {
                [0, 32767]
            } else {
                [0; 2]
            };
            session
                .tick(Controls {
                    buttons: if (30..95).contains(&frame) { 0x1000 } else { 0 },
                    right,
                    ..Default::default()
                })
                .unwrap();
            let pose = session.pose();
            assert_pose(&pose);
            assert_eq!(pose.tick, initial.tick + tick + 1);
            saw_air |= pose.state.contains("Air");
            changed_pose |= pose.bones != initial.bones;
            maximum_speed = maximum_speed.max(pose.velocity.x.hypot(pose.velocity.z));
        }
        let final_pose = session.pose();
        assert!(maximum_speed > 3., "goofy={goofy}: {maximum_speed} m/s");
        assert!(saw_air, "goofy={goofy}: the raw right-stick gesture never launched");
        assert!(changed_pose, "the animation graphs must publish moving bones");
        assert_eq!(final_pose.state, "PhysicsGround", "goofy={goofy}");
        assert!(final_pose.root.w_axis.y.abs() < 1., "rider must return to the floor");
    }
}

#[test]
fn deliberate_bail_recovers_and_running_remount_uses_new_position() {
    let mut session = session();
    session.configure("normal", false, 0.5).unwrap();
    session.activate([0.; 3], 0.).unwrap();
    let mut saw_wipeout = false;
    for tick in 0..600 {
        let frame = tick / 2;
        let chord = (20..35).contains(&frame);
        session
            .tick(Controls {
                buttons: if chord {
                    0xc0
                } else if (110..115).contains(&frame) {
                    0x1000
                } else {
                    0
                },
                triggers: if chord { [255; 2] } else { [0; 2] },
                ..Default::default()
            })
            .unwrap();
        let pose = session.pose();
        assert_pose(&pose);
        saw_wipeout |= pose.state.contains("Wipeout");
    }
    assert!(saw_wipeout, "the native bail chord must enter a wipeout");
    assert_eq!(session.pose().state, "PhysicsGround");

    for spawn in [[15., 0., 10.], [-12., 0., -8.]] {
        session.suspend_input();
        let mounted = session.activate(spawn, 0.).unwrap();
        assert!((mounted.root.w_axis.x - spawn[0]).hypot(mounted.root.w_axis.z - spawn[2]) < 0.02);
        session.launch([0., 0., 4.2]);
        assert_eq!(session.pose().velocity, Vec3::new(0., 0., 4.2));
        session.tick(Controls::default()).unwrap();
        let moved = session.pose();
        assert_pose(&moved);
        assert!(moved.velocity.z > 3.5);
        assert!((0.0..0.25).contains(&(moved.root.w_axis.z - spawn[2])));
    }
}

#[test]
fn grab_and_deliberate_transfer_are_separate_raw_inputs() {
    let mut session = session();
    session.activate([0.; 3], 0.).unwrap();
    for (input, transfer) in [
        (Controls { triggers: [0, 255], ..Default::default() }, false),
        (Controls { buttons: TRANSFER, ..Default::default() }, true),
        (Controls::default(), false),
    ] {
        session.tick(input).unwrap();
        assert_eq!(session.physics.transfer, Some(transfer));
        assert_pose(&session.pose());
    }
}
