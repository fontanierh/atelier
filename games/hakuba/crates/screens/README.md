# screens

What every screen shares.

- `Screen`, the state saying which screen is showing: the menu, the world, the character viewer or the settings. The
  game opens on the menu, and Escape, or a controller's Start button, goes back to it from the viewer and the
  settings.
- `Pause`, whether the world is paused: Escape or Start pauses and resumes it. While it is paused, its time stands
  still.
- `button` and `text`, so every screen's buttons and text look the same.
- The frame rate, shown in the top right corner on every screen: the frames drawn in the last second and the slowest
  of them, in milliseconds. On the Mac it is read from when Metal actually showed each frame (the vendored Metal
  backend, vendor/wgpu-hal), and logged each second with the buffers the backend made.
- `switch` and `switched_on`, the desktop switches: environment variables, named `HAKUBA_…`, that playtests and
  measurements set. They are read the same way everywhere, never in the browser, and the game plays the same without
  any. The ones there are: `HAKUBA_START` (world), `HAKUBA_FORWARD_MOTION` and
  `HAKUBA_PIPELINES` (world), `HAKUBA_SCRIPT` and `HAKUBA_RECORD` (gamepad), `HAKUBA_DEV`, `HAKUBA_SHOT` and
  `HAKUBA_TRIS` (dev), `HAKUBA_MUTE` (audio), `HAKUBA_SCREEN` (here) and `HAKUBA_FULLSCREEN` (the program).
- `GameScreen`, the screen the game plays on, whose refresh rate paces its frames (crates/pacing): the main screen,
  or with `HAKUBA_SCREEN=other` the first other screen (a laptop's own beside an external one), borderless
  fullscreen there.
- `run_this_thread_as`, which sets how urgently macOS runs the calling thread: the frame loop interactive, work in
  the background (the skate session built ahead) at utility.

Each screen spawns its camera, lights and interface when it is entered, all tagged `DespawnOnExit`, so leaving a
screen removes everything it spawned.
