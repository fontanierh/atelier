//! Full exported-package and fixed-step session smoke regression.
use super::*;
fn bytes() -> Vec<u8> {
    std::fs::read(
        std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../assets/simulations/skate-simulation/skate-simulation.skatepack"),
    )
    .expect("committed exported simulation")
}
#[test]
fn current_export_drives_complete_fixed_step_session() {
    let bytes = bytes();
    let triangles = vec![
        [[-100., 0., -100.], [-100., 0., 100.], [100., 0., 100.]],
        [[-100., 0., -100.], [100., 0., 100.], [100., 0., -100.]],
    ];
    let mut session =
        Session::from_resources(&Session::preload(bytes).unwrap(), triangles, vec![1 << 7; 2], vec![], [0.; 3], 0.)
            .unwrap();
    let reference = session.reference_pose().unwrap();
    assert!(!reference.is_empty());
    let initial = session.activate([0.; 3], 0.).unwrap();
    assert_eq!(initial.bones.len(), reference.len());
    assert_eq!(initial.bones.len(), initial.names.len());
    assert_eq!(initial.bones.len(), initial.parents.len());
    assert_eq!(initial.board.len(), 7);
    assert!((session.period() - 1. / 60.).abs() < 1e-6);
    for tick in 0..120 {
        session.tick(Controls { buttons: if tick % 30 < 15 { 0x1000 } else { 0 }, ..Default::default() }).unwrap();
    }
    let pose = session.pose();
    assert!(pose.tick >= initial.tick + 120);
    assert!(pose.root.is_finite());
    assert!(pose.bones.iter().all(|m| m.is_finite()));
    assert!(pose.board.iter().all(|m| m.is_finite()));
    assert!(pose.velocity.is_finite());
    assert!(!pose.state.is_empty());
    let (score, reward, _) = session.score();
    assert!(score.is_finite() && reward.is_finite());
}
#[test]
fn malformed_package_is_reported_before_session_creation() {
    assert!(Session::preload(b"not a package".to_vec()).is_err());
}

#[test]
fn current_export_retains_complete_animation_banks_and_compact_tracks() {
    let bytes = bytes();
    let resources = crate::resources::Resources::from_bytes(bytes).unwrap();
    let frames = &resources.animation.evaluator.frames;
    assert_eq!(frames.clip_count(), 3324);
    assert_eq!(resources.metadata.sources().len(), 2);
    for name in ["KEEPDEFAULTANIM", "R_PUSHLSP_HSTR_N_0_CYC1"] {
        let clip = frames.clip(name).unwrap();
        assert!(clip.frame_count() > 0);
        assert_eq!(clip.bone_count(), frames.bone_names.len());
        assert!((0..clip.bone_count()).flat_map(|bone| clip.key(0, bone)).all(|w| f32::from_bits(w).is_finite()));
        assert_eq!(clip.source_offset, resources.metadata.clip(name).unwrap().source_offset);
    }
}

#[test]
fn prepared_resources_reuse_the_same_immutable_assets_across_sessions() {
    let prepared = Session::preload(bytes()).unwrap();
    let cloned = prepared.clone();
    assert!(std::sync::Arc::ptr_eq(&prepared.0, &cloned.0));
    fn send_sync<T: Send + Sync>() {}
    send_sync::<PreparedResources>();
    let mut first = Session::from_resources(&prepared, vec![], vec![], vec![], [0.; 3], 0.).unwrap();
    let mut second = Session::from_resources(&cloned, vec![], vec![], vec![], [0.; 3], 0.).unwrap();
    for _ in 0..4 {
        first.tick(Controls::default()).unwrap();
        second.tick(Controls::default()).unwrap();
    }
    assert_eq!(
        first.pose().root.to_cols_array().map(f32::to_bits),
        second.pose().root.to_cols_array().map(f32::to_bits)
    );
}
