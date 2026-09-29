# Atelier

Atelier is a small game platform built around Unreal Engine 5.8 and Blender, made to be driven by people and agents
together. It has five parts:

- **Studio** (`platform/studio`): the `atelier` command and the Python package behind it. It calls the AI services
  (Sunburst images, Tripo models, H3 and Seedance reference videos), runs Blender without a window, builds worlds,
  characters and sound banks, imports everything into Unreal, and runs the scenario tests.
- **Engine kit** (`platform/engine/Plugins`): Unreal plugins that any game can switch on.
- **Conventions** (`platform/conventions`): the house rules every tool and plugin agrees on: units and axes, the
  humanoid bone contract, clip roles, sound cue names, file formats.
- **Library** (`platform/library`): generic assets any game may borrow.
- **Games** (`games/`): each game owns its world, characters, look, sounds and feel. **Yorimichi**
  (`games/yorimichi`), a painterly Japanese island, is the first.

Everything is text: layouts, meshes, materials, poses and clips are produced by scripts, and Unreal's imported assets
are build output. [ARCHITECTURE.md](ARCHITECTURE.md) explains the layers and the rules that keep the platform
reusable. [docs/MIGRATION.md](docs/MIGRATION.md) tracks the move from the original prototype repository.

## Requirements

| Tool | Version | Used for |
|---|---|---|
| macOS on Apple silicon | 15+ | the only platform tested so far |
| Unreal Engine | 5.8 (`/Users/Shared/Epic Games/UE_5.8`, or set `UE_ROOT`) | the game |
| Blender | 5.2.1 LTS on `PATH` | meshes, rigs, clips |
| Python | 3.11+ with numpy and Pillow (`uv sync` installs them) | the studio |
| ffmpeg | 7+ on `PATH` | sound slicing, films |
| Node | 24+ (optional) | phone streaming, H3 / Seedance scripts |

## Build and play Yorimichi from a fresh clone

```sh
git config core.hooksPath .githooks     # the pre-commit lint (this repository is public)
uv sync                                  # one Python environment (numpy, Pillow, httpx)
uv run atelier doctor yorimichi          # checks Unreal, Blender, ffmpeg and the sources
uv run atelier fetch yorimichi           # downloads the Sonniss sound masters (not redistributed here)
uv run atelier build yorimichi           # world, characters, sounds, effects, Unreal import, compile
uv run atelier play yorimichi            # 1080p window; `--profile desktop` for the 1440p desktop profile
```

`atelier build` only reruns steps whose inputs changed; `atelier build yorimichi --list` shows every step and
`atelier build yorimichi <step>` runs one (and what it depends on). Generated files go to `build/yorimichi/` and to the
game's ignored `unreal/Content/`, both safe to delete.

Paid AI calls (Sunburst, Tripo, H3, Seedance) never run as part of a build. They need API keys in a local `.env` (see
[.env.example](.env.example)), which is ignored by git.

## Licences of what is in this repository

The code and the assets made for these games (layouts, generated meshes, the characters' source files, AI-generated
concepts and textures) are the author's. Third-party material is not redistributed here:

- **Sounds** come from the Sonniss GDC Game Audio Bundles. Their licence allows shipping them inside a game but not
  redistributing them as files, so `atelier fetch` downloads the masters from the public archive and the build slices
  them. The licence also forbids using them with AI tools.
- **Mixamo** motion was retargeted onto Warm Original's sword attacks and is baked into that character's source file;
  the downloaded Mixamo files are not included.
- **Fonts**: Noto Sans JP, under the SIL Open Font License (`games/yorimichi/world/regions/hidamari/fonts/OFL.txt`).
