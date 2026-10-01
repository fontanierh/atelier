> Wanderer is an NPC only: the villagers of Hidamari and Momiji Hamlet. Cairo is the player.

# Wanderer V2

The villager follows Yellow Boy's (now Cairo's) proportions and graphic style:
large simple face, broad angular hair, tied topknot, short moss haori, rust scarf,
cropped trousers and slim shoes with thin, flush soles. A single belt pouch and
faceted straw hat preserve his traveller identity.

## Imagegen references

The built-in imagegen tool produced the [model sheet](references/design-sheet.png) and the
[walking, running and action sheet](references/motion-sheet.png). Its inputs included the
original Yellow Boy reference and unretouched screenshots of both game characters.
Exact prompts are saved alongside those sheets as `*-prompt.txt`.

The sheets guide silhouettes, gesture and outfit construction. Their approximate
contact drawings are not motion capture: the actual animation uses constrained
foot contacts and continuous stride recovery.

## Source and assets

- `wanderer_mesh.py`, `wanderer_hair.py`: editable metre-scale procedural geometry.
- `wanderer_rig.py`: 34-bone compact rig, independent head, scarf tails, pouch and hat.
- `wanderer_motion.py`: 21 clips at 60 Hz; quieter arms and shorter recovery than
  Yellow Boy. Walk 0.90 m/s, jog 1.80 m/s, default run 3.00 m/s, crouch 0.50 m/s.
- `accessories.py`: baked secondary motion (hat, scarf tails, pouch).
- `kit/`: the contact solver (`animate.py`), geometry primitives and shoe contact conventions shared with the
  prototype's Yellow Boy.
- `build/yorimichi/wanderer`: disposable `.blend`, FBXs and manifests.

The body has about 3,800 triangles and a single opaque vertex-colour material.
There are no cloth grain textures, woven straw microgeometry or fine hair strands.
Unreal uses `/Game/Wanderer/V2` for the mesh, skeleton and clips; the
`/Game/Wanderer/DA_Wanderer` selection asset points to them.

## Rebuild and import

```sh
atelier build yorimichi characters.wanderer unreal.world
```

`characters.wanderer` runs `build.py -- --animations --export --no-render` into `build/yorimichi/wanderer` and records
source and artifact hashes; `unreal.world` imports the result (`Scripts/import_wanderer.py`). For geometry studies, use
`build.py -- --study NAME --views front,side,back,face,head_profile`. Studies cannot overwrite production exports.
