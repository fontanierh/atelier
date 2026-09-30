# Skateboarding (flick-it, game-r17)

> Moved from the prototype repository on 29 September 2026. Paths are translated to this repository where the file moved; paths still starting with `japan/` or `output/imagegen/` refer to the prototype archive (authoring tools, earlier revisions, review images). See [docs/MIGRATION.md](../../../docs/MIGRATION.md).

Skateboarding comes back for the player (Cairo) with controls modelled on EA's *skate.* series: the left stick
steers and spins, the right stick does every trick (**Flick-It**), the triggers grab. This page is the design and the
contract between the skating runtime, Cairo and the skate pier. The recovered Rust Session supplies physics and
animation when its local data is installed; the standalone C++ controller port and game-r17 clips are the fallback.

C++ fallback validation (30 Sep 2026): the ride, retail Flick-It with thirty named ollie/nollie tricks and
their fakie versions, spins, grabs, manuals, grinds and slides on rails, ledges and coping, powerslides, vert,
bails, sounds, the rider clips (game-r17) and the skate pier all work in the game; `games/yorimichi/scenarios/skate.py` passes 22/22
against the running game. A filmed run is in `build/yorimichi/skatefilm/<take>/showreel.mp4` (see Checks).
`-skatedebug` logs every change of mode with its reason and the wheel probes.

Not done: skate controls on the phone page (skate through the plain player at `/play/` with a controller), switch stance (fakie is
supported), tweaked grabs and lip tricks. The painted world map does not show
the pier; its travel pin does.

## Recovered runtime

The full Rust session can now supply the board/rider constraint solver, animation graphs, tricks, scoring and
camera. Cairo receives the solved pose through a reference-pose retargeter, and the board parts follow native
bones. Retargeting preserves Cairo's bone lengths and shoe scale, then fits foot contacts with leg IK.
The original C++ system below remains the fallback when the runtime data/executable are absent, or when
`UseRetailRuntime=false` is set under `[/Script/AtelierSkate.SkateSettings]`. Its 22/22 QA result above applies to
that fallback; the complete-session smoke check is separate.

Install once from the repository root (the local disc data stays in ignored Content):

```sh
python3 games/yorimichi/tools/import_skate_runtime.py --game /path/to/extracted/game --engine /path/to/skate-3-rust-engine
python3 games/yorimichi/tools/build_skate_runtime.py --toolchain 1.97.1
uv run atelier build yorimichi unreal.compile
python3 games/yorimichi/tools/check_skate_runtime.py
# With the game running and runtime installed:
uv run atelier qa yorimichi skate_runtime
```

The upstream tools checkout must contain `tools/asset_pipeline`; the disc folder contains `default.xex` and
`data/`. Rust >=1.95 is needed to build; omit `--toolchain` if the default Rust is recent enough. Source crates and
Cargo.lock are vendored, so building the worker needs no further upstream Git checkout. The first mount loads
animation banks for several seconds; subsequent rides reuse the process. The ordinary Unreal build does not
invoke Cargo or the importer. Live `skate_state()` includes `retail=<physical state> tick=<number>` when active.
The importer was verified with upstream tools commit `60efdef86600d8d8d4feb4b7c608fa0efd0643d7`.

The complete backend currently targets editor builds with static mesh CPU buffers. Nearby render triangles and
registered rails become its collision world; dynamic obstacles, detailed surface materials and packaged mesh
buffer retention remain follow-ups. See the exact boundaries and provenance in
[NATIVE_PORT.md](../../../platform/engine/Plugins/Activities/Skate/NATIVE_PORT.md).

## Native controller fallback

The Rust-engine port and its exact scope are documented in the plugin's
[NATIVE_PORT.md](../../../platform/engine/Plugins/Activities/Skate/NATIVE_PORT.md).
Retail tuning and all 78 input-pattern variants are committed C++ data; no extracted game is needed for this backend.
`Difficulty=normal` (also `easy`, `hardcore`) and `TruckTightness=0.5` live under
`[/Script/AtelierSkate.SkateSettings]`. The old sector-gesture and random-balance descriptions are superseded by this port.

## Controls, Flick-It and physics

They belong to the platform's Skate plugin: [platform/engine/Plugins/Activities/Skate/README.md](../../../platform/engine/Plugins/Activities/Skate/README.md).
Yorimichi's side: `AWandererCharacter` is the `ISkateRider` (clips from its definition's `SkateActions`, the sword
sheathed on mounting, the menu and the map take the board's input), `UJapanCharacterMovement` runs the skate movement
mode, `ASkatePark` and the road guardrails add the rails, and `[/Script/AtelierSkate.SkateSettings]` in
`unreal/Config/DefaultGame.ini` names the board, the sounds and the world's surface materials.

## Rider clips (Blender, game-r17)

Authored on the game-r16 revision with `games/yorimichi/assets/characters/tools/cairo_rig.py`, saved as game-r17 with manifest roles, exported with
`games/yorimichi/assets/characters/cairo/export_unreal.py -- --revision game-r17 --clips <list> --clips-only --report export-skate.json` and
installed by `Scripts/import_cairo_skate.py` into `DA_Cairo.SkateActions`.

**Frame.** The rig faces +X (Blender), left +Y, up +Z; the Root bone stays at the origin on the ground. The board lies
across the rider: its long axis along Y with the **nose toward +Y (regular: left foot forward)**, the toe edge toward
+X, **deck top at Z = 9.05 cm**, deck centre above the origin. In every clip the board is at this rest place; the game
moves it (pop, manual tilt, flips) and moves the feet with it.

**Board on screen.** A board 9 cm over the ground at speed left a speckled halo and a ghost copy of itself on the
ground: Lumen's short-range AO counted it as a wall down to the ground, and its temporal history lagged behind. Short-
range AO now ignores occluders floating more than 4% of the pixel's depth in front
(`r.Lumen.ScreenProbeGather.ShortRangeAO.HorizonSearch.ForegroundSampleRejectDistanceFraction=0.04`, engine default
0.3); the landscape changes by 2-4 grey levels inside foliage. A faint TAA trail of the deck remains at speed.
(Switching `r.Lumen.ScreenProbeGather.ShortRangeAO.Temporal` off at runtime crashes UE 5.8's renderer.)

**Board (cm, deck-local: origin at the centre of the deck top, +X nose, +Y toe side, +Z up).** Deck 80 × 20.5, kicks
rise over the last 13 cm to +4.5 cm at the tips (x = ±40), concave 0.9 cm, thickness 1.2. Truck kingpins at x = ±18
(the wheelbase is 36), axles at z = -6.35, wheel centres at y = ±9.3, wheel radius 2.65 (ground at z = -9.05). In the
Blender rider frame, deck-local (x, y, z) is (y, x, z + 9.05).

**Foot spots on the deck (deck-local).** Riding: front foot centre (+16, +1), back foot (-21, +1). Ollie load: back
foot's ball on the tail (-31, +1) on the kick, front foot just behind the front bolts (+8, +1). Nollie load: front
foot's ball on the nose (+31, +1), back foot (-8, +1). Front foot turned about 55° from the board axis toward the nose,
back foot about 80°, toes toward the toe edge (+Y deck-local). Soles on the grip, no penetration.

**Contacts.** For each clip the manifest lists, per foot and per hand, the intervals when it is on the board. The game
maps those limbs through the board's current transform (IK) and leaves the others to the clip.

**Clips** (60 fps; loops must close; goofy versions are the regular ones mirrored, suffix `Goofy`):

| Role | Length | What it is |
| --- | --- | --- |
| SkateStance | 2.0 s loop | riding stance: knees soft, weight centred, arms relaxed and a little away from the body, palms toward the body, head turned to the nose; slow breathing sway |
| SkateStanceFakie | 2.0 s loop | the same, looking back over the right shoulder toward the tail |
| SkatePush | 1.0 s loop | front foot turns to point along the board, body turns forward, back foot plants on the ground on the toe side beside the front truck (plant 0.30 s), strokes back 44 cm (release 0.62 s), lifts and returns to the tail; ends in the stance |
| SkateBrake | 0.4 s, then hold the last frame | back foot slides off the tail and drags its sole flat on the ground behind, weight on the front leg |
| SkateCrouch | 0.2 s hold | the ollie load: deep crouch, back foot on the tail, front foot behind the front bolts, arms a little forward |
| SkateNollieCrouch | 0.2 s hold | the nollie load, front foot on the nose |
| SkateOllie | 0.45 s | pop and rise, from SkateCrouch to the air tuck: back ankle snaps (board pitches nose-up about the rear wheels, 30° at 0.05 s, level again at 0.24 s), front foot drags up the grip to (+24, +1) by 0.20 s, knees pull up; ends in SkateAir |
| SkateNollie | 0.45 s | the same popped from the nose |
| SkateAir | 1.0 s loop | the air tuck: knees up (feet on the deck, pelvis about 18 cm lower than in the stance), arms out for balance, eyes ahead and down |
| SkateFlip | 0.45 s | the flick for flip tricks and shove-its, from SkateAir: both feet leave the deck by 0.08 s (front foot kicks forward and up, back foot up), about 15 cm above the grip at 0.2 s, come back down to catch at 0.38 s; ends in SkateAir |
| SkateLand | 0.35 s | touchdown from SkateAir: absorb (pelvis 15–20 cm down at 0.12 s), rise to the stance |
| SkateManual | 1.0 s loop | balancing on the back wheels: hips over the back foot, front leg straighter, arms out, small balancing wobble (the game tilts the board nose-up 11°) |
| SkateNoseManual | 1.0 s loop | the same over the front wheels |
| SkateGrind | 1.0 s loop | 50-50: crouched, arms out, looking down the line, balancing |
| SkateGrindTail | 1.0 s loop | 5-0 / smith / feeble: weight back |
| SkateGrindNose | 1.0 s loop | nosegrind / crooked: weight forward |
| SkateSlide | 1.0 s loop | boardslide / lipslide / nose- and tailslides: lower, wider arms, looking along the rail (toward +X) |
| SkateGrabIndy | 0.5 s (reach by 0.18 s, hold) | right hand grabs the toe edge between the feet |
| SkateGrabMelon | 0.5 s | left hand grabs the heel edge between the feet |
| SkateGrabNose | 0.5 s | left hand to the nose |
| SkateGrabTail | 0.5 s | right hand to the tail |
| SkateGrabMethod | 0.5 s | left hand on the heel edge, knees bent back so the board comes up behind |
| SkateGrabStalefish | 0.5 s | right hand behind the back leg to the heel edge |
| SkateGrabDouble | 0.5 s | right hand indy and left hand melon |
| SkatePowerslide | 0.6 s, hold the end | board turned across the travel (the game turns it), weight back toward the heel edge, knees bent, arms forward |
| SkateCarveToe | 0.5 s hold | leaning into a toe-side turn: knees and hips toward +X |
| SkateCarveHeel | 0.5 s hold | leaning into a heel-side turn: sitting back toward -X |

Bails reuse the dive-roll and the knock-down clips (Roll; SitDown, SitIdle, StandUp). What the rider clips actually do,
where they depart from this contract and their checks: `games/yorimichi/assets/characters/cairo/README.md`.

## Skate pier (Blender + Unreal)

A concrete skate plaza on a pier off the beach south of the spawn road, reached by a concrete path that leaves the
road through the guardrail gap at x = -150 m and runs downhill to the pier; "Skate pier" is on the world map's travel
list. `games/yorimichi/world/regions/skatepark/` builds it, the board, and `park.json` (20 grindable lines, spawn points and the vegetation
clearance); `games/yorimichi/world/regions/skatepark/README.md` has the features and dimensions. The road guardrails are grindable too.

## Sounds

`games/yorimichi/assets/audio/skate/make.py` builds `games/yorimichi/assets/audio/skate/`: rolling, grind, slide, powerslide and foot-brake loops
synthesised as shaped noise (seamless), pops, landings, catches and bail clatter around two wooden stick hits from the
Sonniss masters, push scuffs and flip whirrs. The board carries the loops (volume and pitch follow the speed) and plays
the one-shots.

## Build

From the repository root, Unreal closed for the imports:

```sh
atelier build yorimichi unreal.world                                                        # pier, path, board: build + import
blender -b --python games/yorimichi/assets/characters/tools/cairo_skate_clips.py -- --parent game-r16 --revision game-r17   # rider clips
blender -b --python games/yorimichi/assets/characters/cairo/export_unreal.py -- --revision game-r17 --clips <Skate* roles> --clips-only --report export-skate.json
<python with numpy> games/yorimichi/assets/audio/skate/make.py                               # sounds
# then with UnrealEditor-Cmd -run=pythonscript: Scripts/import_cairo_skate.py, Scripts/import_skate_audio.py
atelier build yorimichi unreal.compile
```

## Checks

- `python3 games/yorimichi/scenarios/skate.py [name] [--only case,...]` with the game running (`atelier play yorimichi`): 22 cases through
  the live bridge, scripted skate. controls and simulated keys and mouse; report in `build/yorimichi/skateqa/`.
- The showreel: `atelier live py "TAKE='take2'"`, then `atelier live py - <
  games/yorimichi/scenarios/skate_showreel.py`, wait for `build/yorimichi/skatefilm/<take>/done.json`, then
  `<python with numpy> games/yorimichi/scenarios/skate_mix_showreel.py build/yorimichi/skatefilm/<take>`: eight shots filmed at a fixed 60 fps
  step with their sound.
- Live verbs (`games/yorimichi/live/python/yorimichi_live.py`): `live.skate()`, `live.skate_park()`, `live.skate_input(...)`,
  `live.flick(name)`, `live.skate_script(steps)`, `live.skate_state()`, `live.L.skate_launch(v)`,
  `live.L.skate_goofy(b)`, `live.L.input_key(key, event, value)`, `live.L.hold_camera(s)`; `games/yorimichi/scenarios/skate_live_skate.py`
  adds park coordinates and recorded scenarios.
