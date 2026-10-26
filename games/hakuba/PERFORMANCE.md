# Performance

Hakuba holds 60 frames a second in the browser on the reference setting: a 2560 × 1440 window at device scale 2 (a 5K
display), Resolution 50%, Near shadows, Temporal anti-aliasing and the default settings otherwise. That leaves about
16 ms of GPU time a frame. `crates/CONTRACTS` holds the rules below as checks for every change; this file says how to
measure and why the rules are what they are.

## Measuring

Measure in the browser, which is slower than the desktop build and differs from it in ways that matter (below).

- **Nothing else on the GPU.** A video playing in another browser, another game, a Rust build or a second headless
  browser each moves a frame by several milliseconds. With the same build and settings, frames measured 7.4 ms and
  19.5 ms an hour apart. Check Activity Monitor's GPU history before trusting a number.
- **Count frames as the player sees them**: frames a second and the median and 90th percentile frame times from
  `requestAnimationFrame` with vsync on, over at least ten seconds of play after the splash lifts. Without vsync, the
  times between `getCurrentTexture` calls say how fast the CPU queues frames, not how fast the GPU draws them.
- **Time each pass on the GPU** with Xcode's Metal System Trace of the browser's GPU process. Bevy cannot time passes
  in WebGPU, which has no timestamps inside a pass. Start Chrome with
  `--enable-dawn-features=use_user_defined_labels_in_backend` so each pass carries Bevy's name for it, wait about ten
  seconds after the splash lifts, then run
  `xcrun xctrace record --template 'Metal System Trace' --attach <GPU process id> --time-limit 3s --output run.trace`.
  Export the `metal-gpu-intervals` table with `xcrun xctrace export` and add up each label's time per frame, counting
  only the game's GPU process.
- **A fresh browser profile after an export.** The browser caches the game's `.glb` files: after an asset changes,
  load the page with a hard reload (Cmd+Shift+R) or a new profile, or the game runs new code on old files.
- **Before and after, on the same machine and settings.** A pull request that claims a frame-rate effect gives both,
  with the per-pass times where they moved.

## Where a frame goes

GPU time per frame on the reference setting, in milliseconds, in October 2026:

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
  a steady 60.
- **Merge small copies by square, not by tile.** Thousands of grass entities cost more to cull than their vertices cost
  to draw, so their copies merge, but a merged mesh is culled whole: one per 16 m square keeps what is out of view
  undrawn. A large model, such as a tree, is never merged; Bevy draws its copies together anyway.
- **Let the browser pace 60.** A frame cap's timer runs apart from the display's refreshes, so a 60 cap in the browser
  drew 14 and 28 ms frames by turns. In the browser a cap of 60 or more leaves the pacing to `requestAnimationFrame`.
- **What did not pay**: hardware 2 × 2 shadow filtering (no gain), a 1024 shadow map (1.7 ms, visibly softer shadows).
  Shadow map sizes must be powers of two.
