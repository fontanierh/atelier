# Typed motion assets

`USkateMotionData` is the native simulation's animation source. It references bounded
`USkateMotionBank` assets, each containing at most 128 clips. The adapter resolves
Unreal objects on the game thread, copies their fields into the existing immutable
native animation structures, and passes those values to the simulation worker.
The simulation, interpolation, graph evaluation and retargeting arithmetic are unchanged.
The initial asset load and field copy are synchronous on the game thread during
the existing session preload. Startup hitch and cooked-package behavior still
need a separate runtime check; offline replay equality does not measure them.

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
processes. The first imports and saves typed packages. The second reloads those
packages from disk and invokes `USkateMotionLibrary::VerifyMotion`:

1. Compare every original rig/reference field, metadata record, track component,
   loop transform, channel weight and expanded frame/bone sample exactly. This
   compares float bits, including signed zero, rather than accepting a tolerance.
2. Load the production resources with typed motion from a fixture containing only
   the non-animation native files. No motion `.skate` file exists in that fixture.
3. Replay twelve deterministic controller cases across both stances through the
   production `GameplaySession`, comparing each published root, bone, velocity,
   state, camera, score, trick and balance value. Cases cover push, ollie, steering,
   spins, slide inputs and trick-stick inputs at 30/60 Hz transport rates.
4. Change one sample bit in memory and require the exact checker to reject it.
   Saved assets are never changed by this control.
5. Reject a cyclic rig, an empty component track and a zero metadata frame rate.

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
