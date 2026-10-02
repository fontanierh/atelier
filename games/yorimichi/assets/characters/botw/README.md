# BOTW characters

Yorimichi can bring in characters from a local BOTW asset library: their rigged meshes, every animation clip, and a
game-side actor that plays them. The library is not part of the repository and none of its files are committed; this
folder holds only the roster and the scripts that convert it. Without the library the build skips these steps and the
game runs as before.

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
  14 m, chases, attacks; sword hits stagger and knock it down) and scripted. The island spawns a camp of three
  Bokoblins 25 m up the road; `-nobotw` turns it off, and scripted sessions (QA, films) get it only with `-botw`.
- **Riders**: a character with a `skate` map gets a `DA_<Name>Rider` definition (its idle and a locomotion blend
  space). `-rider=<Name>` makes it the player (`ABotwRider`): it walks, runs and gets on the board, where the skate
  runtime's solved pose is retargeted through `ISkateRider::GetSkateBone` like on Cairo.
- **Character switch**: the Esc menu's Character row switches the player between Cairo and every rider while playing
  (`ABotwRider::SwitchPlayer`): the new character stands where the old one stood, facing the same way, with the camera
  unchanged; the board and the sailboat are put away first. It is refused on the zeppelin.
- **Live verbs**: `botw_roster`, `botw_spawn(name, ground, yaw, mode)`, `botw_play`, `botw_move_to`, `botw_mode`,
  `botw_list`, `botw_clear` and `switch_character(name)` (`YorimichiLive.h`).

```sh
uv run atelier play yorimichi -- -rider=Bokoblin
```

`scenarios/botw_film.py` films the demo: a line-up of the roster on the island road, the Bokoblin camp, and the
rider's flat trick and pool trick in the Mega Park: the Bokoblin's 360 flip and Christ air 360, or Link's varial
kickflip and flair (a backflip 180: the grab held from take-off and the left stick pulled back twice, quickly,
`POOL_TRICK='flair'`). The trick names never mention a body flip (the flair shows as "BS Grab"): the skate runtime only
scores it.
