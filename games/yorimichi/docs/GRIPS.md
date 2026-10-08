# Grips

A held prop looks held only if the hand sits on it the same way in every clip. The procedural finger wrap
(`FingerWrapNode.h`) closes fingers round a handle's shape, but it starts from wherever the clip left the hand, so the
grip drifts from clip to clip. The grip poser lets a person pose each grip once, by hand, on the real prop. The game
then holds that pose exactly in every clip: the hand's place and turn on the prop, and every finger joint.

For Modori it covers four grips:
- the sword hand (`sword_R`);
- the off hand in the two-handed guard (`sword_L`);
- both hands on the paraglider's bar (`glider_R`, `glider_L`).

Measured in game over 49 shots of every sword and glide clip, each hand stays within 0.0 mm and 0.003 degrees of its
place on the prop.

## The pipeline

Everything lives in `games/yorimichi/assets/characters/grips/` and writes under `build/yorimichi/grips/<character>/`.
Modori's posed grips are committed in `grips/modori/`, every file the poser made:
- `poses.json`, the saves the game uses, and `poses/`, every save in order, with its edit log;
- `snapshots/`, the page's views of each grip at each save;
- `moments.json`, the scenes the grips were posed in, and `samples/surface28.jsonl.gz`, the game samples they came from
  (gzipped to fit GitHub's file limit; `moments.py` reads it as it is);
- `body.glb` and `body.json`, his posing body;
- `grips.json`, what the game reads.

The build's `characters.modori_grips` step runs `game.py --source games/yorimichi/assets/characters/grips/modori`, so a
fresh clone or package gets the game's file from them; `tests/test_grips.py` checks it rebuilds the committed
`grips.json` exactly. Without the file, Modori logs a warning and his hands keep the clips' grips. To pose further, copy
the folder to `build/yorimichi/grips/modori/`, run `serve.py`, then copy `poses.json`, `poses/` and the new `grips.json`
back. The props' meshes
(`LinkSword.glb`, `LinkGlider.glb`) are not in it: `moments.py` and `serve.py` read them from the BOTW library
([botw/README.md](../assets/characters/botw/README.md)).

A save records the visitor's Tailscale login in `by`, which the committed copy replaces with `operator`. Scrub it the
same way before committing new saves.

| Step | Command | Output |
|---|---|---|
| 1. Body | `blender -b --python export.py -- --character modori` | `body.glb`: the skinned body and the game's skeleton |
| 2. Samples | `sample.py PORT OUT.jsonl SECONDS` beside a running game (two-handed guard, glide) | the hands' skin and joints, the props' vertices |
| 3. Scenes | `moments.py --character modori --samples OUT.jsonl` | `moments.json`: each handle's frame, the prop placed in it, every sampled moment |
| 4. Pose | `serve.py --character modori --port 8897 [--allowed-user LOGIN]` | the poser page; every save in `poses/`, the newest as `poses.json` |
| 5. Game data | `game.py --character modori [--source DIR]` | `unreal/Content/Data/<character>/grips.json` (ignored) |
| 6. Check | `sample.py PORT ROWS.jsonl SECONDS --held`, then `check.py ROWS.jsonl` | the drift and miss of every grip |

Run the Python steps with `uv run python` from the repository root, and steps 1–3 once per character.

`serve.py` listens on loopback only. To publish it on the tailnet, use
`tailscale serve --bg --set-path /grips http://127.0.0.1:8897`. With `--allowed-user`, only that Tailscale login (or a
loopback visitor) gets in. A posed grip reaches the game only through step 5, and the game reads it at startup
(`ModoriCharacter.cpp` passes it to `UBotwMoveSet::Initialize`). After posing, run `game.py` and restart the game; no
compile is needed.

## How the game holds a posed grip

- **The carrying hand is not moved; the prop is placed on it.** The sword hand keeps its clip, and the sword is attached
  to it at the inverse of the posed hand-on-sword transform, at the sword's own scale (`ReadGrips` sets `S->Held`). Only
  its fingers are posed.
- **The other hands are pinned.** `FGripPoseNode` moves each pinned hand onto its posed place, using a two-bone IK in
  the plane the arm already bends in. The hand takes the posed turn, and each finger joint takes its posed rotation on
  its parent.
  - The off hand on the sword is pinned in the sword hand's bone space, so it follows the sword through every swing.
  - The glider hands are pinned in component space, because the move set places the glider on the body.
- **The grip node is the last component-space node** before `ToLocal`. Anything evaluated after it would move a hand off
  its prop.
- **Weights blend each grip in and out:** `SwordHold` (sword hand), `TwoHandGrip` (off hand) and `GlideHands`
  (glider). A grip is exact once its weight reaches 1.

## What we learned

**Frames.**
- The poser works in glTF's frame (Y up, metres), the game in Unreal's (Z up, centimetres). A point maps as
  `(x, y, z) → (x, z, y) × 100`. This is a reflection `G`, not a rotation. A turn `R` in glTF's frame is `G R G` in the
  game's, so convert the matrix and then take its quaternion. Swapping a quaternion's components does not work.
- The prop meshes (`LinkSword.glb`, `LinkGlider.glb`) map into their Unreal mesh frames the same way.
- Bone frames differ too. A glTF node's rotation is not an Unreal bone's: the game's component rotation for a bone is
  the posed turn times that bone's reference-pose rotation. A finger's local rotation is the parent's reference rotation
  inverted, times the posed rotation, times its own reference rotation. `game.py` writes turns in the first form, and
  `ReadGrips` converts them.

**Where the posed hand is.**
- The poser's authoritative placement is the moment's hand times the person's offset (`holdOf` in `app.js`). A save
  also caches a derived world placement, and that cache can be stale: `glider_R`'s was in an older frame. `game.py`
  recomputes the placement from the anchor and offset.
- `game.py`'s placements were checked against the live page's own export (read with Playwright, saves blocked) and
  agree to a hundredth of a millimetre. Check any change to the conversion the same way.

**Holding it exactly, every clip.**
- **One-tick lag.** The animation proxy's `PreUpdate` runs in the mesh's tick, before the actor's `Tick` that advances
  the move set and places the glider. The hands were therefore posed on the previous tick's glider: 3–5 mm off while
  it banked. `UBotwMoveSet::PlaceGliderForPose` now puts the glider on as the animation reads the grips, so both use
  the same placement. The move set still places it directly on the first frame of a glide, or when no animation reads
  it.
  - The diagnosis: films run two game ticks per film frame. Comparing the hand with the glider interpolated halfway to
    the previous film frame took the error to 0.0 mm. A lag of a whole film frame did not fit.
- **Reach.** In some banks and while braking, the bar was up to 3 cm beyond the straight arm overhead, so the hand fell
  short. Moving the glider would break the posed grip, and stretching bones looks wrong. Instead the collar bone turns
  toward the goal (`FGripPoseNode::Reach`) by no more than the arm needs, and never more than 35 degrees. In the films
  this reads as a natural overhead reach, and the miss is now 0.
- **Measure the animation's weight, not the move set's.** While a grip blends in, the move set's weight can be a tick
  ahead of the one the animation evaluated with. Measuring by it counted a 60 % frame as held (a false 46 mm error).
  The grip report's `pose.weight` is the one to trust.

**Checking.**
- Measure the hand in the prop's own frame, not by eye. `check.py` reports, per grip:
  - the hand's distance from its posed place;
  - each bone's spread on the prop across every sample (0 when the grip is the same in every clip);
  - the hand's turn spread;
  - the node's largest IK miss.
- Film every grip from several angles and in every kind of clip: still, running, combo, charged, dash, jump, guard
  strafing, the glider opening, banking both ways and braking. Lag and reach errors appear only in some of them.
- Cameras under the glider see the sleeve, not the hand. The front, side and behind views show the grip.

## Files

- `grips/export.py`, `moments.py`, `serve.py`, `web/`: the poser.
- `grips/game.py`: poses to `grips.json`.
- `grips/modori/`: Modori's posed grips (see above).
- `grips/sample.py`: in-game sampling (scenes, or `--held` for checks).
- `grips/check.py`: the per-grip drift report.
- `GripPoseNode.h`: the animation node.
- `BotwMoveSetCombat.cpp`: `ReadGrips`, `GripPose`, `PlaceGliderForPose`.
- `BotwMoveSetTraversal.cpp`: the glider's placement on the body.
- `WandererAnimInstance.cpp`: the node's place in the graph and its inputs.
