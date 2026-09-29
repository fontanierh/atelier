"""Read the TOML manifests next to sources: game.toml, character.toml, bank.toml, asset.toml. Standard library only."""
import tomllib
from pathlib import Path

from .paths import game_dir


def load(path):
    with open(path, 'rb') as handle:
        return tomllib.load(handle)


def game(name):
    """games/<name>/game.toml, with `dir` added."""
    data = load(game_dir(name) / 'game.toml')
    data['dir'] = game_dir(name)
    return data


def find(root, filename):
    """Every `filename` under `root`, sorted, as (folder, manifest) pairs."""
    return [(path.parent, load(path)) for path in sorted(Path(root).rglob(filename))]
