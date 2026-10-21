"""Small original metadata recovery cannot become active-workspace capture or new success."""
import json
from pathlib import Path
import time

import pytest

from atelier import checkpoint_history as history, native_protocol as protocol


@pytest.fixture
def original(tmp_path, monkeypatch):
    monkeypatch.setenv('ATELIER_CACHE', str(tmp_path / 'cache'))
    source = tmp_path / 'producer'
    path = source / 'build/sample/stamps/unreal.mesh.json'; path.parent.mkdir(parents=True)
    stamp = dict(fingerprint='a' * 64, time=1., input_state={'inputs': {'<repo>/import.py': 'b' * 64}})
    path.write_text(json.dumps(stamp))
    boundary = time.time_ns()
    value = dict(schema=1, game='sample', checkout=protocol.identity(str(source.resolve())), context={}, files={}, stamps={},
                 steps=['unreal.mesh'], candidate_only=True, source_revision='d' * 40)
    key = protocol.identity(value)
    store = protocol.ReadStore('sample')
    protocol.atomic_json(store.directory / 'candidate-sources' / (key + '.json'), value)
    return source, path, stamp, boundary, key, store


def test_recovers_only_original_history_without_writing_producer(original):
    source, path, stamp, boundary, key, store = original
    before = (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_ctime_ns)
    result = history.recover('sample', key, source, ['unreal.mesh'], before_ns=boundary)
    assert result['recovered'] == ['unreal.mesh'] and not result['missed']
    saved = history.original(store, result['checkpoint'])
    assert saved['historical_stamps'] == {'unreal.mesh': stamp}
    assert saved['stamps'] == {} and not saved.get('actions') and saved['files'] == {}
    assert (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_ctime_ns) == before
    assert not (store.directory / 'actions').exists()


@pytest.mark.parametrize('change', ['rewritten', 'linked', 'missing', 'no-inputs', 'touched', 'moving'])
def test_rewritten_or_incomplete_history_is_a_miss(original, monkeypatch, change):
    source, path, stamp, boundary, key, store = original
    if change == 'rewritten': path.write_text(path.read_text())
    elif change == 'missing': path.unlink()
    elif change == 'linked':
        other = path.with_suffix('.copy'); path.rename(other); path.symlink_to(other)
    elif change in ('no-inputs', 'touched'):
        if change == 'no-inputs': stamp.pop('input_state')
        else: stamp['touched'] = True
        path.write_text(json.dumps(stamp))
        # Keep the test focused on malformed content rather than newer metadata.
        boundary = time.time_ns(); origin = store.directory / 'candidate-sources' / (key + '.json')
        origin.touch()
    else:
        original_signature = history.signature
        calls = []
        def move(info):
            calls.append(None)
            return original_signature(info) if len(calls) < 4 else ('changed',)
        monkeypatch.setattr(history, 'signature', move)
    result = history.recover('sample', key, source, ['unreal.mesh'], before_ns=boundary)
    assert result['checkpoint'] == key and result['recovered'] == []
    assert 'unreal.mesh' in result['missed']


def test_boundary_after_snapshot_cannot_recover_later_history(original):
    source, _, _, _, key, _ = original
    with pytest.raises(protocol.CheckpointError, match='boundary'):
        history.recover('sample', key, source, ['unreal.mesh'], before_ns=time.time_ns()+10**9)


def test_other_checkout_cannot_supply_original_policy(original, tmp_path):
    _, _, _, boundary, key, _ = original
    with pytest.raises(protocol.CheckpointError, match='captured producer'):
        history.recover('sample', key, tmp_path / 'unrelated', ['unreal.mesh'], before_ns=boundary)
