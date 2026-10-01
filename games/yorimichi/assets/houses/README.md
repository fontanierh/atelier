# House art

The concept paintings behind the [houses on the main road](../../world/regions/houses/README.md). Each image is a
compact JPEG copy of the PNG the image model returned; the full-size originals stay outside the repository
(`build/yorimichi/houses/originals/`).

| File | What it shows |
| --- | --- |
| `concepts/street.jpg` | A downhill lot seen from the road: stone kerb and clipped hedge, the gate with stepping stones to a gabled entrance porch, the engawa, ishigaki down the side, the garden corner with a stone lantern, pine and maple. |
| `concepts/variants.jpg` | The three houses side by side: tiled hip-and-gable roof, thatched farmhouse with a woodpile lean-to, two storeys with a pent roof and balcony. |
| `concepts/uphill.jpg` | An uphill lot cut into the bank: steps up through the gate, the hedge on a stone kerb, the bank behind. |

All three are `gpt-image-2.5-sunburst`, quality high, 1536 x 1024, through `/v1/images/edits` with two playtest
screenshots of the game as style references (a roadside house seen from the road and beside the uphill bank).
Each painting has its prompt (`*.prompt.txt`) and its provenance (`*.provenance.json`): model, quality, size, the
reference images and their hashes, token usage, the hash of the returned PNG and how the JPEG was made. A provenance
file is written with status `submitted` before the call and completed when it returns.

## Making them again

    uv run python games/yorimichi/tools/house_concepts.py [--only street] [--again street] [--dry-run]

The key comes from `OPENAI_API_KEY` (or the ignored `.env`) and is never printed. The two reference screenshots are
not in git: put them in `build/yorimichi/houses/refs/` as `playtest-road-house.webp` and `playtest-bank-house.webp`.
A concept whose JPEG is here is skipped. A concept with a provenance file but no JPEG (a call that failed or never
came back) is not asked for again unless `--again` names it, so a paid call is never repeated blindly.
