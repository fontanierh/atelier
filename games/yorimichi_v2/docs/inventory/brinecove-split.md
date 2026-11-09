# Brine Cove split batch 1: 13 objects out of the fused harbour, ship, prop and market tiles

Group G4a of `exceptions.md`. Each object below is carved out of a fused tile mesh without changing a vertex, a material
or a transform. The split is **planned and proven in pure Python on the donor's exported GLBs**
(`tools/migrate/brinecove_split.py`, tests `tests/test_brinecove_split.py`); nothing was run in Blender or Unreal.

## How the split works

The donor bakes Brine Cove into tile meshes `SM_BC_<Feature>_<tx>_<ty>[_Soft|_PieceN]` (`build/yorimichi/brinecove/glb`,
one node, one mesh, one primitive per material). Every tile is placed with an identity transform (`runtime.json` `groups`:
`translation_cm [0,0,0]`, scale 1), so a part cut from a tile keeps the tile's frame and needs no re-pivot.
Builder primitives (boxes, beams) are not welded to each other, so the exported mesh has hundreds of small connected
components per object, not one. The tool therefore:

1. welds vertices (1e-4 m) and groups triangles into connected components;
2. gives each component to the nearest object anchor it lies within: ground distance to the object's generator
   position (layout `x`, `y`; the GLB ground plane is `(x, -y)`), a longest-side cap (quay, floor and terrain slabs
   are longer and never belong to an object), a lowest-vertex floor (slabs the object stands on are lower) and, where the
   object stands on a paved floor, a list of floor materials it never uses;
3. writes every object's part, and the tile's remainder, with source positions, normals, UVs and materials copied
   unchanged (`write_subset`), and checks per tile that the parts plus the remainder are exactly the tile's triangles
   (`verify_partition`: counts, per-material counts and a hash of the order-free welded triangle set).

Result on the donor export: 40 tiles written and re-read, **0 partition problems**. Both cannons come out at 2,732
triangles, a useful check that the same generator function gave the same part twice.

## The batch

| Object | Donor generator boundary | Donor output: tile mesh and triangles taken | Anchor: x, y, radius, max extent, min height (layout m) | Saved placement that references the fused tile now |
|---|---|---|---|---|
| galleon-nightjar | `procedural/ships.py` `ships()` -> `ship(b, 40, -132, ...)` scale 1.10, black canvas; `procedural/ship.py`. Rig, deck, guns, hull planking above the water; the shared hero hull stays in `hero-galleon-hull` | `SM_BC_Ships_4_2` 172; `SM_BC_Ships_4_3` 7428 (total 7600) | 40, -132, 110, 120, -50 | `object/brinecove/ships-nightjar-sloop` |
| sloop-east | `procedural/ships.py` `ships()` -> `ship(b, 252, -72, ... yaw 180, scale 0.45)`, cream sails | `SM_BC_Ships_4_3` 6540; `SM_BC_Ships_5_3` 2788 (total 9328) | 252, -72, 40, 120, -50 | `object/brinecove/ships-nightjar-sloop` |
| shipyard-yard | `landmarks.py` `shipyard(b)` (hull on cradle, scaffolds, shear legs, bench, shed, stacks), called from `procedural/harbor.py`. The stone slip is not included (see Not in the batch) | `SM_BC_Harbor_5_3` 8926; `SM_BC_Harbor_5_4` 632 (total 9558) | 376, 78, 36, 40, -5 excl. stone, stone_dark, stone_light | `object/brinecove/harbor-5-3`, `object/brinecove/harbor-5-4` |
| crane-west | `procedural/harbor.py` cargo cranes loop, (-334, 84), -22 deg | `SM_BC_Harbor_2_3` 410; `SM_BC_Harbor_2_3_Soft` 30 (total 440) | -326, 83, 14, 25, 4.5 | `object/brinecove/harbor-2-3` |
| crane-east | `procedural/harbor.py` cargo cranes loop, (412, 128), 16 deg | `SM_BC_Harbor_5_4` 168 (total 168) | 418, 127, 14, 25, 4.5 | `object/brinecove/harbor-5-4` |
| fish-shed | `procedural/harbor.py` fish market shed, `shed_x, shed_y = 305, 86` (posts, gable roof, counter, awning boards) | `SM_BC_Harbor_5_3` 678; `SM_BC_Harbor_5_3_Soft` 30 (total 708) | 305, 86, 21, 40, 4.9 | `object/brinecove/harbor-5-3` |
| net-rack-west | `procedural/props.py` net racks loop, (274, 70) | `SM_BC_Props_5_3` 672 (total 672) | 274, 70, 5.5, 12, 4.5 | `object/brinecove/props-5-3` |
| net-rack-east | `procedural/props.py` net racks loop, (286, 70) | `SM_BC_Props_5_3` 672 (total 672) | 286, 70, 5.5, 12, 4.5 | `object/brinecove/props-5-3` |
| cannon-west | `procedural/props.py` `LM.cannon(-206, 88, yaw 18, scale 2.5)` | `SM_BC_Props_3_3` 2732 (total 2732) | -206, 88, 8, 12, 4.5 | `object/brinecove/props-3-3` |
| cannon-east | `procedural/props.py` `LM.cannon(210, 88, yaw -14, scale 2.5)` | `SM_BC_Props_4_3` 2732 (total 2732) | 210, 88, 8, 12, 4.5 | `object/brinecove/props-4-3` |
| quay-anchor | `procedural/props.py` `LM.anchor(-292, 90, yaw 28)` | `SM_BC_Props_2_3` 2052 (total 2052) | -292, 90, 6, 12, 4.5 | `object/brinecove/props-2-3` |
| market-well | `procedural/market.py` well, `wx, wy = 47, 137` (stone ring, water disc, posts, gable roof) | `SM_BC_Market_4_4_Piece003` 128; `SM_BC_Market_4_4_Soft` 44 (total 172) | 47, 137, 4.5, 8, 4.5 excl. cobble, cobble_dark, stone_light | `object/brinecove/market-4-4` |
| market-auction-block | `procedural/market.py` auction block, `ax, ay = -44, 188` (platform, steps, canopy posts) | `SM_BC_Market_3_4_Piece130` 132 (total 132) | -44, 188, 7, 14, 4.5 excl. cobble, cobble_dark, stone_light | `object/brinecove/market-3-4` |

Bounds of each object as cut (metres, glTF axes, x/y/z with y up):

| Object | GLB bounds min / max (m, glTF axes) |
|---|---|
| galleon-nightjar | [26.9, 7.7, 84.3] / [54.0, 46.2, 164.6] |
| sloop-east | [246.8, 2.5, 58.4] / [257.2, 18.2, 91.9] |
| shipyard-yard | [340.9, 0.4, -106.5] / [408.5, 23.4, -53.0] |
| crane-west | [-338.2, 4.5, -84.2] / [-319.1, 18.1, -68.3] |
| crane-east | [407.8, 4.6, -132.6] / [427.5, 18.1, -127.8] |
| fish-shed | [288.0, 5.0, -94.1] / [322.0, 13.9, -68.0] |
| net-rack-west | [272.4, 4.8, -73.5] / [275.6, 9.2, -66.5] |
| net-rack-east | [284.4, 4.8, -73.5] / [287.6, 9.2, -66.5] |
| cannon-west | [-208.4, 4.7, -91.0] / [-203.8, 8.2, -83.1] |
| cannon-east | [208.0, 4.8, -91.1] / [212.3, 8.3, -83.1] |
| quay-anchor | [-294.2, 4.7, -92.0] / [-289.7, 10.8, -88.0] |
| market-well | [44.3, 4.8, -139.5] / [49.7, 10.3, -134.5] |
| market-auction-block | [-49.0, 4.7, -191.7] / [-39.0, 11.1, -184.3] |

Tile mesh totals for the remainder arithmetic: `Ships_4_3` 13,968 = 7,428 nightjar + 6,540 sloop; `Ships_5_3` 2,788 is all
sloop; `Ships_4_2` 172 is all nightjar. The other tiles keep the rest as `_rest`.

## Render, collision and LOD ownership

From `runtime.json` `groups` and the tile records' `[recipe.settings]`:

| Tile kind | Render | Collision | LOD |
|---|---|---|---|
| hard tiles (`Ships_*`, `Harbor_n_n`, `Props_*`, `Market_*_Piece*`) | shadow on, cull 1,200 m, one static mesh | `complex`, runtime `collision: true` | one LOD (`verified.json` `lods` count 1) |
| `*_Soft` tiles | shadow on, cull 1,200 m | none (`collision: false`, no `collision` setting) | one LOD |

Ownership after the split:

- **Each object's part mesh** becomes its own record `prop/brinecove/<object>` (render, complex collision and the single
  LOD are all this record's, copied from the tile it was cut from). Parts cut from a Soft tile are separate meshes
  (`<object>-soft`) without collision, so collision on the hard part is unchanged.
- **The tile record keeps the remainder** (its `src/` file becomes the `_rest` GLB; the sha256 and triangle count change,
  its collision and LOD settings do not). The tile's other objects, ground and unsplit geometry stay where they were.
- **Materials**: parts keep the tile's glTF material names, which map to the same `MI_BC_*` instances through
  `slot_materials` (a part keeps the source's whole material list, so slot indices are unchanged; unused slots are harmless).
  `adopted/brinecove/materials` is still referenced, not copied.
- **Placement**: a new `object/brinecove/<object>` placement (editor-owned, region `region/w09-brinecove`) places the part
  at identity with the same shadow, cull and collision flags. The existing placement that references the fused tile
  (last column) keeps the remainder. Nothing else moves.

## Mapping to the saved placements

The V2 world already holds one saved actor per fused group, referencing the tile model records, in
`world/regions/w09-brinecove/objects.toml`:

- `object/brinecove/ships-nightjar-sloop` (groups `SM_BC_Ships_4_2`, `_4_3`, `_5_3`, actor `.../3/RH/QSB99NGEX27RF32C1SHDZ7`)
  becomes two placements, `object/brinecove/galleon-nightjar` and `object/brinecove/sloop-east`. The old placement and its
  `adopted/brinecove/ships-nightjar-sloop` model unit retire when both remainders are empty (they are: the three ship tiles
  hold only these two ships).
- `harbor-5-3` (+ Soft) and `harbor-5-4` give `shipyard-yard`, `fish-shed`, `crane-east`; `harbor-2-3` (+ Soft) gives
  `crane-west`; `props-5-3` gives the two net racks; `props-3-3`, `props-4-3` and `props-2-3` give the cannons and the
  anchor; `market-4-4` and `market-3-4` give the well and the auction block. Those placements keep their remainders and stay.

`tools/migrate/objects.py` already reads `objects.toml` entries (`group`, `groups`, `model`); the new objects are
entries with `model = "prop/brinecove/<object>"` and the tile's group names removed from the old entry's share, which is a
planner change to `tools/migrate/recover.py` and `objects.py` (not made here: workers A and B own `recover.py`).

## Implementation (done): `tools/migrate/brinecove_split_apply.py`

One tool, three commands. `DONOR` is the donor's `build/yorimichi` folder (read only). Tests:
`tests/test_brinecove_split.py` (reader, components, anchors, partition, writer) and `tests/test_brinecove_split_apply.py`
(objects.toml and runtime-file edits, names, expectation shape).

- `plan --donor DONOR`: splits into the stage folder (`build/yorimichi_v2/brinecove-split`, never committed) and prints
  each part (triangles, bytes, tiles) and each tile's remainder. Nothing in the game changes.
- `apply --donor DONOR`: the same split, then
  - **records**: one generated record per part, `assets/prop/brinecove/<object>` (`<object>-soft` for a part cut from a
    Soft tile), package `/Game/Brinecove/Meshes/SM_BC_<Object>[_Soft]`. Its source is the part GLB copied into the
    record's `src/` and pinned by sha256 (the layout recover.py uses for copied donor sources; the donor folder is never
    referenced). The recipe is the tile's own: `static-mesh`, `collision = "complex"` (none for Soft parts),
    `full_precision_uvs`, `triangles`, and `slot_materials` for the part's used materials in first-use order.
  - **tile records**: the 12 touched tiles take their remainder as the new source (new sha256, triangles and slot list);
    the three ship tiles are empty and are retired with their package files.
  - **placements**: `objects.toml` gains the 13 objects in its hand-written head (`group` = the part mesh, or `groups`
    = hard + Soft part); the generated tail's `ships-nightjar-sloop` entry, its record, its `objects.saved.json` entry
    and its actor package are removed. The runtime scenery file (`unreal/Content/Data/brinecove/runtime.json`, must
    be hydrated) gets one group per part copied from the tile group (same flags, identity transform), the remainders'
    material lists, and no group for retired tiles; `runtime-data.lock.json` is rewritten. `--skip-runtime` leaves the data
    file alone (it then must be edited by a second `apply` before the objects are saved).
  - **expectation**: `world/regions/w09-brinecove/split-batch1.json` (per part and per tile: triangles, bounds, hashes,
    original settings, the tile's source triangles and each object's share). A rerun changes nothing (tested on a copy).
- `check [--donor DONOR]`: pure Python, after the import. Proves record, source hash, triangle count and bounds of every part
  against the expectation; remainder + shares = the tile for every tile; that each part mesh is a group of exactly one object
  and once in the runtime file with identity transforms; that retired tiles and the retired object are gone; that every
  record is imported (`verified.json`). With `--donor` it also proves, at vertex level, that all parts plus all remainders are
  exactly the donor tiles' triangles.

### What the split writes (donor export of 2026-11-07, run on the scratch stage)

28 files, 9.5 MB: 16 part meshes (4 KB to 1.0 MB, e.g. `SM_BC_GalleonNightjar.glb` 827,064 bytes, `SM_BC_SloopEast.glb`
1,014,504, `SM_BC_ShipyardYard.glb` 1,037,708, each cannon 299,632) and 12 remainders (7.6 KB to 1.5 MB).

### Controller sequence

```
DONOR=build/yorimichi                      # the donor export the records were recovered from
CMD="uv run python games/yorimichi_v2/tools/migrate/brinecove_split_apply.py"
git lfs pull --include="games/yorimichi_v2/unreal/Content/Data/brinecove/runtime.json"
$CMD plan  --donor $DONOR                  # read the plan
$CMD apply --donor $DONOR                  # records, remainders, placements, runtime file, expectation
for id in $(git status --porcelain games/yorimichi_v2/assets/prop/brinecove | sed -n 's#.*assets/\(prop/brinecove/[^/]*\)/asset.toml#\1#p'); do
  uv run python games/yorimichi_v2/tools/import/run.py $id    # under the controller's guard, one record at a time
done
uv run python games/yorimichi_v2/tools/migrate/objects.py region/w09-brinecove --environment region/w00-island \
  --claim TASK --only <the 13 new object ids>                  # saves the 13 new actors; kept actors are untouched
$CMD check --donor $DONOR                  # triangles, bounds, partition, drawn-once
uv run python games/yorimichi_v2/tools/content/check.py
```

Remainder actors that were saved before the split keep working: a remainder keeps its package name, so its actor shows the
new remainder after the re-import. Where a remainder lost a material, its slot list shrinks (listed by `plan`), so those
actors (`harbor-2-3`, `harbor-5-3`, `harbor-5-4`, the three `props-*` and the two `market-*` objects) must be checked for
material overrides copied from the old runtime list; `saved_objects.py` (below) shows any slot mismatch as a miss.

### Importer changes: none needed

`import_asset.py` already binds `slot_materials` by slot index, checks the slot count and the `triangles` count, applies
complex collision and full-precision UVs. Nothing in it changes.

### Ray collision and captures (run by the controller after the import)

```
uv run python games/yorimichi_v2/tools/test/saved_objects.py --zone brinecove_quay      # each object drawn once
uv run python games/yorimichi_v2/tools/parity/capture_runtime.py ...                    # fixed cameras, before and after
uv run python games/yorimichi_v2/tools/parity/compare.py BEFORE AFTER                   # zero changed pixels outside AA noise
```

For collision, trace the same rays (grid of 25 per object, 20 cm apart, from 3 m out on 4 sides) against the tile and the
part before and after and compare hit points within 1 cm.

## Proof the controller run needs

Source-registry entries and native receipts alone do not prove a split. The run must show all of:

1. **Partition** per tile: `brinecove_split.py plan` prints `"problems": []`, and the written parts plus `_rest` re-read to
   the source tile's triangle set (the check run here). Re-run on the controller's donor export, because a different export
   would move the numbers.
2. **Per-object triangle and bounds match** against the table above (counts exact; bounds within 0.001 m), and after
   Unreal import `verified.json` `triangles` equals the part's count, the material slots equal the part's materials, and
   the imported static mesh bounds equal the GLB bounds x 100 within 0.1 cm. Remainders: source minus parts, per tile.
3. **Collision**: the hard part imports with `complex` collision and the Soft part with none, as the tile did; a line
   trace set (the same rays before and after) over each object returns the same hit points within 1 cm.
4. **Draw once**: `tools/test/saved_objects.py` for `--zone brinecove_quay` (and the market and ship zones) draws every
   new and remaining placement exactly once; no double (the old fused tile plus the new part).
5. **Capture comparison**: fixed cameras per object (one overview, one close-up of the most detailed side, one from the
   water for ships and the yard), same time of day, before the split and after, compared with `tools/parity/compare.py`
   at a tolerance of zero changed pixels outside anti-aliasing noise; any difference blocks.
6. `uv run python games/yorimichi_v2/tools/content/check.py` passes and `save_validate.py` records each new placement.

## Not in the batch (and why)

- **Signal mast** (`market.py`, (0, 158)): its ropes and bunting reach 18 m and its flags and pole sit among market carts
  and parasols; a distance rule pulled 14,154 triangles of clutter, so it needs the generator to build it alone.
- **The 19 market stalls**: positions are jittered by the shared `RNG` and each stall brings its own barrel and crate; the
  bazaar clutter between them overlaps every radius. They need `kit.market_stall` in its own Builder and the RNG draw order
  replayed.
- **Shipyard slip** (the stone block in the quay wall's notch): welded into the quay wall component (1,342 + 268 triangles
  across `Harbor_5_3`, `Harbor_5_4`), so `shipyard-yard` takes everything except it. Splitting it needs the quay courses
  cut at the notch in `landmarks._slipway`.
- **Rowboats, cranes beyond the two, town houses, ship hulls**: unchanged from `brinecove-objects.md`. The galleon hulls
  stay shared in `hero-galleon-hull`, so `galleon-nightjar` is the rig, deck and guns.
- Two cargo discs near (408, 95) may sit on the yard's radius edge (36 m from the anchor); the capture comparison will show
  it, and the anchor can be shrunk by 1 m without touching the tests.

## Commands

```
uv run python -m pytest -q games/yorimichi_v2/tests/test_brinecove_split.py
python3 games/yorimichi_v2/tools/migrate/brinecove_split.py plan DONOR/build/yorimichi/brinecove/glb            # report only
python3 games/yorimichi_v2/tools/migrate/brinecove_split.py plan DONOR/build/yorimichi/brinecove/glb --out NEWDIR  # also writes parts
python3 games/yorimichi_v2/tools/migrate/brinecove_split.py components DONOR/build/yorimichi/brinecove/glb/SM_BC_Ships_4_3.glb --min-tris 30
```
