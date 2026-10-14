import hashlib

import pytest

from atelier import contract_review_tools as tools


def fixture_action(tmp_path, monkeypatch, extra=''):
    source = ''.join(f'      uses: {ref}\n' for ref in tools.ACTION_PINS)
    source += ('        node-version: ${{ steps.node-version.outputs.version }}\n'
               '        npm ci\n        effort: ${{ inputs.effort }}\n' + extra)
    action = tmp_path / 'action.yml'; action.write_text(source)
    monkeypatch.setattr(tools, 'SOURCE_SHA256', hashlib.sha256(source.encode()).hexdigest())
    return action


def test_transitive_actions_and_cli_are_pinned_before_use(tmp_path, monkeypatch):
    action = fixture_action(tmp_path, monkeypatch)
    tools.prepare(action)
    value = action.read_text()
    assert all(ref in value for ref in tools.ACTION_PINS.values())
    assert 'npm ci --ignore-scripts' in value
    assert '        package-manager-cache: false\n' in value
    assert f'codex-version: {tools.CODEX_VERSION}' in value


def test_unreviewed_upstream_bytes_are_rejected_without_rewriting(tmp_path):
    action = tmp_path / 'action.yml'; action.write_text('changed upstream action')
    with pytest.raises(ValueError, match='differs'): tools.prepare(action)
    assert action.read_text() == 'changed upstream action'


def test_added_mutable_action_is_rejected(tmp_path, monkeypatch):
    action = fixture_action(tmp_path, monkeypatch, '      uses: example/action@main\n')
    original = action.read_text()
    with pytest.raises(ValueError, match='Unpinned'): tools.prepare(action)
    assert action.read_text() == original
