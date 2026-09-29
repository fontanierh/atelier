# Atelier

Atelier is a small game platform built around Unreal Engine 5.8 and Blender, made to be driven by people and agents
together. It has six parts:

- **Studio** (`platform/studio`): the `atelier` command and the Python package behind it. It calls the AI services
  (Sunburst images, Tripo models, H3 and Seedance reference videos), runs Blender without a window, builds worlds,
  characters and sound banks, imports everything into Unreal, streams games to browsers and runs the scenario tests.
- **Engine kit** (`platform/engine/Plugins`): Unreal plugins any game can switch on: core runtime helpers, animation
  nodes, effects, skateboarding, streaming and the live bridge.
- **Web** (`platform/web`): the stream's web server and pages: the plain player and touch primitives for game pages.
- **Conventions** (`platform/conventions`): the house rules every tool and plugin agrees on: units and axes, the
  humanoid bone contract, clip roles, sound cue names, file formats.
- **Library** (`platform/library`): generic assets any game may borrow.
- **Games** (`games/`): each game owns its world, characters, look, sounds and feel. **Yorimichi**
  (`games/yorimichi`), a painterly Japanese island, is the first. **Sandbox** (`games/sandbox`) is the smallest game on
  the platform: a flat test ground that proves the platform works without Yorimichi.

Everything is text: layouts, meshes, materials, poses and clips are produced by scripts, and Unreal's imported assets
are build output. [ARCHITECTURE.md](ARCHITECTURE.md) explains the layers, what exists today and the rules that keep the
platform reusable. [docs/MIGRATION.md](docs/MIGRATION.md) tracks the move from the original prototype repository.

## Requirements

| Tool | Version | Used for |
|---|---|---|
| macOS on Apple silicon | 15+ | the only platform tested so far |
| Unreal Engine | 5.8 (`/Users/Shared/Epic Games/UE_5.8`, or set `UE_ROOT`) | the games |
| Blender | 5.2.1 LTS on `PATH` (or set `BLENDER`) | meshes, rigs, clips |
| Python | 3.11+ with numpy and Pillow (`uv sync` installs them) | the studio |
| ffmpeg | 7+ on `PATH` | sound slicing, films |
| Node | 24+ (optional) | streaming pages and their tests, H3 / Seedance scripts |
| coturn, Tailscale | (optional) | streaming to other devices (`brew install coturn`) |

## Build and play Yorimichi from a fresh clone

```sh
git config core.hooksPath .githooks     # the pre-commit lint (this repository is public)
uv sync                                  # one Python environment (numpy, Pillow, httpx)
uv run atelier doctor yorimichi          # checks Unreal, Blender, ffmpeg, the sources and the sound masters
uv run atelier fetch yorimichi           # downloads the Sonniss sound masters (not redistributed here)
uv run atelier build yorimichi           # world, characters, sounds, effects, compile, Unreal import
uv run atelier play yorimichi            # 1080p window; `--profile desktop` for the 1440p desktop profile
```

`atelier build` only reruns steps whose inputs changed; `atelier build yorimichi --list` shows every step and
`atelier build yorimichi <step>` runs one (and what it depends on). Generated files go to `build/yorimichi/` and to the
game's ignored `unreal/Content/`, both safe to delete. A fresh clone builds Yorimichi end to end with these commands
(see docs/MIGRATION.md for the last verified run and its timings).

Paid AI calls (Sunburst, Tripo, H3, Seedance) never run as part of a build. They need API keys in a local `.env` (see
[.env.example](.env.example)), which is ignored by git.

## Everyday commands

| Command | What |
|---|---|
| `atelier play <game> [--profile P]` | play under the render lock and memory guard; Yorimichi's profiles: `play`, `desktop`, `desktop-1440`, `foxqa`, `swordqa` |
| `atelier live state` / `py "..."` / `shot` | talk to the running game through the live bridge (loopback only) |
| `atelier qa <game> <scenario>` | run `games/<game>/scenarios/<scenario>.py`; Yorimichi: `skate` (against a running game), `sailboat`, `zeppelin`, `lake` |
| `atelier stream <game> start [--local]` / `status` / `stop` | stream the game to a browser (below) |
| `atelier lint` | the public-repository rules: no secrets, no personal paths, no game names in the platform |

## Streaming

`atelier stream yorimichi start` runs the game offscreen and serves two pages through Tailscale
(`https://<this Mac>.<tailnet>.ts.net:8443/`, or `http://127.0.0.1:8080/` with `--local`):

- `/` is Yorimichi's phone page: touch controls, the world map and settings;
- `/play/` is the platform's plain player: the far device's own keyboard, mouse or controller drive the game, for a
  handheld PC or a friend's computer.

Details: [platform/web/stream/README.md](platform/web/stream/README.md) and
[games/yorimichi/phone/README.md](games/yorimichi/phone/README.md).

## Checks

- Python: `uv run python -m unittest discover -s platform/studio/tests` (the build engine, machine safety, conventions).
- Yorimichi on a fresh build: `atelier qa yorimichi skate` (22 cases), `atelier play yorimichi --profile foxqa` and
  `--profile swordqa` (scripted fights), `atelier qa yorimichi sailboat|zeppelin|lake`, and with a local stream the
  phone smoke tests in `games/yorimichi/phone/` and `platform/web/stream/player-smoke.mjs`.
- The sandbox: `atelier build sandbox`, `atelier play sandbox`, then `atelier live state`.

## Licences of what is in this repository

The code and the assets made for these games (layouts, generated meshes, the characters' source files, AI-generated
concepts and textures) are the author's. Third-party material is not redistributed here:

- **Sounds** come from the Sonniss GDC Game Audio Bundles. Their licence allows shipping them inside a game but not
  redistributing them as files, so `atelier fetch` downloads the masters from the public archive and the build slices
  them. The licence also forbids using them with AI tools.
- **Mixamo** motion was retargeted onto Warm Original's sword attacks and is baked into that character's source file;
  the downloaded Mixamo files are not included.
- **Fonts**: Noto Sans JP, under the SIL Open Font License (`games/yorimichi/world/regions/hidamari/fonts/OFL.txt`).
- **Engine content**: the sandbox references Unreal's basic shapes and textures; nothing from the engine is copied.
- **Packages**: Epic's Pixel Streaming libraries, express, esbuild and Playwright are installed by `npm ci` from
  `platform/web/package-lock.json`; they are not in the repository.
