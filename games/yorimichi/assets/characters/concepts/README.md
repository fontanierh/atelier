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
Smart UV on each. In Blender the coat is aligned to the body at the shoulders and skinned with the body swap's skirt
rules first; a cloth simulation, if it is wanted, drives the coat below the hips from a low-poly proxy.
