# Performance

Hakuba targets 60 frames a second in the browser on the reference setting: a 2560 × 1440 CSS viewport at device
scale 2, Resolution 50%, Near shadows, Temporal anti-aliasing and the default settings otherwise. That leaves about
16 ms of GPU time a frame. The skating port has not yet met this target: a 30-second idle sample measured 58.5 FPS
and a separate 30-second mounted sample measured 55.2 FPS, with Nominal thermal pressure throughout. These samples
used the same browser connection for viewport setup and measurement; the canvas was 2560 × 1440 in both phases.
The mounted player rolled under normal gravity, so this is not a fixed-camera comparison. `crates/CONTRACTS` holds
the rules below as checks for every change; this file says how to measure and why the rules are what they are.

## Forward-motion prototype

The explicit `?forward_motion=single` browser mode writes opaque/masked color and motion together, then publishes
motion and depth to TAA. It keeps shadow rendering unchanged and omits the camera prepass's geometry draws.
The normal world still uses its original renderer while temporal edge quality is checked.

A clean release-browser sample at the same reference setting measured **60.00 FPS idle and 59.33 FPS mounted**,
30 seconds each after warm-up, with Nominal thermal pressure. The viewport connection remained open and both
samples recorded CSS 2560 × 1440, device scale 2 and canvas 2560 × 1440. No capture, CPU profile or GPU-query
injection ran during measurement. The mounted 99th-percentile frame interval was 32.2 ms: this is an improvement
over 55.2 FPS, not sustained 60 FPS acceptance.

A separate 29-sample GPU diagnostic verified zero indexed geometry in the camera prepass and both shadow cascades
still rendering. Main rendering made about 6,496 indexed draws / 27.48 million indexed entries; its median pass interval
was 14.22 ms. Motion transfer had equal, unresolved timestamps in many samples; positive intervals had one
0.065536 ms timestamp quantum as their median. TAA remained about 0.131 ms. The earlier geometry prepass was about
8.19 ms and main about 9.83 ms in a slightly different visible workload. These overlapping pass intervals are not additive frame
times or a workload-matched A/B. The main pass pays more shading without the prepass's depth rejection.

Main foliage retains its existing depth margin, so its surface winner can differ from the unbiased old prepass
at intersections. Exact motion-texture publication does not prove identical TAA edge quality. `compare` keeps the
old displayed TAA input; `publish` retains both geometry passes but feeds TAA from main. These remain explicit
validation modes, not quality settings or proof that the 60 FPS contract is met.

## The desktop build on the Mac

The desktop build is not the reference measurement, but it is how the game is playtested, so it holds 60 frames a
second on its own terms: an Apple M3 Pro on a 120 Hz display, 1440 lines drawn, the default settings. Frames start on
fixed 62 Hz deadlines and Metal keeps each on screen at least a 60th of a second (crates/pacing).

Measure it with a recorded pad session, so every run walks the same route: `HAKUBA_RECORD=FILE` records one and
`HAKUBA_SCRIPT=FILE` replays it (crates/gamepad), with nothing else using the CPU or GPU. The frame log says each
second how many game-loop frames fell under 12 ms, about one 60 Hz frame, 20–29, 29–40 and over 40 ms; count a frame
in the 20–29 bucket or above, after the splash lifts, as late. The counter in the corner reads from when Metal actually
showed each frame, not the game loop; `gpu` is the GPU's work per frame that second. Xcode's Metal System Trace of
the game itself gives each pass's GPU time.

On 2026-11-04, with this build, the screen not recorded and nothing else heavy running:

| Route (replayed pad session) | Frames after the splash | Late (over 20.8 ms) | Over 29 ms | Worst |
| --- | --- | --- | --- | --- |
| Walk | 1761 | 45 to 90 (2.6–5%) over four runs | 35 to 57 | 70 ms |
| Skate | 1812 | 15 (0.8%) | 2 | 33 ms |
| Paraglider glide down the hill | 2362 | 6 (0.3%) | 0 | 28 ms |
| Free-camera rise over the forest | 2049 | 19 (0.9%) | 7 | 34 ms |

The walk's late frames are one view: up the slope near the skate start, facing north over the forest, where the main
pass's vertex and fragment work each double and a frame's GPU work reaches 18 ms (95th percentile). How many of them
there are follows what else the machine runs.

### What Unreal does on the Mac, and what Hakuba does instead

Unreal's renderer is the yardstick for what a Mac game should do for itself. Each of its optimizations that fits a
small open world drawn by Bevy has its counterpart here:

| Unreal | Hakuba |
| --- | --- |
| Pooled Metal buffers (the Metal RHI's buffer pool) | Freed Metal buffers are kept, up to 768 MB, and reused by size (vendor/wgpu-hal) |
| Async compute | Bevy's preprocess compute passes run as concurrent Metal passes (vendor/wgpu-hal, vendor/bevy_pbr) |
| Frame pacing with a minimum present duration | Fixed 62 Hz deadlines, each frame on screen at least a 60th (crates/pacing) |
| Forward shading | One forward pass writes color and motion, with no geometry prepass (crates/rendering, the desktop default) |
| Shadow cascade caching | Each of the two cascades redraws every other frame, the last one fading out (crates/rendering `defaults.rs`) |
| Mesh LODs with dithered transitions | Trees swap versions at 65 m and small plants fade at 16 m, through a moving dither (crates/world `scenery.rs`) |
| Hierarchical LODs | A 512 m block whose nearest tile is past 300 m merges its far tiles into one mesh per look, switching whole, as HLOD clusters do; blocks at the 2.5 km horizon load and leave whole (crates/world `blocks.rs`, `tiles.rs`) |
| Nanite's error-bounded simplification | On the desktop, a block's plants are simplified to stray under a pixel from their shapes (crates/world `blocks.rs`) |
| Distance-based detail | Plants show their middle version near and their far version past 200 m, showing both within 64 m of it (crates/world `tiles.rs`) |
| Instanced and merged static meshes | Small models merge by 32 m square or tile; large ones draw instanced |
| PSO precaching | The splash holds until every pipeline the world needs is made |
| Thread priorities | The frame loop runs at interactive QoS and the skater's background work at utility QoS (crates/screens) |
| World Partition streaming | Tiles load and swap versions around the player (crates/world `tiles.rs`) |

Not taken: Bevy has no Lumen or virtual shadow maps, so the sky lights the world through a hemisphere light
(vendor/bevy_pbr) and the sun through two cascades; Bevy's GPU occlusion culling needs the depth prepass, which the
single forward pass leaves out; GPU light clustering adds compute passes and a readback a frame for the few lights
here, so lights cluster on the CPU.

## Measuring

Measure the reference in the browser, which is slower than the desktop build and differs from it in ways that matter
(below).
Use `trunk serve --release` for the reference measurement. Plain `trunk serve` uses the faster-to-build development
profile, whose frame rate is not the reference measurement.

- **Nothing else on the GPU.** A video playing in another browser, another game, a Rust build or a second headless
  browser each moves a frame by several milliseconds. With the same build and settings, frames measured 7.4 ms and
  19.5 ms an hour apart. Check Activity Monitor's GPU history before trusting a number.
- **Count frames as the player sees them**: frames a second and the median and 90th percentile frame times from
  `requestAnimationFrame` with vsync on, over at least ten seconds of play after the splash lifts. Without vsync, the
  times between `getCurrentTexture` calls say how fast the CPU queues frames, not how fast the GPU draws them.
- **Inspect GPU pass intervals** with Xcode's Metal System Trace of the browser's GPU process. Bevy does not enable
  WebGPU pass timing here. External diagnostics can request the optional `timestamp-query` feature and write pass
  boundary timestamps, but must report support, quantization and instrumentation overhead. Start Chrome with
  `--enable-dawn-features=use_user_defined_labels_in_backend` so each pass carries Bevy's name for it, wait about ten
  seconds after the splash lifts, then run
  `xcrun xctrace record --template 'Metal System Trace' --attach <GPU process id> --time-limit 3s --output run.trace`.
  Export the `metal-gpu-intervals` table with `xcrun xctrace export`, counting only the verified game's GPU process.
  Merge overlapping intervals before reporting occupied time. Channels and even different encoders can overlap;
  do not add their durations as elapsed frame time. A command-buffer frame number is not a displayed game frame.
  Label an interval average or encoder duration as such unless an independent frame association is established.
- **Keep viewport setup alive.** CDP device-metrics overrides end when their connection closes. Use the same
  connection for setup and measurement, and record the actual CSS viewport, device scale and canvas dimensions
  during every sample. Setup metadata alone is not evidence of the measured dimensions.
- **Separate diagnostics from frame pacing.** CPU profiling, GPU timestamp queries and draw-call recording add work.
  Use them to locate costs, not as the clean FPS acceptance run. Equal quantized timestamp pairs are unresolved,
  not proof that a pass costs nothing.
- **A fresh browser profile after an export.** The browser caches the game's `.glb` files: after an asset changes,
  load the page with a hard reload (Cmd+Shift+R) or a new profile, or the game runs new code on old files.
- **Before and after, on the same machine and settings.** A pull request that claims a frame-rate effect gives both,
  with the per-pass times where they moved.

## Where a frame goes

Historical pass/channel estimates from October 2026, in milliseconds, before the skating port. Their exact
association with displayed frames was not established. These are not current acceptance results, and overlapping
columns or passes must not be added as elapsed frame time:

| Pass                             | Fragment | Vertex |
| -------------------------------- | -------- | ------ |
| The sun's shadow cascades        | 4.2      | 0.5    |
| Prepass (depth, normals, motion) | 2.9      | 1.7    |
| Main pass                        | 2.2      | 2.4    |
| Painterly filter                 | 0.7      |        |
| Menu and text                    | 1.0      |        |
| Upscaling to the window          | 0.7      |        |
| Temporal anti-aliasing           | 0.5      |        |

Plants dominate the passes that draw geometry: grass alone costs about 4 ms across them. Every vertex that sways pays
its wind in the shadow, prepass and main passes.

## What we learned

- **A discarded fragment is not free in the browser.** Chrome's WebGPU on Metal keeps running a fragment after
  `discard` to the end of the shader. Bevy's standard fragment shader discards a cut-out texel and then lights it in
  full, so every leaf card in front of what shows paid the lighting and shadow lookups. The plants' fragment shader
  (`crates/world/src/leaves.wesl`) branches around the lighting instead: about 4 ms a frame, which took the reference
  setting from about 41 frames a second to 50. The world logs an error for any standard material that cuts out.
- **Shadows can be cast by what is never seen.** A directional light casts shadows only from meshes on its render
  layers. The sun is on layers 0 and `SHADOW_ONLY`; the camera sees only 0. So a plant near the camera shows its full
  version, which never changes as the player walks up to it, and its cheaper middle version casts its shadow from
  `SHADOW_ONLY`. Swapping a model's version while it is in view reads as popping, however far away it happens.
- **A post filter's kernel belongs in its shader as constants.** The painterly filter's 21 taps each weighed in all
  eight wedges through a uniform array; written into the shader, leaving out the two thirds of weights that are zero,
  it looks the same and costs 0.7 ms instead of 2.0: with it the reference setting went from about 50 frames a second to
  a steady 60, before the skating port.
- **Balance merged geometry against draw preparation.** Thousands of grass entities cost more to cull than their
  vertices cost to draw, so their copies merge, but a merged mesh is culled whole: shadow-casting models use 32 m
  squares and non-shadow-casting models currently merge by tile. A large model, such as a tree, is never merged; Bevy draws its copies
  together anyway. Tile scenery is prepared over multiple updates, then the complete version replaces the old one.
- **Keep presentation cameras out of 3D visibility work.** The window's 2D camera displays the world image and UI;
  it has no 3D render layers or directional-light shadow view. Rigid GPU-built meshes also use a direct binding path, while
  skinned, morphed, lightmapped and CPU-built meshes retain Bevy's original binding.
- **Note where each mesh's buffers sit.** Bevy's draw looked up a mesh's vertex, index and metadata places in the mesh
  allocator for every draw in the prepass, main and shadow passes: over the whole island, a quarter of the browser's
  time a frame went to those lookups. Rigid meshes now note them once, when the mesh is prepared or its buffer moves,
  and draw from the note: looking over the island from the crater rim, the browser went from about 48 frames a second
  to 60.
- **Fetch a draw's resources only when it uses them.** Bevy's draw state fetches every resource its commands might
  read for every item; the rigid-mesh draw, which carried Bevy's binding and draw as fallbacks, fetched 16 per item,
  about 13% of the browser's main thread at the crater rim. It now fetches the 5 its own path reads, and the
  fallbacks' resources only when a draw falls back.
- **Keep ground rays to nearby solids.** Bevy's general mesh picker checked bounds on decorative meshes before the
  solid filter. Ground now queries solid meshes directly, bounds each ray by its reach and uses Bevy's triangle
  intersections. At the reference setting, walking rose from about 57 to 60 frames a second.
- **Let the browser pace 60.** A frame cap's timer runs apart from the display's refreshes, so a 60 cap in the browser
  drew 14 and 28 ms frames by turns. In the browser a cap of 60 or more leaves the pacing to `requestAnimationFrame`.
- **Switch blocks whole.** Far tiles joined their block one by one as each crossed a ring around the camera, and
  left it one by one at the horizon: a glide merged a block every 50 ms, each a few milliseconds of main-thread work,
  an upload, a stalled frame and the block's trees reshaped. Blocks now merge and leave whole, as Unreal's HLOD
  clusters do, and simplify for their distance in √2 steps: the glide's merges fell from 304 to 11 and the ride's from
  147 to 3, and the late frames of both by about half.
- **Prove a tree's level of detail in the forest lab first** (crates/forest_lab). It flies and walks a fixed path
  through a forest drawn as the game draws it and counts the squares of the screen that jump between frames against
  an all-full reference. An impostor from 90 m, as the game had, reshaped trees; from 150 m over a 12 m fade it still
  did in 17 frames of 238, over 40 m in 4, and from 200 m over 40 m in none. The width of the fade mattered more than
  the impostor's detail: lighting the impostor deeper in its crown made it worse. On the forest flight a 200 m swap
  costs 14.7 ms of GPU time a frame against 11.4 at 150 m and 9.7 at 90 m.
- **Fewer, larger trees.** A placed region's tree groups may share a thinning (tools/export/src/world/placed.rs): the
  forest keeps its trees 11 m apart and grows each kept one by 1.2, 67,413 of 197,810. The source keeps every tree.
  With every tree an impostor the flight's frame fell from 9.0 to 7.6 ms; with full trees to 200 m it did not move,
  as the near crowns still fill the screen.
- **Leaf cards cost by their overlap, not their count.** Testing a cut-out texel turns off the Apple GPU's hidden
  surface removal, so every card layer over a pixel is tested. A depth prepass of only the leaves took the main pass's
  fragment work from 6.4 to 2.4 ms, but its own alpha test cost 4.4 ms and 2.6 ms of vertex work. Opaque leaf
  outlines need about 57 vertices a card for the clustered leaf textures, and 8-point hulls doubled the vertices and
  ran slower (18.1 against 14.1 ms in the lab) while reshaping the crowns.
- **The GPU's clock follows its load.** macOS lowers the GPU's performance state when a frame is light, so a cheaper
  setting can read as slower: in one Metal System Trace the full trees ran at the maximum state and impostors at the
  minimum, every unchanged pass taking about twice as long. Compare passes between traces whose
  `gpu-performance-state-intervals` show the same state, or scale by a pass whose work does not change, such as the
  painterly filter.
- **Measure without recording the screen.** Recording the screen at the same time tripled a ride's late frames (56
  against 13 and 17 in 32 s): count late frames with nothing else drawing, and record only to look.
- **What did not pay**: hardware 2 × 2 shadow filtering (no gain), a 1024 shadow map (1.7 ms, visibly softer shadows),
  dynamic resolution (the same replayed ride had 122 late frames with it and 66 without, a glide 139 and 43: 65% of
  the pixels took the GPU as long, held by geometry, while each new size made a new image and restarted
  anti-aliasing), and Bevy's contrast-adaptive sharpening (it showed rare untonemapped pale frames, the white
  flashes of a playtest).
  Shadow map sizes must be powers of two.
