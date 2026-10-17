# Local textured-head comparison

Work in progress: this comparison will rank all locally generated candidates after
the native Pixal3D texturing and Microsoft TRELLIS.2 experiments finish. Each
candidate is inspected from eight matched yaw/pitch labels, including both profiles,
rear, top and underside. No post-generation mesh editing is allowed.
The existing [Apple Silicon experiment](MESHAXIOM_EXPERIMENT.md) supplies the pinned
weights, runtime installation, single-view baseline, and hardware measurements.

## Measured comparisons so far

The baseline has 18,931 native triangles (18,925 nondegenerate), 1,323 boundary edges
and six connected components. UV authoring and projection preserve those defects.
The previous atlas occupied 5.44% of its pixels. Three automated Smart UV trials
occupied 46.52%, 46.86% and 48.85%; the last used an 89-degree angle and 0.00005
island margin. Its 2,048,854 occupied texels provide about nine times the previous
texel area. This is a packing measurement, not proof of better visual quality.
Preparation took 19.89 seconds and peaked at 1.26 GiB on the M1 Max.

The following eight-view comparison reproduced **on the M1 Max** under a 4 GiB
aggregate guard. Its five GLBs match the earlier hosted macOS results byte for byte.
All five outputs preserved every native triangle and winding. Times include
projection and buffer validation, but exclude the
eight diagnostic renders per output and remote image generation.

| Projection | Occupied texels painted | Seconds | Observed result |
| --- | ---: | ---: | --- |
| Original single image | 16.11% | 3.94 | Most sides and back stay neutral |
| Geometry-guided front | 16.33% | 4.53 | Better alignment, similar limited coverage |
| Eight-view weighted blend | 55.11% | 16.65 | Doubled facial features |
| Eight-view best angle | 55.11% | 17.21 | Broken pupil shapes at view boundaries |
| Eight-view front first | 56.06% | 17.08 | Coherent eyes; side seams and neck patches remain |

The complete local five-variant run, including forty diagnostic renders, took
108.24 seconds and peaked at 1.96 GiB. The earlier hosted run took 164.10 seconds
and peaked at 1.91 GiB; those hosted timings are separate from laptop benchmarks.
The nine additional Sunburst
reference calls include eight selected views and one rejected guided opposite-view candidate;
the identity image comes from the earlier experiment. A further eight calls supplied
the independently generated denser head below.

On the laptop, the selected eight-view recipe reproduced the hosted 2K GLB
byte for byte. Its projection and validation took 17.07 seconds at 2K and
35.10 seconds at 4K. The complete pair, including sixteen diagnostic views,
took 75.78 seconds and peaked at 7.14 GiB under the unchanged 10 GiB CPU guard.
The 2K output is 2.96 MB; 4K is 7.05 MB. Painted coverage was 56.06% and 56.08%
of occupied texels respectively. Both preserve all 18,931 triangles and winding.
At matched viewing size, 4K adds modest detail but does not remove side seams,
patches, or the original surface defects. The 2K output is the cheaper default.

A separate deterministic color-completion pass extrapolated nearby surface-cell
colors into 352,560 previously unobserved occupied texels (17.21% of occupied
texels). All 1,148,583 observed texels remain byte-identical, as do every
non-image GLB buffer and the original native triangles/winding. This is color
extrapolation, not additional observed coverage. It took 15.23 seconds and peaked
at 1.10 GiB under a 4 GiB aggregate guard. It removes some neutral hair patches,
but the cheek seam and existing shape defects remain visible.

## Native learned PBR and hybrid textures

The native texture recipe named by MeshAxiom uses Tencent Pixal3D's image/shape
texture flow with TRELLIS.2's supplied-shape encoder and PBR decoder. It now runs
locally on MPS without changing the supplied mesh or its UVs. The successful trial
used 512-pixel DINO/NAF conditioning, 1024 shape support, twelve texture sampling
steps, seed 42 and a 2K atlas. This is the documented model stack adapted to a
smaller conditioner, not a successful run of its full 1024-pixel default recipe.

The complete guarded job took 590.93 seconds, including eight diagnostic renders;
the verified GLB was ready after 582.59 seconds. Peak aggregate physical footprint
was **11.75 GiB**, under a 14 GiB process-tree ceiling and a separate 12 GiB MPS
allocator ceiling. No new swap-out was observed. Every original non-image buffer
and all 18,931 native triangles/winding remain unchanged. The decoder produced
5,872,775 finite PBR voxels. Materials cover unseen sides well, but the eyes and
facial details are softer than the projected photographs. The CPU comparison
renders show base color with matched cameras; the interactive viewer also loads
the native metallic/roughness map.

Full-size conditioning attempts hit their explicit MPS allocator limits and
exited cleanly. A 16 GiB aggregate attempt was refused before work because the
reservation plus unchanged host headroom did not fit. These failures are not
claims that the default model recipe runs within the available envelope.

Two deterministic hybrid trials retain that native PBR base outside calibrated
photo coverage. The original image replaces 16.11% of occupied texels; eight
front-first views replace 56.06%. The two-output job, including sixteen renders,
took 40.98 seconds and peaked at 2.04 GiB under a 4 GiB aggregate guard. The
single-front hybrid has sharper eyes and smoother sides than the eight-view
hybrid, which inherits the photo disagreement and cheek seam. Unobserved base
colors are learned predictions, not observed texture coverage. Neither hybrid
changes geometry, normals, UVs, indices or the native metallic/roughness image.

`paint --material-base PATH` checks the original prepared mesh's nodes, accessors,
primitives and every non-image buffer before using a different material base.
It rejects position, normal, UV, index or node-transform differences. Reference
generation cameras remain bound to their original clay guides; projection
records separately identify the PBR target GLB.

## Higher native density

The 30,000-face request produced 14,936 vertices and **29,427 native triangles**
(29,420 nondegenerate), using the original identity image, seeds and 20 sampling
steps. Vertex generation took 3,470.25 seconds; topology took 1,670.99 seconds.
The combined worker time was 85 minutes 41 seconds, excluding queues, references,
UVs and painting. Peak physical footprint was 7.85 GiB for vertices and 7.52 GiB
for topology. The stages used actual 16 GiB and 12 GiB aggregate ceilings respectively.

The new head has 1,197 boundary edges, three components, no nonmanifold edges and
seven degenerate faces. Its UV atlas occupies 53.40%, up from 48.85% on the earlier
head. Every native triangle and winding survives UV authoring and texturing.
It remains an open experimental mesh; the face count is not a rigging approval.

Reusing the earlier eight photos failed the independent target-silhouette gate:
overlap ranged from 88.44% to 94.93%. No threshold or source receipt was changed.
Eight fresh Sunburst high references were generated from the new head's own
cameras. Front-first projection painted 62.64% of occupied texels in a complete
28.39-second run, including eight diagnostic renders, peaking at 2.03 GiB under
a 4 GiB guard. Color completion filled another 250,921 occupied texels while
preserving observations; it took 13.32 seconds and peaked at 1.03 GiB.

At matched viewing size the denser head adds some ear and silhouette detail,
but it still has the cheek seam and introduces worse eye/lip alignment and pale
hair patches in these texture samples. The earlier completed 2K head is stronger
so far. This comparison changes both native geometry and geometry-guided reference
images: it does not isolate face density as the cause of any texture difference.

## Memory and a cheaper replay

These measurements come from a 32 GiB M1 Max. A 16 GiB process ceiling does not
demonstrate operation on a laptop with 16 GiB total: macOS and other processes
also need memory. Texture replay needs neither MeshAxiom weights nor a GPU model.
The measured 2K projection peaks near 2 GiB, whereas the complete 2K/4K pair
peaks near 7.14 GiB. Reuse the committed eight images and run only the 2K
`front-first` variant under a 4 GiB guard for the cheaper texture pipeline.
The guard must still obtain normal admission on a shared machine.

The first 16 GiB topology reservation was refused before useful work because the
full reservation plus the existing 4 GiB host headroom did not fit. Its guarded
launcher exited with empty, complete cleanup. A new run uses a **lower 12 GiB
actual-child and aggregate ceiling**, with a matching 12 GiB broker reservation;
no shared profile, reserve or guard was changed. The owner's 16 GiB maximum is
an upper bound, not a requirement to reserve unavailable memory.

Native generation uses the sequential, mmap-backed model lifecycle documented in
the Apple Silicon experiment. The 30,000-face vertex request completed with 14,936
vertices in 3,470.25 seconds and peaked at 7.85 GiB. The requested face count is
conditioning, not an exact output count; its topology and geometry comparison
are measured separately. No disk-streaming performance estimate substitutes for
these actual runs.

## Constraint and experiment matrix

The geometry is never edited after native MeshAxiom generation. No retopology,
decimation, subdivision, hole filling, vertex movement, sculpting, or manual Blender
work is used. The published topology decoder remains part of native generation.
UV seams may duplicate exported vertices. Every triangle's three positions and winding
are compared with the original output at float32 precision after the same uniform
scale, origin and Z-up to Y-up conversion used by the baseline.

Compare the original 18,931-triangle head with:

1. Better UV packing, the original image, and a 2K atlas.
2. A geometry-guided front image, then seven and eight geometry-guided Sunburst views.
3. Weighted blending versus best-angle reference selection, without changing UVs or geometry.
4. A 4K atlas with the same UVs and geometry.
5. A new 30,000-face native request using the original reference, seed and 20-step recipe.
   Requested density is conditioning; it is not a guarantee of actual face count.

The original request was 16,000 faces. The higher request stays within upstream's public
30,000-face limit and the existing 26,000-vertex safety bound. The native stages use
separate aggregate ceilings and matching full broker reservations, up to the owner's
16 GiB maximum; shared machine profiles and host reserves stay unchanged. Each stage
has a two-hour deadline.

## Pipeline

`meshaxiom_quality.py prepare` runs Blender headlessly for three Smart UV configurations,
verifies all native triangles, measures actual atlas occupancy, and chooses the fullest
packing. It renders eight known perspective cameras from the fixed surface. This is
scripted UV authoring and rendering, not manual mesh editing.

`references` makes eight sequential GPT Image 2.5 Sunburst high-quality edits. Each call
receives the identity reference and one fixed-camera clay render. It requests exact
silhouette, feature positions and framing, with flat material colors. Every paid request
has an exclusive provenance ledger, full prompt, input hashes and camera matrix; an
uncertain call is never retried automatically. Successful calls can be run in separate
explicit view subsets; rerunning an existing ledger refuses before submission.

`paint` rejects generated views with silhouette overlap below 95%. This checks the outer
shape, not facial feature consistency. It compares the original and geometry-guided
single-view projections, the pinned
Pixel Match weighted blend, and a deterministic most-frontal visible-view selection.
Occlusion, matte and grazing-angle weights protect unseen texels, which remain neutral.
Neither painting method repairs mesh defects or invents unseen geometry.

The first seven-view results exposed doubled eyes in weighted blending and broken
pupils in per-texel best-angle selection. The next variant keeps the front image
where its visibility confidence is at least 0.3, then fills remaining texels from
the opposite face, profiles, rear, top and underside. It samples accepted colors
at full weight. Triangle normals are used only for projection confidence, avoiding
cancellation in averaged normals; the stored mesh normals also remain unchanged.
Its facing thresholds are 0.08/0.35 and silhouette fade is two pixels. These choices
are recorded with each result. The 4K variant uses this same coherent projection.

An additional opposite-view experiment uses the already projected front as guidance.
The `guide` stage crops that camera from the completed diagnostic contact sheet and
records the source model/contact hashes and crop rectangle. It preserves the original
camera and pure-clay silhouette check. Sunburst fills its neutral-gray regions while
using the existing face colors and gaze as context. The new reference has a separate
filename and paid receipt; previous paid inputs remain in the experiment archive.
The candidate worsened rendered eye alignment even with the projected front as context.
The selected recipe therefore retains the earlier eight independent geometry-guided views.
Its rejected candidate inputs remain available with `guides/cameras-coherent.json` for
reproducing the negative experiment. No geometry changes are made when constructing
its guide or projecting the result.

That candidate initially failed silhouette overlap at 90.7%. `register` corrected its
image framing with a 1.03725 uniform scale and translation of (-16.52, -20.33) pixels,
raising overlap to 96.8%. The raw paid PNG remains unchanged. Its registered copy and
sidecar record identify both inputs, output hash and transform. No nonuniform warp,
mesh change or camera-threshold exception is used. Registration rejects scales beyond
0.85–1.15, shifts beyond 12% of image width, or final overlap below 95%.

For each result it verifies both the native triangle multiset and byte-identical
non-image GLB buffers. It saves confidence, protected/changed masks and eight diagnostic
renders. Coverage means the fraction of occupied UV texels reached by a reference;
it is not a measurement of physical surface area or a visual-quality score.

For a separately generated denser head, `paint --reference-set PATH` can reuse the
earlier photos after a fresh `prepare` on the new native output. The source UV mesh,
paid cameras and guide hashes remain bound to the original generation; the new UV
mesh and projection cameras are recorded separately. Both the original image/guide
fit and the image/new-guide fit must reach 95% silhouette overlap. A passing outline
does not prove facial correspondence, so rendered eyes, mouth and ears still decide
whether this transfer is useful. A failure is rejected rather than hidden by changing
the camera receipt or weakening the threshold. This is texture transfer, not multiview
conditioning of MeshAxiom's geometry model.

The committed `meshaxiom-head-reference-set` contains the exact UV clay mesh, camera
guides, generated views and paid receipts. The hosted `Fixed geometry head textures`
workflow projects its five 2K variants under a 4 GiB aggregate guard, without downloading
model weights, launching Blender or making paid calls. It retains models, renders and
geometry evidence. These hosted CPU results are separate from laptop measurements.
Local preparation and painting default to 10 GiB; `--memory-gib 4` selects a lower ceiling.

## Quality limits

More views substantially improve coverage, but their facial features must agree in
3D. A 98% silhouette match can coexist with incorrectly placed pupils or a different
mouth. Blending those views averages incompatible features; choosing the most frontal
view independently at each texel can cut across a pupil. The front-first ordering is
a reproducible compromise, and the rejected projected-front guide shows that asking
an image model to preserve existing pixels does not guarantee it will do so.

The source photographs are 1024 pixels square. A 4K atlas gives their projection more
storage resolution, but it does not create additional source detail or correct feature
placement. The source mesh's open boundaries and inconsistent winding also survive
every texture variant. The viewer exposes those edges on the exact native triangles.
These results remain short of the requested Tripo-quality target for a finished head.

Geometry uses the released single-image-conditioned MeshAxiom weights and published
mean/sample topology decoder. Multiview photographs are used for texture projection.
An experimental multiview inference hook in the pinned vendor tree is not a substitute
for a compatible checkpoint trained for multiview geometry. This pipeline does not
claim that its additional photographs improve MeshAxiom's underlying reconstruction.

## Reproduction

Use the runtime from the Apple Silicon document. Commands run from a repository checkout;
the public entry points own their existing admission and aggregate memory guard. Do not
wrap preparation in another render lock. Set `ATELIER_AGENT` to your registered board owner
on a managed machine. Keep paid credentials in the ignored environment.

To replay the fixed head without new image charges, copy the committed reference set
to an ignored build directory and run only `paint`. This also avoids Blender and model
weights for texture experiments. Use a new output/report directory for each run.

```sh
uv run python - <<'PY'
import shutil
shutil.copytree('games/yorimichi/assets/characters/meshaxiom-head-reference-set',
                'build/yorimichi/meshaxiom/head-quality/replay')
PY
uv run python games/yorimichi/tools/meshaxiom_quality.py paint \
  --mesh games/yorimichi/assets/characters/meshaxiom-skater-head/mesh.source.json.gz \
  --image games/yorimichi/assets/characters/meshaxiom-skater-head/reference.png \
  --output build/yorimichi/meshaxiom/head-quality/replay \
  --report build/yorimichi/logs/meshaxiom-quality-replay.guard \
  --variants front-first --memory-gib 4
```

For a new reference set, prepare its cameras and explicitly make the paid image calls:

```sh
uv run python games/yorimichi/tools/meshaxiom_quality.py prepare \
  --mesh games/yorimichi/assets/characters/meshaxiom-skater-head/mesh.source.json.gz \
  --image games/yorimichi/assets/characters/meshaxiom-skater-head/reference.png \
  --output build/yorimichi/meshaxiom/head-quality/original \
  --report build/yorimichi/logs/meshaxiom-quality-uv.guard

uv run python games/yorimichi/tools/meshaxiom_quality.py references \
  --mesh games/yorimichi/assets/characters/meshaxiom-skater-head/mesh.source.json.gz \
  --image games/yorimichi/assets/characters/meshaxiom-skater-head/reference.png \
  --output build/yorimichi/meshaxiom/head-quality/original

uv run python games/yorimichi/tools/meshaxiom_quality.py paint \
  --mesh games/yorimichi/assets/characters/meshaxiom-skater-head/mesh.source.json.gz \
  --image games/yorimichi/assets/characters/meshaxiom-skater-head/reference.png \
  --output build/yorimichi/meshaxiom/head-quality/original \
  --report build/yorimichi/logs/meshaxiom-quality-paint.guard
```

To create a front-projected opposite-view candidate, first generate only the front
reference and bake it with `paint --views yaw60-pitch-5 --variants guided-single`.
Then use the completed GLB and contact sheet in a new, uniquely named experiment:

```sh
uv run python games/yorimichi/tools/meshaxiom_quality.py guide \
  --mesh games/yorimichi/assets/characters/meshaxiom-skater-head/mesh.source.json.gz \
  --image games/yorimichi/assets/characters/meshaxiom-skater-head/reference.png \
  --output build/yorimichi/meshaxiom/head-quality/original \
  --from-model build/yorimichi/meshaxiom/head-quality/original/guided-single/head-pixel-match.glb \
  --from-contact build/yorimichi/meshaxiom/head-quality/original/guided-single/contact.png \
  --reference-stem yaw120-coherent
```

Run `references --views yaw120-pitch-5` with the same mesh/image/output to make its
new paid call. The guide stage itself only crops completed files and verifies their
identity; it launches no native work or model. An existing receipt blocks both guide
replacement and another submission. The current saved candidate used the 384-pixel
camera crop as context and requested a 1024-pixel output.

If only image framing drifted, run the same arguments with stage `register` and
`--guide-view yaw120-pitch-5`. Painting verifies the registered source/output hashes and
measures overlap again. A view that still fails the threshold is rejected.

On this shared Mac prefix native commands with `nice -n 10`. The image stage is remote
and does not hold render capacity while waiting. Use only available normal admission;
check current board, live records and resource telemetry before native launches.

Generate higher density with two separate normally admitted stages, allowing resources
to release between them. Use a new guard report path for each stage and preserve failed
or uncertain evidence. A completed vertex result is bound to its image, requested faces,
seed, diffusion steps, pinned revisions and actual vertex-file hash.

```sh
uv run python -m atelier.ai.meshaxiom.guarded \
  --root build/yorimichi/meshaxiom \
  --image games/yorimichi/assets/characters/meshaxiom-skater-head/reference.png \
  --output build/yorimichi/meshaxiom/head-quality/30k \
  --report build/yorimichi/logs/meshaxiom-quality-30k-vertex.guard \
  --stage vertex --face-budget 30000 --steps 20 --max-nodes 26000 \
  --memory-gib 16 --timeout 7200
```

Repeat with `--stage topology` and a new topology report directory. A larger ceiling
requires the managed full-capacity broker; unmanaged machines keep the ordinary 10 GiB
ceiling. Do not claim an unmeasured 30K run fits a smaller laptop.

After a new native output completes, prepare its UVs/cameras with `prepare`, then try
the frozen photo set without another paid request:

```sh
uv run python games/yorimichi/tools/meshaxiom_quality.py paint \
  --mesh build/yorimichi/meshaxiom/head-quality/30k/mesh.json \
  --image games/yorimichi/assets/characters/meshaxiom-skater-head/reference.png \
  --output build/yorimichi/meshaxiom/head-quality/30k-quality \
  --reference-set games/yorimichi/assets/characters/meshaxiom-head-reference-set \
  --report build/yorimichi/logs/meshaxiom-quality-transfer.guard \
  --variants front-first
```

Use a new report directory for each attempt. A failed fit needs a different documented
reference setup; do not rewrite the paid receipt or treat the earlier mesh's guide as
if it had been generated from the new mesh.
