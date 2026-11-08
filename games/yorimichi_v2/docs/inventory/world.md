# Yorimichi V2 inventory: the world (W00–W20)

Source: `the baseline checkout` (baseline 7eec0f98dd). Paths below are relative to
`games/yorimichi/` unless they start with `platform/` or `docs/`. Everything here was read only; no builds were run.
Instance counts come from an existing build output, `~/dev/atelier-sk2-bv1/build/yorimichi/world.json`
(written 2026-10-30 at revision 7ca4d926d4, **not** the baseline). Treat them as approximate scale only and
recount them at the donor revision.

## 0. The main finding: almost the whole island is created at runtime

- `unreal/Content/` is git-ignored (root `.gitignore:26`), so the repo contains no `/Game` package. Every package
  is produced by a build step.
- The saved map `/Game/Japan/Maps/Slice` (`unreal/Config/DefaultEngine.ini:2-3`) holds only:
  - the island terrain children as `StaticMeshActor`s, labelled `Island:<parent>:<name>` with tag
    `IslandSurface:<parent>`: 36 `Terrain_cell_*`, 247 `FarHills_cell_*`, `Road`, `Lane`, `Guardrail` and
    `Wires`. Sea is excluded;
  - the sun, sky light, height fog, an unbound PostProcessVolume and the PlayerStart.

  Writer: `unreal/Scripts/setup_project.py:113-178` (`build_level`), called by
  `unreal/Scripts/import_island_world.py:67` in step `unreal.island`.
- Everything else is spawned on every `BeginPlay`:
  - `AJapanGameMode::BeginPlay` (`unreal/Source/Yorimichi/JapanGameMode.cpp:57`) spawns `AJapanWorld` at the
    origin.
  - `AJapanWorld::Load` (`unreal/Source/Yorimichi/JapanWorld.cpp:77`) reads `Content/Data/world.json`
    (`JapanWorld.cpp:81`) plus about 20 region data files. It builds one `UHierarchicalInstancedStaticMeshComponent`
    per mesh key under `instances` (`JapanWorld.cpp:423-623`; HISM creation at `:519`, shadow twins at `:602`).
    It also creates the sky dome (`:665`), the sea pieces (`:675-689`), lights and post-process volumes for
    Hidamari, the treehouse and the caldera (`:140-320`, `:694-808`), and the region actors and services
    (`:809-881`).
- Runtime edits that a saved-actor migration must bake in or keep, or the scene will differ:
  - removal of the old Tree instances inside Hidamari's box (`JapanWorld.cpp:113-127`);
  - the vegetation clearance for the skate park, hippodrome and stable (`:360-369`, `:505`);
  - region `Clear` calls for Belmonte, Brinecove and the gondola (`:383-385`);
  - the backdrop-tree ground trace that deletes floating trees (`:885-908`);
  - the Ronin camp, which removes every instance within 15.5 m of (-54, -94) (`SwordTrainer.cpp:427-460`);
  - the grindable guardrail rails from `rail_runs` (`:909-922`);
  - `JapanGameplayCollision::Install` (`:936`). Its `IsFixed` (`JapanGameplayCollision.cpp:18-26`) accepts
    `AJapanWorld`, `ASkatePark`, `AMegaRamp`, `ASuperUltraMegaPark`, `AHippodrome`, `AHidamariStable` or any
    *static* `AStaticMeshActor`. Saved ISM or foliage actors of another class would need that rule extended.
- Two saved maps besides Slice: `/Game/MegaPark/Maps/SuperUltraMegaPark` (`unreal/Scripts/import_megapark.py:356-395`,
  a standalone parity level) and a Crater Park scratch level (`import_craterpark.py:180`, not saved as a game map).
- Scale in the reference build:
  - `world.json` has 78 instance keys and 198,539 instances (`Tree_Maple_A` 49,282, `Grass_A`/`Grass_B` about 32k
    each, `Litter` 19,780, `Tree_Pine_B` 15,177, `Tree_Ginkgo` 14,803, `Tree_Broad_A` 13,238, …). About 40 keys
    are single "parent" placements `[0,0,0,0,1]` that expand into region pieces.
  - `hidamari/city.json` adds 145 keys and 191,098 instances.
  - In total about 390k runtime instances before the clearances.

**Consequence for P3/P5:** the plan's step "migrate placements once, then disable the spawner" applies to
`AJapanWorld` (instances, sky, sea), `ASkatePark`, `AMegaRamp`, `ASuperUltraMegaPark` (both parks),
`AHippodrome`, `AHidamariStable`, `ABelmonteRegion` (Belmonte and Brinecove), `ABelmonteTrack`, and the static
parts of `AFerryService`, `AGondolaService` and the zeppelin stations. These need per-key or per-region switches;
today there is one monolithic `Load()`.

## 1. Coordinates, units and origin

| What | Rule | Where |
| --- | --- | --- |
| Source frame | Blender metres; X east, Y north, Z up | `unreal/Source/Yorimichi/JapanWorld.h:44-45` |
| Position to UE | `FVector(X*100, -Y*100, Z*100)`: cm, Y flipped | `JapanWorld.h:52` (`AJapanWorld::ToUE`) |
| Instance row | `[x, y, z, yaw_deg, uniform_scale]`; UE rotation `FRotator(0, -yaw, 0)`, scale `FVector(s)` | `JapanWorld.cpp:498-516` |
| Player start | `[x, y, z, yaw]`; map actor at `(x*100, -y*100, z*100+100)`, yaw `-ps[3]`; runtime copy without the +100 | `setup_project.py:173-175`, `JapanWorld.cpp:345-346` |
| Fixed views | `shots` `[x, y, z, yaw, pitch]` gives `FRotator(pitch, -yaw, 0)` (39 views) | `JapanWorld.cpp:348-355` |
| Origin | Island origin `[0,0,0]`; every terrain child is placed at (0,0,0) with world-space vertices | `import_island_world.py:43`, `setup_project.py:124` |
| Mesh export | Blender FBX `axis_forward='-Y', axis_up='Z', apply_unit_scale, FBX_SCALE_ALL`; UE import `convert_scene=True, convert_scene_unit=True, import_uniform_scale=1.0` | `world/asset_mesh.py:249-250`, `world/plan_terrain.py:13`, `unreal/Scripts/mesh_import.py:64,98` |
| Heightfield | `size` 600 m, `n` 301 (2 m spacing), `heightmap.bin` little-endian float32, row J = +Y north; used only for cosmetic particles (+6 cm) | `world/gen_world.py:371-372`, `JapanWorld.cpp:327-341`, `:972-987` |
| Terrain grid | `Terrain_cell_i_j` = 128 m cells over x,y ∈ [-300, 300]; FarHills 247 cells to ±3200 m; Sea is one 8-triangle quad ±24 km | `terrain/island.json` (build), `terrain_atomic_build.py:14` |
| Skate park | Park-local metres with origin on the deck top; world = origin (-110, -234, 1.8) + local; UE yaw = -yaw_deg | `world/regions/skatepark/park.json` doc field, `world/regions/skatepark/pier_site.py:3-4` |
| **Exception:** Mega Park source | Native Y-up: `(x, y, z)` m → `(100x, 100z, 100y)` cm, then `placement.py` CENTRE (-150, 1300), YAW -60, BASE 49.3 | `unreal/Scripts/import_megapark.py:39-40`, `assets/megapark/provenance.json`, `world/regions/megapark/placement.py:18-21` |
| Gondola/ferry data | Already in UE cm (`location_cm`, `walk_cm`) | `GondolaService.cpp:169-180` |

`edit_bounds` tuples are **not uniform**. Mega is `(xmin, ymin, xmax, ymax)` `(20, 220, 150, 292)`
(`regions/mega/layout.py:8`). Southwest is `(-300, -200, -190, -90)` (`regions/southwest/layout.py:25`). Village is
`(40, 185, -40, 190)` (`regions/village/layout.py:11`), which reads as `(xmin, xmax, ymin, ymax)`. P0/P1 must
normalize these into explicit region records.

## 2. Writers of the root world.json, folder-wide deletes and recreate paths

The plan forbids these as routine paths.

**world.json writers**
- `world/gen_world.py:377-378` is the only normal writer, run by step `world.layout` (`build.py:1070-1083`,
  `cutoff=True`). It rewrites the whole file and also writes `heightmap.npy`, `heightmap.bin` and `farhills.npy`
  (`:314`, `:371-372`). Every region's `integrate()` mutates the one `world` dict inside this process
  (`gen_world.py:343-375`: village, mega, southwest, forest_lake, zeppelin, treehouse, megapark trail, train
  corridor, coastal dressing).
- `world/regions/zeppelin/layout.py:133-141` and `world/regions/forest_lake/layout.py:52-61` (`__main__`) rewrite
  `build/yorimichi/world.json`, `heightmap.npy` and `heightmap.bin` in place from a one-time backup. This is a
  manual standalone path.
- `runtime_data.py:23,55-70` (`data.stage`, `build.py:1824`) copies `world.json` and `heightmap.bin` into
  `unreal/Content/Data/`. This is a staging copy, not a rewrite.
- Not world data: the racing save at `Saved/racing/world.json` (`RacingService.cpp:402`), which P5 must not
  delete.

**Folder-wide delete-and-recreate (`delete_directory` then `make_directory`)**
- `unreal/Scripts/import_belmonte_track.py:131-133` deletes `/Game/BelmonteTrack`; `:180` deletes its `/Source`.
- `unreal/Scripts/import_belmonte_train.py:165-167` deletes `/Game/BelmonteTrain`; `:215` deletes its
  `Source/<leaf>`.
- `unreal/Scripts/import_horses.py:425-427` deletes `/Game/Horses`.
- `unreal/Scripts/import_adventure.py:261-263` deletes `/Game/Adventure`.
- `unreal/Scripts/import_adventure_moveset.py:332-334` deletes the move-set destination.
- `unreal/Scripts/import_city_tree_lods.py:32-33` deletes `/Game/Experiments/CityTrees/<tag>`.
- `import_belmonte.py:344` and `import_brinecove.py:423` delete their temporary `/Import` folders, which is
  benign scratch.

**Map recreate**
- `setup_project.py:116` + `:176` create a `new_blank_map` and save it over `/Game/Japan/Maps/Slice` on every
  `unreal.island` run. The whole persistent map is regenerated, so it cannot hold editor-owned actors.
- `import_megapark.py:356` + `:395` do the same for the Mega Park level.

**Purge and archive**
- `setup_project.py:59-73` `purge()` deletes all of `/Game/Japan` except independent owners. It is defined but
  not called by `main()` (`:180-228`); `city_parent_transition.py:143` still references it in an AST check.
  Remove it in V2.
- `content_policy.py:105-120` (`data.content`, `build.py:2065`) moves every Content/Data root not in
  `ASSET_ROOTS`/`DATA_ROOTS` (`:28-38`) into an archive before cook. This is a folder-level move that already
  lost `/Game/SwordCamp` once.
- Targeted retirement deletes: `import_island_atomic.py:107-137`, `import_village_atomic.py` (about line 110),
  `import_hippodrome.py:174`, `import_belmonte.py:273,291`, `import_brinecove.py:380`, `import_foliage.py:140`,
  `import_music.py:74`, `import_combat_audio.py:22`. These are owned-package retirements, not folder wipes.

**Replace-on-import:** almost every importer sets `replace_existing=True, save=True`, for example
`setup_project.py:33`, `mesh_import.py:84` and `import_skatepark.py:122`. Combined with the steps' reruns, this
resaves packages whether or not they changed, against the plan's no-op rule.

**Startup reimports:** none found. No `StartupScripts` or auto-reimport setting in `unreal/Config/*.ini`. The
"startup" cost is the runtime spawn in §0.

## 3. Region rows

Columns used per row: **Src** (region code, generators, committed assets), **Steps** (build steps), **/Game**
(Unreal packages), **Runtime** (how the content reaches the running game), **Bounds** (bounds and neighbours),
**Dyn** (dynamic services), **Checks** (A = automated assertion, V = visual review, P = performance
measurement), **Scale**.

### W00 Island foundation (terrain, coast, sea, background, roads, surface queries, boundaries)
- **Src.**
  - `world/gen_world.py` with `build_terrain.py`, `plan_terrain.py`, `terrain_sources.py`, `terrain_product.py`,
    `terrain_query.py`, `shorelines.py`, `coastal_surface.py`, `coast_water.py`, `farhills_grid.py`,
    `farhills_surface.py`, `far_crown.py`, `skydome_source.py` and `walk_raster.py`.
  - Assets: `assets/environment/textures/*.jpg` (7.7 MB, generated, with provenance),
    `assets/shorelines/concepts` (3.7 MB), `assets/props/skydome/provenance.json`.
- **Steps.** `world.layout`; `world.island.sources`, `world.terrain`, `world.terrain.meshes` and
  `world.island.receiving` (`terrain_atomic_build.py`); `world.farhills` (`build.py:1093`); `world.textures`;
  `unreal.materials` (`foliage_build.py:101`); `unreal.island` (`build.py:1529`); `world.map` (`build.py:1318`);
  `data.stage`.
- **/Game.**
  - `/Game/Experiments/IslandTerrain/v1_atomic/{Terrain_cell_*, FarHills_cell_*, Road, Lane, Guardrail, Wires, Sea}`
  - `/Game/Japan/Materials/{M_ForestGround, MI_FarForest, MI_Coast, M_CoastRock, MI_CoastRock, MI_Sand, M_Sea}`
    and `/Game/Japan/Textures/T_CoastRock` (`island_native_policy.py:2-4`)
  - the shared `/Game/Japan/Materials/MI_*`, `M_Painterly`, `M_CloudShadow` and `MPC_Wind` (`world/asset_catalog.py:100-108`)
  - `/Game/Japan/Maps/Slice`
- **Runtime.**
  - Terrain, road, guardrail and wires are **saved actors** in Slice (`setup_project.py:118-130`).
  - Sea is runtime-spawned, non-blocking and shadowless (`JapanWorld.cpp:675-689`).
  - The sky dome is runtime-spawned at a 20 km scale (`:665-673`).
  - Grind rails from `world.json:rail_runs` (`:909-922`); the heightfield is particle-only (`:327-341`).
  - Gameplay ground is collision, plus `JapanGameplayCollision` (`:936`).
- **Bounds.** Playable square ±300 m (`size` 600); FarHills to ±3.2 km; Sea ±24 km. Hidamari city terrain
  (`terrain/HD_Terrain`, x 300–2200) and `HD_NorthMountains` belong to W07/W12.
- **Dyn.** Wind (`JapanWorld.h:83-86`), GullFlock (`JapanWorld.cpp:932`), LeafStorm (`:930`).
- **Checks.**
  - A: `tests/test_island_atomic_{native,products,sources,uvmap}.py`, `test_island_world_owner.py`,
    `test_terrain_query.py`, `test_terrain_inventory.py`, `test_sea_depth_seams.py`, `test_shorelines.py`,
    `test_coastal_surface.py`, `test_walk_raster.py`, C++ `IslandPiecesTests.cpp`, `JapanFixedCollisionTests.cpp`.
  - V: the 39 `shots`, `tools/capture.py`.
  - P: `tools/benchmark.py`.
- **Scale.** 36 + 247 + 4 terrain actors, 1 sea mesh, about 390k runtime instances overall.

### W01 Start/coastal road and `houses`
- **Src.**
  - `world/regions/houses/{layout, house_a/b/c, lots, lot_data, construction, geometry_mesh, catalogue}.py`.
    The meshes are procedural; `assets/houses` holds only concepts (908 KB).
  - `world/coastal_dressing.py`; props from `world/prop_sources.py` and `world/asset_catalog.py:10`
    (`Pole`, `Pole_Lamp`, `Guardrail`, `Lantern`, `Torii`, `Rock_*`, `Litter`).
- **Steps.** `world.houses.data.<key>`, `world.houses` (`houses_build.py`); `unreal.houses` (`build.py:1637`);
  `world.props.sources`, `world.props` (`props_atomic_build.py`); props are imported inside `unreal.world`
  (`setup_project.py:203-212`).
- **/Game.** `/Game/Japan/Assets/{House_A, House_B, House_C, HouseLot_1..5}` and
  `/Game/Japan/Assets/{Pole, Pole_Lamp, Lantern, Torii, Rock_*, Litter, Leaf}`.
- **Runtime.** The houses, lots and props are **runtime HISM instances** from `world.json:instances`. Road,
  guardrail and wires are W00 saved actors.
- **Bounds.**
  - Spawn `player_start` (-255.26, -99.51, 10.29, yaw -4.7).
  - Houses: House_A at (-195.7, -108.2) and (26.3, -55.6); House_B at (-155.2, -65.3); House_C at (-125.1, -57.4)
    and (47.8, -19.0).
  - The road is 624 points from (-295, -95) to (294.5, 59.7), 5.2 m wide.
  - It overlaps the Southwest `edit_bounds` (-300..-190, -200..-90): spawn and lane are inside the fishing
    village's box.
- **Dyn.** The fox hunter spawns 12 m ahead of PlayerStart (`JapanGameMode.cpp:25-40`). The Ronin camp sits at
  (-54, -94) beside the road bend (`SwordTrainer.cpp:427-440`, W13).
- **Checks.**
  - A: `test_houses_atomic_sources.py`, `test_house_lot_data.py`, `test_world_props_atomic.py`,
    `test_coastal_dressing.py`.
  - V: the start shots, the `ronin_camp_film` scenario.
- **Scale.** 5 house instances and 5 lots; Pole 14, Pole_Lamp 7, Lantern 17, Torii 6; about 10–12k vegetation
  instances per 128 m start cell.

### W02 `village` / Momiji Hamlet
- **Src.** `world/regions/village/{layout, atomic_sources, catalogue, decorations, logical, mesh}.py`,
  `assets/village` (84 KB).
- **Steps.** `world.village.sources`, `world.village`, `world.village.import` (`village_atomic_build.py`),
  `unreal.village` (`build.py:1547`).
- **/Game.** `/Game/Experiments/VillageAtomic/v1_atomic/*`, `/Game/Japan/Materials/{M_Village, M_VillageResident}`.
- **Runtime.** HISM: the `Village_*` parents expand through `village/atomic-manifest.json` (`JapanWorld.cpp:451-460`).
  Residents come from `AVillageLife` (`:813`). Kaede (sword trainer) comes from `ASwordTrainer::SpawnInVillage`
  (`JapanGameMode.cpp:63`, `SwordTrainer.cpp:126`).
- **Bounds.** Offset (0, 70, 9); edit_bounds (40, 185, -40, 190); 5 buildings, 3 residents. The road joins at
  `entrance_road_index` 395.
- **Dyn.** Villagers, Kaede's lawn and trainer bouts.
- **Checks.**
  - A: `test_village_atomic_{native,products,sources}.py`, `test_village_owner_integration.py`,
    `VillagePiecesTests.cpp`, `JapanEncounterTests.cpp`.
  - V: `trainer_film` scenario.
- **Scale.** 13 parent keys (`Village_*`), 1 instance each.

### W03 `mega` (mini Mega ramp)
- **Src.** `world/regions/mega/{layout, ramp, ride, trail_data, plan_asset}.py`.
- **Steps.** `world.mega.trail_data`, `world.mega` (`mega_build.py`); `unreal.mega` (`build.py:1596`).
- **/Game.** `/Game/Japan/Assets/{Mega_Ramp, Mega_Trim, Mega_Trail}`.
- **Runtime.** `AMegaRamp::Initialize` (`MegaRamp.cpp:6`), spawned at `JapanWorld.cpp:836` from `world.json:mega`.
  `Mega_Trail` is a HISM instance.
- **Bounds.** Origin (65, 242, 66.8); bounds x 20–150, y 220–292; the trail starts from the village path
  (`mega/layout.py:10-14`).
- **Checks.** A: `test_mega_atomic_data.py`, `test_mega_ramp_layers.py`. V/A: skate ramp routes.
- **Scale.** 3 meshes.

### W04 `skatepark` / Sunset Pier
- **Src.**
  - `world/regions/skatepark/{park.json (committed, 113 KB), layout, features, pieces, pier_site, modules, board, build, assemble_atomic, plan_atomic}.py`.
  - Assets: `assets/skatepark/modules/*.glb` (18 modules, 256 KB), `modules.json`, `textures/{ceramic, concrete, mural, steel, wood}.jpg` (2.4 MB) and `concepts` (1.7 MB).
- **Steps.** `world.skatepark_textures` (`build.py:1174`); `world.skatepark.material_geometry`,
  `world.skatepark.ao`, `world.skatepark.query_data`, `world.skatepark.roundtrip.<key>` and `world.skatepark`
  (`skatepark_atomic_build.py`); `unreal.skatepark` (`build.py:1720`); `unreal.skate_board`; `skate.runtime`,
  `unreal.skate_data`, `unreal.skate_clips`.
- **/Game.** `/Game/SkatePark/{SM_SkatePier, SM_SkatePierPilings, SM_SkateParkFeatures, SM_SkatePath, SM_SkateParkFurniture, SM_SkateParkPlanting, SM_SkateParkDecals}`.
  Each mesh is split into `_Piece<hash16>` pieces on a 128 m grid, at most 32,768 triangles each
  (`regions/skatepark/pieces.py:12-14`). Also `/Game/SkatePark/{Textures, Materials, Board}` and
  `/Game/SkateRuntime`.
- **Runtime.** **Runtime actor** `ASkatePark::Initialize` (`SkatePark.cpp:84`), spawned at `JapanWorld.cpp:842-846`
  from the staged `skatepark/park.json`. It adds 7 mesh components (`SkatePark.cpp:125-127`), park trees as
  HISMs (`:144-147`), the pier look box/post-process (`:101-106`) and rails. Vegetation clearance applies at
  `JapanWorld.cpp:361-362`, `:505`.
- **Bounds.**
  - Deck x -195..-25, y -300..-168 (half extents 85 × 66).
  - Path from the road edge at (-154.2, -86.8) to the deck entrance near (-104, -168). It crosses terrain cells
    -2_-1, -1_-1 and -1_-2.
- **Dyn.** Skating sessions and replay; spawns `park`, `bowl`, `mini` and `path_top`.
- **Checks.**
  - A: `test_skatepark_{atomic, import_pieces, modules, pieces}.py`, `test_park_line_validator.py`,
    `test_skate_simulation_*`.
  - V: `scenarios/skatepark.py`, `pier_part*.py`, `skate_ride*.py`, `skate_showreel.py`.
  - P: `skate_performance.py`.
- **Scale.** 7 parent meshes; 44 features; 70 rails; 10 park trees.

### W05 `forest`
- **Src.** `world/regions/forest/{ecotone, specs}.py`; `world/{build_forest, forest_source, forest_trees, forest_parameters, forest_impostors, bake_forest_tree, plan_forest_tree, assemble_forest, foliage_geometry, build_foliage_lods}.py`; `assets/foliage` (72 KB), `assets/forest` (32 KB) and the leaf and bark textures.
- **Steps.** `world.forest_textures`; `world.forest.impostor.*`, `world.forest` (`forest_atomic_build.py`);
  `world.foliage.definitions.*`, `world.foliage.source.*`, `world.foliage.*`, `world.foliage_lods`
  (`foliage_build.py`); `unreal.forest` (`build.py:1696`); `unreal.foliage.<name>` (`foliage_build.py:114`).
- **/Game.** `/Game/Japan/Assets/{Tree_*, Bush_*, Grass_*}`, `/Game/Japan/FoliageLODs/<name>/`,
  `/Game/Japan/Materials/M_Foliage` and `MI_*`.
- **Runtime.** HISM groups with near and backdrop splits and shadow twins (`JapanWorld.cpp:498-623`). Leaf storm
  (`:930`). Tree sway and LOD settings (`JapanWorld.h:91-97`).
- **Bounds.** Island-wide scatter; the northern ecotone; the treehouse forest screen.
- **Checks.**
  - A: `test_forest_atomic.py`, `test_foliage_{collision, products, lod_policy, lod_package_continuity}.py`.
  - P: `tools/benchmark.py` (foliage is the dominant cost).
  - V: shots.
- **Scale.** About 160k trees, bushes and grass in `world.json`.

### W06 `forest_lake`
- **Src.** `world/regions/forest_lake/{layout, assemble, geometry, details, scatter, query_data, plan_asset}.py`.
- **Steps.** `world.lake.query_data`, `world.lake` (`lake_atomic_build.py`); `unreal.lake` (`build.py:1686`).
- **/Game.** `/Game/Japan/Lake/Pieces`, `/Game/Japan/Materials/M_ForestLakeWater`.
- **Runtime.** HISM `Lake_*` parents expand through `forest_lake/manifest.json` (`JapanWorld.cpp:461-470`). The
  lake record (centre, radii, safe shore) is read at `:816-825`.
- **Bounds.** Centre (-90, 235), radii (34, 23), water at 75 m, cabin (-56, 215, 75.65).
- **Dyn.** Swim/sail shore recovery.
- **Checks.** A: `test_lake_atomic.py`, `test_forest_lake_owner_integration.py`, `LakePiecesTests.cpp`,
  `JapanHorseWaterTests.cpp`. V: `scenarios/lake.py`.
- **Scale.** 5 parents.

### W07 `hidamari`
- **Src.**
  - `world/regions/hidamari/*`: 14 MB, including `textures/` (3.5 MB) and `fonts/NotoSansJP.ttf` + `OFL.txt`.
  - `world/city_surface_tiles.py`, `city_terrain_surface.py`, `city_tree_lods.py`.
  - `assets/hidamari` (46 MB, 96 library files).
- **Steps.**
  - `world.hidamari.layout_data`, `.data.*`, `.source.*`, `.harbor_cut_data`, `.north_masks`, `world.hidamari`,
    `world.hidamari.*` (`hidamari_build.py`).
  - `world.hidamari.tiles.*`, `world.city_tiles.*` and `world.city_tiles` (`build.py:346-378`);
    `world.hidamari_textures`; `world.hidamari_props`; `world.city_trees`.
  - `unreal.world` (`import_hidamari.py`, NORTH=False); `unreal.desktop` (`import_city_atomic.py`, `build.py:1771`);
    `unreal.city_tree_lods` (`build.py:1782`).
- **/Game.** `/Game/Japan/Assets/HD_*`, `/Game/Japan/Hidamari/PropLODs/*`,
  `/Game/Experiments/CitySurfaces/v1_128m/*`, `/Game/Experiments/CityTrees/v4`, `/Game/Japan/Materials/{M_Arcade, …}`.
- **Runtime.** `hidamari/city.json` instances are merged into the HISMs (`JapanWorld.cpp:110-139`). CityPieces
  manifest (`:388-391`). City, arcade and plaza post-process plus arcade point lights (`:140-320`). Resident
  groups via `AVillageLife` (`:925-928`). Fog town factor (`JapanWorld.h:141-144`).
- **Bounds.** City box [300, -260, 1320, 430] (`city.json:bounds`). Old trees are cut in x 300–2200, y -450–1600
  and x -700–2400, y 500–3000 (`JapanWorld.cpp:122-123`).
- **Dyn.** Residents, harbour/ferry, station/train, zeppelin city station.
- **Checks.**
  - A: `test_city_*` (about 20 files), `test_hidamari_*` (about 10), `CitySurfacePiecesTests.cpp`.
  - V: shots, `tools/capture.py`.
  - P: city tree LOD menu (`JapanWorld.h:95`).
- **Scale.** 145 instance keys, about 191k instances. **The plan says to split Hidamari.**

### W08 `southwest`
- **Src.** `world/regions/southwest/{layout, fishing, island, temple, stand, models, mesh, contexts/}`,
  `assets/southwest` (952 KB).
- **Steps.** `world.southwest` (`southwest_atomic_build.py`); `unreal.southwest` (`build.py:1588`).
- **/Game.** `/Game/Japan/Southwest/Pieces`.
- **Runtime.** HISM `SW_*` parents expand through `southwest/runtime.json` (`JapanWorld.cpp:441-450`).
- **Bounds.** edit_bounds (-300, -200, -190, -90); island at (-150, -530), yaw 15; boat launch and crossing.
- **Dyn.** Sailboat launch.
- **Checks.** A: `test_southwest_atomic.py`, `SouthwestPiecesTests.cpp`. V: `scenarios/sailboat.py`.
- **Scale.** 13 SW keys, about 150 boulders.

### W09 `brinecove`
- **Src.** `world/regions/brinecove/*` (1.1 MB, including `foliage_models`); `assets/brinecove` (47 MB, 123 files).
- **Steps.** `world.brinecove.{rim_data, placements, query_data, sources, model.*, meshes, textures}` and
  `world.brinecove`; `unreal.brinecove` (`build.py:932`).
- **/Game.** `/Game/Brinecove/{Meshes, Materials, Textures}`.
- **Runtime.** **Runtime actor** `ABelmonteRegion::Spawn(..., "brinecove")` (`BelmonteRegion.cpp:82`, called at
  `JapanWorld.cpp:866`). It also calls `Clear` on island instances (`:384`).
- **Bounds.** Origin (-1500, -120) (`regions/brinecove/region.py:14`).
- **Dyn.** Ferry terminal (W17).
- **Checks.** A: `test_brinecove_*` (about 15 files).
- **Scale.** Ask `products/brinecove/runtime.json` at the donor revision.

### W10 `treehouse`
- **Src.** `world/regions/treehouse/*` (336 KB); `assets/treehouse` (33 MB: props, textures and refs, each with
  provenance).
- **Steps.** `world.treehouse`, `world.treehouse_trees.data`, `.recolour`, `world.treehouse.source_data`
  (`treehouse_atomic_build.py`); `world.treehouse_textures`; `unreal.treehouse` (`build.py:1707`);
  `unreal.see_through`.
- **/Game.** `/Game/Japan/Assets/TH_*`, `/Game/Japan/Treehouse/{Materials, Textures}`, `/Game/Japan/Textures`,
  `/Game/SeeThrough/MPC_SeeThrough`.
- **Runtime.** HISM `TH_Structure`/`TH_Dressing` expand through `treehouse/{surfaces, pieces}.json`
  (`JapanWorld.cpp:471-482`). The runtime JSON is merged at `:88-105`. Lights, grade and room volumes at
  `:694-808`; see-through rooms at `JapanWorld.h:103-117`.
- **Bounds.** Grade box centre (-135, 169.25, 74.06), extent (43, 47.25, 45).
- **Checks.**
  - A: `test_treehouse_{atomic, pieces, ledger}.py`, `TreehousePiecesTests.cpp`, `SeeThroughTests.cpp`.
  - V: `treehouse*.py` scenarios (walk, tour, live).
- **Scale.** 4 TH keys.

### W11 `megapark` (Super Ultra Mega Park)
- **Src.** `world/regions/megapark/*`; `assets/megapark` (89 MB, 505 files: npz geometry and collision, 405 PNG,
  `map.json`) — rights cleared by the owner on 2026-11-08 (§5 item 1, DECISIONS D05 group 3).
- **Steps.** `world.megapark.letters_data`, `world.megapark`, `world.megapark_restyle`; `unreal.megapark`
  (`build.py:1618`); `unreal.kei` (cars).
- **/Game.** `/Game/MegaPark/{Meshes, Materials, Textures, Maps/SuperUltraMegaPark}`.
- **Runtime.** Saved actors exist only in the standalone map (`import_megapark.py:336-395`). On the island it is a
  **runtime actor**, `ASuperUltraMegaPark::Spawn(megapark/park.json)` (`SuperUltraMegaPark.cpp:43`, called at
  `JapanWorld.cpp:848`).
- **Bounds.** CENTRE (-150, 1300), YAW -60, BASE 49.3; a seam with the zeppelin footbridge
  (`placement.py:18-27`).
- **Dyn.** Mega Park air station; a separate play profile `megapark`.
- **Checks.**
  - A: `test_megapark_{access, placement, restyle}.py`, `verify_import.py`, `verify_source.py`.
  - V: `megapark_*_film.py`, `megapark_tour.py`.
- **Scale.** 50 models / 955 parts / 213k triangles; 147,660 collision triangles; 151 grind paths
  (`docs/MEGAPARK.md:225-228`).

### W12 `craterpark` (volcano)
- **Src.** `world/regions/craterpark/*` (1.4 MB, including `v2/`) and `world/craterpark_layout.py`;
  `assets/craterpark` (59 MB, 300 files; provenance names an external GitHub repo); the volcano lives in
  `hidamari/mountains.py`.
- **Steps.** `world.craterpark_geometry`, `world.craterpark_layout` (`build.py:164-170`); `world.craterpark.inputs`
  and `world.craterpark` (`craterpark_atomic_build.py`); `world.craterpark_restyle`; `world.crater_cloud`;
  `unreal.craterpark` (`build.py:1627`); `unreal.crater_cloud`; `unreal.north` (`build.py:1579`, `HD_North*`).
- **/Game.** `/Game/CraterPark/{Meshes, Materials, Textures, Cloud}`, `/Game/Japan/Assets/HD_North*`,
  `M_NorthMountains`.
- **Runtime.** **Runtime actor** `ASuperUltraMegaPark::Spawn(craterpark/park.json)` (`JapanWorld.cpp:851`). Cap
  cloud from `ACraterCloud::Spawn` (`:855`). Caldera grade (`:193-210`). Tower and hoist starts come from data
  (`CraterParkTower.h:6-20`; map travel at `JapanMap.cpp:229-234`). The volcano terrain is the island/HD terrain.
- **Bounds.** Caldera centre (850, 2400), heading 185, lift 680 (`craterpark/placement.py:26-31`).
- **Checks.**
  - A: `test_craterpark_*` (about 50 files).
  - V: `scenarios/crater_tower_hoist.py`.
- **Scale.** Ask `craterpark/park.json` at the donor revision.

### W13 `swordcamp`
- **Src.** `world/regions/swordcamp/{build, catalogue, make_atlas, mesh, parts/}`; `assets/swordcamp` (2 MB,
  concepts and textures with provenance).
- **Steps.** `world.swordcamp`, `world.swordcamp_atlas`; `unreal.swordcamp` (`build.py:1605`).
- **/Game.** `/Game/SwordCamp/{Assets, Materials, Textures}`.
- **Runtime.** **Runtime only**: `ASwordTrainer::SpawnRoninCamp` (`SwordTrainer.cpp:427`, called at
  `JapanGameMode.cpp:64`) places the camp at (-54, -94), facing the road at (-55, -71). It also deletes every
  instanced tree, bush and rock within 15.5 m. It can be disabled with `-noronincamp`.
- **Dyn.** Ronin encounters (`RoninProjectile.cpp`).
- **Checks.** A: `test_swordcamp.py`, `JapanEncounterTests.cpp`. V: `ronin_camp_film.py`.

### W14 `hidamari_stable`
- **Src.** `world/regions/hidamari_stable/*`; `assets/hidamari-stable` (160 KB).
- **Steps.** `world.hidamari_stable.{sources, query}`, `world.hidamari_stable` (`stable_atomic_build.py`);
  `world.hidamari_stable_review` (explicit); `unreal.hidamari_stable` (`build.py:819`, **explicit=True**).
- **/Game.** `/Game/HidamariStable/*`.
- **Runtime.** `AHidamariStable::Spawn` (`HidamariStable.cpp:142`). It is gated off: `bEnabled = false`
  (`HidamariStable.h:57`), paired with `ENABLED = False` (`layout.py:20`).
- **Bounds.** SITE (955, 447), YAW 0.
- **Checks.** A: `test_stable_atomic.py`, `test_hidamari_stable_layout.py`, `HidamariStableBoundsTests.cpp`.
- **Status.** Disabled in the source. P0 must decide in-scope vs. not shipped.

### W15 `hippodrome`
- **Src.** `world/regions/hippodrome/*` (no Blender); `assets/hippodrome` (4.8 MB, props with provenance).
- **Steps.** `regions/hippodrome/atomic.py` steps; `world.hippodrome` digest; `unreal.hippodrome` (`build.py:794`).
- **/Game.** `/Game/Hippodrome`, plus `Data/hippodrome/hippodrome.json`.
- **Runtime.** **Runtime actor** `AHippodrome::Spawn` (`Hippodrome.cpp:57`, called at `JapanWorld.cpp:856`), with
  clearance (`:364-365`).
- **Bounds.** ORIGIN (600, 525), turn radius 50 m.
- **Dyn.** Racing (`ARacingService::Spawn`, `JapanWorld.cpp:879`).
- **Checks.** A: `test_hippodrome_{atomic, layout}.py`, `RacingTests.cpp`.

### W16 `belmonte`
- **Src.** `world/regions/belmonte/*` (240 KB); `assets/belmonte` (156 MB, 438 files).
- **Steps.**
  - `world.belmonte.*`: model_definitions, final_source.*, valley_*, north_context, north.*, scene_views,
    prepare_materials, prepare_planting, meshes, ground, textures.
  - `world.belmonte`; `unreal.belmonte` (`build.py:990`).
- **/Game.** `/Game/Belmonte/{Meshes, Materials, Textures}`, `/Game/Racing/M_RacingTv`.
- **Runtime.** **Runtime actor** `ABelmonteRegion::Spawn(belmonte/runtime.json)` (`JapanWorld.cpp:863`).
  TVs from `ARacingBroadcast::Spawn` (`:881`); racing service (`:879`).
- **Bounds.** ORIGIN (550, 4500); source bounds give x -474.5..1573.5, y 3899.5..5691.5 (`belmonte/layout.py:11-16`).
  SOUTH_JOIN is 3600.
- **Dyn.** Racing calendar and saves, 4 TVs, train station, gondola, zeppelin station.
- **Checks.** A: `test_belmonte_*` (about 40 files), `test_racing_courses.py`, `RacingTests.cpp`.

### W17 `ferry` (route system)
- **Src.** `world/regions/ferry/*`; `assets/vehicles/ferry` (ship and terminals); `regions/{hidamari, brinecove}/ferry_terminal.py`.
- **Steps.** `world.ferry_ship.*`, `world.ferry_terminals.*`, `world.ferry_probes`, `world.ferry_site`,
  `world.hidamari_ferry_cut`, `world.ferry_service`; `unreal.ferry` (`build.py:1972`).
- **/Game.** `/Game/Ferry/{Ship, Terminals, Materials}`.
- **Runtime.** Host-only `AFerryService::Spawn(ferry/service/service.json)` (`FerryService.cpp:213`, called at
  `JapanWorld.cpp:874`). Its static terminal meshes and hidden collision are runtime components
  (`FerryService.cpp:272-289`).
- **Bounds.** Route bounds (-2000, -1080, 1000, -220) (`ferry/route.py:25`).
- **Checks.** A: `test_ferry_*` (about 15 files), `FerryServiceTests.cpp`. V: `ferry_roundtrip_live.py`.

### W18 `gondola` (route system)
- **Src.** `world/regions/gondola/*`, `world/gondola/*`, `{belmonte, hidamari}/gondola.py`, `assets/vehicles/gondola`.
- **Steps.** `world.gondola_kit.*` (`gondola_atomic_build.py`), `world.gondola_ground_inputs`, `world.gondola_ground`,
  `world.gondola_structure_inputs`, `world.gondola_structures`, `world.gondola_site`, `world.gondola_service`;
  `unreal.gondola` (`build.py:1913`).
- **/Game.** `/Game/Gondola/{Kit, World, Materials, Textures}`.
- **Runtime.** Host-only `AGondolaService::Spawn(gondola/runtime.json)` (`GondolaService.cpp:122`, called at
  `JapanWorld.cpp:876`). Stations, supports and access are runtime "static" parts (`GondolaService.cpp:169-174`);
  ropes have 3 LODs (`:191`). Instance clear at `JapanWorld.cpp:385`.
- **Bounds.** (340, 2700, 560, 4680) (`gondola/structures.py:19`).
- **Checks.** A: `test_gondola_*` (about 20 files), `GondolaServiceTests.cpp`. V: `gondola_roundtrip_live.py`,
  `gondola_seat.py`.

### W19 `zeppelin` (route system)
- **Src.** `world/regions/zeppelin/*` (156 KB, including `parts/`).
- **Steps.** `regions/zeppelin/atomic.py` steps (`build.py:1126`); `world.zeppelin` digest; imported assets-only
  inside `unreal.world` (`setup_project.py:224-225`).
- **/Game.** `/Game/Japan/Assets/ZP_*`, `/Game/Japan/Materials/M_ZeppelinFabric`.
- **Runtime.** Station and trail meshes are HISM parents `ZP_Woodland`, `ZP_Belmonte` and `ZP_Trail`
  (`zeppelin/layout.py:127-128`). The ship comes from `AZeppelinService::Initialize` (`ZeppelinService.cpp:44`,
  called at `JapanWorld.cpp:831`).
- **Bounds.** **Four** stations, not the plan's three:
  - Woodland at (-205, 230, 70.4);
  - Hidamari at (1273, 321, 35.5);
  - Mega Park at (-200, 1484, 130);
  - Belmonte at (410, 4660, 217.75).

  Fix F11/W19 in the plan.
- **Checks.** A: `test_zeppelin_*` (4 files). V: `scenarios/zeppelin.py`.

### W20 Train and cross-region routes
- **Src.** `world/train/*` (corridor, earthworks, route, …), `world/map/*`, `world/racing/belmonte_courses.json`.
- **Steps.**
  - `world.belmonte_track.*` (`train_atomic_build.py`), `world.belmonte_train.*` (`train_carriage_build.py`).
  - `world.belmonte_train_{plan, furniture_lods, assembly, authoring, review, route, service}`,
    `world.belmonte_track_{review, data, meshes}`.
  - `unreal.belmonte_track` (`build.py:1013`) and `unreal.belmonte_train` (`:1002`), both with folder wipes (§2).
  - `world.map` (`:1318`).
- **/Game.** `/Game/BelmonteTrack`, `/Game/BelmonteTrain`, plus `Data/belmonte_track/track.json` and
  `Data/belmonte_train/service.json`.
- **Runtime.** **Runtime actor** `ABelmonteTrack::Spawn` (`BelmonteTrack.cpp:32`, called at `JapanWorld.cpp:870`)
  places the static track, tunnels and viaduct. `ABelmonteTrainService::Spawn` (`:872`; `IsEnabled()` returns
  true at `BelmonteTrainService.cpp:266-269`). Corridor vegetation is cleared at generation
  (`gen_world.py:366-367`). Map travel is `UJapanMap` (`JapanMap.cpp:139`, `TravelTo` at `:432`), with the atlas
  at `JapanAtlas.cpp:33`.
- **Checks.**
  - A: `test_belmonte_train_*`, `test_train_*`, `BelmonteTrainServiceTests.cpp`, `TrainPassengerViewTests.cpp`,
    `JapanMapTests.cpp`, `test_world_map_*`.
  - V: the rides.

## 4. Proposed P3 slice (start → Sunset Pier approach)

**Ground.** Two neighbouring 128 m cells sharing the edge x = -128 m (UE X = -12800):
- `Terrain_cell_-2_-1`, x -256..-128, y -128..0. It holds PlayerStart, House_A and HouseLot_1, House_B and
  HouseLot_2, road, poles and lamps, guardrail, and the path top at (-154.2, -86.8).
- `Terrain_cell_-1_-1`, x -128..0, y -128..0. It holds the path's middle third, House_C and HouseLot_3, and the
  road bend.
- Add `Terrain_cell_-1_-2` only as the shoreline under the deck entrance. The pier path's footprint is split
  44/28/44 points across cells -2_-1, -1_-1 and -1_-2.
- These cells are in the saved Slice map today, so this half is adoption, not spawner migration.
- `Road`, `Guardrail`, `Wires` and `Lane` are each **one island-wide mesh** (x ±295). The slice must adopt them
  whole or split them. This is a real boundary question to settle in the slice.

**Tree patch.**
- The runtime HISM instances inside the two cells: about 1,500 trees, about 1,000 bushes, about 17.8k grass and
  about 1,800 litter, mainly `Tree_Maple_A`, `Tree_Broad_A`, `Tree_Ginkgo`, `Tree_Pine_A/B` and `Tree_Cedar_B`.
- Migrate one bounded patch, for example the trees within 40 m of the path, into one saved instanced-foliage or
  ISM actor.
- Bake the park clearance (`JapanWorld.cpp:505`) and the backdrop trace. Exclude or bake the Ronin camp clearing:
  the camp at (-54, -94) lies in cell -1_-1, so run with `-noronincamp` or include W13's clearing.

**Building/bench.**
- `House_B` + `HouseLot_2`, or `House_C` + `HouseLot_3`, from `unreal.houses`.
- Plus the pier's `harbour_bench` feature (park-local x 42..56, y 22..23.2, so world (-68..-54, -212..-211)) and
  timber seating in `SM_SkateParkFurniture`. This matches the plan's example ID `prop/harbour-bench-01`.

**Water/materials.**
- The `Sea` piece with `M_Sea`, currently a runtime component at `JapanWorld.cpp:675-689`. Coast and ground
  `MI_Coast`, `MI_Ground` and `MI_Sand`; `MI_Road`, `MI_Paint`, `MI_Metal`.
- The shared `/Game/Japan/Materials` set, `M_Painterly` post-process and `MPC_Wind`. The sky dome as a shared
  scope.

**Rideable feature.**
- The `SM_SkatePath` pieces from road to deck (a riding/walking route; check both directions).
- The deck entrance and `plaza_kicker`/`plaza_landing` (world (-107..-97, -204..-199)) or `harbour_bench`, with
  their `park.json` rails (`SkateRailSubsystem`).
- Include the 128 m `SM_SkatePier` and `SM_SkateParkFeatures` pieces that cover cell -1_-2. Adopt the whole pier
  only if the pieces are not grid-aligned.

**Source assets.**
- `world/gen_world.py` and `world/regions/houses/*`.
- `world/regions/skatepark/{park.json, layout, features, pieces, pier_site}.py`.
- `assets/skatepark/{modules/*.glb, modules.json, textures/*.jpg}`.
- `assets/environment/textures/*`, `world/textures/*`, `assets/foliage/*` (species specs) and
  `world/prop_sources.py`.
- Cairo (F01) and the Skate plugin data (`platform/engine/Plugins/Activities/Skate/Data`).

**Build steps (donor side).** `world.layout` → `world.island.sources`/`world.terrain*`/`world.island.receiving`
→ `world.textures` → `unreal.materials` → `unreal.island` (cells + Slice) → `world.props` + `unreal.world`
(props) → `world.houses*` → `unreal.houses` → `world.foliage.<species>` → `unreal.foliage.<species>` +
`unreal.forest` → `world.skatepark_textures` + `world.skatepark.*` → `unreal.skatepark` + `unreal.skate_board` →
`skate.runtime`/`unreal.skate_data` → `data.stage`.

**/Game outputs.**
- `/Game/Experiments/IslandTerrain/v1_atomic/{Terrain_cell_-2_-1, Terrain_cell_-1_-1, Terrain_cell_-1_-2, Road, Lane, Guardrail, Wires, Sea}`
- `/Game/Japan/Materials/{MI_Ground, MI_Coast, MI_Sand, MI_Road, MI_Paint, MI_Metal, M_Sea, M_ForestGround, M_Painterly, MPC_Wind, M_Foliage, M_Village, …}`
- `/Game/Japan/Assets/{House_B, HouseLot_2, House_C, HouseLot_3, Pole, Pole_Lamp, Lantern, Tree_Maple_A, Tree_Broad_A, Tree_Ginkgo, Tree_Pine_A/B, Tree_Cedar_B, Bush_*, Grass_A/B, Litter, Rock_*, SkyDome}`
- `/Game/Japan/FoliageLODs/<species>/`
- `/Game/SkatePark/{SM_SkatePath*, SM_SkatePier*, SM_SkateParkFeatures*, SM_SkateParkFurniture*, Textures, Materials, Board}`
- `/Game/SkateRuntime/*`
- `/Game/Japan/Maps/Slice`

**Spawners to switch off for the slice.** In `AJapanWorld::Load`: the instance keys inside the slice cells,
the Sea and SkyDome, and `InstallPark` (`JapanWorld.cpp:842-846`); or a slice-only ASkatePark mode. Keep tags
`IslandSurface:*` and `CitySurface:*` and the fixed-collision rule.

## 5. Licensing and provenance

**What exists**
- `source-library.json` lists 1,895 files with only `bytes` and `sha256`, and `"ownership": "Atelier's own asset
  library."`. It carries **no license field**.
- There is **no LICENSE file** at the repo root or in `games/yorimichi`.
- Per-asset `*.provenance.json` records about 230 files: prompt, model (`gpt-image-2.5-sunburst`, MeshAxiom,
  TRELLIS, Tripo), hashes and timestamps. They cover the treehouse, Brinecove, character concepts, environment
  textures, props, the hippodrome and Hidamari props, and the swordcamp. They give no license terms.
- Fonts: `assets/ui/fonts/OFL.txt` and `world/regions/hidamari/fonts/OFL.txt` (Noto Sans JP, OFL). These are fine.
- Audio: `assets/audio/SONNISS-LICENSE.txt` (GDC bundle). Its own note: "must NOT ship them as a sound pack of
  their own". The masters are fetched into `the machine cache (~/.cache)/atelier/sonniss` and are not committed. The kart has 21
  committed WAVs (X02, excluded).
- Music: `assets/audio/music/music.lock.json` points to a **public** GitHub release, `yorimichi-music-v1.zip`
  (1.8 GB of MP3), generated with Suno v6 through a cookie-based client (`docs/MUSIC.md`).

**Unclear or high-risk for a public repo with LFS**
1. **Super Ultra Mega Park (`assets/megapark`, 89 MB): highest risk.**
   - `provenance.json` claims "Atelier's own asset library".
   - But `map.json` has `retail_material_guid`/`retail_external_reference_guid`; geometry is "original position
     words" with a decoded vertex codec (`GetVertex82AC79D0`); rails are "120-byte big-endian cubic segment
     payloads"; it has baked lightmaps, "original desert campus" and "shark logos" (`docs/MEGAPARK.md:166-228`).
   - My inference, not verified: this is extracted from a commercial console game whose park has this name.
   - Do **not** upload it to public LFS until the rights are established. Mark W11 blocked or restricted.
   - **Resolved 2026-11-08:** the owner granted Mega Park's asset permissions in full (DECISIONS D05 group 3,
     board #31124). W11 is ported in full: `/Game/MegaPark` and `Data/megapark` are adopted as group 1 content.
2. **Crater Park (`assets/craterpark`, 59 MB).** The source is `github.com/fontanierh/crater-skate-park` @bf511b1,
   "contributed by the park's author". It is probably the owner's, but no license file was copied. Record a
   license.
3. **Suno music.** Ownership depends on the Suno plan held at generation time. The release is already public.
   Record the plan/terms or keep it in authorized storage.
4. **Sonniss-derived one-shots** (footsteps, combat, transport and skate cues are cut from masters). Shipping
   them inside a build is allowed. Committing standalone WAV/uasset banks to a public repo looks close to
   "selling/sharing as they come". Keep them in restricted storage or get a ruling.
5. **Mixamo rigs/animations** (`assets/characters/*`, `docs/MIXAMO_WORKFLOW.md`, sword-trainer manifest). Adobe
   terms allow use in projects, not redistribution of the raw files. Public LFS of the raw FBX/GLB clips is a risk
   (affects F01/F02 more than the world).
6. **AI-generated meshes and textures** (Tripo, MeshAxiom, TRELLIS, gpt-image). Provenance exists. Add the
   tool-terms basis per generator, especially Tripo's output license tier.
7. **Binary metadata.** No `/Game` packages are committed now. Any adopted donor `.uasset` will embed absolute
   `build/yorimichi/...` source paths from `AssetImportTask.filename` (for example `setup_project.py:32`).
   Normalize them before the public push (plan §4).

## 6. Gaps for P0 follow-up
- No complete donor `unreal/Content` was found. A quick check of local worktrees found only fragments: `Data`,
  `Japan`+`SeeThrough` or `Adventure` in the `atelier-v2-*` worktrees. Since Content is ignored, P0 step 3
  (controlled import) is likely needed.
- Per-region actor counts for Belmonte, Brinecove, Crater Park, ferry and gondola need their `runtime.json` at the
  donor revision; the reference build lacked them.
- Decide W14 (stable disabled) and fix the zeppelin station count (4).
