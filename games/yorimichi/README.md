# Yorimichi

A painterly Japanese island in Unreal 5.8: walk, run, sprint and roll through a coastal countryside, a forest hamlet,
the city of Hidamari, a fishing cove and an island temple; sail a dinghy, ride the zeppelin, skate the pier with
skate.-style Flick-It controls, and fight the fox hunter with a wooden sword. The direction is a sword brawler where
spirits come out of openings across the island ([docs/LORE.md](docs/LORE.md), a draft).

Current state and what is in the game: [docs/STATUS.md](docs/STATUS.md).

## Build and play

From the repository root (requirements in the [top-level README](../../README.md)):

```sh
uv run atelier fetch yorimichi      # Sonniss sound masters, once per machine
uv run atelier build yorimichi      # everything; only changed steps rerun
uv run atelier play yorimichi       # 1080p window; --profile desktop or desktop-1440 for the measured desktop profile
uv run atelier qa yorimichi skate   # 22 skateboarding cases against the running game
```

`uv run atelier build yorimichi --list` shows every step: world data and meshes, characters, sounds, effects, the C++
module, the Unreal imports and the runtime data. A clean build from nothing takes about half an hour on an M3 Pro, most of
it in Unreal's first shader compile.

## Where things are

| Folder | What |
|---|---|
| `game.toml` | this game's description for Atelier: project, fetches, play profiles |
| `build.py` | the build recipe |
| `world/` | island generator (`gen_world.py`), textures, props, foliage LODs, terrain, city tiles; `world/regions/*` (Momiji Hamlet, Hidamari, the southwest, the mini-mega ramp, the woodland lake, the zeppelin stations, the skate pier, the tree house, the houses on the main road); `world/map` (map tools and the painted sheet) |
| `assets/characters/` | the player (`cairo`), the enemy (`fox-hunter`) and the villagers (`wanderer`): source files, manifests, exporters |
| `assets/audio/` | sound banks: fetch, slice and synthesis scripts (the sounds themselves are built, not committed) |
| `assets/fx/`, `assets/props/`, `assets/vehicles/` | effect sprites, live-workshop props, the sailboat |
| `unreal/` | the Unreal project: `Source/Yorimichi` (C++), `Config`, `Scripts` (editor import scripts); `Content` is build output |
| `live/` | the live bridge's in-game Python and saved overlays |
| `scenarios/` | tests and films driven through the live bridge |
| `streaming/` | phone play over Pixel Streaming (to be split into streaming and touch controls) |
| `tools/` | desktop profile launcher, benchmark, fight film |
| `docs/` | how the game works: skate, combat, fox hunter, animation principles, world map, sound, lore |

## Names still to settle

The player is still called by its concept-sheet name, Cairo (`cairo`, `/Game/Cairo`), and several
C++ classes carry prototype names (`ACairoCharacter` is the player, `AWandererCharacter` its base, `Japan*` the
rest). They are renamed in one pass once the new names are chosen.
