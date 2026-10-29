# Hakuba port

Brings Yorimichi's built world into Hakuba (`games/hakuba`) as plain props and data-only regions, so Hakuba never
reads or names anything outside its own folder.

```sh
uv run python games/yorimichi/hakuba_port/port.py --build build/yorimichi REGION...
uv run python games/yorimichi/hakuba_port/ground.py   # after porting a region's terrain
uv run python games/yorimichi/hakuba_port/plants.py --build build/yorimichi [--models | --brinecove]
uv run python games/yorimichi/hakuba_port/crater_park.py --build build/yorimichi
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
| `regions.py` | one adapter per region: which meshes to bring, how each material slot is coloured, where each stands |
| `ground.py`  | samples the ported terrain cells (far hills, Brinecove, Hidamari, Belmonte with its north country and apron, the southwest islet) into Hakuba's ground height and colour pages, then removes those cells' props and placements |
| `plants.py`  | ports the island's trees, bushes, grass and ground cover into Hakuba's `forest` region, each standing on the ground; `--models` first imports the tree models and Brinecove's plants Hakuba lacks, with their textures, each plant's far version made by the step that imports it (Brinecove's palms' from their fronds and trunk), already in its fixed cell of one atlas; `--brinecove` imports only Brinecove's plants, without Blender |
| `plant_convert.py` | the Blender script: writes one of a tree's FBX detail levels as a GLB, keeping each corner's wind weights; `plants.py` joins a tree's full, middle and far levels into one plant |
| `contact.py` | checks every exported copy of a ported placement against the ground the tiles draw: buried or adrift models fail, floating and sunk ones are counted |
| `crater_park.py` | ports Crater Park into Hakuba's `craterpark` region without Blender: each grid cell of the park's built meshes (`craterpark/v2/geometry.npz`) becomes one prop on the caldera floor, drawn with the park's own restyled textures and colours as its Yorimichi materials draw them, its riding surfaces and sides its collision; the park's ground is the volcano's terrain, already Hakuba's ground |
| `convert.py` | the Blender script: joins a mesh, keeps its UVs and each slot's texture, bakes each slot's colour per vertex, keeps `UCX_` or separate collision hulls, moves the origin to the footprint's centre and writes the GLB with `painted.py` |
| `painted.py` | writes the prop GLBs Hakuba's exporter accepts, without Blender: a `full` node coloured per vertex in linear RGB, or drawn with textured materials, and an optional `collision` node |

Props look as Yorimichi draws them: each image a slot's rule names becomes a Hakuba texture asset
(`<region>-<image>`, BC7-compressed), drawn on the mesh's own UVs, times a colour baked per vertex in linear RGB, the
product of the source's vertex colour, a flat colour and a gain, as that region's Yorimichi material combined them.
A prop with no textured slot is painted per vertex alone. Slots with no equivalent (water, cut-out leaves, additive
light) are dropped. Plants (trees, bushes, grass) are ported by `plants.py` as Hakuba's plant kind, which sways them in the
wind.
