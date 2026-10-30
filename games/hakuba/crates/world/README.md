# world

The world screen: the ground, the road and what stands around it from `assets/world`, the sea, the sky, sun and haze, and a camera
that starts at the spawn, or at a start chosen in the page's address (`#start=x,y,z,bearing`, map metres and a
compass bearing) or, on the desktop, in `HAKUBA_START`. It publishes where the player starts (`Spawn`), what the player stands on (`Ground`) and
`PushesPlants`, which makes the grass and bushes around whatever carries it lean away; the player crate spawns the
player with it and moves the camera. The settings change it as they change, and Escape pauses it.

```text
src/
  lib.rs         the plugin: spawns the sea and the camera, then reads the world's index for the spawn and tiles;
                 makes any crossfading visibility range abrupt, since its dither shimmers
  ground.rs      marks tile and scenery collision pending until a version activates, and casts rays at active solids
  collision.rs   publishes owned, ordered triangle snapshots with materials, grind lines and zones; a rider's
                 predictive focus pins complete full-detail tiles and reports installed coverage
  loading.rs     a splash over the world until its tiles, models, textures and shaders are all ready, so nothing
                 appears after; says when the renderer makes a pipeline later
  look.rs        the sky dome, the sun, the haze, and the camera's colour grade
  painterly.rs   the painterly filter over the finished image
  painterly.wgsl its shader
  pixels.rs      draws the world into an image of the resolution the settings ask and stretches it over the window
  tiles.rs       prepares each new detail version hidden, then swaps its visibility and collision together
  scenery.rs     spawns the trees, bushes, grass and poles a tile lists, merging the copies of small models
                 per 32 m square when they cast shadows or whole tile otherwise; preparation is spread across updates.
                 A tree or bush in a full tile shows its full version and casts its middle version's shadow;
                 model exports can mark their visible meshes solid
  vertex_paint.rs an opaque static vertex-colour material with asset-owned fill, glow bounds and haze
  vertex_paint.wesl its colour, emission and aerial-perspective shaders
  wind.rs        sways leaves and grass by their exported weights
  source_foliage.wesl source-weighted motion in the main, prepass and shadow vertices
  source_leaves.wesl source foliage colour, haze and cut-out lighting
  shadow_alpha.wesl shadow-only cut-outs from exact alpha companions
  wind.wesl      its vertex shaders, which also lean leaves and blades away from what pushes plants aside
  leaves.wesl    its fragment shader, which lights only what a leaf card keeps
  push.rs        gives that shader where the things that push plants are, up to four, the nearest the camera
  settings.rs    applies the settings: the painterly filter, the wind, anti-aliasing and shadows
  pause.rs       the pause screen over the world, with the settings
```

`WorldCollision` publishes a generation-tagged `Arc<CollisionSnapshot>`. It owns actual solid triangles, including
invisible model collision, rather than rays or walking approximations. `CollisionFocus::request(position, velocity)`
pins full tiles over a swept 100 m margin and two seconds ahead; consumers wait for `ready` before stepping and use
`covers` before accepting travel. A pending place return sets `destination` while continuing to request the current
rider corridor, so one immutable snapshot retains both ends without loading the intervening world. Clear the
destination after transfer, and clear the focus after riding. Render batches retain their original collision
instances so changing preparation budgets does not reorder contacts. Triangle winding stays outward under mirrored
transforms. When hidden collision omits materials, exact matching drawn triangles supply their authored materials;
no ray or nearest-surface guess can cross to another layer. Rails and oriented assist/boost boxes come from the
world index, not region names at runtime.

A static vertex-painted model may put a `vertex_paint` object in its `full` node extras. Its `fill`, `glow`,
`glow_min`, `glow_max`, `haze_start_m`, `haze_length_m` and `haze_colour` are its authored material values.
Its untextured white material is opaque, and its linear RGBA vertex colours have zero alpha: alpha is reserved for
motion, not transparency. The world reports nonzero weights and skinned or morphed meshes until that motion is
supported. The profile uses its own depth haze, so it does not also receive the camera's distance fog.

A tile node may instead carry `surface_paint` with `haze_start_m`, `haze_length_m` and `haze_colour`. Its static
mesh uses positions, normals and UV0, with no vertex colours, and its opaque material supplies the texture and tint.
The profile sets roughness to 1 and reflectance to 0, applies its own pre-light haze and haze-colour emission, and
holds the tile until the material is ready. A failed profile leaves the previous tile visible.
