//! A DualSense read straight from its HID reports, on macOS. Over Bluetooth the system switches the controller to its
//! full report (0x31), which macOS hands over as one opaque vendor field, so gilrs sees it connect but never sees a
//! button or a stick. A thread reads the reports and this plugin feeds them to Bevy as the gamepad's raw events.
//!
//! For playtests it also plays a scripted pad (`HAKUBA_SCRIPT`) and records the pad as a script (`HAKUBA_RECORD`).
//! Elsewhere than macOS the plugin does nothing.

use bevy::prelude::*;

#[cfg(target_os = "macos")]
mod dualsense;

pub struct GamepadPlugin;

impl Plugin for GamepadPlugin {
    fn build(&self, _app: &mut App) {
        #[cfg(target_os = "macos")]
        _app.add_plugins(dualsense::DualSensePlugin);
    }
}
