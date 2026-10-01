# Fox hunter animation

The fox-masked hunter is a Tripo mesh, auto-rigged and given finger bones (53 bones, rig `tripo-rig-r02`), with
fifteen clips authored in code on that rig by `fox_hunter_animate.py`. The current set is `animation-r05`:
`assets/characters/fox-hunter/FoxHunter-Anim-r05.blend` and its `manifest.json`, at 30 fps. This document covers the
clips, the authoring tools and the pose language they use, and the rules learnt making them. How the hunter fights with
these clips is in [FOX_HUNTER_COMBAT.md](FOX_HUNTER_COMBAT.md).

## The clips

Distances are at game scale (the 0.918-unit body scaled to 1.70 m).

| Clip | Kind | Length | Motion |
| --- | --- | --- | --- |
| Idle | loop | 4.0 s | weight shifts twice, head scan, breathing, claws working; both feet planted |
| Creep | loop | 1.5 s | stalking walk in place at 59 cm/s, 65% stance per foot; the swing foot follows a solved 4.5 cm arc and the pelvis is lowest a quarter step after each heel strike |
| Run | loop | 0.6 s | in place at 591 cm/s, with real flight between stances |
| AttackR_A, AttackL_A | one-shot | 1.9 s | claw cocked above the shoulder, one diagonal slash across to the far hip; hit window 0.52–0.68 s; L mirrors R |
| AttackL_B, AttackR_B | one-shot | 1.9 s | low outside the hip, a rising backhand across to the far shoulder; hit window 0.50–0.63 s; R mirrors L |
| Kick | one-shot | 1.1 s | rear-leg front kick at chest height on a planted foot, a one-frame overshoot and rebound, replant, knee absorb; hit window 0.38–0.48 s |
| DashForward | one-shot | 1.6 s | crouch, dive, land in a skid, rise; 2.96 m of root travel |
| DashBackward | one-shot | 1.5 s | crouch, backward spring, land, recover; 1.66 m back |
| TurnLeft, TurnRight | one-shot | 1.3 s | 180° in two short steps pivoting on the ball of the foot, as root yaw; R mirrors L |
| Hurt | one-shot | 1.2 s | hit to the chest, head whip, one stagger step back, claw to the chest, recover; 52 cm back |
| Death | one-shot | 3.0 s | hit, knees buckle, kneel, fold onto the hands, pitch over face down, still; holds the last pose |
| Jump | one-shot | 1.4 s | crouch, push, vertical jump with split legs at the apex, staggered landing (not used in the game) |

The manifest records what the engine import reads: `hit_window_seconds` and `strike` (the striking hand or foot) for
the attacks and the kick, `root_motion`, `travel_units` and `yaw_degrees` for the dashes, Hurt and the turns,
`travel_speed_units_per_s` for the loops, and `holds_last_pose` for Death. Its `checks` block holds the per-clip
numbers: sole height, foot skate per frame, yaw steps, hand and head heights, and the self-intersection results.

House rules, also in the manifest: hanging arms have the palms toward the body; loops stay in place and record their
travel speed; the dashes, turns and Hurt carry their motion on the Root bone.

## Authoring tools

All in `games/yorimichi/assets/characters/tools/`. They read the rig and earlier revisions from the prototype archive,
under `output/imagegen/yorimichi-fox-hunter-2026-09-13/`, and write each new revision there as `<rev>/`. Point
`YORIMICHI_ARCHIVE` at a checkout of the archive (see `_archive.py`).

| Tool | What it does |
| --- | --- |
| `fox_hunter_animate.py` | poses, clips, foot solve, contact checks, export (`.blend`, `.glb` with every clip as an NLA track, a web preview, `manifest.json`) |
| `fox_hunter_clip.py`, `fox_hunter_clipcheck.py` | self-intersection check on the deformed mesh (shared code, and a standalone runner) |
| `fox_hunter_captures.py` | review captures: 12 frames per clip from three cameras, then tiled |
| `review_fox_rig.py`, `add_fox_fingers.py` | rig diagnostics and the finger bones |
| `fox_hunter_animref.py` | starting frames and prompts for H3 Max motion references ([H3_ANIMATION_REFERENCE_WORKFLOW.md](H3_ANIMATION_REFERENCE_WORKFLOW.md)) |
| `fox_hunter_pipeline.py` | the earlier stages: concept views, Tripo mesh, clean-up, rig |
| `promote.py` | copies an approved revision into `assets/characters/fox-hunter/` and updates `character.toml` |

Commands, from the repository root, for a new revision `animation-r06`:

```sh
blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/fox_hunter_animate.py -- --rev animation-r06 --no-sheets --check
blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/fox_hunter_captures.py -- --rev animation-r06 --only Idle,Run
python3 games/yorimichi/assets/characters/tools/fox_hunter_captures.py tile --rev animation-r06
blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/fox_hunter_clipcheck.py -- --rev animation-r06 --step 1
python3 games/yorimichi/assets/characters/tools/promote.py fox-hunter "$YORIMICHI_ARCHIVE/output/imagegen/yorimichi-fox-hunter-2026-09-13/animation-r06"
```

`fox_hunter_animate.py` builds every clip, exports, runs the contact checks and, with `--check`, the clipping check
(`--check-step`, default 2). `--only Idle,Run` limits the clips, `--no-export` skips the files for a fast numbers-only
run, `--dump Run` prints the foot tracks per frame, and `--no-bake` turns off the per-frame contact pass for debugging.
The captures put the floor at the soles and an orange cone on the forward axis; the three cameras are three-quarter,
side and front. The clip check at step 1 takes a few minutes. After promotion, `atelier build yorimichi
characters.fox_hunter unreal.fox_hunter` exports and imports the new set
([FOX_HUNTER_COMBAT.md](FOX_HUNTER_COMBAT.md#build-and-try-it)).

## The pose language

Poses are dictionaries from bone name to a rotation, written in the character's own frame (forward, left, up), which
turns with the Root bone. Each bone's rotation is composed on top of its parent's posed orientation, so a pitch is
always a pitch about the character's left-right axis.

- `[(axis, degrees), ...]`: rotations applied in the order listed. `legs(thigh, knee, foot, ...)` builds the three leg
  bones from pitch values (thigh negative is forward, foot negative is toes up).
- `arm_rot(side, elev, az, twist)`: the upper arm placed by direction. `elev` is degrees below horizontal (90 hanging,
  0 level, negative raised); `az` is degrees from sideways toward forward (90 forward, over 90 across the body,
  negative back). The arm starts from a canonical orientation with the elbow hinge lateral and the palm forward;
  `twist` rolls from there.
- `{'flex': d, 'roll': r}` on a forearm: elbow flexion about the real hinge, then pronation about the forearm's own
  axis (positive turns the palm toward the body on both sides). `arms(elev, az, twist, flex, roll, left=, right=)` and
  `one_arm(side, ...)` build both.
- `{'world': [...]}`: an absolute orientation in the character frame, used for planted feet.
- `hips`, `root`, `root_rot`, `root_tilt`, `hands(curl, spread, thumb, opposition)`.
- `plant(left, right, l_pitch, r_pitch)`: solves the leg (thigh aim, knee, level foot) so the ball of the foot sits on
  a target: `'hold'` (where it was at the previous key), `'ready'` (its spot in the ready stance),
  `('ready', dx, dy[, dz])`, `('world', x, y[, dz])` or `('hold', dz)`. A `dz` makes the foot hover, so a stepping foot
  rises over its landing spot and drops onto it. A pitch raises the heel with the toes flat.
- `free: True` marks airborne keys (no grounding); `nofloor: True` marks kneeling or lying keys.

Mirrored clips are reflections of their twins (sides swapped, y flipped), and the solve runs after mirroring on the
actual rig. Keyed quaternions stay in the same hemisphere per bone. After a clip is keyed, a per-frame pass pins each
planted ball of the foot in the world between keys that plant it on the same spot, and lifts the hips wherever a pinned
sole would sink.

## Rules for the next character

1. Compose in the character's frame and turn it with the root. Anything written in world axes breaks as soon as the
   root yaws or tilts.
2. Aim limbs from where the posed parent actually leaves them, never from an assumed rest direction. The rest arm on
   this rig hangs about 20° out, and the spine pitch moves it.
3. The elbow must not follow the palm. Bend on a lateral hinge and turn the palm with a separate forearm roll;
   otherwise every bent arm with the palm toward the body folds across the chest.
4. Planted feet need a solve, not a hips shift: thigh aim, knee from the law of cosines, foot levelled, ball of the
   foot on the target. Then pin between keys, because interpolation drifts. Let a stepping foot hover over its landing
   spot before it drops, or it skims the floor on the way in. A swing foot needs a solved arc: a forward-kinematic
   swing can dip under the floor and make the contact pass lift the whole body.
5. Loops that travel in place move the stance foot back at the travel speed, not on a sinusoid. Flight is a lift on
   the hips, not a leg pose.
6. A hit lands on the frame after contact with no ease-in; a hard accent can overshoot for one frame and rebound.
7. Measure before showing: sole depth, skate per frame, hit-window reach, pierced edges, hands on their own side of the
   chest. Faults that are invisible in six-frame sheets are obvious in the numbers.
8. Capture from three cameras with the floor at the soles. A side camera alone cannot tell behind from beside.
9. Ask reviewers for changes in the pose language, so the fixes are mechanical.

## Known gaps

- Creep and Run graze one arm against the other in a few frames: at most 33 pierced edges, under 0.5 mm deep in model
  units (the manifest's `checks`).
- The Jump clip is not used in the game.
