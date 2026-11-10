# Transport scenery: saved objects and remaining boundaries

Snapshot: **main `3027366ced` (2026-11-09)**. The initial audit described fixed scenery created by the donor's
service actors. That migration has since landed: it is no longer correct to say that only the four zeppelin
stations are saved. [INVENTORY](../INVENTORY.md) tracks port status; this note describes editing boundaries.

## Current saved structure

| System | Saved placement records | Model ownership | Remaining distinction |
|---|---|---|---|
| Ferry | 2: Hidamari and Brine Cove terminals (`w17-ferry/objects.saved.json`) | 4 adopted records / 66 packages | The ship, gates, hinged brows and live timetable remain dynamic services |
| Gondola | 16: six stations and ten per-tower pylons (`w18-gondola/objects.saved.json`, [PR #790](https://github.com/fontanierh/atelier/pull/790)) | 26 adopted records / 96 packages | Each tower is its own saved object; cabins and ropes remain dynamic |
| Railway | 24, including Belmonte station, overbridge, track sections, tunnels and twelve per-fitting objects (`w20-railway/objects.saved.json`, [PR #790](https://github.com/fontanierh/atelier/pull/790)) | 14 adopted records / 146 packages | Track areas are not proof that each useful piece is independently editable. The fittings are saved one per object (2 buffer stops, 2 stop boards, 2 turnouts, 6 tunnel portals, each routed by its row; `tools/migrate/railway_fittings.py`) |
| Zeppelin | Four station meshes saved with their owning region scenery | Recovered Japan model records; the old single `adopted/japan/assets/zeppelin` proposal is obsolete | Dock gates and the ship move; boarding, line and station data must stay aligned |
| Train rolling stock | 67 recovered generated mesh records under `prop/belmontetrain/` | Imported mesh records preserve LOD/collision/material settings; other train packages retain adopted owners | Vehicles are dynamic gameplay objects, separate from fixed station/track placements |

`objects.toml` names current model owners and route members. `objects.saved.json` binds the saved definitions;
`verified.json` binds their package bytes. A model units map alone does not establish a saved placement.

## Constraints when editing

- Ferry terminals must stay aligned with `service.json` anchors, brow hinges and walking/boarding points. Static
  terminal parts are saved; moving brows, gates and timetable text remain service-owned.
- Gondola stations must stay aligned with the cable plan and station boarding data. Pylon-pass audio comes from
  cable-clock data, not an actor lookup. Keep WorldStatic collision and the existing climb exemption when splitting
  a pylon group into independent objects.
- The train follows route data. Moving a track chunk without updating the route can break the ride, even when its
  mesh saves successfully. Hidamari's platform/buffer `Block()` geometry and live arrival boards remain runtime
  concerns; inspect their actual useful-object boundary rather than declaring all runtime code obsolete.
- Railway fittings: every fitting is row `i` of one runtime group with key `""` per mesh (`SM_TK_BufferStop#`, `SM_TK_StopBoard#`, `SM_TK_Turnout#`, `SM_TK_Portal#`; 2+2+2+6 rows). The saved split is twelve objects, one per fitting, `object/railway/<buffer-stop|stop-board|turnout|tunnel-portal>-<i>`, routed as `SM_TK_<mesh>#@<i>` (the row index in the file's order). The save and the runtime honour the row name (`BelmonteTrack.cpp`, `V2MigrationTravel.cpp`); `track.json` is not changed. Rendering stays batched for the other rows.
- `AV2ScenePatch::ClimbExempt` recognizes the saved source keys (`railway:`, `ferry:`, `gondola:`, parks and pier),
  so the old service-actor `NoClimb` tag is not the only path protecting saved scenery.
- Gondola pylons are saved as ten per-tower objects (`object/gondola/pylon-l<line>-<n>`) by
  `tools/migrate/gondola_pylons.py`; the three line groups are retired ([PR #790](https://github.com/fontanierh/atelier/pull/790); see the pylon section below). Cabins, ropes, the cable plan and station data are not part of that split.
- Rendering batches may remain for performance. Several useful towers or fittings in one editable group still
  require independent editing boundaries under the whole-game authoring requirement.

## Gondola pylon split (saved)

Status on main: **saved and retired** ([PR #790](https://github.com/fontanierh/atelier/pull/790)). `w18-gondola/objects.saved.json`
holds the six stations and the ten pylons. `tools/migrate/gondola_pylons.py --check` reports the state of the tree.

- Selection: the ten `GD_L<line>_<n>_Tower` static entries of `gondola/runtime.json`, lines in id order, and within a
  line by straight distance from its lower station (L1 Hidamari, L2 Belmonte, L3 Floor). At most 20 are taken; all ten are.
- Each tower becomes `object/gondola/pylon-l<line>-<n>`, with `route` = its entry and `model` = its existing record
  `adopted/gondola/tower-l<line>-<n>`.

States, each reached by one step that repeats safely: **unprepared** -> **prepared (pending save)** -> **saved (pending
retire)** -> **done**. The pending state is `world/regions/w18-gondola/pylon-retire.json`: the three groups, their record
files and actor packages, and the ten replacement ids.

1. **Prepare** (`--claim TASK`): every path and scope of `--paths` is authorized before any write (W18 and W00). One
   journaled write puts the ten objects into objects.toml, removes the three group entries, and writes the pending file.
   The groups' records, actors and saved keys stay, so their towers are still drawn. A rerun is a no-op.
2. **Save**: the coordinator runs `objects.py` for the ten (unchanged). Its saved-definition check looks only at the
   objects it is given, and `write_saved` keeps the groups' saved keys, so it accepts the state. The group actors stay on
   disk, and `SaveUnits` creates new patches for the new unit ids while the manifest's names stay the same. Until retire,
   the towers are drawn twice in the map. This is not verified in Unreal.
3. **Retire** (`--retire --claim TASK`): refused, changing nothing, unless every replacement has a receipt (its
   `objects.saved.json` entry equals its definition, its record names it, and its `verified.json` hashes each actor
   package as on disk). It then deletes exactly the pending files and drops the three group keys, journaled. A rerun
   after it is a no-op.

Between the steps the map is consistent: prepare leaves the groups drawing, and a failed save leaves the pending file so a
rerun of prepare says so and retire refuses. The Unreal manifest is never edited; its names are the tower names. The
replacement records of a failed save are not created by these steps, so retire has nothing to delete for them.

### Coordinator sequence

```sh
gp() { uv run python games/yorimichi_v2/tools/migrate/gondola_pylons.py "$@"; }
gp --check                     # unprepared
gp --paths                     # the paths and scopes (W18 + W00) the claim must cover; acquire it
gp --claim TASK                # 1. prepare; a rerun prints "already prepared"
uv run python games/yorimichi_v2/tools/migrate/objects.py region/w18-gondola --environment region/w00-island \
    --claim TASK --only object/gondola/pylon-l1-0 --only object/gondola/pylon-l1-1 --only object/gondola/pylon-l1-2 \
    --only object/gondola/pylon-l1-3 --only object/gondola/pylon-l2-0 --only object/gondola/pylon-l2-1 \
    --only object/gondola/pylon-l2-2 --only object/gondola/pylon-l2-3 --only object/gondola/pylon-l3-0 --only object/gondola/pylon-l3-1
gp --check                     # prepared (pending save) until every receipt exists, then saved (pending retire)
gp --retire --claim TASK       # 3. refused until "saved"; then done; a rerun prints "already done"
```

If the save fails, stop there. Re-run `objects.py` with the same claim; prepare and `--check` remain safe to repeat, and
retire is refused until the replacements have receipts.

## Recorded gameplay evidence

These are **historical revision-bound results**, not new tests on the latest package. On 2026-11-08, the guarded
slice session at `493a6f4419` plus climb exemption `06bd5e1f27` recorded:

| Check | Result |
|---|---|
| `ferry_ride.py --start hidamari` | Boarded at Hidamari, crossed and stepped ashore at Brine Cove |
| `gondola_ride.py --start hidamari belmonte floor` | Three lines; seated riding, no cabin clipping, exit at the next station |
| `train_ride.py` | Boarded at Belmonte, walked the saloon at speed, seated, passed loop/spiral and stepped off at Hidamari |
| `saved_objects.py`, Brine Cove | 243 of 243 then-saved groups drawn once |
| `saved_objects.py`, Belmonte | 289 of 289 then-saved groups drawn once |
| Park trees | No visible doubles among 165,010 instances; hidden shadow twins were not visible duplicates |
| City LODs after return travel | No incomplete-child-swap errors after the loaded-subset correction |

Later fixes and content have their own receipts. The package at `3027366ced` built successfully, with automated
acceptance reported passing; this does not automatically repeat the ride evidence on that package. The owner
will perform human and multiplayer playtesting after construction. That work does not block independent migration.
