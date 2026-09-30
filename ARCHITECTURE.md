# Architecture

Atelier is the shared part of every game made here. Games use it; it never uses a game.

```
games/            each game: world, characters, look, sounds, tuning, its own little C++
  yorimichi/
  sandbox/        a plain game made only of platform parts; proves the platform stands alone
platform/
  studio/         the `atelier` command and Python package: AI, Blender, build, import, tests, review
  engine/Plugins/ Unreal plugins any game can switch on
  conventions/    units, the humanoid bone contract, clip roles, sound cue names, formats
  library/        generic assets any game may borrow
build/            ignored: everything a build generates, per game
```

## What exists today

The table below is the platform as built (29 September 2026); the rest of this page is the target it grows toward.

| Piece | Where | What | Used by |
|---|---|---|---|
| `atelier` command | `platform/studio/atelier` | `doctor`, `fetch`, `build` (incremental steps), `play` (profiles), `stream`, `live`, `qa`, `lint`; render lock (one big slot, optionally a small one beside it) and memory guard around every heavy process | both games |
| AI and review tools | `platform/studio/atelier/{ai,review,blender}`, `platform/studio/node` | Tripo, Sunburst, H3 and Seedance helpers, contact sheets, glTF previews | Yorimichi's authoring tools |
| Conventions | `platform/conventions` | units, humanoid bones, clip roles, sound cues, naming | the studio, Yorimichi's characters |
| AtelierCore | `engine/Plugins/AtelierCore` | runtime data files (`AtelierDataPath`), sprint stamina | Yorimichi, sandbox |
| AtelierAnimation | `engine/Plugins/AtelierAnimation` | ground contact, skate rider and sailboat stance anim nodes | Yorimichi |
| AtelierFX | `engine/Plugins/AtelierFX` | sprites, light flashes, hit-stop, slow motion, shake, sound cues, blade trails | Yorimichi (sword) |
| Skate | `engine/Plugins/Activities/Skate` | skate.-style skateboarding behind `ISkateRider` | Yorimichi |
| AtelierStream | `engine/Plugins/Streaming` | the game's end of a browser stream: actions and leased touch controls | Yorimichi's phone page |
| LiveBridge | `engine/Plugins/Dev/LiveBridge` | the loopback live bridge: Python in the game, runtime GLB props, overlays | Yorimichi, sandbox |
| Stream pages | `platform/web/stream` | stream server, browser connection, touch primitives, the plain player | Yorimichi, sandbox |

Still inside Yorimichi, to move when a second game needs them: the player character (on-foot movement, actions,
camera), sword combat and the fox hunter, the sailboat, the zeppelin, the mini-mega ramp, footsteps, the world map,
preferences and the HUD. The old cruiser skateboard, the mini-mega ride and five rendering experiments were removed
(29 September): their assets stayed in the prototype archive, so nothing could reach them.

## Who owns what

| Concern | Atelier provides | The game provides |
|---|---|---|
| Characters | The pipeline (concept, model, rig, fingers, pose authoring, checks, export), the humanoid contract | Its characters, outfits and every clip's poses |
| Animation in game | The C++ graph base, foot placement, transitions, IK nodes, clip lookup by role | Each character's clip table |
| Movement | The player shell and activities: on foot, skate, sail, ride | Which activities are on, and their tuning |
| Combat | Hits, parries, health, lock-on, the enemy shell, hit effects | Timing windows, enemy brains, combo design |
| World | Terrain, scatter, clearance, foliage and LOD generators, the region spawner, water, wind | The island, regions, building kits, scatter rules, the map |
| Look | Material graph builder, material families, post-process plumbing | The painterly settings, haze, palette, sky, sun |
| Sound | Banks, cue lookup, footsteps by surface, mixing, fetch and slice tools | Its banks: sounds for platform cues, plus its own cues |
| Streaming | `atelier stream`: picture and sound to a browser on any device; the plain player sends that device's keyboard, mouse and controller as normal input | Its protocol name, video size, extra routes |
| Touch | Touch primitives (stick, look pad, hold buttons and axes) and a leased message channel | Its touch page: layout, panels, what each button does |
| Testing | Live bridge, scenario runner, capture, film mixer, benchmark | Its scenarios |

## Rules

1. **Dependencies point down.** Games use the platform, never the reverse. Mechanics use the base plugins, never
   the reverse. `atelier lint` fails if a platform file names a game, a game path or a game's `/Game/...` asset.
2. **Games give data, not code changes.** Speeds, timings, colours, clip names and sounds reach the platform as data.
3. **Behaviour comes in through named extension points**: activity, enemy brain, region feature, look, HUD widget,
   clip builders, scenario steps, sound banks, touch layouts.
4. **The sandbox stays green.** Every platform plugin has sandbox scenarios.
5. **Things graduate on evidence.** A mechanic starts inside a game (a game-local plugin), becomes experimental in the
   platform when a second game wants it or it runs in the sandbox, and stable when two games use it with docs and tests.
6. **Contracts are versioned.** Bone contract, clip roles and manifest formats carry a version; a breaking change ships
   with a migration for every game in the same commit.
7. **Keep the base small.** AtelierCore knows players, activities, input, camera and settings; nothing more.
8. **Every plugin explains itself** in a README: what it does, its extension points, tuning fields and scenarios.
9. **Licences travel with assets.** Every manifest names its licence; the library only takes assets that are safe for
   every game and every tool.

## Files

- Manifests are **TOML** (`game.toml`, `character.toml`, `bank.toml`, `asset.toml`): Python 3.11+ reads TOML without
  extra packages, so the same files are readable from the `atelier` command, from Blender's Python and from Unreal's.
- Sources that are binary (character `.blend` files, painted images, fonts) are committed directly while they stay
  small. Old revisions, captures and trailer takes live in an archive outside git.
- Coordinates: sources are in metres with Z up; Unreal is in centimetres with Y flipped
  (`platform/conventions/units.md`). One converter, `atelier.conventions.to_unreal`.

## Why the studio is Python

Blender's only scripting language is Python, and Unreal's editor scripting is Python too, so one language covers the
command line, Blender and Unreal, and the house rules exist once. The shared core (`atelier.conventions`,
`atelier.paths`, `atelier.manifest`) uses only the standard library so it runs in all three interpreters; host code
(`atelier.blender`, `atelier.unreal`) is only loaded inside its host. C++ is for the game, JavaScript for browser pages,
and Node only where a library requires it (Pixel Streaming's frontend and signalling, the AI gateway client).
