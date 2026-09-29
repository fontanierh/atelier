"""Where things are: the repository, each game's folders and its build folder.

Every script finds files through here instead of computing paths from its own location, so moving a script never
breaks a build. Standard library only (imported from Blender and Unreal too).

    ATELIER_BUILD_ROOT   moves every game's build folder (default: <repo>/build)
    ATELIER_CACHE        downloads that are not redistributed, such as sound masters (default: ~/.cache/atelier)
"""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PLATFORM = REPO / 'platform'
STUDIO = PLATFORM / 'studio'
CONVENTIONS = PLATFORM / 'conventions'
ENGINE_PLUGINS = PLATFORM / 'engine' / 'Plugins'
LIBRARY = PLATFORM / 'library'
GAMES = REPO / 'games'


def game_dir(game):
    """games/<game>, the game's sources."""
    path = GAMES / game
    if not path.is_dir():
        raise FileNotFoundError(f'no game called {game!r} in {GAMES}')
    return path


def build_root():
    return Path(os.environ.get('ATELIER_BUILD_ROOT') or REPO / 'build')


def build_dir(game):
    """build/<game>, everything a build generates for that game. Created on first use."""
    path = build_root() / game
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir(*parts):
    """Downloads kept outside the repository, shared by every checkout on this machine."""
    path = Path(os.environ.get('ATELIER_CACHE') or Path.home() / '.cache' / 'atelier').joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def unreal_dir(game):
    """games/<game>/unreal, the Unreal project folder."""
    return game_dir(game) / 'unreal'


def uproject(game):
    projects = sorted(unreal_dir(game).glob('*.uproject'))
    if not projects:
        raise FileNotFoundError(f'no .uproject in {unreal_dir(game)}')
    return projects[0]


def content_data(game):
    """unreal/Content/Data: loose runtime files (world layout, map) staged by the build and packaged as-is."""
    path = unreal_dir(game) / 'Content' / 'Data'
    path.mkdir(parents=True, exist_ok=True)
    return path
