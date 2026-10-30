//! Actual Bevy keyboard/controller input reaches the same native marker owner and canonical saved settings.
use super::super::{SkateStatus, ride_input};
use super::*;
use bevy::input::{gamepad::RawGamepadEvent, keyboard::Key, mouse::AccumulatedMouseMotion};
fn session() -> Session {
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
        vec![128; 2],
        vec![],
        [0.; 3],
        0.,
    )
    .unwrap();
    s.activate([0.; 3], 0.).unwrap();
    for _ in 0..120 {
        s.tick(Controls::default()).unwrap();
    }
    s
}
fn app() -> (App, Entity) {
    let mut app = App::new();
    app.init_resource::<Ride>()
        .init_resource::<Places>()
        .init_resource::<RideInput>()
        .init_resource::<Time<Real>>()
        .init_resource::<ButtonInput<KeyCode>>()
        .init_resource::<ButtonInput<MouseButton>>()
        .init_resource::<AccumulatedMouseMotion>()
        .init_resource::<SkateStatus>()
        .init_resource::<Settings>()
        .add_message::<KeyboardInput>()
        .add_message::<RawGamepadEvent>()
        .add_message::<ride_input::StickReading>()
        .add_systems(Update, (ride_input::read, read).chain());
    let pad = app.world_mut().spawn(Gamepad::default()).id();
    app.world_mut().resource_mut::<Ride>().session = Some(session());
    (app, pad)
}
fn step(app: &mut App, n: usize) {
    app.update();
    for _ in 0..n {
        let raw = app.world().resource::<RideInput>().packet;
        let packet = packet(&mut app.world_mut().resource_mut::<Places>(), raw);
        app.world_mut().resource_mut::<Ride>().session.as_mut().unwrap().tick(packet).unwrap();
        let session = app.world_mut().resource_mut::<Ride>().session.take().unwrap();
        app.world_mut().resource_scope(|world, mut places: Mut<Places>| {
            let mut settings = world.resource_mut::<Settings>();
            publish(&session, &mut places, &mut settings);
        });
        app.world_mut().resource_mut::<Ride>().session = Some(session);
    }
    app.world_mut().resource_mut::<ButtonInput<KeyCode>>().clear();
    let mut query = app.world_mut().query::<&mut Gamepad>();
    for mut pad in query.iter_mut(app.world_mut()) {
        pad.digital_mut().clear();
    }
}
fn key(app: &mut App, key: KeyCode, pressed: bool) {
    let mut keys = app.world_mut().resource_mut::<ButtonInput<KeyCode>>();
    if pressed {
        keys.press(key);
    } else {
        keys.release(key);
    }
}
fn pad(app: &mut App, pad: Entity, button: GamepadButton, pressed: bool) {
    let mut p = app.world_mut().get_mut::<Gamepad>(pad).unwrap();
    if pressed {
        p.digital_mut().press(button);
    } else {
        p.digital_mut().release(button);
    }
}
#[test]
fn real_keyboard_places_once_saves_names_reloads_and_returns_only_after_hold() {
    let (mut app, _) = app();
    key(&mut app, KeyCode::KeyM, true);
    key(&mut app, KeyCode::ArrowDown, true);
    step(&mut app, 1);
    let marker = app.world().resource::<Ride>().session.as_ref().unwrap().marker().unwrap();
    let placements = app.world().resource::<Places>().status.placements;
    assert_eq!(placements, 1);
    step(&mut app, 30);
    assert_eq!(app.world().resource::<Places>().status.placements, placements);
    key(&mut app, KeyCode::KeyM, false);
    key(&mut app, KeyCode::ArrowDown, false);
    step(&mut app, 1);
    key(&mut app, KeyCode::KeyP, true);
    step(&mut app, 1);
    key(&mut app, KeyCode::KeyP, false);
    key(&mut app, KeyCode::KeyN, true);
    step(&mut app, 12); // Native release then press, each crossing three-call edge suppression.
    key(&mut app, KeyCode::KeyN, false);
    assert!(app.world().resource::<Places>().editing.is_some());
    for _ in 0.."Marker 1".len() {
        app.world_mut().write_message(KeyboardInput {
            key_code: KeyCode::Backspace,
            logical_key: Key::Backspace,
            state: ButtonState::Pressed,
            text: None,
            repeat: false,
            window: Entity::PLACEHOLDER,
        });
    }
    app.world_mut().write_message(KeyboardInput {
        key_code: KeyCode::KeyM,
        logical_key: Key::Character("My bridge line".into()),
        state: ButtonState::Pressed,
        text: Some("My bridge line".into()),
        repeat: false,
        window: Entity::PLACEHOLDER,
    });
    step(&mut app, 1);
    key(&mut app, KeyCode::Enter, true);
    step(&mut app, 1);
    step(&mut app, 30);
    assert_eq!(app.world().resource::<RideInput>().packet.buttons, 0, "confirmation must release before return");
    key(&mut app, KeyCode::Enter, false);
    step(&mut app, 1);
    let settings = app.world().resource::<Settings>();
    assert_eq!(settings.skate_places.saved[0].name, "My bridge line");
    let encoded = serde_json::to_string(settings).unwrap();
    let reloaded: Settings = serde_json::from_str(&encoded).unwrap();
    let mut remount = session();
    restore(&mut remount, &reloaded).unwrap();
    assert_eq!(remount.marker().unwrap(), native(reloaded.skate_places.marker.unwrap()));
    // A new physical session is the host's stow/remount boundary. Retain only canonical Settings.
    remount.activate([12., 0., 0.], 0.).unwrap();
    restore(&mut remount, &reloaded).unwrap();
    app.world_mut().resource_mut::<Ride>().session = Some(remount);
    app.world_mut().insert_resource(reloaded);
    key(&mut app, KeyCode::Enter, true);
    step(&mut app, 6);
    assert_eq!(app.world().resource::<Places>().status.returns, 0);
    assert!(app.world().resource::<Places>().status.progress > 0.);
    step(&mut app, 40);
    assert_eq!(app.world().resource::<Places>().status.returns, 1);
    let position = app.world().resource::<Ride>().session.as_ref().unwrap().pose().root.w_axis.truncate();
    assert!((position.x - marker.transform[3][0]).abs() < 1.);
    step(&mut app, 120);
    assert_eq!(app.world().resource::<Places>().status.returns, 1, "held return fires once");
}
#[test]
fn selected_controller_places_opens_bar_edits_name_and_transfer_is_separate() {
    let (mut app, p) = app();
    pad(&mut app, p, GamepadButton::LeftTrigger, true);
    pad(&mut app, p, GamepadButton::DPadDown, true);
    step(&mut app, 1);
    assert_eq!(app.world().resource::<Places>().status.placements, 1);
    assert_eq!(app.world().resource::<RideInput>().packet.buttons & crate::TRANSFER, 0);
    pad(&mut app, p, GamepadButton::DPadDown, false);
    step(&mut app, 1);
    pad(&mut app, p, GamepadButton::DPadLeft, true);
    step(&mut app, 1);
    assert!(app.world().resource::<Places>().open);
    pad(&mut app, p, GamepadButton::DPadLeft, false);
    pad(&mut app, p, GamepadButton::LeftTrigger, false);
    step(&mut app, 1);
    pad(&mut app, p, GamepadButton::North, true);
    step(&mut app, 12); // Native release/press comes from per-tick modal packet publication.
    assert!(app.world().resource::<Places>().editing.is_some());
    pad(&mut app, p, GamepadButton::North, false);
    step(&mut app, 1);
    pad(&mut app, p, GamepadButton::DPadRight, true);
    step(&mut app, 1);
    pad(&mut app, p, GamepadButton::North, true);
    step(&mut app, 1);
    let name = app.world().resource::<Places>().editing.as_ref().unwrap().name.clone();
    assert!(name.ends_with('B'));
    pad(&mut app, p, GamepadButton::South, true);
    step(&mut app, 1);
    assert_eq!(app.world().resource::<Settings>().skate_places.saved[0].name, name);
    assert_eq!(app.world().resource::<RideInput>().packet.buttons & 0x1000, 0, "saving must not push/recover");
    pad(&mut app, p, GamepadButton::South, false);
    pad(&mut app, p, GamepadButton::North, false);
    pad(&mut app, p, GamepadButton::DPadRight, false);
    step(&mut app, 4);
    let saved = app.world().resource::<Settings>().skate_places.selected().unwrap().marker;
    app.world_mut().resource_mut::<Ride>().session.as_mut().unwrap().activate([12., 0., 0.], 0.).unwrap();
    pad(&mut app, p, GamepadButton::South, true);
    step(&mut app, 6);
    assert_eq!(app.world().resource::<Places>().status.returns, 0, "short controller hold cannot travel");
    step(&mut app, 40);
    assert_eq!(app.world().resource::<Places>().status.returns, 1);
    let position = app.world().resource::<Ride>().session.as_ref().unwrap().pose().root.w_axis.truncate();
    assert!((position.x - saved.transform[3][0]).abs() < 1.);
    step(&mut app, 120);
    assert_eq!(app.world().resource::<Places>().status.returns, 1, "held controller return fires once");
}
#[test]
fn raw_transfer_and_airborne_place_cannot_create_a_marker() {
    let mut s = session();
    s.tick(Controls { buttons: crate::TRANSFER, ..default() }).unwrap();
    assert!(s.marker().is_none());
    s.activate([0., 20., 0.], 0.).unwrap();
    s.tick(Controls { buttons: 0x0102, ..default() }).unwrap();
    assert!(s.marker().is_none());
    assert!(!s.marker_status().can_place);
    let invalid = MarkerSnapshot { transform: [[f32::NAN; 4]; 4], on_board: true, foot_forward: false };
    assert!(s.restore_marker(Some(invalid)).is_err());
    assert!(s.marker().is_none());
}
