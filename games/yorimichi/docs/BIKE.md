# Cairo's bike

A kid-size teal mamachari, from Sunburst's approved concept: step-through frame, wicker basket, rear rack with the
skateboard strapped on, chain case, dynamo lamp, bell and a two-leg centre stand. Cairo gets it out with V (hold Y on a
gamepad), rides it on the island's ground with the walking physics, and parks it on its stand wherever he stops.

## Controls

| | Keyboard and mouse | Gamepad |
|---|---|---|
| Bike out and on / off and parked (stopped) | V | Hold Y (0.4 s; a tap is still the skateboard) |
| Pedal / brake / steer | W / S / A, D | Left stick |
| Pedal hard (on / off) | Shift | Sprint (press the left stick) |
| Hop | Space | Jump |
| Skid stop | C | Crouch |
| Bell | Left click | Attack |
| Wave | Q | |

He cruises at up to 22 km/h (600 cm/s). Pedalling hard is a toggle: one press and he pulls away harder, up to 43 km/h
(1200 cm/s), and keeps it while he pedals. It ends at a second press, a brake, a skid, a stop or when he stops pedalling
for more than 0.6 s. Above cruising speed the hub's higher gears keep his legs from spinning with the wheels.

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
  mount, wave and crash follows the H3 video references ([H3 workflow](../../../docs/H3_ANIMATION_REFERENCE_WORKFLOW.md)).
  Each clip goes out as an FBX on SK_Cairo's skeleton, and `export.json` keeps, per frame, the bike's channels
  (crank, stand, lift, pitch, lean, yaw, steer), the contact windows and the reach errors. Step `characters.cairo_bike`;
  `unreal.cairo_bike` imports the clips to `/Game/CairoBike` (outside DA_Cairo, so Cairo's own imports leave them alone) and `data.stage`
  copies `export.json` to `Content/Data/cairo/bike/`.
- `UBikeComponent` (`unreal/Source/Yorimichi/BikeComponent.*`) owns the bike's parts as components on the rider's mesh
  and the ride. Each tick it sets his speed and heading before the movement component moves him (floors, slopes and
  walls stay the walking physics'), runs the clip clock (the ride loop turns with the wheels, one crank turn per
  2.3 m, and stops when he freewheels) and poses the parts from the clip's channels plus the live steering and wheel
  roll. Rider and bike lean into turns together about the ground line, and pitch to the ground under the two wheels
(the walking capsule stays level on one point, so on a rise the front wheel used to sink in). The material's shaders
are finished when the component starts, so the first summon never draws the bike in the default material. A new clip blends in over 0.2 s, the bike's
  channels on the same curve as the rider's pose, and the ride loop starts at the crank's current angle.
- The animation instance plays the component's clip at the component's clock. `FBikeGripNode` (AtelierAnimation)
  keeps his hands on the bars as the player steers past the clip's own steering: each gripping hand moves with its
  grip and turns with the bars, and the arm is re-solved in its authored bend plane.

## Sounds

`assets/audio/bike/make.py` (step `audio.bike`) synthesises them with the skateboard's DSP helpers and two Sonniss
masters, and `unreal.sounds` imports them to `/Game/Audio/Bike` (`import_bike_audio.py`). `UBikeComponent` plays:

- **Loops on the bike:**
  - The tyres, by the ground under them. A complex trace through `USkateSettings::SurfaceAt` uses the skateboard's
    surface tables. Smooth ground (concrete, asphalt, metal) has its own loop, and so do wood planks, cobbles, gravel
    and dirt (sand too) and grass.
  - The freewheel ticking while he coasts, at the wheel's rate.
  - The chain while he pedals (one loop is one crank turn, played at the cadence).
  - Wind above about 13 km/h.
  - The back tyre skidding, with a gravel version on soft ground.
- **One-shots at the clips' key times:** the saddle creaking as he sits and hops, the stand flipping up and coming
  down, the bell's two thumb strikes, the hop's landing, and the crash into the wall followed by the bike falling on
  its side.
- **Other one-shots:** a landing after a drop (louder for a harder fall) and the basket rattling over cobbles and
  gravel at speed.

## Checking it

`uv run python games/yorimichi/tools/review_bike.py` (under the render guard, after the steps above and
`unreal.compile`) launches the island, finds open level ground near the towns, and rides every move on a fixed 60 fps
step (`scenarios/bike_live.py`). The crash is into a test wall (`live.L.test_wall`) put up 11 m ahead. On the same run with the wall gone, he rides a
test ramp (`live.L.test_ramp`, 12.5 degrees up to 1 m, then a drop), and both wheels must stay on the ground and the
ramp. It checks the
recorded states, speeds, turns, the sprint toggle, parking and crash, and writes `build/yorimichi/bike/review/` with
`checks.json`, stills, `bike.mp4` and `bike_sound.mp4`. The second is the same film with its soundtrack, mixed from
the sounds the game played and the bike's loops every frame (`skate_mix_showreel.mix`). The live bridge has
`live.bike()`, `live.bike_state()` and `live.press('jump' | 'crouch' | 'attack' | 'wave' | 'sprint')` for trying things by hand.
