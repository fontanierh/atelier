use super::*;

#[test]
fn private_stock_camera_loads_every_graph_operation_and_shot_dependency() {
    let root = &crate::test_support::resources();
    let camera = CameraRuntime::load(root).expect("complete normal stock camera assets");
    assert!(camera.frame.is_none());
}

#[cfg(all(not(target_family = "wasm"), panic = "unwind"))]
#[test]
fn only_the_exceptional_angle_payload_becomes_a_camera_error() {
    use crate::core::camera::ExceptionalAngleConversion;
    use std::panic::{catch_unwind, panic_any};
    assert_eq!(contain_exceptional_angle::<u8>(Ok(Ok(7))), Ok(7));
    assert_eq!(contain_exceptional_angle::<u8>(Ok(Err("ordinary".into()))), Err("ordinary".into()));
    let typed = catch_unwind(|| panic_any(ExceptionalAngleConversion { angle_bits: 0x7fc0_0001 })).map(|()| Ok(0u8));
    let error = contain_exceptional_angle(typed).unwrap_err();
    assert!(error.contains("0x7fc00001"), "{error}");
    // Any other panic leaves the boundary with its own payload.
    let other = catch_unwind(|| panic!("unrelated")).map(|()| Ok(0u8));
    let resumed = catch_unwind(std::panic::AssertUnwindSafe(|| contain_exceptional_angle(other))).unwrap_err();
    assert_eq!(resumed.downcast_ref::<&str>(), Some(&"unrelated"));
    #[derive(Debug, PartialEq)]
    struct Unrelated(u32);
    let other = catch_unwind(|| panic_any(Unrelated(3))).map(|()| Ok(0u8));
    let resumed = catch_unwind(std::panic::AssertUnwindSafe(|| contain_exceptional_angle(other))).unwrap_err();
    assert_eq!(resumed.downcast_ref::<Unrelated>(), Some(&Unrelated(3)));
}
