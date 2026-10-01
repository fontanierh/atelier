# Super Ultra Mega Park

The original Skate 3 Super Ultra Mega Park sits in the island's western foothills, about a
kilometre north of the forest lake. It is also an editable, standalone Unreal level at
`/Game/MegaPark/Maps/SuperUltraMegaPark`, the parity reference for the placed park.
The wooden transitions, large gaps, bowls, coping, lower vert section and grandstands keep their
original scale and shape; in the island the whole park is turned and moved as one body.

Build with `atelier build yorimichi world.megapark unreal.megapark`, then open that level in the
editor or run `atelier play yorimichi --profile megapark`. A fresh checkout also needs the usual
player and board asset imports (`atelier build yorimichi` installs everything). The park's own
build does not require an extracted game, downloaded asset bundle, Python retail decoder or
external Rust map loader. It uses only the committed source below.
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

`verify_import.py` checks every built triangle against the source with the plants left out and
the letters swapped; every other render and collision triangle must still match exactly.

## What is bundled

`assets/megapark/map.json` is the source contract. Everything it references is committed:

| Source | Contents |
| --- | --- |
| `geometry/*.npz` | 50 complete source model resources, 955 mesh parts, 227,275 vertices and 213,482 triangles; original position words, faces, UVs, lightmap/decal UVs and decoded retail normal/tangent arrays |
| `collision/*.npz` | 29 collision resources, 147,660 original triangles; original surface/group IDs, edge codes, unit flags and sidedness |
| `textures/*.png` | 405 lossless RGBA textures at the original dimensions, including diffuse, alpha, normal, specular, baked lightmap, decal, detail and environment data |
| `map.json` rails | 151 complete grind paths with 1,507 untouched 120-byte big-endian cubic segment payloads, source IDs and flags |
| `provenance.json` | Original archive SHA-256, extraction tool revision, coordinate transform and independent source comparison results |

The source is `worldDIST_University.big`. Despite its name, `worldDIST_MegaPark.big` is a
different area. Selection keeps whole resources intersecting native X=200..500 and Z=-800..-500
metres. This includes all 32 University model resources using authored `_MP` material names
and whole surrounding rock, terrain, road and foliage resources. Resource bounds extend beyond
that selection rectangle. This is the full park with adjacent context, not the whole University
district. No ramp triangles were cut at the boundary or simplified.
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
render mesh. CPU access is retained for the skating backend's world queries. Original collision
attributes remain in the committed arrays; standard Chaos collision does not itself reproduce
EA's feature-edge and surface-ID solver behavior.

The level-owned `SuperUltraMegaPark` actor registers the original grind curves with the skating
subsystem. Curves are sampled with at most 2 mm control-point chord deviation and 50 cm segments;
the untouched original cubics are also serialized in the level. The subsystem treats these as rail
contact paths; their original flags are kept with them.

Materials retain original texture bindings and UVs, with the restyled images in place of the
originals. Shared Unreal graphs translate diffuse, decal, macro overlay,
normal/detail, specular and alpha into lit native materials, and the baked irradiance
(`4*L*L`) into ambient occlusion (see "Restyle"). Lightmaps use UV1, decals UV2; UVs are stored
at full precision. This is not a reproduction of EA's renderer: reflection cubemaps, animated
tree shaders and special shader effects remain source data. A texture is reimported when its
source image changes (its hash is kept in the asset's metadata).

`MegaParkGameMode` uses Cairo and the skating backend. `MegaParkWorld` supplies the
player's world services without generating the island, leaf storm, villagers or other island
effects. The level and asset paths are independent of the skating runtime implementation.

## Extraction and verification

The one-time extraction uses SK8-ENGINE/skate-3-rust-engine tools pinned to
`60efdef86600d8d8d4feb4b7c608fa0efd0643d7`. Prepare the University Pres/Sim/Tex streams with
`tools/vendor/university/tools/vanilla_map_extraction/tools/prepare_hawaiian_dream.py`, enabling
the raw texture cache, then run `world/regions/megapark/extract.py --cache <cache> --upstream <tools>`.
This is an optional provenance workflow; normal builds consume the committed native source.

Collision decoding: compressed deltas are unsigned 16-bit values, with saturating signed base
addition, integer-to-f32 rounding, then f32 multiplication. `extract.py` applies that
interpretation before converting collision. `verify_source.py` independently compares the
converted collision against the unmodified Rust retail reader, reading the untouched original RX2
sections: every vertex float word, surface/group ID, edge code and sidedness byte matches across
all 147,660 triangles. It also checks all 3,718,591 render-array elements and every decoded pixel
of all 405 textures, and confirms coverage of all 32 authored park model resources.

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
This is a map import check, not proof that the skating backend handles every original mega gap or
transition identically to Skate 3.
