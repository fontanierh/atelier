# screens

What every screen shares.

- `Screen`, the state saying which screen is showing: the menu, the world or the character viewer. The game opens on
  the menu, and Escape goes back to it from anywhere.
- `button` and `text`, so every screen's buttons and text look the same.

Each screen spawns its camera, lights and interface when it is entered, all tagged `DespawnOnExit`, so leaving a
screen removes everything it spawned.
