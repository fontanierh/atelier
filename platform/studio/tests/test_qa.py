"""Retired scenario runs stop before snapshots, session selection or a subprocess."""
from pathlib import Path

import pytest

from atelier import build_snapshot, cli, live


def test_disabled_qa_never_reaches_a_session_or_runner(monkeypatch):
    monkeypatch.setattr(cli.manifest, 'game', lambda name: {'qa_enabled': False})
    def forbidden(*args, **kwargs):
        pytest.fail('disabled QA reached launch preparation')
    monkeypatch.setattr(build_snapshot, 'require_complete', forbidden)
    monkeypatch.setattr(live, 'select', forbidden)
    monkeypatch.setattr(cli.subprocess, 'call', forbidden)
    with pytest.raises(SystemExit, match='QA is disabled for retired game fixture'):
        cli.main(['qa', '--session', 'example-session', 'fixture', 'route'])


@pytest.mark.parametrize('data', [{}, {'qa_enabled': True}])
def test_active_qa_keeps_snapshot_check_and_game_session(monkeypatch, tmp_path, data):
    scenario = tmp_path / 'scenarios/route.py'
    scenario.parent.mkdir()
    scenario.write_text('raise AssertionError("test must not execute scenario code")\n')
    monkeypatch.setattr(cli.manifest, 'game', lambda name: data)
    monkeypatch.setattr(cli.paths, 'game_dir', lambda name: tmp_path)
    events = []
    monkeypatch.setattr(build_snapshot, 'require_complete', lambda *a, **kw: events.append('snapshot'))
    def run(command, *, env):
        assert events == ['snapshot']
        assert Path(command[1]) == scenario
        assert env['ATELIER_LIVE_GAME'] == 'fixture'
        events.append('scenario')
        return 17
    monkeypatch.setattr(cli.subprocess, 'call', run)
    assert cli.main(['qa', 'fixture', 'route']) == 17
    assert events == ['snapshot', 'scenario']
