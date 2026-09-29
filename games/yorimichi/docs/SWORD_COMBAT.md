# Sword combat: the game-r13 set and its gameplay

> Moved from the prototype repository on 29 September 2026. Paths are translated to this repository where the file moved; paths still starting with `japan/` or `output/imagegen/` refer to the prototype archive (authoring tools, earlier revisions, review images). See [docs/MIGRATION.md](../../../docs/MIGRATION.md).

## Update 24 September 2026: combat-r02 (game-r15)

The clips are rebuilt without the capture's spin and play faster. Strikes last 0.50–0.58 s where they used
to take 0.77–0.93 s, and they end facing the target instead of 120–224° away
([game-r15/README.md](../../output/imagegen/yorimichi-yellow-boy-2026-09-12/game-r15/README.md)).

Gameplay changes that come with them:
- **Aiming.** Each strike aims and steps in with its own measured contact point (`ContactYaw`,
  `ContactDistance` on `FWandererSwordClip`, written by `import_cairo_sword.py`). This replaces the hard-coded
  offsets.
- **Soft lock.** The lock also takes the training post.
- **Charging.** Holding attack now cuts first, then winds up the charge from the follow-through. The cut is too
  fast to charge before it lands, and it counts as its own strike. A parry or the menu still cancels a charge
  safely.
- **Hit-stop.** It applies to every hit and freezes both fighters (`AJapanCombatFX`). It no longer works by
  pausing the clip's play rate.

Effects, sound and the filmed fight are in [COMBAT_FEEDBACK.md](COMBAT_FEEDBACK.md). `-swordqa` passes all 37
checks and `-foxqa` all of its checks on game-r15. The harness timeline moved with the new clip lengths.

The rest of this document describes the game-r13 set as installed on 16 September. Its "Known limits" about
the 130° turn and the slow recoveries no longer apply.

Originally written 16 September 2026. This installs a playable sword set for Yellow Boy built only from the
accepted Mixamo combo. Assets are under `output/imagegen/yorimichi-yellow-boy-2026-09-12/`; the
rejected video reconstruction (`rebuild-*`, `anim-r0*`) is not used anywhere.

Review links (workstation awake, Tailscale for the phone):

- Studio, local: `http://127.0.0.1:8794/?asset=yellow-boy-combat`
- Studio, phone or desktop on Tailscale: `<tailnet address>
- Scenarios tab presets: `sword-chain`, `sword-charge-early`, `sword-charge-full`, `sword-charge-cancel`,
  `sword-parry`, `sword-draw-run`. The untouched combo stays at `?asset=yellow-boy-sword`.
- Contact sheets and validation: `combat-r01/captures/`, `combat-r01/combat-validation.json`.

## What is in the set

`game-r13/README.md` lists the twelve clips with source frames and windows. In short: a breathing
guard, draw/sheathe from the library idle, three captured strikes with recoveries, a charge (raise,
breathing hold, captured release), a parry from the captured rising cover with a recoil, and the whole
combo as a reference clip. Facing and hip travel of captured phases live on the root bone; the game
plays them as root motion, so a strike turns and advances the capsule exactly as the capture did.

## Controls

| Action | Keyboard / mouse | Controller |
| --- | --- | --- |
| Attack (tap) / charge (hold) | Left mouse button | Right trigger |
| Parry | Right mouse button | Left trigger |
| Draw / sheathe | R | D-pad Left |

Existing bindings are untouched: jump, roll, dash and interact stay on the face buttons, L3 sprints,
R3 crouches, shoulders keep the airship speed. Both triggers and D-pad Left were free on every pad.
The HUD's second line shows the sword hints and a weapon-state line (state, charge percentage, last
event, dummy counters) whenever the sword set is installed and the player is on foot.

## Behaviour

- **Draw.** Attacking while the sword is put away draws it first; the attack press is buffered and
  fires when the draw ends (0.45 s). The bokken is visible from the first draw frame at the hip (there
  is no scabbard); sheathing hides it on the last frame.
- **Quick attack and chain.** A tap starts `SwordAttack1` at once, facing the stick direction or the
  camera forward if the character was facing away. Contact is swept from 0.27 s. A press inside the
  last 0.3 s before a clip's link window (0.47 s on strikes 1 and 2) chains to the next strike; the
  chain ends after strike 3. Movement input after the cancel time returns control to locomotion.
- **Charge.** Holding the button through the wind-up (0.22 s, before the cut lands) turns the strike
  into `SwordChargeUp`, then the breathing hold loops for as long as the button is held. Release plays
  `SwordChargeRelease`: early releases at 1.0×; after 0.9 s in the hold the release is a full charge at
  1.05× with a 90 ms hit-stop on contact and a 0.8× settle. Parry, roll, dash, jump, opening the menu
  or losing the button (menu focus) cancel the charge back to guard without a strike.
- **Parry.** `SwordParry` is active between 0.08 s and 0.33 s. A strike landing in that window is
  deflected: the recoil `SwordParryHit` plays and the counter (`SwordAttack1`) starts from 0.13 s.
  Outside the window the strike counts as a hit on the player (no health system yet).
- **Weapon policy.** Armed locomotion, jumps, falls, landings, crouching and dashes keep the sword in
  hand through a right-arm layer (clavicle_R branch). Walking, running and sprinting play the arm of the armed
  locomotion (game-r16, below), so the sword swings in step with the stride. With the sword out, jumps, falls,
  landings, dashes, the double jump, the roll, crouching and the knock-down play armed copies with their own arm
  movement, and standing still plays `SwordStand` (the idle with the sword in hand). Rolling keeps the sword, and
  draw and sheathe are instant with no clip (28 Sep). Dodging,
  interacting, waving, boarding a vehicle or the airship tuck the sword away; the next attack
  press draws again. Draws, sheathes and the parry recoil finish before another action can interrupt.
- **Hits.** In each clip's active window the blade segment (guard to tip) is swept with six spheres
  between frames; the wielder is excluded and a target is hit at most once per strike. Strength is 1
  (quick), 2 (charged) or 3 (full charge). Timing uses clip source seconds, so it does not depend on
  the frame interval.

The first enemy that can be fought with this set is the fox-masked hunter: `FOX_HUNTER_COMBAT.md` covers
its behaviour, the player's health, the flinch and knock-down, and the soft lock that turns the spinning
strikes toward it. `ASwordDummy` remains as a deterministic training post for the sword harness: it takes
hits, swings on request or every 3 s when spawned in play, and tells the player's sword when its swing
lands. Launch with it: `YORIMICHI_EXTRA_ARGS=-sworddummy atelier play yorimichi --profile desktop-1440`.

## Pipeline

```sh
# clips on the current body, validation, sheets, Studio GLB
blender -b --threads 4 --python-exit-code 1 --python games/yorimichi/assets/characters/tools/cairo_sword_combat_build.py
blender -b --threads 4 --python-exit-code 1 --python games/yorimichi/assets/characters/tools/cairo_sword_combat_check.py
blender -b --threads 4 --python-exit-code 1 --python games/yorimichi/assets/characters/tools/cairo_sword_combat_review.py -- sheets
blender -b --threads 4 --python-exit-code 1 --python games/yorimichi/assets/characters/tools/cairo_sword_combat_review.py -- export
# Unreal: clips + bokken + attachment data, then the targeted installer
blender -b --threads 4 --python-exit-code 1 --python games/yorimichi/assets/characters/cairo/export_unreal.py -- \
  --revision game-r13 --clips SwordIdle,SwordDraw,SwordSheath,SwordAttack1,SwordAttack2,SwordAttack3,SwordChargeUp,SwordChargeHold,SwordChargeRelease,SwordParry,SwordParryHit,SwordCombo \
  --clips-only --sword --report export-sword.json
python3 platform/studio/atelier/safety/guarded.py --report build/yorimichi/cairo/sword-import --timeout 900 --purpose 'Sword clip import' -- \
  '/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor-Cmd' "$PWD/games/yorimichi/unreal/Yorimichi.uproject" \
  -run=pythonscript "-script=$PWD/games/yorimichi/unreal/Scripts/import_cairo_sword.py" -unattended -nosplash -NullRHI -stdout
atelier build yorimichi unreal.compile
```

`import_cairo_sword.py` adds the `A_Sword*` clips (root motion enabled where the manifest says so, root
lock at the reference pose), `SM_Bokken` with its two materials, and the sword fields of
`DA_Cairo`; it verifies that every other Cairo asset file is byte-identical before and
after. The attachment is computed in Unreal as the exported rest transform of the sword times the
inverse of `hand_R`'s reference pose; the exported hand position matches the skeleton to 6 µm.

Code: `WandererSword.h/.cpp` (component, state machine, sweeps, dummy), `WandererSwordReview.cpp`
(harness), `WandererDefinition.h` (`FWandererSwordClip`, sword fields), `WandererAnimInstance.cpp`
(carry layer, root motion mode), `WandererCharacter.cpp` (inputs, cancels, movement lock),
`JapanHUD.cpp` (hints).

## Validation performed

- Blender, saved file, 240 Hz: no blade/sword against head, outfit or free skin overlap samples on any
  gameplay clip; fists clear the head; support grip ≤ 1.9 mm on two-handed captured frames; library
  curves byte-identical to game-r12 (`combat-r01/combat-validation.json`).
- Unreal, `-swordqa` at 60 and 30 fps (`build/yorimichi/logs/swordqa-60`, `swordqa-30`): scripted presses
  through the real handlers check draw, single tap, buffered chain, early/full charge with hit-stop,
  charge cancel by parry and by the menu, parry miss, parry success with counter, late parry, movement
  cancel with the carry layer, roll stow and redraw, mashing, sheathe, and that every registered strike
  target matches a dummy hit. Results are in `sword_qa.json` next to `sword_telemetry.csv` and the
  screenshots.
- Studio: the `yellow-boy-combat` asset loads with 21 clips, the six presets play, phone layout checked
  at 375 × 812 with the sticky loop/speed controls intact; `npm test --prefix studio` and
  `format:check` pass.
- Desktop: `YORIMICHI_EXTRA_ARGS=-sworddummy atelier play yorimichi --profile desktop-1440` launched at 1440p with the full HUD.

## Known limits

- The combo is a spinning capture: after a quick attack the character faces about 130° left of where
  it started (the capture's own turn). The next attack re-faces the stick or camera during its wind-up
  at 900°/s; when the player moves, the controller orients as usual.
- The charge raise leaves the support hand up to 33 mm off the grip for six frames (0.1 s); the draw
  and sheathe are one-handed until the last 40 %.
- Attack recoveries are authored blends of about 0.27 s; a recovery frame of strike 2 has a shoe toe
  15 mm under the guard's contact height.
- Mixamo login was not available in this session, so no dedicated sword-idle or block source was
  downloaded; the guard and the parry come from the combo's own stance and rising cover. With an Adobe
  login, [MIXAMO_WORKFLOW.md](MIXAMO_WORKFLOW.md#adding-another-mixamo-move) describes how to add such sources to the same build.
- The tassel is static. Damage and health exist only in the fox hunter fight (`FOX_HUNTER_COMBAT.md`); the dummy only counts.
- Phone-stream input has no attack buttons yet.

## Armed locomotion (game-r16, 28 September 2026)

User feedback: when running with the sword out, the sword arm was static and stiff, and it should do the usual
arm animation with the sword in hand. `games/yorimichi/assets/characters/tools/cairo_sword_locomotion.py` builds `SwordWalk · armed` and
`SwordSprint · armed` as copies of `Walk · library` and `Sprint · dressed`. Only the right arm and the grip
change.

- **Walk.** The clip's own arm. The hand grips with the palm toward the body, so the blade points forward:
  11° down at the back of the swing, 36° up at the front, 8° out from the legs. The wrist bends at most 16°.
- **Sprint (and the run, which is the sprint at 0.8×).** A full sprint pump would bring the blade over the
  head. The swing keeps its timing at 70% of its size about its middle. The elbow keeps the forearm pointing
  down and forward (−86° at the back, −40° at the front), so the blade is level at the back and rises to 42°
  at the front.
- **Width.** Seen from behind, the elbow and wrist stay at the unarmed sprint arm's distance from the body,
  plus 1.5 cm (hand 19 cm out from the centre line; the free hand is at 16). The first version held the hand
  28 cm out; the user said it hung too wide and should look like the other arm from the back. The blade
  angles up to 15° out at the back of the swing to clear the hip, and the wrist bends at most 21°.
- **Checks** (`game-r16/locomotion-build.json`): blade clearance to the clothes and head is at least 15.5 cm
  (walk) and 4.3 cm (sprint), and the loops close exactly. Review videos are in `armed-r01/captures/`.

In Unreal, `Scripts/import_cairo_armed.py` imports A_SwordWalk, A_SwordSprint and A_SwordRun (sprint at 0.8×).
It builds `BS_SwordLocomotion` (SwordIdle, SwordWalk, SwordRun, SwordSprint at BS_Locomotion's speeds) and sets
`DA_Cairo.ArmedLocomotion`. `WandererAnimInstance` plays that blend space in the "Stride" sync group,
so the arm follows the body's step phase. Its right arm feeds the carry layer while grounded locomotion is
playing. Actions and crouching fade back to the guard's carry pose over 0.17 s.

Checked in game at the beach with the live bridge (`live.sword()`, `live.drive(0, -1, 'sprint')`). Not reviewed
by the user yet.

### Jumps, roll, stand and instant draw (28 September 2026)

User feedback, in order:
1. The jump should reset the sword arm.
2. The roll should keep the sword.
3. Jumps should use the arm's usual movement.
4. There should be no draw or sheathe animation, and drawing should not move the arm.
5. Every animation, crouching included, should keep its own arm movement.

The armed copies (`Sword<Action>`) and how their blades are kept clear are described in `game-r16/README.md`.

In the game:
- `AWandererCharacter::GetAnimationClip()` picks the copy for Roll, DoubleJump, JumpStart, JumpRise, Fall, Land,
  HardLand, DashAir, DashGround, SitDown, SitIdle and StandUp while armed, and the anim instance swaps it in place
  when the sword changes mid-action.
- Crouching plays `BS_SwordCrouching` (`ArmedCrouching`) through the carry layer.
- The carry layer is off during a copy and returns at 12/s after it.
- `UWandererSwordComponent::SetArmed` shows or hides the sword at once, with the draw or sheathe sound. It is used
  by the toggle, by an attack press while sheathed (which now strikes at once) and by stowing.
- `StandClip()` is `SwordStand`.
- `-swordqa` at 60 fps passes all 36 checks (`build/yorimichi/logs/swordqa-60-r16b`), with the draw, roll and sheathe
  checks updated.
- The live bridge gained `live.press('jump' | 'jump_release' | 'roll')`.

Checked in game at the beach: the draw shows the sword in the hanging hand with no arm change, and standing and
running jumps keep the jump's arm movement.

