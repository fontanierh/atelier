"""Argument parsing of `atelier play`: Unreal arguments after `--` reach the game wherever the options sit.

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


@pytest.mark.parametrize('gib', [8., 16.])
def test_play_refuses_a_memory_limit_out_of_range(gib):
    from atelier.cli import play
    with pytest.raises(SystemExit, match='--memory-gib'):
        play('sandbox', 'play', '', [], gib)


def test_script_play_forwards_the_selected_memory_limit(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from atelier import cli
    ctx = SimpleNamespace(out=tmp_path, game_dir=tmp_path, env=lambda: {})
    monkeypatch.setattr(cli, 'Context', lambda game: ctx)
    monkeypatch.setattr(cli.manifest, 'game', lambda game: {'play': {'play': {
        'script': 'launcher.py', 'args': ['--memory-gib={memory_gib}']}}})
    commands = []
    monkeypatch.setattr(cli.subprocess, 'call', lambda command, **kwargs: commands.append(command) or 0)
    assert cli.play('sandbox', 'play', 'show_fps=1', [], 12.) == 0
    assert commands[0][2:] == ['--memory-gib=12', '--settings', 'show_fps=1']
