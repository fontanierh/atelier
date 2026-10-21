# Local WebGPU scene

The browser port currently targets the skate pier with Cairo, the skating core,
painterly rendering and original sound. It is a bounded scene; island streaming
and multiplayer need separate validation. See [verification status](BROWSER_PORT_STATUS.md)
for completed checks and remaining gates.

Use the restricted `PooyaEimandar/UnrealEngine` `5.8-webgpu` source checkout at
`3c5c6b098ec411254cb662437676de5548d929be`, and its pinned Emscripten 6.0.10 SDK.
The stock Third Person baseline must work before importing the game. The
[source handoff](https://github.com/fontanierh/atelier/blob/codex/webgpu-handoff/games/yorimichi/docs/BROWSER_PORT_HANDOFF.md)
covers the engine, SDK, Dawn, host-tool and template stages. Preserve their
build outputs and normal machine admission. The engine sources and binaries
are not distributed here.

Activate the SDK and set `UE_ROOT` to that source engine. Then, from this checkout:

```sh
# Audio masters are fetched through the normal shared download cache.
uv run atelier fetch yorimichi

# Normal incremental dependencies prepare and validate the required assets.
ATELIER_AGENT=YOUR_OWNER nice -n 10 uv run atelier build yorimichi browser.package \
  --rebuild-reason "Initial source-engine browser scene build in this checkout"

# A dedicated Chrome profile retains this scene's browser storage.
ATELIER_AGENT=YOUR_OWNER nice -n 10 uv run atelier play yorimichi --profile browser
```

`CHROME` may select a Chrome executable. The preview serves only on loopback,
uses a stable port (8840) for saved settings, and runs its own Chrome process tree under normal
admission and an aggregate memory guard. Close the session with Ctrl-C; its
default deadline is three hours. Extra play arguments may set `--seconds N` for
a shorter diagnostic. `--port N` selects another stable loopback origin; port 0
is explicitly temporary. Existing browser windows are not controlled.

The initial Wasm link deliberately uses `-O0` without LTO while C++ compilation
remains optimized. A required post-link step verifies the link manifest, makes
scoped skating FTZ arithmetic explicit, assembles/validates, and then optimizes
with bounded inlining. An unprepared module refuses skating readiness. Do not
replace this with a readiness override or optimize away the named boundaries
before preparation.

`browser.scene` builds/imports the scene without cooking. `browser.compile`
builds the actual HTML5 game module. `browser.package` selects both and cooks
only the explicit browser content/staging profile. A native launch with
`-browserpilot` selects the same scene for diagnostic comparison; ordinary
native play keeps the island.

Generated assets remain in `build/yorimichi` and ignored `unreal/Content`.
Required Cairo fit checks, typed skating data verification, original park
collision/rails and audio preparation remain in the normal dependency graph.
