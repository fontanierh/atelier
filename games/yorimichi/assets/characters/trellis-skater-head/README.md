# Automatically reconstructed local TRELLIS head

- `head.glb`: selected 99,999-triangle lit head with 4K texture and conservative SAM2 repair.
- `head-40k.glb`: lighter 39,999-triangle lit head with sharp 4K texture.
- `head-quads.glb`: 9,092 automatic quads triangulated to18,184 triangles; rougher eyelids/hair.
- `quad-mesh.npz`: actual quad connectivity and triangle source, without Blender file paths.
- `mesh*.source.json.gz`: corresponding reduced geometric sources in native Z-up coordinates.
- `basecolor.png`, masks and `regions.png`: selected 100K texture and approximate automated regions.
- `provenance.json`: source/model hashes, geometry invariants, measured guards and camera/mask provenance.

The original neural reference is [the Sunburst skater image](../meshaxiom-skater-head/reference.png).
No manual mesh editing or new paid generation was used in this post-processing.
UV/paint preserves the separately reduced derivative; reduction changes the original
dense shape. The dense source remains retained as an experiment output.

See the [exact best setup and limitations](../../../docs/TRELLIS_HEAD_RETOPO.md) and
[eight-view comparisons](../../../docs/TRELLIS_HEAD_RETOPO_GALLERY.md). This is a
free local fallback with an existing reference, lower quality than Tripo, and not
a production facial-rig asset. Masks are conservative approximations, not semantic
ground truth; gold means protected features or unknown, not a fourth material.
