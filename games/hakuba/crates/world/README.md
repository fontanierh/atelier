# world

The world screen: the ground, the road and what stands around it from `assets/world`, the sea, the sky, sun and haze, and a camera
that starts at the spawn and flies (drag to look, W A S D to move, E and Q to rise and sink, shift for speed, scroll
to change it).

```text
src/
  lib.rs         the plugin: spawns the sea and the camera, then reads the world's index for the spawn and tiles
  loading.rs     covers the world until the tiles in sight and their models have loaded
  look.rs        the sky dome, the sun, the haze, and the camera's colour grade
  painterly.rs   the painterly filter over the finished image
  painterly.wgsl its shader
  pixels.rs      draws the world into an image of at most 3 million pixels and stretches it over the window
  tiles.rs       shows each tile in full detail near the camera and in middle detail further out
  scenery.rs     spawns the trees, bushes, grass and poles a tile lists, merging the copies of small models
  wind.rs        sways leaves and grass in the wind, by how far the export says each vertex sways
  wind.wesl      its vertex shader
  fly.rs         the flying camera
```
