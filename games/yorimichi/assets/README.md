# Yorimichi asset library

The model GLBs and park assets here are Atelier's own library and are committed
with the game. A fresh checkout includes the community megapark scene, all 18
Skate Pier obstacle modules, the motion reference, sword and paraglider, the
Hidamari, hippodrome and treehouse props, and the horses: six breeds with their
clips, seven tack sets each, five coat masks and 16 painted coat variants.

`source-library.json` records the local paths, sizes and SHA-256 hashes of all
source GLBs, texture images, geometry/collision arrays, character Blender files
and merged motion data. `tools/verify_asset_library.py` checks those sources
without existing build output. The library tests check the GLBs' embedded
geometry and images and confirm that a fresh checkout includes every park step.

- `skatepark/modules.json` records each module GLB's filename, size, SHA-256,
  dimensions and grind lines.
- `megapark/map.json` references Super Ultra Mega Park's committed geometry and
  collision arrays and textures. This park's native source format is NPZ and PNG.
- `characters/adventure/source/manifest.json` records the reference rig and
  equipment GLBs used by the merged move sets.
- `horses/manifest.json` declares the breeds, tack sets, clips, coat masks, hair
  colours, hair patterns and tints, and records every horse and tack GLB's size
  and SHA-256 ([HORSE.md](../docs/HORSE.md)).
- `horses/coats/variants/manifest.json` lists the coat variant PNGs with their
  SHA-256 and the provenance record (model and prompt) of each.
- Prop definitions use `asset.toml` or their region's model catalog.

The build reads these sources directly. GLBs exported during a build are derived
from committed models, Blender sources or mesh-building scripts and go under
`build/yorimichi/`. `atelier fetch yorimichi` obtains the sound masters.

For new local model sources, follow the [local asset pipeline](../docs/LOCAL_ASSET_PIPELINE.md):
TRELLIS.2/MLX generation, exterior reconstruction and reduction, checked UV baking,
optional masked repaint, scripted assembly and multi-view review. It includes the
tested Apple Silicon settings, weight-cache reuse and the source/provenance handoff.
It is a free local inference fallback below Tripo quality; new Sunburst references
are paid. The automatic head recipe needs adaptation and inspection for other shapes.

The four character Blender sources pack their meshes, textures, rigs and authored
animations. The merged set's 109 motion-reference clips and paraglider animation
are committed in `characters/adventure/source/`. The skating data is not part of this library: it
is shared by every game in the [Skate plugin](../../../platform/engine/Plugins/Activities/Skate/Data/README.md).
