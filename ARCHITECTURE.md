# Architecture

Atelier is the shared part of every game made here. Games use it; it never uses a game. A game runs on Unreal
Engine 5.8 or on Bevy; the `atelier` command is the same for both, and [engines](docs/ENGINES.md) says what differs.

```
games/            each game: world, characters, look, sounds, tuning, its own C++ module
  yorimichi_v2/   the active Unreal game, with committed editable Content and targeted authoring
  yorimichi/      retired V1 donor/reference; its old build and tests are not the V2 workflow
  sandbox/        a plain game made only of platform parts, and the Unreal template for `atelier new`
  hakuba/         retired Bevy experiment retained as reference
platform/
  studio/         the `atelier` command and Python package: build, play, live, QA, AI helpers, review
  engine/Plugins/ Unreal plugins any game can switch on
  harness/        agent board, session delivery, capacity admission and guarded processes
  web/            stream pages and motion helpers
  conventions/    units, the humanoid bone contract, clip roles, sound cue names, naming
build/            ignored: everything a build generates, per game
```

## The platform

| Piece | Where | What |
|---|---|---|
| Studio | `platform/studio/atelier` | The `atelier` CLI, incremental builds/products, verified reuse, game launch, live QA and releases |
| Engines | `platform/studio/atelier/engines`, `platform/studio/templates` | What differs per engine: doctor checks, play launch, live/stream support, `atelier new` templates |
| Harness | `platform/harness` | Durable board messages, session delivery, resource admission and process guards (`atelier.harness`) |
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
| Agent board | `platform/harness/web`, `platform/harness/world` | Rust coordination server, React web UI and world view |

Systems that only one game uses stay in that game. In Yorimichi V2 these are the player character (on-foot movement,
actions, camera), sword combat and the fox hunter, the sailboat, the bike, the horse, the zeppelin, the mini-mega
ramp, footsteps, the world map, preferences and the HUD. Horse racing rules are owned by
`games/yorimichi_v2/unreal/Plugins/HorseRacing`; the plugin and module names stay stable for
Unreal discovery and reflected type compatibility.

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

Yorimichi V2 commits its editable Unreal packages in Git LFS. Its normal build validates and compiles;
explicit targeted import/save routes own package changes, with claims and verification records. It does not
use whole-game generation/reuse as an authoring substitute. The [V2 README](games/yorimichi_v2/README.md)
and [inventory](games/yorimichi_v2/docs/INVENTORY.md) describe the completed migration, on-demand authoring and
remaining gameplay/visual acceptance. A recovered source or saved object is not a claim that its model already
has an independent generator; that route is required before changing the selected generated model's geometry.
The generated-product mechanisms below remain relevant to the sandbox and other retained platform uses.

The [recipe guide](docs/BUILD_RECIPES.md) covers named products, content-based read dependencies and read-only build
plans, historical phase timings, certified-output differences and retained-log DDC diagnostics, file-hash
memoization, bounded Blender/editor batches, automatic portable-product caching and opt-in Python input/write
auditing. Recipe-declared spatial queries provide frozen matched-product reads; the sandbox exercises them without
native tools. Whole-build reuse certifies named inventories and blocks launch while its copy journal is incomplete. The
[incremental build architecture](docs/INCREMENTAL_BUILDS.md) describes the remaining native import and remote storage
migration. [World build practices](docs/WORLD_BUILD_PRACTICES.md) explain how to structure asset libraries,
terrain and regions for small rebuilds. Proposed features are marked; the [artifact pool](docs/ARTIFACT_POOL.md)
documents automatic cache maintenance, signed bundle ingestion, optional HTTPS lookup, explicit verified public-V2
bundle upload and the older explicit reuse commands.
Imports require pinned publisher keys, explicit redistribution grants and complete byte verification;
an operator-controlled producer can freshly build an independent audited Python action and export a signed
directory. Automatic publication and hostile-source signer isolation remain separate work.
The [Harness capacity guide](docs/BUILD_CAPACITY.md) covers resource reservations, named locks and guarded process
ownership. A supervised Unix broker admits configured build/play clients; offline plans and shadow simulations do
not grant admission. Full mode allows compatible jobs to overlap without manual slot coordination. Legacy slots,
the migration bridge and sealed maintenance remain distinct supported modes; machine activation is explicit and
clients must never fall back after a configured broker refusal.

## Why the studio is Python

Blender's only scripting language is Python, and Unreal's editor scripting is Python too, so one language covers the
command line, Blender and Unreal, and the house rules exist once. The shared core (`atelier.conventions`,
`atelier.paths`, `atelier.manifest`) uses only the standard library so it runs in all three interpreters; Blender code
(`atelier.blender`) is only loaded inside Blender. C++ is for the games and plugins, JavaScript for browser pages, and
Node where libraries require it (Pixel Streaming, AI gateway and contract checking), and Rust for the board server.
