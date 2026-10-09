# Native skating data

The data the Skate session runs on, shared by every game that uses the plugin. It holds 3,334 payloads in the
plugin's native formats: 3,324 animation clips (131,642 frames), the animation rig and both metadata banks, the
action, motion and camera graphs, 285 gesture patterns, camera data, settings and physical skeletons, 70,695,340
bytes in all.

| Path | Content |
| --- | --- |
| [`motion/`](motion) | The animation as readable JSON: `rig.json` (bones, mirrors, reference poses), `metadata/bank-0.json` and `bank-1.json` (clip timing, flags, attributes, blend and selection trees) and `clips/<bank>/<CLIP>.json` (one clip per file, every bone's tracks) |
| [`runtime/`](runtime) | The rest as readable JSON: `settings.json` (records and typed fields by category), `action-graph.json`, `motion-graph.json` and `camera-graph.json` (element trees), `camera.json` (shots and shakes), `gestures.json` (sets, patterns and points) and `physics-skeletons.json` (bones and their limits) |
| [`package-manifest.json`](package-manifest.json) | Every payload's relative path, size and SHA-256 |
| [`bundle.json`](bundle.json) | The descriptor: the manifest's SHA-256, source identity, required formats and expected counts |

Numbers in the JSON are binary32 values written as their shortest round-trip decimal (negative zero as `-0.0`); a
value is read as a double and rounded to binary32. A value with no finite decimal is its bit pattern as a `0x` string.
A track is one number when it is constant, otherwise one number per frame. Edit a value and the payloads change
accordingly; the manifest and `bundle.json` then need updating with them.

## Using it in a game

[`Tools/native_package.py`](../Tools/native_package.py) assembles the complete package (the rig, clips and metadata
banks built from `motion/` by [`motion_text.py`](../Tools/motion_text.py), and the other payloads built from
`runtime/` by [`runtime_text.py`](../Tools/runtime_text.py)) and checks every payload against the manifest and
`bundle.json`:

```sh
python3 platform/engine/Plugins/Activities/Skate/Tools/native_package.py \
  --assemble build/<game>/skate-native/package --output build/<game>/skate-native/verification.json
```

A game runs this as a build step, then imports the package into typed Unreal assets ([TYPED_DATA.md](../TYPED_DATA.md))
that it loads and cooks. The Ride clip imports and offline skating checks read the assembled package.

`motion_text.py export --native <package> --source motion` and `runtime_text.py export --native <package> --source
runtime` write the JSON back from a package; both converters rebuild every payload byte for byte. The
[runtime reference](../RUNTIME.md#data-bundle) describes the formats and the parity checks.
