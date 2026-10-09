# Typed motion assets

`USkateMotionData` is the native simulation's animation source. It references bounded
`USkateMotionBank` assets, each containing at most 128 clips. The simulation,
interpolation, graph evaluation and retargeting arithmetic are unchanged.

Loading (`SkateMotionAdapter.h`) never blocks the game thread in normal play:

1. The first session launch, normally the on-foot preload, requests the configured
   asset through the engine's streamable manager. The root and then its banks load
   asynchronously.
2. While the packages are held, a task thread copies their fields into the existing
   immutable native animation structures. Nothing edits the assets at runtime.
3. The decoded source is kept for the rest of the process and the packages are
   released. Later sessions, including the relaunch after a bail, reuse it at no cost.
   A failed load is forgotten, so the next launch retries.
4. The simulation worker waits for the decoded source on its own thread. A Ride mount
   that must wait for its first pose without ticking first finishes the package load
   on demand; the decode still runs on a task thread.

Cooked-package behavior and the measured startup cost still need a runtime check.
Offline replay equality does not measure them.

The assets contain named fields rather than a serialized `.skate` blob:

- Bone names, parent/mirror indices and reference poses.
- Per-bone scale XYZ, quaternion XYZW and translation XYZ float tracks. A constant
  component has one value; a varying component has one value per source frame.
- Frame rates/counts, loop rotation/translation and per-bone channel weights.
- Clip flags, speeds, scalar attributes and bone-contact events with named targets.
- Phase blends, blend-space simplexes, selectors and selection-space candidates.
- Bank provenance and record identifiers, including authored duplicate ordering.

The components use native Y-up metres and binary32 floats. Quaternion components
are preserved without normalizing them. `FTransform` and compressed animation keys
would change these values: the existing animation-sequence importer composes a
reference pose, changes coordinate space, normalizes rotations and passes through
Unreal's key storage. The sequences remain the derived assets used by the Ride
body and retargeting; exact native simulation sampling uses the typed component
tracks. There are no changes to the runtime's loop or mirror rules.

## Building and verifying

The game recipe's `unreal.skate_motion` step runs two separate NullRHI editor
processes. The first imports and saves typed packages, and deletes banks left by an
earlier, larger import. The second loads the asset named by `USkateSettings::MotionData`
through the game's own asynchronous loader and invokes `USkateMotionLibrary::VerifyMotion`:

1. Compare every original rig/reference field, metadata record, track component,
   loop transform, channel weight and expanded frame/bone sample exactly. This
   compares float bits, including signed zero, rather than accepting a tolerance.
2. Load the production resources with typed motion from a fixture containing every
   reference file except `animation/` and `metadata/`, so optional authored clips
   apply over typed frames as they do in the game.
3. Replay twelve deterministic controller cases across both stances through the
   production `GameplaySession`, comparing each published root, bone, velocity,
   state, camera, score, trick and balance value. Cases cover push, ollie, steering,
   spins, slide inputs and trick-stick inputs at 30/60 Hz transport rates.
4. Change one sample bit in memory and require the exact checker to reject it.
   Saved assets are never changed by this control.
5. Reject a cyclic rig, an empty component track and a zero metadata frame rate.
6. Require every package in the bank folder to be referenced, since the whole folder
   is cooked.

The step reruns when the reference bundle, the AtelierSkate module, the game config or
the installed engine version changes. The assets are read-only in the editor:
details-panel edits would pass floats through text, and the next import overwrites
them. `SchemaVersion` is written by the importer and defaults to 0, so assets from an
older schema are rejected rather than read as current.

No game, map, renderer or live bridge is started. The verification report lives in
the game's build output under `skate-motion/verify.json`. Replays provide a finite
behavioral regression corpus. Exhaustive source-field equality plus unchanged
native evaluation code establishes that the storage conversion preserves inputs;
it does not claim to exercise every possible game interaction.

## First migration boundaries

This first migration covers animation data. Settings, physical skeletons, action/
motion graphs, gestures and camera data still use their existing native loaders.
An empty `USkateSettings::MotionData` preserves that reference path for games that
have not migrated; a configured missing/invalid asset fails rather than silently
falling back. Asset references are cooked with the game.

The committed native bundle remains the migration input and independent reference.
Typed packages are generated under ignored Content, like the existing sequences;
rebuilding the motion step overwrites edits to these generated packages. Moving
source authoring to committed typed assets and retiring the animation reference
bundle is a separate follow-up once this conversion has been reviewed. No raw
byte array is embedded in the new motion assets. The importer currently supports
the scalar and bone-contact attribute types present throughout the reference
bundle and explicitly rejects an unsupported kind or nonzero alignment padding.
