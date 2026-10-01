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
and original-format data remain development migration/oracle inputs. Normal builds do not read them.
Project-authored optional clip overrides use their own configuration format.

Component comparisons against the pinned original are recorded in the
[C++ migration notes](../../../../platform/engine/Plugins/Activities/Skate/CXX_PORT.md).
Complete gameplay/session equivalence and the Unreal hookup are still under validation; successful bundle
verification checks data integrity, not gameplay equivalence.
