# Toolchain

The engine compatibility pin and current V2 plugin configuration, with a historical host/tool snapshot
recorded on 6 November 2026 (DECISIONS D03). Host versions below are dated evidence, not a claim that every
installed utility was rechecked for each later package. Do not upgrade any of these during the migration (plan §1.3). Content compatibility means **the
same engine changelist**; executable hashes may differ between hosts.

## Engine

| Item | Value | Source |
|---|---|---|
| Install path | `/Users/Shared/Epic Games/UE_5.8` (`UE_ROOT` overrides) | `platform/studio/atelier/engine.py:8,12-23` |
| Build | **5.8.2, Changelist 56702186**, CompatibleChangelist 55116800, `++UE5+Release-5.8`, promoted, not a licensee build | `Engine/Build/Build.version` |
| Editor binaries | `Engine/Binaries/Mac/UnrealEditor-Cmd`, `UnrealEditor.app/Contents/MacOS/UnrealEditor` | `engine.py:16-23` |
| Bundled .NET | `Engine/Binaries/ThirdParty/DotNet/10.0/mac-arm64` (no `dotnet` on PATH) | filesystem |
| Project association | `"EngineAssociation": "5.8"` | `unreal/YorimichiV2.uproject` |

### Recorded local engine patches (6 November 2026)

These come from `atelier setup --headless` (`platform/studio/atelier/setup.py`; it refuses anything other than
5.8.2 CL 56702186, `setup.py:243-244`). They are documented in `docs/SETUP.md:19-47`. The machine's `atelier setup --headless` receipt is under `~/.cache/atelier/toolchain/`, and originals are kept in that folder's
`originals/Engine/`. The hashes below matched the installed files when verified on 6 November 2026 with `shasum -a 256`.

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

`workers = 3` is the recorded compiler cap. Use the current [setup guide](../../../docs/SETUP.md) and setup
receipt for supported repairs; do not alter engine/broker settings during another owner's job. Content compatibility is
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
| Git / Git LFS | 2.54.0 (Apple Git-157) / git-lfs 3.8.0 | LFS required for V2; `.githooks/pre-push` |
| Blender | 5.2.1 at `/Applications/Blender.app/Contents/MacOS/Blender`, reached through the `/usr/local/bin/blender` exec wrapper (`BLENDER` unset) | `engine.py:9,26-29`; `platform/conventions/versions.toml` `blender = "5.2"` (5.2.1 LTS). Version read from `Info.plist`, not launched. V2 needs Blender only for preparation tools, never for a normal checkout. |
| Python | uv 0.10.0; project venv 3.12.12; system python3 3.14.3 | `pyproject.toml:6` `>=3.11`; CI uses 3.12 (`python.yml`) ; UE embeds 3.11 (`versions.toml`) |
| Node / npm | 25.6.1 / 11.9.0 | Contracts need Node ≥24.16 and npm ≥11.11 (`platform/studio/contracts/package.json`); **local npm 11.9 is below 11.11** |
| ffmpeg | 9.0.2 | `>=7` |
| Rust | cargo/rustc 1.93.0 (default); Hakuba pins 1.97.1 | Board server and Bevy tooling; retired game tests stay disabled |

## Current project plugins and modules

`unreal/YorimichiV2.uproject` is authoritative:

- Runtime modules: `Yorimichi`, `YorimichiAssets`; editor/import module: `YorimichiImport` (`UncookedOnly`).
- Game, Editor and Server targets live in `unreal/Source/`.
- `AdditionalPluginDirectories` points to `../../../platform/engine/Plugins`.
- Enabled: HorseRacing, EnhancedInput, PythonScriptPlugin, EditorScriptingUtilities, Interchange, AtelierCore,
  AtelierAnimation, LiveBridge, AtelierFX, Skate and ElectraPlayer. Python and authoring tools use editor builds;
  ElectraPlayer remains necessary for MP3 playback.
- Disabled: AndroidFileServer (avoids generated tokens), Driving, AtelierStream and PixelStreaming2. Phone
  streaming and go-kart driving are excluded. The four character Blueprints were cleaned of the removed
  component in PR #784; current package automated checks report excluded content absent (PACKAGE.md).

V2's `Yorimichi.Build.cs` computes its network identity from V2 Source/Config/Plugins, the shared plugins and
V2's project descriptor. It no longer hashes the donor's source folders. Current source locations are organized
by feature in `unreal/Source/Yorimichi/README.md`; donor-era line numbers are not current removal tasks.

## Supported host route

DECISIONS D03 chose macOS for native Unreal work. Windows workers can prepare code and review, using their own
checkouts; a native Windows launch/admission/memory-guard adapter is not implemented. Do not route native work
around those protections. A separate Mac checkout still shares the same machine and is not second-machine proof.

Keep the same engine changelist for editable content. On a supported Mac, `atelier setup --headless` installs
its recorded build-tool patches. Actual second-machine open/edit/package and human collaboration proofs remain
unverified; independent migration proceeds while they await the owner-led acceptance work.
