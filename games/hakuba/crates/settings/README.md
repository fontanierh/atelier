# settings

The settings, which the player chooses on the **Settings** screen from the menu, or on the pause screen in the world,
and which the game keeps between visits: in the browser's local storage, or in `~/.config/hakuba/settings.json` on
the desktop.

- **Painterly**: how much of the painterly filter shows over the image, from none to all of it.
- **Wind**: how strongly the wind moves the plants, from still to twice the usual.
- **Resolution**: how many pixels the world draws, as a share of the window's width and height, or **Auto**, the
  window's pixels up to 3 million.
- **Shadows**: none, near (60 m around the camera) or far (150 m, in two cascades).
- **Anti-aliasing**: temporal, which keeps thin edges such as grass steady, SMAA, or none.
- **Detail**: how far from the camera tiles show in full.
- **Frame rate**: at most 30 or 60 frames a second, or as many as the machine draws.
- **Volume**: how loud every sound plays, from silent to as recorded.

`Settings` is the resource the other crates read; the world applies what it changes, and the audio crate the
volume. `panel()` is the list of settings with a button on each side of its value to step through it, which both
screens show. This crate also holds the game to its frame rate.

```text
src/
  lib.rs     the settings, keeping them, the frame rate and the Settings screen
  panel.rs   the list of settings and their buttons
```
