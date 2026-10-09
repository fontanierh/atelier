# Typed data assets

A game's session reads all of its data from two typed assets that `USkateSettings` names:

- `MotionData`, a `USkateMotionData` (`SkateMotionData.h`), is the animation source. It
  references bounded `USkateMotionBank` assets, each containing at most 128 clips.
- `RuntimeData`, a `USkateRuntimeData` (`SkateRuntimeData.h`), holds the settings, the
  action, motion and camera graphs, the camera shots and shakes, the gesture sets and
  the physical skeletons.

`USkateDataLibrary::ImportMotion` and `ImportRuntime` build them from a simulation package.
The simulation reads them into the same structures, with the same interpolation, graph
evaluation and retargeting arithmetic, as the package files.

Loading (`SkateMotionAdapter.h`, `SkateRuntimeAdapter.h`) never blocks the game thread
in normal play:

1. The first session launch, normally the on-foot preload, requests both configured
   assets through the engine's streamable manager. The motion root and then its banks
   load asynchronously, as does the runtime asset.
2. While the packages are held, a task thread copies their fields into the existing
   immutable simulation structures. Nothing edits the assets at runtime. The runtime
   asset is encoded to the package's runtime files, each checked against the size and
   SHA-1 the import recorded, and read by the same loaders as the package files.
3. The decoded data is kept for the rest of the process and the packages are
   released. Later sessions, including the relaunch after a bail, reuse it at no cost.
   A failed load is forgotten, so the next launch retries.
4. The simulation worker waits for both on its own thread. A Ride mount that must
   wait for its first pose without ticking first finishes the package loads on demand;
   the decode still runs on a task thread.

In a packaged game the whole motion bank decodes off the game thread in about 70 ms on
an Apple-silicon Mac, before the first mount needs it. Offline replay equality does not
cover that timing; a packaged ground check does.

The motion assets hold named fields:

- Bone names, parent/mirror indices and reference poses.
- Per-bone scale XYZ, quaternion XYZW and translation XYZ float tracks. A constant
  component has one value; a varying component has one value per source frame.
- Frame rates/counts, loop rotation/translation and per-bone channel weights.
- Clip flags, speeds, scalar attributes and bone-contact events with named targets.
- Phase blends, blend-space simplexes, selectors and selection-space candidates.
- Bank source identity and record identifiers, including authored duplicate ordering.

The components use the simulation Y-up metres and binary32 floats. Quaternion components
are preserved without normalizing them. `FTransform` and compressed animation keys
would change these values: the existing animation-sequence importer composes a
reference pose, changes coordinate space, normalizes rotations and passes through
Unreal's key storage. The sequences remain the derived assets used by the Ride
body and retargeting; exact simulation sampling uses the typed component
tracks.

The runtime asset keeps each record's named fields in order. Every value the session
reads as a binary32 or raw word is stored as its `uint32` bit pattern, since a float
property would save negative zero as its default value. Graph attributes keep their
text alongside its binary32 reading; settings fields keep their declared type and byte
width.

## Building and verifying

A game recipe's `unreal.skate_data` step reads the complete simulation package that
`skate.runtime` assembles from the plugin's [`Data/`](Data/README.md) (every payload
built from the JSON in `Data/motion/` and `Data/runtime/` and checked against the
manifest). It runs three separate NullRHI editor processes. The first imports the
runtime asset; it decodes each runtime file into fields and requires the fields to
encode back to the same bytes before saving. The second imports and saves the motion
packages, and deletes banks left by an earlier, larger import. The third loads both
assets named by `USkateSettings` through the game's own asynchronous loaders and invokes
`USkateDataLibrary::Verify`:

1. Compare every simulation rig/reference field, metadata record, track component,
   loop transform, channel weight and expanded frame/bone sample exactly. This
   compares float bits, including signed zero, rather than accepting a tolerance.
2. Compare every encoded runtime file with the package's, byte for byte, and load the
   production resources from the two assets exactly as the game does.
3. Replay twelve deterministic controller cases across both stances through the
   production `GameplaySession`, comparing each published root, bone, velocity,
   state, camera, score, trick and balance value. Cases cover push, ollie, steering,
   spins, slide inputs and trick-stick inputs at 30/60 Hz transport rates.
4. Change one motion sample bit in memory and require the exact checker to reject it,
   and change one camera bit and require the digest check to reject it. Saved assets
   are never changed by these controls.
5. Reject a cyclic rig, an empty component track and a zero metadata frame rate; reject
   an out-of-range graph child, a short physical bone and an unset schema version.
6. Require every package in the bank and runtime folders to be referenced, since both
   folders are cooked.

The step reruns when the data, the AtelierSkate module, the game config or the installed
engine version changes. The assets are read-only in the editor:
details-panel edits would pass floats through text, and the next import overwrites
them. `SchemaVersion` is written by the importer and defaults to 0, so assets from an
older schema are rejected rather than read as current.

No game, map, renderer or live bridge is started. The verification report lives in
the game's build output under `skate-data/verify.json`. Replays provide a finite
behavioral regression corpus. Exhaustive source-field equality plus unchanged
the simulation evaluation code establishes that the storage conversion preserves inputs;
it does not claim to exercise every possible game interaction.

## Scope

The game ships only the typed assets, which are cooked with it; a missing or invalid
asset fails the session launch. Tools, offline checks and the Ride clip imports read the
assembled package.

The data is committed as readable JSON (`Tools/motion_text.py` for the animation, one
file per clip, and `Tools/runtime_text.py` for the rest). The JSON writes each binary32
value as its shortest round-trip decimal, so the build regenerates the simulation files byte
for byte, and those files remain the independent reference. Typed packages are generated
under the game's ignored Content, like the Ride clip sequences; rebuilding the step
overwrites edits to them. The assets hold only named fields. The motion importer
supports the scalar and bone-contact attribute types the bundle uses and rejects any
other kind or nonzero alignment padding.
