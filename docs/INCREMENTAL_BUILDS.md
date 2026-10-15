# Incremental build architecture proposal

Atelier should build a small edit by generating, importing and cooking only the products whose actual inputs
changed. Every certified product should be reusable across compatible worktrees and revisions. The normal `atelier build`
command should handle this automatically, with a local store that works offline and an optional remote store.

**Status: foundations and local portable caching implemented; native migration proposed.** `Step.products`, `reads` and `references`, complete
product inventories, content-based downstream invalidation, read-only `--plan` / `--explain` / `--json`, and command
timings, a file-hash index, opt-in automatic portable-product restoration, and cache accounting/pruning are available.
Whole-build reuse also verifies named inventories and blocks incomplete copies with an interruption journal.
Opt-in bounded tool batches retain per-action identities and receipts; native recipe migration and acceptance
remain separate work. Optional output sidecars retain absence in their product identities and frozen query reads.
Instrumented scripts can emit bounded phase records; `--timings` displays historical command/phase measurements
separately from restoration time. The sandbox demonstrates the protocol; native phase baselines remain to be measured.
`--changes` lists added, changed and retired members between certified named-product inventories, with unchanged
member counts. It reuses existing inventories, preserves unknown baselines and makes no extra product-byte reads.
`--ddc` reads bounded retained-log observations of cache configuration and explicit cook hit/miss statistics.
Those historical logs do not prove current settings or measured warm/cold improvements; native baselines remain open.
Opt-in Python access auditing now checks declared file reads and owned writes before certification, with complete
source directory inventories and separate completion reports; the sandbox uses it. It does not prove metadata,
environment or native-I/O dependencies. Blender/Unreal Python bootstraps now have offline protocol coverage;
native execution and equivalence evidence remain separate requirements.
Named actions can declare exact optional source files; absent/present identities track conditional reads without
hashing unrelated siblings. The sandbox demonstrates this with a block override. Recipe-declared spatial boxes now
resolve into tracked product reads, including empty selections, additions, removals and movement. Audited Python
actions receive frozen matches through `atelier.build_context.query`; the offline sandbox proves narrow rebuilds
and restoration. Runtime-discovered query volumes and generated spatial indexes remain proposed.
[The recipe guide](BUILD_RECIPES.md) describes the implemented API, exercised by the sandbox's asset/placement example.
Signed source bundles can now enter the existing local store after publisher/policy checks and complete byte
verification. Optional HTTPS lookup uses fixed object-store paths, pinned publisher keys and bounded downloads;
ordinary builds fall back locally on a remote failure. A trusted producer can freshly execute one independent
audited Python action and export a signed V2 directory after clean/pushed-source, grant, audit and inventory
checks. It makes no native memory-guard assertion. Explicit HTTPS upload verifies public V2 bundles before loading
write credentials, commits immutable manifests last and checks remote bytes. Automatic publication and
hostile-source signer isolation remain unimplemented. Unreal restoration, import transactions and native spatial
migration still require native proof.
Legacy fingerprints, output cutoffs, module isolation and the [portable artifact pool](ARTIFACT_POOL.md) remain.
The current CLI and safety rules remain in force; no native import recipe or scheduler is switched by this phase.

The central contract is: **incremental build and clean build produce equivalent playable content, while unchanged
products stay unchanged.** Broad work remains appropriate for genuinely broad changes, such as an engine upgrade
or a shared generator that changes every mesh. Each such rebuild must have an inspectable reason.

## Evidence and priorities

The October 14, 2026 source and build-log audit found three distinct costs: invalidation spreads too widely,
individual build units do too much work, and valid outputs cannot generally be recovered across revisions.

| Observed case | Existing cost | Architectural cause |
| --- | --- | --- |
| Five tree LODs changed | `unreal.world` 2,000.4 s; 22 of 110 steps ran in 3,081 s | The world import clears a shared namespace and downstream steps restore unrelated assets |
| The package following that build | `unreal.cook` 1,328.2 s; download assembly 44.8 s | The cook stage includes native build, cook, staging and archive work; it is broader than import |
| A current world import | 1,171 package deletion operations over 630.5 s before the first texture import | Loading, deleting and preparing existing assets is itself expensive |
| Crater Park geometry and material edits | Region export 909 s, as reported by its builder | Geometry, neighbourhood operations, collision, AO and export share one step |
| One C++ line in a fresh reused worktree | First compile 832 s, from the builder's retained notes | Reused Binaries do not provide the object files and build state omitted from Intermediate |

The tree and package timings are recorded in the historical `ff-build.log` and `ff-package.log`; the deletion
interval comes from `unreal.world.guard/stdout.log`. These are observations of existing builds, not projected
speedups. Fourteen short import steps in the tree build alone totalled 256.6 s. Their costs are consistent with
substantial repeated editor startup, although a phase trace is needed to separate startup from useful work.

The implementation explains the first two causes. [The world importer](../games/yorimichi/unreal/Scripts/setup_project.py)
purges `/Game/Japan` to avoid stale material slots. [The recipe](../games/yorimichi/build.py) consequently makes
many region and sound imports depend on `unreal.world`. Its newer export digests stop some unchanged exports
from reaching Unreal, but a real change to one consumed asset still reruns the whole importer.

Much of the island is already placed at runtime from JSON by
[JapanWorld](../games/yorimichi/unreal/Source/Yorimichi/JapanWorld.cpp). Splitting the `.umap` alone would leave
the expensive import and generation dependencies intact.

## Build products and exact dependencies

Extend the build engine around three records:

| Record | Meaning |
| --- | --- |
| Action | A recipe, its exact inputs, parameters, tool context, outputs and validation policy |
| Artifact | Immutable files produced by an action, with a complete inventory and byte hashes |
| Build snapshot | The chosen artifact for each logical asset or data product, plus its dependency closure |

A logical product has a stable name, such as `foliage/pine_a/mesh`, `terrain/12_8/heights` or
`regions/harbour/placements`. A recipe can emit several products. Consumers depend on the particular products
they read; the fact that two files were produced by the same process does not make both inputs to every consumer.

An action key includes the implementation and imported helper closure, named source contents, consumed product
digests, parameters, relevant environment, output schema and tool identity. Unreal products additionally include
the engine build, loaded import modules and saved-type definitions, relevant configuration and package mount
context. Cooked products include target platform, renderer requirements, serialization versions and cook hooks.
Compiler actions include the real compiler, SDK, headers, flags and target.

Git revision and checkout location belong in provenance, not in a universal cache key. Inputs outside Git still
need explicit content identities. Hash the tools an action uses; the initial pool's hash of all studio Python
files is safely conservative but would cause unnecessary misses as a general policy. Concrete identities include
the Blender binary and relevant bundled libraries, UE build ID and loaded module identities, Python interpreter
and resolved package versions, and `uv.lock` for the Python environment. A narrower environment key requires proof
of the packages actually used; version labels alone do not identify locally modified binaries.

Dependencies need three meanings:

- **Read:** this action consumes values or bytes from another product, so a change can invalidate it.
- **Reference:** this product names another asset at a stable path and embeds no data derived from it. The asset
  must be present in the final snapshot, but changing its vertices does not by itself require resaving a record
  that only names it. Bounds, HISM/HLOD bounds, baked lighting/visibility, embedded collision, sockets, skeletons,
  and material slots or usage flags baked into a consumer are **read** dependencies. Runtime JSON placement can
  qualify as a reference; a map with precomputed scene data must prove the distinction.
- **Order:** an execution prerequisite, such as having the required editor modules available. Order alone does
  not imply that all changes to that prerequisite affect the content.

After an action reruns, propagate the identities of its resulting products. If an output is unchanged, stop
invalidation at that output. This generalizes the existing `cutoff` and export-digest work to every boundary.

Keep byte identity and semantic identity separate. Byte hashes prove that a copied artifact is intact. A validated
format adapter may ignore known nonsemantic FBX timestamps or generated IDs when deciding whether an import needs
to run. It must preserve geometry, ordering, settings and references. Do not remove arbitrary metadata or receipts
from dependency keys just because they look incidental. Logs and timings should live outside product payloads.

If the same action key produces different output, never replace the existing index entry silently. Quarantine
the conflict and diagnose missing inputs or nondeterminism. An adapter may accept different bytes only after its
versioned semantic checks establish equivalence; retain one canonical artifact and the comparison evidence.
An unresolved conflict removes the action's shared-cache eligibility.

## Dependency discovery and ownership

Each action declares the files and products it reads and the exact outputs it owns. One final Unreal package has
one owner. Base mesh import, authored LODs, collision, material assignment and CPU-access flags are phases of that
owner's recipe, or inputs to its final assembly. Independent steps must not quietly overwrite the same package.

Static Python import discovery supplies useful defaults, but cannot prove the closure of dynamic imports,
directory scans, environment access or data files opened at runtime. Builders should read products through an
Atelier context API that records those accesses. Directory queries record membership as well as file contents,
so adding or removing a neighbour invalidates the query's consumers. Add `sys.addaudithook` to the Atelier Python,
Blender and Unreal Python bootstraps for `open`, `os.listdir` and `os.scandir`, alongside the context API's records.
These hooks audit Python-level reads only: native FBX texture reads, native package loading and other subprocess
accesses still need explicit declarations and importer-specific dependency enumeration. This is not a complete
macOS process-access tracer. Controlled input workspaces and clean-versus-incremental checks test the declared
closure; until it is proven, keep conservative dependencies and restrict shared publication.

The implemented `Step.audit=True` accepts one Python, guarded Blender or guarded Unreal Python command per
owned-product action. Its access hook, private
scratch/bytecode paths and completion pipe catch undeclared reads, reference misuse, writes outside ownership and
reuse of stale output bytes. Each executed action starts with empty owned outputs; cache hits restore without running
it. Unsupported observed subprocess mechanisms fail. Path checks for ordinary Python
metadata queries do not make timestamp values portable. See [the current API and limits](BUILD_RECIPES.md#audit-a-python-generators-accesses);
the tracked context API remains separate work. Native audits use the same private nonce-bound completion pipe
and existing actual-child guard. They require `cache=False`; they grant no native cache or package-equivalence
certification. Their runtime exemptions are restricted to Python library directories inside the fingerprinted
host installation, never arbitrary import search paths. Blender uses factory startup; Unreal retains its module
descriptor isolation and before/after library checks. Offline fake-host tests cover the adapter protocol, not
successful real-host imports.

The bootstrap rejects preloaded project/helper Python modules even when their source is declared: an import from
`sys.modules` cannot establish which bytes or earlier reads produced the cached values. Preloaded module origins,
package paths and bytecode must belong to the fingerprinted tool (or fresh private bytecode scratch); only genuine
builtin/frozen loaders and an explicit set of native host API modules may lack file origins. Native Blender audits
include the complete installation bytecode inventory. Native host API state remains outside this Python diagnostic.

Audited native actions always use fresh processes. A `Batch` declaration falls back to ordinary execution for each
audited action, and direct audited warm-session launches are refused. Irreversible audit hooks and warm module or
callback state are not silently reused. The observer remains armed after completion; any further observed Python
file access, even one previously allowed, produces a trailing failure record. The parent drains through pipe closure
and requires exactly start/accesses/complete in order before certification. Native host startup, native callbacks,
native I/O and environment or metadata values still require explicit dependencies and native equivalence proofs.

Legacy actions can opt into deferred, explicit input membership: only selected actions enumerate their members,
after prerequisites finish, and execution rechecks the selection before certification. This does not track arbitrary
reads or enable native caching; [the recipe guide](BUILD_RECIPES.md#defer-legacy-input-membership) describes its restricted scope.

The planner should reject cycles, duplicate package ownership, missing products and writes outside owned paths.
Every output, including leaf assets and bulk-data sidecars, belongs in a verified manifest. A sentinel such as
`Torii.fbx` or `manifest.json` existing is insufficient evidence that the rest of a step's outputs survive.

## Import only changed assets

Treat an Unreal import as a cacheable compilation step:

```text
source asset and settings
          |
          v
generated mesh or texture  ->  imported Unreal package  ->  target cooked package
          |                            |                            |
          +-------------------- immutable artifact store ---------+
```

Before launching Unreal, resolve local and remote hits and calculate the changed package set. A cache hit for an
imported package restores the actual `.uasset` and required sidecars and dependencies. A cached FBX alone still
leaves the expensive Unreal work to do. Unreal's DDC remains a separate cache for derived engine data; it cannot
replace the imported package and its manifest.

Imported packages must also be relocatable. UE's `AssetImportData` records source filenames and timestamps;
its path conversion can produce relative or machine-dependent paths. Standardize a project-relative import
staging layout and normalize import metadata through supported APIs before publication. Resolve reimport from
the logical source catalog in the receiving checkout, never the donor's path. A semantic hash ignoring a path
does not remove that path from cached bytes. Scan exported package metadata and public bundles for machine paths,
and test restore and reimport with the donor checkout unavailable.

For misses, import into a controlled workspace with the final logical package paths and declared dependencies.
Preserve object paths on updates. Reset the affected package's material slots, LOD count, collision and other
authoritative settings explicitly; validate the result. Where an importer needs a fresh asset, recreate that
owned asset with reference-safe handling. The old namespace purge disappears once all of its outputs have owners.

Validate the complete write set and publish only completed products. Install them under a checkout write lease
while that checkout's editor/game is stopped. Use a journal and a snapshot completion marker: multiple package
file replacements are not one atomic filesystem operation. Interruption leaves an incomplete snapshot that
`play` and packaging refuse until repaired. Previously committed artifacts remain available for retry.

Hydration must invalidate affected generated asset-registry/discovery caches and arrange a supported rescan at
the next editor/cooker startup before assets are resolved. Include registry readiness in the snapshot launch
contract; a filesystem copy alone is not sufficient. Own redirectors explicitly, fix references on rename and
verify that registry queries and cooking see the new inventory. Do not restore a donor's registry blindly.

Deletion is a diff between the previous and new owned inventories. Remove only retired generated outputs, after
checking the new snapshot's references. Preserve authored content. Renames must update references explicitly;
they must not leave old packages discoverable by cooking.

Batch compatible misses into a bounded editor session. Compatibility includes the module closure, configuration,
renderer requirements and input snapshot. Keep individual artifact keys and success receipts even when execution
is batched. Size batches against measured memory growth, baseline editor footprint and guard headroom, rather
than an arbitrary asset count. End the session at each bounded batch boundary; an oversized asset takes a
separately sized batch. Validate that previous imports cannot leak state into the next recipe. Retain the current
render lock, memory guard, worker limits and handoff rules until the separately proposed capacity scheduler is
validated. A batch does not authorize parallel Unreal processes or an idle editor holding capacity. Use an empty
import world where possible and measure startup, import, derived-data work, validation and save separately.

The implemented opt-in `Batch` protocol saves and acknowledges each action before starting the next. It uses a
separate session guard report, per-action observed memory growth and a budget of at most 240 seconds checked
between actions. It yields with exit 75 instead of immediately reacquiring capacity; see [the operational contract](BUILD_RECIPES.md#reuse-a-tool-process-without-merging-actions).
Cold/warm and reversed-order native equivalence remain acceptance gates for every batch-enabled recipe.

Stage 1 now reports DDC configuration and explicit hit counts from retained logs. The two inspected worktrees use the same per-user
ZenLocal service and filesystem DDC, while ZenShared is disabled. Preserve that reuse and measure its effectiveness;
evaluate a remote/shared DDC for additional machines only on demonstrated benefit. DDC and Zen cook storage have
different responsibilities even when served by related infrastructure. Sharing DDC does not eliminate the import
package work measured above.

## Worlds built from independent parts

Separate world generation into reusable asset libraries, spatial data and placement:

- **Asset libraries:** meshes, textures, material families, character bodies, skeletons, individual clips and audio
  cues. A region references these products; placing a second tree does not generate another copy of its mesh.
- **Terrain:** stable tiles with height, surface and collision outputs. Boundary samples and blend margins are
  explicit products. A local terrain change affects its tile and the neighbours whose calculations read it.
- **Regions:** placement records, lights, gameplay markers, paths and local rules. These read asset IDs and the
  relevant terrain/connection contracts. Their geometry is generated in local coordinates where practical.
- **World assembly:** a small index of regions, their transforms, connections and runtime dependencies, plus a
  persistent map for global atmosphere and startup. Assembly does not reimport referenced asset libraries.

Initially retain Yorimichi's JSON and HISM placement model, splitting its records and generators at these
boundaries. Regions can later use sublevels or Level Instances for authored scene content. World Partition and
external actor packages are a separate choice for streaming and editor workflows; they do not remove an importer's
global reads or shared writes. Select them through a bounded region prototype when those needs justify the cost.

Region independence is a dependency contract, not a geographical assertion. A road crossing two regions reads
both boundary profiles. A volcano edit may affect the crater floor, access route and nearby vegetation. A global
lighting or terrain-seed change legitimately reaches much farther.

Crater Park needs an inner graph as well as a region boundary. Gate its detailed split on phase timings from Stage
1. Start with per-piece decoding, local simplification and export, retaining global neighbourhood passes until
measurements justify their split. Verify the archive checksum, then identify the actual piece arrays separately
so an unrelated edit in the source archive does not invalidate every piece. Export consumes the final processed
piece; caching export alone cannot bypass preceding neighbourhood work. Key those passes on the geometry,
transforms and roles within their influence volume:
covered faces and collision walls use nearby surfaces, AO and tunnel effects reach about 12 m, and supporting
walls can query ground up to 30 m below. Additions with large fixed boxes depend on the box contents. A single
12 m sphere is therefore not a sufficient key for all passes.

Replace global rail numbering and role-wide sequential collision chunks with stable element IDs and bounded
spatial chunks. Preserve the skate solver's required triangle ordering within each chunk. A geometry edit must
invalidate both its old and new influence areas. Terrain samples, collision queries, neighbouring-piece discovery
and removal of an occluder all belong in this dependency model.

## Artifact storage and reuse

The local store should be the default resolver for every certified action:

1. Use the current checkout product if its identity and inventory are valid.
2. Restore a matching immutable product from the machine store.
3. Fetch it from a configured remote store.
4. Execute and validate the action on a miss, then publish locally and optionally remotely.

Store an action-key index, content-addressed file blobs and snapshot manifests. Keep cache compatibility namespaces
for portable source products, imported Unreal packages, compiled objects and cooked target packages. A stable
package path is part of an imported artifact's identity: copying its bytes into a differently named mount is not
a valid remap.

Use independent APFS clones or copies for writable worktrees, preserving immutable store entries. Do not share
mutable Content, Binaries or Intermediate through links. Hydration verifies all bytes and the complete dependency
closure, including leaves. A fresh worktree may reuse unchanged products from different commits once those keys
are proven; it need not find a single donor whose entire build is current. Preserve strict `atelier reuse` until
the replacement satisfies those stronger per-product guarantees.

The optional HTTPS receiver now supports frequent small artifact retrieval from fixed object-store paths, with
explicit configuration, verified manifests, bounded downloads and local fallback; see [the cache guide](ARTIFACT_POOL.md#fetch-signed-products-over-https).
Explicit public-V2 bundle upload now completes the producer/receiver transport path with immutable conditional
writes and verified readback. Private redistribution/upload policy, receiver authentication, automatic publication
and hostile-source signing remain separate work. A private object store is the proposed default.
GitHub release bundles are a plausible backend for versioned starter packs
and larger snapshots; choose bundle sizes after checking current service constraints. GitHub Actions caches should
remain disposable accelerators. The source of truth is the recipe and committed sources, not the availability of
any hosted cache. No hosting limits or prices were assessed in this offline proposal.

Include trusted producer provenance, engine/tool context, package dependencies, checksums and redistribution
policy in manifests. Sign remote manifests and verify them against a pinned allowlist of publisher keys. The
default shared publisher accepts only a clean, recorded, pushed revision built by a trusted guarded producer;
development builds may still cache exact dirty-tree results locally. Publication policy does not put the whole
revision into every action key. Require an explicit redistribution grant; missing policy means private. Reject
credentials, `.env`, authentication state and sensitive billing/ledger records from output inventories. An approved
asset may carry a sanitized provenance reference. Public starter packs contain only approved distributable products.

Use quotas, leases for active builds and pinned manifests for released snapshots. Garbage collection removes
unreferenced blobs only after those roots are considered. Report unique store bytes separately from logical
worktree size; APFS clone sizes do not add up to physical disk consumption. Budget restore, cook and archive
temporary space before starting, and retain enough space to complete or roll back an installation.

## Compilation and cooking

Keep the existing separation between gameplay, saved asset types and editor import helpers. Move new serialized
types into small stable modules when their responsibility warrants it. Creating a C++ module for every geographic
region would add build and dependency overhead; most regions should be content and data units. Content plugins
are useful for genuinely reusable libraries with stable mounts.

Fresh-worktree compilation needs its own solution. Keep warm intermediates in long-lived worktrees and evaluate
the installed UnrealBuildTool's compiler artifact facilities on this Mac. Prove compiler, SDK, PCH, absolute-path,
debug-info and header compatibility before enabling reuse. Copying Intermediate wholesale across paths is not
the proposed shortcut. Continue to let UBT determine native compile actions and use its supported cache boundary.

Separate native target build, cook, container/staging and download assembly in timing and product identities.
The existing independent archive receipt is useful. Keep cook state warm and evaluate UE 5.8's dependency-aware
incremental cooker with the installed ZenStore/IoStore setup. An inspected cook log reports 7,694 packages cooked
and zero incrementally skipped. The installed engine source also distinguishes modern dependency tracking from
legacy iterative cooking; adding an `iterate` flag alone is not a correctness proof.

Use the build snapshot to enumerate runtime assets, including soft loads and data-driven paths. The current
`-cookall` approach protects those paths from omission; replace it only when explicit roots and their references
cover them. Engine/configuration/serialization changes, custom pre-save cook hooks and asset deletion must all
invalidate the appropriate cooked products. Let Unreal manage package-level cook dependencies and use whole
target receipts to certify their assembly; do not splice arbitrary cached cooked bytes into an unrelated registry.

Maintain the multiplayer identity over the actual composed code, assets and data. Per-artifact inventories can
make its calculation incremental, but the final identity must still reject mixed or incompatible builds. Content
containers may eventually be split by stable library/region groups to reduce repackaging. Shared shaders and
container metadata can still require broader work; measure that separately from generation and import.

## User and author experience

`atelier build <game>` remains the normal entry point. New projects should receive small example asset and region
recipes and [world authoring guidance](WORLD_BUILD_PRACTICES.md). Authors declare products and relationships;
the executor chooses cache lookup and batching. The same machinery must work for the sandbox and another game
without game names in platform code.

`build <game> [step ...] --plan`, `--explain` and `--json` now show decisions, changed inputs, missing products and
conditional consumers. Selection still uses step names or prefixes. Further reports should add cache hit source, retirement, time spent
waiting and actual useful execution. During planning, a dirty generator's unchanged output is not yet known;
show its consumers as conditional until that generator or a cache hit resolves them.

A no-op build should inspect cached inventories without repeatedly reading every large source and generated file.
Use a local file-hash index, with filesystem identity/change metadata as a memoization aid and full verification
at trust boundaries. Hash memoization must never certify a remote download or a suspected corrupted output.
The implemented index uses file identity, size and high-resolution modification/change metadata as hints, and
rehashes replacements or ambiguous whole-second metadata. No watcher is required; membership is scanned on each
check. `--verify` reads all bytes. A future watcher optimization must also invalidate on lost event history.

## Resource capacity

Small build products also allow finer scheduling. The [capacity admission proposal](BUILD_CAPACITY.md) replaces
fixed big/small lane categories with atomic memory/CPU reservations, measured workload profiles and named locks
for real exclusivity. Artifact lookup and the build graph determine the work; the capacity service decides when
it can safely execute. Existing slots remain authoritative until that scheduler passes its migration gates.
The implemented broker migration path also takes every legacy lane lock and retains the existing guards;
configuring it adds the capacity veto without authorizing new native overlap. Service installation, client
activation and removal of slot exclusion are distinct rollout steps.
The implemented `atelier capacity history GUARD_DIRECTORY` command inspects retained process measurements
without running a job. It distinguishes sampling sessions and watched processes, and reports a retained
aggregate tree-guard receipt separately when present. It does not yet provide per-phase owned-tree profiles,
calibrated reservations or disk estimates.

## Migration and acceptance gates

Implement in reviewable stages, each with a working ordinary build:

| Stage | Atelier work | Yorimichi work | Required evidence |
| --- | --- | --- | --- |
| 1 | Build explanations, phase timings, hash index, DDC diagnostics, output inventory and ownership checks | Record the tree, ramp, placement, clip and C++ baselines | Every rerun has a reason; complete changed-output lists; measured DDC reuse |
| 2 | Product references and reusable import recipe API | Extract foliage, shared materials and audio from the world purge; absorb package overlays into their owner | A tree LOD edit leaves unrelated regions, sounds and maps byte-identical |
| 3 | Automatic local artifact resolution, transactional hydration, compatible import batches | Migrate region and character imports to owned packages | Cross-revision restores, path portability, registry refresh, leaf integrity and interruption recovery |
| 4 | Spatial products and query dependencies, gated by phase profiles | Split world layout/terrain/scatter; make measured Crater Park bottlenecks local | A ramp edit updates only its proven influence area; seams and 64-triangle collision groups remain correct |
| 5 | Compiler cache experiment and incremental cook integration | Explicit runtime asset roots and final snapshot identity | Native one-line edit avoids asset import; incremental package agrees with clean package |
| 6 | Remote transport, trusted manifests, retention and distributable starter packs | Publish approved snapshots | Fresh checkout builds from cache; unavailable/corrupt remote falls back correctly |

Each stage must also land in the sandbox before it is accepted as platform functionality. Stage 1 supplies a
generic edit-boundary test harness; Stage 2 supplies recipe templates, product declarations, the context API,
Python audit bootstraps for Blender/Unreal and the ownership checker. Later stages exercise restore/registry
recovery, two neighbouring terrain tiles, native/cook invalidation and remote fallback using sandbox fixtures.
`atelier new` inherits these templates and examples. Yorimichi supplies the demanding case, not platform special cases.

The offline part of Stage 4 now has a sandbox proof: two fixed query tiles update for changed, added, removed
and moved products, ignore distant edits and unread siblings, and agree after cache restoration and a fresh build.
Audited actions refuse reads of the raw catalogue or nonmatching products. These are JSON dependency fixtures;
terrain seams, generated spatial indexes, native queries and collision ordering still require their own proof.

Stage 2 should start with the observed five-tree edit. The current foliage importer already accepts a subset of
names, which offers a concrete migration seam. Remove its shared material writes into the material owner and
make the final foliage package account for LOD0, authored LODs, slots, collision and required runtime flags. Once
the owner is complete, changing a LOD must not request `unreal.world` at all. Batching follows ownership so it
does not merely combine large unnecessary imports into one long editor run.

Keep a compatibility adapter for unmigrated `Step` recipes, with conservative dependencies and limited cache
eligibility. Migrate one package family at a time, record package ownership changes, and keep canonical generated
assets available throughout. Existing paths can remain during the split; wholesale package renaming is not a
prerequisite. Recipes without full dependency proof must not obtain broad shared-cache eligibility by default.

Performance acceptance has two parts. Structural gates require no Unreal launch on a no-op build, no import on a
pure runtime-JSON placement change, no unrelated package writes on a tree or texture edit, and reuse of unchanged products
across revisions. Provisional warm-machine latency goals are under 5 s for a no-op and under 5 min for the measured
five-tree edit, excluding gameplay QA and release assembly. Establish baselines and p50/p95 over repeated runs
before accepting these goals as supported performance. Report cold-cache cost separately.

Correctness gates compare a clean build, an incremental build after a representative edit, and a cache-restored
build. Compare exact identities where deterministic and validated semantic properties where engine metadata is
not: geometry, materials, LODs, collision, ordered triangles, skeletons, runtime records, package references and
multiplayer compatibility. Include negative controls for changed data/settings/tool versions, missing files,
new or removed neighbours, corruption, renames and stale redirectors/registry state, missing donor paths, conflicting
same-key results, interrupted saves and mixed snapshots. Native smoke tests must
load restored assets and exercise affected gameplay. These future native gates use normal guarded slots.

The migration is complete when these are enforced by Atelier's reusable APIs and regression checks, the sandbox
teaches the structure, and Yorimichi has no routine shared-namespace purge or whole-world generation dependency
for a local edit. A cache hit rate alone is not acceptance: a genuinely new local edit must also build locally.

## Documentation cutover

Documentation cleanup is part of every stage's acceptance, not a later task. Inventory all build, cache, world
structure and scheduling guidance, including agent instructions, inline CLI help and runnable examples. Rewrite
current reference documents in the implementation change that alters their behavior. Delete obsolete instructions
and redundant plans once their useful content has moved to the authoritative guide; Git retains their history.
Keep historical measurements clearly labeled as evidence rather than current commands.

| Documentation surface | Required treatment |
| --- | --- |
| [README](../README.md), [architecture](../ARCHITECTURE.md), [setup](SETUP.md) and CLI help | Explain ordinary automatic reuse, current commands, dependency diagnostics and resource admission |
| [Artifact pool](ARTIFACT_POOL.md) and reuse examples | Keep accurate during migration; consolidate into one artifact/cache guide and retire the manual-only guide when its commands are superseded |
| [Agent rules](../AGENTS.md), [board guide](AGENT_BOARD.md), machine-local board/setup templates | Replace slot-specific instructions at scheduler cutover, including fitting/compile rules, leases, fairness, recovery and protocol compatibility |
| [Sandbox](../games/sandbox/README.md) and `atelier new` templates | Ship executable examples for owned products, tracked inputs, small edits, restore and capacity requests |
| [World authoring](WORLD_BUILD_PRACTICES.md), [world map](../games/yorimichi/docs/WORLD_MAP.md), [Crater Park](../games/yorimichi/docs/CRATERPARK.md), [volcano](../games/yorimichi/docs/VOLCANO.md) and other affected region guides | Document final product boundaries, terrain contracts, package ownership and supported local-edit workflows; remove full-world workarounds that no longer apply |
| [Character pipeline](CHARACTER_PIPELINE.md), [packaging](../games/yorimichi/docs/PACKAGING.md), [desktop performance](../games/yorimichi/docs/DESKTOP_PERFORMANCE.md) and other affected workflow guides | Update clip/body/material dependencies, cook roots, cache compatibility and phase-specific admission; preserve valid QA requirements |
| This proposal and [capacity proposal](BUILD_CAPACITY.md) | Promote implemented sections into current architecture, retain unresolved decisions separately, and remove superseded proposal text when migration ends |

The stage reviewer checks links and CLI examples and searches for retired step names, removed flags, whole-world
import assumptions and old slot/admission rules. Machine-local instructions must be updated on each participating
host at cutover, without committing personal paths or host data. No stage is done while an active guide tells a
new user or agent to follow the old workflow. Until cutover, label future behavior as proposed and keep current
safety instructions operational.
