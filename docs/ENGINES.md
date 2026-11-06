# Engines

A game on Atelier runs on one engine: **Unreal Engine 5.8** or **Bevy** (Rust). The `atelier` command is the same for
both. The engine decides only what really differs between them.

| | Unreal | Bevy |
|---|---|---|
| `game.toml` | `engine = "unreal"` | `engine = "bevy"`, `[bevy] workspace = "."` |
| Build commands in `build.py` | `UnrealCompile`, `UnrealScript`, `UnrealGame`, `UnrealPackage` | `Cargo` |
| `atelier doctor` | Unreal, Xcode and Metal, the `.uproject`, Blender | cargo, rustup when `rust-toolchain.toml` pins one, `Cargo.toml` |
| `atelier play` profile | `args` for the editor binary, `-set=` for `--set` | `binary`, `args`, `env`, optional `settings_env` for `--set` |
| `atelier new --engine` | copies `games/sandbox` | copies `platform/studio/templates/bevy` |
| `atelier live`, `atelier stream` | yes | no |
| `atelier setup` | the Unreal toolchain on macOS | not needed |

Everything else is shared by every engine: build steps, inputs, named products and caching, the admission broker and
memory guards, `atelier qa` scenarios, `atelier fetch`, releases and the board. A `Python` or `Blender` step works the
same in either kind of game.

## Which engine a game uses

`atelier.engines.of(game)` reads `engine` from `game.toml`. A manifest without it is an Unreal game when it holds an
Unreal project (`unreal/*.uproject`), as every game did before engines were named. Anything else must name its engine;
an unknown name is an error.

## A Bevy game

```toml
engine = "bevy"
build = "build.py"

[bevy]
workspace = "."                          # the folder holding Cargo.toml, from the game's folder

[play.play]
binary = "target/release/my_game"        # from the workspace; a build step builds it
args = ["--windowed"]                    # {run}: this run's log folder; {workspace}: the workspace folder
env = { BEVY_ASSET_ROOT = "{workspace}" }
settings_env = "MY_GAME_SET"             # optional: `atelier play --set k=v` arrives in this variable
```

```python
from atelier.build import Cargo, Step

def steps(ctx):
    return [Step('game.binary', [Cargo(('build', '--release'), workspace=GAME)],
                 inputs=[GAME / 'src', GAME / 'Cargo.toml', GAME / 'Cargo.lock'], heavy=True)]
```

`Cargo` runs `cargo <args>` in the workspace folder, so the workspace's `.cargo/config.toml` aliases and
`rust-toolchain.toml` apply exactly as they do by hand. It asks admission for the compile slot, as an Unreal compile
does, and caps rustc at three workers with `CARGO_BUILD_JOBS`. Cargo keeps its own incremental state in the
workspace's `target/`. The step's inputs only decide whether the command runs.

`atelier play` runs the binary under the same guard and memory limit as an Unreal game (`kind='game'`).

## Adding an engine

Subclass `atelier.engines.Engine` in `platform/studio/atelier/engines/<name>.py`. Set `name`, `live`, `stream` and
`template`, then implement `checks` and `launch`. Register it in `engines._registry`. Then add its build commands as
dataclasses with `argv(ctx)`, and `admission_kind = 'compile'` when they compile. The build runs any such command
under the guard, and its `repr` is its fingerprint.
