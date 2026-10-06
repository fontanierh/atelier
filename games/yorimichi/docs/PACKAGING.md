# Packaging the macOS game

`atelier build yorimichi unreal.package` builds a packaged Yorimichi `.app` (Mac, Development) for playtests on another
Mac. The step needs every Unreal import and the staged runtime data in the same checkout, so in a checkout whose imports
are current only the package runs. It reruns by itself whenever any of them, the C++ source, the project file, the engine
plugins, `unreal/Config` or the packaging code (`tools/package_archive.py`, `tools/desktop_preview.py`) changed. It is only built when named exactly, never by a plain `atelier build yorimichi` or
`atelier build yorimichi unreal`. Do not add `--force`: that reruns everything in the plan, including every import.

```sh
nice -n 10 uv run atelier build yorimichi unreal.package
```

## What it does

- **One guarded turn:** RunUAT `BuildCookRun` builds the game target, cooks all content (the game loads about 83 assets
  by path at run time), stages, paks and archives.
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

It honours saved settings, except the renderer. Settings are in `~/Library/Application Support/Yorimichi/settings.txt`
and the log is `~/Library/Logs/Yorimichi/game.log`. The package is cooked for forward shading only (the project's
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
