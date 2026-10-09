# Native skating data

The skating data is tracked in two places, in the Skate plugin's native formats. It contains 3,334 payloads: 3,324
animation clips (131,642 frames), the animation rig and both metadata banks, the action, motion and camera graphs,
285 gesture patterns, camera data, settings and physical skeletons. The payloads total 70,695,340 bytes. They are part
of Atelier's own asset library. The skating module's code licence is documented separately.

| Path | Content |
| --- | --- |
| [`motion/`](motion) | The animation as readable JSON: `rig.json` (bones, mirrors, reference poses), `metadata/bank-0.json` and `bank-1.json` (clip timing, flags, attributes, blend and selection trees) and `clips/<bank>/<CLIP>.json` (one clip per file, every bone's tracks) |
| [`unreal/Content/Data/SkateNative`](../../unreal/Content/Data/SkateNative) | The runtime payloads the packaged game reads as loose files: settings, graphs, gestures, physical skeletons and camera data |
| [`runtime.json`](runtime.json) | The descriptor: both directories, the manifest's SHA-256, source identity, required formats and expected counts |
| [`package-manifest.json`](../../unreal/Content/Data/SkateNative/package-manifest.json) | Every payload's relative path, size and SHA-256 |

Numbers in the JSON are binary32 values written as their shortest round-trip decimal (negative zero as `-0.0`); a
value is read as a double and rounded to binary32. A track is one number when it is constant, otherwise one number per
frame. Edit a value and the native files change accordingly; the manifest then needs updating with them.

The `skate.runtime` build step runs [`tools/verify_skate_native.py`](../../tools/verify_skate_native.py). It writes
`build/yorimichi/skate-native/package/`, the complete native package: the runtime payloads plus the rig, clips and
metadata banks built from `motion/` by the plugin's
[`motion_text.py`](../../../../platform/engine/Plugins/Activities/Skate/Tools/motion_text.py). It checks every payload
against both files and writes `build/yorimichi/skate-native/verification.json`; `unreal.compile` waits for it. Nothing
is extracted or downloaded:

```sh
uv run atelier build yorimichi skate.runtime
```

The game reads its animation from typed Unreal assets (`unreal.skate_motion`, see the plugin's
[MOTION_DATA.md](../../../../platform/engine/Plugins/Activities/Skate/MOTION_DATA.md)), so the packaged game ships only
the runtime payloads. The verifier refuses `animation/` or `metadata/` files in the runtime folder. The motion imports,
the Ride clip imports and the offline skating checks (`tools/check_skate_*.py`) read the assembled package.

The bundle is only rebuilt to change a native format or add an optional file, with the plugin's `Tools/` converters
and [`assemble_native_package.py`](../../../../platform/engine/Plugins/Activities/Skate/Tools/assemble_native_package.py),
then `motion_text.py export --native <package> --source motion` for the animation; update `runtime.json` to match. The
plugin's [runtime reference](../../../../platform/engine/Plugins/Activities/Skate/RUNTIME.md#data-bundle) describes the
formats, the converters and the parity checks.
