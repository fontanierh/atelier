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
