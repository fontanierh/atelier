# Hidamari

The city at the eastern end of the coastal road: arrival terraces, a clock hall and fountain square, a covered
shopping arcade, two temples and a shrine on the hillside, a sunlit park with a pond and a cedar bridge, the station
district, and a fishing harbour with a fish market, lighthouse, breakwater and canal. Street lamps, benches, flower
beds, street trees and resident groups fill it. North of it rise the foothills and a distant volcano, with a trail
up from the park. Buildings are exteriors; there is no shopping, fishing or train travel.

## Build and check

```sh
uv run atelier build yorimichi world.hidamari unreal.world data.stage
uv run atelier build yorimichi world.city_tiles world.city_trees unreal.desktop   # desktop profile
```

- `world.hidamari` ([`build.py`](build.py), Blender) runs [`layout.py`](layout.py), which lays the city out from the
  seeded world (the eastern road end is read from `world.json`'s road, never copied by hand) and writes
  `build/yorimichi/hidamari/city.json`; then it builds the modular meshes, their collision and `manifest.json`. Streets
  and the terrain under them share one height profile, intersections included, and the far terrain is lowered
  smoothly round the city.
- `unreal.world` imports them with `unreal/Scripts/import_hidamari.py`, keeping the authored collision.
- `data.stage` stages `city.json`; the game merges it into the world when it builds the instanced meshes.
- `world.city_tiles` and `world.city_trees` build the desktop profile's 128 m city surface tiles and city tree LODs,
  and `unreal.desktop` imports them into `/Game/Experiments`.

For an art iteration on a few meshes, set `HIDAMARI_ASSETS` to comma-separated mesh names for both the Blender build
and the importer, and `HIDAMARI_TERRAIN=1` on the importer to replace the base terrain too. Run the importer on its own
(`kit/lab.py`, or `import_hidamari.py` through `-run=pythonscript`), never through `atelier build`: `unreal.world`
purges `/Game/Japan` first, so a filtered import there leaves only the named meshes. A layout or height
change can need `HD_Terrain`, `HD_Streets` and the ground-anchored public spaces rebuilt; rerun the collision audit
after it.

A capture shot spec with `"validate_hidamari": true` (`tools/capture.py SESSION --file SHOTS.json`) makes the game
audit the city's live collision before filming and write `hidamari-physics.json` (`HidamariReview.cpp`): ground
samples along every street and the north trail, character capsule sweeps along three lateral tracks, the park bridge
every half metre, building entrances, and no collision on the water. `tools/benchmark.py` measures frame time on the
`hidamari`, `arcade`, `plaza`, `harbor`, `harbor_pier` and `north` routes, for example:

```sh
python games/yorimichi/tools/benchmark.py CITY_PERF --view road_walk --route hidamari --road-index 258 --seconds 30 --hide-hud
```

Do not run a benchmark beside Blender or another Unreal session; it rejects contaminated runs.

## Files

| File | Holds |
| --- | --- |
| [`layout.py`](layout.py) | Roads, heights, building and resident placements, routes, water probes |
| [`location.json`](location.json) | District bounds; the world map centres its city zones on them |
| [`public_spaces.py`](public_spaces.py) | Positions shared by the layout and the mesh builders |
| [`arcade.py`](arcade.py), [`plaza.py`](plaza.py), [`harbor.py`](harbor.py) | The arcade, clock-square and harbour kits |
| [`living_streets.py`](living_streets.py), [`living_plaza.py`](living_plaza.py), [`working_harbor.py`](working_harbor.py) | Street details, plaza furniture, the fish market |
| [`pond_garden.py`](pond_garden.py), [`garden_bridge.py`](garden_bridge.py), [`civic_gardens.py`](civic_gardens.py), [`hero_approaches.py`](hero_approaches.py) | The park, its bridge, temple gardens, the station forecourt and the stone approaches |
| [`mountains.py`](mountains.py), [`forest_backdrop.py`](forest_backdrop.py) | The north foothills, volcano and trail; tree cover on the eastern hills |
| [`arrival.py`](arrival.py), [`park_grounds.py`](park_grounds.py), [`temple_precinct.py`](temple_precinct.py), [`station_yard.py`](station_yard.py) | The arrival road's rice terraces, the pond park's grounds, the temple precinct, the railway behind the station |
| [`lane_edges.py`](lane_edges.py), [`city_poles.py`](city_poles.py) | What lines the narrow lanes; utility poles and their wires |
| [`garden_shrubs.py`](garden_shrubs.py), [`house_gardens.py`](house_gardens.py) | The clipped garden shrubs; the planting of the back-lane houses' front plots |
| [`props.py`](props.py), [`street_props.py`](street_props.py) | The Tripo street props made into game meshes (`world.hidamari_props`); where they stand |
| [`surfaces.py`](surfaces.py) | The surface each face of a textured city mesh is made of (`HDS_<slug>` material slots) |
| [`kit/`](kit/GUIDE.md) | The building kit (see its guide) |
| [`textures/`](textures/prompts.json) | `paving.png` and `timber.png`, with their prompts |
| [`fonts/`](fonts/README.md) | The Japanese font for signs |

## Rules

- Falling into the harbour, the canal or the pond returns the player to their last grounded position in the city.
- Inland water is a separate mesh with no collision; banks, quay edges and bridges collide.
- Keep the main plaza route (y 150), the pond's crossing and its 5 m perimeter walk clear.
