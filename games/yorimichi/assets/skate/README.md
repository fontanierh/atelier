# Skating runtime data

`runtime.zip` contains the 19 files loaded by the recovered Skate 3 Session: OnBoard/OffBoard animation banks,
action/motion/camera state graphs, seven gesture files, input configuration, camera shakes, converted VLT
settings and physical skeletons, plus the headless manifest/scene. It contains no original meshes, textures,
audio, executable or unrelated game content. `runtime.json` records every file checksum, the archive checksum
and the converter revision. The source game data is EA Skate 3; these data are distinct from the Apache-2.0
recovered Rust source. Included for this project's personal use at the owner's request.

The normal Yorimichi build runs `tools/build_skate_runtime.py`, compiles the worker, and stages the verified
bundle into generated `unreal/Content/Data/SkateRuntime`. Fresh checkouts use the same data as development.
