# World map

The in-game map shows a painted sheet of the whole playable world with the player's position and heading, and lets
the player travel to any zone on it. Every position on the sheet comes from the generated layout (`world.json`, the
heightmaps, `hidamari/city.json`, the island and city height functions), never from screenshots or hand placement;
only the artwork is painted. The tools live in [`games/yorimichi/world/map/`](../world/map/).

## Build

```sh
uv run atelier build yorimichi world.map data.stage
```

`world.map` runs [`build_map.py`](../world/map/build_map.py) after `world.layout`, `world.hidamari`,
`world.skatepark` and `world.zeppelin`. It writes `build/yorimichi/map/`:

| File | Contents |
| --- | --- |
| `rough.png`, `rough.jpg` | The label-free sheet drawn from the data, the base for any painting |
| `map.png`, `map.jpg` | The sheet the game (`map.png`) and the phone page (`map.jpg`) show: the committed painted sheet when it matches, otherwise the rough sheet |
| `map.json` | `bounds`, `projection_x`/`projection_y`, `px_per_m`, `sea_level` and the `zones` |
| `map_lines.json` | Every polyline drawn, to check that a painted sheet's roads sit on the data |

`data.stage` copies them into `unreal/Content/Data/map/`, where `UJapanMap` reads them.

## Frame and projection

- Coordinates are Blender metres: x east, y north, z up, the frame of `gen_world.py` and `world.json`. Unreal uses
  the same values in centimetres with y negated (`AJapanWorld::ToUE`); zone yaws are negated on load.
- The sheet uses the compact projection in [`map_projection.py`](../world/map/map_projection.py): piecewise-linear
  knots on each axis (`X_KNOTS`, `Y_KNOTS`) over `BOUNDS = [-400, -650, 1685, 740]`. Gameplay scale is untouched; the
  distant north takes only a fifth of the sheet. The southern strip reaches world y -730, keeping the temple island
  visible after its 50 m offshore move; projection controls north of world y -461.31835938 are unchanged.
  `map.json` carries the knots, and the game and `phone/map.js` place
  the player and the pins through the same ones.
- The sheet is 3:2, the aspect the image model paints at (the painted sheet is 1536 x 1024).

## What the sheet draws

Height-coloured terrain and sea from one height raster over the whole sheet (the 600 m square, the south-west island,
Hidamari and the northern foothills; everything else fades to paper), forest cover from the placed trees, land
contours, the water the game tests against (canal, park pond, plaza basin, the woodland lake), roads, streets, lanes
and trails, the mini-mega's two riding sections with their gap, rollout and ladder, the Mega Park's riding footprint,
buildings, landmarks and props, and the spawn. Sunset Pier's 170 x 132 m deck, riding features and trees are drawn
from `skatepark/park.json` by [`pier_plan.py`](../world/map/pier_plan.py).

## Zones

Each zone is a travel target with a key, name, position, yaw and hint. Zones are snapped to a walkable polyline
(road, lane, route or stair), so travel lands on paved ground; the game traces the ground again on arrival.

| Region | Zone keys |
| --- | --- |
| Main road and hamlet | `spawn`, `hamlet`, `mega` |
| South-west island | `fishing`, `cove`, `landing`, `temple` |
| Hidamari | `arrival`, `arcade`, `plaza`, `harbor`, `hillside`, `park`, `station`, `foothills` |
| Elsewhere | `forest_lake`, `megapark`, `skatepier`, `hippodrome`, `zeppelin_forest`, `zeppelin_city`, `zeppelin_megapark` |

`UJapanMap` adds a `skatepier` stop from `skatepark/park.json`, and a `hippodrome` stop (by Hudson, at the
grandstand) from `hippodrome/hippodrome.json`, when `map.json` has none ([HIPPODROME.md](HIPPODROME.md)).

## Saved skate-line markers

Press **F5** while grounded to save a new place and heading; **F9** returns to the selected marker. Each F5 press
adds a new `Marker N`, keeping your earlier locations. Open the map with **M** to enter a name and **Save here**,
choose **Previous** / **Next**, **Rename selected**, or **Delete selected**. Clicking a blue **M** pin selects and
returns to that place. With the map open, the controller's top face button saves a new place and its left face
button returns; the hint names the connected pad's buttons. Controller users can choose any saved pin with the
stick or d-pad and travel with the bottom face button. The phone receives the same named marker zones.

Up to 64 places are saved, with unique names of 1–48 characters. Positions, headings and the selected marker are
written to `markers.json` beside the game's preferences file (normally `unreal/Saved/settings.txt` in development;
in the packaged game's user container beside `settings.txt`). They survive character switches and game restarts,
including a new package with the same bundle identity. Saving uses a temporary sibling and an atomic replacement;
a failed write or unreadable save preserves the previous file and reports the problem.

Returns stow vehicles and clear momentum through normal travel. A local ground trace keeps a place under a roof
under it. Missing, changed or obstructed ground refuses travel and preserves the marker. An airborne or ungrounded
save attempt also leaves previous places intact.

The durable review scenario is `uv run atelier qa yorimichi session_marker --port PORT --save-file FILE`. Start a
fresh guarded CairoBotw game with `-markersave=FILE` pointing to a new review file; the scenario refuses to operate
on a game using the player's normal save. It checks keyboard input, several named places, selection, rename/delete,
map/phone travel, airborne refusal, roofs, blocked or removed floors and character switches. Restart with the same
review save and add `--reload` to verify persisted places, headings and selection. Evidence goes to
`build/yorimichi/session-marker/review/`; test files remain under `build/`.

## The painted sheet

The painted sheet is committed in [`world/map/painted/`](../world/map/painted/), because it cannot be reproduced
from data:

| File | Contents |
| --- | --- |
| `world_map.png` | The painted sheet |
| `world_map_bounds.json`, `world_map_registration.json` | The bounds and projection knots it was painted for |
| `world_map_calibration.json` | The pixel control points of the axis calibration |
| `world_map_provenance.json` | Model, prompt and inputs, with each earlier version's record nested under `parent` |
| `island_repaint.provenance.json` | The ledger of the south-west island repaint call |
| `sunset_pier_repaint.provenance.json` | The shared paid-call ledger for the enlarged pier and moved island |

`build_map.py` uses the painted sheet only while its bounds and knots match the current ones exactly; otherwise it
falls back to the generated sheet. Never stretch old artwork over a changed world: every pin would move off its
destination.

To make a painted sheet the map:

```sh
uv run python games/yorimichi/world/map/promote_map.py build/yorimichi/map/<sheet>.png
```

[`promote_map.py`](../world/map/promote_map.py) writes `map.png`, `map.jpg` and `painted.txt` in
`build/yorimichi/map/`, and the committed sheet, bounds, registration and provenance (from a `paint_provenance.json`
next to the sheet) in `painted/`.

### Local repaints

Fix a wrong landmark or a redesigned area by repainting only that area, never the whole sheet. The mini-mega
landmark and the south-west island were corrected this way. [`repaint_island.py`](../world/map/repaint_island.py)
now handles the enlarged pier and the moved island together:

```sh
uv run atelier build yorimichi world.layout
uv run python games/yorimichi/world/map/build_map.py                # current generated plan and travel zones
uv run python games/yorimichi/world/map/repaint_island.py prepare    # old sheet crop and exact pier/island plan
uv run python games/yorimichi/world/map/repaint_island.py paint      # one GPT Image 2.5 Sunburst call
uv run python games/yorimichi/world/map/repaint_island.py register   # fit, blend, check -> world_map_candidate.png
uv run python games/yorimichi/world/map/promote_map.py build/yorimichi/map/sunset_pier_repaint/world_map_candidate.png
```

- `prepare` keeps the committed sheet as the parent and writes a 3:2 crop with a plan in the same frame: the
  current pier footprint and features, island coastline, rock, cove, tree crowns, stair, torii and temple.
- `paint` sends both crops and the aerial island concept to `gpt-image-2.5-sunburst` (quality high). Its provenance
  file goes through `atelier.ai.ledger` before and after the call; while it exists the call is never sent again.
- `register` fits the island and pier independently to their data footprints, matches the sea colour,
  blends through a feathered mask around the affected land and water, and checks that every pixel outside the mask
  equals the parent. It writes `registration-check.json` and `registration-check.jpg` (data coastline and stair over
  the result).

Sheet bounds stay fixed. The southern projection control and the island's landing/temple zones follow the new
location. Work files go to `build/yorimichi/map/sunset_pier_repaint/`. Completed paid revisions and older evidence
belong in the archive; an existing ledger is never removed to retry an uncertain submission.

### Rules

- Never hand-place anything on the sheet. A missing feature is missing from `world.json`; fix it there.
- Check landmark identity and orientation as well as road alignment: a yellow dot at the mini-mega was once painted
  as a cottage, which is why `build_map.py` draws the ramp itself.
- Label only what a player can reach or see as a destination.

## In the game

- **Desktop:** M opens and closes the map. `UJapanMap` draws the sheet fitted to the viewport, numbered pins with
  names and the player arrow; clicking a pin travels.
- **Controller:** View / Touchpad / Minus opens and closes it. The left stick moves a reticle that catches the nearest
  pin, the d-pad hops to the nearest pin in that direction, the right stick pans, the shoulders zoom about the
  reticle, the bottom button travels and the right button closes. The top/left buttons set/return to the selected saved marker;
  other pad buttons are swallowed. Moving the mouse
  hands the sheet back to hover and click; the header and hint lines name the connected pad's buttons.
- **Phone:** `{action:"map"}` returns the bounds, knots, zones and the sheet URL (`/map/map.jpg`, served from
  `build/yorimichi/map` by the `[stream] routes` entry in `game.toml`); `{action:"teleport", zone}` travels. The
  status message carries `yaw`. [`phone/map.js`](../phone/map.js) draws the pins and the player;
  [`phone/map-smoke.mjs`](../phone/map-smoke.mjs) exercises it against a running stream
  (`atelier stream yorimichi start`), and [`phone/map-scroll-smoke.mjs`](../phone/map-scroll-smoke.mjs) tests the
  touch gestures offline.

Travel goes through `AWandererCharacter::TravelTo`: it cancels a zeppelin ride, stows the board and the sailboat,
clears momentum, traces the ground under the target and places the character facing the zone's yaw. The phone's
"back to spawn" button uses the same path.

`uv run atelier play yorimichi -- -mapqa -reviewdir=DIR` travels to every zone in turn, screenshots each
(`map_NN_key.png`) and the open map (`map_overlay.png`), and writes `map_qa.json` (target, landed position, drift,
on-ground).
