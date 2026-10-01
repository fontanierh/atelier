# Cairo

Cairo is the player character: a boy 148 cm tall, in the skate outfit, with a bokken he can draw. His source of truth
is the current revision's blend, `Cairo-Game-r18.blend` (textures packed inside), and the JSON records beside it. The
rig is the humanoid bone contract with fingers: 53 bones (23 core and 30 finger bones). The blend carries 56 clip
roles: 25 unarmed (locomotion, crouch, jumps, dashes, dodge, roll, sitting, climbing, gliding, turns, interact,
wave), 12 combat clips (guard, draw, sheath, three strikes, charge, parry, combo) and 19 armed clips that keep the
sword in hand through locomotion, crouch, jumps, dashes, sitting and the roll.

## Build

```sh
uv run atelier build yorimichi characters.cairo unreal.cairo
```

`characters.cairo` runs `export_unreal.py` in Blender three times into `build/yorimichi/cairo/`: the mesh, skeleton,
bokken and every clip role (`export.json`), the combat clips with the sword (`export-sword.json`), and the armed clips
(`export-armed.json`). The export checks the blend against `native_sha256` in `source-manifest.json` first.
`unreal.cairo` imports the result into `/Game/Cairo` in three layers: `import_cairo.py` (`SK_Cairo`, the `A_*` clips,
`BS_Locomotion`, `BS_Crouching`, `DA_Cairo`), `import_cairo_sword.py` (the `A_Sword*` combat clips, `SM_Bokken`, the
sword fields of `DA_Cairo`) and `import_cairo_armed.py` (`BS_SwordLocomotion`, `BS_SwordCrouching`, the armed clips).

Cairo has no skate clips: on the board, the skate runtime's solved pose is retargeted onto him at run time. See
[skating](../../../docs/SKATE.md) and the [runtime assets](../../skate/README.md).

## Files

| File | Contents |
| --- | --- |
| `Cairo-Game-r18.blend` | mesh, rig, morphs, outfit, bokken and every clip |
| `character.toml` | id, rig, height, current revision and source, clip role count, export arguments, Unreal path |
| `source-manifest.json` | every clip role with its reference, timing and contacts; the source hashes the export checks |
| `combat-build.json` | the combat clips' build record, including each strike's aim (`contact_yaw_degrees`, `contact_distance`) |
| `locomotion-build.json` | the armed locomotion's measurements (blade angles and clearances) |
| `export_unreal.py` | the Blender export to FBX |
| `outfit_correctives.py` | cloth pose corrections (`set_clip`), used by the export |
| `outfits/*.toml` | outfit specs for the [body swap](../../../docs/BODY_SWAP_GUIDE.md): `skate` (the outfit in the game), `hoodie`, `gi-hakama`, `jersey-shorts`, `long-coat` |

## A new revision

Clips and outfits are authored in Blender with the tools in [`../tools`](../tools/README.md), which read and write
revision folders in the prototype archive. An approved revision comes into this folder with `promote.py`, which copies
its blend (renamed `Cairo-<stage>-rNN.blend`) and JSON records here and updates `revision` and `source` in
`character.toml`; the next build re-exports and re-imports Cairo. Animation and outfit workflows:
[Mixamo](../../../docs/MIXAMO_WORKFLOW.md), [body swap](../../../docs/BODY_SWAP_GUIDE.md),
[animation principles](../../../docs/ANIMATION_PRINCIPLES.md).
