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
rises over 196.7 m, with a maximum grade of 9.47%. Its station-side join sits
at the stone pavement height, just above the terrain datum.

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
The park owns a sixty-metre woodland belt with mature, overlapping maple,
ginkgo and cedar crowns on staggered 4.5 m spacing. The tree-house canopy
meshes provide articulated branches and 1,100–1,250 leaf cards per crown.
Coherent red, gold and dark-green groves replace isolated roadside trees;
young trees, overlapping shrubs, grasses and litter close the lower layers.
Trunks and plants stay outside the source footprint. Mature trunks leave
9.5 m clearance from the approach centreline, young trees 6.8 m, shrubs
4.8 m and ground plants 3.2 m, preserving the four-metre riding ribbon.
The revised seclusion direction uses a high-quality Sunburst paintover of
actual overview and station-approach captures; its provenance stays in build.

Dark steel frames carry the elevated ramp groups from shared piers outside
the recovered skating footprint. Underside ribs follow the original slabs;
full pipes bear on their bottoms, keeping their riding tubes open. Two short
feet use an already closed low pad edge, and the original grind features keep
their normal inset legs. The top bridge shares an exterior pier instead of
putting columns in the bowls. A timber service stair rises
from the north deck through eighteen switchback flights and broad landings;
14.7 cm risers, 45 cm treads and a 2.4 m width suit normal character movement.
The railed top bridge joins the highest original ramp at its ridge. Its open
west edge permits a drop-in. The design follows a high-quality
`gpt-image-2.5-sunburst` concept; the model, prompt and paid-call provenance stay
with the concept in the ignored build folder. Timber reuses the project's
authored cedar texture. Source ramp placements remain unchanged.

`unreal.communitypark` imports `/Game/CommunityPark`, checks scale, bounds and
UV count, binds the reconstructed materials, and enables complex collision
from the rendered triangles. `ASkatePark` loads the generated manifest through
its optional asset root and key. Sunset Pier retains its existing assets and
QA spawn. Rails, ledges and continuous coping paths derive from source edges.

## Validation and captures

```sh
uv run pytest games/yorimichi/tests/test_communitypark*.py
uv run python games/yorimichi/world/regions/communitypark/validate.py --imported
uv run python games/yorimichi/tools/review_communitypark.py
```

The source audit samples upward triangles at intervals of at most two metres,
checks that ground stays below them, checks the access grade and its deck join,
and compares the patch boundary. The import audit compares all 30 built source
meshes against the pinned GLB, tolerating only 0.01 cm float conversion.
The structure audit checks grounded contacts, footing and body clearance at
every ascent waypoint and at 25 cm intervals between them, the deck riding
lane, and both new meshes after import. Main piers must sit outside every
original piece's footprint with a 65 cm margin. A separate solid-member audit
samples each frame beam's width and depth against the original scene, checking
a 70 cm rider width and up to three metres of previously usable skating
airspace. This detects tall columns even when both endpoints lie outside the
rider's height band. These source checks supplement the game review.
The guarded game review owns a separate loopback bridge and quits its own game;
it checks actor/mesh/tree inventory, original surface traces, riding, the
Sunset Pier QA spawn and the entire ascent using character movement without
intermediate teleports. It captures the overview, approach, bowls, trestles,
stair tower, bridge and top arrival. Evidence and
captures go under `build/yorimichi/communitypark/`, never beside source files.
