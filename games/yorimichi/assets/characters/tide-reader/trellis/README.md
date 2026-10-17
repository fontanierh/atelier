# Kiyo · local TRELLIS head and body

This folder holds the selected local TRELLIS rebuild of Kiyo (`tide-reader`). The procedural `Kiyo-r01` character remains the comparison baseline and is unchanged.

The head and body were generated separately from the two single-object Sunburst references in `references/`, then retopologized, UV-baked, inspected and assembled in headless Blender. The authored indigo weather hat, staff, tide board and satchel are retained; their geometry is not neural.

## Selected files

- `Kiyo-TRELLIS.glb`: render model, 261,583 triangles, one 30-bone skeleton, 4K head and body atlases.
- `Kiyo-TRELLIS.blend`: the assembled Blender source used for the GLB.
- `reports/`: exact generation, bake, repaint and assembly reports.
- `../assemble_trellis.py`: the deterministic fit and assembly script.

The procedural sources remain at `../Kiyo-r01.glb`, `../Kiyo-r01.blend` and `../source-manifest.json`.

## Generation settings

- Backend: Microsoft TRELLIS.2 MLX, native learned RGB and vertex colours, single-image conditioning.
- Both parts use seed 42, 12 steps, `--max-tokens 16384` and requested resolution 1024.
- Head: actual mesh grid 768, 14,668 selected tokens, 8,074,802 native triangles, 17m23s, 9.38 GiB aggregate peak under the 14 GiB guard.
- Body: actual mesh grid 1024, 6,981 selected tokens, 4,345,274 native triangles, 7m40s, 7.68 GiB aggregate peak under the 14 GiB guard.

No paid image call is needed to reproduce the model: both references, their exact prompts and their ledger provenance are committed beside this file.

## Processing

- Head reconstruction used the 26-view exterior surface, one-thread screened Poisson depth 9 and adaptive QEM at 100K. The selected bake is 99,999 triangles, 4,609 charts and a 4K atlas with zero UV interior overlaps. SAM2.1 Tiny on MPS used the grey-hair palette; conservative repair changed 57 skin texels and 73 hair texels while keeping every geometry, normal, UV and index buffer exact. The full repaint changed about 8.15 million region texels and softened the face, so it was not selected.
- Body reconstruction selected 160,000 triangles and an 80K fallback is retained in the build area. Blender Smart UV formed the charts; conflicting faces were split and a small residual set was shrunk 10% in UV space. The final layout reports zero conflicts, no vertex movement, a 4K atlas and zero UV interior overlaps.
- Selected processed inputs: head `7d1f4965303d959124ce14ca2cdb96f8ce3d228b18ff168944e108344eabcac7`; body `33d7081632cb8858ac2f8219e80b1a246108956bed2e382c3cbf67d7972e0429`.

## Assembly

`../assemble_trellis.py` uniformly fits the body to 1.115 m at the neck top, uniformly scales the head to 0.325 m and overlaps its underside 35 mm into the neck. It measures the body neck plug, chest front, head under-cap and face front in mesh space, then moves the head along its own measured face direction to a 20.0 mm profile clearance from the chest (38.5 mm in this export, unclamped). The measured neck XY also seeds the neck and head bone pivots, so a head turn pivots at the socket rather than world zero.

The authored hat is centred on the top-2% crown centroid and lowered to a measured 4.0 mm inner-brim contact with the crown (28.3 mm in this export, unclamped); its bone remains a child of `head`. The report records the achieved clearance, contact and both clamp flags, not just the configured targets. The assembled character is 1.520 m to the hat top.

The assembly retains the authored accessories and writes one 30-bone armature: the 23-bone humanoid contract plus `hat`, `hair_bun`, `cape_L`, `cape_R`, `staff`, `tide_board` and `satchel`.

Blender's bone-heat solve failed on the generated body, so the selected mesh uses deterministic nearest-segment weights with at most four influences per vertex and zero unweighted vertices. The palette material's vertex-colour emission link is flattened to black for glTF because glTF cannot represent it; `COLOR_0` still carries the full indigo/brass palette.

Reproduce the assembly from a clean worktree. The measured assembly peak was 0.68 GiB, so this uses the
existing 3 GiB small envelope; normal admission still decides the turn and the command uses a fresh report and
output rather than overwriting the selected artifact.

```sh
ATELIER_AGENT=tide-reader nice -n 10 uv run python -m atelier.safety.guarded \
  --small 3 --report build/yorimichi/kiyo-local/assembly-guarded.guard --timeout 600 \
  --purpose 'Kiyo corrected TRELLIS assembly fit' -- \
  blender -b --threads 3 --python-exit-code 1 --python games/yorimichi/assets/characters/tide-reader/assemble_trellis.py -- \
  --head build/yorimichi/kiyo-local/head-post/paint100k/head.glb \
  --body build/yorimichi/kiyo-local/body-post/bake160k-final/head.glb \
  --baseline games/yorimichi/assets/characters/tide-reader/Kiyo-r01.blend \
  --output build/yorimichi/kiyo-local/assembly-verify \
  --report build/yorimichi/kiyo-local/assembly-verify/report.json
```

The generation, reconstruction, UV and mask commands are in `games/yorimichi/docs/TRELLIS_HEAD_RETOPO.md`, `TRELLIS_HEAD_RETOPO_GALLERY.md` and `APPLE_HEAD_MODELS.md`. Use normal render admission and the documented aggregate guards.

## Viewer

The selected comparison viewer is staged as a build artifact under `build/yorimichi/kiyo-local/viewer` and published on the machine's tailnet `/kiyo` route. It shows the two source references, the procedural `Kiyo-r01` baseline and the new `Kiyo-TRELLIS` model with matched front, three-quarter, profile and head views, plus wireframe, material, turntable and download controls. The fit gallery adds before/after profile and head close-ups, a head turn, a neck close-up and arms-down/crouch pose checks.

## Limits

This is a free local fallback, below Tripo-quality parity. The masks are automatic and approximate; the face and hair were inspected in matched views but no manual facial sculpting was done. Body weights are deterministic nearest-segment weights rather than an animator-authored skin, so the pose check is part of the acceptance evidence. The 14 GiB process cap is a guard, not a claim that the job fits a 16 GiB installed-RAM host.
