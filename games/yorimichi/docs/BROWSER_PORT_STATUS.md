# Browser port verification

Updated 2026-10-21. The stock Unreal Third Person baseline builds, cooks and
renders locally in Chrome through WebAssembly and WebGPU. Current skating math
and a complete session replay also match the native FTZ reference in Chrome.
Yorimichi's C++ has compiled and linked for HTML5, full-module preparation has
passed diagnostically, and the bounded skate-pier asset graph is complete.
The final-source package and browser gameplay check remain pending. **No Yorimichi browser
gameplay pass is claimed yet.**

This continues the [browser port handoff](https://github.com/fontanierh/atelier/blob/codex/webgpu-handoff/games/yorimichi/docs/BROWSER_PORT_HANDOFF.md).

## Recorded environment

| Input | Tested identity |
| --- | --- |
| Atelier code | `c551e430f9fd18438ffb6705477459c0115629b4` |
| Source engine | `PooyaEimandar/UnrealEngine`, `5.8-webgpu`, `3c5c6b098ec411254cb662437676de5548d929be` |
| Engine version | 5.8.3, compatible changelist 55116800 |
| Emscripten | 6.0.10 |
| Dawn | `0af48199d12fab8b838d7dc5af4917eb6b9d0081` |
| Host | Apple M3 Pro, 36 GiB, macOS 27.0.1 |
| Xcode | 27.1, build 27A9275 |
| Chrome | 155.0.8059.85 |
| Playwright | 1.58.2, using the installed Chrome executable |
| Runtime build | Development, `-O2`, `-NoDebugInfo`, `MEMORY64=2` |

The engine remains an independent restricted checkout. Its only tracked local
change limits shader workers to three. No engine implementation or dependency
binary is distributed by this repository. The browser module uses the fork's
lowered 32-bit memory mode; this is not evidence of a native Wasm64 heap.

All native work used normal admission, the aggregate 10 GiB guard and explicit
deadlines. Compile actions, SDK workers and shader workers were capped at three.
The host uses legacy admission. No machine profile or shared installed engine
was changed. Completed stages verified cleanup with empty owned process lists.

## Locally verified stock baseline

| Check | Result |
| --- | --- |
| SDK and platform prerequisites | Passed; UBT reported HTML5 VALID |
| Dawn source build and Metal readback | Passed; expected pixel, no mismatches |
| Tint, SPIRV-Tools and Wasm third-party libraries | Built from the pinned inputs |
| Source editor | Compiled and linked; all 3,077 receipt build products present; app signature verified |
| ShaderCompileWorker and UnrealPak | Built; all receipt products present |
| UnrealGame HTML5 | Built in 1,315 seconds; observed aggregate peak 8.22 GiB |
| Third Person cook/stage/archive | Passed in 515 seconds; observed peak 3.36 GiB |
| Chrome rendered-scene smoke | World entered play; 144 distinct presented frames; screenshot inspected; no recorded assertions, ensures or WebGPU errors |
| Browser input | All nine upstream checks passed, including measured character movement, mouse capture, focus release, resize/DPR, fullscreen and bind-group lifetime |
| Browser audio | All six upstream checks passed, including measured mixer tones through AudioWorklet, autoplay gesture, suspension/resume and cleanup |
| Browser storage | All twelve upstream checks passed, including reload/restart persistence, namespace locking, failed writes/flushes and explicit temporary-storage behavior |
| HTTP content unit checks | All 19 passed; these use fault-injecting HTTP/mocks |
| Preflight unit checks | All eight passed; these include mocked missing-feature cases |

The input test's touch and gamepad samples are emulated. It does not establish
physical-controller latency or skating feel. The audio test measures test tones
with analysers while Chrome is muted; it does not validate Yorimichi's sounds.
Storage tests use an isolated temporary browser profile.

Chrome GPU diagnostics from the input-test process reported Apple M3 Pro/Metal
hardware acceleration and WebGPU enabled. Unreal's browser adapter label itself
was redacted as unknown. The rendering result is supported by actual game frames
and inspected images, rather than an adapter initialization alone.

The Wasm file is 187,784,137 bytes. The streamed-content manifest lists nine files
totaling 51,972,933 bytes. These are artifact sizes, not measured transfer sizes.
The smoke run is not a frame-rate, cold-start or memory-budget benchmark.

![Stock Third Person rendered in Chrome](https://raw.githubusercontent.com/fontanierh/atelier/9d0766c1c30895fbd212ee2e0398c439522a7a30/scene.png)

![Character after keyboard movement](https://raw.githubusercontent.com/fontanierh/atelier/9d0766c1c30895fbd212ee2e0398c439522a7a30/walked.png)

The captures are game-only images retained in `refs/pr-media/browser-port-baseline`.

## Reproduction details discovered locally

Follow the handoff's sequential guarded stages and preserve their caches. The
source editor and host tools were built with `-NoUBA -MaxParallelActions=3
-NoDebugInfo`; the browser runtime used the same options. Emscripten, Binaryen,
CMake and Cargo worker limits were explicit in the stage environment.

The first editor build reached the documented Xcode 27 `ApplePostBuildSync`
failure at the custom shell-script step. Running its exact logged post-build
command separately succeeded. Only after Xcode signed and validated the actual
app was UBT rerun with a scoped `UE_BUILD_FROM_XCODE=1` to finalize receipts.
The override was not set globally and did not substitute for creating the app.

A reduced dependency download excluding iOS omitted resources that AutomationTool
still compiles for an HTML5 run. Three original manifest entries were restored:
the AutomationTool iOS GreenCheck/GreyCheck icons and the Apple automation
BouncyCastle reference. Their original packs totaled about 1.5 MiB; hashes were
verified before installation. No platform module was disabled to hide the error.

The template helper ran once against a new ignored destination. UAT explicitly
selected the source editor app executable and used `-nocompileeditor`,
`-nodebuginfo`, and `-AdditionalCookerOptions=-nullrhi`. NullRHI was used only for
cooking. The browser rendering and input tests used WebGPU. Missing debug
sidecars were optional SymbolFile receipt entries; required runtime files were
present, and no placeholder files or altered receipts were created.

Local evidence is retained under `build/yorimichi/webgpu/`: `guards/`,
`sample-browser/`, `sample-input/`, `sample-audio/`, `sample-storage/` and the
independent `sample-package/HTML5` archive. These outputs are ignored and are
not committed game inputs.

## Skating numeric compatibility

The original browser core correctly refused readiness: Wasm does not provide
native flush-to-zero (FTZ). Returning true would hide a known decaying-vector
failure. The required post-link pass instead makes FTZ arithmetic explicit only
inside retained skating functions and private copies of their math helpers.
Unrelated engine arithmetic and the original libc/libm bodies stay IEEE.
The runtime checks actual input/output arithmetic, including negative zero,
before becoming ready. An unprepared probe exits with code 3 and no output.

Native default-environment C++ matched the unchanged frozen Rust math corpus.
Against native FTZ, original Wasm differed in 1,605 words across 493 cases.
The prepared implementation now matches all bits, including NaN sign and payload,
without tolerances or canonicalization. A larger 111,469-case check adds 66,020
atan2 inputs, FMA operand/NaN combinations, pre-rounding underflow and conversion
boundaries. Its native and Wasm output is 3,029,332 bytes, SHA-256
`4f96c14c8bf477c1b507746789cf309af93033722e8a8d69d43fb8eedcbf4d1f`.
The reproducible guarded check is
`platform/engine/Plugins/Activities/Skate/Tests/check_browser_math.py`.

A complete current-native session replay matched prepared Wasm in Node and
Chrome: 187,273,896 bytes, SHA-256
`f7ed0002cef58f13ec1e3644f40accc60b72ac80b7c9d2ab609103f64cca364e`.
A diagnostic sustained run covered 48,000 ticks (400 simulated seconds), regular
and goofy stance, idle/axis decay and six reactivations. Every pose was finite
and included in the raw-bit digest; periodic full states and final states also
matched. This does not establish the Unreal worker's lifecycle or input latency.

The expanded check exposed link-time inlining outside the simulation namespace.
C++ objects therefore remain optimized, but the initial Wasm link must use
`-O0` without LTO. The pass verifies the actual link manifest and optimizes only
after FTZ preparation. The complete session was rerun with the final initial-link and optimization
policy: Node and Chrome again matched every byte, with zero runtime stderr bytes
in Chrome. The complete guarded check took 49 seconds and peaked at 1.79 GiB.
The sustained check also passed with this final policy in Node and Chrome: all
48,000 ticks and six reactivations matched every byte of the native reference.
The complete guarded check took 291 seconds and peaked at 1.06 GiB, with clean
teardown. Its output is 567,380 bytes, SHA-256
`170c04eb1eb7f8982ee0b58da791766a36fb402d57a56289db53cf7377515033`.

The older frozen Rust full-session check differs from current native C++ before
Wasm is introduced, at byte 280,528 in an activation actor-query field. That
failure remains recorded separately; it has not been relabeled as a Wasm pass.

## Actual game integration

All Yorimichi HTML5 C++ compilation and initial linking passed. Native streaming,
HTTP live tooling and runtime GLB authoring have explicit HTML5 boundaries;
the game uses cooked assets. Two existing typed JSON loops were made compatible
with UE 5.8.3's shared-string keys. Game translation units compile separately to
avoid private helper collisions in Unity files.

The 306,771,833-byte initial module passed scoped arithmetic transformation.
Pinned Binaryen's text parser repeatedly scanned gigabytes while disambiguating
implicit SIMD lane memory indices. Naming the same memory explicitly fixed
assembly without changing the operations: 20,876 spellings were disambiguated,
and the full module assembled in about a minute. A subsequent optimizer attempt
hit the normal aggregate 10 GiB guard; no prepared module was published. Inlining
now uses the default tiny-function threshold, with single-caller expansion disabled.
Optimization succeeded in 137 seconds at an aggregate peak of 6.84 GiB. The result
is 254,499,394 bytes (about 243 MiB); it is diagnostic evidence, pending the normal
final-source build and scene cook.

The explicit browser scene selects the skate pier, Cairo, collision/rails,
typed simulation data, the shared painterly material and original audio. Its
build plan excludes the full island import. Readiness requires a versioned
manifest, required assets and actual riding collision at spawn. Native play
keeps its normal world; `-browserpilot` selects the bounded scene for diagnosis.
The source editor and all game/plugin modules compile successfully. The normal
`browser.scene` dependency graph completed: the park and board, Cairo's body and
merged movement/pawn/fit, shared materials and original audio were imported, and
the browser map and versioned runtime manifest were saved. A fresh typed-data
reload verified 3,324 clips, 131,642 frames, seven runtime files, and exact
7,200-step replays across twelve cases, including negative controls. The mobile
shader cook and actual browser gameplay remain pending.

## Remaining gates

- Validate the actual Unreal worker startup/shutdown, resource loading and
  repeated activation/stow in the cooked game.
- Validate the mobile painterly material path in the actual scene cook.
- Build a bounded Yorimichi scene with Cairo, skating/collision data, essential
  UI and a limited sound set; prevent other regions from loading.
- Measure startup, transfer, heap/GPU residency, frame cadence and controller feel.
- Evaluate whole-island residency and multiplayer only after the small scene.

No Yorimichi browser pass, whole-island budget, multiplayer result, Shipping
build or Safari/Firefox compatibility is claimed by the stock baseline.
