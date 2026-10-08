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
| Fingers and own clips | `sword_trainer_rig.py` | 30 finger bones (`atelier.blender.tripo_fingers.add_fingers`), the character's own clips |
| **Eyes, light and noise** | `atelier.blender.tripo_character_texture` + `face.json` | flat painted colour, chips gone, eyes and brows solid, the face clean, brows and mouth redrawn (below) |
| Promote | `promote.py sword-trainer <revision>` | the blend and its records in `assets/characters/<id>/` |
| Move set | `botw/retarget.py --character <id>` | the merged move set retargeted onto the body (106 Link clips and Cairo's own 4) |

## Eyes, light and noise: the fix almost every Tripo character needs

Tripo bakes things into a character that the game must do itself or draws differently:

- **Lighting.** The colour carries Tripo's own light: dark hair undersides, a gradient across the face, occlusion in
  every fold of the cloth. In the game the engine lights the character (with the characters' 30% emissive fill), so the
  baked light doubles up and the folds read as dirt.
- **Noise.** Pencil scratches and smudges everywhere, and chips of the wrong colour where two colours meet: skin on a
  strand of hair, hair flecks at the temples, skin on a collar, a fleck of hair on a headband. Tripo's UV atlas is cut
  into hundreds of charts, so one chip is often several pieces of texture far apart.
- **Eyes.** Tripo models each eye as **a small mesh piece of its own**, set into a socket in the face, textured with a
  soft painted oval and a muddy brown rim. It often does the same for a brow, and the socket's walls carry the old
  eye's brown paint (a line over each eye once the eye is fixed).
- **Hair.** Tufts at the nape and side locks are small pieces of their own, often partly painted skin.
- **Face drawing.** Brows, the mouth, lashes and the cheeks are scratchy pencil strokes on the skin.
- **Normal map.** Tripo's normal map embosses its own drawing: clean the colour and the old outlines come back as
  creases under any light. The game's character material uses no normal map; the review material should not either.

The platform's [`tripo_character_texture.py`](../../../platform/studio/atelier/blender/tripo_character_texture.py)
fixes all of it on the rig's blend (mesh, rig and clips untouched), from a small **face spec**
(`assets/characters/<id>/face.json`), in three stages so each fits the small slot's 4 GiB:

```sh
# raster (Blender): the mesh in texture space -> <out>/work/raster.npz, pixels.npy
blender -b --python-exit-code 1 --python platform/studio/atelier/blender/tripo_character_texture.py -- --input <Name>-Rig-rNN.blend --output <out> --stage raster
# paint (plain Python, the repo's venv): the colour -> work/colour.npy, paint.json
python platform/studio/atelier/blender/tripo_character_texture.py --input ... --output <out> --face <id>/face.json --stage paint
# pack (Blender): the texture packed into <out>/<Name>-rMM.blend, renders, source-manifest.json, texture.json
blender -b --python-exit-code 1 --python platform/studio/atelier/blender/tripo_character_texture.py -- --input ... --output <out> --face ... --stage pack
```

Run each under the guard (`python -m atelier.safety.guarded --small 3 ...`; paint peaks near 3 GiB). Raster once;
paint and pack again after each change to the spec or the options (8 minutes for a 4096 texture).

1. **Raster.** Every texel's place on the body, its facing, its **mesh piece** (the welded parts: head, each eye, each
   lock, the clothes) and its **UV chart**, from the mesh's UV triangles at the texture's full size.
2. **Colour groups.** k-means (16) in Lab, lightness at half weight; each texel then takes the group most of its
   neighbours in its own chart have (7 x 7, twice: specks and pencil strokes go, nothing is voted across a seam), and
   the group most common round it in 3D within its piece (cells of 0.0008 of the height: chips the atlas cut up).
3. **Regions.** The groups of each piece merged greedily, the closest pair first by the merged colours, while a and b
   are within 9 and lightness within `--merge-l` (10). Lower merges a design into the cloth round it (Kaede's shin
   straps are 10 lighter than her trousers); higher splits lit and shaded cloth into patches.
4. **Chips.** Each region's texels joined into patches within a chart and across its seams (edge texels of other charts
   at the same place on the body). A patch under `--chip` (3000) texels and `--chip-size` (0.04 of the height) across,
   with half its border one other region, becomes that region; three passes. A long thin patch (a strap, a seam line)
   stays. Then the regions' edges are rounded in each chart (the 3D vote leaves them stepped).
5. **Flat colour.** Each region its median colour, keeping `--shading` (0.3) of its broad lightness (a 25-texel blur):
   folds still read, Tripo's light and noise do not.
6. **The face** (from the spec):
   - the eye pieces (small pieces in front at an eye) painted as eyes: a dark pupil, an iris (`colours.iris`) and a
     catchlight up and to the outside; a brow piece solid in the brow colour;
   - small pieces round the head that are mostly hair, or behind the head (nape tufts): all hair;
   - the sockets' walls round the eye pieces: skin;
   - dark paint inside the face on the skin's surface (a cubic fit of depth over the face, so a strand standing in
     front is kept), below the hairline: skin; the old lashes above each eye: skin;
   - the spec's brows and mouth drawn anti-aliased on the skin.
7. **Pack.** Colour carried 8 texels past every chart's edge (no black at the seams), the normal map disconnected,
   renders: the head from seven angles (`after-front`, `q_left`, `q_right`, `side_left`, `side_right`, `back`,
   `above`) and the body front and back, 1200 px.

### Writing the face spec

Render the face straight on (`before-front.png`), lay a grid over it (0.005 of the height a line) and read off, in
fractions of the height (y to her left, z up): each eye's centre, the half size of the old painted drawing
(`drawing_half`) and of the eye (`disc_half`); each brow's centreline points and thickness; the mouth's centreline and
thickness; the colours of the eyes, iris, brows and mouth. Kaede's is `assets/characters/sword-trainer/face.json`.

### Judge it close

**Look at the head close-ups from every angle at full size, then zoom in 2-3x on the temples, the ears, the nape, the
collar and the face-framing strands**, and at the body front and back against `before-body.png` (a design detail lost
in the merge shows there). A small body render hides every defect that matters; most of Kaede's took four review
rounds to find.

### What did not work (Kaede, 2026-10-05)

- Finding the brows, the mouth and the marks automatically: a strand crossing a brow merged with it, the mouth was
  missed. Hand-read positions in a small spec were reliable where every heuristic failed somewhere.
- Painting new eyes into the texture, or discs over Tripo's eye pieces (their rims still showed); smoothing the
  sockets out of the mesh (exposed the brown walls).
- Pulling each colour group's lightness toward its median (de-lighting): the noise stays. Flat region colour is what
  reads clean.
- Merging groups transitively (skin to shaded skin to brown to hair became one grey region): merge greedily by the
  merged colours.
- A majority vote in texture space across seams (votes in another body part's colour), a wide one (17 x 17: it erased
  the shin straps), and 3D cells coarser than 0.001 (staircase edges).
- Geometric rules for the hair (a band of the head under the jaw, "in front of the cheek's fit"): each painted a
  rectangle or a cheek. Patches judged by their own border (step 4) fixed the strands, temples and collar.

## Rig notes

- Tripo's biped rig (`spec: mixamo`) gives 23 bones (`Root`, `mixamorig:Hips`...) facing +X with the left on +Y, as
  Cairo's; with the 30 finger bones it is the humanoid contract, and `atelier.character.names.mixamo_aliases` renames it.
- `atelier.blender.tripo_fingers.add_fingers` slices the hand's vertices along the hand to find four fingers and the thumb standing up
  above them. `thumb_band` (0.2 for Kaede, 0.35 for the fox hunter's claws) is the top share of the hand's height kept
  for the thumb: an index finger that sits a little high otherwise counts as the thumb and only three fingers remain.
- Poses for a character's own clips are written in its frame (`sword_trainer_rig.py pose`): each bone turns about an
  axis of the character's frame through its own head, parents first. Hinge a bow at the hips with the thighs turned
  back by the same angle, or the whole body tips.
