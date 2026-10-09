# Fox hunter combat

The fox-masked hunter is the game's enemy. One hunter waits 12 m up the road from the player start, notices the player
at 9 m, runs in, stalks to range and attacks with four claw swipes and a kick. The player fights it with the sword
([SWORD_COMBAT.md](SWORD_COMBAT.md)): parry into a counter, roll through its strikes, and cut it down with quick or
charged strikes. It dies, burns away and returns home 10 s later. `AFoxHunter` (`FoxHunter.h/.cpp`) is a state machine
over the fifteen clips described in [FOX_HUNTER_ANIMATION.md](FOX_HUNTER_ANIMATION.md); effects and sounds are in
[COMBAT_FEEDBACK.md](COMBAT_FEEDBACK.md).

## Build and try it

```sh
atelier build yorimichi characters.fox_hunter unreal.fox_hunter   # export the mesh and clips, build /Game/FoxHunter
atelier play yorimichi                                            # the hunter is up the road, a little to the left
```

Draw the sword with R (D-pad Left) or just attack. `atelier play yorimichi -- -nofox` starts without the hunter.

`characters.fox_hunter` runs `assets/characters/fox-hunter/export_unreal.py` in Blender on `FoxHunter-Anim-r05.blend`.
It scales the 0.918-unit body to 1.70 m (scale 1.852; the player is 1.48 m), puts the floor 0.65 cm under the soles
as the player export does, renames the bones with the player's aliases (`root`, `pelvis`, `hand_R`,
`finger_end_1_R`...), and bakes the fifteen clips at 30 fps. Loops keep their seam frame, so Idle, Creep and Run wrap
over one frame step. It writes `build/yorimichi/fox_hunter/{fbx,textures,export.json}`; the report records per clip
the duration, the root travel and yaw measured after export, and for each attack its hit window, striking bones and
reach. `--clips` and `--clips-only` limit the export.

`unreal.fox_hunter` runs `unreal/Scripts/import_fox_hunter.py`, which builds `/Game/FoxHunter`:

- `SK_FoxHunter` with its skeleton and physics asset.
- The material, with a `HitFlash` scalar for hits and a `Dissolve` scalar that burns the body away with world-space
  noise and an ember edge.
- The `A_Fox*` clips: root motion on the dashes, turns and Hurt, root lock at the reference pose, the shared character
  compression.
- `BS_FoxLocomotion`: Idle at 0, Creep at 59 and Run at 591 cm/s.
- `DA_FoxHunter` (`UFoxHunterDefinition`): mesh, blend space, the per-clip gameplay table (`FFoxHunterClip`: hit
  window, striking bones, travel), capsule radius 26 cm and half-height 86 cm.

## How the hunter fights

The fox has no controller and no navigation. The state machine feeds movement input on open ground
(`bRunPhysicsWithNoController`, gravity scale 1.5) and sets the facing itself, because root-motion clips must not be
turned by their own velocity (the backward dash would spin it round). The capsule blocks the Visibility channel so the
blade can hit it, and ignores the camera.

| State | What it does |
| --- | --- |
| Idle | Stands at home. Notices the player within 9 m (`fox_alert`), unless the player is knocked down or the notice block is running. |
| Approach | Faces the player at 420°/s and runs at 480 cm/s until 2.5 m. At 3.0–3.8 m, facing within 12°, it may lunge (about 1.5 chances a second). Beyond 26 m, or with the player down, it returns home. |
| Lunge | DashForward: a 3 m dive. Armoured. Then Stalk with a 0.15 s cooldown. |
| Stalk | Faces at 360°/s and creeps at 75 cm/s, stopping at 0.92 m. Back to Approach beyond 3.8 m. Plays TurnLeft or TurnRight when the player is more than 130° off and it is nearly still. Attacks within 1.1 m, facing within 30°, when the cooldown is over. |
| Attack | One of five strikes (below). Tracks the player at 150°/s until 0.15 s before the hit window, then commits: that is the moment to step aside. |
| Recover | 0.3 s facing the player, then Stalk with a 0.9–1.8 s cooldown. |
| Retreat | DashBackward: springs 1.66 m back. Armoured. Cooldown 1 s. |
| Hurt | The Hurt clip (1.2 s, 52 cm back). Cooldown at least 0.5 s after it. |
| Turn | TurnLeft or TurnRight, a 180° root-yaw turn. |
| Withdraw | DashBackward after knocking the player down. Armoured. Then Return. |
| Return | Walks home at 336 cm/s. At home it goes Idle and ignores the player for 4 s. |
| Dead | See below. |

### Attacks

| Clip | Weight | Hit window | Striking part | Damage |
| --- | --- | --- | --- | --- |
| AttackR_A | 24% | 0.52–0.68 s | right hand | 20 |
| AttackL_A | 24% | 0.52–0.68 s | left hand | 20 |
| AttackL_B | 18% | 0.50–0.63 s | left hand | 20 |
| AttackR_B | 18% | 0.50–0.63 s | right hand | 20 |
| Kick | 16% | 0.38–0.48 s | right foot | 30 |

The swipe or kick sound plays 0.07 s before the window. Inside the window four points along the striking hand or foot
(bone, midpoint, tip, 8 cm past the tip) are swept between frames as 14 cm spheres on the Pawn channel, once per
attack. The player's sword component decides the outcome (`IncomingStrike`):

- **Parried**: the fox staggers into Hurt with a quarter of its authored step, so the counter can reach, and waits
  1.3 s before attacking again.
- **Dodged**: a roll in its first 0.9 s makes the strike miss ("swipes at air").
- **Absorbed**: the player is invulnerable or down; it counts as a miss.
- **Hit**: the player loses 20 (claw) or 30 (kick) health.

After the clip: if the player went down, the fox withdraws. Otherwise a claw has a 45% chance of an immediate
follow-up (within 1.35 m and 40°, at most three attacks in a row). Failing that, within 2.2 m it springs back 30% of
the time, and otherwise recovers.

### Taking hits

- Six health. A sword hit takes its strength: 1 for a quick strike, 2 charged, 3 full charge. The material flashes for
  0.22 s.
- The fox cries (`fox_hurt`) on the first hit, on charged hits and on death, and otherwise on every other hit.
- A hit staggers it into Hurt unless it is armoured. It is armoured while lunging, retreating or withdrawing, during
  an attack once the wind-up is over, and during a wind-up when it is out of poise. Poise is 2, each interrupted
  wind-up costs 1, and it regains 1 every 2.5 s. Charged and full-charge hits stagger it through armour.
- At zero health it plays Death and holds the last pose. Movement stops and the capsule stops blocking pawns and the
  blade. The body lands at 1.95 s (`body_fall` and dust); from 2.45 s it burns away over 1.7 s with rising embers
  (`fox_death`), ending in a burst and a flash. At 4.3 s it is hidden, and 10 s later it reappears at home with full
  health and ignores the player for 2 s.

With these numbers, five claws or four kicks knock the player down, and two sword chains, or a chain and a full
charge, kill the fox.

### The player's side

The player has 100 health, a short flinch and 0.7 s of grace after each hit, and is knocked down at zero for 4.1 s
before standing up restored with 1.5 s of grace ([SWORD_COMBAT.md](SWORD_COMBAT.md#player-health)). The soft lock
turns each strike and the counter toward the nearest living fox within 3 m that is roughly ahead, and steps in so the
clip's contact point lands on it.

The HUD shows the health bar beside the stamina rings, a red wash when the player is hit, and, for the nearest fox
that is engaged or within 15 m, a line at the top with its state, its last event and six health pips.

### Spawning

`JapanGameMode` spawns the hunter 12 m ahead of the player start and 3.5 m to the left, on traced ground, facing the
player. `-nofox` suppresses it. Scripted sessions (a command line containing `qa`, `benchmark`, `trailershot`,
`buildingreview` or `AtelierStream`) get no fox unless `-foxhunter` is given, so the phone stream has
none.

### Animation

`UFoxHunterAnimInstance` plays the speed blend space under an action node, with `RootMotionFromEverything`. Above the
Run sample (591 cm/s) only the playback rate rises. The FBX root bone carries the export scale, so root-motion
translation is normalised with `SetAnimRootMotionTranslationScale`. Death has no root motion: the body pitches over in
the mesh.

## Combat checks

The player uses the merged Adventure move set in every session. Its attacks, sword guard, parry and dodges meet
the fox's existing strike and hit interfaces; the player's authored legacy combat set is not installed.
For movement and combat checks, use `scenarios/adventure_moves.py` through the live bridge. Kaede's
[training bouts](SWORD_TRAINER.md) exercise both fighters on the merged set.

## Files

All under `games/yorimichi/`.

| What | Where |
| --- | --- |
| State machine, strikes, hit reactions, death and return | `unreal/Source/Yorimichi/FoxHunter.h/.cpp` |
| Animation graph | `unreal/Source/Yorimichi/FoxHunterAnimInstance.h/.cpp` |
| Player side: combat and reactions, health | `unreal/Source/Yorimichi/AdventureMoveSetCombat.cpp`, `WandererSword.h/.cpp` |
| Spawning | `unreal/Source/Yorimichi/JapanGameMode.cpp` |
| Health bar and fox line | `unreal/Source/Yorimichi/JapanHUD.cpp` |
| Source, manifest, export | `assets/characters/fox-hunter/` (`FoxHunter-Anim-r05.blend`, `manifest.json`, `character.toml`, `export_unreal.py`) |
| Unreal import | `unreal/Scripts/import_fox_hunter.py` |

## Limits

- No navigation: the fox moves straight at the player and can be blocked by a tree or a wall.
- One hunter, placed by the game mode near the start; no encounter design and no loot.
- The Jump clip is imported but not used.
- The gameplay timings (hit windows, reach) come from the animation manifest and have not been tuned for play.
