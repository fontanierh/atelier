# Transport scenery: saved objects and remaining boundaries

Snapshot: **main `3027366ced` (2026-11-09)**. The initial audit described fixed scenery created by the donor's
service actors. That migration has since landed: it is no longer correct to say that only the four zeppelin
stations are saved. [INVENTORY](../INVENTORY.md) tracks port status; this note describes editing boundaries.

## Current saved structure

| System | Saved placement records | Model ownership | Remaining distinction |
|---|---|---|---|
| Ferry | 2: Hidamari and Brine Cove terminals (`w17-ferry/objects.saved.json`) | 4 adopted records / 66 packages | The ship, gates, hinged brows and live timetable remain dynamic services |
| Gondola | 9: six stations and three line-pylon groups (`w18-gondola/objects.saved.json`) | 26 adopted records / 96 packages | A pylon group still bundles several useful towers; cabins and ropes remain dynamic |
| Railway | 13, including Belmonte station, overbridge, track sections, tunnels and fittings (`w20-railway/objects.saved.json`) | 14 adopted records / 146 packages | Track areas and repeated fitting groups are not proof that each useful fitting is independently editable. The track-fittings group is **prepared, not saved** as twelve per-fitting objects (2 buffer stops, 2 stop boards, 2 turnouts, 6 tunnel portals, each routed by its row; `tools/migrate/railway_fittings.py`) |
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
- Railway fittings: every fitting is row `i` of one runtime group with key `""` per mesh (`SM_TK_BufferStop#`, `SM_TK_StopBoard#`, `SM_TK_Turnout#`, `SM_TK_Portal#`; 2+2+2+6 rows). The prepared split is twelve objects, one per fitting, `object/railway/<buffer-stop|stop-board|turnout|tunnel-portal>-<i>`, routed as `SM_TK_<mesh>#@<i>` (the row index in the file's order). The save and the runtime honour the row name (`BelmonteTrack.cpp`, `V2MigrationTravel.cpp`: a C++ change, uncompiled); `track.json` is not changed. Rendering stays batched for the other rows.
- `AV2ScenePatch::ClimbExempt` recognizes the saved source keys (`railway:`, `ferry:`, `gondola:`, parks and pier),
  so the old service-actor `NoClimb` tag is not the only path protecting saved scenery.
- Rendering batches may remain for performance. Several useful towers or fittings in one editable group still
  require independent editing boundaries under the whole-game authoring requirement.

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
