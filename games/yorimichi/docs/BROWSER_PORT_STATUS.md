# Browser port verification

Updated 2026-10-21. The stock Unreal Third Person baseline now builds, cooks and
renders locally in Chrome through WebAssembly and WebGPU. **Yorimichi itself has
not yet passed a browser build or gameplay check.** The next gate is its skating
runtime, followed by a small representative scene.

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

## Skating investigation in progress

The native float-environment probe confirmed that the real
`FlushDenormalsToZero` enables FTZ. Wasm preserves subnormal operands/results and
the unmodified function correctly returns false. Rounding, a fused-operation
witness and signed zero matched; Emscripten warns that FENV_ACCESS is unsupported.
Simply returning true would leave a known decaying-vector NaN failure unresolved.

The unchanged math corpus contains 34,309 cases. Native default-environment C++
matched the frozen Rust oracle exactly. Unmodified Wasm differed by 166 NaN words
only. Against native FTZ behavior, unmodified Wasm differed by 1,605 words across
493 cases, including 1,439 non-NaN differences.

An ignored diagnostic prototype explicitly handles Wasm subnormal arithmetic,
pre-rounding fused-operation underflow and min/max boundaries. With the engine's
SIMD flags, all non-NaN outputs matched native FTZ; 166 NaN sign/payload
differences remain. Chrome and Node produced identical complete prototype
outputs: 2,101,476 bytes, SHA-256
`75004e4ad8e7bf5e0f5c82533213648613848b07816727d85279e3145b6f7922`.
No NaN canonicalization or tolerance was used. This is a prototype result, not
an integrated or complete numeric-parity pass.

The older full-session Rust check also found a mismatch against current native
C++ before Wasm was introduced: byte 280,528, in an actor-query field during
activation. That failure is retained separately. The current native session has
also been replayed with verified FTZ; its trace differs from the default float
environment. Full Wasm session comparison and sustained decay tests are next.

## Remaining gates

- Resolve numeric compatibility and validate sustained sessions, worker
  startup/shutdown, resource loading and repeated activation/stow.
- Add explicit browser boundaries for native streaming/live tooling and validate
  the mobile painterly material path.
- Build a bounded Yorimichi scene with Cairo, skating/collision data, essential
  UI and a limited sound set; prevent other regions from loading.
- Measure startup, transfer, heap/GPU residency, frame cadence and controller feel.
- Evaluate whole-island residency and multiplayer only after the small scene.

No Yorimichi browser pass, whole-island budget, multiplayer result, Shipping
build or Safari/Firefox compatibility is claimed by the stock baseline.
