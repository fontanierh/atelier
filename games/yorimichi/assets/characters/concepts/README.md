# Character concepts

Concept sheets for new playable characters, painted by Sunburst with Cairo's approved renders as the style reference.
Nothing here is modelled yet.

## The cool rival

A second playable hero beside Cairo: a lean, dark-haired young man of about eighteen in the mould of the cool,
mysterious anime rival. He is calm and nonchalant, and quietly the smartest person in the room. A long fringe hides one
eye and his pill eyes are half-lidded. He stands about 5 heads tall to Cairo's 4, so he is not another child (the lore
avoids a child-versus-adult framing). Each take ties him to a different side of the [lore](../../../docs/LORE.md) and
gives him a bell-metal weapon with a different move set from Cairo's sword:

| Take | Who he is | Weapon |
| --- | --- | --- |
| [`came-back`](came-back.jpg) | came out of the forest sinkhole alone after six weeks; knows what the spirits offered | knotted rope with a bell-metal weight |
| [`bell-reader`](bell-reader.jpg) | monastery dropout, the only one on the coast who can read the bell inscription | staff topped with a caged bell |
| [`guild-defector`](guild-defector.jpg) | assayer's apprentice who walked out with the ledger proving the guild cut the lock | short bell-metal blade, reverse grip |
| [`ferry-courier`](ferry-courier.jpg) | coastal courier who hears every rumour and knows which one is true | oil-paper umbrella with a bell-metal tip |

Whichever take is chosen is modelled for the humanoid bone contract (53 bones, as Cairo), so Cairo's clip library
retargets onto him; his own weapon clips come after.

## Painting again

```sh
YORIMICHI_ARCHIVE=<prototype archive> uv run python games/yorimichi/tools/character_concepts.py [--only slug] [--dry-run]
```

The archive holds Cairo's r05 captures; only their names and hashes are recorded. Each sheet keeps its prompt
(`*.prompt.txt`) and the ledger record of the paid call (`*.provenance.json`). A take with a provenance file is never
sent again: rename its files to `<slug>.rejected-N.*` to paint it again. Full-size originals stay in
`build/yorimichi/characters/concepts/originals/`.

## The chosen take: came-back in T-pose

`came-back` is the one going to 3D, without the rope and bell weight. [`came-back-tpose/`](came-back-tpose) holds
the four Tripo multiview references (front, back, left, right), painted by
[`came_back_tpose.py`](../../../tools/came_back_tpose.py): the front from single-figure crops of the sheet, the
other three from the front, one figure per image as for Kaede ([Tripo characters](../../../docs/TRIPO_CHARACTERS.md)).
The full-size PNGs to upload to Tripo are in `build/yorimichi/characters/concepts/came-back-tpose/`.

The knee-length coat is his look, but it breaks the Tripo workflow's rule that nothing hangs below the hips except
the trousers: after rigging, expect the coat skirt to need its own weights or cloth bones so it does not stretch
between the legs.

### In two parts: the body and the coat

`came_back_tpose.py parts` edits each full view twice: `body-<view>` is him without the coat (a black long-sleeved
high-neck top under it) and with a blank face, so the eyes, brows and mouth are painted later on clean skin rather
than fought out of Tripo's eye pieces; `coat-<view>` is the coat alone on an invisible body, hollow at the collar and
cuffs, its lining seen through the open front. The body views match the full views pixel for pixel. The coat views
came back at slightly different sizes (the right one about 9% shorter), so `collect` scales each to the front's
height (`coat-normalisation.json`) and gathers the Tripo Studio upload folder,
`build/yorimichi/characters/concepts/came-back-tpose/tripo/{full,body,coat}/{front,back,left,right}.png`.

Two Tripo generations, both as game-ready quad meshes (the API runs used `quad` with a 12,000 face limit), then
Smart UV on each. In Blender the coat is fitted onto the rigged body and its skirt simulated as cloth (below).

### The models: texture, face and coat

Tripo Studio built both parts (Smart Mesh, then Smart UV; the body also rigged, a Mixamo skeleton). The files stay in
`build/yorimichi/characters/came-back/` (`tripo-body-r01/`, its `rigged/` copy, `tripo-coat-r01/`).

[`came_back_texture.py`](../tools/came_back_texture.py) cleans the body texture and paints the face. Every texel is
placed on the body in 3D, so it works on any UV layout. On the head, a texel whose colour disagrees with the surface
round it (skin colour on a lock, hair colour or a thin dark line on the cheek) takes that surface's colour. The vote is
taken within the texel's own UV island, so a lock lying over the cheek keeps its hair. Tripo's baked shadow behind the
ears and under the hair stays. The eyes, brows and mouth are then drawn from the `FACE` table, measured on the concept
and projected from the front onto the skin only. `--variant redo` is the comparison: Tripo's colours on the head are
dropped, only the labels (skin, hair, the white streak, the collar) stay, and the skin and hair are painted fresh with
soft shading from the geometry (`basecolor-redo.png`). The rigged FBX has the same mesh and UVs, so the texture
applies to it.

[`came_back_coat.py`](../tools/came_back_coat.py) fits the coat: scaled until its cuffs sit on the wrist bones
(0.766), centred on the chest, then pushed 4 mm clear of the body. It takes the body's bone weights, the skirt
blending to the hips below 0.50 m, and a `cloth_pin` group (the torso and the sleeves pinned, the skirt free below
0.44 m). Its `sim` stage drives the skeleton through a short take (arms down, a few steps, a quick turn) and bakes the
skirt as cloth with the body colliding, gravity scaled for a 1 m model. The Blender cloth is a look check; in Unreal
the same pin weights paint a Chaos Cloth mask, or the skirt gets bones.
