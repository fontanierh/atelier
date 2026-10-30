//! Raw skating input. One selected controller owns analog input; keyboard/mouse provides the same native packets.
#[path = "ride_input/history.rs"]
mod history;
use crate::{Controls, TRANSFER};
use bevy::input::gamepad::{GamepadAxis, RawGamepadEvent};
use bevy::input::mouse::AccumulatedMouseMotion;
use bevy::prelude::*;
pub use history::StickReading;

#[derive(Resource, Default)]
pub struct RideInput {
    pub packet: Controls,
    pub toggle: bool,
    pub recover: bool,
    pub stow: bool,
    active_pad: Option<Entity>,
    history: history::StickHistory,
    release_pop: bool,
    recovery_pending: bool,
    mouse_stick: Vec2,
    raw_left: Vec2,
    raw_right: Vec2,
    raw_triggers: [f32; 2],
}

pub fn read(
    mut input: ResMut<RideInput>,
    real_time: Res<Time<Real>>,
    mut fine_readings: MessageReader<StickReading>,
    keys: Res<ButtonInput<KeyCode>>,
    mouse: Res<ButtonInput<MouseButton>>,
    motion: Res<AccumulatedMouseMotion>,
    pads: Query<(Entity, &Gamepad)>,
    mut events: MessageReader<RawGamepadEvent>,
    status: Res<super::SkateStatus>,
    settings: Res<hakuba_settings::Settings>,
) {
    let now = real_time.elapsed_secs_f64();
    if input.active_pad.is_none_or(|e| !pads.contains(e)) {
        input.history.clear();
        input.active_pad = pads.iter().min_by_key(|(entity, _)| entity.to_bits()).map(|(entity, _)| entity);
        if let Some((_, pad)) = input.active_pad.and_then(|entity| pads.get(entity).ok()) {
            input.raw_left = pad.left_stick();
            input.raw_right = pad.right_stick();
            input.raw_triggers = [
                pad.get(GamepadButton::LeftTrigger2).unwrap_or(0.),
                pad.get(GamepadButton::RightTrigger2).unwrap_or(0.),
            ];
        }
    }
    for event in events.read() {
        match event {
            RawGamepadEvent::Axis(event) if Some(event.gamepad) == input.active_pad => match event.axis {
                GamepadAxis::LeftStickX => input.raw_left.x = event.value,
                GamepadAxis::LeftStickY => input.raw_left.y = event.value,
                GamepadAxis::RightStickX => input.raw_right.x = event.value,
                GamepadAxis::RightStickY => input.raw_right.y = event.value,
                _ => {}
            },
            RawGamepadEvent::Button(event) if Some(event.gamepad) == input.active_pad => match event.button {
                GamepadButton::LeftTrigger2 => input.raw_triggers[0] = event.value,
                GamepadButton::RightTrigger2 => input.raw_triggers[1] = event.value,
                _ => {}
            },
            _ => {}
        }
    }
    let axis = |v: f32| (v.clamp(-1.0, 1.0) * 32767.0).round() as i16;
    if input.active_pad.is_some() {
        let left = input.raw_left.to_array().map(axis);
        let right = input.raw_right.to_array().map(axis);
        input.history.observe(now, now, left, right);
    }
    for reading in fine_readings.read() {
        if Some(reading.gamepad) == input.active_pad {
            input.history.observe(reading.captured_at, now, reading.left, reading.right);
        }
    }
    let key = |code| if keys.pressed(code) { 1. } else { 0. };
    let forward = if keys.pressed(KeyCode::ShiftLeft) || keys.pressed(KeyCode::ShiftRight) { 1.0 } else { 0.0 };
    let riding_y = if status.on_foot { 0.0 } else { forward - key(KeyCode::KeyC) };
    let mut left = Vec2::new(key(KeyCode::KeyD) - key(KeyCode::KeyA), riding_y);
    let mut right =
        Vec2::new(key(KeyCode::ArrowRight) - key(KeyCode::ArrowLeft), key(KeyCode::ArrowUp) - key(KeyCode::ArrowDown));
    let mut buttons = 0;
    if keys.pressed(KeyCode::KeyW) {
        buttons |= 0x1000;
    } // push: South
    if keys.pressed(KeyCode::KeyS) {
        buttons |= 0x2000;
    } // footbrake: East
    if keys.pressed(KeyCode::KeyB) {
        buttons |= 0x0040 | 0x0080;
    } // deliberate native bail chord
    if keys.pressed(KeyCode::KeyR) {
        buttons |= TRANSFER;
    }
    if keys.pressed(KeyCode::KeyT) {
        buttons |= 0x0200;
    }
    let mut triggers = [(key(KeyCode::KeyQ) * 255.) as u8, (key(KeyCode::KeyE) * 255.) as u8];
    if keys.pressed(KeyCode::KeyB) {
        triggers = [255; 2];
    }
    let mut toggle = keys.just_pressed(KeyCode::KeyV);
    let mut recover = keys.just_pressed(KeyCode::Enter);
    if keys.pressed(KeyCode::Space) {
        right.y = -1.;
    }
    // Retain the release through a simulation tick; render-rate sampling must not lose a pop.
    if keys.just_released(KeyCode::Space) {
        input.release_pop = true;
    }
    if input.release_pop {
        right.y = 1.;
    }
    if mouse.pressed(MouseButton::Left) {
        input.mouse_stick = (input.mouse_stick
            + Vec2::new(motion.delta.x, -motion.delta.y) * settings.skate.mouse_flick / 70.)
            .clamp_length_max(1.);
        right = input.mouse_stick;
    } else {
        input.mouse_stick = Vec2::ZERO;
    }
    if let Some((_, pad)) = input.active_pad.and_then(|e| pads.get(e).ok()) {
        let l = input.raw_left;
        let r = input.raw_right;
        if l.length_squared() > 0.0001 {
            left = l;
        }
        if r.length_squared() > 0.0001 {
            right = r;
        }
        for (button, bit) in [
            (GamepadButton::South, 0x1000),
            (GamepadButton::East, 0x2000),
            (GamepadButton::West, 0x4000),
            (GamepadButton::North, 0x8000),
            (GamepadButton::LeftTrigger, 0x0100),
            (GamepadButton::RightTrigger, 0x0200),
            (GamepadButton::LeftThumb, 0x0040),
            (GamepadButton::RightThumb, 0x0080),
            (GamepadButton::DPadUp, 0x0001),
            (GamepadButton::DPadDown, 0x0002),
            (GamepadButton::DPadLeft, 0x0004),
            (GamepadButton::DPadRight, 0x0008),
        ] {
            if pad.pressed(button) {
                buttons |= bit;
            }
        }
        for i in 0..2 {
            triggers[i] = triggers[i].max((input.raw_triggers[i].clamp(0., 1.) * 255.).round() as u8);
        }
        if pad.pressed(GamepadButton::LeftTrigger) && input.raw_left.y > 0.5 {
            buttons |= TRANSFER;
        }
        toggle |= pad.just_pressed(GamepadButton::Select);
        recover |= pad.just_pressed(GamepadButton::Start);
    }
    if status.on_foot {
        left.y = (key(KeyCode::KeyW) - key(KeyCode::KeyS)).clamp(-1., 1.);
        buttons &= !0x3000;
        if keys.pressed(KeyCode::Space) {
            buttons |= 0x4000;
            right.y = 0.;
        }
        if keys.pressed(KeyCode::ShiftLeft) || keys.pressed(KeyCode::ShiftRight) {
            buttons |= 0x1000;
        }
    }
    if keys.pressed(KeyCode::KeyM) {
        buttons |= 0x0100;
        if keys.pressed(KeyCode::ArrowDown) {
            buttons |= 0x0002;
        }
        if keys.pressed(KeyCode::ArrowUp) {
            buttons |= 0x0001;
        }
        right = Vec2::ZERO;
    }
    let axis = |v: f32| (v.clamp(-1., 1.) * 32767.).round() as i16;
    input.recovery_pending |= recover;
    if input.recovery_pending {
        buttons |= 0x1000;
    }
    input.packet =
        Controls { buttons, triggers, left: [axis(left.x), axis(left.y)], right: [axis(right.x), axis(right.y)] };
    input.toggle = toggle;
    input.recover = recover;
    input.stow = keys.just_pressed(KeyCode::KeyF);
}

impl RideInput {
    pub fn consume_modal(&mut self) {
        self.packet = Controls::default();
        self.toggle = false;
        self.recover = false;
        self.stow = false;
        self.release_pop = false;
        self.recovery_pending = false;
        self.mouse_stick = Vec2::ZERO;
    }
    pub fn selected_pad(&self) -> Option<Entity> {
        self.active_pad
    }
    /// Two genuine observations inside this physics tick, or ordinary packet fallback.
    pub fn fine_for_tick(&self, end: f64, period: f32, packet: Controls) -> Option<(Controls, Controls)> {
        self.history.for_tick(end, period, packet)
    }

    pub fn ticked(&mut self) {
        if self.release_pop {
            self.packet.right[1] = 0;
        }
        self.release_pop = false;
        self.recovery_pending = false;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn app() -> (App, Entity) {
        let mut app = App::new();
        app.init_resource::<RideInput>()
            .init_resource::<Time<Real>>()
            .init_resource::<ButtonInput<KeyCode>>()
            .init_resource::<ButtonInput<MouseButton>>()
            .init_resource::<AccumulatedMouseMotion>()
            .init_resource::<super::super::SkateStatus>()
            .init_resource::<hakuba_settings::Settings>()
            .add_message::<RawGamepadEvent>()
            .add_message::<StickReading>()
            .add_systems(Update, read);
        let pad = app.world_mut().spawn(Gamepad::default()).id();
        app.world_mut().resource_mut::<Time<Real>>().advance_by(std::time::Duration::from_secs_f64(1.017));
        (app, pad)
    }
    fn axis(app: &mut App, pad: Entity, axis: GamepadAxis, value: f32) {
        app.world_mut().write_message(RawGamepadEvent::Axis(bevy::input::gamepad::RawGamepadAxisChangedEvent::new(
            pad, axis, value,
        )));
    }
    #[test]
    fn riding_keyboard_reaches_transfer_drift_and_handplant_without_changing_push() {
        let (mut app, _) = app();
        {
            let mut keys = app.world_mut().resource_mut::<ButtonInput<KeyCode>>();
            keys.press(KeyCode::ShiftLeft);
            keys.press(KeyCode::KeyW);
            keys.press(KeyCode::KeyT);
        }
        app.update();
        let input = app.world().resource::<RideInput>();
        assert_eq!(input.packet.left[1], 32767);
        assert_eq!(input.packet.buttons & (0x1000 | 0x0200), 0x1000 | 0x0200);
        {
            let mut keys = app.world_mut().resource_mut::<ButtonInput<KeyCode>>();
            keys.release(KeyCode::ShiftLeft);
            keys.press(KeyCode::KeyC);
        }
        app.update();
        assert_eq!(app.world().resource::<RideInput>().packet.left[1], -32767);
        app.world_mut().resource_mut::<super::super::SkateStatus>().on_foot = true;
        app.update();
        assert_eq!(app.world().resource::<RideInput>().packet.left[1], 32767);
    }

    #[test]
    fn raw_axis_messages_keep_one_capture_time_not_fake_half_samples() {
        let (mut app, pad) = app();
        axis(&mut app, pad, GamepadAxis::RightStickX, 0.6);
        axis(&mut app, pad, GamepadAxis::RightStickY, -0.6);
        axis(&mut app, pad, GamepadAxis::RightStickY, 0.6);
        app.update();
        let input = app.world().resource::<RideInput>();
        assert_eq!(input.packet.right, [19660, 19660]);
        assert!(input.fine_for_tick(1.017, 1.0 / 60.0, input.packet).is_none());
    }
    #[test]
    fn timestamped_source_messages_supply_true_midpoint_and_match_final_packet() {
        let (mut app, pad) = app();
        axis(&mut app, pad, GamepadAxis::RightStickX, 0.6);
        axis(&mut app, pad, GamepadAxis::RightStickY, 0.6);
        for (captured_at, right) in [(1.002, [19660, -19660]), (1.012, [19660, 19660])] {
            app.world_mut().write_message(StickReading { gamepad: pad, captured_at, left: [0; 2], right });
        }
        app.update();
        let input = app.world().resource::<RideInput>();
        let (half, end) = input.fine_for_tick(1.017, 1.0 / 60.0, input.packet).unwrap();
        assert_eq!(half.right, [19660, -19660]);
        assert_eq!(end.right, input.packet.right);
    }
}
