# Patched dependencies

Two dependencies are copied here and corrected for the game. Cargo selects each with `[patch.crates-io]`; the rest of
Bevy and wgpu remain pinned to the registry versions in the lockfile. No Cargo cache edits or external checkout paths
are required. Each copy's `PROVENANCE.json` records the source release, archive checksum, upstream commit and the
upstream hashes of the files changed. The original MIT and Apache-2.0 licenses are retained.

Every local change is marked with a `Hakuba:` comment, so `grep -rn Hakuba: vendor/` lists them all. Compare updates
against the recorded upstream release and carry each marked change forward before upgrading Bevy or wgpu; neither
copy is an independently versioned engine. Keep each upstream crate whole, so its declared features and shader
imports remain complete.

## bevy_pbr

The Bevy 0.20.0 PBR crate. Its changes:

- **Forward color and motion** (opt-in by view). A marked camera's main pass writes its own motion and depth;
  `crates/rendering/` owns comparison, publication to TAA and camera geometry-prepass elision (see its README). A
  rigid mesh passes on only its instance and the fragment finds its previous position from the instance's two
  transforms, and the fragment finds its world position from its depth, so fewer values travel from vertex to fragment.
- **Hemisphere fill light** (opt-in by camera, `HemisphereLight`). The sky's fill light given as three colours, sky,
  horizon and ground, and evaluated per normal, rather than walked to and sampled from a cubemap.
- **Shadow cascades reused** (opt-in by resource, `ShadowCascadeReuse` in the render world). A cascade redraws only
  every few frames, taking turns with the others, and the frames between sample the map it kept, through the matrices
  it was drawn with.
- **Concurrent GPU preprocessing** (all views, same results). The uniform-allocation scans of all batch sets run
  together in one pass per step rather than each waiting for the last; such passes are labelled `[concurrent]`, which
  the Metal backend below runs concurrently.
- **Last cascade fades out** (all views). Over its last fifth, so shadows grow in as the camera nears them rather than
  appearing at a line.
- **Crossfade dither moves** (all views that crossfade). The visibility-range dither steps through its sixteen
  positions every frame, told by the camera's jitter, so temporal anti-aliasing blends a crossfade into a smooth fade
  rather than a fixed screen-space pattern.

## wgpu-hal

The wgpu-hal 30.0.1 crate, of which only the Metal backend is changed:

- **Buffer pool.** Buffers wgpu destroys are kept, at most 768 MB of them, and handed out again for a new buffer of the
  same size class, as Metal's own heaps would: making a Metal buffer costs milliseconds when the world streams in.
- **Concurrent compute passes.** A compute pass labelled `[concurrent]` holds only independent dispatches, so Metal may
  run them together.
- **Frames on screen** (`wgpu_hal::metal::frames`). `set_minimum_on_screen` keeps each frame on screen at least that
  long (crates/pacing sets a 60th of a second); `shown` reports when frames actually reached the screen; `gpu_busy_ms`
  how long the GPU worked, which the drawn pixels follow (crates/world `pixels.rs`); `buffers` how many buffers were
  made and reused. Without a call to `set_minimum_on_screen` frames present as upstream.
