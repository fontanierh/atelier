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
| **Eyes and light** | `sword_trainer_texture.py` + `face.json` | the texture de-lit, eye and brow pieces solid, the face's skin clean, brows and mouth redrawn (below) |
| Promote | `promote.py sword-trainer <revision>` | the blend and its records in `assets/characters/<id>/` |
| Move set | `cairo/botw.py --character <id>` | the merged move set retargeted onto the body (106 Link clips and Cairo's own 4) |

## Eyes and light: the fix almost every Tripo character needs

Tripo bakes things into a character that the game must do itself or draws differently:

- **Lighting.** The colour carries Tripo's own light: dark hair undersides, a gradient across the face, occlusion in
  every fold of the cloth. In the game the engine lights the character (with the characters' 30% emissive fill), so the
  baked light doubles up and the folds read as dirt.
- **Eyes.** Tripo models each eye as **a small mesh piece of its own**, set into a socket in the face, textured with
  a soft painted oval, a muddy brown rim and a highlight: nothing like Cairo's clean solid dark ovals. It often does the
  same for a brow. Painting the head's texture never reaches them, and new eyes drawn over them leave the old ones'
  rims showing.
- **Face drawing.** Brows, the mouth, a scar and the cheeks are scratchy pencil strokes and smudges on the skin, and
  sometimes a strand of hair is painted onto a cheek beside the real one.
- **Normal map.** Tripo's normal map embosses its own drawing: clean the colour and the old outlines come back as
  creases under any light. The game's character material uses no normal map; the review material should not either.

`sword_trainer_texture.py` fixes all of it on the promoted rig's blend (mesh, rig and clips untouched), from a small
**face spec** (`assets/characters/<id>/face.json`):

1. **Per-texel bakes** (Cycles emission, at half the texture's size to stay under the small slot's 4 GiB): every
   texel's position and normal on the body, and its **mesh piece** (the welded pieces, encoded as a colour attribute).
   Tripo's UV atlas is cut into hundreds of islands, so nothing can be painted in texture space; everything is decided
   by where a texel sits on the body.
2. **De-lighting.** Texels are grouped by colour (k-means in Lab, lightness at half weight), groups of one material
   merged (a, b within 9, lightness within 25: a lit and a shaded patch of the same skin must be one group, or
   flattening each to its own median leaves a step between them), and in each group the lightness is pulled toward its
   median, keeping 35% (`--strength`) of its departure. Hue and chroma stay.
3. **Eye and brow pieces recoloured.** The small pieces in front of the face at an eye (or on a brow in the spec) are
   recoloured solid: the eyes Cairo's eye colour, the brows the brows' colour. Tripo's own crisp ovals become the eyes.
   (Only when a character has no eye pieces does the tool draw eye discs fitted to the face instead.)
4. **The face's skin, one smooth field.** On the head's piece, within 3.5 mm of the skin's surface (so a strand
   standing in front is never touched), inside the face's outline: every texel that is not hair takes a widely
   averaged skin colour, which wipes every pencil stroke, smudge and leftover of baked light at once. Hair (the dark
   colour groups) is kept, except hair painted onto the skin itself well inside the face.
5. **Brows and mouth redrawn** from the spec: each a centreline with a thickness at each point, in fractions of the
   character's height in a front view (y to her left, z up), painted solid on the skin layer, with a band of skin round
   them to take the old scratchy edges. Round each eye the old drawing and its lashes are wiped too.
6. **Normal map** disconnected.

### Writing the face spec

Render the face straight on (`front` shots, `before-front-lit.png`), lay a grid over it (0.005 of the height a line)
and read off: each eye's centre and the half size of the whole painted drawing; each brow's centreline points and
thickness (a brow under a strand can run on under it: only the skin layer is painted); the mouth's centreline and
thickness. Kaede's is `assets/characters/sword-trainer/face.json`. Then run the tool and judge **the straight-on face
close-up and a three-quarter view, lit**, before promoting: `after-front-lit.png`, `after-face-lit.png`,
`after-body-lit.png`. A judgement made on a small body render misses everything that matters here.

### What did not work (Kaede, 2026-10-05)

- Finding the brows, the mouth and the marks automatically: a strand crossing a brow merged with it, the mouth was
  missed or flattened, a strand across the forehead was taken for a mark and painted skin. Hand-read positions in a
  small spec were reliable where every heuristic failed somewhere.
- Painting new eyes into the texture: the fragmented atlas and the half-size position bake leave ragged edges, and the
  old eye pieces' rims stay in front. Geometry discs on top of the old pieces still showed their rims.
- Smoothing the eye sockets out of the mesh: unnecessary once the eye pieces are recoloured, and it risks burying them.
- Wiping "everything dark inside the skin" (hair over the forehead went with it), and flattening the skin to one
  colour (the mouth went with it).

## Rig notes

- Tripo's biped rig (`spec: mixamo`) gives 23 bones (`Root`, `mixamorig:Hips`...) facing +X with the left on +Y, as
  Cairo's; with the 30 finger bones it is the humanoid contract, and `atelier.character.names.mixamo_aliases` renames it.
- `tripo_fingers.add_fingers` slices the hand's vertices along the hand to find four fingers and the thumb standing up
  above them. `thumb_band` (0.2 for Kaede, 0.35 for the fox hunter's claws) is the top share of the hand's height kept
  for the thumb: an index finger that sits a little high otherwise counts as the thumb and only three fingers remain.
- Poses for a character's own clips are written in its frame (`sword_trainer_rig.py pose`): each bone turns about an
  axis of the character's frame through its own head, parents first. Hinge a bow at the hips with the thighs turned
  back by the same angle, or the whole body tips.
