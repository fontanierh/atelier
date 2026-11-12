# Inventory

**Migration complete by owner decision, 2026-11-10. Final handoff: main `1abaab9d70` (#831). Further splitting is on demand; the remaining list below is an authoring backlog.**
This is the status index for the original-game port and subsequent authoring work.
The current Development package is `1a45eac4a6ee`, reported from `75bc99b55a`; it includes the final handoff
and performance/visual work through #851. Later merged #853/#854/#856 are not included in this package.
Automated checks and host/leave pass, but packaged Zeppelin performance
remains below 60 FPS and manual/human/two-machine acceptance is still open. Existing old extraction-root
ledgers do not apply to this fingerprint; see the [current package checkpoint](PACKAGE.md#current-development-package-checkpoint-2026-11-11).
The source baseline `7eec0f98dd` is documented separately in [features](inventory/features.md) and
[world](inventory/world.md); those pages describe the donor, not today's V2 completion state.

## Post-handoff development checkpoint

At main `a3b145ff2b` (2026-11-12), follow-ups through #856 are merged. The package checkpoint remains
`75bc99b55a` (2026-11-11); later source/content changes are listed separately below.

| Change | Source/content delivered | Verification limit |
| --- | --- | --- |
| [#836](https://github.com/fontanierh/atelier/pull/836) | Runtime tick, audio-probe, raycast and allocation changes | Compilation is recorded in the PR; this is not a measured whole-game frame-rate or memory improvement. |
| [#837](https://github.com/fontanierh/atelier/pull/837) | Forward-renderer configuration, aspect-matched 1440p viewport, tree LOD defaults, streaming and lazy map/JSON loading | The settings and code are merged; the combined runtime observation below does not isolate this PR's effect. |
| [#838](https://github.com/fontanierh/atelier/pull/838) | Foliage, treehouse, water and other material builders and saved imports; duplicate capture-CVar registration fixed | The import/check evidence is in the PR. Saved materials do not establish human visual acceptance. |
| [#840](https://github.com/fontanierh/atelier/pull/840) | Texture compression/mipmaps, multi-level mesh LODs and removal of unused render-mesh collision/CPU buffers | The PR records accepted editor saves and 130 generated/dependent imports. This work is merged, not still planned. |
| [#841](https://github.com/fontanierh/atelier/pull/841) | Sea/water HLSL string formatting and treehouse shader input names corrected after runtime fallback materials were found | Nine master/instance imports are recorded. Import acceptance alone does not prove every runtime shader or view correct. |
| [#842](https://github.com/fontanierh/atelier/pull/842) | Lower per-frame World Partition streaming budgets and registration batch sizes | Included in the passing runtime checkpoint below; its individual effect is not isolated. |
| [#844](https://github.com/fontanierh/atelier/pull/844) | Earlier non-Shipping loading-range override: 896 m Performance, 576 m Laptop; Quality restores the authored range | This is the configuration measured below. #848 subsequently changes the ranges and adds a Shipping code path; the earlier result does not verify those changes. |
| [#845](https://github.com/fontanierh/atelier/pull/845) | macOS game activity token and offscreen idle-setting adjustment | Merged and included below; earlier runs with this code still failed under the original caller context, so this PR alone is not a proven cure for the capture slowdown. |
| [#847](https://github.com/fontanierh/atelier/pull/847) | Four-level LOD settings and saved mesh updates for 170 standalone building, ship, stall and related asset records | The PR records content-check and focused-test acceptance. Saved LODs do not establish visual quality or a measured frame-rate improvement across towns. |
| [#848](https://github.com/fontanierh/atelier/pull/848) | Runtime spatial-bucket pooling of eligible static patch components, 2 ms async-loading budgets, and loading ranges of 1,344 m Performance / 640 m Laptop; Quality restores the authored range | Code and compilation are recorded. #850 removes its incompatible Shipping SpatialHash path; #851 supersedes its ranges. The earlier route receipt does not verify this pooling change. |
| [#850](https://github.com/fontanierh/atelier/pull/850) | Meadow anti-tiling, water glints, sky cumulus, surface AO and sky-fill changes; incompatible Shipping SpatialHash branch removed | The PR records 19 material imports and focused checks. The current package uses Development and its RuntimeHashSet route; Shipping behavior and human visual acceptance remain separate. |
| [#851](https://github.com/fontanierh/atelier/pull/851) | Restores authored 3 km Desktop Performance/Quality vistas after mountain/sea unstreaming was observed; Laptop uses 896 m and matching cloud cull | Included in the current package. The packaged north view is near 60 FPS; Zeppelin and route hitches remain limited as recorded in PACKAGE.md. |

Changes through #851 in the table above are included in the current package. The record census remains
7,662 asset records; the migration-handoff snapshots remain historical. Planned optimization is not counted as
delivered. Performance and visual work is owner-authorized normal development, not a reopening of the migration or whole-world splitting
campaign.
Use [measurement guidance](BUDGETS.md#recording-a-current-performance-run) for new evidence.

### Later merged changes, not yet in the package checkpoint

| Change | Source/content delivered | Verification limit |
| --- | --- | --- |
| [#853](https://github.com/fontanierh/atelier/pull/853), `7dd334391a` | Tree-material dither settings and saved imports; farther visible tree LOD defaults with capped shadow detail; racing clock, pose, ground-offset and save-cadence changes; review-camera aspect constraints and explicit viewport sizing; initial rider board scaling. | The PR records focused Python checks, 12 racing automation checks and content validation. These do not establish smooth transitions/racing, undistorted projection or whole-game frame-rate acceptance. Its capsule-based board scaling is superseded by #854. |
| [#854](https://github.com/fontanierh/atelier/pull/854), `bb803a4c9f` | Default rider board scale uses the Adventure `BodyScale` leg ratio relative to Cairo, with a capsule fallback; explicit non-default scales are retained. | Compilation and content checks are reported in the PR. The later receipt below records live deck scales; final appearance/gameplay acceptance remains separate, and the earlier package cannot validate this change. |
| [#856](https://github.com/fontanierh/atelier/pull/856), `a3b145ff2b` | Race fields rotate through playable jockey rigs with complete horse clips; repeated riders in larger fields use stable-colour outer garments. | The PR reports 12 racing automation checks. Saved runtime component/material receipts show varied rigs in five- and six-rider fields; this is not a new package or performance result. |

### Teaser handoff and corrected runtime evidence (2026-11-12)

Carbon-god handed off a replacement teaser in board #31684: `build/yorimichi_v2/yorimichi_v2_teaser.mp4`
in the producing checkout, 89.3 s, 1920×1080 at 30 fps, square pixels and 16:9 display aspect. This is a
video handoff, not confirmed owner acceptance or evidence that gameplay always runs at the video's frame rate.

Saved evidence is under `build/yorimichi_v2/teaser_v2_evidence/` in that checkout:

- `strict_realtime_fps_and_proofs.json` names source `bb803a4c9f` (#853/#854), records a projected
  200×200 cm square with equal 332.554 px sides, and live deck scales of Cairo 1.000, Paul 1.426,
  Nox 1.463 and Modori 1.468. These replace the earlier missing projection/scale observations; they do
  not independently accept every camera, rider pose or shot.
- `material_slots_and_fixed100_proof.json` cross-references forest/city material slots with editor-verified
  dither flags. It still records `all_tree_slots_verified_dithered_true: false`: four multi-LOD Caldera
  meshes have null flag verification, as do three single-LOD bamboo/lean-pine meshes. Do not describe this
  as complete tree-transition proof; visual smoothness remains a separate check.
- `varied_jockeys_runtime_proof.json` records the #856 jockey rigs and garment material assignments.
  The earlier FPS measurements below do not establish #856's performance.

The seven retained CSVs (`01_*.csv` through `07_*.csv`) support the corrected metrics below. All numeric
frame-time samples are retained. Average FPS is `1000 / mean(frame_ms)`; 1% low is `1000 / mean(slowest
ceil(frame_count × 0.01) frame times)`, not the reciprocal of the 99th-percentile frame time.

| Recorded route | Duration | Average / 1% low FPS | Worst frame | Frames >33.3 ms |
| --- | ---: | ---: | ---: | ---: |
| Coastal road bike (01) | 10.22 s | 59.57 / 37.00 | 72.63 ms | 1 |
| Treehouse bridge (02) | 8.17 s | 58.17 / 18.21 | 60.78 ms | 5 |
| Hidamari race including spawn (03) | 10.16 s | 54.84 / 6.17 | 677.85 ms | 3 |
| Belmonte race (04) | 10.16 s | 58.87 / 21.51 | 73.65 ms | 3 |
| Sunset Pier skate (05) | 8.25 s | 55.67 / 13.56 | 101.61 ms | 16 |
| Volcano skate (06) | 12.16 s | 58.71 / 20.66 | 140.48 ms | 4 |
| Hidamari steady race, fixed 100% (07) | 10.16 s | 59.85 / 49.54 | 41.14 ms | 1 |

These are short Editor-game runs using the `slice` profile, `-RenderOffscreen -ForceRes` and 2560×1440
output. Runs 01–06 retained dynamic resolution after preferences were applied; they are not fixed native
1440p measurements. Run 07's receipt records dynamic resolution disabled after BeginPlay and median screen
percentage 100%. It measures a steady race and does not replace run 03's spawn stalls. Route names do not
prove successful traversal or landings. The handoff corrects the earlier metric/profile claims in #31679;
stalls, human visual/gameplay acceptance and actual two-machine acceptance remain open. No new package
checkpoint or whole-island sustained-60-FPS claim follows from these results.

### Historical runtime evidence

**Earlier runtime checkpoint, not a performance pass:** the clean source run `d204bb79e0` (`after-final`,
2026-11-11) reached gameplay in 68.48 s, recorded a 14.528 GiB aggregate peak under a 16 GiB guard, and ended
with `child_exited` and completed cleanup. Its route receipt reports `passed: false`: the minimum of 20 sampled
frames was 12.2 FPS, below the 20 FPS check. Walking/skating measurements and seven 2560×1440 capture poses
were saved, but this is not sustained 60 FPS, human visual acceptance or a packaged build.

The saved evidence is `build/yorimichi_v2/perf_compare/after-final/summary.json`, `route/report.json` and
`captures/capture.json` beneath that same run directory in the producing checkout. The earlier pre-change
attempt hit the aggregate guard at 16.56 GiB before gameplay; that aborted startup is not a complete matched
baseline or a measured percentage improvement. The lower observed peak was useful evidence despite the failed route.
These earlier receipts do not accept #842 or later changes retroactively.

**Later bounded route/capture pass:** the clean `65318620c4` Editor-game run `after-interactive-qos`
(2026-11-11) reached gameplay in 53.41 s under a 14 GiB guard. It recorded 11.476 GiB primary and
11.574 GiB aggregate peak memory, clean game/route/capture exits and completed cleanup. The route passed:
all 20 scored walking/skating frame-rate readings were 60.0 FPS, with 15.6 m walking and 27.7 m skating. Three 2560×1440
poses were captured: spawn houses, harbour pier and Brine Cove quay. The summary correctly labels fullscreen.

Evidence is `build/yorimichi_v2/perf_compare/after-interactive-qos/summary.json`, `route/report.json` and
`captures/capture.json` in the producing checkout. Its capture caller used launchd `ProcessType=Interactive`
while retaining normal Atelier admission and guards; earlier caller-context attempts failed. See the
[launch-context diagnostic](BUDGETS.md#check-the-launch-context-before-tuning-around-a-slow-capture).
This is a sampled route pass, not sustained whole-island 60 FPS or human visual acceptance. It is not a packaged
build, a two-machine check or a measured standalone-package memory forecast. The aborted pre-change attempt
still does not support a matched percentage-saving claim. The first performance/visual pass was handed off at
that revision. The second pass through #851 and its Development package are now delivered; their
[packaged measurements](PACKAGE.md#current-development-package-checkpoint-2026-11-11) remain separate from this earlier checkpoint.

## How to read status

- **Ported** means the implementation and its committed inputs are present in V2. It does not certify every
  gameplay interaction, appearance or source-recovery requirement.
- **Prepared** means sources/recipes or plans exist; it does not establish an accepted import.
- **Merged** means the change is on main. Saved working-branch content is not merged or packaged by implication.
- **Saved** means committed placements/packages have owner records and receipts. A record for a fused tile
  is not proof that every useful object inside it is independently editable.
- **Packaged** names the revision that was cooked. Unmerged follow-ups are not included in that package.
- **Verified** applies only to the specific check and revision cited. Final human gameplay, visual and
  multiplayer acceptance is still open; the owner plans to playtest with his brother.
  Human-editor and second-machine proofs remain separate from same-host automation and the migration closure.

## What is already delivered

| Scope | Saved content / package checkpoint | Evidence and limits |
| --- | --- | --- |
| Whole island | W00–W20 have committed coverage (29 world region scopes); W14 keeps its disabled baseline. The 18 object receipts contain 2,937 saved object definitions. | [Regions](../world/regions/), `actors.verified.json`, `objects.saved.json`; these counts are not the number of independently split source models. |
| Recovered models | Merged:<br>- 1,048 city records;<br>- 67 train mesh records, plus 159 train texture and material records (459 packages);<br>- ten families with 141 meshes and 29 textures;<br>- 100 Japan props;<br>- 72 Brine Cove plants and city tree residuals;<br>- the two Japan leaf instances.<br>The first small-families batch (21 records, 48 packages) is merged (#797). | [PR #784](https://github.com/fontanierh/atelier/pull/784), [PR #786](https://github.com/fontanierh/atelier/pull/786), [PR #792](https://github.com/fontanierh/atelier/pull/792), [PR #794](https://github.com/fontanierh/atelier/pull/794), [PR #796](https://github.com/fontanierh/atelier/pull/796); the read-back results are below. Source completeness and remaining fused objects are tracked below. |
| Restricted and Adventure originals | 6,768 restricted package entries and 124 Adventure/animation entries have source routes; the manifest records 6,086 original pins. | [restricted.originals.json](../restricted.originals.json), [PR #785](https://github.com/fontanierh/atelier/pull/785). Private bytes stay on the pinned restricted route. These are source links, not gameplay acceptance. |
| Brine Cove individual objects | All 21 market stalls, all 265 town objects, the two harbour Soft fragments, eleven small props and three ship objects have saved placements in main ([PR #787](https://github.com/fontanierh/atelier/pull/787)). The signal mast and the shipyard slip are saved, merged and packaged ([PR #798](https://github.com/fontanierh/atelier/pull/798), [PR #800](https://github.com/fontanierh/atelier/pull/800)). The 13 harbour rowboats, buoys and potted palms (`props1`) are merged ([PR #813](https://github.com/fontanierh/atelier/pull/813)); the 6 quay cargo clusters and 7 fish baskets (`props2`, [PR #815](https://github.com/fontanierh/atelier/pull/815)) are merged; the 32 lantern posts (`props3`, [PR #816](https://github.com/fontanierh/atelier/pull/816)) are merged; the 3 harbour piers and 12 quay palms (`harbor1`, [PR #817](https://github.com/fontanierh/atelier/pull/817)) are merged; the 45 loose barrels and crates (`props4`, [PR #818](https://github.com/fontanierh/atelier/pull/818)) are merged; the re-split of the six quay cargo clusters and the pier cargo into 54 pieces (`props5`, #823) is merged; the 3 fish-shed rope coils and 18 gulls (`props6`, #830) are merged; and the 8 shipyard crates and 8 open-water rowboats (`harbor2`, #831) are merged. Other scenery still includes fused models/patches. | [Brine Cove scope](inventory/brinecove-objects.md), [split work](inventory/brinecove-split.md), [remaining exceptions](inventory/exceptions.md). |
| Transport objects | The 10 gondola pylons and 12 railway fittings are saved as their own objects; their fused groups and the train LOD records are retired. | [PR #790](https://github.com/fontanierh/atelier/pull/790), [exceptions](inventory/exceptions.md). |
| Current Development package | Reported source `75bc99b55a`, fingerprint `1a45eac4a6ee`: automated checks 8/8 reported; saved host/leave 9/9; packaged north/route/Zeppelin CSVs available. | [Current package evidence](PACKAGE.md#current-development-package-checkpoint-2026-11-11). Zeppelin averages 50.70 FPS (39.68 1% low); route max frame 671.771 ms. Dynamic resolution, manual acceptance and two-machine limits remain explicit. |
| Historical desktop package | Main `da0a41f891`, fingerprint `c89f535441be`: guarded package in 255.7 s; automated acceptance 8/8; host/leave 9/9; first launch (Slice in 15.9 s, peak 7.8 GiB, no error lines) and shutdown recorded passing. | [Package guide](PACKAGE.md#current-main-checkpoint-2026-11-10). Log-only launch evidence; human input, travel, gameplay, sound and persistence remain unrecorded. Host/leave covers one process, not a second machine joining. |
| Earlier integration package (#803, #804) | Built 2026-11-10 13:03 Paris from branch `7f43b4ccf3`, fingerprint `88d415e733ec`; automated checks, first launch and shutdown passed. | [Historical package evidence](PACKAGE.md#integration-package-for-803-and-804-2026-11-10). It predates #808/#809 and cannot host; later success does not upgrade this older app. |
| Appearance | Whole-island captures exist, as well as the earlier slice route/package measurements. | [PARITY](PARITY.md) retains their exact revisions and limits; those earlier captures do not accept every later split. |

## Merged content and package coverage

Saved, prepared and packaged totals are kept separate:
- **Earlier saved content retained:** package `c89f535441be` includes the small-families batch (#797), the Brine Cove
  signal mast and shipyard slip (#798, #800), and these imports already present in `0adbb5ab212e` at `7719234597`:
  - The two used Japan leaf instances (MI_LeafAmber, MI_LeafCrimson) are material-instance records imported
    from their recipe ([PR #792](https://github.com/fontanierh/atelier/pull/792)). They read identical to the
    packaged ones.
  - 72 Brine Cove plants and city tree residuals are source records, imported and verified
    ([PR #794](https://github.com/fontanierh/atelier/pull/794)).
  - The residual Belmonte train batch has 138 texture and 21 material-instance records covering 459 packages
    ([PR #796](https://github.com/fontanierh/atelier/pull/796)). A read-only read-back matches the donor in
    parent, switches and effective values for all 321 instances, and in every setting for the 138 textures.
  - The first small-families batch (#797) has 21 records covering 48 packages:
    - 4 Hippodrome loose meshes;
    - 4 plaza textures and 3 tree house textures;
    - 10 material-instance records (37 instances).

    All 21 are imported under claim SMALLFAM. The read-back matches the editor reads of the original packages:
    - the 37 instances in parent, switches, overrides and effective values;
    - the 7 textures in every setting;
    - the 4 meshes in LODs, triangles, slots and trace.

    The donor meshes carried one convex hull, which the complex-as-simple recipe drops. That trace flag never
    uses a hull, so collision is unchanged.
- **Merged and packaged:** [PR #803](https://github.com/fontanierh/atelier/pull/803) (`b684978143`)
  contains 36 generated material masters with pinned builders: Hippodrome, skating, FX, racing, Sword Camp, Mega Park,
  Hidamari city and 13 Japan base masters. Their native receipts cover the comparisons recorded at each revision.
  Sword Camp's two masters and Hidamari city now pin the shared haze helper; their claimed refresh at `6c807a71f9`
  passed the rooted native comparison and saved read-back ([evidence](inventory/shared-haze-sources.md)). Those reports
  predate the later tiling, transform and Time fields and do not prove those settings equal. Source-only generator
  records retain all 30 Hidamari and 43 Mega Park pins.
- **Merged and packaged follow-up:** [PR #804](https://github.com/fontanierh/atelier/pull/804) (`da0a41f891`) adds
  13 Japan masters (49 total with #803); its base-materials adopted record retains only `MPC_Wind`. These batches
  supersede the old “19 masters still to start” list. They are in `c89f535441be`; their receipts do not upgrade
  older packages or constitute final visual acceptance.
- **Hippodrome residuals closed in #804:** four texture and four instance records were imported, the four dependent
  props re-imported, and six unused course instances retired after a reference check. Native before/after reads
  agree. The old adopted owner is retired; this batch is merged and included in `c89f535441be`.
- **Merged and included in the current package:** claim `JAPANMI` ([PR #812](https://github.com/fontanierh/atelier/pull/812)) closes the 45
  material instances: the 41 Japan instances, `MI_HD_flat`, `MI_TH_pane` and the two two-sided Mega Park seams become
  10 generated `material-instance` records (`tools/migrate/held_instances.py`), replacing their adopted owners. Each
  row agrees with a native editor read that now includes the base-property overrides (LOD blending, masking, two-sided),
  and each import read back equal to the read before it. See
  [exceptions](inventory/exceptions.md#current-source-classification). Brine Cove `props1` (13 harbour objects, claim
  `BCPROPS1`, [PR #813](https://github.com/fontanierh/atelier/pull/813)) is merged too. Package `c89f535441be` predates
  both; current package `1a45eac4a6ee` includes them.
- **Final source batches merged:** no whole-source item is left in the tracked recovery list (#826, #827 merged): `MPC_SeeThrough` (claim
  `SEETHRU`, the `parameter-collection` importer) and `RuntimeData` (claim `SKATERT`, the `skate-runtime` importer) are
  imported from their pinned generators; see
  [exceptions](inventory/exceptions.md#current-source-classification).

The final handoff also repairs stale material-slot overrides in eleven Brine Cove placements: market-3-3,
market-3-4, market-4-3, market-4-4, townlower-4-4, townupper-3-4, townupper-4-4 and harbor-2-3 through harbor-5-3.
PR #831 re-saved them from their current tiles and added `brinecove-remainder-slots-resaved`; the all-batch retired
check with donor evidence and the content check reported no problems. These saves are on main `1abaab9d70`,
and included in current package `1a45eac4a6ee`, unlike historical `c89f535441be`. They still need human visual acceptance.

After the migration (on demand, not acceptance gates):
- Split the remaining useful objects when someone needs to edit them (backlog below); an imported package with an
  unknown original stays marked as such in [sources](inventory/sources.md) and [exceptions](inventory/exceptions.md).
- The master follow-ups are integrated. The earlier #799/#801 preparation and
  [master recovery design](inventory/master-sources.md) explain their provenance; they are not another backlog.
- Current package `1a45eac4a6ee` includes the final handoff and later changes through #851. The guard fixes
  (#805/#807), multiplayer manifest (#809) and host/leave check (#810) are merged. Manual acceptance and
  owner-led gameplay/two-machine playtesting remain open; old package ledger entries do not transfer.
- **Migration complete by owner decision (2026-11-10, Paris).** The owner chose on-demand splitting: the V2 migration is
  complete with the work merged so far, and the earlier full-splitting targets are withdrawn. Useful objects still
  bundled in generated tiles or area patches are split **on demand**, when someone needs to edit them. The table below
  is that authoring backlog, not a migration acceptance gate. Before a geometry edit, the selected generated model gets
  an independent generator first (`independent-generator-before-model-edit`); recoverable originals and all completed
  content are preserved. Counts are constructor groups (one loop body or call each), a lower bound: a group may hold
  several useful props, sized when that batch is planned.

  | Area | Bundled useful objects | Groups | Work | Batch |
  |---|---|---:|---|---|
  | Brine Cove props | 3 fish-shed rope coils, 18 gulls | 21 | done (#830) | `props6` |
  | Brine Cove harbour | 8 shipyard crates, 8 open-water rowboats | 16 | done (#831) | `harbor2` |
  | Brine Cove lower town | walkways, waterfront bunting, fish crates, plant and sack pairs (likely 8 pieces) | 29 | cut, import, save | `townlower2` |
  | Brine Cove upper town | 3 terrace stairs, cistern, laundry line, 4 palms, bunting, pots, benches | 22 | cut, import, save | `townupper2` |
  | Brine Cove market | foreground stall, 34 parasols, 6 trees, 6 palms, 6 colonnade bays, 9 lantern strings, benches, bunting, carts, sacks | 114 | cut, import, save | `market4` |
  | Brine Cove market lanes | 59 small lane stalls; their goods are unsized (could add 100 to 300 pieces) | 59+ | size goods, cut, import, save | `market5a`, `market5b` |
  | Brine Cove landmarks | fort towers, keep, gatehouse, ramp, lighthouse cottage, tower and shed, rope bridge, shrine | about 12 | extend the split tool to `landmarks.py`, then cut, import, save | `landmarks1` |
  | Mega Park | 16 stream-cell units hold 33 hashed render meshes: ramps, rails and bowls in a cell are fused | unsized | identify features in the park generator before any cut | to size |
  | Treehouse (W06) | `TH_Dressing` (16 cells) and `TH_Structure` (5 cells) area patches still bundle treehouse dressing and structure | 21 patches, contents unsized | read the patch members, then promote or split | `treehouse1` |
  | Mega Park gate (W11) | `HD_NorthGate` area patches | 6 | promote or split | `megapark-gate` |
  | Hidamari harbour (W07) | `HD_PlazaShopSides` (57) and its corner piece (1) are still area instances; 2 `Pole`/`Pole_Lamp` rows look like duplicates of saved city rows | 58 (owner decision), 2 to check | look, then split | `hidamari-plaza` |
  | Villages, start, pier, south-west coast, Hidamari station | poles, lamps, lanterns, torii, signs, houses, shops and props are saved objects (audited against the donor rows); `HD_Wires` overhead cables are area infrastructure | 0 | none | none |
  | Brine Cove ships, Crater Park, hippodrome, Belmonte, Sword Camp, transport, forests | each ship, park piece, course unit, camp prop, terminal, pylon and fitting is already its own object; forests are terrain and plants | 0 | none | none |

  Sizes for planning an on-demand batch: a Brine Cove batch has taken 10 to 20 minutes native plus 20 to 40 minutes
  review and CI; batches in one region share its claims and run one after another. Lane-stall goods and other
  sub-pieces may add 1 to 2 batches; `landmarks1` needs a split-tool extension (3 to 4 hours); Mega Park needs its
  features identified in the park generator before any estimate.

## Runtime and ownership facts

- The donor built most scenery at runtime. V2's `/Game/V2/Maps/Slice` now covers the island through saved
  World Partition scenery and stable ownership records. The map name and `slice` profile are historical names,
  not a coastal-only content limit. Dynamic services remain; `JapanWorld` consults the saved manifest instead
  of duplicating covered scenery. Fused scenery is split when a selected edit needs a finer boundary.
- The kart component, phone profile and phone streaming are removed from the V2 runtime. Four character
  Blueprints were cleaned after the serialized component change. Exclusions are listed below.
- V2 has its own project/build identity and `com.atelier.yorimichiv2` package identity. ElectraPlayer remains
  because the optional music library uses it. See [PACKAGE](PACKAGE.md) for current fetch/play commands.
- Mega Park rights were cleared by the owner on 2026-11-08; it is included. Restricted originals, including
  restricted sound sources, keep their pinned private route rather than being copied into public Git.

## Gameplay and shared systems

| ID | Coverage | Area | Donor baseline | Depends on | Current V2 implementation / remaining proof |
| --- | --- | --- | --- | --- | --- |
| F01 | Cairo, Modori, Nox, Paul: rigs, textures, clothes, equipment | Player and characters | implemented | — | Ported: [Player](../unreal/Source/Yorimichi/Player/) and character packages; four character Blueprints cleaned of the excluded kart component. Human appearance/animation checks remain. |
| F02 | Walk, run, sprint, jumps, crouch, climb, swim, glide, wave, interact | Player and characters | implemented | F01 | Ported: [Player](../unreal/Source/Yorimichi/Player/). Earlier walk/skate route evidence is in [PARITY](PARITY.md); full movement playtest remains. |
| F03 | Chase camera, see-through, first-person seats, collisions | Presentation | implemented | F02 | Ported: Player, Presentation and seat camera code. Human camera/occlusion checks remain. |
| F04 | Sword combat | Combat | implemented | F01, F02 | Ported: [Combat](../unreal/Source/Yorimichi/Combat/). Gameplay playtest remains. |
| F05 | Fox hunter, Kaede's trainer, Ronin camp | Combat | implemented (offline only) | F04, W01, W13 | Ported: FoxHunter and SwordTrainer spawn from JapanGameMode; camp scenery saved in W13. Keep the baseline offline-only limitations. |
| F06 | Flick-It skating | Skating | implemented | F01, Skate plugin | Ported: [Skating](../unreal/Source/Yorimichi/Skating/), shared Skate plugin and clips. Earlier route evidence is limited to its recorded revision. |
| F07 | Board carry/stow, markers, ride record/replay | Skating | partial: no player UI for replay | F06 | Ported baseline behavior: board/markers/replay code. A new player replay UI is outside this port. |
| F08 | Bike | Travel | implemented | F01, W00 | Ported: [BikeComponent](../unreal/Source/Yorimichi/Travel/BikeComponent.cpp) and recovered bike inputs. Ride playtest remains. |
| F09 | Sailboat | Travel | implemented | F01, W00 | Ported: [SailboatComponent](../unreal/Source/Yorimichi/Travel/SailboatComponent.cpp) and recovered boat inputs. Sailing playtest remains. |
| F10 | Horse: six breeds, tack, appearance | Travel | implemented | F01 | Ported: [HorseComponent](../unreal/Source/Yorimichi/Travel/HorseComponent.cpp), roster and restricted originals route. Breed/tack playtest remains. |
| F11 | Zeppelin: **four** stations (Woodland, Hidamari, Mega Park, Belmonte) | Travel | implemented | W19 | Ported: [ZeppelinService](../unreal/Source/Yorimichi/Travel/ZeppelinService.cpp), four stations and saved station scenery. Ride playtest remains. |
| F12 | Belmonte train, stations, interior, seats | Travel | implemented | W16, W20 | Ported: [BelmonteTrainService](../unreal/Source/Yorimichi/Travel/BelmonteTrainService.cpp), 67 recovered train records, saved W20 stations/track. Boarding/seats playtest remains. |
| F13 | Ferry | Travel | implemented | W17 | Ported: [FerryService](../unreal/Source/Yorimichi/Travel/FerryService.cpp); terminals saved in W17. Ride playtest remains. |
| F14 | Gondola | Travel | implemented | W18 | Ported: [GondolaService](../unreal/Source/Yorimichi/Travel/GondolaService.cpp); fixed stations and the ten per-tower pylon objects saved in W18 ([PR #790](https://github.com/fontanierh/atelier/pull/790), [transport-objects](inventory/transport-objects.md)). Ride playtest remains. |
| F15 | Horse racing, calendar, broadcasts, saves | Racing | implemented | F10, W15, W16 | Ported: [Racing](../unreal/Source/Yorimichi/Racing/) and [HorseRacing](../unreal/Plugins/HorseRacing/). Race/save playtest remains; proposed betting/stables are not added. |
| F16 | Villagers and ambient actors | Player and characters | implemented: movement only, no interactions found | W02, W07 | Ported: [VillageLife](../unreal/Source/Yorimichi/World/VillageLife.cpp). Baseline movement retained; new villager interactions are not claimed. |
| F17 | Desktop menus, English text, hints, settings | Presentation | implemented: the phone profile must be removed | — | Ported: [Presentation](../unreal/Source/Yorimichi/Presentation/); phone profile removed. Human menu/settings checks remain. |
| F18 | Painted world map, travel points | Presentation | implemented | W00–W20 | Ported: [JapanMap](../unreal/Source/Yorimichi/Presentation/JapanMap.cpp), atlas and runtime map data. Human travel/map checks remain. |
| F19 | Footsteps, combat and vehicle sounds | Presentation | partial: no train or sailboat sounds found | D05 restricted audio | Ported sound code and restricted audio packages/original links. Listening checks remain; baseline train/sailboat sound gaps are not claimed fixed. |
| F20 | Zone music director, optional library | Presentation | implemented | external music release | Ported: [JapanMusic](../unreal/Source/Yorimichi/Presentation/JapanMusic.cpp) and optional pinned music fetch/launcher route. See [PACKAGE](PACKAGE.md). |
| F21 | Painterly materials, sky, sea, foliage, effects | World | implemented | W00 | Ported: saved environment/scenery and dynamic effects. Whole-island comparison evidence is in [PARITY](PARITY.md); it is not final visual acceptance. |
| F22 | Multiplayer | Network | partial: local two-process tests only | F02–F14 | Packaged host → leave → Solo passes on `c89f535441be` with #809/#810. This is one process; cross-machine gameplay acceptance remains with the owner and his brother. |
| F23 | Live bridge, QA, dev tools | Presentation/Dev | implemented: single port 8830 | P2-C | Ported: [Dev](../unreal/Source/Yorimichi/Dev/) and session-targeted LiveBridge. Native packaged build has no Python input route; see [PACKAGE](PACKAGE.md). |
| F24 | Runtime data, saves, startup, packaging | World/Presentation | implemented | — | Packaged checkpoint `c89f535441be` (main `da0a41f891`); V2 identity, staged runtime files, launch and shutdown checked. Human save/persistence checks remain. |
| F25 | Crater Park tower hoist | Travel | implemented | W12 | Ported: [CraterParkTower](../unreal/Source/Yorimichi/Travel/CraterParkTower.cpp). Hoist playtest remains. |
| F26 | Mega Park standalone level and game mode | World | implemented | W11 | Ported: [standalone profile](../game.toml) and Mega Park map/game mode. Rights cleared; standalone playtest remains. |
| F27 | In-game Dev mode and notes | Presentation/Dev | implemented | F17 | Ported: [DevNotes](../unreal/Source/Yorimichi/Dev/DevNotes.cpp). Human notes/export checks remain. |
| F28 | Friends sessions over Tailscale | Network | implemented | F22 | Ported: [JapanSession](../unreal/Source/Yorimichi/Network/JapanSession.cpp) and Tailscale adapter. Live two-person acceptance remains with F22. |
| F29 | Hair spring, cloth, seat correctives | Player and characters | implemented | F01 | Ported character presentation code and linked rig/animation inputs. Human hair/cloth/seat checks remain. |
| F30 | Train departure boards | Travel | implemented | F12 | Ported: [BelmonteTrainBoards](../unreal/Source/Yorimichi/Travel/BelmonteTrainBoards.cpp). In-game board readability/schedule checks remain. |
| F31 | Kei cars as static car-park dressing (not driving) | World | implemented | W11 | Ported static Mega Park dressing; rights cleared. These cars are scenery, distinct from excluded go-kart driving. |
| F32 | Trailer, benchmark and building-review modes | Presentation/Dev | implemented | F23 | Ported [Dev](../unreal/Source/Yorimichi/Dev/) modes. Available tools do not imply every diagnostic mode has been exercised on this package. |

Only proposals exist for the canteen lady, the tide-reader and player betting or stables. They are not
migration requirements. Baseline partial behavior is not silently counted as a new V2 feature.

## Every world region and connection

All rows below have current V2 coverage; gameplay and appearance still need the final human playtest. Saved
terrain/scatter patches are valid area owners. A patch that bundles several useful objects still needs splitting.
W10 shares W06's region scope; W19's stations belong to their host regions, so there are no separate W10/W19 folders.

| ID | Area | Current saved coverage / remaining work |
| --- | --- | --- |
| W00 | Island foundation: terrain, coast, sea, background, roads | Saved [island environment](../world/regions/w00-island/) and region scenery; source recovery merged. |
| W01 | Start, coastal road, houses | Saved [start](../world/regions/w01-start/) scenery and object placements; earlier route proof in PARITY. |
| W02 | Momiji Hamlet village | Saved [village](../world/regions/w02-village/) scenery/objects; ambient life remains dynamic. |
| W03 | Mini Mega ramp | Saved [mini ramp](../world/regions/w03-mega/); family source recovery merged. |
| W04 | Sunset Pier skate plaza | Saved [pier approach](../world/regions/w04-pier-approach/) and skate-park content; family source recovery merged. |
| W05 | Forest | Saved across five `w05-forest-*` scopes in [regions](../world/regions/); scatter stays grouped for rendering/editing. |
| W06 | Forest lake | Saved [lake/treehouse](../world/regions/w06-lake-treehouse/) scenery/objects. |
| W07 | Hidamari | Saved [harbour](../world/regions/w07-hidamari-harbour/) and [station](../world/regions/w07-hidamari-station/) scenery/objects; 1,048 city source records recovered. |
| W08 | Southwest | Saved across coast, terrace and isle-east scopes in [regions](../world/regions/); recovered models in main. |
| W09 | Brine Cove | Saved [region](../world/regions/w09-brinecove/): small props, ships, the 21 market stalls and the 265 town objects (#787), with the fused originals preserved and the emptied tiles retired. The signal mast and the shipyard slip are saved, merged and packaged ([PR #798](https://github.com/fontanierh/atelier/pull/798)). |
| W10 | Tree house | Saved under [W06](../world/regions/w06-lake-treehouse/); recovered models in main. |
| W11 | Super Ultra Mega Park and its own map | Saved [island region](../world/regions/w11-megapark/) and standalone map/profile; rights cleared. |
| W12 | Volcano and Crater Park | Saved [Crater Park](../world/regions/w12-craterpark/) plus three volcano scopes; restricted original routes linked. |
| W13 | Sword camp | Saved [camp](../world/regions/w13-swordcamp/) props; trainers/squad stay dynamic. Clearing verification remains recorded in [D10](DECISIONS.md). |
| W14 | Hidamari stable | [Site](../world/regions/w14-hidamari-stable/) retained; stable remains disabled as in the donor (`bEnabled = false`, D06). |
| W15 | Hippodrome | Saved [hippodrome](../world/regions/w15-hippodrome/) scenery/objects; racing service stays dynamic. |
| W16 | Belmonte | Saved [town/estates/courses](../world/regions/w16-belmonte/) and object placements; broader useful-object/source exceptions still tracked. |
| W17 | Ferry route | Saved [terminals](../world/regions/w17-ferry/); ships remain dynamic. |
| W18 | Gondola route | Saved [stations](../world/regions/w18-gondola/) and the ten per-tower pylon objects ([PR #790](https://github.com/fontanierh/atelier/pull/790)); cabins/ropes remain dynamic. |
| W19 | Zeppelin route (four stations) | Saved station scenery in Woodland/W06, Hidamari/W07, Mega Park/W11 and Belmonte/W16; moving service remains dynamic. |
| W20 | Railway and cross-region routes | Saved [railway](../world/regions/w20-railway/); 67 train source records recovered, moving train retained. |

## Explicit exclusions

| ID | Deferred by owner | V2 action | Status |
| --- | --- | --- | --- |
| X01 | Phone streaming, Pixel Streaming, touch controls | Not ported. Plugins disabled in `YorimichiV2.uproject`; `YorimichiPhone`, the stream hooks in `WandererCharacter`, `JapanHUD`, `JapanGameMode` and the phone profile in `JapanPreferences` are removed from the V2 copy | deferred by owner |
| X02 | Go-kart driving | Not ported. `Driving` disabled; `CarRide`, `JapanKartGrip`, kart HUD, animation and live hooks, and `/Game/Japan/Kart` stay out of V2 | deferred by owner |
| X03 | Browser and mobile ports, Hakuba rendering experiments | Not implemented | deferred by owner |
| X04 | New gameplay, engine upgrade, new art direction | Outside the migration scope; owner-authorized performance and visual follow-ups are tracked above | separate development |

## Keeping the status current

A content or behavior PR updates this index and its affected README, workflow notes, TODOs and comments in the
same change. Record the revision and distinguish prepared, imported, saved, merged, packaged and human-verified
work. Never promote a provisional receipt or an ownership map to accepted content. When a follow-up lands,
replace its pending row with the merged evidence rather than leaving contradictory status in another page.

The baseline inventories, dated measurements and decision history remain evidence of their named revisions;
their historical findings are not current blockers unless repeated here or in the current exceptions list.
Files under `assets/adopted/**/source/**` are pinned donor inputs, including embedded README/TODO/comments.
Preserve their bytes and provenance; current V2 instructions live in this documentation, not in rewritten originals.
