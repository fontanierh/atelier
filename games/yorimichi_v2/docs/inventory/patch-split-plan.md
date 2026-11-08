# Splitting migrated scenery into per-object actors

Survey of how the static scenery that `tools/migrate/run.py` saved as `AV2ScenePatch` actors can be split so every useful
object has its own editing boundary, as the Brine Cove wreck now has. Counts come from each region's `patches.json`
(one entry per saved patch, with its source key) and `actors.verified.json` (one file per actor package), and from the
runtime data the migration read (`Content/Data/world.json`, `hidamari/city.json`).

## What a patch is

`UV2Migration::MigrateStaticScenery` (`V2ScenePatch.cpp`) builds the original `AJapanWorld::Load` scenery in the
editor and saves it. For each runtime group `Group` (a hierarchical instanced mesh with one mesh, `MigrationKeys[Group]`
as its source key) and each owner region, it sorts the group's instances into square cells of the region's patch size
(128 m; 32 m for w01 and w04, `region.toml patch_m`) by the instance's owner point, and saves one `AV2ScenePatch` per cell:

- one patch = one (owner region, source key, mesh, role `near` or `backdrop`, cell). `V2Id` hashes exactly those.
- its components: one instanced component holding that cell's transforms of that one mesh, plus a shadow-twin component
  when the group has one. So a patch holds **one kind of thing, many copies**, not many different objects. A migrated
  region has about as many patches as (kinds x cells it touches).
- `ExpectedMembers` lists one `"<mesh path>|<sorted component tags>|<instance count>"` per component.
  `Members()` recomputes it, and a mismatch fails the world's readiness.

Whole-world pieces (`SkyDome`, `Sea`, the island's terrain, road, lane, guardrail, wires, far hills) are separate:
island pieces come from `Content/Data/terrain/island.json` and are single static actors already.

## Identity: what survives in the saved patch

| Layer | Identity | Survives in the saved patch? |
|---|---|---|
| Kind of object | `SourceKey` (the `world.json` instance key, or a Load key such as `HD_Shop_12`, `Village_Storehouse`, `SW_Temple`, `TH_P_bell`) | yes: the actor's `SourceKey`, its label `<region>:<key>:<role>:<id>` and the `V2Id:` / `V2Region:` tags |
| Mesh | the mesh path | yes: in `ExpectedMembers` and on the component |
| One physical object | the instance transform (position, yaw, scale) | yes, as the instance transform; nothing names it. Where a key has one instance, the patch is the object. Hidamari buildings are matched by position against `city.json buildings[] {asset, position, yaw}` |
| Plants and scatter | none; the instance index | not an object: stays an area patch |

**Identity rule: an object is (region, source key, mesh) restricted to instances that the key's source data lists as a
single placed thing (a key with one instance, or one entry of a building list). Terrain, roads, ground, wires and every
tree, bush, grass, litter, rock and pole key stay area patches.** The component carries no per-instance name, so a split
must record the object's transform and give the new actor the same deterministic `V2Id` shape
(`StableId({region, key, mesh, "object", index-or-position})`).

## Counts per migrated region

Patches and distinct source keys are from `patches.json`. "Object keys" are the keys left after dropping scatter, terrain
and backdrop keys (`Tree_*`, `Bush_*`, `Grass*`, `Litter`, `Pole*`, `Rock_*`, `HD_Terrain`, `HD_NorthMountains`,
`HD_NorthRock*`, `FarHills`, `Sea`, `SkyDome`). Components are one per patch plus its shadow twin, so between 1x and 2x the patch count.

| Region | Patches | Source keys | Object keys | Example object keys |
|---|---:|---:|---:|---|
| w00-island | 3 | 3 | 0 | `SkyDome`, `Sea`, `HD_Sea` (whole-world, stay) |
| w01-start (32 m) | 253 | 28 | 6 | `House_A`, `House_B`, `HouseLot_1`, `HouseLot_2`, `SW_FisherHouseB`, `Lantern` |
| w02-village | 119 | 41 | 18 | `Village_Storehouse`, `Village_CottageB`, `Village_Workshop`, `Village_TeaHouse`, `Torii`, `House_C`, `HouseLot_4` |
| w03-mega | 66 | 18 | 2 | `Mega_Trail` |
| w04-pier-approach (32 m) | 256 | 26 | 4 | `House_C`, `HouseLot_3`, `Lantern`, `SkatePark` |
| w05 forest (5 regions) | 3741 | 17 to 22 each | 2 | `HD_NorthApproach`, `HD_NorthParkTrail`; the rest is forest scatter |
| w06-lake-treehouse | 163 | 45 | 23 | `TH_Structure` (5 cells), `TH_Frame`, `TH_P_bell`, `TH_P_kamado`, `TH_P_futon`, `TH_P_globe`, `TH_P_bookshelf` |
| w07-hidamari-harbour | 883 | 118 | 89 | `HD_Shop_00..14`, `HD_Streets`, `HD_Square`, `HD_Lamp`, `HD_P_*` |
| w07-hidamari-station | 586 | 79 | 64 | same family |
| w08-southwest-coast | 162 | 32 | 13 | `SW_Temple`, `SW_BoatShed`, `SW_Dock`, `SW_CoconutStand`, `SW_DryingRack`, `SW_Island` (16 patches), `SW_Boat` |
| w08-southwest-isle-east | 94 | 22 | 3 | `SW_Boulder_*` (scatter) |
| w08-southwest-terrace | 27 | 22 | 2 | `SW_FisherHouseA`, `SW_StoneStairs` |
| w09-brinecove | 459 | 13 | 0 | none (its fixed objects are runtime groups, `world/regions/w09-brinecove/objects.toml`) |
| w11-megapark | 559 | 26 | 2 | `HD_NorthGate` (6), `ZP_MegaPark` |
| w12 craterpark and volcano (4 regions) | 1430 | 9 to 20 each | 0 | none (park and rock backdrop) |
| w14-hidamari-stable | 165 | 13 | 1 | `HD_NorthTrail` |
| w15-hippodrome | 149 | 11 | 0 | none |
| w16-belmonte | 196 | 10 | 1 | `ZP_Belmonte` (its fixed objects are runtime groups) |
| **Total** | **9311** | | | |

Instance counts behind them (`world.json instances` rows inside each box, mostly scatter): w02 35,550, w06 21,763,
w05-far-west 17,967, w05-far-east 17,846, w03 12,341, w04 12,238, w09 11,810, w01 10,523, w07-harbour 9,788. Hidamari's
buildings come from `hidamari/city.json`: **437 buildings** (276 in w07-harbour, 161 in w07-station; 54 asset kinds),
each with its own position and yaw, so each is an individually identifiable object that is today one instance
among many in a `HD_Shop_NN` patch.

Distinct candidate objects (counting each placed building or single-instance key once):

| Group | Count | Where |
|---|---:|---|
| Hidamari buildings (`HD_Shop_*`, houses, temple and so on) | 437 | w07-harbour 276, w07-station 161 |
| Single-instance keys (`Village_*`, `House_*`, `HouseLot_*`, `SW_*`, `TH_*`, `Torii`) | about 45 | w01, w02, w04, w06, w08 |
| Tree house props (`TH_P_*`, 13 kinds, 1 to 2 each) | about 20 | w06 |
| Hidamari street furniture (`HD_Lamp`, `HD_P_*`, `HD_Planter`) | several hundred instances | w07 |

## What a native split job needs (editor side)

A new guarded step (`migrate.split`, in the style of `migrate.objects`) that, for each object in a region's list:

1. Load the area patch that holds the object (by `V2Id`, from `patches.json`, with World Partition loading its cell).
2. Find the object's instance(s) in the patch's component by transform match with the source data (a `city.json`
   building position, a `world.json` row), within a small tolerance. If not found or ambiguous, stop and report.
3. Spawn a new `AV2ScenePatch` for the object (`Region`, `SourceKey = <key>`, `V2Id = StableId({region, key, mesh,
   "object", position})`, tags and label as `MigrateRegionGroups` does), copy the component's settings (`CopyInto`), add
   the one instance, set `ExpectedMembers = Members()`.
4. Remove that instance from the area patch's component (`RemoveInstance`), rebuild its tree and set that patch's
   `ExpectedMembers` again. If the component becomes empty, delete the component, then the actor if it holds none.
5. Save both packages; list the new packages in the region's `patches.json` and `actors.verified.json`.
6. The step is idempotent: an object whose `V2Id` already exists is kept.

The runtime needs no change: `RegisterScenePatch` takes components by role tag, so an object patch joins the same lists.

## Risks

- **World Partition cell changes.** A new per-object actor is placed at the object's position and is saved to the
  external-actor folder of whichever cell holds it, which can differ from the area patch's cell for an object near an
  edge, and can differ from the grid cell the patch size predicted. Loading order and streaming change. Mitigation:
  spawn at the instance's point and compare the saved folders; measure with a streaming test on the harbour.
- **Duplicates.** A rerun of `migrate.map` creates the area patch again if its `V2Id` is missing from the map, and the
  object exists in both. Mitigation: split before any rerun; make `migrate.map` skip instances whose object ID exists;
  keep the instance removal and the object creation in one editor session and one save.
- **Lost members.** If the instance is removed from the area patch but the object patch fails to save (or the reverse),
  the world loses or doubles the object, and `ExpectedMembers` fails readiness. Mitigation: create and save the object
  first, then remove, then save the area patch; compare instance totals before and after (the sum over both patches
  equals the old count); fail the step otherwise.
- **Claims and verification.** Each new package needs claim scope and entries in two verification files per region
  (`actors.verified.json`, `patches.json`); the step must bind them as `migrate.objects` does.
- **Count explosion.** 437 Hidamari buildings plus about 70 others add several hundred actors. One file per actor is the
  World Partition design, but save time and the verification files grow; do the first batch small and measure.
- **No per-instance name.** A moved instance (edited in the editor) breaks the transform match. Split from the saved
  state, not from the source data, and match by transform within tolerance.

## First 15 objects

Chosen because each is a single-instance key with a distinct role, so no matching ambiguity:

1. `Village_Storehouse` (w02-village)
2. `Village_CottageB` (w02-village)
3. `Village_Workshop` (w02-village)
4. `Village_TeaHouse` (w02-village)
5. `Torii` (w02-village)
6. `House_A` (w01-start)
7. `House_B` (w01-start)
8. `House_C` (w02-village)
9. `SW_Temple` (w08-southwest-coast)
10. `SW_BoatShed` (w08-southwest-coast)
11. `SW_Dock` (w08-southwest-coast)
12. `SW_CoconutStand` (w08-southwest-coast)
13. `SW_DryingRack` (w08-southwest-coast)
14. `SW_FisherHouseA` (w08-southwest-terrace)
15. `TH_Frame` (w06-lake-treehouse)

After that, the Hidamari buildings by position (`HD_Shop_*`), then `TH_Structure` cells and the `TH_P_*` props.
