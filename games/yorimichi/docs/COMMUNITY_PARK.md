# Hidamari community skate park

The textured April 2024 community megapark from `fontanierh/skate-extractions`
sits in the northern apron above Hidamari station, east of the summit trail. It
is separate from the original Super Ultra Mega Park in the western foothills.
Travel to **Hidamari · community skate park** from the world map, or take the
four-metre approach north from the station street at `(1240, 343)`.

The source's 586 placements are preserved at metre scale, batched into 30 meshes.
The complete scene turns 180° about its recentered root and moves to
`(1280, 560, 38.472)` in island metres. Its main deck is at `48.5 m`, the tall
vert reaches `85.586 m`, and its footprint is about `94 × 103 m`. The approach
rises over 196.7 m, with a maximum grade of 9.58%.

## Source and build

Recovered geometry and texture pixels belong to their original owners. The
public repository contains the pin, importer and placement code; the GLB and
five PNGs remain in the ignored cache/build folders. The fetch needs `gh`
authenticated with access to the private handoff repository:

```sh
uv run atelier fetch yorimichi
uv run atelier build yorimichi
```

`assets/communitypark/source.json` pins commit, blob, size and SHA-256. The
fetch refuses a changed checksum. Both original UV channels and source normals
are retained; the colour textures use UV1. Surface assignment and PBR factors
are the handoff's reconstruction, rather than the original game's shaders.
Fifty zero-area source triangles are explicitly omitted from Unreal import;
the other 39,545 source triangles retain their positions without simplification.

`world.communitypark` exports the original pieces, the approach and a 1 m
ground patch. The patch replaces matching coarse mountain cells and cuts below
upward riding surfaces, including narrow floor spacers and bowl bottoms.
Downward foundations can remain buried. Its outer nodes share the surrounding
terrain height. Vegetation is cleared around skating and the approach; nearby
backdrop crowns become detailed island trees.

`unreal.communitypark` imports `/Game/CommunityPark`, checks scale, bounds and
UV count, binds the reconstructed materials, and enables complex collision
from the rendered triangles. `ASkatePark` loads the generated manifest through
its optional asset root and key. Sunset Pier retains its existing assets and
QA spawn. Rails, ledges and continuous coping paths derive from source edges.

## Validation and captures

```sh
uv run pytest games/yorimichi/tests/test_communitypark.py
uv run python games/yorimichi/world/regions/communitypark/validate.py --imported
uv run python games/yorimichi/tools/review_communitypark.py
```

The source audit samples upward triangles at intervals of at most two metres,
checks that ground stays below them, checks the access grade and its deck join,
and compares the patch boundary. The import audit compares all 30 built source
meshes against the pinned GLB, tolerating only 0.01 cm float conversion.
The guarded game review owns a separate loopback bridge and quits its own game;
it checks actor/mesh inventory, original surface traces, riding, both park
destinations and captures the overview, approach, deck and bowls. Evidence and
captures go under `build/yorimichi/communitypark/`, never beside source files.
