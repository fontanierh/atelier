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

## Native physics arithmetic and controller input

`NativeMath.*` and `Geometry.*` preserve scalar estimates, recovered trigonometric polynomials,
quaternion/matrix operations, point graphs, camera Bezier samples, closest triangle points and thin
triangle queries. Explicit nonfinite paths preserve the frozen compiler's operand ordering, including
NaN signs and payloads; the comparator does not canonicalize these results. `GeometrySweep.*` adds
the rounded-triangle dispatcher, sphere/cylinder roots and bounded feature walk. Misses retain the same
payload fields and partial updates as the reference. `WorldGeometry.*` preserves static triangle caches,
authored metadata, mesh acceleration, ordered candidate traversal and nearest thin/swept line queries.
`GeometryFeatures.*` adds primitive projection intervals, separating axes and capsule/triangle/box
point/edge/face selection, retaining incoming scratch lanes and original partial writes.
`GeometryPrism.*` intersects those features into ordered contact pairs, preserving clipping scratch,
header updates, normal correction and the original 16-pair capacity contract.
`GeometryTriangleFixup.*` preserves face/edge/vertex classification, sidedness, convexity and disabled
vertices, including normal bending and contact reprojection. `WorldPrimitiveContact.*` composes the
typed sphere/capsule/triangle/box path, the original triangle/box separating-axis specialization,
velocity-based separation allowance and complete contact manifolds. `WorldContactProducer.*` connects
ordered candidate traversal, primitive queries, material combination, retention and imported-floor
seam suppression. Body-workspace preparation remains separate work. `ContactRetention.*` preserves ordered material
combination, duplicate rejection, coplanar reduction, point selection and capacity/flush behavior.

`RigidBody.*` preserves the packed body update, typed body adapters, quaternion integration, inverse
inertia, point forces, drag, caps and cooldowns. Opaque lanes survive packed updates and reaction words
are cleared in the original order. `BodyMass.*` preserves primitive sphere/capsule/rounded-box/cylinder
moments and volume. `ConstraintSolver.*` runs compiled contact, joint and drive records in shared
iteration order, preserving position/velocity reaction separation and carried lanes. It validates every
reaction index before any mutation, including zero-iteration calls. `ContactBuild.*` preserves contact
arm/inertia preparation, active-body gates, mass response and restitution targets. It publishes a
compiled record only after the mass-response callback succeeds. `AggregateMass.*` preserves compound
volume moments, principal-axis reduction and mass finalization. `DeckGeometry.*` reconstructs the
deck's primitive/triangle children, including disabled children's mass and the final deck-frame override.
`DriveFrames.*` computes the seven authored part poses, truck geometry and relative parent/child frames.
`ConstraintFrames.*`, `JointBuild.*` and `DriveBuild.*` preserve frame composition, joint limit modes,
kinematic prediction, active-body mass gates and soft/hard drive targets. They emit the original full
compiled records consumed by the shared solver, including opaque joint identifiers and carried lanes.
`JointRecords.*` constructs the six authored deck/truck/wheel constraints in registration order, with
the original definition-to-live body reversal and stock/custom parameter/frame words.
`TruckDriveFrames.*`, `DrivePreparation.*` and `HookDrive.*` retain steering frame order, repeated
normalization, untouched translation lanes and the live animation-drive lifecycle.
`BoardPose.*` preserves part/mass-frame conversion, both distinct orthonormalization paths,
live body/inertia updates and whole-board movement with the separate original hook request.
`ContactGeneration.*` constructs the original tangents, copied force/inertia workspaces and typed
compiled contact facade. `BoardAssembly.*` builds the ordered six-joint/two-truck/hook assembly from
live snapshots, preserving active-body filtering and live hook normalization. Complete body ownership
and scheduling remain open. These comparisons establish
parity with the frozen Rust reconstruction, including its documented unresolved retail joint-matrix
gather and carry-lane interpretation; they do not independently verify those against the EA executable.

`Input.*`, `InputIntentions.*`, `AnimationName.*` and `Intents.*` preserve pad history, Xbox conversion,
retained controller fields, encoded-name aliases, ordered intent emissions, turn filters and slide state.
These cover the original core modules. Production host scheduling, camera-relative off-board remapping
and complete motion gameplay remain open. `GraphConditions.*`, `GraphIntentOperations.*` and
`GraphMotionSliding.*` add typed action-host factories/conditions/lifecycle, ordered action-to-motion
intent publication, and the original host's distinct slide state/direction/deceleration behavior.
Unported graph leaves retain explicit diagnostics rather than silently supplying a neutral result.
`GraphGestureOperations.*` preserves all authored gesture-to-trick mappings, encoded-key bucket
priority, mirror/dark-catch/underflip selection and the later flip-hold intent lifecycle. Its action-host
registration now runs through the real C++ controller, with fresh per-instance state and owned cleanup.
`GestureInputPublication.*` owns the seven recognizers over the native gesture bank, original stick
deadzone/Y conversion, held-pattern ordering and graph permission gates. The frame scheduler must still
call it at the original point between mapped controller input and action-graph evaluation.

Arithmetic source files disable implicit Clang FP contraction and use explicit fused operations where
the reference does. The module disables unity compilation so internal helpers and FP settings remain
isolated in the same translation units used by the standalone checks. Unreal compilation remains a
separate integration check; standalone tests alone do not establish engine compatibility.

## Native physical skeleton

`PhysicsSkeleton.*` reads `ATPHYS01`: all 28 words of every physical bone, its name and record identity,
plus the source bank identity. Size, rotation and translation are derived without decimal conversion.
Lookup preserves ASCII case-insensitivity; native loading validates bounds and retains the current package
if a replacement fails. The runtime no longer needs a JSON parser for these records. Body construction,
constraints and collision remain separate migration work.

## Native animation metadata

`AnimationMetadata.*` reads `ATMETA01` banks containing clip timing/flags/attributes, phase blends,
blend-space simplexes, selectors and selection spaces. It preserves raw attribute payloads and every
record, including overwritten names. Direct clip lookup and tree lookup keep their distinct tie-breaking
rules; bank merging rejects namespace collisions and preserves source identity.

The temporary exporter reads through the frozen original decoder. It exposes overwritten records by
renaming headers in an input copy, then verifies the complete payload of every winning clip/tree against
the untouched bank. Both the independent exporter and C++ dump must agree with the native converter.
Run `Tests/check_animation_metadata_parity.py` with the same assets/output/target-dir arguments as the
animation sample check. The final runtime consumes the native banks, not original ABIN or metadata JSON.

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

## Native animation playback

`AnimationPlayback.*` ports clip clocks, event windows and curve sampling, attribute blending/mirroring,
channel fade/resurrection state, frame selection and decoded-pose blending. It reuses the native sample
and metadata readers. Retained payload lanes and duplicate attributes preserve their original behavior.
`AnimationPlaybackParameters.*` preserves parameter sources/defaults and PlayAnimation lifecycle
requests through an explicit service interface. `AnimationTrees.*` constructs every authored tree and
preserves phase/blend/selection clocks, deferred selection, transition insertion/pruning, bind-pose flags
and the main-tree owner lifecycle. `AnimationChannels.*` adds ordered persistent overlays with encoded
key lookup, priority ties, retirement, transition resurrection and channel-weighted attributes/commands.
`AnimationPose.*` executes the command stack, trajectory deltas, full bone poses and hierarchy. Stock
poses use the verified native tracks. Project-authored custom/mod overrides retain their existing
version-1 absolute-joint JSON interface, including baking and owner/conflict/precedence behavior; this
is not an original EA data format. `MotionAnimation.*` combines the main tree and live channels with
parameter sources, graph attributes, reset/stance and PlayAnimation/CreateAttribute factories and
lifecycle. Connecting that owner to the complete graph host and physical feedback remains separate
work; matching pose commands does not establish full animation execution. `AnimationPublication.*`
preserves actor stance/events and the selective animation-to-physics packet reset/publication boundary,
including consumed request flags, signal hashing and retained matrix tails.

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
- Rigid bodies and primitive mass: 41,020 cases and 2,460,235 exact output words (9,840,940 bytes), including
  evolving packed and typed bodies, orientation/inertia, force application, caps/cooldowns, every opaque
  body lane and sphere/capsule/rounded-box/cylinder moments.
- Shared math and initial geometry: 34,309 cases and 525,369 exact output words (2,101,476 bytes),
  including scalar/vector/quaternion/matrix/SQT arithmetic, point graphs, Bezier sampling, all seven
  closest-triangle regions and 1,103 thin-triangle hits. The corpus includes finite boundaries, signed
  zeros, infinities and NaN payloads.
- Rounded-triangle dispatcher: 17,156 cases and 205,872 exact words, including 4,121 hits and 13,035
  misses. Every miss retains position/volume payloads; 12,054 also exercise the original normal/fraction
  rewrites. Coverage includes faces/edges/vertices, both windings, degenerate geometry, overlap/tangency,
  radius/fatness boundaries and opaque incoming output records.
- Static world geometry: 3,669 cases, 8,815 line queries and 1,206,140 exact words, including 157 worlds
  requiring hierarchy splits, source-order nearest-hit ties, conservative bounds and all seven metadata
  diagnostic messages. PrimitiveBounds and primitive-contact integration are not established by these
  line-query checks and remain pending their original public contact-path comparison.
- Collision feature arithmetic: 13,917 cases and 1,664,030 exact words across single/batch projection,
  separating-axis generation/selection, segment construction, maximum features and edge planes.
  Includes speculative rejected-axis stores, every opaque scratch word and incoming box-plane lanes.
- Triangle contact correction: 23,342 cases and 2,169,222 exact words across all seven regions,
  sidedness/edge-cosine/convexity/disabled-vertex flags, reverse/object handling and all 16 contact slots.
  Coverage includes 6,606 accepted contacts, 113 normal bends, 99 pair reprojections and unchanged tails.
- Feature intersections: 10,376 valid cases and 3,018,956 exact words across all eight public prism
  helpers and every dispatcher feature-count pair. Complete prism records, mutated feature headers,
  clipping intervals and untouched scratch are compared. Three synthetic raw-feature cases exceed the
  original 16-point capacity; each is retained separately and both implementations must reject it.
- Primitive/world triangle contacts: 15,052 cases and 1,332,852 exact words, including 12,560 contact
  queries, velocity-based separation limits and triangle-volume transforms. All four primitive types
  produce both hits and misses (5,026 hits total); all 16 manifold slots are compared, including unused
  zeros. Packing and the private triangle/box specialization are exercised through the original public
  typed contact query. Complete world traversal and retention are checked separately below.
- Complete world contact production: 2,809 worlds, 4,755 queries and 2,371,281 exact words.
  The full original public query supplies every expected seed, including candidate/culling order,
  all primitive types, material combination, duplicates, deferred reduction and capacity drops.
  Paired imported-floor fixtures remove 774 internal seam contacts while retaining open edges/curbs.
  Body workspaces remain unpopulated until the simulation applies its current force queue.
- Contact generation: 9,820 cases and 940,436 exact words, including velocity/normal tangent boundaries,
  copied current force/torque workspaces, complete uncompiled/compiled records and independent body,
  reaction and contact identifiers. Six invalid-timestep fixtures fail on both original and C++.
- Contact retention: 6,268 cases and 3,733,259 exact words, including 756 stateful buffer streams.
  Every buffer field, all 50 complete records and each publication chunk are compared. Coverage includes
  10,743 capacity rejections, 320 duplicate rejections, 1,699 published chunks and source-order reduction,
  plus scalar float-copy NaN quieting with integer body IDs/tags retained verbatim.
- Shared constraint solver: 7,967 cases and 3,682,300 exact words (14,729,200 bytes), including mixed
  contact/joint/drive iterations over shared reactions, friction and limit boundaries, reversed body
  indices, softness/carry preservation and invalid indices rejected before mutation. An independently
  reviewed operand-order correction preserves the original signed-zero contact carry behavior.
- Contact construction: 11,264 cases and 1,464,320 exact words (5,857,280 bytes), including every exposed
  preparation field and compiled row, active/inactive bodies, 3,072 default reciprocal responses,
  4,096 injected responses and 4,096 callback failures that preserve the original input record. Default
  reciprocal cases stay in the original builder's documented finite-input/intermediate domain.
- Compound and part mass: 3,907 cases and 334,844 exact words, including transformed/accumulated moments,
  mutated center-of-mass moments, unsorted principal axes, inverse frames, strict mass fallback and stock
  wheel/truck finalizers. The corpus includes 1,024 compounds with one, two, four or eight children.
- Deck construction: 902 cases and 259,682 exact words, including child shapes/order/transforms/flags,
  triangle fat-AABB mass, disabled-child mass, zero/negative/end-fan counts, the deck-frame override and
  all seven default body masses.
- Authored part and drive frames: 1,927 cases and 140,880 exact words, including packed pose fourth lanes,
  truck rotation polynomials, dominant-quaternion ties, 1,024 relative-frame pairs and all stock defaults.
- Truck/hook drive frames and lifecycle: 8,022 cases and 941,372 exact words, including 612 stateful
  hook programs, 16,819 duplicate and 2,920 null registrations, carried translation lanes and
  non-normalizing hook setters. Four invalid registration fixtures fail on both original and C++.
- Board/part pose operations: 6,070 cases and 1,018,929 exact words, including 1,072 reused optional
  part programs, all eight body/mass/inertia presence masks and 765 complete board/hook requests.
  Full raw pose/body/inertia records retain the original fourth lanes and unrelated live rates/forces.
- Connected board constraint assembly: 2,048 cases and 4,452,352 exact words across all 256 board/hook
  activation masks. Comparisons include repeated frame preparation, full typed/packed rows, shared
  solver iterations and resulting body updates (9,216 joint and 4,608 drive rows).
- Persistent board runtime: 96 command streams, 8,379 snapshots and 7,464,452 exact words across
  active/frozen/static construction, force queues, resets, transform changes and shared attached-body
  solves. Comparisons include all body state, 9,269 solved contact rows, 1,892 reports and 384 force
  capacity rejections. Contacts use the current force workspace; all constraint families finish before
  any body's integration. Attached bodies here are explicit fixtures, not the gameplay skeleton producer.
  Optional debug capture retains its source cadence/lifecycle; C++ exposes typed diagnostics instead
  of the unused original formatted string, and this corpus checks diagnostic presence rather than text.
- Joint and drive construction: 7,244 cases and 933,564 exact words, including 2,952 complete joint
  workspaces, 3,519 typed/packed drive records, 260 drive parameter sets and 513 six-joint authored
  record sets with stock/custom settings. All swing/twist branches,
  active/kinematic body combinations, independent body bases, singular quaternion components, angular
  cone boundaries and soft/hard/disabled drive coefficients are compared. The private original drive
  packer is included unchanged in the reference probe; no candidate-generated expected values are used.
- Controller input and intents: 58,508 commands and 31,515,955 exact output bytes, covering encoded byte
  names/aliases, Xbox packets, pad history, retained raw/derived fields, ordered producer callbacks,
  filter state and slide latches. This is core subsystem coverage, not full host scheduling.
- Action host, conditions and production slide logic: 8,512 subsystem commands, 3,072 live controller
  ticks, 3,072 bound-condition frames and authored action parameters preserve 2,979,481 output bytes.
  All 12 host fixtures have distinct traces; oracle coverage requires actual state transitions,
  reallocation, both flip directions, varying numeric intent emissions and end-all cleanup. This does
  not cover the complete motion host or the whole-session scheduler.
- Gesture trick operations: all 270 authored mapping rows, 19,480 commands and 16,384 lifecycle frames
  preserve 14,890,874 output bytes, including selected names, map ordering, alias/collision priority,
  mirrored tricks and hold successors.
- Action-host gesture integration: 21 live graph fixtures and 1,344 controller ticks preserve 206,283
  output bytes. All seven groups exercise membership conditions, state selection, fresh instances,
  launch/hold progression, missing-stance errors and owned cleanup. The earlier action-host baseline
  also passes after registration; complete actor scheduling remains open.
- Stick gesture publication: 141,873 commands and 141,782 publication frames preserve 68,857,168 output
  bytes against the original host loading the original PAT/settings. Coverage includes 6,078 trick
  publications, 21,803 held-pattern frames and isolated permission gates. Hidden recognizer state is
  exercised through later outputs; whole-session sampling order remains a separate check.
- Animation playback: 7,115 cases and 41,311,421 exact bytes across clocks, curves, attribute operations,
  channels and pose blending. All 3,324 native clips are sampled at eight boundary/normal/invalid times
  against the frozen original core reading the independent decoded originals. Invalid-clock failures
  preserve the original partial updates through explicit errors; the C++ check disables exceptions.
- Animation parameters and PlayAnimation requests: 7,947 cases and 9,319,384 exact bytes, including
  callback interleaving, source/default/normalized values, variant precedence, consumed transition
  overrides, refusal/fallback/error handling and begin/update/end lifecycles.
- Animation trees: 4,881 cases and 4,633,249 exact bytes, including all 4,643 authored tree lookups,
  112 synthetic trees, 120 owner lifecycle sequences and six pending-posture sequences. Recursive
  clocks, pose commands, attributes, partial error output and construction behavior match the original.
  Owner comparisons use an empty original channel container; live channel integration is still pending.
- Animation channel container: 169 multistep cases and 8,048,904 exact bytes covering ordered trees,
  priority/encoded-key ties, fades, replacement/resurrection, retirement, parameter/attribute forwarding,
  pose commands and partial outputs on failure against the original channel container.
- Pose evaluator: 3,959 cases and 14,818,831 exact bytes across all 3,324 stock clips, complete poses and
  hierarchy, trajectory/add/mirror operations, command stacks and all seven project-authored override
  slots. Comparisons cover override ownership, conflicts, precedence, removal and representative schema,
  skeleton, timing and matrix errors. OS file-read error text and exhaustive malformed JSON diagnostics
  are not established by this corpus. The original evaluator and its authored-clip module are included
  byte-for-byte; staged module aliases are separately hashed without editing original implementation.
- Combined motion-animation owner: 338 multistep cases and 20,916,488 exact bytes covering main-tree
  and channel ordering, parameters, cached attributes, pose commands, reset/stance and immediate graph
  side effects. PlayAnimation/CreateAttribute factories and lifecycle use real service callbacks.
  Original tested method bodies and factory arms are extracted verbatim with recorded byte boundaries
  and hashes; the remaining gameplay graph and physical publication are separate integration steps.
- Animation/physics publication: 1,363 cases and 1,150,750 exact bytes for selective resets, complete
  packets, consumed requests, retained tails and flags, signed reset versus unsigned publication extents,
  stance/events/cull state, checkpoint requests and signed-byte signal hashing. Invocation order within
  the complete actor scheduler and live physical feedback remain separate checks.
- Physical skeleton conversion: all 24 authored physical bones and their 28-word records, typed transforms,
  record identities and case-insensitive lookup match the original Rust loader exactly. Wrong-bank/missing
  lookups and malformed native data are rejected.
- Physical skeleton bodies: 3,164 cases and 9,340,512 exact words cover definition/mass construction,
  hats, all four inertia modes, pose mapping, animation/physical COM history and 128 persistent 26-body
  programs with actual integration. The corpus includes 88 original volume errors and 64 mapping-bounds
  errors. Skeleton joints, drives, collision policy and whole-rider scheduling remain separate steps.
- Animation metadata: both banks, 3,324 clips, 14,879 clip attributes, 1,183 phase blends, two blend spaces,
  98 selectors and 38 selection spaces. Every record word/order and 4,643 original lookup results match;
  33 duplicate/tie fixtures, two merge fixtures and nine malformed-format cases pass.
- Animation sample conversion: all 3,324 clips, 131,642 frames and 4,739,112 bone samples reconstruct exactly,
  together with the full rig and reference poses. 833,087 of 1,196,640 component tracks are bit-identical
  constants. Decoded sample files shrink from 190,365,107 bytes to 65,630,991 bytes without quantization.
- The session comparator's five regression tests catch single-bit float differences, signed zero,
  nonfinite output, field/array omissions and integer differences without lossy float conversion.
- A frozen build of reference `46513a6` reproduced all 8,286 published responses across 25 flat-ground
  scenarios exactly on a second run. States exercised: GroundAnimation, KnownAir, PhysicsGround,
  SlideGround, Teleporting and WipeoutGround. This establishes reference repeatability for that corpus;
  there is not yet a complete C++ session candidate to compare.
- A second reference corpus adds 23 transition/bowl/rail/long-session cases and reproduces all 18,024
  responses exactly. It reaches PhysicsAir, GrindFiftyFifty, GrindFiveO, GrindTipslide and Nonspecific in
  addition to flat-ground states. Inputs cover both stances and all three difficulty settings. A pumping
  input scenario is present; proving pumping energy behavior and internal solver state remains open.

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
