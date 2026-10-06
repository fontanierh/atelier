# Packaging the macOS game

`atelier build yorimichi unreal.package` builds a packaged Yorimichi `.app` (Mac, Development) for playtests on another
Mac. It runs after every Unreal import and the staged runtime data in the same checkout, so package a checkout whose
imports are current. Use `--force` to repackage after content changes: the step reruns by itself only when the C++
source, the project file, the engine plugins or `unreal/Config` change.

```sh
nice -n 10 uv run atelier build yorimichi unreal.package --force
```

## What it does

- **One guarded turn:** RunUAT `BuildCookRun` builds the game target, cooks all content, then stages, paks and
  archives. It cooks everything because the game loads about 83 assets by path at run time.
- **Slots and workers:** the run takes both render slots like a compile. UAT calls UnrealBuildTool directly, past the
  capped `Build.sh`, so the step passes `-MaxParallelActions=3` itself. Shader workers keep the engine's patched
  limits.
- **Memory guards:** the heavy work happens in UAT's descendants. Each cook editor, shader worker and `dotnet` process
  gets its own memory guard, pinned to its pid and start time, with a report at
  `build/yorimichi/logs/unreal.package.guard/memory-health-<name>-<pid>.json`.
- **Deadline and progress:** the whole package has a 4-hour deadline. A progress line prints every minute while UAT
  is quiet.
- **Cleanup:** when the run ends, recorded descendants that are still the same processes are stopped. Nothing else is
  signalled.
- **Release files:** the `.app` is zipped with `ditto` into `build/yorimichi/package/Yorimichi-macOS-<revision>.zip`,
  alongside `SHA256SUMS` and `manifest.json`. A zip over 1.9 GB is split into `.zip.part-aa`, `-ab`, … parts, each
  small enough for a GitHub release asset.

A packaged game does not start the live bridge (the HTTP remote control and its overlays) unless it is launched with
`-live`. The game is not inside the repository those overlays come from.

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

4. The app is not notarised, so remove the download quarantine before the first launch:

   ```sh
   xattr -dr com.apple.quarantine Yorimichi.app
   ```

   Then open it. Alternatively, right-click the app, choose Open, then choose Open again.
