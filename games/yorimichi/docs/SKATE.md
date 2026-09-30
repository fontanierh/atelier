# Skateboarding

Yorimichi uses the recovered Skate 3 Rust Session for all skating physics and animation. Cairo receives the
solved rider pose through a retargeter; the board parts follow the solved deck, trucks and wheels. The earlier
C++ simulation, gesture recognizer, procedural tricks, clip player and skating IK node have been removed.
Walking and the transition onto/off the board remain in Unreal.

## Build and run

The required animation banks, graphs, gesture patterns, settings and skeleton data are committed in
[`assets/skate/runtime.zip`](../assets/skate/runtime.zip), with file hashes in `runtime.json`. The normal build
compiles the pinned Rust worker and verifies/unpacks that bundle into the game's generated Content directory.
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
executable belongs to the current host platform and is staged with the bundled data in
`unreal/Content/Data/SkateRuntime`. The first mount decodes the banks; subsequent mounts reuse the session.
A failed runtime reports an error and returns to walking. There is no fallback skating engine.

The offline importer remains as an optional provenance/reconversion tool. It is not a build requirement.
Its converted data was produced with upstream tools commit `60efdef86600d8d8d4feb4b7c608fa0efd0643d7`.

## Feel and controls

Yorimichi sets `PopHeightScale=1.15`, `AirSpinScale=2.6`, normal difficulty and medium trucks in `DefaultGame.ini`.
These scale the recovered height and spin-response curves, including their acceleration, without replacing the
solver. Holding a spin through a loaded flat-ground ollie allows a 360. Release the stick to line up the landing.

Triangle / Y (or keyboard B) mounts/steps off; D-pad Down interacts on foot. Running onto the board preserves position, heading of travel and speed. W pushes, S brakes,
A/D steer or spin. Hold/release Space for an ollie, or hold the left mouse button and flick for tricks. C holds a
powerslide (A/D chooses its side); controllers use the left stick down-left/down-right. Q/E or triggers grab.
See the [plugin controls](../../../platform/engine/Plugins/Activities/Skate/README.md) for the full input contract.

`scenarios/skate_runtime.py` checks push/flip/landing, steering, manuals, rails, vert, bail/recovery, retargeted
bone lengths and head direction, actual keyboard input, mounting, spins, slides and both stances. Scripted input
is always released when a check finishes. The live state includes `retail=<physical state> tick=<number>`.

## Integration boundaries

Nearby pawn-blocking static meshes and registered rails supply native collision. Dynamic objects, individual
collision surface materials and packaged static-mesh CPU buffer retention still need adapters. Editor builds
are the validated path. Cairo keeps its authored visual proportions; the solver uses the recovered rider's
physical proportions. Grabs and extreme poses can therefore still need visual contact adjustments.

Detailed provenance and limits are in the [native port notes](../../../platform/engine/Plugins/Activities/Skate/NATIVE_PORT.md).
