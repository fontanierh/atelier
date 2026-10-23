# Hidamari stable (陽だまり厩舎)

Henry's racing stable, one of the two player stables of the racing V1 (Paul's is at Belmonte). It stands on the flat
slope above Hidamari's north edge, east of the [Hidamari Hippodrome](../../../docs/HIPPODROME.md), in Hidamari's
style: charred cedar boards under cream plaster, dark timber frames, blue-grey kawara tile roofs, paper lanterns and
stone tōrō. A dirt road carries on from the end of the city's street at x = 920 and climbs to its roofed gate.

```sh
uv run atelier build yorimichi world.hidamari_stable                              # independent source/export assembly
uv run atelier build yorimichi unreal.compile unreal.hidamari_stable                # /Game/HidamariStable/Atomic
uv run atelier live py "live.stable('aisle')"                                       # in game: arrival, aisle, yard, paddock
uv run pytest games/yorimichi/tests/test_hidamari_stable_layout.py -q
```

The Stable remains disabled by the committed paired Python/C++ switch. Its source/query/export and native steps are explicit; a normal disabled build refuses before generating artifacts. Enabling it requires the complete saved-native equivalence checks. The pad and its slopes are not a mesh: they are
Hidamari's own terrain. `hidamari/layout.py height()` passes its ground through `grade()` here, so `HD_Terrain`, the
heightmap, the scatter and the foliage all see the graded ground and keep Hidamari's grass and material. Every step that
reads `hidamari/layout.py` therefore also lists this `layout.py` as an input. `world.hidamari_stable` needs
`world.layout`, Treehouse dimensions and the selected Crater geometry for the complete canonical height-query closure. The old review script consumes a historical diagnostic blend; it is not a production export or an acceptance fallback.

`unreal.hidamari_stable` (`unreal/Scripts/import_hidamari_stable.py`) imports the stable with its three LODs and the
placements' axis-aligned boxes as simple collision (the roof as steps), the door leaves, the walkable pad and road, and the
road's sign. The stable, its doors and the sign use Hidamari's `M_Arcade` vertex-colour material. The yard, paddock and
path overlays and the road carry Hidamari's surface slots (`HDS_<slug>`, `hidamari/surfaces.py`) and take the city's own
`MI_HD_<slug>` materials, as its yards and lanes do (made by `unreal.world`). It writes `Content/Data/hidamari_stable/stable.json`.
`AHidamariStable` (`HidamariStable.cpp`) places them at runtime: `JapanWorld` spawns it when that file exists and
removes the island's trees inside its clearance polygons. It keeps the stalls (name plates, horse spots, sliding doors
through `SetDoorOpen`), the sign, the transfers board and the NPC spots for the racing game.

## Site

| | |
| --- | --- |
| Frame origin (`SITE`) | (955, 447) island metres, chosen by Paul; Unreal (95500, -44700) cm |
| Pad top (`PAD_Z`) | 45.6 m, where cut and fill balance: the natural ground runs from 47.0 m (north edge) to 42.6 m (south edge). `grade()` cuts about 1.4 m into the north and fills about 3 m in the south, with slopes of 1 in 4 (14°, `GRADE_SLOPE`) rounded at the crest and toe, back to the natural ground within 22 m (`GRADE_REACH`). The slopes are Hidamari's terrain, grass and foliage included |
| Orientation | yaw 0: the barn's ridge runs east-west. The gate faces west, onto the road |
| Footprint | pad x −40..40, y −35..35 (80 × 70 m) round the origin |
| Distance to the course | barn centre about 250 m from the oval's outer rail; the pad and its slopes stay outside the hippodrome's clearance polygons. The pad's south edge (y 412) and its slopes reach into the city's bounds, clear of its buildings and streets |
| Road | 5 m dirt lane, 145 m: north from the end of the street at (920, 350, 36.7 m), a bend west to x = 890, north there, round the south slope, and east into the gate (`ROAD_CONTROL`, bends of 9 m radius). It lies on the graded ground (about 7 % uphill) and eases onto the pad's height over its last 14 m. Two stone lanterns and a plank sign 陽だまり厩舎 mark it at the street |

The island has trees on this terrace. `placements.json` lists `clearance` polygons (the pad with a 4 m border, and the road's corridor):
the importer has to remove the island's trees and grass inside them, as the hippodrome does. The slopes keep theirs.

## Plan (stable frame, metres)

- **Barn (umaya)**: 23.25 × 11.5 m, centred at (6, 12), walls 3.9 m, ridge 6.7 m, 26° kawara gable roof and a
  raised ridge vent (koshi-yane). The 3.5 m central aisle runs east-west between two 3.2 × 3.3 m doors (west to the
  yard, east towards the paddock).
- **Stalls**: 10 boxes of 3.6 × 3.6 m, 5 on each side (N1–N5, S1–S5, west to east). Each has a 1.4 × 2.45 m sliding
  door on the aisle that opens west, and a blank name plate (0.42 × 0.28 m, centre 1.75 m above the floor) east of the
  door: stats plaques go there later. Each stall also has a barred window with a propped shutter, a hay rack and a bucket.
- **West bay**: the tack room (north: saddle racks, bridles, chest) and the jockeys' office (south: desk, stools,
  trophy shelf and the cork **transfers board** on its east wall). Each opens onto the aisle through a 1.0 × 2.15 m
  sliding door. A hay loft sits over them.
- **Yard**: sand, between the gate and the barn. It holds a stone water trough with a bamboo spout, a hitching rail,
  four stone lanterns, hay bales and garden trees.
- **Gate**: two posts with a small tiled roof and a 4.2 m opening, flanked by bamboo fences. The name plate
  陽だまり厩舎 (2.6 × 0.72 m) hangs on its west face.
- **Paddock**: 36 × 32 m south of the barn, post-and-rail fence 1.35 m, with a 3.6 m gate in its north side.

## Atomic outputs

| Path under `build/yorimichi/` | Holds |
| --- | --- |
| `stable-source-data/<source>.json` | One observed original random state for each independent semantic/LOD constructor |
| `stable-query-data/` | Complete canonical height-query inputs, separate from rendered exports |
| `stable-sampled-queries/` | Exact requested Road/RoadSign height samples and original placement site data |
| `planned_exports/hidamari_stable/<source>/` | One bounded primary's complete positions, ordered corners, normals, UVs, colours, material graph and frame |
| `atomic_regions/hidamari_stable/assets/*.glb` | 24 independently cached single-primary GLBs; assembly copies files and never joins geometry |
| `hidamari-stable/atomic-manifest.json` | Complete ten-parent native membership, coordinated LOD chains, material/collision policy and original logical budgets |
| `hidamari-stable/placements.json` | Original site, pivots, travel, stalls, rooms, anchors, canonical road and clearance data, with five separate Stable semantics |

Barn, BarnRoof, Gate, Yard and Paddock each retain three LODs. StallDoor and RoomDoor
retain their original three LODs; Ground, Road and RoadSign remain singles. Native
assets stay separate under `/Game/HidamariStable/Atomic`. A separate logical bounds
override preserves the original whole Stable's coordinated LOD box and true sphere;
source AABB approximations are not accepted as native equivalence. The original
whole AABB collision table is owned once by Barn; the other four semantic components
retain zero shapes. Door collision must match the original saved/reloaded
three-LOD control; source bounds alone do not prove that policy. Ground, Road and
RoadSign remain complex-as-simple.

All meshes and placements are in the stable's frame: Blender metres, origin on the pad's top at `SITE`, glTF exported
Y-up by Blender. Island = `SITE` + p; Unreal = (100 x, −100 y, 100 z).

Budgets (`layout.BUDGETS`, checked by the build): LOD0 ≤ 60k triangles, LOD1 ≤ 15k, LOD2 ≤ 2.5k, a stall door ≤ 600,
and at most 120 collision boxes. Suggested LOD screen sizes are 1.0, 0.35 and 0.12.

## Files

| File | Holds |
| --- | --- |
| [`layout.py`](layout.py) | Every number: site, barn, stalls, rooms, yard, gate, paddock, road, spots, clearance, collision boxes (standard library and numpy) |
| [`build.py`](build.py) | The Blender model with Hidamari's kit (`village.build.Mesh`, `hidamari/kit/kawara.py`), exports and placements |
| [`render.py`](render.py) | The control renders, with the island's ground, the city's two streets, the hippodrome's meshes and scattered autumn trees |
| [`../../../tests/test_hidamari_stable_layout.py`](../../../tests/test_hidamari_stable_layout.py) | The programme, the doors, aisle and gate clearances, the site, the grading and the road |
