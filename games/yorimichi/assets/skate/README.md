# Skating runtime data

The 19 files loaded by the recovered Skate 3 Session are tracked individually in
[`unreal/Content/Data/SkateRuntime/assets`](../../unreal/Content/Data/SkateRuntime/assets): OnBoard/OffBoard animation banks,
action/motion/camera state graphs, seven gesture files, input configuration, camera shakes, converted VLT
settings and physical skeletons, plus the headless manifest/scene. These files include no original meshes, textures,
audio, executable or unrelated game content. `runtime.json` records every file checksum
and the converter revision. The source game data is EA Skate 3; these data are distinct from the Apache-2.0
recovered Rust source. Included for this project's personal use at the owner's request.

The normal Yorimichi build runs `tools/build_skate_runtime.py`, verifies the tracked data in place, and compiles
the worker into ignored `unreal/Content/Data/SkateRuntime/bin`. The data directory is explicitly exempt from
the Content ignore rule. The game reads these tracked files directly; there is no ZIP to unpack or external
data cache to install. Fresh checkouts use the same data as development.
