# game-r17: skateboarding rider clips (regular and goofy)

28 September 2026. `Cairo-Game-r17.blend` is `game-r16` plus 54 actions named `<Role> · skate`, built by
`japan/tools/warm_skate_clips.py` for the native skate system (contract: `japan/docs/SKATE.md`, "Rider clips"). Every
game-r16 action is unchanged (curve signatures asserted before saving). Not reviewed by the user yet.

- **Frame.** The rig faces +X, left +Y, up +Z; the Root bone stays put and the rider frame's origin is its head on the
  ground (the standing sole level). The board lies across the rider at its rest place in every clip: nose toward +Y for
  regular (toward -Y for the `Goofy` copies), toe edge toward +X, deck top 9.05 cm. Armature units x 148 = cm (measured).
  In the exported mesh's component space the Root head is at [6.991, -1.408, 0.65] cm and the deck top centre at [6.991, -1.408, 9.7] cm (UE axes):
  the mesh attaches to the board frame so the Root head sits on the board's ground point.
- **Feet.** Each foot is placed by the centre (or the ball) of its shoe footprint on a deck spot with its angle to the
  board, aligned to the deck surface (concave, kicks); the deformed shoe (its heel is skinned partly to the shin) is then
  pushed to touch the grip without going through it. Riding stance: front foot centre (+16, +1), 55 deg from the board
  axis; back foot (-21, +1), 80 deg (deck-local cm).
- **Contacts.** `skate-build.json` lists, per clip and limb (foot_L, foot_R, hand_L, hand_R), the [t0, t1] seconds on
  the board (sole within 0.5 cm of the deck; hands holding), the push plant/release and planted position, the measured
  stance spots and every check below. The manifest roles carry the same contacts.
- **Goofy.** Each clip is solved again on the real rig with the stance mirrored (right foot forward, nose toward -Y),
  not copied: the Tripo rig is not symmetric.
- **Review.** Sheets (behind the board = the game camera, toe side, above) in `../skate-r01/review/`, pose references
  (GPT Image 2.5 Sunburst) in `../skate-r01/references/`. For SkateOllie/SkateNollie/SkateManual/SkateNoseManual and the
  flip the sheets move the board as the game will and move the feet with it (two-bone legs), as the game's IK will.

| Clip | Length | Kind | Feet on the board (regular) | Hands | Notes |
| --- | --- | --- | --- | --- | --- |
| SkateStance | 2.00 s | loop | L 0.00-2.00; R 0.00-2.00 | - | riding stance, soft knees, weight centred, head to the nose, slow breathing sway |
| SkateStanceFakie | 2.00 s | loop | L 0.00-2.00; R 0.00-2.00 | - | riding stance looking back over the back shoulder toward the tail |
| SkatePush | 1.00 s | loop | L 0.00-1.00; R 0.00-0.02, 0.90-1.00; ground R 0.30-0.62 | - | front foot swivels on its ball to point along the board, body turns forward, back foot plants beside the front truck, strokes back 44 cm, returns to the tail |
| SkateCrouch | 0.20 s | hold last frame | L 0.00-0.20; R 0.00-0.20 | - | ollie load: deep crouch, back foot ball on the tail, front foot behind the front bolts |
| SkateNollieCrouch | 0.20 s | hold last frame | L 0.00-0.20; R 0.00-0.20 | - | nollie load: front foot ball on the nose, back foot behind the back bolts |
| SkateOllie | 0.45 s | one-shot | L 0.00-0.45; R 0.00-0.45 | - | pop, front foot drags up the grip, knees up; ends in SkateAir |
| SkateNollie | 0.45 s | one-shot | L 0.00-0.45; R 0.00-0.45 | - | nollie pop from the nose; ends in SkateAir |
| SkateAir | 1.00 s | loop | L 0.00-1.00; R 0.00-1.00 | - | air tuck, knees up, feet on the deck, arms out |
| SkateFlip | 0.45 s | one-shot | L 0.00-0.02, 0.37-0.45; R 0.00-0.02, 0.37-0.45 | - | flick: both feet leave the deck, 15 cm up at 0.2 s, catch at 0.38 s |
| SkateLand | 0.35 s | one-shot | L 0.00-0.35; R 0.00-0.35 | - | touchdown from SkateAir: absorb, rise to the stance |
| SkateBrake | 0.40 s | hold last frame | L 0.00-0.40; R 0.00-0.00; ground R 0.33-0.40 | - | foot brake: back foot leaves the tail and drags its sole flat on the ground beside the tail, weight on the front leg |
| SkateManual | 1.00 s | loop | L 0.00-1.00; R 0.00-1.00 | - | manual: hips over the back foot, arms out, balancing (the game tilts the board nose-up 11 deg) |
| SkateNoseManual | 1.00 s | loop | L 0.00-1.00; R 0.00-1.00 | - | nose manual: hips over the front foot, arms out, balancing (the game tilts the board nose-down 11 deg) |
| SkateGrind | 1.00 s | loop | L 0.00-1.00; R 0.00-1.00 | - | 50-50: crouched over the trucks, arms wide, looking down the line |
| SkateGrindTail | 1.00 s | loop | L 0.00-1.00; R 0.00-1.00 | - | 5-0 / smith / feeble: weight over the back truck |
| SkateGrindNose | 1.00 s | loop | L 0.00-1.00; R 0.00-1.00 | - | nosegrind / crooked: weight over the front truck |
| SkateSlide | 1.00 s | loop | L 0.00-1.00; R 0.00-1.00 | - | boardslide family: lower, arms wide, square to +X and looking along the rail |
| SkateGrabIndy | 0.50 s | one-shot | L 0.00-0.50; R 0.00-0.50 | R 0.17-0.50 | indy: back hand grabs the toe edge between the feet |
| SkateGrabMelon | 0.50 s | one-shot | L 0.00-0.50; R 0.00-0.50 | L 0.17-0.50 | melon: front hand reaches behind the front leg to the heel edge |
| SkateGrabNose | 0.50 s | one-shot | L 0.00-0.50; R 0.00-0.50 | L 0.17-0.50 | nose grab: front hand to the nose |
| SkateGrabTail | 0.50 s | one-shot | L 0.00-0.50; R 0.00-0.50 | R 0.17-0.50 | tail grab: back hand to the tail |
| SkateGrabMethod | 0.50 s | one-shot | L 0.00-0.50; R 0.00-0.50 | L 0.17-0.50 | method: front hand on the heel edge, knees bent back, chest up |
| SkateGrabStalefish | 0.50 s | one-shot | L 0.00-0.50; R 0.00-0.50 | R 0.17-0.50 | stalefish: back hand behind the back leg to the heel edge |
| SkateGrabDouble | 0.50 s | one-shot | L 0.00-0.50; R 0.00-0.50 | L 0.17-0.50; R 0.17-0.50 | double: indy with the back hand and melon with the front hand |
| SkatePowerslide | 0.60 s | hold last frame | L 0.00-0.60; R 0.00-0.60 | - | powerslide: square to the travel (+X), weight back toward the heel edge, knees bent, arms forward |
| SkateCarveToe | 0.50 s | hold last frame | L 0.00-0.50; R 0.00-0.50 | - | toe-side carve: knees and hips toward the toe edge |
| SkateCarveHeel | 0.50 s | hold last frame | L 0.00-0.50; R 0.00-0.50 | - | heel-side carve: sitting back toward the heel edge |

## Checks (all 54 actions)

- Sole on its deck spot: worst 0.00 cm; sole below the deck surface: worst 0.00 cm; below the ground: 0.00 cm.
- Knees: flexion 32-151 deg, always bending toward the knee pole (at least 8.1 cm in front of the hip-ankle line):
  no hyperextension.
- Loops close exactly (first frame = last frame).
- Grab hands on their edge: worst 0.89 cm. The arms are short for a board at its rest place, so a grabbing hand
  that cannot reach lowers the pelvis up to 8 cm and the clavicle drops and comes forward.
- Mesh clipping (edges of one body part through faces of another, on the deformed outfit, hands and head, every 2nd
  frame). In the grabs the sleeves lie against the baggy trousers: the deepest measured overlap is 1.2 cm (Rlower>torso). Outside the grabs: SkatePush, SkatePushGoofy (the swinging leg brushes the other trouser leg, at most 0.1 cm).

## Deviations from SKATE.md

- SkatePush: the pushing foot plants its ball at (+18, +26) deck-local (26 cm toward the toe side, beside the front
  truck: nearer and the shoe's heel, skinned to the shin, swings over the deck edge) and slides back 44 cm to (-26, +26):
  plant 0.30 s, release 0.62 s as specified. The front foot pivots on its ball from 55 to 14 deg off the board axis.
- SkateLand: the absorb bottoms out 21 cm below the stance at 0.12 s (the air tuck is already 18 cm down, so 15-20 cm would
  not be an absorb).
- Grabs: while holding, the pelvis sits 26-35 cm below the stance (SkateAir: 18) because the hands (38-40 cm arms) must reach
  the deck edge with the board at its rest place; knees splay to let the arm pass. Method and stalefish cannot bring the
  board up behind with a board fixed under the feet: the method is the melon grab with the chest up and the back arm high.
- Foot spots per clip (deck-local x): manual back foot -24, front +15; nose manual front +21, back -15; grinds over the
  trucks +18 / -19; brake foot on the ground at (-25, +27); everything else uses the stance spots, the ollie load spots or
  the nollie load spots of the contract.
- Board profile assumed for the checks and the proxy: concave z += 0.9 (y / 10.25)^2, kicks z += 4.5 u^2 over the last
  13 cm, rounded ends. The board mesh should match it or the sole checks shift by up to a few millimetres.

## Rebuild and export

```sh
blender -b --threads 4 --python-exit-code 1 --python japan/tools/warm_skate_clips.py -- --parent game-r16 --revision game-r17
blender -b --threads 4 --python-exit-code 1 --python japan/tools/warm_skate_review.py -- --blend output/imagegen/yorimichi-yellow-boy-2026-09-12/game-r17/WarmOriginal-Game-r17.blend
blender -b --python japan/tools/export_warm_original_unreal.py -- --revision game-r17 --clips <every Skate* role> --clips-only --report export-skate.json
```

## Known weaknesses

- The shoe heels are skinned about half to the shin, so they lift or sink with the ankle angle; in deep crouches the
  heel of the shoe rises off the grip (the forefoot carries the contact).
- Deep grabs open the trousers' crotch (dark inside visible from the toe side, not from the game camera) and press the
  sleeves against the trousers.
- The push stroke keeps the support knee bent about 100 deg: the deck is 9 cm high and the legs are 60 cm.
- Reviewed by numbers and renders only; not yet seen in the game with the real board transform and IK.
