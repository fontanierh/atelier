# Crater Park

Crater Park is a skate park on the volcano's caldera floor ([VOLCANO.md](VOLCANO.md)). Its author made it and gave it
to Yorimichi from [fontanierh/crater-skate-park](https://github.com/fontanierh/crater-skate-park). It is a 337.9 ×
384.5 m block of hillside with concrete runs, bowls, wooden ramps, plazas and paths. It has no trees, props or grind
paths yet.

## Source

`assets/craterpark/` holds everything from the repository's `readable/mountain/`, converted once by
[`craterpark/extract.py`](../world/regions/craterpark/extract.py):

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
about 26 stands of 16-35 trees (the Mega Park's detailed pines, cedars, maples and ginkgos), on the floor and the wall's
lower slope; about 50 groups of two to five grey boulders 9-16 m across (`SW_Boulder_*`, which take no snow) with scree on bare ground; and
ochre shrubs. About 8,700 autumn thicket plants clump along the crest, on rock as steep as 55 degrees and more thinly on
snow (red shrub maples, golden ginkgo shrubs and ochre bushes), and ochre bushes ring the park's block 9-40 m out, snow
or not. Some 900 small stones, 1-3 m, lie in clusters over the floor's snow. Nothing stands within 7 m of the park's block. The
caldera is a `near_trees` box, so its trees cast shadows and keep trunk collision.

The volcano's own snow (`hidamari/mountains.py` `snow_cover`) leaves the caldera floor mostly white with dark cinder
patches. On the outer flank it lies in snowfields between bare rock ribs for about 110 m below the crest, and lower
down only in thin couloirs, so the far views read rock with a few streaks. The
mountain material shades the exposed rock in faceted planes about 22 m across (5 m cells read as cobbles), each tilted at random against the sun,
warm where lit and cool where turned away, so the walls read as granite rather than clay; olive moss lies on its
gentler upward faces.

## Snow

The block's hillside (`material_024`) carries snow where it faces up, in broad world-space patches with crisp edges
(`import_craterpark.py` `SNOWY`); between them the volcanic ground shows. A soft edge left a third of the snow
part-covered, with the dark ground smeared through it in diagonal streaks. The skating surfaces, the edge guard and its
coping, foundations and bridges stay clear. The park's materials are matte, like the terrain's.

## Shading

The park has no lightmap to take occlusion from, as the Mega Park does, so `craterpark/build.py` bakes it: the drawn
triangles fill a 0.5 m voxel grid, and from every drawn vertex 16 cosine-weighted rays march out to 12 m. The result
(1 open, 0 closed) is the vertex colour, sRGB-encoded. The parent materials take `Occlusion` (0.6) of it from the sky's
fill and `Cavity` (0.3) from the albedo, so bowl floors, wall feet and the gaps between boxes darken and the blue
sky fill no longer lights every face evenly. It costs 4 bytes per drawn vertex: about 0.43 million vertices, 2-3 MB
of GPU memory with Unreal's vertex splits.

Foundation faces that lie on a drawn riding surface (within 5 cm, facing the same way; the foundations sit up to 3 cm
off the surfaces) are left out of the render, so they no longer flicker through it; the collision keeps every face.

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

## Build and game

| Step | Does |
|---|---|
| `world.craterpark` | [`craterpark/build.py`](../world/regions/craterpark/build.py) (Blender) exports one render FBX per mesh, without its `render_skip` faces or the foundation faces on a riding surface, with creases over 35° and the baked occlusion as vertex colour ("Shading"). Collision FBX are built per role, at most 200,000 triangles each, with every face. It writes `park.json`. |
| `unreal.craterpark` | [`import_craterpark.py`](../unreal/Scripts/import_craterpark.py) imports them into `/Game/CraterPark`, with their vertex colours. Each material is a texture times its base colour, or the colour alone, darkened by the baked occlusion, and is two-sided where the source says so. |
| `data.stage` | Copies `craterpark/park.json` to `Content/Data`. |

In the game, `JapanWorld` spawns the park with `ASuperUltraMegaPark::Spawn`, the Mega Park's actor. `park.json` names
its own `mesh_root` and sets `rails_required: false`. The collision is invisible and blocking, and counts as a skate
surface like the Mega Park's. The world map has a **Crater Park** travel point at the marked drop-in.

## Later

- Grind paths: the source has none.
- A way up: a zeppelin stop or a trail over the crest.
- A ground material for the block that matches the volcano.
