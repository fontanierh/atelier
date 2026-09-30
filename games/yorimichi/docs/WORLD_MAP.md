# World map: how it is made

> Moved from the prototype repository on 29 September 2026. Paths are translated to this repository where the file moved; paths still starting with `japan/` or `output/imagegen/` refer to the prototype archive (authoring tools, earlier revisions, review images). See [docs/MIGRATION.md](../../../docs/MIGRATION.md).

`games/yorimichi/docs/yorimichi_world_map.png` is drawn from the generated layout, never from screenshots, so every
position and distance on it is the one the game uses. Regenerate it after any world change:

```sh
python3 japan/tools/render_map.py                      # reads japan/out, writes games/yorimichi/docs/yorimichi_world_map.png
python3 japan/tools/render_map.py --data path/to/out   # another checkout's generated output
```

Needs only NumPy and Pillow (no matplotlib). Rendering takes a few seconds.

## Inputs (all produced by `gen_world.py` and the village/skate layout steps)

| File | What the map takes from it |
| --- | --- |
| `out/world.json` | `size` (600 m), `road` (624 samples with height), `road_width`, `rail_runs` (guardrail polylines), `instances` (every placed prop by asset name: x, y, z, yaw, scale), `player_start`, `shots` (scripted camera positions), `houses` (the lots of the houses on the main road: centre, yaw, outline and roof footprint in the lot frame), `village` (lanes as `surface_paths`, `buildings` with footprint and yaw, `planting_beds`, `residents`, signs), `mega` (trail polyline and start point), `wind_dir`, `wind_speed` |
| `out/heightmap.npy` | 301 × 301 heights in metres over the square, 2 m spacing, row 0 = south, column 0 = west |
| `out/farhills.npy` | 96 × 96 heights of the 6.4 km scenery ring around the square (inset only) |

Coordinates are Blender metres: x east, y north, z up. Unreal uses the same values in centimetres with y negated;
the map stays in the Blender frame with north up, so it matches `gen_world.py` and `world.json` directly.

## Layers, bottom to top

1. **Terrain**: the heightmap upsampled to 4 px/m (bicubic), coloured by height (deep to shallow sea below 0 m,
   sand at the shore, meadow to highland greens above), multiplied by a hillshade lit from the north-west.
2. **Forest cover**: every `Tree_*` instance is binned into 2 m cells and blurred. Warm species (maple, ginkgo,
   broadleaf) tint rust, evergreens (pine, cedar) tint dark green; the mix is normalised to the 85th percentile of
   local density, so clearings (road corridor, beach, hamlet, ramp run) read as clear ground.
3. **Contours** every 5 m from the upsampled heightmap, bold every 25 m, drawn as the edges of threshold masks.
4. **Grid** every 100 m with coordinate labels.
5. **Guardrail runs**, then the **road** (dark casing, asphalt fill, centre line), at true width.
6. **Hamlet**: lanes at their 2.6 m width, planting beds, building footprints rotated by yaw and labelled,
   residents, waymark signs. **Mega ramp trail** at its 8 m width with its start point.
7. **Props**: the houses on the main road (lot outline with its hedge, then the roof footprint, rotated by yaw), poles, torii, lanterns. **Spawn** and **camera shots**.
8. **Labels**, title, legend, counts, scale bar, north arrow, wind rose (the arrow points where the wind blows),
   and the surroundings inset with the playable square outlined.

## Conventions worth keeping

- Never hand-place anything on the map; if a feature is missing, it is missing from `world.json`, which is the
  real problem to fix.
- Keep the map in the Blender frame. Anyone reading `gen_world.py` or the village layout can match numbers 1:1.
- Label only what a player can reach or see as a destination. Scripted camera shots are drawn small because they
  are tooling, not world content.

## Proposed expansions (Hidamari)

Use the same renderer with an explicit planning overlay:

```sh
python3 japan/tools/render_map.py --proposal games/yorimichi/docs/hidamari/location.json --out games/yorimichi/docs/hidamari/location-map.png
```

This reuses the actual terrain, forest, road, building and trail layers from the normal renderer, at the same metre coordinates, then extends the sheet to include a proposed city. The normal map command remains unchanged. `location.json` owns the proposed bounds and districts; none are manually painted onto an image or added to the runtime `world.json`. The red connection begins at the current generated road's eastmost sample.

The existing playable boundary is dashed charcoal; planned Hidamari is dashed ochre. Outside the actual terrain square the background is explicitly ungenerated, not inferred terrain or sea. Proposed district rectangles are planning zones, not built geometry. Do not imply the southwest island has surveyed coordinates until its layout supplies them.

Overlay the implemented city's actual street samples, rotated building footprints and landmark positions with:

```sh
python3 japan/tools/render_map.py --proposal games/yorimichi/docs/hidamari/location.json --built-city build/yorimichi/hidamari/city.json --out games/yorimichi/docs/hidamari/current-map.png
```

This retains the original map raster and coordinate system. District colors remain concept zones; the new streets and footprints come directly from the same sidecar used by the game. The city terrain is not rasterized in this sheet, so it is a placement map rather than a new terrain survey.

The base map now extends south to include the generated southwest island, shore lane, and kite crossing.

## In-game map (M on the desktop, Map on the phone)

The game shows a painted map of the whole world with the player's position and heading, and lets the player travel
to any zone. Three files under `build/yorimichi/map/` drive it, all generated:

```sh
python3 games/yorimichi/world/map/build_map.py                 # rough.png/jpg (label-free data render), map.json, map_lines.json
OPENAI_API_KEY_FILE=... python3 japan/tools/paint_map.py <in-game stills...> --n 2   # painted_N.png + paint_check_N.jpg
python3 games/yorimichi/world/map/promote_map.py build/yorimichi/map/painted_1.png                        # -> map.png (game), map.jpg (phone)
```

- `build_map.py` draws the sheet from the same data as this document's map, extended to the whole playable world
  (the 600 m square, the south-west island, Hidamari): `hidamari/layout.py` and `southwest/island.py` supply the
  city and island heightfields, `farhills.npy` the scenery ring, `world.json` and `city.json` every road, lane,
  building and boat. The sheet is 3:2 (`bounds` in `map.json`, Blender metres, north up) because that is the aspect
  gpt-image-2 paints at. It also picks the **zones**: each one is snapped to a walkable polyline (road, lane, route,
  the island stair), so travelling lands on paved ground; the game re-traces the ground height on arrival anyway.
- `paint_map.py` sends the rough sheet plus a few in-game stills to gpt-image-2 and asks for the game's own look
  while keeping every road, coastline and block in place. `paint_check_N.jpg` overlays the generated polylines and
  zones on each result: promote only a sheet whose roads sit on the magenta lines. `paint_provenance.json` records
  the prompt, inputs and hashes. `rough.*` is kept so a re-run after a world change starts from fresh data.
- `promote_map.py` copies the chosen sheet to `map.png`/`map.jpg` and writes `painted.txt`; `build_map.py` then
  leaves those two alone when it regenerates the rough sheet.

Runtime: `UJapanMap` (Source/JapanProto/JapanMap.*) loads `map.json` and `map.png`, converts zones to Unreal
(`AJapanWorld::ToUE`, yaw negated) and draws the Slate overlay (sheet fitted to the viewport, numbered pins with
names, the pulsing player arrow); clicking a pin calls `AWandererCharacter::TravelTo`, which stows the board and the
kite, clears momentum, traces the ground and places the character facing the zone's yaw. `Back to spawn` on phones
uses the same path. `-mapqa -reviewdir=DIR` travels to every zone in turn, screenshots each (`map_NN_key.png`),
screenshots the open map (`map_overlay.png`) and writes `map_qa.json` (target, landed position, drift, on-ground).

With a controller the map opens and closes on View / Touchpad / Minus. The sheet keeps Slate focus while open and
reads the pad itself: the left stick moves a reticle that catches the nearest pin (and settles on it when let go), the
d-pad hops to the nearest pin in that direction, the right stick pans, the shoulders zoom about the reticle, the bottom
button travels and the right button closes. Other pad buttons are swallowed, so nothing fires behind the map. Moving
the mouse hands the sheet back to hover and click; the header and hint lines name the buttons of the connected pad.

Phones get the data over the stream: `{action:"map"}` returns bounds, zones and the sheet URL (`/map/map.jpg`,
served by the stream server straight from `build/yorimichi/map`, game.toml `[stream] routes`), `{action:"teleport", zone}`
travels; the status message carries `yaw`. `phone/map.js` draws pins and the player on the sheet; `node games/yorimichi/phone/map-smoke.mjs`
exercises it against a running stream.

### PR 4 integration validation

Integrated on top of the PR 3 landing and temple collision repairs. The native
build and generated 14-zone map passed. `out/map/pr4-qa/map_qa.json` records all
14 destinations grounded and stationary, zero horizontal drift, and at most
97.9 cm correction from the authored height to the built surface. The desktop
map overlay was visually checked.

The phone map smoke test ran on a separate local stream while the live phone
session remained connected. It verified 14 pins/list entries, travel out of an
active 610.9 cm/s skate ride (board stowed and speed zero on arrival), marker
alignment, list travel to the island landing, and return to spawn. The isolated
web-output build also passed. Pinch zoom remains outside this change; the list
provides access to the closely spaced southwest pins.

### Mini-mega landmark correction (2026-09-09)

The compact painted sheet had a cottage at the mini-mega. The rough generator supplied only a yellow dot there,
so positional checks alone missed the incorrect landmark identity. `build_map.py` now draws the real two wooden
riding sections, the gap, ladder and rollout from `world.json.mega`. Future paint prompts explicitly prohibit a
house/roof at that location. Review landmark identity and ramp orientation as well as road alignment.

The live painting was corrected locally with **GPT Image 2.5 Sunburst, high quality**, using the imagegen skill CLI,
the current map crop/full sheet and real game ramp stills. The generated landmark was registered to the existing
world-to-map projection, then blended only into the small clearing. 99.62% of the original map pixels remain
identical. Existing map bounds, projection and travel destinations were retained. The old painting and provenance
are preserved in `docs/map/mini-mega-fix/`.

- Generation prompt/result/provenance: `output/imagegen/mini-mega-map/` (repo root).
- Deterministic placement: `tools/register_mega_map.py` reconstructs `map-candidate.png` from the preserved original
  and the generated crop, and writes an outside-edit pixel equality check.
- Promotion uses `tools/promote_map.py`; regenerate the road/zone alignment overlay and visually check the phone
  map while standing at the destination (`streaming/mega-map-smoke.mjs`).
- Do not repaint the entire map just to fix a landmark. New image generation uses Sunburst; untouched historical
  pixels retain their original provenance. The earlier GPT Image 2 references above describe the original process.

### South-west island repaint

The painted sheet showed the old round island after `southwest/island.py` was redesigned. Only the island was
repainted, the same way as the mini-mega fix, with `games/yorimichi/world/map/repaint_island.py`:

1. **prepare.** It keeps the committed sheet as the parent. It finds the old painted island and the new data island
   (the heightfield through the map projection) and picks a 3:2 crop box around both, `[0, 707, 476, 1024]`. It
   writes that crop of the sheet and a plain plan of the new island in the same frame:
   - the coastline, rock and cove;
   - every placed tree crown, by species;
   - the stair with its torii, and the temple.
2. **paint.** One **GPT Image 2.5 Sunburst** call (quality high, `/v1/images/edits`) takes the two crops and the
   aerial island concept. The repository has no shared ledger module, so
   `painted/island_repaint.provenance.json` is the call's ledger: it holds the prompt, the input and output hashes
   and the usage, and is written before and after the call.
3. **register.** It fits the painting to the projection: a scale and offset that lay the painted island on the data
   island. The fit's intersection over union with the data island's main body is 0.937. It shifts the painting's
   sea colour to the sheet's, measured on the open water around the island. It then blends the painting in through
   a feathered mask that covers only the old island, the new island with its stacks, and their shallows.

The result:

- **Outside the mask, every pixel is identical to the parent.** The script checks this over the whole sheet.
- **94.70% of the sheet's pixels are unchanged.** The edit's bounding box is `[36, 735, 376, 1024]`.
- **Bounds, projection, registration and calibration are unchanged.** `build_map.py` still selects the registered
  painted sheet.
- **The zones keep their positions and yaws.** Only the temple's height follows the lower terrace. The landing pin
  sits on the painted cove and the temple pin on the painted temple.

`register` writes `paint_provenance.json` next to the candidate, with the parent's record nested under `parent`.
`promote_map.py` promoted the candidate and copied that file to `painted/world_map_provenance.json`. The work files
are in `build/yorimichi/map/island_repaint/`:

- the parent sheet;
- the crops;
- the generated painting;
- `registration-check.json`;
- `registration-check.jpg`, which draws the data coastline and stair over the parent and the result.
