# Build v2 recipe coverage and unit design

E0a documentation snapshot, 2026-10-23. This ledger maps the v1 production surface to migration tasks;
it does not turn on v2 or attest a native cutover. Task IDs refer to the build-v2 delivery plan, draft 7.
The design baseline is draft 8 and the testing baseline draft 7. Those planning documents remain separately owned.

The source baseline is **`9eefc8a99c3566165c8ebf2eb638451e7ffd1de2`**. Recipe discovery at that revision
produced **313 Yorimichi declarations and 11 sandbox declarations**, including explicit targets.
The older 301-step r13 sample is historical. Counts are not completeness criteria: dynamic membership and
conditional branches below are part of the scope even when absent in one invocation.

Discovery evaluated `load_recipe(game).steps(Context(game, create=False))` for each game and read the
factory definitions and callers. It launched no producer or native process and created no `build/` directory.
The recipe source SHA-256 is `3736c682c0acd2b328834568c6d8c177998fc3fff93b6fb999dbb30176e5681f`, also bound by Editor Cost’s independent static call census. That census is not an executed export inventory. The declaration snapshot is [coverage.json](coverage.json); it is documentation, not a second recipe format,
a generator, a saved build certificate, or a replacement for Editor Cost's original-export census.

## Decision and ownership rules

| Decision | Meaning |
|---|---|
| already atomic | The existing runnable boundary is useful as-is; declare/adapt it, then prove equivalence. This is not a native proof-ready state. |
| split needed | One v1 action still owns independent exports/imports/finishes/data or combines stages. Split those owners using existing source interfaces. |
| adapter only | Preserve the existing product, validation gate, query or target boundary; replace v1 declaration/dependency mechanics. |
| move to QA | Keep diagnostics accessible as QA consumers of production outputs, outside the production graph. |
| remove | Remove only after replacement and last-reader migration, with a stated reason. |

A logical final asset has one owner: raw import owns a scratch package set; finish owns its checkout package set.
An authored LOD/collision group stays whole where it cannot run independently. A skeleton/physics set is owned
once, while animations consume that skeleton as content. Assembly owns its roster/placement files and copies
independent exports; it never claims sibling meshes by listing a representative manifest.

`outputs` in v1 often lists only a report or seed FBX. The JSON preserves those under `representative_outputs`
and keeps declared Product and checkpoint roots separately. An empty declared inventory means **ownership must
be established from the producer/save census before migration**, not that the action writes nothing.
The row's task owns that completion. All required package sidecars, optional-sidecar absence, runtime records,
textures and retired members must be accounted for before a v2 declaration is accepted.

## Unit boundaries by output family

| Output owners | Task | Design and remaining work |
|---|---|---|
| 22 `world.textures.<key>` source images | E1 | Already one image per action. Keep logical key and exact consumed image bytes. `world.textures` is an aggregate selector, not another image owner. |
| Forest, Hidamari, Treehouse, SwordCamp atlas, MegaPark/Crater restyles, pier and FX images; Belmonte/Brinecove selected textures | E1 | Split multi-image finishers into independent textures. Material graphs belong to E15/D6 or their named family, not image generation. Native textures require decoded-pixel/mip comparison. |
| Six sound preparation families and optional selected music clips | E2 | One prepared clip per unit. Preserve source master selection and DSP inputs; do not key every clip on unrelated masters. |
| Audio manifests, banks, cues, SoundWaves and runtime assembly | E18 | One owner per manifest/bank/cue and one native import per clip; E2 owns the prepared clip bytes. Optional music selector changes retire stale owned packages explicitly. |
| `skate.runtime`, staged Data, content retirement, network identity and racing roots | E3 | Separate independently produced runtime payloads and staged files. Network identity intentionally reads the whole participating content set; retain a justified whole input, not an unproved reference. Racing checks retain breed/coat/tack/jockey cook-root coverage. |
| Skate skeletal set, about 1,600 clips, simulation/motion assets and board transition material | E4 | One clip per unit; skeleton once; independent data/material owners. Existing 4 import/2 verify batches are execution grouping, not shared clip keys. |
| 18 foliage species and independent render variants; city tree LOD/CPU-access finishing | E5 | Species planner; one independently exportable mesh/variant per key. Preserve authored LOD and collision groups. `world.foliage_lods` is only a selector. Shared material interface bytes are content; material paths become references only after invariance tests. |
| Brinecove source catalogue, 36 plant models, 13 logical constructors / 520 outputs | E6 | Plant-model actions already exist; adopt them. Consume Editor Cost's per-piece payload plans and file-only runtime/geometry/material/map/clearance views. First cutover includes the one-piece edit chain and warm v1 import. |
| Terrain/road/wires/sea, final map images/data and native world map/assets (148 raw-mesh baseline) | E7 | Export/import/finish per item; map owns only baked content. `world.map` emits runtime atlas PNGs and JSON: these are production content, not diagnostic renders. Split composite `unreal.world` by actual package owners. |
| All-region `world.layout` | E8 | Terrain/query units plus one placement unit per region. Each reads its real layout/queries and references asset names only when contents are not read. |
| SwordCamp 14, mini-Mega 3, houses 8 | E9 | Adopt existing Editor Cost splits at matching hashes; preserve material and placement ownership. SwordCamp's narrow native edit proof is the only completed one-edit native reuse claim in this handoff. |
| Hidamari constructors, selected city/volcano inputs, city tiles/trees, native north | E10 | 86 constructors plus city/tree leaves; preserve selected-input cutoffs and current city membership. Full actual 1,049-leaf receiving proof remains pending. Shared tree finishing is E5. |
| Belmonte 232 static, 56 ground, 2 north | E11 | Adopt explicit geometry/material/placement views. North/ground queries consume exact values without quantization. Material identity proof does not certify saved native meshes. |
| Train vehicles, fitted furniture, furniture LOD/bake, consist, route, track, service/runtime files and native train/track | E11.1 | One model/LOD group per independent owner; keep production bake/optimization in dependency graph. Separate SVG/review output from runtime route/data. Source split handoff remains pending. |
| Island 7 parents / 290 final pieces; Southwest 16; Crater Park; MegaPark | E12 | Adopt bounded export plans and native rosters; keep authored collision once and seams/contact gates. MegaPark's 50 render models / 82 logical exports include collision/seam/seed owners; 832 internal construction parts are not 832 required assets. |
| Village and explicit stable | E13.1 | Source conversion active at Editor Cost; stable model/native remain production-capable explicit targets. Stable renders move to QA. |
| Forest 40 levels and lake 5 logical producers | E13.2 | Source/FBX proof exists; actual new-region native equivalence remains pending. Forest twig images remain E1. |
| Zeppelin and four stations | E13.3 | Separate independent constructor/export owners and runtime station/layout data; native receiving is currently inside `unreal.world`, not a missing independent `unreal.zeppelin` row. |
| Hippodrome course/structures and native venue/data | E13.4 | Python producer today, not automatically a Blender task. Preserve source GLBs and per-course/structure ownership; convert using existing interfaces after source handoff. |
| Treehouse frame/dressing | E13.5 | Preserve frame, trunks, structure, bounded dressing pieces, five baked UV channels, native roster and retired-parent removal. Capsule-axis bake remains an explicit global data barrier. |
| Treehouse 13 props and four canopy trees | E13.6 | Independent prop/tree exports, textures and native groups; source conversion active. Shared native treehouse importer must be decomposed without overlapping E13.5 paths. |
| Skatepark pier, board, runtime queries and textures | E13.7 | Bounded native pieces are not proof of independent source cache units. Keep complete pier/board/material/texture inventory, collision and logical riding query ownership. |
| Gondola kit/structures/ground/site/service and native packages | E13.8, E17 | Separate geometry and contact queries; each fitted support/access/span consumes exact relevant terrain/structure output. Preserve closure, walk and actual collision probes. |
| Ferry ship/terminals/site/service, harbour cuts and native packages | E13.9, E17 | Preserve deck walks, sweep/underwater envelope, moving brow collision and both harbours. Hidamari ferry cut is a real geometry dependency, not incidental ordering. |
| Generic world props | E13.10 | Independent rock/torii/lantern/pole/bird/sky exports; native import currently hidden in `unreal.world`. Source handoff pending. |
| Sailboat | E13.11 | Five source constructors (`hull`, `sail`, `boom`, `rudder`, `wake`) loop in one Blender action. **Split needed**, not already atomic merely because five files are written. Native sailboat import/materials currently run inside `unreal.world`. |
| Kei, kart and bike | E13.12 | **Split needed**: four kei models; kart body/seat/wheel/steering wheel; bike's eight parts plus layout and assembly. Retain collision/pivot ownership and cockpit/grip validation. No extra body variants inferred from source-library files. |
| Horses | E13.13 | **Split needed**: per-breed contacts/trajectories/turn source and per native skeletal/animation/tack/coat owner. Six breeds (`arabian`, `thoroughbred`, `friesian`, `andalusian`, `clydesdale`, `quarter`), seven tack IDs (`00`–`06`), eleven manifest clips plus generated turns. Five coat-mask families and manifest-selected coat variants remain dynamic members. |
| Crater cloud | E13.14 | Source is **already atomic Python data**: `cloud_build.py` calls `cloud.write` to emit `craterpark/cloud.json`, used for runtime nested shells. Native action creates the plain/blur-veil materials. Do not invent a Blender/static-mesh exporter requirement. |
| Cairo, Modori, Nox, Paul, Sword Trainer | E14.1–E14.5 | See character matrix. Own each skeletal set, texture, authored/retargeted clip, runtime data and pawn/readiness record explicitly. Fit gates remain required validation. |
| Fox Hunter, Wanderer; shared adventure reference/props | E14.6, E14.7 | Fox Hunter exports mesh and 15 clips; Wanderer is imported through `setup_project`. Shared adventure reference rig/marker, sword and paraglider are separate owners, not another playable body. |
| Shared materials/textures/parameter collections, FX, see-through finish, desktop city-piece integration | E15 | Decompose actual saved packages and mutations. `unreal.see_through` writes character materials: fold into their unique finish owners. `unreal.desktop` owns city pieces and retired parents; it is not disposable UI configuration. Tree CPU access/LOD finish remains E5. |
| Editor target and four module digests | P1, I8 | Adopt #603 project-source closure and complete binary receipt. Module digest steps are dependency proxies, not four extra compiler products; remove only after all readers use the explicit code closure. |
| Game target, cooked packages/globals and app/archive | P2, F1/F3, P3 | Adopt #614 after handoff. Separate game receipt from cook (`-skipbuild`). Individual Zen package restore and mixed-history global rebuild need F1 proof; whole-cook restore does not close G5. |
| Sandbox block, placements, spatial sources/tiles, material/level, explicit cook; copied new-project templates | E19 | Preserve source/placement independence, optional override identity and touching/empty spatial queries. Native level currently combines material/map; split it. New projects must emit only v2 declarations after their cutover. |

## Conditional and dynamic coverage

These rules extend the exact instantiated rows. They are not optional migration exemptions.

| Branch / factory | Baseline and all branches to cover | Task and owner rule |
|---|---|---|
| `texture_steps`, `foliage_build.world_steps/unreal_steps` | Catalogue currently 22 textures and 18 species; additions/removals create/retire named members. | E1/E5; use catalogue identity and independent item keys, not a fixed count. |
| Brinecove source/model factory | `foliage_names.definitions()` selects 36 committed model definitions today. Membership/checksum record is distinct from each model output. | E6; removed models retire only their exact output owners. |
| City factory | Six sources: HD_Terrain, HD_Streets, HD_Square, HD_CivicGardens, HD_Park, HD_Harbor; Harbor has final ferry-opening input; trees have separate selection. Runtime expansion produces more pieces than declaration rows. | E10/E5; plan children use stable names and complete roster; full receiving pending. |
| Crater `CRATERPARK_V2` | True selects NumPy geometry + Blender export. False selects legacy `regions/craterpark/build.py` under the same `world.craterpark` name. | E12; include both source paths until explicitly retired under I8. Never alias their keys. |
| Crater editor/design selection | Default shipped editor park; explicit editor park and selected lines; `EDITOR_PARK=off` legacy/generator route; design file selection chooses v4. `world.craterpark_layout` appears only for selected design/editor. Referenced terrain/heightmap/elements/site/block data and preferred-site existence affect selection. | E12/E8/E7; declare selected files, existence and setting values, including referenced data. Same recipe name does not imply same unit identity. |
| Character discovery | `definition.movers()` discovers committed `adventure.toml` definitions, donor first; playable flag adds bike/horse lanes and pawn; committed grips directory adds grip data; adventure manifest availability adds/removes reference and retarget/import actions; fit steps depend on available export lanes. | E14.1–E14.7; absence is explicit, new characters require an E0a row/task assignment. Do not assume every definition is playable. |
| Character module/finish options | Character TOML selects modules, source/exporter, physics/morph/contact/cloth/see-through behavior and material options. Nox adds AtelierCore contact types. | E14 / E15 / P1; project settings remain keyed; skeleton/material mutations must have one finish owner. |
| Optional music | `audio.music` and `unreal.music` are always declared explicit targets. Cache catalogue/lock, categories/styles/groups/limit select tracks. `data.content` also records enablement/selection and retires old music. | E2/E18/E3; empty/missing/present selection and removed SoundWaves tested, no implied download during plain build. |
| Train furniture / vehicle selection | `TRAIN_VEHICLES`, `TRAIN_FURNITURE`, per-item LOD budget and `status == built` assembly membership are dynamic. | E11.1; exact selected model/LOD/bake and runtime membership, not representative SVG/report outputs. |
| Transport generated membership | Gondola parameter `product_files()` / LOD suffix filtering and ferry reports determine packages, ground/structure queries, service data and textures. | E13.8/E13.9/E17; source-bound complete census before declaration. |
| Horse roster | Breed, clip, generated turn, tack, coat-mask and coat-variant catalogues expand source/native/racing and rider clip lists (`Horse<clip>`, mount, dismount). | E13.13/E14/E3; shared skeleton/group ownership, exact selected material/texture inputs. |
| Native modules / save ownership | Four current module digest declarations depend on character/import module requirements. `declare_owned_content` adds explicit checkpoint roots only for known independent native namespaces; shared Japan/character/SkatePark roots remain mixed. | P1/E tasks/I3; declarations are not observed save proof. Never infer whole-folder ownership for shared namespaces. |
| Sandbox source discovery | `world/spatial/*.json` creates per-source geometry/preview products; two tiles query a fresh catalogue. Block override may be absent or present. | E19; disappearance retires only the corresponding source outputs; optional input presence changes identity. |
| Sandbox cook modes | Explicit experiment only. `build_cook.apply` chooses default vs dependency-tracked incremental when configured, or requested full/incremental mode. | E19/F1; preserve explicit mode selection, project-owned settings and evidence; no unproved production cache hit. |
| `atelier new` | Copies tracked sandbox files and renames module/project/game paths, including build recipe and README; fresh ProjectID generated in config. | E19/J2/P4; migrate copied declarations, template docs and installation together. |

## Character variant matrix

Only these observed recipe lanes belong to the current character migration scope. A source library's unused
body/outfit file does not create an extra production variant. Clip membership remains in the bound source manifests.

| Character | Task | Body / own clips | Bike / horse | Adventure / fit | Grips | Pawn |
|---|---|---|---|---|---|---|
| Cairo | E14.1 | yes | both | donor; `own.npz`, retarget and fit | absent | yes |
| Modori | E14.2 | yes | both | retarget and fit | committed | yes |
| Nox | E14.3 | yes; contact morph data | both | retarget and fit | absent | yes |
| Paul | E14.4 | yes | both | retarget and fit | absent | yes |
| Sword Trainer | E14.5 | yes | neither | retarget and fit | absent | no |
| Fox Hunter | E14.6 | mesh + 15 clips | neither | no separate mover lane | absent | no |
| Wanderer | E14.6 | procedural model + clips | neither | no separate mover lane | absent | no |
| Shared adventure reference | E14.7 | reference rig/marker + sword/paraglider | neither | source for all retargets | n/a | no |

## Diagnostics still reachable from v1

E16's merged #615 removed `skate.ride_stills` and the train viewer. It did not remove the following declarations.
All six are explicit; plain builds skip them. The delivery-plan owner accepted E16.1 for these remaining targets, without changing
any rendering behavior here. Production furniture LOD baking remains E11.1.

| Explicit diagnostic target | Output | Normal production consumers of this target |
|---|---|---|
| `world.belmonte_train_plan` | dimensioned SVG plan | none |
| `world.belmonte_train_review` | white-background train control renders | none |
| `world.belmonte_track_review` | railway track control renders | none |
| `world.belmonte_station_review` | station control renders | none |
| `world.belmonte_train_furniture_review` | LOD/interior renders and sheets | none |
| `world.hidamari_stable_review` | stable control renders | none |

`world.belmonte_train_route` mixes runtime route/line/terrain-mask data with diagnostic plans/profile work; keep
its runtime data under E11.1 and extract only the diagnostics. Fit/equivalence/contact reports that gate a
production result remain validators; “reports out of build” must not remove correctness checks.

## Caller and last-reader migration

| Caller / reader | Current entry or boundary | Task / acceptance |
|---|---|---|
| Build CLI, listing, target prefixes, dry/JSON plan and explain | `atelier/cli.py`, `build.py`, `build_plan.py`, `build_products.py`, `build_spatial.py` | I1/I2/A4; one scheduler/output owner and summary across mixed migration. Read-only plan never runs/fetches/installs. |
| Play | `cli.play`; game profile scripts including `games/yorimichi/tools/desktop_preview.py`; `build_snapshot.require_complete` | I10/B3; restored build/readiness and reader exclusion before launch. It currently launches rather than automatically building. |
| QA and live scenarios | `cli.py` QA dispatch + game `scenarios/`; live bridge | I10/B3; QA requires complete output snapshot; live bridge is a reader, not a hidden build executor. |
| Stream | `stream.py` uses build Context/project outputs and own web build | I10/J2; reader locking for native products; web build remains its own non-game-build path. |
| Release publish / playtest downloader | `release.py`, `release_claim.py`, `playtest.py` | I10/P3/I4; existing verified package inventory, source binding, readiness and immutable upload semantics retained. Release publish does not cook or launch. |
| Merge | Owner workflow uses exact-head `gh pr merge`; old `atelier merge` is absent in this source revision | I10/I8/J2; audit docs/tool callers, preserve successful shared results without reinstating an obsolete wrapper. |
| Cache / legacy donor commands | `cache_admin.py`, `artifact_pool*`, `artifact_snapshot.py`, `artifact_publisher.py`, `artifact_remote*`, `artifact_bundle.py` | I2/I3/I8; migrate warm evidence before deleting producer/receiver paths. Remote retention/publication has readers beyond build CLI. |
| Checkpoint capture/restore/worker and native candidates | `checkpoint_*`, `build_checkpoints.py`, `unreal_mesh_reuse.py` | I3/I8; original task evidence and current validation remain distinct; candidate hint is not a result certificate. Preserve non-build release/backup readers until migrated. |
| Support/batch/cook recovery | `build_support_migration.py`, `build_batch_migration.py`, `build_cook_recovery.py`, `build_zen.py` | I8/C5/B3/F; retire only after replacement recovery/cleanup proof and last readers move. |
| Timings/changes/DDC observations | `build_timings.py`, `build_changes.py`, `build_ddc.py`, `build_tree_observations.py` | I2/I8/I4; diagnostics read v2 unit state/evidence without reintroducing v1 fingerprint evaluation. |
| Templates/examples/install | `new.py`, `games/sandbox/`, `docs/BUILD_RECIPES.md`, README, ARCHITECTURE, agent docs | E19/J2/P4/I11; fresh generated project v2-only; installation walkthrough uses its existing smoke proof. |

## Source handoff and proof limits

Editor Cost owns source decomposition and central graph/adapters until explicit commit/file handoff. This ledger
changes no source interface and creates no competing geometry representation. Adopt `Asset(key, source, suffix)`,
`export_tasks.steps`, validated `plan.json` discovery, exclusive Product roots, stable parent/cell/piece names,
32,768-triangle single-primary membership, APFS casefold uniqueness and one retained whole collision owner.
Identical projected payload bytes stop export propagation even if shared planner code changes. Assembly is file-only;
queries preserve exact consumed values. v2 owns declarations/controller/store/native cache adaptation after handoff. Editor Cost confirms the immutable executed original-export census is **not complete**; the harness’s 22-group minimum is not exhaustive. Every family above remains explicitly pending that census and native proof as applicable.

The following are scope-limited inherited observations, not new validations run for E0a. Proof reuse requires the
actual relevant code/input hashes in the bound receipt; a commit label alone cannot transfer proof to changed code.
Private receipt locations stay outside this public document.

| Family / bound evidence identity | Inherited observation | Still required |
|---|---|---|
| SwordCamp, invocation `10622386aca40ecd89b2d3c9` | One edit: 1 imported, 13 reused locally; whole exit 0, 18.84 s, empty guard; 26 sibling planner/export certificates unchanged. | Match exact code/input hashes, then v2 export/import/finish/store and cutover gates. No cook/restore claim. |
| Southwest immutable `283329c07` | 16 parents / 99,329 triangles → 31 exports, max 16,759; source and actual FBX only. | Native saved mesh/GPU LOD/collision/contact comparison and normal assembly as affected. |
| Island final `08dcfc27e`, 7 parents / 290 pieces | Final source/FBX proof reported passed in the handoff update. | Relevant source bindings plus actual saved native packages, current collision/LOD and normal assembly acceptance. |
| Parks immutable `283329c07` | Mega 82 logical exports / 303,303 triangles; Crater 1,123 render controls / 1,100,476 triangles and four whole collision controls / 757,537 triangles → 26 children. | Final normal assembly and actual native acceptance. Earlier collision codec changes require affected revalidation. |
| Hidamari producer / frozen native source `14b09c56` | 86 raw constructors / 4,978,909 triangles source exact; Harbor 190,896 triangles / 12 pieces attribute proof; warm compile and three synthetic automation passes. | Actual complete 1,049-leaf city receiving; synthetic/source tests do not close it. |
| Belmonte | Selected material PNG/report identity, grouping and assembly/graph checks passed. | Full original/new native receiving and collision-canary revalidation where codec changed. |
| Forest/lake source `34928771`, normal graph `d10be430` | 40 + 5 producers, 80 image pixel arrays source/FBX pass; normal native products/runtime wired. | Actual new-region native equivalence. Native observer compile `04` completed whole exit 0 with empty guard but **no reporters**, so it proves no model comparison. |
| Other E13 and E14 families | No complete source/native equivalence claim inherited here. | Immutable original-export census, handed-off source, per-class comparisons and targeted native checks. |

The inherited evidence index binds these exact available receipt hashes. They identify metadata bytes, not a
blanket acceptance of the current branch; the receipts contain the relevant producer/input hashes.

| Receipt | SHA-256 |
|---|---|
| SwordCamp native edit result | `a304aaf0b5346b63dbe20c71a106a5c3eddb4e48b14d1555b8406d4f8ecf5e52` |
| Southwest result | `17d4e8e2224012cec54b00775c02f3b4ae73f2b83c05f33a9418734c742b1cb2` |
| Southwest original sources | `abb2898819bd09181fd2f77992a811e9622503b943030d612999dd48899bfaeb` |
| Parks result | `a1a61af137ba670e22a9c48b7e969c9b3fc62e1dc4d0093e8f69e30901303ca2` |

The index’s earlier Island 512 m result is superseded by the final seven-parent proof; no old receipt hash is
presented as the new final proof. Obtain the final bound receipt before reusing that acceptance.

Adopt `atomic_equivalence` source binding/census/results and `NativeAtomicEquivalence` snapshot/probe/component-policy
API. Compare full source/FBX attributes and multiplicity; then real saved MeshDescription, every GPU LOD/tangent
basis, cooked triangles/typed hulls, component policy and both-neighbour ray/capsule seams. Empty or missing reporters
cannot pass the aggregate. No row in this document claims G1–G5, cook parity, fresh-checkout native restore or complete
all-family acceptance.

## Plan corrections and contract planning

The delivery-plan owner accepted these narrow corrections during the inventory handoff:

1. E16's #615 completion stays scoped to the two removed previews; E16.1 covers the six explicit diagnostic
   targets above and separation of the mixed production/diagnostic route output. This does not reopen the completed PR.
2. E13.14 source adaptation now names D1, D5/D6 for native materials, not an obligatory D2/D4a mesh path. Keep the
   family acceptance, runtime cloud data and material proof; do not invent static geometry work.
3. The inventory classifies E13.11 and E13.12 as **split needed** at this baseline: five sailboat constructors, four kei models,
   four kart parts, eight bike parts plus assembly/layout. Source splitting remains coordinated with Editor Cost.
4. E0a's 301 sample must remain historical; this snapshot has 313 + 11, with future dynamic plan rows added
   at handoff/cutover. I11 closure checks mappings and branches, not a fixed row count.

J1 should attach narrow `owner:fontanierh` invariants and specific test links at the actual implementation scopes:
project-input identity/manual platform invalidation (A3 identity tests); stable child/removed membership (A4 T0);
complete disjoint raw/finish ownership and optional-sidecar presence (A2/B3/D4/D5); query/reference invariance
(D3/D6 T1/T2); file-only assembly (D2/E-family equivalence); unchanged output cutoff and per-clip independence
(A9/E4); validate-before-publish/current native admission (B2/D4); fit/readiness/cook-root preservation (E3/E14);
and restored reader exclusion (B3/I10). Do not impose global AST scans or “check all code” as a substitute.

Execution-platform policy is deliberate: installed Python, libraries/lockfiles, Blender/add-ons, Unreal and
Xcode/SDK/clang are excluded from automatic Atelier keys. Relevant **project-owned** code, settings and build files
remain inputs. Platform refreshes use explicit op/cache-version bumps. v1 automatic tool fingerprints in existing
recipes are migration evidence only and must not silently return as v2 identity requirements.

E0b scaffolding is not needed for this ledger. The exact declaration snapshot and family/branch decisions are
reviewable without Rust or an additional generic generator. Remaining native work is batched by proof owner;
source-only passes are reused only within their actual hash scope.

## Instantiated recipe rows

The exact declaration snapshot, including required and optional Product roots and representative legacy outputs, is in [coverage.json](coverage.json). `output_inventory_complete` means the recipe declares products or checkpoint roots; it does **not** attest runtime write tracing, native acceptance, or that legacy `outputs` are complete. Every row below has the baseline source revision above. The JSON carries the same task, decision and reason per row.

| Game / recipe | Task | Decision | Output role |
|---|---|---|---|
| yorimichi / `world.textures.leaf_broad` | E1 | already atomic | texture |
| yorimichi / `world.textures.leaf_cedar` | E1 | already atomic | texture |
| yorimichi / `world.textures.leaf_pine` | E1 | already atomic | texture |
| yorimichi / `world.textures.leaf_ochre` | E1 | already atomic | texture |
| yorimichi / `world.textures.leaf_maple` | E1 | already atomic | texture |
| yorimichi / `world.textures.leaf_ginkgo` | E1 | already atomic | texture |
| yorimichi / `world.textures.leaf_ochre_small` | E1 | already atomic | texture |
| yorimichi / `world.textures.leaf_small` | E1 | already atomic | texture |
| yorimichi / `world.textures.litter` | E1 | already atomic | texture |
| yorimichi / `world.textures.cloudmask` | E1 | already atomic | texture |
| yorimichi / `world.textures.flower` | E1 | already atomic | texture |
| yorimichi / `world.textures.rooftile` | E1 | already atomic | texture |
| yorimichi / `world.textures.grass` | E1 | already atomic | texture |
| yorimichi / `world.textures.bark_olive` | E1 | already atomic | texture |
| yorimichi / `world.textures.bark` | E1 | already atomic | texture |
| yorimichi / `world.textures.road` | E1 | already atomic | texture |
| yorimichi / `world.textures.ground` | E1 | already atomic | texture |
| yorimichi / `world.textures.ground_detail` | E1 | already atomic | texture |
| yorimichi / `world.textures.sky` | E1 | already atomic | texture |
| yorimichi / `world.textures.water` | E1 | already atomic | texture |
| yorimichi / `world.textures.concrete` | E1 | already atomic | texture |
| yorimichi / `world.textures.white` | E1 | already atomic | texture |
| yorimichi / `world.textures` | E1 | adapter only | target |
| yorimichi / `world.treehouse_trees` | E13.6 | split needed | source |
| yorimichi / `world.layout` | E8 | split needed | layout |
| yorimichi / `world.forest_textures` | E1 | split needed | texture |
| yorimichi / `world.forest` | E13.2 | split needed | source |
| yorimichi / `world.props` | E13.10 | split needed | source |
| yorimichi / `world.foliage.Tree_Broad_A` | E5 | split needed | source |
| yorimichi / `world.foliage.Tree_Broad_B` | E5 | split needed | source |
| yorimichi / `world.foliage.Tree_Broad_C` | E5 | split needed | source |
| yorimichi / `world.foliage.Tree_Maple_A` | E5 | split needed | source |
| yorimichi / `world.foliage.Tree_Maple_B` | E5 | split needed | source |
| yorimichi / `world.foliage.Tree_Ginkgo` | E5 | split needed | source |
| yorimichi / `world.foliage.Tree_Pine_A` | E5 | split needed | source |
| yorimichi / `world.foliage.Tree_Pine_B` | E5 | split needed | source |
| yorimichi / `world.foliage.Tree_Cedar_A` | E5 | split needed | source |
| yorimichi / `world.foliage.Tree_Cedar_B` | E5 | split needed | source |
| yorimichi / `world.foliage.Bush_Green_A` | E5 | split needed | source |
| yorimichi / `world.foliage.Bush_Green_B` | E5 | split needed | source |
| yorimichi / `world.foliage.Bush_Ochre_A` | E5 | split needed | source |
| yorimichi / `world.foliage.Bush_Ochre_B` | E5 | split needed | source |
| yorimichi / `world.foliage.Bush_Flower_A` | E5 | split needed | source |
| yorimichi / `world.foliage.Bush_Flower_B` | E5 | split needed | source |
| yorimichi / `world.foliage.Grass_A` | E5 | split needed | source |
| yorimichi / `world.foliage.Grass_B` | E5 | split needed | source |
| yorimichi / `world.foliage_lods` | E5 | adapter only | target |
| yorimichi / `world.farhills` | E12 | split needed | source |
| yorimichi / `world.hidamari` | E10 | split needed | source |
| yorimichi / `world.hidamari.city` | E10 | adapter only | digest |
| yorimichi / `world.hidamari.north` | E10 | adapter only | digest |
| yorimichi / `world.belmonte` | E11 | split needed | source |
| yorimichi / `world.belmonte.meshes` | E11 | adapter only | digest |
| yorimichi / `world.belmonte.ground` | E11 | adapter only | digest |
| yorimichi / `world.brinecove.sources` | E6 | adapter only | digest |
| yorimichi / `world.brinecove.model.broad_0` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.broad_1` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.broad_2` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.broad_3` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.broad_4` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.broad_5` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.broad_6` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.broad_7` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.emergent_0` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.emergent_1` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.emergent_2` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.small_0` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.small_1` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.small_2` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.palm_0` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.palm_1` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.palm_2` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.palm_3` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.palm_4` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.palm_5` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.shrub_0` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.shrub_1` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.shrub_2` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.shrub_3` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.shrub_4` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.bloom_0` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.bloom_1` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.cover_fern_0` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.cover_grass_0` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.cover_leaf_0` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.cover_fern_1` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.cover_grass_1` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.cover_leaf_1` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.cover_fern_2` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.cover_grass_2` | E6 | already atomic | source |
| yorimichi / `world.brinecove.model.cover_leaf_2` | E6 | already atomic | source |
| yorimichi / `world.brinecove` | E6 | split needed | source |
| yorimichi / `world.brinecove.meshes` | E6 | adapter only | digest |
| yorimichi / `world.zeppelin` | E13.3 | split needed | source |
| yorimichi / `world.zeppelin.meshes` | E13.3 | adapter only | digest |
| yorimichi / `world.hidamari_textures` | E1 | split needed | texture |
| yorimichi / `world.hidamari_props` | E10 | split needed | source |
| yorimichi / `world.hidamari_props.import` | E10 | adapter only | digest |
| yorimichi / `world.treehouse_textures` | E1 | split needed | texture |
| yorimichi / `world.treehouse_props` | E13.6 | split needed | source |
| yorimichi / `world.treehouse` | E13.5 / E13.6 | split needed | source |
| yorimichi / `world.terrain` | E7 | split needed | source |
| yorimichi / `world.terrain.meshes` | E7 | adapter only | digest |
| yorimichi / `world.village` | E13.1 | split needed | source |
| yorimichi / `world.village.import` | E13.1 | adapter only | digest |
| yorimichi / `world.houses` | E9 | split needed | source |
| yorimichi / `world.southwest` | E12 | split needed | source |
| yorimichi / `world.mega` | E9 | split needed | source |
| yorimichi / `world.swordcamp_atlas` | E1 | already atomic | texture |
| yorimichi / `world.swordcamp` | E9 | split needed | source |
| yorimichi / `world.megapark_restyle` | E1 | split needed | texture |
| yorimichi / `world.megapark` | E12 | split needed | source |
| yorimichi / `world.craterpark_restyle` | E1 | split needed | texture |
| yorimichi / `world.craterpark_geometry` | E12 | split needed | source |
| yorimichi / `world.craterpark` | E12 | split needed | source |
| yorimichi / `world.craterpark_layout` | E12 | adapter only | data |
| yorimichi / `world.crater_cloud` | E13.14 | already atomic | data |
| yorimichi / `world.lake` | E13.2 | split needed | source |
| yorimichi / `world.skatepark_textures` | E1 | split needed | texture |
| yorimichi / `world.skatepark` | E13.7 | split needed | source |
| yorimichi / `world.sailboat` | E13.11 | split needed | source |
| yorimichi / `world.bike` | E13.12 | split needed | source |
| yorimichi / `world.horses` | E13.13 | split needed | source |
| yorimichi / `world.kei` | E13.12 | split needed | source |
| yorimichi / `world.kart` | E13.12 | split needed | source |
| yorimichi / `world.belmonte_train` | E11.1 | split needed | source |
| yorimichi / `world.belmonte_train_plan` | E16.1 | move to QA | qa |
| yorimichi / `world.belmonte_train_furniture_lods` | E11.1 | split needed | source |
| yorimichi / `world.belmonte_train_assembly` | E11.1 | split needed | source |
| yorimichi / `world.belmonte_train_review` | E16.1 | move to QA | qa |
| yorimichi / `world.belmonte_train_route` | E11.1 | adapter only | data |
| yorimichi / `world.belmonte_track` | E11.1 | split needed | source |
| yorimichi / `world.belmonte_track_review` | E16.1 | move to QA | qa |
| yorimichi / `world.belmonte_station_review` | E16.1 | move to QA | qa |
| yorimichi / `world.belmonte_train_furniture_review` | E16.1 | move to QA | qa |
| yorimichi / `world.belmonte_train_service` | E11.1 | adapter only | data |
| yorimichi / `world.belmonte_track_data` | E11.1 | adapter only | data |
| yorimichi / `world.belmonte_track.meshes` | E11.1 | adapter only | digest |
| yorimichi / `world.map` | E7 | split needed | source |
| yorimichi / `world.hidamari.tiles.HD_Terrain` | E10 | adapter only | digest |
| yorimichi / `world.city_tiles.HD_Terrain` | E10 | split needed | source |
| yorimichi / `world.hidamari.tiles.HD_Streets` | E10 | adapter only | digest |
| yorimichi / `world.city_tiles.HD_Streets` | E10 | split needed | source |
| yorimichi / `world.hidamari.tiles.HD_Square` | E10 | adapter only | digest |
| yorimichi / `world.city_tiles.HD_Square` | E10 | split needed | source |
| yorimichi / `world.hidamari.tiles.HD_CivicGardens` | E10 | adapter only | digest |
| yorimichi / `world.city_tiles.HD_CivicGardens` | E10 | split needed | source |
| yorimichi / `world.hidamari.tiles.HD_Park` | E10 | adapter only | digest |
| yorimichi / `world.city_tiles.HD_Park` | E10 | split needed | source |
| yorimichi / `world.hidamari.tiles.HD_Harbor` | E10 | adapter only | digest |
| yorimichi / `world.city_tiles.HD_Harbor` | E10 | split needed | source |
| yorimichi / `world.city_tiles` | E10 | adapter only | assembly |
| yorimichi / `world.city_tiles.meshes` | E10 | adapter only | assembly |
| yorimichi / `world.hidamari.trees` | E5 | adapter only | digest |
| yorimichi / `world.city_trees` | E5 | split needed | source |
| yorimichi / `world.city_trees.meshes` | E5 | adapter only | digest |
| yorimichi / `characters.cairo` | E14.1 | split needed | source |
| yorimichi / `characters.cairo_bike` | E14.1 | split needed | source |
| yorimichi / `characters.cairo_horse` | E14.1 | split needed | source |
| yorimichi / `characters.cairo.import` | E14.1 | adapter only | digest |
| yorimichi / `characters.cairo_bike.import` | E14.1 | adapter only | digest |
| yorimichi / `characters.cairo_horse.import` | E14.1 | adapter only | digest |
| yorimichi / `characters.modori` | E14.2 | split needed | source |
| yorimichi / `characters.modori_bike` | E14.2 | split needed | source |
| yorimichi / `characters.modori_horse` | E14.2 | split needed | source |
| yorimichi / `characters.modori.import` | E14.2 | adapter only | digest |
| yorimichi / `characters.modori_bike.import` | E14.2 | adapter only | digest |
| yorimichi / `characters.modori_horse.import` | E14.2 | adapter only | digest |
| yorimichi / `characters.nox` | E14.3 | split needed | source |
| yorimichi / `characters.nox_bike` | E14.3 | split needed | source |
| yorimichi / `characters.nox_horse` | E14.3 | split needed | source |
| yorimichi / `characters.nox.import` | E14.3 | adapter only | digest |
| yorimichi / `characters.nox_bike.import` | E14.3 | adapter only | digest |
| yorimichi / `characters.nox_horse.import` | E14.3 | adapter only | digest |
| yorimichi / `characters.paul` | E14.4 | split needed | source |
| yorimichi / `characters.paul_bike` | E14.4 | split needed | source |
| yorimichi / `characters.paul_horse` | E14.4 | split needed | source |
| yorimichi / `characters.paul.import` | E14.4 | adapter only | digest |
| yorimichi / `characters.paul_bike.import` | E14.4 | adapter only | digest |
| yorimichi / `characters.paul_horse.import` | E14.4 | adapter only | digest |
| yorimichi / `characters.sword_trainer` | E14.5 | split needed | source |
| yorimichi / `characters.sword_trainer.import` | E14.5 | adapter only | digest |
| yorimichi / `characters.modori_grips` | E14.2 | adapter only | data |
| yorimichi / `characters.fox_hunter` | E14.6 | split needed | source |
| yorimichi / `characters.wanderer` | E14.6 | split needed | source |
| yorimichi / `audio.footsteps` | E2 | split needed | audio |
| yorimichi / `audio.combat` | E2 | split needed | audio |
| yorimichi / `audio.skate` | E2 | split needed | audio |
| yorimichi / `audio.bike` | E2 | split needed | audio |
| yorimichi / `audio.transport` | E2 | split needed | audio |
| yorimichi / `audio.kart` | E2 | split needed | audio |
| yorimichi / `audio.music` | E2 / E18 | split needed | audio |
| yorimichi / `fx.textures` | E1 | split needed | texture |
| yorimichi / `world.ferry_ship` | E13.9 | split needed | source |
| yorimichi / `world.ferry_probes` | E13.9 / E17 | split needed | source |
| yorimichi / `world.ferry_site` | E13.9 / E17 | split needed | source |
| yorimichi / `world.ferry_terminals` | E13.9 | split needed | source |
| yorimichi / `world.hidamari_ferry_cut` | E13.9 | split needed | source |
| yorimichi / `world.ferry_service` | E13.9 | adapter only | data |
| yorimichi / `world.gondola_kit` | E13.8 | split needed | source |
| yorimichi / `world.gondola_ground_inputs` | E13.8 / E17 | split needed | source |
| yorimichi / `world.gondola_ground` | E13.8 / E17 | split needed | source |
| yorimichi / `world.gondola_structure_inputs` | E13.8 / E17 | split needed | source |
| yorimichi / `world.gondola_structures` | E13.8 / E17 | split needed | source |
| yorimichi / `world.gondola_site` | E13.8 / E17 | split needed | source |
| yorimichi / `world.gondola_service` | E13.8 | adapter only | data |
| yorimichi / `skate.runtime` | E3 | split needed | data |
| yorimichi / `unreal.compile` | P1 | adapter only | compile |
| yorimichi / `unreal.module.YorimichiImport` | P1 / I8 | remove | digest |
| yorimichi / `unreal.module.YorimichiAssets` | P1 / I8 | remove | digest |
| yorimichi / `unreal.module.AtelierCore` | P1 / I8 | remove | digest |
| yorimichi / `unreal.module.Yorimichi` | P1 / I8 | remove | digest |
| yorimichi / `unreal.materials` | E15 | split needed | native |
| yorimichi / `unreal.foliage.Tree_Broad_A` | E5 | split needed | native |
| yorimichi / `unreal.foliage.Tree_Broad_B` | E5 | split needed | native |
| yorimichi / `unreal.foliage.Tree_Broad_C` | E5 | split needed | native |
| yorimichi / `unreal.foliage.Tree_Maple_A` | E5 | split needed | native |
| yorimichi / `unreal.foliage.Tree_Maple_B` | E5 | split needed | native |
| yorimichi / `unreal.foliage.Tree_Ginkgo` | E5 | split needed | native |
| yorimichi / `unreal.foliage.Tree_Pine_A` | E5 | split needed | native |
| yorimichi / `unreal.foliage.Tree_Pine_B` | E5 | split needed | native |
| yorimichi / `unreal.foliage.Tree_Cedar_A` | E5 | split needed | native |
| yorimichi / `unreal.foliage.Tree_Cedar_B` | E5 | split needed | native |
| yorimichi / `unreal.foliage.Bush_Green_A` | E5 | split needed | native |
| yorimichi / `unreal.foliage.Bush_Green_B` | E5 | split needed | native |
| yorimichi / `unreal.foliage.Bush_Ochre_A` | E5 | split needed | native |
| yorimichi / `unreal.foliage.Bush_Ochre_B` | E5 | split needed | native |
| yorimichi / `unreal.foliage.Bush_Flower_A` | E5 | split needed | native |
| yorimichi / `unreal.foliage.Bush_Flower_B` | E5 | split needed | native |
| yorimichi / `unreal.foliage.Grass_A` | E5 | split needed | native |
| yorimichi / `unreal.foliage.Grass_B` | E5 | split needed | native |
| yorimichi / `unreal.world` | E7 / E10 / E13.1 / E13.3 / E13.10 / E13.11 / E14.6 / E15 | split needed | native |
| yorimichi / `unreal.north` | E10 | split needed | native |
| yorimichi / `unreal.southwest` | E12 | split needed | native |
| yorimichi / `unreal.mega` | E9 | split needed | native |
| yorimichi / `unreal.swordcamp` | E9 | split needed | native |
| yorimichi / `unreal.megapark` | E12 | split needed | native |
| yorimichi / `unreal.craterpark` | E12 | split needed | native |
| yorimichi / `unreal.houses` | E9 | split needed | native |
| yorimichi / `unreal.kei` | E13.12 | split needed | native |
| yorimichi / `unreal.kart` | E13.12 | split needed | native |
| yorimichi / `unreal.bike` | E13.12 | split needed | native |
| yorimichi / `unreal.horses` | E13.13 | split needed | native |
| yorimichi / `unreal.lake` | E13.2 | split needed | native |
| yorimichi / `unreal.forest` | E13.2 | split needed | native |
| yorimichi / `unreal.treehouse` | E13.5 / E13.6 | split needed | native |
| yorimichi / `unreal.skatepark` | E13.7 | split needed | native |
| yorimichi / `unreal.skate_board` | E4 | split needed | native |
| yorimichi / `unreal.crater_cloud` | E13.14 | split needed | native |
| yorimichi / `unreal.sounds` | E18 | split needed | native |
| yorimichi / `unreal.music` | E18 | split needed | native |
| yorimichi / `unreal.fx` | E15 | split needed | native |
| yorimichi / `unreal.fox_hunter` | E14.6 | split needed | native |
| yorimichi / `unreal.cairo` | E14.1 | split needed | native |
| yorimichi / `unreal.cairo_bike` | E14.1 | split needed | native |
| yorimichi / `unreal.cairo_horse` | E14.1 | split needed | native |
| yorimichi / `unreal.modori` | E14.2 | split needed | native |
| yorimichi / `unreal.modori_bike` | E14.2 | split needed | native |
| yorimichi / `unreal.modori_horse` | E14.2 | split needed | native |
| yorimichi / `unreal.nox` | E14.3 | split needed | native |
| yorimichi / `unreal.nox_bike` | E14.3 | split needed | native |
| yorimichi / `unreal.nox_horse` | E14.3 | split needed | native |
| yorimichi / `unreal.paul` | E14.4 | split needed | native |
| yorimichi / `unreal.paul_bike` | E14.4 | split needed | native |
| yorimichi / `unreal.paul_horse` | E14.4 | split needed | native |
| yorimichi / `unreal.sword_trainer` | E14.5 | split needed | native |
| yorimichi / `unreal.see_through` | E15 | split needed | native |
| yorimichi / `unreal.city_tree_cpu_access` | E5 | split needed | native |
| yorimichi / `unreal.city_tree_lods` | E5 | split needed | native |
| yorimichi / `unreal.desktop` | E15 | split needed | native |
| yorimichi / `unreal.skate_clips` | E4 | split needed | native |
| yorimichi / `unreal.skate_data` | E4 | split needed | native |
| yorimichi / `data.stage` | E3 | split needed | data |
| yorimichi / `data.racing_assets` | E3 | adapter only | data |
| yorimichi / `characters.adventure` | E14.7 | split needed | source |
| yorimichi / `unreal.adventure` | E14.7 | split needed | native |
| yorimichi / `characters.cairo_adventure` | E14.1 | split needed | source |
| yorimichi / `unreal.cairo_adventure` | E14.1 | split needed | native |
| yorimichi / `characters.modori_adventure` | E14.2 | split needed | source |
| yorimichi / `unreal.modori_adventure` | E14.2 | split needed | native |
| yorimichi / `characters.nox_adventure` | E14.3 | split needed | source |
| yorimichi / `unreal.nox_adventure` | E14.3 | split needed | native |
| yorimichi / `characters.paul_adventure` | E14.4 | split needed | source |
| yorimichi / `unreal.paul_adventure` | E14.4 | split needed | native |
| yorimichi / `characters.sword_trainer_adventure` | E14.5 | split needed | source |
| yorimichi / `unreal.sword_trainer_adventure` | E14.5 | split needed | native |
| yorimichi / `world.hippodrome` | E13.4 | split needed | source |
| yorimichi / `world.hippodrome.meshes` | E13.4 | adapter only | digest |
| yorimichi / `unreal.hippodrome` | E13.4 | split needed | native |
| yorimichi / `world.hidamari_stable` | E13.1 | split needed | source |
| yorimichi / `world.hidamari_stable_review` | E16.1 | move to QA | qa |
| yorimichi / `unreal.hidamari_stable` | E13.1 | split needed | native |
| yorimichi / `unreal.belmonte` | E11 | split needed | native |
| yorimichi / `unreal.belmonte_train` | E11.1 | split needed | native |
| yorimichi / `unreal.belmonte_track` | E11.1 | split needed | native |
| yorimichi / `world.belmonte.textures` | E1 | split needed | texture |
| yorimichi / `unreal.brinecove` | E6 | split needed | native |
| yorimichi / `world.brinecove.textures` | E1 | split needed | texture |
| yorimichi / `unreal.ferry` | E13.9 | split needed | native |
| yorimichi / `unreal.gondola` | E13.8 | split needed | native |
| yorimichi / `characters.cairo_fit` | E14.1 | adapter only | gate |
| yorimichi / `characters.modori_fit` | E14.2 | adapter only | gate |
| yorimichi / `characters.nox_fit` | E14.3 | adapter only | gate |
| yorimichi / `characters.paul_fit` | E14.4 | adapter only | gate |
| yorimichi / `characters.sword_trainer_fit` | E14.5 | adapter only | gate |
| yorimichi / `unreal.cairo_pawn` | E14.1 | adapter only | native |
| yorimichi / `unreal.modori_pawn` | E14.2 | adapter only | native |
| yorimichi / `unreal.nox_pawn` | E14.3 | adapter only | native |
| yorimichi / `unreal.paul_pawn` | E14.4 | adapter only | native |
| yorimichi / `data.content` | E3 | adapter only | data |
| yorimichi / `data.network` | E3 | adapter only | data |
| yorimichi / `unreal.cook` | F1 / F3a / F3b / F3 / F4 | split needed | cook |
| yorimichi / `unreal.package` | P2 / P3 | split needed | package |
| sandbox / `world.block` | E19 | already atomic | source |
| sandbox / `world.placements` | E19 | already atomic | source |
| sandbox / `unreal.compile` | E19 / P1 | adapter only | compile |
| sandbox / `unreal.level` | E19 / D6 / D8 | split needed | native |
| sandbox / `spatial.source.east` | E19 | already atomic | source |
| sandbox / `spatial.source.far` | E19 | already atomic | source |
| sandbox / `spatial.source.west` | E19 | already atomic | source |
| sandbox / `spatial.tile.west` | E19 | already atomic | source |
| sandbox / `spatial.tile.east` | E19 | already atomic | source |
| sandbox / `spatial.demo` | E19 | adapter only | target |
| sandbox / `unreal.cook` | E19 / F1 / F3 | split needed | cook |
