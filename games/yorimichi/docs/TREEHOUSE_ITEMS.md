# Tree house: item list

Step 4 of [TREEHOUSE_PLAN.md](TREEHOUSE_PLAN.md). Every part of the house, taken from the references in
`assets/treehouse/refs/`, and how each one is made.

- **Script**: built by `world/regions/treehouse/build.py` in Blender: vertex colours from the game's palette,
  multiplied in the tree house material by a Sunburst detail texture per surface (planks, bark, shingles, plaster,
  rope, cloth...) or carrying a Sunburst picture (noren, maps, quilts, rugs, the flag).
- **Tripo**: a Sunburst reference of the object alone, cut from the place reference that shows it; then a Tripo
  model (`tools/treehouse_props.py`), reduced in Blender to a low face count, its texture kept and its colours
  brought to the palette's brightness by a calibrated gain (`world/regions/treehouse/props.py`), placed as its own
  mesh wherever the rooms use it.

The rule: the script makes everything that must fit the layout to the centimetre (decks, bridges, stairs, rails,
slide), everything repeated many times (lanterns, floats, crates) and everything that is naturally simple shapes
(planks, rope, cloth, boxes, jars). Tripo makes only one-off hero pieces with round, hand-made forms that a script
would make look crude.

## 1. Structure (script, blocked out already, detail pass next)

Walkable, with collision. Counts come from `world/regions/treehouse/layout.py`.

| Item | Count | Detail pass, from the references |
|---|---|---|
| Decks | 10 | Plank strips with gaps, moss in the corners, dark joists and knee braces, a thick rim board |
| Rails | all deck edges | Square dark posts, two timber rails, rope lashings wound round each post top |
| Rope bridges | 12 | Plank floor, two thick rope handrails, thin rope or stick balusters, rope suspenders, a lantern post at each end |
| Entry way | 1 | 5 level stepping stones from the trail (a flight of stone steps up the bank, no rise over 17 cm; the last, wider one against the lowest step), 9 plank treads 1.4 m wide with stringers, rope handrails on short posts just outside the treads, one post lantern beside the first stone |
| Little hut | 1 | 4.8 x 6.1 m beside the maple: plank walls 3 m high on a timber frame, open to the rafters under a gable roof whose ridge runs north-south, 2.5 m doors in both gables with plank sliding doors parked open beside them and a lantern on a bracket over head height, a round window toward the maple, a six-pane window over the window seat |
| Small huts | 3 | Map room, Kitchen, Sleeping nest: the same kit as the little hut, gable roof, door on the bridge side, round window, six-pane window |
| Heart room | 1 | Eight walls with posts, three doors, round and six-pane windows, the big open round window, cone roof with rafters, balcony all round |
| Boat room | 1 | Upturned rowboat as a roof: faded blue hull with a pale stripe, ribs and planks showing underneath, on four posts |
| Slide | 1 | Pale wooden chute, one turn round the trunk, low side walls, posts to the ground, start gate on the deck, straw and leaf landing |
| Pulley crane | 1 | Timber arm and brace, pulley wheel, rope to the ground, basket (see 3) |
| Chime hoop | 1 | Wooden ring round the trunk on four arms, 12 fuurin (see 2) |
| Lookout | 1 | Four-legged timber tower with cross braces, 91 treads spiralling round the trunk, crow's nest ring deck, rail, awning posts |
| Roofs | 5 | Bark shingles in rows, moss patches, a few blue-grey tiles, ridge board, eave boards |
| Windows and doors | all | Round windows with a cross frame, six-pane windows, a soft glow in each pane, plank doors |
| Trunks | 10 | Thick bark trunks with a flared base and roots; crowns are the game's own trees |
| Canopy trees | about 130 | Tall maple, crimson, amber and ginkgo trees whose crowns stand at deck height (`world/regions/treehouse/trees.py`) |
| Shimenawa | 1 | Thick straw rope with paper shide, on the Heart room camphor only |

## 2. The kit, repeated everywhere (script)

These give the house one look. They are in nearly every reference.

| Item | About how many | Notes |
|---|---|---|
| Paper lanterns | 60 | Two shapes: round hanging ones (inside, on strings) and upright ones with wooden caps (rail posts, bridge ends). Glow colour |
| Glass floats in rope nets | 25 | Teal-green sphere, dark rope net lines, hanging from posts and eaves |
| Fuurin chimes | 20 | Clear glass bell, a paper tail; 12 on the chime hoop, the rest in windows and on the crow's nest |
| Noren | 8 | Split cloth in doorways: cream outside, indigo with a white maple leaf inside and at the little hut's north door |
| Crates | 30 | Plain crates, crate planters with flowers, a crate bench with an indigo cushion |
| Potted plants | 15 | Clay pots with a few leaf cards |
| Rope coils | 8 | On decks by the bridges |
| Buckets and barrels | 6 | Wooden staves and hoops, one with a ladle |
| Sail awnings | 3 | Cream triangles tied between posts (sleeping nest, pulley deck, crow's nest) |
| Flags and banners | 4 | Indigo with a white maple leaf (crow's nest flag, banners on the lookout and the little hut) |
| Quilts on rails | 4 | Patchwork squares, indigo, cream and red, over the Sleeping nest rail |
| Persimmon strings | 3 | Orange fruit on strings under the Kitchen eaves |
| Fallen maple leaves | many | A few flat red leaves on decks and bridges |

## 3. What is in each place

Script unless marked **Tripo**. Furniture that the player could walk into gets a simple box for collision;
small and hanging things get none.

| Place | Items |
|---|---|
| Little hut | A genkan, everything against the walls and a 3.5 m clear middle from door to door: a shoe cupboard of children's geta, zori, rain boots and sneakers with a lantern on top, a bench under a peg rail with a straw hat, a red scarf, **the backpack** and a rope coil; the island map over a treasure chest, a basket of rolled maps, crates and a rolled rug; a window seat with cushions, a shelf of jars of acorns and shells; an umbrella stand; a kite and the children's drawings high on the gables; a mat at the north door, a rug, a big lantern from the ridge. Porch: crate bench with cushions against the south wall, a post lantern and a planter in the far corner, a potted plant by the landing, the banner on the east wall, a woodpile on the west wall, a name board with a red maple leaf over the north door; nothing on the landing or the way to the bridge |
| Map room | Island map on the wall, desk made from a crate with a compass, magnifying glass, lamp and rolled charts, bookshelves, a small globe, a paper kite, **the backpack**, star cushion on a patchwork rug, toy sailboat, pinned drawings |
| Heart room | Stump table with **the brazier and kettle**, star cushions, patchwork rugs, a hammock from rope turns round the camphor to a wall peg, shelves of jars, shells and books, the island map, a kite, **the backpack**, a hanging bell, strings of round lanterns, a loft shelf with quilts high on the north side and a leaning ladder at its west end (for looks only: the player cannot climb) |
| Kitchen | **The clay stove with pot and kettle**, its iron chimney pipe, log stools round a log table, shelves of bowls, jars and baskets, a counter with a cutting board, a water barrel with a ladle, hanging herbs and persimmons, tea towels |
| Sleeping nest | Two futons with patchwork quilts and pillows, a hammock on wall pegs along the window wall with the futons in front of it, a shelf with a picture book, a framed picture and a toy boat, a hanging lantern |
| Boat room | Fishing net under the hull, two oars on the ribs, a lantern from the keel, crate benches with cushions, a rolled sail, a blue rug |
| Slide tree | Start gate, lanterns, straw landing heap at the bottom |
| Pulley deck | Woven basket on the rope, crates, rope coil |
| Chime tree | The chime hoop, two lanterns, a potted plant |
| Crow's nest | **The telescope**, a brass bell on a bracket, the flag, the sail awning, a crate, a lantern |

## 4. Tripo items

Thirteen models, 120 credits each. Each started from a Sunburst reference of the object alone, painted from the
place reference that shows it, so it matches the room it goes in.

| Item | Where | Why not script |
|---|---|---|
| Clay kamado stove with an iron pot, a kettle and logs | Kitchen | Rounded hand-made clay body, the room's centrepiece |
| Tree-stump table with a cast-iron teapot | Heart room | The hearth of the biggest room, round cast forms |
| Brass telescope on a wooden tripod | Crow's nest | Thin tripod and a detailed tube, the lookout's hero prop |
| Green canvas backpack | Little hut, Map room | Soft sewn shape |
| Brass ship's bell on a bracket | Crow's nest, Heart room | Cast bell and braided rope |
| Desk globe | Map room | Turned stand, brass ring, painted sphere |
| Woven basket on ropes | Pulley deck | Wicker weave |
| Water barrel with a ladle | Kitchen | Staves, hoops and a half-open lid |
| Futon with a patchwork quilt | Sleeping nest | Soft puffy quilt |
| Log table with teapot, persimmons and flowers | Kitchen | Bark sides and a laid table |
| Tall bookshelf full of books and jars | Map room, Heart room | Hundreds of small shapes |
| Plank-on-crates desk with map, compass and lamp | Map room | A cluttered hero piece |
| Crate planter with autumn flowers | Decks | Soft planting |

## 5. What not to follow in the references

- A shimenawa on every trunk: only the Heart room's camphor has one.
- A climbable loft: the Heart room ladder and loft are for looks only.
- A second tower in a few views, and rooms painted larger than the 3.4 x 2.8 m huts: the layout sizes stand.
  Hut furniture goes along the walls, keeping a clear path from the door to the window.
