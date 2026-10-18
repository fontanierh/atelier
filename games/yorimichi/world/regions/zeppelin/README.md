# Zeppelin line

One open-deck airship serves four air stations: Woodland, at the end of a trail west of the hidden woodland lake;
Hidamari, in the city's station district; the Mega Park, on the crest above the park's top road; and Belmonte, on the
meadow outside Porta NW between the walled hill town and the racecourse. The player rides as a passenger; there is no
piloting. All four stations are in the map's destination list.

## Build and check

```sh
uv run atelier build yorimichi world.zeppelin unreal.world data.stage
uv run atelier qa yorimichi zeppelin SESSION [STATION]
```

- [`layout.py`](layout.py) owns the stations (`STATIONS`, in line order), the legs, the ship, entry and safe-landing
  datums and the terrain and foliage clearance. `world.layout` calls `zeppelin.layout.integrate` from `gen_world.py`,
  after the lake: it levels the Woodland pad, lays the trail from the lake cabin round the southern shore and west
  through the woods, clears the trees in the way and writes `world['zeppelin']` and `build/yorimichi/zeppelin/layout.json`.
  `integrate` refuses a world that already has a zeppelin; run `python -m zeppelin.layout` (from
  `games/yorimichi/world/regions`) to reapply it to the pre-zeppelin snapshot in `build/yorimichi/zeppelin/source/`.
  The Hidamari pad (`city_pad`) and the Mega Park pad (`megapark_pad`) are levelled where those terrains are built.
- `world.zeppelin` ([`build.py`](build.py), Blender) builds `ZP_Airship` (envelope and deck), `ZP_Motors`,
  `ZP_Propeller`, `ZP_Gate`, `ZP_Gangway`, `ZP_Trail` and the four stations `ZP_Woodland`, `ZP_City`,
  `ZP_MegaPark` and `ZP_Belmonte`. Fittings and stations use the village material; the envelope fabric has its own slot. The build
  runs [`check_rotors.py`](check_rotors.py), which proves the swept propeller disc clears the hull by more than 30 cm
  at every angle and writes `build/yorimichi/zeppelin/rotor-clearance.json`.
- `unreal.world` imports them through `unreal/Scripts/import_zeppelin.py`, which also builds `M_ZeppelinFabric`
  (sun-driven shading and distance haze). `ZEPPELIN_ASSETS_ONLY=1` reimports the meshes without the terrain.
- The `zeppelin` scenario launches its own game under the render guard at station `STATION` (0, 1, 2 or 3; default 0),
  captures thirteen views round it and probes the ten entry treads and six landings to 4 cm, into
  `build/yorimichi/zeppelin/SESSION/`. `--visual` keeps three views and no probes.

## Stations

Coordinates are Blender metres (x east, y north). Station-local x points east and -y is the front.

| Key | Name | Origin |
| --- | --- | --- |
| `zeppelin_forest` | Woodland air station | (-205, 230), 70.4 m |
| `zeppelin_city` | Hidamari air station | (1273, 321), 35.5 m |
| `zeppelin_megapark` | Mega Park air station | (-200, 1484), 130 m |
| `zeppelin_belmonte` | Belmonte air station | (410, 4660), 217.75 m |

Woodland keeps the lake cabin, water and islet untouched. Hidamari stands on dry grass east of the x 1240 road and
north of the town railway. Its apron, docked ship and turning envelope clear the tracks; its pedestrian link joins
the open lane at (1240, 329), beyond the railway barrier, and skirts the ticket hut to the apron. Local grading
leaves the railway cutting and the y 335 road and crossing untouched. The ship, entry, safe landing and all three
Hidamari flight legs derive their positions and durations from the same station origin.

## The ship

- A fully open passenger deck: shallow wooden hull, perimeter railings, benches, a helm and a hinged boarding gate. No
  cabin, windows, roof or canopy.
- Two motor pods, one per side, fixed to the envelope with short rigid brackets; four vertical struts carry the deck
  from the envelope keel. No ropes between the propellers and the deck.
- A cream-and-sage envelope about 26 m long and 8 m across, with gold bands and a gold sunrise mark, over a cedar deck.
- Separate propeller blade meshes turn round their hub pivots: slowly when docked, spooling up on departure and down
  on arrival.

## The ride

`AZeppelinService` owns the one ship and its stages: docked, boarding, take-off, cruise, landing, disembarking. Using
the docked ship boards it: the gate closes and the gangway retracts, the passenger's board and sailboat are stowed,
and the ship lifts off, cruises and docks; the passenger walks off with normal movement. A player who jumps onto the
docked deck can board from there.

- At another station, Use calls the empty ship. In flight, Use skips to a safe docking and disembarking, never a drop
  in mid-air. Map travel or Back to spawn cancels the ride cleanly.
- The camera pulls back once the ship lifts off: the arm is the player's own distance times 11, clamped to 42-70 m,
  and returns to the player's setting on disembarking. Look stays free throughout.
- The ride speed steps through 0.5x, 0.75x, 1x, 1.5x, 2x and 3x. It scales take-off, cruise and landing alike, the
  propellers spin to match, and it stays set for the next flight. Boarding and disembarking keep their pace. Only the
  passenger can change it: `[` and `]` on a keyboard, the shoulder buttons on a gamepad, **Slower** and **Faster** on
  the phone (the page sends `{yorimichi:1,action:'flightSpeed',delta:-1|1}` and reads `flightSpeed` back from the
  telemetry).
- On the phone, Use reads **Fly**, **Call ship** or **Skip flight** at a station or aboard.

## The Mega Park stop

The line runs **Woodland → Hidamari → Mega Park → Belmonte** (the order of `STATIONS`). The ship carries on the way it came and
turns back at either end; whoever stands at the docked ship can choose another stop before boarding.

- **Mega Park: (-200, 1484)**, 130 m, on the crest just west of the park's top road. The station, the docked ship and
  its turn on take-off all stay clear of the park. `megapark_pad` levels the north terrain under the station and the
  ship and along an earth footpath east to x -170, and the Mega Park gate's ground (`megapark/gate.py`,
  [MEGAPARK.md](../../../docs/MEGAPARK.md#gate)), which replaces the terrain there, keeps it level. From there a level
  timber footbridge (part of `ZP_MegaPark`) crosses a grassy dell beside the park to a stone sill against the road
  deck's slanted west edge (`DECK_EDGE`), at 130 m. Trees are cleared over the station and within 7.5 m of the path.
- **Belmonte: (410, 4660)**, 217.75 m, on the naturally level meadow outside Porta NW between the walled hill town and
  the racecourse's south stand. A stone footpath (`BELMONTE_WALK`, part of `ZP_Belmonte`) runs south from the station
  apron through the open archway of `SM_BM_BH_Porta_NW` onto the cobbled town street (`SM_BM_BC_Pave_0_3`).
  `belmonte/planting.py` clears planted trees, bushes and grass over the station and along the path.
- **Legs.** Every pair of stops is a leg with its own cruise height, clearing the ground and trees under a 40 m
  corridor with room for the trailing camera. All legs fly at 53 m/s (1480 m in 28 s), and the ship turns to the
  leg's true heading on take-off. Climbs take at least 5 s and descents at least 4 s, longer for a bigger height change.

| Leg | Cruise height | Cruise at 1x |
| --- | --- | --- |
| Woodland-Hidamari | 155 m | 28 s |
| Woodland-Mega Park | 185 m, over the western foothills and the park | 23.7 s |
| Hidamari-Mega Park | 240 m, past the volcano's flank (163 m) | 35.7 s |
| Mega Park-Belmonte | 520 m, over the volcano's western shoulder | 61.2 s |
| Woodland-Belmonte | 600 m, over the western flank | 84.6 s |
| Hidamari-Belmonte | 910 m, high above the volcano caldera and Crater Park | 84.0 s |

- **Choosing the stop.** At the docked ship the hint names the next stop, and `[` / `]` (shoulder buttons on a
  gamepad, **‹ Stop** / **Stop ›** on the phone) step through the others (`zeppelinChoose` in the telemetry says when
  they can). Aboard, the same buttons set the ride speed.
