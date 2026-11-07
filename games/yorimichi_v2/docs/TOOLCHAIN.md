# Toolchain

The exact engine, plugins and host tools V2 is pinned to. Recorded 6 November 2026 on the reference Mac
(DECISIONS D03). Do not upgrade any of these during the migration (plan §1.3). Content compatibility means **the
same engine changelist**; executable hashes may differ between hosts.

## Engine

| Item | Value | Source |
|---|---|---|
| Install path | `/Users/Shared/Epic Games/UE_5.8` (`UE_ROOT` overrides) | `platform/studio/atelier/engine.py:8,12-23` |
| Build | **5.8.2, Changelist 56702186**, CompatibleChangelist 55116800, `++UE5+Release-5.8`, promoted, not a licensee build | `Engine/Build/Build.version` |
| Editor binaries | `Engine/Binaries/Mac/UnrealEditor-Cmd`, `UnrealEditor.app/Contents/MacOS/UnrealEditor` | `engine.py:16-23` |
| Bundled .NET | `Engine/Binaries/ThirdParty/DotNet/10.0/mac-arm64` (no `dotnet` on PATH) | filesystem |
| Project association | `"EngineAssociation": "5.8"` | `Yorimichi.uproject:3` |

### Local engine patches (installed now)

These come from `atelier setup --headless` (`platform/studio/atelier/setup.py`; it refuses anything other than
5.8.2 CL 56702186, `setup.py:243-244`). They are documented in `docs/SETUP.md:19-47`. The receipt is
`the machine's `atelier setup --headless` receipt under `~/.cache/atelier/toolchain/``, and originals are kept in that folder's
`originals/Engine/`. All hashes below match the installed files. Verified on 6 November 2026 with `shasum -a 256`.

| Patched file | SHA-256 (installed = receipt) |
|---|---|
| `Engine/Source/Programs/Shared/EpicGames.Build/Unreal.cs` (Documents lookup → `UE_HEADLESS_USER_DIR`) | `f516a6a4…1558d` |
| `…/UnrealBuildTool/Configuration/Xml/XmlConfig.cs` (explicit XML config cache, personal path) | `d4a67bea…2584` |
| `…/UnrealBuildTool/ProjectFiles/Xcode/XcodeProjectFileGenerator.cs` (isolated GPF intermediates) | `da9532d3…a0` |
| `…/UnrealBuildTool/Configuration/UEBuildTarget.cs` (installed-engine intermediates) | `ad23afb3…394` |
| Rebuilt `EpicGames.Build.dll` (UBT and 2× UAT copies) | `ea04fbd1…fa732c2` |
| Rebuilt `UnrealBuildTool.dll` (UBT and 2× UAT copies) | `ea54cee1…cc2a` |
| `Engine/Build/BatchFiles/Mac/Build.sh` | Wrapper block `# BEGIN ATELIER HEADLESS BUILD`: `renice 10`, `UE_HEADLESS_USER_DIR`, `-XmlConfigCache=…/remote-xmlconfig.bin -MaxParallelActions=3` |
| `Engine/Config/BaseEngine.ini:2181-2189` | Shader workers capped: `NumUnusedShaderCompilingThreads=7` (was 3), `…DuringGame=7` (was 4), `PercentageUnusedShaderCompilingThreads=70` (was 50) |

`workers = 3`. There are no other engine-source patches recorded in the repo. Searched for `engine patch`,
`patched engine` and `UE_5.8`; `5.8.2` appears only in SETUP/setup.py/FOLIAGE_BUILDS. Content compatibility is
defined by **5.8.2 CL 56702186**. The patches touch build tools and shader-thread config only, not runtime or
serialization. Another host needs the same engine CL. On a Mac, it reproduces the patches by running
`atelier setup --headless`.

## Host (reference Mac)

| Tool | Version | Repo expectation |
|---|---|---|
| macOS | 26.2 (25C56), arm64 | README.md:51 "macOS on Apple silicon 15+" |
| CPU / RAM | Apple M1 Max, 10 cores, 32 GiB (34359738368 B) | — |
| Xcode | 27.0 (27A266a), `/Applications/Xcode.app/Contents/Developer`, macOS SDK 27.0 | full Xcode plus Metal toolchain (`setup.py:72-94`, SETUP.md:8-16) |
| Clang | Apple clang 21.0.0 (clang-2100.3.34.2), arm64-apple-darwin25.2.0 | — |
| Git / Git LFS | 2.54.0 (Apple Git-157) / git-lfs 3.8.0 | LFS required (Hakuba already uses it; `.githooks/pre-push`) |
| Blender | 5.2.1 at `/Applications/Blender.app/Contents/MacOS/Blender`, reached through the `/usr/local/bin/blender` exec wrapper (`BLENDER` unset) | `engine.py:9,26-29`; `platform/conventions/versions.toml` `blender = "5.2"` (5.2.1 LTS). Version read from `Info.plist`, not launched. V2 needs Blender only for preparation tools, never for a normal checkout. |
| Python | uv 0.10.0; project venv 3.12.12; system python3 3.14.3 | `pyproject.toml:6` `>=3.11`; CI uses 3.12 (`python.yml`) ; UE embeds 3.11 (`versions.toml`) |
| Node / npm | 25.6.1 / 11.9.0 | Contracts need Node ≥24.16 and npm ≥11.11 (`platform/studio/contracts/package.json`); **local npm 11.9 is below 11.11** |
| ffmpeg | 9.0.2 | `>=7` |
| Rust | cargo/rustc 1.93.0 (default); Hakuba pins 1.97.1 | Only for the board server and Hakuba |

## Project plugins and modules

Yorimichi's `Yorimichi.uproject:6-91` declares:

- **Modules:** `Yorimichi` (Runtime), `YorimichiAssets` (Runtime), `YorimichiImport` (UncookedOnly).
- **Targets:** Game, Editor, Server (`Source/*.Target.cs`).
- **Plugin directory:** `AdditionalPluginDirectories: ../../../platform/engine/Plugins`.

| Plugin | V2 | Why / dependants |
|---|---|---|
| HorseRacing (game) | **KEEP** (copy into `games/yorimichi_v2/unreal/Plugins`) | `Yorimichi.Build.cs:70` `AtelierHorseRacing` |
| EnhancedInput | KEEP | uproject module dependency |
| PythonScriptPlugin | KEEP (editor) | LiveBridge.uplugin depends; `AtelierLive.Build.cs:11` (editor only); targeted import scripts |
| EditorScriptingUtilities | KEEP (editor) | Import/authoring scripts |
| Interchange | KEEP | LiveBridge.uplugin depends (GLB props) |
| AtelierCore, AtelierAnimation, AtelierFX, LiveBridge (AtelierLive), Skate | KEEP | `Yorimichi.Build.cs:59`. Skate pulls engine `PhysicsControl`; AtelierFX pulls `ProceduralMeshComponent` |
| **ElectraPlayer** | **KEEP (not a drop)** | `JapanMusic.cpp:194-195`: the soundtrack plays MP3s through Electra ("AvfMedia lists no mp3 extension"). Drop it only if the music is converted. |
| AndroidFileServer | Keep **disabled** | It writes a token into Config (AGENTS.md:32-33) |
| **PixelStreaming2** | **DROP** (X01) | Only `AtelierStream.uplugin` depends on it (`AtelierStream.Build.cs:8-9`) |
| **AtelierStream** | **DROP** (X01) | `Yorimichi.Build.cs:59`; `WandererCharacter.cpp:21,267`; `YorimichiPhone.h/.cpp` (whole file); `JapanGameMode.cpp:19` (string key only); `Config/DefaultGame.ini:93` section |
| **Driving** (AtelierDriving) | **DROP** (X02) | `Yorimichi.Build.cs:59`; `WandererCharacter.h:29,132,283` + `.cpp:29,34,93` (`CreateDefaultSubobject<UDrivingComponent>("CarRide")`), `:355-361` (kart meshes/cockpit), `:1716-1724`; `JapanHUD.cpp:12,292,305,359`; `JapanKartGrip.h/.cpp`; `WandererAnimInstance.cpp:20,304`; `YorimichiLive.cpp:9,196-219`, `.h:54,58`; `/Game/Japan/Kart/*` |

Dependency check:

- No kept plugin or module depends on PixelStreaming2, AtelierStream or Driving. Checked all 8 `.uplugin` files and
  all `*.Build.cs` files.
- Only the `Yorimichi` game module itself references the dropped plugins, so dropping them is a code change in V2's
  copy.
- Removing the `CarRide` default subobject is a serialized-class change. Saved packages derived from
  `AWandererCharacter` must load without warnings; test this (plan §4, identities).
- Neither `Driving.uplugin` nor `AtelierStream.uplugin` sets `EnabledByDefault`, and both are discovered through
  `AdditionalPluginDirectories`. List them in `YorimichiV2.uproject` with `"Enabled": false`, as
  `Sandbox.uproject` does for unused platform plugins. Verify in the P1 editor log that they are not loaded.

Copy hazard when the code moves:

- `Yorimichi.Build.cs:16,20` hardcodes `games/yorimichi/unreal/{Source,Config,Plugins}` and its `*.uproject` for the
  network build ID. A verbatim copy into V2 would hash the **old** game's sources. Re-point it to
  `games/yorimichi_v2`.
- `DefaultGame.ini:30-31` also points at `games/yorimichi/live/{overlays,python}`.

## Windows host readiness (for the P0 route decision)

The Python harness is POSIX/macOS-only in places; many modules fail on import on native Windows (`fcntl`). By area:

| Area | macOS / POSIX assumption | Location |
|---|---|---|
| Engine paths | `Engine/Binaries/Mac/UnrealEditor-Cmd`, `UnrealEditor.app` | `platform/studio/atelier/engine.py:16-23` |
| Doctor/setup | Non-Darwin → "macOS on Apple silicon is the tested build platform"; Xcode/Metal checks; headless repair edits Mac `Build.sh` | `setup.py:72-94,159,252`; `engines/unreal.py:12-17` |
| Process launch | `taskpolicy -a` + `nice` on darwin (no-op elsewhere); `start_new_session`; POSIX signals `SIGTERM/SIGKILL/SIGHUP` | `harness/safety/process.py:15-30`; `guard.py:166,285-290`; `guarded.py:185-197`; `cancellation.py:25` |
| Memory guard | libproc via `/usr/lib/libproc.dylib`; Linux `/proc` fallback; **no Windows path** | `harness/safety/memory_guard.py:19-29,106-124,167` |
| Render lock / admission | Module-level `import fcntl`; `flock`; `vm_stat` memory | `harness/safety/render_lock.py:47,113-134,287-301` |
| Capacity broker/client | `AF_UNIX` socket, `fcntl.flock`, darwin socket-path limit; boot ID via `sysctl kern.bootsessionuuid` or `/proc` | `capacity_broker.py:9,124,161,192`; `capacity_client.py:92`; `capacity_protocol.py:246-254`; `capacity_cpu.py:28,126,192` (Darwin timebase) |
| Supervision | launchd LaunchAgents plists + `launchctl`; refuses non-darwin | `capacity_supervision.py:40-73`; `board_service.py:39-96` |
| Board/session | `import fcntl`; `AF_UNIX` receipts; `ps -o lstart=` | `board.py:8,172,232`; `board_remote.py:7`; `board_claude.py:22,71,94-99`; `safety/worker_binding.py:7`; `capacity_compat.py:12` |
| Crash reporters / process tree | libproc + sysctl (macOS-only module) | `harness/safety/mac_crash_reporters.py:101-161`; `process_tree.py:1` |
| Board server (Rust) | macOS diagnostics branch; `libc::statfs` | `platform/harness/web/server/src/db.rs:290-300`; `disk.rs:52-53` |
| APFS clone | `clonefile` (byte-copy fallback elsewhere) | `platform/studio/atelier/file_copy.py:11-20` |
| CI | macOS board job disabled; Linux-only test shards | `.github/workflows/python.yml` (board `if: false`) |

**Route options to record:**

1. A bounded Windows adapter for launch, memory guard, lock, broker and cleanup (Job Objects, named mutex or
   `msvcrt.locking`, a named-pipe broker, a Windows service). This touches roughly 10 modules.
2. Windows workers do code and review only; Unreal work runs in separate owned workspaces on a supported Mac.

Option 2 needs no harness changes. Either way, record the Windows box's own engine identity separately: same
5.8.2 CL 56702186 content compatibility; the Mac UBT patches do not apply there.
