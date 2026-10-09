# Hidamari Hippodrome

A public oval and grandstand on the terraced slope north of Hidamari, reached by the lane from the eastern street
(x = 560). The map's hippodrome stop arrives beside the grandstand. You can walk, skate and explore the grounds.

The venue keeps its flat platform, skirt, turf, dirt oval, rails, access lane, grandstand, judges' tower, finish post
and display board. The oval is centred at (600, 525) metres, with 120 m straights, 50 m turn radii and a 14 m width.
Its perimeter is 554.2 m. Clearance polygons keep island vegetation outside the platform and lane.

`world/regions/hippodrome/layout.py` defines the plan; `build.py` writes the meshes, textures and venue data to
`build/yorimichi/hippodrome/region/`. `unreal/Scripts/import_hippodrome.py` imports the static meshes with walkable
collision and writes `Content/Data/hippodrome/hippodrome.json`. `AHippodrome` places the venue's meshes at runtime.

```sh
uv run atelier build yorimichi world.hippodrome unreal.hippodrome
uv run atelier live py "live.hippodrome()"
```
