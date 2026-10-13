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
- They rise by `LIFT` (518 m), so the block's low east edge meets the 485 m caldera floor.

The block's high side faces the tallest part of the crest. It keeps at least 60 m to the wall's foot, and its top
stays more than 120 m under the lowest crest.

## Ground

The block's sides go down to 110 m below its top, so the caldera floor is shaped to bury them
(`placement.terrain`, chained into `hidamari/mountains.py` `raw_height`):

- **Under the block:** the ground sinks `SINK` (2 m) below the block's lowest top within `REACH` (15 m). No terrain
  triangle pokes through.
- **Round it:** the floor is offset to the block's top edge, less 0.3 m. It eases back over a skirt 30–120 m wide,
  which widens with the height it makes up (up to about 57 m on the high side).

Trees and rocks already stay out of the caldera (`hidamari/layout.py`).

## Build and game

| Step | Does |
|---|---|
| `world.craterpark` | [`craterpark/build.py`](../world/regions/craterpark/build.py) (Blender) exports one render FBX per mesh, without its `render_skip` faces and with creases over 35°. Collision FBX are built per role, at most 200,000 triangles each, with every face. It writes `park.json`. |
| `unreal.craterpark` | [`import_craterpark.py`](../unreal/Scripts/import_craterpark.py) imports them into `/Game/CraterPark`. Each material is a texture times its base colour, or the colour alone, and is two-sided where the source says so. |
| `data.stage` | Copies `craterpark/park.json` to `Content/Data`. |

In the game, `JapanWorld` spawns the park with `ASuperUltraMegaPark::Spawn`, the Mega Park's actor. `park.json` names
its own `mesh_root` and sets `rails_required: false`. The collision is invisible and blocking, and counts as a skate
surface like the Mega Park's. The world map has a **Crater Park** travel point at the marked drop-in.

## Later

- Grind paths: the source has none.
- A way up: a zeppelin stop or a trail over the crest.
- A ground material for the block that matches the volcano.
