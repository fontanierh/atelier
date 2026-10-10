# Super Ultra Mega Park

Super Ultra Mega Park, from Atelier's own asset library, sits in the island's western foothills, about a
kilometre north of the forest lake. It is also an editable, standalone Unreal level at
`/Game/MegaPark/Maps/SuperUltraMegaPark`, the parity reference for the placed park.
The wooden transitions, large gaps, bowls, coping, lower vert section and grandstands keep their
original scale and shape; in the island the whole park is turned and moved as one body.

Build with `atelier build yorimichi world.megapark unreal.megapark`, then open that level in the
editor or run `atelier play yorimichi --profile megapark`. A fresh checkout also needs the usual
player and board asset imports (`atelier build yorimichi` installs everything). The park's own
build reads the committed geometry, collision arrays and textures described below.
Use `--profile megapark-fullscreen` for a fullscreen controller playtest.

## Placement

`world/regions/megapark/placement.py` is the single source for where the park is: the terrain, the
forest, the park build and the review tool all read it. It is pure NumPy.

- The island keeps the park itself: the 32 models with authored `_MP` materials, and the 20
  collision sections that lie within the bounds of those models in their own stream tile (117,143
  triangles). The campus, roads and outer hills around it are left out. All 151 grind paths are
  kept; five road rails that ran on into the left-out campus end at the park's edge.
- The park turns 60 degrees clockwise about its centre, which lands at Blender (-150, 1300); its
  lowest collision point is at 49.3 m. The riding collision and grind paths are the original
  triangles and curves under that one rigid transform, so the ramps ride as they did.
- The spot was chosen by sight lines from every map place. With the terrain reshaped around it,
  the park is hidden from the city, the hamlet, the beaches, the pier and the lake; from the island
  temple, 1.75 km away, about 5% of it shows against the volcano's lower western flank. Its open,
  low side faces west across a forested valley to the 200 m western ridge; the volcano rises behind
  its high rims. It reads as a rocky canyon in the forest from the air, the volcano's flank and the
  western hills.
- The foothills meet the park: under it the terrain stays a metre below the park's lowest surface
  within 20 m; around it the natural relief is offset to the park's edge height and eases back
  over a skirt that widens with the height it makes up (35 to 220 m). Trees are cleared from the
  footprint (`hidamari/layout.py`).
- The forest round it is the detailed kind the skater gets close to (`megapark/forest.py`), and
  closed like the Sunburst paintovers of the park (`assets/megapark/concepts/improve-*`): the north
  forest's low-poly crowns become the island's leaf-card maples, ginkgos, pines and cedars within
  220 m of the footprint, which takes in the hills the park is seen from, fewer and fewer out to
  320 m. New detailed trees fill that band to a touching canopy in clumps of one family (dark
  conifers above red maples and yellow ginkgos), with a few glades, and bushes and grass grow
  between the trunks at the park's edge. Beyond it the island's opaque crowns close the canopy out
  to 1250 m, over the north forest's thinned slopes and the steep face west of the park and the
  plateau on top of it, the park's skyline, up to the forest line. The crowns grow in the same
  clumps (pine, rust, gold), a little warmer than the fill, and the north forest's own crowns there
  take them too, so the hills read as patches of one colour. The pines grow closer together and
  stand above the broadleaf crowns. Where the crowns grow west of the north forest,
  `clear_far_forest` (called last by `gen_world.py`) removes the far forest's painted cards, which
  would stand over the plateau's canopy as a pale skyline. The ground under the canopy is dark forest floor, fading into the island's own ground by 650 m
  (`hidamari/mountains.py`). `city.json` lists the area as `near_trees`, so `AJapanWorld` gives the
  detailed trees shadows, collision and the camera fade instead of treating them as distant backdrop.
- `world.megapark` writes `megapark/park.json`, staged into `Content/Data`: the actor transform,
  the kept meshes at their native origins, the grind paths and the upper deck start.
  `ASuperUltraMegaPark::Spawn` (called by `AJapanWorld`) builds the park from it, using the meshes
  `unreal.megapark` imports.

`python games/yorimichi/tools/review_megapark.py --island` checks the placed park in the island
the same way as the standalone review below, then captures it in the game's own look: from the air,
from its deck, from the hills around it, and at eye height from the lake, the woodland air station,
the mini-mega ramp, the temple, the foothills and the plaza (whose volcano view it must not touch).

`python games/yorimichi/scenarios/megapark_tour.py plan` prints the camera path of the park's
presentation film and its clearance from the park, the ground and the tree crowns;
`film <label>` shoots it in a guarded game (`--preview` for a quick 960x540 pass) and `cut <label>`
makes `build/yorimichi/megapark/tour/<label>.mp4`: over the west hills, through the canopy, down
the roll-in behind a rider's line, the canyon, the snake bowl, the bowls, the 寄り道 letters and an aerial
pull-back toward the volcano.

## Getting there

- **On foot.** A secluded forest trail (`world/regions/megapark/trail.py`) leaves the woodland air
  station's footpath beside its pad and climbs through the woodland and a switchback over the far
  hills' shoulder. It drops down their north side into the valley west of the park and follows the
  valley to the park's low west deck, about 1.2 km in all. Eight timber steps climb from its end
  onto the deck. The path is a 2.4 m earth bed at walking grades (at most about 25% over 10 m): the
  ground along it smoothed, then carved into the square's 2 m ground, the 2 m approach band north
  of the square, and the foothills' 10 m grid. In the foothills the bed follows the ground as that
  grid will have it, so it meets the park's stamp at the deck edge. The trees and plants on the
  path are cleared and the woods close in beside it. The world map draws it.
- **By air.** The zeppelin's third stop, the Mega Park air station
  ([zeppelin](../world/regions/zeppelin/README.md#the-mega-park-stop)), stands on a levelled pad
  beside the park's top road, at about 130 m. A footpath and a short footbridge lead from it onto
  the road deck. The line runs Woodland, Hidamari, Mega Park. At any station, before boarding, the
  passenger can pick another stop with the flight speed buttons.

`scenarios/megapark_access_film.py` films the way in, inside a running game: Cairo boards at
Hidamari, the ship flies to the Mega Park stop at 2x, he runs down the station stairs and over the
footbridge, then skates the park road (Kickflip, 360 Flip, Powerslide), drops off the upper deck
into a BS Grab about 11 m over the pool's north-west quarter, and takes that quarter again with a
Kickflip. `scenarios/megapark_access_film_mix.py` builds its soundtrack (game sounds, a synthesized
airship drone and wind, the ambience) and the 1080p MP4. Both docstrings give the commands.

## Seam

Where the park meets the air station's footbridge, the gate's rock ends in a drop that the
source's surrounding hills cover. The island keeps that piece of those hills (`placement.SEAM`):
the earth hillside between the rock and the source's road and the concrete wall that holds it
above the road (three render parts of one source model), and the 333 collision triangles of their
section that lie on them (`seam_mask`, within 25 cm of the render surface). The park's frame and
transform leave the seam out, so the seam does not move the park.

- **Skirt.** Wherever the hillside stops in the air, a skirt of its own earth or concrete hangs
  45 m under the edge and faces outward, so the edges show no void from outside
  (`placement.seam_skirt`, 33 edges). Edges shared with the park or the rest of the seam, and
  walls' tops, get none. The skirt is in the seam's render and collision meshes. It shades as one
  face with the face above it: shared corner normals, its texture and decal running on down, and
  that face's lightmap. The seam's materials are matte copies of the hillside's (`_Seam` slots), so
  its earth and concrete take none of the sky's blue sheen at grazing angles.
- **Terrain.** North of y 1440 the island's ground is the gate patch (below). Further south the
  terrain stamp counts the seam as part of the footprint: under it the ground stays below its
  lowest surface within one terrain cell, so the hillside meets the island ground along its edges.
  The eased skirt round the park still starts from the park's own rim, so the seam does not move
  the ground past it.
- **Plants.** `plants.seam()` plants the hillside by the ledge rules (forest on the earth, shrubs at
  the wall's foot) and lays rocks of the park's grey-violet stone (`HD_NorthRock*`) where the earth
  meets the concrete. South of the gate patch, where the hillside meets the forest floor,
  `forest.py` grows a denser undergrowth of ochre bushes, red shrub maples, grass, leaves and a few
  rocks, as in the Sunburst concept `assets/megapark/concepts/seam-gate`; only that undergrowth
  comes closer to the park than the 4 m `hidamari/layout.py` clears.
- **The rest of the rim.** Elsewhere the park's own banks and hillsides end at its rim, and the
  ground outside meets them lower than their tops. The park's rock, stone, earth and grass
  materials are drawn from both sides (`import_megapark.py`, `NATURAL`), so from the forest those
  banks read as hill rather than as a window into the park.

The park build writes the seam as `SM_MP_Seam` and `UC_MP_Seam` with the island's meshes in
`park.json`; `import_megapark.py` imports them, but the standalone level stays the parity reference
without them.

## Gate

Between the air station and the park (`GATE`, x -260 to -60 and y 1440 to 1600), the island's ground
is a 1 m patch of its own (`world/regions/megapark/gate.py`) instead of the north foothills' 10 m
facets, which round the park sink under its lowest surface and left a pit under the footbridge, a
trench along the hillside and park edges standing over the air. It follows the Sunburst concept
`assets/megapark/concepts/gate-ground`: the island's meadow and forest floor running up to the park.

- **Shape.** `gate.grid` classes every node by the park's and the seam's triangles above it and
  solves the ground between what it must meet. It rises to every open park edge from below and
  sits 8 cm under it, at the edge's own height where it is reached; within 2.5 m of an edge it
  follows the cover's underside 15 cm down, so no edge stands over a gap from any angle. It buries
  the seam's skirt where that hangs less than 10 m, 22 cm under its edge so the rock shows as a low
  ledge rather than a line on the grass, and any wall seen from behind; deeper skirts
  (the gate's west cliff) and the park's own walls keep their faces, the ground meeting them
  between foot and top. The station's pad and footpath stay level, a grassy dell (`DELL`) dips
  under the footbridge, and 20 m from the park the foothills' relief returns, eased into their own
  surface on the patch's border.
- **Look.** `gate.paint` gives each node a colour and how much of the island's ground texture it
  shows: meadow round the station, along the footpath and in a verge along the park's edges, the
  foothills' forest floor further out, the earth footpath soft-edged to the footbridge, bare darker
  earth at the foot of walls and rock faces. `HD_NorthGate` draws it with `M_NorthGate`
  (`unreal/Scripts/mountain_material.py`): the vertex colour times `T_ground` over its mean, by
  the vertex alpha, under the island's haze. `T_ground` does not tile, so the material samples it
  without tile edges (four taps half a tile apart, each weighted away from its own edges) at 6 m
  and again turned at 16 m. `gate.dress` replaces the undergrowth on the patch with grass (thick
  on the meadow and along every edge), fallen leaves, bushes where the meadow meets the forest, and
  along the park's edges clumps of bushes, grass and boulders of the park's stone a metre or two
  out, sized to keep off the road (low and few between the footbridge and the hillside, nothing at
  the footbridge's ends). Boulders also stand at the foot of real walls, a third sunk.
- **Footbridge.** It crosses the dell from a timber sleeper on the path to a stone sill against the
  road deck's slanted west edge (`zeppelin.layout.DECK_EDGE`), so the planks meet the deck flush.

## Restyle

In the island the park keeps every ridden surface, rail and collision triangle, and wears the
island's look instead of the original desert campus. Concepts painted with Sunburst are in
`assets/megapark/concepts/` (`tools/megapark_concepts.py`).

- **Plants.** The desert trees, cacti and shrubs are camera-facing cards (11 textures). The park
  build leaves those render parts out, and `world/regions/megapark/plants.py` turns each original
  plant (card groups joined by kind) into one of the island's own detailed trees or bushes at its
  foot: pines, cedars and broadleaves on the rock rims, painted maples and ginkgos in the groves
  and canyons, big conifers and broadleaves for any 12 m or taller, ochre bushes and small red
  maples for the shrubs, sized to the original. The park's own rock, earth and grass are planted
  too, as in the paintovers: shrubs and red shrub-sized maples on the ledges and at the foot of the
  walls, small trees on the rims, forest on the earth hillsides and the grass. The rock is ridden, so those plants keep 6 m (trees) or 1.4 m (shrubs) from
  any built surface, 5 m from the roll-in below the deck start and 2 m from every grind path; the
  original cacti and shrubs on the roll-in itself are left out. None
  are the far forest's painted-card `_lo` trees. `ASuperUltraMegaPark::Spawn` plants them as
  instanced meshes with the island's see-through fade and no collision, so the skate world
  snapshot never sees them.
- **Textures.** `tools/megapark_textures.py paint` repaints the five big natural surfaces (rock,
  smooth rock, cut stone, earth, grass) as Sunburst edits of the originals in the concept's style,
  so they keep their layout on the park's UVs, and paints the two billboard skate graphics (a
  samurai over the canyon, an oni on the snake bowl's boards), a wave cloth and a maple and waves
  crest for the signs (`assets/megapark/restyle/`, prompts in each provenance file).
  `finish` (the `world.megapark_restyle` step) makes the surfaces seamless at a dark grey-violet
  rock and olive grass, regrades the rock decals and the macro overlay to match, recolours the
  teal and sky-blue paint, banners and decals to indigo, ochre and moss exactly (layout and alpha
  untouched), fits the paintings to the original billboards, shark logos and lettering, and writes
  `build/yorimichi/megapark/textures/`. Concrete, wood and metal stay as they were.
- **Moss.** The rock and cut stone materials grow moss where they face up, in patches broken by
  two world-space noises, as on the paintovers' ledges; the walls stay bare
  (`import_megapark.py`, `MOSSY`).
- **Light.** The park material is lit by the island's sun, sky and Lumen like the terrain around
  it, matte with a little of the original specular. The baked irradiance stays only as ambient
  occlusion: each material divides it by its lightmap page's sunlit level (the 95th percentile,
  at least 1) and applies it at `LightmapOcclusion` strength, so corners stay grounded without
  the original desert sun's shadows.
- **寄り道.** The SHARKS letters on the hill above the bowls become 寄り道 in the same concrete,
  plane, height and support trusses (`world/regions/megapark/sign.py`). The park build extrudes
  them from a Black instance of the island's Noto Sans JP and swaps their collision: the original
  letters' 2,172 triangles leave their section and the 寄り道 letters' 2,008 take their place.
  No rail ran on the letters.
- **Cars.** The car park's four photo-textured traffic cars (two sedans, an SUV and a sports car)
  leave the park build (`world/regions/megapark/cars.py`), and so do their 762 collision
  triangles; the bays' ground stays. Four kei cars, from the Sunburst sheet
  `assets/megapark/concepts/kei-sheet` and the car park painting `kei-carpark`, take their bays:
  a sage pickup with a crate and a board in its bed, an ochre and cream wagon, a vermilion retro
  car with a cream roof, and an indigo microvan with two boards on its roof rack. They are built
  in Blender with flat vertex colours, like the village props (`assets/vehicles/kei/build.py`,
  the `world.kei` and `unreal.kei` steps). `cars.py` stands each on a plane fitted to its bay's
  ground. `park.json` lists them as props, and `ASuperUltraMegaPark::Spawn` places them with
  their box collision, so Cairo walks round them and the board stops against them.

`verify_import.py` checks every built triangle against the source with the plants and cars left
out, the letters swapped and the seam added (its parts, its collision triangles and the skirt);
every other render and collision triangle must still match exactly.

## What is bundled

`assets/megapark/map.json` is the source contract. Everything it references is committed:

| Source | Contents |
| --- | --- |
| `geometry/*.npz` | 50 complete source model resources, 955 mesh parts, 227,275 vertices and 213,482 triangles; original position words, faces, UVs, lightmap/decal UVs and decoded normal/tangent arrays |
| `collision/*.npz` | 29 collision resources, 147,660 original triangles; original surface/group IDs, edge codes, unit flags and sidedness |
| `textures/*.png` | 405 lossless RGBA textures at the original dimensions, including diffuse, alpha, normal, specular, baked lightmap, decal, detail and environment data |
| `map.json` rails | 151 complete grind paths with 1,507 untouched 120-byte big-endian cubic segment payloads, source IDs and flags |
| `provenance.json` | Library ownership, source manifest SHA-256, coordinate transform and source comparison results |

The library stores complete park resources, including all 32 models using authored
`_MP` material names and their adjacent rock, terrain, road and foliage resources.
Selection keeps whole resources intersecting native X=200..500 and Z=-800..-500
metres; resource bounds extend beyond that rectangle. Ramp triangles remain
complete and unsimplified.
The native draw meshes omit 42 proven zero-area render faces that Unreal cannot import;
their original words remain in the source arrays. All 147,660 collision faces survive.

## Native Unreal output

`world/regions/megapark/build.py` generates FBX interchange files in `build/yorimichi/megapark`.
`unreal/Scripts/import_megapark.py` creates meshes, textures, material instances and the saved
`.umap` under the normal generated `unreal/Content/MegaPark` folder. Geometry is grouped by
original resource, with descriptive actor folders and stable source IDs. Each chunk has a local
origin for convenient selection and editing; placement reconstructs its original world position.

Native Y-up metres become Unreal centimetres with `(x,y,z) -> (100*x,100*z,100*y)`. Render
geometry has no gameplay collision. Hidden collision actors use the original collision triangles
with Chaos complex-as-simple collision, rather than convex approximations or the decorative
render mesh. CPU access is retained for the skating simulation's world queries. Original collision
attributes remain in the committed arrays; standard Chaos collision does not itself reproduce
the skating simulation's feature-edge and surface-ID solver behavior.

The level saves the park's layout in an `AMegaParkLayout` actor: the grind curves, the source hash and the
upper deck start (`FMegaParkLayoutData`, in the `YorimichiAssets` module, which holds no gameplay). When play starts,
the level's game mode spawns a `SuperUltraMegaPark` from it, the actor the island uses, which registers the curves with
the skating subsystem. Curves are sampled with at most 2 mm control-point chord deviation and 50 cm segments;
the untouched original cubics are also serialized in the level. The subsystem treats these as rail
contact paths; their original flags are kept with them.

Materials retain original texture bindings and UVs, with the restyled images in place of the
originals. Shared Unreal graphs translate diffuse, decal, macro overlay,
normal/detail, specular and alpha into lit native materials, and the baked irradiance
(`4*L*L`) into ambient occlusion (see "Restyle"). Lightmaps use UV1, decals UV2; UVs are stored
at full precision. Reflection cubemaps, animated tree shaders and special shader effects remain source data.
A texture is reimported when its source image changes (its hash is kept in the asset's metadata).

`MegaParkGameMode`, chosen by the level's name (`GameModeMapPrefixes` in `Config/DefaultEngine.ini`; a `?game=`
option still wins), uses Cairo and the skating simulation. It spawns a `MegaParkWorld`, which supplies the player's
world services without generating the island, leaf storm, villagers or other island effects. A level imported before
the layout existed has none, and play logs an error asking for `atelier build yorimichi`. The level and asset paths are independent of the skating runtime implementation.

## Source verification

`assets/megapark/provenance.json` records the library identity, coordinate
transform, manifest checksum and completed source comparisons. The checks cover
all 147,660 collision triangles, 3,718,591 render-array elements, pixels of all
405 textures and all 32 authored park models. Normal builds consume this
committed source directly.

The optional `world/regions/megapark/extract.py` and `verify_source.py` tools
convert and compare a library map cache when maintaining its native format.
Collision decoding uses unsigned 16-bit deltas, saturating signed base addition,
integer-to-f32 rounding and f32 multiplication; verification compares every vertex
float word, surface/group ID, edge code and sidedness byte.

The Unreal importer fails if source/export hashes disagree, any material slot is unresolved,
any imported mesh loses triangles, or any world bounds drift by 0.05 cm or more. Its import
report and captures go to `build/yorimichi/megapark`, outside source control.
`world/regions/megapark/verify_import.py` additionally compares every built Unreal LOD triangle
against the source, accepting at most 0.05 cm float-conversion error and requiring identical
triangle connectivity despite FBX section reordering.

The import compares 361,100 built triangles, with a maximum vertex error of 0.00177 cm, and
every render mesh keeps its three UV channels. The runtime review is
`python games/yorimichi/tools/review_megapark.py`: it launches its own game under the render
guard, checks original ground heights at 11 deck/transition/bowl sites, records a push session on
the upper deck, captures the park, and quits that game. It matches all 11 heights within
0.0013 cm, registers 151 grind paths, and rides 48.5 metres on the original deck without bailing.
These results validate the map import. The skating simulation's mega-gap and transition behavior
has separate runtime checks.
