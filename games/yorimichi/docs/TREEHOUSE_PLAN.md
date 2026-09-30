# Tree house plan

A children's secret base hidden on the west hillside below the Woodland air-station trail. From the trail it is one
small hut in a maple. Through the hut, rope bridges reach nine more places in the trees, stepping down the slope
to a lookout whose crow's nest rises above the canopy and looks out to the sea.

- Layout, the single source of truth: `world/regions/treehouse/layout.py` (places, bridges, stairs, slide, anchor
  trunks, the canopy trees round the house and which existing trees must go). `gen_world.py` calls its
  `integrate()` last, after every other region, and everything else reads what it writes into `world['treehouse']`.
- Drawings: `world/regions/treehouse/plan_views.py` writes `plan-map.png` (top view) and `plan-section.png` (side
  view along the main path) to `build/yorimichi/review/treehouse/plan/`.
- Art it follows: the concepts in `assets/treehouse/concepts/` (`tools/treehouse_concepts.py`) (overview, reveal, glimpse, lookout, room) and one
  Sunburst reference per view in `assets/treehouse/refs/`, each with its prompt and provenance.

All positions are Blender metres (x east, y north); heights are absolute, in metres.

## How you find it

The trail runs along the top of the hillside in a cutting, so the woods below it cannot be seen from the path. At
about (-133, 211) there is a low gap in the south bank: six stepping stones lead down through it, flush with the
ground, to a wider seventh stone against the lowest plank step; the steps climb 1.7 m to the little hut's north door. The hut sits 3 m above the ground in its maple, half inside the
leaves. That is all you see from the trail.

Step through the hut onto its south porch and the hillside opens up: the ground drops away, and bridges run out to
the Map room and on to the Heart room below. The porch is the reveal: the layout clears the crowns on the lines of
sight from the porch to every other place, so the crow's nest shows past the Heart room's crown.

## Places

Heights are the deck's height and how far it stands above the ground under it. The deck is an octagon round its
tree; small huts (3.4 x 2.8 m) stand on one side of the trunk, in the direction no bridge uses.

| # | Place | Position | Deck | Above ground | What is there |
| --- | --- | --- | --- | --- | --- |
| 1 | Little hut | (-135, 198.5) | 77.0 | 3 m | the only part seen from the trail; a hut round the trunk, north door, south porch with a bench and banner |
| 2 | Map room | (-144, 185) | 75.8 | 6 m | desk under the window, bookshelves, maps, globe, kite; the first junction |
| 3 | Heart room | (-131, 168) | 74.2 | 11 m | the big octagonal room (8.6 m across) round the camphor trunk with the shimenawa rope, a loft shelf, a balcony all round |
| 4 | Kitchen | (-117, 175) | 74.8 | 10 m | clay stove and chimney pipe, log table and stools, drying persimmons |
| 5 | Sleeping nest | (-160, 172) | 74.8 | 9 m | futons with patchwork quilts, a hammock |
| 6 | Boat room | (-110, 161) | 73.8 | 13 m | an old rowboat hauled up the tree, upside down as a roof |
| 7 | Slide tree | (-122, 149) | 72.8 | 15 m | a spiral slide, 1.2 turns round the trunk, down to the forest floor: the back door |
| 8 | Pulley deck | (-150, 157) | 73.2 | 13 m | a crane arm with a basket on a rope to the ground |
| 9 | Chime tree | (-135, 145) | 72.4 | 16 m | a small ring landing hung with wind chimes, where three bridges meet |
| 10 | Lookout | (-148, 140) | 71.8 | 16 m | 91 steps spiral up the trunk to the crow's nest at 89 m (33 m above the ground): telescope, bell, flag, awning |

Every deck is between 71.8 and 77.0 m, so the whole house feels level while the hill falls away under it. From
the trail end it looks like a hut on the ground; at the far end you are four or five storeys up. The crow's nest
stands clear over the crowns so the view back takes in the whole house.

## How they connect

Twelve rope bridges, 1.15 m wide, with plank floors, rope handrails and a gentle sag (3% of the span). No bridge
drops more than 1.8 m, so every one can be walked without steps.

| From | To | Span | Drop | Height above ground (middle) |
| --- | --- | --- | --- | --- |
| Little hut | Map room | 9.5 m | 1.2 m | 4.5 m |
| Map room | Heart room | 12.9 m | 1.6 m | 7.9 m |
| Map room | Sleeping nest | 14.1 m | 1.0 m | 6.7 m |
| Heart room | Kitchen | 6.8 m | -0.6 m | 10.6 m |
| Kitchen | Boat room | 8.7 m | 1.0 m | 11.7 m |
| Boat room | Slide tree | 10.9 m | 1.0 m | 14.2 m |
| Slide tree | Chime tree | 8.3 m | 0.4 m | 15.1 m |
| Chime tree | Lookout | 8.0 m | 0.6 m | 15.8 m |
| Heart room | Pulley deck | 13.6 m | 1.0 m | 11.7 m |
| Sleeping nest | Pulley deck | 11.8 m | 1.6 m | 10.8 m |
| Pulley deck | Lookout | 11.0 m | 1.4 m | 14.1 m |
| Heart room | Chime tree | 15.7 m | 1.8 m | 13.6 m |

The route is a big loop with the Heart room in the middle:

- East side: Little hut, Map room, Heart room, Kitchen, Boat room, Slide tree, Chime tree, Lookout.
- West side back: Lookout, Pulley deck, Sleeping nest, Map room.
- Short cuts from the Heart room to the Pulley deck and the Chime tree.

Ways out: back through the little hut, or down the slide to the forest floor at the south-east end (then a walk
back up through the woods). The pulley basket and its rope reach the ground under the Pulley deck but are scenery.

## Trees

The ten anchor trees are new, thick bark trunks (0.45 to 1.15 m in radius) built with the house, with flared roots.
Their crowns are the game's own painted trees, placed larger and raised so the crown sits over the roof. The Heart
room's camphor is the only really big tree.

The houses stand 3 to 16 m up the slope, above the tops of the island's maples, so from a deck the eye first met
sky where the paintings have a wall of red and gold. `trees.py` makes four tall canopy trees (maple, crimson,
amber, ginkgo) the same way as the rest of the forest (card canopies, the same atlases and material slots, two
recoloured maple atlases), and `layout.py` places them round every place and bridge:

- each is scaled so its crown top stands about 1 m under to 3.5 m over the nearest deck, so from above the house
  sits just over a carpet of crowns and on the walks the crowns frame the rails;
- they keep 2.5 m of headroom over every deck and roof and take the spots of the short broadleaves (cedars and
  pines stay as the dark accents);
- a ring of extra autumn forest (50 m round the house) makes the woods dense enough to hide it from the trail.

Existing trees go only where they would pass through the build: a trunk through a floor, leaves through a bridge,
a roof or the slide, anything hugging an anchor trunk, and the crowns on the sight lines from the porch and from
the crow's nest to every bridge. Ground plants go along the stepping stones and under the slide's end.

## Look

- Surfaces: 26 Sunburst textures (`tools/treehouse_textures.py`), tileable surfaces (bark, planks, shingles,
  plaster, rope, canvas...) turned into neutral detail maps on the game's own palette, and one-off pictures
  (noren, maps, quilts, rugs, the flag) that keep their colours.
- Hero props: 13 Tripo models, each from its own Sunburst reference (`tools/treehouse_props.py`), reduced and
  given calibrated colour gains in Blender (`world/regions/treehouse/props.py`).
- Light: 69 warm lantern lights, sunbeams through every window (a soft shaft, the window's shape on the floor and a
  gentle glow in the opening) and a warmer colour grade inside the rooms. `build.py` writes them to
  `treehouse/runtime.json`, which the game merges into the world data at load.
- Camera: the rooms are small, so the camera stays back and what hides Cairo dithers away: walls, rails, props, and
  the near walls and roof of the room he is in. The noren part round him and swing back
  ([CAMERA.md](CAMERA.md)).

## Build

```sh
atelier build yorimichi unreal.treehouse
```

runs, in order: `world.treehouse_trees` (the canopy trees), `world.layout` (the world with the tree house
integrated), `world.treehouse_textures`, `world.treehouse_props`, `world.treehouse` (TH_Structure, TH_Trunks,
TH_Dressing, the props and runtime.json) and `unreal.treehouse` (`unreal/Scripts/import_treehouse.py`).
`data.stage` copies runtime.json into the game's data. The Sunburst and Tripo steps (`treehouse_textures.py paint`,
`treehouse_props.py`, `treehouse_concepts.py`, `treehouse_refs.py`) spend credits and are run by hand; their results are committed under
`assets/treehouse/`.

`python games/yorimichi/scenarios/treehouse.py LABEL` captures the 22 reference views in the game and writes each
beside its reference: the pairs the build was compared against, round after round.

## What the build checks

- The little hut reads as small and alone from the trail (the glimpse view).
- The porch reveal shows the Map room, the Heart room and, beyond, the crow's nest.
- The player can walk every bridge, climb every stair and slide down without getting stuck (the character steps 45
  cm and walks slopes up to about 44 degrees; there is no ladder climbing, so every way up is stairs).
- No existing tree or crown pokes through a floor, a wall or a roof.

## How it was made

1. **Layout** (this document, the two drawings).
2. **Blockout in the game**: plain decks, bridges, stairs, slide, hut boxes, trunks and crowns, captured from 22
   views.
3. **References per place**: Sunburst painted over each capture (`tools/treehouse_refs.py`). Every image got the
   capture, the master overview, the plan map, the concepts and the finished references of its neighbours, in
   four waves (the south aerial; then the east aerial, the porch reveal and the crow's nest looking back; then
   every approach; then every inside), so each place carries the same look from picture to picture.
4. **Item list** ([TREEHOUSE_ITEMS.md](TREEHOUSE_ITEMS.md)): every part of the house, and for each whether it is
   built by script or made in Tripo.
5. **Tripo references**: for the Tripo items only, exact Sunburst references (one object, clean background).
6. **Build**: the scripted items, from the references, then the textures, props and lights.
7. **Assemble and compare**: captures of every view beside its reference, and one change after another until the
   gaps closed.
