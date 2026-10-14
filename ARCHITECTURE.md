# Architecture

Atelier is the shared part of every game made here. Games use it; it never uses a game.

```
games/            each game: world, characters, look, sounds, tuning, its own C++ module
  yorimichi/      the full game
  sandbox/        a plain game made only of platform parts, and the template for `atelier new`
platform/
  studio/         the `atelier` command and Python package: build, play, live, QA, AI helpers, review, safety
  engine/Plugins/ Unreal plugins any game can switch on
  web/            stream pages, motion helpers, the Rust/React agent board and board-world
  conventions/    units, the humanoid bone contract, clip roles, sound cue names, naming
build/            ignored: everything a build generates, per game
```

## The platform

| Piece | Where | What |
|---|---|---|
| `atelier` command | `platform/studio/atelier` | `new`, `doctor`, `setup`, `fetch`, `build` (incremental steps/products), `reuse`, `pool`, `play` (profiles), `playtest`, `stream`, `live`, `qa`, `lint`, `contracts`, `capacity` (shadow plans), `board`; the lock and memory guard around heavy processes (`atelier.safety`) |
| AI and review tools | `platform/studio/atelier/{ai,review,blender}`, `platform/studio/node` | Tripo, Sunburst, H3 and Seedance helpers, the paid-call ledger, the UniMate and Kimodo runners, contact sheets, glTF previews |
| Conventions | `platform/conventions` | units and axes, humanoid bones, clip roles, sound cues, naming |
| AtelierCore | `engine/Plugins/AtelierCore` | runtime data files (`AtelierDataPath`), sprint stamina |
| AtelierAnimation | `engine/Plugins/AtelierAnimation` | ground contact, sailboat stance and bike grip animation nodes |
| AtelierFX | `engine/Plugins/AtelierFX` | sprites, light flashes, hit-stop, slow motion, camera shake, sound cues, blade trails |
| Skate | `engine/Plugins/Activities/Skate` | in-process skateboarding behind `ISkateRider`, with its tracked data checks |
| AtelierStream | `engine/Plugins/Streaming` | the game's end of a browser stream: actions and leased touch controls |
| LiveBridge | `engine/Plugins/Dev/LiveBridge` | the loopback live bridge: Python in the running game, runtime GLB props, overlays |
| Stream pages | `platform/web/stream` | stream server, browser connection, page lifecycle, touch primitives, the plain player, smoke-test helpers |
| Motion helpers | `platform/web/motion` | Three.js helpers that capture a rig's rest pose, apply generated motion to an existing skin and close authored loops |
| Agent board | `platform/web/board`, `platform/web/board-world` | Rust coordination server, React web UI and world view |

Systems that only one game uses stay in that game. In Yorimichi these are the player character (on-foot movement,
actions, camera), sword combat and the fox hunter, the sailboat, the zeppelin, the mini-mega ramp, footsteps, the
world map, preferences and the HUD.

## Rules

1. **Dependencies point down.** Games use the platform, never the reverse. Mechanics use the base plugins, never
   the reverse. `atelier lint` fails if a file under `platform/` names a game.
2. **Games give data, not code changes.** Speeds, timings, colours, clip names and sounds reach the platform as data
   (`game.toml`, manifests, `Config/DefaultGame.ini` sections).
3. **Behaviour comes in through named extension points**: interfaces such as `ISkateRider` and `IAtelierFXTarget`,
   clip roles, sound banks, touch layouts, build steps and scenarios.
4. **The sandbox stays green.** It is built from platform parts only, so it must still build and play after every
   platform change.
5. **Things graduate on evidence.** A mechanic starts inside a game, becomes experimental in the platform when a
   second game wants it or it runs in the sandbox, and stable when two games use it with docs and tests.
6. **Contracts are versioned.** The bone contract, clip roles and manifest formats carry a version; a breaking change
   ships with the update for every game in the same commit.
7. **Keep the base small.** AtelierCore holds only what every game needs.
8. **Every plugin explains itself** in a README: what it does, what the game provides, its settings and how to test it.
9. **Licences travel with assets.** Every manifest names its licence.

## Files

- Manifests are **TOML** (`game.toml`, `character.toml`, `bank.toml`, `asset.toml`): Python 3.11+ reads TOML without
  extra packages, so the same files are readable from the `atelier` command, from Blender's Python and from Unreal's.
- Binary sources (character `.blend` files, painted images, fonts) are committed directly while they stay small. Only
  the current revision of a source is in git; older revisions, captures and takes live in an archive outside git.
- Coordinates: sources are in metres with Z up; Unreal is in centimetres with Y flipped
  ([platform/conventions/units.md](platform/conventions/units.md)). One converter: `atelier.conventions.to_unreal`.

## Build products

The [recipe guide](docs/BUILD_RECIPES.md) covers named products, content-based read dependencies and read-only build
plans, file-hash memoization and automatic local caching of portable products. The
[incremental build architecture](docs/INCREMENTAL_BUILDS.md) describes the remaining native import and remote storage
migration. [World build practices](docs/WORLD_BUILD_PRACTICES.md) explain how to structure asset libraries,
terrain and regions for small rebuilds. Proposed features are marked; the [artifact pool](docs/ARTIFACT_POOL.md)
documents automatic cache maintenance alongside the older explicit reuse commands.
The related [capacity admission proposal](docs/BUILD_CAPACITY.md) describes replacing fixed execution slots with
measured resource reservations while preserving memory guards and exclusive-resource locks.

## Why the studio is Python

Blender's only scripting language is Python, and Unreal's editor scripting is Python too, so one language covers the
command line, Blender and Unreal, and the house rules exist once. The shared core (`atelier.conventions`,
`atelier.paths`, `atelier.manifest`) uses only the standard library so it runs in all three interpreters; Blender code
(`atelier.blender`) is only loaded inside Blender. C++ is for the games and plugins, JavaScript for browser pages, and
Node where libraries require it (Pixel Streaming, AI gateway and contract checking), and Rust for the board server.
