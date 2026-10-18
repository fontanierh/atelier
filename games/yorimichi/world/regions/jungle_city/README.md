# Jungle City proposal

`Jungle City` is an unplaced Yorimichi region proposal: a roughly 650 x 520 m
Khmer-inspired city enclosed by tropical forest. It is deliberately absent from
the game recipe and Unreal project. The source produces review assets only:

- `assets/concepts/`: compact GPT Image 2.5 Sunburst references and ledger records.
- `build/yorimichi/jungle-city/concepts/originals/`: full-resolution generated PNGs.
- `build/yorimichi/jungle-city/models/`: separate Blender/GLB modules and their assembled scene.
- `build/yorimichi/jungle-city/reviews/`: headless Blender comparison renders.
- `viewer/`: a local Three.js proposal viewer, served on loopback and published
  through Tailscale Serve when requested.

## Reproduce

```sh
uv run python games/yorimichi/world/regions/jungle_city/concepts.py
uv run python -m atelier.safety.guarded \
  --report build/yorimichi/jungle-city/guard/build \
  --timeout 1800 --purpose "Jungle City modular Blender build" --kind job -- \
  blender --background --python games/yorimichi/world/regions/jungle_city/build.py
uv run python games/yorimichi/world/regions/jungle_city/viewer/serve.py --port 8899
```

Every paid concept call is created in `atelier.ai.ledger` before submission and
is never retried by the script. The model builder uses Blender 5.2 headless and
exports reusable modules before importing them into `JungleCity.glb`.
