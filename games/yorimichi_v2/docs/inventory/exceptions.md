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
linked Adventure/animation records. The other **48 records / 678 packages** comprise:

| Family | Records | Packages |
|---|---:|---:|
| Residual Belmonte train packages | 7 | 459 |
| Japan materials (41 prepared, 2 blocked: see below) | 7 | 43 |
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
for all 138 donor-backed ids, after the generator's own source record is pinned.

## Japan materials: source closure (prepared, not applied)

The seven adopted records `adopted/japan/materials/{bark, buildings, foliage, ground, rock-concrete, sky-wind, water}`
hold 43 packages, all `MI_*` material instances in `/Game/Japan/Materials`, all `authority = "editor"`. They have no
`[[sources]]` and no recipe, and they stay that way: adding sources would make `check.py` report `STALE_IMPORT`.

Result: **0** imported textures or meshes (a). **41** generator-built instances (b): **Prepared, read-confirmed**,
the saved parent and parameters match the donor script on every row. **2** used leaf instances
(`MI_LeafAmber`, `MI_LeafCrimson`): **Prepared, recipe recorded**. No row is Blocked. Nothing here is verified
closure: the read confirms parameters only, and no import has been compared with the accepted packages.

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
| `MI_LeafAmber` | `foliage` | Prepared, recipe recorded | `M_Foliage` | `T_leaf_amber` | recipe below (no donor builder) |
| `MI_LeafBroad` | `foliage` | Prepared, read-confirmed | `M_Foliage` | `T_leaf_broad` | shared_materials.py build_materials |
| `MI_LeafCedar` | `foliage` | Prepared, read-confirmed | `M_Foliage` | `T_leaf_cedar` | shared_materials.py build_materials |
| `MI_LeafCrimson` | `foliage` | Prepared, recipe recorded | `M_Foliage` | `T_leaf_crimson` | recipe below (no donor builder) |
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
originals.

### Recipe for the two used leaves

`material-instance` is a valid record kind (`tools/content/records.py`), but no record uses it and no recipe fields
are defined for it, so the recipe is recorded here rather than as a new schema.

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
(2) an editor reproduction of the two leaf recipes, compared with their accepted packages; (3) a read of the
base-property overrides of the 13 rows; (4) the texture imports listed above, compared with the saved parents.
Counts are pinned by `tests/test_japan_materials_sources.py`.

Brine Cove's source-preservation route is applied by #787: 148 carved tile records keep their fused original and a
carve selection, and each remainder derives byte-identically (see [sources.md](sources.md)). No accepted package changed.

## Evidence and updates

The counts above were read from canonical `asset.toml` files in the immutable Git tree, excluding files nested
inside another asset's source folder. A loose filesystem glob can include stale/untracked records and donor copies.
`verified.json` and `objects.saved.json` distinguish imported packages from saved placements. Keep changes to this
page and the main inventory in the same content PR; do not mark a family complete from a plan or provisional receipt.
