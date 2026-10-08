# BOTW characters

Yorimichi can bring in characters from a local BOTW asset library: their rigged meshes, every animation clip, and a
game-side actor that plays them. The library is not part of the repository and none of its files are committed; this
folder holds only the roster and the scripts that convert it. Without the library the build skips these steps and the
game runs as before.

One exception, approved by the operator on 2026-10-08: Modori's committed grip poser files
([grips/modori/](../grips/modori/), [docs/GRIPS.md](../../../docs/GRIPS.md)) include the sampled vertices of the sword,
sheath and glider in `samples/surface28.jsonl.gz`, and renders of them in `snapshots/`. The prop meshes themselves
(`LinkSword.glb`, `LinkGlider.glb`) stay in the library.

## The library

Extract the library zip so that `~/.cache/atelier/botw/library/catalog/archive-info.json` exists (the folder holds
`START_HERE.md`, `catalog/`, `library/` and `viewer/`). `library.py` reads it from there; the build hashes only the
files the roster uses.

Link and his clothing come from the private `fontanierh/botw-extract` repository, whose extended catalog adds the
player character and Link's armour to the library. Clone it to `~/.cache/atelier/botw/botw-extract` and restore its
metadata and viewer packs (its own README has the details):

```sh
git clone https://github.com/fontanierh/botw-extract ~/.cache/atelier/botw/botw-extract
cd ~/.cache/atelier/botw/botw-extract && python3 scripts/restore_assets.py --group metadata --group viewer
```

`library.py` looks an id up in the library first, then in `playground/private/catalog.json` (characters) and
`clothing.json` (Link's clothing) there.

## Build

```sh
uv run atelier build yorimichi characters.botw unreal.botw
```

`characters.botw` runs `export.py` into `build/yorimichi/botw/`: for each roster character it bakes the library's
curve clips (`bake.py`, a port of the library viewer's BFRES curve player) into one GLB with the mesh and every clip,
measures the height and the walk and run speeds from the planted ankles, applies the roster's `scale`, and writes
`export.json`.

`unreal.botw` runs `Scripts/import_botw.py`, which imports each GLB into `/Game/Botw/<Name>/` (`SK_<Name>`, its
skeleton and the `A_<Name>_<Clip>` sequences; a variant imports only its mesh, on its owner's skeleton) and writes
`Content/Data/botw/roster.json` for the game. Every material is reparented onto `M_BotwCharacter` (or its masked twin
for cut-out hair and cloth): the game's character look (base colour with a 30% emissive fill, roughness 0.7,
specular 0.3, no normal map), so the characters sit in the painterly light like Cairo instead of the source's shiny
PBR look.

## Roster

`roster.toml` lists the characters; its header documents the fields:

| Field | Meaning |
| --- | --- |
| `id`, `name` | the library entry, and the Unreal name |
| `clips` | `"all"`, or clip names; `"re:<pattern>"` adds every match |
| `shares` | a colour variant: the owner's skeleton and clips, its own mesh and textures |
| `roles` | the clip `ABotwCreature` plays for each behaviour (idle, walk, run, notice, attack, hit, down, ...) |
| `scale` | its size in the game relative to the source; the top-level `scale = 0.8` is every character's default (the library draws them about 15% larger than Yorimichi: a Bokoblin becomes 1.31 m, Zelda 1.49 m beside Cairo's 1.48 m) |
| `skate` | the character's bone for each humanoid contract role; makes it a rider |
| `board` | a rider's skateboard size relative to the standard one (1.6 puts the Bokoblin's big feet over the trucks); only the visible board grows, about its wheels' contact, and the pose rises onto its deck |
| `outfit` | Link's clothing, by `clothing.json` id: `outfit.py` merges each garment's meshes onto his body (cloth bones added at rest) and drops the body parts it covers (the library viewer's rules, but the belts stay on); Link wears the Champion's Tunic and Hylian Trousers |

## In the game

- **Creatures**: `ABotwCreature` (`Source/Yorimichi/BotwCreature.h`) plays the baked clips, stays on the ground and
  has a capsule the sword hits. Its modes: idle, showcase (every clip in turn), wander, camp (notices the player within
  14 m, chases, attacks; sword hits stagger and knock it down) and scripted. None is spawned at the start; the live
  verbs below place them.
- **Riders**: a character with a `skate` map gets a `DA_<Name>Rider` definition (its idle and a locomotion blend
  space). `-rider=<Name>` makes it the player (`ABotwRider`): it walks, runs and gets on the board, where the skate
  runtime's solved pose is retargeted through `ISkateRider::GetSkateBone` like on Cairo.
- **Character switch**: the Esc menu's Character row switches the player between Cairo (with the move set his setting
  picks) and the riders with a move set (Link; the others start only with `-rider=<Name>`) while playing
  (`ABotwRider::SwitchPlayer`): the new character stands where the old one stood, facing the same way, with the camera
  unchanged; the board and the sailboat are put away first. It is refused on the zeppelin.
- **Live verbs**: `botw_roster`, `botw_spawn(name, ground, yaw, mode)`, `botw_play`, `botw_move_to`, `botw_mode`,
  `botw_list`, `botw_clear` and `switch_character(name)` (`YorimichiLive.h`); for a move set, `move_state()` (its
  mode, action, stamina, glider, target and counts as JSON), `launch(velocity)` and `press(button)` with `dodge`,
  `dash`, `attack`, `attack_release`, `guard`, `guard_release` and `weapon`.

## The merged move set

The player plays one move set, Cairo's and Link's merged: Link's moves from BOTW with Cairo's double jump, and no dash.
Link plays it, and so does Cairo whenever his copy is built (below).

The "Move set" setting (Esc menu and phone, saved; `-moveset=merged|cairo|botw` decides for a scripted session) can
bring the legacy sets back. **Merged** is the default. **Cairo (legacy)** gives Cairo his original moves: the dive roll,
the ground and air dashes, his own sword. Link has none of Cairo's clips, so he keeps the merged set. **Breath of the
Wild (legacy)** is the set as it was before the merge: no double jump (Jump in the air opens the paraglider), the
shield always carried, and the guard button only locking on while the sword is sheathed. Merged and legacy BOTW switch
at once. Changed in the Esc menu while playing Cairo, a choice that moves him to or from his legacy moves switches
the character in place; changed on the phone, it waits until Cairo next comes into play. `moves.toml` names each game action, the Link clip it plays and the BOTW action timeline
its timing comes from (rate, start and end, the frames a blow lands, the next press is read, it may be cancelled, the
sword changes hands), the locomotion blends, the BOTW parameters the game reads and his equipment: the Traveler's
Sword and its sheath on his back, the Traveler's Shield, and the paraglider. `export.py` bakes the clips and the equipment
with him; `import_botw.py` makes them `DA_LinkRider`'s actions and blend spaces (each sample at its BOTW play rate) and
the `moves` record of `roster.json`. In the game `UBotwMoveSet` (`Source/Yorimichi/BotwMoveSet.h`) gives any rider
whose record has a move set these moves in place of Cairo's original jump, dodge, dash and sword, with the usual buttons
([CONTROLLER_CONTROLS.md](../../../docs/CONTROLLER_CONTROLS.md)):

| | |
| --- | --- |
| On foot | Jump, standing or running; Link's sprint (no dash on foot or in the air, no roll). Roll is the dodge: a side hop (stick left or right) or the backflip (anything else). A fall from more than 4.5 m lands hard, from more than 9 m it hurts. |
| Double jump | Cairo's: Jump again in the air, once until he stands, climbs or swims again. A fresh 6.5 m/s launch, all the ground speed turned toward the stick (even right round), and one forward somersault: Cairo plays his own `DoubleJump` clip; Link, who has none, tucks into BOTW's slope-tumble ball (`DoubleJumpTuck`, the `Rolldown` pose) and the game turns his mesh one full turn about the ball's middle on Cairo's timing, lifted so his hips stay level. |
| Paraglider | Jump in the air after the double jump (or with it spent) opens it; the stick steers and pulling back brakes; Jump or Roll closes it. It spends stamina and closes when the stamina runs out. |
| Climbing | Run or jump into anything steeper than 50° (not the skate parks' ramps and rails). The stick climbs, Jump leaps a hold further for a chunk of stamina, Roll lets go, and at the top he pulls himself over. He drops off when the stamina runs out. |
| Swimming | Water above his waist: he swims at the surface; Jump or Dash is the swim dash. Out of stamina he sinks and comes back on the last dry ground, a little hurt. Swimming into a low bank climbs out. |
| Sword | Draw / sheathe; Attack (which draws first if needed): the four-cut combo, the dash attack while sprinting, the jump attack in the air, the plunge from 3 m up, the sneakstrike on an unaware enemy while crouched; held, the charged spin. |
| Guard and parry | Parry held: the guard and lock-on, strafing around the nearest enemy (drawing the sword first when it is sheathed). Jump while guarding: the parry, which staggers the attacker. A dodge just as a blow comes slows the world for a flurry rush: Attack, repeatedly. |
| Taking hits | From the front, back, left or right (the way the blow came), on BOTW's damage clips: a light hit flinches (`HitF`... `Nml_Damage_S_*`); a strong one (15 or more), or the third within 1.2 s, staggers (`HitMF`... `Nml_Damage_M_*`, pushed further); a heavy one (25 or more) or the last of his health knocks him down (`KnockF`/`B`/`L`/`R`) and he gets up the way he fell (`KnockUp*`). Over every reaction a recoil (`FlinchRotation`, the animation graph's flinch layer) bends the spine, chest, neck and head away from the blow and back, the head last, twisted a little away from the struck side. A heavy blow on the guard breaks it (`GuardBreak`, `SwordGuardBreak`): the arms thrown wide, no guard for a second, no damage. Being parried staggers. |
| Shield | Optional: the "Shield" setting (Esc menu and phone, saved; off by default; `-shield` or `-noshield` for a scripted session). Carried, the shield guards and parries (`GuardCarry`, `Parry`, `GuardHit`). Off, it is hidden and the sword does both: Link on BOTW's sword-only clips and the same timelines (`SwordGuardCarry`, `SwordParry`, `SwordGuardHit`: `Sword_Guard_Wait`, `Sword_Guard_Just`, `Sword_Guard_Hit`), Cairo on his own two-handed bokken guard stance, parry and recoil at their authored windows (`SwordIdle`, `SwordParry`, `SwordParryHit`). |

Stamina is the sprint rings' wheel (`FSprintStamina`), refilled only on foot.
Every move has its effects (`YorimichiCombatFX`): dust kicked up by jumps, a shock ring and wind motes under the double
jump and a wind swirl through its somersault, dust and speed lines while sprinting, a whoomp of air as the paraglider
opens and wind off its tips in flight, speed lines off the side hop and backflip, a cold flash and ring for a perfect
dodge, a ribbon behind the blade through every cut, and steel sparks for a sword parry.
`scenarios/botw_moves.py` checks it all in the game through the live bridge.

```sh
uv run atelier play yorimichi -- -rider=Bokoblin
```

`scenarios/botw_film.py` films the demo: a line-up of the roster on the island road, the Bokoblin camp, and the
rider's flat trick and pool trick in the Mega Park: the Bokoblin's 360 flip and Christ air 360, or Link's varial
kickflip and flair (a backflip 180: the grab held from take-off and the left stick pulled back twice, quickly,
`POOL_TRICK='flair'`). The trick names never mention a body flip (the flair shows as "BS Grab"): the skate runtime only
scores it.

### Cairo with the merged move set

Where a person plays, Cairo has the merged move set whenever it is built, unless the "Move set" setting picks his
legacy moves (the character switch follows it too). QA, reviews and benchmarks keep his legacy moves (his roll, dashes
and sword) unless the command line asks with `-rider=CairoBotw`; without the local library he has only those.
`characters.cairo_botw` runs [`retarget.py`](retarget.py) in Blender, which retargets every Link clip onto
Cairo's skeleton (`build/yorimichi/cairo/botw/`). Both rest poses are T-poses. Each limb and finger swings to point
where Link's points, the hands keep their palm frames, the feet keep their level heading at Cairo's own rest pitch (so his
flat shoes stay flat on the ground), and the spine and head keep
Cairo's own posture. The hips move as Link's do, at the ratio of the two hip heights (`body`, 0.63). The legs are then
solved so that planted feet stay planted, at that same scale, from Cairo's own stance. `unreal.cairo_botw`
(`Scripts/import_botw_moveset.py`) imports the clips into `/Game/CairoBotw` and copies `DA_Cairo` into `DA_CairoBotw`
with Link's blends and actions. Both scripts are the same for every character with the set: each character's own
`botw.toml` ([`../cairo/botw.toml`](../cairo/botw.toml), `../modori/botw.toml`, `../sword-trainer/botw.toml`) gives its
paths, whether its base definition's own clips stay, and the fit of the carried pieces to its own mesh; Cairo's also
names him the set's donor (`[donor]`: his double jump and bokken guard clips with their timing, and his gestures). It also writes Cairo's move record, `Content/Data/cairo/botw.json`. In that record:

- Link's action paths, gait speeds and swim hang are scaled to Cairo's size.
- His own `DoubleJump` clip joins `DA_CairoBotw`'s actions, so his double jump is his somersault, and his own bokken
  guard stance, parry and recoil replace Link's sword-only guard clips (with their authored timing in the record).
- `BodyScale` converts BOTW's metres for him.
- Link's sword, sheath, shield and paraglider are scaled with Cairo. Each piece is moved from Link's weapon bones to
  Cairo's hands in the palm's frame (`held`), and from Link's back bone to Cairo's chest (`carry`). The shield's
  carry is fitted to Cairo's own mesh instead (`[fit.carry]` in his `botw.toml`): his deeper torso and bigger head ran through it
  where Link's chest put it.

```sh
uv run atelier build yorimichi unreal.cairo_botw
uv run atelier play yorimichi -- -rider=CairoBotw
```

### Review film

`scenarios/botw_moves_film.py` films every move of the set, shot by shot and close up, with the move set's state
recorded for each frame and the game's sounds logged: Link with `-rider=Link`, Cairo with `-rider=CairoBotw`, each in its
own game.
`scenarios/botw_moves_film_cut.py` captions the takes and joins them into one MP4, keeping or leaving out sections per
take so that retakes splice in. Their docstrings give the commands.
