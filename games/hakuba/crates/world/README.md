# world

The world screen: the ground and the road from `assets/world`, the sea, a sun, and a camera that starts at the spawn
and flies (drag to look, W A S D to move, E and Q to rise and sink, shift for speed, scroll to change it).

```text
src/
  lib.rs      the plugin: spawns the sea, the sun and the camera, then reads the world's index for the spawn and tiles
  tiles.rs    shows each tile in full detail near the camera and in middle detail further out
  fly.rs      the flying camera
```
