# Mixamo → Yellow Boy: download, retarget and review

> Moved from the prototype repository on 29 September 2026. Paths are translated to this repository where the file moved; paths still starting with `japan/` or `output/imagegen/` refer to the prototype archive (authoring tools, earlier revisions, review images). See [docs/MIGRATION.md](../../../docs/MIGRATION.md).

> The workflow below is current. Its status lines date from 16 September 2026; the combat set it produced is in the game as game-r13/r14 ([SWORD_COMBAT.md](SWORD_COMBAT.md), [PLAN.md](../PLAN.md)).

Updated 16 September 2026. This is the workflow behind the accepted
[sword combo in Asset Studio](<tailnet address>).
Use captured skeletal motion, transfer it onto our existing rig, then adapt
weapon contact and clearance for our proportions.

The accepted result is `sword-r01/stage1-bokken/mixamo-r02`, not the rejected
reconstruction under `rebuild-*`. It is a review asset; the sword combo has not
yet been installed as a gameplay attack. The current unarmed character and its
complete gameplay library are in `game-r12`.

The combat set built from that combo (guard, draw, three-strike chain, parry, charge) is
`game-r13` / `combat-r01`; its gameplay, controls, pipeline and limits are in
[SWORD_COMBAT.md](SWORD_COMBAT.md). The original brief is the
[Claude sword animation handoff](CLAUDE_SWORD_ANIMATIONS_HANDOFF.md).

## 1. Download a useful source

1. Open [Mixamo](https://www.mixamo.com/) and sign in with an Adobe ID. No OpenAI,
   Tripo or video-generation key is needed. Adobe documents free access without
   a Creative Cloud subscription and royalty-free use in games in its
   [Mixamo FAQ](https://helpx.adobe.com/creative-cloud/faq/mixamo-faq.html), checked
   on the date above.
2. Select a rigged Mixamo library humanoid with complete hands/fingers. Search
   Animations for `sword`, then choose the intended one-hand/two-hand mechanics.
   Inspect the whole clip at normal speed, including recovery. A good preview on
   an adult mannequin still needs adaptation for our large head and short arms.
3. For our exact example, the catalog card was **Great Sword Slash**, with the
   description **Great Sword Combo Slash**. Use full trim, Mirror off,
   Overdrive **50**, and Character Arm-Space **50**. Record different controls
   on another motion. Keep captured travel for the initial comparison; choose
   in-place versus root-driven movement deliberately at game integration.
4. Click **Download** and use the settings below. These are our tested project
   settings, not a claim that Adobe prescribes them for every project.

| Download field | Setting | Reason |
| --- | --- | --- |
| Format | FBX Binary (`.fbx`) | Retains source skeleton, bind transforms and keys. |
| Skin | With Skin | Allows direct source mannequin renders and contact inspection. |
| Frames per Second | 60 | Matches our authoring timeline. |
| Keyframe Reduction | None | Preserve the capture before optimization. |

5. Keep the original download in `build/yorimichi/mixamo-sword-test/source/`. That
   directory is ignored by Git and excluded from Asset Studio's catalog and
   file server. The example file is `great-sword-combo-slash.fbx`. Preserve it
   unchanged; keep rendered comparisons and provenance with the processed revision.
6. Record animation title, selected source character, URL, date, all controls,
   download settings, frame rate/range, and SHA-256. Mixamo only retains the last
   selected character, not a durable history of every download; Adobe recommends
   keeping rigged characters locally. [Adobe FAQ](https://helpx.adobe.com/creative-cloud/faq/mixamo-faq.html)

The original example's source-character display name was not recorded. Its exact
FBX hash is the source identifier; a fresh download on another mannequin is a
new input and should be revalidated:

```text
183b1451a518b3a738688f72f4ff94792f5a25abc4995e21e4d60b95daa32a13
212 frames, frames 1–212 at 60 fps, 3.516667 seconds between first and last keys
```

Our route downloads mannequin motion and retargets locally, preserving the
existing Tripo/finger rig, skin weights, body swap and sockets. Uploading a
rigged FBX is an alternative Adobe supports through automatic skeleton mapping,
but was not the tested route here. See
[Adobe's upload/mapping guide](https://helpx.adobe.com/creative-cloud/help/mixamo-rigging-animation.html).

## 2. Which files to use

Asset paths below are under `output/imagegen/yorimichi-yellow-boy-2026-09-12/`.

| File or directory | Purpose |
| --- | --- |
| `game-r12/WarmOriginal-Game-r12.blend` | Current full character/library, with frontflip waistband correction. Start here for new unarmed motions. |
| `sword-r01/stage1-bokken/hold-r14/WarmOriginal-SwordHold-r14.blend` | Fixed input for reproducing the sword test: approved dominant-hand grip and sword. |
| `sword-r01/stage1-bokken/mixamo-r01/` | Original retarget, source/target videos and provenance. High swings still clip the hair. |
| `sword-r01/stage1-bokken/mixamo-r02/` | Accepted combo with head clearance: native blend, GLB/textures, video and saved-animation checks. |
| `animation-review-r01/` | Current character's full library; references the sword as a separate model. |
| `game-r13/`, `combat-r01/` | The combat clip set on the current body and its Studio/validation package (`SWORD_COMBAT.md`). |

The current hero and sword test have matching 53-bone names, hierarchy and bind
matrices (`animation-review-r01/validation.json`). Matching skeletons allow
animation transfer, but do not make outfit revisions identical or prove
clearance on a different mesh. Validate the current body before promotion.

## 3. Reproduce the accepted sword pipeline

Requirements: Blender **5.2.1** (tested version), its bundled Python/NumPy and
FBX/glTF support, plus `ffmpeg` on PATH for optional videos. Node/npm are only
needed to run Asset Studio. On this Mac, Blender is also at
`/opt/homebrew/bin/blender`.

Run from the repository root. These commands write to an ignored scratch folder
and preserve the approved `mixamo-r01`/`mixamo-r02` deliverables:

```sh
MIXAMO_SOURCE="$PWD/build/yorimichi/mixamo-sword-test/source/great-sword-combo-slash.fbx"
MIXAMO_WORK="$PWD/build/yorimichi/mixamo-sword-test/guide-check"
test -f "$MIXAMO_SOURCE" || { echo "Download the source FBX first"; exit 1; }
shasum -a 256 "$MIXAMO_SOURCE"
mkdir -p "$MIXAMO_WORK"

# Transfer source motion and fit the support hand.
blender -b --threads 4 --python-exit-code 1 \
  --python games/yorimichi/assets/characters/tools/warm_mixamo_test.py -- \
  --source "$MIXAMO_SOURCE" --out "$MIXAMO_WORK/r01"

# Apply corrections authored for THIS combo's three overhead swings.
blender -b --threads 4 --python-exit-code 1 \
  --python japan/tools/warm_mixamo_clearance.py -- \
  --source "$MIXAMO_WORK/r01/WarmOriginal-Mixamo-Slash.blend" \
  --out "$MIXAMO_WORK/r02"

# Independently evaluate the saved corrected result at 240 Hz.
blender -b --threads 4 --python-exit-code 1 \
  --python japan/tools/warm_mixamo_clearance_check.py -- \
  --out "$MIXAMO_WORK/r02"

# Export web/slash.glb + external texture images.
blender -b --threads 4 --python-exit-code 1 \
  --python games/yorimichi/assets/characters/tools/warm_mixamo_review.py -- export \
  --out "$MIXAMO_WORK/r02"
```

The retarget tool also rewrites the ignored diagnostic
`build/yorimichi/mixamo-sword-test/working.blend`, which contains the source mannequin.
The delivered character blend removes imported source objects and retains only
the new sword action. **Do not replace the full gameplay-library blend with
this single-action output.**

The clearance checker compares against the **committed** `mixamo-r01` baseline
and assumes frames 1–212. It is for this exact combo, not an arbitrary motion.
The initial support-contact report had a bug; use the saved-animation checker,
not the old `retarget.json` grip figures.

Optional renders, using the same variables:

```sh
# Source rendering uses the fixed local FBX filename above.
blender -b --threads 4 --python-exit-code 1 \
  --python games/yorimichi/assets/characters/tools/warm_mixamo_review.py -- source --out "$MIXAMO_WORK/r01"
blender -b --threads 4 --python-exit-code 1 \
  --python games/yorimichi/assets/characters/tools/warm_mixamo_review.py -- target --out "$MIXAMO_WORK/r01"
blender -b --threads 4 --python-exit-code 1 \
  --python games/yorimichi/assets/characters/tools/warm_mixamo_review.py -- target --out "$MIXAMO_WORK/r02"
```

Review videos are 30 fps; the native/exported animation remains 60 fps. Scratch
outputs are excluded from the server. For browser review of a new candidate,
put its processed character blend, GLB and **all sibling texture images** in a
fresh revision under `output/imagegen/…`, then click **Rescan project assets**.
A new `--out` directory does not create the bespoke historical `review.html`;
the shared Asset Studio is the standard viewer now.

## 4. How the retarget works

Implementation: [warm_mixamo_test.py](../tools/warm_mixamo_test.py).

1. **Read bind transforms before editing bones.** Import with
   `automatic_bone_orientation=False`. Validate required `mixamorig:` names; our
   extra `Root` stays on the target. Preserve the target armature and lengths.
2. **Align anatomy, not guessed axes.** `anatomical_frame()` measures lateral
   direction from shoulders and up from hips to neck. Transfer world-space
   rotation changes relative to source rest, then resolve through target
   parent/rest transforms. Copying local Euler/quaternion values between matching
   names is insufficient when rest axes or bone roll differ.
3. **Scale travel, not the skeleton.** Scale hip displacement by the ratio of
   target/source hip-to-toe rest heights, then rotate through the anatomical
   alignment. Keep timing. The measured ratio here is about 0.3905; recompute it
   for another source character. Source travel and future game movement are
   separate decisions.
4. **Align palms separately.** `hand_frame()` uses wrist, index-knuckle and
   pinky-knuckle landmarks. Matching hand names alone gave incorrectly oriented
   hands in our first transfer.
5. **Preserve the dominant-hand attachment.** Keep the approved right-hand sword
   socket and finger wrap. Blender bone parenting is relative to the bone tail;
   the script compensates to preserve the socket's head-space transform.
6. **Fit the second hand anatomically.** `fit_support_hand()` uses a two-bone
   solve with the captured elbow bend plane, clamped to actual reach. A
   sword-derived elbow pole caused the earlier twisted/backward arm. This
   recipe extends the lower handle by 72 mm and uses a fixed left-grip socket;
   those choices are specific to this weapon and character.
7. **Bake stable keys.** Use quaternion hemisphere continuity
   (`dot(previous, current) >= 0`), linear interpolation, original timing and
   only necessary translation tracks. Save/reload before measuring the result.

## 5. Add another Mixamo animation

These scripts are a tested **two-handed sword recipe**, not a universal retarget
CLI. `--source`/`--out` do not change weapon assumptions, action names or the
clearance envelopes. For the next motion:

1. Create a new source filename and provenance record; render the source first.
   Use its actual frame range/FPS, not this example's 212-frame constant.
2. Create a new recipe using the transform/hand-frame helpers above. Target a
   copy of current `game-r12` (or a weapon-equipped copy built on that body), use
   a new action name/output revision, and preserve the existing action library.
3. For unarmed motion, omit the sword extension, fixed finger wrap and support-
   hand solve. For one-handed attacks, preserve the captured free arm. For
   two-handed motion, define grip sockets and when contact engages/releases.
4. Check palms, shoulders, elbows and sleeves before extra IK. Preserve captured
   timing and body mechanics. Full source skeletal motion is available; there
   is no need to reconstruct it from 2D video landmarks.
5. Measure head, clothing and weapon collisions. Blend in proportion corrections
   before contact while keeping targets reachable. The three envelopes in
   `warm_mixamo_clearance.py` only fit this combo; retune for a different motion.
6. Adapt the checker to the new baseline, duration and contact phases. Export a
   candidate for visual review before promotion; keep prior revisions.

## 6. Review and acceptance

In Asset Studio, inspect the actual new clip from front, back, side and three-
quarter views. Use slow playback, frame stepping, rig/skin-weight display and
hands/head close-ups. Loop/speed are sticky; speed multiplies the role's authored
rate. Compare matching source/target phases, then watch again at real speed.

Check the visible skinned mesh, not only joint endpoints:

- shoulder roll, elbow direction, continuous wrists and grip contact;
- blade, guard and handle against hair/skin, body, free arm and clothing;
- planted feet, pelvis/root travel, entry and recovery;
- interpolated poses and linear skinning in the exported viewer;
- unchanged unrelated bones/clips when applying local corrections.

The accepted correction edits six arm/forearm/hand rotations. Its
[saved-animation report](../../output/imagegen/yorimichi-yellow-boy-2026-09-12/sword-r01/stage1-bokken/mixamo-r02/clearance-checks.json)
checks **845 samples at 240 Hz**, with zero blade/head or whole-sword/head overlap
samples and unchanged body/leg/root transforms. The 4 mm BVH margin passes too.
These are sampled checks, not continuous whole-body collision guarantees.

Remaining limits: the support wrist separates by up to **31.4 mm** in final
recovery; the correction adds less than **0.815 mm** to baseline grip error. The
tassel is static, precise foot planting needs polish, and combat transitions,
hit windows and game integration remain separate work. Details are in the
[accepted revision notes](../../output/imagegen/yorimichi-yellow-boy-2026-09-12/sword-r01/stage1-bokken/mixamo-r02/README.md).

Measurement lesson: `Matrix.translation` returns a wrapped vector. Use
`goal = wanted.translation.copy()` before subsequently changing that matrix.
The initial solver's residual looked perfect because it mutated its own target.
Always remeasure the saved action independently.

## 7. Promote and commit

Add accepted actions to the current library/role manifest without replacing
existing clips. Use [export_warm_original_unreal.py](../tools/export_warm_original_unreal.py)
and the game animation import path for new clips. The `reimport_warm_mesh.py`
shortcut is **geometry-only**, not an animation installer. Decide root-motion
policy, transitions, input/recovery, hit detection, notifies and sound in the
game; a browser scenario does not implement those systems.

Commit the recipe, provenance/settings, processed character native/export,
textures, review captures and validation reports. Keep original mannequin
downloads and diagnostic working scenes in the ignored local source area, and
credentials out of Git. Stage explicit paths to keep unrelated parallel work
separate; commit and push at completed task boundaries.

The delivered native files, exports/textures, retarget/clearance tools, reports
and Asset Studio are committed. A fresh clone can view the processed result;
reproducing from capture requires the local source FBX described in section 1.

## Reproduction check

On 16 September, the source hash was verified and retarget → clearance →
saved-pose validation → GLB export was rerun in the ignored scratch directory.
The 845-sample clearance report exactly matches the approved revision, and the
export contains the corrected combo and resolves all texture files. This run
also fixed the clearance tool's report-writing failure with relative source
paths. Accepted native/export assets were not overwritten.

The commit audit found no missing deliverable files. Individual PNG render
frames under the two Mixamo `captures/` folders remain intentionally ignored;
the rendered contact sheets and review videos are tracked. Original downloads,
working scenes and API credentials remain local.
