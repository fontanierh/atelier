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

### Residual Belmonte train records (seven, 473 packages): donor evidence

The records `adopted/belmontetrain/{baggage-van,brake-van,first-class,locomotive,restaurant,second-class,tender}` hold
73, 78, 73, 51, 75, 84 and 39 packages (473). None has `[[sources]]` or a recipe, and **none is closed**. The donor
build output (Train Builder GLBs, `service/import-report.json`, texture PNG/JPG outputs) was read in place, read-only,
and is not committed. `recover.py belmontetrain --donor <belmonte-train folder>` plans **0 generated records**: its
`plan_belmontetrain` covers only the root vehicle packages (already generated) and door leaves (none in these seven
records), so none of the 473 packages has a planner row. Plan mode writes nothing.

| Kind | Packages | Donor evidence (checked) | Verdict |
|---|---:|---|---|
| `Source/SM_BT_<V>/SM_BT_<V>_LOD1` and `_LOD2` meshes | 14 | Each level GLB is pinned by the donor's `import-report.json` sha256 (14 of 14). The donor counts triangles per node placement: a mesh placed by several nodes counts once per placement. Counted that way, all 14 levels match the committed root chain's triangles and material names (sets). The earlier six-LOD1 disagreement was this instancing, not door leaves (refuted: tender has no doors and is short by 1,160 = 2 × 580) | **Retirement prepared, not applied; not imported.** These are unused donor leftovers. The vehicle records `assets/prop/belmontetrain/<v>/` pin the full LOD chain from the GLB sources, and `unreal/Scripts/import_asset.py` imports LOD1 and LOD2 as transient meshes, attaches them and deletes them. Nothing references the packages (`tools/migrate/belmontetrain_lods.py --check` proves it). The claimed `belmontetrain_lods.py --claim TASK` step removes them from the seven records, `verified.json` and `units.json`, and deletes the 14 `.uasset` files. `recover.py belmontetrain`'s `-lod1|lod2` rows must not be applied: they would recreate the records |
| `M_BT_*` material instances in `Source/SM_BT_<V>/LOD0..2` | 321 | Each GLB material slot (321 across all levels of all seven vehicles) binds by name to exactly one residual material package in the same LOD folder: 321 of 321 | **Prepared.** The binding closes by name, but the instance parameters and the source texture links still need an editor read, and no committed facts exist to compare them with |
| `T_BT_*` textures | 138 (27 names) | The donor has an image for all 138 packages. `T_BT_Walnut1` (10 packages, LOD0 and LOD1 of five vehicles) is not a separate image: in each of those ten GLBs two glTF textures share the one `T_BT_Walnut` image (sha256 `82a95ac294…`), and Interchange names the second texture `T_BT_Walnut1`. Its original is that image. No committed texture facts (size, format) are saved | **Prepared** for all 138 packages: the donor image is the candidate source, with `generator/source/world/train/textures.py` as its generator (`T_BT_Walnut1` from its `T_BT_Walnut` entry). Verifying needs an editor import compared with the committed packages, and accepted content is not re-imported |

Adding `[[sources]]` to these records would change their import fingerprints and make `check.py` report `STALE_IMPORT`,
so the records stay as they are until a verified import closes them. The count and the texture coverage are pinned by
`tests/test_belmontetrain_residual.py`. The LOD retirement takes 14 packages out of them (473 to 459);
the count is updated once it has run.

Next steps, not run here. (1) `tools/migrate/belmontetrain_lods.py --claim TASK` retires the 14 unused LOD meshes (see the row above). It is a retirement, not an import, and it runs under the seven `shared/belmontetrain/<unit>` scopes. (2) Textures remain prepared,
for all 138 donor-backed ids, after the generator's own source record is pinned.

Brine Cove's source-preservation route at `5f2d21fbd1` is prepared but not applied on main. It is due after town9;
see [sources.md](sources.md). It fixes preservation of fused originals without changing accepted package bytes.

## Evidence and updates

The counts above were read from canonical `asset.toml` files in the immutable Git tree, excluding files nested
inside another asset's source folder. A loose filesystem glob can include stale/untracked records and donor copies.
`verified.json` and `objects.saved.json` distinguish imported packages from saved placements. Keep changes to this
page and the main inventory in the same content PR; do not mark a family complete from a plan or provisional receipt.
