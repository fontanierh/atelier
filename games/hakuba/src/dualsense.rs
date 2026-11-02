//! A DualSense read straight from its HID reports, on macOS. Over Bluetooth the system switches the controller to its
//! full report (0x31), which macOS hands over as one opaque vendor field, so gilrs sees it connect but never sees a
//! button or a stick. A thread reads the reports and this plugin feeds them to Bevy as the gamepad's raw events.

use std::sync::mpsc::{Receiver, channel};
use std::sync::Mutex;

use bevy::input::gamepad::{
    GamepadConnection, GamepadConnectionEvent, RawGamepadAxisChangedEvent, RawGamepadButtonChangedEvent,
    RawGamepadEvent,
};
use bevy::prelude::*;

const SONY: u16 = 0x054C;

/// One report, decoded.
#[derive(Clone, Copy, PartialEq, Default)]
struct Pad {
    sticks: [f32; 4],
    triggers: [f32; 2],
    buttons: [bool; BUTTONS.len()],
}

const BUTTONS: [GamepadButton; 17] = [
    GamepadButton::West,
    GamepadButton::South,
    GamepadButton::East,
    GamepadButton::North,
    GamepadButton::LeftTrigger,
    GamepadButton::RightTrigger,
    GamepadButton::LeftTrigger2,
    GamepadButton::RightTrigger2,
    GamepadButton::Select,
    GamepadButton::Start,
    GamepadButton::LeftThumb,
    GamepadButton::RightThumb,
    GamepadButton::Mode,
    GamepadButton::DPadUp,
    GamepadButton::DPadRight,
    GamepadButton::DPadDown,
    GamepadButton::DPadLeft,
];

/// Decodes a report: the full Bluetooth one (0x31) or the simple/USB one (0x01), which share their layout one byte
/// apart.
fn decode(report: &[u8]) -> Option<Pad> {
    let data = match report.first()? {
        0x31 if report.len() >= 12 => &report[2..],
        0x01 if report.len() >= 11 => &report[1..],
        _ => return None,
    };
    let axis = |b: u8| (b as f32 - 127.5) / 127.5;
    let (b0, b1, b2) = (data[7], data[8], data[9]);
    let hat = b0 & 0x0F;
    let mut buttons = [
        b0 & 0x10 != 0,
        b0 & 0x20 != 0,
        b0 & 0x40 != 0,
        b0 & 0x80 != 0,
        b1 & 0x01 != 0,
        b1 & 0x02 != 0,
        b1 & 0x04 != 0,
        b1 & 0x08 != 0,
        b1 & 0x10 != 0,
        b1 & 0x20 != 0,
        b1 & 0x40 != 0,
        b1 & 0x80 != 0,
        b2 & 0x01 != 0,
        false,
        false,
        false,
        false,
    ];
    if hat < 8 {
        buttons[13] = matches!(hat, 7 | 0 | 1);
        buttons[14] = matches!(hat, 1..=3);
        buttons[15] = matches!(hat, 3..=5);
        buttons[16] = matches!(hat, 5..=7);
    }
    Some(Pad {
        sticks: [axis(data[0]), -axis(data[1]), axis(data[2]), -axis(data[3])],
        triggers: [data[4] as f32 / 255.0, data[5] as f32 / 255.0],
        buttons,
    })
}

#[derive(Resource)]
struct Reports(Mutex<Receiver<Pad>>);

#[derive(Resource, Default)]
struct Fed {
    pad: Option<Entity>,
    last: Pad,
}

pub struct DualSensePlugin;
impl Plugin for DualSensePlugin {
    fn build(&self, app: &mut App) {
        let (send, receive) = channel();
        std::thread::spawn(move || {
            loop {
                let opened = hidapi::HidApi::new().ok().and_then(|api| {
                    let info = api.device_list().find(|d| d.vendor_id() == SONY)?;
                    info.open_device(&api).ok()
                });
                let Some(device) = opened else {
                    std::thread::sleep(std::time::Duration::from_secs(2));
                    continue;
                };
                info!("DualSense opened for raw reports");
                let mut buf = [0u8; 128];
                while let Ok(len) = device.read_timeout(&mut buf, 500) {
                    if let Some(pad) = decode(&buf[..len]) {
                        if send.send(pad).is_err() {
                            return;
                        }
                    }
                }
                std::thread::sleep(std::time::Duration::from_secs(1));
            }
        });
        app.insert_resource(Reports(Mutex::new(receive))).init_resource::<Fed>().add_systems(PreUpdate, feed.before(bevy::input::InputSystems));
    }
}

/// Sends what changed since the last report as the gamepad's raw events, on the gamepad gilrs connected (the lowest,
/// which the game reads first) or on one of its own.
fn feed(
    reports: Res<Reports>,
    mut fed: ResMut<Fed>,
    pads: Query<Entity, With<Gamepad>>,
    mut commands: Commands,
    mut raw: MessageWriter<RawGamepadEvent>,
    mut buttons: MessageWriter<RawGamepadButtonChangedEvent>,
    mut axes: MessageWriter<RawGamepadAxisChangedEvent>,
    mut connections: MessageWriter<GamepadConnectionEvent>,
) {
    let Some(pad) = reports.0.lock().unwrap().try_iter().last() else { return };
    let target = match pads.iter().min_by_key(|e| e.to_bits()) {
        Some(entity) => entity,
        None => {
            let entity = commands.spawn_empty().id();
            let event = GamepadConnectionEvent::new(
                entity,
                GamepadConnection::Connected { name: "DualSense".into(), vendor_id: Some(SONY), product_id: None },
            );
            raw.write(event.clone().into());
            connections.write(event);
            fed.pad = Some(entity);
            return;
        }
    };
    fed.pad = Some(target);
    let last = fed.last;
    let sticks = [GamepadAxis::LeftStickX, GamepadAxis::LeftStickY, GamepadAxis::RightStickX, GamepadAxis::RightStickY];
    for (i, axis) in sticks.into_iter().enumerate() {
        if pad.sticks[i] != last.sticks[i] {
            raw.write(RawGamepadAxisChangedEvent::new(target, axis, pad.sticks[i]).into());
            axes.write(RawGamepadAxisChangedEvent::new(target, axis, pad.sticks[i]));
        }
    }
    for (i, button) in BUTTONS.into_iter().enumerate() {
        let value = match button {
            GamepadButton::LeftTrigger2 => pad.triggers[0],
            GamepadButton::RightTrigger2 => pad.triggers[1],
            _ => f32::from(u8::from(pad.buttons[i])),
        };
        let was = match button {
            GamepadButton::LeftTrigger2 => last.triggers[0],
            GamepadButton::RightTrigger2 => last.triggers[1],
            _ => f32::from(u8::from(last.buttons[i])),
        };
        if value != was {
            raw.write(RawGamepadButtonChangedEvent::new(target, button, value).into());
            buttons.write(RawGamepadButtonChangedEvent::new(target, button, value));
        }
    }
    fed.last = pad;
}
