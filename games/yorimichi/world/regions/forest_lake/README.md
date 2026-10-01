# Hidden woodland lake

A secluded 68 × 46 m lake in the woods at Blender (-90, 235), west of the mini-mega, with a fisher's cabin and a
timber jetty on its shore. A winding dirt trail leads from the ramp clearing to the cabin; the existing autumn trees
close round the clearing. The boat and the fishing gear are scenery: there is no fishing or rowing. The world map's
**Hidden woodland lake** zone lands on dry ground beside the cabin.

## Build and check

```sh
uv run atelier build yorimichi unreal.lake data.stage
uv run atelier qa yorimichi lake LABEL [shot ...]
```

- `world.layout` calls `forest_lake.layout.integrate` from `gen_world.py`, after the village, the mini-mega and the
  south-west. It digs the lake bed, levels the cabin pad, carves the trail and clears the trees in the way, and
  writes `world['forest_lake']` (centre, radii, water height, cabin, trail, safe shore) and
  `build/yorimichi/forest_lake/layout.json`.
- `world.lake` ([`build.py`](build.py), Blender) builds five meshes in `build/yorimichi/forest_lake/assets/`:
  `Lake_Cabin`, `Lake_Water`, `Lake_Trail`, `Lake_Shore` and `Lake_Plants`. [`details.py`](details.py) holds the
  cabin's joinery and the shoreline pieces.
- `unreal.lake` (`unreal/Scripts/import_forest_lake.py`) imports them into `/Game/Japan/Assets` with `M_Village`,
  and gives `Lake_Water` its own material (`forest_lake_material.py`).
- The `lake` scenario launches its own game under the render guard, captures twelve views (hero, overview, the four
  cabin sides, wood store, jetty, boat interior, rock islet, shore, trail, aerial) and probes seven jetty and step
  heights to 4 cm, into `build/yorimichi/forest_lake/LABEL/`. It fails if a probe fails.
- [`phone/forest-lake-smoke.mjs`](../../../phone/forest-lake-smoke.mjs) drives the streamed touch controls along the
  trail, onto the porch and the jetty, and into deep water to check the recovery.

Running `python -m forest_lake.layout` on its own (from `games/yorimichi/world/regions`) snapshots the pre-lake world
into `build/yorimichi/forest_lake/source/` and reapplies the lake to that snapshot. `integrate` refuses a world that
already has a lake, so never overwrite the snapshot with an integrated world.

## Reference

| Thing | Value |
| --- | --- |
| Lake | Centre (-90, 235), radii 34 × 23 m with a wavy shore, water at 75 m |
| Cabin | (-56, 215), floor 75.65 m, on a levelled pad |
| Safe shore | (-54, 223, 75.65), where deep water returns the player |
| Collision | The cabin, shore rocks and jetty collide; water and plants do not |

The cabin has a tiled roof with a dormer, shoji windows, a tiled covered porch on timber braces, a step, a bench, a
wood store, the jetty with a bucket and rod, and a moored rowboat. The water is opaque, with jade shallows and
animated ripples. When the player's feet sink 45 cm under the surface inside the shore, the game moves them to the
safe shore (`AWandererCharacter`).
