# Tree house

A children's secret base hidden on the west hillside below the Woodland air-station trail. From the trail it is one
small hut in a maple. Through the hut, twelve rope bridges reach nine more places in the trees, stepping down the
slope to a lookout whose crow's nest rises above the canopy and looks out to the sea. This document describes the
house and the rules it is built to; the files, build details and pitfalls are in the region's
[README](../world/regions/treehouse/README.md).

[`world/regions/treehouse/layout.py`](../world/regions/treehouse/layout.py) is the single source of truth: places,
bridges, stairs, slide, anchor trunks, the canopy trees round the house and which existing trees must go.
`gen_world.py` calls its `integrate()` after every other region except the house lots' dressing and the Mega Park
trail and far-forest clearing, and everything else reads what it writes into `world['treehouse']`. Positions are
Blender metres (x east, y north); heights are absolute, in metres.

## Build and check

```sh
uv run atelier build yorimichi unreal.treehouse data.stage
```

| Step | What it makes |
| --- | --- |
| `world.treehouse_trees` | The four tall canopy trees ([`trees.py`](../world/regions/treehouse/trees.py)) |
| `world.layout` | The world with the tree house integrated (`world['treehouse']`, `treehouse/layout.json`) |
| `world.treehouse_textures` | Game-ready textures from the committed paintings (`tools/treehouse_textures.py finish`) |
| `world.treehouse_props` | The 13 Tripo props, reduced and sized ([`props.py`](../world/regions/treehouse/props.py)) |
| `world.treehouse` | TH_Structure, TH_Frame, TH_Trunks, TH_Dressing, the prop placements and `runtime.json` ([`build.py`](../world/regions/treehouse/build.py)) |
| `unreal.treehouse` | The Unreal import (`unreal/Scripts/import_treehouse.py`) |
| `data.stage` | Copies `runtime.json` into the game's data |

The paintings, textures and Tripo models are paid calls run by hand; their results are committed in
[`assets/treehouse/`](../assets/treehouse/README.md).

| Scenario | What it does |
| --- | --- |
| `atelier qa yorimichi treehouse LABEL` | Captures the 22 reference views in the game, each beside its painting in `assets/treehouse/refs/` |
| `atelier qa yorimichi treehouse_tour plan\|film\|cut LABEL` | A fifteen-shot camera tour of the house, cut into `build/yorimichi/treehouse/tour/LABEL.mp4` |
| `atelier qa yorimichi treehouse_walk plan\|film\|cut TAKE` | Cairo walks every place with the follow camera; `film --rehearse` reports where he gets stuck |
| `treehouse_walk_live` | The in-game half of `treehouse_walk`, sent over the live bridge |

[`plan_views.py`](../world/regions/treehouse/plan_views.py) draws `plan-map.png` (top view) and `plan-section.png`
(side view along the main path) into `build/yorimichi/review/treehouse/plan/`.

## How you find it

The trail runs along the top of the hillside in a cutting, so the woods below it cannot be seen from the path. At
about (-133, 211) there is a low gap in the south bank: level stepping stones lead up through it, a stride apart on
the flat and a short flight of stone steps cut into the steep part of the bank (each top flush with the ground on its
uphill side, no rise over 17 cm), to a wider, level foot stone against the lowest plank step and one rise under it.
Ten plank steps (16.6 cm rise, 29 cm tread, 1.4 m wide) climb from it to the little hut's north door. The hut sits
3 m above the ground in its maple, half inside the leaves. That is all you see from the trail.

Step through the hut onto its south porch and the hillside opens up: the ground drops away, and bridges run out to
the Map room and on to the Heart room below. The porch is the reveal: the layout clears the crowns on the lines of
sight from the porch to every other place, so the crow's nest shows past the Heart room's crown.

## Places

Heights are the deck's height and how far it stands above the ground under it. A landing is an octagon round its
tree; a room stands beside its trunk, in the direction no bridge uses, on a deck with a porch at each door.

| # | Place | Position | Deck | Above ground | What is there |
| --- | --- | --- | --- | --- | --- |
| 1 | Little hut | (-135, 198.5) | 76.7 | 3 m | The only part seen from the trail: a hut beside its maple, north door, south porch with a bench and banner |
| 2 | Map room | (-144, 185) | 76.1 | 6 m | Map table, four bookshelves, maps, globe, kite; the first junction |
| 3 | Heart room | (-131, 168) | 74.2 | 11 m | The big octagonal hall beside the camphor with the shimenawa rope, seen through its round window |
| 4 | Kitchen | (-117, 175) | 74.8 | 10 m | Clay stove and chimney pipe, log table and stools, drying persimmons |
| 5 | Sleeping nest | (-160, 172) | 74.8 | 9 m | Futons with patchwork quilts, two hammocks slung across the front corners from wall pegs |
| 6 | Boat room | (-110, 161) | 73.8 | 13 m | An old rowboat hauled up the tree, upside down as a roof |
| 7 | Slide tree | (-122, 149) | 72.8 | 15 m | A 30-degree spiral slide round the trunk down to the forest floor: the back door |
| 8 | Pulley deck | (-150, 157) | 73.2 | 13 m | A crane arm with a basket on a rope to the ground |
| 9 | Chime tree | (-135, 145) | 72.4 | 16 m | A small ring landing hung with wind chimes, where three bridges meet |
| 10 | Lookout | (-148, 140) | 71.8 | 16 m | 96 steps spiral up the trunk to the crow's nest at 89 m (33 m above the ground): telescope, bell, flag, awning |

Every deck is between 71.8 and 76.7 m, so the whole house feels level while the hill falls away under it. From the
trail end it looks like a hut on the ground; at the far end you are four or five storeys up.

| Room | Inside | Walls to the plate |
| --- | --- | --- |
| Map room, Kitchen, Sleeping nest (`HUT`) | 7 x 6 m, a door in each gable end | 3 m (`WALL`) |
| Little hut (`ENTRY_HUT`) | 4.8 x 6.1 m | 3 m |
| Heart room (`HALL`) | Octagon 9 m across | 3.2 m |
| Boat room (`BOAT`) | 7 x 3.2 m under the hull | Gunwale 2.6 m |

Every door is 1.3 x 2.5 m (`DOOR`), and a 1.4 m lane runs from door to door with nothing in it.

## Bridges

Twelve rope bridges, 1.4 m wide (`BRIDGE_WIDTH`), with plank floors and rope handrails. They sag 3.2% of the span,
less where that would tilt an end more than 1 in 4 (a short bridge between decks at different heights hangs almost
straight), so every one can be walked without steps. A bridge leaves its deck no more than 40 degrees off square
(`SQUARE`); where the straight line would leave at a sharper slant it lands on the edge that faces the other end
instead. The end posts and their lanterns stand on the deck's edge, splayed 35 cm out past the handrails
(`BRIDGE_SPLAY`), so the 1.4 m way on stays clear, and the mouth between them is planked out to the edge.

| From | To | Span | Drop | Height above ground (middle) |
| --- | --- | --- | --- | --- |
| Little hut | Map room | 3.2 m | 0.6 m | 5.3 m |
| Map room | Heart room | 15.9 m | 1.9 m | 8.3 m |
| Map room | Sleeping nest | 9.9 m | 1.3 m | 6.8 m |
| Heart room | Kitchen | 4.2 m | -0.6 m | 10.4 m |
| Kitchen | Boat room | 6.5 m | 1.0 m | 11.7 m |
| Boat room | Slide tree | 9.4 m | 1.0 m | 14.4 m |
| Slide tree | Chime tree | 7.0 m | 0.4 m | 15.1 m |
| Chime tree | Lookout | 6.2 m | 0.6 m | 15.8 m |
| Heart room | Pulley deck | 13.0 m | 1.0 m | 11.7 m |
| Sleeping nest | Pulley deck | 9.5 m | 1.6 m | 11.3 m |
| Pulley deck | Lookout | 9.3 m | 1.4 m | 14.2 m |
| Heart room | Chime tree | 13.2 m | 1.8 m | 13.8 m |

Spans are from deck edge to deck edge. The bridge from the Map room lands on the Heart room's deck beside the
camphor, so the way past the trunk to the hall's door keeps 1.4 m clear.

The route is a big loop with the Heart room in the middle:

- East side: Little hut, Map room, Heart room, Kitchen, Boat room, Slide tree, Chime tree, Lookout.
- West side back: Lookout, Pulley deck, Sleeping nest, Map room.
- Short cuts from the Heart room to the Pulley deck and the Chime tree.

Ways out: back through the little hut, or down the slide to the forest floor at the south-east end. The pulley basket
and its rope reach the ground under the Pulley deck but are scenery.

## Trees

The ten anchor trunks (0.45 to 1.15 m in radius) are built with the house, with flared roots. Their crowns are the
game's own painted trees, placed larger and raised so the crown sits over the roof. The Heart room's camphor is the
only really big tree, and the only one with a shimenawa.

The decks stand 3 to 16 m up, above the tops of the hillside's maples, so `trees.py` makes four tall canopy trees
(maple, crimson, amber, ginkgo) the same way as the rest of the forest, and `layout.py` places them round every place
and bridge (`CANOPY`):

- each is scaled so its crown top stands about 1 m under to 3.5 m over the nearest deck, so from above the house sits
  just over a carpet of crowns and on the walks the crowns frame the rails;
- they keep 2.5 m of headroom over every deck and roof and take the spots of the short broadleaves (cedars and pines
  stay as the dark accents);
- a ring of denser autumn forest, 50 m round the house (`FOREST`), hides it from the trail.

Existing trees go only where they would pass through the build: a trunk through a floor, leaves through a bridge, a
roof or the slide, anything hugging an anchor trunk, and the crowns on the sight lines from the porch and from the
crow's nest to every bridge. `screen.py` plants tall trees where the lookout would show over the forest from the lake
trail.

## Script or Tripo

The script ([`build.py`](../world/regions/treehouse/build.py)) makes everything that must fit the layout to the
centimetre (decks, bridges, stairs, rails, slide, rooms, roofs), everything repeated many times (lanterns, glass
floats, fuurin, noren, crates, pots, rope coils) and everything made of simple shapes (planks, rope, cloth, boxes,
jars). Its faces carry the game's palette as vertex colours, multiplied in `M_TreeHouse` by a painted detail texture
per surface or carrying a painted picture (noren, maps, quilts, rugs, the flag).

Tripo makes only one-off hero pieces with round, hand-made forms, each from its own painted reference of the object
alone, then reduced, sized and brought to the palette's brightness by a calibrated gain:

| Prop | Where |
| --- | --- |
| Clay kamado stove with pot, kettle and logs (`kamado`) | Kitchen |
| Tree-stump table with a cast-iron kettle (`stump_kettle`) | Heart room |
| Brass telescope on a tripod (`telescope`) | Crow's nest |
| Canvas backpack (`backpack`) | Little hut, Map room |
| Ship's bell on a bracket (`bell`) | Crow's nest, Heart room |
| Desk globe (`globe`) | Map room |
| Woven basket on ropes (`basket`) | Pulley deck |
| Water barrel with a ladle (`barrel`) | Kitchen |
| Futon with a patchwork quilt (`futon`) | Sleeping nest |
| Log table with teapot, persimmons and flowers (`log_table`) | Kitchen |
| Tall bookshelf (`bookshelf`) | Map room, Heart room |
| Plank-on-crates desk with map, compass and lamp (`crate_desk`) | Map room |
| Crate planter with autumn flowers (`planter`) | Decks |

Furniture the player could walk into gets a simple collision box; small and hanging things get none.

## Look

- Surfaces: 26 painted textures, 15 tileable surfaces (bark, planks, shingles, plaster, rope, canvas...) turned into
  neutral detail maps on the game's palette and 11 one-off pictures that keep their colours.
- Light: warm point lights from the lanterns, a soft glow in every window's opening and a warmer colour grade inside
  the rooms. `build.py` writes them to `treehouse/runtime.json`, which `AJapanWorld` merges into the world data at
  load.
- Camera: the rooms are big enough for the chase camera to follow Cairo in by one door and out by the other, with the
  furniture against the walls; what still hides him dithers away (walls, rails, props, and the near walls and roof of
  the room he is in), and the noren part round him and swing back ([CAMERA.md](CAMERA.md)).

## Design rules

- The little hut reads as small and alone from the trail; the porch reveal shows the Map room, the Heart room and,
  beyond, the crow's nest.
- The character steps 45 cm and walks slopes up to about 44 degrees, and there is no ladder climbing, so every way up
  is stairs: no rise over 18 cm (`RISE`), no bridge end steeper than 1 in 4, every way 1.4 m wide.
- Nothing stands in a lane, a doorway or a bridge mouth. Furniture stands against the walls, no post stands free in a
  room (the hammocks hang from wall pegs), and the roofs start 3 m up, so the chase camera can follow Cairo through
  every room.
- No existing tree or crown pokes through a floor, a wall or a roof.
- The references show things the house does not have: a shimenawa on every trunk (only the camphor has one), a
  climbable loft (the Heart room's ladder and loft are for looks only), a second tower in a few views, and small
  rooms. The layout wins.
