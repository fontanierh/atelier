# Make a character playable

This guide takes an approved, rigged humanoid to a character you can choose in the game. It gets the full merged
move set, the bike, skating, the sword and the paraglider. Everything after the rig is data, and the build does the
rest. Making the model itself is covered in [the character pipeline](../../../docs/CHARACTER_PIPELINE.md) and, for a
case study, [Nox](NOX_CHARACTER_RECIPE.md).

Cairo, Modori, Nox and Paul use the shared export, import, recipe and player class described below.
Kaede also uses the shared asset pipeline, with the game-specific `ASwordTrainer` subclass for her training behavior.

## What you need

- **A rigged humanoid source** in `assets/characters/<id>/`: a `.glb` or a `.blend` with textures packed. Its skeleton
  follows the [humanoid contract](../../../platform/conventions/rigs/humanoid.toml) by name, using Mixamo's names as
  Tripo's auto-rig produces them. Fingers are optional but needed for grips. Extra bones (hair,
  extra spine joints) are allowed; you tell the export what to do with them.
- **A `source-manifest.json`** with the source's SHA-256 (`native`, `native_sha256`). The export refuses a source that
  does not match it.
- **Its height** in centimetres. The export scales the body to it, with the soles 0.65 cm under the floor and the body
  facing +X.

## 1. Define it: `character.toml`

The smallest definition is an id, a role, a source and a height:

```toml
id = "new-one"
display_name = "New One"
role = "player"                       # "player": choosable, rides the bike. "npc": the move set only.
rig = "humanoid"
height_cm = 170
source = "NewOne.glb"
manifest = "source-manifest.json"
```

Everything else has a default in [`pipeline/definition.py`](../assets/characters/pipeline/definition.py). Override
only what differs. Unknown keys are refused, so a typo fails at once.

| Table | What it sets | Examples |
|---|---|---|
| top level | names | `asset_name` (default: the id in PascalCase), `unreal_path` (`/Game/<Name>`), `output` (the build folder) |
| `[export]` | how the source becomes the game's body | `extra_bones = "drop"` (or `"follow"`), `mesh_names`, `actions = "authored"` to keep the source's own clips |
| `[export.materials]` | its materials | name and texture templates, `two_sided`, roughness, metallic and specular (a number or `"shader"`), `atlas` |
| `[unreal]` | the Unreal import | `camera_height`, `cpu_access`, `physics_asset`, `vertex_colors`, `morph_targets`, `contact_morphs`, `modules` |
| `[blender]` | how its Blender steps run | `threads` (3 for a heavy source) |
| `[game]` | its pawn (step 6) | `capsule_radius`, `cloth_teleport`, `hair_spring_morphs` |
| `[[fit]]` | fit waivers (step 4) | `report`, `clip`, `metric`, `bound`, `reason` |

Paul is a complete example: Tripo's auto-rig with Mixamo names, whose unweighted end bones are dropped
([paul/character.toml](../assets/characters/paul/character.toml)). Nox keeps a hair rig as bones that follow their
parents ([nox/character.toml](../assets/characters/nox/character.toml)).

Some geometry needs code. A body-specific step goes in an optional `<id>/export_hooks.py` with
`body(prepared, report)`. It runs after the rig is prepared and before the FBX is written. Modori's hook gives his coat
its cloth mask and colliders ([modori/export_hooks.py](../assets/characters/modori/export_hooks.py)). Nox's adds his
seat correctives ([nox/export_hooks.py](../assets/characters/nox/export_hooks.py)). Keep a hook to what the data
cannot say.

## 2. Give it the move set: `adventure.toml`

An `adventure.toml` beside `character.toml` makes it a mover. The build then retargets the reference rig's move set
and the donor's own clips (Cairo's double jump, two-handed guard, parry and gestures) onto it. The file can hold only
a comment. Its layout defaults to the character's own folder: `/Game/<Name>/Adventure`, `DA_<Name>`,
`DA_<Name>Base`.

Fit the carried pieces to the body only where they clip. Each number comes with the measurement behind it:

```toml
# Clear his shoulder blades: the reference carry sits up to 4.0 cm inside his back, plus 1.5 cm clearance.
[fit.push]
sword = [5.5, 0.0, 0.0]               # cm along the body: backward, left, up

[fit.glider]
fit_grip_span = true                  # fit the paraglider's bar to narrower palms
```

The `[fit]` keys are `carry`, `push`, `tilt`, `yaw`, `mount`, `crouch` and `glider`. Their meanings are listed at the
top of [`Scripts/import_adventure_moveset.py`](../unreal/Scripts/import_adventure_moveset.py). Modori's file shows
them all.

**A standing pose of its own.** A character can replace one clip's stance while keeping its motion. Nox's idle stands
with his own posture: `[stance.Nml_Wait] choice = "provenance/idle-pose-choice.json"`. The retarget applies it with
planted ankles and keeps the idle's breathing ([`adventure/stance.py`](../assets/characters/adventure/stance.py)).

## 3. Build it

```sh
nice -n 10 uv run atelier build yorimichi unreal.<key>_pawn unreal.<key>_bike characters.<key>_fit
```

`<key>` is the id with dashes as underscores. The build generates these steps from the two files:

| Step | What it does |
|---|---|
| `characters.<key>` | the body, textures and own clips to FBX (`pipeline/export.py`) |
| `unreal.<key>` | the mesh, materials, physics asset and base definition (`Scripts/import_character.py`) |
| `characters.<key>_adventure`, `unreal.<key>_adventure` | the merged move set, retargeted and imported |
| `characters.<key>_bike`, `unreal.<key>_bike` | every bike action authored on its rig (players only) |
| `characters.<key>_grips` | its posed grips, when `grips/<id>/` is committed |
| `characters.<key>_fit` | the fit gate (step 4) |
| `unreal.<key>_pawn` | its pawn, registered with the game (step 6; players only) |

Use `atelier build` or `atelier.safety.guarded` for every heavy step, as `AGENTS.md` requires.

## 4. Check the fit

`characters.<key>_fit` runs [`pipeline/fit.py`](../assets/characters/pipeline/fit.py) on the exported reports, and the
build fails when a clip fits badly:

- `ankle_cm`: how far an ankle falls short of where the leg was asked to put it (default bound 4 cm);
- `reach_<limb>_cm`: how far a hand or foot falls short of its bike grip, pedal or ground spot (default bound 4 cm);
- `lowest_toe_cm` and the stance checks, against the baseline.

A missing, non-finite or zero-sample report fails. So does a clip worse than its baseline by more than 0.5 cm.

When a value is above the bound for a reason you accept, waive that one clip and metric with the measured value:

```toml
[[fit]]
report = "bike"
clip = "BikeKickstand"
metric = "reach_hand_L_cm"
bound = 6.5
reason = "the left hand falls 6.02 cm short of its keyed target"
```

Once a build has been reviewed, record its baseline so any regression fails. Review it, then commit it:

```sh
uv run python games/yorimichi/assets/characters/pipeline/fit.py --character <id> --record
```

The baseline lands in `assets/characters/fit/<id>.json`.

## 5. Grips

The sword and paraglider grips start from Modori's posed grips. The poser then shows each grip on the new hand for a
person to adjust ([GRIPS.md](GRIPS.md)):

```sh
uv run python games/yorimichi/assets/characters/grips/seed.py --from modori --to <id>
uv run python games/yorimichi/assets/characters/grips/serve.py --character <id> --port 8897
```

A seeded grip is a draft. It reaches the game only after someone has opened it in the poser and saved it. Commit
`poses.json` and `grips.json` to `grips/<id>/`, and the build's `characters.<key>_grips` step reproduces them.

## 6. In the game

A player needs no code. The `unreal.<key>_pawn` step makes its pawn, `BP_<Name>`, a Blueprint of the game's
`AMoverCharacter` ([MoverCharacter.h](../unreal/Source/Yorimichi/MoverCharacter.h)), from the `[game]` table in
`character.toml`. The capsule comes from the height: the half height is half of `height_cm` rounded up, the crouch
seven eighths of it, and the mesh sits 0.65 cm lower. Override only what differs:

| Key | What it sets |
|---|---|
| `capsule_radius`, `half_height`, `crouched_half_height` | the capsule (cm) |
| `bike_rig` | the bike clips' folder, `/Game/<bike_rig>Bike` (default: the asset name) |
| `skate_clothing_clearance`, `skate_hull_directions` | how far clothes reach beyond the body's capsules; the bail hull's resolution |
| `leg_scaled_sailboat` | move the sailboat stance by the leg length |
| `cloth_teleport` | `[cm, degrees]`: a cloth restarts from the skinned pose after a jump this far or this sharp |
| `hair_spring_morphs` | `[forward, sideways]` morph targets a hair spring drives |
| `seat_correctives` | the morph target prefix of seat correctives an `export_hooks.py` made |
| `default`, `aliases` | the character a game starts as; older names `-rider=` accepts |

Modori's coat (`skate_clothing_clearance`, `cloth_teleport`) and Nox's seat (`seat_correctives`) are examples.

The step writes `Content/Data/<id>/character.json` last. The game registers every character with that record when it
starts, for `-rider=`, the character menu and shared games. The console command `yorimichi.RescanCharacters` registers
the records that appeared in the game's own `Content/Data` since then. It replaces the catalogue only when every name,
alias and default is consistent. A shared game keeps the catalogue it started with.

```sh
nice -n 10 uv run atelier build yorimichi unreal.<key>_pawn
nice -n 10 uv run atelier play yorimichi -- -rider=<Name>
```

## 7. Validate

A successful import does not prove the character is playable. Before review, run each check below as the new
character, under the guard, and quit each game promptly:

- **The move set:** `scenarios/adventure_moves.py` with `RIDER='<Name>'` (39 checks: jumps, sword, glider, swim, climb).
- **The bike:** `tools/review_bike.py --rider <Name>`. It films the circuit and checks every move. On every rider,
  two checks fail for shared physics reasons, not the character: sprint speed and the ramp wheel.
- **Skating:** mount, push, tricks, bails and recoveries on the live retargeter. Check the skin against the board
  (`skate.RideSkinCheck 1`).
- **Grips:** `grips/sample.py --held`, then `grips/check.py`. It exits 1 on a drifting grip.
- **Close-up stills and footage:** front, back, three-quarter and the armpits, in motion. These catch deformation that
  the checks do not.

Report results by their actual scope. Name any known failure, and say who owns it.

## 8. Commit

Commit:
- the source, its manifest and the two TOML files;
- any `export_hooks.py`;
- the fit baseline;
- committed grips.

Build outputs, Unreal Content, FBXs and captures stay ignored. Run `uv run atelier lint` and `uv run pytest -q`, read
`git diff`, and ask another agent for review on the board.

## Changing the pipeline

A change to `pipeline/` or the shared import must leave every character as it was. Two tools prove it:
- [`pipeline/fingerprint.py`](../assets/characters/pipeline/fingerprint.py) records a prepared body and its clips in
  Blender: bones, geometry, weights, shape keys, every clip frame. `--compare` checks two records.
- [`Scripts/character_snapshot.py`](../unreal/Scripts/character_snapshot.py) records the imported mesh, morph deltas,
  materials and every compressed clip in Unreal. `--compare` checks two snapshots.

Record both before and after the change, for every character.
