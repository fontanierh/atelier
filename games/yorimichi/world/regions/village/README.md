# Momiji Hamlet

A small autumn settlement in the forest off the coastal road: a two-storey tea house, two cottages, a pottery workshop
and a storehouse, round a covered well under a maple. A 2.6 m dirt trail leaves the asphalt at a wooden waymark (an
arrow-shaped board marked on both faces) and winds through 70 m of forest before the houses show; a short branch loops
round the maple and the well. The buildings are modelled exteriors with closed doors. Three residents give the hamlet
life: one works at the workshop, one stands by the tea house and one walks beside a cottage.

This folder's `build.py` is also the mesh kit the other regions build with (`Mesh`, `export`, `roof`, `window`,
`door`, `lantern`, `PALETTE`), and `M_Village`, the opaque vertex-colour material it feeds, is shared by every
kit-built place.

## Build and check

```sh
uv run atelier build yorimichi world.village unreal.world data.stage
python games/yorimichi/tools/benchmark.py village-walk --view road_walk --route village --seconds 25 --hide-hud
```

- `world.layout` calls `village.layout.integrate` first among the regions in `gen_world.py`. It moves the authored
  hamlet coordinates 70 m into the forest and 9 m up (`village_point`), grades only the terrace and lanes inside
  `EDIT_BOUNDS`, clears the foliage in the way (reserving bush canopy and grass blade width, not just instance
  centres), reseats nearby trees, and leaves the road, the spawn and every placement outside the earthwork
  byte-for-byte as the seeded world made them. It writes `world['village']`: the lanes (`paths`, `surface_paths`),
  `buildings`, `residents`, `planting_beds`, camera `shots`, and the removed instances and adjusted heights.
- `world.village` ([`build.py`](build.py), Blender) writes twelve meshes to `build/yorimichi/village/assets/`: the five
  buildings, `Village_Garden` (the roofed well and its nook), `Village_Sign`, `Village_Ground` (the lane), `Village_Edges`,
  and from [`decorations.py`](decorations.py) `Village_Details` (household furniture), `Village_Planting` and
  `Village_Threshold` (the forest gate). It also saves `Village.blend` with everything in place, `manifest.json` and
  `build-identity.json`. Collision is simple UCX volumes; furniture never blocks the lane.
- `unreal.world` runs `unreal/Scripts/import_village.py` (through `setup_project.py`): it creates `M_Village` and
  imports the village and the terrain, and refuses a build whose sources, `world.json` or heightmap hashes do not
  match `build-identity.json`.

The benchmark walks the trail with uncapped frame-time measurements (`--route village_loop` for the loop). A capture
shot with `"validate_village": true` (`tools/capture.py SESSION --file SHOTS.json`) makes the game audit the hamlet in
the live collision scene before filming: ground traces and capsule sweeps across the lane width, and a collision check
against every building front (`ValidateVillage` in `JapanTrailer.cpp`).

## Reference

| Building | Centre (authored) | Yaw | Size |
| --- | --- | --- | --- |
| `Village_TeaHouse` | (77.5, 7.5) | 90 | 8.0 × 6.4 m |
| `Village_CottageA` | (80.0, 29.0) | 45 | 6.5 × 5.0 m |
| `Village_CottageB` | (104.5, 35.0) | -20 | 6.0 × 5.3 m |
| `Village_Workshop` | (118.0, -2.0) | -120 | 6.2 × 4.8 m |
| `Village_Storehouse` | (122.0, 19.5) | -90 | 3.8 × 4.5 m |

Authored centres are before `village_point`'s offset (+70 m north, +9 m up); a building's local front is -y.

The residents (`AVillageLife`) reuse the villager rigs and clips with their own clothing colours. They have no
conversations, AI, navigation or blocking bodies, and stay beside the houses. Pose evaluation stops off screen, and
they tick once a second when the camera is more than 160 m away.
