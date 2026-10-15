# Crater Park

Crater Park is a skate park on the volcano's caldera floor ([VOLCANO.md](VOLCANO.md)). Its author made it and gave it
to Yorimichi from [fontanierh/crater-skate-park](https://github.com/fontanierh/crater-skate-park). It is a 337.9 ×
384.5 m block of hillside with concrete runs, bowls, wooden ramps, plazas and paths. It has no trees, props or grind
paths yet.

## Source

`assets/craterpark/` holds everything from the repository's `readable/mountain/`, converted once by
[`craterpark/extract.py`](../world/regions/craterpark/extract.py). The build reads only these committed files; a
checkout of the park's repository is needed only to rerun `extract.py` and refresh them.

| File | What |
|---|---|
| `scene.json` | Every mesh: role, material, bounds, checksums, and its arrays file |
| `geometry/*.npz` | 197 meshes: `positions`, `uvs`, `triangles` and `render_skip` |
| `materials.json`, `textures/` | 28 materials and 21 textures, unchanged |
| `drop-in.json` | The marked ramp drop-in |
| `provenance.json` | Source repository, commit and conversion |

The arrays are bit-identical to the source. Each mesh's `arraysSha256` is checked on conversion and in
`tests/test_craterpark.py`. The OBJ files and per-mesh JSON hold the same arrays, so they are left out. To update the
park, convert a clean checkout of a newer commit:

```sh
uv run python games/yorimichi/world/regions/craterpark/extract.py /path/to/crater-skate-park
```

The meshes have these roles:

| Role | Meshes | Triangles | Use |
|---|---|---|---|
| original | 85 | 97,809 | Textured skating surfaces |
| helper | 85 | 97,809 | Untextured duplicates; kept in the library, not built |
| foundation | 10 | 753,704 | Foundations under the skating surfaces |
| mountain | 1 | 70,694 | The closed block of hillside the park stands on |
| access_bridge, bridge_support | 15 | 4,476 | Bridges |
| boundary | 1 | 8,688 | The edge guard |

## Placement

[`craterpark/placement.py`](../world/regions/craterpark/placement.py) moves the park as one rigid body:

- Native points (x, y up, z) become Blender metres (x, −z, y).
- They turn by `HEADING` (185°) about the block's centre, which lands on the caldera's centre (850, 2400).
- They rise by `LIFT` (680 m), so the block's low east edge meets the 640 m caldera floor.

The block's high side faces the tallest part of the crest. It keeps at least 60 m to the wall's foot. The main deck
stands about level with the crest's lowest stretch (687 m) and the roll-in ramp's top (720 m) just over most of it
(median 723 m). From the top of the roll-in a rider sees over the rim in about half of all directions: the far
horizon, not the land below. No part of the park can be seen from the city, Belmonte, the Mega Park, the foothill
trail or the volcano's flanks.

## Ground

The block's sides go down to 110 m below its top, so the caldera floor is shaped to bury them
(`placement.terrain`, chained into `hidamari/mountains.py` `raw_height`):

- **Under the block:** the ground sinks `SINK` (2 m) below the block's lowest top within `REACH` (15 m). No terrain
  triangle pokes through.
- **Round it:** the floor is offset to the block's top edge, less 0.3 m. It eases back over a skirt 30–120 m wide,
  which widens with the height it makes up (up to about 57 m on the high side).

## Dressing

The caldera round the park has its own planting (`hidamari/layout.py` `dress_caldera`), from its own random stream:
about 26 stands of 16-35 trees (the Mega Park's detailed pines and cedars, with fewer maples and ginkgos), on the
floor and the wall's lower slope; about 50 groups of two to five grey boulders 9-16 m across (`SW_Boulder_*`, which
take no snow) with scree on bare ground; and ochre shrubs. About 9,600 autumn thicket plants clump along the crest, on
rock as steep as 55 degrees and more thinly on snow (loose red and gold `Bush_HD_Autumn` bushes, ochre bushes and a
few red shrub maples and golden ginkgo shrubs), and ochre bushes ring the park's block 9-40 m out, snow or not. The
block itself carries none of the island's planting. `dress_caldera` places about 250 granite domes and 10,000 bushes
on the block's hillside, but the block filter that follows (`contains(margin=3)`) drops them, so city.json has no
instance on the block. In the r5 build the nearest is 5.5 m off its 5 m mask. The v2 park dresses its own ground
instead ([`v2/dressing.py`](../world/regions/craterpark/v2/dressing.py)): autumn and ochre bushes on its upward ground
faces, 4 m plus their reach clear of every riding, side, coping and rail face, planted by the park actor from
park.json `trees`. `dressing.check` keeps every drawn v2 face on the block's mask, and every riding face 4 m inside the
ground the island keeps clear of dressing, so no island plant or rock pokes through it. The
autumn bush has a warm core: the garden shrubs' near-black one, sunk in a slope or seen from afar, read as black
shards on the snow. Bushes have no collision and are culled beyond 300 m, the autumn bush beyond 550 m (the rim and
air views look across the caldera; `JapanWorld.cpp`). Some 500 granite stones (`HD_NorthRockA`/`C`, as on the north
slopes) lie in clusters over the floor, and about 70 low crags 15-30 m across sit deep in its bare ground, so from
the zeppelin the floor reads as dark rock among the snow. No tree or stone stands within 7 m of the park's block. The
caldera is a `near_trees` box, so its trees cast shadows and keep trunk collision.

The volcano's own snow (`hidamari/mountains.py` `snow_cover`) leaves about a third of the caldera floor white, the
rest dark cinder. Broad couloirs, tens of metres wide, run down the inner wall from just under the crest to its foot,
between rock ribs, each narrowing upward to a point at its own height, breaking on the steepest cliff risers, so a
little over a third of the wall is white (the zeppelin target). On the outer flank snow lies in snowfields between
bare rock ribs for about 110 m below the crest, and about half the gullies carry a long couloir, wandering and
unbroken, from the crest towards the tree line (the city target). Away from the chutes and the collar, snow slides off
rock steeper than about 55 degrees, and fine rock noise breaks every patch into many small pieces, so it reads as snow
among broken granite rather than cut-out blobs or strips. The mountain material shades the exposed rock in faceted
planes about 22 m across (on steep faces, columns about 15 m wide and 60 m tall, so walls read as jointed cliffs),
each broken into faces about 7 m across (5 m cells alone read as cobbles), each tilted at random against the sun, warm
where lit and cool where turned away, so the walls read as granite rather than clay; bright olive moss patches its
gentler upward faces.

## Snow

The block's hillside (`material_024`) carries snow on its flatter tops and benches, with a crisp edge
(`import_craterpark.py` `SNOWY`); its sides steeper than about 33 degrees show the volcanic ground in bands, like the
targets' outcrops. Smooth value noise (about 26 m and 9 m) leaves about half the flat ground bare in broad
patches, so the block never reads as a white sheet; sine patterns of holes read as spots and dashes, and a soft edge
left the dark ground smeared through the snow. The skating surfaces, the edge guard and its coping, foundations and
bridges stay clear. The park's materials are matte, like the terrain's.

## Shading

The park has no lightmap to take occlusion from, as the Mega Park does, so `craterpark/build.py` bakes it: the drawn
triangles fill a 0.5 m voxel grid, and from every drawn vertex 16 cosine-weighted rays march out to 12 m. The result
(1 open, 0 closed) is the vertex colour, sRGB-encoded. The parent materials take `Occlusion` (0.6) of it from the sky's
fill and `Cavity` (0.3) from the albedo, so bowl floors, wall feet and the gaps between boxes darken and the blue
sky fill no longer lights every face evenly. It costs 4 bytes per drawn vertex: about 0.43 million vertices, 2-3 MB
of GPU memory with Unreal's vertex splits.

Foundation faces that lie on a drawn riding surface (within 5 cm, facing the same way; the foundations sit up to 3 cm
off the surfaces) are left out of the render, so they no longer flicker through it, and out of the collision. Every
riding surface had a foundation face within 6 cm of it, and the board met the two as rival contacts: the ride stuttered
on every ramp and bailed on the snake run's joins. A downward face lying on an upward one (a double-sided piece modelled
with both windings) is left out too. The collision is what is drawn, as Mega Park's: the riding surfaces exactly, never
simplified (a simplified ramp strayed up to 2.3 cm off its curve), the other roles simplified.

Inside the block, the foundations' shared walls and the pieces' sides rise to 3 cm under the ramps. At speed (above
about 7 m/s) the board's trucks met their top edges head-on: a single contact closing faster than the simulation's
7.1 m/s limit, which it treats as a run-out, so the rider stepped off on the snake run's joins and at the foot of the
wooden ramps. The collision leaves out every steep face whose top edge lies inside the solid (a riding face over it,
and 2 cm to either side across the wall, up to 1 m above; a point on the seam of two riding faces is under both), and sinks every other collision corner inside the solid 25 cm, so a wall
with an outer corner showing keeps its outside. A riser of 3 cm or more keeps its face. About 260,000 hidden faces
leave the collision; by the east wooden ramps they filled the board's collision snapshot (196,608 triangles).

The skate simulation tests a snapshot's triangles 64 at a time, in their stored order, against each group's box. The
simplified foundations came out of Blender in scattered order, so each group of 64 spanned a median 433 m and every
query met nearly all of them: by the east wooden ramps a simulation step took up to 186 ms, and the ride stuttered while
walking stayed smooth. Each collision mesh is now stored along a Z-order curve of its faces' centres, the faces over
8 m across in groups of their own: a group spans a median 9-16 m (52 m on the hillside's large faces).

## Clean geometry

r4 hid its geometry's faults instead of removing them. It dropped faces lying on an earlier mesh, pushed partial
overlaps back 5 mm, merged flat faces into fans of needles, and drew the foundations' prism walls and bottoms buried in
the block. [`craterpark/cleanbuild.py`](../world/regions/craterpark/cleanbuild.py) cleans build.py's pieces once,
after the additions, for both the render and the collision:

- **Seen faces only** ([`visibility.py`](../world/regions/craterpark/visibility.py), `clean.reachable`). The open space
  connected to the outside is flood-filled on a 0.5 m grid. A face is drawn if a ray from it escapes the park, or runs
  freely through that space. Up to 16 sample points per face, 8 cosine-weighted rays each, cover tunnels, spans and
  pockets.
  - Two exact tests run before any ray: a foundation face within 5 cm of a riding surface, and a wall two prisms
    share (a face lying wholly on one turned the other way).
  - A riding top (normal y over 0.2) is never dropped on failed rays alone.
- **No face on another** (`clean.overlap_pairs`, `clean.subtract`). Faces within 1 cm of each other and parallel within
  2 degrees are found through a plane index. The lower-ranked face (rank as `ROLES`, then the added pieces, the
  coping last) has the higher one's outline cut out of it exactly, in its own plane. Nothing is pushed back.
- **Conforming seams** (`clean.fix_tjunctions`). A vertex lying inside another face's edge, of its own mesh or of any
  other, splits that face. Its UVs are interpolated along the split edge.
- **Remeshed with bounds** ([`remesh.py`](../world/regions/craterpark/remesh.py)).
  - Each mesh is cut into patches: the added pieces' tops as height fields over the ground, the rest as planar
    patches (within 0.5 degrees and 1 mm).
  - The chains between patches are simplified once, within 1.5 mm (and 0.02 of the occlusion). Both sides share them.
  - Each patch is re-triangulated by constrained Delaunay and refined from its own vertices until every original
    vertex lies within 3 mm of it, within 0.02 of its occlusion, and within 0.002 of its UVs.
  - A patch that cannot be certified keeps its faces, and its neighbours are redone against its full outline.
- **The occlusion** is baked as before (same rays, reach and smoothing) on the fine faces, before the remesh.
- **An old mesh an added piece was laid through** (`CUT_UNDER`; the planter under the plaza kicker) loses its parts
  over the piece's top, cut exactly. The list is explicit: a floor that a piece runs under, as the pool landing's
  run-out does, is ridden and stays.
- **The ramps and snake runs are swept**, not gridded (`additions.run_mesh`):
  - A cross-section every 25 cm along the eased centreline, each vertex on its exact distance from the centreline.
  - The floor's edges, the arcs' tops, the lips and the outline are true lines. A 25 cm grid gave them a staircase,
    and its smoothing left teeth on the side walls.
  - The side walls are textured by distance along their top.

Each piece's remesh is cached under its inputs' hash, in `build/yorimichi/craterpark/clean-cache`.

## Riding

Faces of two meshes lying partly on each other (a foundation's wall behind a ramp's side, the hillside against a
block's wall) were drawn at the same depth and flickered, worst far away, where the depth buffer resolves about 15 µm
at 250 m. Each such face of the later mesh in role order (riding pieces, built walls and blocks, added pieces,
hillside) moves 5 mm back along its normal in the render; its corners stay shared, so nothing cracks. The collision
keeps them where they are.

Faces are ranked per piece of their mesh, not per mesh: a source mesh is often many pieces laid over each other. The
crater's perimeter is 724 boxes, each 2.2 m long, set every 2 m, so their faces met in 20 cm coplanar strips every 2 m;
the foundations carry about 70,000 m² of walls duplicated within one mesh. A face lying wholly on an earlier piece of its
own mesh is left out, and where two pieces overlap in part, every other piece moves back 5 mm.

[`craterpark/grind.py`](../world/regions/craterpark/grind.py) finds the grind lines along the lips already in the
park, on the collision the board rides: the edge of a level deck where the ground falls away, with nothing over it,
as the runtime's grind probes accept (the deck within 4 cm on one side 9 cm out, nothing at deck height on the
other). A stair's nosing, a path's edge over the hillside and anything under a roof are left out. `park.json` lists
them as `rails` and sets `rails_required`.

The foundation blocks were made solid up to the top of the pieces over them, so they filled the round tunnel: the
rider met its flat end. [`craterpark/tunnel.py`](../world/regions/craterpark/tunnel.py) finds the pieces that close
round an open bore (a riding face over and under a point, and round it on most sides, within 12 m) and cuts every
block face that reaches into one out of the render and the collision. A bore is straight: it is taken as a convex
prism, the hull of its grid's nodes across its axis extruded along it, carried on to each mouth while the bores'
pieces together still roof it (near the portal one piece is the roof, another a wall). A face inside is left out; a
face crossing the prism's side is clipped exactly against it and its parts outside kept, so a block's wall keeps its
solid round the portal and a long face crossing the bore keeps its ends. Parts one bore leaves are clipped by the
next. The real tunnel: 123k parts in about 20 s, no face left inside. The added pieces are cut the same way (a cap's
wall once stood across the tunnel).

[`craterpark/additions.py`](../world/regions/craterpark/additions.py) adds riding pieces, shaped on the park's own
surfaces; none moves, cuts or covers what is ridden:

- **East bowls.** The slots in the bowls' floor fell 20-31 m to the hillside. They are filled flush with the floor,
  so at the foot of a riding deck at least 2 m across, 0.9-5 m over the floor, one transition of 2.5-3.5 m radius runs
  from the floor up to the deck's edge, over the filled slot, with no gutter at its foot. A rail, a ledge or a wall stub
  gets none, and a transition passing one eases down to the floor 0.3 m from it. Under each access bridge the floor
  meets the bridge's top. The curves are seamless concrete (`material_010`); where they flatten onto the floor, within
  2 cm of its level, they take the bowls' own dark floor (`material_004`), so the concrete ends along a smooth contour.
- **Pockets.** The plaza's stage pit and the holes in its terrace row are dishes 1.5 m deep, flush with the plaza round
  them, their sides a sine curve of at most 1.75 m and a flat bottom when wider. A hole whose rim stands 25 cm over the
  plaza round it is a planter: it gets a flat bed 45 cm under its cap, not a dish curving up inside the box.
- **Banks.** A smooth surface spans the hillside between pieces, flush with them, meeting a piece at its lip: the true
  top of its coping, which can lie up to 0.6 m over the grid's nodes on a quarter pipe's steep face. A bank meets only
  the pieces named for it, by box and height; it passes the others by. The hip from the tower channel's coping (16.3 m)
  down to the plaza terrace is a landing transition: steep off the coping (about 30 degrees), easing out flat at its
  foot. The run from the south-west bowl's rim deck (11 m) meets the banked curve's outer lip (10.4 m), where the
  rider drops in. At the curve's far end, where it rose into a quarter 2.5 m short of the peanut bowl's rim and
  stopped, a deck across makes a spine over into the bowl.
- **Kicker.** A short arc from the plaza terrace up onto its parapet, at the hip's foot.
- **Street.** The central street between the two walkway strips was hillside, level with them, as is the ground on
  to the half-pipe's open north side. It is paved flush with the strips (herringbone, `material_012`), 5 cm over the hillside at least; a higher deck beside it keeps its wall,
  and where the hill rises more than 30 cm through it, the paving stops at the hill.
- **Snake runs.** A run along a centreline: a floor 6 m wide on the path it is laid over (flush with it), or on a
  smooth profile through given heights; a 2.5 m wall of 3.5 m radius each side to carve and pump between; open ends cut
  square. The narrow path from the banked curve's foot to the blue pool is one, carried over the gap to the pool's
  coping; another joins the pool's north coping to the 12 m half-pipe's floor. The hillside under a run is cut 30 cm
  below it.
- **Ramps and gaps.** A ramp follows a straight centreline, its profile drawn from arcs and lines (a crest, a kicker's
  transition up to its lip, a landing's knuckle and run-out) so each angle holds where it is meant to. A gap is a
  kicker and a landing on one line. Every gap was first ridden by the game's own rider offline
  (`Tests/build_simulation_session_cli.py`, `tools/check_skate_feel.py`'s session) across the speeds its line gives,
  and shaped until each landed clean: the blue pool gap off the south-west bowl's rim deck (a 50 m bridge over the
  dumbbell's disk, a 15-degree lip at -2.5 m, a 35 m, 2.2 s air into the pool); the plaza's gap south-east over the
  city into the 12 m half-pipe (a 4.5 m step-up bleeds the hip's speed, clean from 14 to 26 m/s). A steep lip throws
  the rider at the same angle into a landing too short to match it, so lips are 15 degrees and landings long and steep;
  a crest is at least 10 m in radius, or the rider leaves it. The pool's 3 m wall is vertical at its top and the rider
  bailed there from 22 m/s, so a bank carries the gap's run-out over it up 22.5 m to the south-east run's deck. The
  half-pipe's east wall is carried up 11 m to the black bowls' pocket as a roll-in (a 75-degree coping threw the
  rider off; a 14 m crest takes the rider from a standstill to 16.5 m/s on the floor), and a ramp lies over the half-pipe's
  stepped neck down to the peanut bowl. A ramp's flanks slope at 30 degrees down to the ground within 4 m (a hip to
  ride over where it meets a street, not a wall), and where its wall would stand on a riding face 3 m or more under
  it, the wall stops 60 cm down: a span, the run under it left open.
- **Pump track.** The valley's floor, where the rider stopped, runs south through the city's dirt to its paved street
  between transition walls, over 1 m rollers every 8 m.
- **Steel coping.** A 7 cm steel tube is drawn along every grind line, its top 12 mm over the deck (render only; a
  metallic `Steel` parent in `import_craterpark.py`).
- **Solid edges.** A riding sheet's free edge that ends in the air, a knife edge (a half-pipe's flank, the back of its
  wall), gets a level cap 35 cm wide on the side away from the piece, a grindable lip, and a wall from it down to
  the ground, so the piece reads as solid concrete. A run of free edge shorter than 2 m (a stray scrap) gets none.
  An added piece's outline, a staircase of its 25 cm grid, is smoothed first, so its walls stand straight, not in
  slats.

The added pieces take the riding concrete's materials with world-planar UVs at the piece's own texture scale, and
rank after the bridges: where an added piece meets a bridge or a riding piece, theirs is drawn.

## Restyle

[`tools/craterpark_textures.py`](../tools/craterpark_textures.py) repaints the park's realistic textures in the
island's style, after the art-direction paintovers in `assets/craterpark/concepts/`: pale warm concrete, dark grey bowl
concrete, warm wooden ramps, terracotta tiles and a blue pool, in soft flat painterly strokes.

- **paint** makes one ledgered Sunburst edit of each original texture, keeping its layout on the park's UVs. The
  compact copies and their provenance are in `assets/craterpark/restyle/`.
- **paint** also makes the world textures for the materials whose meshes have no UVs: volcanic ground for the block's
  hillside (`material_024`) and cast concrete for the foundations and bridges (`023`, `025`, `026`). The edge guard
  (`027`) reuses the Mega Park's restyled rock.
- **finish** (offline) writes `build/yorimichi/craterpark/textures/` and `textures.json`. `textures` maps each original
  texture path to its restyled PNG. `world_aligned` maps a material to its PNG and a suggested tile size in metres
  for a world-aligned (triplanar) projection; that PNG carries the material's colour, so its Tint becomes white.
  The `world.craterpark_restyle` step runs it, and `import_craterpark.py` uses a `World` parent material for them.
- The palette means are **albedos**. The island's light and grade show a sunlit flat surface at about albedo^0.5 per
  channel (linear), measured on the review shots, which halves value contrast and saturation. So each mean is the
  paintover's colour taken back through that response: pale concrete (172, 162, 139), the plaza (166, 138, 108), the
  bowls (50, 54, 62), as dark as the original's. Taking the paintovers' screen colours as albedos made the park pale,
  pink and lavender.
- The paintings are smooth, so finish stretches each one's variation about its mean, up to 14% of its luminance (at
  most 2.5 times), so the concrete still reads as a material.
- The snake run's box tops (`material_003`, an irregular-stone texture) are finished from the masonite painting, as
  wooden decks like the paintovers'.

## Review

`tools/review_craterpark.py` is the park's tour for the owner's page after every build. It runs the editor game under
the render guard and takes its cameras from the build's own outputs, so the tour follows the layout:
- `aerial` and `aerial_plan` frame the whole block;
- `tower_<line>` looks from each roll-in crest down its line (park.json `lines`);
- `gap_<feature>` is a side view of every air, with the rider launched off the lip at the design speed (18.5 m/s)
  and caught near the apex (geometry-report `checks`, else the layout's gaps);
- `feature_<id>` frames every bowl, half bowl, elbow or quarter pipe, from its built faces or else the layout.

`--video` adds a chase flythrough of each line (`flythrough_<line>.mp4`, from `v2/lines/*.npz`). `--plan` prints the
shot list without a game. `--shots far` takes the r4 review's views of the volcano from far away (`rim`, `zeppelin`,
`city`, `hidamari`, `hidamari_east`, `belmonte`, `trail`), to check the park stays hidden. It writes the PNGs,
`tour.json` and `index.html` (a contact sheet) to `build/yorimichi/craterpark/review`. The game peaked at about 11.5
GiB in the r4 review: pass `--memory-gib 14` explicitly after coordinating the guarded turn.

```sh
nice -n 10 uv run python games/yorimichi/tools/review_craterpark.py --video --memory-gib 14
```

## Build and game

| Step | Does |
|---|---|
| `world.craterpark` | [`craterpark/build.py`](../world/regions/craterpark/build.py) (Blender) exports one render FBX per mesh and per added piece ("Riding"), without its `render_skip` faces, the foundation faces on a riding surface or the block's faces in the tunnel, with creases over 35° and the baked occlusion as vertex colour ("Shading"). Collision FBX are built per role, at most 200,000 triangles each, from the drawn faces, without the faces inside the solid; only the riding surfaces stay unsimplified. It writes `park.json`. |
| `unreal.craterpark` | [`import_craterpark.py`](../unreal/Scripts/import_craterpark.py) imports them into `/Game/CraterPark`, with their vertex colours. Each material is a texture times its base colour, or the colour alone, darkened by the baked occlusion, and is two-sided where the source says so. |
| `data.stage` | Copies `craterpark/park.json` to `Content/Data`. |

In the game, `JapanWorld` spawns the park with `ASuperUltraMegaPark::Spawn`, the Mega Park's actor. `park.json` names
its own `mesh_root`, its grind lines and `rails_required: true`. The collision is invisible and blocking, and counts as a skate
surface like the Mega Park's.

## Editor parks

The remake is designed in the owner's park editor; its `park.json` (`craterpark-editor/1`) is the build's source of
truth. One command takes a saved design to the game:

```sh
uv run python games/yorimichi/tools/ship_craterpark_editor.py --lines L1 --build
```

[`ship_craterpark_editor.py`](../tools/ship_craterpark_editor.py) freezes the editor folder (park.json, data/ and
pieces.js) as `ship/rev<N>`, never overwriting a frozen revision. If pieces.js changed, it vendors it as
[`editor/pieces.cjs`](../world/regions/craterpark/v2/editor/) and re-pins its hash in `pin.json`; commit both. It
checks that the bridge meshes the frozen park, then runs the guarded build with `ATELIER_CRATERPARK_EDITOR_PARK` and
`ATELIER_CRATERPARK_EDITOR_LINES`. Without `--build` it prints that command.

With `ATELIER_CRATERPARK_EDITOR_PARK` set, `world.craterpark_geometry` runs
[`editor_generate.py`](../world/regions/craterpark/v2/editor_generate.py) instead of the v4 generator. It meshes every piece
through the pinned pieces.js, exactly as the editor draws it. It keeps the chosen lines (by id; L1 is orange), the bowls
they land in and the decks they start from. The ground is the editor's cut terrain within 60 m of a kept piece. Each
line spawns at its roll-in. The rest of the chain (`world.craterpark`, `unreal.craterpark`, `data.stage`) is unchanged.
Editor parks have no supports yet, so their geometry is marked `editor_playtest` and skips the v4 acceptance checks.

## Tower

The v2 park starts every line from one tower on the high east rim. `park.json` lists one start per designed line under
`lines`: `{key, name, spawn: {location_cm, yaw_deg}, ground_error_m}`, island Unreal cm and yaw, facing down the line.
The build places each start on its checked ground ([`v2/spawns.py`](../world/regions/craterpark/v2/spawns.py)):
a downward ray from 2 m over it must meet collidable ground within 0.5 m, no steeper than 10°, on the tower deck, with
the yaw within 15° of the line's first segment. Otherwise the build fails, naming the line. The top-level `spawn` is
the first line's start.

In the game ([`CraterParkTower.cpp`](../unreal/Source/Yorimichi/CraterParkTower.cpp)) the menu has a **Crater Park
tower** button per line, and **F7** returns to the line chosen last (the first by default). The world map's
**Crater Park** stop is the first line's start too. Each puts the rider on foot, standing still, facing down the line,
after the same ground trace at runtime: with no ground within 50 cm of the start, it refuses with a message. A
`park.json` without `lines` (r4) falls back to its single marked drop-in, which is also where the map stop stays.

## Assist zones

The kickers that launch into a big gap's landing should send the rider forward even when the player rides with
**Vert assist** at 1 (which turns straight airs short of vertical back into the ramp). `park.json` lists them under
`assist_zones`: `[{id, center_cm: [x, y, z], half_extent_cm: [hx, hy, hz], yaw_deg, vert_assist_max}]`, boxes in island
Unreal cm turned `yaw_deg` about up (`id` and `yaw_deg` are optional). While the board or the rider is inside one, the
vert assist is at most `vert_assist_max`; an air launched inside one keeps that limit until it lands, so the whole jump
rides with it. `ASuperUltraMegaPark::Spawn` adds them to the Skate plugin's `USkateAssistSubsystem` (plugin README,
"Assist zones"); a park without the key changes nothing.

## Later

- A way up: a zeppelin stop or a trail over the crest.
- A ground material for the block that matches the volcano.
