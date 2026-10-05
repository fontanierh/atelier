# Skate runtime reference

The skating runtime is the C++ under `Source/AtelierSkate/Private/Native/`, namespace `atelier::skate`. It is a port of
the recovered Skate 3 implementation from
[2010-rust-rewrite-mashup/skate](https://github.com/chasmlol/2010-rust-rewrite-mashup/tree/7842b9e70e9aac22ed176b655dd63302618ee023/skate),
which originated in [SK8-ENGINE/skate-3-rust-engine](https://github.com/SK8-ENGINE/skate-3-rust-engine). It reads
only the project's native data formats. The parity checks in `Tests/` compare it, bit for bit, with that Rust
implementation as pinned in this repository's history at commit `46513a6` (and `1536531` for the transfer and vert
assistance), built with Rust 1.97.1. The plugin [README](README.md) covers the Unreal side.

## Session

`GameplaySession` (`GameplaySession.h`) is the only entry point the Unreal adapter uses:

| Call | Effect |
| --- | --- |
| `Create(resources, world, anchor, heading, out, error)` | Builds a session from loaded data and a collision snapshot |
| `Configure(difficulty, goofy, trucks)` | Controller preset, stance and truck tightness |
| `Tune(pop, spin, speed, power, vert_assist)` | Scales on the stock values; out-of-range values are an error |
| `Activate(position, heading)` | Puts the rider on the board at a spot |
| `Step(pad, frame_interval)` | Adds host time and runs whole ticks |
| `SuspendInput()` | Stops reading the pad between rides |
| `InstallCollision(world)` | Swaps in a prepared collision snapshot between steps |
| `Pose()`, `ReferencePose()` | Root, bones, bone names, camera frame, velocity, tick and state name |
| `Launch(velocity)` | Sets the velocity of every board and rider body (QA) |

A tick lasts 16.6666 ms (60 Hz); camera effects can request another rate for a number of ticks. Within a tick the
runtime applies camera rate requests, runs climbing, queries the board and skeleton against the world, advances the
animation graphs, samples input, selects the ground profile, selects and updates the player state, updates board
possession, solves the bodies and publishes pose, score and camera. The pad is an Xbox-style packet; bit `0x0800`
(`GameplayTransferButton`) is the host's transfer button and is removed before the pad is sampled.

The module compiles without unity builds and with precise floating-point semantics; the adapter runs native work in
the default floating-point environment and restores the caller's afterwards. Native space is metres, left/up/forward;
the adapter converts with `FVector(V.Z, -V.X, V.Y) * 100` and reverses triangle winding.

## Systems

| Group | Units | What they do |
| --- | --- | --- |
| Session and frame | `GameplaySession`, `GameplayRuntime`, `GameplayFrameRuntime`, `GameplayResources`, `SimulationClock`, `SessionMarkerRuntime`, `ControllerInputRuntime` | Own the runtime, load data, schedule ticks, keep controller history and session markers |
| Data readers | `DataReader`, `Settings`, `StockSettingsReader`, `NameId`, `PhysicsSkeleton`, `AnimationSamples`, `AnimationMetadata`, `Graph`, `CompiledGraph`, `Gestures`, `ClimbingClips` | Parse the native formats into settings, skeletons, clips, metadata, graphs and gesture sets |
| Maths and geometry | `NativeMath`, `Geometry*`, `PrimitiveGeometry`, `WorldGeometry`, `GameplayWorld` | Vectors and matrices, primitive pairs, sweeps, prisms, the world BVH and snapshot preparation |
| Contacts | `WorldContactProducer`, `WorldPrimitiveContact`, `ContactGeneration`, `ContactRetention`, `ContactBuild`, `AssemblyContacts`, `CollisionBody` | Generate, retain and build contacts between bodies and the world |
| Bodies and solver | `RigidBody`, `BodyMass`, `AggregateMass`, `ConstraintSolver`, `ConstraintFrames`, `JointBuild`, `JointRecords`, `Drive*`, `ForceQueue` | Rigid bodies, joints, drives and the constraint solver |
| Board | `Board*`, `DeckGeometry`, `DeckAngularCorrections`, `TruckDriveFrames`, `HookDrive` | The seven-body deck, truck and wheel assembly, its colliders, probes and possession by the rider |
| Rider skeleton | `Skeleton*`, `Biped*`, `FootIk*`, `Footplant*`, `PhysicalSimulationRuntime`, `PhysicalPhase`, `CentreOfMassFilter` | The physical rider: bodies, drives, targets, feet, foot IK and the biped ground and air controllers |
| Input and graphs | `Input`, `InputIntentions`, `Intents`, `PlayerControls`, `GestureInputPublication`, `GraphController`, `GraphConditions`, `Graph*Operations`, `MotionGraph*`, `ActionGraphFrame` | Flick-It gesture recognition, intents and the action and motion graphs |
| Player state | `PlayerState*`, `PlayerInput*`, `PlayerPreInput`, `PlayerPostInput`, `PlayerPostPhysicsPhase`, `PlayerSceneProbe`, `FilteredState` | The riding state machine and its per-tick phases |
| Ground riding | `Ground*`, `Push`, `Braking`, `Steering`, `SpeedModel`, `SpeedWobble`, `Pumping`, `Manual`, `SlideFriction`, `Straighten`, `Heading`, `AntiFlip`, `TrainerTuning` | Pushing, braking, steering, pumping, manuals, powerslides and the tuning scales |
| Air | `Air*`, `KnownAir*`, `BodySpin`, `BodyFlip`, `AirReckoning`, `ReckoningFrames` | Take-off trajectory selection, spins, flips and air control |
| Grinds and slides | `Grind*`, `PlayerGrind*`, `Slide*` | Rail and ledge selection, balance and grind or slide forces |
| Landing | `LandingDeck*`, `LandingOnDeck*`, `LandingQuality` | Landing prediction and quality |
| Bails | `Wipeout*` | Bail detection, ragdoll and recovery |
| Handplants | `Handplant*`, `Plant*` | Handplants and plants |
| Off the board | `Offboard*` | Walking off the board, off-board airs and ledge grabs |
| Climbing | `Climbing*` | Optional climbing clips and ledges |
| Respawn | `TeleportStateRuntime`, `PlayerTeleportRuntime`, `Respawn*`, `Revert*` | Teleports, respawn history and reverts |
| Animation | `Animation*`, `SkaterAnimation`, `MotionAnimation*`, `AnimatedSkeleton`, `RidingAnimation*`, `RenderPoseRuntime`, `BonelessRuntime` | Clip playback, blend trees, procedural adjustments and the published render pose |
| Scoring | `Scoring*` | Trick names, combos and score |
| Camera | `Camera*`, `GrindCamera` | Camera graph, shots, tracking and effects |
| Support | `NetworkProxies`, `HostScalar`, `DebugString` | Remote-proxy contacts and exact number and string formatting |

## Data bundle

The game tracks the bundle in `unreal/Content/Data/SkateNative/`. The adapter reads it from
`FPaths::ProjectContentDir()/Data/SkateNative` and refuses to start when `package-manifest.json` is missing.
`LoadGameplayResources` reads the files in this order and checks each one's magic tag:

| File | Magic | Content |
| --- | --- | --- |
| `settings.skate` | `ATATTR01` | Stock settings collections |
| `metadata/bank-0.skate`, `bank-1.skate` | `ATMETA01` | Animation metadata, merged into one lookup |
| `physics-skeletons.skate` | `ATPHYS01` | Physical skeletons (requires `PHYS_TPOSE`) |
| `animation/rig.skate` | `ATSKEL01` | Animation rig |
| `animation/clips/0/*.skate`, `clips/1/*.skate` | `ATCLIP01` | One clip per file, by animation bank |
| `custom/crouch-treflip.json` (optional) | JSON object | A project-authored clip override |
| `action.graph`, `motion.graph`, `camera.graph` | `ATGRPH01` | The action, motion and camera graphs |
| `camera.skate` | `ATCAM001` | Camera shots |
| `gestures.skate` | `ATGEST01` | Seven gesture sets: `main`, `rotated90`, `rotated_minus90`, `air`, `fingerflip` (right stick), `left`, `step` (left stick) |
| `custom/climbing.skate` (optional) | `SKCLIP1\0` | Climbing clips |

All formats are little-endian; strings carry a u32 byte count. A clip stores one f32 per constant component and one
per frame for a varying one.

`package-manifest.json` (version 1) lists the formats, the source identity and every file's path, size and SHA-256.
The tracked bundle has 3,334 payloads totalling 70,695,340 bytes: 3,324 clips (2,672 in bank 0, 652 in bank 1) with
131,642 frames, 285 gesture patterns and two metadata banks. It has no `custom/` files.

## Verification

### Bundle check

The game's `skate.runtime` build step runs its `tools/verify_skate_native.py` against the descriptor in
`assets/skate/runtime.json`, and `unreal.compile` depends on it. It checks:

- the descriptor's version and backend, the manifest's SHA-256, version, formats, source identity and counts;
- that the file set matches the manifest exactly, with safe relative paths and no symlinks;
- each file's size, SHA-256 and magic tag, rejecting any file the table above does not allow;
- the rig header (at most 255 bones), each clip's layout (bank, weights per rig bone, ten tracks per bone, one sample
  or one per frame) and each gesture pattern (2 to 15 points);
- the source identity inside `physics-skeletons.skate` and `metadata/bank-0.skate`.

It writes `build/<game>/skate-native/verification.json`. It checks integrity, not behaviour; the parity checks below
cover behaviour.

### Rebuilding the bundle

The tools in `Tools/` turn the original data into the bundle. Normal builds never run them. Rerun them only to change
a native format or to add an optional `custom/` file, then copy the result over the bundle and update the descriptor's
`manifest_sha256` and counts.

| Tool | Input | Output |
| --- | --- | --- |
| `convert_native_data.py --source A --output O [--animation-samples S]` | Restored original assets (`A/private/...`), decoded clip export | Settings, gestures, graphs, physical skeletons; clips with `samples-manifest.json` |
| `convert_animation_metadata.py --decoded D --output O` | Decoded metadata export | `bank-*.skate` and `metadata-manifest.json` |
| `convert_camera_data.py --decoded D --output O` | Decoded camera export | `camera.skate` |
| `assemble_native_package.py --assets A --samples S --metadata M --camera C --output O` | The above | A complete bundle and its `package-manifest.json` (`O` must not exist) |

The decoded exports come from the reference readers: `check_animation_samples_parity.py` and
`check_animation_metadata_parity.py` write them under their `--output` as `decoded/` and convert them to `native/`.
`assemble_native_package.py` also picks up `private/custom/crouch-treflip.json` and `private/custom/climbing.json`
from the assets when present.

### Parity checks

`Tests/` holds 155 `check_*_parity.py` scripts, one per system or slice of a system, plus helpers
(`historical_oracle.py`, `reference_build.py`, `session_parity.py`, `session_terrain.py`, `player_input_protocol.py`,
`reference_case_runner.py`). Each script builds a C++ probe from `Tests/Native/` against the native sources and a Rust
probe from `Tests/Reference/` against a Git snapshot of the reference, runs both on the same inputs and compares the
outputs bit for bit. The docstring of each script says what it covers; `--help` lists its options. Most take
`--assets` (the restored original assets), `--output` and `--target-dir` (a Cargo target directory), all under
`build/`; many accept `--preflight`, which stages and hashes the sources without compiling. The widest checks are:

- `check_gameplay_session_parity.py`: complete sessions through `GameplaySession` against the `46513a6` reference;
- `check_latest_gameplay_session_parity.py`: the transfer button and vert assistance against `1536531`, given the
  previous check's output as `--baseline-build`.

Compiling and running probes is heavy: run it under the render lock and memory guard. With `<game>` the game whose
history holds the original assets:

```sh
P=platform/engine/Plugins/Activities/Skate
O=build/<game>/skate-cpp
python3 $P/Tests/historical_oracle.py --game <game> --check-history --output $O/oracle   # pinned objects present?
python3 $P/Tests/historical_oracle.py --game <game> --output $O/assets                   # restore the original assets
uv run python -m atelier.safety.guarded --report $O/guard --kind compile --purpose "skate session parity" -- \
  python3 $P/Tests/check_gameplay_session_parity.py --assets $O/assets \
    --native-package games/<game>/unreal/Content/Data/SkateNative --output $O/session --target-dir $O/cargo
```

`historical_oracle.py` reads only Git objects already in the clone and never fetches; output must stay under
`build/<game>/`. `python3 $P/Tests/historical_oracle.py --game <game> --self-test --output $O/oracle` and
`cd $P/Tests && python3 -m unittest test_session_parity` test the helpers themselves.

### Reference build

`build_reference.py` extracts `ThirdParty/skate-runtime` at the pinned commit with `git archive` and builds the
reference binary `atelier-skate-runtime` with `cargo +1.97.1 build --release --locked --jobs 2`, recording
`provenance.json` beside it. No script installs the toolchain or fetches dependencies; prepare them by hand, once
(with `P` and `O` as above):

```sh
rustup toolchain install 1.97.1
mkdir -p $O/snapshot && git archive 46513a6:$P/ThirdParty/skate-runtime | tar -x -C $O/snapshot
cargo +1.97.1 fetch --locked --manifest-path $O/snapshot/atelier-host/Cargo.toml
uv run python -m atelier.safety.guarded --report $O/guard --kind compile -- \
  python3 $P/Tests/build_reference.py --output $O/reference --target-dir $O/cargo
```

`session_parity.py record --reference $O/reference/atelier-skate-runtime --reference-provenance
$O/reference/provenance.json --assets A --recording R` records a fixed-step session suite (`--suite flat` or
`terrain`) into the new directory `R`. `compare --candidate <executable> --assets A --recording R --report D` replays
it against another executable speaking the same protocol; `repeat-reference` replays it against the reference binary
to check that it is deterministic.

`build_native_session_cli.py` stages (default, `--preflight`) or compiles (`--compile`) the offline QA executable
`build/skate-native-session-cli/gameplay-session-cli` from every native source plus
`Tests/Native/gameplay_session_cli.cpp`, with `clang++ -std=c++17 -O2 -ffp-contract=off -fno-fast-math`. Run
`--compile` under the guard. The game's offline checks drive it; it is a test tool, not a game backend.

## Limits

- The checks establish equivalence with the recovered implementation over their recorded inputs, not with the
  original console game. Operating-system input timing and the timing of background collision builds are outside
  them.
- The reference's own test
  `physics::board_world::broadphase_tests::predictive_contacts_and_retention_match_full_scan_for_every_primitive`
  fails at the pinned commit: its linear scan finds extra contacts on distant triangles that the indexed scan
  rejects. The C++ keeps the indexed behaviour.
- Collision is a static snapshot: moving objects, skeletal meshes, procedural meshes and streamed-out terrain are
  not seen.
- Every surface gets one collision material (friction and restitution). Ground kinds differ only by the recovered
  surface profile that the wheels' vote selects (smooth, rough, slow, very slow), and by their sounds.
- Rails reach the session as polylines only; their kind, side and radius are not used.
- A complex-as-simple mesh is seen in a cooked build only if its importer enables CPU access. Editor builds are the
  checked path; cooked loading of the bundle is unverified.
- The solver keeps the recovered rider's proportions, so contacts near low obstacles can need visual review on a
  differently proportioned character. Grab grips scale with the host's hand, but the finger curl angles are fixed:
  on a hand with short fingers for its knuckle spacing, the fingertips end at the rail rather than under the deck.
- Only the `pop`, `land` and `clatter` sounds play; `catch`, `push`, `flick` and `fall` are loaded but not
  triggered. The original audio and interface are not part of the runtime.
