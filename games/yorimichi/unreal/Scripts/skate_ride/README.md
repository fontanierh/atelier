# Ride clips

The native skating animation (`unreal/Content/Data/SkateNative/animation` and `metadata`) as ordinary Unreal assets,
keyed frame for frame and measured against the native decode. The build step `unreal.skate_clips` makes them; the
Ride runtime reads the manifest.

```sh
uv run atelier build yorimichi unreal.skate_clips      # import (4 editor runs) and verify (2 editor runs)
uv run atelier build yorimichi skate.ride_stills       # stills of four clips from the verified poses
SKATE_RIDE_LIMIT=20 uv run atelier build yorimichi unreal.skate_clips   # a quick subset (manifest says partial)
```

| File | What it does |
| --- | --- |
| `native.py` | Standard-library decoder of the rig, the clips and the metadata (a word-for-word port of the C++ readers), the additive composition and the conversion to Unreal space. Tested by `tests/test_skate_ride_native.py`, including agreement with the C++ reader. |
| `rider_mesh.py` | A box body and board skinned to the native rig in RIG_TPOSE, written as a GLB. |
| `import_clips.py` | Editor script: the rider, the compression settings, the mirror table, one sequence per clip and the manifest. Batched by `SKATE_RIDE_BATCH=i/n`; resumable. |
| `verify_clips.py` | Editor script: samples every clip's compressed data at every frame and compares every bone with the native pose. Batched by `SKATE_RIDE_VERIFY_BATCH=i/n`. |
| `render_stills.py` | Draws the rider in the verified poses with the native joints on top. |

## Assets

- `/Game/SkateRide/SKEL_SkateRider`, `SK_SkateRider`: the 36 native bones, same names and parents, `TRAJECTORY` at
  the root; reference pose RIG_TPOSE. The board is part of the rig: `SKATEBOARD_ROOT` (child of `TRAJECTORY`),
  `TRUCK_FRONT`, `TRUCK_BACK` and the four wheels; the clips animate it (flips spin `SKATEBOARD_ROOT`). The four
  `*_REPARENTED` bones are the hand and toe targets parented to the board.
- `/Game/SkateRide/Clips/B<bank>/<CLIP>`: one `UAnimSequence` per native clip (3,324: 2,672 in bank 0, 652 in bank 1),
  one key per native frame at the clip's own rate (30 or 60 fps; length = (frames - 1) / fps).
- `/Game/SkateRide/MDT_SkateRider`: the native mirror partners, mirror axis Y.
- `/Game/SkateRide/ACL_SkateRideExact`, `CC_SkateRideExact`: ACL Safe bone compression (full-precision rotations,
  translations and scales held to 0.00001 cm) and lossless curve compression.
- `unreal/Content/Data/SkateRide/clips.json`: the manifest (below).

## What the keys are

The native clips are deltas on the reference pose: the runtime's BindPose tree adds every clip onto RIG_TPOSE
(`AddAnimationPose`, motion first: scale `ref.s * s`, rotation `ref.q * q`, translation `ref.q(t) + ref.t`). Their
translations are zero apart from the hips, the board root and the reparented targets, so the bone lengths come from
RIG_TPOSE. Each key is that sum, the native local pose (`native.local_pose`), with the sample's rotation normalised as
the native sampler does and the sum normalised, converted to Unreal space:

    translation (x, y, z) m  -> (z, -x, y) * 100 cm
    rotation    (x, y, z, w) -> (-z, x, -y, w)
    scale       (x, y, z)    -> (z, x, y)

No posture pose (`POSTURE_STIFF`, `_SLOUCH`, `_BUFF_POSE`) and no `BOARD_BACKWARDS` layer is baked in; the native
runtime adds those only when asked, and a Ride runtime that wants them layers them the same way.

The native evaluator builds its matrices from the un-normalised sum, whose norm is the RIG_TPOSE rotation's (it
differs from 1 by up to 0.4%, for example on `SPINE` and `RIGHTSHOULDER`). Its joints therefore sit up to 1.2 cm from
the rigid pose (hands and toes, measured over every sixth frame of every clip). An Unreal transform holds a rotation,
not a skewed matrix, so the keys are the rigid pose; compare with the native evaluator's joints within that margin.

## Root motion

`TRAJECTORY` is the root and carries the clip's travel. Root motion is on with the root locked to zero: like the native
runtime, which never composes the trajectory into its children, the body and the board stay where the clip puts them
relative to the actor while the trajectory's frame-to-frame change moves the actor. RIG_TPOSE's trajectory is the
identity, so the keyed trajectory is the clip's own.

- At rest the trajectory sits about 8.9 cm up (`motion.first.translation_cm`), and the board root's local position is
  near zero, so with the root locked the deck is at the actor origin and the wheels are below it; RIG_TPOSE puts the
  board root 8.9 cm above the trajectory. Each clip's `motion.board_root_first_cm` and `hips_first_cm` give the
  first-frame positions relative to the root.
- Looping clips (`looping`) wrap with the native loop transform (`motion.loop_translation_cm`, `loop_rotation`). The
  native wrap (`AnimationTrajectoryDelta`) adds the loop transform at the wrap; Unreal's looping root motion uses
  last minus first instead. `loop_vs_travel_cm` says how far apart the two are; where it is not zero, a runtime that
  needs the native wrap applies the loop transform itself.

## Events and channel weights

- Each metadata attribute becomes a float curve named after it (`PUSH_CONTACT`, `MIRRORED`, ...), constant-interpolated:
  a whole-clip attribute holds its value; a windowed one holds its value from `begin` to `end` and 0 outside (an
  instant gets one frame). The manifest's `events` has the exact native windows (normalised and in seconds and
  frames), the payload value and, for kind 3, the raw words.
- `channel_weights` per clip: the 36 per-bone ChannelBlend coefficients (0 masks a bone; larger values speed its blend
  in), with `animated` (the native `channel_animation` flag) and whether they are uniform. They are data for the
  runtime's blending, not baked into the keys.

## Mirroring

`MDT_SkateRider` pairs the left and right bones and maps the centre bones (the root, spine, head and
`SKATEBOARD_ROOT`) onto themselves, mirror axis Y in Unreal (the native x axis). Unreal leaves a bone without a row
unmirrored, so without those rows a mirrored pose keeps the authored hips and spine under swapped limbs. The trucks
and wheels have no row, as in the native rig. The native mirror modes differ: mode 1 also turns the root and its
children 180 degrees about up. The manifest's `mirror` per clip says whether the clip carries `MIRRORED` or `SWITCH`
attributes.

## Manifest

`clips.json` holds the rig (bone names, parents, mirror partners, board bones, the reference pose in Unreal space and
its import error), the compression settings and, per clip: `asset`, `bank`, `fps`, `frames`, `duration`, `looping`,
`phase_controlled`, `base_speed`, `motion`, `channel_weights`, `snap_guarded_keys`, `events`, `curves` and `mirror`.

## Verification

`build/yorimichi/skate-ride/clips-verify.json` compares, for every clip, frame and bone, the pose Unreal samples from
the compressed asset (`AnimPoseExtensions`, compressed evaluation with retargeting on so the compressed path is taken)
with `native.local_pose` in Unreal space. It reports the largest translation (cm), rotation (rad, as
4 atan2(|a - b|, |a + b|), which stays exact at small angles in single precision) and scale errors overall and per
clip, the curve errors at every frame, and a control: the same clip under the engine's default compression, which
must show an error, proving the measurement reads compressed data. The limits are 0.01 cm and 1e-4 rad.

### Euler key storage

UE 5's animation sequence data model keeps bone keys as single-precision Euler angles: the controller converts each
key with `FQuat4f::Euler` and evaluation rebuilds the quaternion. When a bone's local pitch is within 0.081 degrees of
+-90 degrees, `Rotator` snaps it to exactly +-90 and the roll to 0, so the sequence holds a rotation up to about 2e-3
rad from the key; compression adds nothing on top. `native.euler_stored` reproduces that round trip, and over the whole
library it predicts 38 such bone frames in 35 clips, all on leaf bones (the hands and three reparented targets), so no
joint position moves; at the hand's 10 cm the mesh moves less than 0.02 cm. The verification counts each of them in
`euler_storage` when the sampled rotation matches `euler_stored` within 2e-5 rad, and measures it by that distance.
Avoiding them would need other bone frames than the native ones.

### Reference snap

Unreal samples a sequence's data model (as compression does) by running its FK control rig, which writes each bone's
local transform through `URigHierarchy::SetTransform`. That skips a transform `FRigComputedTransform::Equals` the
bone's current one, within 1e-4 per component, and the current one is the reference pose. A key that close to the
reference but not on it comes back as the reference: 19 clips had toe frames up to 2.83e-4 rad off this way (the
toes rest near their reference rotation), with every larger error in the library predicted to 2e-6 rad by that rule.
The import gives such a key (`native.snap_guard`) a 0.0003 cm X offset, which the equality test sees, so the rotation
is kept; 2079 bone frames in 44 clips (`snap_guarded_keys` per clip in the manifest).

`build/yorimichi/skate-ride/clip-stills/` has six frames each of an ollie, a kickflip, a push and a 50-50 grind: the
rider drawn from Unreal's sampled poses, with the native joints as blue rings.
