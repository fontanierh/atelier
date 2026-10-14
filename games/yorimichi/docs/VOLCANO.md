# The volcano

The volcano north of Hidamari is a broad cone with a level caldera at its top, built to hold a park. Its shape,
snow, rock and ground colours come from [`hidamari/mountains.py`](../world/regions/hidamari/mountains.py). Trees
and rocks are planted by [`hidamari/layout.py`](../world/regions/hidamari/layout.py), and pine bands by
[`forest/ecotone.py`](../world/regions/forest/ecotone.py).

## Shape

All values are Blender metres (x east, y north).

| | Value | Constant |
|---|---|---|
| Centre | (850, 2400) | `VOLCANO` |
| Base radius (where the cone meets the foothills) | 1480 m | `BASE_RADIUS` |
| Crest radius (it wanders by about 35 m) | 470 m | `RIM_RADIUS` |
| Crest height | 690–720 m, broken into crags and notches, up to about 20 m, gathered in groups; three spires reach 790–800 m | `CREST` |
| Inner wall | steps down in warped cliff bands and ledges every 16 m | `CRAG_STEP` |
| Upper flank | granite ribs about 20 m across run downslope for 260 m below the crest; snow gathers between them | `_cone` |
| Caldera floor | level at 640 m (±1 m), 660 m across | `FLOOR_RADIUS`, `caldera_floor()` |
| Floor to crest | 45 m nominal; 47–145 m round the broken crest | `DEPTH` |

The floor holds a 340 × 390 m footprint at any heading, and the crest stands more than 40 m above it all the way
round. `test_northern_landscape.py` checks both.

The floor is sized for [Crater Park](https://github.com/fontanierh/crater-skate-park):
- **Fit:** a 337.95 × 384.51 m block with a corner radius of 256 m. It keeps at least 62 m to the wall's foot at any
  heading, room for the earth slopes round its edges. Heading 185° turns its high west side toward the tallest part of
  the crest.
- **Height:** it stands high in the crater. Its main deck is about level with the crest's lowest stretch (687 m), and
  its tallest ramp (720 m) rises just over most of the crest. Riders on it see the far horizon over the rim; nothing
  of the park can be seen from the city, Belmonte, the Mega Park or the volcano's flanks.
- **Ground:** it is a cut block of hillside whose west side stands up to 60 m above the floor. Like the Mega Park, it
  has a terrain stamp: the floor lowered under it and slopes up its high sides ([CRATERPARK.md](CRATERPARK.md)).

The wall steepens toward the crest. Its foot moves in and out by up to 12 m in collapse scallops.

The former, smaller summit at (550, 1930) stands on as the volcano's western shoulder. Within 1150 m of the Mega Park,
the ground is whichever is higher, the former cone or the new one. So the ground round the park (and its terrain
stamp, `megapark/placement.py`) is unchanged.

## Snow, rock and trees

The larger cone keeps the old one's look at the same share of its slope:
- `stretch(r)` maps a radius on the old cone (rim 95 m, base 1170 m) to the same place on this one.
- `lifted(z)` scales a height above the apron by `LIFT` (1.35).

The tree line, pine band, exposed rock, snow line and outcrop band all use these two helpers.

- **Snow** runs down 40 seeded gullies from the crest and lies in patches on the caldera floor, with drifts at the
  wall's foot. The crest stays bare. The mask (`north_snow.png`, 1024² at 2.5 m) also records the rock band and the
  Belmonte join for the ground material (`unreal/Scripts/mountain_material.py`). Loose rocks (`HD_NorthRock*`) use its
  instance `MI_NorthRockCaps` (`Caps` 1): they wear patchy snow on their flattest tops where snow lies thick round
  them, rather than the ground's mask cut across them.
- **Trees** stop at the lifted tree line and stay out of the caldera, which is left open for its park. The closed
  forest ends about `lifted(330)`; above it an olive alpine meadow (`colours`) runs up to the cliffs at about
  `lifted(360)`, and only scattered dark pines (about one in seventeen sample points) climb it to about `lifted(395)`.
- **Outcrops** and scree cover the flank from the crest down to about 970 m out.

## Belmonte

The valley moved 600 m north to keep its distance from the volcano's northern foot (`belmonte/layout.py`
`NORTH_SHIFT`). The foothills now reach its southern join at `SOUTH_JOIN` (y = 3600). Along Belmonte's apron, the
volcano's foot runs on into the collar rather than easing back to the far hills.

The country north of the far hills sinks under the foothills, as the far hills do. The country runs out to sea 600 m
further north too. The world map's Belmonte knots moved with it (`map/map_projection.py`), so Belmonte keeps its
painted pixels.

The painted sheet's middle band was repainted once for the new volcano by
[`map/repaint_volcano.py`](../world/map/repaint_volcano.py). Its ledger is `painted/volcano_repaint.provenance.json`.
