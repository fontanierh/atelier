# Skateboarding

Yorimichi uses the recovered Skate 3 Rust Session for all skating physics and animation. Cairo receives the
solved rider pose through a retargeter; the board parts follow the solved deck, trucks and wheels. The earlier
C++ simulation, gesture recognizer, procedural tricks, clip player and skating IK node have been removed.
Walking and the transition onto/off the board remain in Unreal.

## Build and run

The required animation banks, graphs, gesture patterns, settings and skeleton data are committed in
[`unreal/Content/Data/SkateRuntime/assets`](../unreal/Content/Data/SkateRuntime/assets) as individual files,
with hashes in [`assets/skate/runtime.json`](../assets/skate/runtime.json). That directory is explicitly
excluded from Content's ignore rule. The normal build verifies those files in place and compiles the pinned Rust worker.
No extracted game, upstream tools checkout or separate data installation is needed.

```sh
# Requires rustup; the build selects Rust 1.97.1.
uv run atelier build yorimichi unreal.compile
uv run atelier play yorimichi
# Deterministic solver/animation checks, including flat-ground spins and slides:
python3 games/yorimichi/tools/check_skate_runtime.py
# Against the running game:
uv run atelier qa yorimichi skate
```

`skate.runtime` is a dependency of `unreal.compile` and is also available as a named build step. The generated
executable belongs to the current host platform and is staged in the ignored `unreal/Content/Data/SkateRuntime/bin`.
The game reads the tracked `assets` directory directly. The first mount decodes the banks; subsequent mounts reuse the session.
A failed runtime reports an error and returns to walking. There is no fallback skating engine.

The Mac renderer enables Unreal's GPU skin cache for Cairo's animated hair. This avoids the UE 5.8
morph-buffer startup assertion observed with inline skinning while keeping the hair animation enabled.

The offline importer remains as an optional provenance/reconversion tool. It writes a candidate conversion to
`build/yorimichi/skate-runtime/reconverted` for review, never over the tracked data. It is not a build requirement.
Its converted data was produced with upstream tools commit `60efdef86600d8d8d4feb4b7c608fa0efd0643d7`.

## Feel and controls

Yorimichi sets `PopHeightScale=1.15`, `AirSpinScale=1.6`, `PushPowerScale=1.45`,
`PushSpeedScale=1.15`, normal difficulty and medium trucks in `DefaultGame.ini`.
These scale the recovered height, spin-response and push curves without replacing the solver or the animation
timing of each push. The loaded flat-ground ollie turns about 250° in the native checks (330–340° with the earlier
2.15), so a 360 needs a setup turn. Release the stick to line up the landing. From rest, the tuned push reaches
9.11 m/s after two seconds versus 6.99 m/s with stock values.

The skating worker starts about two seconds into play, with the collision around the player, so the first mount
does not wait for the animation banks. While riding, the collision around the rider is gathered again once they
leave its inner area; the file is written and built off the game thread, and the worker switches to it between
steps. The view eases into the native skating camera over about 0.6 s after mounting, out of it when the right
stick looks around, and back two seconds after the stick is released.

Triangle / Y (or keyboard B) mounts/steps off; D-pad Down interacts on foot. Running onto the board preserves position, heading of travel and speed. W pushes, S brakes,
A/D steer or spin. Hold/release Space for an ollie, or hold the left mouse button and flick for tricks. C holds a
powerslide (A/D chooses its side); controllers use the left stick down-left/down-right. Q/E or triggers compress for pumping on the ground and grab in the air.
See the [plugin controls](../../../platform/engine/Plugins/Activities/Skate/README.md) for the full input contract.

`scenarios/skate_runtime.py` checks push/flip/landing, steering, manuals, rails, vert, bail/recovery, retargeted
bone lengths and head direction, actual keyboard input, mounting, spins, slides and both stances. Scripted input
is always released when a check finishes. The live state includes `retail=<physical state> tick=<number>`.

## Sunset Pier and pumping

The [park guide](../world/regions/skatepark/README.md) describes the new street plazas, manual pads, bars,
mini-ramp, bowl and roll-ins, with the Sunburst references and build/physics checks.

Hold L2/R2 (Q/E on keyboard) to compress, then release as you pass through the lower/middle transition to extend.
Compress high on the descent and extend through the bottom curve; repeat for the next wall. Release the triggers
before leaving the lip unless you want a grab. The native centre-of-mass and curvature controller supplies the
acceleration, so timing matters. The measured bowl comparison gains about 1.25 m of apex height and 0.51 m/s on return.

During bails, the retargeter samples Cairo's actual skinned surface and lifts the visual pose above supporting
geometry. This accounts for his larger head and clothing while preserving bone lengths and the native physical
rider's motion. The coasting pose uses the current parent transform even inside Unreal's scoped movement update,
which prevents the previous rider/board flicker.

## Integration boundaries

Nearby pawn-blocking static meshes and registered rails supply native collision. The park importer retains CPU mesh data for collision export. Dynamic objects, individual
collision surface materials and buffer retention on other imported world meshes still need adapters. Editor builds
are the validated path. Cairo keeps its authored visual proportions; the solver uses the recovered rider's
physical proportions. Grabs and extreme poses can therefore still need visual contact adjustments.

Detailed provenance and limits are in the [native port notes](../../../platform/engine/Plugins/Activities/Skate/NATIVE_PORT.md).
