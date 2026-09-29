# Fox hunter: the enemy animation set, how it was built and what we learned

> Moved from the prototype repository on 29 September 2026. Paths are translated to this repository where the file moved; paths still starting with `japan/` or `output/imagegen/` refer to the prototype archive (authoring tools, earlier revisions, review images). See [docs/MIGRATION.md](../../../docs/MIGRATION.md).

Written 14 September 2026. Companion to [TRIPO_P2_ASSET_WORKFLOW.md](TRIPO_P2_ASSET_WORKFLOW.md) (how the
character was made) and [H3_ANIMATION_REFERENCE_WORKFLOW.md](H3_ANIMATION_REFERENCE_WORKFLOW.md) (how the
motion references were generated). Everything lives under
`output/imagegen/yorimichi-fox-hunter-2026-09-13/`, referred to below as the asset folder.

## What exists

The fox-masked hunter is Yorimichi's first enemy: a Tripo mesh, auto-rigged and given finger bones (53 bones,
`tripo-rig-r02`), with fifteen clips authored on that rig. Revision r04 is the current set, reviewed by Henry on
the Fox Hunter Build page ("Looks really cool"). It is ready for engine import.

| Clip | Kind | Length | Notes |
| --- | --- | --- | --- |
| Idle | loop | 4.0 s | weight shift twice, head scan, breathing, claws working; both feet planted |
| Creep | loop | 1.5 s | stalking walk in place, 0.32 body heights per second, 65 percent stance per foot |
| Run | loop | 0.6 s | in place, 3.2 body heights per second, real flight between stances |
| AttackR_A, AttackL_A | one-shot | 1.9 s | claw cocked above the shoulder, one diagonal slash across to the far hip; L is the mirror |
| AttackL_B, AttackR_B | one-shot | 1.9 s | low outside the hip, rising backhand across to the far shoulder; R is the mirror |
| Kick | one-shot | 1.1 s | rear-leg front kick at chest height on a planted foot, replant, knee absorb |
| DashForward | one-shot | 1.6 s | crouch, dive, land in a skid, rise; 1.6 body heights of root travel |
| DashBackward | one-shot | 1.5 s | crouch, backward spring, land, recover; 0.9 body heights of root travel |
| TurnLeft, TurnRight | one-shot | 1.3 s | 180 in two short steps pivoting on the ball of the foot, root yaw; R is the mirror |
| Hurt | one-shot | 1.2 s | hit to the chest, head whip, one stagger step back, claw to the chest, recover; root travel |
| Death | one-shot | 3.0 s | hit, knees buckle, kneel, fold onto the hands, pitch over the knees face down, still |
| Jump | one-shot | 1.4 s | crouch, push, vertical jump with split legs at the apex, staggered landing |

Hit windows, root travel, loop speeds and per-clip numeric checks are in `animation-r04/manifest.json`; the
clipping numbers are in `animation-r04/clipcheck.json`. Both are what the engine import should read.

## Files and tools

| What | Where |
| --- | --- |
| Authoring script (poses, clips, solve, export) | `games/yorimichi/assets/characters/tools/fox_hunter_animate.py` |
| Self-intersection check on the deformed mesh | `games/yorimichi/assets/characters/tools/fox_hunter_clip.py` (shared code), `games/yorimichi/assets/characters/tools/fox_hunter_clipcheck.py` (standalone) |
| Review captures, three cameras, tiles | `games/yorimichi/assets/characters/tools/fox_hunter_captures.py` |
| Rig diagnostics and finger bones | `games/yorimichi/assets/characters/tools/review_fox_rig.py`, `games/yorimichi/assets/characters/tools/add_fox_fingers.py` |
| Motion references (H3 Max) | `games/yorimichi/assets/characters/tools/fox_hunter_animref.py`, asset folder `animref/` |
| Outputs per revision | asset folder `animation-r01` to `animation-r04`: `.blend`, `.glb` (all clips as NLA tracks), `preview/` (JSON glTF for the web page), `captures/` tiles, `manifest.json` |
| Reviewer reports | `animation-r01/reviews/*.json`, `animation-r02/reviews/*.json` (prompt in `animation-r02/reviews/PROMPT.md`) |
| Review page source | asset folder `review-page/` (the published artifact page and its update script) |

Commands, from the repo root:

```bash
blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/fox_hunter_animate.py -- --rev animation-r05 --no-sheets --check
```

builds every clip, exports the GLB and the web preview, runs the contact checks, and with `--check` the
clipping check too. `--only Idle,Run` limits the clips, `--no-export` skips the files for a fast numbers-only
run, `--dump Run` prints foot tracks per frame, `--no-bake` disables the per-frame contact pass for debugging.

```bash
blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/fox_hunter_captures.py -- --rev animation-r05 --only Idle,Run
python3 games/yorimichi/assets/characters/tools/fox_hunter_captures.py tile --rev animation-r05
blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/fox_hunter_clipcheck.py -- --rev animation-r05 --step 1
```

Captures render 12 frames per clip from three cameras (three-quarter, side, front) with the floor at the soles
and an orange cone marking forward; running the three clip groups as parallel Blender processes takes about
ten minutes. The clip check at step 1 takes a few minutes and writes `clipcheck.json`.

## The pose language

Poses are dictionaries of bone name to a rotation, written in the character's own frame (forward, left, up),
which turns with the Root bone. Every bone's rotation is composed on top of its parent's posed orientation, so
a pitch is always a pitch about the character's left-right axis.

- `[(axis, degrees), ...]`: rotations applied first-listed-first; `legs(thigh, knee, foot, ...)` builds the
  three leg bones from pitch values (thigh negative = forward, foot negative = toes up).
- `arm_rot(side, elev, az, twist)`: upper arm placed by direction. `elev` is degrees below horizontal
  (90 hanging, 0 level, negative raised), `az` is degrees from sideways toward forward (90 forward, over 90
  across the body, negative back). The arm is put on a canonical orientation where the elbow hinge is lateral
  and the palm faces forward; `twist` rolls from there.
- `{'flex': d, 'roll': r}` on a forearm: elbow flexion about the real hinge, then forearm pronation about its
  own axis (positive turns the palm toward the body on both sides). `arms(elev, az, twist, flex, roll, left=,
  right=)` and `one_arm(side, ...)` build both.
- `{'world': [...]}`: absolute orientation in the character frame, used for planted feet.
- `hips`, `root`, `root_rot`, `root_tilt`, `hands(curl, spread, thumb, opposition)`.
- `plant(left, right, l_pitch, r_pitch)`: solve that leg (thigh aim, knee, level foot) so the ball of the foot
  sits on a target: `'hold'` (where it was at the previous key), `'ready'` (its spot in the ready stance),
  `('ready', dx, dy[, dz])`, `('world', x, y[, dz])`, `('hold', dz)`. A `dz` makes the foot hover, used so a
  stepping foot rises over its landing spot and drops onto it. A pitch raises the heel with flat toes.
- `free: True` marks airborne keys (no grounding); `nofloor: True` marks kneeling or lying keys.

Mirrored clips are reflections of their twins (sides swapped, y flipped); the solve runs after mirroring on the
actual rig. Keyed quaternions are kept in the same hemisphere per bone. After a clip is keyed, a per-frame pass
pins each planted ball of the foot in the world between keys that plant it on the same spot, and lifts the hips
wherever a pinned sole would sink.

## How review worked

Each revision was captured to tiles and reviewed before Henry saw it. For r01 and r02 that meant fifteen
independent Opus reviewers, one per clip, each reading the tiles, the reference video sheet, the manifest and
the authoring code, allowed to measure in headless Blender, writing a JSON report (verdict, findings with
expected, observed and a concrete change in the pose language, regressions, what to keep). The r02 prompt is
kept next to the reports. The reports drove the r02 and r03 rebuilds; r04 came from Henry's own pass.

What each round found, in short:

- r01: forward swings reversed once the arm went above the shoulder; forearm rotation was a twist about its
  own axis so no elbow bent; child bones were composed in the rest frame; a 172 degree one-frame pop in the
  right turn; mirrored clips kept the sign of their metadata; the capture floor sat 3 cm high.
- r02: direction and structure fixed everywhere. Still: feet skating and floating in every stepping clip,
  turns ending with the arms overhead (poses composed in world axes), the arm helper aiming from an assumed
  rest direction, attack hit windows opening after the strike, no flight in the run, dash travel not linear,
  the defeat sinking then climbing.
- r03 (Henry): clipping in every clip: forearms crossing in creep and run, hands into thighs in the attacks
  and the kick, arms into the body in the dashes, hands in the defeat, arms in the jump.

## Lessons that carry to the next character

1. Compose in the character's frame and turn it with the root. Anything written in world axes breaks the
   moment the root yaws or tilts.
2. Aim limbs from where the posed parent actually leaves them, never from an assumed rest direction. The
   rest arm on this rig hangs about twenty degrees and the spine pitch moves it.
3. The elbow must not follow the palm. Bend on a lateral hinge, turn the palm with a separate forearm roll.
   With the palm turned toward the body and the elbow following it, every bent arm folds across the chest.
4. Planted feet need a solve, not a hips shift: thigh aim, knee from the law of cosines, foot levelled, ball
   of the foot on the target. Then pin between keys, because interpolation drifts. Let a stepping foot hover
   over its landing spot before it drops, or it skims the floor on the way in.
5. Loops that travel in place should move the stance foot at the travel speed (ankle target sliding back),
   not by a sinusoid; flight is a lift on the hips, not a leg pose.
6. Measure before showing: sole depth, skate per frame, hit-window reach, pierced edges, hands on their own
   side of the chest. Every fault above was invisible in six-frame sheets and obvious in the numbers.
7. Three cameras with the floor at the soles. The side camera alone cannot tell behind from beside.
8. Independent reviewers with a numeric brief and Blender access find things a single pass does not; two
   rounds cost about 4.5 million tokens and were worth it. Their reports must ask for changes in the pose
   language so the fixes are mechanical.

## Engine import

Done on 16 September 2026: `games/yorimichi/assets/characters/fox-hunter/export_unreal.py` and
`games/yorimichi/unreal/Scripts/import_fox_hunter.py` bring the r04 set into `/Game/FoxHunter`, and the hunter
fights the player in the game. See [FOX_HUNTER_COMBAT.md](FOX_HUNTER_COMBAT.md). The paragraph below is the
plan as it was written before the import.

### The plan before the import

Bring `animation-r04/FoxHunter-Anim-r04.glb` into the Unreal project as the enemy's skeletal mesh and animation
set. From the manifest: `hit_window_seconds` per attack and kick (attach the hit volume to the striking hand or
foot for that window), `root_motion` and `travel_units` for the dashes, hurt and turns, `yaw_degrees` for the
turns, `travel_speed_units_per_s` for the loops, `holds_last_pose` for the defeat. Check the clips at game
distance in the level before the next enemy is started; the same tools apply to it unchanged.
