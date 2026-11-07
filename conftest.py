"""Keep the Python suite hermetic: no test reads or writes this machine's home or Atelier state.

A machine running full capacity admission has a real cutover record, client configuration, broker
socket, render locks, board database and Claude session registry below HOME. Tests must never see
or change them, so the whole session runs with a private HOME and without the caller's ATELIER_*
settings, and every test then gets a fresh HOME of its own (child processes inherit it).

Several modules compute machine paths from HOME at import time, so those paths point into the
session HOME (or the HOME of the test that first imported them). Each test re-points them to its
own HOME, so state written by one test cannot reach another through a module-level path. Tests
that need specific paths still patch them as before.
"""
import os
from importlib.machinery import PathFinder
from pathlib import Path, PurePath
import re
import shutil
import sys
import tempfile

import pytest

_SESSION = pytest.MonkeyPatch()
_SESSION_HOME = None
_REPO = Path(__file__).resolve().parent

# Retired experiments (owner, 2026-11-07). Keep their source as reference, but never
# import their tests during collection. build-v2 is an unused build-system experiment,
# unrelated to the active game in games/yorimichi_v2.
_RETIRED_TEST_TREES = ('games/yorimichi', 'games/hakuba', 'platform/build-v2')
_RETIRED_TEST_FILES = ('platform/studio/tests/test_build_v2_*.py',)


def _retired_test_path(path):
    try:
        relative = path.resolve().relative_to(_REPO)
    except ValueError:
        return False
    return (any(relative.is_relative_to(tree) for tree in _RETIRED_TEST_TREES)
            or any(relative.match(pattern) for pattern in _RETIRED_TEST_FILES))


def pytest_ignore_collect(collection_path, config):
    if _retired_test_path(collection_path):
        return True


def _retired_test_module(name):
    """Resolve --pyargs package locations without executing their __init__ or test code."""
    search = None
    parts = name.split('.')
    for part in parts:
        # Look up each component in its parent's paths. A qualified namespace
        # spec would require importing the parent into sys.modules first.
        spec = PathFinder.find_spec(part, search)
        if spec is None:
            return False
        locations = list(spec.submodule_search_locations or ())
        if spec.origin:
            locations.append(spec.origin)
        if any(_retired_test_path(Path(path)) for path in locations):
            return True
        if spec.submodule_search_locations is None:
            return False
        search = list(spec.submodule_search_locations)
    return False


def _caller_settings():
    return [name for name in os.environ if name.startswith('ATELIER_')]


def pytest_configure(config):
    """Before collection imports any Atelier module, replace HOME and drop inherited Atelier settings."""
    # Pytest's ignores do not cover explicitly requested paths. Refuse those too,
    # before importing a retired test module or running any fixtures.
    for arg in config.args:
        name = arg.split('::', 1)[0]
        path = config.invocation_params.dir / name
        if (_retired_test_path(path)
                or (config.option.pyargs and _retired_test_module(name))):
            raise pytest.UsageError(f'Retired experiment tests are disabled: {arg}. '
                                    'Run games/yorimichi_v2/tests or the active shared tooling tests.')
    global _SESSION_HOME
    _SESSION_HOME = Path(tempfile.mkdtemp(prefix='atelier-tests-home-')).resolve()
    _SESSION.setenv('HOME', str(_SESSION_HOME))
    for name in _caller_settings():
        _SESSION.delenv(name)


def pytest_unconfigure(config):
    _SESSION.undo()
    if _SESSION_HOME is not None:
        shutil.rmtree(_SESSION_HOME, ignore_errors=True)


_REPOSITORY_MODULES = {}


def _repository_module(name, module):
    """Whether a loaded module is this checkout's own code (Atelier, game tools), not a dependency."""
    known = _REPOSITORY_MODULES.get(name)
    if known is None or known[0] is not module:
        try:
            path = Path(getattr(module, '__file__', None) or '').resolve()
        except (OSError, TypeError, ValueError):
            path = Path()
        own = path.is_relative_to(_REPO) and not path.is_relative_to(_REPO / '.venv')
        known = _REPOSITORY_MODULES[name] = (module, own)
    return known[1]


def _below_home(value, homes):
    """The part of a path below the session HOME or an earlier test's HOME, or None."""
    if value.is_relative_to(_SESSION_HOME):
        return value.relative_to(_SESSION_HOME)
    if value.is_relative_to(homes):
        parts = value.relative_to(homes).parts
        if parts and re.fullmatch(r'home\d+', parts[0]):
            return PurePath(*parts[1:])
    return None


def _home_paths(homes):
    """(module, attribute, path below HOME) for every checkout module-level path derived from HOME.

    A module first imported during a test derived its paths from that test's HOME, so those count too.
    """
    found = []
    for name, module in list(sys.modules.items()):
        if module is None or not _repository_module(name, module):
            continue
        for attribute, value in list(vars(module).items()):
            if isinstance(value, PurePath):
                relative = _below_home(value, homes)
                if relative is not None:
                    found.append((module, attribute, relative))
    return found


@pytest.fixture(autouse=True)
def hermetic_home(tmp_path_factory):
    """@cc [owner:fontanierh,label:safety] hermetic-test-home
    Every test MUST run with a fresh private HOME, inherited by its child processes, and with
    checkout module paths derived from HOME re-pointed into it. Tests MUST NOT read or change this
    machine's capacity record, client configuration, broker, render locks, board or sessions.
    """
    # A private MonkeyPatch, not the `monkeypatch` fixture: requesting that fixture here would set it
    # up before every test's own fixtures and so tear it down after them, changing when tests undo
    # patches of `os` relative to their temporary-directory cleanup.
    with pytest.MonkeyPatch.context() as patch:
        home = tmp_path_factory.mktemp('home')
        patch.setenv('HOME', str(home))
        for module, attribute, relative in _home_paths(home.parent):
            patch.setattr(module, attribute, home / relative)
        yield home
