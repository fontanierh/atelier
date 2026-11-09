# Brine Cove split batch 1: saved small props

Snapshot: **main `3027366ced` (2026-11-09)**. Batch 1 is implemented and its **11 useful small-object placements
are saved**, not merely planned. The Nightjar/sloop work is separate and now saved too; see
[brinecove-ships.md](brinecove-ships.md). Current overall status is [INVENTORY](../INVENTORY.md).

## Current batch contents

The authoritative geometry table is `world/regions/w09-brinecove/split-batch1.json`, with 12 part records for
11 objects (the market well has a separate Soft part). It pins exact triangles, bounds, material names and source
hashes rather than relying on a duplicated table in this document.

| Object | Part triangles in the current expectation |
|---|---:|
| shipyard-yard | 9,558 |
| crane-west / crane-east | 168 each |
| fish-shed | 468 |
| net-rack-west / net-rack-east | 672 each |
| cannon-west / cannon-east | 2,732 each |
| quay-anchor | 2,052 |
| market-well | 128 hard + 44 Soft |
| market-auction-block | 132 |

The earlier 410-triangle west crane and 678-triangle fish shed incorrectly included neighbouring palms. The
corrected exclusion zones return each whole palm to its tile. Their obsolete Soft parts are retired; the two
remaining harbour Soft fragments still need saved placements in the follow-up checkpoint.

## Split and ownership

`tools/migrate/brinecove_split.py` partitions donor GLB triangles into the chosen useful object and the remainder.
It preserves vertex positions, normals, UVs and material identities, and checks the complete triangle partition.
Parts retain the tile's world-space frame; saved placements use the same transform and render/collision flags.
Hard parts keep complex collision, Soft parts have none. Slot tables are rebuilt when a changed source has a
new material count; the importer no longer assumes every carved source keeps the original slot table.

On this main revision, `brinecove_split_apply.py` writes carved part/remainder sources into their asset records.
That source mutation is a recorded remaining defect. The prepared source-preservation follow-up keeps the fused
original plus a selection and derives output under `build/yorimichi_v2/`; it has not yet been applied here.
See [sources.md](sources.md). Do not mistake the existing record for complete recoverability of the fused original.

## Source form of a carved tile (derived remainder)

A carved tile never commits its remainder. Its record keeps the fused original as its first pinned source (the bytes
`tools/migrate/recover.py` produced from the donor generator, before any carve), and `src/SM_BC_<tile>.carve.json` beside
it lists the triangles the remainder keeps and removes (half-open ranges of triangle ordinals). The `[derive]` table of
`asset.toml` names the two (`tools/content/carve.py`). The targeted import derives the remainder under
`build/yorimichi_v2/derived/<record>/` from the two and imports it; the import fingerprint covers both hashes. A normal build
never writes it.

The split tools write only a tile's selection and its `[[sources]]`; the cut-out parts keep their own committed part GLB as
before. Tile records in the old form (remainder committed as the source) are converted once by
`tools/migrate/brinecove_sources.py --check` (proof, no claim) and `--claim TASK` (write). The conversion takes the original
from the record's first commit in git history (read from the local LFS store, checked against the first pin), finds the kept
triangles by matching the committed remainder to the original, and requires the derived remainder to be byte-identical
(sha256) to the committed one. The record's import stays current, so no package is rewritten and no placement moves.

## Claimed apply/import/retire/save sequence

`DONOR` names the donor's `build/yorimichi` folder, read-only. Reuse accepted imports and existing focused evidence;
run only the changed selection. One claim must cover all printed paths and scopes, including both the Brine Cove
region and the island environment for actor saves.

```sh
bc_split() { uv run python games/yorimichi_v2/tools/migrate/brinecove_split_apply.py "$@"; }
bc_split plan --donor DONOR
bc_split paths --donor DONOR --json
bc_split apply --donor DONOR --claim TASK
# Import the explicit changed record IDs from the plan, in the existing warm queue.
uv run python games/yorimichi_v2/tools/import/run.py ID... --claim TASK --batch 8
bc_split check --records --donor DONOR
bc_split retire --donor DONOR --claim TASK
uv run python games/yorimichi_v2/tools/migrate/objects.py region/w09-brinecove --environment region/w00-island --claim TASK --only IDS
bc_split check --donor DONOR
```

Apply checks the complete touched set before mutation and journals its writes under the claim. Retire binds to the
persisted applied selection, current accepted import fingerprints and package hashes; it must not use another
selection's receipts. Pending stale-part and resave work survives separate commands. Recovery validates the
persisted write paths/scopes under the active claim before changing files; an unauthorized recovery preserves its
journal. Legacy journals without scope metadata need their original scope set recovered explicitly.

Only one removal selection may be outstanding in `split-batch1.json`. Finish that selection before replacing it.
The town planner uses its own manifests and two-stage retirement; see [brinecove-market.md](brinecove-market.md).
Accepted native receipts, saved placements and drawn-once checks are distinct evidence. Reuse existing captures and
checks; investigate a changed or broken result with the smallest focused check, not a new benchmark campaign.

## Still outside this batch

Signal mast, the stone shipyard slip welded into the quay, and remaining useful objects in fused town/harbour
geometry are not completed merely by saving the 11 objects above. Market and town splits use the donor's actual
constructor boundaries instead of radius selection. Each ship now combines its rig with its own hull instance;
the rig-only triangle counts do not include the hero hull's deck and guns.
