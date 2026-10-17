# Clean local TRELLIS heads: UVs, masks and automatic reduction

**Use TRELLIS.2 cascade requested1024/actual768, then exterior reconstruction,
99,999-triangle QEM reduction, a 4K xatlas bake with nearest-surface colors, and
optional conservative eight-view SAM2 repair.** The selected, conventionally lit
result is committed as [`head.glb`](../assets/characters/trellis-skater-head/head.glb).
Use [`head-40k.glb`](../assets/characters/trellis-skater-head/head-40k.glb) for a
lighter alternative. All steps run locally and require no manual Blender edits.

**This is lower quality than Tripo.** It is a useful free local fallback when
Tripo credits are unavailable, using an existing or self-made reference image.
New Sunburst references cost money. This experiment has no same-reference Tripo
benchmark and does not establish quality parity, animation readiness or production
acceptance. Eyes, hair gaps, neck closure and baked-in color shading remain imperfect.

The [multi-view gallery](TRELLIS_HEAD_RETOPO_GALLERY.md) shows each completed
candidate and rejected geometry control. The earlier [24-recipe comparison](MESHAXIOM_HEAD_GALLERY.md)
covers MeshAxiom, native Pixal3D texturing, photo/multiview projection and five neural
geometries. This follow-up reuses one of those native TRELLIS results; it does not
claim additional independent neural samples.

## What improved, and what changed

The dense source had **11,386,792 triangles**, vertex colors, no UV atlas and no
semantic masks. Shading-normal correction helped grain but left dark skin speckles
and ragged surface details. A geometry-preserving 16-neighbor color median still
left dots. Color filtering alone was insufficient in this example.

The owner subsequently authorized a separate low-poly derivative. The new surface
pipeline samples 26 exterior depth/RGB views, repairs small supported depth outliers,
filters isolated color noise, fuses oriented samples, runs screened Poisson and then
adaptive QEM. This replaces the dense surface with a derived approximation. It is the
main source of the visible improvement; SAM2 is not responsible for removing the dots.
The original dense checkpoint and selected dense viewer export remain retained.

After reduction, UV generation/export verifies every ordered triangle corner and
winding. UV and shading-normal seams add coincident render vertices without moving
triangle corners. In the selected export, 740 vertices have the same position/UV
pair as another vertex but a different shading normal. These are intentional
normal discontinuities, not additional geometric surface detail.
Repainting verifies identical position, normal, UV and index bytes, identical scene
and material bindings, and unchanged protected texels. These guarantees apply to
the chosen reduced derivative, not geometric equivalence to the dense original.

## Ranking this follow-up

Ranks are qualitative judgments from eight matched lit views, close-ups, gray and
wire controls. There is no perceptual score or measured Hausdorff-error claim.

| Rank | Pipeline / actual triangles | Judgment |
| --- | --- | --- |
| **1** | Exterior + QEM **99,999**, nearest-color 4K atlas; conservative SAM2 repair | Best close-view result. Clean skin, smoother contours than 40K. Repair changes only 107 texels, so it is visually tied with the unpainted bake. |
| **2** | Exterior + QEM **39,999**, nearest-color 4K atlas | Best lighter asset. Slightly more angular cheeks/eyelids; 4.64 MiB GLB. |
| Control | Same 100K mesh, full confident-region skin/hair repaint | Changes 767,759 region texels; no clear visual gain over conservative repair. Not selected. |
| Control | Exterior 40K, 16-neighbor median transfer | Clean surface, but softer pupils and fine color boundaries than nearest transfer. |
| **3** | Exterior + QuadriFlow **9,092 quads / 18,184 triangles** | Low density with recognizable face, but rough eyelids, hair edges and small nose artifacts. Not the close-view recommendation. |
| Negative control | Dense original + color median, **11,386,792** | Exact geometry/normals retained, but dots remain. No UV atlas. |
| Rejected | Direct meshoptimizer permissive **112,312** / sloppy **42,389** | Nonmanifold output and worse feature edges. Vertex-color controls are not full texture-quality comparisons. Sloppy 4K UV bake failed validation. |
| Rejected | Occupancy/volume + QuadriFlow **28,698** / VDB route **23,432** | Holes or loss of facial shape. Successful solver exit did not make a usable head. |

The 100K result reduces triangle count by **99.12%**; 40K reduces it by **99.65%**.
The 100K surface has 50,018 physical vertices and 78,911 exported vertices after
normal/UV seams; 40K has 20,006 physical and 33,473 exported vertices. These measured
counts differ from requested budgets. QuadriFlow requested 10K quads but made 9,092.
The committed quad NPZ retains the actual quad connectivity; GLB triangulates it.

All three selected derivatives have zero edges with more than two incident faces
before UV/normal splitting. They retain **67 / 47 / 76 boundary edges**, respectively
for 100K, 40K and quads. They are not certified watertight. Automatic quad flow does
not produce a guaranteed facial animation loop layout; no rig or facial deformation
test was performed. Prefer the adaptive triangle result for this static preview.

## UVs and segmentation: useful, with limits

Each derivative has one 4096-square texture atlas. xatlas creates charts, detects
folded chart interiors at output texel resolution, separates affected triangles
into isometric islands and repacks. The final check finds **zero overlapping texel
interiors at 4096**, and export independently verifies ordered triangle geometry.
This is a raster-resolution check, not a proof against every subpixel intersection.

This is a fragmented automatic atlas, **not an artist-authored facial unwrap**.
The 100K atlas has 4,839 charts and 1,235,324 strict interior texels (7.36% of 4K);
40K has 2,007 charts. Many small islands and gutters waste texture space. Pixels use
glTF's top-left texture convention; the image is not vertically flipped. The atlas
supports deterministic surface projection and masks, but direct UV painting is less
pleasant than on an intentionally laid-out face atlas.

[SAM2.1 Hiera Tiny](https://huggingface.co/facebook/sam2.1-hiera-tiny), pinned at
`de431c4043854a71d8101e17995dfe596bf101a5`, runs on MPS over eight unlit RGB/depth
views. Its 155,908,064-byte weights are downloaded locally, not committed. Color
priors choose spatially distributed positive/negative prompts automatically; no one
clicks prompts or paints masks. Visibility/depth tests and facing weights fuse the
result into UV space. Dark features inside the skin support hull are protected even
when an eyebrow touches the hair. Some bangs are deliberately left unknown.

The selected UV masks contain **331,926 skin**, **435,833 hair** and **467,565 protected
feature/unknown** texels. Pink/blue/gold preview colors show these regions. They are
approximate, palette-dependent masks, not semantic ground truth or a complete face
parser. Eyes and brows are largely protected; fine hair, lip boundaries and unknown
regions still require inspection. Generalizing to different skin/hair palettes
requires adapting the automatic prompting rule. The full repaint control is not a
recommended substitute for a learned, semantic face texture model.

The default `repair` mode replaces only dark navy contamination inside confident
skin and warm contamination inside confident hair, using nearby same-palette native
surface colors. Here it changed one skin texel and 106 hair texels; it has little
visible effect because reconstruction and the original bake already did the cleanup.
`full` repaints all confident region texels and leaves protected interiors exact.
Both update empty atlas gutters. Neither moves or reorders the reduced mesh.

## Apple Silicon measurements

Measured on the **32 GiB M1 Max**, with sequential stages, three CPU workers where
supported, one Poisson solver thread, normal capacity admission and an 8 GiB aggregate
guard for each processing job. These are observed physical process-tree peaks,
not model-file sizes or installed-RAM requirements. No process guard, host reserve
or shared capacity profile was disabled or raised.

| Stage | Child wall time | Observed peak GiB |
| --- | ---: | ---: |
| Existing native generation/export/eight views | 1,206.88 s | 13.06 under a 14 GiB cap |
| 26 exterior views + sample fusion | 20.51 s | 2.64 |
| Poisson + both 40K/100K reductions | 40.61 s | 1.41 |
| 100K fresh 4K UV atlas, bake and export | 25.87 s | 1.41 |
| Eight segmentation views/depth | 2.45 s | 1.18 |
| Eight-view SAM2 inference, warm runtime | 8.15 s | 3.66 |
| Conservative UV mask projection/repaint | 10.72 s | 1.51 |
| Optional QuadriFlow on 100K | 6.07 s | 0.59 |
| Optional quad 4K atlas/bake | 9.72 s | 1.38 |

The measured selected post-process stages sum to **1m48s**; combined with the earlier
native generation measurement, **21m55s**. This excludes downloads, admission waits,
installation, rejected experiments and final browser QA. Core worker timers can be
shorter than child wall time because process startup/imports are excluded. These
figures are one run, not a benchmark confidence interval. The 40K sharp rebake reused
an existing atlas, so its seven-second wall time is not a fresh-atlas estimate.

A first cold SAM2 probe took 38.28s overall, versus eight seconds for this warmed
eight-view pass. Python/framework startup and filesystem cache state matter. The
post-processing itself fits well below 8 GiB in these measurements. The best native
generation was tested on a 32 GiB host; **a 14 GiB process cap does not establish that
this recipe runs safely on a 16 GiB Mac**. Use the smaller 512 recipe from the Apple
guide as the lower-memory candidate, then this same processing pipeline; that exact
end-to-end combination has not been validated here.

The current exports use learned RGB, uniform roughness 0.85 and metallic 0, no normal
map or unlit extension. They respond to light in the actual WebGL viewer. Native
spatially varying PBR is omitted, and learned base color can contain baked shading.
Neither a clean render nor lower polygon count proves production material quality.

## Reproduce from the retained native checkpoints

First follow [Apple Silicon setup/download and native generation](APPLE_HEAD_MODELS.md#reproduce-the-best-lit-head).
Use its `--vertex-colors` cascade recipe. The generation directory's `checkpoints/`
must contain `mesh_raw.npz`, `mesh_raw.json`, `decoder_output.npz` and `texture.npz`.
The dense `lit_normals.py` step is optional for the retained dense control and is
unnecessary for this reduced pipeline, which computes its own shading normals.

The examples below assume generation output at `build/yorimichi/meshaxiom/head-trellis-cascade`.
Run each command sequentially from the repository root, with fresh output/report
paths. In a responsive agent client, yield long jobs and retain their session IDs;
do not wrap a whole pipeline in a foreground wait. The public launchers own one
aggregate guard per stage and normal admission. On this shared Mac check the current
render board, live admission and supervisor first. Do not run worker files directly.

```sh
retopo_root=build/yorimichi/meshaxiom/retopo
native_checkpoint=build/yorimichi/meshaxiom/head-trellis-cascade/checkpoints

ATELIER_AGENT=meshaxiom-laptop nice -n 10 uv run python games/yorimichi/tools/head_retopo.py \
  setup --root "$retopo_root" --report build/yorimichi/logs/retopo-setup.guard --memory-gib 4
ATELIER_AGENT=meshaxiom-laptop nice -n 10 uv run python games/yorimichi/tools/head_retopo.py \
  surface --root "$retopo_root" --checkpoint "$native_checkpoint" \
  --output "$retopo_root/surface" --report build/yorimichi/logs/retopo-surface.guard
ATELIER_AGENT=meshaxiom-laptop nice -n 10 uv run python games/yorimichi/tools/head_retopo.py \
  reconstruct --root "$retopo_root" --checkpoint "$native_checkpoint" \
  --source "$retopo_root/surface/cloud.npz" --output "$retopo_root/reconstruct" \
  --depth 9 --triangles 40000 100000 --report build/yorimichi/logs/retopo-reconstruct.guard
ATELIER_AGENT=meshaxiom-laptop nice -n 10 uv run python games/yorimichi/tools/head_retopo.py \
  bake --root "$retopo_root" --checkpoint "$native_checkpoint" \
  --source "$retopo_root/reconstruct/mesh-100000.npz" \
  --color-cloud "$retopo_root/surface/cloud.npz" --output "$retopo_root/bake100k" \
  --texture-size 4096 --neighbors 1 --report build/yorimichi/logs/retopo-bake100k.guard
```

Setup pins NumPy 2.2.6, SciPy 1.15.3, Pillow 12.2.0, Open3D 0.20.0, xatlas 0.0.11
and fast-simplification 0.2.0 in an isolated build venv. macOS needs Homebrew and
Open3D's libusb runtime; setup installs the missing binary bottle under its existing
guard, with Homebrew auto-update disabled for that child. It does not install Blender.
QuadriFlow used installed Blender 5.2.1 LTS. The default worker path can be changed
with `--blender`. The selected triangle pipeline does not require Blender.

The exterior sampler uses 24 yaw/pitch cameras plus top/bottom, 768-square rays,
3x3 RGB/depth medians, a 0.0025-unit depth outlier threshold only where local coverage
exceeds 70%, and 0.0025-unit voxel fusion. Colors average in linear light and are
stored as sRGB. Reconstruction uses at most 400K samples with seed42, depth9,
scale1.1 and one solver thread, crops to the native bounds, removes components below
0.5% of the largest area, and reduces adaptively. Newly degenerate float32 faces are
removed here, before any geometry-preserving UV/paint promise. The public replay
reproduced the prototype's 40K and 100K mesh SHA256 values exactly on this machine.

Multi-threaded Poisson aborted inside the native library on this ARM setup; the
one-thread path completed. This follows the documented [Open3D issue](https://github.com/isl-org/Open3D/issues/2027)
and [PoissonRecon report](https://github.com/mkazhdan/PoissonRecon/issues/136).
All failed children remained inside the guard; no shared safety setting changed.

For 40K, repeat `bake` with `mesh-40000.npz` and fresh paths. Optional quads:

```sh
ATELIER_AGENT=meshaxiom-laptop nice -n 10 uv run python games/yorimichi/tools/head_retopo.py \
  remesh --root "$retopo_root" --source "$retopo_root/reconstruct/mesh-100000.npz" \
  --output "$retopo_root/quads" --quads 10000 --report build/yorimichi/logs/retopo-quads.guard
```

Bake `quads/mesh.npz` exactly as above. The solver scales coordinates by1000 only
while running to pass Blender's absolute edge tolerance, then divides back. It
checks nonmanifold/wire/short/inconsistently oriented edges, uses seed42 and three
threads, and checks the operator result. It never modifies the retained input.

## Automatic masks and repaint

```sh
ATELIER_AGENT=meshaxiom-laptop nice -n 10 uv run python games/yorimichi/tools/head_masks.py \
  setup --root "$retopo_root" --report build/yorimichi/logs/head-mask-setup.guard --memory-gib 4
ATELIER_AGENT=meshaxiom-laptop nice -n 10 uv run python games/yorimichi/tools/head_masks.py \
  views --root "$retopo_root" --source "$retopo_root/bake100k/mesh-uv.npz" \
  --model "$retopo_root/bake100k/head.glb" --output "$retopo_root/views" \
  --report build/yorimichi/logs/head-mask-views.guard
ATELIER_AGENT=meshaxiom-laptop nice -n 10 uv run python games/yorimichi/tools/head_masks.py \
  infer --root "$retopo_root" --views "$retopo_root/views" --output "$retopo_root/masks" \
  --device mps --report build/yorimichi/logs/head-mask-infer.guard
ATELIER_AGENT=meshaxiom-laptop nice -n 10 uv run python games/yorimichi/tools/head_masks.py \
  project --root "$retopo_root" --source "$retopo_root/bake100k/mesh-uv.npz" \
  --model "$retopo_root/bake100k/head.glb" --views "$retopo_root/masks" \
  --color-cloud "$retopo_root/surface/cloud.npz" --output "$retopo_root/paint" \
  --paint-mode repair --report build/yorimichi/logs/head-mask-project.guard
```

Setup pins Torch2.7.1, torchvision0.22.1, Transformers4.57.1 and the checkpoint
revision above in a second isolated venv. Inference verifies checkpoint file hashes
and rejects missing/mismatched image weights; the upstream video/image config-type
warning was observed, with all image weights loaded. MPS memory fraction is0.15;
the outer process-tree guard still applies. CPU inference is available but unbenchmarked.

Outputs include `head.glb`, external `basecolor.png`, skin/hair/protected/occupied
mask PNGs, `regions.png`, a segmentation preview GLB and SHA-bound proof JSON.
Mask inference outputs keep their calibrated depth files and prompts. Projection
rejects mismatched source model/UV/depth/mask hashes. Re-running with `--paint-mode full`
and fresh output/report paths reproduces the alternate repaint control.

## Evidence and remaining limits

The committed [provenance](../assets/characters/trellis-skater-head/provenance.json)
binds selected files, dense checkpoint, color cloud, reduced geometry, UV bake,
SAM2 weights, mask prompts, camera parameters, protected buffers, protected texels,
timings and aggregate guard cleanup. It contains public relative paths only.
The source library records checksums for the committed GLBs, maps and geometry sources.

Focused behavioral tests cover UV ownership/overlap rejection, top-left texture
orientation, immutable geometric corners after attribute compaction, source color
preservation, local depth repair, camera projection, image-only replacement,
identity-scene validation and aggregate launcher admission. Actual browser checks
load each candidate, capture eight views, exercise wire/gray modes and verify that
reducing light intensity changes the render. This does not replace an Unreal
import, animation test or extensive generalization study.

Other rejected trials included direct dense xatlas, raw QEM reduction that plateaued
near500K with nonmanifold edges, global hole-fill that stalled, occupancy reconstruction
that destroyed the face, and raw unoriented-point Poisson that left topology defects.
They are recorded as failures, not successful models with invented galleries. The
completed, visually reviewed geometry controls are shown in the gallery.

Relevant upstream implementations: [TRELLIS.2](https://github.com/microsoft/TRELLIS.2),
[trellis2mlx](https://github.com/lyonsno/trellis2mlx),
[Open3D reconstruction](https://www.open3d.org/docs/release/tutorial/geometry/surface_reconstruction.html),
[xatlas Python](https://github.com/mworchel/xatlas-python),
[SAM2](https://github.com/facebookresearch/sam2) and
[meshoptimizer](https://github.com/zeux/meshoptimizer) for the rejected direct-reduction controls.
