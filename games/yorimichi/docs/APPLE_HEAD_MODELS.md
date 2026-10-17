# Local Apple Silicon head model recipes

These experiments use the published neural models on the laptop. Sunburst high
supplies reference images; it does not generate the 3D meshes. The comparison and
measured results are in [MESHAXIOM_HEAD_QUALITY.md](MESHAXIOM_HEAD_QUALITY.md).
The machine is a 32 GiB M1 Max. A process ceiling is distinct from installed RAM.

## Isolated runtimes and exact weights

`tools/head_models.py` owns normal admission and one aggregate process-tree guard
for installation, downloads, inference and comparison renders. The explicit larger
memory reservation uses the existing reviewed MeshAxiom adapter. It never changes
machine profiles, host reserves or other owners' processes. Each attempt needs a
new report directory. Commands expected to take more than thirty seconds must run
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
published 1024 texture checkpoint. Full 1024 conditioning is a separate experiment;
a successful reduced recipe must not be called a successful full-default run.
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
  --output build/yorimichi/meshaxiom/head-trellis-512 --resolution 512 --steps 12
```

The raw recipe disables cleanup, simplification and hole filling and sets the
face target to zero. It keeps every native extracted triangle; UV seam splits are
permitted. The GLB is compared to the raw checkpoint after only the port's fixed
Z-up to Y-up rotation. Dense verification canonicalizes cyclic triangle rotations
in bounded chunks and compares sorted exact float32 records, retaining winding and
duplicate counts. This is verification, not repair. Raw meshes can contain millions
of triangles and be expensive to export or view despite modest neural-model memory.

The 512 trial uses an 8 GiB MLX allocation limit and a separate 12 GiB aggregate
process-tree guard. Both remain active; framework accounting is not physical process
footprint. The adapter also drops the sparse-structure models from their caller
scope before loading shape models; deleting callee parameters does not release
caller references. Input preprocessing records the deterministic alpha mask,
foreground crop and prepared-image hash. Checkpoint/model state mismatches reject.

`trellis compare` accepts `--model`, `--image`, `--output` and optional
`--yaw-offset` after `--`, under the same outer guard. It creates eight base-color
views with the same yaw/pitch labels and framing rule as MeshAxiom, recording any
camera-frame offset. The source GLB bytes remain unchanged. Use a fresh report for
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
