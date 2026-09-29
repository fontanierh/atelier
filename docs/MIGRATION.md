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

**Stage 2: platform plugins.** Pull the engine code into platform plugins, one plugin per commit, each verified with
scenario tests: FX and audio, animation nodes, live bridge and scenarios, streaming and touch controls, skate. The
player shell and on-foot activity, sail and ride, and combat stay in Yorimichi until a second game wants them
(ARCHITECTURE.md, rule 5: things graduate on evidence); the sandbox is that second game's starting point.

## Status

| Piece | Prototype | Here | State |
|---|---|---|---|
| Skeleton, conventions | — | `README.md`, `ARCHITECTURE.md`, `platform/conventions/` | done |
| Studio core, machine safety | `japan/streaming/{exclusive,guard,memory_guard,provenance}.py`, `japan/tools/guarded_run.py` | `platform/studio/atelier/` | done, tests pass |
| Build engine and `atelier` command | `japan/run.sh` | `platform/studio/atelier/{build,cli}.py`, `games/yorimichi/{build.py,game.toml}` | done: 35 steps, incremental; imports run `after` the compile and one step per region |
| World generators, regions, map, sailboat | `japan/*.py`, `japan/{village,hidamari,southwest,mega,forest_lake,zeppelin,skatepark,sailboat}/`, `japan/tools/*map*.py` | `games/yorimichi/world/`, `games/yorimichi/assets/vehicles/sailboat/` | done, verified (below) |
| Characters (player, fox hunter, villager) | `output/imagegen/.../game-r17`, `.../animation-r05`, `japan/characters/wanderer` + shared cape boy modules, `japan/tools/export_*_unreal.py` | `games/yorimichi/assets/characters/` | done, exports verified |
| Sound banks, effect textures | `japan/audio`, `japan/tools/{fetch_sonniss_*,slice_*,make_skate_sfx,gen_combat_fx_textures}.py` | `games/yorimichi/assets/{audio,fx}/` | done: all 593 WAVs and 5 textures byte-identical |
| Unreal project | `japan/unreal/JapanProto` | `games/yorimichi/unreal` (module `Yorimichi`) | done: compiles; runtime data from `Content/Data` |
| Platform plugins | the game module | `platform/engine/Plugins`: AtelierCore, AtelierAnimation, AtelierFX, Skate, AtelierStream, LiveBridge | done (stage 2, below) |
| Streaming | `japan/streaming/{run.py,server.cjs,client.js}` | `atelier stream`, `platform/web/stream`, `games/yorimichi/phone` | done: phone page and plain player verified |
| A second game | — | `games/sandbox` | done: builds, plays, live bridge and stream verified |
| Live bridge, scenarios, streaming, tools | `japan/live`, `japan/skatepark/qa.py` and friends, `japan/{sailboat,zeppelin,forest_lake}/qa.py`, `japan/streaming`, `japan/{benchmark,desktop_preview}.py`, `japan/tools/{film_fight.sh,mix_fight_film.py,building_lab.py}`, `japan/trailer/capture.py` | `games/yorimichi/{live,scenarios,streaming,tools}`, `.../hidamari/kit/lab.py` | done |
| Character authoring tools | 44 `japan/tools/*` + 6 helpers, `lib/renderdev.py` | `games/yorimichi/assets/characters/tools`, `platform/studio/atelier/{ai,review,blender}`, `platform/studio/node` | done (history via `YORIMICHI_ARCHIVE`) |
| Docs | `japan/PLAN.md`, 19 current docs | `games/yorimichi/docs` | done, paths translated |
| Fresh build and play | — | — | done: every scenario passes (below) |

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

### Stage 2 (29 September)

| Plugin | Took from the game | The game's side |
|---|---|---|
| AtelierCore | `AtelierDataPath` (was `YoriData.h`), `FSprintStamina` | — |
| AtelierAnimation | ground-contact, skate-rider and sailboat-stance anim nodes | — |
| AtelierFX | the effects half of `JapanCombatFX`: sprites, flashes, hit-stop, slow motion, shake, sound cues, trails | `AYorimichiCombatFX` composes the sword's reactions; the player implements `IAtelierFXTarget` |
| LiveBridge | the generic half of `JapanLive`: HTTP bridge, Python, GLB props, overlays, input, screenshots | `UYorimichiLive` keeps the game's verbs; the bridge refuses a non-loopback port |
| Skate | `USkateComponent`, Flick-It, the rail subsystem | `AWandererCharacter` implements `ISkateRider`; `ASkatePark` stays; board, sounds and surfaces in DefaultGame.ini |
| AtelierStream, `platform/web/stream`, `atelier stream` | the launcher, server and data channel of `japan/streaming`, plus a new plain player (`/play/`) | `games/yorimichi/phone` (the touch page) and `FYorimichiPhone` |

### Fresh build verification (29 September)

A local clone of the repository at `3832479`, built in its own folder with `atelier build yorimichi` (the Sonniss
masters already in `~/.cache/atelier`, as `atelier fetch` leaves them; Python 3.12 with numpy and Pillow): **35 of 35
steps in 666 s**, with no manual step. The longest were the Unreal world import (165 s on an empty project), the
player's four import layers (73 s), the Hidamari generator (66 s), the first compile of the module and plugins (68 s)
and the desktop city tiles (56 s). Its `world.json`, heightmap, `city.json`, `map.json`, `map.png`, all 635 sound files
and all 24 textures are byte-identical to the main checkout's build. The game plays from the clone and skate QA passes
22/22 there (the scenario now waits for a steady frame rate first: on a new project the first minutes compile shaders,
and one mouse case read a flick as a shove-it until the game warmed up).

Scenarios on the fresh build: skate QA 22/22; `foxqa` passes (7 fox attacks: 5 landed, 1 parried, 1 dodged; the fox
defeated; the player knocked down and back up); `swordqa` passes (16 strikes, 11 dummy hits, a parry); sailboat 53
checks; zeppelin; lake. With a local stream: the phone double jump, map travel, the 20 settings, the sailboat, and the
plain player moving the character through Pixel Streaming's keyboard input.

After the migration, code that nothing could reach was removed (the old cruiser skateboard, the mini-mega ride, their
review modes and five rendering experiments; an audit traced every file's trigger and asset path), which brought back
the "Skate stance" setting the old board's flag had hidden. Every scenario above passed again afterwards. The review
harnesses no tool used went next (the jump, ground-contact and locomotion reviews, the south-west demo and flyover). Still
runnable without a profile: the character film review (`-warmqa`, BODY_SWAP_GUIDE.md) and the trailer capture
(`tools/capture.py`).

Fixed on the way, because the prototype's project had accumulated assets that hid them: the first import of a mesh
with build warnings crashed the commandlet (a placeholder now makes it a reimport), Hidamari's terrain needed the
south-west import's sand material, the skate pier import read `park.json` from the wrong folder. Scenario scripts that
had gone stale in the prototype were brought up to date (the sailboat's water recovery with the new board, the phone
map test's skateboard button, the settings count).
