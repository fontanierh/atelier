# Fixed-geometry head quality experiment

Work in progress: results will be filled after the guarded experiments complete.
The existing [Apple Silicon experiment](MESHAXIOM_EXPERIMENT.md) supplies the pinned
weights, runtime installation, single-view baseline, and hardware measurements.

## Constraint and experiment matrix

The geometry is never edited after native MeshAxiom generation. No retopology,
decimation, subdivision, hole filling, vertex movement, sculpting, or manual Blender
work is used. The published topology decoder remains part of native generation.
UV seams may duplicate exported vertices. Every triangle's three positions and winding
are compared with the original output at float32 precision after the same uniform
scale, origin and Z-up to Y-up conversion used by the baseline.

Compare the original 18,931-triangle head with:

1. Better UV packing, the original image, and a 2K atlas.
2. A geometry-guided front image, then all seven geometry-guided Sunburst views.
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

`references` makes seven sequential GPT Image 2.5 Sunburst high-quality edits. Each call
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

For each result it verifies both the native triangle multiset and byte-identical
non-image GLB buffers. It saves confidence, protected/changed masks and eight diagnostic
renders. Coverage means the fraction of occupied UV texels reached by a reference;
it is not a measurement of physical surface area or a visual-quality score.

The committed `meshaxiom-head-reference-set` contains the exact UV clay mesh, camera
guides, generated views and paid receipts. The hosted `Fixed geometry head textures`
workflow projects its four 2K variants under a 4 GiB aggregate guard, without downloading
model weights, launching Blender or making paid calls. It retains models, renders and
geometry evidence. These hosted CPU results are separate from laptop measurements.
Local preparation and painting default to 10 GiB; `--memory-gib 4` selects a lower ceiling.

## Reproduction

Use the runtime from the Apple Silicon document. Commands run from a repository checkout;
the public entry points own their existing admission and aggregate memory guard. Do not
wrap preparation in another render lock. Set `ATELIER_AGENT` to your registered board owner
on a managed machine. Keep paid credentials in the ignored environment.

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
