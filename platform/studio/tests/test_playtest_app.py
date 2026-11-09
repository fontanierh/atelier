"""`atelier playtest GAME --app PATH`: a local package runs its own executable as a guarded game, nothing else.

    uv run pytest platform/studio/tests/test_playtest_app.py

The guard is a stand-in that records its call; nothing is launched.
"""
import plistlib

import pytest

from atelier import playtest
from atelier.harness.safety import guarded


def packaged(tmp_path, executable='Game', write=True):
    app = tmp_path / 'Game.app'
    (app / 'Contents' / 'MacOS').mkdir(parents=True)
    with open(app / 'Contents' / 'Info.plist', 'wb') as plist:
        plistlib.dump({'CFBundleExecutable': executable, 'CFBundleIdentifier': 'com.example.game'}, plist)
    if write:
        (app / 'Contents' / 'MacOS' / executable).write_text('#!/bin/sh\n')
    return app


def test_a_local_app_runs_its_executable_under_the_game_guard(tmp_path, monkeypatch):
    app = packaged(tmp_path)
    calls = []
    monkeypatch.setattr(guarded, 'run', lambda argv, logs, **kw: calls.append((argv, logs, kw)) or 0)
    monkeypatch.setattr(playtest.manifest, 'game', lambda name: {'dir': tmp_path})
    monkeypatch.setattr(playtest.paths, 'build_dir', lambda game: tmp_path / 'build' / game)
    assert playtest.play_app('game', app, ('-windowed',), 14.) == 0
    (argv, logs, kw), = calls
    assert argv == [str(app / 'Contents/MacOS/Game'), '-windowed']
    assert kw['kind'] == 'game' and kw['watch'] == ('Game',) and kw['limit_gib'] == 14.
    assert logs.parent == tmp_path / 'build' / 'game' / 'logs' and logs.is_dir()


def test_an_app_without_its_executable_is_refused(tmp_path):
    with pytest.raises(SystemExit, match='no executable'):
        playtest.app_executable(packaged(tmp_path, write=False))
    with pytest.raises(SystemExit, match='not a packaged app'):
        playtest.app_executable(tmp_path / 'Missing.app')
