# Yorimichi V2 authoring audit — 8 November 2026

**Result: the port has committed editable Unreal content, but the split into independently editable objects is incomplete.** Some large areas still create their buildings and props at runtime. Some saved actors contain many objects, and the supported claim scopes often cover a whole region. Most external sources are not connected to V2's asset records.

This is an authoring audit, not a new gameplay acceptance report. A region can look right and play correctly while remaining difficult for two people to edit. Earlier estimates of playable-port progress do not measure the authoring work below.

## Scope and evidence

Baseline: **`7b4f509762714b3eb4240f4e8cae8ffdbd9563ed`**. Counts below describe that revision, not the implementer's changing working tree.

The audit enumerated every V2 `asset.toml` and region record, the saved patch rosters, all main-world service spawn paths, the import/save/ownership/check code, the original W00–W20 inventory, and the legacy source library. Large runtime JSON files were read only after their bytes matched the baseline's Git LFS object hash. Unreal content in the audit checkout was not imported, rebuilt or resaved. No native play session, full binary-content validation or retired test suite was run for this audit.

The code-supported findings below are distinct from observed play failures. In particular, the camp-clearance risk still needs an in-game check. Source-file counts describe tracked files or pinned LFS identities; they do not prove that every remote LFS object is retrievable or that every old generator can run unchanged.

**Work already in progress:** commit `0f3eb37adb` on the Mega Park port branch replaces eight default adoption batches with **45 named units for 1,017 packages**: 22 park sections, shared surface families, base materials, the seam and the standalone level. The largest unit has 111 packages. Its committed `units.json` and generator identify section source files. This is a useful improvement, excluded from the baseline counts. Adoption, saved-placement coverage and an editing round trip were not proved by this audit. Mega Park's asset permission is granted by the owner; old D05 group 3 restrictions are obsolete.

## What the folders actually mean

| Location | Role | What it does not establish by itself |
| --- | --- | --- |
| `unreal/Content/` | The saved Unreal meshes, materials, maps and other packages. These are committed through Git LFS. | A separate package is not necessarily one useful object: it may contain a whole chunk of geometry. |
| `unreal/Content/__ExternalActors__/` and `__ExternalObjects__/` | Saved map actors and their companion objects. Unreal chooses their filenames. | One actor may contain many tree instances or several meshes. Separate files do not guarantee separate claim scopes. |
| `assets/**/asset.toml` | Connects an asset ID, writer, ownership scope and output packages; can also declare sources and an import recipe. | An adopted record generally names only saved Unreal packages, not an original model or generator. |
| `assets/**/verified.json` | Records the exact accepted package bytes and declared inputs. | It does not prove visual quality or useful editing granularity. |
| `world/regions/**` | Defines areas and records which saved actor files each area owns. | It is not a complete list of everything visible there; runtime services add scenery too. |
| `unreal/Content/Data/` and `unreal/Source/Yorimichi/` | Runtime data and code for gameplay, plus remaining scripted scenery. | Fixed scenery here is not automatically a saved editor object. |
| `build/yorimichi_v2/` and ignored `Saved/` | Temporary exports, logs and other derived work. | These must not be the only recoverable copy of an authoring source. |

Keep these roles. The asset records and world ownership index are useful; they need accurate, narrower entries and a supported update path. Do not create a second manually maintained list of every transform or every Unreal reference.

## Inventory totals

| Measure | Baseline count |
| --- | ---: |
| Asset records | 360 |
| Declared asset output packages | 11,352 |
| Editor-owned records | 359 |
| Generated records | 1: `prop/lantern` |
| Records with a registered external source | 1: the lantern FBX |
| Records without registered external sources | 359, covering 11,351 packages |
| Of those: adopted records | 357, covering 11,345 packages |
| Of those: native map records | 2, covering 6 packages |
| Records declaring `references` or `input_dependencies` | 0 |
| Region records, including the small test map | 26 |
| Files listed in region actor records | 9,610 |
| Saved scene patches | 9,311 |
| Records named `loose_files` or `loose_files_N` | 29, covering 2,491 packages |

These are different measures: package counts are not object counts, actor-record files are not all scene patches, and an empty source list is not proof of lost source art. The family and region tables below cover the complete enumerated record set.

## Findings and repairs, in order

### A1 — Finish saving fixed scenery, starting with Brine Cove

**Impact:** a person can see a building or ship in the game but cannot reliably move that object by saving the editor map. It is created again from runtime data on the next run.

In [JapanWorld.cpp](../unreal/Source/Yorimichi/World/JapanWorld.cpp), the migration returns at `bMigrationBuild` before most service actors are spawned. [V2ScenePatch.cpp](../unreal/Source/Yorimichi/World/V2ScenePatch.cpp) additionally handles sky, sea and skate-pier scenery. It does not save the static geometry produced by all other services. A service being enabled in `RuntimeServices` is not evidence that its scenery was saved.

The largest clear gaps are Belmonte, Brine Cove, Crater Park and the fixed parts of transport systems. Brine Cove's runtime manifest has 529 mesh groups; Belmonte has 442, of which 432 are marked non-plant. Crater Park has 1,123 render pieces and 26 collision pieces. These are manifest entries, not measured live actor totals; runtime filters and instancing affect what is drawn.

**Smallest repair:** migrate one useful Brine Cove object and its collision to saved actors. Preserve appearance, fade, culling and contact behavior. Add an explicit switch that prevents only that migrated scenery from being spawned again. Retain the runtime activity or service. Extend this per feature, with stable IDs and an idempotent migration that preserves accepted editor changes.

Do not disable a whole service merely because its buildings were saved: that could remove trains, boarding, rails, NPCs or other gameplay. Do not regenerate the whole island for this work.

### A2 — Make ownership as narrow as the intended edit

**Impact:** separate actor files still contend when both writers need the same broad claim scope. This affects agents on one machine and on different machines equally.

[authority.py](../tools/content/authority.py), especially `scope_of`, `subject_scope`, `owning_scopes` and `authorize`, requires the owning scope as well as exact file locks. Region actors resolve to `region/<name>`. A claim on an invented child scope does not authorize that parent. The largest region owns 1,892 recorded files; Hidamari harbour owns 883. The ordinary supported workflow therefore serializes otherwise separate edits within those regions.

Asset records similarly provide a common scope and verification record. Asset-ID and declared-owner scope aliases exist; exact file locks still protect the same binary. Do not use the aliases to work around broad ownership. They do not provide a clear, supported per-object editing model.

**Smallest repair:** allow a saved object or bounded scenery unit to resolve to its own stable scope and owned paths. Use a region claim for actual region-wide migration or region-wide membership changes. Update ownership resolution and the save/validation path together; changing the scope name alone is insufficient. Keep verification entries split or deterministically mergeable so two disjoint saves do not overwrite each other's index updates. Keep one writer per Unreal package and companion file.

**Acceptance:** two agents edit two independent objects in the same named region, each in its own warm checkout. Both save, commit and integrate successfully; a third attempt to edit either exact owned package is refused. Repeat the handoff on a second physical machine when available. Same-host worktrees do not prove that last check.

### A3 — Replace arbitrary batches and split only the geometry that needs it

**Impact:** unrelated work shares a record, and a model may still bake several structures into one mesh. Renaming an ownership record cannot separate geometry inside that mesh.

| Current mesh ownership | Records | Packages | Why this needs work |
| --- | ---: | ---: | --- |
| `adopted/belmonte/meshes/loose_files_01..03` | 3 | 559 | Sorted batches mix furniture, buildings and country pieces. Individual source-model identities already exist. |
| `adopted/brinecove/meshes/loose_files_01..03` | 3 | 520 | Ground, rocks, ships and town pieces share arbitrary batches; some geometry is baked in place. |
| `adopted/craterpark/meshes/loose_files_01..06` | 6 | 1,149 | Render and collision pieces are divided by package order, not by the park feature being edited. |

Those 12 records cover **2,228 packages**. The other `loose_files` names are not automatically defects: a small coherent group may be fine. Conversely, a descriptive name alone does not make a group narrow enough.

Also inspect these concrete editing boundaries:

- `adopted/japan/foliagelods` holds 116 packages across tree families. A Ginkgo change should own its trunk/crown/LOD products, not unrelated species.
- `adopted/japan/treehouse` holds 109 piece/material/texture packages; `adopted/japan/assets/treehouse` holds 15 packages including `TH_Frame`, `TH_Trunks` and props. Those whole frame/trunk meshes combine substantial structures. Identify the actual owning record and preserve logical room/structure and fade boundaries when extracting an editable part.
- The skate pier is saved as one scenery patch. Split a prop or riding feature when independent edits require it, retaining its collision and rail relationship.
- Numbered batches also occur outside `loose_files`: examples include `experiments/citysurfaces/v1-128m/hd-northmountains_01..03`, `experiments/islandterrain/v1-atomic/farhills_01`, and `skateride/clips/b0/b_01`, `g_01..02`, `r_01..02` (under `adopted/`). These include 200-package records. Prefer spatial editing units for terrain and complete movement/clip families for animation; a sorted filename cutoff does not establish either. The 2,228-package count above covers only the three named mesh families, not every coarse group.
- Shared materials/textures, sound banks and character animation sets should be split by a real change boundary, not by a universal package-count limit. A skeleton and compatible clips can be a legitimate group; a single sound edit should not require claiming unrelated banks.
- Terrain/city surface pieces and tree instances may remain bounded rendering batches. One file per leaf, triangle or repeated tree is not the goal.

**Smallest repair:** first split the ownership records without moving package paths or reimporting bytes. Use source model IDs, named objects, park features or bounded surfaces; keep each package in exactly one record. Separately extract combined geometry only when a specific object cannot otherwise be edited. Pair render/collision variants and required LODs deliberately rather than relying on adjacent filenames.

Mega Park's pending 45-unit change is the right direction for package ownership. Its 100 m sections still need the same practical test: can the intended ramp or prop be changed without rebuilding unrelated sections?

### A4 — Accept intentional edits to saved patch contents

**Impact:** moving an existing instance can work, while adding/removing an instance or swapping its mesh can make the game report that the saved world is incomplete.

[V2ScenePatch.h](../unreal/Source/Yorimichi/World/V2ScenePatch.h) stores `ExpectedMembers`. `Members()` includes mesh path, role tags and instance count. `JapanWorld::RegisterScenePatch` compares the current members with that migration-time list. The migration writes the expected list; [save_validate.py](../tools/content/save_validate.py) records saved package hashes but does not accept a new member list.

Changing the bytes of an existing mesh at the same package path does not itself change this list. Editing transforms is also a different case from adding or deleting members.

**Smallest repair:** add an explicit claimed editor-save acceptance step for intentional membership edits. Validate references, roles and needed collision, then save the accepted membership and refresh the package record. Keep detection of accidental missing components. Do not simply remove the readiness check, and do not silently accept arbitrary changes at game startup.

**Acceptance:** add, remove and replace one small prop; close/reopen the editor, run the game, and rerun the applicable migration. The accepted edit persists exactly once, the game is ready, and unrelated packages are unchanged. A deliberately broken reference must still be rejected.

### A5 — Recover the source links before claiming a complete authoring workflow

**Impact:** an agent told to change a model usually cannot follow the V2 record back to its original model or generator. The broad donor provenance is useful, but does not describe a targeted reimport.

Only `prop/lantern` has a registered external source and recipe. The current [import runner](../tools/import/run.py) supports the narrow static-mesh and texture cases; it does not provide a registered skeletal-animation or procedural-world workflow for the adopted content. Editor-owned records are intentionally refused by that runner.

**This is not evidence that 11,351 packages have lost their sources.** Maps, Blueprints and material graphs may legitimately use the saved Unreal package as their original source. Much of the imported content has recoverable source files or code in V1. The next section identifies those sources and the remaining uncertainty.

**Smallest repair:** for each editing unit being worked on, declare one of these statuses:

1. **Native Unreal:** the saved package is authoritative; no external source is required.
2. **External source located:** record the exact file and checksum, plus the narrow import/export route and output packages. Preserve the source in V2 or in an explicitly retained shared location before retiring V1.
3. **Generator located:** record the generator, parameters and real inputs; support regenerating only this unit into temporary output.
4. **Restricted source located:** use the existing pinned restricted-storage route and verify it can be recovered. Do not put restricted originals in the public repository merely to fill a source field.
5. **Not located:** say so. Preserve the Unreal package and donor provenance; do not invent a source or claim reproducibility.

Supporting source import must not overwrite accepted editor-owned changes. Keep package authority explicit: either a targeted importer owns a package, the editor owns it, or a split record separates those products. An emergency export from Unreal is a recovered derivative, not the original Blender scene or generator.

Do not re-enable V1 tests or its full build as an acceptance requirement. Port a useful narrow importer/generator and its relevant checks into active V2 ownership when needed. Irrelevant old documentation and contracts may be retired; relevant source art and recipes must first be preserved.

### A6 — Be precise about what the indexes keep fresh

[check.py](../tools/content/check.py) and [changeset.py](../tools/review/changeset.py) already provide useful protection: package ownership, recorded hashes, declared source fingerprints, actor-record coverage, companion files, runtime-data pins and restricted-content checks. The hash cache also compares file metadata; a full check can rehash the bytes. These mechanisms should remain.

The gaps are semantic:

- An ordinary editor Save is not the entire V2 operation; the appropriate save validation must refresh the record.
- All 360 asset records have empty `references` and `input_dependencies`. The importer has no populated dependency graph for derived outputs. Unreal's direct package references still work; this does not mean every material change requires an import.
- Valid hashes do not prove that a tree's reduced-detail meshes still match its edited main mesh, that render and collision shapes agree, or that a world index includes runtime-spawned scenery.
- A record can remain internally consistent while its source recovery instructions are absent.

**Smallest repair:** make the supported edit command update/check the affected record as part of the save or import. Declare dependencies only where another asset's bytes are actually baked into an output. Query Unreal's own references for shared-use and deletion checks instead of manually duplicating its entire reference graph. Validate that new packages have exactly one owner. Keep normal build as validation/compile; missing inputs should produce a precise repair request, not a global regeneration.

## Do many assets lack source files?

**Many lack registered V2 sources. We cannot honestly count how many original sources are truly unavailable yet.** The audit found substantial original or convertible source material, but no complete package-to-source map. Do not report an unsupported lost-source percentage.

The tracked V1 asset tree contains **622 GLB files, 6 Blender files, 1 FBX and 278 NPZ geometry/data files**, as well as textures, manifests, audio and generators. Its [source library](../../yorimichi/assets/source-library.json) contains 1,895 entries. These sets overlap and must not be added together as unique asset totals. Some source assets are unused or outside the active port.

| Family | Source evidence located | What remains unproved or missing in V2 |
| --- | --- | --- |
| Belmonte | [source.json](../../yorimichi/assets/belmonte/source.json) describes 288 model sources with file paths/checksums. All 288 tracked file identities match those hashes; 278 names also occur among V2 outputs. | Register per-model source links and targeted import, including generated collision/split products. This is not a one-to-one mapping for all 559 mesh packages. |
| Brine Cove | [hero_sources.py](../../yorimichi/world/regions/brinecove/hero_sources.py), seven committed hero GLBs, textures and region generators. Hero sources include hull, figurehead, anchor, wheel, cannon, capstan and statue. | Map the baked ship/town pieces to their actual inputs; identify which pieces form the user's wreck. A hull source alone does not reconstruct the complete dressed wreck. |
| Main island, village, Hidamari, forest, treehouse and southwest | World/region builders, terrain/city partition builders, source-library models, foliage specifications. `Tree_Ginkgo.json` names its generator, parameters and reduced-detail settings. | Preserve the narrow recipes and inputs under active ownership. Many geometry packages are generated products rather than missing hand-authored Blender files. |
| Crater Park | [provenance.json](../../yorimichi/assets/craterpark/provenance.json), converted geometry/collision NPZ files, models and textures. The library lists 300 source entries. | Connect each park feature and collision product to its inputs; original authoring scenes are not proved available for every piece. |
| Mega Park, pending port | [provenance.json](../../yorimichi/assets/megapark/provenance.json), map/source IDs, geometry/collision NPZ and textures; 505 source-library entries. Pending units record section provenance. | Prove recovery/import and independent saved placement; prose source paths are not yet a checked importer fingerprint. Owner permission is granted. |
| Train, ferry, gondola and other vehicles | Vehicle source models/textures and region builders; the source library has 26 vehicle entries. | Trace each adopted output, derived collision and assembly. Keep moving parts under service logic. |
| Cairo, Modori, Nox, Paul | Cairo and Modori have tracked Blender files; Nox and Paul have tracked GLBs and source manifests. | Some earlier construction inputs point to build outputs or archived generations. A usable final model is not necessarily the complete history. Register the current authoritative source and each rig/animation dependency. |
| Fox hunter and sword trainer | Tracked Blender files and manifests. | Verify the source-to-current-package mapping and narrow character imports. The two tide-reader Blender files in the six-file total do not establish required port content. |
| Adventure moves and ride variants | Adventure source manifest, reference rig, clips, sword/glider models; retargeting and character-import code. | A targeted V2 animation/rig workflow, compatible-skeleton checks and a complete output map. |
| Horses and racing | Horse source manifest, models/coats and import code; 111 horse source-library entries. | Link breed, animation, coat and derived outputs; separate native racing data from imported geometry. |
| SkateRide, SkateMotion, SkateRuntime | Shared Skate plugin data plus the donor's simulation, clip import and verification recipes. | These 3,359 packages are not 3,359 missing original meshes. Identify raw restricted inputs versus derived clips/data; preserve their pins and narrow regeneration route. |
| Audio | Sound-bank manifests, fetch/slicing recipes and procedural synthesis code. | Some original masters are intentionally external/restricted. Verify recoverability, not public redistribution. A saved SoundWave is usable but does not prove its master is retained. |
| Materials, FX, Blueprints, maps, native data | Saved Unreal packages plus donor creation code and some source textures. | Classify each as native-authoritative or derived. No separate model file is needed for a native material graph or map. |

The donor's pinned baseline plus its archived local-fix patch remains useful provenance. It must not be presented as a tested per-object source recipe. Keep that provenance while replacing broad ownership with precise records.

## Concrete edit examples

### Change the Ginkgo model

Today the main model and its reduced-detail products can belong to different records; the 116-package foliage record combines species. An edit to only the main mesh may look correct nearby and wrong at distance.

1. Identify the selected tree's actual mesh and all derived Ginkgo crown/LOD/collision products. Distinguish changing the shared species from making one unique tree variant.
2. Extract a named Ginkgo editing unit and map its generator/specification or authoritative source. Keep package paths stable where possible.
3. Claim only that unit's changed source and output packages. Use a separate checkout. For a unique variant, create new owned packages and change only the selected saved placement.
4. Regenerate/import only the required derived products, or use the supported editor-owned route. Never run the legacy whole-world build for this edit.
5. Refresh the record; inspect near/far appearance and collision. Reopen and confirm an unrelated tree species and unrelated region packages did not change.

### Modify the shipwreck in Brine Cove

There is no unambiguous named `shipwreck` asset/actor in the baseline records. The audit found five `SM_BC_Ships_*` mesh groups, but that is not proof that all five belong to the requested wreck. First identify the actual visible object in the editor/game.

At baseline, the ship packages are in `adopted/brinecove/meshes/loose_files_02`, a 200-package group containing rocks and town geometry too. Brine Cove is created by [BelmonteRegion.cpp](../unreal/Source/Yorimichi/World/BelmonteRegion.cpp) from `Data/brinecove/runtime.json`; its ship transforms are identity placements with geometry baked into the pieces. The W09 saved patch roster has no ship keys. Moving a transient play-session actor is not a durable edit.

Use this order:

1. Select the wreck and list its actual render meshes, collision and shared materials. Determine whether a mesh also contains other structures.
2. Split a named wreck ownership record without changing existing bytes. Keep shared materials separately owned when other objects use them.
3. If the wreck is fused with other geometry, extract only its useful model parts from the retained source/generator. Preserve the old appearance and contacts; keep a stable local origin.
4. Save the wreck as one object or a small assembly of editable actors. Its placement and its reusable model have separate responsibilities. Stop runtime spawning only those migrated parts.
5. Change shape through the source/import route, position through the saved actor, or appearance through the relevant material. Claim the files actually changed, including collision/LOD products when needed.
6. Accept the intentional saved membership, reopen, play and rerun the applicable migration. The wreck must remain in its edited state exactly once. Another agent should be able to edit an unrelated Brine Cove object concurrently.

This is a repair plan for the current gaps, not a claim that the complete workflow already works.

## Whole-world coverage

This covers every W00–W20 inventory entry. Saved-patch presence means the recorded static patch path exists; it does not mean every visible service-owned object is saved. Source-code paths below are within `unreal/Source/Yorimichi/`.

| Inventory area | Authoring state at baseline | Needed boundary |
| --- | --- | --- |
| W00 island, sea, sky, roads | Main terrain and instance patches saved; sea/sky handled explicitly. | Preserve seams, per-patch settings and targeted surface products. |
| W01 start / houses | Saved patches. | Useful object scopes, source links and accepted membership edits. |
| W02 village | Saved scenery patches; trainer behavior remains runtime. | Save activity locations/props where still hardcoded; keep NPC behavior. |
| W03 mini Mega | Surroundings saved; `Skating/MegaRamp.cpp` creates ramp and trim. | Save ramp/trim and collision policy. |
| W04 skate pier | Scenery explicitly saved; rails, look and spawns remain runtime. | Split useful editable features and connect rails/markers to them. |
| W05 forest | Saved, instanced patches across several regions. | Tree-family sources/LODs and narrower placement ownership. |
| W06 lake | Saved patches. | Same placement/source rules; avoid whole-region locks for unrelated objects. |
| W07 Hidamari | Main city geometry saved; lights/local look and some settings still scripted. | Save local light/settings placement where useful; preserve dynamic look behavior. |
| W08 southwest | Saved patches. | Named surface/prop units and source mapping. |
| W09 Brine Cove | Surroundings saved; town/ship mesh groups still in `World/BelmonteRegion.cpp`. | Save useful fixed structures and props; do not mistake W09's roster for the town itself. |
| W10 treehouse | Structure/dressing/trunks represented by saved patches, largely within W06; lights/room volumes from `World/JapanWorld.cpp`. | Separate useful structural parts, room settings and lights; preserve fade/contact behavior. |
| W11 Mega Park | Saved surrounding terrain; actual park excluded from this baseline and now being ported with owner permission. | Complete active port, then fixed park-feature authoring. No rights block remains. |
| W12 crater/volcano | Volcano surroundings saved; park meshes/props from `Skating/SuperUltraMegaPark.cpp`, cloud from `World/CraterCloud.cpp`. | Save park features/collision and cloud settings/shell; retain rails, activities and animated effects. |
| W13 Ronin camp | `Combat/SwordTrainer.cpp` creates props and hardcoded NPC positions. | Save campsite props/markers. Verify vegetation clearance against saved-patch owners. |
| W14 Hidamari stable | A surrounding region record exists; `World/HidamariStable.h` disables the stable itself. | Preserve the baseline's disabled state unless the owner requests this feature. Do not infer enabled buildings from the region name. |
| W15 hippodrome | Surroundings saved; `Racing/Hippodrome.cpp` creates fixed venue meshes and reads course data. | Save venue and course markers; retain race logic. |
| W16 Belmonte | Surroundings saved; buildings/props/signs from `World/BelmonteRegion.cpp`. | Save bounded structures, signs and dressing with their collision/fade rules. |
| W17 ferry | `Travel/FerryService.cpp` mixes terminal geometry, boarding pieces and ships. | Save fixed terminal and anchors; keep boats and moving boarding parts. |
| W18 gondola | `Travel/GondolaService.cpp` mixes static supports/stations, ropes and moving cabins. | Save fixed supports/route anchors and suitable rope geometry; retain cabin/grip/audio logic. |
| W19 zeppelin | Fixed station meshes already occur in saved rosters; service animates gates/gangways. | Do not classify the moving parts as a static-migration defect. Move hardcoded station offsets to owned anchors when edited. |
| W20 train and shared routes | `Travel/BelmonteTrack.cpp` builds track/tunnel pieces; train service adds platform extensions and boards. | Save fixed track/platform/board structures and route anchors; keep trains, doors, changing displays and activation logic. |

Other local scenery to account for: train-board frames/posts in `Travel/BelmonteTrainBoards.cpp`, TV bodies in `Racing/RacingBroadcast.cpp`, local lighting in `World/HarborLook.cpp` and `World/JapanWorld.cpp`. Preserve dynamic screen pictures, moving vehicles, NPC equipment, birds, leaves and other effects as runtime behavior.

**Unproved camp risk:** `SwordTrainer.cpp` clears foliage through `AJapanWorld` components, while saved foliage belongs to `AV2ScenePatch`. The migration return precedes camp creation. Inspect the camp during its normal gameplay pass; if vegetation blocks it, move the clearance to the actual saved-content path. This audit did not observe a live obstruction.

## Execution plan

The next delivery should be a small, working editing example, followed by the other regions. Do not pause the independent gameplay port for an abstract redesign.

1. **Brine Cove pilot:** identify the user's wreck, split its ownership, save its placement, retain its source and prevent duplicate runtime spawning. Implement A4 only as much as needed to accept this legitimate edit. Preserve an untouched appearance baseline.
2. **Prove independent work:** another agent edits a nearby unrelated prop in a separate checkout. Integrate both changes, reopen and play. Fix the broad region scope/index bottleneck if it prevents this. No whole-world rebuild or shared mutable editor folders.
3. **Apply the pattern:** Belmonte objects, Crater Park features, then fixed transport structures and camp/hippodrome/local dressing. Use the coverage table, preserve gameplay, and keep the Mega Park port moving with its improved units.
4. **Recover sources in the same units:** use the source table; record native-authoritative, located, restricted or not-located status. Add targeted recipes only for the actual source types being edited. Keep donor source and provenance until transferred or deliberately retained.
5. **Close the source inventory:** account for every asset record, including shared materials, animation banks and audio. The deliverable is an actionable source status and recovery path, not a promise that every package has an FBX. Resolve unknowns or state the accepted limitation explicitly.
6. **Final collaboration proof:** human editor save/reopen and two physical machines, each using separate writer checkouts. Check conflict refusal, successful disjoint edits, handoff and preserved edits. Keep these honest final acceptance items; unavailable collaborators need not stop independent port work.

For each migrated editing unit, report only: **what is now saved; what remains runtime; source/recovery status; ownership scope; what was actually edited and played**. Update the existing inventory rather than adding another competing progress system.

The port's authoring goal is met when an agent can find an object, know what owns its shape and placement, recover its authoring source where one is needed, change only that unit, and hand it to another person without losing edits or rebuilding unrelated content.

## Complete record-family inventory

Every adopted family below has zero registered `sources`, `references` and `input_dependencies` at the baseline. This table is a snapshot for audit coverage, not a new live index. Read the actual records for later revisions.

| Asset family | Records | Packages |
| --- | ---: | ---: |
| `adopted/adventure` | 2 | 123 |
| `adopted/audio` | 5 | 200 |
| `adopted/belmonte` | 5 | 616 |
| `adopted/belmontetrack` | 2 | 146 |
| `adopted/belmontetrain` | 27 | 659 |
| `adopted/brinecove` | 5 | 699 |
| `adopted/cairo` | 2 | 21 |
| `adopted/cairoadventure` | 1 | 113 |
| `adopted/cairobike` | 1 | 10 |
| `adopted/cairohorse` | 1 | 13 |
| `adopted/craterpark` | 9 | 1,265 |
| `adopted/experiments` | 99 | 1,392 |
| `adopted/ferry` | 3 | 66 |
| `adopted/foxhunter` | 2 | 21 |
| `adopted/fx` | 2 | 12 |
| `adopted/gondola` | 4 | 96 |
| `adopted/hippodrome` | 4 | 31 |
| `adopted/horses` | 8 | 637 |
| `adopted/japan` | 74 | 1,182 |
| `adopted/modori` | 3 | 131 |
| `adopted/modoribike` | 1 | 10 |
| `adopted/modorihorse` | 1 | 13 |
| `adopted/nox` | 3 | 130 |
| `adopted/noxbike` | 1 | 10 |
| `adopted/noxhorse` | 1 | 13 |
| `adopted/paul` | 3 | 130 |
| `adopted/paulbike` | 1 | 10 |
| `adopted/paulhorse` | 1 | 13 |
| `adopted/racing` | 1 | 1 |
| `adopted/seethrough` | 1 | 1 |
| `adopted/skatemotion` | 2 | 27 |
| `adopted/skatepark` | 4 | 47 |
| `adopted/skateride` | 69 | 3,331 |
| `adopted/skateruntime` | 1 | 1 |
| `adopted/swordcamp` | 3 | 17 |
| `adopted/swordtrainer` | 3 | 129 |
| `adopted/wanderer` | 2 | 29 |
| `map/slice` | 1 | 3 |
| `map/test-minimal` | 1 | 3 |
| `prop/lantern` | 1 | 1 |

## Complete saved-region inventory

The file count is the length of each `actors.verified.json` file map, including any recorded companion objects. Patch counts come from each region's patch roster. An area's runtime scenery is additional; see the coverage table above.

| Region | Recorded files | Scene patches |
| --- | ---: | ---: |
| `region/test-minimal` | 4 | 0 |
| `region/w00-island` | 292 | 3 |
| `region/w01-start` | 255 | 253 |
| `region/w02-village` | 119 | 119 |
| `region/w03-mega` | 66 | 66 |
| `region/w04-pier-approach` | 260 | 256 |
| `region/w05-forest-far-east` | 1,892 | 1,892 |
| `region/w05-forest-far-northeast` | 122 | 122 |
| `region/w05-forest-far-west` | 1,344 | 1,344 |
| `region/w05-forest-north` | 304 | 304 |
| `region/w05-forest-west` | 79 | 79 |
| `region/w06-lake-treehouse` | 163 | 163 |
| `region/w07-hidamari-harbour` | 883 | 883 |
| `region/w07-hidamari-station` | 586 | 586 |
| `region/w08-southwest-coast` | 162 | 162 |
| `region/w08-southwest-isle-east` | 94 | 94 |
| `region/w08-southwest-terrace` | 27 | 27 |
| `region/w09-brinecove` | 459 | 459 |
| `region/w11-megapark` | 559 | 559 |
| `region/w12-craterpark` | 176 | 176 |
| `region/w12-volcano-north` | 275 | 275 |
| `region/w12-volcano-south` | 501 | 501 |
| `region/w12-volcano-west` | 478 | 478 |
| `region/w14-hidamari-stable` | 165 | 165 |
| `region/w15-hippodrome` | 149 | 149 |
| `region/w16-belmonte` | 196 | 196 |
