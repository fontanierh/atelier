# gamepad

A DualSense controller read straight from its HID reports, on macOS only. Over Bluetooth the system switches the
controller to its full report, which macOS hands over as one opaque field, so Bevy's own gamepad support sees it
connect but never sees a button or a stick. A thread reads the reports and `GamepadPlugin` feeds them to Bevy as the
gamepad's raw events, so the rest of the game reads the controller as any other.

For playtests, two desktop switches (see crates/screens):

- `HAKUBA_SCRIPT=FILE` plays a scripted pad instead of the controller. Each line is `SECONDS LX LY RX RY BUTTON...`,
  held until the next line; `+SECONDS` counts from the world having loaded. Buttons go by name: cross, circle, square,
  triangle, l1, r1, l2, r2, create, options, l3, r3, ps, up, right, down, left.
- `HAKUBA_RECORD=FILE` writes every change of the pad as such a line, so a session can be played back.

- `lib.rs` the plugin, which does nothing elsewhere than macOS.
- `dualsense.rs` decodes the reports, runs the reading thread, and plays and records the script.
