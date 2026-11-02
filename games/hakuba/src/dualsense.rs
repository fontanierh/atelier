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

/// `HAKUBA_SCRIPT=FILE` plays a scripted pad instead of the controller: each line is `SECONDS LX LY RX RY BUTTON...`
/// from the program's start, held until the next line; buttons by name (cross, circle, square, triangle, l1, r1, l2,
/// r2, create, options, l3, r3, ps, up, right, down, left).
#[derive(Resource)]
struct Script {
    started: std::time::Instant,
    /// When the world finished loading; times written `+N` count from then.
    loaded: Option<std::time::Instant>,
    steps: Vec<(bool, f32, Pad)>,
}

impl Script {
    fn load() -> Option<Self> {
        let text = std::fs::read_to_string(std::env::var("HAKUBA_SCRIPT").ok()?).ok()?;
        let names = [
            "square", "cross", "circle", "triangle", "l1", "r1", "l2", "r2", "create", "options", "l3", "r3", "ps",
            "up", "right", "down", "left",
        ];
        let mut steps = Vec::new();
        for line in text.lines().map(str::trim).filter(|l| !l.is_empty() && !l.starts_with('#')) {
            let words: Vec<&str> = line.split_whitespace().collect();
            let num = |i: usize| words.get(i).and_then(|w| w.trim_start_matches('+').parse::<f32>().ok()).unwrap_or(0.0);
            let mut pad = Pad { sticks: [num(1), num(2), num(3), num(4)], ..default() };
            for word in words.iter().skip(5) {
                if let Some(i) = names.iter().position(|n| n == word) {
                    pad.buttons[i] = true;
                    if i == 6 { pad.triggers[0] = 1.0 }
                    if i == 7 { pad.triggers[1] = 1.0 }
                }
            }
            steps.push((words[0].starts_with('+'), num(0), pad));
        }
        info!("playing pad script of {} steps", steps.len());
        Some(Self { started: std::time::Instant::now(), loaded: None, steps })
    }

    fn at(&self) -> Pad {
        let t = self.started.elapsed().as_secs_f32();
        let since_load = self.loaded.map(|l| l.elapsed().as_secs_f32());
        self.steps
            .iter()
            .take_while(|(relative, start, _)| if *relative { since_load.is_some_and(|s| *start <= s) } else { *start <= t })
            .last()
            .map(|(_, _, pad)| *pad)
            .unwrap_or_default()
    }
}

/// `HAKUBA_RECORD=FILE` writes every change of the pad as a script line (`+SECONDS` from the world loading), so a
/// session can be played back with `HAKUBA_SCRIPT`.
#[derive(Resource)]
struct Record {
    file: std::io::LineWriter<std::fs::File>,
    started: std::time::Instant,
    loaded: Option<std::time::Instant>,
}

impl Record {
    fn write(&mut self, pad: &Pad) {
        use std::io::Write;
        let names = [
            "square", "cross", "circle", "triangle", "l1", "r1", "l2", "r2", "create", "options", "l3", "r3", "ps",
            "up", "right", "down", "left",
        ];
        let time = match self.loaded {
            Some(loaded) => format!("+{:.3}", loaded.elapsed().as_secs_f32()),
            None => format!("{:.3}", self.started.elapsed().as_secs_f32()),
        };
        let mut line = format!("{time} {:.3} {:.3} {:.3} {:.3}", pad.sticks[0], pad.sticks[1], pad.sticks[2], pad.sticks[3]);
        for (i, name) in names.iter().enumerate() {
            let pressed = match i {
                6 => pad.triggers[0] > 0.5,
                7 => pad.triggers[1] > 0.5,
                _ => pad.buttons[i],
            };
            if pressed {
                line.push(' ');
                line.push_str(name);
            }
        }
        let _ = writeln!(self.file, "{line}");
    }
}

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
        if let Some(script) = Script::load() {
            app.insert_resource(script);
        }
        if let Some(file) = std::env::var("HAKUBA_RECORD").ok().and_then(|path| std::fs::File::create(path).ok()) {
            app.insert_resource(Record { file: std::io::LineWriter::new(file), started: std::time::Instant::now(), loaded: None });
        }
        app.insert_resource(Reports(Mutex::new(receive))).init_resource::<Fed>().add_systems(PreUpdate, feed.before(bevy::input::InputSystems));
    }
}

/// Sends what changed since the last report as the gamepad's raw events, on the gamepad gilrs connected (the lowest,
/// which the game reads first) or on one of its own.
fn feed(
    reports: Res<Reports>,
    script: Option<ResMut<Script>>,
    mut record: Option<ResMut<Record>>,
    loaded: Option<Res<hakuba_world::SceneryLoaded>>,
    unready: Query<(), With<hakuba_world::Unready>>,
    mut fed: ResMut<Fed>,
    pads: Query<Entity, With<Gamepad>>,
    mut commands: Commands,
    mut raw: MessageWriter<RawGamepadEvent>,
    mut buttons: MessageWriter<RawGamepadButtonChangedEvent>,
    mut axes: MessageWriter<RawGamepadAxisChangedEvent>,
    mut connections: MessageWriter<GamepadConnectionEvent>,
) {
    let reported = reports.0.lock().unwrap().try_iter().last();
    if let Some(record) = record.as_mut() {
        if record.loaded.is_none() && loaded.is_some() && unready.is_empty() {
            info!("pad record: world loaded");
            record.loaded = Some(std::time::Instant::now());
        }
    }
    let Some(pad) = script
        .map(|mut script| {
            if script.loaded.is_none() && loaded.is_some() && unready.is_empty() {
                info!("pad script: world loaded");
                script.loaded = Some(std::time::Instant::now());
            }
            script.at()
        })
        .or(reported)
    else {
        return;
    };
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
    if pad != last {
        if let Some(record) = record.as_mut() {
            record.write(&pad);
        }
    }
    fed.last = pad;
}
