# Brine Cove split batch 1: 11 small props out of the fused harbour, prop and market tiles (ships held back)

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

One tool. `DONOR` is the donor's `build/yorimichi` folder (read only). Tests: `tests/test_brinecove_split.py` (reader,
components, anchors, partition, writer) and `tests/test_brinecove_split_apply.py` (edits, touched set, refusal paths, journal).

**Scope.** The default batch is the 11 complete small props: both cranes, the fish shed, both net racks, both cannons, the
quay anchor, the market well, the auction block and the shipyard yard (with their Soft parts: 14 part records). `galleon-nightjar`
and `sloop-east` are held back until the Nightjar's hull follows its upperworks: the three ship tiles and the
`ships-nightjar-sloop` actor stay as they are. `--only a,b` picks any subset (including the ships).

| Command | Does |
|---|---|
| `plan --donor DONOR` | splits into the stage folder (`build/yorimichi_v2/brinecove-split`, never committed) and prints each part and remainder |
| `paths --donor DONOR [--json]` | prints the complete touched sets (apply, then retire) and the claim scopes |
| `apply --donor DONOR --claim TASK` | preflight, claim check, then write; never deletes |
| `check [--donor DONOR]` | after the import: triangles, bounds, hashes, partition, drawn once |
| `retire --donor DONOR --claim TASK` | deletes stale parts, retired tiles and the actors that must be saved again, and their runtime groups; refuses unless `check --records` passes |

**What `apply` writes** (only after every check passed): one generated record per part, `assets/prop/brinecove/<object>`
(`<object>-soft` for a part cut from a Soft tile, which has no collision), source = the part GLB copied into its `src/` and
pinned by sha256 (the layout recover.py uses), recipe = the tile's own; each touched tile record with its remainder as the new
source; the objects.toml head with the objects; `split-batch1.json` (the expectation); the runtime scenery file (a group per
part, the remainders' material lists) and `runtime-data.lock.json`.

**Preflight, then mutation.** Before the first byte is written, `apply`: reads the hydrated runtime file (a pointer or invalid
JSON refuses), finishes all splitting into the stage folder, computes every output in memory, and requires the claim to cover
the whole touched set through `authority.authorize` (the path `objects.py` and `run.py` use: the claim's scopes plus a live
check that its verified locks cover exactly these paths). Any failure refuses with the tree unchanged (tested byte for
byte). Then it journals every file it will write (`unreal/Saved/BrinecoveSplitJournal`, the import journal's model),
makes writable only the touched files that Git marks `lockable` (what git-lfs does for a locked file; read-only
unlockable files stay read-only and the write fails and rolls back), writes, and closes the journal. A failure restores every
file; a crash is restored at the start of the next run. A rerun with nothing to change writes nothing.

**Nothing is deleted by `apply`.** Replaced tile packages are overwritten by their import; retired packages (the three ship
tiles' and the actor's, only if the ships are in the batch) stay in place until the replacements are accepted. `retire`
then deletes them, with the retired actor's entries in `objects.toml`, `objects.saved.json` and the runtime file.

### Controller sequence

```
DONOR=build/yorimichi
CMD="uv run python games/yorimichi_v2/tools/migrate/brinecove_split_apply.py"
git lfs pull --include="games/yorimichi_v2/unreal/Content/Data/brinecove/runtime.json"
$CMD plan  --donor $DONOR                  # read the plan: parts, remainders, stale parts, objects to save again
$CMD paths --donor $DONOR                  # three lists (apply, retire, objects step) and every scope
#   ONE claim TASK holds all three lists and every scope printed: objects.py needs a single active claim whose scopes
#   cover both region/w09-brinecove and region/w00-island.
$CMD apply --donor $DONOR --claim TASK     # exactly the changed records; refuses with no change on any failure
IDS=$(git status --porcelain games/yorimichi_v2/assets/prop/brinecove | sed -n 's#.*assets/\(prop/brinecove/[^/]*\)/asset.toml#\1#p' | sort -u)
uv run python games/yorimichi_v2/tools/import/run.py $IDS --claim TASK --batch 8     # one claimed warm batch
$CMD check --records --donor $DONOR        # records, sources, receipts, vertex-level partition (placements not yet)
$CMD retire --donor $DONOR --claim TASK    # stale parts, and objects that must be saved again, are deleted
uv run python games/yorimichi_v2/tools/migrate/objects.py region/w09-brinecove --environment region/w00-island \
  --claim TASK --only <the new and re-saved object ids>        # saves them; kept actors are untouched
$CMD check --donor $DONOR                  # everything, drawn-once included
uv run python games/yorimichi_v2/tools/content/check.py
```

### Updating a batch already applied (the palm correction)

The first batch's radius rule took the harbour palms standing next to the west crane (-330, 72) and the fish shed (300, 72)
(donor `procedural/harbor.py` lines 97-103: stone planter, trunk and fronds) into `crane-west`, `crane-west-soft` and
`fish-shed-soft`. The anchors for those two objects now carry `exclude_zones` (the palm's base, 5 m: a palm's trunk, planter
and every frond card lie within it), so each whole palm stays in its tile. Rerunning the tool on a tree that already holds the
first result re-plans from the expectation file (`split-batch1.json` keeps each tile's original settings), so:

- `crane-west` (410 to 168 triangles; it now equals `crane-east`) and `fish-shed` (678 to 468) are rewritten;
- `Harbor_2_3` and `Harbor_5_3` remainders grow (2,436 to 2,678 and 3,198 to 3,408), and `Harbor_2_3_Soft` and
  `Harbor_5_3_Soft` go back to the donor's own 90-triangle meshes (nothing takes from them any more);
- `crane-west-soft` and `fish-shed-soft` are empty and become *stale*: `apply` leaves them, `retire` deletes their
  records, packages and runtime groups, and drops the objects whose group list changed from the saved list so
  objects.py saves them again (an object's saved definition may not change).

Remainder actors that were saved before the split keep working: a remainder keeps its package name, so its actor shows the
new remainder after the re-import. Where a remainder lost a material, its slot list shrinks (listed by `plan`), so those
actors (`harbor-2-3`, `harbor-5-3`, `harbor-5-4`, the four `props-*` and the two `market-*` objects) must be checked for
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
