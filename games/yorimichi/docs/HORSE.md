# Horseback riding

A horse to ride anywhere on the island's ground: six breeds (Arabian, Thoroughbred, Friesian, Andalusian,
Clydesdale, Quarter), seven tack sets of saddle and reins, and a look made of a coat, a coat mask, a hair colour and
pattern for the mane and tail, and a tint. H (hold RB on a gamepad) summons it under the player and mounts it; it
walks, trots, canters, gallops and sprints on the walking physics, and goes away when he gets off. Every playable
character (Cairo, Modori, Nox, Paul) rides it with clips authored on his own rig.

## Controls

| | Keyboard and mouse | Gamepad |
|---|---|---|
| Summon and mount / get off (stopped, on the ground) | H | Hold RB / R1 / R (0.4 s) |
| Ride on (the further, the faster) | W | Right trigger (analogue) |
| Rein in | S | Left trigger (analogue) |
| Steer | A / D | Left stick left / right |
| Hold to a walk / a trot | Alt / J (held) | |
| Sprint (on / off) | Shift | Sprint (press the left stick) |
| Random horse: breed, tack, coat, mask, hair, pattern and tint | N | X / Square / Y (mounted) |
| Next breed | U | D-pad Up (mounted) |
| Next tack set | I | D-pad Right (mounted) |
| Next coat | O | D-pad Left (mounted) |

The keyboard's N, U, I and O work on foot too and change the next horse. The gamepad's look buttons work only in the
saddle, because on foot they are the dash, the sailboat, the skateboard to the hand and the sword. Beside a docked
zeppelin and aboard one the shoulders choose its stop or flight speed, so the hold leaves the horse alone there. The
coat mask, the hair colour and pattern and the tint change only with the random horse or `live.L.horse_configure`.

While mounted the HUD's first line shows the horse controls, the breed, coat id, tack set and gait (for example
`Arabian (kestrel-bay, tack 03) - Canter`), any refusal, and the speed in km/h. On foot, when the character has horse
clips, it adds "H horse   N random horse" (or "Hold RB horse") to the second line; online only while the host allows
vehicles.

## Riding

The gait follows the speed. Under 12 cm/s he stands; up to 260 cm/s (9.4 km/h) is the walk, up to 540 cm/s
(19.4 km/h) the trot, up to 880 cm/s (31.7 km/h) the canter and up to 1180 cm/s (42.5 km/h) the gallop. The sprint
is a toggle like the bike's hard pedalling: with it on, a full throttle runs up to 1480 cm/s (53.3 km/h) and the
Sprint clip plays above the gallop's top speed. It ends at a second press, when the horse comes to a halt (under
12 cm/s: reined in, coasted down or stopped by a wall) or when he gets off. Alt holds the ride to
a fifth of the top speed (236 cm/s, a walk) and J to 42 % (496 cm/s, a trot); with the sprint on, the shares are of
the sprint's top speed.

- **Speed.** Riding on gathers speed at 520 cm/s² (720 sprinting) towards the throttle's share of the top speed. With
  no throttle the horse slows at 420 cm/s²; reining in, or opening a menu or the map, slows it at 1400 cm/s². Only the
  ground changes the speed: in the air the horse carries what it had.
- **Turning.** 135 degrees a second standing, narrowing with speed to 68 at the sprint's top speed, and about a third of
  that in the air. He and the horse bank into a turn together, up to 16 degrees at speed.
- **Gaits.** The rider's and the horse's clips share one phase, kept on the rider's clip, and play faster through
  the gait's speed range (for example the walk from 0.82 to 1.22 times). From one gait to the next the cycle carries
  on, so the legs stay in step. A breed without a clip for a role plays its Idle there, as the rider does.
- **Standing.** Now and then the horse looks round, grazes, shakes, sniffs (flehmen) or nuzzles: the first idle after
  5.5 s, then 6.5 to 11.3 s after each one ends. The variant is picked from the clip serial, not a random number,
  so a replayed step picks the same one.
- **Slopes.** Traces at the front and back hooves (75 cm either side of the saddle, scaled by the breed) pitch the
  horse and rider to the ground between them, up to 25 degrees.
- **Walls.** Two traces reach ahead of the capsule, at a foreleg's knee (55 cm up, 80 cm ahead) and the muzzle (150 cm
  up, 155 cm ahead). They are the reference breed's for every breed: the look replicates outside the movement stream,
  so the simulation never reads it and a breed change mid-ride cannot break prediction. A surface steeper than about
  53 degrees there stops the horse dead, on the ground or in the air. On the ground above 60 cm/s, when the movement
  component's last step made less than 40 % of the horse's speed (a wall it slid along or stopped against), the speed
  drops to what it made. The horse has no fall or crash.
- **Getting on and off.** Summoning needs him standing on the ground, not crouching (otherwise the HUD says "Stand on
  the ground, not crouching, to get the horse"), not skating, sailing, on the bike or aboard the zeppelin. Offline, H
  first stands a crouched player up and does nothing in the air; online the host refuses both with that message. Any
  walkable floor or slope will do: as on the bike, there is no levelness check. Mounting and getting off last as long
  as the rider's HorseMount and HorseDismount clips (1.60 s and 1.40 s as authored), so each plays to its end; the
  horse stands still meanwhile. Getting off needs the horse stopped (40 cm/s, 1.4 km/h, or less) and the ground under
  him; faster, the HUD says "Slow down to get off", and in the air "Land to get off". Then the horse goes away.
- **Water.** The horse does not swim. It queries the move set's sea and woodland lake and ends the ride at the same
  depth that starts swimming on foot: feet below the surface by 1.1 capsule half-heights while grounded, or 10 cm
  while falling. Offline it stows immediately; online the host confirms the stow. The player is told "The horse will
  not swim: you are on foot" and the normal move set takes over. Engine swimming volumes also end the ride.
  The bike has no such rule.
- **In the saddle.** Jump, Attack, Guard, the sword and the move set do nothing, and the bike, sailboat and
  skateboard cannot be taken out. Crouch, Wave and Interact do nothing either (on the bike Crouch skids and Wave waves,
  but the horse has no such clips): he cannot crouch, wave, talk to the sword trainer, or call or board the zeppelin
  from the saddle. Online the same presses are refused: the move set takes no presses on a vehicle, and the host
  boards the zeppelin only from on foot. Map travel, back to spawn and leaving the game stow the horse at once.
- **Camera.** The chase camera comes up 45 cm and pulls back 35 %, settles in behind him above 80 cm/s as on the bike
  (unless the player looked around in the last two seconds), and widens the view by up to 10 degrees between 600 and
  1200 cm/s (22 to 43 km/h). After he gets off the framing blends back to walking over about two seconds, and still
  finishes if he takes the bike out meanwhile.
- **Hoofsteps.** There is no hoof sound in the footstep library, so each hoof is the surface's own footstep under the
  horse, heavier and lower ([FOOTSTEPS.md](FOOTSTEPS.md)): four strikes a walk cycle, two a trot, three a canter,
  gallop or sprint, louder with speed. His own footsteps are silent in the saddle.

### How it moves

The horse moves him the way the bike does. `UHorseComponent` ticks before physics and sets the character movement
component's velocity and the actor's yaw; the movement component then moves him, so floors, steps, slopes, falls and
walls stay the walking physics'. Ground friction and walking braking are zero while he rides and restored when he gets
off; they are saved once, when the horse arrives, so a later handoff never saves the zeros. One step of the ride is
`AdvanceSimulation`: speed, heading, phase, clip and clock, from the state, the input and the world, with no
presentation, sound or randomness. `Present` then drives the horse's clip, the hoofsteps, the ground pitch, the bank and
the rider's torso spring.

### Online

In a shared game the same `AdvanceSimulation` runs inside the movement component's saved moves, on the owner and the
host, in the bike's bounded substeps (the loop is in `JapanMovementPrediction.cpp`, the horse's side in
`HorseNetwork.cpp`); the component ticks after the movement component and only presents. Host checkpoints restore
`FJapanHorseState` before a correction replays, and other players see the host's 20 Hz presentation. Getting on and off
are requests the host grants (the same rules as offline), the sprint travels as the bike's sprint button, and a look
change is a request the host checks against its roster and replicates to everyone, the owner included. See
[MULTIPLAYER.md](MULTIPLAYER.md).

## Looks

A look is seven roster indices: breed, tack set, coat, coat mask, hair colour, hair pattern and tint.
The default is the first of each (the breed's own coat and hair), with the `Solid` mask. Changing one wraps around its list.

| Part | Choices | What it changes |
|---|---|---|
| Breed | 6 | the horse's mesh, skeleton and clips, and where the seat, stirrups and rein grips are |
| Tack set | 7 (`00` to `06`) | the saddle and reins, which follow the horse's skeleton |
| Coat | 17: the breed's own and 16 painted variants | the coat's base colour texture |
| Coat mask | 5: Overo, Tobiano, Spots, Pangare, Solid | an off-white pattern over the coat, at 0.85 strength |
| Hair colour | 19: the breed's own and 18 dyes, from Jet Black to Charcoal | the mane and tail's primary and secondary colours |
| Hair pattern | 4: Solid, Ombre Tips, Frosted Tips, Streaked | how far the secondary colour mixes in (0 to 0.55) |
| Tint | 5: Natural, Warm Sun, Rich Amber, Cool Slate, Deep Ebony | an RGB multiplier on the coat |

The coat and the mane and tail get dynamic instances of their imported materials, so a look overrides only what it
changes; the eyes, hooves and tack keep their imported look. The import gives each breed's mane and tail the breed's
`hair_colour` from the library manifest. Hair colour 0 (id `native`) keeps it, as coat 0 keeps the breed's own coat;
any other hair colour replaces it.

## The library

`assets/horses/` is committed source, like every other GLB the game consumes. It is 111 MiB in 131 files:

- `<breed>/horse.glb` for each breed: the skinned horse, its eleven clips (Idle, IdleLook, IdleGraze, IdleShake,
  IdleFlehmen, IdleAffection, Walk, Trot, Canter, Gallop, Sprint) and its solved rein bones, 8.4 to 10.1 MiB each.
- `<breed>/tack/Saddle_<id>.glb` and `Reins_<id>.glb` for the seven tack sets, skinned to that breed's skeleton.
- `coats/T_Coat_<mask>_Mask.png`, the five 512 px coat masks.
- `coats/variants/kestrel/<variant>.png` and `<variant>.json`: the 16 coat variants, each a 1024 px PNG with its
  provenance record beside it; `coats/variants/manifest.json` lists each variant's id, name, swatch colour, file,
  checksum and provenance record.
- `manifest.json`, the library's one declaration: the reference breed (`arabian`), each breed's name and hair colour,
  the tack sets, the clips with their loop flag, the coat masks, the hair colours, hair patterns and tints, and the
  size and SHA-256 of every GLB. Nothing else restates these lists.
- `build.py` and `rider.py`, the two Blender steps below.

Every GLB is self-contained: one embedded buffer, and only base-colour images, which Unreal's Interchange imports
straight from the GLB. The library was slimmed from 443 MiB in 569 files: the meshes were re-indexed (shared vertices
instead of triangle soup) and lost their unused second UV set, a leg-id attribute, their normal and emissive images
(no horse material samples them) and the exporter's extras; animation channels that do not move collapse to one key
or the rest pose within 0.1 mm or 1e-5. The geometry expands back to the original triangles exactly. The loose
texture folders, byte copies of the embedded images, and the coat JPEG fallbacks are gone.

`assets/source-library.json` records each GLB and PNG with its size and checksum, and
`tools/verify_asset_library.py` checks them in a fresh checkout.

### Coat provenance

The 16 variants (bay, seal brown, black, chestnut, sorrel, palomino, buckskin, perlino, blue roan, red roan, dapple
grey, silver dun, bay tobiano, chestnut overo, leopard spots and blanket appaloosa) are image edits of the horse
vendor's "Kestrel" coat atlas (`coat_Kestrel_Mt_Body.png`), repainted in place on its UV layout; the variant ids carry
its name (`kestrel-bay`). That atlas is not committed: each record names it and keeps its SHA-256 (`source_sha256`).
Each `kestrel/<variant>.json` records the model (`gpt-image-2.5-sunburst`, quality high, 1024x1024, the edits
endpoint), the full prompt and its SHA-256, the source texture and its checksum, timings, token usage and the output's
checksum. The PNG beside it is that generated output, unchanged.

## Build

```sh
nice -n 10 uv run atelier build yorimichi unreal.horses unreal.cairo_horse characters.cairo_fit
```

| Step | Runs | Reads | Writes |
|---|---|---|---|
| `world.horses` | `assets/horses/build.py` (Blender) | `build.py`, `manifest.json`, every breed's GLBs, `yori.py` | `build/yorimichi/horses/manifest.json` |
| `characters.<key>_horse` | `assets/horses/rider.py --character <id>` (Blender) | the character's folder and pipeline, `rider.py`, `vehicles/rider_common.py`, `yori.py`; needs `world.horses` | `build/yorimichi/<id>/horse/export.json` and `fbx/A_Horse*.fbx` (13 clips) |
| `unreal.horses` | `Scripts/import_horses.py` (after `unreal.compile`) | `manifest.json`, the coat masks, `coats/variants/manifest.json` and its PNGs, every GLB, `horse_data.py`, `animation_compression.py`, `yori.py`, `platform/studio/atelier/gltf.py`; needs `world.horses` | `/Game/Horses`, `Content/Data/horses/roster.json`, `build/yorimichi/horses/unreal_import.json` |
| `unreal.<key>_horse` | `Scripts/import_ride_clips.py` with `RIDE=horse` | the clips, the script and what it imports (`animation_compression.py`, `yori.py`, the pipeline's `definition.py`), the character's `character.toml`; needs `characters.<key>_horse` and `unreal.<key>` | `/Game/<bike_rig>Horse/A_Horse*`, `build/yorimichi/<id>/horse/unreal_import.json` |
| `characters.<key>_fit` | `pipeline/fit.py` | the adventure, bike and horse reports | `build/yorimichi/<id>/fit.json` |

`<key>` is the character id with dashes as underscores; every playable character gets its own horse steps.

- **`world.horses`** first checks every GLB against the manifest's size and checksum. It then measures each breed's
  rest contacts on `Saddle_00`, in rider space (metres, +X forward, +Y left, +Z up, origin on the ground between the
  hooves): `saddle_root`, `seat_z` and `seat_offset_z`, `scale_ratio` (its saddle height over the Arabian's 1.5993 m),
  the top centre of each stirrup tread (`stirrup_L`/`R`) and the rein grips at Idle's first frame (`grip_L`/`R`). It
  samples the reference breed's clips at 60 Hz: per frame the seat, saddle, spine, neck, head, bit, stirrup treads,
  rein grips, rein bones and spine pitch. The step is a cutoff: when its output is unchanged its dependents do not
  rerun for it, so a palette edit reruns only `world.horses` and `unreal.horses`, and a coat edit only
  `unreal.horses`.
- **`characters.<key>_horse`** authors 13 clips on the character's own rig: one per horse clip (HorseIdle, the five idle
  variants, HorseWalk, HorseTrot, HorseCanter, HorseGallop, HorseSprint) from the reference breed's trajectory, plus
  HorseMount (1.60 s) and HorseDismount (1.40 s). Each frame places the seat, then reaches the hands to the rein grips
  and the feet to the stirrup treads with a two-bone solve, while the torso follows the horse's spine pitch, roll and
  head and neck motion. `export.json` keeps `source_sha256`, `fps` and each clip's frames, duration and loop (what
  `unreal.<key>_horse` reads) and `reach_error_cm` per limb (what the fit gate bounds); the horse clip and the solved
  targets per frame stay in memory for the review renders. The rig solve, hand frames, keyed actions, studio and
  character loader are shared with the bike in `assets/vehicles/rider_common.py`. Mounting lifts the trailing foot
  with the rider's body, then swings it over the saddle; dismounting reverses the path. The torso leans over the
  saddle and shifts within all four limbs' reach, keeping the targets and bone lengths fixed and leaving a bend
  in the elbows and knees. Unreachable contacts still fail the normal 4 cm fit gate.
  A manual `rider.py --review` run
  re-exports every clip into the build, and `--clips` a subset (into `export-partial.json`), overwriting the step's FBXs
  while its build stamp still says current, as the bike's rider does: after one from changed sources, rebuild it
  (`uv run atelier build yorimichi --force characters.<key>_horse`, under the guard) before the next import.
- **`unreal.horses`** deletes and rebuilds `/Game/Horses`. It imports the coat masks, makes the masters `M_HorseCoat`,
  `M_HorseHair`, `M_HorseTack` and `M_HorseTackMasked`, imports each coat variant as `T_CoatVariant_<id>` with the id's
  dashes as underscores (`T_CoatVariant_kestrel_bay`), then for each breed an upright copy of its GLB
  (`horse_data.upright_glb`, written to `build/yorimichi/horses/glb/`) as `SK_Horse_<Name>`, `SKEL_Horse_<Name>` and
  `A_Horse_<Name>_<Clip>` (no root motion), and its 14 tack meshes as `SK_Horse_<Name>_<Part>_<id>`. Each imported
  material instance is reparented to its master, keeping the base-colour texture from the GLB; the report also lists
  each mesh's material instances and those textures. The step's check passes only when the roster matches its report,
  the contract and the library, and every asset either names is saved.
- **`unreal.<key>_horse`** imports the 13 FBXs onto the character's skeleton at the export rate, with the shared
  compression and no root motion. The bike's clips use the same script with `RIDE=bike`.

`unreal.<key>_pawn` runs after the horse clips but does not need them: the pawn reads none of them, so a horse change
leaves it current. `UHorseComponent` reads only the roster and the clips, so `data.stage` stages no rider's horse
`export.json` (unlike the bike's, which `UBikeComponent` reads); the report feeds `characters.<key>_fit` only.

### roster.json

`Content/Data/horses/roster.json` is what `UHorseComponent` reads. Its shape is the contract in
`Scripts/horse_data.py`, which `roster_problems` checks:

```text
{"reference_breed": slug, "breed_order": [slug, ...], "fps": int,
 "masters": {"coat" | "hair" | "tack" | "tack_masked": material path},
 "breeds": {slug: {"slug", "name", "mesh", "skeleton": asset path, "mesh_yaw": degrees,
                   "contacts": {"saddle_root": [x, y, z], "seat_z": m, "scale_ratio": float,
                                "stirrup_L" | "stirrup_R" | "grip_L" | "grip_R": [x, y, z]},
                   "clips": {clip: {"path", "length": s, "loop": bool}},
                   "saddles": {tack id: path}, "reins": {tack id: path}}},
 "tack_sets": [tack id, ...], "coat_masks": {mask: texture path},
 "coat_variants": [{"id", "name", "swatch", "texture"}],
 "hair_colors": [{"id", "label", "primary", "secondary"}], "hair_patterns": [{"id", "label", "mix"}],
 "tints": [{"id", "label", "rgb": [r, g, b]}]}
```

Contacts are in rider space. `mesh_yaw` is -90 for every breed: the horse faces +Y once imported, the actor +X.

### The rider in the saddle

The rider's clips are authored on the reference breed. In the game the animation instance plays the component's
rider clip at its clock, and `FHorseRiderNode` (`HorseRiderNode.h`) fits it to the breed and the ride:

- The pelvis moves by the breed's seat offset from the reference (forward and in height) and a spring-damped lift
  from the gait.
- A torso spring turns the pelvis, spine, chest, neck and head: speeding up leaves him pitched back, reining in throws
  him forward, a slope leans him with it, the gait rocks him, and a turn rolls and turns him into it. The neck and
  head take back about two thirds of the chest's pitch and roll, so his gaze stays level.
- Each arm and leg is re-solved with a two-bone IK in the bend plane it already has: the hands to the rein grips, the
  feet to the stirrup treads, keeping the hands' and feet's authored turn. The targets are the authored ones moved by
  the breed's grip and stirrup offsets from the reference breed's, which come from `world.horses`' contacts (the grips
  at Idle's first frame). Full steering pulls the inside rein back 3.2 cm and out 2.2 cm; reining in pulls both back
  2.8 cm.
- The node's weights ease in late in mounting and out early in getting off.

The clips load from `/Game/<bike_rig>Horse`; a rider with no rig name of his own uses the default character's, as on
the bike. Summoning refuses with "This character has no horse clips" when they do not match his skeleton, and with
"The horses are not installed" when the roster, its breeds or the rider's HorseIdle clip is missing.

## Live

```python
live.press('horse')          # summon and mount, or get off
live.press('horse_random')   # also horse_breed, horse_tack, horse_coat
live.press('sprint')         # the sprint toggle
live.drive(1)                # rides on with the stick's forward axis; live.drive(0) lets go
live.L.horse_state()         # phase, rider and horse clip, speed, sprint, steering, ground, look, status, placement
live.L.horse_configure('friesian', '03', 'kestrel-dapple-grey', 'Tobiano', 'silver-white', 'ombre', 'cool-slate')
```

`horse_configure` takes roster ids (breed slug, tack id, coat id or `native`, mask, hair colour id or `native`, hair
pattern, tint); an empty id keeps that part, and an unknown one changes nothing and returns an empty string.

There is no phone control and no single-player QA scenario for the horse yet; the multiplayer feature case
`switch-horse` rides it online ([MULTIPLAYER.md](MULTIPLAYER.md)).

## Tests

The native `Yorimichi.Network.HorseCheckpoint` (in the network wire suite) checks the shared game's checkpoint and look
indices. `Yorimichi.Network.HorseWater` checks the actual sea/lake query, shallow/deep and falling entry,
scaled capsules and restored walking friction after stowing. `uv run pytest games/yorimichi/tests/test_horses.py -q`
needs no Blender or Unreal. It checks that the library
manifest matches the files on disk and the source library, the palettes' shapes, each coat variant against its
provenance record, that every GLB is slim, self-contained and skinned within range, the uprighting, the roster
contract and what breaks it, the `unreal.horses` output check, that the rider and recipe take their clip lists from
the manifest and the rider's transitions, that each horse step hashes what its script imports, and that the bike's
rider shares only `rider_common`'s names and keeps its `export.json` keys.

## Validation

Python tests do not run the horse. These native checks do; all are heavy and run under the render board, its lock and
the machine guards:

```sh
nice -n 10 uv run atelier build yorimichi unreal.compile unreal.horses
nice -n 10 uv run atelier build yorimichi unreal.<key>_horse characters.<key>_fit   # each playable character
blender -b --python games/yorimichi/assets/horses/rider.py -- --character <id> --review DIR --breed <slug> --tack <id>
nice -n 10 uv run python games/yorimichi/tools/review_network_wire.py
nice -n 10 uv run python games/yorimichi/tools/review_network_session.py --feature-case switch-horse --render-view host
nice -n 10 uv run python games/yorimichi/tools/review_network_session.py --feature-case switch-horse --render-view guest
```

- **Build and import.** `unreal.horses` passes only when the roster matches its report, the contract and the library
  and every asset they name, materials and textures included, is saved; `unreal.<key>_horse` checks each clip's imported length against `export.json`;
  the fit gate holds every horse clip's `reach_error_cm` to the 4 cm bound (waivers aside) and, once the character has
  a horse baseline, to it ([PLAYABLE_CHARACTER.md](PLAYABLE_CHARACTER.md)).
- **Review renders.** The Blender run goes under `atelier.safety.guarded`, for several breeds and tack sets
  (`--review-video` with clip names adds MP4s). It writes into the build (see `characters.<key>_horse` above).
- **Checkpoint.** The native wire suite runs `Yorimichi.Network.HorseCheckpoint` with the other network fixtures
  ([MULTIPLAYER.md](MULTIPLAYER.md)).
- **Online.** The `switch-horse` feature case, from both observer views.
- **Play.** Each character offline: mount and get off, every gait and the sprint, idle variants, slopes, a wall at
  speed, the look keys and buttons with a keyboard and a gamepad, map travel with the horse out, and the
  hoofsteps on each surface.
