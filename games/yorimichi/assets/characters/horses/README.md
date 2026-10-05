# Hippodrome horses and riders

The horses, riders and race master of the Hidamari Hippodrome ([docs/HIPPODROME.md](../../../docs/HIPPODROME.md)).
They come from the local BOTW asset library like the [BOTW roster](../botw/README.md). None of their files are
committed: this folder holds only the roster and the exporter. Without the library the build skips these steps, and
the hippodrome stands without its horses and Hudson.

## The library

The BOTW library setup is in [../botw/README.md](../botw/README.md). The horse entries go in `library/horses/`
(`Horse`, `Horse_Mane`, `Horse_Epona`, `Horse_White` and the others). `scripts/build_horses.py` in the
botw-extract repository decodes them from the game's `Horse` and `Horse_Mane` archives: the meshes, the standard
horse's coats (`library/horses/Horse/coats/coats.json`) and every clip. The riders' `Horse_*` clips come from the
same humanoid packs as the BOTW roster.

## Roster

`roster.toml` lists:

- `Horse`: the standard horse, with its mane and tail.
- Six coats, as variants that share its skeleton: `HorsePinto`, `HorseBlack`, `HorseRoan`, `HorseLilac`,
  `HorseDun` and `HorseWhite`.
- `Epona`.
- Six riders: `RiderLink`, `RiderUrbosa`, `RiderMipha`, `RiderPaya`, `RiderTali` and `RiderKohm`.
- `Hudson`, on foot.

Each record names its clips and maps them to roles. For horses the roles are `idle`, `walk`, `trot`, `canter`,
`run`, `sprint`, `start`, `left`, `right`, `stop`, `rear` and `dance`. A rider has the same gaits plus `spur` and
`soothe`.

A rider's clips are BOTW's own riding clips. Their root sits on the horse's `Saddle_Root`, and each
`Horse_Move_Gear_<n>` is the rider's half of the horse's `Move_Gear_<n>`, frame for frame. The exporter measures
each gait clip's ground speed (`speeds`), and the game plays the clip at the rate that matches the horse's real
speed.

## Build

```sh
uv run atelier build yorimichi characters.horses unreal.horses
```

`characters.horses` (`export.py`, Blender) writes `build/yorimichi/horses/glb/<Name>.glb` and `export.json`.
BOTW models a few rigid pieces in their bone's own space, on a second skin with identity bind matrices: the horses'
shoes and eyeballs, and the riders' eyes, earring and hairband. Unreal imports every mesh against one reference
pose, so the exporter moves these pieces into model space and rebinds them to the body's skin. Left as they were,
they floated at the horse's feet.
`unreal.horses` (`unreal/Scripts/import_horses.py`) imports them to `/Game/Horses` and writes
`Content/Data/horses/roster.json`, which `FHorseSpec` reads.
