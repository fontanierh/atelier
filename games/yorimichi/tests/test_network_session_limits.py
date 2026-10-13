"""Extra memory may be requested only for an actual rendered QA observer."""
import importlib.util
from pathlib import Path
import sys

import pytest


def session_module():
    path = Path(__file__).resolve().parents[1] / 'tools/review_network_session.py'
    spec = importlib.util.spec_from_file_location('network_session_limit_review', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('option,value', [('--aggregate-memory-gib', '18'), ('--rendered-memory-gib', '12')])
def test_higher_limits_refuse_a_headless_pair(monkeypatch, option, value):
    module = session_module()
    monkeypatch.setattr(sys, 'argv', ['review_network_session.py', '--listen', option, value])
    with pytest.raises(SystemExit) as result:
        module.main()
    assert result.value.code == 2


@pytest.mark.parametrize('view', ['host', 'guest'])
def test_explicit_rendered_limits_reach_only_the_guarded_worker(tmp_path, monkeypatch, view):
    from atelier.safety import guarded
    module = session_module()
    observed = {}

    def capture(command, folder, **options):
        observed.update(command=command, options=options)
        return 0

    monkeypatch.setattr(guarded, 'run', capture)
    monkeypatch.setattr(sys, 'argv', ['review_network_session.py', '--listen', '--render-view', view,
                                    '--aggregate-memory-gib', '18', '--rendered-memory-gib', '12',
                                    '--output', str(tmp_path / 'run')])
    assert module.main() == 0
    command = observed['command']
    assert command[command.index('--aggregate-memory-gib') + 1] == '18'
    assert command[command.index('--rendered-memory-gib') + 1] == '12'
    assert command[command.index('--render-view') + 1] == view
    assert observed['options']['kind'] == 'game'
    assert observed['options']['track_tree'] is True
    assert observed['options']['timeout'] == 330
