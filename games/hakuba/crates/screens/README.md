# screens

What every screen shares.

- `Screen`, the state saying which screen is showing: the menu, the world, the character viewer or the settings. The
  game opens on the menu, and Escape, or a controller's Start button, goes back to it from the viewer and the
  settings.
- `Pause`, whether the world is paused: Escape or Start pauses and resumes it. While it is paused, its time stands
  still.
- `button` and `text`, so every screen's buttons and text look the same.
- The frame rate, shown in the top right corner on every screen: the frames drawn in the last second and the slowest
  of them, in milliseconds.

Each screen spawns its camera, lights and interface when it is entered, all tagged `DespawnOnExit`, so leaving a
screen removes everything it spawned.
