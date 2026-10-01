# Cairo character

The current source blend and `source-manifest.json` supply Cairo's mesh, bind skeleton, locomotion and action
clips. `export_unreal.py` exports the roles requested by the game build. Cairo has no skate clips: skating uses the
recovered runtime's animation banks and retargets its solved pose onto Cairo at runtime (game-r18 removed the old
authored ones).
See [skating](../../../docs/SKATE.md) and [runtime assets](../../skate/README.md).
