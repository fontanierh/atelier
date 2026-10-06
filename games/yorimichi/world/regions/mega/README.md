# Forest mini-mega

A full-scale plywood mega ramp in a sunlit clearing in the woods, at the end of a trail that continues beyond Momiji
Hamlet. The riding line runs from the roll-in tower through the takeoff, over the open gap and down the landing into
a circular vert quarter pipe; a side ladder reaches the tower, a rollout returns to the clearing, and a walking route
surrounds the ramp. The ramp is scenery with collision: `AMegaRamp` places `Mega_Ramp` from `world.json` `mega`, and
there is no scripted ride on it. The seams between the sheets and the coping are a separate `Mega_Trim` with no
collision, so the riding surface is smooth plywood and the deck behind the vert starts on the wall's top edge.

The dimensions follow [Elliot Sloan's description of Sloanyard](https://www.monsterenergy.com/en-us/skateboard/elliot-sloan-talks-sloanyard/).

## Build

```sh
uv run atelier build yorimichi world.mega unreal.mega
```

- `world.layout` calls `mega.layout.integrate` from `gen_world.py`, after the village: it lays the trail from the
  hamlet's last lane, levels the oval clearing, clears the trees and plants in the way, and writes `world['mega']`
  (origin, trail width, gap, ladder and trail).
- `world.mega` ([`build.py`](build.py), Blender) builds `Mega_Ramp` and `Mega_Trim` from [`ramp.py`](ramp.py), and
  `Mega_Trail`, in `build/yorimichi/mega/` with the village kit's single vertex-colour material.
- `unreal.mega` (`unreal/Scripts/import_mega.py`) imports them into `/Game/Japan/Assets` with `M_Village`. The terrain
  under them belongs to `unreal.world` and `unreal.southwest`.

`python games/yorimichi/tools/benchmark.py NAME --view road_walk --route mega --seconds 55` walks the trail with
frame-time measurements.

## Reference

[`ramp.py`](ramp.py) is the one metre-space profile both the mesh and the collision come from; [`layout.py`](layout.py)
holds its place, the clearing and the trail. Only `world.mega` and `world.map` read `ramp.py`, so a change to the
ramp's shape rebuilds the ramp and the map (`world.mega`, `unreal.mega`, `world.map`) without regenerating the terrain
or reimporting `/Game/Japan`. A change to `layout.py` rebuilds the world.

| Dimension | Value |
| --- | --- |
| Roll-in platform | 10.7 m |
| Open gap | 10.4 m (`GAP`) |
| Landing | a straight 35° from the knuckle, then a 4 m transition to the flat |
| Vert quarter pipe | 6.1 m, an exact circular transition ending in true vertical |
| Riding width | 8 m (`ramp.WIDTH`) |
| Origin | (65, 242), deck base at 66.8 m (`ORIGIN`) |

The world map draws the two riding sections, the gap and the rollout from `ramp.py`, and the trail from `world['mega']`
([WORLD_MAP.md](../../../docs/WORLD_MAP.md)).
