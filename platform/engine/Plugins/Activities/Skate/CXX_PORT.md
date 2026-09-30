# C++ skating migration

The required end state is one in-process C++ skating implementation using project-native data. All current
physics, animation, gameplay and camera behavior must be preserved. The Rust worker and original data
formats are migration references until the replacement has passed differential checks; they are removed
from the final runtime and normal build. A partial controller, a Rust library behind C++, or recorded-pose
playback does not satisfy this migration.

## Verification contract

- Pin reference source/data identities. Feed identical initial conditions, collision/rail geometry, tuning
  and controller samples at the same fixed simulation period to the reference and replacement.
- Compare all published fields at every tick, including pose, velocity, state, trick/score and camera.
  Add internal graph/controller/solver state probes as systems are translated to locate the first divergence.
- Start with exact float bits. Any tolerance needs a specific demonstrated arithmetic cause and must not
  hide changed contacts, transitions, landing decisions, scoring or bails.
- Convert the data once. Verify every used value, ordering, reference and animation sample against the
  original readers before allowing the new format into the runtime.
- Cover authored examples, boundaries, generated input, long rides, both stances and difficulty settings.
  Validate the integrated game and frame pacing after replacing the worker.
- Expected outputs come from the independent reference implementation, never from the new C++ code.

The reference integration is `46513a6`, including the current 1.6 spin scale, collision-shape export and
asynchronous collision refresh/preload changes. Data tracking is inherited from `02233f1`. Reference
scenarios include the current 1.6 spin setting as well as the previous 2.15 regression cases.
The migration branch also includes `68e384a`'s walking/skating camera easing. That change is entirely
in the Unreal adapter; the worker source remains identical to the pinned reference.

## Work remaining

- [ ] Whole-session record/replay comparator and pinned reference traces.
- [ ] Data conversion: settings, skeleton, gestures, graphs, camera samples, animation hierarchy,
  poses, clips, blend/selection definitions and attributes.
- [ ] C++ scalar/geometry/curve kernels and controller input.
- [ ] C++ graph execution, action/motion conditions, behaviors and intent publication.
- [ ] C++ animation decoding, clocks, blending, procedural adjustments and physical feedback.
- [ ] C++ collision/BVH, bodies, contacts, constraints, board and rider solver.
- [ ] C++ ground/air/grind/manual/slide/pump/off-board/wipeout state owners and scoring.
- [ ] C++ camera and complete session scheduling.
- [ ] In-process Unreal ownership, background world refresh, mounting, retargeting and shutdown.
- [ ] Remove the Rust worker/build dependency and original runtime data formats; commit all native data.
- [ ] Run whole-session comparisons, in-game scenarios, visual checks and frame-pacing checks; submit the PR.

## Gesture port

`Source/AtelierSkate/Private/Native/Gestures.*` ports the reference recognizer into C++ with preserved
evaluation order, overflow masks, tie selection, refractory and held-pattern handling. Only the explicitly
fused strength calculation uses `std::fma`; ordinary squared distances retain separate multiplies and adds.

`ATGEST01` is a little-endian native data format: eight-byte signature, set count, then each set's UTF-8
name, stick index and patterns. Strings use a u32 byte count. Each pattern stores its name, squared tolerance
as original f32 bits, point count, and authored-order pairs of f32 coordinates. Names, duplicates and set
order are preserved. The C++ runtime contains no original PAT parser.

`Tests/check_gesture_parity.py` independently compiles the original Rust recognizer/PAT reader and the C++
port. It compares decoded data and every output bit for all authored patterns, input durations, difficulty
settings, miss limits, counter wrapping and deterministic noisy streams. It is a subsystem check and does
not establish whole-game parity. Run it through the shared render lock/memory guard; place all generated
outputs in the game's build directory. The reference Rust probe is temporary migration tooling.

## Settings and graph data

`ATATTR01` stores every settings record, with interned UTF-8 names and host-order numeric words. Text
values retain their full UTF-8 data; partial numeric words retain their original length and bits. Name
identity, direct-name lookup priority, numeric aliases, inheritance and typed access follow the original
implementation. The game will not parse the original JSON or its big-endian hexadecimal strings.

`ATGRPH01` stores a preorder element arena, interned strings, all attribute representations and ordered
child indices. Duplicate attributes remain in the data, while lookup keeps the first hashed key, including
collisions. `GraphBinding` preserves operation order, disabled ancestry, condition masks, priority,
interrupt ancestors, transition resolution and dotted-path search. `CompiledGraph` maps those bindings into
the C++ controller's executable topology and compact operation IDs. Registered gameplay operations and
their physical inputs still require porting; matching generic execution alone does not establish gameplay parity.

## Native animation samples

`AnimationSamples.*` reads the project's `ATCLIP01` tracks and `ATSKEL01` hierarchy/reference poses. Each
scale, quaternion and translation component retains its original f32 bits. A constant component stores one
word; a varying component stores one word per frame. There is no quantization, frame reduction or original
compressed animation reader in the C++ runtime. Channel weights, loop transforms, timing, bank identities,
parent/mirror indices and per-bank pose replacement order are preserved.

The one-time exporter uses the original decoder on every clip and every reference-pose record. The conversion
tool then packs native tracks. The C++ probe reconstructs the complete decoded output and compares every byte
against the original export, including all frames and bones. Animation metadata, clocks, interpolation,
blending and physical pose adjustments remain separate migration tasks.

## Validation completed

On arm64 macOS, optimized Clang C++17 versus Rust 1.97.1:

- Gesture data and recognizer: all 285 patterns, 13,722 cases, 551,088 input records and 47,908 matches;
  all published bits identical, with no tolerance.
- Settings identities: 21,317 authored/boundary/generated names; C++ and the converter match Rust u64 IDs.
- Settings: all 6,849 records and 87,668 fields identical; 249,866 direct/alias/inherited queries match,
  including 33,840 inherited fields and typed numeric bit patterns.
- Graph decoding, lookup and binding: all three authored graphs (18,364 elements), 12 additional valid and
  invalid fixtures, and 203,374 hash inputs. Includes a real collision between differently spelled keys,
  raw boolean bytes, duplicate attributes, nonfinite float payloads, dotted paths and a 1,501-level tree.
- Generic graph execution: 128 generated hierarchies and 20,736 commands, preserving all 36,855,872
  output bytes from the reference. Comparisons include lazy condition calls, masks, priorities, self/ancestor
  transitions, state timer bits, allocation/begin/update/end/hook/release order, opaque contexts and immediate
  host side effects. Concrete gameplay operation hosts and their physical producers remain to be ported.
- Authored graph compilation: exact controller programs and operation IDs for action, motion and camera
  compared with the unmodified original host compiler. Each executes 65 commands with the deterministic
  test operation host; every output byte matches the original controller. The compiler also rejects an
  unresolved transition target exactly as the reference does, even when binding disabled that transition.
- Animation sample conversion: all 3,324 clips, 131,642 frames and 4,739,112 bone samples reconstruct exactly,
  together with the full rig and reference poses. 833,087 of 1,196,640 component tracks are bit-identical
  constants. Decoded sample files shrink from 190,365,107 bytes to 65,630,991 bytes without quantization.
- The session comparator's five regression tests catch single-bit float differences, signed zero,
  nonfinite output, field/array omissions and integer differences without lossy float conversion.
- A frozen build of reference `46513a6` reproduced all 8,286 published responses across 25 flat-ground
  scenarios exactly on a second run. States exercised: GroundAnimation, KnownAir, PhysicsGround,
  SlideGround, Teleporting and WipeoutGround. This establishes reference repeatability for that corpus;
  there is not yet a complete C++ session candidate to compare. Transition/bowl/rail coverage remains open.

Generated reports and probe binaries live under `build/<game>/skate-cpp/`. Reproduce subsystem checks
with `Tests/check_{gesture,name,settings,graph}_parity.py --assets ASSETS --output BUILD_DIRECTORY`, through
the shared render lock and memory guard. Temporary Rust oracles compile the unmodified original source;
the graph probe stages its original module layout verbatim in the build directory.
Run the generic controller comparison with `Tests/check_controller_parity.py --output BUILD_DIRECTORY`.
`Tests/check_compiled_graph_parity.py` tests the full authored data-to-controller connection. It also takes
`--assets ASSETS --output BUILD_DIRECTORY --target-dir CARGO_CACHE`; all original Rust implementation files
come from the frozen Git revision. The temporary probe adds only its own target and dependency declarations.
`Tests/check_animation_samples_parity.py` takes the same arguments and compares every original decoded sample
against C++ reconstruction, including rig lookup and malformed-data checks. Generated native assets remain in
the build directory during migration; the final native package must be tracked before the runtime switches.

`Tests/build_reference.py` extracts the pinned source directly from Git, builds it with its locked Cargo
dependencies, and records the compiler, source hashes and executable hash. `Tests/session_parity.py` requires
that provenance when recording. `repeat-reference` checks reference determinism; `compare` refuses to
accept the reference executable as a C++ candidate. The current external worker protocol exposes each
packet's final pose; probes for intermediate ticks, solver state and graph execution remain to be added.

These are migration foundations. The production game still uses the existing backend until the complete
C++ session passes the remaining verification contract. The final runtime will contain only the C++ backend.
