# Native skating data

The project-native bundle is committed in
[`unreal/Content/Data/SkateNative`](../../unreal/Content/Data/SkateNative). It contains 3,334 payloads:
3,324 decoded animation clips (131,642 frames), the animation rig and both metadata banks,
action/motion/camera graphs, 285 gesture patterns, camera data, settings and physical skeletons.
The payloads total 70,695,340 bytes. They contain converted records from EA Skate 3, distinct from the
Apache-2.0 recovered source, without original meshes, textures, audio or executables.

[`runtime.json`](runtime.json) pins the native package manifest, source identity, counts and required formats.
[`package-manifest.json`](../../unreal/Content/Data/SkateNative/package-manifest.json) records every relative
payload path, byte size and SHA-256. The normal `skate.runtime` build step runs
[`verify_skate_native.py`](../../tools/verify_skate_native.py), checks the tracked bundle in place, and writes
a verification report under `build/yorimichi/skate-native/`. It does not compile or stage a worker.
Fresh checkouts need no asset extraction, conversion, Rust toolchain or external data cache for this step.

The one-time [`assemble_native_package.py`](../../../../platform/engine/Plugins/Activities/Skate/Tools/assemble_native_package.py)
uses original-format data restored from pinned historical Git into ignored build output for migration/oracle work.
Original-format shipping files and the Rust worker are removed; normal builds do not read historical inputs.
Project-authored optional clip overrides use their own configuration format.

Component comparisons against the pinned original are recorded in the
[C++ migration notes](../../../../platform/engine/Plugins/Activities/Skate/CXX_PORT.md).
Complete baseline/latest-main Session comparisons and native Unreal editor compilation, live gameplay,
park and frame-pacing checks pass. The descriptor is editor-validated within those finite recovered-source
corpora; it does not claim original-console parity or cooked/package validation. Bundle verification checks
data integrity independently of gameplay equivalence.
