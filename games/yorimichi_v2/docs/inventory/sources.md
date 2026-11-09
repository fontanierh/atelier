# Recoverable sources

Current snapshot: **main `3027366ced` (2026-11-09, PR #786)**. [INVENTORY](../INVENTORY.md) is the
status index. The former 1,285 source-less-record / 9,069-package total described `adc324851b`; it is not a
current backlog. The older family-by-family donor commands are retained in Git history, not a queue to rerun.

## What is already recovered

- The city batch has **1,048** generated records and accepted imports; the train batch has **67**.
- The ten-family batch has **141 meshes and 29 textures**; the Japan batch has **100 model records**.
- `restricted.originals.json` has **6,086 original pins**, **6,768 restricted package entries**, and
  **124 open Adventure/animation package links**. Both `problems` and `open_problems` are empty at this revision.
  Restricted entries comprise 3,267 imported, 3,324 keyed, 8 embedded and 169 editor-authored packages.
- PRs #782/#783 linked the restricted originals and the keyed-clip importer code; #785 added the open links.
  These are merged. Unknown imported originals are not reclassified as Unreal-authored to close a gap.

The original 6,076-file restricted fetch was verified before the four keyed-code pins and six Adventure pins were
added. Do not describe that older fetch as verification of every later pin. The existing fetch verifies the bytes
it retrieves against the current manifest.

## What a direct-source count means

Reading canonical records from the Git tree at `3027366ced` gives **6,223 records**: 1,433 adopted,
2,490 placements, 2,267 static meshes, 31 textures and 2 maps. There are 2,298 generated-authority records.
Nested donor `asset.toml` files inside another record's source tree are excluded, as `record_paths` requires.

**851 adopted records have neither direct `[[sources]]` nor a recipe:** 800 are restricted and 51 are open.
This is a metadata query, **not 851 missing originals**: the restricted manifest supplies a separate supported
source route, and three of the open records have the 124 Adventure/animation links above. The remaining
48 open records cover 678 packages. They include material/settings packages and residual train packages;
classify their actual origin and follow their source references before declaring a source gap or closing one.

An imported model needs its model, textures and applicable rig/animation inputs. Generated art needs the generator,
settings and inputs. A package genuinely authored in Unreal can be its own original. A saved package or an
ownership map alone does not establish the original of an imported asset.

## Remaining source work

- Finish source closure for the open material, texture, procedural plant and residual package families identified
  in [exceptions.md](exceptions.md). Do not rerun completed mesh imports just to change a tally.
- **Brine Cove carving still rewrites committed remainder GLBs on this main revision.** The source-preservation
  follow-up at `5f2d21fbd1` retains the fused original and a recorded triangle selection, then derives the remainder
  under `build/yorimichi_v2/` during targeted import. Its preparation and focused checks are complete according to
  the author; the conversion is **not merged or applied** here. It is scheduled at the stopped boundary after town9
  in [PR #787](https://github.com/fontanierh/atelier/pull/787). Accepted package bytes and placements must be preserved.
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
