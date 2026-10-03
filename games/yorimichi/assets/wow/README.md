# Offline vanilla content extraction

This directory can run by itself on a machine with Python 3.11+, Rust/Cargo and Blender. It has no
Unreal, game-server, Bevy or Atelier runtime dependency. Inside this repository, builds and heavy
extraction use Atelier's guard automatically; standalone jobs preserve logs and deadlines.

The decoder pins benilla to `b396bbf69a0486b6d29829ec191145f63c363eea` with its MIT OR Apache-2.0
licence. Cargo fetches only the required reader/schema crates. No retail assets are included.

```sh
python3 pipeline.py doctor --data /path/to/client/Data --output /path/to/private/output
python3 pipeline.py plan --output /path/to/private/output
python3 pipeline.py build --output /path/to/private/output
python3 pipeline.py extract --data /path/to/client/Data --output /path/to/private/output
python3 pipeline.py verify --output /path/to/private/output
```

Use a fresh output directory for each extraction. In an Atelier checkout, `--output` must be under
ignored `build/`; standalone outputs can be elsewhere. The source folder is read-only and must be
separate from output. `WOW_DATA` can substitute for `--data`. Change `profile.toml` or supply
`--profile` for a different class, level, model set, terrain bounds or selected model directories.

The first profile selects a level-60 mage, human body models, selected jungle creatures, item
components and a 3×3 tile window around an upstream Booty Bay fixture. That window is a starting
selection, not a verified complete boundary. MPQ listfiles are incomplete: explicit table/model
seeds and recursive format dependencies supplement listing.

Outputs include input archive hashes, extraction manifest, lossless raw files, PNG textures,
neutral JSON models/animations/terrain/buildings, registered typed CSV tables, class/spell/talent,
creature-appearance and item-display catalogues, preview GLBs and world-geometry OBJs.

The GLB writer currently handles ordinary bone inheritance and clip tracks with step/linear
interpolation. It rejects billboard/special-inheritance/global-sequence rigs rather than baking
them incorrectly. Preview materials do not reproduce character texture composition, geoset
selection or spell particles/ribbons. Neutral channels and raw files remain available for these.

Client data does not contain complete named NPC templates, spawns, item stats, loot, quests or
server effect implementations. A level-eligible spell catalogue is not a learned spellbook.
Further offline reference-data extraction and native mechanic implementation are separate work;
neither requires running VMangos. See the comprehensive handoff included in the delivery bundle.

Current validation uses synthetic, authored format fixtures. No retail client data or real model
was available for extraction. Generated/retail-derived content must stay outside public source.
