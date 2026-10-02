# Native skating data

The skating source data is tracked in [`native/`](native), in the Skate plugin's native formats. It contains
3,334 payloads: 3,324 animation clips (131,642 frames), the animation rig
and both metadata banks, the action, motion and camera graphs, 285 gesture patterns, camera data, settings and
physical skeletons. The payloads total 70,695,340 bytes. They contain converted records from EA Skate 3, distinct from
the Apache-2.0 recovered source, without original meshes, textures, audio or executables.

| File | Content |
| --- | --- |
| [`runtime.json`](runtime.json) | The descriptor: data directory, the manifest's SHA-256, source identity, required formats and expected counts |
| [`native/package-manifest.json`](native/package-manifest.json) | Every payload's relative path, size and SHA-256 |
| [`profile.json`](profile.json) | Difficulty, stance, tuning, board/audio references, collision roots and the scene-scan interval |

The `skate.runtime` build step runs [`tools/verify_skate_native.py`](../../tools/verify_skate_native.py), which checks
the bundle in place against both files and writes `build/yorimichi/skate-native/verification.json`; `unreal.compile`
waits for it. Nothing is extracted, converted or downloaded:

```sh
uv run atelier build yorimichi skate.runtime   # source integrity, without Unreal
uv run atelier build yorimichi unreal.skate    # generated UAssets and aggregate editor checks
```

`unreal.skate` runs [`import_skate_native.py`](../../unreal/Scripts/import_skate_native.py) after the geometry,
character and sound imports. It creates `/Game/SkateNative/DA_RuntimeData` with exact source bytes,
`DA_Collision` with baked per-mesh geometry, and `DA_YorimichiProfile` from `profile.json`. Those UAssets and the
`CollisionMeshes/` assets are ignored build output. Gameplay loads them exclusively, without loose-file fallback;
the tracked source is needed only to build them and for offline QA.

The script collects lossless save/reload, file-versus-asset session, collision/material/scene and animation checks
in `build/yorimichi/skate-unreal/validation.json`. The
[integration guide](../../../../platform/engine/Plugins/Activities/Skate/UNREAL_INTEGRATION.md#validation-status)
records the tested engine and cooked-game scope.

The bundle is only rebuilt to change a native format or add an optional file, with the plugin's `Tools/` converters
and [`assemble_native_package.py`](../../../../platform/engine/Plugins/Activities/Skate/Tools/assemble_native_package.py);
update `runtime.json` to match. The plugin's
[runtime reference](../../../../platform/engine/Plugins/Activities/Skate/RUNTIME.md#data-bundle) describes the
formats, the converters and the parity checks; the
[Unreal integration](../../../../platform/engine/Plugins/Activities/Skate/UNREAL_INTEGRATION.md) covers assets and cooking.
