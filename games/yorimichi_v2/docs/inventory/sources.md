# Recoverable sources

Current snapshot: **main `028bc6243b` (2026-11-10, through PR #802)**. [INVENTORY](../INVENTORY.md) is the
status index. The former 1,285 source-less-record / 9,069-package total described `adc324851b`; it is not a
current backlog. The older family-by-family donor commands are retained in Git history, not a queue to rerun.

## What is already recovered

- The city batch has **1,048** generated records and accepted imports; the train batch has **67**.
- The ten-family batch has **141 meshes and 29 textures**; the Japan batch has **100 model records**.
- #792 imported the two Japan leaf instances; #794 recovered 72 Brine Cove plants/city tree residuals.
- #796 imported the 138 train textures and 321 instances through 159 records, retiring the seven old owners.
- #797 imported 21 small-family records covering 48 packages: four Hippodrome loose meshes, seven plaza/treehouse
  textures and 37 instances. These batches are merged and included in package `0adbb5ab212e`.
- `restricted.originals.json` has **6,086 original pins**, **6,768 restricted package entries**, and
  **124 open Adventure/animation package links**. Both `problems` and `open_problems` are empty at this revision.
  Restricted entries comprise 3,267 imported, 3,324 keyed, 8 embedded and 169 editor-authored packages.
- PRs #782/#783 linked the restricted originals and the keyed-clip importer code; #785 added the open links.
  These are merged. Unknown imported originals are not reclassified as Unreal-authored to close a gap.

The original 6,076-file restricted fetch was verified before the four keyed-code pins and six Adventure pins were
added. Do not describe that older fetch as verification of every later pin. The existing fetch verifies the bytes
it retrieves against the current manifest.

## What a direct-source count means

Reading canonical records at `028bc6243b` gives **7,219 records**: 1,406 adopted, 2,790 placements,
2,812 static meshes, 176 textures, 33 material-instance records and 2 maps. There are 3,021
generated-authority records. These are ownership records, not the 2,750 saved definitions in region receipts.
Nested donor `asset.toml` files inside another record's source tree are excluded, as `record_paths` requires.

**824 adopted records have neither direct `[[sources]]` nor a recipe:** 800 use the restricted manifest and
24 are public records. Three public records have the 124 Adventure/animation links above. The remaining
**21 records / 83 packages** are a classification query, not 83 missing originals; see the
[current table](exceptions.md#current-source-classification). The old 48-record residual list included the now
recovered train, plant and small-family packages. Material masters with pinned donor sources are outside this
query, so this total is not the complete master backlog either. #803/#804 hold saved follow-ups not yet on this
main checkpoint; [INVENTORY](../INVENTORY.md) keeps that distinction explicit.

An imported model needs its model, textures and applicable rig/animation inputs. Generated art needs the generator,
settings and inputs. A package genuinely authored in Unreal can be its own original. A saved package or an
ownership map alone does not establish the original of an imported asset.

## Remaining source work

- Finish source closure for the current material/settings and Hippodrome residual rows identified
  in [exceptions.md](exceptions.md). Do not rerun completed mesh imports just to change a tally.
- **Completed: Brine Cove carved tiles keep their fused original** ([PR #787](https://github.com/fontanierh/atelier/pull/787)).
  Each of the 148 carved tile records pins the fused original and a recorded triangle selection; the remainder is
  derived under `build/yorimichi_v2/` during targeted import and reproduces the accepted remainder byte-identically.
  Accepted package bytes and placements were preserved; the two untouched harbour Soft tiles stay as recovered.
- Source recovery and independently editable placements are different deliverables. Continue the useful-object
  splits even where the source has already been recovered.

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
