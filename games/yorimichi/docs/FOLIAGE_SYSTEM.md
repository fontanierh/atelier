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
of its bounding rectangle must fit entirely inside the projected convex hull of one certified opaque,
closed generated distant core. Only the exact core vertices may certify this footprint; smooth bounding
ellipses and arbitrary source/alpha-proxy hulls cannot prove occupied area. Authored far proxies without
that certificate retain individual optimized LODs. This certifies area coverage, including spaces between
sample points. Boundary crowns retain their individual LODs; only crowns wholly inside the patch's
inscribed .92 ellipse may transition to it. Nonuniform component scale also keeps individual LODs, avoiding
shear loss when converting world-aligned patches to relative transforms. At least eight interior trees and
a fourfold reduction from their certified final-LOD triangle cost are required. Sparse or uncertain cells retain
individual optimized trees. Render-only patch transforms derive from the actual placed instances;
the source placement and all collision bodies stay intact. Shadow proxies use the shared tree-shadow
distance, including city and regional vegetation.

## Adding vegetation

Use explicit vegetation names/material semantics (`Tree`, `Palm`, `Leaf`, `Bush`, `Grass`, `Plant`,
`Flower`, `Fern`, `Hedge`, and the shared classifier's other terms), or the foliage shading model.
Names use delimiter/camel-case word boundaries and regular plurals, so `StreetTree02` and `Trees`
are plants while `HD_Streets` is rigid. Python preparation and native registration share this rule.
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
An unannotated collision hull can share a plant's name without containing visible vegetation. The build
disambiguates this name heuristic only through a hard StaticMesh reference whose `complex_collision_mesh`
is exactly that hull. Explicit foliage roles/materials take precedence; a suffix alone proves nothing.
This adds no rigid stamp or runtime exemption: drawing that named hull directly still fails registration.
Small, indivisible planted props (including Belmonte’s nine small flower/herb containers, the potted plants,
planter boxes and bonsai shelf) explicitly
declare an authored-surface policy in their source owner. They retain their painted plants and containers
under a hard 12,288-triangle whole-prop budget, with certified visual/shadow variants and aggregation
disabled. This is not a missing-classification fallback. Bigger props require normal asset preparation;
new dense vegetation must use canopy or thin-surface roles. Their UV5 value is 3 and cooked prefix is
`FoliageAuthored_`; ordinary roles use 0 for rigid, 1 for solid canopy and 2 for thin surfaces.
Crater Park’s numbered grass/shrub surfaces declare roles at their DSL exporter; painted moss and snow
remain rigid. Lake shoreline plants, ornamental pier grass, embedded flower buckets and fallen leaves
also carry explicit roles independently of their visible paint.
Any new adapter belongs in the shared owner, with source-geometry regression coverage.

Instanced scenery components use `UYorimichiFoliageSubsystem::NewInstances`. The subsystem also audits
static components, refuses unknown vegetation and validates its required representations before game
readiness. New placement mechanisms must not create an independent vegetation renderer. Opaque grass-painted ground and
treehouse architecture are surfaces; explicit `cover_grass`, `cover_leaf` and `cover_fern` roles remain vegetation
even when their source material is opaque. After editing a registered instance layout, call `RefreshSource` before its next rendered frame. New
material palettes need certified mesh variants; overriding a registered source's material bindings at runtime refuses. Both rendering
modes remain under this subsystem. A prototype or import cannot exempt itself from the game contract.
The audit caches weak component/mesh/material/role-slot verdicts, including rigid components, and
reclassifies changed bindings. Use `SetSourceVisibility` for authored visibility changes such as the
hide-groups diagnostic; it updates managed copies and the visibility restored by the graphics toggle.
Invalid vegetation discovered after bootstrap still fails readiness: the universal production contract
does not allow an unoptimized fallback. The legacy city-tree selection remains the source for both
foliage modes; its `/Game/Experiments/CityTrees/v4` meshes are included in the normal registry scan.
Legacy FBX imports log separate import, role/save and collection timings (`MESH ROLE TIMING`) so the
cost of bounded package collection can be measured during normal preparation.

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
For uncapped Metal timings, use the fullscreen play profile: UE 5.8 forces display synchronization in windowed mode even when `r.VSync=0`. Confirm the effective viewport and pacing before interpreting gains.

Compare on/off in the same settled session at fixed resolution and settings. Check shadow/base/depth pass
times and p95/p99 frame time, not just triangle counts. Inspect patch transitions and clearings in motion.
An optimization claim requires those native checks; geometry unit tests alone do not establish it.

Find slow aerial views before selecting comparisons. The scout bins actual tree placements in 128 m cells,
chooses the densest neighborhood in each of four regions, and samples down-facing and oblique cameras at
80, 140 and 240 m above the highest local tree root. It ranks original-mode GPU mean and frame p95 independently;
the three slowest GPU views plus the worst pacing view become exact replay cameras. Inspect their captures
to confirm trees fill the frame and the camera clears the terrain. A scout records baselines, never speedup ratios.

```sh
uv run python games/yorimichi/scenarios/foliage_performance.py --port OWN_PORT --take aerial_scout --aerial-scout --seconds 5 --settle 3
uv run python games/yorimichi/scenarios/foliage_performance.py --port OWN_PORT --take slow_aerial_abba --camera-file build/yorimichi/foliage_performance/aerial_scout/slow_views.json
```

The report records actual render-scale and lighting controls as well as saved preferences and viewport dimensions.
Both phases restore the saved foliage mode, camera, HUD and changed CVars, including background-idle throttling.

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

The editor-only `YorimichiFoliagePreparation` module owns source transport, binary
geometry readback and authored-leaf residency compaction. These commands load that
module and `YorimichiImport`, whose current classification and geometry snapshot
helpers they still call. Both actual compiled module records enter preparation
identity; the unrelated gameplay library does not. Runtime and raw imports do not
link the preparation module.

Preparation waits for every normal importer before observing the complete source
package and sidecar membership. It keys those actual bytes and consumed native
libraries instead of the importers' action identities. A source, material, sidecar,
configuration or consumed library change still requires current native validation.
Moving the native classes changes their reflected editor module path and requires
ordinary compilation, descriptor-isolation checks and receiving validation. Old
unit policies remain historical proof only: an exact independently reviewed
source-pair witness must bind moved paths before old hints can be looked up.
