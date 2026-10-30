//! Marker bindings travel through the same raw packet and simulation time as gameplay.
use super::*;
#[test]
fn raw_lb_place_and_timed_return_preserve_native_marker_controls() {
    let bytes = std::fs::read(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../assets/simulations/skate-simulation/skate-simulation.skatepack"
    ))
    .unwrap();
    let floor = vec![
        [[-100., 0., -100.], [-100., 0., 100.], [100., 0., 100.]],
        [[-100., 0., -100.], [100., 0., 100.], [100., 0., -100.]],
    ];
    let mut s = Session::from_resources(
        &crate::PreparedResources::from_bytes(bytes).unwrap(),
        floor,
        vec![1 << 7; 2],
        vec![],
        [0.; 3],
        0.,
    )
    .unwrap();
    s.activate([0.; 3], 0.).unwrap();
    for _ in 0..120 {
        s.tick(Controls::default()).unwrap();
    }
    s.tick(Controls { buttons: 0x0102, ..Default::default() }).unwrap();
    assert!(s.markers.marker_transform().is_some(), "LB+DPadDown must place through native Pad");
    assert_eq!(s.physics.transfer, Some(false), "marker LB is not a transfer");
    assert_eq!(s.marker_status().placements, 1);
    for _ in 0..10 {
        s.tick(Controls { buttons: 0x0102, ..Default::default() }).unwrap();
    }
    assert_eq!(s.marker_status().placements, 1, "held Down cannot repeat placement");
    let marker = s.markers.marker_transform().unwrap();
    s.tick(Controls::default()).unwrap();
    let mut destination = marker;
    destination[3][0] += 12.;
    s.skater.travel_to_on_board(destination, true).unwrap();
    for _ in 0..10 {
        s.tick(Controls::default()).unwrap();
    }
    let far = s.pose().root.w_axis.truncate();
    for _ in 0..6 {
        s.tick(Controls { buttons: 0x0101, ..Default::default() }).unwrap();
    }
    assert!((s.pose().root.w_axis.truncate() - far).length() < 2., "short hold cannot return");
    for _ in 0..30 {
        s.tick(Controls { buttons: 0x0101, ..Default::default() }).unwrap();
    }
    assert_eq!(s.marker_status().returns, 1);
    for _ in 0..60 {
        s.tick(Controls { buttons: 0x0101, ..Default::default() }).unwrap();
    }
    assert_eq!(s.marker_status().returns, 1, "held Up cannot repeat relocation");
    let position = s.pose().root.w_axis.truncate();
    assert!((position.x - marker[3][0]).abs() < 1., "hold timer must advance per raw tick: {position:?}");
}
