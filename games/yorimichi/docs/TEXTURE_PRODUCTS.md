# Independent source textures

`nice -n 10 uv run atelier build yorimichi world.textures` still generates the island's complete texture set.
Each of its 22 PNG/JPEG files is now owned by one action and one portable product. For example,
`world.textures.leaf_maple` owns `texture.leaf_maple`, whose only output is
`build/yorimichi/textures/T_leaf_maple.png`.

Edit the corresponding JSON under `world/textures/` to change its settings. A maple palette edit changes only
the maple source action's key; it does not regenerate cedar, bark or sky. Each action reads its selected spec,
shared generator/import code and managed Python tool context. Bark additionally reads `tree-bark.jpg`;
ground detail reads the Tuscan ground image and its existing checksum provenance. No other source texture
depends on those images. A shared algorithm change intentionally invalidates its shared-code users.

The `world.textures` aggregate writes nothing and reads every texture product's byte identity. Existing mesh
and Unreal steps retain their familiar dependency on that aggregate. Regenerating an identical texture leaves
the aggregate current; changing texture bytes still invalidates these existing broad consumers. This change
does not divide Unreal imports or prove new native package behavior.

Each product owns its exact file, rather than the containing directory. The forest finishing tool owns its
separate `forest/textures` output; treehouse recolours remain under `treehouse/trees`. They cannot be removed
by restoring an island texture. The generator refuses a selected output filename that differs from its catalogue.
The argument-free `world/gen_textures.py` command remains available and uses the same selected generators.

Local cache hits verify complete file inventories and restore independent copies. A fresh output directory can
reuse already certified textures without launching their Python actions. Audited execution must succeed before
certification; an import/bootstrap error is a failure, never a reason to accept old outputs or disable auditing.

The complete 22-texture audited cache proof took 17.844 seconds cold, 0.800 seconds warm with no action executions,
and 4.483 seconds to restore into a different directory. The receiver's action runner was replaced with an
execution failure, and donor outputs were moved away. All restored files matched the legacy bytes; every cold
audit passed. This used Python 3.12.12, NumPy 2.5.3 and Pillow 12.3.0. It exercises portable source textures;
native consumers retain their broad aggregate dependency.

The source refactor was compared against the generator at `bd755fb9`: all 22 file sizes and SHA256 digests
matched for the legacy run, the split aggregate, and reversed selection with one fresh Python process per
texture in another directory. The serial proof took 61.528 seconds, with a maximum individual child RSS of
702,775,296 bytes. This proves source-byte compatibility under the recorded Python/Pillow/NumPy environment;
it does not claim native import validation. Generated receipts and captures belong under ignored
`build/yorimichi/texture-proof/`, not beside sources.

Focused tests use actual small Pillow/NumPy textures to check audit certification, warm stamps, restoration in
a different directory with execution forbidden, independent copies, and one-spec invalidation of only its
texture and consumers. Other source generators retain their current ownership and cache policy.
