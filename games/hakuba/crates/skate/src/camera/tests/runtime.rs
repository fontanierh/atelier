use super::*;

#[test]
fn private_stock_camera_loads_every_graph_operation_and_shot_dependency() {
    let root = &crate::test_support::resources();
    let camera = CameraRuntime::load(root).expect("complete normal stock camera assets");
    assert!(camera.frame.is_none());
}
