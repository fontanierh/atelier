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
