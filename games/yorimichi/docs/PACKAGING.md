# Packaging the macOS game

`atelier build yorimichi unreal.package` produces a packaged Yorimichi `.app` (Mac, Development) for another Mac.
It plans two independently stamped steps: `unreal.cook` builds and certifies the app, then `unreal.package` assembles the
download. The cook needs every Unreal import and the staged runtime data in the same checkout. A C++ source, project,
plugin, Config or imported-content change invalidates the cook and its download. A launcher or archive-script edit
invalidates only download assembly, so it reuses the completed cook.

Both steps are explicit: a plain `atelier build yorimichi` or `atelier build yorimichi unreal` never plans either.
Do not add `--force`: it reruns every prerequisite, including every import. The first build after this split needs a
cook to establish `cook.json`; an older package is not silently certified as current.

```sh
nice -n 10 uv run atelier build yorimichi unreal.package
```

On a Mac without a logged-in GUI session, run `uv run atelier setup --headless` first. Without it, UAT's in-process
build configuration waits forever on the macOS Documents privacy check (README, "headless"). The step exports
`UE_HEADLESS_USER_DIR` for UAT and the build tool it starts.

## What it does

- **Cooked tree buffers:** `unreal.city_tree_cpu_access` retains CPU buffers on the three production city trees before
  `unreal.desktop` creates their optimized variants. The runtime verifies the original and variant geometry before
  swapping. This metadata layer changes three assets without clearing or reimporting the world; a later world
  import invalidates the layer automatically.

- **One guarded turn:** RunUAT `BuildCookRun` builds the game target, cooks all content (the game loads about 83 assets
  by path at run time), stages, paks, packages and archives. On a Mac, `-package` has Xcode finalize a self-contained
  `.app` (paks and `Content/Data` inside `Contents/UE`). Without it, the archive step copies the bare
  `Binaries/Mac` app, and the archive job refuses it.
- **Slots and workers:** the step is compile-kind, so it holds both render slots for the whole run. UAT calls
  UnrealBuildTool directly, past the capped `Build.sh`, so the step passes `-ubtargs=-MaxParallelActions=3`. Shader
  workers keep the engine's patched limits.
- **Descendant guards:** the heavy work runs in UAT's descendants. `guarded.run(watch=...)` reaches every descendant
  through pinned parents and records it by pid and start time. It reads names again on every poll, so a process that
  execs the cook is still caught. Each UnrealEditor(-Cmd), ShaderCompileWorker and `dotnet` process gets its own memory
  guard, started with its validated start time; the reports are at
  `build/yorimichi/logs/unreal.cook.guard/memory-health-<name>-<pid>.json`. If a guard exits while its process is
  still running, the run fails at once.
- **Orphans and shared services:** each poll walks from the root and from every recorded process still alive, so an
  intermediate that lost its parent still brings in the cook it starts. Shared engine services that a cook starts
  (`zenserver`, `UnrealTraceServer`), and anything under them, are recorded but never guarded or signalled.
- **Cleanup:** when the run ends, every other recorded descendant is stopped, deepest first. Each signal is sent only if
  the process still has its pinned identity at that moment; nothing else is signalled.
- **Deadline and progress:** the UAT turn has a 4-hour deadline. While UAT is quiet, a progress line prints every
  25 s.
- **Archive job:** once UAT releases its turn, `tools/package_archive.py` runs as a guarded job of its own. It takes
  its own slot turn, has its own deadline, and its `ditto` and `split` children are watched. Its zip, split and checksum
  phases are each bounded to 45 minutes and report progress every 25 s. It requires a certified app whose
  staged `Content/Data` contains `world.json`, `heightmap.bin` and `map/map.json`.
- **Cook identity and retries:** `package/cook.json` records the source revision, engine version, prerequisite
  fingerprint and file hashes. The app remains under `package/archive/`; assembly makes an independent copy, verifies
  it against that record, and signs only the copy. A failed ZIP or signing phase leaves the cook and previous download
  intact. The ZIP name and manifest retain the cook's source revision even if a later docs or launcher commit changes
  HEAD. A removed or changed cooked file invalidates the cook. All candidate files are finished before publication;
  the manifest is published last.
- **Audio signing:** the ad-hoc playtest archive preserves the signed app's sandbox and existing entitlements, adding
  one exact Mach lookup allowance for `com.apple.cmio.registerassistantservice.system-extensions`. On macOS 26,
  CoreAudio's first default-output-device query can wait on this denied lookup before the game starts. The archive
  verifies the resulting entitlements and full signature before zipping; it refuses to replace a Developer ID signature.
  This uses [Apple's documented Mach lookup exception](https://developer.apple.com/library/archive/documentation/Miscellaneous/Reference/EntitlementKeyReference/Chapters/AppSandboxTemporaryExceptionEntitlements.html).
- **Release files:** the download folder `Yorimichi/` holds the `.app`, `Play Yorimichi.command` and `README.txt`.
  It is zipped with `ditto` into `build/yorimichi/package/Yorimichi-macOS-<revision>.zip`, split into
  `.zip.part-aa`, `-ab`, … if it is larger than 1.9 GB, with `SHA256SUMS` and `manifest.json`. The step counts as up
  to date only while every listed zip or part exists at its recorded size.

A packaged game does not start the live bridge (the HTTP remote control and its overlays) unless it is launched with
`-live`. The game is not inside the repository those overlays come from.

## The launcher

Double-clicking `Yorimichi.app` starts the game without the desktop profile. `Play Yorimichi.command` is generated from
`tools/desktop_preview.py`, so it carries the same profile as `atelier play yorimichi --profile desktop-1440`,
which already selects shared settings:

- forward rendering
- the native 1440 viewport
- the optimized city tiles and trees, and the tuned lighting

It honours saved settings, except the renderer. Xcode signs the app with App Sandbox, so the launcher reads its bundle
identifier from `Yorimichi.app/Contents/Info.plist` and uses that container's writable directories:

- settings: `~/Library/Containers/<bundle-id>/Data/Library/Application Support/Yorimichi/settings.txt`
- log: `~/Library/Containers/<bundle-id>/Data/Library/Logs/Yorimichi/game.log`

Capture and benchmark output paths must also be inside that container. An absolute path elsewhere can fail to write
even when the app reports that its scenario completed. Check that fresh output files actually exist. Keep the signed
app's sandbox enabled; a launcher-only correction needs a new archive, not another compile or cook.

The package is cooked for forward shading only (the project's
`r.ForwardShading`), so the launcher always starts Forward. The packaged menu says so: its Lighting row reads
"Forward · Lumen is not in this build" and explains instead of switching, and a Lumen request from the phone is
refused before anything is saved. Packaged Lumen would need a deferred cook and a verified switch, and neither exists.
Editor builds keep both renderers.

## On the playtest Mac

1. Download every file of the release. If the zip was split, join the parts:

   ```sh
   cat Yorimichi-macOS-*.zip.part-* > Yorimichi-macOS.zip
   ```

2. Check the download against `SHA256SUMS`:

   ```sh
   shasum -a 256 -c SHA256SUMS
   ```

   For a split zip, compare the parts.

3. Unzip by double-clicking the zip, or with `ditto -x -k Yorimichi-macOS.zip .`.

4. Double-click `Yorimichi/Play Yorimichi.command`. The app is not notarised: if macOS refuses to open it, right-click
   the launcher, choose Open, then Open again. The launcher removes the download quarantine from the folder itself.
   If the game quits within seconds of its first launch, before any window, open the launcher again (see "A first
   launch can crash before the game starts").

## Before publishing a release

Verify the files that will be uploaded, rather than an app left in a previous staging directory:

```sh
nice -n 10 uv run python games/yorimichi/tools/verify_package.py \
  --package build/yorimichi/package --extract build/yorimichi/release-check/extracted \
  --report build/yorimichi/release-check/verification.json --expected-revision "$(git rev-parse HEAD)"
```

Choose new extraction and report paths for each run. The tool checks the manifest, SHA256SUMS and actual file hashes,
joins numbered parts when necessary, and extracts with `ditto` under the normal lock and memory guard. Read the render
ledger and announce that extraction job before running it. It then checks the launcher permissions, Apple silicon
executable, every bundled Mach-O dependency, app signature, sandbox audio allowance, symlinks and core staged data.
Use `--require-communitypark` when the release includes the optional park. The expected revision is the full revision
in the cook record; an older manifest without that record carries only its short revision.

This verifies the download, not gameplay. Run a separate, guarded standalone smoke test from the extracted launcher's
folder and quit it promptly. Check that captures and logs were written inside the app's writable sandbox container.
Upload the verified ZIP or all numbered parts, SHA256SUMS, manifest.json and the verification report together.

## A first launch can crash before the game starts

**Observed twice, each time on the first launch of a freshly signed or extracted app; the next launch of the same,
unchanged app started normally.** The launcher's process ends with SIGSEGV (exit -11) within seconds, before
`game.log` exists. macOS writes `Yorimichi-<date>.ips` under `~/Library/Logs/DiagnosticReports/`.

- 2026-10-06 12:05: the first launch of the re-signed `afc541e1` package, an earlier build that day (not a
  published release). A launch six seconds later started.
- 2026-10-07 03:06: the first launch of the extracted r4 package (`7250edaf`). The unchanged app's next launch
  started and its map check ran.

Both reports have the same main-thread stack and the same faulting address (`KERN_INVALID_ADDRESS at 0x3`):

```text
FGenericPlatformMisc::RaiseException
UE::LLMPrivate::FLLMTracker::PopTag
FLLMScope::DestructInTheOpen
FMallocBinned3::PushNewPoolToFront / FMallocBinned3::Malloc
FMallocPoisonProxy::Malloc
operator new
LaunchServices asString / _LSCopyApplicationInformation
-[NSApplication _sendFinishLaunchingNotification] (via _handleAEOpenEvent)
-[NSApplication run] / tchar_main / main
```

AppKit's launch event makes LaunchServices allocate on the main thread before the engine has started. The engine's
low-level memory tracker (LLM), compiled into Development and Test packages by default (`LLM_ENABLED_IN_CONFIG` and
`ALLOW_LOW_LEVEL_MEM_TRACKER_IN_TEST` in `Runtime/Core/Public/HAL/LowLevelMemTrackerDefines.h`), wraps that allocation
in its bootstrap scope and fails in `PopTag`. Nothing in the project configures LLM. The cause is read from the
stacks, not reproduced: treat it as an intermittent engine and LaunchServices race on a newly registered app.

When it happens, keep the `.ips` report and launch the same extracted app once more. Report it as a known first-launch
limitation if that launch starts. A crash on a second launch, or a different stack, is a new failure.

Two mitigations are **unvalidated**; neither is in use, and each needs a cook and repeated first launches of
freshly extracted copies before adoption:

- Build the game target with `LLM_ENABLED_IN_CONFIG=0`. This needs a unique build environment for the target, so the
  engine modules it uses compile with the game.
- Package the Shipping configuration, which leaves LLM out (Test keeps it). Shipping also drops logging and console
  commands, which the launcher's `-ExecCmds` tuning and the release checks' `game.log` rely on.

## The shared-PCH rebuild on every cook

**Proven: every UAT `-build -package` run recompiles all game and plugin objects, even with no C++ change.** The
installed UE 5.8 engine causes this loop on Mac:

1. The build writes the 12 `SharedPCH.*.rsp` response files under
   `Intermediate/Build/Mac/arm64/Yorimichi/Development/`, then compiles and links.
2. Its last action, `ApplePostBuildSync`, generates a stub Xcode project. `AppleToolChain.GenerateProjectFiles`
   sets `ProjectFileGenerator.bGenerateProjectFiles = true` (`Platform/Apple/AppleToolChain.cs:973` under
   `Engine/Source/Programs/UnrealBuildTool`). With that flag `UEBuildModuleCPP.AddModuleToCompileEnvironment` adds a
   `-I".../Inc/<Module>/UHT"` line for every dependency module (`Configuration/UEBuildModuleCPP.cs:519`).
3. The generator's native-target pass (`ProjectFiles/Xcode/XcodeProjectFileGenerator.cs:577` and `:583`) writes
   those response files into the build's own folder: on an installed engine the separate project-file folder is
   never used (`Configuration/UEBuildTarget.cs:1332` and `:1894`), and its null action-graph builder still writes
   files (`Actions/ActionGraphBuilder.cs:121-130`). Stage and Package run the same generator again.
4. The next build writes the files without the `/UHT` lines, finds all 12 changed, and rebuilds every shared PCH and
   everything that includes them.

Evidence (refresh at `dc144aa9`): the preserved pre-refresh response files and the rebuilt ones differ only by
removed `/UHT` lines (3 to 30 per file); the log shows 12 `Updating ... SharedPCH...rsp: contents have changed`
lines followed by all 494 actions. The editor target's response files, which get no post-build sync, did not change.
Measured cost: all 494 actions, 586 s and 593 s of build time on two consecutive same-source runs (three parallel
actions), before cooking starts.

Two mitigations are **unvalidated**; neither is in use, and each needs one measured run before adoption:

- Add `-NoSharedPCH` to the package build's `-ubtargs` (`Configuration/Rules/TargetRules.cs:2398`), so the build
  never reads the rewritten files. It costs one full rebuild, and later full builds are slower.
- Inside the same guarded package run, after BuildCookRun, restore each `SharedPCH*.rsp` from its `.rsp.old` when
  the only difference is the added `/UHT` lines.

`UE_BUILD_FROM_XCODE=1` is not a fix: Stage and Package still regenerate the project. A missing ISPC folder also
invalidates the makefile on every run, but that costs seconds and is not the cause. Preserve each run's
`UBA-Yorimichi-Mac-Development.txt` and changed `.rsp` files when investigating: UBT overwrites its logs. Do not
clear caches, remove `-build` or accept stale binaries to hide the cause.
