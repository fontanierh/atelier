# Bounded mesh export workflow

This workflow separates authored geometry from serialization and runtime assembly. A logical
asset can span several physical meshes, each with at most 32,768 rendered triangles. Splitting
changes ownership and task boundaries; it does not authorize changing the authored surface,
collision, materials, LOD behavior, placement, or culling policy.

## Build direction

```text
committed source + selected constructor + explicit world queries
        → final source/query products and logical plan
        → independent per-piece payloads and narrow projections
        → one cached small mesh export per payload
        → validated file-only assembly
        → complete native import and runtime membership
```

Use `region_exports.LogicalAsset` and `region_exports.steps` for the logical source boundary,
and `atelier.export_tasks.Asset` for each physical export. A constructor must build only its
selected source. Giving a whole-region generator several small task names does not create
independent work. Do not build siblings merely to recover random state; publish the required
deterministic source parameters or commands instead.

Declare every consumed code file, committed model, material definition, terrain/query product,
and auxiliary output. Named `Product` reads carry actual data dependencies. Ordering or reference
edges do not replace dependencies on bounds, materials, collision, or placement data. A query
producer must consume final source geometry before exports; it must not import a sibling's
rendered FBX/GLB to discover geometry needed by another constructor.

Some legacy queries depend on a serializer's numerical frame. Preserve their ordered arrays,
dtypes, tessellation, float32 quantization and float64 transform order exactly. A finite conversion
needs an actual roundtrip proof and a checked tool/version binding. Refuse unsupported frames;
do not substitute cleaner coordinates or accept a tolerance without an authored behavior change.

## Plans, projections and stable payloads

Raw geometry uses MeshIR payloads and `region_mesh_parts`; already encoded GLB geometry uses
`encoded_region_plan`. Both publish a complete plan and exclusive, regular per-piece files.
An exporter reads its own payload and actual serializer/tool inputs. Sibling names, bounds,
material tables and payload hashes must not enter that export's key unless actually consumed.

Keep each raw leaf's used material slots compact while retaining the complete original logical
material table in assembly metadata. Preserve slot names and corner material assignments.
The ordinary MeshIR path retains its default schema 2. Explicit finite material descriptors
select schema 3; this must not silently rewrite unrelated default payloads or change shaders.
For encoded GLB, retain unchanged bytes when possible. Parent runtime fields such as bounds and
original material-slot grouping belong in explicit plan-row assembly metadata, not every leaf's
encoded packet header. Belmonte's `atomic_metadata.entry(piece, metadata)` reconstructs that
original runtime view. Never drop these fields or copy them back into all payloads to bypass a
projection boundary.

The transient v1 graph discovers `plan.json`, publishes a region inventory and uses `replan=True`
to expand successful cold planners into export tasks. This is a discovery mechanism, not the
final locality contract. The v2 cutover must publish a group-membership projection and separate
per-piece projections: a membership edit updates its group inventory, while an unrelated leaf
keeps the same payload, projection bytes and export key. Assembly consumes the complete current
membership. Do not claim v2 is active from the presence of v1 discovery files, or make each leaf
read a complete mutable roster. Keep export-recipe/projection versions distinct from MeshIR or
encoded-packet schema versions. Verify the actual implementation before choosing the cutover.

Authored partition policy is explicit: a whole unit stays whole and refuses oversize geometry;
a spatial owner keeps its spatial partition even when the total happens to fall below the
budget. Do not switch policies at a triangle-count threshold, renumber unrelated spatial leaves,
or globally repack unchanged geometry after a local edit.

For raw plans, declare `partition='whole'` or `partition='spatial'`; authored `face_groups`
use the explicit policy. Pass `collision_owner` as the exact existing member key for spatial
or multi-piece whole UCX ownership. An absent declared owner must refuse, not move the hulls
to a newly sorted first member. Include the authoring-policy implementation in the checkpoint
before adopting these arguments; older planners without this API require the corresponding
cutover rather than silently inferring a policy.

## Collision, materials and runtime policy

Preserve winding, corner normals, every UV/color layer, material fields, object matrices and
pivots. Do not force UV precision, tangent generation or shader changes as part of task splitting.

An authored whole UCX hull set belongs to exactly one explicitly selected existing render member.
Spatial or multi-piece plans must declare that owner; do not infer it from current sort order.
Keep every hull whole and attach it once. Other members must retain the original component
collision policy without creating extra blocking surfaces. Assets that originally use complex
collision retain that policy on their corresponding rendered geometry. Collision-only payloads
remain explicit products, not missing render leaves.

Assembly validates every current member, source ownership and export receipt, then copies files.
It never joins geometry, invokes constructors/exporters, fills missing pieces, or silently accepts
old products. Retire only the producer's recorded obsolete members after successful replacement
validation and reference preflight; preserve unknown files and packages by refusing the operation.

Migrate every actual authored LOD, its screen sizes, source binding and runtime forced-LOD rules.
Coordinated pieces must retain the original logical box and true sphere where tighter per-piece
bounds would change culling or LOD selection. Match the original native bounds calculation: imported assets can retain double-precision
MeshDescription bounds rather than float32 render-buffer bounds. Preserve its exact box and
true vertex sphere across the complete logical union; an AABB-diagonal sphere or arbitrary
bounds extension is not equivalent.
Preserve native/runtime membership, material bindings, collision flags, shadow and cull settings,
instance grouping, transforms and placement. Include all receiver helpers and module requirements
in the normal import graph. Native success alone does not establish cooked or runtime parity.

## Ordinary commands and validation

Use the normal build graph in an isolated worktree. Run `uv sync` at a stopped caller/child boundary.
Inspect actual misses before starting work:

```sh
uv sync
uv run atelier build yorimichi --list
uv run atelier build yorimichi world.hidamari.geometry.HD_Streets --plan --explain
nice -n 10 uv run atelier build yorimichi world.hidamari.geometry.HD_Streets
uv run atelier build yorimichi --list
```

After the selected planner publishes its inventory, select the exact discovered
`world.REGION.export.PIECE` task for one bounded export. Use
`world.REGION.assembled` when the complete region membership is ready; it can run other ordinary
missing prerequisites. Confirm the actual target names with `--list`, since family-specific
assembly/import tasks may retain established names.

Declare new non-rendering Blender commands with `threads=3` and factory startup. Use ordinary
admission, full actual reservations, memory guards and work deadlines for native diagnostics too.
Read the machine's board, live ownership and telemetry before heavy work, and keep the session
responsive. Never clear caches, transplant stamps, force/touch a task to conceal a miss, or share
mutable Content/Binaries folders. Inspect `--plan --explain` again after edits: an unchanged leaf
must keep its verified inputs and output, even when another member changes.

Run focused tests for changed behavior, `uv run atelier lint`, and
`uv run atelier contracts check`. The contract checker validates syntax/owners; assess the actual
data flow against the contracts in `region_exports`, `region_mesh_parts`, `export_tasks`,
`export_assembly`, and the owning family. Hosted CI runs the full Python suite. Documentation-only
changes need no Python test run. Finish the project's exact-head CI/review/merge checklist before
resuming deferred family expansion.

## Evidence levels

| Level | Required evidence | Limit of the conclusion |
|---|---|---|
| Census | SHA-bound reports/plans; original counts, complete leaves and maximum leaf count | Metadata can identify candidates; it does not prove payloads or native acceptance. |
| Source | Immutable original authority; complete consumed inputs before/after; exact geometry, ownership and ordered query fields | A mock or the same supplied arrays cannot prove independent world-query migration. |
| Serialized export | Actual FBX/GLB; all source attributes, corner fields, materials, transforms and whole authored hulls compared | Counts or byte equality of a different source revision are insufficient. |
| Native receiver | Actual final LOD/GPU data, cooked-data policy where applicable, materials, collision, logical bounds and complete membership | Import success or source equality alone cannot establish this level. |
| Cook/runtime | Current cooked outputs and focused runtime placement, culling/LOD, collision and behavior checks | A Python/source fixture cannot substitute for a running native receiver or game. |

Record exact source revisions, tool identities, hashes, commands, exits and terminal empty guard
receipts. Freeze donor files with before/after SHA and file identities, and use independent copies.
Do Git/history preparation on the host, never inside a guarded Blender/Unreal child. A successful
stored receipt whose source hashes differ is another authority, not permission to relabel the
current result PASS. Keep failures strict; do not weaken contact gates, tolerances or completeness.

## Deferred ledger and resume order

The checkpoint is not an all-family native acceptance claim. Finish proof and integration for the
city and large-region work. The owner excludes further small-asset and skeletal splitting.

| Family | Retained finding | Resume requirement |
|---|---|---|
| Gondola fitted site | Main `90d7a918` includes the #601 curve correction. The matching r13 site passes the unchanged 2 mm contact gate at 1.608/1.701/1.831 mm. Its large L1/L2 ropes are 47,176/59,392 triangles; the unmerged design used two members across all three LODs. The old 6.767 mm failure and 88,408/63,472 counts belong to historical fixtures. | **Deferred to keep this checkpoint focused on cities.** Accepted main's kit, final North Trail/query inputs, fitted-site importer and runtime path remain unchanged. The unmerged site/rope/runtime expansion is archived at `codex/deferred-gdx-city-priority-b596`; private source/export evidence remains preserved. No new Gondola compile/native campaign is part of this checkpoint, and existing contact evidence is not current native acceptance. |
| Hidamari props | Merged PR648 (`aad723836`) gives the 36 logical bases and 48 physical exports (maximum 12,890 triangles) separate selected source/export tasks and file-only assembly. All 48 source/FBX records, 48 native meshes and 60 render LOD pages per side passed the scoped equivalence comparison. A postbox edit changed one constructor/export and left 47 siblings unchanged. | Preserve the exact proof and its limits in `proofs/hidamari-prop-atomic.json`. Full production placement, runtime, package cooking and normal native-owner reuse still require their own exercise; the fixture is not that evidence. |
| Foliage | The sealed follow-up at `c50af3e67` separates 84 authored LOD exports and 18 required Seed exports into 102 selected source/export pairs, with 18 file-only assemblies. All 102 source packets and literal FBX files match the immutable original bytes; all 18 legacy manifests agree. Maximum export size is 4,484 triangles, with ten authored UCX hulls preserved. A single-LOD edit changes two of 204 source/export fingerprints, preserving 202 siblings and 564 published files. The ordinary producer completed; its repeat had 264 current tasks and no execution. An independent receiver restored 39 task results with no command execution. This follow-up is not yet merged. | Paired native fixture validation passed at `b59638ab`: 18 owners, 84 saved mesh packages and 150 native LOD pages per side, including source/GPU/cooked geometry, materials, bounds and fixture queries. Both invocations exited 0 with empty guards and absent fixture roots. A new immutable-log receipt preserves the original receipts and exact late TraceServer append lineage; its digest is in `proofs/selected-export-followup.json`. Finish final integrated CI. The 39 restores are checkpoint-action results, not native mesh reuse. Production placement, HISM/game/package behavior and distance-field/mesh-card runtime remain outside this fixture. |
| Bike validation | Complete saved source/GPU/cooked steering geometry and imported double-precision logical bounds agree. Artificial query-enabled original whole versus isolated-piece parity is not established; normal Bike components use NoCollision. | Preserve this distinction. Current-piece positive controls and actual original/current NoCollision readbacks do not certify synthetic whole-query parity or the unexecuted production owner/clip/network path. |
| Train | The follow-up source proof at `f37d202d` covers 138 Track owners/363 LOD exports, maximum 31,272 triangles: every current GLB matches the immutable original bytes. The production runtime excludes the editor marker, so native receiving must cover 137 meshes/362 LODs. The carriage follow-up at `4839eddbc` covers all seven owners and 81 actual Body/door/authored-LOD GLBs, byte-identical under the same genuine atlas query, maximum 30,590 triangles. Three original combined LOD0 intermediates exceed the budget (33,458/34,478/33,214) and are not serialized as final exports. These follow-ups are not yet merged. | Carriage scoped paired comparison passes for 67 meshes/81 LOD pages, including source/GPU/cooked geometry, materials, bounds, poses, fixed/switchable collision and moving doors. A separate immutable retained-capture revalidation preserves the initial material-text failure and excludes only engine-generated GUID fields justified by installed source; it does not certify static-lighting or texture-streaming runtime. Track retains 137 original observations/362 LOD pages and exact consumed source/runtime identities, with a conditional carry only. Its original whole remains exit255; 14 invalid concave-face controls remain failed. A separate saved-package check passed 28 actual queries across those seven owners, without imports, saves or package deletion. There is no independent current paired Track execution. Source-count metadata covers every authored LOD; the corrected comparators also require true nonempty saved-source data at each level. Distinguish shared-atlas serialization equality from independent atlas-render repeatability: the retained independent render comparison failed by six RGB pixels and is not waived. Preserve the actual broad atlas-code input dependency until a separately proven projection replaces it. Retained reports do not certify absent current files or production/runtime acceptance. Exact receipt digests and limits are in `proofs/selected-export-followup.json`. |
| Characters, horses and avatars | Characters and horses retain their existing skeletal mesh owners. Avatar presentation shares those body owners. Historical source census evidence is retained separately; it does not establish skeletal equivalence. | **Owner-excluded.** Do not split characters, horses or avatars or start a skeletal proof campaign for this work. Existing source, receiving and runtime owners remain unchanged; these census observations are not a future splitting requirement. |
| Hippo | Four committed structure sources are bounded at 24,940/11,779/5,006/11,859 triangles. Source-only loop arithmetic also places all six procedural owners below the budget; actual output identities remain unverified. Its ten logical source/export owners already exist. | No additional splitting is scheduled under the city priority. Preserve the existing owners; source arithmetic is not native or generated-output acceptance. |

Retain deferred source commits, exact failure diagnoses and private evidence locators in the
operator handoff. Keep machine paths, personal identifiers, credentials and local evidence out
of this public guide. Resume from the existing products and verified input identities; do not
regenerate a whole family merely to rediscover its state.
