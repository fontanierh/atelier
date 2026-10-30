# Hakuba port

Brings Yorimichi's built world into Hakuba (`games/hakuba`) as plain props and data-only regions, so Hakuba never
reads or names anything outside its own folder.

```sh
uv run python games/yorimichi/hakuba_port/port.py --build build/yorimichi REGION...
uv run python games/yorimichi/hakuba_port/ground.py   # after porting a region's terrain
uv run python games/yorimichi/hakuba_port/crater_park.py --build build/yorimichi
uv run python games/yorimichi/hakuba_port/transport.py --build build/yorimichi railway
uv run python -m atelier.safety.guarded --report build/yorimichi/gondola/fit-guard --timeout 3600 --small 4 \
  --purpose 'hakuba port: fit the gondola' -- blender -b --threads 3 -P games/yorimichi/hakuba_port/gondola_fit.py \
  -- build/yorimichi/gondola build/yorimichi/gondola/hakuba   # under the machine's guard, as port.py runs Blender
uv run python games/yorimichi/hakuba_port/port.py --build build/yorimichi gondola ferry
uv run python games/yorimichi/hakuba_port/plants.py --build build/yorimichi [--models | --brinecove | --caldera]
(cd games/hakuba && cargo export assets)
uv run python games/yorimichi/hakuba_port/contact.py --leave-out   # drops the forest's buried plants
(cd games/hakuba && cargo export assets)
uv run python games/yorimichi/hakuba_port/contact.py
```

A region's terrain cells become Hakuba's shared ground, not props: `ground.py` samples them into the height and
colour pages and removes them. The far hills are only terrain, so `far-hills` is not listed as a Hakuba region.

`--build` is a Yorimichi build folder holding the world steps' products (`exports/`, `atomic_regions/`, each
region's runtime data and textures). The port converts every mesh of the named regions in one Blender run under
the machine's guard, writes each as `games/hakuba/assets/props/<region>-<piece>/` (`src/model.glb` and
`asset.toml`) and writes `games/hakuba/assets/world/src/regions/<region>/placements.json`. A region must also be
listed once in Hakuba's `tools/export/src/world/regions.rs`.

| File         | What it holds                                                                                   |
|--------------|-------------------------------------------------------------------------------------------------|
| `port.py`    | the command: runs an adapter, converts its meshes, writes the props, their texture assets and the placements |
| `regions.py` | one adapter per region: which meshes to bring, how each material slot is coloured, where each stands; the `ferry` adapter reads the ship and both terminals, so `assets/vehicles/ferry/build.py` and `assets/vehicles/ferry/terminals/build.py` must be built first, and `kei` reads the cars `assets/vehicles/kei/build.py` writes to `kei/assets` |
| `ground.py`  | samples the ported terrain cells (far hills, Brinecove, Hidamari, Belmonte with its north country and apron, the southwest islet) into Hakuba's ground height and colour pages, then removes those cells' props and placements |
| `plants.py`  | ports the island's trees, bushes, grass and ground cover into Hakuba's `forest` region, each standing on the ground; `--models` first imports the tree models and Brinecove's plants Hakuba lacks, with their textures, each plant's far version made by the step that imports it (Brinecove's palms' from their fronds and trunk), already in its fixed cell of one atlas (the caldera's four conifers share one cell, a quarter each); `--brinecove` imports only Brinecove's plants, without Blender; `--caldera` imports only the caldera's conifers round Crater Park, from the prop export's fitted detail levels, each drawing its Tripo model's own texture at the gain the source draws it with |
| `plant_convert.py` | the Blender script: writes one of a tree's FBX detail levels as a GLB, keeping each corner's wind weights; `plants.py` joins a tree's full, middle and far levels into one plant |
| `transport.py` | ports the transport as standing scenery, nothing moving or ridden, without Blender: `railway` brings the Belmonte railway's track, structures and station from `world/train/track.py` on the committed line, its Belmonte materials drawn with Belmonte's textures, and its two trains, one at each terminus, from the coach shells `world/train/build.py` wrote, drawn with their own textures |
| `gondola_fit.py` | the Blender script: fits the three gondola lines to Hakuba's ground with `regions/gondola/site.py`'s own functions (stations on timber posts and their stairs, towers, haul ropes simplified within the jaw's contact allowance in stretches of about 60 m and audited as read back from their FBX, and each line's cabins where the service clock has them at the moment, of eight across a headway, with the most cabins out on the rope, hanging plumb, each grip a mesh of its own), keeps its closure, seating, ground, riding, jump and rope-contact gates, and writes the pieces and `gondola.json` for the `gondola` adapter; the gondola kit (`assets/vehicles/gondola/build.py`) must be built first |
| `contact.py` | checks every exported copy of a ported placement against the ground the tiles draw: buried or adrift models fail, floating and sunk ones are counted |
| `crater_park.py` | ports Crater Park into Hakuba's `craterpark` region without Blender: each grid cell of the park's built meshes (`craterpark/v2/geometry.npz`) becomes one prop on the caldera floor, drawn with the park's own restyled textures and colours as its Yorimichi materials draw them, its riding surfaces and sides its collision; the park's ground is the volcano's terrain, already Hakuba's ground |
| `convert.py` | the Blender script: joins a mesh, turns it first by its job's `turn` if any (a model placed once at a tilt), keeps its UVs and each slot's texture, bakes each slot's colour per vertex, keeps `UCX_` or separate collision hulls, moves the origin to the footprint's centre and writes the GLB with `painted.py` |
| `painted.py` | writes the prop GLBs Hakuba's exporter accepts, without Blender: a `full` node coloured per vertex in linear RGB, or drawn with textured materials, and an optional `collision` node; `prop` writes one with its origin at its footprint's centre, `read` returns a GLB's triangles, UVs, materials and images (the train's coach shells), and `rename_images` repoints a prop's images at its own textures |

Props look as Yorimichi draws them: each image a slot's rule names becomes a Hakuba texture asset
(`<region>-<image>`, BC7-compressed; one only a single prop shows moves into that prop as its own texture), drawn on
the mesh's own UVs over the rule's `tile`, times a colour baked per vertex in linear RGB, the product of the source's
vertex colour, a flat colour and a gain, as that region's Yorimichi material combined them. Belmonte's materials draw
their texture over their tile in metres, and a neutral detail texture twice over. A prop with no textured slot is
painted per vertex alone. Hakuba draws every surface matte, so an untextured paint's sheen is folded into its colour
(the trains' black engine). A material whose look layers images on other UVs or at another scale keeps only the image
on the mesh's first UVs and folds the others in by their mean: the Mega Park's decals (third UVs) and macro overlays
(first UVs at 0.3 or 0.7 times), with its baked lightmap occlusion left out. Slots with no equivalent (water, cut-out
leaves, additive light) are dropped. Plants (trees, bushes, grass) are ported by `plants.py` as Hakuba's plant kind,
which sways them in the wind.

`plants.py` stands each plant on Hakuba's ground, except a Belmonte or Brinecove plant its source stands more than
2 m above it: that one keeps its source height only where a ported prop's surface, as the last export's tiles draw it,
is within 0.5 m of it (a planter, a terrace, a roof garden). Over no prop it would float, so it stands on the ground
like the island's plants. Run it after an export that holds the ported props.

`contact.py`'s floating and sunk counts are for review; most are as built. A prop is checked against the ground
alone, so one standing on another prop floats in the count: the hippodrome stand's café chairs and tables, the
bridge's lantern posts, the tree house's furniture, the north gate's rocks and air station, the plaza trees on the
plaza floor, the lighthouse on its breakwater. Some hang or float by design: the street wires, the wall lanterns,
the tree house's bell, the harbour boats over the sea floor. The sunk ones are foundations and set stones as built:
the north country's terrain skirts tucked under Belmonte's ground, Brinecove's sea cliffs and town footings on its
slope, the south-west boulders set into the sea bed. Each keeps its Yorimichi position exactly (the converter's
origin shift is undone in the placement), so none needs moving.
