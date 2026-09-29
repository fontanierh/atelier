# Forest mini-mega

A woodland trail continues beyond Momiji Hamlet to a separate sunlit clearing.
The ramp uses Sloanyard-scale dimensions: **10.7 m roll-in platform, 10.4 m open
gap, 6.1 m vert quarter pipe, 8 m riding width**. The actual riding line runs
from the tower through the takeoff and descending landing to a circular vert
transition. A side ladder reaches the tower; a walking route surrounds the ramp.

The dimensions are based on [Elliot Sloan's description of Sloanyard](https://www.monsterenergy.com/en-us/skateboard/elliot-sloan-talks-sloanyard/).
The built-in imagegen tool designed `references/forest-mega.png` using three
actual game screenshots, then `references/motion-sheet.png` using the character
and environment references. `references/grab-sheet.png` develops the rear-hand
grab and 180 re-entry using the actual yellow rider as reference. Exact prompts
are beside the images. The generated
sheet's horizontal width annotation is misplaced: width is across the ramp,
while the actual model and physics share the explicit dimensions in `layout.py`.

## Controls

Stop beside the ladder and press **E** (controller **Y / Triangle**) to climb.
At the top, press forward to drop in. **A/D** steer across the riding lane;
**S** brakes. Gravity builds speed down the roll-in. Crossing the takeoff lip
launches the board without requiring an ollie. The quarter pipe launches a
grabbed 180 air and returns nose-first to the same transition. On the return,
a curved plywood rollout guides the rider off the flat and onto the clearing.
Both feet remain on the board through the grab; the rear hand releases before
landing. Wanderer remains an NPC with his hat and ordinary animations. If he
ever participates in a future skating sequence, he must remove and stow the
hat before climbing the ramp; that sequence is not enabled now. **B** queues a stop and step-off on a shallow part of the ramp.

The normal road controls, successive pushes, ollies, regular/goofy preference,
and free camera remain available. The yellow kid is the only player character; his asymmetric accessories stay
on their original side in regular and goofy stance.

## Implementation

`layout.py` is the shared metre-space profile for generated plywood geometry
and native ramp contact. The terrain edit and scatter exclusions are local to
the new trail and clearing. Meshes use one existing opaque vertex-colour
material. `MegaMovement.cpp` integrates gravity along the surface at 120 Hz,
allows lateral steering, and switches to ballistic movement at the lip.
Airborne velocity is projected onto the landing tangent; normal sweeps handle terrain and
obstacles. Normal street skating retains the existing movement solver.

Build world, ramp, terrain and animation assets, compile, then run targeted
imports. `qa.py` drives the actual input bindings through the complete line;
`preview.py` captures actual in-game establishing views. Fixed-step captures
are functional evidence, not performance measurements.


## Rebuild and verification

Run `JAPAN_PYTHON=/path/to/python-with-numpy japan/run.sh mega` with Unreal closed.
The script rebuilds the world, ramp, terrain, the yellow kid’s articulated finger rig and skating clips, builds
the native module, and imports the generated assets. Terrain and skateboard
imports use separate processes and explicitly select their correct FBX pipeline.
Generated binaries, FBX files and `.blend` files are disposable outputs under
`japan/out`; source geometry, animation code and concept references are tracked.
`grip_review.py` renders the baked palm/finger/board contact and checks the
thumb above and fingers curled below the deck edge in both stances, rejecting
any finger triangles intersecting the plywood. Native QA also
checks the imported hand’s position relative to the moving board.

- `python-with-numpy japan/mega/verify.py`: shared dimensions, trail grades,
  clearing height and tree clearance.
- `python3 japan/mega/qa.py NAME --character cape_boy --goofy 0`: actual input
  route through ladder, gap, vert 180 and rollout. Repeat for both stances. Includes imported scale and sole-contact checks.
- `python3 japan/mega/preview.py NAME --shots overview,arrival,aerial`: in-game
  establishing views.
- `python3 japan/benchmark.py NAME --view village_skate --route mega --seconds 55`:
  ordinary skating along the connecting trail with real-time frame measurements.
