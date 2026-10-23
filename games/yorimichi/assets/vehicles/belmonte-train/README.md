# Belmonte train — coach shells and furniture contract

Two coaches of the luxury train between Belmonte and Hidamari (provisional name): a restaurant coach and a
first-class coach with four private seated cabins. The shells are built by script in Blender; the furniture comes
from Tripo Studio and is fitted to [the dimension contract](planning/furniture-dimensions.json). Design history and
decisions: [the concept prompt](../../../docs/BELMONTE_TRAIN_PROMPT.md) and [the shell notes](../../../docs/BELMONTE_TRAIN_SHELL.md).

The train is assembled into the Belmonte–Hidamari service by the game build. This folder holds its committed
source assets; generated shells, fitted copies, assemblies and baked LODs stay under `build/yorimichi/`.

## Build

```sh
uv run atelier build yorimichi world.belmonte_train        # vehicle shells, collision, placements, fitted furniture
uv run atelier build yorimichi world.belmonte_train_plan   # dimensioned plans and section (SVG)
uv run atelier build yorimichi world.belmonte_train_review # control renders, under the render lock (a few minutes)
```

The train shells, furniture LOD bake, assembly and import are part of the normal game build; plan and review steps are explicit. Sources are in
[`world/train/`](../../../world/train/): `layout.py` holds every number (plain Python, tested by
`tests/test_belmonte_train_layout.py`), `build.py` makes the meshes, `textures.py` draws the detail maps with numpy,
`render.py` the control views, `plan.py` the plans, and `fit_furniture.py` fits a Tripo export to the contract.

[`furniture/`](furniture/) contains all 16 fitted Tripo Studio exports contributed in
[Polozer/atelier#1](https://github.com/Polozer/atelier/pull/1). [`source.toml`](source.toml) records their local paths,
SHA-256 checksums, fitting reports and project ownership (`licence = "own"`). The original exports were made in
Tripo Studio; provider model versions, prompts and job receipts were not supplied with this contribution.
The fitted GLB bytes are preserved. Source reports describe those sources only: dimensions and errors are aligned with
the current contract, the pot's triangle count includes its separate porridge mesh, and generated LOD records
have been removed.

`world.belmonte_train` verifies the complete inventory before copying the GLBs and reports into the build.
Missing, corrupt or invalid sources fail the build. There is no placeholder fallback or private download.
`world.belmonte_train_furniture_lods` is a required incremental Cycles bake. It produces budgeted meshes,
embedded textures and `furniture/lod/summary.json` without modifying fitted source reports. Assembly and service
require a complete, source-matched bake; missing, corrupt or over-budget outputs fail instead of falling back to
full fitted meshes. The assembly uses baked LOD0 too. Unchanged inputs reuse the verified bake.

`world.belmonte_train_furniture_review` produces optional comparison renders; it does not control whether
production furniture is optimized.

## Outputs (`build/yorimichi/belmonte-train/`)

| File | What |
| --- | --- |
| `<coach>/<coach>.blend` | collections `<Coach>_Shell`, `_Roof` (removable: hide it to look in), `_Glazing`, `_Doors`, `_Interior`, `_Reservations`, `_Collision`, `_LOD2` |
| `<coach>/SM_BT_<Coach>_LOD0.glb` | full shell; nodes grouped under `BT_<Coach>_Shell/Roof/Glazing/Doors/Interior` |
| `<coach>/SM_BT_<Coach>_LOD1.glb` | no lining panels, trims, ribs, roof details or steps |
| `<coach>/SM_BT_<Coach>_LOD2.glb` | closed hull with dark window quads, for distance |
| `<coach>/SM_BT_<Coach>_Collision.glb` | `UCX_SM_BT_<Coach>_NN` boxes: floor, walls broken at every doorway, partitions, ceiling, fixed fittings |
| `<coach>/<coach>-blockout.glb` | furniture reservations `FURN_<id>` (origin and yaw of each placement), `RES_` fixed fittings, `SEAT_` and `MOUNT_` markers |
| `<coach>/<coach>-placements.json` | rooms, walls, openings, windows, doors with pivots and motion, placements, seats, mounts, reservations, collision boxes |
| `plan/*.svg`, `review/*.png` | dimensioned plans and control renders |
| `furniture/<asset>.glb/.json` | verified fitted Tripo furniture and source reports, copied from this folder's `furniture/` |
| `manifest.json` | sizes, SHA-256, triangle counts, mesh and layout checks |

Coach frame (metres): x along the coach, end A at −X, end B (bar and galley) at +X; +Y is the compartment and galley
side; z = 0 on the top of the rail, origin at the coach's centre. Placements convert to Unreal only through
`atelier.conventions.to_unreal` (`unreal = (x, −y, z) × 100`, `yaw_unreal = −yaw`). The GLBs are standard glTF
(Y-up) from Blender's exporter; do not add another rotation.

Coupling: every coach shares `layout.coupling()` (buffers, draw hook, gangway, floor); the GLBs carry
`SOCKET_Coupler_A/B` and `SOCKET_Gangway_A/B`, and coupled coaches sit 24.00 m apart, origin to origin.

## Assembling the Studio furniture on the shells

1. Export each Tripo Studio model (FBX or GLB) and fit it:
   `uv run python games/yorimichi/world/train/fit_furniture.py first-class-table model.fbx --column .15 .85`.
   It scales uniformly to the contract width, sets the pivot, and with `--column` lengthens only the legs or
   pedestal to the contract height. It stops if a dimension misses by more than 2 cm: then fix the model or revise
   the contract, never stretch the whole object on one axis.
2. Inspect the fitted GLB and report under `build/yorimichi/belmonte-train/furniture/`. Copy the accepted pair
   into this folder's `furniture/`, remove any generated `lods` record from the source report, and update both
   checksums in `source.toml` and the GLB size/checksum in `assets/source-library.json`. Keep the report's dimensions, pivot and triangle count consistent with the GLB
   and contract. Run `uv run pytest games/yorimichi/tests/test_belmonte_train_furniture.py games/yorimichi/tests/test_asset_library.py -q` before committing.
3. Each fitted asset faces −Y with its width on X. Place one instance per `placements` entry with that asset id:
   location `x, y, z`, rotation `yaw` degrees about +Z. Table lamps sit on their table (z is the table top); sconces'
   origin is the wall mount point, back against the panelling.
4. `SEAT_` markers give the sitting point (seat height 0.46 m) and the way the passenger faces, for sitting animations.
5. `MOUNT_` markers carry curtain rails (top of each clear window, `length_m`), luggage racks and sconce points.
6. Collision: shells use the collision GLB; each piece of furniture brings its own simple box. Doors are separate
   nodes with their pivot at the origin: sliding leaves move by `open_offset_m`, hinged leaves turn by `swing_deg`.

The six reservations already match the first fitted object: the golden table from Tripo Studio fits as
`first-class-table` (0.65 × 0.397 × 0.62 m).

## Livery textures

`textures/` holds the exterior swatches the build maps onto every vehicle. The user generated them in ChatGPT on
13 October 2026 from the prompts in the train session, and `world/train/prepare_livery.py` prepared them so they tile:
- `livery-blue-panel.jpg`: one lined panel of the blue lower body, mapped once per panel between the doors and the crest;
- `livery-ivory.jpg`: the upper-body enamel;
- `roof-canvas.jpg`: the canvas roof, its seams running across the coach;
- `underframe.jpg`: the riveted black steel of the bogies, frames and headstocks.

`backhead.jpg` is not mapped. It was the Tripo Studio input for the 3D pipework of the locomotive's backhead (the
`loco-backhead` furniture asset). `smokebox-door.jpg` is mapped on the round smokebox door.

The worn second class weathers these same images (`textures.weather`), so it keeps the train's livery.
