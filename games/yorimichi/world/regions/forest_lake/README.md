# Hidden woodland lake

A secluded 68 × 46 m inland lake at Blender world (-90, 235), west of the mini-mega. A winding dirt trail connects the ramp clearing to the fisher cabin. Existing autumn trees enclose the clearing; no new tree asset family is added.

The cabin includes a tiled roof, shoji windows, roof dormer, tiled covered porch with timber braces, ground-access step, bench, wood store, fishing pier, bucket, rod and a decorative moored rowboat. Water uses a separate opaque material with animated ripple normals and jade shallows. Stepping into deep water returns the player to the dry cabin approach. The boat and fishing gear are scenery; this does not introduce a fishing or rowing mechanic.

## Design and map

`output/imagegen/forest-lake/concept.png` was generated with **gpt-image-2.5-sunburst**, quality high, through the imagegen CLI, using current game stills and the current map. Prompt and provenance are alongside it.

The map follows the same accurate rough-layout → Sunburst painting → local registration process. `register_map.py` composites only the lake and trail, preserving 99.69% of the previous painting. Existing zone coordinates and map projection are preserved. The added **Hidden woodland lake** destination leads to dry ground beside the cabin.

## Rebuild

- Full world generation calls `forest_lake.layout.integrate` after the existing regional integrations.
- For a targeted update, `PYTHONPATH=japan python -m forest_lake.layout` snapshots the pre-lake world/heightmap in `out/forest_lake/source` and always reapplies edits from that snapshot. Do not overwrite that baseline with an already-integrated world.
- `blender -b --threads 2 --python japan/forest_lake/build.py`
- `blender -b --threads 2 --python japan/build_terrain.py`
- Import with `atelier build yorimichi unreal.lake` (Unreal's Python commandlet under the render lock and memory guard), with the stream stopped.
- Rebuild YorimichiEditor after C++ changes (`atelier build yorimichi unreal.compile`).
- `python japan/forest_lake/qa.py <fresh-session>` captures twelve native views and collision probes under the same memory guard.
- `node japan/streaming/forest-lake-smoke.mjs` exercises streamed touch movement along the forest trail, onto the porch and pier, and into shore recovery.

The build adds five static meshes, sharing the existing village material except for the independent water material. Water and planting have no collision; building, shore rocks and jetty retain complex query collision. No second rendering process is required.

## Validation

Native editor target compiled successfully. Eleven final inspection views plus a separate overview capture cover all four cabin sides, porch, wood store, boat interior, pier, islet, shore, trail and clearing. All seven native step/deck collision probes passed. The streamed touch test traversed the entire trail, mounted the porch and jetty, stepped into deep water and recovered to the shore, and used the new map destination. All 432 sampled movement states remained grounded along the trail and pier; reported stream frame rate was 59.9–60 FPS. The final native capture stayed around 7.2 GiB, below the 10 GiB process guard.

Follow-up detail fixes include the upward-facing dry boat floor, solid roof underlay, dormer, tiled canopy, stone footing, touching stacked logs, porch braces, fishing creel, rain barrel, rope bindings, and a planted rocky islet using an existing maple mesh.
