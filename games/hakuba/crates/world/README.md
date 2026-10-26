# world

The world screen: the ground, the road and what stands around it from `assets/world`, the sea, the sky, sun and haze, and a camera
that starts at the spawn. It publishes where the player starts (`Spawn`) and what the player stands on (`Ground`); the
player crate spawns the player and moves the camera. The settings change it as they change, and Escape pauses it.

```text
src/
  lib.rs         the plugin: spawns the sea and the camera, then reads the world's index for the spawn and tiles
  ground.rs      marks the tiles' meshes solid, but their cables, and casts rays at them
  loading.rs     covers the world until the tiles in sight and their models have loaded
  look.rs        the sky dome, the sun, the haze, and the camera's colour grade
  painterly.rs   the painterly filter over the finished image
  painterly.wgsl its shader
  pixels.rs      draws the world into an image of the resolution the settings ask and stretches it over the window
  tiles.rs       shows each tile in full detail near the camera and in middle detail further out
  scenery.rs     spawns the trees, bushes, grass and poles a tile lists, merging the copies of small models
  wind.rs        sways leaves and grass in the wind, by how far the export says each vertex sways
  wind.wesl      its vertex shader
  settings.rs    applies the settings: the painterly filter, the wind, anti-aliasing and shadows
  pause.rs       the pause screen over the world, with the settings
```
