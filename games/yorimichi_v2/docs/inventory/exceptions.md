# Remaining exceptions to independent editing and recoverable sources

Snapshot: **main `3027366ced` (2026-11-09)**. See [INVENTORY](../INVENTORY.md) for the overall port status.
The earlier "320 remaining records" total came from a preparation branch before source recovery and object saves;
it is retired. Counts of records, packages, cells and useful objects are not interchangeable.

A useful object needs an editing boundary of its own and a recoverable original. Rendering can remain batched.
For imported content, an editor-saved package is not a substitute for the imported model and its relevant inputs.

## Closed or superseded groups

| Earlier group | Current evidence |
|---|---|
| G1: restricted originals missing | Closed for the manifest's 6,768 restricted package entries: original routes and pins are merged in PRs #782/#783. Private storage remains the required route |
| G2: 124 Adventure/animation originals missing | Closed by PR #785: 124 `open_packages` entries, with no `open_problems` on main |
| G4c: broad Japan model records | The 100-model Japan recovery is merged in PR #786; do not reuse the old 16-record / 52-package model backlog |
| G5: shared map packages | A map is a legitimate editing scope. Region actors and map-level edits have different ownership; sharing one map does not make every region unfinished |

## Remaining useful-object work

| Area | Landed | Still open |
|---|---|---|
| Brine Cove small props | Eleven placements saved, including the corrected crane/fish-shed split, and the two harbour Soft fragments (#787) | Finish any remaining useful fused objects (signal mast, shipyard slip); preserve each whole palm |
| Brine Cove ships | Nightjar, sloop and Adventure hull placements saved with per-instance hull groups | Retire the three emptied ship tiles and obsolete grouped placements after accepted replacement checks |
| Brine Cove market | All 21 stalls saved on main (market1–3, #786 and #787) | None for the stalls themselves |
| Brine Cove town | All 265 town objects saved on main (#787); the 42 emptied tiles and the three ship tiles are retired | None for the town objects |
| Other Brine Cove features | Existing fort, lighthouse and other saved units remain | The signal mast, stone shipyard slip and other useful objects still bundled in residual tiles need a real object boundary, not just a smaller package |
| Transport groups | Two ferry terminals, nine gondola route objects, thirteen railway route objects, the ten gondola pylons and the twelve railway fittings saved | Pylon groups and the track-fittings group are retired (`gondola_pylons.py`, `railway_fittings.py`; fittings routed by row, `SM_TK_<mesh>#@<i>`). Preserve route data and moving services while splitting their editing boundaries |
| Area patches (G6) | Saved terrain, ground and scatter patches are legitimate scopes | A patch-name tally is only a candidate list. Any patch that still bundles several useful buildings or props remains unfinished until they are independently editable |

The counts above describe saved definitions and known plans, not a full new geometry audit. Use actual object
membership, not a name pattern, to decide whether a remaining patch is complete. Do not make useful-object splitting
optional simply because a patch is legal to save.

## Source closure still to classify

At this revision 51 open adopted records have no direct `[[sources]]` and no recipe. Three of them are the already
linked Adventure/animation records. The other **48 records / 676 packages** comprise:

| Family | Records | Packages |
|---|---:|---:|
| Residual Belmonte train packages | 7 | 459 |
| Japan materials (41 prepared in seven adopted records; 2 used leaves are recipe records: see below) | 7 | 41 |
| Brine Cove plants | 9 | 36 |
| City tree residual packages | 1 | 36 |
| Mega Park materials and standalone map | 4 | 25 |
| Hippodrome | 3 | 23 |
| Tree house surface materials | 5 | 8 |
| Skatepark board/materials | 2 | 8 |
| Belmonte shared materials | 2 | 7 |
| FX residual packages | 1 | 7 |
| Japan plaza/harbour textures | 1 | 4 |
| Bike residual packages | 1 | 2 |
| Sword camp materials | 1 | 2 |
| Hidamari surface, racing, see-through and skate runtime | 4 | 4 |

This query is a **classification list**, not a claim that every package lacks an original. Follow references and
verify origin: procedural materials may need generator inputs; genuinely Unreal-authored maps/settings may use
saved packages; imported files need their original bytes. Do not relabel unknown imports as editor originals.

### Residual Belmonte train records (seven, 459 packages): donor evidence

The records `adopted/belmontetrain/{baggage-van,brake-van,first-class,locomotive,restaurant,second-class,tender}` hold
71, 76, 71, 49, 73, 82 and 37 packages (459, after the 14 unused LOD meshes were retired). None has `[[sources]]` or a recipe, and **none is closed**. The donor
build output (Train Builder GLBs, `service/import-report.json`, texture PNG/JPG outputs) was read in place, read-only,
and is not committed. `recover.py belmontetrain --donor <belmonte-train folder>` plans **0 generated records**: its
`plan_belmontetrain` covers only the root vehicle packages (already generated) and door leaves (none in these seven
records), so none of the 459 packages has a planner row. Plan mode writes nothing.

| Kind | Packages | Donor evidence (checked) | Verdict |
|---|---:|---|---|
| `Source/SM_BT_<V>/SM_BT_<V>_LOD1` and `_LOD2` meshes | 14 | Each level GLB is pinned by the donor's `import-report.json` sha256 (14 of 14). The donor counts triangles per node placement: a mesh placed by several nodes counts once per placement. Counted that way, all 14 levels match the committed root chain's triangles and material names (sets). The earlier six-LOD1 disagreement was this instancing, not door leaves (refuted: tender has no doors and is short by 1,160 = 2 × 580) | **Retired** (`belmontetrain_lods.py`, on this branch). These were unused donor leftovers. The vehicle records `assets/prop/belmontetrain/<v>/` pin the full LOD chain from the GLB sources, and `unreal/Scripts/import_asset.py` imports LOD1 and LOD2 as transient meshes, attaches them and deletes them. Nothing referenced the packages (`tools/migrate/belmontetrain_lods.py --check` proved it). The claimed `belmontetrain_lods.py --claim TASK` step removed them from the seven records, `verified.json` and `units.json`, and deleted the 14 `.uasset` files. `recover.py belmontetrain`'s `-lod1|lod2` rows must not be applied: they would recreate the records |
| `M_BT_*` material instances in `Source/SM_BT_<V>/LOD0..2` | 321 | Each GLB material slot (321 across all levels of all seven vehicles) binds by name to exactly one residual material package in the same LOD folder: 321 of 321 | **Prepared.** The binding closes by name, but the instance parameters and the source texture links still need an editor read, and no committed facts exist to compare them with |
| `T_BT_*` textures | 138 (27 names) | The donor has an image for all 138 packages. `T_BT_Walnut1` (10 packages, LOD0 and LOD1 of five vehicles) is not a separate image: in each of those ten GLBs two glTF textures share the one `T_BT_Walnut` image (sha256 `82a95ac294…`), and Interchange names the second texture `T_BT_Walnut1`. Its original is that image. No committed texture facts (size, format) are saved | **Prepared** for all 138 packages: the donor image is the candidate source, with `generator/source/world/train/textures.py` as its generator (`T_BT_Walnut1` from its `T_BT_Walnut` entry). Verifying needs an editor import compared with the committed packages, and accepted content is not re-imported |

Adding `[[sources]]` to these records would change their import fingerprints and make `check.py` report `STALE_IMPORT`,
so the records stay as they are until a verified import closes them. The count and the texture coverage are pinned by
`tests/test_belmontetrain_residual.py`. The LOD retirement has run (`belmontetrain_lods.py`, referencer proof clean):
the 14 standalone LOD1/LOD2 meshes and their packages are gone (473 to 459).

Next step, not run here: textures remain prepared,
for all 138 donor-backed ids, after the generator's own source record is pinned. The planned records and the
per-package table are in the next section.

### Residual Belmonte train: planned source records (459 packages, read and agreeing, not imported)

Planner: `tools/migrate/belmontetrain_materials.py`. Plan mode (the default) reads the donor and the committed bytes and
writes nothing; `--table` prints the table below; `--paths` lists the claim's paths and scopes. Nothing is claimed or
imported here.

**Planned records: 159, no source copy of any GLB.** 138 `texture` records, one per texture package, each pinning its
donor image by sha256 in `src/`. 21 `material-instance` records, one per unit and LOD, in the per-package `instances`
form: one `[[recipe.settings.instances]]` row per output, stating its parent, its `BaseColorTexture`, `BaseColorFactor`,
`RoughnessFactor`, `MetallicFactor` and, where the GLB has them, `ClearCoatFactor`, `EmissiveFactor` (with alpha) and
`EmissiveStrength`, and its `bHas*` switches. The texture records are its `input_dependencies`.

**Settled by the native reads (`docs/inventory/belmontetrain-read.json` holds the evidence; the test
`tests/test_belmontetrain_read.py` checks the plan against it):**

- Textures, 138: sRGB true, compression `TC_DEFAULT`, LOD group `TEXTUREGROUP_WORLD`, address `TA_WRAP` on both axes. The
  plan states exactly these.
- Materials, 321: the parent of every row, its base texture, its scalars and vectors (EmissiveFactor alpha included), and
  every `bHas*` switch whose effective value differs from its parent or that the row states. The plan disagreed with the
  read on the clear-coat rows (it stated `bHasAnisotropyTextureAndOrRotation`, which the clear-coat parent does not have,
  and `bHasSpecularColorTexture`, which neither parent has); both are removed. The read has no override the plan does not
  state; a value stated equal to its default (a white base colour, metallic 1) is redundant, not wrong.
- The parent of each row: `MI_Default_Opaque_DS` 240, `MI_ClearCoat_Opaque_DS` 46, `MI_Default_Blend_DS` 30, and
  `MI_Default_Opaque` 5 (single-sided window interiors).

**Remaining gaps (not settled):**

1. **The import has not run.** The importer writes each row's parent, textures, scalars, vectors and switches, and reads
   them back before the save. The read-back and the donor-path refusal are checked only by fake tests in Python; no
   editor has run them. The clear/verify logic of the leaf material importer (`_material_instances` overrides the recipe
   does not declare) is being fixed separately on PR #792 and is not part of this branch's changes.
2. **The texture import's donor-path scrub** (blank the recorded source, set the portable source, refuse an absolute name)
   has the same status: fake-tested helper, not run.
3. **The committed packages carry the donor's absolute path** in `AssetImportData` (459 of 459). The first verified import
   must clear it (the material and texture imports both do, by the code above).
4. **Owner decisions:** (a) the emptied adopted records are deleted, not kept, with their verified and `units.json` entries
   (as the LOD retirement did); (b) the 67 prop records reference every record of their unit, not only the ones their slots
   use, because `references` is not part of a fingerprint.
5. **`check.py`:** a generated record with no `verified.json` is fatal (`RECORD_MISSING`, plus `UNOWNED` on each of its
   package files; pinned by a fake-tree test). The claim must land with the import that writes those files.

Claim and scopes: the seven `shared/belmontetrain/<unit>` scopes; `--paths` lists 379 paths (138 texture `src/` copies, 159
record files, the seven adopted `asset.toml` and `verified.json` (14 deletes), `units.json`, and 67 prop records). The claimed
step is `belmontetrain_materials.py --claim TASK`, one journaled write, after the import is ready.

Reads (read-only `editor.run`, already run; kept for re-running):

- Textures: `unreal/Scripts/report_textures.py` on `docs/inventory/belmontetrain-texture-packages.txt` (138).
- Materials: `unreal/Scripts/report_materials.py` on `docs/inventory/belmontetrain-material-packages.txt` (321).

Per package (generated by `belmontetrain_materials.py --table`; every row's values are settled by the read above):

| Package | Planned record | Donor evidence | Committed bytes | Status and read job |
|---|---|---|---|---|
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/T_BT_Walnut` | `texture/belmontetrain/baggage-van-lod0-walnut` (texture) | T_BT_Walnut.png pinned, sha256 `82a95ac294…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/T_BT_Walnut1` | `texture/belmontetrain/baggage-van-lod0-walnut1` (texture) | T_BT_Walnut.png pinned, sha256 `82a95ac294…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/T_BT_PanelWide` | `texture/belmontetrain/baggage-van-lod0-panel-wide` (texture) | T_BT_PanelWide.png pinned, sha256 `cc31811be2…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/T_BT_PanelTall` | `texture/belmontetrain/baggage-van-lod0-panel-tall` (texture) | T_BT_PanelTall.png pinned, sha256 `9c1b7dd0b2…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/T_BT_Roof` | `texture/belmontetrain/baggage-van-lod0-roof` (texture) | T_BT_Roof.jpg pinned, sha256 `0269313a90…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/T_BT_Underframe` | `texture/belmontetrain/baggage-van-lod0-underframe` (texture) | T_BT_Underframe.jpg pinned, sha256 `e16f7c563c…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/T_BT_Crest` | `texture/belmontetrain/baggage-van-lod0-crest` (texture) | T_BT_Crest.png pinned, sha256 `ed2d1c397b…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/T_BT_Ivory` | `texture/belmontetrain/baggage-van-lod0-ivory` (texture) | T_BT_Ivory.jpg pinned, sha256 `6d1d5c4364…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/T_BT_BluePanel` | `texture/belmontetrain/baggage-van-lod0-blue-panel` (texture) | T_BT_BluePanel.jpg pinned, sha256 `d0e139bb1b…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/T_BT_Walnut` | `texture/belmontetrain/baggage-van-lod1-walnut` (texture) | T_BT_Walnut.png pinned, sha256 `82a95ac294…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/T_BT_Walnut1` | `texture/belmontetrain/baggage-van-lod1-walnut1` (texture) | T_BT_Walnut.png pinned, sha256 `82a95ac294…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/T_BT_Roof` | `texture/belmontetrain/baggage-van-lod1-roof` (texture) | T_BT_Roof.jpg pinned, sha256 `0269313a90…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/T_BT_Underframe` | `texture/belmontetrain/baggage-van-lod1-underframe` (texture) | T_BT_Underframe.jpg pinned, sha256 `e16f7c563c…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/T_BT_Crest` | `texture/belmontetrain/baggage-van-lod1-crest` (texture) | T_BT_Crest.png pinned, sha256 `ed2d1c397b…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/T_BT_Ivory` | `texture/belmontetrain/baggage-van-lod1-ivory` (texture) | T_BT_Ivory.jpg pinned, sha256 `6d1d5c4364…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/T_BT_BluePanel` | `texture/belmontetrain/baggage-van-lod1-blue-panel` (texture) | T_BT_BluePanel.jpg pinned, sha256 `d0e139bb1b…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD2/T_BT_Underframe` | `texture/belmontetrain/baggage-van-lod2-underframe` (texture) | T_BT_Underframe.jpg pinned, sha256 `e16f7c563c…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD2/T_BT_Ivory` | `texture/belmontetrain/baggage-van-lod2-ivory` (texture) | T_BT_Ivory.jpg pinned, sha256 `6d1d5c4364…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD2/T_BT_BaggageVanInterior` | `texture/belmontetrain/baggage-van-lod2-baggage-van-interior` (texture) | T_BT_BaggageVanInterior.png pinned, sha256 `8e6f6e9810…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD2/T_BT_Roof` | `texture/belmontetrain/baggage-van-lod2-roof` (texture) | T_BT_Roof.jpg pinned, sha256 `0269313a90…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/T_BT_Walnut` | `texture/belmontetrain/brake-van-lod0-walnut` (texture) | T_BT_Walnut.png pinned, sha256 `82a95ac294…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/T_BT_Walnut1` | `texture/belmontetrain/brake-van-lod0-walnut1` (texture) | T_BT_Walnut.png pinned, sha256 `82a95ac294…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/T_BT_Tiles` | `texture/belmontetrain/brake-van-lod0-tiles` (texture) | T_BT_Tiles.png pinned, sha256 `929cdacfd4…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/T_BT_PanelWide` | `texture/belmontetrain/brake-van-lod0-panel-wide` (texture) | T_BT_PanelWide.png pinned, sha256 `cc31811be2…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/T_BT_PanelTall` | `texture/belmontetrain/brake-van-lod0-panel-tall` (texture) | T_BT_PanelTall.png pinned, sha256 `9c1b7dd0b2…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/T_BT_Ivory` | `texture/belmontetrain/brake-van-lod0-ivory` (texture) | T_BT_Ivory.jpg pinned, sha256 `6d1d5c4364…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/T_BT_Roof` | `texture/belmontetrain/brake-van-lod0-roof` (texture) | T_BT_Roof.jpg pinned, sha256 `0269313a90…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/T_BT_Underframe` | `texture/belmontetrain/brake-van-lod0-underframe` (texture) | T_BT_Underframe.jpg pinned, sha256 `e16f7c563c…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/T_BT_Crest` | `texture/belmontetrain/brake-van-lod0-crest` (texture) | T_BT_Crest.png pinned, sha256 `ed2d1c397b…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/T_BT_BluePanel` | `texture/belmontetrain/brake-van-lod0-blue-panel` (texture) | T_BT_BluePanel.jpg pinned, sha256 `d0e139bb1b…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/T_BT_Walnut` | `texture/belmontetrain/brake-van-lod1-walnut` (texture) | T_BT_Walnut.png pinned, sha256 `82a95ac294…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/T_BT_Tiles` | `texture/belmontetrain/brake-van-lod1-tiles` (texture) | T_BT_Tiles.png pinned, sha256 `929cdacfd4…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/T_BT_Walnut1` | `texture/belmontetrain/brake-van-lod1-walnut1` (texture) | T_BT_Walnut.png pinned, sha256 `82a95ac294…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/T_BT_Ivory` | `texture/belmontetrain/brake-van-lod1-ivory` (texture) | T_BT_Ivory.jpg pinned, sha256 `6d1d5c4364…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/T_BT_Roof` | `texture/belmontetrain/brake-van-lod1-roof` (texture) | T_BT_Roof.jpg pinned, sha256 `0269313a90…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/T_BT_Underframe` | `texture/belmontetrain/brake-van-lod1-underframe` (texture) | T_BT_Underframe.jpg pinned, sha256 `e16f7c563c…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/T_BT_Crest` | `texture/belmontetrain/brake-van-lod1-crest` (texture) | T_BT_Crest.png pinned, sha256 `ed2d1c397b…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/T_BT_BluePanel` | `texture/belmontetrain/brake-van-lod1-blue-panel` (texture) | T_BT_BluePanel.jpg pinned, sha256 `d0e139bb1b…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD2/T_BT_Underframe` | `texture/belmontetrain/brake-van-lod2-underframe` (texture) | T_BT_Underframe.jpg pinned, sha256 `e16f7c563c…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD2/T_BT_Ivory` | `texture/belmontetrain/brake-van-lod2-ivory` (texture) | T_BT_Ivory.jpg pinned, sha256 `6d1d5c4364…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD2/T_BT_BrakeVanInterior` | `texture/belmontetrain/brake-van-lod2-brake-van-interior` (texture) | T_BT_BrakeVanInterior.png pinned, sha256 `3eeb003ecb…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD2/T_BT_Roof` | `texture/belmontetrain/brake-van-lod2-roof` (texture) | T_BT_Roof.jpg pinned, sha256 `0269313a90…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/T_BT_Walnut` | `texture/belmontetrain/first-class-lod0-walnut` (texture) | T_BT_Walnut.png pinned, sha256 `82a95ac294…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/T_BT_Tiles` | `texture/belmontetrain/first-class-lod0-tiles` (texture) | T_BT_Tiles.png pinned, sha256 `929cdacfd4…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/T_BT_CarpetEmerald` | `texture/belmontetrain/first-class-lod0-carpet-emerald` (texture) | T_BT_CarpetEmerald.png pinned, sha256 `69cb063ec5…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/T_BT_Walnut1` | `texture/belmontetrain/first-class-lod0-walnut1` (texture) | T_BT_Walnut.png pinned, sha256 `82a95ac294…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/T_BT_PanelWide` | `texture/belmontetrain/first-class-lod0-panel-wide` (texture) | T_BT_PanelWide.png pinned, sha256 `cc31811be2…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/T_BT_PanelTall` | `texture/belmontetrain/first-class-lod0-panel-tall` (texture) | T_BT_PanelTall.png pinned, sha256 `9c1b7dd0b2…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/T_BT_Roof` | `texture/belmontetrain/first-class-lod0-roof` (texture) | T_BT_Roof.jpg pinned, sha256 `0269313a90…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/T_BT_Underframe` | `texture/belmontetrain/first-class-lod0-underframe` (texture) | T_BT_Underframe.jpg pinned, sha256 `e16f7c563c…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/T_BT_Crest` | `texture/belmontetrain/first-class-lod0-crest` (texture) | T_BT_Crest.png pinned, sha256 `ed2d1c397b…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/T_BT_Ivory` | `texture/belmontetrain/first-class-lod0-ivory` (texture) | T_BT_Ivory.jpg pinned, sha256 `6d1d5c4364…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/T_BT_BluePanel` | `texture/belmontetrain/first-class-lod0-blue-panel` (texture) | T_BT_BluePanel.jpg pinned, sha256 `d0e139bb1b…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/T_BT_Tiles` | `texture/belmontetrain/first-class-lod1-tiles` (texture) | T_BT_Tiles.png pinned, sha256 `929cdacfd4…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/T_BT_CarpetEmerald` | `texture/belmontetrain/first-class-lod1-carpet-emerald` (texture) | T_BT_CarpetEmerald.png pinned, sha256 `69cb063ec5…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/T_BT_Walnut` | `texture/belmontetrain/first-class-lod1-walnut` (texture) | T_BT_Walnut.png pinned, sha256 `82a95ac294…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/T_BT_Walnut1` | `texture/belmontetrain/first-class-lod1-walnut1` (texture) | T_BT_Walnut.png pinned, sha256 `82a95ac294…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/T_BT_Roof` | `texture/belmontetrain/first-class-lod1-roof` (texture) | T_BT_Roof.jpg pinned, sha256 `0269313a90…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/T_BT_Underframe` | `texture/belmontetrain/first-class-lod1-underframe` (texture) | T_BT_Underframe.jpg pinned, sha256 `e16f7c563c…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/T_BT_Crest` | `texture/belmontetrain/first-class-lod1-crest` (texture) | T_BT_Crest.png pinned, sha256 `ed2d1c397b…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/T_BT_Ivory` | `texture/belmontetrain/first-class-lod1-ivory` (texture) | T_BT_Ivory.jpg pinned, sha256 `6d1d5c4364…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/T_BT_BluePanel` | `texture/belmontetrain/first-class-lod1-blue-panel` (texture) | T_BT_BluePanel.jpg pinned, sha256 `d0e139bb1b…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD2/T_BT_Underframe` | `texture/belmontetrain/first-class-lod2-underframe` (texture) | T_BT_Underframe.jpg pinned, sha256 `e16f7c563c…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD2/T_BT_Ivory` | `texture/belmontetrain/first-class-lod2-ivory` (texture) | T_BT_Ivory.jpg pinned, sha256 `6d1d5c4364…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD2/T_BT_FirstClassInterior` | `texture/belmontetrain/first-class-lod2-first-class-interior` (texture) | T_BT_FirstClassInterior.png pinned, sha256 `4b2b7fb1c8…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD2/T_BT_Roof` | `texture/belmontetrain/first-class-lod2-roof` (texture) | T_BT_Roof.jpg pinned, sha256 `0269313a90…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/T_BT_Walnut` | `texture/belmontetrain/locomotive-lod0-walnut` (texture) | T_BT_Walnut.png pinned, sha256 `82a95ac294…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/T_BT_Underframe` | `texture/belmontetrain/locomotive-lod0-underframe` (texture) | T_BT_Underframe.jpg pinned, sha256 `e16f7c563c…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/T_BT_Walnut1` | `texture/belmontetrain/locomotive-lod0-walnut1` (texture) | T_BT_Walnut.png pinned, sha256 `82a95ac294…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/T_BT_SmokeboxDoor` | `texture/belmontetrain/locomotive-lod0-smokebox-door` (texture) | T_BT_SmokeboxDoor.jpg pinned, sha256 `df4f5c6b50…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/T_BT_Crest` | `texture/belmontetrain/locomotive-lod0-crest` (texture) | T_BT_Crest.png pinned, sha256 `ed2d1c397b…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD1/T_BT_Walnut` | `texture/belmontetrain/locomotive-lod1-walnut` (texture) | T_BT_Walnut.png pinned, sha256 `82a95ac294…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD1/T_BT_Underframe` | `texture/belmontetrain/locomotive-lod1-underframe` (texture) | T_BT_Underframe.jpg pinned, sha256 `e16f7c563c…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD1/T_BT_Walnut1` | `texture/belmontetrain/locomotive-lod1-walnut1` (texture) | T_BT_Walnut.png pinned, sha256 `82a95ac294…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD1/T_BT_SmokeboxDoor` | `texture/belmontetrain/locomotive-lod1-smokebox-door` (texture) | T_BT_SmokeboxDoor.jpg pinned, sha256 `df4f5c6b50…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD1/T_BT_Crest` | `texture/belmontetrain/locomotive-lod1-crest` (texture) | T_BT_Crest.png pinned, sha256 `ed2d1c397b…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD2/T_BT_Underframe` | `texture/belmontetrain/locomotive-lod2-underframe` (texture) | T_BT_Underframe.jpg pinned, sha256 `e16f7c563c…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/T_BT_Walnut` | `texture/belmontetrain/restaurant-lod0-walnut` (texture) | T_BT_Walnut.png pinned, sha256 `82a95ac294…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/T_BT_Tiles` | `texture/belmontetrain/restaurant-lod0-tiles` (texture) | T_BT_Tiles.png pinned, sha256 `929cdacfd4…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/T_BT_CarpetBurgundy` | `texture/belmontetrain/restaurant-lod0-carpet-burgundy` (texture) | T_BT_CarpetBurgundy.png pinned, sha256 `ea2ec0efcf…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/T_BT_Walnut1` | `texture/belmontetrain/restaurant-lod0-walnut1` (texture) | T_BT_Walnut.png pinned, sha256 `82a95ac294…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/T_BT_PanelWide` | `texture/belmontetrain/restaurant-lod0-panel-wide` (texture) | T_BT_PanelWide.png pinned, sha256 `cc31811be2…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/T_BT_PanelTall` | `texture/belmontetrain/restaurant-lod0-panel-tall` (texture) | T_BT_PanelTall.png pinned, sha256 `9c1b7dd0b2…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/T_BT_Roof` | `texture/belmontetrain/restaurant-lod0-roof` (texture) | T_BT_Roof.jpg pinned, sha256 `0269313a90…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/T_BT_Underframe` | `texture/belmontetrain/restaurant-lod0-underframe` (texture) | T_BT_Underframe.jpg pinned, sha256 `e16f7c563c…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/T_BT_Crest` | `texture/belmontetrain/restaurant-lod0-crest` (texture) | T_BT_Crest.png pinned, sha256 `ed2d1c397b…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/T_BT_Ivory` | `texture/belmontetrain/restaurant-lod0-ivory` (texture) | T_BT_Ivory.jpg pinned, sha256 `6d1d5c4364…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/T_BT_BluePanel` | `texture/belmontetrain/restaurant-lod0-blue-panel` (texture) | T_BT_BluePanel.jpg pinned, sha256 `d0e139bb1b…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/T_BT_Tiles` | `texture/belmontetrain/restaurant-lod1-tiles` (texture) | T_BT_Tiles.png pinned, sha256 `929cdacfd4…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/T_BT_CarpetBurgundy` | `texture/belmontetrain/restaurant-lod1-carpet-burgundy` (texture) | T_BT_CarpetBurgundy.png pinned, sha256 `ea2ec0efcf…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/T_BT_Walnut` | `texture/belmontetrain/restaurant-lod1-walnut` (texture) | T_BT_Walnut.png pinned, sha256 `82a95ac294…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/T_BT_Walnut1` | `texture/belmontetrain/restaurant-lod1-walnut1` (texture) | T_BT_Walnut.png pinned, sha256 `82a95ac294…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/T_BT_Roof` | `texture/belmontetrain/restaurant-lod1-roof` (texture) | T_BT_Roof.jpg pinned, sha256 `0269313a90…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/T_BT_Underframe` | `texture/belmontetrain/restaurant-lod1-underframe` (texture) | T_BT_Underframe.jpg pinned, sha256 `e16f7c563c…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/T_BT_Crest` | `texture/belmontetrain/restaurant-lod1-crest` (texture) | T_BT_Crest.png pinned, sha256 `ed2d1c397b…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/T_BT_Ivory` | `texture/belmontetrain/restaurant-lod1-ivory` (texture) | T_BT_Ivory.jpg pinned, sha256 `6d1d5c4364…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/T_BT_BluePanel` | `texture/belmontetrain/restaurant-lod1-blue-panel` (texture) | T_BT_BluePanel.jpg pinned, sha256 `d0e139bb1b…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD2/T_BT_Underframe` | `texture/belmontetrain/restaurant-lod2-underframe` (texture) | T_BT_Underframe.jpg pinned, sha256 `e16f7c563c…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD2/T_BT_Ivory` | `texture/belmontetrain/restaurant-lod2-ivory` (texture) | T_BT_Ivory.jpg pinned, sha256 `6d1d5c4364…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD2/T_BT_RestaurantInterior` | `texture/belmontetrain/restaurant-lod2-restaurant-interior` (texture) | T_BT_RestaurantInterior.png pinned, sha256 `d2a05cccdf…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD2/T_BT_Roof` | `texture/belmontetrain/restaurant-lod2-roof` (texture) | T_BT_Roof.jpg pinned, sha256 `0269313a90…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/T_BT_DarkWorn` | `texture/belmontetrain/second-class-lod0-dark-worn` (texture) | T_BT_DarkWorn.png pinned, sha256 `e624212eaa…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/T_BT_Tiles` | `texture/belmontetrain/second-class-lod0-tiles` (texture) | T_BT_Tiles.png pinned, sha256 `929cdacfd4…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/T_BT_TilesGrimy` | `texture/belmontetrain/second-class-lod0-tiles-grimy` (texture) | T_BT_TilesGrimy.jpg pinned, sha256 `299ba07696…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/T_BT_Lino` | `texture/belmontetrain/second-class-lod0-lino` (texture) | T_BT_Lino.jpg pinned, sha256 `e5b1ba3ce7…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/T_BT_PaintPeel` | `texture/belmontetrain/second-class-lod0-paint-peel` (texture) | T_BT_PaintPeel.jpg pinned, sha256 `cdca50945d…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/T_BT_RoofWorn` | `texture/belmontetrain/second-class-lod0-roof-worn` (texture) | T_BT_RoofWorn.jpg pinned, sha256 `4d56f63b37…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/T_BT_Underframe` | `texture/belmontetrain/second-class-lod0-underframe` (texture) | T_BT_Underframe.jpg pinned, sha256 `e16f7c563c…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/T_BT_Two` | `texture/belmontetrain/second-class-lod0-two` (texture) | T_BT_Two.png pinned, sha256 `cd8a852101…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/T_BT_BlueWorn` | `texture/belmontetrain/second-class-lod0-blue-worn` (texture) | T_BT_BlueWorn.png pinned, sha256 `ca8fe879ce…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/T_BT_IvoryWorn` | `texture/belmontetrain/second-class-lod0-ivory-worn` (texture) | T_BT_IvoryWorn.jpg pinned, sha256 `d065538f46…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/T_BT_BluePanelWorn` | `texture/belmontetrain/second-class-lod0-blue-panel-worn` (texture) | T_BT_BluePanelWorn.jpg pinned, sha256 `489ea601fa…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/T_BT_DarkWorn` | `texture/belmontetrain/second-class-lod1-dark-worn` (texture) | T_BT_DarkWorn.png pinned, sha256 `e624212eaa…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/T_BT_Tiles` | `texture/belmontetrain/second-class-lod1-tiles` (texture) | T_BT_Tiles.png pinned, sha256 `929cdacfd4…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/T_BT_TilesGrimy` | `texture/belmontetrain/second-class-lod1-tiles-grimy` (texture) | T_BT_TilesGrimy.jpg pinned, sha256 `299ba07696…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/T_BT_Lino` | `texture/belmontetrain/second-class-lod1-lino` (texture) | T_BT_Lino.jpg pinned, sha256 `e5b1ba3ce7…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/T_BT_PaintPeel` | `texture/belmontetrain/second-class-lod1-paint-peel` (texture) | T_BT_PaintPeel.jpg pinned, sha256 `cdca50945d…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/T_BT_RoofWorn` | `texture/belmontetrain/second-class-lod1-roof-worn` (texture) | T_BT_RoofWorn.jpg pinned, sha256 `4d56f63b37…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/T_BT_Underframe` | `texture/belmontetrain/second-class-lod1-underframe` (texture) | T_BT_Underframe.jpg pinned, sha256 `e16f7c563c…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/T_BT_Two` | `texture/belmontetrain/second-class-lod1-two` (texture) | T_BT_Two.png pinned, sha256 `cd8a852101…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/T_BT_BlueWorn` | `texture/belmontetrain/second-class-lod1-blue-worn` (texture) | T_BT_BlueWorn.png pinned, sha256 `ca8fe879ce…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/T_BT_IvoryWorn` | `texture/belmontetrain/second-class-lod1-ivory-worn` (texture) | T_BT_IvoryWorn.jpg pinned, sha256 `d065538f46…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/T_BT_BluePanelWorn` | `texture/belmontetrain/second-class-lod1-blue-panel-worn` (texture) | T_BT_BluePanelWorn.jpg pinned, sha256 `489ea601fa…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD2/T_BT_Underframe` | `texture/belmontetrain/second-class-lod2-underframe` (texture) | T_BT_Underframe.jpg pinned, sha256 `e16f7c563c…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD2/T_BT_BlueWorn` | `texture/belmontetrain/second-class-lod2-blue-worn` (texture) | T_BT_BlueWorn.png pinned, sha256 `ca8fe879ce…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD2/T_BT_IvoryWorn` | `texture/belmontetrain/second-class-lod2-ivory-worn` (texture) | T_BT_IvoryWorn.jpg pinned, sha256 `d065538f46…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD2/T_BT_SecondClassInterior` | `texture/belmontetrain/second-class-lod2-second-class-interior` (texture) | T_BT_SecondClassInterior.png pinned, sha256 `f1a578ae81…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD2/T_BT_RoofWorn` | `texture/belmontetrain/second-class-lod2-roof-worn` (texture) | T_BT_RoofWorn.jpg pinned, sha256 `4d56f63b37…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD0/T_BT_Underframe` | `texture/belmontetrain/tender-lod0-underframe` (texture) | T_BT_Underframe.jpg pinned, sha256 `e16f7c563c…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD0/T_BT_Crest` | `texture/belmontetrain/tender-lod0-crest` (texture) | T_BT_Crest.png pinned, sha256 `ed2d1c397b…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD0/T_BT_Walnut` | `texture/belmontetrain/tender-lod0-walnut` (texture) | T_BT_Walnut.png pinned, sha256 `82a95ac294…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD0/T_BT_Roof` | `texture/belmontetrain/tender-lod0-roof` (texture) | T_BT_Roof.jpg pinned, sha256 `0269313a90…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD1/T_BT_Underframe` | `texture/belmontetrain/tender-lod1-underframe` (texture) | T_BT_Underframe.jpg pinned, sha256 `e16f7c563c…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD1/T_BT_Crest` | `texture/belmontetrain/tender-lod1-crest` (texture) | T_BT_Crest.png pinned, sha256 `ed2d1c397b…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD1/T_BT_Walnut` | `texture/belmontetrain/tender-lod1-walnut` (texture) | T_BT_Walnut.png pinned, sha256 `82a95ac294…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD1/T_BT_Roof` | `texture/belmontetrain/tender-lod1-roof` (texture) | T_BT_Roof.jpg pinned, sha256 `0269313a90…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD2/T_BT_Walnut` | `texture/belmontetrain/tender-lod2-walnut` (texture) | T_BT_Walnut.png pinned, sha256 `82a95ac294…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD2/T_BT_Underframe` | `texture/belmontetrain/tender-lod2-underframe` (texture) | T_BT_Underframe.jpg pinned, sha256 `e16f7c563c…` | sRGB flag not in the bytes: native read | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/M_BT_Glass` | `material/belmontetrain/baggage-van-lod0` (material-instance) | SM_BT_BaggageVan_LOD0.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/M_BT_IronBlack` | `material/belmontetrain/baggage-van-lod0` (material-instance) | SM_BT_BaggageVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/M_BT_BrassDull` | `material/belmontetrain/baggage-van-lod0` (material-instance) | SM_BT_BaggageVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/M_BT_EndDark` | `material/belmontetrain/baggage-van-lod0` (material-instance) | SM_BT_BaggageVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/M_BT_Walnut` | `material/belmontetrain/baggage-van-lod0` (material-instance) | SM_BT_BaggageVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/M_BT_CurtainCanvas` | `material/belmontetrain/baggage-van-lod0` (material-instance) | SM_BT_BaggageVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/M_BT_EnamelGrimy` | `material/belmontetrain/baggage-van-lod0` (material-instance) | SM_BT_BaggageVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/M_BT_EnamelWhite` | `material/belmontetrain/baggage-van-lod0` (material-instance) | SM_BT_BaggageVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/M_BT_EnamelSoot` | `material/belmontetrain/baggage-van-lod0` (material-instance) | SM_BT_BaggageVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/M_BT_LampWhite` | `material/belmontetrain/baggage-van-lod0` (material-instance) | SM_BT_BaggageVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/M_BT_Parquet` | `material/belmontetrain/baggage-van-lod0` (material-instance) | SM_BT_BaggageVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/M_BT_PanelWide` | `material/belmontetrain/baggage-van-lod0` (material-instance) | SM_BT_BaggageVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/M_BT_PanelTall` | `material/belmontetrain/baggage-van-lod0` (material-instance) | SM_BT_BaggageVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/M_BT_Brass` | `material/belmontetrain/baggage-van-lod0` (material-instance) | SM_BT_BaggageVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/M_BT_Ceiling` | `material/belmontetrain/baggage-van-lod0` (material-instance) | SM_BT_BaggageVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/M_BT_Roof` | `material/belmontetrain/baggage-van-lod0` (material-instance) | SM_BT_BaggageVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/M_BT_Steel` | `material/belmontetrain/baggage-van-lod0` (material-instance) | SM_BT_BaggageVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/M_BT_Undercarriage` | `material/belmontetrain/baggage-van-lod0` (material-instance) | SM_BT_BaggageVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/M_BT_Rubber` | `material/belmontetrain/baggage-van-lod0` (material-instance) | SM_BT_BaggageVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/M_BT_Crest` | `material/belmontetrain/baggage-van-lod0` (material-instance) | SM_BT_BaggageVan_LOD0.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/M_BT_LiveryIvory` | `material/belmontetrain/baggage-van-lod0` (material-instance) | SM_BT_BaggageVan_LOD0.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/M_BT_LiveryBlue` | `material/belmontetrain/baggage-van-lod0` (material-instance) | SM_BT_BaggageVan_LOD0.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD0/M_BT_LiveryPanel` | `material/belmontetrain/baggage-van-lod0` (material-instance) | SM_BT_BaggageVan_LOD0.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/M_BT_Glass` | `material/belmontetrain/baggage-van-lod1` (material-instance) | SM_BT_BaggageVan_LOD1.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/M_BT_BrassDull` | `material/belmontetrain/baggage-van-lod1` (material-instance) | SM_BT_BaggageVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/M_BT_CurtainCanvas` | `material/belmontetrain/baggage-van-lod1` (material-instance) | SM_BT_BaggageVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/M_BT_EndDark` | `material/belmontetrain/baggage-van-lod1` (material-instance) | SM_BT_BaggageVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/M_BT_EnamelGrimy` | `material/belmontetrain/baggage-van-lod1` (material-instance) | SM_BT_BaggageVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/M_BT_EnamelWhite` | `material/belmontetrain/baggage-van-lod1` (material-instance) | SM_BT_BaggageVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/M_BT_IronBlack` | `material/belmontetrain/baggage-van-lod1` (material-instance) | SM_BT_BaggageVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/M_BT_EnamelSoot` | `material/belmontetrain/baggage-van-lod1` (material-instance) | SM_BT_BaggageVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/M_BT_LampWhite` | `material/belmontetrain/baggage-van-lod1` (material-instance) | SM_BT_BaggageVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/M_BT_Parquet` | `material/belmontetrain/baggage-van-lod1` (material-instance) | SM_BT_BaggageVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/M_BT_Walnut` | `material/belmontetrain/baggage-van-lod1` (material-instance) | SM_BT_BaggageVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/M_BT_Ceiling` | `material/belmontetrain/baggage-van-lod1` (material-instance) | SM_BT_BaggageVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/M_BT_Roof` | `material/belmontetrain/baggage-van-lod1` (material-instance) | SM_BT_BaggageVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/M_BT_Steel` | `material/belmontetrain/baggage-van-lod1` (material-instance) | SM_BT_BaggageVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/M_BT_Undercarriage` | `material/belmontetrain/baggage-van-lod1` (material-instance) | SM_BT_BaggageVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/M_BT_Brass` | `material/belmontetrain/baggage-van-lod1` (material-instance) | SM_BT_BaggageVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/M_BT_Rubber` | `material/belmontetrain/baggage-van-lod1` (material-instance) | SM_BT_BaggageVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/M_BT_Crest` | `material/belmontetrain/baggage-van-lod1` (material-instance) | SM_BT_BaggageVan_LOD1.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/M_BT_LiveryIvory` | `material/belmontetrain/baggage-van-lod1` (material-instance) | SM_BT_BaggageVan_LOD1.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/M_BT_LiveryBlue` | `material/belmontetrain/baggage-van-lod1` (material-instance) | SM_BT_BaggageVan_LOD1.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD1/M_BT_LiveryPanel` | `material/belmontetrain/baggage-van-lod1` (material-instance) | SM_BT_BaggageVan_LOD1.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD2/M_BT_Undercarriage` | `material/belmontetrain/baggage-van-lod2` (material-instance) | SM_BT_BaggageVan_LOD2.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD2/M_BT_LiveryBlue` | `material/belmontetrain/baggage-van-lod2` (material-instance) | SM_BT_BaggageVan_LOD2.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD2/M_BT_LiveryIvory` | `material/belmontetrain/baggage-van-lod2` (material-instance) | SM_BT_BaggageVan_LOD2.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD2/M_BT_GlassDark` | `material/belmontetrain/baggage-van-lod2` (material-instance) | SM_BT_BaggageVan_LOD2.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD2/M_BT_WindowInteriorBaggageVan` | `material/belmontetrain/baggage-van-lod2` (material-instance) | SM_BT_BaggageVan_LOD2.glb, parent `MI_Default_Opaque` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD2/M_BT_Rubber` | `material/belmontetrain/baggage-van-lod2` (material-instance) | SM_BT_BaggageVan_LOD2.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BaggageVan/LOD2/M_BT_Roof` | `material/belmontetrain/baggage-van-lod2` (material-instance) | SM_BT_BaggageVan_LOD2.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_Glass` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_IronBlack` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_BrassDull` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_EndDark` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_Walnut` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_CurtainCanvas` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_EnamelGrimy` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_EnamelWhite` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_EnamelSoot` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_LampWhite` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_Parquet` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_Tile` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_PanelWide` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_PanelTall` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_Brass` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_Ceiling` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_LiveryIvory` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_Roof` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_Steel` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_Undercarriage` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_Rubber` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_Crest` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_LiveryBlue` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_LiveryPanel` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD0/M_BT_LampRed` | `material/belmontetrain/brake-van-lod0` (material-instance) | SM_BT_BrakeVan_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/M_BT_Glass` | `material/belmontetrain/brake-van-lod1` (material-instance) | SM_BT_BrakeVan_LOD1.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/M_BT_BrassDull` | `material/belmontetrain/brake-van-lod1` (material-instance) | SM_BT_BrakeVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/M_BT_CurtainCanvas` | `material/belmontetrain/brake-van-lod1` (material-instance) | SM_BT_BrakeVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/M_BT_EndDark` | `material/belmontetrain/brake-van-lod1` (material-instance) | SM_BT_BrakeVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/M_BT_EnamelGrimy` | `material/belmontetrain/brake-van-lod1` (material-instance) | SM_BT_BrakeVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/M_BT_EnamelWhite` | `material/belmontetrain/brake-van-lod1` (material-instance) | SM_BT_BrakeVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/M_BT_IronBlack` | `material/belmontetrain/brake-van-lod1` (material-instance) | SM_BT_BrakeVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/M_BT_EnamelSoot` | `material/belmontetrain/brake-van-lod1` (material-instance) | SM_BT_BrakeVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/M_BT_LampWhite` | `material/belmontetrain/brake-van-lod1` (material-instance) | SM_BT_BrakeVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/M_BT_Parquet` | `material/belmontetrain/brake-van-lod1` (material-instance) | SM_BT_BrakeVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/M_BT_Tile` | `material/belmontetrain/brake-van-lod1` (material-instance) | SM_BT_BrakeVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/M_BT_Walnut` | `material/belmontetrain/brake-van-lod1` (material-instance) | SM_BT_BrakeVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/M_BT_Brass` | `material/belmontetrain/brake-van-lod1` (material-instance) | SM_BT_BrakeVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/M_BT_Ceiling` | `material/belmontetrain/brake-van-lod1` (material-instance) | SM_BT_BrakeVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/M_BT_LiveryIvory` | `material/belmontetrain/brake-van-lod1` (material-instance) | SM_BT_BrakeVan_LOD1.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/M_BT_Roof` | `material/belmontetrain/brake-van-lod1` (material-instance) | SM_BT_BrakeVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/M_BT_Steel` | `material/belmontetrain/brake-van-lod1` (material-instance) | SM_BT_BrakeVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/M_BT_Undercarriage` | `material/belmontetrain/brake-van-lod1` (material-instance) | SM_BT_BrakeVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/M_BT_Rubber` | `material/belmontetrain/brake-van-lod1` (material-instance) | SM_BT_BrakeVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/M_BT_Crest` | `material/belmontetrain/brake-van-lod1` (material-instance) | SM_BT_BrakeVan_LOD1.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/M_BT_LiveryBlue` | `material/belmontetrain/brake-van-lod1` (material-instance) | SM_BT_BrakeVan_LOD1.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/M_BT_LiveryPanel` | `material/belmontetrain/brake-van-lod1` (material-instance) | SM_BT_BrakeVan_LOD1.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD1/M_BT_LampRed` | `material/belmontetrain/brake-van-lod1` (material-instance) | SM_BT_BrakeVan_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD2/M_BT_Undercarriage` | `material/belmontetrain/brake-van-lod2` (material-instance) | SM_BT_BrakeVan_LOD2.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD2/M_BT_LiveryBlue` | `material/belmontetrain/brake-van-lod2` (material-instance) | SM_BT_BrakeVan_LOD2.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD2/M_BT_LiveryIvory` | `material/belmontetrain/brake-van-lod2` (material-instance) | SM_BT_BrakeVan_LOD2.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD2/M_BT_WindowInteriorBrakeVan` | `material/belmontetrain/brake-van-lod2` (material-instance) | SM_BT_BrakeVan_LOD2.glb, parent `MI_Default_Opaque` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD2/M_BT_Rubber` | `material/belmontetrain/brake-van-lod2` (material-instance) | SM_BT_BrakeVan_LOD2.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_BrakeVan/LOD2/M_BT_Roof` | `material/belmontetrain/brake-van-lod2` (material-instance) | SM_BT_BrakeVan_LOD2.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/M_BT_GlassFrosted` | `material/belmontetrain/first-class-lod0` (material-instance) | SM_BT_FirstClass_LOD0.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/M_BT_Glass` | `material/belmontetrain/first-class-lod0` (material-instance) | SM_BT_FirstClass_LOD0.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/M_BT_EndDark` | `material/belmontetrain/first-class-lod0` (material-instance) | SM_BT_FirstClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/M_BT_Walnut` | `material/belmontetrain/first-class-lod0` (material-instance) | SM_BT_FirstClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/M_BT_Brass` | `material/belmontetrain/first-class-lod0` (material-instance) | SM_BT_FirstClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/M_BT_Zinc` | `material/belmontetrain/first-class-lod0` (material-instance) | SM_BT_FirstClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/M_BT_VelvetEmerald` | `material/belmontetrain/first-class-lod0` (material-instance) | SM_BT_FirstClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/M_BT_CordEmerald` | `material/belmontetrain/first-class-lod0` (material-instance) | SM_BT_FirstClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/M_BT_Tile` | `material/belmontetrain/first-class-lod0` (material-instance) | SM_BT_FirstClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/M_BT_CarpetEmerald` | `material/belmontetrain/first-class-lod0` (material-instance) | SM_BT_FirstClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/M_BT_Parquet` | `material/belmontetrain/first-class-lod0` (material-instance) | SM_BT_FirstClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/M_BT_PanelWide` | `material/belmontetrain/first-class-lod0` (material-instance) | SM_BT_FirstClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/M_BT_PanelTall` | `material/belmontetrain/first-class-lod0` (material-instance) | SM_BT_FirstClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/M_BT_Ceiling` | `material/belmontetrain/first-class-lod0` (material-instance) | SM_BT_FirstClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/M_BT_Roof` | `material/belmontetrain/first-class-lod0` (material-instance) | SM_BT_FirstClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/M_BT_Steel` | `material/belmontetrain/first-class-lod0` (material-instance) | SM_BT_FirstClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/M_BT_Undercarriage` | `material/belmontetrain/first-class-lod0` (material-instance) | SM_BT_FirstClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/M_BT_Rubber` | `material/belmontetrain/first-class-lod0` (material-instance) | SM_BT_FirstClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/M_BT_Crest` | `material/belmontetrain/first-class-lod0` (material-instance) | SM_BT_FirstClass_LOD0.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/M_BT_LiveryBlue` | `material/belmontetrain/first-class-lod0` (material-instance) | SM_BT_FirstClass_LOD0.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/M_BT_LiveryIvory` | `material/belmontetrain/first-class-lod0` (material-instance) | SM_BT_FirstClass_LOD0.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD0/M_BT_LiveryPanel` | `material/belmontetrain/first-class-lod0` (material-instance) | SM_BT_FirstClass_LOD0.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/M_BT_GlassFrosted` | `material/belmontetrain/first-class-lod1` (material-instance) | SM_BT_FirstClass_LOD1.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/M_BT_Glass` | `material/belmontetrain/first-class-lod1` (material-instance) | SM_BT_FirstClass_LOD1.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/M_BT_Brass` | `material/belmontetrain/first-class-lod1` (material-instance) | SM_BT_FirstClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/M_BT_VelvetEmerald` | `material/belmontetrain/first-class-lod1` (material-instance) | SM_BT_FirstClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/M_BT_Tile` | `material/belmontetrain/first-class-lod1` (material-instance) | SM_BT_FirstClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/M_BT_CarpetEmerald` | `material/belmontetrain/first-class-lod1` (material-instance) | SM_BT_FirstClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/M_BT_Parquet` | `material/belmontetrain/first-class-lod1` (material-instance) | SM_BT_FirstClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/M_BT_Walnut` | `material/belmontetrain/first-class-lod1` (material-instance) | SM_BT_FirstClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/M_BT_Ceiling` | `material/belmontetrain/first-class-lod1` (material-instance) | SM_BT_FirstClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/M_BT_Roof` | `material/belmontetrain/first-class-lod1` (material-instance) | SM_BT_FirstClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/M_BT_Steel` | `material/belmontetrain/first-class-lod1` (material-instance) | SM_BT_FirstClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/M_BT_Undercarriage` | `material/belmontetrain/first-class-lod1` (material-instance) | SM_BT_FirstClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/M_BT_Rubber` | `material/belmontetrain/first-class-lod1` (material-instance) | SM_BT_FirstClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/M_BT_EndDark` | `material/belmontetrain/first-class-lod1` (material-instance) | SM_BT_FirstClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/M_BT_Crest` | `material/belmontetrain/first-class-lod1` (material-instance) | SM_BT_FirstClass_LOD1.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/M_BT_LiveryBlue` | `material/belmontetrain/first-class-lod1` (material-instance) | SM_BT_FirstClass_LOD1.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/M_BT_LiveryIvory` | `material/belmontetrain/first-class-lod1` (material-instance) | SM_BT_FirstClass_LOD1.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD1/M_BT_LiveryPanel` | `material/belmontetrain/first-class-lod1` (material-instance) | SM_BT_FirstClass_LOD1.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD2/M_BT_Undercarriage` | `material/belmontetrain/first-class-lod2` (material-instance) | SM_BT_FirstClass_LOD2.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD2/M_BT_LiveryBlue` | `material/belmontetrain/first-class-lod2` (material-instance) | SM_BT_FirstClass_LOD2.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD2/M_BT_LiveryIvory` | `material/belmontetrain/first-class-lod2` (material-instance) | SM_BT_FirstClass_LOD2.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD2/M_BT_GlassDark` | `material/belmontetrain/first-class-lod2` (material-instance) | SM_BT_FirstClass_LOD2.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD2/M_BT_WindowInteriorFirstClass` | `material/belmontetrain/first-class-lod2` (material-instance) | SM_BT_FirstClass_LOD2.glb, parent `MI_Default_Opaque` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD2/M_BT_Rubber` | `material/belmontetrain/first-class-lod2` (material-instance) | SM_BT_FirstClass_LOD2.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_FirstClass/LOD2/M_BT_Roof` | `material/belmontetrain/first-class-lod2` (material-instance) | SM_BT_FirstClass_LOD2.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/M_BT_EnamelGrimy` | `material/belmontetrain/locomotive-lod0` (material-instance) | SM_BT_Locomotive_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/M_BT_EndDark` | `material/belmontetrain/locomotive-lod0` (material-instance) | SM_BT_Locomotive_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/M_BT_EnamelWhite` | `material/belmontetrain/locomotive-lod0` (material-instance) | SM_BT_Locomotive_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/M_BT_IronBlack` | `material/belmontetrain/locomotive-lod0` (material-instance) | SM_BT_Locomotive_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/M_BT_EnamelSoot` | `material/belmontetrain/locomotive-lod0` (material-instance) | SM_BT_Locomotive_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/M_BT_LampWhite` | `material/belmontetrain/locomotive-lod0` (material-instance) | SM_BT_Locomotive_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/M_BT_LocoBlack` | `material/belmontetrain/locomotive-lod0` (material-instance) | SM_BT_Locomotive_LOD0.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/M_BT_Walnut` | `material/belmontetrain/locomotive-lod0` (material-instance) | SM_BT_Locomotive_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/M_BT_Undercarriage` | `material/belmontetrain/locomotive-lod0` (material-instance) | SM_BT_Locomotive_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/M_BT_Fire` | `material/belmontetrain/locomotive-lod0` (material-instance) | SM_BT_Locomotive_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/M_BT_Parquet` | `material/belmontetrain/locomotive-lod0` (material-instance) | SM_BT_Locomotive_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/M_BT_Brass` | `material/belmontetrain/locomotive-lod0` (material-instance) | SM_BT_Locomotive_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/M_BT_BrassDull` | `material/belmontetrain/locomotive-lod0` (material-instance) | SM_BT_Locomotive_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/M_BT_Steel` | `material/belmontetrain/locomotive-lod0` (material-instance) | SM_BT_Locomotive_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/M_BT_Ceiling` | `material/belmontetrain/locomotive-lod0` (material-instance) | SM_BT_Locomotive_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/M_BT_Coal` | `material/belmontetrain/locomotive-lod0` (material-instance) | SM_BT_Locomotive_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/M_BT_SmokeboxDoor` | `material/belmontetrain/locomotive-lod0` (material-instance) | SM_BT_Locomotive_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/M_BT_LiningRed` | `material/belmontetrain/locomotive-lod0` (material-instance) | SM_BT_Locomotive_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/M_BT_Crest` | `material/belmontetrain/locomotive-lod0` (material-instance) | SM_BT_Locomotive_LOD0.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD0/M_BT_Glass` | `material/belmontetrain/locomotive-lod0` (material-instance) | SM_BT_Locomotive_LOD0.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD1/M_BT_LocoBlack` | `material/belmontetrain/locomotive-lod1` (material-instance) | SM_BT_Locomotive_LOD1.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD1/M_BT_Walnut` | `material/belmontetrain/locomotive-lod1` (material-instance) | SM_BT_Locomotive_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD1/M_BT_IronBlack` | `material/belmontetrain/locomotive-lod1` (material-instance) | SM_BT_Locomotive_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD1/M_BT_Undercarriage` | `material/belmontetrain/locomotive-lod1` (material-instance) | SM_BT_Locomotive_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD1/M_BT_Fire` | `material/belmontetrain/locomotive-lod1` (material-instance) | SM_BT_Locomotive_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD1/M_BT_Parquet` | `material/belmontetrain/locomotive-lod1` (material-instance) | SM_BT_Locomotive_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD1/M_BT_Ceiling` | `material/belmontetrain/locomotive-lod1` (material-instance) | SM_BT_Locomotive_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD1/M_BT_Brass` | `material/belmontetrain/locomotive-lod1` (material-instance) | SM_BT_Locomotive_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD1/M_BT_Steel` | `material/belmontetrain/locomotive-lod1` (material-instance) | SM_BT_Locomotive_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD1/M_BT_EndDark` | `material/belmontetrain/locomotive-lod1` (material-instance) | SM_BT_Locomotive_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD1/M_BT_Coal` | `material/belmontetrain/locomotive-lod1` (material-instance) | SM_BT_Locomotive_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD1/M_BT_SmokeboxDoor` | `material/belmontetrain/locomotive-lod1` (material-instance) | SM_BT_Locomotive_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD1/M_BT_Crest` | `material/belmontetrain/locomotive-lod1` (material-instance) | SM_BT_Locomotive_LOD1.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD1/M_BT_LampWhite` | `material/belmontetrain/locomotive-lod1` (material-instance) | SM_BT_Locomotive_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD1/M_BT_Glass` | `material/belmontetrain/locomotive-lod1` (material-instance) | SM_BT_Locomotive_LOD1.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD2/M_BT_LocoBlack` | `material/belmontetrain/locomotive-lod2` (material-instance) | SM_BT_Locomotive_LOD2.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD2/M_BT_IronBlack` | `material/belmontetrain/locomotive-lod2` (material-instance) | SM_BT_Locomotive_LOD2.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Locomotive/LOD2/M_BT_Undercarriage` | `material/belmontetrain/locomotive-lod2` (material-instance) | SM_BT_Locomotive_LOD2.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/M_BT_Glass` | `material/belmontetrain/restaurant-lod0` (material-instance) | SM_BT_Restaurant_LOD0.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/M_BT_GlassFrosted` | `material/belmontetrain/restaurant-lod0` (material-instance) | SM_BT_Restaurant_LOD0.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/M_BT_EndDark` | `material/belmontetrain/restaurant-lod0` (material-instance) | SM_BT_Restaurant_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/M_BT_EnamelCream` | `material/belmontetrain/restaurant-lod0` (material-instance) | SM_BT_Restaurant_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/M_BT_BrassDull` | `material/belmontetrain/restaurant-lod0` (material-instance) | SM_BT_Restaurant_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/M_BT_Zinc` | `material/belmontetrain/restaurant-lod0` (material-instance) | SM_BT_Restaurant_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/M_BT_Brass` | `material/belmontetrain/restaurant-lod0` (material-instance) | SM_BT_Restaurant_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/M_BT_VelvetBurgundy` | `material/belmontetrain/restaurant-lod0` (material-instance) | SM_BT_Restaurant_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/M_BT_Walnut` | `material/belmontetrain/restaurant-lod0` (material-instance) | SM_BT_Restaurant_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/M_BT_CordBurgundy` | `material/belmontetrain/restaurant-lod0` (material-instance) | SM_BT_Restaurant_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/M_BT_Tile` | `material/belmontetrain/restaurant-lod0` (material-instance) | SM_BT_Restaurant_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/M_BT_CarpetBurgundy` | `material/belmontetrain/restaurant-lod0` (material-instance) | SM_BT_Restaurant_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/M_BT_Parquet` | `material/belmontetrain/restaurant-lod0` (material-instance) | SM_BT_Restaurant_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/M_BT_PanelWide` | `material/belmontetrain/restaurant-lod0` (material-instance) | SM_BT_Restaurant_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/M_BT_PanelTall` | `material/belmontetrain/restaurant-lod0` (material-instance) | SM_BT_Restaurant_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/M_BT_Ceiling` | `material/belmontetrain/restaurant-lod0` (material-instance) | SM_BT_Restaurant_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/M_BT_Roof` | `material/belmontetrain/restaurant-lod0` (material-instance) | SM_BT_Restaurant_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/M_BT_Steel` | `material/belmontetrain/restaurant-lod0` (material-instance) | SM_BT_Restaurant_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/M_BT_Undercarriage` | `material/belmontetrain/restaurant-lod0` (material-instance) | SM_BT_Restaurant_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/M_BT_Rubber` | `material/belmontetrain/restaurant-lod0` (material-instance) | SM_BT_Restaurant_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/M_BT_Crest` | `material/belmontetrain/restaurant-lod0` (material-instance) | SM_BT_Restaurant_LOD0.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/M_BT_LiveryBlue` | `material/belmontetrain/restaurant-lod0` (material-instance) | SM_BT_Restaurant_LOD0.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/M_BT_LiveryIvory` | `material/belmontetrain/restaurant-lod0` (material-instance) | SM_BT_Restaurant_LOD0.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD0/M_BT_LiveryPanel` | `material/belmontetrain/restaurant-lod0` (material-instance) | SM_BT_Restaurant_LOD0.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/M_BT_Glass` | `material/belmontetrain/restaurant-lod1` (material-instance) | SM_BT_Restaurant_LOD1.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/M_BT_GlassFrosted` | `material/belmontetrain/restaurant-lod1` (material-instance) | SM_BT_Restaurant_LOD1.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/M_BT_Brass` | `material/belmontetrain/restaurant-lod1` (material-instance) | SM_BT_Restaurant_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/M_BT_VelvetBurgundy` | `material/belmontetrain/restaurant-lod1` (material-instance) | SM_BT_Restaurant_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/M_BT_Tile` | `material/belmontetrain/restaurant-lod1` (material-instance) | SM_BT_Restaurant_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/M_BT_CarpetBurgundy` | `material/belmontetrain/restaurant-lod1` (material-instance) | SM_BT_Restaurant_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/M_BT_Parquet` | `material/belmontetrain/restaurant-lod1` (material-instance) | SM_BT_Restaurant_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/M_BT_Walnut` | `material/belmontetrain/restaurant-lod1` (material-instance) | SM_BT_Restaurant_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/M_BT_Ceiling` | `material/belmontetrain/restaurant-lod1` (material-instance) | SM_BT_Restaurant_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/M_BT_Roof` | `material/belmontetrain/restaurant-lod1` (material-instance) | SM_BT_Restaurant_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/M_BT_Steel` | `material/belmontetrain/restaurant-lod1` (material-instance) | SM_BT_Restaurant_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/M_BT_Undercarriage` | `material/belmontetrain/restaurant-lod1` (material-instance) | SM_BT_Restaurant_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/M_BT_Rubber` | `material/belmontetrain/restaurant-lod1` (material-instance) | SM_BT_Restaurant_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/M_BT_EndDark` | `material/belmontetrain/restaurant-lod1` (material-instance) | SM_BT_Restaurant_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/M_BT_Crest` | `material/belmontetrain/restaurant-lod1` (material-instance) | SM_BT_Restaurant_LOD1.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/M_BT_LiveryBlue` | `material/belmontetrain/restaurant-lod1` (material-instance) | SM_BT_Restaurant_LOD1.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/M_BT_LiveryIvory` | `material/belmontetrain/restaurant-lod1` (material-instance) | SM_BT_Restaurant_LOD1.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD1/M_BT_LiveryPanel` | `material/belmontetrain/restaurant-lod1` (material-instance) | SM_BT_Restaurant_LOD1.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD2/M_BT_Undercarriage` | `material/belmontetrain/restaurant-lod2` (material-instance) | SM_BT_Restaurant_LOD2.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD2/M_BT_LiveryBlue` | `material/belmontetrain/restaurant-lod2` (material-instance) | SM_BT_Restaurant_LOD2.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD2/M_BT_LiveryIvory` | `material/belmontetrain/restaurant-lod2` (material-instance) | SM_BT_Restaurant_LOD2.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD2/M_BT_WindowInteriorRestaurant` | `material/belmontetrain/restaurant-lod2` (material-instance) | SM_BT_Restaurant_LOD2.glb, parent `MI_Default_Opaque` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD2/M_BT_GlassDark` | `material/belmontetrain/restaurant-lod2` (material-instance) | SM_BT_Restaurant_LOD2.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD2/M_BT_Rubber` | `material/belmontetrain/restaurant-lod2` (material-instance) | SM_BT_Restaurant_LOD2.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Restaurant/LOD2/M_BT_Roof` | `material/belmontetrain/restaurant-lod2` (material-instance) | SM_BT_Restaurant_LOD2.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_GlassGrimy` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_BrassDull` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_CurtainFabric` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_IronBlack` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_EnamelGrimy` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_EndDarkWorn` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_EnamelWhite` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_EnamelSoot` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_LampWhite` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_MenuBoard` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_EnamelCream` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_Cord` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_Tile` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_TilesGrimy` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_Lino` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_PaintPeel` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_CeilingDingy` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_RoofWorn` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_Steel` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_Undercarriage` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_Rubber` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_DecalTwo` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_LiveryBlueWorn` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_LiveryIvoryWorn` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD0/M_BT_LiveryPanelWorn` | `material/belmontetrain/second-class-lod0` (material-instance) | SM_BT_SecondClass_LOD0.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/M_BT_GlassGrimy` | `material/belmontetrain/second-class-lod1` (material-instance) | SM_BT_SecondClass_LOD1.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/M_BT_BrassDull` | `material/belmontetrain/second-class-lod1` (material-instance) | SM_BT_SecondClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/M_BT_CurtainFabric` | `material/belmontetrain/second-class-lod1` (material-instance) | SM_BT_SecondClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/M_BT_IronBlack` | `material/belmontetrain/second-class-lod1` (material-instance) | SM_BT_SecondClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/M_BT_EndDarkWorn` | `material/belmontetrain/second-class-lod1` (material-instance) | SM_BT_SecondClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/M_BT_EnamelGrimy` | `material/belmontetrain/second-class-lod1` (material-instance) | SM_BT_SecondClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/M_BT_EnamelWhite` | `material/belmontetrain/second-class-lod1` (material-instance) | SM_BT_SecondClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/M_BT_EnamelSoot` | `material/belmontetrain/second-class-lod1` (material-instance) | SM_BT_SecondClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/M_BT_LampWhite` | `material/belmontetrain/second-class-lod1` (material-instance) | SM_BT_SecondClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/M_BT_MenuBoard` | `material/belmontetrain/second-class-lod1` (material-instance) | SM_BT_SecondClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/M_BT_EnamelCream` | `material/belmontetrain/second-class-lod1` (material-instance) | SM_BT_SecondClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/M_BT_Tile` | `material/belmontetrain/second-class-lod1` (material-instance) | SM_BT_SecondClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/M_BT_TilesGrimy` | `material/belmontetrain/second-class-lod1` (material-instance) | SM_BT_SecondClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/M_BT_Lino` | `material/belmontetrain/second-class-lod1` (material-instance) | SM_BT_SecondClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/M_BT_PaintPeel` | `material/belmontetrain/second-class-lod1` (material-instance) | SM_BT_SecondClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/M_BT_CeilingDingy` | `material/belmontetrain/second-class-lod1` (material-instance) | SM_BT_SecondClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/M_BT_RoofWorn` | `material/belmontetrain/second-class-lod1` (material-instance) | SM_BT_SecondClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/M_BT_Steel` | `material/belmontetrain/second-class-lod1` (material-instance) | SM_BT_SecondClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/M_BT_Undercarriage` | `material/belmontetrain/second-class-lod1` (material-instance) | SM_BT_SecondClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/M_BT_Rubber` | `material/belmontetrain/second-class-lod1` (material-instance) | SM_BT_SecondClass_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/M_BT_DecalTwo` | `material/belmontetrain/second-class-lod1` (material-instance) | SM_BT_SecondClass_LOD1.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/M_BT_LiveryBlueWorn` | `material/belmontetrain/second-class-lod1` (material-instance) | SM_BT_SecondClass_LOD1.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/M_BT_LiveryIvoryWorn` | `material/belmontetrain/second-class-lod1` (material-instance) | SM_BT_SecondClass_LOD1.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD1/M_BT_LiveryPanelWorn` | `material/belmontetrain/second-class-lod1` (material-instance) | SM_BT_SecondClass_LOD1.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD2/M_BT_Undercarriage` | `material/belmontetrain/second-class-lod2` (material-instance) | SM_BT_SecondClass_LOD2.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD2/M_BT_LiveryBlueWorn` | `material/belmontetrain/second-class-lod2` (material-instance) | SM_BT_SecondClass_LOD2.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD2/M_BT_LiveryIvoryWorn` | `material/belmontetrain/second-class-lod2` (material-instance) | SM_BT_SecondClass_LOD2.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD2/M_BT_WindowInteriorSecondClass` | `material/belmontetrain/second-class-lod2` (material-instance) | SM_BT_SecondClass_LOD2.glb, parent `MI_Default_Opaque` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD2/M_BT_Rubber` | `material/belmontetrain/second-class-lod2` (material-instance) | SM_BT_SecondClass_LOD2.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_SecondClass/LOD2/M_BT_RoofWorn` | `material/belmontetrain/second-class-lod2` (material-instance) | SM_BT_SecondClass_LOD2.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD0/M_BT_EndDark` | `material/belmontetrain/tender-lod0` (material-instance) | SM_BT_Tender_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD0/M_BT_Brass` | `material/belmontetrain/tender-lod0` (material-instance) | SM_BT_Tender_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD0/M_BT_LocoBlack` | `material/belmontetrain/tender-lod0` (material-instance) | SM_BT_Tender_LOD0.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD0/M_BT_Undercarriage` | `material/belmontetrain/tender-lod0` (material-instance) | SM_BT_Tender_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD0/M_BT_Steel` | `material/belmontetrain/tender-lod0` (material-instance) | SM_BT_Tender_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD0/M_BT_Rubber` | `material/belmontetrain/tender-lod0` (material-instance) | SM_BT_Tender_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD0/M_BT_Crest` | `material/belmontetrain/tender-lod0` (material-instance) | SM_BT_Tender_LOD0.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD0/M_BT_Coal` | `material/belmontetrain/tender-lod0` (material-instance) | SM_BT_Tender_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD0/M_BT_Parquet` | `material/belmontetrain/tender-lod0` (material-instance) | SM_BT_Tender_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD0/M_BT_IronBlack` | `material/belmontetrain/tender-lod0` (material-instance) | SM_BT_Tender_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD0/M_BT_Roof` | `material/belmontetrain/tender-lod0` (material-instance) | SM_BT_Tender_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD0/M_BT_LiningRed` | `material/belmontetrain/tender-lod0` (material-instance) | SM_BT_Tender_LOD0.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD1/M_BT_EndDark` | `material/belmontetrain/tender-lod1` (material-instance) | SM_BT_Tender_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD1/M_BT_Brass` | `material/belmontetrain/tender-lod1` (material-instance) | SM_BT_Tender_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD1/M_BT_LocoBlack` | `material/belmontetrain/tender-lod1` (material-instance) | SM_BT_Tender_LOD1.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD1/M_BT_Undercarriage` | `material/belmontetrain/tender-lod1` (material-instance) | SM_BT_Tender_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD1/M_BT_Steel` | `material/belmontetrain/tender-lod1` (material-instance) | SM_BT_Tender_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD1/M_BT_Rubber` | `material/belmontetrain/tender-lod1` (material-instance) | SM_BT_Tender_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD1/M_BT_Crest` | `material/belmontetrain/tender-lod1` (material-instance) | SM_BT_Tender_LOD1.glb, parent `MI_Default_Blend_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD1/M_BT_Coal` | `material/belmontetrain/tender-lod1` (material-instance) | SM_BT_Tender_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD1/M_BT_Parquet` | `material/belmontetrain/tender-lod1` (material-instance) | SM_BT_Tender_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD1/M_BT_IronBlack` | `material/belmontetrain/tender-lod1` (material-instance) | SM_BT_Tender_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD1/M_BT_Roof` | `material/belmontetrain/tender-lod1` (material-instance) | SM_BT_Tender_LOD1.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD2/M_BT_LiveryBlue` | `material/belmontetrain/tender-lod2` (material-instance) | SM_BT_Tender_LOD2.glb, parent `MI_ClearCoat_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD2/M_BT_Coal` | `material/belmontetrain/tender-lod2` (material-instance) | SM_BT_Tender_LOD2.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD2/M_BT_Parquet` | `material/belmontetrain/tender-lod2` (material-instance) | SM_BT_Tender_LOD2.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |
| `/Game/BelmonteTrain/Source/SM_BT_Tender/LOD2/M_BT_Undercarriage` | `material/belmontetrain/tender-lod2` (material-instance) | SM_BT_Tender_LOD2.glb, parent `MI_Default_Opaque_DS` | all checked facts are in the bytes | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |

### Brine Cove plants and city tree residuals (72 packages): determined, planned, waiting on two importer steps

Families: the nine `adopted/brinecove/plant-*` records (36 packages, `/Game/Brinecove/Meshes/SM_BC_Plant_*`) and
`adopted/experiments/citytrees` (36 packages: 12 `HD_*_v4` LOD chains and 24 `lods/` LOD levels). The planner is
`tools/migrate/plant_sources.py` (plan mode by default; `--table`; `--paths`; `--claim TASK`, one journaled write, not run).
Plan mode reads the donor (`$YV2_DONOR_BUILD`, the build folder) and the repository and writes nothing.

**Origins (checked against the donor).**

- **Plants (36).** `brinecove/build-report.json` names each mesh's GLB with its sha256 (all 36 match on disk). The donor
  imports the GLB with its slot materials (`MI_BC_*`, owned by `adopted/brinecove/materials`), full-precision UVs for
  non-terrain, and runs `generate_lods` with a fixed plan (import_brinecove.py): 100/45/20/8 percent at screens
  1/0.3/0.12/0.04. That plan is the record's `lods`.
- **City `lods/` (24).** The donor's FBX LOD levels (`city_tree_lods/v4/manifest.json`, every file pinned and present),
  standalone, with the original's material `M_Arcade`.
- **City `_v4` (12).** The recovered citysurfaces original (`prop/citysurfaces/*`, FBX in `src/`) as LOD0, with the two donor
  FBX levels attached (screens 1 / 0.18 / 0.07). The record is that `lod_chain`.

**The read agrees with the plan on all 72 packages** (`docs/inventory/plants-and-city-tree-read.json`, the evidence of
`report_meshes.py`; `plant_sources.disagreements` is empty, and a test pins it).

- Slots: every package's saved slot materials are the planned ones, in order. LOD0 uses every slot.
- LOD0 triangles equal the donor's report for every package, and each `_v4` chain's triangles and screens equal its piece's
  manifest numbers.
- Plants: four levels at screens 1/0.3/0.12/0.04. The triangle counts fall with each level (UE's reduction is not linear on
  these small meshes, so the check is "never grows", not the percent); some levels keep their sections only where the mesh
  still has triangles.
- Collision: a plant reads one convex hull with the default trace, which is the importer's default for a record that
  states no collision; a `lods/` level reads none, as planned; each `_v4` reads its original's hull count (2, 1 or 0, copied
  from the original record) and the `simple_and_complex` trace.

The first comparison showed disagreements; they were mistakes in my comparison (a shared triangle list for every `_v4`, and a
linear ratio test), not in the plan. No record changed.

**Determined, by package:**

- **24 `lods/`:** determined; the importer path already exists. Ready for the claimed import.
- **36 plants:** determined; the import needs the new-package LOD step (`import_asset.py`, implemented, not run).
- **12 `_v4`:** determined; the import needs the FBX chain-level step (`import_asset.py`, implemented, not run).

So 72 of 72 are determined. 48 wait on the editor run of the two steps.

**The two importer steps (implemented; pure rules in `import_settings.py` and tested; the Unreal calls not run):**

1. A new package takes its record's `lods` reduction plan (`reduction_plan`). `preserve()` restores a chain only for a
   package that already had one.
2. A `lod_chain` level is imported by its own file's importer (`level_kind`): an FBX with LOD0's options (legacy when the
   record says so), a glTF or GLB as before.

**Claimed sequence for the import** (every file below is in `scratchpad/island/trainreads`):

1. Claim TASK with `--scope` for each line of `plants-scopes.txt` (21: nine `shared/brinecove/plant-*` and
   `shared/experiments/citytrees`, the `asset/adopted/*` scope of each adopted record, and `region/w09-brinecove` for the 51
   saved-object records that name a plant). Add `--path` for each line of `plants-paths.txt` (312: the 240 claim paths and
   the `verified.json` the import writes for the 72 records), and `--lock-path` for each line of `plants-locks.txt` (360: the
   five files `.uasset .uexp .ubulk .umap .uptnl` of each of the 72 packages).
2. `uv run python games/yorimichi_v2/tools/migrate/plant_sources.py --claim TASK` (the journaled move; the 72 records, the
   adopted records' outputs and `units.json`).
3. Editor run of the two steps, then the claimed import: `tools/import/run.py` with the 24 `lods/` ids first, then the 36
   plant ids and 12 `_v4` ids, each `--plan` first, then `--claim TASK`.
4. Read again with `report_meshes.py` on the same 72 packages, and compare with `plant_sources.disagreements`.

**Open, before step 1:** whether the claims service accepts the `asset/adopted/brinecove/*` scope for the brinecove
`units.json` write (the train's list did not need that case); the region scope must be held for the 51 saved-object records.

**Blockers, in order:** (1) the editor run of the two importer steps; (2) the claim and move; (3) `check.py`: a generated
record without `verified.json` is fatal until its import runs, so the claim must land with the import.

**Native read (already run, read-only `editor.run`, nothing saved), and the command to repeat it:**

```sh
V2_EDITOR_READ_ONLY=1 V2_EDITOR_SCRIPT=$PWD/games/yorimichi_v2/unreal/Scripts/report_meshes.py \
  V2_REPORT_PACKAGES="$(tr '\n' ' ' < $PWD/games/yorimichi_v2/docs/inventory/plants-and-city-tree-packages.txt)" \
  V2_REPORT_OUT=$PWD/build/yorimichi_v2/reports/plants-and-city-trees.json \
  ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi_v2 editor.run
```

Per package (generated by `plant_sources.py --table`):

| Package | Planned record | Donor origin and evidence | Committed bytes | Status |
|---|---|---|---|---|
| `/Game/Brinecove/Meshes/SM_BC_Plant_Broad0` | `prop/brinecove/plant-broad0` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Broad0.glb sha256 `25e37ee00e…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Broad1` | `prop/brinecove/plant-broad1` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Broad1.glb sha256 `0e2b77f44f…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Broad2` | `prop/brinecove/plant-broad2` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Broad2.glb sha256 `966f57cb0e…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Broad3` | `prop/brinecove/plant-broad3` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Broad3.glb sha256 `8650fbe3d4…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Broad4` | `prop/brinecove/plant-broad4` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Broad4.glb sha256 `1af9c42cfe…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Broad5` | `prop/brinecove/plant-broad5` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Broad5.glb sha256 `82db73907c…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Broad6` | `prop/brinecove/plant-broad6` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Broad6.glb sha256 `0473e884d3…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Broad7` | `prop/brinecove/plant-broad7` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Broad7.glb sha256 `c05238a1aa…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Emergent0` | `prop/brinecove/plant-emergent0` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Emergent0.glb sha256 `a696b6f601…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Emergent1` | `prop/brinecove/plant-emergent1` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Emergent1.glb sha256 `77c77d1608…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Emergent2` | `prop/brinecove/plant-emergent2` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Emergent2.glb sha256 `a1d2709b76…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Small0` | `prop/brinecove/plant-small0` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Small0.glb sha256 `6af225de30…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Small1` | `prop/brinecove/plant-small1` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Small1.glb sha256 `065dac95c5…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Small2` | `prop/brinecove/plant-small2` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Small2.glb sha256 `0175e6015f…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Palm0` | `prop/brinecove/plant-palm0` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Palm0.glb sha256 `8ef96351b6…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Palm1` | `prop/brinecove/plant-palm1` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Palm1.glb sha256 `aa66e4bf72…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Palm2` | `prop/brinecove/plant-palm2` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Palm2.glb sha256 `0afb466069…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Palm3` | `prop/brinecove/plant-palm3` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Palm3.glb sha256 `3a7ecd374c…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Palm4` | `prop/brinecove/plant-palm4` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Palm4.glb sha256 `af043950db…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Palm5` | `prop/brinecove/plant-palm5` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Palm5.glb sha256 `55b18e2277…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Shrub0` | `prop/brinecove/plant-shrub0` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Shrub0.glb sha256 `d416496169…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Shrub1` | `prop/brinecove/plant-shrub1` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Shrub1.glb sha256 `bd450387c6…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Shrub2` | `prop/brinecove/plant-shrub2` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Shrub2.glb sha256 `7df66b475d…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Shrub3` | `prop/brinecove/plant-shrub3` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Shrub3.glb sha256 `26cb7983b1…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Shrub4` | `prop/brinecove/plant-shrub4` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Shrub4.glb sha256 `f92f582c89…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Bloom0` | `prop/brinecove/plant-bloom0` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Bloom0.glb sha256 `75544c3a95…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_Bloom1` | `prop/brinecove/plant-bloom1` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_Bloom1.glb sha256 `f4fe338578…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_CoverFern0` | `prop/brinecove/plant-cover-fern0` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_CoverFern0.glb sha256 `d1980dbc42…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_CoverGrass0` | `prop/brinecove/plant-cover-grass0` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_CoverGrass0.glb sha256 `8d298d59ad…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_CoverLeaf0` | `prop/brinecove/plant-cover-leaf0` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_CoverLeaf0.glb sha256 `09a6353f05…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_CoverFern1` | `prop/brinecove/plant-cover-fern1` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_CoverFern1.glb sha256 `9bafa27ac4…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_CoverGrass1` | `prop/brinecove/plant-cover-grass1` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_CoverGrass1.glb sha256 `a158567b84…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_CoverLeaf1` | `prop/brinecove/plant-cover-leaf1` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_CoverLeaf1.glb sha256 `8a5d9fbc39…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_CoverFern2` | `prop/brinecove/plant-cover-fern2` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_CoverFern2.glb sha256 `3cc6b34dbc…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_CoverGrass2` | `prop/brinecove/plant-cover-grass2` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_CoverGrass2.glb sha256 `642ea3b995…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Brinecove/Meshes/SM_BC_Plant_CoverLeaf2` | `prop/brinecove/plant-cover-leaf2` | GLB LOD0 and the donor generate_lods plan; src/SM_BC_Plant_CoverLeaf2.glb sha256 `814a87df2e…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the new-package LOD step |
| `/Game/Experiments/CityTrees/v4/lods/HD_ArcadeTree_LOD1_cell_-1_-1` | `prop/citytrees/hd-arcade-tree-lod1-cell-m1-m1` | donor FBX level (standalone); src/HD_ArcadeTree_LOD1_cell_-1_-1.fbx sha256 `1eaf873299…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); ready for the claimed import |
| `/Game/Experiments/CityTrees/v4/lods/HD_ArcadeTree_LOD2_cell_-1_-1` | `prop/citytrees/hd-arcade-tree-lod2-cell-m1-m1` | donor FBX level (standalone); src/HD_ArcadeTree_LOD2_cell_-1_-1.fbx sha256 `096675bc52…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); ready for the claimed import |
| `/Game/Experiments/CityTrees/v4/HD_ArcadeTree_cell_-1_-1_v4` | `prop/citytrees/hd-arcade-tree-cell-m1-m1-v4` | citysurfaces original FBX and two donor FBX levels; src/HD_ArcadeTree_cell_-1_-1.fbx sha256 `95947173a1…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the FBX chain-level step |
| `/Game/Experiments/CityTrees/v4/lods/HD_ArcadeTree_LOD1_cell_-1_0` | `prop/citytrees/hd-arcade-tree-lod1-cell-m1-0` | donor FBX level (standalone); src/HD_ArcadeTree_LOD1_cell_-1_0.fbx sha256 `c28556e3a1…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); ready for the claimed import |
| `/Game/Experiments/CityTrees/v4/lods/HD_ArcadeTree_LOD2_cell_-1_0` | `prop/citytrees/hd-arcade-tree-lod2-cell-m1-0` | donor FBX level (standalone); src/HD_ArcadeTree_LOD2_cell_-1_0.fbx sha256 `f1a0067715…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); ready for the claimed import |
| `/Game/Experiments/CityTrees/v4/HD_ArcadeTree_cell_-1_0_v4` | `prop/citytrees/hd-arcade-tree-cell-m1-0-v4` | citysurfaces original FBX and two donor FBX levels; src/HD_ArcadeTree_cell_-1_0.fbx sha256 `382f466769…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the FBX chain-level step |
| `/Game/Experiments/CityTrees/v4/lods/HD_ArcadeTree_LOD1_cell_0_-1` | `prop/citytrees/hd-arcade-tree-lod1-cell-0-m1` | donor FBX level (standalone); src/HD_ArcadeTree_LOD1_cell_0_-1.fbx sha256 `e7fdc9448c…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); ready for the claimed import |
| `/Game/Experiments/CityTrees/v4/lods/HD_ArcadeTree_LOD2_cell_0_-1` | `prop/citytrees/hd-arcade-tree-lod2-cell-0-m1` | donor FBX level (standalone); src/HD_ArcadeTree_LOD2_cell_0_-1.fbx sha256 `b2e57992d0…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); ready for the claimed import |
| `/Game/Experiments/CityTrees/v4/HD_ArcadeTree_cell_0_-1_v4` | `prop/citytrees/hd-arcade-tree-cell-0-m1-v4` | citysurfaces original FBX and two donor FBX levels; src/HD_ArcadeTree_cell_0_-1.fbx sha256 `b0311507d3…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the FBX chain-level step |
| `/Game/Experiments/CityTrees/v4/lods/HD_ArcadeTree_LOD1_cell_0_0` | `prop/citytrees/hd-arcade-tree-lod1-cell-0-0` | donor FBX level (standalone); src/HD_ArcadeTree_LOD1_cell_0_0.fbx sha256 `06f1914db6…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); ready for the claimed import |
| `/Game/Experiments/CityTrees/v4/lods/HD_ArcadeTree_LOD2_cell_0_0` | `prop/citytrees/hd-arcade-tree-lod2-cell-0-0` | donor FBX level (standalone); src/HD_ArcadeTree_LOD2_cell_0_0.fbx sha256 `0ad2b29018…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); ready for the claimed import |
| `/Game/Experiments/CityTrees/v4/HD_ArcadeTree_cell_0_0_v4` | `prop/citytrees/hd-arcade-tree-cell-0-0-v4` | citysurfaces original FBX and two donor FBX levels; src/HD_ArcadeTree_cell_0_0.fbx sha256 `f783788fc7…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the FBX chain-level step |
| `/Game/Experiments/CityTrees/v4/lods/HD_PlazaTreeGold_LOD1_cell_-1_-1` | `prop/citytrees/hd-plaza-tree-gold-lod1-cell-m1-m1` | donor FBX level (standalone); src/HD_PlazaTreeGold_LOD1_cell_-1_-1.fbx sha256 `5e25778d93…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); ready for the claimed import |
| `/Game/Experiments/CityTrees/v4/lods/HD_PlazaTreeGold_LOD2_cell_-1_-1` | `prop/citytrees/hd-plaza-tree-gold-lod2-cell-m1-m1` | donor FBX level (standalone); src/HD_PlazaTreeGold_LOD2_cell_-1_-1.fbx sha256 `248d7b6c0d…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); ready for the claimed import |
| `/Game/Experiments/CityTrees/v4/HD_PlazaTreeGold_cell_-1_-1_v4` | `prop/citytrees/hd-plaza-tree-gold-cell-m1-m1-v4` | citysurfaces original FBX and two donor FBX levels; src/HD_PlazaTreeGold_cell_-1_-1.fbx sha256 `138844eab6…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the FBX chain-level step |
| `/Game/Experiments/CityTrees/v4/lods/HD_PlazaTreeGold_LOD1_cell_-1_0` | `prop/citytrees/hd-plaza-tree-gold-lod1-cell-m1-0` | donor FBX level (standalone); src/HD_PlazaTreeGold_LOD1_cell_-1_0.fbx sha256 `49c08587ca…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); ready for the claimed import |
| `/Game/Experiments/CityTrees/v4/lods/HD_PlazaTreeGold_LOD2_cell_-1_0` | `prop/citytrees/hd-plaza-tree-gold-lod2-cell-m1-0` | donor FBX level (standalone); src/HD_PlazaTreeGold_LOD2_cell_-1_0.fbx sha256 `a895748bd5…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); ready for the claimed import |
| `/Game/Experiments/CityTrees/v4/HD_PlazaTreeGold_cell_-1_0_v4` | `prop/citytrees/hd-plaza-tree-gold-cell-m1-0-v4` | citysurfaces original FBX and two donor FBX levels; src/HD_PlazaTreeGold_cell_-1_0.fbx sha256 `63498750f7…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the FBX chain-level step |
| `/Game/Experiments/CityTrees/v4/lods/HD_PlazaTreeGold_LOD1_cell_0_-1` | `prop/citytrees/hd-plaza-tree-gold-lod1-cell-0-m1` | donor FBX level (standalone); src/HD_PlazaTreeGold_LOD1_cell_0_-1.fbx sha256 `2356c32c00…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); ready for the claimed import |
| `/Game/Experiments/CityTrees/v4/lods/HD_PlazaTreeGold_LOD2_cell_0_-1` | `prop/citytrees/hd-plaza-tree-gold-lod2-cell-0-m1` | donor FBX level (standalone); src/HD_PlazaTreeGold_LOD2_cell_0_-1.fbx sha256 `fbd10b3ca5…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); ready for the claimed import |
| `/Game/Experiments/CityTrees/v4/HD_PlazaTreeGold_cell_0_-1_v4` | `prop/citytrees/hd-plaza-tree-gold-cell-0-m1-v4` | citysurfaces original FBX and two donor FBX levels; src/HD_PlazaTreeGold_cell_0_-1.fbx sha256 `1e19fd0121…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the FBX chain-level step |
| `/Game/Experiments/CityTrees/v4/lods/HD_PlazaTreeGold_LOD1_cell_0_0` | `prop/citytrees/hd-plaza-tree-gold-lod1-cell-0-0` | donor FBX level (standalone); src/HD_PlazaTreeGold_LOD1_cell_0_0.fbx sha256 `351904db5d…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); ready for the claimed import |
| `/Game/Experiments/CityTrees/v4/lods/HD_PlazaTreeGold_LOD2_cell_0_0` | `prop/citytrees/hd-plaza-tree-gold-lod2-cell-0-0` | donor FBX level (standalone); src/HD_PlazaTreeGold_LOD2_cell_0_0.fbx sha256 `6aad231ff0…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); ready for the claimed import |
| `/Game/Experiments/CityTrees/v4/HD_PlazaTreeGold_cell_0_0_v4` | `prop/citytrees/hd-plaza-tree-gold-cell-0-0-v4` | citysurfaces original FBX and two donor FBX levels; src/HD_PlazaTreeGold_cell_0_0.fbx sha256 `b8b31dc513…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the FBX chain-level step |
| `/Game/Experiments/CityTrees/v4/lods/HD_PlazaTreeOrange_LOD1_cell_-1_-1` | `prop/citytrees/hd-plaza-tree-orange-lod1-cell-m1-m1` | donor FBX level (standalone); src/HD_PlazaTreeOrange_LOD1_cell_-1_-1.fbx sha256 `9f87a99772…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); ready for the claimed import |
| `/Game/Experiments/CityTrees/v4/lods/HD_PlazaTreeOrange_LOD2_cell_-1_-1` | `prop/citytrees/hd-plaza-tree-orange-lod2-cell-m1-m1` | donor FBX level (standalone); src/HD_PlazaTreeOrange_LOD2_cell_-1_-1.fbx sha256 `07c9028596…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); ready for the claimed import |
| `/Game/Experiments/CityTrees/v4/HD_PlazaTreeOrange_cell_-1_-1_v4` | `prop/citytrees/hd-plaza-tree-orange-cell-m1-m1-v4` | citysurfaces original FBX and two donor FBX levels; src/HD_PlazaTreeOrange_cell_-1_-1.fbx sha256 `f987edd875…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the FBX chain-level step |
| `/Game/Experiments/CityTrees/v4/lods/HD_PlazaTreeOrange_LOD1_cell_-1_0` | `prop/citytrees/hd-plaza-tree-orange-lod1-cell-m1-0` | donor FBX level (standalone); src/HD_PlazaTreeOrange_LOD1_cell_-1_0.fbx sha256 `80d37dae9a…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); ready for the claimed import |
| `/Game/Experiments/CityTrees/v4/lods/HD_PlazaTreeOrange_LOD2_cell_-1_0` | `prop/citytrees/hd-plaza-tree-orange-lod2-cell-m1-0` | donor FBX level (standalone); src/HD_PlazaTreeOrange_LOD2_cell_-1_0.fbx sha256 `91fde465f6…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); ready for the claimed import |
| `/Game/Experiments/CityTrees/v4/HD_PlazaTreeOrange_cell_-1_0_v4` | `prop/citytrees/hd-plaza-tree-orange-cell-m1-0-v4` | citysurfaces original FBX and two donor FBX levels; src/HD_PlazaTreeOrange_cell_-1_0.fbx sha256 `fdbbea7593…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the FBX chain-level step |
| `/Game/Experiments/CityTrees/v4/lods/HD_PlazaTreeOrange_LOD1_cell_0_-1` | `prop/citytrees/hd-plaza-tree-orange-lod1-cell-0-m1` | donor FBX level (standalone); src/HD_PlazaTreeOrange_LOD1_cell_0_-1.fbx sha256 `905bf27ee0…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); ready for the claimed import |
| `/Game/Experiments/CityTrees/v4/lods/HD_PlazaTreeOrange_LOD2_cell_0_-1` | `prop/citytrees/hd-plaza-tree-orange-lod2-cell-0-m1` | donor FBX level (standalone); src/HD_PlazaTreeOrange_LOD2_cell_0_-1.fbx sha256 `96845685d6…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); ready for the claimed import |
| `/Game/Experiments/CityTrees/v4/HD_PlazaTreeOrange_cell_0_-1_v4` | `prop/citytrees/hd-plaza-tree-orange-cell-0-m1-v4` | citysurfaces original FBX and two donor FBX levels; src/HD_PlazaTreeOrange_cell_0_-1.fbx sha256 `780f5f4d5a…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the FBX chain-level step |
| `/Game/Experiments/CityTrees/v4/lods/HD_PlazaTreeOrange_LOD1_cell_0_0` | `prop/citytrees/hd-plaza-tree-orange-lod1-cell-0-0` | donor FBX level (standalone); src/HD_PlazaTreeOrange_LOD1_cell_0_0.fbx sha256 `b15629b2eb…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); ready for the claimed import |
| `/Game/Experiments/CityTrees/v4/lods/HD_PlazaTreeOrange_LOD2_cell_0_0` | `prop/citytrees/hd-plaza-tree-orange-lod2-cell-0-0` | donor FBX level (standalone); src/HD_PlazaTreeOrange_LOD2_cell_0_0.fbx sha256 `2ea57c81e3…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); ready for the claimed import |
| `/Game/Experiments/CityTrees/v4/HD_PlazaTreeOrange_cell_0_0_v4` | `prop/citytrees/hd-plaza-tree-orange-cell-0-0-v4` | citysurfaces original FBX and two donor FBX levels; src/HD_PlazaTreeOrange_cell_0_0.fbx sha256 `372286e4ed…` | slot materials are in the bytes; LOD chain and triangles need the read | determined by the read (agrees); waits on the editor run of the FBX chain-level step |

## Japan materials: source closure (leaves imported; the rest read-confirmed)

The seven adopted records `adopted/japan/materials/{bark, buildings, foliage, ground, rock-concrete, sky-wind, water}`
hold 41 packages, all `MI_*` material instances in `/Game/Japan/Materials`, all `authority = "editor"`. They have no
`[[sources]]` and no recipe, and they stay that way: adding sources would make `check.py` report `STALE_IMPORT`. The
two used leaves (`MI_LeafAmber`, `MI_LeafCrimson`) were moved out of `foliage` into their own `material-instance` records,
`assets/material/japan/leaf-{amber,crimson}`, which carry a recipe (see "Recipe for the two used leaves").

Result: **0** imported textures or meshes (a). **41** generator-built instances (b): **Prepared, read-confirmed**,
the saved parent and parameters match the donor script on every row. **2** used leaf instances
(`MI_LeafAmber`, `MI_LeafCrimson`): **Imported and verified** on 2026-11-10 from their recipe under claim task
`LEAVES`. A read-only parameter read before and after the import is identical (parent `M_Foliage`, only `Tex`
overridden, effective `FadeMode`, `CutScale` and `Tint` unchanged), and `check.py` accepts both records. No row is
Blocked. The 41 (b) rows are not verified closure: their read confirms parameters only.

Method. Each saved `.uasset` matches its `verified.json` sha256 in the full donor checkout and in the fix checkout
(43 of 43). Parent and texture references were read from those bytes with `LC_ALL=C grep -a`. Every (b) package is
made by `material_assets.instance(...)` (or the `"MI_" + k` loop in `build_materials`) inside the donor's Unreal
editor run, so the saved package is the only byte-level original: a rerun needs an editor, and verifying means an
editor read of the saved parent and texture values against the generator, not an import. Parent masters (`M_Painted`, `M_Foliage`, `M_Grass`,
`M_Sky`, `M_ForestGround`, `M_CoastRock`, `M_NorthMountains`) belong to other records (`base-materials`, the
ground and mountain generators) and are not counted here.

Donor generators (repo-relative under `games/yorimichi/`, sha256 of the file):

| Script | sha256 | Packages built |
|---|---|---|
| `games/yorimichi/unreal/Scripts/shared_materials.py` | `8cf144f9752bffe771bbddfe984091ad4c288259bc00abba4a64fad5d6678720` | builds 32 instances (`build_materials`); `main` imports the textures from `build/yorimichi/textures` and saves |
| `games/yorimichi/unreal/Scripts/material_assets.py` | `4f48db1203b44c5abca932291ce323f7247a655753167a5f72dfefe5ac4be50f` | `instance`, `master` helpers used by the above |
| `games/yorimichi/unreal/Scripts/forest_ground.py` | `90c1256d9cf521e484a6d1ed8027056849a14ab3f4fc1ddaebb275d563d8f4f3` | MI_Coast and MI_CoastRock |
| `games/yorimichi/unreal/Scripts/import_island_world.py` | `33521dfe75b50a9a3e451862de0d1a86e8f6810f116e75428a6eef1d008dabb5` | MI_FarForest |
| `games/yorimichi/unreal/Scripts/mountain_material.py` | `21238502c415c255cb5081801368871b0c96e9d81b1315812ae1a63d39087185` | MI_NorthRockCaps |
| `games/yorimichi/unreal/Scripts/import_southwest.py` | `2c7377af142b19e5bd3457a93f7fa19bc4526934b2f66b15409a53d143180e45` | MI_Sand |
| `games/yorimichi/unreal/Scripts/import_forest.py` | `54df366cd7ddcd3cc3900352e055c5b1c4522cf4f2affaff0fec3ab4c1b2f4f2` | MI_LeafOak, MI_LeafOlive, MI_LeafCypress, MI_LeafStonePine (texture from the next row) |
| `games/yorimichi/tools/forest_textures.py` | `0bd7bb94358294c11919ba4b0da0ff2a01a6ce3de34c39c27fb4cdf731a42d39` | Tuscan leaf atlases `T_Leaf*.png` in `build/yorimichi/forest/textures` |
| `games/yorimichi/world/gen_textures.py` | `5b8b93fe242873529e1a781a994fd3be9309a6aa3af56fb3b7d07b971e27aaf6` | shared texture PNG/JPGs in `build/yorimichi/textures` |
| `games/yorimichi/unreal/Scripts/see_through.py` | `9d7da40163a6e4023d91e8fc2aaacdd2578bf07ef02f05b4e10dcc1c4c8fd105` | also names MI_Paint; not checked further, so not counted as a generator |
| `games/yorimichi/unreal/Scripts/sea_look.py` | `ffae53cded2bb461534c88c100bc75d3f93ec3bf396eb303e5d4ec3ad4dbb4fa` | MI_Sky tint only; not counted as a generator |

Texture references (the `T_*` names the instances point at) and their donor inputs. These textures are imported by
the generators above and are owned by other records; they are listed for the native read. Textures are not counted
in the 43:

| Texture | Donor file (repo-relative) | sha256 |
|---|---|---|
| `T_bark` | `build/yorimichi/textures/T_bark.jpg` | `8b6caef1e0c3fb3554d3c974f709cc840c642d33d0c1c11119bbd91eea2c71cb` |
| `T_bark_olive` | `build/yorimichi/textures/T_bark_olive.jpg` | `fab79211380649a5649fa68577105a722f08e96cc4e110068a263e9ba7146c20` |
| `T_concrete` | `build/yorimichi/textures/T_concrete.jpg` | `0f28429a59f164909382e5b579f2fd8606311656a95f162c922bb24c666aeaac` |
| `T_ground` | `build/yorimichi/textures/T_ground.jpg` | `601b2e42035dcb8ae8354ce7036bf60aeb55fa99f913d40df2dfbd8af0b9ef72` |
| `T_road` | `build/yorimichi/textures/T_road.jpg` | `935bbf46af273405b8cecd0c3504c68d7f52bd0b73908a46464aed8ad7b6e998` |
| `T_rooftile` | `build/yorimichi/textures/T_rooftile.jpg` | `7dad0f942feaaca5be55df0487478f3e57f0f18fab2d56e7440f9694702882b5` |
| `T_water` | `build/yorimichi/textures/T_water.jpg` | `ac69c14388f5a9fc83b0cc02c8b686d42c717afaac802bb4f5b4f3a0a7cfd62a` |
| `T_white` | `build/yorimichi/textures/T_white.png` | `b68de61392c506377e0d673fa36e239a47b67e603bdcb9cbf61d4ddbcd9722ff` |
| `T_flower` | `build/yorimichi/textures/T_flower.png` | `18cf510c7e5a668bd1c61f6da0ef834da39e4c8420841daf631d1e634f85ce70` |
| `T_grass` | `build/yorimichi/textures/T_grass.png` | `6340efa1d535359fc73b696c9c38cade1e3c4612dc2a90b7c69c3dbcc757c751` |
| `T_litter` | `build/yorimichi/textures/T_litter.png` | `2df4362cc0fc5af0807fa14f7f6c45512d4524452d7e7772137060f1399e4e74` |
| `T_leaf_broad` | `build/yorimichi/textures/T_leaf_broad.png` | `5886d1372e5d9d73003b890194cdac1fa9b71cbada7549db1afcc22bfb46768b` |
| `T_leaf_cedar` | `build/yorimichi/textures/T_leaf_cedar.png` | `be0df8b44a945c51723a19d1080d11c8117ba820c51a9582d965a30ffac7c059` |
| `T_leaf_pine` | `build/yorimichi/textures/T_leaf_pine.png` | `facb38e38d197f82338716774d4948bab09b0c763b99ade0b16a3c35fd6e1f23` |
| `T_leaf_ochre` | `build/yorimichi/textures/T_leaf_ochre.png` | `9c4910d49f8ec22d1c6c3b7b2a8af17657bd4643fb0256382454123dad637ee6` |
| `T_leaf_ochre_small` | `build/yorimichi/textures/T_leaf_ochre_small.png` | `0b62cc34ffa24206c070b1c93a6e4f5d6213be73d1a1c036da99f56f4d96dc77` |
| `T_leaf_maple` | `build/yorimichi/textures/T_leaf_maple.png` | `808043ab4180a807d9b932f33079d47b3c2cd1e1af786a74d9d970a68c32a710` |
| `T_leaf_ginkgo` | `build/yorimichi/textures/T_leaf_ginkgo.png` | `137850cd79e62431304b300713911aa141f7d857291c53871bf2aa8c86e142a9` |
| `T_leaf_small` | `build/yorimichi/textures/T_leaf_small.png` | `914439b3798347108a1766bc9211faaa68646e077c66f94f86135f15b735ff51` |
| `T_LeafOak` | `build/yorimichi/forest/textures/T_LeafOak.png` | `1b2dbdbc6e2a048ec7c788e8b0ecc9ebd07309578775cab628ca765a85f8a190` |
| `T_LeafOlive` | `build/yorimichi/forest/textures/T_LeafOlive.png` | `0a7910a4b61649cc78f55a8ea245472e9fff99ff0a88838dfe824e4f74d04dff` |
| `T_LeafCypress` | `build/yorimichi/forest/textures/T_LeafCypress.png` | `094f0b2c7405ac001179e4a83ebf82374e30e81f1b685f18eb4a7ff40c9b32df` |
| `T_LeafStonePine` | `build/yorimichi/forest/textures/T_LeafStonePine.png` | `62505bc2b129575966cb7ac1dcc542b33139cd5ff6b9453f060aa945c35020dc` |
| `T_leaf_amber (two leaf recipes)` | `build/yorimichi/treehouse/trees/T_leaf_amber.png` | `e9614e6d278c200bfca7a2233ca141760259d3c0f473ae92526c0b51b25fb9c5` |
| `T_leaf_crimson (two leaf recipes)` | `build/yorimichi/treehouse/trees/T_leaf_crimson.png` | `406c9d466b7d479d26003e03c05a2b0134107833779e64eb1a86b19923fef309` |

Per-package table. Status: **Prepared, read-confirmed** (a generator row whose saved parent and parameters match the
donor script in the editor read below), or **Prepared, recipe recorded** (a used leaf, with its recipe below).
Parent and texture references come from the real package bytes:

| Package | Record | Status | Parent | Texture refs | Candidate original |
|---|---|---|---|---|---|
| `MI_Bark` | `bark` | Prepared, read-confirmed | `M_Painted` | `T_bark` | shared_materials.py build_materials; base-property override not in the read |
| `MI_BarkOlive` | `bark` | Prepared, read-confirmed | `M_Painted` | `T_bark_olive` | shared_materials.py build_materials; base-property override not in the read |
| `MI_BarkTuscan` | `bark` | Prepared, read-confirmed | `M_Painted` | `T_bark_olive` | shared_materials.py build_materials; base-property override not in the read |
| `MI_Lattice` | `buildings` | Prepared, read-confirmed | `M_Painted` | `T_white` | shared_materials.py build_materials; base-property override not in the read |
| `MI_Metal` | `buildings` | Prepared, read-confirmed | `M_Painted` | `T_white` | shared_materials.py build_materials; base-property override not in the read |
| `MI_Paint` | `buildings` | Prepared, read-confirmed | `M_Painted` | `T_white` | shared_materials.py build_materials; base-property override not in the read |
| `MI_Plaster` | `buildings` | Prepared, read-confirmed | `M_Painted` | `T_white` | shared_materials.py build_materials; base-property override not in the read |
| `MI_RoofTile` | `buildings` | Prepared, read-confirmed | `M_Painted` | `T_rooftile` | shared_materials.py build_materials; base-property override not in the read |
| `MI_Tile` | `buildings` | Prepared, read-confirmed | `M_Painted` | `T_white` | shared_materials.py build_materials; base-property override not in the read |
| `MI_Vermilion` | `buildings` | Prepared, read-confirmed | `M_Painted` | `T_white` | shared_materials.py build_materials; base-property override not in the read |
| `MI_Wood` | `buildings` | Prepared, read-confirmed | `M_Painted` | `T_white` | shared_materials.py build_materials; base-property override not in the read |
| `MI_FarForest` | `foliage` | Prepared, read-confirmed | `M_ForestGround` | none | main |
| `MI_Feather` | `foliage` | Prepared, read-confirmed | `M_Painted` | `T_white` | shared_materials.py build_materials |
| `MI_FeatherDark` | `foliage` | Prepared, read-confirmed | `M_Painted` | `T_white` | shared_materials.py build_materials |
| `MI_Flower` | `foliage` | Prepared, read-confirmed | `M_Foliage` | `T_flower` | shared_materials.py build_materials |
| `MI_Grass` | `foliage` | Prepared, read-confirmed | `M_Grass` | `T_grass` | shared_materials.py build_materials |
| `MI_LeafAmber` | `material/japan/leaf-amber` | Prepared, recipe recorded | `M_Foliage` | `T_leaf_amber` | recipe below (no donor builder) |
| `MI_LeafBroad` | `foliage` | Prepared, read-confirmed | `M_Foliage` | `T_leaf_broad` | shared_materials.py build_materials |
| `MI_LeafCedar` | `foliage` | Prepared, read-confirmed | `M_Foliage` | `T_leaf_cedar` | shared_materials.py build_materials |
| `MI_LeafCrimson` | `material/japan/leaf-crimson` | Prepared, recipe recorded | `M_Foliage` | `T_leaf_crimson` | recipe below (no donor builder) |
| `MI_LeafCypress` | `foliage` | Prepared, read-confirmed | `M_Foliage` | `T_LeafCypress` | import_forest.py (textures from tools/forest_textures.py) |
| `MI_LeafGinkgo` | `foliage` | Prepared, read-confirmed | `M_Foliage` | `T_leaf_ginkgo` | shared_materials.py build_materials |
| `MI_LeafMaple` | `foliage` | Prepared, read-confirmed | `M_Foliage` | `T_leaf_maple` | shared_materials.py build_materials |
| `MI_LeafOak` | `foliage` | Prepared, read-confirmed | `M_Foliage` | `T_LeafOak` | import_forest.py (textures from tools/forest_textures.py) |
| `MI_LeafOchre` | `foliage` | Prepared, read-confirmed | `M_Foliage` | `T_leaf_ochre` | shared_materials.py build_materials |
| `MI_LeafOchreSmall` | `foliage` | Prepared, read-confirmed | `M_Foliage` | `T_leaf_ochre_small` | shared_materials.py build_materials |
| `MI_LeafOlive` | `foliage` | Prepared, read-confirmed | `M_Foliage` | `T_LeafOlive` | import_forest.py (textures from tools/forest_textures.py) |
| `MI_LeafPine` | `foliage` | Prepared, read-confirmed | `M_Foliage` | `T_leaf_pine` | shared_materials.py build_materials |
| `MI_LeafSmall` | `foliage` | Prepared, read-confirmed | `M_Foliage` | `T_leaf_small` | shared_materials.py build_materials |
| `MI_LeafStonePine` | `foliage` | Prepared, read-confirmed | `M_Foliage` | `T_LeafStonePine` | import_forest.py (textures from tools/forest_textures.py) |
| `MI_Ground` | `ground` | Prepared, read-confirmed | `M_Painted` | `T_ground` | shared_materials.py build_materials |
| `MI_Litter` | `ground` | Prepared, read-confirmed | `M_Foliage` | `T_litter` | shared_materials.py build_materials |
| `MI_Moss` | `ground` | Prepared, read-confirmed | `M_Painted` | `T_white` | shared_materials.py build_materials |
| `MI_Road` | `ground` | Prepared, read-confirmed | `M_Painted` | `T_road` | shared_materials.py build_materials |
| `MI_Sand` | `ground` | Prepared, read-confirmed | `M_Painted` | `T_white` | sand_material |
| `MI_Coast` | `rock-concrete` | Prepared, read-confirmed | `M_ForestGround` | none | coast_instance |
| `MI_CoastRock` | `rock-concrete` | Prepared, read-confirmed | `M_CoastRock` | none | coast_rock_instance |
| `MI_Concrete` | `rock-concrete` | Prepared, read-confirmed | `M_Painted` | `T_concrete` | shared_materials.py build_materials; base-property override not in the read |
| `MI_NorthRockCaps` | `rock-concrete` | Prepared, read-confirmed | `M_NorthMountains` | none | rock_material |
| `MI_Rock` | `rock-concrete` | Prepared, read-confirmed | `M_Painted` | `T_white` | shared_materials.py build_materials |
| `MI_Stone` | `rock-concrete` | Prepared, read-confirmed | `M_Painted` | `T_white` | shared_materials.py build_materials; base-property override not in the read |
| `MI_Sky` | `sky-wind` | Prepared, read-confirmed | `M_Sky` | none | shared_materials.py build_materials |
| `MI_Water` | `water` | Prepared, read-confirmed | `M_Painted` | `T_water` | shared_materials.py build_materials |

Used leaves: `MI_LeafAmber` and `MI_LeafCrimson` are **used**: `assets/prop/japan-kit/tree-canopy-amber/asset.toml`
and `tree-canopy-crimson/asset.toml` (recipe `slot_map`, line 20) bind their `LeafMaple` slot to them. No donor script
builds them, so the original script is not found. Their image inputs are the treehouse generator's `T_leaf_amber.png`
and `T_leaf_crimson.png` (`world/regions/treehouse/trees.py`, listed above). They are not relabelled as editor
originals. Their texture packages `T_leaf_amber` and `T_leaf_crimson` are already owned by the editor-saved record
`adopted/japan/textures/leaf-atlases`, so the leaf records reference that record as an input and pin no PNG of their
own (committing the derived PNG would need its rights settled first). That record's sources are the Tuscan leaf JPGs,
not these two PNGs, so whether the saved `T_leaf_*` bytes match the PNGs above is not verified.

### Recipe for the two used leaves

`material-instance` now has a recipe schema (`tools/content/records.py`, `material_settings`): `[recipe]` with
`importer = "material-instance"` and version 2, and `[recipe.settings]` with `parent` (a `/Game` package), `textures`
(parameter to `/Game` texture package), `scalars` and `vectors`. Every package it reads must be owned by one of its
`input_dependencies`. The records are `assets/material/japan/leaf-amber/asset.toml` and
`assets/material/japan/leaf-crimson/asset.toml`, with inputs `adopted/japan/materials/base-materials` (the parent) and
`adopted/japan/textures/leaf-atlases` (the texture). Neither has a verified state yet, so `check.py` reports each as
`RECORD_MISSING` and its package as `UNOWNED` until the import below is run. The table is the recipe they state:

| Field | `MI_LeafAmber` | `MI_LeafCrimson` |
|---|---|---|
| Parent | `/Game/Japan/Materials/M_Foliage` | `/Game/Japan/Materials/M_Foliage` |
| Tex (texture parameter) | `/Game/Japan/Textures/T_leaf_amber` | `/Game/Japan/Textures/T_leaf_crimson` |
| Vector and scalar overrides | none | none |
| Texture input (donor) | `build/yorimichi/treehouse/trees/T_leaf_amber.png`, sha256 `e9614e6d278c200bfca7a2233ca141760259d3c0f473ae92526c0b51b25fb9c5` | `build/yorimichi/treehouse/trees/T_leaf_crimson.png`, sha256 `406c9d466b7d479d26003e03c05a2b0134107833779e64eb1a86b19923fef309` |
| Effective (read) | FadeMode 0, CutScale [1,1,2,1], Tint [1,1,1,1]: the parent's defaults | same |

The recipe is the form `import_forest.py` uses for the Tuscan leaves: set the parent to `M_Foliage` and set `Tex` to the
imported texture. It specifies exactly the content of the read. Reproducing it in an editor, and comparing the result
with the accepted packages, is not done.

Editor read. `docs/inventory/japan-materials-read.json` is the output of `unreal/Scripts/report_materials.py`, run as a
read-only `editor.run` (43 rows, 0 errors, nothing saved):

```sh
V2_EDITOR_READ_ONLY=1 V2_EDITOR_SCRIPT=$PWD/games/yorimichi_v2/unreal/Scripts/report_materials.py \
  V2_REPORT_PACKAGES="$(tr '\n' ' ' < $PWD/games/yorimichi_v2/docs/inventory/japan-materials-packages.txt)" \
  V2_REPORT_OUT=$PWD/build/yorimichi_v2/reports/japan-materials.json \
  ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi_v2 editor.run
```

Each generator row was compared with what its donor script sets: parent; `Tex`; `Tint`; the `CutScale` that
`see_through.py` gives `MI_Paint`; `NearGround` on `MI_Coast`; `Caps` on `MI_NorthRockCaps`; `MI_Sand`'s tint; and the
Tuscan leaves' `Tex` only. **Mismatches: none.** The read confirms parameters only. Thirteen rows also carry
base-property overrides that the job does not read: `enable_bark_lod_blend` (foliage_material.py) sets dithered LOD
transition on `MI_Bark`, `MI_BarkOlive` and `MI_BarkTuscan`; `mask_instance` (see_through.py) sets masked blend with
clip 0.5 on `MI_Bark`, `MI_RoofTile`, `MI_Tile`, `MI_Plaster`, `MI_Wood`, `MI_Lattice`, `MI_Vermilion`, `MI_Paint`,
`MI_Metal`, `MI_Stone` and `MI_Concrete`. Those rows say so in the table. The pins are in
`tests/test_japan_materials_read.py`.

Still to do, not run here: (1) an editor reproduction of each generator row, compared with its accepted package;
(2) the leaf import below, compared with the accepted packages; (3) a read of the base-property overrides of the 13
rows; (4) the texture imports listed above, compared with the saved parents. Counts are pinned by
`tests/test_japan_materials_sources.py`; the leaf schema, records and import route by `tests/test_material_records.py`.

Native steps for the two leaves (prepared, not run; each needs an editor, claims and a clean LFS hydrate).
`uv run python games/yorimichi_v2/tools/import/run.py material/japan/leaf-amber material/japan/leaf-crimson --plan`
prints the plan. The import is `tools/import/run.py` with `--claim TASK`: an active claim on scopes
`shared/japan/materials/leaf-amber` and `shared/japan/materials/leaf-crimson`, with the LFS locks on
`unreal/Content/Japan/Materials/MI_LeafAmber.uasset`, `MI_LeafCrimson.uasset` and their companions. The
`adopted/japan/materials/foliage` and `adopted/japan/textures/leaf-atlases` records are read, not written. Before the
import, read the accepted parameters with `report_materials.py` (the editor read above). After it, read them again and
compare both rows with `docs/inventory/japan-materials-read.json`: parent `M_Foliage`, `Tex` the texture, no overrides,
and the same effective values. A record is accepted only once the importer writes its `verified.json`.

Brine Cove's source-preservation route is applied by #787: 148 carved tile records keep their fused original and a
carve selection, and each remainder derives byte-identically (see [sources.md](sources.md)). No accepted package changed.

## Evidence and updates

The counts above were read from canonical `asset.toml` files in the immutable Git tree, excluding files nested
inside another asset's source folder. A loose filesystem glob can include stale/untracked records and donor copies.
`verified.json` and `objects.saved.json` distinguish imported packages from saved placements. Keep changes to this
page and the main inventory in the same content PR; do not mark a family complete from a plan or provisional receipt.

## Small families: source closure plan (planned, not imported)

The ten smaller families of "Source closure still to classify" (90 packages in 25 adopted records) are classified by
`tools/migrate/small_families.py`. Its plan mode reads the committed records, the hydrated bytes (each file matches its
`verified.json` sha256) and the donor. Nothing is imported, claimed or written. Counts are pinned by
`tests/test_small_families.py`.

### Hippodrome (3 records, 23 packages)

Plan: `games/yorimichi_v2/tools/migrate/small_families.py` (plan mode only; `--claim` is refused). Donor checkout read
only (the donor checkout, commit `7eec0f98dd`). Evidence and verdicts for the three records:

- `adopted/hippodrome/loose_files` (4 static meshes): the donor writes these GLBs in `world/regions/hippodrome/build.py`
  and imports them in `unreal/Scripts/import_hippodrome.py:161-177`. The four GLBs are in the donor
  (`build/yorimichi/hippodrome/region/glb/`) with the same bytes as the exports. The static-mesh importer fits: its
  precedent is `prop/hippodrome/lane`, whose committed `src/SM_HD_Lane.glb` (sha256 `1b1558f9…`) equals the donor region
  GLB. Pins (sha256 of the donor GLB, triangles from `build/yorimichi/hippodrome/import-report.json`):

  | Package | GLB sha256 | Triangles | GLB material |
  |---|---|---:|---|
  | `SM_HD_FinishPost` | `123ab4602df5111d…` | 5006 | `HD_FinishPost` |
  | `SM_HD_Grandstand` | `92add5b3492eb839…` | 24940 | `HD_Grandstand` |
  | `SM_HD_JudgesTower` | `ebfe7c40abbd75f5…` | 11779 | `HD_JudgesTower` |
  | `SM_HD_ToteBoard` | `8086362ef6c65c64…` | 11859 | `HD_ToteBoard` |

  The loose packages' bytes name `M_HD_Structure` as their master, so that is the slot material of the recipe. Status:
  **planned**. The four `prop/hippodrome/<part>` records would need the GLBs copied into `src/` (not done here) and a
  claimed native import. The object records `object/hippodrome/{finish-post,grandstand,judges-tower,tote-board}` still
  reference this record, so nothing changes until that import is accepted.
- `adopted/hippodrome/materials` (5 material masters): `import_hippodrome.py:32-33` (SURFACES: grass, dirt, stone, rail)
  and `:60-61` (`M_HD_Structure`). `T_Dirt` and `T_Grass` are owned by `texture/hippodrome/*`. Status: **blocked**: kind
  `material` has no importer, so the graph and parameters need a native read before anything can be recorded.
- `adopted/hippodrome/meshes` (14 packages): the Interchange sub-objects of the same four GLBs (`import_hippodrome.py:102-103`
  puts each GLB in `Meshes/<name>`), with the embedded `Color_<uuid>` textures. The loose meshes reference them (18 files
  under `unreal/Content` name `Hippodrome/Meshes/`). Status: **blocked** until a loose re-import is accepted and a
  referencer check shows nothing else uses them.

Native reads still needed (read-only; each needs an editor and a clean hydrate). The list file is
`docs/inventory/small-families-hippodrome-materials.txt`; the command is the Japan form with `V2_REPORT_PACKAGES` set to
that list, `V2_REPORT_OUT` under `build/yorimichi_v2/reports/`, and `editor.run` as the step.

`report_materials.py` reads material instances; it may not read the masters (`M_HD_*`), so those rows need a master
reader first. No static-mesh reader exists in this tree for the loose meshes or the `Meshes/` sub-objects.

Blockers: the static mesh import (not run, claim needed); master materials have no importer; the `Meshes/` sub-objects
need a referencer proof before any retirement.

- `adopted/hippodrome/loose_files`: generated static mesh (GLB, region/glb). Evidence: donor world/regions/hippodrome/build.py via unreal/Scripts/import_hippodrome.py:161-177. Status: **planned**. static-mesh recipe needs the GLB copied to src/ and a native import; object records still reference this record
- `adopted/hippodrome/materials`: generator master materials M_HD_Structure and M_HD_<surface>. Evidence: import_hippodrome.py:32-33 (SURFACES), :60-61 (M_HD_Structure). Status: **blocked**. no importer for material masters (kind material has no recipe); parameters need a native read
- `adopted/hippodrome/meshes`: Interchange sub-objects of the loose GLB imports. Evidence: import_hippodrome.py:102-103 (Meshes/<name> folder per GLB). Status: **blocked**. referenced by the four loose meshes (18 files under unreal/Content name Hippodrome/Meshes/); retire only after a loose re-import

| Package | Record | Status | Inputs (owner records) | Native read still needed |
|---|---|---|---|---|
| `SM_HD_FinishPost` | `hippodrome/loose_files` | planned | Hippodrome/Meshes/SM_HD_FinishPost/HD_FinishPost, Hippodrome/Meshes/SM_HD_FinishPost/HD_FinishPost | no static-mesh reader in this tree |
| `SM_HD_Grandstand` | `hippodrome/loose_files` | planned | Hippodrome/Meshes/SM_HD_Grandstand/HD_Grandstand, Hippodrome/Meshes/SM_HD_Grandstand/HD_Grandstand | no static-mesh reader in this tree |
| `SM_HD_JudgesTower` | `hippodrome/loose_files` | planned | Hippodrome/Meshes/SM_HD_JudgesTower/HD_JudgesTower, Hippodrome/Meshes/SM_HD_JudgesTower/HD_JudgesTower | no static-mesh reader in this tree |
| `SM_HD_ToteBoard` | `hippodrome/loose_files` | planned | Hippodrome/Meshes/SM_HD_ToteBoard/HD_ToteBoard, Hippodrome/Meshes/SM_HD_ToteBoard/HD_ToteBoard | no static-mesh reader in this tree |
| `M_HD_Dirt` | `hippodrome/materials` | blocked | Hippodrome/Textures/T_Dirt | `report_materials` (material list) |
| `M_HD_Grass` | `hippodrome/materials` | blocked | Hippodrome/Textures/T_Grass | `report_materials` (material list) |
| `M_HD_Rail` | `hippodrome/materials` | blocked | - | `report_materials` (material list) |
| `M_HD_Stone` | `hippodrome/materials` | blocked | - | `report_materials` (material list) |
| `M_HD_Structure` | `hippodrome/materials` | blocked | - | `report_materials` (material list) |
| `Color_c3f66034-a443-44e1-ac12-bc4a9a617bb9` | `hippodrome/meshes` | blocked | Hippodrome/Meshes/SM_HD_FinishPost | no static-mesh reader in this tree |
| `HD_FinishPost` | `hippodrome/meshes` | blocked | Hippodrome/Materials/M_HD_Structure, Hippodrome/Materials/M_HD_Structure, Hippodrome/Meshes/SM_HD_FinishPost ... | no static-mesh reader in this tree |
| `Color_d791cab5-3476-4925-85c1-f4131c7af4b8` | `hippodrome/meshes` | blocked | Hippodrome/Meshes/SM_HD_Grandstand | no static-mesh reader in this tree |
| `HD_Grandstand` | `hippodrome/meshes` | blocked | Hippodrome/Materials/M_HD_Structure, Hippodrome/Materials/M_HD_Structure, Hippodrome/Meshes/SM_HD_Grandstand ... | no static-mesh reader in this tree |
| `HD_Grass` | `hippodrome/meshes` | blocked | Hippodrome/Meshes/SM_HD_Ground | no static-mesh reader in this tree |
| `Color_13d66ee9-7f6a-447a-a77d-ada02b839472` | `hippodrome/meshes` | blocked | Hippodrome/Meshes/SM_HD_JudgesTower | no static-mesh reader in this tree |
| `HD_JudgesTower` | `hippodrome/meshes` | blocked | Hippodrome/Materials/M_HD_Structure, Hippodrome/Materials/M_HD_Structure, Hippodrome/Meshes/SM_HD_JudgesTower ... | no static-mesh reader in this tree |
| `HD_Dirt` | `hippodrome/meshes` | blocked | Hippodrome/Meshes/SM_HD_Track | no static-mesh reader in this tree |
| `HD_Stone` | `hippodrome/meshes` | blocked | Hippodrome/Meshes/SM_HD_Skirt | no static-mesh reader in this tree |
| `HD_Rail` | `hippodrome/meshes` | blocked | Hippodrome/Meshes/SM_HD_Rails | no static-mesh reader in this tree |
| `HD_Stone` | `hippodrome/meshes` | blocked | Hippodrome/Meshes/SM_HD_Skirt | no static-mesh reader in this tree |
| `Color_72c00844-b377-41e6-8796-37d3e46331b9` | `hippodrome/meshes` | blocked | Hippodrome/Meshes/SM_HD_ToteBoard | no static-mesh reader in this tree |
| `HD_ToteBoard` | `hippodrome/meshes` | blocked | Hippodrome/Materials/M_HD_Structure, Hippodrome/Materials/M_HD_Structure, Hippodrome/Meshes/SM_HD_ToteBoard ... | no static-mesh reader in this tree |
| `HD_Dirt` | `hippodrome/meshes` | blocked | Hippodrome/Meshes/SM_HD_Track | no static-mesh reader in this tree |

### Tree house surface materials (5 records, 8 packages)

Donor evidence: `unreal/Scripts/import_treehouse.py:3-4` turns each `build/yorimichi/treehouse/textures/<slug>.png`
(written by `tools/treehouse_textures.py finish`) into `T_TH_<slug>`, and gives `M_TreeHouse` the village look; `:10` says
`MI_TH_trunk` is the bark of `TH_Trunks`. The import is a texture import of a generated PNG, so the texture importer fits.
Byte evidence: the four `T_TH_*` packages and their `MI_TH_*` instances reference `M_TreeHouse` and `M_TH_Light`
(owned by `adopted/japan/treehouse/generator`) and the textures named below.

Donor PNG pins (sha256, from `build/yorimichi/treehouse/textures/`):

| Texture package | Donor PNG | sha256 | Note |
|---|---|---|---|
| `T_TH_flat` | `flat.png` | `10b379bb6586c9e9…` | same bytes as `glass.png` |
| `T_TH_glass` | `glass.png` | `10b379bb6586c9e9…` | `T_TH_glass` is 8303 bytes, `T_TH_flat` 8297: the 6-byte difference is the name length, so the two imports are probably identical, to be confirmed by a native read |
| `T_TH_rope` | `rope.png` | `13d328aea5ed6186…` | |
| `T_TH_bark` | `bark.png` | `89d2715329c84685…` | owned by `adopted/japan/treehouse/surface-bark`, not by these records |

Status per record:
- `surface-flat` (`MI_TH_flat`, `T_TH_flat`), `surface-glass` (`MI_TH_glass`, `T_TH_glass`), `surface-rope`
  (`MI_TH_rope`, `T_TH_rope`): **planned**. Each texture takes a texture recipe with the donor PNG committed under `src/`
  (not done here), and each instance a material-instance recipe with `M_TreeHouse` as parent and `Tex` set to its texture.
  Nothing is imported.
- `surface-pane` (`MI_TH_pane`, parent `M_TH_Light`): **need-read**. The instance has no texture of its own, so its
  parameters come from a native read of the saved instance.
- `surface-trunk` (`MI_TH_trunk`, parent `M_TreeHouse`, `T_TH_bark`): **need-read**. Its bark texture is owned by
  `surface-bark`, which is outside these families, so the input owner is named but not changed here.

Native reads still needed (read-only; editor and clean hydrate): the material list file
`docs/inventory/small-families-treehouse-materials.txt` (the five `MI_TH_*` instances) through `report_materials.py`,
with `V2_REPORT_PACKAGES` set to that list and `V2_REPORT_OUT` under `build/yorimichi_v2/reports/`, run as an `editor.run`
step in the same form as the Japan read. Texture settings need the same kind of read for the four `T_TH_*` packages.

Blockers: no claimed import; `glass` versus `flat` settings to confirm; `T_TH_bark` has an owner outside these records.

- `adopted/japan/treehouse/surface-flat`: generated texture T_TH_flat and MI_TH_flat. Evidence: import_treehouse.py:3-4; build/yorimichi/treehouse/textures/flat.png. Status: **planned**. texture recipe from the donor PNG; the glass PNG has the same sha256 (see the table)
- `adopted/japan/treehouse/surface-glass`: generated texture T_TH_glass and MI_TH_glass. Evidence: import_treehouse.py:3-4; build/yorimichi/treehouse/textures/glass.png. Status: **planned**. glass.png and flat.png are byte-identical in the donor; the two textures differ in V2 (8297 and 8303 bytes), so the import settings are not yet established
- `adopted/japan/treehouse/surface-pane`: generated MI_TH_pane (parent M_TH_Light). Evidence: treehouse generator (adopted/japan/treehouse/generator); parent M_TH_Light. Status: **need-read**. material instance without its own texture; parameters need a native read
- `adopted/japan/treehouse/surface-rope`: generated texture T_TH_rope and MI_TH_rope. Evidence: import_treehouse.py:3-4; build/yorimichi/treehouse/textures/rope.png. Status: **planned**. the MI parent M_TreeHouse is owned by adopted/japan/treehouse/generator; the import settings are not yet confirmed
- `adopted/japan/treehouse/surface-trunk`: generated MI_TH_trunk (bark, RoomCut 0). Evidence: import_treehouse.py:10; texture T_TH_bark owned by adopted/japan/treehouse/surface-bark. Status: **need-read**. material instance; its bark texture is owned elsewhere

| Package | Record | Status | Inputs (owner records) | Native read still needed |
|---|---|---|---|---|
| `MI_TH_flat` | `japan/treehouse/surface-flat` | planned | Japan/Treehouse/Materials/M_TreeHouse, Japan/Treehouse/Materials/M_TreeHouse, Japan/Treehouse/Textures/T_TH_flat | `report_materials` (material list) |
| `T_TH_flat` | `japan/treehouse/surface-flat` | planned | Japan/Treehouse/Textures | no reader in this tree |
| `MI_TH_glass` | `japan/treehouse/surface-glass` | planned | Japan/Treehouse/Materials/M_TreeHouse, Japan/Treehouse/Materials/M_TreeHouse, Japan/Treehouse/Textures/T_TH_glass | `report_materials` (material list) |
| `T_TH_glass` | `japan/treehouse/surface-glass` | planned | Japan/Treehouse/Textures | no reader in this tree |
| `MI_TH_pane` | `japan/treehouse/surface-pane` | need-read | Japan/Treehouse/Materials/M_TH_Light, Japan/Treehouse/Materials/M_TH_Light | `report_materials` (material list) |
| `MI_TH_rope` | `japan/treehouse/surface-rope` | planned | Japan/Treehouse/Materials/M_TreeHouse, Japan/Treehouse/Materials/M_TreeHouse, Japan/Treehouse/Textures/T_TH_rope | `report_materials` (material list) |
| `T_TH_rope` | `japan/treehouse/surface-rope` | planned | Japan/Treehouse/Textures | no reader in this tree |
| `MI_TH_trunk` | `japan/treehouse/surface-trunk` | need-read | Japan/Treehouse/Materials/M_TreeHouse, Japan/Treehouse/Materials/M_TreeHouse, Japan/Treehouse/Textures/T_TH_bark | `report_materials` (material list) |

### Mega Park materials and standalone map (4 records, 25 packages)

Donor evidence: `unreal/Scripts/import_megapark.py` builds the Mega Park materials in `materials(report)` (`:166-221`)
from the donor's build report `build/yorimichi/megapark/build.json` (its `materials`, 523 rows: 449 with alpha mode 0,
71 masked, 3 translucent). Each row becomes `MI_` plus its key without the `M_` prefix (`:194`), with parent
`M_RetailOpaque`, `M_RetailMasked` or `M_RetailTranslucent` by alpha mode (`:189-190`, names at `:76`). The 24 instance
packages of the three material records are all among those 523 names (pinned by `tests/test_small_families.py`).

Byte evidence: every instance's parent is `/Game/MegaPark/Materials/M_Retail*` (owned by `adopted/megapark/base-materials`),
and its textures are `/Game/MegaPark/Textures/T_*`, owned by the editor-saved records `adopted/megapark/shared-textures-*`
(common, wood, pavement, concrete, dirtgravel). Those texture packages are not regenerated by these records.

Status per record:
- `shared-materials-wood` (20 instances), `seam` (3, with the seam scalars `SpecularScale`, `Gloss`,
  `LightmapOcclusion`, `:210-213`), `shared-materials-pavement` (1): **need-read**. The parameters are the donor
  row's, but two blockers stop a recipe. First, the `natural` rows set a two-sided base-property override
  (`:215-217`), which recipe v2 cannot express. Second, `LightmapNorm` (`:208`) reads `restyle['lightmaps']` from
  `build/yorimichi/megapark/textures/textures.json` (`:172`), which is not in these records. The count of two-sided rows is
  not computed here.
- `standalone-level` (`/Game/MegaPark/Maps/SuperUltraMegaPark`): **unreal-authored**. `import_megapark.py:20-28` names the
  level, and `:375` spawns the `MegaParkLayout` actor and saves it, so the level is an editor save from a script over
  committed native source. It keeps its editor-saved record form (`authority = "editor"`). The map references 29
  `/Game/MegaPark/Meshes/UC_MP_<hash>` collision packages. The cell records own the `UC_MP_<hash>_0` names of the same
  hashes (`cell-*` outputs), so whether the map's references resolve to them is a native check, not a conclusion.

Native reads still needed (read-only; editor and clean hydrate): the 24 instances through `report_materials.py`, using the
material list file `docs/inventory/small-families-megapark-materials.txt`, `V2_REPORT_OUT` under
`build/yorimichi_v2/reports/`, as an `editor.run` step. The map needs a reader for its actor references (none in this tree).

Blockers: the two-sided override on the natural rows (recipe v2 has no field for it); the restyle lightmap norms
(`textures.json` not in the records); the map's collision references need the native check above.

- `adopted/megapark/shared-materials-wood`: generator-built material instances MI_<key>. Evidence: import_megapark.py:166-221 (materials(report)). Status: **need-read**. parameters come from the donor import-report materials; the two-sided base-property override (lines 218-219) is not expressible in recipe v2
- `adopted/megapark/seam`: generator-built seam instances MI_<key>_Seam. Evidence: import_megapark.py:166-221 with the seam scalars (SpecularScale, Gloss, LightmapOcclusion). Status: **need-read**. as shared-materials-wood, plus the seam scalars
- `adopted/megapark/shared-materials-pavement`: generator-built material instance. Evidence: import_megapark.py:166-221. Status: **need-read**. as shared-materials-wood
- `adopted/megapark/standalone-level`: editor-saved level built by a script from committed native source. Evidence: import_megapark.py:20-28 (LEVEL), :347 (main). Status: **unreal-authored**. keeps its editor-saved form (authority editor); a native read lists the actors it references

| Package | Record | Status | Inputs (owner records) | Native read still needed |
|---|---|---|---|---|
| `MI_0297e420658d668d` | `megapark/shared-materials-wood` | need-read | MegaPark/Materials/M_RetailOpaque, MegaPark/Materials/M_RetailOpaque, MegaPark/Textures/T_0000043d03e3870a ... | `report_materials` (material list) |
| `MI_0a62da3eb9f73004` | `megapark/shared-materials-wood` | need-read | MegaPark/Materials/M_RetailOpaque, MegaPark/Materials/M_RetailOpaque, MegaPark/Textures/T_0000043d03e3870a ... | `report_materials` (material list) |
| `MI_0e1c4253739c05d1` | `megapark/shared-materials-wood` | need-read | MegaPark/Materials/M_RetailOpaque, MegaPark/Materials/M_RetailOpaque, MegaPark/Textures/T_0000043d03e3870a ... | `report_materials` (material list) |
| `MI_0e3433716e431235` | `megapark/shared-materials-wood` | need-read | MegaPark/Materials/M_RetailOpaque, MegaPark/Materials/M_RetailOpaque, MegaPark/Textures/T_0000043d03e3870a ... | `report_materials` (material list) |
| `MI_234095f625b41d97` | `megapark/shared-materials-wood` | need-read | MegaPark/Materials/M_RetailOpaque, MegaPark/Materials/M_RetailOpaque, MegaPark/Textures/T_0000043d03e3870a ... | `report_materials` (material list) |
| `MI_26bca4f4c4439b9a` | `megapark/shared-materials-wood` | need-read | MegaPark/Materials/M_RetailOpaque, MegaPark/Materials/M_RetailOpaque, MegaPark/Textures/T_0000043d03e3870a ... | `report_materials` (material list) |
| `MI_2d236e27b1c7ae19` | `megapark/shared-materials-wood` | need-read | MegaPark/Materials/M_RetailOpaque, MegaPark/Materials/M_RetailOpaque, MegaPark/Textures/T_0000043d03e3870a ... | `report_materials` (material list) |
| `MI_2d299e45c0b686a4` | `megapark/shared-materials-wood` | need-read | MegaPark/Materials/M_RetailOpaque, MegaPark/Materials/M_RetailOpaque, MegaPark/Textures/T_0000043d03e3870a ... | `report_materials` (material list) |
| `MI_4154dbd709458a3a` | `megapark/shared-materials-wood` | need-read | MegaPark/Materials/M_RetailOpaque, MegaPark/Materials/M_RetailOpaque, MegaPark/Textures/T_0000043d03e3870a ... | `report_materials` (material list) |
| `MI_54b9cb948ff265c3` | `megapark/shared-materials-wood` | need-read | MegaPark/Materials/M_RetailOpaque, MegaPark/Materials/M_RetailOpaque, MegaPark/Textures/T_0000043d03e3870a ... | `report_materials` (material list) |
| `MI_5b7d4772f362d980` | `megapark/shared-materials-wood` | need-read | MegaPark/Materials/M_RetailOpaque, MegaPark/Materials/M_RetailOpaque, MegaPark/Textures/T_0000043d03e3870a ... | `report_materials` (material list) |
| `MI_5fa42b1b843c5f13` | `megapark/shared-materials-wood` | need-read | MegaPark/Materials/M_RetailOpaque, MegaPark/Materials/M_RetailOpaque, MegaPark/Textures/T_0000043d03e3870a ... | `report_materials` (material list) |
| `MI_74de62d96d172fcd` | `megapark/shared-materials-wood` | need-read | MegaPark/Materials/M_RetailOpaque, MegaPark/Materials/M_RetailOpaque, MegaPark/Textures/T_0000043d03e3870a ... | `report_materials` (material list) |
| `MI_97fb1d5d055dc83e` | `megapark/shared-materials-wood` | need-read | MegaPark/Materials/M_RetailOpaque, MegaPark/Materials/M_RetailOpaque, MegaPark/Textures/T_0000043d03e3870a ... | `report_materials` (material list) |
| `MI_9d9ad61af96a5a48` | `megapark/shared-materials-wood` | need-read | MegaPark/Materials/M_RetailOpaque, MegaPark/Materials/M_RetailOpaque, MegaPark/Textures/T_0000043d03e3870a ... | `report_materials` (material list) |
| `MI_b34bfde2b1b2ba35` | `megapark/shared-materials-wood` | need-read | MegaPark/Materials/M_RetailOpaque, MegaPark/Materials/M_RetailOpaque, MegaPark/Textures/T_0000043d03e3870a ... | `report_materials` (material list) |
| `MI_c3a8971b198e360e` | `megapark/shared-materials-wood` | need-read | MegaPark/Materials/M_RetailOpaque, MegaPark/Materials/M_RetailOpaque, MegaPark/Textures/T_0000043d03e3870a ... | `report_materials` (material list) |
| `MI_c941862c2cc7a50f` | `megapark/shared-materials-wood` | need-read | MegaPark/Materials/M_RetailOpaque, MegaPark/Materials/M_RetailOpaque, MegaPark/Textures/T_0000043d03e3870a ... | `report_materials` (material list) |
| `MI_cef7e645a74d3d6c` | `megapark/shared-materials-wood` | need-read | MegaPark/Materials/M_RetailOpaque, MegaPark/Materials/M_RetailOpaque, MegaPark/Textures/T_0000043d03e3870a ... | `report_materials` (material list) |
| `MI_da41d4c91df999ea` | `megapark/shared-materials-wood` | need-read | MegaPark/Materials/M_RetailOpaque, MegaPark/Materials/M_RetailOpaque, MegaPark/Textures/T_0000043d03e3870a ... | `report_materials` (material list) |
| `MI_3fc3174182abbed4_Seam` | `megapark/seam` | need-read | MegaPark/Materials/M_RetailOpaque, MegaPark/Materials/M_RetailOpaque, MegaPark/Textures/T_0000043d03e3870a ... | `report_materials` (material list) |
| `MI_4cef5bb305cb09eb_Seam` | `megapark/seam` | need-read | MegaPark/Materials/M_RetailOpaque, MegaPark/Materials/M_RetailOpaque, MegaPark/Textures/T_0000043d03e3870a ... | `report_materials` (material list) |
| `MI_b4686eeb54647811_Seam` | `megapark/seam` | need-read | MegaPark/Materials/M_RetailOpaque, MegaPark/Materials/M_RetailOpaque, MegaPark/Textures/T_0000043d03e3870a ... | `report_materials` (material list) |
| `MI_99622005a8467a13` | `megapark/shared-materials-pavement` | need-read | MegaPark/Materials/M_RetailOpaque, MegaPark/Materials/M_RetailOpaque, MegaPark/Textures/T_00008ccc03e3870a ... | `report_materials` (material list) |
| `SuperUltraMegaPark` | `megapark/standalone-level` | unreal-authored | Japan/Maps/Slice, MegaPark/Meshes/SM_MP_04CCB1FDB63D6C87, MegaPark/Meshes/SM_MP_072BEA8B3D376763 ... | no reader in this tree |

### Skatepark board and materials (2 records, 8 packages)

Donor evidence: `unreal/Scripts/board_dissolve_material.py` builds `/Game/SkatePark/Board/M_BoardDissolve` (`:11` FOLDER and
NAME, `:15` create_asset, graph from `:22-29`), and `unreal/Scripts/import_skatepark.py` builds the seven `M_Pier_<surface>`
masters (`:137`, with `T_Pier_<surface>_<role>` textures at `:148`). Both are Unreal-script graphs, not imports.

Byte evidence: the seven masters name `T_Pier_<surface>_{albedo,normal,roughness}` textures (`mural` has albedo only).
Those textures are owned by the 19 `texture/skatepark/pier-*` records, which are outside this family. `M_BoardDissolve`
names no other package.

Status per record:
- `skatepark/board` (`M_BoardDissolve`): **blocked**. A material master has no importer in this tree, and its graph has never been read natively. The donor's `build.py` and
  `unreal/Config/DefaultGame.ini` name it as the board's dissolve material.
- `skatepark/materials` (seven `M_Pier_*`): **blocked** for the same reason. Their texture inputs are determined (owned by
  `texture/skatepark/*`), so only the graph read is missing.

Native reads still needed: a read of each master's graph and its texture parameters. No reader for masters or graphs is
in this tree (`report_materials.py` reads material instances), so the read is a new read-only script, not a command.

Blockers: no importer kind for material masters; no native read of the graphs.

- `adopted/skatepark/board`: generator master M_BoardDissolve. Evidence: board_dissolve_material.py:11-15. Status: **blocked**. no importer for material masters; native read of the graph needed
- `adopted/skatepark/materials`: generator masters M_Pier_<surface>. Evidence: import_skatepark.py:137-173 (M_Pier_ and T_Pier_ textures). Status: **blocked**. no importer for material masters; their textures are owned by texture/skatepark records

| Package | Record | Status | Inputs (owner records) | Native read still needed |
|---|---|---|---|---|
| `M_BoardDissolve` | `skatepark/board` | blocked | - | `report_materials` (material list) |
| `M_Pier_basalt` | `skatepark/materials` | blocked | SkatePark/Textures/T_Pier_basalt_albedo, SkatePark/Textures/T_Pier_basalt_normal, SkatePark/Textures/T_Pier_basalt_roughness | `report_materials` (material list) |
| `M_Pier_ceramic` | `skatepark/materials` | blocked | SkatePark/Textures/T_Pier_ceramic_albedo, SkatePark/Textures/T_Pier_ceramic_normal, SkatePark/Textures/T_Pier_ceramic_roughness | `report_materials` (material list) |
| `M_Pier_concrete` | `skatepark/materials` | blocked | SkatePark/Textures/T_Pier_concrete_albedo, SkatePark/Textures/T_Pier_concrete_normal, SkatePark/Textures/T_Pier_concrete_roughness | `report_materials` (material list) |
| `M_Pier_mural` | `skatepark/materials` | blocked | SkatePark/Textures/T_Pier_mural_albedo | `report_materials` (material list) |
| `M_Pier_painted` | `skatepark/materials` | blocked | SkatePark/Textures/T_Pier_painted_albedo, SkatePark/Textures/T_Pier_painted_normal, SkatePark/Textures/T_Pier_painted_roughness | `report_materials` (material list) |
| `M_Pier_steel` | `skatepark/materials` | blocked | SkatePark/Textures/T_Pier_steel_albedo, SkatePark/Textures/T_Pier_steel_normal, SkatePark/Textures/T_Pier_steel_roughness | `report_materials` (material list) |
| `M_Pier_wood` | `skatepark/materials` | blocked | SkatePark/Textures/T_Pier_wood_albedo, SkatePark/Textures/T_Pier_wood_normal, SkatePark/Textures/T_Pier_wood_roughness | `report_materials` (material list) |

### Belmonte shared materials (2 records, 7 packages)

Donor evidence: `world/regions/belmonte/material_preparation.py:21` names each Belmonte instance `MI_BM_` plus the first
12 hex digits of the sha256 of its source path. The instances are `MI_BM_*` with parent `M_Belmonte`, which is owned by
`adopted/belmonte/generator` (its only `/Game` reference). The donor's shared-material path list is what would name each
hash, so the names are reproducible only by running that preparation.

Byte evidence: all seven `.uasset` files are 6899 bytes, and each names only `/Game/Belmonte/Materials/M_Belmonte` as a
package reference. Equal size and one shared parent are consistent with seven identical instances differing in name, but
the parameter values are not compared here.

Status per record:
- `shared-metal-glass` (five instances, `MI_BM_4ee3168b033c`, `_69b755f9ad2a`, `_aa1a8d45375e`, `_b5dfa6e6373d`,
  `_fae8893ff89f`): **need-read**.
- `shared-water` (two instances, `MI_BM_aadab9c1da71`, `_f76f48666871`): **need-read**.

Both records are instances of one master, so a material-instance recipe fits only once the saved parameters are read.
The instances name no texture, so their recipe would carry scalars and vectors only. Those values are not in the
committed records.

Native reads still needed (read-only; editor and clean hydrate): the seven instances through `report_materials.py`, with
`V2_REPORT_PACKAGES` set to `docs/inventory/small-families-belmonte-materials.txt` and `V2_REPORT_OUT` under
`build/yorimichi_v2/reports/`, as an `editor.run` step. The donor's path list for the hashes is a separate check, not a read.

Blockers: no parameter read yet; the path-to-name mapping is only reproducible by the preparation script.

- `adopted/belmonte/shared-metal-glass`: generator-built MI_BM_<hash>. Evidence: world/regions/belmonte/material_preparation.py:21 (name from sha256 of the path). Status: **need-read**. parent M_Belmonte is owned by adopted/belmonte/generator
- `adopted/belmonte/shared-water`: generator-built MI_BM_<hash>. Evidence: world/regions/belmonte/material_preparation.py:21. Status: **need-read**. as shared-metal-glass

| Package | Record | Status | Inputs (owner records) | Native read still needed |
|---|---|---|---|---|
| `MI_BM_4ee3168b033c` | `belmonte/shared-metal-glass` | need-read | Belmonte/Materials/M_Belmonte, Belmonte/Materials/M_Belmonte | `report_materials` (material list) |
| `MI_BM_69b755f9ad2a` | `belmonte/shared-metal-glass` | need-read | Belmonte/Materials/M_Belmonte, Belmonte/Materials/M_Belmonte | `report_materials` (material list) |
| `MI_BM_aa1a8d45375e` | `belmonte/shared-metal-glass` | need-read | Belmonte/Materials/M_Belmonte, Belmonte/Materials/M_Belmonte | `report_materials` (material list) |
| `MI_BM_b5dfa6e6373d` | `belmonte/shared-metal-glass` | need-read | Belmonte/Materials/M_Belmonte, Belmonte/Materials/M_Belmonte | `report_materials` (material list) |
| `MI_BM_fae8893ff89f` | `belmonte/shared-metal-glass` | need-read | Belmonte/Materials/M_Belmonte, Belmonte/Materials/M_Belmonte | `report_materials` (material list) |
| `MI_BM_aadab9c1da71` | `belmonte/shared-water` | need-read | Belmonte/Materials/M_Belmonte, Belmonte/Materials/M_Belmonte | `report_materials` (material list) |
| `MI_BM_f76f48666871` | `belmonte/shared-water` | need-read | Belmonte/Materials/M_Belmonte, Belmonte/Materials/M_Belmonte | `report_materials` (material list) |

### FX residual packages (1 record, 7 packages)

Donor evidence: `unreal/Scripts/import_combat_fx.py` builds the sprite masters `M_FX_Additive` (`:82`) and `M_FX_Dust` (`:83`) with
`sprite_material` (`:52`), the instances `MI_FX_Glow`, `MI_FX_Spark`, `MI_FX_Ring` (parent `M_FX_Additive`) and `MI_FX_Dust`
(parent `M_FX_Dust`) with `instance` (`:72`, list at `:84-85`), and the trail master `M_FX_Trail` (`:87`). The sprite
textures are the donor's `build/yorimichi/combat_fx/T_FX_{Dust,Glow,Ring,Spark,Trail}.png`, imported by the five
`texture/fx/*` records, and the donor keeps its import manifest beside them (`combat_fx/unreal_import.json`).

Byte evidence: `M_FX_Additive` and `M_FX_Dust` reference `T_FX_Glow` and `T_FX_Dust` (owned by `texture/fx/glow` and
`texture/fx/dust`). `M_FX_Trail` references no texture: it is the procedural slash-ribbon material (`:87`, vertex colour
and alpha). The four instances each reference their master and their own texture.

Status per record:
- `adopted/fx` (seven packages): **need-read**. The instances are plain (parent plus `Tex`), so a material-instance recipe
  fits once the parameters are read. The three masters are Unreal-script graphs, which have no importer in this tree
  (the same blocker as the skatepark masters), so `M_FX_*` cannot be closed by recipe.

Native reads still needed (read-only; editor and clean hydrate): the four instances through `report_materials.py`, with
`V2_REPORT_PACKAGES` set to `docs/inventory/small-families-fx-materials.txt` and `V2_REPORT_OUT` under
`build/yorimichi_v2/reports/`, as an `editor.run` step. A read of the three masters' graphs needs a new reader.

Blockers: masters (`M_FX_Additive`, `M_FX_Dust`, `M_FX_Trail`) have no importer; the trail's ribbon graph has no native read.

- `adopted/fx`: generator masters and instances (sprite materials). Evidence: unreal/Scripts/import_combat_fx.py:82-87 (sprite_material, instance). Status: **need-read**. the T_FX_* textures are owned by texture/fx records; the masters are script-built

| Package | Record | Status | Inputs (owner records) | Native read still needed |
|---|---|---|---|---|
| `MI_FX_Dust` | `fx` | need-read | FX/M_FX_Dust, FX/M_FX_Dust, FX/Textures/T_FX_Dust | `report_materials` (material list) |
| `MI_FX_Glow` | `fx` | need-read | FX/M_FX_Additive, FX/M_FX_Additive, FX/Textures/T_FX_Glow | `report_materials` (material list) |
| `MI_FX_Ring` | `fx` | need-read | FX/M_FX_Additive, FX/M_FX_Additive, FX/Textures/T_FX_Ring | `report_materials` (material list) |
| `MI_FX_Spark` | `fx` | need-read | FX/M_FX_Additive, FX/M_FX_Additive, FX/Textures/T_FX_Spark | `report_materials` (material list) |
| `M_FX_Additive` | `fx` | need-read | FX/Textures/T_FX_Glow | `report_materials` (material list) |
| `M_FX_Dust` | `fx` | need-read | FX/Textures/T_FX_Dust | `report_materials` (material list) |
| `M_FX_Trail` | `fx` | need-read | FX/Textures/T_FX_Trail | `report_materials` (material list) |

### Japan plaza and harbour textures (1 record, 4 packages)

Donor evidence: the four textures are imports of two tracked PNGs from the donor's source tree,
`world/regions/hidamari/textures/paving.png` (sha256 `0cf002e567a081c1e32f…`) and `timber.png` (sha256 `d71b181a3d0df569f0c8…`).
`unreal/Scripts/arcade_material.py:5-12` imports them as `T_Arcade_<name>` and `unreal/Scripts/harbor_material.py:24-27` as
`T_Harbor_<name>`, both into `/Game/Japan/Textures`. The two PNGs are tracked in the donor (`git ls-files`), so they are
authored inputs, not build outputs. The donor's `plaza_material.py:45` only loads `T_Arcade_paving`; it does not make it.

Byte evidence: `T_Arcade_paving` and `T_Harbor_paving` are both 2219461 bytes, and `T_Arcade_timber` and `T_Harbor_timber`
both 1833653 bytes. Equal sizes fit one import of each PNG with the same settings. The four packages name no other package.

Status: **planned** (`adopted/japan/textures/plaza-harbor`). The texture importer fits: the record would commit the two
PNGs under `src/` with their sha256, and each `T_*` package would take a texture recipe. Two conditions stand in front
of it. First, the asset rights of the PNGs must be settled before their bytes are uploaded (`games/yorimichi_v2/CONTRACTS`,
`yorimichi-v2-portable-records`). Second, a native read must confirm the equal settings, because the sizes are only
consistent with, not proof of, the same import. Nothing is imported or claimed here.

Native reads still needed (read-only; editor and clean hydrate): the texture settings of the four packages. No texture
reader is in this tree (the texture report of the residual Belmonte train is in PR #793, not on this branch), so this
needs that reader first.

- `adopted/japan/textures/plaza-harbor`: textures imported from two tracked donor PNGs. Evidence: arcade_material.py:5-12 (T_Arcade_<name>) and harbor_material.py:24-27 (T_Harbor_<name>), both from world/regions/hidamari/textures/{paving,timber}.png. Status: **planned**. T_Arcade and T_Harbor packages of each name have equal sizes (2219461 and 1833653 bytes), so one import of each PNG is consistent; the PNGs are tracked in the donor source (paving sha256 0cf002e5..., timber d71b181a...)

| Package | Record | Status | Inputs (owner records) | Native read still needed |
|---|---|---|---|---|
| `T_Arcade_paving` | `japan/textures/plaza-harbor` | planned | Japan/Textures | no reader in this tree |
| `T_Arcade_timber` | `japan/textures/plaza-harbor` | planned | Japan/Textures | no reader in this tree |
| `T_Harbor_paving` | `japan/textures/plaza-harbor` | planned | Japan/Textures | no reader in this tree |
| `T_Harbor_timber` | `japan/textures/plaza-harbor` | planned | Japan/Textures | no reader in this tree |

### Bike residual packages (1 record, 2 packages)

Donor evidence: `unreal/Scripts/import_bike.py:36-46` imports each bike part from `build/yorimichi/bike/assets/<part>.fbx`,
with its entry in `build/yorimichi/bike/manifest.json` (`parts`, triangles 26060 for each wheel) and the wheel rule that
requires CPU access and no full-precision UVs. The FBX files are the donor's Blender bike build output: they are
git-ignored under `build/`, and their generator is `assets/vehicles/bike/build.py` on `Bike.blend`. `M_Bike` is the
parent, owned by `adopted/japan/materials/base-materials`.

Byte evidence: `BK_WheelFront` and `BK_WheelRear` are 550 KB each and reference only `/Game/Japan/Materials/M_Bike`.

Donor FBX pins (sha256, `build/yorimichi/bike/assets/`): `BK_WheelFront.fbx` `b9d91c3ff4143f67…`, `BK_WheelRear.fbx`
`5a62e75f11e02be6…`.

Status: **need-read** (`adopted/japan/assets/bike`). The importer can take an FBX (`import_asset.py`, `_fbx_static_mesh`),
and the static-mesh recipe can state the wheel settings (`allow_cpu_access`, `full_precision_uvs`, which the recipe
already has for `prop/megapark/seam-collision`). Two things still stop a record. First, the FBX is a git-ignored
build output, so its bytes would be committed as a pinned source only after its generator and inputs (`Bike.blend`) are
recorded, as the generated-art rule requires. Second, the wheel's material slot and `M_Bike` need a native read.

Native reads still needed (read-only; editor and clean hydrate): the wheels' saved settings and the `M_Bike` slot, by a
static-mesh reader that this tree does not have. No command is given because the reader is missing.

Blockers: the FBX generator inputs are not yet recorded; no static-mesh reader in this tree.

- `adopted/japan/assets/bike`: generated wheel static meshes (Blender bike build). Evidence: import_bike.py:40 (manifest parts); build/yorimichi/bike/Bike.blend and manifest.json. Status: **need-read**. the importer needs the bike manifest sha256 and the M_Bike parent (owned by adopted/japan/materials/base-materials)

| Package | Record | Status | Inputs (owner records) | Native read still needed |
|---|---|---|---|---|
| `BK_WheelFront` | `japan/assets/bike` | need-read | Japan/Materials/M_Bike, Japan/Materials/M_Bike | no reader in this tree |
| `BK_WheelRear` | `japan/assets/bike` | need-read | Japan/Materials/M_Bike, Japan/Materials/M_Bike | no reader in this tree |

### Sword camp materials (1 record, 2 packages)

Donor evidence: `unreal/Scripts/import_swordcamp.py` creates `M_SwordCamp` in `/Game/SwordCamp/Materials` (`:47-51`) and
`M_RoninBody` (`:117-122`), and imports the atlas `T_SwordCampAtlas` (`:29-39`) from the donor build's
`build/yorimichi/swordcamp/swordcamp_atlas.jpg`. That JPG is made by `world/regions/swordcamp/make_atlas.py` (the donor's
`world.swordcamp_atlas` step, `build.py:1147-1149`), so the atlas is generated art with its generator recorded.

Byte evidence: `M_SwordCamp` and `M_RoninBody` each reference only `/Game/SwordCamp/Textures/T_SwordCampAtlas`, which
`texture/swordcamp/atlas` owns. Neither names any other package.

Status per record: **blocked** (`adopted/swordcamp/materials`). Both packages are material masters built by Unreal-script
graphs, and this tree has no importer for a material master (the same blocker as the skatepark masters). Their one
texture input is determined and owned, so the only missing piece is the graph, which needs a native read of the saved
nodes. The atlas is not a blocker.

Native reads still needed (read-only; editor and clean hydrate): a read of the two masters' saved graphs and their atlas
parameter. No reader for master graphs is in this tree (`report_materials.py` reads material instances only).

Blockers: no importer for material masters; no native graph read.

- `adopted/swordcamp/materials`: generator masters M_SwordCamp and M_RoninBody. Evidence: import_swordcamp.py:47-51 (M_SwordCamp), :117-122 (M_RoninBody); atlas import :29-39. Status: **blocked**. no importer for material masters (as the skatepark masters); the atlas T_SwordCampAtlas is owned by texture/swordcamp/atlas

| Package | Record | Status | Inputs (owner records) | Native read still needed |
|---|---|---|---|---|
| `M_RoninBody` | `swordcamp/materials` | blocked | SwordCamp/Textures/T_SwordCampAtlas | `report_materials` (material list) |
| `M_SwordCamp` | `swordcamp/materials` | blocked | SwordCamp/Textures/T_SwordCampAtlas | `report_materials` (material list) |

### Hidamari surface, racing, see-through and skate runtime (4 records, 4 packages)

Four records, one package each. None is an import; each is a script product or a runtime data asset.

- `adopted/japan/hidamari/surface-flat` (`MI_HD_flat`): `unreal/Scripts/city_material.py:43-44` builds the master
  `M_HDCity` (owned by `adopted/japan/hidamari/generator`) and `:99` names each instance `MI_HD_<slug>`. Its texture
  `T_HD_plaster` is owned by `adopted/japan/hidamari/surface-plaster`, from the donor's `tools/hidamari_textures.py`.
  Status: **need-read**. The instance is a plain one (parent and `Tex`), so a material-instance recipe fits once its
  parameters are read; the master has no importer.
- `adopted/racing` (`M_RacingTv`): `unreal/Scripts/racing_tv_material.py:12-16` creates the picture master in `/Game/Racing`
  with a graph and no texture input. Status: **blocked** (a master, no importer, no native graph read).
- `adopted/seethrough` (`MPC_SeeThrough`): `unreal/Scripts/see_through.py:47` names the parameter collection and `:246-253`
  creates it; the game's `USeeThroughComponent` writes it every frame (`SeeThrough.cpp`, cited in the script's header). It is a
  parameter collection, which no importer kind takes. Status: **blocked**.
- `adopted/skateruntime` (`RuntimeData`, 31 MB): `build.py:1813` lists it as an output of the skate runtime step, whose
  inputs are `skate_ride/import_runtime.py`, `import_motion.py`, `verify_data.py` and the donor's `skate-data`
  (`build/yorimichi/skate-data/verify.json` is the donor's check). It is a data asset, and no importer kind takes one; the
  editor copy is the only one. Status: **blocked**.

Native reads still needed (read-only; editor and clean hydrate): `MI_HD_flat` through `report_materials.py`, with the list
`docs/inventory/small-families-hidamari-materials.txt`. That list also names `M_RacingTv` and `MPC_SeeThrough`, which
`report_materials.py` is not written to read: those two need a master or parameter-collection reader first. `RuntimeData`
needs a data-asset reader. None of these is in this tree.

Blockers: the `M_HDCity` master (for the instance); the racing and see-through graphs and parameter collection; the
`RuntimeData` data asset has no importer kind.

- `adopted/japan/hidamari/surface-flat`: generated MI_HD_flat (parent M_HDCity). Evidence: city_material.py (hidamari generator), tools/hidamari_textures.py. Status: **need-read**. parent M_HDCity and T_HD_plaster are owned by adopted/japan/hidamari records
- `adopted/racing`: generator master M_RacingTv. Evidence: racing_tv_material.py:12-16. Status: **blocked**. no importer for material masters; native read of the graph needed
- `adopted/seethrough`: generator material parameter collection MPC_SeeThrough. Evidence: see_through.py:47 and :246-253. Status: **blocked**. no importer for parameter collections
- `adopted/skateruntime`: generated RuntimeData data asset (31 MB). Evidence: build.py:1813 (RuntimeData output); unreal/Scripts/skate_ride/verify_data.py:15. Status: **blocked**. no importer for data assets; the cooked data is the only copy in the editor

| Package | Record | Status | Inputs (owner records) | Native read still needed |
|---|---|---|---|---|
| `MI_HD_flat` | `japan/hidamari/surface-flat` | need-read | Japan/Hidamari/Materials/M_HDCity, Japan/Hidamari/Materials/M_HDCity, Japan/Hidamari/Textures/T_HD_plaster | `report_materials` (material list) |
| `M_RacingTv` | `racing` | blocked | - | `report_materials` (material list) |
| `MPC_SeeThrough` | `seethrough` | blocked | - | `report_materials` (material list) |
| `RuntimeData` | `skateruntime` | blocked | - | no reader in this tree |
