# Missing sources of the adopted records

Measured on `origin/main` (adc324851b) by reading every record under `record_paths` (3,706 records: 1,831 placements,
1,867 adopted, 6 generated, 2 maps). An adopted record is **source-less** when it has no `[[sources]]` and no
`recipe`. There are 1,285 of them, in two groups: 801 restricted and 484 open. The 582 adopted records that already
list `[[sources]]` were checked against the hydrated LFS content of `jim5/yv2-statics-run` (read-only): all 3,089
listed sources are present and match their hashes. In a checkout made with `GIT_LFS_SKIP_SMUDGE=1` the same binaries
are still pointer files, so their hashes differ until `git lfs pull` runs.

## Totals

| Group | Records | Packages | Status |
|---|---:|---:|---|
| Restricted, pinned | 801 | 5,997 | restricted original via pinned route (all 801 packages are in `restricted.lock.json`) |
| Open, generator present | 479 | 2,946 | generator present; recipe not yet written |
| Open, generator missing | 3 | 124 | the clip libraries are not in the donor |
| Open, editor-owned | 2 | 2 | the saved packages are the source; not a generator case |
| **Source-less total** | **1,285** | **9,069** | |

Recovered this round: **0 families, 0 records.** No record was changed. See "Why no record was flipped" below.

## Family table

Counts are from the adopted records. "Generator" names the donor file or step (in `games/yorimichi/`) that writes the
packages' meshes or textures. Status values: *generator present (recipe not written)*, *generator missing*,
*editor-owned*, *restricted, pinned*.

| Family | Records | Packages | Status | Generator (donor) | Controller command |
|---|---:|---:|---|---|---|
| experiments/citysurfaces | 159 | 1,048 | generator present (recipe not written) | `city_tile_products.py`, step `world.city_tiles` | `ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi world.city_tiles` |
| brinecove | 196 | 510 | generator present (recipe not written) | `brinecove_atomic_build.py`, step `world.brinecove.meshes` | `ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi world.brinecove.meshes` |
| belmontetrain (7 coaches and their doors) | 7 | 540 | generator present (recipe not written) | `train_carriage_build.py`, `train_atomic_build.py`, step `world.belmonte_train_furniture_lods` | `ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi world.belmonte_train_furniture_lods` |
| experiments/islandterrain | 12 | 287 | generator present (recipe not written) | `island_atomic_products.py` | `ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi --list` (find the island terrain step, then build it) |
| japan/assets (bike, sailboat, treehouse, zeppelin, mega) | 58 | 131 | generator present, partial (the audit lists generator references only) | `vehicle_atomic_build.py`, `bike_atomic_products.py` | `ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi --list` (find the bike and vehicle steps, then build them) |
| belmonte (north apron and country, shared materials) | 4 | 123 | generator present (recipe not written) | `belmonte_scene_build.py`, `belmonte_atomic_build.py`, step `world.belmonte.meshes` | `ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi world.belmonte.meshes` |
| japan/treehouse, materials, textures, southwest, lake, hidamari | 23 | 117 | generator present (recipe not written) | `treehouse_atomic_build.py`, `southwest_atomic_build.py`, `lake_atomic_build.py`, `hidamari_build.py`, step `world.treehouse_textures` | `ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi world.treehouse_textures` |
| experiments/citytrees, villageatomic | 2 | 55 | generator present (recipe not written) | `village_atomic_build.py`, `build_foliage_lods.py`, step `unreal.city_tree_lods` | `ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi --list` (confirm the tree LOD step, then build it) |
| skatepark (board, decals, textures, loose files) | 4 | 47 | generator present (recipe not written) | `skatepark_build.py`, `skatepark_atomic_build.py`, step `world.skatepark_textures` | `ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi world.skatepark_textures` |
| hippodrome | 4 | 31 | generator present (recipe not written) | hippodrome atomic (`hippodrome` region step `world.hippodrome`) | `ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi world.hippodrome` |
| megapark (seam, wood and pavement materials) | 3 | 26 | generator present (recipe not written) | `megapark_atomic_build.py`, `megapark_textures.py`, step `world.megapark_restyle` | `ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi world.megapark_restyle` |
| swordcamp | 3 | 17 | generator present (recipe not written) | `swordcamp_build.py`, step `world.swordcamp_atlas` | `ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi world.swordcamp_atlas` |
| fx (textures and loose files) | 2 | 12 | generator present (recipe not written) | step `fx.textures` | `ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi fx.textures` |
| racing | 1 | 1 | generator present (recipe not written) | `racing_assets.py`, step `data.racing_assets` | `ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi data.racing_assets` |
| skateruntime | 1 | 1 | generator present (recipe not written) | step `skate.runtime` | `ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi skate.runtime` |
| adventure (reference clips, loose files) | 2 | 123 | generator missing (the clip libraries are not committed in the donor) | `characters.adventure` writes only the rig | none until the clip source is located |
| japan/animation | 1 | 1 | generator missing (animation origin not recorded) | none | none until the source is located |
| megapark/standalone-level | 1 | 1 | editor-owned (a saved map) | none | `uv run python games/yorimichi_v2/tools/content/save_validate.py adopted/megapark/standalone-level` after a save |
| seethrough | 1 | 1 | editor-owned candidate (material parameter collection) | none | confirm with the owner, then `save_validate.py` |
| restricted: skateride 692, craterpark 68, japan 7, audio 5, character animation 29 | 801 | 5,997 | restricted, pinned | none (the restricted original) | `V2_RESTRICTED_SOURCE=DIR uv run python games/yorimichi_v2/tools/restricted/fetch.py fetch` |

The `ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi <step>` commands are donor generation steps. Each one
runs Blender under the controller's guard, so run `atelier build yorimichi --list` first to confirm the step name. A
step marked "find" or "confirm" has no single name in `games/yorimichi/build.py` for its family, so the controller
must pick it from the list. None of these steps was run here, so the output names and determinism are not verified.

## Why no record was flipped

The kei recovery (commit 3fb5f71f77) converted records to `generated` only after a real import wrote `verified.json`
with `kind = "imported"` and a matching input fingerprint. `tools/content/check.py` requires that. A `generated`
record whose `verified.json` is `editor-saved`, or which has no fingerprint match, fails with `AUTHORITY`,
`STALE_IMPORT` or `RECORD_MISSING`, and a missing `src/` file fails with `MISSING`. Flipping a record without its
import would therefore break the content check and the build on `main`.

The targeted importer (`tools/import/run.py`) also supports only the `static-mesh` and `texture` importers, so the
recipe can only be imported for mesh and texture families. Audio, animation and map families need a new importer
first.

The next step for each family is the donor generation step above, then:

1. copy the generated `.fbx` into the record's `src/` and record its sha256 in `[[sources]]`;
2. write the `recipe` (importer, version, settings) and set `authority = "generated"`;
3. run `uv run python games/yorimichi_v2/tools/import/run.py ID --plan`, then the same without `--plan` under the
   controller;
4. commit the record, its `verified.json` and the source together.

## Open items

- The donor step names above are those in `games/yorimichi/build.py`. None was run, so the output file names and
  determinism of each family are unverified.
- The 1,285 source-less records describe `origin/main`. The LFS branch `jim5/yv2-statics-run` differs by 232 asset
  files, so its records must be measured again before any batch lands.
- The 13 `asset.toml` files under `assets/adopted/japan/treehouse/prop-futon/source/` are donor sources, not records
  (`record_paths` excludes them).
