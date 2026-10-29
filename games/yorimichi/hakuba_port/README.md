# Hakuba port

Brings Yorimichi's built world into Hakuba (`games/hakuba`) as plain props and data-only regions, so Hakuba never
reads or names anything outside its own folder.

```sh
uv run python games/yorimichi/hakuba_port/port.py --build build/yorimichi REGION...
cd games/hakuba && cargo export assets
```

`--build` is a Yorimichi build folder holding the world steps' products (`exports/`, `atomic_regions/`, each
region's runtime data and textures). The port converts every mesh of the named regions in one Blender run under
the machine's guard, writes each as `games/hakuba/assets/props/<region>-<piece>/` (`src/model.glb` and
`asset.toml`) and writes `games/hakuba/assets/world/src/regions/<region>/placements.json`. A region must also be
listed once in Hakuba's `tools/export/src/world/regions.rs`.

| File         | What it holds                                                                                   |
|--------------|-------------------------------------------------------------------------------------------------|
| `port.py`    | the command: runs an adapter, converts its meshes, writes the props and the placements          |
| `regions.py` | one adapter per region: which meshes to bring, how each material slot is coloured, where each stands |
| `convert.py` | the Blender script: joins a mesh, bakes each slot's colour per vertex, keeps `UCX_` or separate collision hulls, moves the origin to the footprint's centre and writes the GLB Hakuba's exporter accepts |

Colours are baked per vertex in linear RGB, the way Hakuba's painted props draw: a slot's colour is the product of
the source's vertex colour, a texture's mean or its texel at each corner, a flat colour and a gain, as that region's
Yorimichi material combined them. Slots with no painted equivalent (water, cut-out leaves, additive light) are
dropped. Plants (trees, bushes, grass) are not ported here; they need Hakuba's plant kind.
