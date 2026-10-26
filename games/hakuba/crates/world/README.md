# world

The world screen: the ground, the road and what stands around it from `assets/world`, the sea, the sky, sun and haze, and a camera
that starts at the spawn and flies (drag to look, W A S D to move, E and Q to rise and sink, shift for speed, scroll
to change it).

```text
src/
  lib.rs         the plugin: spawns the sea and the camera, then reads the world's index for the spawn and tiles
  look.rs        the sky dome, the sun, the haze, and the camera's colour grade
  painterly.rs   the painterly filter over the finished image
  painterly.wgsl its shader
  tiles.rs       shows each tile in full detail near the camera and in middle detail further out
  scenery.rs     spawns the trees, bushes, grass and poles a tile lists, merging the copies of small models
  fly.rs         the flying camera
```
