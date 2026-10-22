# Shared foliage rendering

Dense vegetation and vegetation embedded in scenery share one classification and runtime owner.
Small export-certified plant props with a complete `FoliageAuthored_` material table and 1–12,288
LOD0 triangles stay ordinary props, preserving their existing rendering and collision.

The normal build has two native preparation steps. `unreal.foliage_system` certifies source roles,
materials and saved intermediate geometry. `unreal.foliage_residency` publishes the final prepared
meshes and `Data/foliage_residency/registry.json` consumed by the game. Original packages remain
read-only. Missing or stale products fail the build or gameplay readiness.

Final meshes retain the original leaf texture, opacity, colour, wind and player-interaction material
wrappers. Sources with authored lower LODs retain their complete chain, including far impostors and
actual rendered screen thresholds, up to eight levels. Sources with only one LOD use the installed
native reducer at explicit 50/25/10 percent targets within each material and categorical role island.
Its minimum island size can prevent tiny sources reaching those percentages. Saved descriptions,
rendered triangle counts, UV channels, material bindings and settings receive native validation.

Rigid scenery appears once, on a separate prepared carrier. Standalone trees retain their authored
rigid LOD chain and use simple trunk collision; leaves and bushes remain passable. Mixed meshes retain
rigid-only ground and building collision. Trunk shapes preserve each placement's authored collision
enablement and channels, including intentionally nonblocking park trees. Bush interaction remains a
material effect. A separately budgeted shadow mesh replaces leaf-card shadow casting. Opaque canopy
volumes and coverage patches are not used for the final visible leaf representation.

The persistent **Foliage optimization** preference is selected before the first scenery mesh load.
Optimized mode resolves canonical source names to prepared assets without opening the originals.
Switching off detaches and releases prepared meshes before loading legacy assets; switching on does
the reverse. A deferred reload waits until callbacks return, preserves placements and visibility, and
reports readiness only after registration and collision installation complete. Failed preference saves
restore the previous mode. The existing city-tree preference remains a separate source selection.

Uncooked editor games retain CPU render arrays that cooked games can discard. After GPU upload,
prepared render-only meshes can release unused CPU vertex copies; collision carriers retain positions
and indices, and only release shading copies when their CPU consumers permit it. Reloads drain complete
registration batches rather than accumulating all uploads. Mesh-surface cache entries are pruned after
garbage collection while immutable in-flight job references remain valid. These mechanisms require
measured process-footprint and mode-switch evidence; resource-size estimates alone do not prove a gain.

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
under a hard 12,288-triangle whole-prop budget. A complete authored slot table remains on the ordinary
prop path in both graphics modes, without generated replacement meshes. This is not a missing-classification fallback. Bigger props require normal asset preparation;
new dense vegetation must use canopy or thin-surface roles. Their UV5 value is 3 and cooked prefix is
`FoliageAuthored_`; ordinary roles use 0 for rigid, 1 for solid canopy and 2 for thin surfaces.
Crater Park’s numbered grass/shrub surfaces declare roles at their DSL exporter; painted moss and snow
remain rigid. Lake shoreline plants, ornamental pier grass, embedded flower buckets and fallen leaves
also carry explicit roles independently of their visible paint.
Any new adapter belongs in the shared owner, with source-geometry regression coverage.

Scenery loaders use `UYorimichiFoliageSubsystem::LoadMesh` before opening a canonical source asset.
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
prototype flag or missing-output fallback. `Content/FoliageSystem`, `Content/FoliageResident` and their registries belong to the normal
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
times and p95/p99 frame time, not just triangle counts. Inspect authored LOD transitions and clearings in motion.
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
project, compiled code identity, gameplay readiness and effective renderer switch and zero inactive mesh residency after each deferred reload, samples off/on/on/off at fixed camera paths, captures game
screenshots and requests GPU event breakdowns in the owned stdout log. Frame and GPU means/p95/p99,
raw samples, settings and source revision go under `build/yorimichi/foliage_performance/`. It refuses
missing GPU timing (including NullRHI) and either fixed-clock mode, restores the active foliage
preference (including launcher-selected settings files), CVars, HUD mode and player camera,
and never treats fixed-step filming as a real-time performance result. Inspect captures before publishing.

## Native preparation boundary

`YorimichiFoliagePreparation` is an editor-only module. Its
`YorimichiFoliagePreparation` Python class exports source palettes and geometry,
constructs derivative meshes, and reads exact stored geometry snapshots. The normal
`unreal.foliage_system` owner declares this module's compiled digest. Raw import role
certification remains in `YorimichiImport`, through `YorimichiFoliageBuilder`.
Neither native module links the other; both use Engine's synchronous garbage collector.
The preparation digest record is also an explicit input of per-mesh resume policy,
so compiler, build-rule and linked-library changes cannot retain an earlier unit policy.

Adding the module changes the project descriptor and moves compiled code once. That
transition requires an ordinary compile and may revalidate imports. Thereafter a
preparation-only edit changes the preparation library and its cutoff token, while
unchanged raw import libraries keep their tokens. Source, engine, configuration and
actually consumed module changes still invalidate their consumers. No fingerprint
exception or manufactured stamp is involved.

The graph/digest/descriptor tests exercise this boundary with stand-in compiled
libraries. They do not establish native build compatibility or a production timing
improvement. Native validation must use the actual preparation library and current saved products.
