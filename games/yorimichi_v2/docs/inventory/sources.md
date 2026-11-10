# Recoverable sources

This guide explains source requirements and supported recovery routes. [INVENTORY](../INVENTORY.md) owns
current delivery status; [exceptions](exceptions.md#current-source-classification) owns the remaining-family
classification. The former 1,285 source-less-record / 9,069-package total described `adc324851b`; it is not a
current backlog. Older family-by-family donor commands are retained in Git history, not a queue to rerun.

## Earlier accepted source evidence

These dated batches are retained as evidence, not a complete list of today's recovered sources. Later master
and Hippodrome batches are recorded in INVENTORY and exceptions rather than a second current-status list here.

- The city batch has **1,048** generated records and accepted imports; the train batch has **67**.
- The ten-family batch has **141 meshes and 29 textures**; the Japan batch has **100 model records**.
- #792 imported the two Japan leaf instances; #794 recovered 72 Brine Cove plants/city tree residuals.
- #796 imported the 138 train textures and 321 instances through 159 records, retiring the seven old owners.
- #797 imported 21 small-family records covering 48 packages: four Hippodrome loose meshes, seven plaza/treehouse
  textures and 37 instances. These batches are merged and included in package `0adbb5ab212e`.
- `restricted.originals.json` has **6,086 original pins**, **6,768 restricted package entries**, and
  **124 open Adventure/animation package links**. Both `problems` and `open_problems` were empty at the
  `028bc6243b` snapshot (2026-11-10).
  Restricted entries comprise 3,267 imported, 3,324 keyed, 8 embedded and 169 editor-authored packages.
- PRs #782/#783 linked the restricted originals and the keyed-clip importer code; #785 added the open links.
  These are merged. Unknown imported originals are not reclassified as Unreal-authored to close a gap.

The original 6,076-file restricted fetch was verified before the four keyed-code pins and six Adventure pins were
added. Do not describe that older fetch as verification of every later pin. The existing fetch verifies the bytes
it retrieves against the current manifest.

## What a direct-source count means

As a historical example, canonical records at `028bc6243b` gave **7,219 records**: 1,406 adopted, 2,790 placements,
2,812 static meshes, 176 textures, 33 material-instance records and 2 maps. There were 3,021
generated-authority records. These are ownership records, not the 2,750 saved definitions in region receipts.
Nested donor `asset.toml` files inside another record's source tree are excluded, as `record_paths` requires.

The current query and counts live only in [exceptions](exceptions.md#current-source-classification). It excludes
records whose outputs have restricted or Adventure/animation source routes. A remaining row is a classification
question, not a claim that each package lacks originals. Conversely, a generator record with pinned source files
can still lack inputs or an accepted import, so this query is not the complete recovery backlog. Completed train,
plant, small-family and master batches must not be restarted from older residual lists.

An imported model needs its model, textures and applicable rig/animation inputs. Generated art needs the generator,
settings and inputs. A package genuinely authored in Unreal can be its own original. A saved package or an
ownership map alone does not establish the original of an imported asset.

## On-demand source work

- Migration is complete by owner decision (2026-11-10). For a requested edit, find the selected model's owning
  record and recoverable inputs; consult [exceptions.md](exceptions.md) for its source classification.
  Preserve accepted imports and original sources.
- **Completed: Brine Cove carved tiles keep their fused original** ([PR #787](https://github.com/fontanierh/atelier/pull/787)).
  Each of the 148 carved tile records pins the fused original and a recorded triangle selection; the remainder is
  derived under `build/yorimichi_v2/` during targeted import and reproduces the accepted remainder byte-identically.
  Accepted package bytes and placements were preserved; the two untouched harbour Soft tiles stay as recovered.
- Source recovery and independently editable placements are different deliverables. Further useful-object
  splitting is on demand for the selected edit. Before changing generated geometry, follow the
  [independent-model workflow](../../../../docs/WORLD_BUILD_PRACTICES.md#make-a-model-independent-before-editing-it).

## Supported routes

Fetch restricted packages and originals through their pinned stores; their bytes remain outside public Git:

```sh
V2_RESTRICTED_SOURCE=DIR uv run python games/yorimichi_v2/tools/restricted/fetch.py fetch
V2_RESTRICTED_ORIGINALS=DIR uv run python games/yorimichi_v2/tools/restricted/originals.py fetch
uv run python games/yorimichi_v2/tools/restricted/originals.py check
```

For a generated record, use its recorded targeted importer (`tools/import/run.py ID --plan`, then the claimed
import when inputs changed). A normal V2 build validates and compiles; it does not recover or regenerate content.
An import is accepted only after the caller validates its receipts and bytes. Commit its sources, record,
packages and receipt together. Reuse successful evidence; run focused checks only for changed behavior.

The donor remains a source reference. Its retired test suites stay disabled. Do not use an old donor command
list as a reason to regenerate already accepted V2 content.
