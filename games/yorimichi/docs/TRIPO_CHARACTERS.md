# Tripo characters

How a new character goes from a concept to a rigged, animated game body through Tripo, and the clean-up a Tripo model
almost always needs before it looks right in Yorimichi: **its eyes and its baked-in lighting**. Kaede, the sword trainer
(`assets/characters/sword-trainer`, [SWORD_TRAINER.md](SWORD_TRAINER.md)), is the worked example; the fox hunter and
Cairo's outfits went through the same stages ([FOX_HUNTER_ANIMATION.md](FOX_HUNTER_ANIMATION.md),
[BODY_SWAP_GUIDE.md](BODY_SWAP_GUIDE.md)).

Every stage writes a revision folder in the archive (`YORIMICHI_ARCHIVE`, `assets/characters/tools/_archive.py`); only
the approved revision comes into the repository (`promote.py`). Paid calls go through `atelier.ai.ledger`; Tripo's
client (`atelier.ai.tripo_asset`) refuses inputs whose hashes are not in an approval file and never resubmits an
uncertain POST. Blender stages run under the guard (`python -m atelier.safety.guarded --small 3 ...`).

## The stages

| Stage | Tool (Kaede's) | Output |
| --- | --- | --- |
| References | `sword_trainer_refs.py` | Cairo rendered front (T-pose) and three-quarter, the style reference |
| Concept | `sword_trainer_pipeline.py front` | three Sunburst front T-pose candidates |
| Views | `sword_trainer_pipeline.py views --choice X` | back, left, right from the chosen front |
| Approval | `sword_trainer_pipeline.py approve --note ...` | `approval.json` with the four images' hashes |
| Tripo mesh | `sword_trainer_pipeline.py tripo` | P2 multiview model, textured (120 credits) |
| Clean-up | `sword_trainer_cleanup.py` | one mesh, facing +X, soles on z = 0, `cleanup.glb` and review renders |
| Tripo rig | `sword_trainer_pipeline.py rig --source cleanup.glb` | rig check, then Tripo's biped rig with Mixamo names under `Root` (25 credits) |
| Fingers and own clips | `sword_trainer_rig.py` | 30 finger bones (`tripo_fingers.add_fingers`), the character's own clips |
| **Eyes and light** | `sword_trainer_texture.py` | the texture de-lit, the face redrawn, geometry eyes (below) |
| Promote | `promote.py sword-trainer <revision>` | the blend and its records in `assets/characters/<id>/` |
| Move set | `cairo/botw.py --character <id>` | the merged move set retargeted onto the body (106 Link clips and Cairo's own 4) |

## Eyes and light: the fix almost every Tripo character needs

Tripo bakes things into its textures that the game must do itself or draws differently:

- **Lighting.** The colour carries Tripo's own light: dark hair undersides, a gradient across the face, occlusion in
  every fold of the cloth. In the game the engine lights the character (with the characters' 30% emissive fill), so the
  baked light doubles up and the folds read as dirt.
- **Eyes.** The eyes are soft painted ovals with muddy brown rims and highlights, nothing like Cairo's clean solid dark
  ovals. The brows, the scar and the cheeks are scratchy pencil strokes and smudges.
- **Normal map.** Tripo's normal map embosses its own drawing: repaint the eyes and their old outlines come back as
  creases under any light. The game's character material uses no normal map; the review material should not either.

`sword_trainer_texture.py` fixes all three on the promoted rig's blend, mesh, rig and clips untouched:

1. **Every texel's place on the body is baked** (Cycles emission bakes of position and normal, at half the texture's
   size to stay under the small slot's 4 GiB), because Tripo's UV atlas is cut into hundreds of islands: nothing can be
   painted in texture space.
2. **De-lighting.** Texels are grouped by colour (k-means in Lab, lightness at half weight, so a shadowed and a lit
   patch of the same cloth fall together), and in each group the lightness is pulled toward the group's median,
   keeping 35% (`--strength`) of its departure. Hue and chroma stay. The face's line work (mouth, nose, brows: texels on
   the front of the head darker than the skin but lighter than the hair) is put back as it was, or the mouth fades away.
3. **The face in a front view.** The texels of the front of the head are laid out at 0.6 mm a cell, each cell showing
   its **frontmost** sample (the lightest sample instead shows skin under hair strands, and the strands then look like
   marks), empty cells filled from their neighbours (the bake is sparser than the cells). The eyes are the pair of
   roundish dark blobs enclosed by skin, mirrored about the middle.
4. **Eyes as geometry.** Each eye becomes a thin disc fitted to the face (ray cast onto the surface, 2 mm off it),
   skinned to the head bone, in its own solid material (`Eyes`, Cairo's dark brown): crisp at any distance, where a
   texture over the cut-up atlas stays ragged. It is an upright oval (1.6 times as tall as wide) sized from the painted
   eye's dark core. Under it the whole old drawing (core, outline, lashes: out to 1.42 times the drawing's oval) is
   repainted with the skin round it diffused inward, so no flat patch shows as a halo.
5. **Marks.** Small dark or mid-dark blobs inside the skin (under 9 mm: pencil strokes, the scratch between the brows,
   a sketchy scar, temple hatching) are wiped to skin; brows, the mouth and the nose are kept, and anything larger (a
   strand of hair over the forehead) is left alone.
6. **Normal map** disconnected.

Look at `before-*` and `after-*` (face and body, lit and as albedo), `face-found.png` (what the front view saw: skin
green, dark red, mid-dark yellow) and `face-map.png` (the eyes red, the brows blue, the marks yellow) before promoting.
`texture.json` records the eyes' size and place, the colour groups and the counts.

### Pitfalls met on the way

- Wiping every dark blob inside the skin took hair strands over the forehead with it: only small blobs are marks.
- Flattening all the skin to one colour erased the mouth; the de-light alone keeps it.
- Repainting the eye rings everywhere but over "hair" (the darkest texels) skipped Tripo's dark eye outline, which is as
  dark as hair: the band right round the eye is repainted whatever its colour.
- Sizing the disc from the whole drawing made round eyes; the width comes from the dark core.
- The face mask must reach the sides of the face (normals more than 0.05 toward the front), or the outer corners of the
  old eyes stay.
- A full-resolution bake (4096) went over the small slot's 4 GiB; the colour work is done in row bands.

## Rig notes

- Tripo's biped rig (`spec: mixamo`) gives 23 bones (`Root`, `mixamorig:Hips`...) facing +X with the left on +Y, as
  Cairo's; with the 30 finger bones it is the humanoid contract, and `atelier.character.names.mixamo_aliases` renames it.
- `tripo_fingers.add_fingers` slices the hand's vertices along the hand to find four fingers and the thumb standing up
  above them. `thumb_band` (0.2 for Kaede, 0.35 for the fox hunter's claws) is the top share of the hand's height kept
  for the thumb: an index finger that sits a little high otherwise counts as the thumb and only three fingers remain.
- Poses for a character's own clips are written in its frame (`sword_trainer_rig.py pose`): each bone turns about an
  axis of the character's frame through its own head, parents first. Hinge a bow at the hips with the thighs turned
  back by the same angle, or the whole body tips.
