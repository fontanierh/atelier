# Merged move set

The committed `source/` bundle contains the motion curves used by the merged move set, their neutral
reference rig, the sword and the paraglider. The reference rig is an animation import aid with a small
marker triangle; it has no character surfaces, clothing or playable definition.

`library.py` reads these inputs directly. `export.py` bakes the motion curves and equipment into
`build/yorimichi/adventure/`; `retarget.py` authors the clips on Cairo, Modori and Kaede's own skeletons.
Each character's `adventure.toml` gives its paths and equipment fit. Cairo supplies the double jump,
bokken guard, parry and everyday gestures that complete the merged set.

`import_adventure.py` imports the reference motion samples and two props. `import_adventure_moveset.py`
imports each character's retargeted clips, copies its own base definition and writes its move record.
The source reference is never offered by the character menu.

```sh
uv run atelier build yorimichi characters.adventure unreal.adventure
uv run atelier build yorimichi unreal.cairo_adventure unreal.modori_adventure unreal.sword_trainer_adventure
```

The merged moves retain jumping, the double jump, sprinting, dodges, climbing, swimming, gliding,
sword attacks and parries. Every playable character always uses its merged move set, including in scripted and
shared sessions. The player's character switch offers only the game's own built characters.
`scenarios/adventure_moves.py` exercises those moves on Cairo.
