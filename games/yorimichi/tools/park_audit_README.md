# Crater Park geometry comparison

`audit_craterpark.py` and `park_audit_geometry.py` are a standalone Python/numpy tool. They never launch Blender or
Unreal. Run long scans under the project's normal guard and scheduling rules.

```sh
python audit_craterpark.py reference/npz candidate/npz --out report.json \
  --box 1195 875 1395 975 --max-samples 30000 --max-pairs 5000000
```

Accepts a directory containing `NAME.npz`, or a parent containing `npz/`. Each mesh has finite `positions (V,3)` and
integer `triangles (F,3)`, in **absolute native metres, y up**. `UC_CP_*` are collision; `SM_CP_*` are render. Both sets
must contain both domains. Import seeds are omitted. Optional `corner_ao (F,3)` is linear; `corner_normal (F,3,3)` is
in the same native frame. No pickle/object arrays are loaded. An optional `build.json` beside the NPZs or in their
parent contributes roles, declared triangle counts and its SHA-256. Per-mesh `manifest_minus_npz` and missing mesh
names reveal extraction discrepancies. Counts alone do not identify why faces disappeared. In the r4 extraction,
the producing agent identified Blender dropping exact duplicate faces: 5,750 render and 6,711 collision faces.
Those defects are absent from the NPZ topology scan and must remain in the baseline defect ledger. FBXs are not read;
extraction must already have applied each mesh's origin and frame.

The JSON records every input's SHA-256, settings, per-piece triangle counts, elapsed time and incremental results.
It is atomically replaced after each completed stage. `complete: false` means the process has not finished all stages.
Always inspect the per-scan completeness flags too. Partial scans are diagnostic lower bounds, never a clean bill.
Progress lines report completed points/pairs, or the current indexing stage, at least every 20 seconds during loops.

## Riding surfaces

`--checks distance` measures both directions. Source faces have unit geometric normal `y > 0.2`. A sample is exposed
when no source collision triangle crosses the vertical segment from **1 micrometre above it to 1 metre above it**.
Nearest target points may lie on **any** target collision face. Matching and exposure always use the complete mesh
set, even when `--box x0 z0 x1 z1` selects source faces by their centroids.

Every selected face offers seven samples: its three corners, three edge midpoints and centroid. A deterministic,
evenly spaced subset of this ordered stencil is used when it exceeds `--max-samples` (default 30,000 per direction).
`--max-samples 0` checks the entire stencil. Samples are not area weighted; percentiles describe sampled points,
including repeated shared corners. The report gives max, p99, p99.9, p50, the worst 20 locations and the fraction of
the available stencil tested. Empty or unmatched samples do not pass. Distances are exact nearest-triangle distances
at those points to floating-point precision, with no search radius cutoff.

**This is sampled Hausdorff, not a continuous-surface guarantee.** Even the complete seven-point stencil can miss a
small interior defect. Passing the default 1 cm threshold means only that the sampled points passed. Use denser
candidate/reference tessellation, independent riding traces and visual inspection for acceptance. The sole exact
continuous identity shortcut requires equal mesh names and bit-for-bit equal triangle arrays: then each sampled
point provably belongs to the identical target face and geometric deviation is exactly zero. It does not zero any
topology defects or ignore attribute differences.

For an independent denser riding check, use `--spacing .05`: each source triangle receives a barycentric lattice
whose subedges are at most 5 cm long. `--max-samples` still limits the number of points **before exposure filtering**.
If that budget thins the lattice, `full_spacing_coverage` is false and `sampling_fraction` reports the fraction
actually tested; the result does not claim uniform 5 cm coverage. Use smaller regions or raise the budget. A complete
unbounded lattice above ten million points is refused with instructions to narrow the region or set a finite budget.
Dense mode applies to riding checks; appearance uses the seven-point render stencil. Dense sampling still does not
prove continuous deviation on a changed mesh or resolve every exposure boundary.

## Overlaps and topology

Render and collision are scanned separately; their intentional agreement is never counted as a defect.

- `--checks overlaps`: triangle-pair AABBs, normals parallel or antiparallel within `--angle-tolerance` (default
  0.5 degrees), and all vertices within `--plane-tolerance` (default 5 mm) of the opposite plane. A projected triangle
  intersection must have positive area above 1e-8 square metres. Shared edges alone do not count. Reports within-mesh
  and between-mesh counts, mesh pairs, first 100 examples, and summed pairwise projected overlap area. The area is
  **not a union**: multiple layers are counted once per pair. Near-plane overlaps are potential flicker, not proof of
  a camera-dependent depth failure. Oppositely wound thin sheets are deliberately included. An overlap touching the
  chosen region is included when either face's centroid is inside; the other face can lie outside.
- `--checks topology`: shared corners are identified on a `--weld` quantization grid (default 10 micrometres). Reports
  edges with one incident face, nonmanifold edges with more than two, degenerate faces, and slivers. Incidence uses
  the complete domain, so a crop boundary does not invent open edges. Quantization is a grid identity, not a Euclidean
  radius weld: points near a grid boundary may remain separate. Open edges are evidence to inspect; some are intended.
- T-junctions are vertex/open-edge interior incidences within the weld tolerance; endpoints are excluded. All mesh
  vertices can participate, including vertices outside the crop. Counts are incidences, not unique crack regions.
  This finds unsplit boundary edges; it does not diagnose every self-intersection or prove watertight solids.
- Sliver quality is `4 * sqrt(3) * area / sum(edge_length_squared)`, 1 for an equilateral triangle and approaching
  zero for a collapsed triangle. Default threshold is 0.001. Degenerates have area at most 1e-12 square metres.

`--max-pairs` defaults to 5 million AABB candidates per overlap/T-junction scan. Exceeding it marks that scan incomplete
and retains its partial findings. `--max-pairs 0` removes the pair budget; use a guarded deadline and inspect runtime.
No test for buried *solid interiors* is claimed: only the explicit riding exposure test is provided.

## Appearance

Add `--checks distance overlaps topology look` to compare linear AO and normals. The same seven-point render stencil
is interpolated on the nearest target render triangle, accepted within `--look-match-tolerance` (default 2 cm).
Reports per source mesh: matched samples, AO absolute differences and normal angles (degrees), with p50/p99/p99.9/max.
Missing attributes and unmatched samples remain visible. Changed triangulation at a material/shading seam can make
the nearest triangle ambiguous; inspect those outliers visually. Identical geometry uses exact face correspondence,
so the self-check preserves corner discontinuities. UVs/material appearance and image similarity are not measured.

## Validation

Run `pytest games/yorimichi/tests/test_craterpark_audit.py -q` from the checkout. Analytic fixtures cover closest-point
regions, degenerate triangles, BVH versus exhaustive queries, unique broad-phase pairs, positive-area overlaps,
shared edges, near-plane layers, T-junctions, slivers, crop boundaries, exposure, missing surfaces, raised surfaces,
attribute interpolation, pair-budget reporting, and self-comparison retaining absolute structural defects.
