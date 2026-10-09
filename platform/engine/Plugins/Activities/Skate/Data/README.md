# Native skating data

The data the Skate session runs on, shared by every game that uses the plugin. It holds 3,334 payloads in the
plugin's native formats: 3,324 animation clips (131,642 frames), the animation rig and both metadata banks, the
action, motion and camera graphs, 285 gesture patterns, camera data, settings and physical skeletons, 70,695,340
bytes in all.

| Path | Content |
| --- | --- |
| [`motion/`](motion) | The animation as readable JSON: `rig.json` (bones, mirrors, reference poses), `metadata/bank-0.json` and `bank-1.json` (clip timing, flags, attributes, blend and selection trees) and `clips/<bank>/<CLIP>.json` (one clip per file, every bone's tracks) |
| [`runtime/`](runtime) | The runtime payloads a packaged game reads as loose files: settings, graphs, gestures, physical skeletons and camera data |
| [`runtime/package-manifest.json`](runtime/package-manifest.json) | Every payload's relative path, size and SHA-256, the motion payloads included |
| [`bundle.json`](bundle.json) | The descriptor: the manifest's SHA-256, source identity, required formats and expected counts |

Numbers in the JSON are binary32 values written as their shortest round-trip decimal (negative zero as `-0.0`); a
value is read as a double and rounded to binary32. A track is one number when it is constant, otherwise one number per
frame. Edit a value and the native files change accordingly; the manifest and `bundle.json` then need updating with
them.

## Using it in a game

[`Tools/native_package.py`](../Tools/native_package.py) assembles the complete native package (the runtime payloads
plus the rig, clips and metadata banks built from `motion/` by [`motion_text.py`](../Tools/motion_text.py)), checks
every payload against the manifest and `bundle.json`, and stages the runtime payloads into the game's runtime folder.
Nothing is extracted, converted or downloaded:

```sh
python3 platform/engine/Plugins/Activities/Skate/Tools/native_package.py \
  --assemble build/<game>/skate-native/package --stage games/<game>/unreal/Content/Data/SkateNative \
  --output build/<game>/skate-native/verification.json
```

A game runs this as a build step before compiling; the staged folder is generated, like the rest of `Content/`. The
game reads its animation from typed Unreal assets ([MOTION_DATA.md](../MOTION_DATA.md)), so it ships only the
runtime payloads, and the tool refuses `animation/` or `metadata/` files in `runtime/`. The motion import, Ride clip
imports and offline skating checks read the assembled package.

The data is only rebuilt to change a native format or add an optional file, with the converters in
[`Tools/`](../Tools) and [`assemble_native_package.py`](../Tools/assemble_native_package.py), then
`motion_text.py export --native <package> --source motion` for the animation; update `bundle.json` to match. The
[runtime reference](../RUNTIME.md#data-bundle) describes the formats, the converters and the parity checks.
