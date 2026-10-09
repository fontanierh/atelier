# Sword combat

Cairo, Modori and Kaede use the merged Adventure move set for sword combat. The retained sword is fitted to each
character's hands and back by its `adventure.toml`. Cairo lends the set his two-handed guard stance, parry and recoil;
the other combat motions come from the committed Adventure motion bundle.

```sh
uv run atelier build yorimichi unreal.cairo_adventure unreal.modori_adventure unreal.sword_trainer_adventure
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

## Implementation

| What | Where |
| --- | --- |
| Action clips, timings and parameters | `assets/characters/adventure/moves.toml` and `moves.py` |
| Donor clips and their timing windows | `assets/characters/cairo/adventure.toml` |
| Per-character retargeting and equipment fit | `assets/characters/adventure/retarget.py`, `unreal/Scripts/import_adventure_moveset.py` |
| Combo, charge, guard, parry, hits and blade sweeps | `unreal/Source/Yorimichi/AdventureMoveSetCombat.cpp` |
| Network defence and reactions | `AdventureMoveSetDefence.cpp`, `AdventureMoveSetReaction.cpp` |
| Player health and training post | `unreal/Source/Yorimichi/WandererSword.h/.cpp` |
| Native scenario | `scenarios/adventure_moves.py` |

Effects and sound are described in [combat feedback](COMBAT_FEEDBACK.md).
