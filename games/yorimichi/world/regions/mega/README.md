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

## State

The ramp is scenery and collision now: `AMegaRamp` places `Mega_Ramp` from `world.json` and the trail and clearing are
walkable. Its scripted ride (ladder, drop-in, gap, vert 180 and rollout on the old cruiser skateboard,
`MegaMovement.cpp`, `-megaqa`) stayed in the prototype archive with that board; a ride on the new board would be built
on the platform's Skate plugin.

## Implementation

`layout.py` is the shared metre-space profile for the generated plywood geometry. The terrain edit and scatter
exclusions are local to the new trail and clearing. Meshes use one existing opaque vertex-colour material.

## Rebuild and verification

`atelier build yorimichi world.mega unreal.mega` regenerates and imports the ramp and trail.

- `python games/yorimichi/tools/benchmark.py NAME --view road_walk --route mega --seconds 55`: walking the connecting
  trail with real-time frame measurements.
