# Shared foliage rendering

Every vegetation source and placement uses the same derivative build owner and runtime subsystem.
The invariant lives in [the game contracts](../CONTRACTS), and applies to every region, material and future
vegetation asset, including vegetation inside otherwise rigid meshes.

`unreal.foliage_system` follows normal native imports and runtime staging. It discovers vegetation by
material semantics as well as mesh names, samples the source materials' linear palettes, and creates:

- Close canopy lobes with a shared budget across palette slots and a bounded fringe of original leaves.
- Thin original surfaces for fronds and standing groundcover, including opaque groundcover embedded in mixed meshes.
  Already cheap material/spatial groups never gain triangles.
- Progressively simpler canopy volumes, using the source's authored reduced branches.
- Existing tiny distant proxies where they are already cheaper than generated volumes.
- Separate closed shadow proxies and distant forest-patch prototypes.

Original packages remain read-only. Runtime keeps their components, transforms and collision; generated
children only render. Mixed architecture keeps its rigid triangles. Detached animated leaf particles
have an explicit particle role, separate from vegetation placements.

The graphics menu's **Foliage optimization** switch applies live and persists with other preferences.
Off restores the original rendering, including the existing city-tree comparison selection; it does not
opt out of registration or validation. Failed settings saves restore the previous rendering mode.
The older city-tree detail controls describe the original comparison path while optimization is off.

Dense forest interiors use 64 m cells and a 200–250 m coverage transition. Cells need at least twelve
trees. A candidate covers only the central half of the cell's crown bounds, and every tile (at most 2 m)
of its bounding rectangle must fit entirely inside one existing convex crown ellipse. This certifies
area coverage, including spaces between sample points. Boundary crowns retain their individual LODs;
only crowns wholly inside the patch ellipse may transition to it. At least eight interior trees and
a fourfold reduction from their certified final-LOD triangle cost are required. Sparse or uncertain cells retain
individual optimized trees. Render-only patch transforms derive from the actual placed instances;
the source placement and all collision bodies stay intact. Shadow proxies use the shared tree-shadow
distance, including city and regional vegetation.

## Adding vegetation

Use explicit vegetation names/material semantics (`Tree`, `Palm`, `Leaf`, `Bush`, `Grass`, `Plant`,
`Flower`, `Fern`, `Hedge`, and the shared classifier's other terms), or the foliage shading model.
Do not hide vegetation inside an unclassified opaque material. A mixed asset's vegetation must have
separate, recognizable material slots or explicit face roles. The shared procedural exporters retain palette
keys in a separate role channel and encode face roles in UV channel 5 after camera UV baking; the source importer stamps
`FoliageRoles_` into cooked slot names. UV channels 0–4 and imported material binding names stay intact.
Visible material selection keys are never rewritten by role annotation.
Brinecove's material-key builder uses `SurfaceKey` for generic plant paint and preserves these roles
through tile splitting. Both GLB export and Interchange import verify that UV5 survives; the source
importer stamps it before LOD reduction. All-zero explicit roles use `FoliageRigid_` for non-vegetation
such as market fruit painted with a leaf palette. Actual vegetation may never use this rigid certification.
Literal plant colours must retain a semantic key with `foliage_roles.PaletteColour`, or explicitly set
the face's key. Cloth canopies, bark, canes and opaque grass paint are rigid surfaces.
The vertex-painted city trees retain a legacy palette adapter for older source chains.
Small, indivisible textured props (the current potted plants, planter boxes and bonsai shelf) explicitly
declare an authored-surface policy in their source owner. They retain their painted plants and containers
under a hard 12,288-triangle whole-prop budget, with certified visual/shadow variants and aggregation
disabled. This is not a missing-classification fallback. Bigger props require normal asset preparation;
new dense vegetation must use canopy or thin-surface roles. Their UV5 value is 3 and cooked prefix is
`FoliageAuthored_`; ordinary roles use 0 for rigid, 1 for solid canopy and 2 for thin surfaces.
Any new adapter belongs in the shared owner, with source-geometry regression coverage.

Instanced scenery components use `UYorimichiFoliageSubsystem::NewInstances`. The subsystem also audits
static components, refuses unknown vegetation and validates its required representations before game
readiness. New placement mechanisms must not create an independent vegetation renderer. Opaque grass-painted ground and
treehouse architecture are surfaces; explicit `cover_grass`, `cover_leaf` and `cover_fern` roles remain vegetation
even when their source material is opaque. After editing a registered instance layout, call `RefreshSource` before its next rendered frame. New
material palettes need certified mesh variants; overriding a registered source's material bindings at runtime refuses. Both rendering
modes remain under this subsystem. A prototype or import cannot exempt itself from the game contract.

Run the ordinary build. Missing/stale outputs rebuild through their owners; there is no production
prototype flag or missing-output fallback. `Content/FoliageSystem` and its registry belong to the normal
cook and content-retirement policy. Per-source dependency fingerprints include material/texture bytes;
changing one palette must not silently reuse another revision's canopy colours.

## Validation

Focused Python checks cover classification across namespaces, closed/outward geometry, bounds, budgets,
preservation of rigid sections and cheap existing proxies, invalid input refusal and factory ownership.
Native automation (`Yorimichi.Foliage`) covers repeated toggles, collision and placement preservation, sway and
shadow settings, and malformed registry refusal. The build compares every imported variant's actual triangle inventory with its generated geometry and
checks source-package hashes before and after generation.

Before claiming visual quality or speed, retain source-revision-bound real-time captures and GPU timings
for close trees, under-canopy views, treehouse decks, city streets, dense forest and aerial traversal.
Compare on/off in the same settled session at fixed resolution and settings. Check shadow/base/depth pass
times and p95/p99 frame time, not just triangle counts. Inspect patch transitions and clearings in motion.
An optimization claim requires those native checks; geometry unit tests alone do not establish it.

For paired diagnostic runs, `japan.FoliageOptimization 0` and `1` temporarily switch rendering in the current
world without rewriting player preferences. The menu remains the persistent control. Keep the same camera,
resolution, lighting and settled simulation for each pair; record the effective `FOLIAGE SYSTEM enabled` log
and GPU captures with the results.

The repeatable real-time comparison driver is `scenarios/foliage_performance.py`. Run it against an
owned normal game with `--port OWN_PORT --take UNIQUE_NAME` from a clean checkout. It verifies the
project, compiled code identity, gameplay readiness and effective renderer switch, samples off/on/on/off at fixed camera paths, captures game
screenshots and requests GPU event breakdowns in the owned stdout log. Frame and GPU means/p95/p99,
raw samples, settings and source revision go under `build/yorimichi/foliage_performance/`. It refuses
missing GPU timing (including NullRHI) and either fixed-clock mode, restores the active foliage
preference (including launcher-selected settings files), CVars, HUD mode and player camera,
and never treats fixed-step filming as a real-time performance result. Inspect captures before publishing.
