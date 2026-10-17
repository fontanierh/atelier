# Fixed-geometry head quality experiment

Work in progress: results will be filled after the guarded experiments complete.
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

The following first eight-view comparison ran on hosted macOS CI at `4eda5848`,
under a 4 GiB aggregate guard. All five outputs preserved every native triangle
and winding. Times include projection and buffer validation, but exclude the
eight diagnostic renders per output and remote image generation.

| Projection | Occupied texels painted | Seconds | Observed result |
| --- | ---: | ---: | --- |
| Original single image | 16.11% | 8.37 | Most sides and back stay neutral |
| Geometry-guided front | 16.33% | 8.26 | Better alignment, similar limited coverage |
| Eight-view weighted blend | 55.11% | 25.85 | Doubled facial features |
| Eight-view best angle | 55.11% | 24.26 | Broken pupil shapes at view boundaries |
| Eight-view front first | 56.06% | 24.82 | Coherent eyes; side seams and neck patches remain |

That complete hosted run took 164.10 seconds including diagnostic renders and
peaked at 1.91 GiB. Hosted timings are not laptop benchmarks. The nine Sunburst
calls include one additional guided opposite-view candidate; its results and
the local 4K/density comparisons follow after validation.

On the laptop, the selected eight-view recipe reproduced the hosted 2K GLB
byte for byte. Its projection and validation took 17.07 seconds at 2K and
35.10 seconds at 4K. The complete pair, including sixteen diagnostic views,
took 75.78 seconds and peaked at 7.14 GiB under the unchanged 10 GiB CPU guard.
The 2K output is 2.96 MB; 4K is 7.05 MB. Painted coverage was 56.06% and 56.08%
of occupied texels respectively. Both preserve all 18,931 triangles and winding.
At matched viewing size, 4K adds modest detail but does not remove side seams,
patches, or the original surface defects. The 2K output is the cheaper default.

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
30,000-face limit and the existing 26,000-vertex safety bound. The native stages use a
separate 16 GiB aggregate ceiling and full broker reservation; shared machine profiles
and host reserves stay unchanged. Each stage has a two-hour deadline.

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
