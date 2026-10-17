# Generate clean assets locally

Use **TRELLIS.2/MLX single-image generation → exterior reconstruction → adaptive
triangle reduction → checked 4K UV bake → optional conservative SAM2 repair →
scripted assembly/rigging → multi-view review**. This is the best tested local head
workflow in this repository. It requires no manual Blender sculpting or painting.

**This is below Tripo quality.** It is useful when Tripo credits are unavailable.
An existing or self-made reference makes local inference and processing free of
per-generation API charges. New **GPT Image 2.5 Sunburst** references are paid and
must go through `atelier.ai.ledger`. The pinned upstream models retain their own
[weight and code terms](../tools/head_models/THIRD_PARTY.md).

This guide connects the working stages. The head recipe is measured and committed;
body processing, attachment fitting and rigging need character-specific scripts and
inspection. There is no universal one-command character generator. For props, start
with one isolated object, then review thin parts, holes and silhouette before using
the head-oriented reconstruction settings unchanged.

| Step | Tools |
| --- | --- |
| Reference images | Existing/self-made images, or GPT Image 2.5 Sunburst through the paid-call ledger |
| Local 3D generation | Microsoft TRELLIS.2 through the pinned MLX port |
| Exterior cleanup and reduction | Open3D raycasting, screened Poisson and QEM simplification |
| UV atlas and texture bake | xatlas and our nearest-surface color-transfer scripts |
| Skin/hair masks and repaint | SAM2.1 Tiny on MPS and our visibility-weighted projection/repair scripts |
| Assembly, accessories and rig | Blender controlled by Python scripts |
| Multi-view inspection | Lit WebGL browser viewer and scripted comparison renders |
| Game import | Atelier's build pipeline and Unreal Engine 5.8 |

## 1. Prepare references and capacity

Run from the repository root after `uv sync` and the [Mac setup](../../../docs/SETUP.md).
Set `ATELIER_AGENT` to your registered board owner on a managed machine and keep its
listener armed. Use the public launchers below, which own normal admission and an
aggregate process-tree guard. Never run their worker files directly or change shared
capacity profiles to make a run fit. Jobs over thirty seconds belong in the agent
client's background facility, with retained session IDs and bounded progress checks.

The selected recipe was tested on a **32 GiB M1 Max** with a 14 GiB generation guard
and an 8 GiB processing guard. Above 10 GiB, the generation launcher requires the
managed full-capacity broker; an unmanaged machine refuses that request. A process
cap is not installed RAM. The [512 recipe](APPLE_HEAD_MODELS.md#trellis2-through-mlx)
is a smaller-memory candidate, but the complete cleaned pipeline on a 16 GiB Mac
has not been validated. MLX's allocation setting is not the outer guard's hard ceiling.

Use a single isolated foreground object with transparent or clean black background,
soft neutral lighting, no cast shadow, and no cropped extremities. Do not feed a
contact sheet to the single-image recipe. For a character, make two separate inputs:

- **Head:** close face, all hair and essential earrings; preserve the approved identity.
- **Body:** headless neck-down T-pose with a usable neck plug and separated arms/legs.
  Keep a staff, hat or bag separate when an existing authored accessory is preferable.

Approve the front identity before making optional side/back references. Use those
views for consistency checks or registered texture projection. The MLX port's
multiple-image feature concatenation is an experimental heuristic, not calibrated
multiview generation; it did not improve our head comparison. More views alone do
not guarantee better geometry or a consistent hairline.

## 2. Set up once, reuse the weights, generate each part

The commands below reproduce the selected skater-head recipe using its committed
reference. Substitute your approved single-part image and fresh output/report paths
for each new asset. **Do not rerun setup/download for every head or body.** Reuse an
existing verified runtime root when available. The pinned TRELLIS set is about
15 GiB on disk, in addition to runtimes and generated dense checkpoints. Keep this
weight cache marked as active during cleanup; it is not a disposable trial output.
Do not move an active runtime. A cross-worktree shared cache is not assumed here.

```sh
model_root=build/yorimichi/local-models
asset_root=build/yorimichi/local-head
retopo_root="$asset_root/processing"
checkpoint="$asset_root/native/checkpoints"

nice -n 10 uv run python games/yorimichi/tools/head_models.py \
  trellis setup --root "$model_root" --memory-gib 4 \
  --report build/yorimichi/logs/local-models-setup.guard
nice -n 10 uv run python games/yorimichi/tools/head_models.py \
  trellis download --root "$model_root" --memory-gib 4 \
  --report build/yorimichi/logs/local-models-download.guard
nice -n 10 uv run python games/yorimichi/tools/head_models.py \
  trellis generate --root "$model_root" --memory-gib 14 --timeout 3600 \
  --report build/yorimichi/logs/local-head-native.guard -- \
  --image games/yorimichi/assets/characters/meshaxiom-skater-head/reference.png \
  --output "$asset_root/native" --resolution 1024 --max-tokens 16384 \
  --mlx-gib 10 --steps 12 --vertex-colors
```

The wrapper fixes seed 42 and uses unquantized weights by default. Requested 1024
can select 768 under the token budget: read the effective grid, actual tokens,
timing and physical process-tree peak from the reports. Keep the raw geometry,
learned texture and intermediate checkpoints. The first export has vertex colors;
it is not yet the clean UV-textured deliverable. Generate a body separately using
the same `model_root`, a body reference and fresh output/report paths; run the two
neural generations sequentially.

Setup pins source revisions; download verifies model sizes and SHA-256 values.
See [the Apple Silicon guide](APPLE_HEAD_MODELS.md) for exact tensor sizes, runtime
details and measured alternatives. Do not substitute an unverified weight set or
promise quantized quality: the ranked recipe did not test quantization.

## 3. Reconstruct the exterior, then reduce

```sh
nice -n 10 uv run python games/yorimichi/tools/head_retopo.py \
  setup --root "$retopo_root" --memory-gib 4 \
  --report build/yorimichi/logs/local-head-retopo-setup.guard
nice -n 10 uv run python games/yorimichi/tools/head_retopo.py \
  surface --root "$retopo_root" --checkpoint "$checkpoint" \
  --output "$retopo_root/surface" \
  --report build/yorimichi/logs/local-head-surface.guard
nice -n 10 uv run python games/yorimichi/tools/head_retopo.py \
  reconstruct --root "$retopo_root" --checkpoint "$checkpoint" \
  --source "$retopo_root/surface/cloud.npz" --output "$retopo_root/reconstruct" \
  --depth 9 --triangles 40000 100000 \
  --report build/yorimichi/logs/local-head-reconstruct.guard
```

This fuses 26 filtered exterior depth/RGB views, runs **single-thread** screened
Poisson at depth 9, then adaptive QEM reduction. The one-thread solver is deliberate:
the multithreaded native solver aborted in the ARM experiment. This creates a new
surface approximation; it does not preserve the dense source's geometry. Retain
that source separately. Exterior reconstruction removed the skin dots more
effectively than normal smoothing or a median on the original vertex colors.

Use the 100K derivative for close-view heads, compare 40K for a lighter asset, and
record actual counts rather than requested budgets. Our 18K-triangle QuadriFlow
control lost eyelid/hair quality. Quads and more faces are not quality guarantees;
this reduction does not produce artist-designed facial animation loops. Inspect
eyes, ears, hair gaps, fingers, clothing edges and intentional openings before
accepting a derivative or applying the head settings to a body or prop.

## 4. Bake UVs and learned color

```sh
nice -n 10 uv run python games/yorimichi/tools/head_retopo.py \
  bake --root "$retopo_root" --checkpoint "$checkpoint" \
  --source "$retopo_root/reconstruct/mesh-100000.npz" \
  --color-cloud "$retopo_root/surface/cloud.npz" --output "$retopo_root/bake100k" \
  --texture-size 4096 --neighbors 1 \
  --report build/yorimichi/logs/local-head-bake.guard
```

The selected export is `bake100k/head.glb`; retain `mesh-uv.npz`, `basecolor.png`
and the bake report for later masking and verification. `--neighbors 1` preserves
pupils and color boundaries better than the larger color medians in our comparison.
The atlas check requires zero overlapping strict texel interiors at the chosen
resolution; this is not a proof against every subpixel intersection. Export verifies
ordered triangle corners and winding, permitting coincident UV/normal seam vertices.

The automatic atlas is fragmented, not an artist facial unwrap. It supports surface
projection and masks, but packs inefficiently and is less convenient to paint by
hand. Current materials use learned RGB with roughness 0.85/metallic 0; they omit
spatial PBR variation and can retain baked shading. Inspect under real lighting.

## 5. Optional segmentation and conservative repaint

```sh
nice -n 10 uv run python games/yorimichi/tools/head_masks.py \
  setup --root "$retopo_root" --memory-gib 4 \
  --report build/yorimichi/logs/local-head-mask-setup.guard
nice -n 10 uv run python games/yorimichi/tools/head_masks.py \
  views --root "$retopo_root" --source "$retopo_root/bake100k/mesh-uv.npz" \
  --model "$retopo_root/bake100k/head.glb" --output "$retopo_root/views" \
  --report build/yorimichi/logs/local-head-mask-views.guard
nice -n 10 uv run python games/yorimichi/tools/head_masks.py \
  infer --root "$retopo_root" --views "$retopo_root/views" \
  --output "$retopo_root/masks" --device mps \
  --report build/yorimichi/logs/local-head-mask-infer.guard
nice -n 10 uv run python games/yorimichi/tools/head_masks.py \
  project --root "$retopo_root" --source "$retopo_root/bake100k/mesh-uv.npz" \
  --model "$retopo_root/bake100k/head.glb" --views "$retopo_root/masks" \
  --color-cloud "$retopo_root/surface/cloud.npz" --output "$retopo_root/paint" \
  --paint-mode repair --report build/yorimichi/logs/local-head-mask-project.guard
```

SAM2.1 Tiny runs locally on MPS with automatic palette-based prompts; visibility
and depth tests fuse eight views into skin/hair/protected UV masks. **Adapt both
prompt selection and repaint palette rules** for different skin, grey hair, hats
or clothing; the shipped default was tuned for warm skin and navy hair. These are
approximate masks, not a general semantic face parser. Inspect eyes, brows, lips,
ears and the hairline. Leave unknown regions protected.

Compare `paint/head.glb` to the unpainted bake. Prefer `repair`, which fixes isolated
cross-region contamination. Full region repaint can erase useful detail and is not
the selected recipe. Painting must verify identical positions, normals, UVs,
indices, scene/material bindings and protected texels. Finish these stages **before
joining or rigging**: the tools expect the single unrigged mesh layout, not an
assembled character. Beyond reduction, this is texture work, not mesh sculpting.

## 6. Assemble parts and fit the rig with a script

For a static head or prop, proceed to review. For a character, use the separate-part
assembly approach in [Nox's recipe](NOX_CHARACTER_RECIPE.md) and the shared
[playable-character workflow](PLAYABLE_CHARACTER.md). Nox uses Tripo sources;
reuse the assembly/validation approach, not its paid model-generation step.

Keep head and body materials/UVs separate. Determine physical scale from the design
and mesh landmarks, not the sizes of separately cropped reference images. Uniform
scale and rigid placement should fit the head to the body's actual neck plug. Do
not use the bottom-most chin as the neck socket, or align only bounding-box centers.
Check front/back profile coverage and a controlled neck overlap, without deforming
the approved face. Retain authored accessories where useful.

Seat a hat using its inner brim and the head's crown/hair surface, including vertical
placement. The old hat height is not valid for a different head. Record achieved
contact/gap after any placement clamp; a configured overlap is not evidence of
actual contact. Report missing contacts or unsuccessful fits rather than silently
accepting them. Do not hide a bad fit by changing the viewer camera.

Put the neck/head rig pivot at the measured socket, parent the hat to the head, and
follow the [humanoid bone contract](../../../platform/conventions/rigs/humanoid.toml).
Check unweighted vertices, influence limits and accessory bones. Automatic body
weights need pose inspection; a successful exporter is not rig approval. Use
guarded Blender with three threads for scripted assembly. Finish queued/native
callers before editing their source or syncing their checkout.

## 7. Review, publish the viewer and commit the asset

Review the **exported GLB**, not just the source scene. Show the reference image(s),
preserved baseline and selected local result in a comparison viewer. Include matched
front, three-quarter, profile, back and head-close views, plus wireframe/material
controls and GLB downloads. Use ordinary lit shading; test a light change so an
unlit material cannot disguise surface problems. Check textures and a gray control.
For characters, add a head turn, arms-down pose and crouch: neck gaps, drifting hats,
bad shoulder weights and accessory intersections may appear only in motion.

Publish updated models and reports together, and version the viewer asset URLs so
browser caches do not show an earlier fit. Keep screenshots of each inspected view
and honest limitations. A usable preview is not a final fit or animation sign-off.

Keep runtime weights, checkpoints and rejected trials under ignored `build/yorimichi/`.
Commit only the selected game-consumed GLB, textures, masks and necessary sources
under `assets/`, with provenance (reference/model hashes, prompts, exact/effective
settings, measured timings/peaks and processing reports). Update
[`source-library.json`](../assets/source-library.json) for its supported asset
formats; keep metadata hashes inside provenance rather than adding unsupported
JSON/gzip entries to the inventory. A fresh clone must build from committed sources
without rerunning inference or reading someone's private model cache.

```sh
uv run python games/yorimichi/tools/verify_asset_library.py
```

## Measured baseline and limits

| Selected skater-head stages, 32 GiB M1 Max | Wall time | Peak physical process-tree memory |
| --- | ---: | ---: |
| Neural generation, export and eight views | 20m07s | 13.06 GiB under a 14 GiB guard |
| Exterior reconstruction, 40K/100K reduction, selected 4K bake and masks/repair | 1m48s total | 3.66 GiB under 8 GiB guards |

These are measured stages from one input, excluding installation, downloads,
admission waits, rejected experiments, assembly and final browser QA. They are not
an end-to-end character ETA. Single-image inference invents unseen surfaces; UVs
and masks do not fix that. No watertightness, facial animation topology or Tripo
quality parity is established. Use the [ranked results](TRELLIS_HEAD_RETOPO.md) and
[multi-view gallery](TRELLIS_HEAD_RETOPO_GALLERY.md) to judge the actual tradeoffs.
