# Migration from the prototype repository

Yorimichi was built from 4 to 28 September 2026 in a private prototype repository (`japan/` inside a larger
experiments repo). This file tracks the move into Atelier. The prototype stays as a read-only archive.

## Definition of done

1. Everything live in the prototype is here, in the Atelier layout: code, sources, build scripts, tests, docs.
2. No secrets, personal data or third-party files that can't be redistributed.
3. A fresh clone builds and plays Yorimichi with `atelier fetch`, `atelier build` and `atelier play`, and the
   generated world, characters and sounds match the prototype's.
4. The scenario tests (skate, combat) pass against the fresh build.

## Stages

**Stage 1: move and bootstrap.** Move every live piece into the new layout with the game behaving exactly as before:
same C++ (renamed module), same generators, same import scripts, with every path going through `atelier.paths` and
the game reading its runtime data from `Content/Data/` instead of the prototype's loose `japan/out/` files.

**Stage 2: platform plugins.** Pull the engine code into platform plugins behind the activity interface, one plugin
per commit, each verified with scenario tests: FX and audio, animation nodes, live bridge and scenarios, streaming and
touch controls, the player shell and on-foot activity, skate, sail and ride, combat.

## Status

| Piece | Prototype | Here | State |
|---|---|---|---|
| Skeleton, conventions | — | `README.md`, `ARCHITECTURE.md`, `platform/conventions/` | done |
| Studio core, machine safety | `japan/streaming/{exclusive,guard,memory_guard,provenance}.py`, `japan/tools/guarded_run.py` | `platform/studio/atelier/` | done, tests pass |
| Build engine and `atelier` command | `japan/run.sh` | `platform/studio/atelier/{build,cli}.py`, `games/yorimichi/{build.py,game.toml}` | done: 30 steps, incremental |
| World generators, regions, map, sailboat | `japan/*.py`, `japan/{village,hidamari,southwest,mega,forest_lake,zeppelin,skatepark,sailboat}/`, `japan/tools/*map*.py` | `games/yorimichi/world/`, `games/yorimichi/assets/vehicles/sailboat/` | done, verified (below) |
| Characters (player, fox hunter, villager) | `output/imagegen/.../game-r17`, `.../animation-r05`, `japan/characters/wanderer` + shared cape boy modules, `japan/tools/export_*_unreal.py` | `games/yorimichi/assets/characters/` | done, exports verified |
| Sound banks, effect textures | `japan/audio`, `japan/tools/{fetch_sonniss_*,slice_*,make_skate_sfx,gen_combat_fx_textures}.py` | `games/yorimichi/assets/{audio,fx}/` | done: all 593 WAVs and 5 textures byte-identical |
| Unreal project | `japan/unreal/JapanProto` | `games/yorimichi/unreal` (module `Yorimichi`) | done: compiles; runtime data from `Content/Data` |
| Live bridge, scenarios, streaming, tools | `japan/live`, `japan/skatepark/qa.py` and friends, `japan/{sailboat,zeppelin,forest_lake}/qa.py`, `japan/streaming`, `japan/{benchmark,desktop_preview}.py`, `japan/tools/{film_fight.sh,mix_fight_film.py,building_lab.py}`, `japan/trailer/capture.py` | `games/yorimichi/{live,scenarios,streaming,tools}`, `.../hidamari/kit/lab.py` | done |
| Character authoring tools | 44 `japan/tools/*` + 6 helpers, `lib/renderdev.py` | `games/yorimichi/assets/characters/tools`, `platform/studio/atelier/{ai,review,blender}`, `platform/studio/node` | done (history via `YORIMICHI_ARCHIVE`) |
| Docs | `japan/PLAN.md`, 19 current docs | `games/yorimichi/docs` | done, paths translated |
| Fresh build and play | — | — | in progress |

### Left in the prototype archive

Kept out on purpose: the cape boy and the procedural Wanderer V1 (`japan/character`, most of
`japan/characters/cape_boy`), the character kit, the old cruiser skateboard (`japan/items/skateboard` and its import
scripts), the unused experiments (sky study, canopy normals, grass art, leaf-coverage trimming, harbor tiles), the
kite, one-off revision scripts (about 110 `refine_*`, `validate_*`, `capture_*` and `author_*` tools), the rejected
sword-from-video, cloth-simulation, Tripo-clothes and Smart UV trials, the female mechanic and the jacket, three
trailer generations, the desktop-quality campaign, the look gate, all review images, captures and trailer takes
(about 170 GB), and every character revision older than the current one. The prototype repository stays available as
the archive.

### World verification (29 September)

A fresh build into an empty folder, compared with the prototype's `japan/out`:

- Textures (24): byte-identical. They are generated, not committed.
- Heightmaps: identical to 1e-5 m. `city.json`, `park.json`, `map_lines.json` and the painted `map.png`: identical.
- `world.json`: 21 more plants out of 204k and a different torii-clearance record. The prototype's file was written
  at 22:24 on 9 September and `gen_world.py` changed at 22:54, so the fresh build follows the committed code.
- `map.json`: the skate pier stop is now in the file (the prototype's game added it at runtime).
- Every mesh (37 props, 48 foliage LODs, 67 Hidamari, 12 village, 14 southwest, 2 mega, 5 lake, 8 zeppelin,
  5 sailboat, 8 skate pier, 85 city tiles, 6 city tree LODs, the terrain): same files; sizes equal or 80-96 bytes
  shorter, which is the embedded texture path. The four unused kite meshes are gone on purpose.

