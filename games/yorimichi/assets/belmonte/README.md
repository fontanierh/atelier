# Belmonte environmental library

The current town, estates and countryside courses from [HarasValley](https://github.com/Polozer/HarasValley),
pinned to `fec48785a36e666d092134f73cebb157f020d3cd` and extracted from `/Game/Maps/HarasValley`.
The project owner authorized this integration from their brother's project.

`source.json` records the current scene placements, model and texture checksums, native transforms,
resolved surface colours and planting data. Every consumed GLB is committed in `meshes/`.
The 127 `_Collision.glb` files contain the original hull geometry and are never rendered.

The library contains 288 render models and 18 colour textures. No Haras tree or vegetation model,
crowd, character, distant backdrop, level, plugin or gameplay script is consumed. Embedded foliage
faces are removed from the architectural models. Planting is rebuilt using the existing island flora.
Terrain consists of the 56 current static mesh tiles, rather than a copied landscape or stale authoring grid.

The acquisition tools are `tools/belmonte_extract.py` (read-only isolated reference editor) and
`tools/belmonte_convert.py` (guarded Blender). Normal builds never use the reference project:
`world.belmonte` reads this library and `unreal.belmonte` imports it into `/Game/Belmonte`.
