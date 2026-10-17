# MeshAxiom Apple Silicon proof of concept

This experiment generates a neighborhood recycling-bin prop for Yorimichi on a 32 GiB M1 Max MacBook Pro.
The input is a GPT Image 2.5 Sunburst reference with a faded indigo cabinet and ochre lid, matching the
street and skate-park palette. Geometry is inferred locally using the public MeshAxiom-Base EMA weights.

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
The 6.42 GiB figure is an observed process-tree peak for the small bin, not a minimum system-RAM promise
or a measurement for a 16,000-face object. Smaller-memory Macs and other chips are unmeasured.

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
checked separately. At this documentation checkpoint, the cart vertex stage is queued behind a machine
capacity-recovery hold; neither larger asset has a measured result yet.

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

## Interactive inspection

`games/yorimichi/tools/meshaxiom_viewer.py` stages only explicitly supplied geometry, image and GLB
inputs into `build/yorimichi/meshaxiom/viewer`. Its adjacent README gives the loopback HTTP and
Tailscale Serve commands. The page supports orbit, zoom, wireframe, gray/color comparison and a
model selector, plus a red open-edge overlay. A browser check on the live tailnet route verified model loading, all toggles, the
phone layout and no page errors. Fetching the served mesh, reference and GLB reproduced the source
SHA256 values. The viewer uses the committed, pinned Three.js bundle and no external CDN.

The displayed colors are simple preview materials. The downloadable GLB preserves the supplied
export bytes, while the viewer converts Z-up JSON into Y-up and normalizes its displayed height.
This display transform does not change connectivity. Only completed meshes enter the model selector.

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
