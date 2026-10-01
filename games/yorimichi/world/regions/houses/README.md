# Houses on the main road

Five rural houses (minka) stand beside the coastal road in the west, each on its own levelled lot and facing the
road the way someone would build their own house there: the entrance and a short approach face the road, the house
sits back behind a stone kerb and a clipped hedge, a gate opens in the hedge in front of the entrance, stepping
stones cross a gravel yard to the genkan, and a small garden (stone lantern, clipped pine, red maple, moss and rocks)
fills the other front corner. Where the ground falls away, battered dry-stone walls (ishigaki) hold the terrace;
uphill lots are cut into the bank and reached by three steps up through the gate. Trees and bushes are kept off the
walls, the roofs and the path.

The concept paintings behind the design are in [assets/houses](../../../assets/houses/README.md).

| Lot | Road s | Side | House | Centre (x, y) | Level |
| --- | --- | --- | --- | --- | --- |
| HouseLot_1 | 96 m | downhill | House_A | (-195.7, -108.2) | 8.68 m |
| HouseLot_2 | 147 m | uphill | House_B | (-155.2, -65.3) | 9.85 m |
| HouseLot_3 | 177 m | uphill | House_C | (-125.1, -57.4) | 10.65 m |
| HouseLot_4 | 327 m | downhill | House_A | (26.3, -55.6) | 16.39 m |
| HouseLot_5 | 357 m | uphill | House_C | (47.8, -19.0) | 17.26 m |

The three houses:

- **House_A**: single storey, tiled hip-and-gable (irimoya) roof with ridge tiles and onigawara, engawa across the
  front with glass sliding doors and shoji transoms, a gabled entrance porch with lattice doors.
- **House_B**: thatched farmhouse (kayabuki) with a tiled ridge cap and crossed ridge logs, wide engawa with storm
  shutters and shoji, a plank door to the earth-floored doma, a koshi window, a woodpile lean-to.
- **House_C**: two storeys, a pent roof round the ground floor, a gabled upper roof, a balcony, koshi windows and
  lattice entrance doors under a small gable.

All three stand on foundation stones, with timber posts, plaster walls and deep eaves over exposed rafters.

## Files

| File | What it does |
| --- | --- |
| `layout.py` | Pure numpy, called by `gen_world.py`. Chooses the lots (`LOTS`), levels each terrace into the heightmap and blends it back to the hillside, clears the scatter off the lots, walls and roofs, and places the garden and hedge-side planting. Writes `world['houses']` (lots, removed scatter, dressing) and the `House_*` / `HouseLot_*` instances. `HOUSES` holds each variant's walls, ground and roof footprints and door position; `build.py` models to those numbers. |
| `build.py` | Blender. Models House_A/B/C in the lot frame (origin at the house centre on the lot level, -y toward the road) with the village kit's single vertex-colour material and UCX boxes for collision, and builds one HouseLot mesh per lot against the final heightmap. |
| `preview.py` | Blender Workbench. Renders every lot from across the road at the player camera's height and from above, with stand-ins for the trees, bushes and poles around it. |

The world instance of a house and of its lot share the same position and yaw, so a lot can be moved by editing
`LOTS` alone. Lot keys in `world['houses']['lots']`: `centre`, `level`, `yaw`, `front` (the hedge line, local),
`polygon` (the lot outline, local), `gate`, `house_ground` and `house_roof` (local footprints) and `garden`.

## Build and check

```sh
uv run atelier build yorimichi world.layout world.houses
blender -b --python-exit-code 1 --python games/yorimichi/world/regions/houses/preview.py -- [OUT_DIR] [LOTS]
```

`world.houses` writes `build/yorimichi/houses/`: the FBX files in `assets/`, `Houses.blend` (every house on its
lot), `manifest.json` (triangles, materials, collision boxes, bounds) and `build-identity.json`. The preview writes
`build/yorimichi/review/houses/preview/lot<k>_road.png` and `lot<k>_above.png`; run it through `atelier.safety`
(render lock and memory guard).

`layout.py` checks that nothing from the scatter stands on a lot, its walls' berm or its verge, and that no tree
crown reaches over a roof (the gardens' own planting excepted). The grading never touches the road and its
shoulders, nor the ground the skate path was laid on (the level pad by the road at s = 150). The skate pier build
(`world.skatepark`) reports the path's distance to the nearest roof and lot and fails if the path crosses a lot.

## Unreal

```sh
uv run atelier build yorimichi unreal.houses
```

`unreal/Scripts/import_houses.py` imports the eight meshes into `/Game/Japan/Assets`, checks they were built for the
current layout and terrain, gives the houses M_Village and their UCX boxes (simple and complex), and gives the lots
M_Village plus the terrain's MI_Ground on the terrace (complex as simple, so the terrace, steps, hedge and walls are
solid). `AJapanWorld` places them from `world.json` like any other instance. The terrain changes with the lots, so
`world.terrain` and the terrain import (`unreal.world`, or `unreal.southwest`, which reimports it) must run as well.
