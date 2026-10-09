# Cairo

Cairo is the player character: a boy 148 cm tall, in the skate outfit, carrying the merged set's sword. His source of truth
is the current revision's blend, `Cairo-Game-r18.blend` (textures packed inside), and the JSON records beside it. The
rig is the humanoid bone contract with fingers: 53 bones (23 core and 30 finger bones). His game import uses the
body and nine authored donor clips: double jump, sword guard/parry/recoil, interact, wave and the three sitting clips.
`adventure.toml` lists these clips; all other movement and combat come from the merged set.

## Build

```sh
uv run atelier build yorimichi unreal.cairo_adventure
```

`characters.cairo` runs `export_unreal.py` once into `build/yorimichi/cairo/`, exporting his body and the nine donor
clips. The export checks the blend against `native_sha256` in `source-manifest.json` first. `unreal.cairo` imports
`SK_Cairo`, the donor clips and `DA_CairoBase`, which supplies body and framing data to the merged importer.
It creates no standalone movement or combat set. The content cleanup archives older movement/combat imports before cooking.

Cairo has no skate clips: on the board, the skate runtime's solved pose is retargeted onto him at run time. See
[skating](../../../docs/SKATE.md) and the [runtime assets](../../skate/README.md).

`characters.cairo_adventure` and `unreal.cairo_adventure` give Cairo the merged move set (the reference rig's moves with his own double jump),
which he uses in every game session. `../adventure/retarget.py` retargets the reference rig's clips onto him, as
`adventure.toml` lays out, using `export_unreal.prepare` for his rig. His base export supplies the body and donor clips;
it is never a separate playable move set. See [the merged move set](../adventure/README.md).

## Files

| File | Contents |
| --- | --- |
| `Cairo-Game-r18.blend` | mesh, rig, morphs, outfit, bokken and every clip |
| `character.toml` | id, rig, height, current revision and source, clip role count, export arguments, Unreal path |
| `source-manifest.json` | every clip role with its reference, timing and contacts; the source hashes the export checks |
| `combat-build.json` | the combat clips' build record, including each strike's aim (`contact_yaw_degrees`, `contact_distance`) |
| `locomotion-build.json` | the armed locomotion's measurements (blade angles and clearances) |
| `export_unreal.py` | the Blender export to FBX (`prepare` sets up the rig for it and for `../adventure/retarget.py`) |
| `adventure.toml` | his merged move set: its paths, the carried pieces' fit to him, and the clips of his it lends every character (`[donor]`) |
| `outfit_correctives.py` | cloth pose corrections (`set_clip`), used by the export |
| `outfits/*.toml` | outfit specs for the [body swap](../../../docs/BODY_SWAP_GUIDE.md): `skate` (the outfit in the game), `hoodie`, `gi-hakama`, `jersey-shorts`, `long-coat` |

## A new revision

Clips and outfits are authored in Blender with the tools in [`../tools`](../tools/README.md), which read and write
revision folders in the prototype archive. An approved revision comes into this folder with `promote.py`, which copies
its blend (renamed `Cairo-<stage>-rNN.blend`) and JSON records here and updates `revision` and `source` in
`character.toml`; the next build re-exports and re-imports Cairo. Animation and outfit workflows:
[Mixamo](../../../docs/MIXAMO_WORKFLOW.md), [body swap](../../../docs/BODY_SWAP_GUIDE.md),
[animation principles](../../../../../docs/ANIMATION_PRINCIPLES.md).
