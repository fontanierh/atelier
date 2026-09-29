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
| Characters (player, fox hunter, villager) | `output/imagegen/.../game-r17`, `.../animation-r05`, `japan/characters/wanderer` + shared cape boy modules, `japan/tools/export_*_unreal.py` | `games/yorimichi/assets/characters/` | done, exports verified |
| Sound banks, effect textures | `japan/audio`, `japan/tools/{fetch_sonniss_*,slice_*,make_skate_sfx,gen_combat_fx_textures}.py` | `games/yorimichi/assets/{audio,fx}/` | done: all 593 WAVs and 5 textures byte-identical |
| World generators, regions, map, sailboat | `japan/*.py`, `japan/{village,hidamari,southwest,mega,forest_lake,zeppelin,skatepark,sailboat}/`, `japan/tools/*map*.py` | `games/yorimichi/world/`, `games/yorimichi/assets/vehicles/sailboat/` | done, verified (below) |

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

