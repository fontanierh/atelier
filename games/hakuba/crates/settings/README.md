# settings

The settings, which the player chooses on the **Settings** screen from the menu, or on the pause screen in the world,
and which the game keeps between visits: in the browser's local storage, or in `~/.config/hakuba/settings.json` on
the desktop.

- **Painterly**: how much of the painterly filter shows over the image, from none to all of it.
- **Wind**: how strongly the wind moves the plants, from still to twice the usual.
- **Resolution**: how many pixels the world draws, as a share of the window's width and height, or **Auto**, the
  window's pixels up to 3 million.
- **Shadows**: none, near (60 m around the camera, in two cascades: sharp within 20 m) or far (150 m, in two cascades).
- **Anti-aliasing**: temporal, which keeps thin edges such as grass steady, SMAA, or none.
- **Detail**: how far from the camera tiles show in full.
- **Frame rate**: at most 30 or 60 frames a second, or as many as the machine draws.
- **Volume**: how loud every sound plays, from silent to as recorded.

`Settings` is the resource the other crates read; the world applies what it changes, and the audio crate the
volume. `Settings.skate` holds skating preferences in that same desktop file or browser storage entry.
Easy, Normal and Hardcore use the authored feel on that difficulty. Custom changes the saved base difficulty,
trucks, flick recognition, air, rails, rolling, turning, balance and bails. Custom edits stay saved while a preset
is selected. Stance, stick and mouse controls, tight and optional 120 Hz flick reading, drift powerslides, bowl
boost, camera and sound choices apply in every mode. The skate crate applies `skate.effective()` to the session.

`panel()` has General and Skating tabs, shared by both screens. Skating uses short grouped pages with step
buttons and scrolling on smaller windows; Custom-only rows are disabled in a preset. Every numeric feel knob,
including half/full drift grip, wall-follow airs and camera follow speed, has a row. The default enables 120 Hz
flick reading when real midpoint stick readings are available; otherwise it uses the frame's sample. This crate also
holds the game to its chosen drawing frame rate, separately from skating physics.

```text
src/
  lib.rs     the settings, keeping them, the frame rate and the Settings screen
  panel.rs        shared setting rows and their buttons
  skate.rs        skating preferences, preset resolution, defaults and limits
  skate_panel.rs  skating pages in the shared settings panel
  places.rs       named skate destinations and the current native marker frame
```
