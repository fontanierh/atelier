# MeshAxiom Apple Silicon proof of concept

This experiment runs the public MeshAxiom-Base EMA weights locally on a 32 GiB M1 Max MacBook Pro,
using GPT Image 2.5 Sunburst references for Yorimichi. It produced a recycling bin, a street-food cart
and a character head. The two larger meshes exceed the requested 15,000 usable triangles without
subdivision or replacing the generated connectivity.

| Asset | Raw / usable triangles | Local geometry inference | Peak process-tree memory |
| --- | ---: | ---: | ---: |
| Recycling bin | 1,938 / 1,935 | 6m 33s | 6.42 GiB |
| Street-food cart | 16,983 / 16,960 | 40m 12s | 6.77 GiB |
| Skater head | 18,931 / 18,925 | 56m 39s | 6.83 GiB |

Usable counts exclude duplicate, repeated-index and zero-area triangles. These are measured geometry
runs, excluding downloads, reference generation, capacity waits, UVs and textures. The meshes remain
experimental: face count and learned connectivity do not establish production or animation quality.

The complete model pipeline produced **1,049 vertices and 1,938 triangles in 392.69 seconds** on the laptop,
with a **6.42 GiB** maximum measured process-tree footprint. Both stages used the normal 10 GiB guards,
exited cleanly and returned all resources; supervisor samples showed no new swap-out. The authored
1-metre GLB and four CPU review views completed in another 45.77 seconds at 1.07 GiB peak.
The bin proves that the full pipeline runs locally, but its visual result needs substantial cleanup.

## Measured run

| Stage | Worker time | Aggregate guard peak |
| --- | ---: | ---: |
| Vertex, nine octree levels and MBR8 coarse selection | 323.48 s | 6.42 GiB |
| Topology diffusion, VAE decoding and extraction | 69.21 s | 5.33 GiB |
| Total local geometry inference | 392.69 s | 6.42 GiB maximum |

These times include model loading and checkpoint checks for the measured stage. They exclude the
initial model download, the 30-second Sunburst request, capacity queue time and Blender authoring.
Validation probes had already warmed filesystem and Metal caches; this is not a cold-boot benchmark.
The vertex model held 4.39 GiB of MPS weights. Before VAE loading, topology model memory fell to zero;
the decoder then held 0.13 GiB. `assets/props/recycling-bin-meshaxiom/benchmark.json` retains the counts,
settings, mesh audit and selected positive guard-exit evidence without machine-private paths.

The raw mesh has 214 boundary edges, three degenerate triangles, five components and no nonmanifold
edges. It is an experimental decorative prop, not a watertight fabrication mesh. The upstream topology
policy includes bounded edge-capacity repair and winding correction; the report identifies those steps.
The authoring script adds scale, origin and matte materials without replacing the neural geometry.
The cabinet, lid, door and feet are recognizable. Both reference bottle apertures were lost, and a
large diagonal front face remains. One nonorientable component and 12 inconsistently wound two-face
edges remain after upstream orientation correction. This first asset is not production-approved.
The initial port used `2 × realized vertices` for the extraction cap; this was corrected to the requested
face budget before the larger runs. The first bin's union of both decoded edge graphs is 3,534 edges,
below both the correct 6,000-edge cap and the initial 6,294-edge cap, so that discrepancy did not alter it.

## Models and memory

Checkpoint tensor metadata was read directly from the pinned release. Every released tensor uses FP32.
The vertex transformer and topology transformer each have 22 layers, width 2,048 and 16 heads.

| Bundle | Parameters | FP32 storage | Calculated 16-bit storage |
| --- | ---: | ---: | ---: |
| Vertex including conditioning | 2,808,789,256 | 10.46 GiB | 5.23 GiB |
| Vertex with unused point-cloud encoder omitted | 2,355,384,328 | 8.77 GiB | 4.39 GiB |
| Topology including conditioning | 2,355,808,448 | 8.78 GiB | 4.39 GiB |
| Topology autoencoder | 111,512,256 | 0.42 GiB | 0.21 GiB |

The two main models are sequential, so fitting both simultaneously is unnecessary. The tested adapter
keeps normalization and small buffers in FP32 and casts Linear layers to BF16, following the upstream
CUDA autocast arithmetic policy. It does not use four-bit quantization or stream layers from SSD.

## Apple Silicon adaptations

The implementation lives in `platform/studio/atelier/ai/meshaxiom/`. Upstream source is pinned and installed
in the ignored build tree; the adapter does not vendor or rewrite it.

- Build the architecture on PyTorch's meta device, assign checkpoint mmap tensors strictly, omit the unused
  point-cloud branch, and move one parameter at a time. This avoids a second full allocation during loading.
- Replace CUDA-only execution machinery with PyTorch MPS operations. Preload Transformers' DINOv3 module
  before entering the meta-device context, so its lazy module resolution does not run inside that context.
- Calculate the original FP64 3D rotary-position tables on CPU, cache them and transfer FP32 sine/cosine
  tables to MPS. Metal has no native double-precision tensor path.
- Tile attention queries while retaining every key and value. This bounds memory without truncating geometry.
  At 26,000 tokens, one explicit FP32 attention-score matrix for 16 heads would otherwise occupy 40.3 GiB.
- Compute rich nearest-neighbour/PCA topology features once on CPU rather than repeating them at every step.
- Retain the upstream mean/sample topology decoding and bounded edge-capacity repairs; record that policy
  with the output. Mesh repairs and later game materials are distinct from raw neural vertex generation.

## Reproduce

See `platform/studio/atelier/ai/meshaxiom/README.md` for the isolated installer and guarded command.
Start with a 2,000-face request, the default 20-step schedule, and the normal 10 GiB guard. The implementation
prints each completed diffusion step and refuses geometry growth beyond its explicit node bound.

The tested machine is an M1 Max MacBook Pro with 10 CPU cores, 32 GPU cores, 32 GiB unified memory and
macOS 26.2. No remote GPU or paid 3D service was used. The one paid operation for the first asset was
the Sunburst reference; inference uses the downloaded public weights. The practical low-cost route is
this resident, sequential MPS implementation on an existing Apple Silicon Mac, without buying a CUDA PC.
The 6.42 GiB figure is the small bin's observed process-tree peak; the larger runs measured up to
6.83 GiB. Neither is a minimum system-RAM promise. Smaller-memory Macs and other chips are unmeasured.
For a lower-memory Mac, start with the 2K request and 10 GiB guard, retaining the host reserve; do not
copy the owner-selected 16 GiB reservation onto a 16 GiB computer. A 16 GiB Mac is a plausible target
for the resident implementation, but needs its own guarded validation. No streamed-weight runner is
required for the tested laptop.

Keep at least 30 GiB free for the initial 19.66 GiB checkpoint payload, source and isolated dependencies.
Install once, retain the verified files and use a fresh output/report directory for each attempt. Close
other memory-intensive applications. Admission still checks available memory and the host reserve before
launching a model; an idle-looking machine alone does not authorize admission. Do not change the MPS
high-watermark setting, disable guards or treat operating-system swapping as an inference strategy.

The first reference is reproducible from the committed prompt and provenance next to its PNG. New
references use `atelier.ai.images.paint(..., model='gpt-image-2.5-sunburst', quality='high', record=...)`;
the ledger record must not already exist. Reusing the committed PNG requires no API call or credential.
This is a single-image model. Its released `generate(image, ...)` interface has no native multiview
conditioning; concatenating a turnaround sheet is not a verified substitute.

The first authored source is `assets/props/recycling-bin-meshaxiom/recycling_bin.glb`, with raw neural
geometry, a complete checksum manifest and benchmark beside it. Recreate its scale/material export and
four review images with the guarded Blender command below (the inference result must already exist):

```sh
ATELIER_AGENT=YOUR_BOARD_OWNER nice -n 10 uv run python -m atelier.safety.guarded \
  --report build/yorimichi/logs/meshaxiom-preview-new.guard --timeout 600 \
  --purpose 'MeshAxiom prop authoring and review' -- \
  /Applications/Blender.app/Contents/MacOS/Blender --background --threads 2 \
  --python games/yorimichi/tools/meshaxiom_prop.py -- \
  --mesh build/yorimichi/meshaxiom/bin-2k/mesh.json \
  --output games/yorimichi/assets/props/recycling-bin-meshaxiom \
  --previews build/yorimichi/meshaxiom/previews
```

## Larger-object follow-up

After inspecting the first bin, the owner requested a food cart and a character head, at least 15,000
faces each, and explicitly authorized a **16 GiB** session ceiling. Both Sunburst high references are
retained in the asset library. The inference condition is 16,000 faces; actual output counts must be
checked separately. The cart has completed with **9,169 vertices, 16,983 raw triangles and 16,960 unique
nondegenerate triangles**. Vertex inference took 1,496.54 seconds and topology took 915.26 seconds:
**40m 12s of worker time**, excluding queue waits and other interleaved jobs. Maximum aggregate footprint
was **6.77 GiB**; both guards ended with complete empty cleanup and no new swap-out was observed.

The cart has 1,827 boundary edges, 92 connected components, 23 degenerate triangles and no nonmanifold
edges. The published orientation pass leaves 76 inconsistently wound edges and ten nonorientable pieces.
Its face minimum passes, but this is an experimental mesh requiring cleanup. Visual inspection retained
the roof ribs, spoked wheels and steamer, while the lower cabinet boards, curtain and bottle are missing
or substantially simplified. Some roof/post junctions have gaps and stretched triangles. The
1.8-metre, ground-origin export uses simple wood/indigo preview materials. A format round-trip verified
every original triangle and winding, the height and ground position, and byte-identical served downloads.
The source is retained losslessly as `assets/props/food-cart-meshaxiom/mesh.source.json.gz`; decompressing
it reproduces the native JSON SHA256 in the manifest. The exporter and viewer accept either JSON or gzip.

```sh
uv run python games/yorimichi/tools/meshaxiom_export.py \
  --mesh games/yorimichi/assets/props/food-cart-meshaxiom/mesh.source.json.gz \
  --output build/yorimichi/meshaxiom/food-cart/reproduced.glb --height 1.8 --palette cart
```

The head completed **9,554 vertices, 18,931 raw triangles and 18,925 unique nondegenerate triangles**.
Vertex inference took 2,522.16 seconds and topology took 876.49 seconds, totaling **56m 39s** at
**6.83 GiB** maximum aggregate footprint. Both guards exited with complete empty cleanup; no new
swap-out was observed. Its audit finds 1,323 boundary edges, six connected components, six degenerate
triangles and no nonmanifold edges. The orientation pass leaves 455 inconsistently wound edges and
one nonorientable piece. The raw source and benchmark are retained next to the head reference.

`atelier.ai.meshaxiom.guarded` reserves the full selected memory and GPU envelope in an explicit broker
session and uses the existing per-process and aggregate guards. The shared profile, 4 GiB host reserve,
managed CPU budget and checkout locks remain intact. The README includes the exact staged command.
The larger request uses a 12,000-node hard bound and a one-hour deadline per stage. The head follows
the cart as a separate job; no two inference models are launched together.

Topology acceptance includes at least 15,000 unique nondegenerate triangles for the larger assets,
boundary and nonmanifold edges, degenerates,
components, silhouette and wireframe inspection. Learned connectivity and the published edge-capacity
policy do not guarantee animation-ready facial edge loops, watertight surfaces or clean production
topology. Any later cleanup must retain a raw source and describe the geometry changes; subdivision
alone must not be presented as newly inferred detail.

## Pixel Match texture comparison

The owner also requested the approach documented in the [Nox recipe](NOX_CHARACTER_RECIPE.md#4-paint-the-hidden-face-without-rebuilding-the-hair).
`games/yorimichi/tools/meshaxiom_pixel_match.py` uses that same committed projection module from
`Bingeljell/image-to-3dlab`, revision `7793fd3622bab7d3fd4526ba02433244d5bf02e2`, verified by SHA256.
It projects the existing Sunburst pixels into UVs; it does not infer new geometry. MeshAxiom's geometry
model takes one image, while the Pixel Match projection module accepts a list of calibrated texture views.
The first comparison uses one view and retains neutral material on unseen surfaces.

Unlike Nox's existing atlas and face-only repairs, this new mesh initially has no UVs. The Blender
adapter adds Smart UV Project islands and a neutral 2K atlas to the native triangles, with uniform
scale and origin changes only. Smart UV Project changes UV layout, not topology. A small-field-of-view
perspective camera is fitted against the reference silhouette; the calibration clay render and overlay
must then be inspected for eye, nose, mouth and chin registration. Silhouette agreement alone does not
establish facial alignment. Explicit yaw/pitch overrides allow a correction without changing the mesh.

Projection uses depth visibility, facing confidence and the reference matte. Near-black pixels connected
to the image border become background; enclosed dark eyes and hair pixels remain intact. Global colour
matching is disabled so unseen surfaces retain their original neutral base. The runner saves confidence,
protected and changed-texel masks, protects empty gutters within four texels of unseen UV coverage,
and verifies unchanged positions, UVs, indices and every non-texture GLB buffer. Focused tests exercise
real projection onto visible and occluded surfaces and reject changed calibration inputs.

After the head's geometry exists, run each stage through normal admission with a fresh report directory:

```sh
ATELIER_AGENT=YOUR_BOARD_OWNER nice -n 10 uv run python -m atelier.safety.guarded \
  --report build/yorimichi/logs/meshaxiom-head-uv-new.guard --timeout 600 \
  --purpose 'MeshAxiom head UV preparation' -- \
  /Applications/Blender.app/Contents/MacOS/Blender --background --threads 3 \
  --python games/yorimichi/tools/meshaxiom_uv.py -- \
  --mesh build/yorimichi/meshaxiom/skater-head/16k/mesh.json \
  --output build/yorimichi/meshaxiom/skater-head/pixel-match --height .35

ATELIER_AGENT=YOUR_BOARD_OWNER nice -n 10 uv run python -m atelier.safety.guarded \
  --report build/yorimichi/logs/meshaxiom-head-camera-new.guard --timeout 900 \
  --purpose 'Pixel Match camera calibration' -- \
  python -u games/yorimichi/tools/meshaxiom_pixel_match.py calibrate \
  --module games/yorimichi/tools/pixel_match/photo_paint.py \
  --mesh build/yorimichi/meshaxiom/skater-head/pixel-match/clay-uv.glb \
  --image games/yorimichi/assets/characters/meshaxiom-skater-head/reference.png \
  --output build/yorimichi/meshaxiom/skater-head/pixel-match
```

Inspect `calibration-clay.png` and `calibration-overlay.png` before painting. Repeat the second command
with a new guard report and explicit `--yaw`/`--pitch` if needed. Then use that calibrated camera:

```sh
ATELIER_AGENT=YOUR_BOARD_OWNER nice -n 10 uv run python -m atelier.safety.guarded \
  --report build/yorimichi/logs/meshaxiom-head-paint-new.guard --timeout 900 \
  --purpose 'Pixel Match texture projection' -- \
  python -u games/yorimichi/tools/meshaxiom_pixel_match.py paint \
  --module games/yorimichi/tools/pixel_match/photo_paint.py \
  --mesh build/yorimichi/meshaxiom/skater-head/pixel-match/clay-uv.glb \
  --image games/yorimichi/assets/characters/meshaxiom-skater-head/reference.png \
  --output build/yorimichi/meshaxiom/skater-head/pixel-match
```

The completed head used a 35 cm export and a 2,048 by 2,048 atlas. UV preparation and camera fitting
took **10.21 seconds** at **0.70 GiB** peak. The selected camera is yaw 60 degrees, pitch -5 degrees;
its 96-pixel silhouette IoU is 0.947. Visual inspection found an approximate eye/nose/mouth/chin fit,
with remaining facial registration error. A triangle-coordinate comparison verified every original
triangle and its winding after scale/origin/axis conversion, despite UV seams splitting the exported
vertex count from 9,554 to 20,006.

Actual Pixel Match projection took **1.7 seconds**, followed by 1.0 second of protection and geometry
validation. Projection, staging and three-model browser QA together used **56.87 seconds** at
**1.32 GiB** peak. Both jobs used the normal 10 GiB guard and exited with complete empty cleanup.
Of 228,161 covered UV texels, 34,845 received reference color (**15.27% of occupied UV texels**, not a
physical surface-area percentage); all 193,316 protected texels remained unchanged. Positions, UVs,
indices and every non-texture buffer remained identical. The fragmented Smart UV layout occupies only
5.44% of the atlas, limiting effective texture resolution despite its nominal 2K size.

The front gains recognizable skin, eyes and hair color. The opposite cheek, nose side, much of the
hair and the back retain neutral patches; eye/mouth borders and hair tips show seams or jagged edges.
Front, side and rear views were inspected. This is a partial texture comparison, not a finished
character: better UV packing, calibrated additional views, winding/normal cleanup and facial retopology
are still needed. Inspect the underside before production acceptance. The projection includes the
reference's painted lighting and cannot repair malformed ears, missing surfaces or facial edge loops.
The head's asset directory retains the clay and painted GLBs, base color, matte, confidence/protection/
change masks, calibration, geometry verification and timing reports with checksums.

## Interactive inspection

`games/yorimichi/tools/meshaxiom_viewer.py` stages only explicitly supplied geometry, image and GLB
inputs into `build/yorimichi/meshaxiom/viewer`. Its adjacent README gives the loopback HTTP and
Tailscale Serve commands. The page supports orbit, zoom, wireframe, gray/color comparison and a
model selector, plus a red open-edge overlay. Browser checks on the live tailnet route verified the
cart and both head GLBs, their native triangle counts, all toggles, phone layouts and no page errors.
The owned browser closed after the checks. Fetching the served mesh, reference and GLB reproduced the source
SHA256 values. The viewer uses the committed, pinned Three.js bundle and no external CDN.

JSON-mode colors are simple preview materials. With `--render-glb`, the viewer loads the supplied
export's actual materials and texture and verifies its triangle count against the generated mesh.
The downloadable GLB preserves the supplied export bytes. Both display modes normalize height and
origin; JSON mode also converts Z-up to Y-up. These display transforms do not change connectivity.
Only completed meshes enter the model selector.

## If weights have to stream from SSD

SSD layer streaming was **not needed or implemented** for the measured run. The largest resident
image-only model is about 4.39 GiB at 16-bit precision, and the transformer stages are sequential.
Checkpoint mmap avoids a second full CPU copy during loading; it does not mean transformer layers
are fetched from disk anew at every denoising step.

A simple I/O estimate shows the cost of genuine layer offload. Vertex generation makes roughly
`9 levels × 20 steps × 2 guidance branches = 360` transformer evaluations. Topology adds roughly
40 more, plus its mean-estimation work. If about 4 GiB had to be reread for every evaluation, that is
about 1.6 TiB of traffic. At an assumed sustained 1–3 GiB/s, disk reads alone would take roughly
9–27 minutes, before accounting for compute, transfers, synchronization and any overlap. These are
illustrative bandwidth assumptions, not measured SSD or end-to-end timings. They are not a prediction
for the 16K assets. Retaining some layers reduces traffic, and CPU execution changes the tradeoff.
An actual small-RAM implementation would need its own benchmark. Four/eight-bit quantization is another
possible route, but no quantized checkpoint, kernel port or output-quality validation is supplied here.

## Provenance

- Upstream source: `AlayaLab/MeshAxiom`, revision `6504db7126ec58e9d275833fb0e5f66640b01abe`.
- Model: `AlayaLab/MeshAxiom-Base`, revision `b80240ce4f77a28bc4debdcca895e96c78ddb294`.
- Reference: `assets/props/recycling-bin-meshaxiom/reference.png`, with prompt and paid-call provenance beside it.
- Reference model: `gpt-image-2.5-sunburst`, quality `high`, one 1024 by 1024 generation, 30.0 seconds.
- Dependencies: isolated Python 3.12, PyTorch 2.7.1, torchvision 0.22.1, Transformers 4.57.3; complete pins in the runner.

The upstream standalone code/weight licence assignment remains pending. Pretrained weights and downloaded
upstream code remain outside git; retained DINOv3 and third-party terms still apply. This experiment does
not assert a new licence for those materials.
