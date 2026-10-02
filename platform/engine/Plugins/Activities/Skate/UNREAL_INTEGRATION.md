# Unreal skating integration

The recovered C++ `GameplaySession` remains the only skating solver. This integration moves content loading,
animation presentation, collision authoring and tooling into Unreal; it does not replace board/rider physics
with Chaos. Simulation arithmetic, controller sampling, recovered graph evaluation and animation timing remain
in the native runtime.

## Source data and cooked assets

A game tracks every native source record in `games/<game>/assets/skate/native`. `runtime.json` pins the
manifest and counts; `profile.json` supplies the game's tuning and content references. Generated `.uasset` files
belong in ignored Content and are reproducible from these tracked inputs.

`atelier build <game> skate.runtime` verifies the source without Unreal. `atelier build <game> unreal.skate`
runs one headless editor script after the geometry, character and audio imports. It creates:

| Asset | Contents |
|---|---|
| `/Game/SkateNative/DA_RuntimeData` | Exact manifest bytes and 3,334 ordered native records with their SHA-256 hashes; no float conversion or animation recompression |
| `/Game/SkateNative/DA_Collision` | Hard references to per-mesh baked collision data and explicit Physical Material mappings |
| `/Game/SkateNative/CollisionMeshes/*` | Source mesh soft reference, collision LOD, body GUID, local f32 positions/normals, triangle indices/material slots and convex fallback indices |
| `/Game/SkateNative/DA_Profile` | Typed runtime-data and collision-catalog soft references, difficulty, stance, tuning, board/audio references and scene-scan interval |

The builder includes saved-package byte comparisons and file-source versus asset-source sessions in both stances,
recording exact public pose, camera and scoring words. The filesystem loader is a QA entry point into the same
parser and solver; gameplay uses only the asset source. No fallback is selected if an asset is missing or invalid.

`USkateSettings::DefaultProfile` selects a profile. `USkateComponent` can instead receive a profile before
`Initialize`, or change it through `SetProfile` while off the board. Profile references and catalog data are validated
before use. The game thread copies resource bytes into immutable plain C++ ownership; the native worker never
reads UObjects. Structural checks and copying happen on the game thread; full checksums run on the native worker
before decoding. Corrupt manifests/payloads are rejected together and failed loads retain the caller's previous output.
The extra transport copy is released after decoding. Retained sessions reuse decoded banks across
mounts, and activation generations reject stale poses.

The game's cook rules must include `/Game/SkateNative`, the board meshes and required sound folders. Asset Manager scans
the profile and runtime-data types and recursively manages their dependencies. The raw source folder is outside
Content/Data, so NonUFS world-data staging does not also copy skating source records.

## Animation

`FAnimNode_SkatePose` is a local-space AnimGraph node with a Base Pose, Weight and optional explicit source component.
Its game-thread `PreUpdate` captures the mesh-indexed local transforms and generation identifiers. Animation workers
consume that copied snapshot without dereferencing the component or other UObjects.
An explicit source must use the target mesh's bone indexing. Pin-driven source changes are captured at the next
`PreUpdate`; the node itself does not retarget between skeletons.

At Weight 1, the node follows the former proxy assignment exactly: reset to the reference pose and copy solved
transforms by mesh bone index. The base graph still updates its clocks. An inactive/invalid pose or zero weight passes
through; intermediate weights blend toward the same solved pose. Native hosts can use this node as their graph root
instead of a custom skating `Evaluate` override. Existing retargeting, foot IK, character proportions and bail skin
clearance remain in the adapter.

The editor graph wrapper supports ordinary Animation Blueprints. The Python-callable animation validator checks
full-weight scalar bits, missing bones, inactive/zero passthrough, partial blending, invalid values, clock behavior
and capture generations for the supplied mesh and profile paths. An optional animation-instance class path adds
checks of the actual native proxy's root/PreUpdate wiring. Node diagnostics expose copied values and a transform
hash after the animation proxy has finished its worker tasks.

## Collision and scene changes

Runtime world snapshots use cooked local collision data for complex-as-simple meshes. They retain the accepted
source triangle order, winding, transformed authored normals, sliver rejection, f32 conversion and seven-decimal
publication. Simple boxes, spheres, capsules and convex bodies use their cooked `UBodySetup` geometry; hull indices
that formerly required a Chaos geometry accessor are baked in the editor. Runtime gathering never reads static-mesh
render buffers or calls that fallback accessor.
The builder disables static-mesh CPU retention before baking and validates the final false-flag source geometry
against the baked words. A game can retain static CPU buffers for separate diagnostics, such as tree-LOD unit
checks. The rider's skeletal bail-clearance samples still require CPU access.
Discovery combines registry entries, meshes referenced by validation maps and actual types loaded from source
packages. This includes meshes spawned later from world data even when their registry metadata is incomplete.

The native BVH, queries, contacts and board/rider constraints are unchanged. Collision retains the adaptive
100/60/35/20 m radii and 500,000-triangle limit. The inner refresh radius remains 60% of the chosen radius. Registered
rail order and spline construction are preserved. A changed source LOD/body setup rejects a stale catalog and asks
for a rebake instead of silently omitting geometry.

Scene tracking compares exact component, mesh/body, transform, instance, material-profile and rail state at the
profile's bounded scan interval (default: 0.25 s). Added, removed, streamed or moved geometry marks the snapshot
dirty even if the rider stays in its inner cube. Gathering occurs on the game thread; BVH construction runs on a
background native thread and installs between simulation ticks. Changes observed while a build is pending remain
dirty for the next refresh. Moving geometry supplies updated shape positions; there is no platform-velocity transfer
or bidirectional rigid-body coupling.
Removing the final nearby colliders fails safely instead of preserving ghost collision. Rail providers must remove
their registered lines on unload and keep bounds current when editing points; the registry does not track actor ownership.

Physical Material mappings are explicit. An unmapped material retains the stock contact material and packed surface
zero. A mapping can override static/dynamic friction and restitution and set a native packed 16-bit surface value:
the low seven bits identify the grind material, bits 7–11 the physics surface category. Unreal's SurfaceType enum is
not converted into an assumed native ID. Default catalog mappings stay empty to preserve existing skating behavior.

## Tools and diagnostics

The `AtelierSkateEditor` module supplies Python-callable libraries for lossless data building, collision baking and
validation, and animation validation. Collision can also be baked through the headless `SkateCollision` commandlet
with `-Roots`, `-Meshes` or `-Map`, `-Catalog`, and optional `-ValidateOnly`/`-Report` arguments. The game module has no
editor-module dependency.

`USkateComponent` exposes Blueprint mode/trick/landing/bail/failure events and `GetRuntimeDiagnostics`. Events publish
after the solved frame has been applied, so listeners can safely stow the board. Diagnostics include readiness,
pending pose/world work, data identity, native tick, pose generation, collision counts/revision and errors.
The game's live bridge can combine those values with its animation instance's snapshot diagnostics.

The aggregate builder writes `build/<game>/skate-unreal/validation.json`. Live runtime, park and frame-pacing
scenarios remain the gameplay checks. Each engine run and compile uses Atelier's render lock and memory guard.
The `skate_unreal` live scenario checks actual graph diagnostics, stationary-rider add/move/remove refreshes,
atomic profile changes, remount generations and recovery inside a Blueprint failure callback.
The opt-in runtime `-SkateCookedProbe=<report.json>` loads the configured profile/data/catalog in a cooked game,
checks cooked package flags and disabled static render-buffer CPU retention, and exercises both stances on an
actual baked floor mesh. It requires no Python plugin or raw source folder and exits after writing its report.
The normal game cook uses the committed Asset Manager and Always Cook rules. Run the probe in a staged game with
`-NullRHI -unattended` for an asset/session check; a rendered package also needs normal shader and gameplay validation.
Use a report path inside the signed app's writable container on macOS. Read the JSON `valid` field to determine
success; platform support for the requested process exit status varies.

## Validation status

The native differential checks described in [RUNTIME.md](RUNTIME.md#verification) establish the solver baseline.
Mac Development Editor and Game targets compile. The aggregate headless pass verifies all 3,334 source payloads,
19 integrity/roundtrip checks, exact file-versus-asset public words across 240 ticks in both stances, and 110 animation
checks. Collision validation covers 417 unique source meshes, reflected/nonuniform transforms, both maps and material/
scene fixtures. Static CPU retention is disabled on 408 meshes; nine tree-LOD diagnostic meshes retain it.
The live gameplay and park suites pass 19/19 and 7/7. A staged non-editor Mac game loads all records and the 417-mesh
catalog from cooked packages with loose Content/Data excluded. Both stances complete 480 actual simulation ticks,
including supported pushing, ollie/trick air, finite poses/camera/scoring and non-tick pose changes. The selected
floor's render data is absent under NullRHI and its CPU-retention flag is false. The seven live integration checks
pass, including stationary scene refresh, atomic profile changes, remount generations, failure-callback recovery and
removal of the final colliders. All six frame-pacing activities pass at 59.5–60 fps, with p95 at most 17.47 ms, p99
at most 23.59 ms and no repeated native poses. The cooked probe covers assets and sessions; rendered gameplay
checks use the editor game rather than a rendered packaged build.
