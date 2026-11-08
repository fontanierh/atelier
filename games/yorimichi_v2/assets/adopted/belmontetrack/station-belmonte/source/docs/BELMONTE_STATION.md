# Belmonte station

The terminus of the Belmonte steam line, designed by Paul (2026-10-17): a Tuscan station that mixes London King's Cross
and Paris Saint-Lazare. Paul's reference elevations are in `assets/belmonte/concepts/station/`. They inspire the
building but are not traced.

## Site

- The station stands on the flat ground north of the road that runs from Belmonte's south-east gate to the Dunes Basses
  estate (`route.py` `BELMONTE`: platform centre (900, 4625), trains arrive running north-west, bearing 140°).
- Its facade faces the town. The forecourt is about 230 m from the north gate, and the Salon des paris is
  200 m from the access road's junction.
- The line now ends in Belmonte's valley:
  - a viaduct over the river;
  - a cutting under the road from the south-east gate, 229 m before the buffer stop. The rail there is 8.6 m below
    the road.
  - It is 496 m longer than the riverside site, takes 17 s more uphill, and leaves the loop and its crossing offset
    unchanged.
- The road keeps its line. A stone overbridge (`SM_ST_Overbridge`, `overbridge.py`) carries it over the cutting; see
  `BELMONTE_TRACK.md`.
- An access road (7 m of cobbles, 86 m, `station_site.ACCESS`) runs from the forecourt north to the road between the
  north gate and the Trois Prés estate. That road also leads to the Salon and the town. It leaves the forecourt's front
  edge at a slant, stays level for its first 8 m (`ACCESS_FLAT`), then climbs at about 2.3 %. Its end dips under the
  junction's ground, so no paving edge shows there.

## Train size

Paul wants the train 15 % larger (2026-10-18). Today it is 131 m long, 3.60 m wide and 4.30 m tall; scaled it is
150.7 m, 4.14 m and 4.95 m. `station_site.py` sizes the station for it (`TRAIN_SCALE`):

- the sheds are 175 m long, so the whole train stands under the roof when its head stops 10 m short of the buffer;
- the platform edges stand 2.12 m from each track, clear of the scaled body.

## Levels

The rail is at 207.6 m. The ground around the station is at 210 to 215 m, so the station sits in a shallow cutting.

| Level | Over the rail | What stands there |
| --- | --- | --- |
| Formation | -0.85 m | Ground under the sheds and the headhouse |
| Platforms and concourse | +1.0 m | The train service's boarding height |
| Street | +7.2 m (214.97 m) | Vestibule, forecourt and the access road's start |

A double staircase in the headhouse joins the street to the concourse: one flight per shed, 37 steps. The landing
between the flights overlooks the concourse.

## Building

All dimensions are in the station frame of `station_site.py`:

- `a` runs along the track towards the buffer stop and beyond it to the facade;
- `u` runs to the left of an arriving train;
- the origin is the end of the line.

| Part | Where | Notes |
| --- | --- | --- |
| Train sheds | a -175..0 | Two glazed vaults, 22 m span each, springing 15.6 m over the street, rise 13.4 m. Ten bays of 17.5 m. The south-west shed holds the line's track. The other holds a decorative siding with three old wooden coaches. Iron columns carry the spine between the sheds. |
| Platforms | | P1 against the south-west wall, an island between the tracks, P3 by the north-east wall. Edges are 2.12 m from each track. |
| Rear end | a -175 | Stone piers with an archivolt over each open shed end, an iron screen above the trains' opening, and pavilions at the outer corners. |
| Great arches | a 17 | Iron tracery windows over the stair hall, framed by archivolts with keystone cartouches. Outer pylons carry finials. |
| Headhouse | a 0..26 | Concourse (a 0.5..7), stair hall (7..18) and vestibule (18..26). The street front has nine open arches under three iron and glass canopies, arched first-floor windows, a cornice and a balustrade with urns. A pediment stands under the clock tower. |
| Clock tower | over the spine | Brick shaft with stone quoins, four 2.3 m dials, a belfry cornice and a tiled spire. Its top is 38 m over the street, plus the spire. |
| Wings | u 12..26 and -55..-41 | Two storeys of terracotta brick panels between stone pilasters, closed arched doors, pedimented windows and a hipped terracotta roof. The wings cannot be entered. |
| Forecourt | a 26..46 | Cobbles with stone kerbs and four lamp posts; the access road leaves its front edge on the axis. |

Materials reuse Belmonte's instances: `MI_B_ashlar`, `MI_B_stone`, `MI_B_plaster` (brick), `MI_B_roof`,
`MI_B_glass_dark`, `MI_B_flag`, `MI_B_cobble`, `MI_B_gravel`, `MI_B_iron` and `MI_B_wood`. Five flat colours are added
as `MI_ST_*` instances of `M_Belmonte`: green ironwork, roof glass, clock dials, coach teak and coach roofs. All shaders
are opaque.

### Glazing

- Up close (LOD0), the roofs, clerestories and arch screens are open iron lattices. Sunlight falls through them onto
  the platforms.
- From farther away (LOD1 and LOD2), the lattice becomes glass panels.

## Pieces and budgets

The station is built with the track. Its pieces sit in `track.json`'s `station` block and are placed by
`ABelmonteTrack`, so every client builds them the same way in multiplayer.

| Mesh | Triangles LOD0 / LOD1 / LOD2 (budget, `track.BUDGETS`) | Built | Collision |
| --- | --- | --- | --- |
| `SM_ST_Headhouse` | 14,500 / 4,200 / 1,200 | 13,032 / 3,756 / 1,036 | LOD2: open arches, floors, stairs as ramps |
| `SM_ST_Sheds` | 34,000 / 6,000 / 2,400 | 31,272 / 5,492 / 2,160 | LOD2: platforms, walls, columns |
| `SM_ST_Coaches` | 2,000 / 300 / 60 | 1,848 / 264 / 36 | LOD2 boxes |
| `SM_ST_Forecourt` | 220 / 80 / 40 | 200 / 72 / 36 | LOD2: the square and the access road |

Belmonte runs near 30 fps on the target Mac, so the budgets keep about 10 % over what is built. The sheds' open
lattice is LOD0 only; beyond the first LOD switch the whole station draws under 10k triangles.

The train service no longer adds its makeshift platform at Belmonte (`tools/belmonte_train_service.py` `BUILT`).

## Arrival boards

Paul (2026-10-19): in both termini, boards show when the next train arrives and the one after, counted down in real
minutes, in French like the rest of the line ("Prochain train · dans 5 min", "Train suivant · dans 31 min"; "arrive"
under a minute, "à quai" while a train stands there).

- **Belmonte**: one over the concourse on the landing block between the flights (a 7, u -14.5, 3.4 m over the
  platforms), facing the platforms; one on posts on P1 and one on the island, 5 m short of the buffer stop, beyond the
  head of a standing train, both faces lettered.
- **Hidamari**: two under the town station's platform canopy, hung from its tie beam between the posts, one near the
  arrival point and one mid-canopy; both faces lettered.

Each board is a dark face in a wood frame with warm amber lettering (TextRender with `M_BT_BoardText`, unlit and
glowing, so it reads at night). Placement is data: `tools/belmonte_train_service.py` `boards()` writes each station's
`boards` into service.json; `ABelmonteTrainService` builds them (`BelmonteTrainBoards.cpp`).

The countdown is a pure function of the service clock (the host's replicated world time plus the replicated dev
offset) and of the timetable's samples, so every player reads the same board. The stands at each terminus come from
the samples (`FBelmonteTrainLine::Stops`); service seconds become real ones through `train.TimeScale`, the host's on a
client. Text is checked once a second and changes about once a minute. Live state: `atelier live py` with
`UBelmonteTrainLive.train_state()` lists each board's lines.

## Ground

- `train/earthworks.py` designs the station's ground together with the line's:
  - under the sheds and the stair hall, the formation, standing straight against their walls;
  - under the vestibule and the wings' street end (`station_site.VESTIBULE`, solid to street level), 2 cm under the
    street, so the ground meets the street flush along the whole facade;
  - the forecourt and the access road at street level, the road rising evenly to its junction, with soil slopes
    beyond. The ground stays level for 1.5 m around the forecourt (`station_site.FORECOURT_HOLD`) before its slopes
    start, so it never rises through the cobbles;
  - under the overbridge, the cutting between its walls.
- `train/corridor.py` keeps plants off all of it, beyond the line's ends too (`settle`).
- The four touched valley terrain tiles (`SM_BM_BT_Terrain_4_3`, `5_2`, `5_3`, `6_2`) remain untouched in
  `assets/belmonte/meshes/`. During `world.belmonte`, `regions/belmonte/terrain.py` (`write_carved_valley_tile`)
  carves them into `build/yorimichi/belmonte/glb/`, subdividing only non-planar triangles and refining along the
  overbridge walls, forecourt edges, access road and Salon path (`SALON_PATH`). `import_belmonte.py` generates
  reduced LODs for the refined tiles.

## Builds

After a change to the station:

```sh
uv run atelier build yorimichi world.belmonte_track world.belmonte_track_data unreal.belmonte_track
uv run atelier build yorimichi world.belmonte_train_service unreal.belmonte_train   # BUILT: no makeshift platform
uv run atelier build yorimichi world.belmonte_station_review     # control renders
```

After a change to the line or the site:

1. Run `world.belmonte_train_route` and copy its `line.json` to `assets/vehicles/belmonte-train/line.json`.
2. Rebuild `world.belmonte` and the steps after it.
