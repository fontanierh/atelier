# Sword combat

Cairo, Modori, Nox, Paul and Kaede use the merged Adventure move set for sword combat. The retained sword is fitted to each
character's hands and back by its `adventure.toml`. Cairo lends the set his two-handed guard stance, parry and recoil;
the other combat motions come from the committed Adventure motion bundle.

```sh
uv run atelier build yorimichi unreal.cairo_adventure unreal.modori_adventure unreal.nox_adventure unreal.paul_adventure unreal.sword_trainer_adventure
uv run atelier play yorimichi
uv run atelier live py - < games/yorimichi/scenarios/adventure_moves.py
```

The build imports each character's merged clips and definition, plus its `Content/Data/<character>/adventure.json`
action timings and equipment fits. Cairo's base import supplies his body and nine donor clips. It produces no
separate combat or armed locomotion set. Old generated movement/combat imports are archived before cooking.

## Controls

| Action | Keyboard and mouse | Controller |
| --- | --- | --- |
| Attack (tap), charged spin (hold) | Left mouse button | Right trigger |
| Guard and lock on (hold) | Right mouse button | Left trigger |
| Parry while guarding | Space | Bottom face button |
| Draw or sheathe | R | D-pad Left |
| Dodge while guarding | Left Ctrl | Right face button |

See [controller controls](CONTROLLER_CONTROLS.md) for the complete bindings. The set supports the four-cut combo,
charged spin, dash attack, jump attack, plunge, sneakstrike, sword guard, parry and the flurry rush after a perfect
dodge. Combat input yields to menus, the skateboard, vehicles and zeppelin travel.

Kaede's [training bouts](SWORD_TRAINER.md) exercise both sides of the same combat rules. The
[fox hunter](FOX_HUNTER_COMBAT.md) remains an enemy. `-sworddummy` places a training post ahead of the player for
manual checks; the `adventure_moves` scenario checks the merged set's movement, traversal and combat.

## Contact, guard and timing

Each swing can resolve one contact per target. Blade sweeps and the close-range arc also check active windows
crossed between frames, so a short window still lands at 15–30 fps. NPCs have 0.10 s of hit recovery instead of
the player's 0.70 s: separate combo cuts can each deal damage and play their directional recoil. The third
quick hit, or a stronger hit, produces the existing medium stagger. Interrupted Ronin abandon their queued combo.

Hold guard and press parry just before contact. A **perfect parry** lasts the first 120 ms of the authored guard
window (Cairo's starts 33 ms after the press), must face the incoming strike, and deflects one contact. It staggers
a melee attacker within counterattack reach. An early attempt falls back to held guard; an attack from behind
bypasses it. The server uses the same window and facing rules for remote players.

Ordinary blocks accumulate guard pressure: four quick light blows, three stronger blows, or one full heavy blow
break guard. A break opens the existing guard-break animation and vulnerable recovery. Pressure begins recovering
after 1.1 s without a blocked hit, at 28% per second. A perfect parry removes 45%. A thin amber line under the
player's and selected opponent's health shows accumulated pressure; sparks and recoil distinguish a block from
a hit or perfect parry. Contact-owned pressure is authoritative and never reapplied by movement replay.

## Ronin roles and tells

The coastal camp retains its scout, guard and captain appearances and encounter attack tickets.

| Role | Pressure and openings |
| --- | --- |
| Scout | Quick 0.30 s melee opening and 0.42 s combo rhythm. At 4.5–11 m, can brace for 0.60 s and throw a small blade with a slash, then close for melee while its 4.8 s throw cooldown runs. |
| Guard | 0.42 s opening and 0.54 s combo rhythm, guarding and countering between openings. |
| Captain | Deliberate 0.56 s opening and 0.66 s combo rhythm, with the existing heavy, jump and charged openings. |

A small warm glint and a quiet swish appear on the weapon about 0.16 s before a committed opening. Charged and
airborne attacks also glint near their authored active window. Follow-up cuts keep their role's rhythm. The cue
does not slow time or add a HUD warning. Animations and spacing remain the primary tells.

The scout's thrown blade flies at 11 m/s toward the point aimed at on release; it cannot track a dodge. Cover and
other bodies stop it. Guard blocks it, a dodge avoids it, and a perfect parry reflects it toward the thrower at
14.5 m/s for 18 damage. It uses the existing short-sword mesh scaled down and the existing slash animation;
there is no new bow or throwing animation. Damage goes through the same authority defence resolver as melee.

The design builds on the previous camp work (PRs #379 and #384). Research references:
[OpenGothic's range/focus/pre-hit tactical selection](https://github.com/Try/OpenGothic/blob/master/common/game/fightalgo.cpp)
and [BotW's GuardJust action](https://github.com/zeldaret/botw/blob/master/src/Game/Actor/Action/actionGuardJust.cpp).
OpenGothic supplies a useful model for distinct tactical sequences; BotW's available GuardJust implementation is
a thin animation wrapper and supplies no exact timing constants. The timing above is Yorimichi tuning.

Native regression tests are `Yorimichi.Combat.Rules` and `Yorimichi.Combat.Contacts`. They exercise active-window
crossings, guard exhaustion, local and historical parry direction, NPC versus player recovery, actual projectile
reflection/damage, cover interception and a target stepping out of the committed flight path.

## Implementation

| What | Where |
| --- | --- |
| Action clips, timings and parameters | `assets/characters/adventure/moves.toml` and `moves.py` |
| Donor clips and their timing windows | `assets/characters/cairo/adventure.toml` |
| Per-character retargeting and equipment fit | `assets/characters/adventure/retarget.py`, `unreal/Scripts/import_adventure_moveset.py` |
| Combo, charge, guard, parry, hits and blade sweeps | `unreal/Source/Yorimichi/AdventureMoveSetCombat.cpp` |
| Network defence and reactions | `AdventureMoveSetDefence.cpp`, `AdventureMoveSetReaction.cpp` |
| Shared guard pressure and window rules | `unreal/Source/Yorimichi/SwordCombatRules.h` |
| Scout projectile flight, interception and reflection | `unreal/Source/Yorimichi/RoninProjectile.h/.cpp` |
| Player health and training post | `unreal/Source/Yorimichi/WandererSword.h/.cpp` |
| Native scenario | `scenarios/adventure_moves.py` |

Effects and sound are described in [combat feedback](COMBAT_FEEDBACK.md).
