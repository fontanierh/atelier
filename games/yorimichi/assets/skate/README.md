# Native skating data

The skating data is tracked in [`unreal/Content/Data/SkateNative`](../../unreal/Content/Data/SkateNative), in the
Skate plugin's native formats. It contains 3,334 payloads: 3,324 animation clips (131,642 frames), the animation rig
and both metadata banks, the action, motion and camera graphs, 285 gesture patterns, camera data, settings and
physical skeletons. The payloads total 70,695,340 bytes. They are part of Atelier's own asset library. The skating module's code licence is documented separately.

| File | Content |
| --- | --- |
| [`runtime.json`](runtime.json) | The descriptor: data directory, the manifest's SHA-256, source identity, required formats and expected counts |
| [`package-manifest.json`](../../unreal/Content/Data/SkateNative/package-manifest.json) | Every payload's relative path, size and SHA-256 |

The `skate.runtime` build step runs [`tools/verify_skate_native.py`](../../tools/verify_skate_native.py), which checks
the bundle in place against both files and writes `build/yorimichi/skate-native/verification.json`; `unreal.compile`
waits for it. Nothing is extracted, converted or downloaded:

```sh
uv run atelier build yorimichi skate.runtime
```

The bundle is only rebuilt to change a native format or add an optional file, with the plugin's `Tools/` converters
and [`assemble_native_package.py`](../../../../platform/engine/Plugins/Activities/Skate/Tools/assemble_native_package.py);
update `runtime.json` to match. The plugin's
[runtime reference](../../../../platform/engine/Plugins/Activities/Skate/RUNTIME.md#data-bundle) describes the
formats, the converters and the parity checks.
