# Hidamari community skate park

The textured community megapark from Atelier's own asset library
sits in the northern apron above Hidamari station, east of the summit trail. It
is separate from the original Super Ultra Mega Park in the western foothills.
Travel to **Hidamari · community skate park** from the world map, or take the
four-metre approach north from the station street at `(1240, 342)`.

The source's 586 placements are preserved at metre scale, batched into 30 meshes.
The complete scene turns 180° about its recentered root and moves to
`(1280, 560, 38.472)` in island metres. Its main deck is at `48.5 m`, the tall
vert reaches `85.586 m`, and its footprint is about `94 × 103 m`. The approach
rises over 197.7 m, with a maximum grade of 9.30%. Its station-side join starts
on the street's last uncarved row, flush with the asphalt.

## Source and build

The scene and its five embedded texture maps are part of Atelier's own asset
library. The complete GLB is committed at
`assets/communitypark/megapark-textured.glb`, so a fresh checkout includes the
park, terrain patch, vegetation clearing, map drawing and travel entry.

```sh
uv run atelier build yorimichi
```

`assets/communitypark/source.json` records its local filename, size, SHA-256 and
geometry inventory. The reader rejects changed source bytes. Both UV channels
and source normals are retained; the colour textures use UV1. Surface assignments
and PBR factors are stored in the library scene.
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

Faded indigo steel frames carry the elevated ramp groups from braced
four-legged trestle towers outside the source skating footprint, never from
a lone pole. Each girder keeps its audited anchor on the tower's headstock; the
tower stands outward from it, 1.8 m square where the ground allows and narrower
in the slots between deck pieces, with ring struts every 2.6 m and X-bracing on
every face. A girder leaving its tower is trussed underneath where its lower
chord can stay 3.1 m above every surface below. Underside ribs follow the original slabs;
full pipes bear on their bottoms, keeping their riding tubes open. Two short
feet use an already closed low pad edge, and the original grind features keep
their normal inset legs. The top bridge rests on an exterior tower instead of
putting columns in the bowls. A timber service stair rises
from the north deck through eighteen switchback flights and broad landings;
14.7 cm risers, 45 cm treads and a 2.4 m width suit normal character movement.
The railed top bridge joins the highest original ramp at its ridge. Its open
west edge permits a drop-in. Timber reuses the project's authored cedar texture. Source ramp placements remain unchanged.

### Restyle

The park follows three Sunburst concepts painted over its game views
(`tools/communitypark_concepts.py`; prompts in
`assets/communitypark/concepts/prompts.json`, paintings and provenance in the
ignored build folder): braced indigo towers, warm painterly concrete, indigo
coping, stencilled wall panels and lawn furniture. `tools/communitypark_textures.py
paint` makes the textures from text alone and
keeps their compact copies and provenance in `assets/communitypark/restyle`.
`finish` (`world.communitypark_restyle`) makes them seamless, brings them to the
island palette and saws a 2 m joint grid into the concrete at the UV1 tile edge.
They replace the library smooth concrete, poured concrete, skatelite, steel
and granite maps; source geometry and UVs are unchanged.
`world/regions/communitypark/murals.py` paints the exposed flat walls (open air in
front, open sky above; coplanar neighbours merged) with faded indigo waves or
mustard maples at a 4.5 × 3 m repeat, or a vermilion sunburst fitted to
well-proportioned walls. Each mural is a quad 1.5 cm proud of its wall with a
concrete margin and no collision. `props.py` spreads 8 timber and granite
benches, 10 lantern posts, 6 granite planters with ochre shrubs and 4 wave
banners on the lawn 1.2–3.5 m beyond the pieces, off the approach, the stair
route and the tower footprints.

`unreal.communitypark` imports `/Game/CommunityPark`, checks scale, bounds and
UV count, binds the restyled materials, and enables complex collision on the
blocking meshes. The 30 rendered source meshes do not block. The skate rides the
hidden `SM_CP_Collision` instead (`collision.py`): the same triangles with
coincident vertices welded across the 586 placements. Wherever a riding edge
stands 4 mm to 8 cm proud of the neighbouring piece, a 1:8 ramp runs from it
down onto that piece's plane. The ramp's run ends taper along the edge too. The
native skate rolls over at most 12 mm, so a taller joint lip used to stop the
wheels and bail the rider. Ledges and the flat rail stay sharp; steps over
8 cm stay as they are. `ASkatePark` loads the generated manifest through its
optional asset root and key. A manifest entry marked `hidden` is collision
only. Sunset Pier retains its existing assets and
QA spawn. Rails, ledges and continuous coping paths derive from source edges.

## Validation and captures

```sh
uv run pytest games/yorimichi/tests/test_communitypark*.py
uv run python games/yorimichi/world/regions/communitypark/validate.py --imported
uv run python games/yorimichi/tools/review_communitypark.py --gait 1
```

The riding audit samples every open riding edge of the collision every 10 cm and
fails on any piece edge left more than 12 mm above its neighbour (208 samples
before the ramps, none after). It also counts the 45 samples, at 13 corners, where a
ramp's run ends against a third piece and its side cheek keeps up to the original
lip. Those are not ramped yet. The import audit also compares `SM_CP_Collision`
triangle for triangle.
The source audit samples upward triangles at intervals of at most two metres,
checks that ground stays below them, checks the access grade and its deck join,
and compares the patch boundary. The import audit compares all 30 built source
meshes against the pinned GLB, tolerating only 0.01 cm float conversion.
The structure audit checks grounded contacts, footing and body clearance at
every ascent waypoint and at 25 cm intervals between them, the deck riding
lane, and every added mesh (structures, murals, props) after import. It also sweeps a 25 cm walking body
along every route segment, from 0.40 to 1.95 m above the floor, measuring the
exact plan distance to each nearby triangle so thin posts between samples fail.
No two added faces may share a plane, face the same way, overlap and shade differently: the depth test
flickers between them. Stair stringers stand 2 cm proud of the tread ends, and the top bridge's decking
abuts its landings instead of overlapping them.
Every tower leg and frame footing must sit outside every original piece's footprint with a 65 cm margin. A separate solid-member audit
samples each frame beam's width and depth against the original scene, checking
a 70 cm rider width and up to three metres of previously usable skating
airspace, starting two centimetres above each riding surface so small wheel-height
bumps are caught too. This detects tall columns even when both endpoints lie outside the
rider's height band. These source checks supplement the game review.
The guarded game review owns a separate loopback bridge and quits its own game;
it checks actor/mesh/tree inventory, original surface traces, riding, the
Sunset Pier QA spawn and the entire ascent using character movement without
intermediate teleports, using the normal running gait within the review deadline.
It captures the overview, approach, bowls, trestles,
stair tower, bridge and top arrival. Evidence and
captures go under `build/yorimichi/communitypark/`, never beside source files.
