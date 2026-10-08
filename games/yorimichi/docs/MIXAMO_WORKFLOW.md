# Mixamo to Cairo: the sword combo workflow

Cairo's sword fighting (three chained strikes, a charge, a parry) comes from one motion-capture clip in Adobe's free
[Mixamo](https://www.mixamo.com/) library: **Great Sword Combo Slash**. Blender scripts move that capture onto Cairo's
own skeleton, fix what his proportions break (a big head, short arms, a two-handed grip), cut it into game clips, take
out the capture's spin and speed it up. The raw Mixamo download is not in this repository; everything made from it is.
This guide is the route from a Mixamo download to clips in the game, and the recipe for the next move.

<table><tr>
<td width="40%"><img src="../../../docs/media/character/06-mixamo-combo.gif" alt="Cairo performing the retargeted Mixamo great-sword combo, spinning through three cuts"></td>
<td width="60%"><img src="../../../docs/media/character/06-despun.jpg" alt="The first strike after the de-spin: guard, raise, cut, contact, follow-through"><br><sub>Left: the capture on Cairo after the retarget and head clearance (3.5 s; it spins a full turn). Above: the first game strike cut from it, de-spun and sped up (0.57 s, recovery included).</sub></td>
</tr></table>

## Capture or video

A capture carries real body mechanics (weight shift, hip drive, a follow-through) that a frame-by-frame reconstruction
of an AI video cannot recover: rebuilt from an H3 Max video, a sword swing comes out with elbows bent backward. Use a
capture when a library has a good match.

Video references are the right tool when no library has a match, or when the move should look like *this* character
rather than an adult stuntman: the dodge roll is authored from an H3 Max reference, the sprint and the dive roll from
Seedance ([H3 workflow](../../../docs/H3_ANIMATION_REFERENCE_WORKFLOW.md)). In both routes the game clip is authored in Blender on
Cairo's rig, and a human reviews it in motion.

## The chain at a glance

| Step | Tool (in `games/yorimichi/assets/characters/tools/`) | Result |
| --- | --- | --- |
| 0. A sword in the hand | `cairo_sword_grip.py` (grip solver) | `hold-r14`: the right-hand grip and the bokken |
| 1. Download | mixamo.com | `great-sword-combo-slash.fbx` (212 frames, 60 fps), kept locally |
| 2. Retarget | `cairo_mixamo_test.py` | `mixamo-r01`: the combo on Cairo, both hands on the grip |
| 3. Head clearance | `cairo_mixamo_clearance.py`, checked by `cairo_mixamo_clearance_check.py` | `mixamo-r02`: the overhead cuts miss the hair |
| 4. Review | `cairo_mixamo_review.py` | videos, contact sheets and a GLB for the browser |
| 5. A combat set | `cairo_sword_combat_build.py`, `cairo_sword_combat_check.py`, `cairo_sword_combat_review.py` | `game-r13`: guard, strikes, charge, parry cut from the combo |
| 6. Facing, feet, speed | `cairo_sword_combat_r02.py` | `game-r15`: strikes that end facing the target, 1.6–2× faster |
| 7. The sword in every move | `cairo_sword_locomotion.py` | `game-r16`: walk, sprint, jumps, roll with the sword in hand |
| 8. Into the game | `atelier build yorimichi characters.cairo unreal.cairo` | the `A_Sword*` clips, `SM_Bokken`, root motion, aim data |

The revision folders of steps 0 to 7 are in the prototype archive (see
[Revisions and reproducing](#revisions-and-reproducing)); the current character, `Cairo-Game-r18.blend`, carries all of
their clips and is in this repository.

## 1. Download a source

1. Sign in to [Mixamo](https://www.mixamo.com/) with an Adobe ID. Mixamo is free, and Adobe's
   [FAQ](https://helpx.adobe.com/creative-cloud/faq/mixamo-faq.html) allows royalty-free use of its animations in
   games. No API key is needed.
2. Pick one of Mixamo's own characters with full fingers, search the animations (`sword`), and watch the whole clip at
   real speed, recovery included. The combo is the card **Great Sword Slash** (description *Great Sword Combo Slash*),
   full trim, Mirror off, Overdrive **50**, Character Arm-Space **50**.
3. Download with these settings:

| Field | Setting | Why |
| --- | --- | --- |
| Format | FBX Binary | keeps the source skeleton, its rest pose and every key |
| Skin | With Skin | lets you render the source for comparison (keep those renders local) |
| Frames per second | 60 | the authoring rate |
| Keyframe reduction | None | keep the capture as it is |

4. Save it as `build/yorimichi/mixamo-sword-test/source/great-sword-combo-slash.fbx` (ignored by git) and record the
   title, controls, date and SHA-256. Mixamo keeps no history of downloads, so the hash is the source's identity:

```text
183b1451a518b3a738688f72f4ff94792f5a25abc4995e21e4d60b95daa32a13  great-sword-combo-slash.fbx
212 frames, 1–212 at 60 fps (3.52 s)
```

Download Mixamo's mannequin motion and retarget it here, rather than uploading Cairo to Mixamo, so his rig, finger
bones, skin weights and outfit stay exactly as they are.

## 2. Retarget onto Cairo

`cairo_mixamo_test.py --source <fbx> --out <dir>` opens `hold-r14` (Cairo with the approved grip), imports the FBX next
to him and writes `WarmOriginal-Mixamo-Slash.blend` plus `retarget.json`. Both skeletons use Mixamo's bone names
(`mixamorig:Hips`, ...), which is why the humanoid [bone contract](../../../platform/conventions/rigs/humanoid.toml)
keeps them: 52 bones map one to one, and Cairo's extra `Root` stays put. Same names are not enough:

- **Align the bodies, not the axes.** Each skeleton gets an anatomical frame (left from the shoulders, up from hips to
  neck). Each bone's *world* rotation change from its rest pose is carried across through that alignment, then
  converted back through Cairo's own parent and rest transforms. Copying local rotations between bones of the same
  name fails because the two rigs' rest poses and bone rolls differ.
- **Rotations only.** Cairo keeps his bone lengths; only hip travel is copied, scaled by the ratio of hip heights
  (0.39: the mannequin is an adult, Cairo is four heads tall). Timing is untouched.
- **Palms separately.** Hands get their own frame from the wrist, index and pinky knuckles; with names alone the palms
  turn the wrong way.
- **The sword stays in the right hand** at the approved `hold-r14` socket, with its finger wrap. Blender parents to the
  bone's tail, so the script offsets by the hand's length to keep the socket where it was approved.
- **The left hand is re-solved onto the grip every frame**: a two-bone arm solve toward a fixed left-grip socket that
  keeps the *captured* elbow direction, clamped to his reach. An elbow direction taken from the sword twists the arm
  backward. The lower grip is lengthened by 72 mm so two small hands fit.
- **Clean keys.** Quaternions keep one hemisphere from frame to frame, keys are linear, and the result is saved and
  reopened before anything is measured.

## 3. Clear the head

Mixamo's mannequin has an adult head; Cairo's is much bigger, so the three overhead cuts go through his hair.
`cairo_mixamo_clearance.py` adds a correction layer to the six arm bones only (upper arm, forearm, hand, both sides):
during each overhead phase the blade tilts up by 28–64° and the wrist moves 2.5–4 cm away from the head, eased in
before the moment of contact and out after it, with the captured elbow side kept and the support hand re-solved. The
body, legs and timing do not change.

`cairo_mixamo_clearance_check.py` reopens the saved file and samples it at 240 Hz (845 samples, in-between poses
included) against the evaluated head mesh. On the accepted `mixamo-r02`:

| Check | Result |
| --- | --- |
| blade or whole sword against head and hair | 0 overlapping samples (also with a 4 mm margin) |
| closest blade point to the head | 12.4 mm |
| support grip drift added by the correction | 0.8 mm at most |
| bones outside the six arm bones | unchanged (0 difference) |

It fails the run if the sword touches the head, other bones change, or the grip drifts more than 4 mm. These are
sampled checks, not a proof of continuous collision. Known gap: the left wrist leaves the grip by up to 31 mm in the
final recovery; the retarget already does, and the correction does not change it.

## 4. Review

`cairo_mixamo_review.py target --out <dir>` renders Cairo from front, back, side and three-quarter views; `source`
renders the Mixamo mannequin for side-by-side comparison (keep those local: they show Adobe's character); `export`
writes a GLB with textures for the browser review. Look at the skinned mesh, not only the bones: shoulders, elbows,
wrists, the grip, blade against hair and clothes, planted feet, and the entry and recovery, first slowed down, then
again at real speed.

## 5. Cut it into a combat set

`cairo_sword_combat_build.py` builds the gameplay clips from the accepted combo on the game body, measured by phase
(strikes at frames 29–65, 81–115 and 127–165, wind-up 137, rising cover 163–177, a hold 177–191): `SwordIdle` (the
guard from frame 5, with breathing), `SwordAttack1-3`, `SwordChargeUp/Hold/Release`, `SwordParry` (the rising cover),
`SwordParryHit` (an authored recoil) and `SwordCombo` (the whole capture, for reference).

- **Root motion.** The capture's hip travel and turn move onto the `Root` bone, smoothed; the hips keep the rest. In
  Unreal the strike then moves and turns the character exactly as the capture does.
- **Only the links are authored**: short recoveries back to the guard (the support hand re-solved on every frame, feet
  clamped to the guard's floor height), breathing on the holds, the parry recoil.
- **Fingers** go through the rig's curl properties (`thumb_curl`, `index_curl`, ...), fitted to the approved wrap by
  least squares, because the library's finger bones are driven by those properties and ignore keyed rotations.

`cairo_sword_combat_check.py` samples every clip at 240 Hz for blade against head, clothes and the free arm, fists
against the head, grip error, joint flips, the garment against the floor and loop seams, and confirms the rest of the
library is untouched. `cairo_sword_combat_review.py sheets|videos|export` makes the contact sheets, videos and a GLB.

## 6. Take out the spin, speed it up, aim it

The combo is a spinning great-sword routine: 130–224° of body turn per strike, a full turn overall, so every captured
strike ends facing away from the enemy, and it plays slowly. `cairo_sword_combat_r02.py` rebuilds the strikes:

- **Facing.** Each strike keeps only a fraction `k` of its captured turn (0.28–0.35: enough to drive the hips into the
  cut), and the recovery turns to where the cut landed.
- **Feet.** Turning less than the capture makes planted feet pivot and slide. Feet that are planted in the capture are
  pinned where they land in the less-turned world, the change is blended through the steps between, and each leg is
  re-solved keeping its knee direction.
- **Speed.** Each strike is re-timed by a smooth monotone curve through phase keys: wind-ups about 2× faster, cuts
  1.6–1.8×, shorter recoveries. A strike with its recovery lasts 0.52–0.60 s (31–36 frames at 60 fps).
- **Aim.** Per strike, the build records where the blade meets a target (70 % of the way along the blade, where it
  crosses the character's heading): `contact_yaw_degrees` and `contact_distance` in
  [combat-build.json](../assets/characters/cairo/combat-build.json). The game uses them to turn and step in so the cut
  lands.

## 7. Keep the sword in every move

With the sword out, every other clip keeps its own arm movement with the fist closed on the grip; the blade only turns
where it would hit something (the rule for every armed clip). `cairo_sword_locomotion.py` makes the armed copies
(`SwordWalk`, `SwordSprint`, `Sword<Jump/Roll/...>`) from the unarmed clips, changing only the right arm and the grip,
and records its measurements in [locomotion-build.json](../assets/characters/cairo/locomotion-build.json). Design rules
and numbers: the "Armed animation" section of [SWORD_COMBAT.md](SWORD_COMBAT.md#armed-animation).

## 8. Into Unreal

```sh
uv run atelier build yorimichi characters.cairo unreal.cairo   # export from Blender, import into Unreal
uv run atelier play yorimichi --profile swordqa                # a scripted duel checks every sword mechanic
```

The export ([export_unreal.py](../assets/characters/cairo/export_unreal.py) `--sword`) writes the clips and the bokken;
[import_cairo_sword.py](../unreal/Scripts/import_cairo_sword.py) makes the `A_Sword*` clips, `SM_Bokken` and the sword
fields of `DA_Cairo`. What the game side needs to get right:

- **Root motion** is on for the sword clips only (`enable_root_motion`, root locked at the reference pose), and the anim
  instance takes root motion from everything.
- **The root bone's scale.** The FBX root carries the armature scale times 100 (148), so root-motion travel arrives 148×
  too large; `WandererSword.cpp` sets the translation scale to 1/148.
- **The sword attachment** is computed in the importer: the sword's exported rest transform times the inverse of
  `hand_R`'s reference pose. It matches Blender to 6 µm.
- **Aim**: `ContactYaw` and `ContactDistance` on each `FWandererSwordClip` come from `combat-build.json`.

Gameplay (controls, chain windows, charge, parry, hits) is in [SWORD_COMBAT.md](SWORD_COMBAT.md); effects and sound in
[COMBAT_FEEDBACK.md](COMBAT_FEEDBACK.md).

## Revisions and reproducing

The authoring tools read and write revision folders in the prototype archive, under
`$YORIMICHI_ARCHIVE/output/imagegen/yorimichi-yellow-boy-2026-09-12/`: `sword-r01/stage1-bokken/hold-r14`,
`.../mixamo-r01` and `.../mixamo-r02`, then `game-r12` to `game-r16`. Point `YORIMICHI_ARCHIVE` at a checkout of the
archive ([tools README](../assets/characters/tools/README.md)). Steps 2 and 3 need only `hold-r14` from it and your own
download:

```sh
export YORIMICHI_ARCHIVE=<prototype archive checkout>
MIXAMO_SOURCE=build/yorimichi/mixamo-sword-test/source/great-sword-combo-slash.fbx
WORK=build/yorimichi/mixamo-sword-test/check
TOOLS=games/yorimichi/assets/characters/tools
shasum -a 256 "$MIXAMO_SOURCE"                     # compare with the hash above

blender -b --python-exit-code 1 --python $TOOLS/cairo_mixamo_test.py -- --source "$MIXAMO_SOURCE" --out $WORK/r01
blender -b --python-exit-code 1 --python $TOOLS/cairo_mixamo_clearance.py -- \
  --source $WORK/r01/WarmOriginal-Mixamo-Slash.blend --out $WORK/r02
blender -b --python-exit-code 1 --python $TOOLS/cairo_mixamo_clearance_check.py -- \
  --baseline $WORK/r01/WarmOriginal-Mixamo-Slash.blend --out $WORK/r02
blender -b --python-exit-code 1 --python $TOOLS/cairo_mixamo_review.py -- target --out $WORK/r02
```

The three Blender steps take about 20 seconds; their `clearance-checks.json` and `clearance-fit.json` match the
accepted `mixamo-r02` exactly. `cairo_sword_combat_build.py` builds `game-r13` on `game-r12`; `cairo_sword_combat_r02.py`
and `cairo_sword_locomotion.py` take their parent and output with `--parent` and `--revision`. Write to a new revision,
review it, then promote it into this repository with `promote.py`.

## Adding another Mixamo move

These scripts are a tested recipe for this two-handed sword combo, not a general retarget command: the frame range,
the grip, the clearance envelopes and the phase frames are specific to it. For the next move:

1. Download and record it as in step 1; render the source first and use its real frame range.
2. Copy the retarget with a new action name and output revision, targeting the current game body. For an unarmed move,
   drop the sword, the finger wrap and the support-hand solve. For a one-handed attack, keep the captured free arm.
3. Look at palms, shoulders, elbows and sleeves before adding any IK; keep the captured timing and mechanics.
4. Measure head, clothes and weapon collisions and correct them with a small layer eased in before contact, as in
   step 3. Retune the envelopes; they fit only this combo.
5. Cut game clips by measured phases, put travel on the root, and decide how much of the capture's turn to keep.
6. Check the saved file independently, review from several views at real speed, then promote without replacing the
   existing clips.

## Pitfalls

- **Blender action slots (4.4 and later).** Assigning an action whose slot name differs from the armature's last slot
  leaves no slot assigned: the character silently plays the rest pose, which shows up as a fake idle and a wrong
  export scale. Create new actions with the library's slot name.
- **Finger props, not finger bones.** Keying finger rotations does nothing on a rig whose fingers are driven by
  properties.
- **`Matrix.translation` is a live view.** Copy it (`.copy()`) before changing the matrix, or a solver measures
  against a target it just moved.
- **Blender's `--python` does not put the script's folder on the import path.** The tools add it themselves.
- **Unreal root motion is 148× too large** without the root-scale fix above.
- **Tripo's packed textures are JPEG bytes**: write them as `.jpg`, or Unreal imports them grey.
