# Cairo's bike

A kid-size teal mamachari, from Sunburst's approved concept: step-through frame, wicker basket, rear rack with the
skateboard strapped on, chain case, dynamo lamp, bell and a two-leg centre stand. Cairo gets it out with V (hold Y on a
gamepad), rides it on the island's ground with the walking physics, and parks it on its stand wherever he stops.

## Controls

| | Keyboard and mouse | Gamepad |
|---|---|---|
| Bike out and on / off and parked (stopped) | V | Hold Y (0.4 s; a tap is still the skateboard) |
| Pedal / brake / steer | W / S / A, D | Left stick |
| Pedal hard | Shift | Sprint |
| Hop | Space | Jump |
| Skid stop | C | Crouch |
| Bell | Left click | Attack |
| Wave | Q | |

Getting off needs him stopped (the HUD says "Slow down to get off"). Getting the bike out needs level ground beside
him: it appears at his left, facing his way or the nearest clear way (30 and 60 degrees either side, or behind). V
next to the parked bike gets back on it rather than bringing out another. Riding hard into a wall throws him over the
bars (the bike rebounds off the wall to give him room): the bike falls on its side, he picks himself up beside it, and
the next V brings it out fresh.

## Pieces

- `assets/vehicles/bike/build.py` (Blender) builds the bike from the concept's side elevation, every moving part a mesh
  with its origin at its pivot: `BK_Frame`, `BK_Steer` (Z up the steering axis), the wheels, `BK_Crank`, `BK_Pedal`
  (one per side), `BK_Kickstand` and `BK_RackBoard`. `manifest.json` records the pivots, the steering axis tilt, wheel
  and crank sizes and the rider's contacts (saddle, grips, pedals). `review.py` renders it against the concept views.
  Steps `world.bike` and `unreal.bike`.
- `assets/vehicles/bike/rider.py` (Blender) authors every rider move on that bike: BikeRide (the pedalling loop),
  BikeMount, BikeDismount, BikeKickstand, BikeHop, BikeSkid, BikeFootDown (the stopped loop), BikeBell, BikeWave and
  BikeCrash. Hands and feet are solved onto the grips, pedals, stand and ground in their contact windows; timing for the
  mount, wave and crash follows the H3 video references (docs/H3_ANIMATION_REFERENCE_WORKFLOW.md). Each clip goes out
  as an FBX on SK_Cairo's skeleton, and `export.json` keeps, per frame, the bike's channels (crank, stand, lift, pitch,
  lean, yaw, steer), the contact windows and the reach errors. Step `characters.cairo_bike`; `unreal.cairo_bike`
  imports the clips to `/Game/CairoBike` (outside DA_Cairo, so Cairo's own imports leave them alone) and `data.stage`
  copies `export.json` to `Content/Data/cairo/bike/`.
- `UBikeComponent` (`unreal/Source/Yorimichi/BikeComponent.*`) owns the bike's parts as components on the rider's mesh
  and the ride. Each tick it sets his speed and heading before the movement component moves him (floors, slopes and
  walls stay the walking physics'), runs the clip clock (the ride loop turns with the wheels, one crank turn per
  2.3 m, and stops when he freewheels) and poses the parts from the clip's channels plus the live steering and wheel
  roll. Rider and bike lean into turns together about the ground line. A new clip blends in over 0.2 s, the bike's
  channels on the same curve as the rider's pose, and the ride loop starts at the crank's current angle.
- The animation instance plays the component's clip at the component's clock. `FBikeGripNode` (AtelierAnimation)
  keeps his hands on the bars as the player steers past the clip's own steering: each gripping hand moves with its
  grip and turns with the bars, and the arm is re-solved in its authored bend plane.

## Checking it

`uv run python games/yorimichi/tools/review_bike.py` (under the render guard, after the steps above and
`unreal.compile`) launches the island, finds open level ground near the towns, and rides every move on a fixed 60 fps
step (`scenarios/bike_live.py`). The crash is into a test wall (`live.L.test_wall`) put up 11 m ahead. It checks the
recorded states, speeds, turns, parking and crash, and writes `build/yorimichi/bike/review/` with `checks.json`,
stills and `bike.mp4`. The live bridge has `live.bike()`, `live.bike_state()` and `live.press('jump' | 'crouch' |
'attack' | 'wave')` for trying things by hand.
