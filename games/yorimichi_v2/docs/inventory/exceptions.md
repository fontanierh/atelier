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
| Brine Cove small props | Eleven placements saved, including the corrected crane/fish-shed split | Save the two soft remainders and finish any remaining useful fused objects; preserve each whole palm |
| Brine Cove ships | Nightjar, sloop and Adventure hull placements saved with per-instance hull groups | Retire the three emptied ship tiles and obsolete grouped placements after accepted replacement checks |
| Brine Cove market | Six market1 stalls saved on main | Fifteen more saved on PR #787; integrate them. The full market has 21 stalls, not the older 19-stall-only list |
| Brine Cove town | Original town appearance still represented by the fused tiles | Seven town1 placements are on PR #787; town2–9 remain pending. Retire the 42 empty tiles only after their replacements are accepted and saved |
| Other Brine Cove features | Existing fort, lighthouse and other saved units remain | The signal mast, stone shipyard slip and other useful objects still bundled in residual tiles need a real object boundary, not just a smaller package |
| Transport groups | Two ferry terminals, nine gondola route objects and thirteen railway route objects saved | Gondola pylon groups and railway fitting groups still bundle useful objects; preserve route data and moving services while splitting their editing boundaries |
| Area patches (G6) | Saved terrain, ground and scatter patches are legitimate scopes | A patch-name tally is only a candidate list. Any patch that still bundles several useful buildings or props remains unfinished until they are independently editable |

The counts above describe saved definitions and known plans, not a full new geometry audit. Use actual object
membership, not a name pattern, to decide whether a remaining patch is complete. Do not make useful-object splitting
optional simply because a patch is legal to save.

## Source closure still to classify

At this revision 51 open adopted records have no direct `[[sources]]` and no recipe. Three of them are the already
linked Adventure/animation records. The other **48 records / 678 packages** comprise:

| Family | Records | Packages |
|---|---:|---:|
| Residual Belmonte train packages | 7 | 473 |
| Japan materials | 7 | 43 |
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

### Residual Belmonte train records (seven, 473 packages): classification

The records `adopted/belmontetrain/{baggage-van,brake-van,first-class,locomotive,restaurant,second-class,tender}` hold
73, 78, 73, 51, 75, 84 and 39 packages (473). None has `[[sources]]` or a recipe, and none is closed. Every package
falls in one of three kinds, each with its own gap:

| Kind | Packages | Origin | Gap |
|---|---:|---|---|
| `Source/SM_BT_<Vehicle>/LOD1` and `LOD2` meshes | 14 | The vehicle's Train Builder GLBs (`service/import-report.json` and the level files, read by `recover.py plan_belmontetrain`; `unreal/Scripts/import_belmonte_train.py`) | The donor build output is not present in this checkout (`build/yorimichi` is empty). Regenerating it needs the donor generator and Blender, which are outside this task. Blocked. |
| `M_BT_*` material instances in each `LOD*` folder | 321 | The same GLB imports: each instance binds a glTF material of the vehicle mesh. `M_BT_BoardText` alone is authored by the import script | Same donor-build gap as the meshes. Blocked. |
| `T_BT_*` textures in each `LOD*` folder | 138 (27 distinct names) | `generator/source/world/train/textures.py` draws 21 of the 27 names from a registry (`T_BT_Walnut` included), with nine pinned jpgs as inputs. Six `*Interior` names and `T_BT_Walnut1` have no registry row | The 21 rows are a candidate route, but verifying them needs an editor import that reproduces the committed texture packages, and accepted content is not re-imported. Prepared, unverified; the six unmatched names are blocked until their origin is found. |

Adding `[[sources]]` to these records would change their import fingerprints and make `check.py` report `STALE_IMPORT`,
so the records stay as they are until a verified import closes them. The donor-build route
(`recover.py belmontetrain --donor <build/yorimichi/belmonte-train>`) is the first step for the mesh and material rows.
The count and the texture coverage are pinned by `tests/test_belmontetrain_residual.py`.

Brine Cove's source-preservation route at `5f2d21fbd1` is prepared but not applied on main. It is due after town9;
see [sources.md](sources.md). It fixes preservation of fused originals without changing accepted package bytes.

## Evidence and updates

The counts above were read from canonical `asset.toml` files in the immutable Git tree, excluding files nested
inside another asset's source folder. A loose filesystem glob can include stale/untracked records and donor copies.
`verified.json` and `objects.saved.json` distinguish imported packages from saved placements. Keep changes to this
page and the main inventory in the same content PR; do not mark a family complete from a plan or provisional receipt.
