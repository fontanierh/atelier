"""The engines a game can run on, and which one each game uses.

A game names its engine in `game.toml` (`engine = "unreal"` or `engine = "bevy"`). The engine answers what differs
between them: which tools `atelier doctor` checks, how `atelier play` launches a profile, and whether the game has the
live bridge, browser streaming and a template for `atelier new`. Everything else (build steps, products, caching,
admission, releases) is the same for every engine: a game's `build.py` declares its steps with the engine's commands.

A manifest without `engine` is an Unreal game when it holds an Unreal project (`unreal/*.uproject`), as every game did
before engines were named; anything else must say which engine it uses.
"""
from pathlib import Path

from .. import manifest, paths


class Engine:
    """What one engine does for the commands. Subclasses set `name` and override what they support."""
    name = ''
    live = False                 # the live bridge (`atelier live`) answers while the game runs
    stream = False               # `atelier stream` can serve the game to a browser
    template = None              # the template `atelier new --engine <name>` copies, or None

    def checks(self, ctx, data):
        """(ok, message) pairs for `atelier doctor`: the engine's own tools and the game's engine sources."""
        return []

    def launch(self, ctx, data, profile, spec, folder, settings, extra):
        """(argv, env pairs) running play profile `spec` of the game whose manifest is `data` directly, its logs in
        `folder`, with `settings` overrides (key=value;key=value, may be empty) and `extra` arguments from after `--`."""
        raise SystemExit(f'the {self.name} engine cannot launch play profile {profile!r} without a script')

    def unsupported(self, what):
        return SystemExit(f'{what} is not available for {self.name} games')


def _registry():
    from .bevy import Bevy
    from .unreal import Unreal
    return {engine.name: engine for engine in (Unreal(), Bevy())}


def named(name):
    """The engine called `name`."""
    engines = _registry()
    if name not in engines:
        raise SystemExit(f'unknown engine {name!r}; the engines are {", ".join(sorted(engines))}')
    return engines[name]

def name_of(data, game_dir):
    """The engine a manifest `data` for the game in `game_dir` names, or Unreal for a manifest from before engines
    were named that holds an Unreal project."""
    name = data.get('engine')
    if name is None:
        if any((Path(game_dir) / 'unreal').glob('*.uproject')):
            return 'unreal'
        raise SystemExit(f'{Path(game_dir) / "game.toml"} names no engine: add engine = "unreal" or engine = "bevy"')
    if not isinstance(name, str):
        raise SystemExit(f'{Path(game_dir) / "game.toml"}: engine must be a string')
    return name

def of(game):
    """The engine game `game` runs on."""
    return named(name_of(manifest.game(game), paths.game_dir(game)))
