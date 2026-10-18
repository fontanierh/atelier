# Jungle City proposal

`Jungle City` is an unplaced Yorimichi region proposal: a roughly 650 x 520 m
Khmer-inspired city enclosed by tropical forest. It is deliberately absent from
the game recipe and Unreal project. The source produces review assets only:

- `assets/concepts/`: compact GPT Image 2.5 Sunburst references and ledger records.
- `assets/jungle_city/references/`: isolated Sunburst references for local TRELLIS reconstruction.
- `assets/jungle_city/textures/`: compact Sunburst material plates and ledger records.
- `build/yorimichi/jungle-city/concepts/originals/`: full-resolution generated PNGs.
- `build/yorimichi/jungle-city/models/`: separate Blender/GLB modules and their assembled scene.
- `build/yorimichi/jungle-city/reviews/`: headless Blender comparison renders.
- `build/yorimichi/jungle-city/trellis/`: raw local TRELLIS checkpoints and candidate GLBs.
- `build/yorimichi/jungle-city/retopo/`: exterior reconstruction, adaptive reduction and 4K bakes.
- `viewer/`: a local Three.js proposal viewer, served on loopback and published
  through Tailscale Serve when requested.

## Reproduce

```sh
uv run python games/yorimichi/world/regions/jungle_city/concepts.py
uv run python games/yorimichi/tools/jungle_city_assets.py references
uv run python games/yorimichi/tools/jungle_city_assets.py textures
uv run python -m atelier.safety.guarded \
  --report build/yorimichi/jungle-city/guard/build \
  --timeout 1800 --purpose "Jungle City modular Blender build" --kind job -- \
  blender --background --python games/yorimichi/world/regions/jungle_city/build.py
uv run python games/yorimichi/world/regions/jungle_city/viewer/serve.py --port 8899
```

Every paid concept call is created in `atelier.ai.ledger` before submission and
is never retried by the script. The model builder uses Blender 5.2 headless and
exports reusable modules before importing them into `JungleCity.glb`.

Local 3D assets use the documented `head_models.py` TRELLIS.2/MLX cascade and
`head_retopo.py` exterior reconstruction, adaptive QEM reduction and checked UV
bake. A candidate is promoted only after `jungle_city_validate.py` records its
geometry, UV, texture and hash checks in `source-manifest.json`.

For the first `hero_prang` candidate, run each guarded stage with a fresh report
directory. The raw generation checkpoints remain the reference and are never
edited by the derived retopology outputs.

```sh
export ATELIER_AGENT=jungle-city-01a14c57
retopo_root=build/yorimichi/jungle-city/retopo/hero-prang
checkpoint=build/yorimichi/jungle-city/trellis/hero-prang-01/checkpoints

nice -n 10 uv run python games/yorimichi/tools/head_retopo.py \
  setup --root "$retopo_root" --memory-gib 4 \
  --report build/yorimichi/jungle-city/guard/retopo-hero-prang-setup
nice -n 10 uv run python games/yorimichi/tools/head_retopo.py \
  surface --root "$retopo_root" --checkpoint "$checkpoint" \
  --output "$retopo_root/surface" --memory-gib 8 \
  --report build/yorimichi/jungle-city/guard/retopo-hero-prang-surface
nice -n 10 uv run python games/yorimichi/tools/head_retopo.py \
  reconstruct --root "$retopo_root" --checkpoint "$checkpoint" \
  --source "$retopo_root/surface/cloud.npz" --output "$retopo_root/reconstruct" \
  --depth 9 --triangles 40000 100000 --memory-gib 8 \
  --report build/yorimichi/jungle-city/guard/retopo-hero-prang-reconstruct
nice -n 10 uv run python games/yorimichi/tools/head_retopo.py \
  bake --root "$retopo_root" --checkpoint "$checkpoint" \
  --source "$retopo_root/reconstruct/mesh-100000.npz" \
  --color-cloud "$retopo_root/surface/cloud.npz" --output "$retopo_root/bake100k" \
  --texture-size 4096 --neighbors 1 --memory-gib 8 \
  --report build/yorimichi/jungle-city/guard/retopo-hero-prang-bake

uv run python games/yorimichi/tools/jungle_city_validate.py \
  "$retopo_root/bake100k/head.glb" \
  --output "$retopo_root/hero-prang.validation.json"
uv run python games/yorimichi/tools/jungle_city_promote.py \
  hero_prang "$retopo_root/bake100k/head.glb" \
  "$retopo_root/hero-prang.validation.json"
```

Promotion is deliberately separate: generation or reconstruction success does not
make an asset library source. Repeat the same sequence with fresh paths for each
remaining object, then rebuild the assembled Blender scene and viewer model.
