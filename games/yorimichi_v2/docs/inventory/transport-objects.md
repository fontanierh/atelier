# Transport systems: fixed objects still spawned at runtime (audit A1)

Each system's service actor builds its fixed scenery from one data file at play start. Nothing below is a saved,
placed actor except the four zeppelin station meshes. Paths are under `unreal/Source/Yorimichi` (C++) and
`unreal/Content/Data` (data). The donor is `games/yorimichi`. Centimetres, Unreal axes, as in the data.

Reading the "Saved as an actor needs" column: the runtime spawn is one loop over a data array. To skip an object,
the loop needs a skip list (the manifest of saved objects, as `migrate.objects` does for Brine Cove groups) and
the loop must not run for it. "Gameplay reads" is what code takes from the object's data row or component.

## Gondola (`Travel/GondolaService.cpp`, data `gondola/runtime.json`)

`AGondolaService::Load` (line ~165) loops `static[]` (52 rows `{name, mesh, collision, location_cm, yaw}`) and makes one
static mesh component per row on the service actor (WorldStatic, overlap off, tag `NoClimb` on the actor). A row
named `*_Collision` is hidden. Ropes and cabins are separate and moving (`lines[]`, `cabin`).

| Fixed object | Meshes and data | V2 records, units | Sources, gaps | Saved as an actor needs |
|---|---|---|---|---|
| Support tower, 10 (`GD_L1_0..3`, `L2_0..3`, `L3_0..1`) | one mesh each `/Game/Gondola/World/GD_Lx_y_Tower`, collision on; rows in `static[]` | `adopted/gondola/world` (towers, foundations, access, rope LODs in one record) | model: `assets/vehicles/gondola/tower.py` (parametric lattice) fitted by `world/regions/gondola/site.py` and `layout.py`; inputs pinned in `runtime.json` `sources` (`site_inputs`). No gap known for the generator; per-tower source is the shared function plus its fit row | Skip its `static[]` row (name list). The saved actor must carry the `NoClimb` tag and WorldStatic collision as `MeshPart` sets them. Gameplay reads nothing from the tower: tower-pass audio comes from `lines[].clock` events and the rope from `clock.points`, both data |
| Foundation and ground access, 6 (`GD_<station>_Foundation`, `_Access`) | meshes in `static[]`, collision on | same record | same generator (`site.py`) | same skip; walk surfaces matter to riders, so keep collision identical |
| Station, 6 (`hidamari`, `southeast`, `belmonte`, `northwest`, `floor`, `floor_rim`) | per station 5 rows: `Building`, `Collision` (hidden), `Fittings`, `Machinery`, `Platform` of the shared meshes `GD_StationValley_*`, `GD_StationRim_*`, `GD_StationCrater_*`; `stations[]` row: `location_cm`, `yaw`, `walk_cm`, `boarding_cm`, `rope_z`, `mouth_*`, `berth_x`, `gauge` | `adopted/gondola/kit` (three station shells, cabin) | model: `assets/vehicles/gondola/stations.py` plus `world/regions/gondola/plan_kit.py`, `kit_sources.py`. The same three shell meshes are reused by two to three stations each; per-station placement is only the `static[]` transform | Skip the 5 rows of the station. Gameplay reads the `stations[]` row (not the mesh): boarding box `boarding_cm`, `walk_cm`, the cable's mouth and `rope_z`, `location_cm` for station audio. A moved station would also move the rope geometry, which is fitted in data, so a station must stay pinned to its `stations[]` row (read its transform from the actor only once the line data is derived from it) |

## Ferry (`Travel/FerryService.cpp`, data `ferry/service/service.json`)

`AFerryService::Spawn` (line ~213; terminals ~272). For each of `terminals[]` (2: `hidamari` berth 0, `brinecove` berth 1):
one static mesh per `parts[]` entry at `anchor_cm`, a hidden collision mesh, a hinged movable brow, and a text
timetable. The ship (7 parts, 2 gates) is separate and moves.

| Fixed object | Meshes and data | V2 records, units | Sources, gaps | Saved as an actor needs |
|---|---|---|---|---|
| Hidamari terminal | parts `Jetty`, `Stage`, `WaitingHouse`, `Timetable` (`FT_HD_*`), collision `FT_HD_Collision`, brow `FT_HD_Brow`; `anchor_cm`, `walk_cm`, `brow.hinge_cm`, `board.location_cm` | `adopted/ferry/terminals` (all 2 terminals, one record) | model: `assets/vehicles/ferry/terminals/build.py`, `site.py`; plan: `world/regions/ferry/plan_terminal.py`, `terminal_sources.py`, `terminal_constructor.py`. `service.json` `sources.products` pins the harbor-cut and `ferry/terminals/site.json` inputs. Gap: none in the tree, but the record holds both terminals, so one claim blocks both | Skip the 4 part rows and the collision row of that terminal (the brow, hinge and text stay runtime). Gameplay reads `Terminal.Anchor` (hinge offset `Anchor - HingeAt`, brow pose) and `walk_cm`/`walk_yaw` (teleport to the terminal), not the part meshes. The saved actor must stay at `anchor_cm`, because the brow and walk points use it |
| Brine Cove terminal | parts `Landing`, `Pavilion`, `TicketHut`, `Fenders`, `Props` (`FT_BC_*`), collision `FT_BC_Collision`, brow; anchor (-174500, 9480, 0) | same record | `world_brinecove.npz` inputs; Brine Cove side of `site_inputs.py` | same. Note the Brine Cove region's own `SM_BC_Harbor_*` tiles lie nearby; the terminal is not in them |

## Zeppelin (`Travel/ZeppelinService.cpp`, data `world.json` `zeppelin`, `JapanWorld.cpp` ~837)

`Initialize` builds the ship, motors, propellers, one deck gate and one `DockGate<i>` per station
(`ZP_Gate`, rotates open, `Stations[i].Origin + Local(5.15,1.04,1.65)`). The four station buildings are **already saved
placed actors**: `ZP_Woodland` (`w06-lake-treehouse` patches), `ZP_City` (`w07-hidamari-station`), `ZP_MegaPark`
(`w11-megapark`), `ZP_Belmonte` (`w16-belmonte`), plus `ZP_Trail` (`w07-hidamari-harbour`), from `world.json` `instances` with
transform 0,0,0 in world space.

| Fixed object | Meshes and data | V2 records, units | Sources, gaps | Saved as an actor needs |
|---|---|---|---|---|
| Station building, 4 | `ZP_Woodland/City/MegaPark/Belmonte` in `/Game/Japan/Assets` | `adopted/japan/assets/zeppelin` (all `ZP_*`, one record); placement actors in the region patches above | model: `world/regions/zeppelin/parts/station.py` (+ `station_data.py`, `layout.py` STATIONS, `plan_*.py`, `build.py`). Gap: one mesh record for the whole system, so one claim blocks all four | Already saved; nothing to skip. Station data (`origin`, `ship`, `entry`, `safe`) is read by `ZeppelinService`/`ZeppelinNetwork` from `world.json`, not from the actor |
| Dock gate, 4 | `ZP_Gate` component `DockGate<i>` | same record | `parts/gate.py` | Moving part (swings 90 degrees with the ship's gate state). Not a first candidate: the service rotates the component each tick |
| Gangways, deck gate, ship | `ZP_Gangway`, `ZP_Gate`, `ZP_Airship`, `ZP_Motors`, `ZP_Propeller` | same | `plan_airship.py`, `plan_gangway.py` | Vehicle parts, move with the ship; stay runtime |

## Train (`Travel/BelmonteTrack.cpp`, `BelmonteTrainService.cpp`, `BelmonteTrainBoards.cpp`; data `belmonte_track/track.json`, `belmonte_train/service.json`)

`ABelmonteTrack::Spawn` (called at `JapanWorld.cpp` ~898, before the service) loops `pieces[]` (131 meshes: 80 chunks,
33 tunnel linings, 7 viaducts, 5 banks, 4 station meshes, loop, overbridge) and `instances[]` (87 groups of
sleepers, lamps, portals, buffer stops, stop boards, turnout) as static meshes and HISM. The service builds the trains,
reads `service.json` `stations[]` for platforms, buffer blocks and arrival boards, and draws `Block()` boxes
for Hidamari's platform and buffer when the track brings no buffer.

| Fixed object | Meshes and data | V2 records, units | Sources, gaps | Saved as an actor needs |
|---|---|---|---|---|
| Belmonte station (head house, sheds, coaches, forecourt) | pieces `SM_ST_Headhouse`, `SM_ST_Sheds`, `SM_ST_Coaches`, `SM_ST_Forecourt` all at (82339.7, -468927.8, 20777); `SM_ST_Overbridge` at (99900.9, -454200.8, 20732) | `adopted/belmontetrack/loose_files` (all 138 packages in one record) | model: `world/train/station.py`, `docs/BELMONTE_STATION.md`, tests `test_belmonte_station.py`; mesh data `assets/belmonte/meshes`. Gap: no per-station unit; one record for the whole line | Skip those 5 `pieces[]` rows. Gameplay reads the platform surface as WorldStatic ground when boarding/alighting (`BelmonteTrainService.cpp` 713-850) and the `stations[]` arrival record (`arrival`, `boards`). The platforms are part of these meshes, so the saved actor must keep collision and position |
| Hidamari station | `service.json` `stations[0]`: `platform` box (centre 120350, -29795, 3057), `buffer` box; boards (`hidamari_canopy_*`) | none: boxes built at runtime (`Block()`) | no mesh at all. Gap: no source model for this platform; the Hidamari station region `w07-hidamari-station` holds only the zeppelin station | Needs a real mesh (a gap) before it can be an actor; the box platform is read as ground |
| Arrival boards (2 stations) | `BelmonteTrainBoards.cpp`, rows in `stations[].boards` | none | runtime text on a flat-colour board | Hold: they show live train times |
| Track: chunks, tunnel linings, viaducts, banks, loop (131 pieces) | `pieces[]`, each its own mesh (e.g. `SM_TK_Chunk_00` .. `_79`) | `adopted/belmontetrack/loose_files` | generator `world/train/track.py`, test `test_belmonte_track.py`, `train_atomic_build.py`; the train follows a spline built from the same route data (`service.json` `sources.route`) | Skip a piece row. Gameplay reads the rail path from data (route), not the meshes, but the train's ground and tunnels (`tunnels[]`, `light`, `exposure`) depend on position. Moving a chunk without moving the route data breaks the ride; treat as pinned |
| Sleepers, lamps, portals, buffer stops, stop boards, turnout | `instances[]` groups (HISM, 159 sleepers per group) | same | same | Repeated objects: leave grouped; buffer stop and stop board are read as the stopping point by the service (`stations[].buffer`) |

## Smallest safe first object

**Gondola support tower `GD_L3_1_Tower`** (location 115890, -209641, 68798, yaw 30.7). It has one mesh of its own
(`/Game/Gondola/World/GD_L3_1_Tower`), no moving part, and gameplay does not read its transform: tower-pass sound comes
from the cable clock events and the rope from data. Other towers work the same; L3 is a good first because it is
on the short crater line. Steps:
1. Add a skip list to `AGondolaService::Load`'s `static[]` loop (a manifest of saved names), as for Brine Cove groups.
2. Place the actor at the row's transform with the tower mesh, WorldStatic collision, overlap off, tag `NoClimb`.
3. Check by walking at the tower foot and by the cabin passing it; the pass event should still fire.

Not first: stations (boarding reads the data row), ferry terminals (brow hinge and teleport read the anchor), zeppelin
dock gates (move), track pieces and the train platforms (the ride and boarding read their ground).

## Gaps to close

- Ferry, gondola world, gondola kit, zeppelin and train track each hold their meshes in one record, so one object is one
  claim for the whole system. Units like Brine Cove's `units.json` are needed per tower, station and terminal.
- Hidamari's train platform and buffer have no mesh or source.
- The service actors carried the `NoClimb` tag for all their parts. Saved units are not tagged; `AV2ScenePatch::ClimbExempt`
  (`World/V2ScenePatch.cpp`) refuses them by their saved `SourceKey` (`railway:`, `ferry:`, `gondola:`, every `megapark:` and
  `craterpark:` unit, the pier, the mini ramp), so patches saved before the rule are covered too.

## Live check of the saved systems (2026-11-08)

One slice session (profile `slice`, 22 GiB) at main 493a6f4419 plus the park climb exemption (06bd5e1f27), each script in
`tools/test` against the live game:

| Check | Result |
|---|---|
| `ferry_ride.py --start hidamari` | passed: boarded at Hidamari, crossed, ashore at Brine Cove |
| `gondola_ride.py --start hidamari belmonte floor` | passed: three lines; boarded seated, carried by the cabin with no clipping, stood off at the next station |
| `train_ride.py` | passed: boarded at Belmonte, walked the saloon at speed, seated, passing loop and spiral, stepped off at Hidamari |
| Park trees drawn once (Mega Park, Crater Park) | 0 visible doubles in 165,010 instances; the earlier 58,409 were each group's hidden shadow-only twin (`V2Role:ShadowTwin`) |
| `saved_objects.py` Brine Cove (`--zone brinecove_quay`) | 243 of 243 drawn once by their saved actor with the runtime's instance counts. The first run's 45 misses were cell-piece groups (`<mesh>#<i>@<x>_<y>`) the checker read as mesh names; fixed |
| `saved_objects.py` Belmonte | 289 of 289. The first run saw none: travel to the town square found no ground (its scenery streams in by cell), the player fell and water recovery took him to Hidamari. `TravelTo` now holds the player until the target's ground blocks (2.25 s at Belmonte, 1.00 s at the Brine Cove quay). A position probe found 0 of 55,594 saved Belmonte plant instances drawn elsewhere; shared plant meshes of other regions are not copies |
| City tree LODs | after leaving the city and coming back: 0 `incomplete child swap` errors (1,688 before), 29 applies; the swap re-runs only for arriving tree pieces and swaps the loaded subset |

Later runs at 98167295fc and 91e7554f65 (this branch).

## Ownership units (data)

`tools/migrate/{gondola,ferry,train}_units.py` write `assets/adopted/{gondola,ferry,belmontetrack}/units.json` (shared
writer `transport_units.py`). The controller adds one `[[units]]` entry each to `assets/adopted/groups.toml`
(`/Game/Gondola` -> `gondola/units.json`, `/Game/Ferry` -> `ferry/units.json`, `/Game/BelmonteTrack` ->
`belmontetrack/units.json`).

Zeppelin is not split: its meshes (`ZP_Woodland`, `ZP_City`, `ZP_MegaPark`, `ZP_Belmonte`, `ZP_Trail`, `ZP_Airship`,
`ZP_Motors`, `ZP_Propeller`, `ZP_Gate`, `ZP_Gangway`) live in `/Game/Japan/Assets`, which already has a `[[group]]` rule
and takes one rule per folder. The rule's `key` captures `ZP` and `names` maps it to `zeppelin`, so all ten are one
record `adopted/japan/assets/zeppelin`. A per-object split needs that rule to capture the whole name for ZP: key
`ZP_[A-Za-z]+` with names `ZP_Woodland -> zeppelin-woodland-station` ... `ZP_Belmonte -> zeppelin-belmonte-station`,
`ZP_Trail -> zeppelin-trail`, and `ZP_Airship|Motors|Propeller|Gate|Gangway -> zeppelin-ship`; the generators are
`world/regions/zeppelin/parts/station.py` and `plan_*.py`. Left for the controller, who owns the rule.
