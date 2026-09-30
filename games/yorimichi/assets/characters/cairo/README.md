# Cairo character

The current source blend and `source-manifest.json` supply Cairo's mesh, bind skeleton, locomotion and action
clips. `export_unreal.py` exports the roles requested by the game build. The build excludes the old Skate roles;
skating uses the recovered runtime's animation banks and retargets its solved pose onto Cairo at runtime.
See [skating](../../../docs/SKATE.md) and [runtime assets](../../skate/README.md).
