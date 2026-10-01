# Villager (wanderer)

The wanderer is the game's villager, the NPC of Hidamari and Momiji Hamlet; Cairo is the player. He shares Cairo's
proportions and graphic style: a large simple face, broad angular hair with a tied topknot, a short moss haori, a rust
scarf, cropped trousers and slim shoes with thin, flush soles. A single belt pouch and a faceted straw hat mark him as a
traveller. He is entirely procedural: `build.py` makes the mesh, rig and clips in Blender, with no binary source.

## Build and import

```sh
uv run atelier build yorimichi characters.wanderer unreal.world
```

`characters.wanderer` runs `build.py -- --animations --export --no-render` into `build/yorimichi/wanderer/` (the
disposable `.blend`, FBXs and `build.json`, with source and artifact hashes). `unreal.world` imports the result with
`unreal/Scripts/import_wanderer.py`: the mesh, skeleton and clips go to `/Game/Wanderer/V2`, and the
`/Game/Wanderer/DA_Wanderer` selection asset points to them.

For geometry studies, run `build.py -- --study NAME --views front,side,back,face,head_profile`. A study writes to
`build/yorimichi/wanderer/studies/NAME/` and refuses `--export`, so it cannot overwrite the production export.

## Model, rig and clips

- About 3,800 triangles and a single opaque vertex-colour material; no cloth grain textures, woven straw
  microgeometry or hair strands.
- A 34-bone compact rig (`wanderer-34` in `character.toml`, not the humanoid bone contract): an independent head,
  scarf tails, pouch and hat.
- 23 clips at 60 Hz: Idle, Walk, Jog, Run, Sprint, CrouchIdle, CrouchWalk, JumpStart, JumpRise, DoubleJump, Fall,
  Land, HardLand, Dodge, Interact, Wave, SitDown, SitIdle, StandUp, Climb, Glide, TurnLeft and TurnRight. The arms are
  quieter and the recoveries shorter than on Cairo's library. Walk 0.90 m/s, jog 1.80 m/s, run 3.00 m/s, crouch walk
  0.50 m/s.
- Feet use constrained contacts and continuous stride recovery; the hat, scarf tails and pouch carry baked secondary
  motion.

## Files

| File | Contents |
| --- | --- |
| `build.py` | the Blender entry point: model, rig, clips, export, studies |
| `wanderer_mesh.py`, `wanderer_hair.py` | editable metre-scale procedural geometry |
| `wanderer_rig.py` | the 34-bone rig |
| `wanderer_motion.py` | the villager's clip settings (speeds, strides, arm swing) over the shared clip builder |
| `accessories.py` | baked secondary motion for the hat, scarf tails and pouch |
| `kit/` | the shared clip builder and contact solver (`animate.py`), rig, head, hair and mesh primitives, shoe contact conventions |
| `pipeline.py` | build records and hashes |
| `references/` | the [model sheet](references/design-sheet.png) and the [walking, running and action sheet](references/motion-sheet.png), each with its prompt (`*-prompt.txt`) |

The reference sheets guide silhouettes, gesture and outfit construction. Their contact drawings are approximate, not
motion capture.
