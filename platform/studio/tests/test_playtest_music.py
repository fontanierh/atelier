"""`atelier playtest`: the optional music library, cloned into the app's container and never required.

    uv run pytest platform/studio/tests/test_playtest_music.py

The fetch script is a stand-in that exits with a chosen status; nothing is downloaded or launched.
"""
import plistlib, sys

import pytest

from atelier import playtest

# atelier playtest installs macOS release builds and clones the music with cp -cR on APFS.
pytestmark = [pytest.mark.macos_only]

SPEC = {'fetch': 'fetch.py', 'cache': 'music', 'into': 'Library/Application Support/Game/Music', 'arg': '-music='}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    home, cache, game = tmp_path / 'home', tmp_path / 'cache', tmp_path / 'game'
    for folder in (home, cache, game):
        folder.mkdir()
    monkeypatch.setattr(playtest.Path, 'home', classmethod(lambda cls: home))
    monkeypatch.setenv('ATELIER_CACHE', str(cache))
    monkeypatch.setattr(playtest.manifest, 'game', lambda name: {'dir': game})
    app = tmp_path / 'release' / 'Game' / 'Game.app' / 'Contents'
    app.mkdir(parents=True)
    with open(app / 'Info.plist', 'wb') as plist:
        plistlib.dump({'CFBundleIdentifier': 'com.example.Game'}, plist)
    launcher = tmp_path / 'release' / 'Game' / 'Play Game.command'
    library = cache / 'game' / 'music'
    library.mkdir(parents=True)
    (library / 'catalog.json').write_text('{"tracks": []}')
    (library / 'manifest.json').write_text('{"sha256": "one"}')

    def fetch(status):
        (game / 'fetch.py').write_text(f'import sys\nsys.exit({status})\n')
    fetch(0)
    target = home / 'Library' / 'Containers' / 'com.example.Game' / 'Data' / SPEC['into']
    return launcher, library, target, fetch


def test_music_is_cloned_into_the_container_and_named_on_the_command_line(setup):
    launcher, library, target, fetch = setup
    said = []
    assert playtest.music('game', SPEC, launcher, said.append) == f'-music={target}'
    assert (target / 'catalog.json').read_text() == '{"tracks": []}'
    assert not target.with_name('Music.partial').exists()
    assert any('linked' in line for line in said)


def test_a_matching_clone_is_reused(setup, monkeypatch):
    launcher, library, target, fetch = setup
    playtest.music('game', SPEC, launcher, lambda text: None)
    (target / 'kept').write_text('same clone')
    assert playtest.music('game', SPEC, launcher, lambda text: None) == f'-music={target}'
    assert (target / 'kept').exists()
    (library / 'manifest.json').write_text('{"sha256": "two"}')   # a new library replaces the clone
    playtest.music('game', SPEC, launcher, lambda text: None)
    assert not (target / 'kept').exists()
    assert (target / 'manifest.json').read_text() == '{"sha256": "two"}'


def test_a_failed_fetch_plays_without_music(setup):
    launcher, library, target, fetch = setup
    fetch(3)
    said = []
    assert playtest.music('game', SPEC, launcher, said.append) is None
    assert not target.exists()
    assert any('without it' in line for line in said)


def test_a_missing_library_plays_without_music(setup):
    launcher, library, target, fetch = setup
    (library / 'manifest.json').unlink()
    assert playtest.music('game', SPEC, launcher, lambda text: None) is None


def test_the_fetch_runs_quickly_with_this_interpreter(setup, monkeypatch):
    launcher, library, target, fetch = setup
    seen = []
    real = playtest.subprocess.run

    def run(command, *args, **kwargs):
        seen.append(command)
        return real(command, *args, **kwargs)
    monkeypatch.setattr(playtest.subprocess, 'run', run)
    playtest.music('game', SPEC, launcher, lambda text: None)
    assert seen[0][0] == sys.executable and seen[0][-1] == '--quick'
