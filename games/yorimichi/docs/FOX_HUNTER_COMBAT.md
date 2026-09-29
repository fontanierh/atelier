# Fox hunter combat: the first enemy in the game

> Moved from the prototype repository on 29 September 2026. Paths are translated to this repository where the file moved; paths still starting with `japan/` or `output/imagegen/` refer to the prototype archive (authoring tools, earlier revisions, review images). See [docs/MIGRATION.md](../../../docs/MIGRATION.md).

Written 16 September 2026; the clips were updated to animation-r05 on 23 September 2026 (see below). The
fox-masked hunter (`games/yorimichi/docs/FOX_HUNTER_ANIMATION.md`) is installed in the Unreal project and fights the player with the sword set of `SWORD_COMBAT.md`. This note
covers the import, the enemy's behaviour, what the player can do to it, the validation performed and the
limits.

Try it: `atelier play yorimichi --profile desktop-1440` (or `play`). The hunter waits 12 m up the road from the start, a little
to the left, and notices the player at 9 m. Draw the sword with R (D-pad Left on a pad) or just attack.

## Import

```sh
blender -b --threads 4 --python-exit-code 1 --python games/yorimichi/assets/characters/fox-hunter/export_unreal.py
atelier build yorimichi unreal.compile
python3 platform/studio/atelier/safety/guarded.py --report build/yorimichi/logs/fox-import --timeout 900 --purpose 'Fox import' -- \
  '/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor-Cmd' "$PWD/games/yorimichi/unreal/Yorimichi.uproject" \
  -run=pythonscript "-script=$PWD/games/yorimichi/unreal/Scripts/import_fox_hunter.py" -unattended -nosplash -NullRHI -stdout
```

`export_fox_hunter_unreal.py` opens `animation-r05/FoxHunter-Anim-r05.blend` (r04 until 23 September), scales the 0.918-unit body to
1.70 m (scale 1.852; the player is 1.48 m), puts the floor 0.65 cm under the soles like the player export,
renames the bones with the player's aliases (`root`, `pelvis`, `hand_R`, `finger_end_1_R`...), writes the
colour map as the JPEG it is, and bakes the fifteen clips at 30 fps. Loops get their seam frame (frame N is
frame 0), so Idle, Creep and Run are exactly 4.0, 1.5 and 0.6 s and wrap over one frame step. The report
`build/yorimichi/fox_hunter/export.json` records, per clip, the duration, root travel and yaw measured after the
export, the hit window, striking bone and reach of each attack, and the authored travel speeds of the loops.

`import_fox_hunter.py` builds `/Game/FoxHunter`: `SK_FoxHunter` (skeleton, physics asset), the material with
the player's small albedo fill plus a `HitFlash` scalar the game drives, `A_Fox*` (root motion enabled on the
dashes, turns and Hurt, root lock at the reference pose, the shared character compression), `BS_FoxLocomotion`
(Idle 0, Creep 59, Run 591 cm/s) and `DA_FoxHunter` (`UFoxHunterDefinition`: mesh, blend space, actions, the
per-clip gameplay table, capsule 26 × 86 cm). Nothing under the other character folders is touched. The
reference pose is checked against the exported bone positions (sub-millimetre).

Measured from the export (cm, at the game scale):

| Clip | Length | Hit window | Reach from the root | Notes |
| --- | --- | --- | --- | --- |
| AttackR_A / AttackL_A | 1.9 s | 0.52 to 0.68 s | 103 / 106 | diagonal claw, hand 73 to 174 cm high |
| AttackL_B / AttackR_B | 1.9 s | 0.50 to 0.63 s | 96 / 97 | rising backhand, 98 to 153 cm high |
| Kick | 1.1 s | 0.38 to 0.48 s (r04: 0.56) | 95 | chest height; hard accent since r05 |
| DashForward | 1.6 s | | | root travel 296 |
| DashBackward | 1.5 s | | | root travel 166 back |
| TurnLeft / TurnRight | 1.3 s | | | root yaw 180 |
| Hurt | 1.2 s | | | root travel 52 back |
| Death | 3.0 s | | | holds its last pose; no root motion, the body pitches over in the mesh |

## Code

- `FoxHunter.h/.cpp`: `UFoxHunterDefinition`, `FFoxHunterClip`, `AFoxHunter` (state machine, strike sweeps,
  hit reactions, death and return).
- `FoxHunterAnimInstance.h/.cpp`: the native graph, a speed blend space under the player's velocity-preserving
  state node, `RootMotionFromEverything`. The FBX root bone carries the export scale, so root-motion
  translation is normalised with `SetAnimRootMotionTranslationScale`, as for the player's sword clips.
- `FoxHunterReview.cpp`: the `-foxqa` harness.
- `WandererSword.h/.cpp`: the player side. `IncomingStrike(Source, Damage, From)` returns hit, parried,
  dodged or absorbed; health, the flinch, the knock-down, the soft lock in `FaceInput`, fox hits in
  `SweepBlade`.
- `JapanGameMode.cpp`: spawns the hunter in ordinary play (`-nofox` suppresses it; scripted sessions get it
  only with `-foxhunter` or `-foxqa`). `JapanHUD.cpp`: the health bar and the fox line.

## How the hunter fights

The fox has no controller and no navigation; the state machine feeds movement input directly on open ground
(`bRunPhysicsWithNoController`) and sets facing explicitly, because root-motion clips must not be re-oriented
by their own velocity (the backward dash would spin it round).

- **Idle** until the player is within 9 m, then **Approach**: runs in (480 cm/s, the Run clip scaled by the
  blend space) until 2.5 m, with a chance of a **Lunge** (DashForward, 3 m of authored travel) from 3 to 3.8 m.
- **Stalk**: creeps the last stretch at 75 cm/s, faces the player at 360°/s, stops at 0.92 m. If the player is
  behind it, it plays TurnLeft/TurnRight (root yaw) instead of pivoting on the spot.
- **Attack** when within 1.1 m and facing: one of the four claws or the kick (weighted, the harness can force
  one). The hand or foot is swept with spheres (r 14 cm, four points from the wrist to beyond the claw tip)
  between frames inside the clip's hit window, once per attack, on the Pawn channel. The wind-up tracks the
  player at 150°/s and stops tracking 0.15 s before the window: that is the moment to step aside. After the
  clip: a 45 % chance of an immediate second claw (at most three in a row), a 30 % chance of springing back
  (DashBackward), otherwise a 0.3 s recovery and a 0.9 to 1.8 s cooldown.
- **Contact** goes through the player's sword: parry-active deflects it (the fox staggers into Hurt for 1.2 s
  and the player's counter starts), a roll or dodge in progress makes it miss, a hit takes 20 (claw) or 30
  (kick) health with a short flinch (the library's Land clip) and a shove; 0.7 s of grace follows a hit.
- **Taking hits**: six points of health; quick strikes take one, charged two, full charges three. A hit
  staggers the fox (Hurt, 52 cm back) unless it is armored: mid-strike after the wind-up, out of poise (two
  wind-up interruptions in 2.5 s), or dashing. Charged hits stagger through anything. At zero it plays Death
  and holds the pose; the capsule stops blocking so the player walks past; after 6 s the body fades and 10 s
  later the hunter is back at its home spot at full health.
- **Knocking the player down**: at zero health the player sits down dazed (SitDown, SitIdle, StandUp, 4.1 s),
  the fox springs back, runs home and ignores the player for 4 s; the player gets up restored with 1.5 s of
  grace. Nothing else runs while down.
- **Soft lock**: an attack or counter faces the nearest living fox within 3 m and roughly ahead of the stick
  (or of the current facing with no stick), so the spinning strike clips land on it. Stick input still wins
  when it points away.

## Validation performed

`-foxqa` (`FoxHunterReview.cpp`) on a flat floor at a fixed 60 Hz and 30 Hz, driving the real handlers:

```sh
python3 platform/studio/atelier/safety/guarded.py --report build/yorimichi/logs/foxqa-60 --timeout 900 --purpose 'Fox QA' -- \
  '/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor' "$PWD/games/yorimichi/unreal/Yorimichi.uproject" \
  -game -windowed -resx=1280 -resy=720 -character=cape_boy -foxqa -foxqafps=60 "-reviewdir=$PWD/build/yorimichi/logs/foxqa-60" -stdout "-abslog=$PWD/build/yorimichi/logs/foxqa-60/game.log"
```

Both runs pass all sixteen checks with the same counts (8 fox attacks: 5 landed, 1 parried, 1 dodged,
1 missed; 4 blade hits and 1 death on the fox; 5 hits and 1 parry on the player; 51.5 s): the fox starts
idle at its world spot, notices and runs in at 480 cm/s, stalks to range and claws; a parry timed from
the clip's window deflects it and the counter takes one point; an unparried claw takes 20 health and
plays the flinch; a roll toward the fox during the wind-up is a clean dodge; quick strikes bring it to
three, a full charge kills it, the body holds and fades, the hunter returns home at full health; standing
still the player is knocked down in four hits, the fox withdraws, the player stands up restored and still
armed. Results in `build/yorimichi/logs/foxqa-60` and `foxqa-30` (`fox_qa.json`, `fox_telemetry.csv`, screenshots
of the approach, parry, counter, hit, roll, charge, death, knock-down and recovery).

The sword harness (`-swordqa`, 60 Hz) still passes after the sword-component changes; it spawns no fox.

Desktop: `atelier play yorimichi --profile desktop` (the windowed 2560 × 1440 variant of the validated desktop profile) reached
the world with the hunter spawned on traced ground 12 m up the road, visible from the start with its HUD line
(`build/yorimichi/desktop-preview/20260916-180451/ready.png`). The fullscreen `desktop-1440` variant was tried twice in
this unattended session and both times the game thread stayed inside macOS's fullscreen transition
(`FMacWindow::UpdateFullScreenState`) until the launcher's four-minute deadline; the same command worked
earlier in the day with someone at the machine, so this is a display-state condition, not a change in the
build. Run it from the desk to see the fight at native 1440p.

Three rounds of the fox harness were needed before it passed, and the telemetry decided each change: the
counter never reached the fox until the parry stagger kept only a quarter of its authored 52 cm step and
strikes stepped in during the wind-up; the step-in had to be a swept offset because the strike clips'
root motion overrides any velocity (and `LaunchCharacter` puts the character in the air for a frame, so the
landing replaced the parry with the Land clip); and the first cut's contact zone is 55 cm ahead and to the
left, not straight ahead, which is why the soft lock carries a per-strike distance and yaw offset.

## Known limits

- No navigation: the fox walks straight at the player and can be blocked by a tree or a wall; it forgets the
  player beyond 26 m and walks home.
- The Jump clip is not used yet (a leap over a low sweep would be a natural use).
- Damage numbers are first values: five claws or three kicks knock the player down, two sword chains or a
  chain and a full charge kill the fox.
- One hunter, placed by the game mode near the start; no encounter design, no loot, no sound.
- The motions are the r04 set the user reviewed on the Fox Hunter Build page plus the r05 timing changes, which
  the user has not reviewed; the gameplay timings (windows, reach) come from the manifest and have not been
  re-tuned for play.

## animation-r05 (23 September 2026)

`fox_hunter_animate.py` changed four clips after the animation-principles pass (commit c044bff,
`ANIMATION_PRINCIPLES.md`), and r05 rebuilds all fifteen from it:

- **Creep:** the swing foot follows a solved 4.5 cm arc. The old forward-kinematic swing reached 8 cm under
  the floor, so the contact pass lifted the whole body and dropped it 8 cm at each heel strike. The pelvis
  now bobs, lowest a quarter step after each strike.
- **Kick:** a hard accent. The foot overshoots for one frame after the hit and rebounds, and the hit window
  shortens from 0.38–0.56 s to 0.38–0.48 s.
- **Hurt and Death:** the displaced hit pose lands on the frame after contact with no ease-in.

The other eleven clips are unchanged. Clipping check (`manifest.json`): the Creep leg graze drops from
56 to 33 edges (0.5 to 0.3 mm deep), and every other clip is the same as r04.

- Export: `blender -b --threads 4 --python-exit-code 1 --python games/yorimichi/assets/characters/fox-hunter/export_unreal.py`.
  The default is now `--rev animation-r05`.
- Import: `import_fox_hunter.py` as above. 15 clips, 0 errors.
- `-foxqa` at 60 Hz passes every check (`build/yorimichi/logs/foxqa-60-r05`): 7 fox attacks, 5 landed, 1 parried,
  1 dodged, 4 blade hits, 1 death, a knock-down and recovery, in 52.3 s. The r04 run had 8 attacks with one
  miss.
