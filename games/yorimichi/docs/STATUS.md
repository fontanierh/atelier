# Yorimichi (Japan project)

> Moved from the prototype repository on 29 September 2026. Paths are translated to this repository where the file moved; paths still starting with `japan/` or `output/imagegen/` refer to the prototype archive (authoring tools, earlier revisions, review images). See [docs/MIGRATION.md](../../../docs/MIGRATION.md).

A painterly Japanese island in Unreal 5.8. Blender and Python generate the art, layout and animation; Unreal
runs the game. The direction is a sword brawler where spirits come out of openings across the island
([docs/LORE.md](docs/LORE.md), draft, not approved).

This page is the current state and an index. Updated 24 September 2026. Details belong in the linked docs.

## What is in the game

**World.** An 18-zone map with travel ([docs/WORLD_MAP.md](docs/WORLD_MAP.md)):

- the coastal spawn road, [Momiji Hamlet](village/README.md) and the [mini-mega ramp](mega/README.md)
- the [skate pier](skatepark/README.md): a concrete plaza with quarter pipes, a kicker, a funbox, stairs with a
  handrail and hubba, flat bars, ledges and a manual pad, on the sea below the spawn road
- the [woodland lake](docs/forest_lake/README.md)
- the [Hidamari city](hidamari/README.md): arcade, plaza, harbor, park and station, with residents but no
  interiors
- the [southwest](southwest/README.md) fishing village, beach and island temple
- the hidden [tree house](../world/regions/treehouse/README.md) on the west hillside: one small hut seen from the
  trail, then ten places in the canopy joined by twelve rope bridges, with furnished rooms, a slide and a lookout
  ([plan](TREEHOUSE_PLAN.md), [items](TREEHOUSE_ITEMS.md))

Ways to get around besides walking: a playable [sailboat](sailboat/README.md) and the
[zeppelin](docs/zeppelin/README.md) between the woodland and Hidamari. Ambient life: leaves, gulls and
villagers.

**Player: Cairo**, revision `game-r17`. Assets are in
`output/imagegen/yorimichi-yellow-boy-2026-09-12/`.

- Outfit: the Tripo skate outfit, a yellow tee and cargo trousers ([body swap guide](docs/WARM_ORIGINAL_BODY_SWAP_GUIDE.md)).
- Movement: walk, run (Sprint at 0.8×), sprint with stamina rings, double jump, ground and air dash, chained
  rolls, crouch, wave, interact, foot placement on slopes, and footsteps that follow the surface
  ([docs/FOOTSTEPS.md](docs/FOOTSTEPS.md)).
- Sword: draw and sheathe, a three-hit chain, hold to cut then charge, a parry, and health with a knock-down
  ([docs/SWORD_COMBAT.md](docs/SWORD_COMBAT.md)). The combat-r02 clips (game-r15) don't spin and are fast.
  With the sword out, the sword arm swings with walk, run and sprint (game-r16).
- Combat feedback: slash trails, sparks, flashes, hit-stop, slow motion on parries, camera shake, dust, the fox
  burning away into embers, combat sounds and a countryside ambience
  ([docs/COMBAT_FEEDBACK.md](docs/COMBAT_FEEDBACK.md)). `games/yorimichi/tools/film_fight.sh` films a scripted fight.
- Skateboarding (game-r17): skate.-style controls with Flick-It on the right stick or the mouse, fourteen flip and
  shove tricks with nollie and fakie versions, spins, grabs, manuals, grinds and slides, powerslides, vert, bails and
  board sounds; B (or Triangle / Y) to get on ([docs/SKATE.md](docs/SKATE.md)).
- Imported but not used in play: Climb, Glide and the Turn clips.
- The class and launch name `cape_boy` / `ACairoCharacter` is historical and loads Cairo.

**Enemy: the fox hunter**, animation `r05`. It waits up the road from the start and fights with claws and a
kick, parries included ([docs/FOX_HUNTER_COMBAT.md](docs/FOX_HUNTER_COMBAT.md)). It has no navigation.

**NPC:** the Wanderer ([characters/wanderer](characters/wanderer/README.md)).

**Live workshop:** the agent changes the running game without a rebuild ([docs/LIVE_WORKSHOP.md](docs/LIVE_WORKSHOP.md)).
A loopback bridge runs Python in the game, loads GLBs at runtime on the painterly material and reloads saved
overlays on every start. `games/yorimichi/assets/props/make_prop.py` turns a sentence into a Sunburst concept, then a Tripo model.

Nothing in the character or combat set is user-approved yet except where a doc says so.

## Build and play

From the repository root:

```sh
atelier build yorimichi unreal.compile          # compile the Unreal module
atelier play yorimichi           # game window (deferred renderer, 1080p)
atelier play yorimichi --profile desktop-1440   # desktop profile: forward renderer, native 1440p, 60 fps cap
```

Other modes:

- `assets` + `setup`: regenerate the world art and rebuild the level. These are slow and only needed for world
  changes.
- `hidamari`, `southwest`, `village`, `mega`, `zeppelin`, `sailboat`: rebuild and import one area.
- `cairo`: full character export and import. Then add the sword with `Scripts/import_cairo_sword.py`.
- `footsteps`, `map`, `test`, `gate`: see the header of `run.sh`.

For a change to a few clips, use the targeted route in
[game-r14/README.md](../output/imagegen/yorimichi-yellow-boy-2026-09-12/game-r14/README.md)
(`tools/cairo_game_clip_transfer.py` + `Scripts/import_cairo_clips.py`). It does not re-import the whole
character. Unreal content is generated locally and not committed.

## Pipelines and where they are written up

| Area | Docs |
| --- | --- |
| World generation | `gen_textures.py`, `build_assets.py`, `build_foliage_lods.py`, `gen_world.py`, `build_terrain.py`, `Scripts/setup_project.py`, `AJapanWorld` |
| Rendering and performance | [docs/DESKTOP_PERFORMANCE_2026_09_14.md](docs/DESKTOP_PERFORMANCE_2026_09_14.md) (current), [docs/WARM_ORIGINAL_STREAM_PERFORMANCE.md](docs/WARM_ORIGINAL_STREAM_PERFORMANCE.md) (phone), [docs/desktop-quality/](docs/desktop-quality/README.md); history in [AUDIT.md](AUDIT.md), [PERFORMANCE.md](PERFORMANCE.md), [PERFORMANCE_60FPS.md](PERFORMANCE_60FPS.md), [VISUAL_POLISH.md](VISUAL_POLISH.md), [GATE.md](GATE.md) |
| Phone streaming | [streaming/README.md](streaming/README.md) |
| New characters through Tripo | [docs/TRIPO_P2_ASSET_WORKFLOW.md](docs/TRIPO_P2_ASSET_WORKFLOW.md), [docs/ASSET_API_REVIEW_PROCESS.md](docs/ASSET_API_REVIEW_PROCESS.md), Smart UV: [docs/TRIPO_SMART_UV_API_RESEARCH.md](docs/TRIPO_SMART_UV_API_RESEARCH.md) |
| Cairo character | [docs/WARM_ORIGINAL_GAME_INTEGRATION.md](docs/WARM_ORIGINAL_GAME_INTEGRATION.md) (history to game-r10), [docs/WARM_ORIGINAL_BODY_SWAP_GUIDE.md](docs/WARM_ORIGINAL_BODY_SWAP_GUIDE.md), garment trials: [docs/GARMENT_MESH_SWAP_TRIAL.md](docs/GARMENT_MESH_SWAP_TRIAL.md) |
| Animation | [docs/ANIMATION_PRINCIPLES.md](docs/ANIMATION_PRINCIPLES.md), [docs/MIXAMO_WORKFLOW.md](docs/MIXAMO_WORKFLOW.md), [docs/H3_ANIMATION_REFERENCE_WORKFLOW.md](docs/H3_ANIMATION_REFERENCE_WORKFLOW.md), [docs/FOX_HUNTER_ANIMATION.md](docs/FOX_HUNTER_ANIMATION.md) |
| Audio | [docs/FOOTSTEPS.md](docs/FOOTSTEPS.md), [audio/combat/README.md](audio/combat/README.md), [docs/COMBAT_FEEDBACK.md](docs/COMBAT_FEEDBACK.md), [docs/SOUND_RESEARCH.md](docs/SOUND_RESEARCH.md) |
| Review tools | Asset Studio (`studio/README.md` at the repository root), [docs/ASSET_REVIEW_TAILSCALE.md](docs/ASSET_REVIEW_TAILSCALE.md) |
| Design | [docs/LORE.md](docs/LORE.md), [docs/IDEAS.md](docs/IDEAS.md) |

Revision history lives in each asset folder's README. Older handoff notes (`CLAUDE_*`, `WARM_ORIGINAL_*`
revision notes, `CHARACTER_POLISH.md`) describe the state when they were written. If one disagrees with this
page, this page and the newest revision README win.

## Open work

- **Combat animations:** combat-r02 fixed the facing and the speed. Still open: the support hand drifts off
  the grip during the charge raise, the tassel doesn't move, and there's no dedicated block or sword idle
  source ([docs/SWORD_COMBAT.md](docs/SWORD_COMBAT.md)). Not reviewed by the user yet.
- **Combat systems:** no attack buttons on the phone, no fox navigation, and damage and timings not tuned.
  Nobody has listened to the combat sounds yet.
- **Characters:** the skate outfit has sleeve and trouser crossings and no corrective shapes. The jacket is
  on hold with 13 QA blockers. The female mechanic is unrigged, and Tripo Smart UV is blocked by membership.
- **Audio:** footsteps, combat sounds and an ambience loop, all recorded (Sonniss). No music or other world
  sounds yet.
- **World:**
  - road and terrain clearance
  - the road-distance field only covers ±20 m around the road
  - collision is not consistent
  - world data is loaded from the loose `out/world.json`
  - no level streaming
  - the forward-desktop acceptance checks are not closed, and the distant-forest cost is unresolved
- **Parked branches:** `perf/foliage-coverage-1440` (leaf-card trimming, GPU savings not measured) and
  `codex/hidamari-buildings` (one audit commit).
