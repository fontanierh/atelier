# Kiyo, the tide-reader

Kiyo is an elderly NPC for Hidamari's seawall. She reads the tide, the weather and the odd bell-metal fragment that
washes up after a bad night, and she is one of the people who has noticed that the old hour bells keep something out.
She is not a quest-giver with an exclamation mark; she is a patient, practical presence at the edge of town.

The [Sunburst turnaround](references/sheet.jpg), [construction sheet](references/details.jpg) and
[attitude study](references/poses.jpg) are committed with their prompts and paid-call provenance. The model is built
entirely by [build.py](build.py) in headless Blender from [kiyo_mesh.py](kiyo_mesh.py) and [kiyo_rig.py](kiyo_rig.py):
no downloaded mesh, photogrammetry or texture atlas. Her visible design is deliberately limited to broad faceted
forms that survive at game-camera distance.

## Build

```sh
ATELIER_AGENT=tide-reader nice -n 10 uv run python -m atelier.safety.guarded \
  --small 3 --report build/yorimichi/tide-reader/guard --timeout 1200 \
  --purpose 'Kiyo tide-reader NPC Blender build' -- \
  blender -b --threads 2 --python-exit-code 1 --python build.py -- \
  --views front,profile,back,three_quarter,face,hat --export
```

The build writes `Kiyo-r01.blend`, `Kiyo-r01.glb`, six orthographic review renders and `build.json` under
`build/yorimichi/tide-reader/`. It validates the 23-bone humanoid contract, the 1.55 m height, floor contact, vertex
weights and at most four influences before exporting. The source `.blend` packs all three approved sheets for offline
review.

## Design and rig

- About 1.55 m tall, short and broad, about 4.4 heads tall; about 5,500 triangles and one opaque vertex-colour material.
- The 23 required humanoid bones use the exact names in `platform/conventions/rigs/humanoid.toml`. Extra bones carry
  the hat, low bun, shoulder mantle halves, tide staff, tide-board and satchel.
- The indigo weather hat is a 12-panel solid with a rust chin cord and brass brim rivets. The coat has a separate
  shoulder mantle, crossed collar and double rust sash. The tide-board carries four shell counters, and the staff has
  eight broad carved notches, a bell-metal cap and a tied shell.
- Feet sit on the shared 6.5 mm game floor, facing -Y, Z up. The model has no cloth simulation, hair strands, alpha
  cards or textures, so it remains cheap beside the villager and player characters.

## Files

| File | Contents |
| --- | --- |
| `concept.py` | Sunburst reference-sheet generation and paid-call provenance |
| `kiyo_mesh.py` | all head, hair, hat, clothing, hands, sandals and prop geometry |
| `kiyo_rig.py` | core humanoid rig plus cloth and prop extras |
| `build.py` | headless Blender scene, validation, renders, packed `.blend` and GLB export |
| `verify.py` | fresh-checkout checks for the GLB, rig, vertex colours, bounds and committed source hash |
| `references/` | the approved compact sheets, prompts and provenance |
