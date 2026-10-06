# Packaging the macOS game

`atelier build yorimichi unreal.package` builds a packaged Yorimichi `.app` (Mac, Development) for playtests on another
Mac. The step needs every Unreal import and the staged runtime data in the same checkout, so in a checkout whose imports
are current only the package runs. It reruns by itself whenever any of them, the C++ source, the project file, the engine
plugins, `unreal/Config` or the packaging code (`tools/package_archive.py`, `tools/desktop_preview.py`) changed. It is only built when named exactly, never by a plain `atelier build yorimichi` or
`atelier build yorimichi unreal`. Do not add `--force`: that reruns everything in the plan, including every import.

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
  `build/yorimichi/logs/unreal.package.guard/memory-health-<name>-<pid>.json`. If a guard exits while its process is
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
  phases are each bounded to 45 minutes and report progress every 25 s. Before anything moves, it refuses an app whose
  staged `Content/Data` lacks `world.json`, `heightmap.bin` or `map/map.json`.
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
`tools/desktop_preview.py`, so it carries the same profile as `atelier play yorimichi --profile desktop-1440
--shared-settings`:

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

## Diagnosing a repeated compile

Preserve each run's `UBA-Yorimichi-Mac-Development.txt` and changed `.rsp` files before retrying: UBT overwrites its
logs. In one same-source retry, 12 SharedPCH response files changed and caused a 494-action rebuild. The subsequent
`ApplePostBuildSync` Xcode generation rewrote those files again with additional UHT include paths. A response file
newer than its `.gch` is a useful lead; recurrence needs comparison of preserved per-run files. Adding `-package`
also introduced `-skipdeploy` and a one-time makefile regeneration, which alone does not explain recompilation.
Do not clear caches, remove `-build` or accept stale binaries to hide the cause.
