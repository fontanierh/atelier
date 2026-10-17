# Belmonte railway track

The track for the Belmonte steam line (Hidamari town station to Belmonte, 7.40 km at 4%), generated from the route study.

Hidamari uses the clock-tower station's existing platform, extended for the 131 m consist. The line runs east along
the old yard, replacing the decorative railcar, narrow-gauge track and engine shed. Its rail datum is fixed 0.67 m
below the station floor; the platform meets the existing surface 0.25 m above that floor. Boarding is on the right
at Hidamari and on the left at Belmonte. The east lane ends either side of the extended station yard. The passing
loop keeps its location with chainages 4810–5070 m. The lower town approach needs about 390 m more tunnel beyond
the spiral than the former H2 alignment (1.32 km, within a 1.4 km budget).

- Input: `build/yorimichi/belmonte-train/route/route.json` (`world/train/route.py`, explicit step
  `world.belmonte_train_route`).
- Layout code, no Blender: `world/train/track.py`.
- Meshes: `world/train/track_build.py` (Blender, explicit step `world.belmonte_track`).
- Control renders: `world/train/track_render.py` (explicit step `world.belmonte_track_review`).
- Output: `build/yorimichi/belmonte-track/`.

## Scope of the first version

Built:

- Standard-gauge track: two rails (1435 mm gauge), sleepers and a ballast bed with shoulders.
- The passing loop. Its second track sits 4 m to one side, with a turnout at each end built as a simple
  points-and-crossing mesh.
- The ends of the line. At each terminus the track runs to a buffer stop, and a stop board marks the stopping point.
  There are no station buildings. The 200 m station reserves stay in the data, but nothing is built on them.
- Tunnels: four portals in Belmonte stone, and a simple horseshoe lining for both tunnels, the spiral included.
- Dark tunnels with lamps (14 October 2026): the lining is soot-black stone (`MI_TK_TunnelLining`). A wall lamp
  (`SM_TK_TunnelLamp`: iron bracket, emissive globe `MI_TK_LampGlow`) stands every ~30 m, 3.0 m over the rail, on
  alternating walls. track.json's `tunnel_lighting` holds one warm point light per lamp (2700 K, 80 cd, 14 m reach,
  no shadows) grouped by tunnel, to be spawned with the tunnel's data layer. Each lining piece also carries an
  oriented `volume` box for a post-process volume that pins the auto-exposure (EV −1…1), so the tunnel reads dark and
  the lamps carry the light. The terrain keeps 8.6 m of ground over the rail (train/earthworks.py), so no sky leaks in.
- The viaduct: arched piers and a deck in Belmonte stone (`MI_B_ashlar`, with `MI_B_stone` for the copings).
- Earthwork marker posts every 50 m at the top of each cut and the toe of each fill. They are editor-only and data
  only.

Not built:

- No terrain carving. That is gated behind earthworks.ENABLED.
- The rail floats on placeholder ground where the far hills have not been rebuilt (route.json flags those samples).
- No Nanite anywhere.

## How the track is made

Everything follows the route.json samples. The rail top is at `rail_z`, and the curves come from the alignment.

| Part | How | LODs |
| --- | --- | --- |
| Ballast bed | Unique strip meshes bent to the line, one per 100 m chunk. Ballast texture with sleepers painted into the far mip. | 3 |
| Rails | Part of the same chunk mesh (one material slot each), swept along the line. Profile: 8 verts at LOD0, 4 at LOD1, a flat strip at LOD2. | 3 |
| Sleepers | One 0.25 x 2.6 m mesh, instanced every 0.63 m in an HISM per chunk. The cull distance fades them out at 120 m. | 2 |
| Loop and turnouts | Loop track chunks as above. Two unique turnout meshes. | 2 |
| Buffer stops and stop boards | One mesh each, instanced. | 2 |
| Tunnel lining | Horseshoe profile of 14 verts, inward faces, chunked every 100 m. Each tunnel goes on its own data layer, loaded only within 60 m of a portal or inside. | 2 |
| Portals | One stone portal mesh with an arch ring and wing walls, instanced 4 times and scaled to the cutting depth. | 2 |
| Viaduct | One mesh per span (pier, arch and spandrel), with the deck carrying the track chunk. Chunked into 3 pieces of 100 m. | 3 |

Collision:

- The ballast top, as simple boxes per chunk.
- The viaduct deck and parapets, as boxes.
- The tunnel lining, through its LOD2 used as complex collision.

Rails and sleepers get no collision.

## Budgets

The target is 1080p at ≥ 60 fps on a MacBook Air M5. The track must stay a small share of the frame: its numbers
are for the worst view, either a player on the viaduct or at the loop looking down the line.

| Budget | Limit |
| --- | --- |
| Draw calls from the track in view | ≤ 40 |
| Triangles in view (after LOD) | ≤ 60k |
| Ballast + rails chunk, LOD0 / LOD1 / LOD2 | ≤ 1,200 / 400 / 120 tris |
| Loop track rails (260 m, one mesh), LOD0 / LOD1 / LOD2 | ≤ 2,000 / 400 / 120 tris |
| LOD screen sizes | 0.5 / 0.15 / 0.04 (LOD2 holds beyond about 600 m) |
| Sleeper | 12 tris; ≤ 400 drawn instances in view (11.4k in total) |
| Tunnel lining chunk, LOD0 / LOD1 | ≤ 600 / 200 tris; nothing drawn from outside a tunnel |
| Portal | ≤ 2,000 / 600 tris |
| Viaduct (290 m in total), LOD0 / LOD1 / LOD2 | ≤ 25k / 6k / 1.5k tris |
| Turnout | ≤ 3,000 tris each |
| Buffer stop | ≤ 800 tris |
| Materials | reuse the Belmonte MIs (`MI_B_ashlar`, `MI_B_stone`, `MI_B_gravel`, `MI_B_iron`) plus one 1k ballast-and-sleeper texture set |
| Shaders | opaque only: no translucency, no world-position offset, no tessellation |
| Total unique mesh data on disk | ≤ 15 MB |

The build writes `manifest.json` with the triangle count of every mesh and LOD. A test checks the counts against
these budgets.

## Version 1 as built

Steps: `atelier build yorimichi world.belmonte_track` (and `world.belmonte_track_review` for the control renders in
`review/`).

| Part | Built | Worst triangles per LOD |
| --- | --- | --- |
| Main chunks | 72 | 950 / 220 / 40 |
| Loop rails | 1 | 1,820 / 312 / 44 |
| Tunnel linings | 28 | 520 / 120 |
| Portal | 1 mesh, 4 instances | 236 / 124 |
| Viaduct | 4 pieces | 1,560 in total at LOD0 |
| Sleepers | 11,725 instances | 10 each |

The GLBs take 7.6 MB in total and `track.json` 1 MB.

- Through the loop, the main chunks' ballast widens under the second track.
- Where the two tracks are closer than a sleeper's length, they share long timbers. These are sleeper instances
  scaled along their length.
- The turnout mesh carries the switch stand, lever, rodding, blades and a block frog.
- The rails of the two tracks simply cross at the frog.
- UVs are planar, in metres along each face's dominant axis.
- The ballast texture with painted sleepers is still to come; the GLBs use flat material colours named after the
  Belmonte material instances.
- Collision comes from the chunk's LOD2 (ballast), the lining's LOD1 and the viaduct's LOD2.

## Outputs (`build/yorimichi/belmonte-track/`)

- `meshes/SM_TK_Chunk_<nn>_LOD0/1/2.glb`: one per 100 m of line.
- `meshes/SM_TK_Loop_LOD*.glb`: the loop track's rails.
- Tunnel linings: `SM_TK_Tunnel_<tunnel>_<nn>_LOD*.glb`.
- Viaduct pieces: `SM_TK_Viaduct_<nn>_LOD*.glb`.
- One file each for the turnouts, portal, sleeper, buffer stop and stop board: `SM_TK_Turnout_*`, `SM_TK_Portal`,
  `SM_TK_Sleeper`, `SM_TK_BufferStop`, `SM_TK_StopBoard`.
- `track.json`, listing:
  - every mesh's world transform;
  - the HISM instance lists (sleepers per chunk, portals, buffer stops, boards, marker posts);
  - the tunnel data-layer extents and the portal trigger boxes.
- `manifest.json`: sizes, checksums, triangle counts per LOD and the budget checks.

The world frame is route.json's: map metres with z up, and the GLBs are in metres. The Unreal import (a later
`unreal.belmonte_track` step, modelled on `import_belmonte.py`) turns the instance lists into HISMs and the
tunnels into data layers.
