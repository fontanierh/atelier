"""Argument parsing of `atelier play`: game arguments after `--` reach the game wherever the options sit.

    uv run pytest platform/studio/tests/test_cli.py

Only the parser runs; nothing is launched.
"""
import pytest

from atelier.cli import parse_args

UNREAL = ['--', '-RenderOffscreen', '-ForceRes']


@pytest.mark.parametrize('words, profile, settings', [
    (['sandbox'], 'play', ''),
    (['--profile', 'megapark', '--set', 'a=1', 'sandbox'], 'megapark', 'a=1'),
    (['sandbox', '--profile', 'megapark', '--set', 'a=1'], 'megapark', 'a=1'),
])
def test_play_passes_unreal_arguments_after_double_dash(words, profile, settings):
    args = parse_args(['play', *words, *UNREAL])
    assert (args.command, args.game, args.profile, args.set) == ('play', 'sandbox', profile, settings)
    assert args.extra == ['-RenderOffscreen', '-ForceRes']


def test_play_still_rejects_dash_arguments_without_double_dash():
    with pytest.raises(SystemExit):
        parse_args(['play', 'sandbox', '-RenderOffscreen'])


def test_play_memory_limit_is_opt_in():
    assert parse_args(['play', 'sandbox', *UNREAL]).memory_gib is None
    assert parse_args(['play', 'sandbox', '--memory-gib', '12', *UNREAL]).memory_gib == 12.


@pytest.mark.parametrize('gib', [8., 9.999, 24.001, 25., float('inf'), float('-inf'), float('nan')])
def test_play_refuses_a_memory_limit_out_of_range(gib):
    from atelier.cli import play
    with pytest.raises(SystemExit, match='--memory-gib'):
        play('sandbox', 'play', '', [], gib)


@pytest.mark.parametrize('gib', [10., 18., 23.5, 24.])
def test_script_play_forwards_the_selected_memory_limit(monkeypatch, tmp_path, gib):
    from types import SimpleNamespace
    from atelier import cli
    ctx = SimpleNamespace(out=tmp_path, game_dir=tmp_path, env=lambda: {})
    monkeypatch.setattr(cli, 'Context', lambda game: ctx)
    monkeypatch.setattr(cli.manifest, 'game', lambda game: {'play': {'play': {
        'script': 'launcher.py', 'args': ['--memory-gib={memory_gib}']}}})
    commands = []
    monkeypatch.setattr(cli.subprocess, 'call', lambda command, **kwargs: commands.append(command) or 0)
    assert cli.play('sandbox', 'play', 'show_fps=1', [], gib) == 0
    assert commands[0][2:] == [f'--memory-gib={gib:g}', '--settings', 'show_fps=1']


@pytest.mark.parametrize('gib', [None, 18., 24.])
def test_direct_play_passes_selected_or_default_ceiling_to_guard(monkeypatch, tmp_path, gib):
    from types import SimpleNamespace
    from atelier import cli
    from atelier.harness.safety import guarded
    ctx = SimpleNamespace(out=tmp_path, game_dir=tmp_path, unreal_app=tmp_path / 'Editor', uproject=tmp_path / 'Game.uproject',
                          env=lambda extra=(): {})
    monkeypatch.setattr(cli, 'Context', lambda game: ctx)
    monkeypatch.setattr(cli.manifest, 'game', lambda game: {'engine': 'unreal', 'play': {'play': {'args': ['-game']}}})
    calls = []
    monkeypatch.setattr(guarded, 'run', lambda command, folder, **kwargs: calls.append(kwargs) or 0)
    assert cli.play('sandbox', 'play', '', [], gib) == 0
    assert calls[0]['limit_gib'] == (10. if gib is None else gib)
    assert calls[0]['kind'] == 'game'
