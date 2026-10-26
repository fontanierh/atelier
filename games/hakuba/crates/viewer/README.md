# viewer

The character viewer, for checking a character and its clips up close. It shows one character at a time on a plain
stage.

- The left column picks the character, or goes back to the menu.
- The right column lists every clip the character has; clicking one plays it in a loop. While a paraglider clip plays
  (all but `glide-close`), the character holds the paraglider (`hakuba_glider`), through the same grip as in the world,
  so the orbit camera can look at each fist on its handle up close.
- Drag to spin the camera around the character, scroll to zoom, and shift + drag to move up and down. The arrow keys
  also spin and tilt it, and page up and page down move it up and down.

`src/lib.rs` builds the screen; `src/orbit.rs` is the camera.
