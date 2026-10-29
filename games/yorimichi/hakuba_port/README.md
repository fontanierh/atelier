# Hakuba port

Brings Yorimichi's built world into Hakuba (`games/hakuba`) as plain props and data-only regions, so Hakuba never
reads or names anything outside its own folder.

```sh
uv run python games/yorimichi/hakuba_port/port.py --build build/yorimichi REGION...
uv run python games/yorimichi/hakuba_port/ground.py   # after porting a region's terrain
uv run python games/yorimichi/hakuba_port/plants.py --build build/yorimichi [--models | --brinecove]
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
| `port.py`    | the command: runs an adapter, converts its meshes, writes the props and the placements          |
| `regions.py` | one adapter per region: which meshes to bring, how each material slot is coloured, where each stands |
| `ground.py`  | samples the ported terrain cells (far hills, Brinecove, Hidamari, Belmonte, the southwest islet) into Hakuba's ground height and colour pages, then removes those cells' props and placements |
| `plants.py`  | ports the island's trees, bushes, grass and ground cover into Hakuba's `forest` region, each standing on the ground; `--models` first imports the tree models and Brinecove's plants Hakuba lacks, with their textures, each plant's far version made by the step that imports it (Brinecove's palms' from their fronds and trunk), already in its fixed cell of one atlas; `--brinecove` imports only Brinecove's plants, without Blender |
| `plant_convert.py` | the Blender script: writes one of a tree's FBX detail levels as a GLB, keeping each corner's wind weights; `plants.py` joins a tree's full, middle and far levels into one plant |
| `contact.py` | checks every exported copy of a ported placement against the ground the tiles draw: buried or adrift models fail, floating and sunk ones are counted |
| `convert.py` | the Blender script: joins a mesh, bakes each slot's colour per vertex, keeps `UCX_` or separate collision hulls, moves the origin to the footprint's centre and writes the GLB Hakuba's exporter accepts |

Colours are baked per vertex in linear RGB, the way Hakuba's painted props draw: a slot's colour is the product of
the source's vertex colour, a texture's mean or its texel at each corner, a flat colour and a gain, as that region's
Yorimichi material combined them. Slots with no painted equivalent (water, cut-out leaves, additive light) are
dropped. Plants (trees, bushes, grass) are ported by `plants.py` as Hakuba's plant kind, which sways them in the
wind.
