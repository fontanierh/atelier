# Yorimichi browser port handoff

Prepared on 2026-10-20 for continuing the investigation on another machine.
Checkpoint workflow guidance updated on 2026-10-21 against main `7a73248b`.

The goal is to run Yorimichi locally in a player's browser, with WebAssembly
executing the game and WebGPU rendering on the player's GPU. The preferred next
experiment is a stock Unreal Third Person browser build using the source fork
below. Establish that baseline before adapting Yorimichi or writing a renderer.

The source audit found an implemented WebGPU renderer, shader compiler, HTML5
target, browser platform services, HTTP content loading and multiplayer gateway
in Pooya Eimandar's fork. Access to the restricted engine source now works. This
is a materially better starting point than the incomplete UT4 experiment that
led to it. Source availability does not establish that Yorimichi will compile,
look correct, fit in browser memory or perform acceptably.

## 1 Current state and next action

### Completed

- Investigated SimplyStream's public product pages, build documentation and
  public agent API description.
- Read the complete public UT4 WebGPU experiment, including its loader, recipe,
  hosting helper, screenshots and issues.
- Restored Epic GitHub organization access. Authenticated reads succeeded for
  both `EpicGames/UnrealEngine` and `PooyaEimandar/UnrealEngine`.
- Pinned the source fork to the revision in section 2 and inspected its browser
  platform, renderer, shader compiler, dependency builders and validation docs.
- Inspected Yorimichi's source for platform assumptions, especially skating math,
  controller sampling, world residency, materials, native tooling and networking.

### Work still required

- Prepare a separate source-engine checkout and the receiving machine's tools.
- Build the fork and render a real Third Person scene in a browser.
- Independently validate the fork's documented capabilities and constraints.
- Port a small Yorimichi scene, then evaluate island residency and multiplayer.

No engine compilation, browser game launch, GPU benchmark, shader cook or
Yorimichi browser build was performed during this investigation. No SimplyStream
account was created, project uploaded, trial credit spent or paid call made.
The owner intends to handle any SimplyStream signup separately.

**First action on the receiving machine:** read its current working rules and
capacity instructions, verify source access, record host/tool versions, and
prepare the pinned fork in an independent directory. Follow the staged baseline
in sections 10–13. Do not begin with a whole-island cook.

## 2 Source revisions and evidence boundaries

| Source | Audited identity | Meaning |
| --- | --- | --- |
| Unreal source fork | `PooyaEimandar/UnrealEngine`, branch `5.8-webgpu`, commit `3c5c6b098ec411254cb662437676de5548d929be` | Engine implementation inspected through authenticated GitHub reads |
| Fork commit | 2026-10-19, `[HTML5] Add browser video textures and public MP4 cube demo` | Source snapshot, not an independently passing build |
| Fork engine version | Unreal Engine `5.8.3`, compatible changelist `55116800` | Read from the fork's `Engine/Build/Build.version` |
| Public fork documentation | `PooyaEimandar/UnrealEngine-WebGPU`, commit `8ba0a9a8f6297ba342e1d91a13117979653f94f0` | Public overview audited alongside engine source; its feature table can lag implementation |
| UT4 experiment | `itpick/ut4-webgpu`, commit `33162d0cc8c6eb664f5be432a23f142cb27d8fb9` | Incomplete recipe and environment/initialization evidence |
| Dawn | Release `v20261007.202641`, source commit `0af48199d12fab8b838d7dc5af4917eb6b9d0081` | Fork's declared dependency pin |
| Sib | Commit `806b59fa59f060994f663c2faad52dcee00e4845` | Gateway dependency pinned in Cargo metadata |
| Emscripten | `6.0.10` | Fork author's validated SDK version; use this for the first reproduction |
| Initial Atelier inspection | `316dc9c3a5fc03e3991840a7dcfb1f00001398b5` | Warm checkout used for the first Yorimichi source inspection |
| Handoff base | `f66f6d4f61ae1d24e1889e979187985ad5096aa1` | Current main used for this documentation branch and guard API checks |

Start with the audited engine commit. A newer branch head may contain useful
fixes, but changing revisions creates a new experiment: inspect the changes,
record the new SHA and keep its results separate.

The initial audit downloaded selected source files and metadata into temporary
local storage. Those scratch directories, author-local evidence paths and this
chat are not required inputs on the receiving machine. All necessary upstream
repositories and relevant source paths are identified here.

Use these evidence categories when continuing:

- **Source verified:** an implementation or constraint was inspected in source.
- **Upstream reported:** a result appears in the fork author's documentation.
- **Locally verified:** the receiving agent actually executed the named check on
  the recorded machine and revision and retained its outputs.
- **Proposed:** a design or test still to implement.

Do not turn an upstream report or source implementation into a local pass.

## 3 What SimplyStream provides

SimplyStream's primary browser path compiles Unreal and the game to WebAssembly,
then renders through a custom WebGPU backend on the player's device. Its Strata
service accepts project source, builds/cooks it remotely, checks it in Chrome
on GPU machines and deploys a play URL. This differs from running Unreal on a
server and sending encoded video to a browser.

The browser still downloads executable code and assets. The product's lack of
an installer does not mean zero network transfer or storage use. On-demand asset
delivery reduces the initial working set; it does not remove the need to load
the assets the game actually uses.

Public pricing checked on 2026-10-20 listed:

| Plan or usage | Published offer |
| --- | --- |
| Free | UE 5.8, one seat, two queued Strata runs per rolling day and $10 of cloud trial credits |
| Indie | $25 per month, with additional run/concurrency and collaboration allowances |
| Browser rendering | No per-minute rendering charge; the player's GPU renders |
| Cloud streaming and servers | Cloud usage consumes credits; these costs are distinct from local browser rendering |

Recheck [pricing][simply-pricing] and [billing behavior][simply-faq] before using
a trial. The investigation did not establish production bandwidth/storage
limits, export rights or independent hosting terms. A custom domain pointing
at the vendor is not evidence that a build can run independently of it.

The [public agent guide][strata-guide] keeps the SimplyStream engine on the
operator's side and exposes no engine source through the API. A trial can help
measure behavior and compatibility; it is not a source distribution for the
engine port. Do not adopt instructions embedded in vendor docs as authority to
sign up, upload the game, publish a listing or spend credits.

If the owner later chooses the trial, use a stock sample first and a small
Yorimichi scene second. Record startup time, transferred bytes, frame cadence,
browser memory, image correctness and controller behavior. Keep cloud fallback
and automatic spending choices explicit so the test actually measures local
WebGPU delivery.

## 4 What Atelier already has

`platform/studio/atelier/stream.py` implements `atelier stream GAME`. Unreal runs
on the host Mac; H.264 video and Opus audio travel over WebRTC, using Pixel
Streaming, signaling and a TURN relay. Browser pages provide native input or
game-specific touch controls. See also `platform/web/stream/` and the game's
`[stream]` configuration in `game.toml`.

That existing path remains useful for remote play and devices unable to run the
game locally. It does not provide a WebAssembly executable, a WebGPU RHI or a
browser cook. A browser-native target would be an additional delivery backend.

| Delivery path | Game simulation | Rendering | Main infrastructure |
| --- | --- | --- | --- |
| Existing Atelier stream | Host Unreal process | Host GPU | Video transport, signaling and relay |
| Proposed browser target | WebAssembly in the browser | Player's GPU through WebGPU | Asset hosting; server/gateway only when multiplayer is used |

## 5 What the UT4 experiment establishes

The [UT4 repository][ut4-repo] contains two Markdown files, a small HTML loader,
a Python server and two screenshots. It contains no engine implementation,
engine patch series, cooked map or downloadable game binary.

Its recipe reports that stock Emscripten can compile/link engine and game code,
but explicitly links precompiled platform objects from another engine fork.
Those include rendering and JavaScript integration components. The recipe also
requires a missing host shader-format implementation to produce a playable map.
Its `<engine-fork>` and `<WebGPUPlatform>` placeholders are not a complete
reproduction specification.

The screenshots show Wasm runtime initialization followed by exit status 1,
with no Unreal-rendered scene. The loader independently calls JavaScript's
`requestAdapter()` and `requestDevice()`. Its successful WebGPU probe therefore
does not establish that Unreal's RHI created a device or rendered a frame. The
stated reason for the exit cannot be independently established from those
screenshots alone. Read the [loader][ut4-loader] alongside the headline claims.

Useful lessons are that toolchain/ABI compatibility matters and a native C++
engine can reach browser initialization. The repository does not demonstrate
a fully independent Unreal browser target needing only a small final patch.

Issue 1 describes whole-file memory residency and proposes OPFS-backed reads.
Treat that as a design proposal, not a completed loader. The newer fork audited
here already implements a different HTTP/WASMFS approach.

Do not copy the experiment's blanket warning suppression, treat an archive hash
mismatch as a successful reproducibility check, or assume permission to reuse
its unprovided binary dependencies. Pin and validate actual inputs instead.

## 6 What is implemented in the newer fork

The restricted [source fork][engine-fork] includes the following implementations.
These paths are relative to the engine checkout, not the Atelier repository.

| Area | Source paths and inspected behavior |
| --- | --- |
| Rendering | `Engine/Source/Runtime/WebGPURHI/`: device, buffers, textures, pipeline and binding caches, shaders, command context, viewport and host/browser surfaces |
| Shader cooking | `Engine/Source/Developer/WebGPUShaderFormat/`: host shader-format registration and shader compiler implementation |
| Shared shader metadata | `Engine/Source/Runtime/WebGPURHI/Public/WebGPUShaderResources.h`: data consumed by compiler and runtime |
| Build and packaging | `Engine/Platforms/HTML5/Source/Programs/UnrealBuildTool/` and `AutomationTool/`: target, SDK, toolchain, staging and deployment integration |
| Browser runtime | `Engine/Platforms/HTML5/Source/Runtime/`: application/input, core platform services, audio, HTTP, persistence, launch and socket integration |
| Content loading | `Core/Private/HTML5/HTML5HttpContent.cpp` and `Build/Templates/library_html5_content.js`: staged manifest and HTTP range-backed reads |
| Multiplayer | `Sockets/Private/HTML5/` and `Programs/HTML5Gateway/`: browser socket bridge and native gateway |
| Dependencies | `Engine/Source/ThirdParty/Dawn/BuildForUE/` and `Engine/Platforms/HTML5/Build/BuildThirdParty.sh`: source build paths for required tools/libraries |
| Checks | `Engine/Platforms/HTML5/Build/Scripts/`, `Tests/`, RHI tests and `docs/`: smoke, services, streaming and multiplayer checks |

### Shader pipeline

The inspected shader compiler preprocesses Unreal HLSL, uses the existing
ShaderConductor/DXC path to generate SPIR-V, reflects resources, assigns bindings,
transforms constructs that WGSL cannot express, runs Tint and packages WGSL with
the runtime header and resource metadata. It includes compatibility work beyond
merely invoking a language translator.

This paired compiler/RHI implementation is the principal reason to evaluate
this fork before implementing our own renderer. Keep the compiler, runtime
metadata, Dawn headers and Emscripten binding package on matching revisions.

### Rendering scope

`WebGPUDynamicRHI.cpp` selects `SF_WEBGPU_ES3_1` and feature level ES3.1. SM5 and
SM6 entries are unavailable. RHI-thread execution and parallel RHI execution
are disabled; texture streaming is enabled. Browser PSO precaching and async
pipeline precompilation are disabled in the inspected capability flags.

This is Unreal's mobile rendering path backed by WebGPU. A capable desktop GPU
does not turn it into Unreal's desktop renderer. The fork's platform INI files
disable unsupported distance fields, virtual texturing, Nanite and other shader
permutations after ordinary project defaults are loaded.

Do not assume SimplyStream's advertised desktop features, Lumen or Nanite are
provided by this independent fork. See the pinned source and
[rendering design][engine-rendering-design].

### Content and runtime scope

The browser game runs on a worker, with pthread support and JSPI used for waits.
The toolchain requires the worker-based main path when WebGPU is enabled. Browser
API support beyond `navigator.gpu` matters, including WebAssembly JSPI,
transferable OffscreenCanvas and cross-origin isolation.

UAT generates `HTML5Content.txt` for staged files. The platform mounts those files
through a WASMFS HTTP backend, preserving engine-facing paths for cooked content,
loose runtime data and the staged command line. Reads can request ranges instead
of making all paks resident in the Wasm heap. The inspected defaults use 1 MiB
content chunks and a 64 MiB retained JavaScript content cache. That cache is
separate from the Wasm heap and GPU allocations.

The public overview had lagged recent networking/media work. Use the pinned
implementation and its contemporaneous docs when deciding what exists; do not
infer a feature's absence solely from an older cached overview.

### Dependency and commercial boundaries

The inspected core renderer and shader-format code had source implementations;
no SimplyStream credential or activation dependency was found in those paths.
The fork documents optional commercial modules separately from its core platform.
That is not a promise that all future capabilities are included.

Keep Unreal engine source and modifications in their authorized repository and
storage. The public documentation's Creative Commons license does not apply to
the engine implementation. Do not copy private engine source, dependency blobs,
credentials or private captures into Atelier's public repository. This handoff
links to source rather than redistributing it.

## 7 Memory models and measurement

Three quantities need separate treatment: compiler pointer width, browser linear
memory capacity and actual host/GPU resource use.

- The fork defaults to 64-bit C++ pointers lowered to Wasm32 using
  `MEMORY64=2`. Its default maximum linear memory is 4096 MiB.
- `MEMORY64=2` does not unlock a 16 GiB browser heap. Emscripten describes it as
  a Wasm64 compiler/linker model lowered by Binaryen to Wasm32.
- The fork has an optional native Wasm64 mode. It requires appropriate browser
  support and compatible libraries. Treat it as a separate configuration to
  validate, not a universal escape from memory budgeting.
- SimplyStream's documented default of 3,998 MB is a vendor configuration, not
  a universal statement about all WebAssembly implementations.
- Wasm capacity does not shrink whenever allocations are freed. Capacity,
  live allocations, JavaScript heap, process RSS/physical footprint and shared
  Chrome GPU-process memory are different measurements.

Host guard ceilings are another independent quantity. A 24 GiB native build
reservation does not give the browser a 24 GiB Wasm heap.

Measure the stock sample before setting a browser content budget. Measure
Yorimichi itself before declaring that it fits or needs native Memory64. A
large desktop guard ceiling is not a measurement of the game's browser needs.
See [Emscripten memory settings][emscripten-memory] and the fork's
[runtime design][engine-runtime-design].

## 8 Source access on another machine

The account was originally linked years ago but no longer belonged to the Epic
organization. The Epic page showed an old link, an Action Recommended notice
and a Relink button. No Epic entry was present in Authorized OAuth Apps. Do not
require a nonexistent authorization to be revoked before proceeding.

The owner completed the repair and source reads succeeded. On the receiving
machine, verify that its browser, `gh` and Git are using the intended account:

```sh
gh api user --jq .login
gh api repos/EpicGames/UnrealEngine --jq .full_name
gh api repos/PooyaEimandar/UnrealEngine --jq .full_name
gh api repos/PooyaEimandar/UnrealEngine/branches/5.8-webgpu --jq .commit.sha
```

If needed, follow [Epic's linking instructions][epic-access]: connect GitHub from
Epic's linked accounts, authorize while signed into the intended GitHub account,
then accept the organization invitation. Authorization and accepted organization
membership are distinct steps. Epic's guide gives invitations a seven-day window.

If Epic's repository opens but the fork does not, follow the public fork's
access instructions and investigate fork permissions. A 404 can reflect missing
access; it does not establish that the repository is absent. If browser access
works but API/Git access fails, investigate that machine's authentication and
repository permissions. Do not print tokens or pass them into recorded commands.

GitHub has separate Authorized OAuth Apps and Authorized GitHub Apps lists.
Only revoke an Epic authorization if one actually exists and a reset is needed.
The screenshot's Relink action is the appropriate next thing to try when there
is no OAuth entry. An absent entry alone does not establish why the link failed.
See [GitHub OAuth authorization management][github-oauth].

## 9 Machine preparation and isolation

### Supported starting host

The fork author's validated build/package path is an Apple Silicon Mac. Native
renderer code exists for other desktop hosts, but Windows/Linux build and host
validation were incomplete in the audited documentation. Do not present the Mac
commands below as a validated Windows or Linux recipe.

For another OS, first audit its host toolchain, source dependencies and platform
status. The first milestone remains a stock sample on that actual host. Do not
install WSL or change machines silently to work around an unsupported path.

Required tools for the Mac path are Git/GitHub source access, full Xcode and its
SDK, Python, CMake, Ninja, Rust/Cargo for the packaged host, Emscripten 6.0.10,
Node supplied by emsdk, Playwright and a real Chrome installation with the
required features. Some bundled tools may need Rosetta; follow the fork's
requirements for the actual dependencies on that host.

Record, without dumping environment secrets:

```sh
git --version
gh api user --jq .login
xcodebuild -version
xcode-select -p
python3 --version
cmake --version
ninja --version
rustc --version
cargo --version
emcc --version
node --version
```

The audit machine had Xcode 27.0 and the shared installed UE 5.8.2 build at
changelist 56702186. The fork is UE 5.8.3. Emscripten and Ninja were not found
on the inspected PATH or standard candidate locations. These observations are
not assumptions about the receiving machine.

There is no measured clean-build duration or disk requirement for this fork
from this investigation. Plan for a substantial source checkout, dependency
trees, editor binaries, intermediate objects, cooked assets and retained logs.
The old UT4 recipe's disk estimate is not a verified sizing result for this fork.

### Repository and engine layout

Use an independent Atelier worktree and a separate engine checkout. Preserve the
canonical Atelier checkout, its artifacts and the shared installed UE engine.
The source fork is a modified engine, not a plugin to drop into the installed
Launcher engine.

Set the following variables to absolute paths on the receiving machine. They
are examples of roles, not paths to copy verbatim:

```sh
export WGPU_ATELIER=/absolute/path/to/own-current-atelier-worktree
export WGPU_ENGINE=/absolute/path/to/independent-unreal-webgpu-source
export WGPU_EMSDK=/absolute/path/to/emsdk
export WGPU_TOOLS=/absolute/path/to/browser-test-tools
export WGPU_OUTPUT="$WGPU_ATELIER/build/yorimichi/webgpu"
export WGPU_SAMPLE="$WGPU_OUTPUT/ThirdPersonWeb"
export WGPU_CHROME='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
export WGPU_OWNER=unique-owner-on-this-machine
export ATELIER_AGENT="$WGPU_OWNER"
export CARGO_BUILD_JOBS=3
```

Use a current main Atelier baseline for the launcher and capacity client, with a
task branch for later implementation changes. This handoff was written on a
documentation branch; it does not introduce a browser build command.

Use normal `atelier build` in fresh and warm worktrees. Current main checks
reusable task results by actual input, product, command, tool and engine
identities, locally and in configured private checkpoints. Matching Git
revisions are not required, and the separate exact-revision transfer command
has been removed. Follow the [build checkpoint workflow][atelier-checkpoints]
for machine-local private storage configuration and restore behavior. Keep the
configured repository identity outside tracked source and documentation.

Checkpoint reuse still requires compatible engine and tool identities. Existing
compiled 5.8.2 products cannot certify this 5.8.3 fork's binaries or cooks. The
current checkpoint implementation targets the installed macOS toolchain; it
does not supply an Atelier browser build backend. Portable art inputs and
independently verified products may be reusable through their normal dependency
graph. Different engine products need their own provenance and validation.

Inspect normal build misses with `--plan --explain`. Unknown or expensive native
misses stop before admission; fix cache access or input declarations first and
use a specific `--rebuild-reason` only for necessary work. Do not clear caches,
force whole graphs, share mutable Content/Binaries/Intermediate trees or
manufacture stamps. Preserve completed producers and generated products until
checkpoint upload, verification and a receiving restore are accepted. Integrate
main and run `uv sync` only after the checkout's enclosing caller and all native
children have stopped.

## 10 Atelier admission and guarded execution

Read the receiving checkout's `AGENTS.md`, applicable `CONTRACTS`, the contract
skill, [capacity guide](../../../docs/BUILD_CAPACITY.md), and that machine's
render board and current supervisor/lock records before native work. Machine
policy and current owner instructions take precedence over this dated handoff.

Register a unique owner, set its task line and verify a persistent board listener
using [the board guide](../../../docs/AGENT_BOARD.md). For a Codex session, the
notification argv must target that session's actual existing chat ID. Do not
copy the original session's owner or notification destination.

In full capacity mode, use the installed default client with
`ATELIER_CAPACITY_CLIENT` unset. Ordinary heavy jobs self-admit. No coordinator
permission, Holding/Waiting handshake or extra legacy lock is needed. Check
current incidents and honor bounded maintenance/capture arrangements.

All engine/tool compilation, UAT cooking and GPU browser tests below need
admission and memory guards. `nice`, `--jobs 3` and an upstream test script do
not provide those protections. Standalone CMake, Cargo and Ninja work also
needs the normal compile workflow.

Keep the three-worker tuning unless the receiving machine has a separately
validated setting. Compiler/shader workers, browser pthread pools and broker
resource reservations are different controls. The fork's browser pthread pool
default of 16 is not a request to compile with 16 workers.

Run uncertain or longer-than-30-second work through the client's background job
facility, retaining the session/job ID. Poll in bounded calls of at most ten
seconds, keep delivery armed and report concrete progress at least every minute.
Give each stage an explicit deadline and observable exit condition. Do not put
a shorter shell timeout around the guard/controller. Cancel through its owned
controller and allow cleanup to finish. Quit test games promptly.

### Memory selection

The owner's standing authorization allows larger guarded sessions, including
24 GiB when needed, when the broker admits the full reservation. Do not request
another per-session memory grant. This does not authorize understating a
reservation, weakening a guard, changing client profiles or bypassing refusal.

The inspected current-main `guarded.run` API supports `compile_memory_gib` for
an explicit full-capacity compile reservation, paired with the same
`limit_gib`. The ordinary standalone guard CLI does not expose a corresponding
memory flag. Passing only a larger guard limit against a smaller reservation
must fail. Verify the installed API before using the wrapper below.

The documented `atelier build ... --cook-memory-gib` option concerns normal
package cooks; it is not a general CLI flag for raw `RunUBT.sh` invocations.
Likewise, `atelier play --memory-gib` does not configure standalone tool builds.

### Guard wrapper for the staged commands

This shell function uses Atelier's existing guard API once per invocation. It
does not add a second lock around `atelier build` or `atelier play`; do not use
it around those commands. Source/build working directories and reports remain
independent. It deliberately refuses an older launcher lacking the required API.

Run `uv sync` in the independent Atelier checkout before defining it. Save the
function in an ignored local script if separate shell cells need to source it.

```sh
webgpu_stage() {
  local wgpu_stage_name="$1"
  local wgpu_stage_seconds="$2"
  local wgpu_stage_memory="$3"
  local wgpu_stage_cwd="$4"
  shift 4
  (
    cd "$WGPU_ATELIER" || return
    nice -n 10 uv run python - \
      "$wgpu_stage_name" "$wgpu_stage_seconds" "$wgpu_stage_memory" \
      "$wgpu_stage_cwd" "$WGPU_OUTPUT/guards" "$@" <<'PY'
import inspect
import os
from pathlib import Path
import sys
import uuid

from atelier.harness.safety.guarded import run

label, seconds, memory, workdir, reports, *command = sys.argv[1:]
if not command or "compile_memory_gib" not in inspect.signature(run).parameters:
    raise SystemExit("Use a current Atelier launcher with explicit compile reservations")
if not os.environ.get("ATELIER_AGENT"):
    raise SystemExit("Set a unique ATELIER_AGENT owner first")
if os.environ.get("ATELIER_CAPACITY_CLIENT"):
    raise SystemExit("Use the machine's installed default capacity client")
if not 10 <= float(memory) <= 24 or float(seconds) <= 0:
    raise SystemExit("Use a supported 10-24 GiB reservation and a positive deadline")
report = Path(reports).resolve() / (label + "-" + uuid.uuid4().hex)
print("Guard report:", report, flush=True)
os.chdir(workdir)
raise SystemExit(run(
    command, report,
    timeout=float(seconds),
    purpose="WebGPU pilot: " + label,
    kind="compile",
    limit_gib=float(memory),
    compile_memory_gib=float(memory),
    progress=25,
    track_tree=True,
    aggregate_tree=True,
    watch=("UnrealEditor", "UnrealEditor-Cmd", "ShaderCompileWorker", "dotnet"),
))
PY
  )
}
```

The wrapper uses compile admission and aggregate tree supervision, including
for a combined package/browser-check stage. Do not lower its accounting because
the visible parent is Python, Bash, Node or dotnet. If full admission or the
actual reservation is refused, retain the error and diagnose normally. If the
receiving machine lacks the configured managed environment, establish that
environment through its supported setup before launching these stages.

The sample deadlines below are proposed bounds, not measured estimates. Allow
the capacity queue and final cleanup to complete without a shorter executor
deadline. Adjust a stage's planned deadline before launch if the machine's
observed work requires it.

## 11 Fetch the source and prepare dependencies

### Source and SDK

Choose new directories; preserve existing work rather than resetting it. Keep
engine source outside the public Atelier tree. Authenticate Git through the
normal GitHub workflow if the receiving machine does not already have access.

```sh
gh repo clone PooyaEimandar/UnrealEngine "$WGPU_ENGINE" -- \
  --branch 5.8-webgpu --single-branch --filter=blob:none
git -C "$WGPU_ENGINE" fetch origin 3c5c6b098ec411254cb662437676de5548d929be
git -C "$WGPU_ENGINE" checkout --detach 3c5c6b098ec411254cb662437676de5548d929be
git -C "$WGPU_ENGINE" rev-parse HEAD
git -C "$WGPU_ENGINE" status --short
```

Fetching/checking out a large source tree can take time; keep the client
responsive. Do not run engine `Setup.sh` until the source identity and machine
admission prerequisites are established.

Install the non-engine host tools through that machine's usual supported
package manager. On a prepared Homebrew Mac, the missing tools may include
`cmake`, `ninja` and `python`; do not reinstall or change Xcode globally merely
because a guide contains setup commands. CPU-heavy source package builds must
also use admission.

For the SDK, start from a new emsdk checkout if one is needed:

```sh
git clone https://github.com/emscripten-core/emsdk.git "$WGPU_EMSDK"
webgpu_stage emsdk-install 3600 10 "$WGPU_EMSDK" ./emsdk install 6.0.10
webgpu_stage emsdk-activate 300 10 "$WGPU_EMSDK" ./emsdk activate 6.0.10
source "$WGPU_EMSDK/emsdk_env.sh"
emcc --version
node --version
```

Source `emsdk_env.sh` in each new pilot shell. A Finder-launched editor does not
automatically inherit that environment. Record the SDK identity; do not replace
the initial pin with `latest` to work around an unexplained failure.

### Engine setup and SDK validation

```sh
webgpu_stage engine-dependencies 7200 10 "$WGPU_ENGINE" /bin/bash ./Setup.sh
webgpu_stage html5-prerequisites 600 10 "$WGPU_ENGINE" \
  /bin/bash Engine/Platforms/HTML5/HTML5Setup.sh
webgpu_stage html5-sdk-validation 1800 10 "$WGPU_ENGINE" \
  /bin/bash Engine/Build/BatchFiles/RunUBT.sh \
  -Mode=ValidatePlatforms -Platforms=HTML5
```

`HTML5Setup.sh` checks prerequisites; it does not install the SDK. Require an
HTML5 VALID result before treating platform preparation as complete.

### Native and Wasm dependencies

```sh
webgpu_stage dawn 7200 10 "$WGPU_ENGINE" \
  python3 Engine/Source/ThirdParty/Dawn/BuildForUE/BuildDawn.py --jobs 3 --test
webgpu_stage tint 7200 10 "$WGPU_ENGINE" \
  python3 Engine/Source/ThirdParty/Dawn/BuildForUE/BuildTint.py --jobs 3
webgpu_stage wasm-libraries 7200 10 "$WGPU_ENGINE" \
  /bin/bash Engine/Platforms/HTML5/Build/BuildThirdParty.sh --jobs 3
```

Run the stages sequentially. Do not clear their caches or use `--clean` for an
ordinary retry. A failure needs its log, current state and guard receipts read
before another attempt.

The Mac Dawn release's Tint binary was documented as lacking the needed SPIR-V
reader. Building Tint through the pinned helper matters. Preserve the fork's
declared Dawn source commit, rather than substituting the release tag's nearby
commit or an unrelated library/header installation.

`BuildThirdParty.sh` defaults to detected host CPU count when `--jobs` is omitted.
Its CPU-heavy compilation must retain the explicit cap above.

## 12 Compile the engine and browser runtime

First inspect the fork's [troubleshooting guide][engine-troubleshooting] and
verify compiler and shader-worker limits for this private checkout. These
commands cap UBT compilation; that alone does not cap every shader/cooker task.
Apply any needed supported shader-worker configuration only to this independent
engine and retain its diff in private evidence.

The existing Atelier `setup --headless` repair explicitly checks for installed
UE 5.8.2 CL 56702186. It is not a validated repair for this source fork's 5.8.3.
Do not disable that check, force the repair or let it edit the shared engine.
If a headless/TCC or Xcode project-generation issue arises, investigate it as a
source-fork compatibility issue with retained evidence.

```sh
webgpu_stage project-files 1800 10 "$WGPU_ENGINE" /bin/bash ./GenerateProjectFiles.sh
webgpu_stage editor 21600 24 "$WGPU_ENGINE" \
  /bin/bash Engine/Build/BatchFiles/RunUBT.sh \
  UnrealEditor Mac Development -NoUBA -MaxParallelActions=3
webgpu_stage host-tools 7200 24 "$WGPU_ENGINE" \
  /bin/bash Engine/Build/BatchFiles/RunUBT.sh \
  '-Target=ShaderCompileWorker Mac Development' \
  '-Target=UnrealPak Mac Development' -NoUBA -MaxParallelActions=3
webgpu_stage browser-runtime 21600 24 "$WGPU_ENGINE" \
  /bin/bash Engine/Build/BatchFiles/RunUBT.sh \
  UnrealGame HTML5 Development -NoUBA -MaxParallelActions=3
```

The 24 GiB examples select a supported larger compile ceiling and full matching
reservation. They are a bounded initial choice for the unmeasured clean engine
build, not a claim that it needs or will stay below that amount. Retain observed
peaks and use them to plan subsequent runs through normal admission.

Under Xcode 27, upstream documents an ApplePostBuildSync failure whose exact
logged post-build command may succeed separately. Only after inspecting and
successfully completing that exact step should `UE_BUILD_FROM_XCODE=1` be used
for the documented receipt-finalization retry. Do not set it globally at the
start or use it to conceal an incomplete app. Keep any such retry guarded.

An editor app, host tools, browser executable and matching build receipts must
exist before cooking. A shared `UnrealGame` binary is appropriate for the
content-only sample; Yorimichi's C++ modules/plugins require its own game target.

## 13 Package and verify the stock sample

### Disposable sample

The upstream template helper replaces an existing destination. Choose a fresh
path and refuse to run it against any working game project. The generated
sample belongs under ignored build output, not beside game source assets.

```sh
test ! -e "$WGPU_SAMPLE"
```

Stop if that check fails and choose another empty destination. Do not continue
to the helper after a failed check.

```sh
webgpu_stage sample-template 600 10 "$WGPU_ENGINE" \
  python3 Engine/Platforms/HTML5/Build/Scripts/MakeTemplateProject.py \
  TP_ThirdPersonBP "$WGPU_SAMPLE"
```

The helper copies the template and requested content packs, applies template
naming rules and removes the GameplayStateTree plugin that is absent from the
shared `UnrealGame` target. Keep the sample content-only for this baseline.

Prepare Playwright in the separate test-tools directory; version 1.58.2 is the
Atelier web package's existing pin and a reasonable initial test-tools choice.
Record the actual version and any compatibility adjustment. Use installed Chrome
with a real GPU, rather than assuming a bundled headless browser has WebGPU.

```sh
mkdir -p "$WGPU_TOOLS"
npm install --prefix "$WGPU_TOOLS" --save-exact playwright@1.58.2
export NODE_PATH="$WGPU_TOOLS/node_modules"
export WGPU_NODE="$(command -v node)"
```

### Cook and archive

These are initial command examples based on the pinned UAT path, not commands
executed during this investigation. Inspect the actual output directory and
receipt names on the receiving machine.

```sh
webgpu_stage sample-package 14400 24 "$WGPU_ENGINE" \
  /bin/bash Engine/Build/BatchFiles/RunUAT.sh BuildCookRun \
  "-project=$WGPU_SAMPLE/ThirdPersonWeb.uproject" \
  -platform=HTML5 -clientconfig=Development \
  -cook -stage -pak -archive \
  "-archivedirectory=$WGPU_OUTPUT/sample-package" \
  -unattended -utf8output '-ubtargs=-MaxParallelActions=3'
```

Verify the archived root containing `HTML5Content.txt`, the generated HTML/JS/Wasm,
cooked content and the matching `html5-gateway` host executable. Set
`WGPU_STAGE` to that actual root; the archive may contain a platform subdirectory.
Do not point the smoke test at a parent folder merely because it exists.

Packaging builds the native gateway host using Cargo and its pinned lockfile.
Keep `CARGO_BUILD_JOBS=3` from the preparation block in the pilot environment
before invoking packaging. The enclosing compile guard still accounts for the
full owned tree.

### Browser smoke

```sh
export WGPU_STAGE=/absolute/path/to/archive-root-containing-HTML5Content.txt
webgpu_stage content-tests 600 10 "$WGPU_ENGINE" \
  "$WGPU_NODE" Engine/Platforms/HTML5/Build/Scripts/TestHTML5Content.js
webgpu_stage browser-preflight 600 10 "$WGPU_ENGINE" \
  "$WGPU_NODE" Engine/Platforms/HTML5/Build/Scripts/TestHTML5Preflight.js "$WGPU_CHROME"
webgpu_stage sample-browser-smoke 900 10 "$WGPU_ENGINE" \
  python3 Engine/Platforms/HTML5/Build/Scripts/RunBrowserSmoke.py \
  --stage "$WGPU_STAGE" --chrome "$WGPU_CHROME" --node "$WGPU_NODE" \
  --output "$WGPU_OUTPUT/sample-browser"
```

The wrapper locates a single generated page beneath the staged root, starts the
packaged host on an ephemeral loopback port and runs the browser check. Supply
its supported `--page` option if the package legitimately contains multiple
pages. Treat a missing/ambiguous page or host as a packaging failure.

A valid baseline requires more than Wasm instantiation or a WebGPU adapter:

- Required capabilities and cross-origin isolation pass in the actual browser.
- The template map enters play and Unreal presents real scene frames.
- The upstream smoke's frame requirement passes without detected Unreal
  assertions/ensures, shader/pipeline failures or WebGPU errors.
- A human or visual check inspects the saved scene image for correctness.
- Console logs, guard receipts, versions, executable identity and outputs are
  retained, and all owned test processes are cleaned up.

Then run the upstream input, audio, HTTP, storage, services and shipping checks
appropriate to the milestone, each within admission and a deadline. Read each
script's actual usage before invoking it. A successful scene smoke does not
certify every service or a production release.

### BuildGraph alternative

The fork also supplies `Build/HTML5CI.xml` and describes it in
[M10-CI.md][engine-ci]. Its graph sequences dependencies, compile, package and
browser smoke. It is a local/private-runner BuildGraph, not proof of a hosted CI
service already running for this fork.

At the audited commit, `Jobs` defaults to six and controls Dawn/Tint. The
`BuildThirdParty.sh` node omits `--jobs`, causing that script to use host CPU
count. Therefore `-set:Jobs=3` alone does not enforce the machine's worker cap.
Use the staged path above for the first run, or make and record a private graph
fix that passes the cap to every relevant dependency invocation before using
the whole graph. Apply UBT and shader-worker limits separately.

Upstream reports a successful warm-cache graph and browser smoke on the author's
Mac. That is not a clean-build estimate or a local result for this handoff.

## 14 Yorimichi adaptation after the sample passes

Use a separate implementation branch/worktree and the normal code-contract and
review workflow. Recheck the current source: other agents may have changed the
game since the initial audit. The following are porting obligations, not fixes
already applied by this document.

### Skating floating point behavior

`platform/engine/Plugins/Activities/Skate/Source/AtelierSkate/Private/Simulation/SimulationMath.cpp`
implements `FlushDenormalsToZero` for ARM64 and x86_64. Other architectures return
false. `SkateRuntimeDetail.h` uses that result in
`FScopedSimulationFloatEnvironment`; the simulation worker fails if setup is
not ready. A Wasm build can therefore compile code yet refuse to start skating.

The mathematical implementation also deliberately uses `std::fma`, precise
floating-point semantics and explicitly controlled operation order. WebAssembly
does not expose the same host floating-point control registers. Preserve the
intended numeric behavior through an explicit port and validation. Do not merely
return true, remove the readiness check, enable fast math or accept a visually
plausible ride as evidence of equivalence.

A useful early experiment is to compile the standalone math/gameplay probes to
Wasm, independently of the full Unreal game. Reuse the existing reference and
parity infrastructure under `Skate/Tests/`. Cover subnormal handling, rounding,
fused operations, signed zero, NaNs/infinities where the existing checks depend
on them, and representative sustained gameplay. Document deliberate numeric
differences and their effect on replay/network behavior if exact equivalence
cannot be preserved. Keep that investigation separate from GPU WGSL transforms.

### Worker scheduling and collision data

The skate runtime starts an `FRunnableThread` simulation worker, uses futures
and background collision gathering, and requests a 32 MiB stack for one worker.
The fork has pthread support, but that is not proof every wait, queue, teardown
or stack allocation works for our runtime.

Validate worker startup, resource futures, collision installation, shutdown and
repeated activate/stow cycles. Budget the actual stack/data working set. Browser
main-thread blocking and worker proxying can deadlock if a synchronous wait
depends on work that cannot run; use the fork's worker model as intended.

### Controller sampling and skating feel

`SkatePadReader.cpp` uses macOS GameController APIs for high-frequency polling.
On other platforms `Acquire` returns no reader. `SkateRuntime.cpp` already has a
frame-input fallback in `ReadFineSticks`, so basic browser input need not depend
on immediately recreating the Mac polling path.

Use the browser Gamepad API and the fork's input implementation first. Measure
flick recognition, stick timestamps, dead zones, frame hitches, background-tab
behavior and reconnects. A high simulation tick rate does not imply equally
fresh gamepad samples. An improved timestamped input bridge is a possible later
adaptation if measurements show the fallback changes the intended feel.

### Rendering and painterly materials

`games/yorimichi/unreal/Config/DefaultEngine.ini` selects desktop forward shading
for normal play and enables custom depth/stencil. Existing LOD/tree optimization
helps, but mobile forward rendering has a different shader feature set.

`unreal/Scripts/shared_materials.py` builds the painterly post-process material.
Its custom HLSL samples scene color, scene depth, custom depth and stencil, and
the shared `painterly_kernel.py` generates additional scene reads. Some calls
use the three-argument desktop `SceneTextureLookup` overload. The inspected
engine material template supplies a parameter-aware overload that routes to
the mobile lookup, which is a candidate adaptation to test. This is not yet a
verified cook fix for our material.

Check the complete mobile post-process path, supported buffer inputs, exposure,
depth units, UV helpers, custom stencil, player exclusion and the chosen blend
location. Also check foliage WPO, camera see-through, board dissolve, water,
clouds, translucency, skeletal deformation and procedural geometry. Start with
a small representative material set and compare actual images.

Do not silently remove the painterly look to claim the game works. If a feature
needs an alternative implementation, make that tradeoff explicit. Keep browser
settings separate from saved desktop renderer/tree preferences. Do not enable
unsupported Lumen/Nanite permutations or offer a nonfunctional browser setting.

### Plugin and native service boundaries

`Yorimichi.Build.cs` directly lists `AtelierLive` and `AtelierStream` dependencies.
The project enables PixelStreaming2 and runtime dev tooling.

- `AtelierStream.Build.cs` directly depends on PixelStreaming2 modules. The
  browser-local executable does not need to encode and send its own video.
- LiveBridge depends on HTTPServer and native/editor integration. A web page
  cannot open the existing native loopback listener or execute desktop processes.
- Merely disabling a plugin in the `.uproject` is insufficient if C++ still
  includes its headers or calls its symbols. Provide appropriate compile/module
  boundaries and preserve desktop behavior.
- Browser QA should use a deliberate browser-test interface. Do not expose the
  native live bridge publicly or ship an unrestricted remote-code facility.

The Skate module also depends on PhysicsControl and Chaos. PhysicsControl's
installed plugin manifest did not show a platform allowlist preventing a port,
but its Wasm build/runtime behavior remains untested. Check all actually used
modules rather than assuming any pure-C++ plugin automatically works.

### Generated data and project staging

The project points to shared plugins through `AdditionalPluginDirectories`
outside the `.uproject` directory. Its build-identity logic also walks
repository-relative source/config/plugin roots. A stripped standalone project
copy can break those assumptions.

For a local source-fork build, preserve an independent Atelier layout or
deliberately implement a self-contained staging step. Do not upload a bare game
folder missing its shared plugins. Preserve source identity across staging.

`AtelierDataPath` reads loose `Content/Data` files. The normal package stages
these as NonUFS, including world layouts, height data, maps and activity payloads.
The audited HTML5 manifest path supports staged loose files, reducing the need
for a wholly separate data reader. Still verify paths, complete manifests and
actual reads in a browser package. A scene that boots without its runtime data
may simply be empty.

Rebuild/import through the normal game dependency graph when the new engine or
inputs require it. Keep generated output under the game's build directory or
ignored Content tree. Committed GLB source inputs remain the portable asset base.

## 15 World residency and browser content budgets

`JapanWorld::Load` reads the world description, merges region instance data,
loads every mesh group it encounters and creates components retaining those
meshes. Other region/activity loaders also perform synchronous object loads.
Rendering cull distances and HISM instancing reduce rendering work but do not
by themselves release these object references.

This creates two separate problems:

1. **Delivery residency:** which asset bytes are cached/downloaded by the
   platform backend. The fork's HTTP ranges address part of this problem.
2. **Game residency:** which meshes, collision structures, textures, animations
   and actors the world creates and keeps alive. Yorimichi needs measurement
   and likely partitioning here for a full-island browser experience.

The small pilot should include one environment chunk, Cairo, required skating
payloads/collision, the painterly material, a limited sound set and essential UI.
Prevent other regions from loading through an explicit pilot configuration or
fixture. Do not rely only on hiding far-away actors.

For island work, investigate region ownership, dependency manifests, async
load/prefetch, bounded collision/animation residency and release of references
on departure. At riding/gliding/vehicle speeds, load distance needs to cover
network and decode latency. Map teleportation and multiplayer travel need
explicit readiness behavior; preserve the current travel/collision contracts.

Set budgets from measured working sets and representative devices. Track cold
start and warm start separately, and keep download cache bytes distinct from
decompressed runtime and GPU memory. Choose desktop-browser scope first; mobile
devices are a separate compatibility/performance milestone.

## 16 Multiplayer after single player

The fork's browser socket subsystem presents datagram-like sockets to Unreal
and relays them through a native gateway. The intended shape is:

```text
Browser Unreal client
  -> WebTransport datagrams or secure WebSocket
  -> native HTML5 gateway
  -> ordinary UDP
  -> native Unreal dedicated server
```

The fork implements the bridge beneath ordinary IpNetDriver, so preserving UE
replication/RPCs may not require writing a whole new game NetDriver. The game
still needs integration with gateway setup and session rules.

Yorimichi's `JapanIpNetDriver` and `JapanTailscale.cpp` implement private native
hosting, including verification via the Tailscale executable and exact private
address binding. Those desktop host operations cannot run inside an ordinary
browser. Keep native server isolation and make browser join/server selection
explicit. Do not turn private hosting into a public wildcard listener to make
the test pass.

Important inspected constraints include:

- Browser listen servers and LAN discovery are not implemented by the gateway.
- The virtual browser peer resolves through the gateway configuration rather
  than an arbitrary UDP destination chosen by the web page.
- The inspected socket bridge rejects payloads larger than 1024 bytes. Audit
  effective UE packet sizing and our near-peer skeletal/pose streams before
  testing; do not assume a desktop packet limit fits.
- WebSocket fallback has different loss/ordering behavior from datagrams.
- The gateway contains admission/ticket and route/origin controls. A disposable
  local test issuer is not a production account/session service.
- Yorimichi checks code/content manifests. Staging changes, platform-specific
  builds and browser/native cross-play must preserve or deliberately version
  compatibility semantics. Do not disable checks to get a join.

Read [M11 networking][engine-networking], the gateway README and its
AUTHENTICATION.md at the pinned engine revision. Use the upstream multiplayer
fixture before the game's custom transport/session logic. Test replication,
RPCs, packet limits, latency/loss, explicit rejoin, tab suspension and owned
process cleanup. Network/server CPU and hosting costs remain even when the
rendering GPU belongs to the player.

The manual Third Person multiplayer launcher has no timed shutdown in its
normal interactive mode. Use a deliberate outer guard deadline and stop owned
sessions promptly. Its finite profiling mode is input-free and does not certify
active gameplay. Do not launch a multi-client test just because a script exists.

## 17 Milestones and completion criteria

| Milestone | Completion criteria |
| --- | --- |
| A Source and machine readiness | Account access works; source/tool/dependency revisions recorded; independent paths and working guards/listener verified |
| B Stock browser baseline | Pinned engine and sample build; real template frames; clean runtime/GPU checks; inspected screenshot; cleanup evidence |
| C Wasm skating core | Required math/runtime probes pass or justified numeric differences are resolved; worker startup/teardown and resource loading work |
| D Small Yorimichi scene | Cairo moves/skates in representative geometry with correct collision, controller behavior, materials, audio and essential UI |
| E Representative residency | Cold/warm start, transfer size, frame-time distribution and memory working set measured; regions actually load/unload as designed |
| F Multiplayer | Gateway/native server and game session/compatibility behavior validated without weakening existing private-host rules |
| G Distribution | Shipping build, hosted headers/ranges/cache behavior, save persistence, failure reporting, restart and supported device matrix verified |

Do not claim D from a blank map, A from a browser screenshot, B from NullRHI,
or G from a Development build. Keep scope changes explicit if the pilot uses a
reduced region/material/device set.

Recommended observations for each rendered milestone are:

- Source and dependency SHAs, host OS/architecture, browser/driver capabilities,
  SDK, Xcode, configuration, exact command and intentional local patches.
- Queue/admission timing, stage duration, exit status, guard process/tree peaks,
  terminal cleanup receipts and any refusal/retry history.
- Time to first playable frame; cold and warm bytes; cache behavior; loader
  errors; runtime frame counts and frame-time distribution.
- Wasm capacity and available allocation counters; JS retained cache; host
  process footprint; GPU allocations where available. Explain shared-process
  accounting rather than treating it as per-player RAM.
- Input, audio, saves, resize/fullscreen/pointer-lock, background/resume and
  browser close/reopen behavior.
- Screenshots/films inspected for missing draws, incorrect materials, depth,
  stencil, animation and collision outcomes.

## 18 Evidence storage and repository workflow

Keep generated reports under `build/yorimichi/webgpu/` in the implementation
checkout. Use fresh stage/report identifiers and retain stdout while the stage
runs. Read `stdout.log`, `memory-health.json`, `memory-health-tree.json` and
execution timing/cleanup receipts before retrying or diagnosing a stall.

Keep restricted engine source, source diffs and upstream private evidence in
authorized local/private storage. Do not assume the original author's local
report paths are accessible on the receiving machine.

For an Atelier PR, follow the repository's media policy: inspect every file and
push only appropriate game/render media through `atelier pr-media`. Browser,
terminal, desktop and board screenshots can expose private data and must not be
published through the public media refs. Private-source audit captures do not
belong in public evidence.

Production asset preparation/optimization eventually belongs in the normal
incremental build/package graph. A manual prototype flag or silent unoptimized
fallback is not a finished production target. Build keys must cover source,
engine/toolchain, settings and all consumed product identities; required missing
or stale outputs must fail. Preserve the platform/game boundary.

For later code changes, run focused local tests for changed behavior, lint and
contract checks. Hosted CI runs the full Python suite; do not duplicate a green
full suite locally without a recorded integration reason. Before merging code,
require green `Studio Python / macOS` on the exact final PR head, resolve contract
findings, request the required `r? cc` paid advisory review once the code PR is
ready, and obtain independent peer approval as the current rules require.
Documentation-only changes need no local Python test run and are exempt from
the paid-review request rule.

## 19 Failure triage

| Symptom | First investigation |
| --- | --- |
| GitHub 404 | Correct identity, accepted Epic membership, CLI/Git authorization and access to the specific fork |
| HTML5 platform unavailable | Engine dependencies, SDK environment/version, target validation and actual fork-built host tools |
| Headless setup refuses engine | The existing repair is version-bound; do not force it onto 5.8.3 |
| Xcode app finalization fails | Exact post-build log and the fork's documented workaround; do not certify missing app products |
| Tint cannot read SPIR-V | Correct source-built Tint with SPIR-V reader and matching pinned dependency set |
| Wasm initializes but no scene appears | Full engine startup log, staged command line/map/content, shader/pipeline errors and actual frame presentation |
| Asset reads fail or download everything | Manifest roots, HTTP 206/range support, cache limits, loader logs and the game's actual eager loads |
| Skating fails immediately | Floating-point readiness path, worker startup and required motion/runtime payloads |
| Painterly shader fails mobile cook | Desktop-only helper overloads, mobile post-process inputs and shader errors; preserve visual requirements |
| Browser cannot join | Gateway config/admission, native endpoint, payload limits and game compatibility/session logic |
| Host memory guard stops job | Owned process/tree receipts and actual budget; select a supported fully reserved envelope rather than weakening guards |
| Browser memory grows | Separate live allocations from Wasm capacity, JS cache, GPU/shared-process state and retained world objects |
| No stdout progress | Inspect current outputs and guard/supervisor telemetry, diagnose the stall, then correct or safely end only the owned job |

Do not blindly retry paid vendor calls or repeated failed cooks. Preserve inputs,
first failure logs and the reason for each retry. An unknown state remains
unknown until reconciled; an exit code without required products is insufficient.

## 20 If the source fork is unsuitable

Possible reasons include unacceptable rendering differences, unsupported game
plugins, missing device/browser coverage, memory limits, unstable dependency
builds or maintenance costs. Establish which requirement fails before choosing
another architecture.

A fully maintained independent port would still need:

1. An Unreal build/cook/packaging platform and rebuilt Wasm dependencies.
2. A WebGPU RHI with resource/pipeline/binding and render-pass semantics.
3. A shader compiler paired with that RHI's reflection and serialized metadata.
4. Browser lifecycle, threading, input, audio, HTTP, filesystem and saves.
5. Content delivery and game-level residency management.
6. Multiplayer gateway/session integration where required.
7. Atelier recipes, budget enforcement, browser QA and release maintenance.

Emscripten, Dawn/Emdawnwebgpu, DXC, Tint and browser APIs provide building blocks.
They do not supply all Unreal adapters or game compatibility. A complete engine
port should be treated as a substantial specialist project; this investigation
did not establish a reliable calendar estimate. An early successful shader cook
and rendered scene would be necessary evidence before expanding that scope.

Existing Atelier Pixel Streaming remains an alternative for browser access with
host rendering. A separate web-native game runtime could reuse some authored
assets, but would also require porting gameplay/animation/collision and preserving
the intended experience. Neither alternative is an automatic substitute for the
same Unreal game running locally in a browser.

## 21 Open questions for the receiving agent

- Which exact host, GPU, OS and browser are available, and does preflight pass?
- Does the pinned engine build from a fresh checkout with the recorded pins and
  machine's worker/memory constraints?
- Are any local engine patches necessary for Xcode, project generation, TCC or
  worker limits, and how will they be versioned?
- Does the stock scene render correctly, and what is its measured working set?
- Which numeric behavior can the skating core preserve under Wasm, at what cost?
- Which material operations need mobile-path changes, and what is the visual
  acceptance baseline?
- Which game regions/assets dominate startup and retained memory?
- Can code/content compatibility remain intact across native and browser cooks?
- What device/browser set is actually required for the first useful release?
- Is the goal initially single player, private friends multiplayer or broader
  distribution, and what hosting/session services does that choice require?
- If SimplyStream is evaluated too, what are its current export, self-hosting,
  bandwidth/storage and billing terms?

## 22 Suggested resume prompt

> Continue the Yorimichi WebGPU investigation from this handoff. First read the
> receiving checkout's AGENTS.md, machine-local render board, applicable contracts
> and capacity workflow, and verify a persistent board listener for this session.
> Verify GitHub access to EpicGames/UnrealEngine and PooyaEimandar/UnrealEngine.
> Start with branch 5.8-webgpu pinned to
> 3c5c6b098ec411254cb662437676de5548d929be, a separate source-engine checkout and
> an independent current-main Atelier worktree. Preserve the installed engine,
> canonical build artifacts and unrelated work. Recheck toolchain/API assumptions,
> then run the guarded staged stock Third Person baseline with explicit worker
> caps, full actual memory reservations, deadlines and retained evidence. Do not
> force the version-specific headless repair, copy private engine source into the
> public repository, or count upstream reports as locally verified. The owner's
> standing authorization covers supported larger memory sessions when the broker
> admits them; do not ask for another per-session memory grant. Keep the session
> responsive and report progress. Once the baseline passes, address the Wasm
> skating numeric blocker, mobile material compatibility and native plugin
> boundaries in a small Yorimichi scene before the full island or multiplayer.

## 23 Source index

Public references:

- [SimplyStream home][simply-home], [pricing][simply-pricing],
  [build guide][simply-build], [FAQ and billing][simply-faq],
  [Strata public agent guide][strata-guide] and
  [machine-readable public surface][strata-surface].
- [UT4 repository][ut4-repo], [recipe][ut4-recipe],
  [loader][ut4-loader] and [memory proposal][ut4-memory].
- [Independent fork overview at the audited documentation revision][fork-overview].
- [Epic GitHub access][epic-access], [GitHub OAuth management][github-oauth],
  [Emscripten memory settings][emscripten-memory],
  [pthreads and main-thread constraints][emscripten-threads] and
  [Tint's SPIR-V to WGSL implementation][tint-source].

Restricted engine references require the source access established above:

- [Pinned engine tree][engine-fork].
- [WebGPU RHI][engine-rhi], [shader compiler][engine-shader],
  [runtime shader metadata][engine-shader-metadata].
- [HTML5 toolchain][engine-toolchain], [runtime model][engine-runtime-design],
  [rendering design][engine-rendering-design], [engine touch points][engine-touchpoints].
- [HTTP content loader][engine-http-content], [networking][engine-networking],
  [gateway source][engine-gateway], [Third Person fixture][engine-thirdperson].
- [CI graph][engine-ci-graph], [CI instructions and upstream verification][engine-ci],
  [troubleshooting][engine-troubleshooting], [commercial-module scope][engine-commercial].

Atelier references:

- [Repository working rules](../../../AGENTS.md), [architecture](../../../ARCHITECTURE.md),
  [capacity admission](../../../docs/BUILD_CAPACITY.md),
  [build checkpoint workflow][atelier-checkpoints],
  [board guide](../../../docs/AGENT_BOARD.md),
  [contracts and review](../../../docs/CODE_CONTRACTS.md).
- [Game packaging](PACKAGING.md), [desktop performance](DESKTOP_PERFORMANCE.md),
  [build recipe](../build.py), [game manifest](../game.toml).

[simply-home]: https://simplystream.com/
[atelier-checkpoints]: https://github.com/fontanierh/atelier/blob/7a73248b/docs/BUILD_CHECKPOINTS.md
[simply-pricing]: https://simplystream.com/pricing
[simply-build]: https://simplystream.com/docs/build-guides
[simply-faq]: https://simplystream.com/docs/troubleshooting
[strata-guide]: https://api.stratavcs.com/v1/agent/guide
[strata-surface]: https://api.stratavcs.com/v1/agent/surface
[ut4-repo]: https://github.com/itpick/ut4-webgpu/tree/33162d0cc8c6eb664f5be432a23f142cb27d8fb9
[ut4-recipe]: https://github.com/itpick/ut4-webgpu/blob/33162d0cc8c6eb664f5be432a23f142cb27d8fb9/RECIPE.md
[ut4-loader]: https://github.com/itpick/ut4-webgpu/blob/33162d0cc8c6eb664f5be432a23f142cb27d8fb9/host/loader-shim.html
[ut4-memory]: https://github.com/itpick/ut4-webgpu/issues/1
[fork-overview]: https://github.com/PooyaEimandar/UnrealEngine-WebGPU/blob/8ba0a9a8f6297ba342e1d91a13117979653f94f0/README.md
[epic-access]: https://www.unrealengine.com/ue-on-github
[github-oauth]: https://docs.github.com/en/apps/oauth-apps/using-oauth-apps/reviewing-your-authorized-oauth-apps
[emscripten-memory]: https://emscripten.org/docs/tools_reference/settings_reference.html#memory64
[emscripten-threads]: https://emscripten.org/docs/porting/pthreads.html
[tint-source]: https://dawn.googlesource.com/dawn/+/59413b087ab30440e0ba43d7664a8959e4ef1dea/src/tint/api/tint.cc
[engine-fork]: https://github.com/PooyaEimandar/UnrealEngine/tree/3c5c6b098ec411254cb662437676de5548d929be
[engine-rhi]: https://github.com/PooyaEimandar/UnrealEngine/tree/3c5c6b098ec411254cb662437676de5548d929be/Engine/Source/Runtime/WebGPURHI
[engine-shader]: https://github.com/PooyaEimandar/UnrealEngine/blob/3c5c6b098ec411254cb662437676de5548d929be/Engine/Source/Developer/WebGPUShaderFormat/Private/WebGPUShaderCompiler.cpp
[engine-shader-metadata]: https://github.com/PooyaEimandar/UnrealEngine/blob/3c5c6b098ec411254cb662437676de5548d929be/Engine/Source/Runtime/WebGPURHI/Public/WebGPUShaderResources.h
[engine-toolchain]: https://github.com/PooyaEimandar/UnrealEngine/blob/3c5c6b098ec411254cb662437676de5548d929be/Engine/Platforms/HTML5/Source/Programs/UnrealBuildTool/HTML5ToolChain.cs
[engine-runtime-design]: https://github.com/PooyaEimandar/UnrealEngine/blob/3c5c6b098ec411254cb662437676de5548d929be/Engine/Platforms/HTML5/docs/ADR-002-runtime-model.md
[engine-rendering-design]: https://github.com/PooyaEimandar/UnrealEngine/blob/3c5c6b098ec411254cb662437676de5548d929be/Engine/Platforms/HTML5/docs/ADR-003-rendering-stack.md
[engine-touchpoints]: https://github.com/PooyaEimandar/UnrealEngine/blob/3c5c6b098ec411254cb662437676de5548d929be/Engine/Platforms/HTML5/docs/ENGINE_TOUCHPOINTS.md
[engine-http-content]: https://github.com/PooyaEimandar/UnrealEngine/blob/3c5c6b098ec411254cb662437676de5548d929be/Engine/Platforms/HTML5/Source/Runtime/Core/Private/HTML5/HTML5HttpContent.cpp
[engine-networking]: https://github.com/PooyaEimandar/UnrealEngine/blob/3c5c6b098ec411254cb662437676de5548d929be/Engine/Platforms/HTML5/docs/M11-NETWORKING.md
[engine-gateway]: https://github.com/PooyaEimandar/UnrealEngine/tree/3c5c6b098ec411254cb662437676de5548d929be/Engine/Platforms/HTML5/Programs/HTML5Gateway
[engine-thirdperson]: https://github.com/PooyaEimandar/UnrealEngine/blob/3c5c6b098ec411254cb662437676de5548d929be/Engine/Platforms/HTML5/Tests/ThirdPerson/README.md
[engine-ci-graph]: https://github.com/PooyaEimandar/UnrealEngine/blob/3c5c6b098ec411254cb662437676de5548d929be/Engine/Platforms/HTML5/Build/HTML5CI.xml
[engine-ci]: https://github.com/PooyaEimandar/UnrealEngine/blob/3c5c6b098ec411254cb662437676de5548d929be/Engine/Platforms/HTML5/docs/M10-CI.md
[engine-troubleshooting]: https://github.com/PooyaEimandar/UnrealEngine/blob/3c5c6b098ec411254cb662437676de5548d929be/Engine/Platforms/HTML5/docs/TROUBLESHOOTING.md
[engine-commercial]: https://github.com/PooyaEimandar/UnrealEngine/blob/3c5c6b098ec411254cb662437676de5548d929be/Engine/Platforms/HTML5/docs/COMMERCIAL-PLUGINS.md
