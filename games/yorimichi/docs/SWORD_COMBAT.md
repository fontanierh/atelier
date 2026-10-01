# Sword combat

Cairo, the player, carries a bokken (a wooden sword). It has a three-strike chain, a charged strike, a parry with a
counter, and armed copies of the locomotion and action clips so the sword stays in hand while running, jumping,
rolling or crouching. `UWandererSwordComponent` (`WandererSword.h/.cpp`) runs the state machine, the blade sweeps and
the player's health. The clips are cut from a Mixamo combo and carry root motion, so a strike turns and advances the
capsule as authored. The fox hunter ([FOX_HUNTER_COMBAT.md](FOX_HUNTER_COMBAT.md)) is the enemy, and a training post
(`ASwordDummy`) is there for practice and the QA run. Effects and sound are in [COMBAT_FEEDBACK.md](COMBAT_FEEDBACK.md).

## Build and try it

```sh
atelier build yorimichi characters.cairo unreal.cairo   # clips, bokken and DA_Cairo sword fields
atelier play yorimichi                                  # the fox hunter waits up the road from the start
atelier play yorimichi -- -sworddummy                   # plus a training post 1.3 m ahead, swinging every 3 s
atelier play yorimichi --profile swordqa                # the scripted sword check (see below)
```

Script profiles such as `desktop-1440` take extra Unreal arguments through the environment:
`YORIMICHI_EXTRA_ARGS=-sworddummy atelier play yorimichi --profile desktop-1440`.

`characters.cairo` exports the sword clips from `Cairo-Game-r18.blend` with the bokken and its attachment data
(`--sword --report export-sword.json`), then the armed copies. `unreal.cairo` runs `import_cairo.py`,
`import_cairo_sword.py` and `import_cairo_armed.py`. The sword import adds the `A_Sword*` clips (root motion where the
manifest asks for it, root lock at the reference pose), `SM_Bokken` with its two materials, and the sword fields of
`DA_Cairo`: the `FWandererSwordClip` table with each clip's windows, link, cancel, counter and contact point. The
bokken's attachment is its exported rest transform times the inverse of `hand_R`'s reference pose.

## Controls

| Action | Keyboard and mouse | Controller |
| --- | --- | --- |
| Attack (tap), charge (hold) | Left mouse button | Right trigger |
| Parry | Right mouse button | Left trigger |
| Draw or sheathe | R | D-pad Left |

All other bindings are in [CONTROLLER_CONTROLS.md](CONTROLLER_CONTROLS.md). Sword input is ignored on the
skateboard, on the sailboat and as a zeppelin passenger. While the sword is installed and the player is on foot, the
HUD shows the sword hints and a weapon line (state, charge percentage, the last event and, with the training post,
its counters). The health bar sits beside the stamina rings.

## How it plays

### Drawing and sheathing

Drawing and sheathing are instant: `SetArmed` shows or hides the bokken in the hand, plays `sword_draw` or
`sword_sheathe`, and blends the carry layer in fast. The toggle draws when the sword is away and sheathes from guard.
An attack press with the sword away draws and starts strike 1 in the same frame. Interacting, waving, boarding the
sailboat or the skateboard stows the sword; the next attack press draws it again. The `SwordDraw` and `SwordSheath`
clips are imported but not played.

### Strikes and the chain

- A tap starts `SwordAttack1` at once (0.07 s blend). Each strike faces the stick direction, or the camera forward
  when the character faces away from it (dot below −0.2).
- The blade sweeps inside each clip's active window (table below). Movement input is ignored until the clip's cancel
  time; after it, movement returns to guard and locomotion.
- From a clip's link time, a press made within the last 0.3 s (and after the strike started) starts the next strike.
  The chain stops at three. Presses during a strike are buffered, so mashing gives at most three strikes.
- Roll, dash and jump are refused during a strike before its cancel time and during the parry recoil.

### Soft lock and step-in

Each strike looks for the nearest living fox hunter or training post within 3 m that is roughly ahead: within
about 72° of the stick direction (dot above 0.3), or within about 107° of the current facing without stick input
(dot above −0.3). The character turns at 900°/s for 0.15 s so the clip's measured contact point (`ContactYaw`,
`ContactDistance`) passes through the target, and steps in by `distance − ContactDistance` (0 to 70 cm) at 350 cm/s
until 0.05 s after the active window opens. The step-in is a swept offset because the strike's root motion overrides
velocity. Clips without contact data fall back to 65 cm and 25° (strike 1), 95 cm and 0° (strike 2), 90 cm and −36°
(strike 3).

### Charge

- If the attack button is still held 0.25 s after strike 1 started, once that cut's active window has ended, the
  strike turns into `SwordChargeUp`. The cut has already landed and counts as its own strike. The counter strike
  never charges.
- `SwordChargeHold` loops while the button is held. After 0.9 s in the hold the charge is full: a flash, a ring and
  the `charge_ready` bell.
- Release plays `SwordChargeRelease`: at 1.0× for an early release (strength 2), at 1.05× for a full charge
  (strength 3), which then drops to 0.8× after its active window for a heavier settle.
- Parry cancels a charge back to guard. Roll, dash, jump, the menu and teleports cancel it without a strike, and the
  menu also drops the held button so a later release does nothing.

### Parry and counter

Parry works from guard and faces the target like a strike. `SwordParry` is active from 0.03 s to 0.30 s. A strike
arriving inside the window is deflected: `SwordParryHit` plays, the counter (`SwordAttack1`) starts 0.1 s into it, and
the parry effects play. A parried fox staggers into Hurt; a parried training post staggers for 1.2 s. Outside the
window the strike is a hit.

### Hits

During the active window the blade (six points from `SwordBladeStart` to `SwordBladeEnd`) is swept between frames as
6 cm spheres on the Visibility channel. The wielder is excluded and each target is hit at most once per strike.
Strength is 1 for a quick strike, 2 for a charged release and 3 for a full charge. Timing uses clip source seconds, so
it does not depend on the frame rate. A fox takes `Strength` points of damage ([FOX_HUNTER_COMBAT.md](FOX_HUNTER_COMBAT.md)).

### Player health

`IncomingStrike(Source, Damage, From)` decides what a strike does to the player:

| Result | When |
| --- | --- |
| Parried (1) | the parry window is active |
| Dodged (2) | a roll or dodge is playing and less than 0.9 s in |
| Absorbed (3) | the player is invulnerable or knocked down |
| Hit (0) | anything else |

The player has 100 health. A hit takes the damage, drops any sword clip to guard, plays a short flinch (the `Land`
clip) with a 260 cm/s shove away from the striker, and gives 0.7 s of invulnerability. At zero health the player is
knocked down: `SitDown`, `SitIdle` and `StandUp` play over 4.1 s, nothing else runs, and the player stands up with 100
health, the sword still drawn and 1.5 s of invulnerability. The training post's swing does no damage; it only counts.

## Armed animation

With the sword out, the right arm keeps the sword in hand through a carry layer: a layered blend on the `clavicle_R`
branch in `WandererAnimInstance`. On the ground it takes the arm from the armed locomotion, so the sword swings in step
with the stride.

- **Locomotion.** `BS_SwordLocomotion` (`DA_Cairo.ArmedLocomotion`) holds `SwordIdle`, `SwordWalk`, `SwordRun` and
  `SwordSprint` at the unarmed blend space's speeds; `SwordRun` is the sprint at 0.8×. It plays in the "Stride" sync
  group with the body, so the arm follows the step phase. Crouching plays `BS_SwordCrouching`
  (`ArmedCrouching`). Actions fade back to the guard's carry pose (`SwordCarry`) over 0.17 s.
- **Actions.** While armed, `AWandererCharacter::GetAnimationClip()` plays the armed copy (`Sword<Action>`) of Roll,
  DoubleJump, JumpStart, JumpRise, Fall, Land, HardLand, DashAir, DashGround, SitDown, SitIdle and StandUp, and swaps
  it in place if the sword changes mid-action. The carry layer is off during a copy and returns at 12/s after it.
  Standing still plays `SwordStand` (`StandClip()`, falling back to `SwordIdle`).
- **Design rules for the armed walk and sprint.** Only the right arm and the grip differ from the unarmed clips. The
  walk keeps the clip's own swing with the palm toward the body, so the blade points forward (about −11° to +36°).
  The sprint keeps its timing at 70% of its swing so the blade never rises over the head, and its forearm points down
  and forward so the blade is level at the back of the swing and rises to about 42° at the front. Seen from behind,
  the sword hand stays at the unarmed arm's distance from the body plus 1.5 cm. Blade clearance to the clothes and
  head is at least 15.5 cm (walk) and 4.3 cm (sprint); the numbers are in
  `assets/characters/cairo/locomotion-build.json`.

The carry is zeroed while sailing, riding the skateboard or travelling as a zeppelin passenger.

## Clip reference

Times are clip source seconds, from `assets/characters/cairo/source-manifest.json`. Contact yaw is the bearing of the
measured contact point, positive to the left.

| Clip | Length | Active window | Link from | Cancel | Notes |
| --- | --- | --- | --- | --- | --- |
| SwordAttack1 | 0.55 s | 0.140–0.259 | 0.259 | 0.259 | contact yaw +27.7° |
| SwordAttack2 | 0.50 s | 0.122–0.251 | 0.241 | 0.241 | contact yaw −23.9° |
| SwordAttack3 | 0.583 s | 0.134–0.277 | | 0.465 | contact yaw −46.7°; ends the chain |
| SwordChargeUp | 0.217 s | | | | |
| SwordChargeHold | 2.0 s | | | | loop |
| SwordChargeRelease | 0.533 s | 0.055–0.198 | | 0.393 | contact yaw −29.1° |
| SwordParry | 0.483 s | 0.033–0.300 (parry) | | 0.333 | |
| SwordParryHit | 0.15 s | | | | counter from 0.1 |
| SwordIdle | 3.0 s | | | | loop; carry fallback |
| SwordCombo | 3.52 s | | | | the whole source combo, reference only |

Armed copies: SwordWalk, SwordSprint, SwordRun, SwordStand, SwordCarry, SwordJumpStart, SwordJumpRise,
SwordDoubleJump, SwordFall, SwordLand, SwordHardLand, SwordDashAir, SwordDashGround, SwordCrouchIdle,
SwordCrouchWalk, SwordSitDown, SwordSitIdle, SwordStandUp and SwordRoll.

The clips are authored in Blender by `assets/characters/tools/cairo_sword_combat_build.py`,
`cairo_sword_combat_r02.py` and `cairo_sword_locomotion.py`, which read the earlier character revisions from the
archive (`YORIMICHI_ARCHIVE`, see `assets/characters/tools/_archive.py`). [MIXAMO_WORKFLOW.md](MIXAMO_WORKFLOW.md)
describes the Mixamo source and how to add another move.

## Sword QA run (swordqa profile)

`atelier play yorimichi --profile swordqa` starts the game with `-swordqa -swordqafps=60 -reviewdir={run}`.
`WandererSwordReview.cpp` steps the game on a fixed clock (`-swordqafps`, clamped to 15–240, default 60), puts the
player on a flat 60 × 60 m floor 20 m above the world with a fixed camera and the training post about 1 m away, and
presses buttons through the real input handlers. It spawns no fox.

It runs 36 checks in order: the set is installed, the post is there, the player starts unarmed; the toggle draws at
once and settles into guard; a tap gives one strike and one hit with movement locked; buffered presses chain into
strikes 2 and 3; a held press winds up a charge; an early release is charged but not full and the cut and the release
each land once; the hold reaches full after 0.9 s and the full release lands once; parry cancels a charge and the
later release does not attack; the parry is active within 0.15 s; a missed parry returns to guard; a timed parry
deflects the post's swing and the counter lands once; an unparried swing is a hit; movement is locked before the
cancel time and returns control after it; armed running keeps the carry; the roll keeps the sword and plays
`SwordRoll`, and an attack after it strikes at once; the menu cancels a charge and the release after it does not
attack; six mashed presses give at most three strikes; the toggle sheathes at once; the player ends unarmed and
unlocked; every strike's target matches a hit on the post.

It writes to the run folder (`build/yorimichi/logs/play-swordqa-<stamp>/`) and exits:

- `sword_qa.json`: `passed`, `errors`, `strikes`, `dummy_hits`, `hits_taken`, `parries`, `fixed_fps`.
- `sword_telemetry.csv`: per step, the sword state, clip and clip time, movement lock, the running counters, the
  player's position and yaw, and the blade tip.
- Screenshots: `sword_draw.png`, `sword_attack1_contact.png`, `sword_attack3.png`, `sword_charge_hold.png`,
  `sword_charge_release.png`, `sword_parry_active.png`, `sword_counter.png`.

## Training post

`ASwordDummy` is a 50 cm × 140 cm post. It counts hits (it flashes red), and swings at the player with a 0.6 s
wind-up: it grows taller and turns yellow, then strikes if the player is within 190 cm. A parried
swing staggers it for 1.2 s (blue). A full charge interrupts its wind-up and staggers it for 0.8 s. With
`-sworddummy` it stands 1.3 m ahead of the player and swings every 3 s; the QA run triggers its swings itself.

## Files

All under `games/yorimichi/`.

| What | Where |
| --- | --- |
| State machine, sweeps, soft lock, player health, training post | `unreal/Source/Yorimichi/WandererSword.h/.cpp` |
| Sword QA run and `-sworddummy` | `unreal/Source/Yorimichi/WandererSwordReview.cpp` |
| `FWandererSwordClip` and the sword fields | `unreal/Source/Yorimichi/WandererDefinition.h` |
| Carry layer and armed blend spaces | `unreal/Source/Yorimichi/WandererAnimInstance.cpp` |
| Inputs, cancels, armed clip swaps | `unreal/Source/Yorimichi/WandererCharacter.cpp` |
| Hints, weapon line, health bar | `unreal/Source/Yorimichi/JapanHUD.cpp` |
| Source clips and their timings | `assets/characters/cairo/Cairo-Game-r18.blend`, `source-manifest.json`, `combat-build.json`, `locomotion-build.json` |
| Unreal import | `unreal/Scripts/import_cairo_sword.py`, `unreal/Scripts/import_cairo_armed.py` |
| Live bridge helpers | `live/python/yorimichi_live.py` (`sword()`, `press(...)`, `drive(...)`) |

## Limits

- The tassel is static.
- The phone stream has no sword buttons.
- The training post's swing does no damage; only the fox hunter hurts the player.
