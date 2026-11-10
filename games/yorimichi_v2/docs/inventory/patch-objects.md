# Promoting a saved area patch to an object

Snapshot: **main `3027366ced` (2026-11-09)**. This page describes the first 31 promotion candidates and their
selection rule, not the current whole-game placement count or a list of work still to start. Current records use
recovered model IDs; `tools/migrate/object_models.py` retargets `model`/`models` in both definitions and saved
receipts without re-saving unchanged actors. [INVENTORY](../INVENTORY.md) is the current status index.

A real patch that still bundles several useful objects remains unfinished. The original one-worldwide-instance
filter below was a conservative first-batch choice, not a permanent exemption for repeated useful objects.

## Current authoring commands

Use the selected region's current `objects.toml` and hold the claim covering its complete record and package paths.
For an entry with `patch = "<V2Id>"` (or a list of patch IDs), promote the already-saved patch into its own object
record without opening the editor or changing the package bytes:

```sh
ATELIER_AGENT=OWNER uv run python games/yorimichi_v2/tools/migrate/objects.py REGION \
    --promote --only OBJECT_ID --claim TASK
```

For an entry with `split = {key = "...", at = [x, y]}`, use the normal guarded migration route. It removes that
placement from its area patches and saves it as its own actor:

```sh
ATELIER_AGENT=OWNER uv run python games/yorimichi_v2/tools/migrate/objects.py REGION \
    --only OBJECT_ID --claim TASK
```

Repeat `--only` to select more objects. `split` is an entry type, not a CLI subcommand. Runtime-group and other
manifest-writing object selections also need `--environment REGION`; a split-only selection does not.
After an interrupted save, follow the [object claim recovery steps](transport-objects.md#recovering-object-package-claims).

## Initial promotion set

`world/regions/<region>/objects.toml` entries with `patch = "<V2Id>"` take the area-patch actor `AV2ScenePatch` that already
holds exactly one object, instead of splitting a patch in the editor. The initial set contained 31 entries in six regions,
tags unique across regions (`start`, `village`, `pier`, `lake`, `swcoast`, `swterrace`; `brinecove` and `belmonte` already exist).
Each file has `data = ""` (no runtime file).

## Rule

An entry is listed only when all of these hold:

1. the key has exactly one placed instance in the source data (`world.json instances` plus `treehouse/runtime.json instances`);
2. the patch is that key's only patch in the region's `patches.json` (shadow twins live in the same patch);
3. it is a thing, not ground: terrain, water, trails, plants and edges stay area patches;
4. `model` is the record whose outputs contain the mesh package (the package whose leaf is the key; checked for every entry).

| Region | Tag | Entries | Keys |
|---|---|---:|---|
| w01-start | `start` | 4 | `HouseLot_1`, `HouseLot_2`, `House_B`, `SW_FisherHouseB` |
| w02-village | `village` | 8 | `HouseLot_4`, `HouseLot_5`, `Village_CottageA`, `Village_CottageB`, `Village_Garden`, `Village_Storehouse`, `Village_TeaHouse`, `Village_Workshop` |
| w04-pier-approach | `pier` | 1 | `HouseLot_3` |
| w06-lake-treehouse | `lake` | 11 | `Lake_Cabin`, `TH_Frame`, `TH_Trunks`, `TH_P_barrel`, `_basket`, `_crate_desk`, `_globe`, `_kamado`, `_log_table`, `_stump_kettle`, `_telescope` |
| w08-southwest-coast | `swcoast` | 5 | `SW_BoatShed`, `SW_CoconutStand`, `SW_Dock`, `SW_DryingRack`, `SW_Temple` |
| w08-southwest-terrace | `swterrace` | 2 | `SW_FisherHouseA`, `SW_StoneStairs` |

The original model references were broad adopted records. Read the current `objects.toml` model references;
the recovered per-model records on main supersede those old IDs.

## Excluded from the initial promotion batch

| Region | Key | Reason |
|---|---|---|
| w01, w02 | `House_A` | 2 placed instances world-wide (one per region); 1 in each region |
| w02, w04 | `House_C` | 2 placed instances world-wide |
| w02, w08-coast | `Torii` | 6 placed instances (1 in w02, 5 in w08-coast; w08 has 1 patch for 5 gates) |
| w04 | `Lantern` | 17 placed instances (a repeated street prop; 1 in this region) |
| w04 | `Pole_Lamp` | 7 placed instances (repeated street prop) |
| w04 | `SkatePark` | a service scenery key with no world.json placements |
| w02 | `Village_Ground`, `_Edges`, `_Details`, `_Threshold` | ground, edges and detail surfaces of the hamlet: area patches |
| w06 | `Lake_Shore`, `_Water`, `_Trail`, `_Plants` | shore, water, trail and plants: area patches |
| w06 | `ZP_Woodland` | woodland scenery of the zeppelin set |
| w06 | `TH_P_futon` (3), `TH_P_planter` (4) | several instances in one patch |
| w06 | `TH_Structure` (5 patches), `TH_Dressing` (16), `TH_P_backpack`, `TH_P_bell`, `TH_P_bookshelf` (2 each) | the key has more than one patch or instance |
| all six | every `Tree_*`, `Bush_*`, `Grass*`, `Litter`, `Rock_*`, `Pole` | scatter |

## Limits of the initial selection

- The instance count per patch is derived from the source data, not read from the actor package (binary). A patch whose
  cell-split lost or added an instance would not show here; the promote tool should check `ExpectedMembers` has one instance.
- `House_A`, `House_C` and `Torii` are single instances in their region and could be promoted if the rule is "one in this
  region"; they are excluded by the stricter "one world-wide" rule.
- The lake and tree house keys have placements at the origin (pieces carry their own bounds); the owner point comes
  from the mesh bounds, so the world.json row is not inside the region box. The patch is still the key's only one.
- `HouseLot_*` meshes are the lot around a house (grounds), not the house; the house `House_A/B/C` is a separate key.
- Model ownership and placement ownership are separate. Recovered model records resolve the earlier broad-model
  references; a saved patch still needs a genuine useful-object membership check before promotion.
