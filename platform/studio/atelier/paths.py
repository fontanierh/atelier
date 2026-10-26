"""Where things are: the repository, each game's folders and its build folder.

Every script finds files through here instead of computing paths from its own location, so moving a script never
breaks a build. Standard library only (imported from Blender and Unreal too).

    ATELIER_BUILD_ROOT   moves every game's build folder (default: <repo>/build)
    ATELIER_CACHE        downloads and local product storage (default: ~/.cache/atelier)
"""
import os
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PLATFORM = REPO / 'platform'
STUDIO = PLATFORM / 'studio'
HARNESS = PLATFORM / 'harness'
CONVENTIONS = PLATFORM / 'conventions'
ENGINE_PLUGINS = PLATFORM / 'engine' / 'Plugins'
GAMES = REPO / 'games'
_DECLARATION = ContextVar('atelier_captured_declaration', default=None)


@contextmanager
def captured_declaration(game):
    """@cc [owner:fontanierh,label:safety] captured-declaration-paths-are-readonly
    Scoped declaration helpers MUST return the selected project's build path without
    creating it and MUST refuse cache/Content creation or another project's mkdir.
    Outside this scope existing path-helper creation behavior MUST remain unchanged.
    See test_captured_declaration_path_scope_is_write_free_and_default_unchanged.

    This covers these named path helpers, not arbitrary Python import effects or a
    sandbox. The caller must first establish the fixed captured provider boundary.
    """
    token = _DECLARATION.set(game)
    try:
        yield
    finally:
        _DECLARATION.reset(token)


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
    declaration = _DECLARATION.get()
    if declaration is not None:
        if game != declaration:
            raise ValueError('captured declaration requested another project build directory')
        return path
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir(*parts, create=True):
    """Machine-local data outside the repository, shared by independent checkouts."""
    path = Path(os.environ.get('ATELIER_CACHE') or Path.home() / '.cache' / 'atelier').joinpath(*parts)
    if create and _DECLARATION.get() is not None:
        raise ValueError('captured declaration cannot create cache state')
    if create:
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
    if _DECLARATION.get() is not None:
        raise ValueError('captured declaration cannot create runtime Content')
    path.mkdir(parents=True, exist_ok=True)
    return path
