# Brine Cove fixed objects

Brine Cove scenery is runtime-spawned from `unreal/Content/Data/brinecove/runtime.json`. The donor generator
(`games/yorimichi/world/regions/brinecove`) bakes each feature collection into meshes `SM_BC_<Feature>_<tx>_<ty>[_Soft]`
by 256 m tile of the face centre; `bounded_parts` may split a tile into `_PieceN`. An object is "alone" when its faces
are the only ones in the group. Face buckets below were measured by running each generator function on its own
(`modules.Builder`, no `bpy`), the same method as the wreck's.

Saved in `world/regions/w09-brinecove/objects.toml`: wreck, galleon-adventure, lighthouse, fort.

| Object | Generator | Group(s) | Alone or fused |
|---|---|---|---|
| wreck | `modules.ship(-492,-246, unfinished=True)` | `SM_BC_Ships_2_2` | alone (saved) |
| galleon Adventure (rig, deck) | `modules.ship`, `layout.SHIPS[0]` | `SM_BC_Ships_3_3` | alone (saved); hull is a hero model, see below |
| lighthouse | `modules.lighthouse` (collection `06_landmarks`) | `SM_BC_Landmarks_1_3`, plus `_Soft` (237 foliage faces: leaf and palm planting) | alone; two groups. Saved with the main group; the planting stays in the scenery |
| fort | `landmarks.fort` | `SM_BC_Landmarks_3_5` | alone (saved) |
| galleon Nightjar | `modules.ship`, `SHIPS[1]` | `Ships_4_3` (3671 faces), `Ships_4_2` (94) | fused: `Ships_4_3` also holds the sloop |
| sloop East | `modules.ship`, `SHIPS[2]` | `Ships_4_3` (3235), `Ships_5_3` (1394) | fused with the Nightjar in `Ships_4_3` |
| galleon hulls (3) | hero model `galleon-hull`, `hero_placements` | `Hero_GalleonHull_cell_{-1,0}_{-1,0}` (4 cells) | each cell group holds all 3 hulls (3 transforms); one hull is not alone |
| pirate queen statue | hero model `pirate-queen-statue`, `L.STATUE` | `Hero_PirateQueenStatue_cell_*` (4 cells, 1 transform each) | alone, but spread over 4 groups; objects.toml takes one group |
| harbour capstans (2) | hero model `harbor-capstan` | `Hero_HarborCapstan` (2 transforms) | the group holds both capstans; one capstan is not alone |
| waterfall, canyon river, rope bridge, ledge shrine | `falls.waterfall` (inside `landmarks()`) | `Landmarks_5_3`, `_5_4`, `_6_3`, `_6_4`, each with `_Soft` and `_Piece` splits (about 20 groups) | alone among groups (only the waterfall lands in those tiles), but many groups |
| shipyard (hull on cradle, slip, scaffold, shed) | `landmarks.shipyard`, called in `modules.harbor` | `Harbor_5_3` (4655 faces, plus its Soft), `Harbor_5_4` (320) | fused with quay, piers, cranes, crates |
| quay cannons (2) | `landmarks.cannon` x2 in `modules.props` | `Props_3_3` (-206,88), `Props_4_3` (210,88) | fused with other props |
| quay anchor | `landmarks.anchor` in `modules.props` | `Props_2_3` | fused with other props |
| market stalls (19) | `kit.market_stall`, `layout.MARKET_STALLS` | `Market_3_3`, `Market_3_4*`, `Market_4_3`, `Market_4_4*` pieces | fused with cobble, wells and each other; 3 to 4 k faces each |
| harbour cranes (2), rowboats, buoys | `modules.harbor`, `modules.props` | `Harbor_*`, `Props_*` | fused |
| town houses | `modules.lower_town`, `upper_town`, `layout.BUILDINGS` | `TownLower_*`, `TownUpper_*` `_Piece` meshes | fused; not checked per building |

## What extracting a fused object needs

For every fused object: split its faces out of the tile mesh in the generator, export it as its own mesh, and rebuild the
tile meshes without it. The exporter keys a face by centre, so the piece's faces must be excluded from the tile pass.

- **Nightjar and sloop**: `modules.ships()` loop over `L.SHIPS`; build each ship in its own `Builder` and export as
  `SM_BC_Ship_<name>`. Changes `Ships_4_2`, `Ships_4_3`, `Ships_5_3` (they would be removed). `ship()` uses no RNG, so
  the geometry is reproducible alone.
- **Galleon hulls**: `hero_placements.placements` gives one transform per ship; `build.hero_models` spatial-partitions the
  model into cells and gives each cell all three transforms. Needs one hero group per ship (or the cell groups split per
  transform); changes the 4 `Hero_GalleonHull_cell_*` groups. Without that, the Adventure keeps a shared hull.
- **Statue and waterfall**: no fusion; they need `objects.toml` to accept several groups per object (`groups = [...]`),
  and the editor step to build all of them into one actor.
- **Capstans**: one object per transform, so split the transform list of `Hero_HarborCapstan` (changes that one group).
- **Shipyard**: `landmarks.shipyard(b)` into its own Builder (deterministic, no RNG); changes `Harbor_5_3`, `_5_3_Soft`,
  `Harbor_5_4`. Note `modules.harbor` calls it between the cranes and crates, so the harbour pass must skip it.
- **Cannons, anchor**: `landmarks.cannon` and `landmarks.anchor` into own Builders; change `Props_3_3`, `Props_4_3`,
  `Props_2_3`. Both are deterministic, but `modules.props` shares the module-level `RNG` (seed 49157) with the
  crates, barrels and palms, so removing them is safe only if the rest keep their RNG draw order.
- **Market stalls**: `kit.market_stall` per entry of `MARKET_STALLS`; the fixed-position stalls are deterministic, the
  random stalls at `modules.market` lines 758-777 draw from the shared `RNG`. Changes the `Market_3_3`, `_3_4*`,
  `_4_3`, `_4_4*` groups.

## Source gaps and cautions

- `modules.lighthouse` draws foliage from the shared `RNG`, so its `_Soft` planting depends on the draw order of earlier
  builders; the `Landmarks_1_3` hard mesh does not. Extracting the planting needs the RNG replayed or its positions saved.
- The ship, fort and lighthouse geometry have no recorded generator settings beyond the code; the hero models
  (galleon hull, statue, capstan) have glb plus provenance files in `games/yorimichi/assets/brinecove/models`.
- `HAS_STATUE` and `HAS_HULL` depend on the glb files existing; without them the generator builds the procedural statue and
  lofted hulls into other tiles.
- Face-centre buckets were measured in this repository checkout, not read back from the exported meshes.

## Suggested unit renames (the controller applies them)

| Now | Rename to | Reason |
|---|---|---|
| `landmarks-1-3` | `lighthouse` | holds the lighthouse alone, including `_Soft` |
| `landmarks-3-5` | `fort` | holds the fort alone |
| `landmarks-5-3`, `landmarks-5-4`, `landmarks-6-3`, `landmarks-6-4` | one unit `waterfall` | only the waterfall lands in those tiles |
| `ships-4-2`, `ships-4-3`, `ships-5-3` | `ships-nightjar-sloop` | the two other ships share these tiles |
| `hero-galleon-hull` | keep | shared model for three ships |
