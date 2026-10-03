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
