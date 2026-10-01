# Skateboarding

Yorimichi's skating backend is a single in-process C++ runtime that preserves the recovered
Skate 3 physics, animation, gameplay and camera behavior. Cairo receives the solved rider pose through a
retargeter; board parts follow the solved deck, trucks and wheels. Component differential proofs are recorded
in the [C++ migration notes](../../../platform/engine/Plugins/Activities/Skate/CXX_PORT.md).
Complete baseline/latest-main Session comparisons and native Unreal editor integration pass their recorded
checks. This establishes finite-corpus equivalence to the recovered implementation, not original-console parity.

## Build and run

The native animation samples, metadata, graphs, gesture patterns, camera, settings and skeleton data are
committed in [`unreal/Content/Data/SkateNative`](../unreal/Content/Data/SkateNative). The bundle has 3,334 payloads,
including 3,324 clips and 131,642 animation frames. Its manifest records each path, byte size and SHA-256;
[`assets/skate/runtime.json`](../assets/skate/runtime.json) pins that manifest and the required native formats.
The normal build verifies these files in place. It requires no extracted game, upstream tools checkout,
Rust toolchain or separate data installation.

```sh
uv run atelier build yorimichi unreal.compile
uv run atelier play yorimichi
# Native bundle integrity only:
python3 games/yorimichi/tools/verify_skate_native.py
# Against the running game:
uv run atelier qa yorimichi skate
```

`skate.runtime` is a light verification dependency of `unreal.compile` and is available as a named build step.
Its report goes to `build/yorimichi/skate-native/verification.json`; it produces no runtime executable or
converted assets. The Unreal module builds the C++ backend against the committed native data. No worker
build or fallback backend is part of the normal build. Bundle verification does not establish runtime equivalence.

The Mac renderer enables Unreal's GPU skin cache for Cairo's animated hair. This avoids the UE 5.8
morph-buffer startup assertion observed with inline skinning while keeping the hair animation enabled.

Original-format assets and pinned Rust source are restored from historical Git into ignored build output
only for independent differential proofs. They are absent from the shipping checkout. The one-time native
conversion/assembly tools live under the Skate plugin's `Tools/` directory and
write candidates under `build/`; they are not normal build dependencies. Runtime settings and graph loading
consume the project-native formats directly.

## Feel and controls

Yorimichi sets `PopHeightScale=1.15`, `AirSpinScale=1.6`, `PushPowerScale=1.45`,
`PushSpeedScale=1.15`, `VertAssist=1`, normal difficulty and medium trucks in `DefaultGame.ini`.
`VertAssist` keeps straight airs over quarters that end short of vertical inside the ramp; 0 retains the
original near-vertical band. The transfer and assist port follows main's `1536531` behavior and passes its
separate full Session/quarter-pipe and departure-helper comparisons.
These scale the recovered height, spin-response and push curves without replacing the solver or the animation
timing of each push. The loaded flat-ground ollie turns about 250° in the earlier reference checks (330–340° with the earlier
2.15), so a 360 needs a setup turn. Release the stick to line up the landing. From rest, the tuned push reaches
9.11 m/s after two seconds versus 6.99 m/s with stock values.

The Unreal integration supplies nearby collision and registered rails to the native runtime and presents
the solved camera and rider pose. Its complete frame/session behavior passes the recorded comparisons against
the pinned recovered implementation. The host view eases into the skating camera over about 0.6 s after mounting,
out while the right stick looks around, and back two seconds after the stick is released. These presentation transitions remain in the Unreal adapter.

Triangle / Y (or keyboard B) mounts/steps off; D-pad Down interacts on foot. Running onto the board preserves position, heading of travel and speed. W pushes, S brakes,
A/D steer or spin. Hold/release Space for an ollie, or hold the left mouse button and flick for tricks. C holds a
powerslide (A/D chooses its side); controllers use the left stick down-left/down-right. Q/E or triggers compress for pumping on the ground and grab in the air.
Hold Shift (or push the left stick forward) through takeoff to transfer over the coping; a grab does not
request a transfer.
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

The actual native Unreal build passes all 419 actions. Native CLI command, flat-ground and exported-park
checks pass. The live reports in `build/yorimichi/skateqa/` record 19/19 runtime checks and 7/7 park checks,
including a 5.10846 m bowl apex and return at park x=41.68899 m. All six real-time performance activities pass
at 59.7568–59.9965 fps, with maximum p95 17.202 ms and p99 17.724 ms, no frames over 33 ms or 50 ms,
and no repeated native simulation frames. After a far teleport into the island's Mega Park, collision refresh and a
six-second push also pass: 49.5369 m travelled, retained PhysicsGround and no new bail.

These are editor checks, not cooked/package validation or a claim about every possible ride.

Nearby pawn-blocking static meshes and registered rails supply native collision. The park importer retains CPU mesh data for collision export. Dynamic objects, individual
collision surface materials and buffer retention on other imported world meshes still need adapters. Editor builds
are the validated path. Cairo keeps its authored visual proportions; the solver uses the recovered rider's
physical proportions. Grabs and extreme poses can therefore still need visual contact adjustments.

Detailed provenance and limits are in the [native port notes](../../../platform/engine/Plugins/Activities/Skate/NATIVE_PORT.md).
