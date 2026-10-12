# Nox

A playable 1.78 m young adult in a black bomber and violet-patterned shirt, with a separately generated head,
repaired painted face, earring, 66 rigged locs and a chain painted onto the garment atlas. No watch.

`Nox.glb` is the approved source, with two embedded 4K atlases and one skeleton. `source-manifest.json` and the
asset-library manifest check its hash. The original 65-bone body rig and 180 hair bones remain in the source.
`export_unreal.py` adds the game's root, scale and humanoid names to a fresh imported copy.

The garment repair retains the original neutral geometry and painted folds, with corrected body weights and
25 sparse seat targets (16 nonzero). The importer requires those targets and captures their native LOD0 deltas
as serialized mesh user data, so contact readers can account for the same pose correction in desktop builds.
The runtime uses hip flexion and bounded bilinear interpolation; neutral and ordinary walking remain unchanged
by the seat targets. Final native garment appearance and contact acceptance are pending for this revision.

Build with `uv run atelier build yorimichi unreal.nox_adventure unreal.nox_bike data.network`, then select Nox in the
character menu or run `uv run atelier play yorimichi -- -rider=Nox`. Every merged and donor action is retargeted;
bike actions are authored on his rig and skating uses the shared runtime retargeter.

The [full recipe](../../../docs/NOX_CHARACTER_RECIPE.md) covers the generations, Pixel Match face transfer,
ear/scalp/chain repairs, assembly, clipping-mark tool and all-lock rig. Current refs and exact prompts are under
`references/`. Prior models, watch experiments and captures stay archived outside Git.

`hair-preview.json` is the calibrated neutral-pose browser demo configuration. It does not claim native Unreal
hair physics or collision against animated clothes. The game animation retarget preserves the auxiliary bones.
