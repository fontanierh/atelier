# Yorimichi

Yorimichi (寄り道, "a detour on the way home") is a painterly Japanese island in Unreal Engine 5.8. You walk, run and
roll through a coastal countryside, a forest hamlet, the city of Hidamari, a fishing cove and an island temple; sail
a dinghy, ride the zeppelin, skate the pier and the Mega Park with skate.-style Flick-It controls, and fight the fox
hunter with a wooden sword. Blender and Python generate the world, characters and animation; Unreal runs the game.
The story and setting are drafted in [docs/LORE.md](docs/LORE.md).

## Build and play

From the repository root (requirements in the [top-level README](../../README.md#requirements)):

```sh
uv run atelier fetch yorimichi      # the sound masters, once per machine
nice -n 10 uv run atelier build yorimichi  # development steps; only changed steps rerun
nice -n 10 uv run atelier play yorimichi   # native 1440 window, saved preferences honored
```

`uv run atelier build yorimichi --list` shows every step: world data and meshes (`world.*`), characters
(`characters.*`), sounds (`audio.*`), effects (`fx.textures`), the native skating data check (`skate.runtime`), the C++
module (`unreal.compile`), the Unreal imports (`unreal.*`) and the runtime data (`data.stage`). Name a step to build
just it and what it needs. A clean build exports and imports the required assets and compiles the editor; later builds
reuse completed steps. The community park and skate pier use committed GLBs from our asset library. Build stamps,
generated Content and the shared derived-data cache are kept for incremental work.

Packaging is explicit: `nice -n 10 uv run atelier build yorimichi unreal.package` plans a certified `unreal.cook` and download
assembly, and neither runs in an ordinary development build. Launcher edits and failed ZIP retries reuse the completed
cook. See [PACKAGING.md](docs/PACKAGING.md) for the guards, release files and independent download verification.

Play profiles (`--profile`, defined in [game.toml](game.toml)):

| Profile | What |
|---|---|
| `play`, `desktop` | the default desktop tuning: native 1440 window, forward renderer and optimized trees by default; saved menu choices are honored ([docs/DESKTOP_PERFORMANCE.md](docs/DESKTOP_PERFORMANCE.md)) |
| `fullscreen`, `desktop-1440` | the same tuning and preferences, fullscreen at native 1440 |
| `megapark`, `megapark-fullscreen` | the Super Ultra Mega Park in its own level |

Scenarios run against the game from another terminal: `uv run atelier qa yorimichi <scenario>` runs
[scenarios/](scenarios)`<scenario>.py`.

| Scenario | What |
|---|---|
| `skate_runtime`, `skatepark`, `skate_performance` | skating checks: controls, animation, mounting, bails and stances; the pier's banks, handrail and bowl; real-time frame pacing |
| `sailboat`, `zeppelin`, `lake` | regression checks and captures for the dinghy, the zeppelin stations and the woodland lake |
| `treehouse`, `treehouse_walk`, `treehouse_tour` | the tree house's reference views, a filmed walk through it and a camera tour |
| `skate_showreel`, `megapark_tour`, `megapark_access_film`, `megapark_ride_film` | filmed takes, with `*_mix.py` scripts to cut them |

## What is in the game

**World.** A painted world map with travel points ([docs/WORLD_MAP.md](docs/WORLD_MAP.md)) covers:

- the coastal road where the walk begins, [Momiji Hamlet](world/regions/village/README.md), the
  [houses on the main road](world/regions/houses/README.md) and the [mini-mega ramp](world/regions/mega/README.md);
- [Sunset Pier](world/regions/skatepark/README.md), a skate plaza on the sea below the road;
- the [woodland lake](world/regions/forest_lake/README.md) and its cabin;
- the city of [Hidamari](world/regions/hidamari/README.md): arcade, clock square, harbour, park, temple hillside and
  station;
- the [south-west](world/regions/southwest/README.md): fishing village, beach and island temple;
- the hidden [tree house](world/regions/treehouse/README.md) in the west hillside canopy
  ([docs/TREEHOUSE_PLAN.md](docs/TREEHOUSE_PLAN.md));
- the [Super Ultra Mega Park](docs/MEGAPARK.md) in the western foothills, reached by a forest trail or the zeppelin;
- the [community skate park](docs/COMMUNITY_PARK.md), with bowls, full pipes and tall vert above Hidamari station.

You get around on foot, in the [sailboat](assets/vehicles/sailboat/README.md), on the
[zeppelin](world/regions/zeppelin/README.md) between its three stations, or on the skateboard. Leaves, gulls and
villagers ([wanderer](assets/characters/wanderer/README.md)) keep the island moving.

**Cairo, the default player** ([assets/characters/cairo](assets/characters/cairo/README.md)): walk, run, sprint with stamina,
double jump, side hops and backflips, crouch, climb, swim, glide, wave and interact, with foot placement on slopes and
[footsteps by surface](docs/FOOTSTEPS.md). Controls are in [docs/CONTROLLER_CONTROLS.md](docs/CONTROLLER_CONTROLS.md);
the chase camera and its see-through in [docs/CAMERA.md](docs/CAMERA.md).

**Modori, the playable rival** ([assets/characters/modori](assets/characters/modori/README.md)): a tall, dark-haired
young man in a long coat with a Chaos Cloth skirt. His own rig carries the retargeted merged move set, sword and
paraglider, and the native skating runtime fits its rider pose to his body. After building the game, launch him with
`nice -n 10 uv run atelier play yorimichi -- -rider=Modori`.

**Sword** ([docs/SWORD_COMBAT.md](docs/SWORD_COMBAT.md)): draw and sheathe, a four-cut combo, a charged spin, guard and parry,
health and knock-downs. Hits carry trails, sparks, hit-stop, slow motion on parries, camera shake and sound
([docs/COMBAT_FEEDBACK.md](docs/COMBAT_FEEDBACK.md)).

**The fox hunter** ([docs/FOX_HUNTER_COMBAT.md](docs/FOX_HUNTER_COMBAT.md),
[docs/FOX_HUNTER_ANIMATION.md](docs/FOX_HUNTER_ANIMATION.md)) waits up the road from the start and fights with claws
and a kick, parries included.

**Skateboarding** ([docs/SKATE.md](docs/SKATE.md)) runs on the platform's native
[Skate plugin](../../platform/engine/Plugins/Activities/Skate/README.md): Flick-It tricks, grabs, manuals, grinds,
powerslides, pumping, vert and bails, with the solved rider retargeted onto Cairo every frame.

**Phone play**: `atelier stream yorimichi start` serves the [phone page](phone/README.md) (touch controls, the
painted map, settings) and the platform's plain player.

**Live workshop** ([docs/LIVE_WORKSHOP.md](docs/LIVE_WORKSHOP.md)): change the running game through the live bridge,
including props made from a sentence by `assets/props/make_prop.py`.

## Where things are

| Folder | What |
|---|---|
| `game.toml` | the game's description for Atelier: project, fetches, play profiles, streaming |
| `build.py` | the build recipe |
| `world/` | the island generator (`gen_world.py`), textures, props, foliage LODs, terrain, city tiles; `world/regions/*` one folder per region; `world/map/` the map tools and painted sheet |
| `assets/characters/` | the default player (`cairo`), playable rival (`modori`), sword trainer (`sword-trainer`), enemy (`fox-hunter`), villagers (`wanderer`), merged moves (`adventure`) and shared character [tools](assets/characters/tools/README.md) |
| `assets/audio/` | sound banks: fetch, slice and synthesis scripts (the sounds are built, not committed) |
| `assets/` (others) | effect sprites (`fx`), live-workshop props (`props`), the sailboat, concepts and sources for the houses, tree house, skate pier and Mega Park, and the skating runtime pins (`skate`) |
| `unreal/` | the Unreal project: `Source/Yorimichi` (C++), `Config`, `Scripts` (editor import scripts); `Content` is build output except the tracked native skating runtime data in `Content/Data/SkateNative` |
| `live/` | the live bridge's in-game Python and saved overlays |
| `scenarios/` | checks and films driven through the live bridge |
| `tests/` | Python and C++ tests for the skating data, the Mega Park and sprint stamina |
| `phone/` | the phone page served by `atelier stream` |
| `tools/` | the desktop profile launcher, benchmark, captures, fight film, concept and texture generators |
| [`animation_lab/`](animation_lab/README.md) | a local playground for text-to-motion models (UniMate, Kimodo) on the fox hunter's rig |
| `docs/` | how the game's systems work |

## Docs

| Area | Docs |
|---|---|
| World | [WORLD_MAP](docs/WORLD_MAP.md), [TREEHOUSE_PLAN](docs/TREEHOUSE_PLAN.md), [MEGAPARK](docs/MEGAPARK.md), [CAMERA](docs/CAMERA.md), [DESKTOP_PERFORMANCE](docs/DESKTOP_PERFORMANCE.md) |
| Play | [CONTROLLER_CONTROLS](docs/CONTROLLER_CONTROLS.md), [SKATE](docs/SKATE.md), [FOOTSTEPS](docs/FOOTSTEPS.md), [LIVE_WORKSHOP](docs/LIVE_WORKSHOP.md) |
| Combat | [SWORD_COMBAT](docs/SWORD_COMBAT.md), [FOX_HUNTER_COMBAT](docs/FOX_HUNTER_COMBAT.md), [COMBAT_FEEDBACK](docs/COMBAT_FEEDBACK.md) |
| Multiplayer | [Implementation, verified scope and test handoff](docs/MULTIPLAYER.md) |
| Characters and animation | [GRIPS: pose a hand and correct its contact](docs/GRIPS.md), [BODY_SWAP_GUIDE](docs/BODY_SWAP_GUIDE.md), [MIXAMO_WORKFLOW](docs/MIXAMO_WORKFLOW.md), [H3_ANIMATION_REFERENCE_WORKFLOW](../../docs/H3_ANIMATION_REFERENCE_WORKFLOW.md), [ANIMATION_PRINCIPLES](../../docs/ANIMATION_PRINCIPLES.md), [FOX_HUNTER_ANIMATION](docs/FOX_HUNTER_ANIMATION.md), [UNIMATE_EXPERIMENT](docs/UNIMATE_EXPERIMENT.md), [KIMODO_EXPERIMENT](docs/KIMODO_EXPERIMENT.md) |
| Story | [LORE](docs/LORE.md) |

## Names in the code

The player is Cairo: `assets/characters/cairo`, `/Game/Cairo` and `ACairoCharacter`, built on `AWandererCharacter`.
Most other game classes and console variables carry the `Japan` prefix (`AJapanWorld`, `japan.SeeThrough`), and the
island's Unreal content is under `/Game/Japan`.
