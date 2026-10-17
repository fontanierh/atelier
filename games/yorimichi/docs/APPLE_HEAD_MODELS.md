# Local Apple Silicon head model recipes

These experiments use the published neural models on the laptop. Sunburst high
supplies reference images; it does not generate the 3D meshes. The comparison and
measured results are in [MESHAXIOM_HEAD_QUALITY.md](MESHAXIOM_HEAD_QUALITY.md).
The machine is a 32 GiB M1 Max. A process ceiling is distinct from installed RAM.

**Recommended local fallback:** TRELLIS cascade requested1024/actual768, 16,384-token
budget, twelve steps, native vertex colors, then 16-iteration lit-normal correction.
This is lower-quality than Tripo and is useful when Tripo credits are unavailable.
With an existing/self-made reference, generation requires no paid API calls; new
Sunburst references are paid. The [best lit recipe](#reproduce-the-best-lit-head)
keeps all geometric triangles and uses conventional lighting. No manual Blender step.

## Isolated runtimes and exact weights

`tools/head_models.py` owns normal admission and one aggregate process-tree guard
for installation, downloads, inference and comparison renders. The explicit larger
memory reservation uses the existing reviewed MeshAxiom adapter. It never changes
machine profiles, host reserves or other owners' processes. Each attempt needs a
new report directory. Ceilings above 10 GiB require the existing managed full-capacity
broker; unmanaged machines retain the ordinary 10 GiB maximum and refuse before work.
The native image1024 recipe does not fit that smaller envelope. The measured TRELLIS512
process peak was 7.19 GiB, but a separate unmanaged 10 GiB run is not claimed.
Commands expected to take more than thirty seconds must run
in the client's background facility, retaining the session ID for bounded polls.

Run from the repository root. The examples use an ignored runtime below
`build/yorimichi/meshaxiom/head-models`; downloaded payloads are never committed.
Native setup needs Xcode command-line tools and an installed Homebrew Eigen package.
It compiles with two workers. It does not install or replace the shared Unreal engine.

```sh
ATELIER_AGENT=meshaxiom-laptop nice -n 10 uv run python games/yorimichi/tools/head_models.py \
  native setup --root build/yorimichi/meshaxiom/head-models \
  --report build/yorimichi/logs/head-native-setup.guard --memory-gib 4
ATELIER_AGENT=meshaxiom-laptop nice -n 10 uv run python games/yorimichi/tools/head_models.py \
  native download --root build/yorimichi/meshaxiom/head-models \
  --report build/yorimichi/logs/head-native-download.guard --memory-gib 4
```

Setup fetches pinned source commits. The only tracked Pixal3D source patch makes
Clang accept the existing double literals/index conversions and reduces the
query batch in sparse attention from 2048 to 256; every query still sees all keys.
The focused CPU extension binds only the existing supplied-mesh voxelizer. It does
not replace the voxelization algorithm with a placeholder. NATTEN is installed
only after Torch, with build isolation disabled. The six Metal packages come from
the pinned fork. Package versions and full weight sizes/hashes are committed in
`tools/head_models/`; see its [source credits](../tools/head_models/THIRD_PARTY.md).

Downloads use Hugging Face's chunked transport with four concurrent ranges,
verify size and SHA256 before use, preserve conflicting/partial files, and never
print credentials. Only selected checkpoints are fetched. The public DINO mirror
matches the official checkpoint's SHA256. Model downloads are read-only operations,
not paid generation calls. Generated Sunburst references retain their paid ledgers.

## Actual tensor sizes

The [weight-header audit](head-model-weight-audit.json) reads the downloaded
safetensors headers, rather than inferring precision from filenames. Sizes below
are whole files in GiB. JSON manifests also bind exact revisions and SHA256 values.

| Component | Parameters | Stored precision | File GiB |
| --- | ---: | --- | ---: |
| Pixal3D texture flow | 1.387 billion | Float32, despite the bf16 filename | 5.166 |
| TRELLIS sparse-structure flow | 1.292 billion | BF16 | 2.407 |
| TRELLIS shape flow, each 512/1024 checkpoint | 1.292 billion | BF16 | 2.407 |
| TRELLIS texture flow, each 512/1024 checkpoint | 1.292 billion | BF16 | 2.407 |
| Supplied-shape encoder | 354 million | Float16 | 0.660 |
| Shape decoder | 474 million | Float16 | 0.883 |
| PBR decoder | 474 million | Float16 | 0.883 |
| DINOv3 image encoder | 303 million | Float32 | 1.129 |
| Sparse-structure decoder | 73.7 million | Mostly Float16, 0.12 million Float32 | 0.137 |

The native MPS loader casts weights to each destination module's declared dtype.
Only one large stage model is kept at a time. The flow/PBR/conditioning activations,
voxel caches and framework allocation pools are substantial, so checkpoint size
alone does not predict physical footprint. Use the measured process-tree peaks.

## MeshAxiom's native texture model stack

The original repository documents a supplied-shape texture path using Pixal3D's
image-conditioned texture flow and TRELLIS.2's shape encoder/PBR decoder. The MPS
adapter loads these exact checkpoints in stages, verifies complete model states,
and releases each model before the next stage. Meta construction plus mapped CPU
weights avoids an initial duplicate model allocation. Unregistered deterministic
position frequencies are recreated from their constructor formulas.

DINO attention is tiled by query while retaining full key/value context. Projected
features are sampled only at occupied shape coordinates; a small control checks
those queried values against the original full-grid implementation. This reduces
intermediate allocation without changing the requested features. DINO/NAF runs
on MPS, as do texture sampling, PBR decoding and attribute sampling. CPU code handles
supplied-mesh voxelization, UV rasterization and final GLB packing.

```sh
ATELIER_AGENT=meshaxiom-laptop nice -n 10 uv run python games/yorimichi/tools/head_models.py \
  native generate --root build/yorimichi/meshaxiom/head-models \
  --report build/yorimichi/logs/head-native-texture.guard --memory-gib 14 -- \
  --dataset games/yorimichi/assets/characters/meshaxiom-head-reference-set \
  --mesh games/yorimichi/assets/characters/meshaxiom-skater-head/mesh.source.json.gz \
  --image games/yorimichi/assets/characters/meshaxiom-skater-head/reference.png \
  --output build/yorimichi/meshaxiom/head-native \
  --condition-size 512 --naf-size 512 --mps-gib 12 --steps 12
```

This recipe uses smaller 512-pixel conditioning with 1024 shape support and the
published 1024 texture checkpoint. A separate successful trial uses
`--condition-size 1024 --naf-size 512`: 629.91 seconds through the verified GLB, 12.75 GiB peak aggregate footprint. Full NAF1024
conditioning hit its allocator limit; neither reduced recipe is the full default.
The temporary rigid camera alignment is used only for neural support and baking.
Every exported mesh buffer and original native triangle/winding is verified.
Only base color and metallic/roughness material data are replaced. The shader's
unused atlas pixels are padded; native occupied surface colors are not mesh edits.

A deterministic hybrid can project the original photo or the eight calibrated
views over the native PBR base. Copy the committed reference set into a new ignored
trial directory, then use `meshaxiom_quality.py paint --material-base head-native.glb`.
The prepared nodes, accessors, UVs, normals, indices and positions must match exactly.
The original photograph covers 16.11% of occupied texels; learned predictions remain
elsewhere. Eight-view references increase observed coverage but can disagree on eyes.

## TRELLIS.2 through MLX

The pinned MLX port uses Microsoft's checkpoints. It supports a 512 pass without
cascade, higher-resolution cascades, 8/12/20 sampling steps, 4/8-bit optional flow
quantization, token limits, texture sizes and stage checkpoints. Its multiple-image
option concatenates DINO feature sequences. It does not supply calibrated camera
labels or a new multiview-trained checkpoint, so that route is an experimental
inference heuristic. The original CUDA implementation and this port are different
runtime implementations; source identity alone is not proof of numerical parity.

The pinned [official implementation](https://github.com/microsoft/TRELLIS.2/tree/75fbf0183001ed9876c8dbb35de6b68552ee08bd)
documents 512³–1536³ generation and supplied-shape PBR texturing, with a Linux/NVIDIA
CUDA environment and at least 24 GB GPU memory. Those CUDA timings and requirements
are distinct from the measured Apple implementations here.

| Option | Official / port support | Local trial scope |
| --- | --- | --- |
| Generation density | Official 512/1024/1536; MLX wrapper 512/768/1024 | 512 and requested1024 reduced to768 by token budget |
| Texture only on supplied shape | Official TRELLIS.2; MeshAxiom documents Pixal3D plus TRELLIS encoder/decoder | Pixal MPS image512 and image1024, both NAF512 |
| Sampling steps | MLX wrapper 8/12/20 | 12 in these TRELLIS and native-texture trials |
| Multiple images | MLX concatenates image-feature tokens; no calibrated view labels | Original identity plus one existing side-view reference |
| Quantization | MLX optional flow 4/8-bit | Available, not tested or ranked here |
| Atlas size | MLX wrapper 1K/2K/4K | Raw UV attempt bounded; verified vertex-color alternative used |
| Mesh cleanup / face target | Port normally supports these export operations | Disabled; every raw native triangle retained |

```sh
ATELIER_AGENT=meshaxiom-laptop nice -n 10 uv run python games/yorimichi/tools/head_models.py \
  trellis setup --root build/yorimichi/meshaxiom/head-models \
  --report build/yorimichi/logs/head-trellis-setup.guard --memory-gib 4
ATELIER_AGENT=meshaxiom-laptop nice -n 10 uv run python games/yorimichi/tools/head_models.py \
  trellis download --root build/yorimichi/meshaxiom/head-models \
  --report build/yorimichi/logs/head-trellis-download.guard --memory-gib 4
ATELIER_AGENT=meshaxiom-laptop nice -n 10 uv run python games/yorimichi/tools/head_models.py \
  trellis generate --root build/yorimichi/meshaxiom/head-models \
  --report build/yorimichi/logs/head-trellis-512.guard --memory-gib 12 -- \
  --image games/yorimichi/assets/characters/meshaxiom-skater-head/reference.png \
  --output build/yorimichi/meshaxiom/head-trellis-512 --resolution 512 --steps 12 \
  --vertex-colors
```

The raw recipe disables cleanup, simplification and hole filling and sets the
face target to zero. It keeps every native extracted triangle; UV seam splits are
permitted. The GLB is compared to the raw checkpoint after only the port's fixed
Z-up to Y-up rotation. Dense verification canonicalizes cyclic triangle rotations
in bounded chunks and compares sorted exact float32 records, retaining winding and
duplicate counts. This is verification, not repair. Raw meshes can contain millions
of triangles and be expensive to export or view despite modest neural-model memory.

The 512 trial uses an 8 GiB MLX memory setting and a separate 12 GiB aggregate
process-tree guard. MLX documents `set_memory_limit` as a guideline during graph
evaluation, not a hard allocation ceiling. The cascade selected 10 GiB but reported
11.04 GiB peak by MLX accounting; its actual process-tree peak was 13.06 GiB under
the enforced 14 GiB aggregate guard. Framework accounting is not physical process
footprint, and the outer guard is the safety ceiling. The adapter also drops the sparse-structure models from their caller
scope before loading shape models; deleting callee parameters does not release
caller references. Input preprocessing records the deterministic alpha mask,
foreground crop and prepared-image hash. Checkpoint/model state mismatches reject.

The measured 512 native output has 4,916,486 triangles. Raw UV unwrapping exceeded
its ten-minute phase bound; use `--vertex-colors` below for the tested UV-free path.
The recorded neural/checkpoint plus export stages total 331.22 seconds, excluding
the discarded UV attempt. They are separate measured stages.

`trellis compare` accepts `--model`, `--image`, `--output` and optional
`--yaw-offset` after `--`, under the same outer guard. It creates eight base-color
views with the same yaw/pitch labels and framing rule as MeshAxiom, recording any
camera-frame offset. For this head, pass `--yaw-offset -90` when comparing existing
vertex-color exports; the generation runner records that offset by default. The
source GLB bytes remain unchanged. Use a fresh report for
this separate render job. Base-color comparison avoids differences in PBR lighting;
interactive material inspection is a separate viewing check.

## A UV-free color-field bake for dense raw output

`head_models/vertex_bake.py` samples the learned native color by the decoder voxel
that produced each raw vertex. It verifies coordinate correspondence and rejects
missing/duplicate support. It writes the original raw indices and positions, after
the same fixed axis rotation, into a GLB and verifies them byte for byte. There is
no simplification, repair, smoothing or vertex movement. Linear vertex colors
represent the learned sRGB field; this preview uses uniform roughness/metallic
values, so it does not preserve the PBR field's material variation.

This is an alternative deterministic material bake when constructing UVs on a
multimillion-triangle raw output dominates the neural computation. It consumes
completed shape-decoder, raw-mesh and texture checkpoints; it makes no new model
or paid call. It streams the complete source JSON into gzip with bounded chunks.
Its optional eight-view renders use the same base-color camera/framing rule.

```sh
ATELIER_AGENT=meshaxiom-laptop nice -n 10 uv run python \
  games/yorimichi/tools/head_models/vertex_bake.py \
  --checkpoint build/yorimichi/meshaxiom/head-trellis-512/checkpoints \
  --image games/yorimichi/assets/characters/meshaxiom-skater-head/reference.png \
  --output build/yorimichi/meshaxiom/head-trellis-512-vertex \
  --report build/yorimichi/logs/head-trellis-vertex.guard --memory-gib 8 --render
```

The viewer's dense-GLB path checks the complete exported triangle count and renders
all triangles. It defers the optional browser edge-map construction and avoids
loading another giant JSON representation into the page. The downloadable source
and GLB remain complete. Color/gray switching also handles vertex-color materials.


For cascade experiments, `--mlx-gib 10` selects the MLX memory guideline and
`--max-tokens 16384` selects a strict token ceiling. The outer aggregate cap remains
independently enforced. Requested 1024 grids may reduce in 128-cell steps to meet the token
ceiling; the actual grid is recorded. This fixes the pinned port's early-exit
condition that otherwise ignores the limit at 1024 and can loop below a valid grid
when starting at 768. High stages use 1024-pixel DINO conditioning and the published
1024 texture flow, following the official cascade's stage choices. The 512 baseline
retains its 512 conditioning and texture checkpoint. No CUDA numerical-parity claim
is made for the MLX implementation.

`trellis generate -- ... --vertex-colors` stops after native shape/PBR checkpoints
and performs the UV-free bake in the same aggregate guard. It avoids repeating the
slow raw-mesh unwrap for every trial. The pinned feature extractor fails closed if
MLX extraction fails; it never falls back to an unpinned local Torch checkout or
random conditioning. Multiple `--image` inputs still use the port's documented
feature-concatenation heuristic without camera calibration.

## Reproduce the best lit head

This is the measured cascade recipe. It requests 1024 and records the effective grid;
the M1 Max trial selected 768 with 13,128 shape tokens and retained all 11,386,792
triangles. The whole guarded job took 20m07s at 13.06 GiB peak, including eight views.
Use the pinned `trellis setup` and `trellis download` commands above first.

```sh
ATELIER_AGENT=meshaxiom-laptop nice -n 10 uv run python games/yorimichi/tools/head_models.py \
  trellis generate --root build/yorimichi/meshaxiom/head-models \
  --report build/yorimichi/logs/head-trellis-cascade.guard --memory-gib 14 --timeout 3600 -- \
  --image games/yorimichi/assets/characters/meshaxiom-skater-head/reference.png \
  --output build/yorimichi/meshaxiom/head-trellis-cascade \
  --resolution 1024 --max-tokens 16384 --mlx-gib 10 --steps 12 --vertex-colors
```

Then run the deterministic shading-only pass. It computes area-weighted normal
tensors, filters them across triangle adjacency, and creates coincident normal seams
where winding requires different shading-normal signs. It never moves a position,
reverses a triangle or removes a face. The export verifies exact ordered triangle
position/color bytes and source-index mapping, including duplicate and degenerate
faces. Normal seam copies increase exported vertices to 8,580,395; they do not change
the geometric surface. All scene and original lit material bindings stay identical.

```sh
ATELIER_AGENT=meshaxiom-laptop nice -n 10 uv run python \
  games/yorimichi/tools/head_models/lit_normals.py \
  --model build/yorimichi/meshaxiom/head-trellis-cascade/head.glb \
  --output build/yorimichi/meshaxiom/head-trellis-cascade-lit \
  --report build/yorimichi/logs/head-trellis-lit-normals.guard \
  --iterations 16 --memory-gib 8
```

Use fresh output/report paths. This pass took 38.87 seconds at 3.92 GiB peak. The
separate native-generation and normal jobs sum to 20m46s, with maximum physical
footprint 13.06 GiB; queues/downloads and final browser review are excluded. The
zero-iteration control takes 13.27 seconds and fixes most grain; sixteen iterations
add modest shading smoothness. Standard double-sided lit shading now works without
unlit extensions or a custom viewer shader. The material still uses native RGB,
uniform roughness0.85/metallic0, rather than spatial PBR variation. Small raw surface
and color defects remain; this is not Tripo quality or a production/rigging approval.

The former `materials.py` standard-unlit export remains an optional diagnostic. It
preserves the entire raw binary but bypasses lighting; it is no longer the selected
setup. Eight matched actual WebGL views for both normal variants, a selected gray
control and the raw lit/unlit baselines are in the gallery. Browser QA also verifies
that changing light intensity changes the selected render.

The raw dense GLBs and full source archives are generated comparison outputs beneath
`build/yorimichi`, alongside SHA-bound model/geometry reports. The viewer offers
complete GLB/source downloads. They are not game-consumed inputs. The compact 7 MB
MeshAxiom native-PBR/front-photo head is committed at
`assets/characters/meshaxiom-skater-head-native/head.glb`, with its source manifest
and proofs, so a fresh checkout can use that asset without another generation.

## Original photograph over native vertex colors

A separate deterministic trial uses the same pinned Pixel Match visibility,
facing and matte weights on native TRELLIS vertices. It searches nine rigid
camera poses against the reference silhouette and changes only the COLOR_0
bytes. The GLB scene, materials, positions, normals and triangle buffers stay
identical, and vertices with zero weight retain their exact learned colors.
Silhouette registration does not prove eye/mouth correspondence; eight renders
are mandatory evidence for accepting or rejecting the output. No UV construction
or geometry fitting is involved.

```sh
ATELIER_AGENT=meshaxiom-laptop nice -n 10 uv run python \
  games/yorimichi/tools/head_models/vertex_photo.py \
  --model build/yorimichi/meshaxiom/head-trellis-512/head.glb \
  --image games/yorimichi/assets/characters/meshaxiom-skater-head/reference.png \
  --output build/yorimichi/meshaxiom/head-trellis-512-photo \
  --report build/yorimichi/logs/head-trellis-photo.guard --memory-gib 8
```
