# Yorimichi asset library

The model GLBs and park assets here are Atelier's own library and are committed
with the game. A fresh checkout includes the community megapark scene, all 18
Skate Pier obstacle modules, the motion reference, sword and paraglider, and the
Hidamari, hippodrome and treehouse props.

`source-library.json` records the local paths, sizes and SHA-256 hashes of all
source GLBs, texture images, geometry/collision arrays, character Blender files
and merged motion data. It also pins the skating bundle's manifest.
`tools/verify_asset_library.py` checks those sources and all 3,334 skating
payloads without existing build output. The library tests check the GLBs' embedded
geometry and images and confirm that a fresh checkout includes every park step.

- `communitypark/source.json` records the scene GLB's filename, size, SHA-256 and
  inventory. Its five texture maps are embedded in the GLB.
- `skatepark/modules.json` records each module GLB's filename, size, SHA-256,
  dimensions and grind lines.
- `megapark/map.json` references Super Ultra Mega Park's committed geometry and
  collision arrays and textures. This park's native source format is NPZ and PNG.
- `characters/adventure/source/manifest.json` records the reference rig and
  equipment GLBs used by the merged move sets.
- Prop definitions use `asset.toml` or their region's model catalog.

The build reads these sources directly. GLBs exported during a build are derived
from committed models, Blender sources or mesh-building scripts and go under
`build/yorimichi/`. `atelier fetch yorimichi` obtains the sound masters.

The four character Blender sources pack their meshes, textures, rigs and authored
animations. The merged set's 109 motion-reference clips and paraglider animation
are committed in `characters/adventure/source/`. The skating data is not part of this library: it
is shared by every game in the [Skate plugin](../../../platform/engine/Plugins/Activities/Skate/Data/README.md).
