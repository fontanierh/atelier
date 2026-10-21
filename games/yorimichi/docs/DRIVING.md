# Driving

The car is an open go-kart (`assets/vehicles/kart`) driven by Atelier's four-wheel
simulation (`platform/engine/Plugins/Activities/Driving`). The chassis is simulated in metres at a fixed 60 Hz;
the host moves the character actor with it and reads the world with one ray per wheel.

## Controls

- `L`, or `live.car()` from the live bridge, summons the kart beside the rider and mounts. Press it again,
  stopped, to step out and park it.
- `W` / `S` (the stick's forward axis) accelerate and brake; holding `S` from a stop selects reverse. `A` / `D`
  steer. `Space` is the handbrake.
- The camera settles behind the kart, pulls back a little and widens with speed.
- The paraglider is stowed while driving. Summoning resets the move set, and every equipment update reconciles
  the glider component's visibility, so a late or externally propagated visibility change cannot leave the
  canopy open behind the kart.

## Ride

The kart runs 3.6 in (9.1 cm) of suspension travel on 90/105 lb/in springs with light damping (12/14 lb/in/s bump,
17/19 rebound) and a 0.5 progression, so a four-tyre contact is kept over broken asphalt instead of bouncing
off the bump stops. On the 20 s test road in
`platform/engine/Plugins/Activities/Driving/Tests/Simulation/kart_ride_test.cpp` (8 m/s over 2 cm and 0.8 cm
ripples), vertical acceleration RMS fell from 5.14 to 3.93 m/s², the peak from 13.6 to 10.1 m/s², and wheel
contact loss from 16% of steps to none.

In the running game, `live.car_ride()` prints the chassis height, vertical speed, pitch/roll and each wheel's
compression, height and contact. `games/yorimichi/scenarios/kart_uneven.py` drives a fixed route at a fixed
throttle and writes the same acceleration and contact numbers, for a before/after comparison on real terrain.

## Equipment transitions

`games/yorimichi/scenarios/kart_equipment.py` opens the glider, lands, summons the kart, steps out and opens
the glider again, checking the canopy's visibility at each step.

## The driver

The character stays visible, seated on the kart's pan by the sailing stance node's pelvis target, with both
feet on the pedals. The final GripPoseNode reads the authored hand and finger frames relative to the live
steering wheel; the seated stance leaves those hands to that node. Arm IK follows the pinned wrists, and
source clips cannot move the saved finger contacts.

## Scale and placement

`assets/vehicles/kart/cockpit.json` owns the metre frame for the generated meshes, preview and runtime:
seat, pelvis, pedal and knee targets, steering hub, column base and wheel positions. The wheel face is
perpendicular to the shaft. The import stages the matching layout with its four meshes and matte material;
`atelier build yorimichi unreal.kart` rebuilds these without rebuilding the island.

Before mounting, the host measures the rider's reference thigh and shin and scales the entire kart by their
combined length divided by the layout's reference length. Seat, pedals, grip positions, wheelbase, tires and
collision dimensions share that scale. It is fixed for the mounted simulation, rather than changing inside
animation evaluation. An unsupported fit is refused rather than silently clamped to another character's size.

Its origin is the ground under the middle, +X the nose. The body is offset below the simulated centre of gravity
by the half height plus the ride height; its wheels follow their individual contact positions, spin and Ackermann
steer angles. The steering wheel and both grip targets rotate together. The rider's capsule is off while driving; a box sweep of the
chassis stops the kart at walls and fences, and every painted surface it crosses is read as tarmac unless a
finer surface mapping is added.

## Current limits

The kart is single player: the vehicle prediction layer does not carry it yet, so `L` does nothing in a shared
game. The seated pose comes from IK rather than an authored clip, so the driver's spine does not lean with the
steering; a passing visual review should decide whether a kart-specific pose or clip is worth authoring.


## Grip studio

The character-specific grip editor lives in `tools/kart_grip_editor`. Export its prepared
skins and the current cockpit through a guarded Blender run of `export_models.py` after
`world.kart`; outputs belong in `build/yorimichi/kart-grip-editor`. Start `server.py`
with the repository Python environment. It listens only on loopback port 8923. To share
it within a tailnet, use Tailscale Serve on a dedicated `/kart-grips` path targeting that
loopback port; the live game bridge remains loopback-only and is never exposed.

Select a character and author the left palm and all three joints of each finger. The
right hand mirrors the left through that character's bind frames, preserving its own
finger lengths and imported rolls. Positive **Tilt up** raises the fingers around the
wrist. **Shoulder down** directly rotates the upper arm and **Elbow bend** folds the
forearm; these FK edits carry the hand, so match the wheel placement afterward.
Their resulting wrist transform and elbow guide reconstruct the same arm bend on load. **Lean forward** brings the shoulders toward the wheel so the elbows have room
to bend; negative arm height lowers the elbow guides. **Wheel height** telescopes the
column along its shaft; **Wheel angle** rotates the shaft and wheel together. Both
carry the pinned hands. These fitting settings are saved independently per character. Check both hand/palm cameras and steering extremes.

Save writes `assets/characters/<character>/kart-grip.json` atomically. Each hand and finger
has a complete transform relative to the unsteered, scaled wheel; changing steering
never edits those transforms. The save also includes the source bind skeleton, model
checksum, mirrored elbow guides, shoulder lean, wheel height/angle and cockpit revision.
Older saves are recoverable under the ignored editor build directory. A stale browser
cannot overwrite a newer save. Save before refreshing after an editor update.

`unreal.kart` stages all four authored profiles with the cockpit and meshes, refusing
missing or stale profiles. The game adapts the recorded bind axes to its imported
skeleton, then the final grip animation node applies the animated wheel transform to
every recorded joint. Source clips cannot reopen or move the fingers. IK reaches the
pinned wrist using the saved elbow guide; reach errors remain diagnostic rather than
silently moving the grip. Sailing retains its original stance and finger requirements.

The wider visual wheel track and body bounds also change the simulation's track,
yaw inertia and collision envelope. This is an intentional match to the new geometry;
stationary fit alone does not validate its driving feel.


## Exterior finish and steering preview

The current four-view Sunburst reference is `assets/vehicles/kart/reference.png`; its
provenance records GPT Image 2.5 Sunburst at high quality and the prompt. The finish
uses ivory bands, warm terracotta variation and split normals. It changes no render
surface or collision vertex. The cockpit and four approved grip JSONs remain fixed.

The studio's steering slider and Play also yaw the front tyres at their own hubs.
The inside tyre turns further, using the native simulation's existing Ackermann
approximation and its 2.5 steering-wheel/left-front ratio. Rear tyres stay straight.
The game already displays each WheelState's steer angle and spin; integration still
needs a native driving check at the accepted revision.

After changing only the kart, run `export_context.py` through the normal Blender guard
to refresh `build/yorimichi/kart-grip-editor/kart.glb`. This preserves character GLBs,
metadata and authored poses. Its optional `--baseline-build` compares all generated
surface/collider coordinates and face topology against an earlier generator.

`assets/characters/<character>/kart-grip-model.json` is the registered identity of its inspected prepared
skin: model SHA, bind SHA, source/preparation SHA and replay shoulder frame. Production
preflight checks that independent receipt and the current character inputs before
accepting a pose; it does not trust the pose's own checksum as its expected value.
After changing a character source, re-export the inspected models, review/save its
poses, then run `tools/kart_grip_editor/source_identity.py` to register the new receipt.
Normal imports fingerprint all those source inputs. Runtime separately compares the
prepared and imported hand-relative bind positions within 3 mm and logs a rejection
if they differ. Saves and preflight refuse neutral wrist reach misses above 1 cm;
runtime logs larger animated misses and preserves incoming bone scales.

Authored kart grips and their prepared-model identities belong beside each character definition.
The kart owns only the shared cockpit and replay mechanism. Its importer builds the runtime
profile table from those character-owned files; there is no second authored copy under vehicles.
