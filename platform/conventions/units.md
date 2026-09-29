# Units and axes

| Where | Units | Axes |
|---|---|---|
| Sources (Blender, layouts, region files) | metres | Z up; characters face -Y; +X is the character's left |
| Unreal | centimetres | Z up, X forward, Y flipped relative to the sources |
| Character clips | 60 frames per second (the fox hunter still exports at 30) | |
| Region-local coordinates | metres from the region's `origin_m` | same as sources |

One conversion, `atelier.conventions.to_unreal`:

```
unreal = (x * 100, -y * 100, z * 100)      yaw_unreal = -yaw_source
```

The game's C++ has the same function (`ToUE`). Nothing else should flip axes on its own.
