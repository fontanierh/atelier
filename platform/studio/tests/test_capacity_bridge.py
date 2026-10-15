"""Real file locks exercise migration without native processes or machine admission."""
import fcntl
import json
from types import SimpleNamespace

import pytest

from atelier.safety import render_lock as locks


@pytest.fixture
def lanes(tmp_path, monkeypatch):
    monkeypatch.setenv('ATELIER_RENDER_LOCK', str(tmp_path / 'render.lock'))
    monkeypatch.setattr(locks, 'usage', lambda pid: SimpleNamespace(started=123))
    return locks.lock_paths()


def available(path):
    with path.open('a+') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(handle, fcntl.LOCK_UN)
        return True


@pytest.mark.parametrize('kind', locks.KINDS)
def test_bridge_excludes_every_legacy_lane_and_releases_together(lanes, kind):
    selected = []
    with locks.render_lock('capacity migration', kind=kind, exclusive_bridge=True, scan=False,
                           on_slot=lambda slot, why: selected.append(slot)):
        assert all(not available(path) for path in lanes.values())
        records = [json.loads(path.read_text()) for path in lanes.values()]
        assert all(record == records[0] for record in records)
        assert records[0]['capacity_bridge'] is True
        assert records[0]['kind'] == kind
        assert selected == ['big']
    assert all(available(path) and path.read_text() == '' for path in lanes.values())


@pytest.mark.parametrize('busy', ['big', 'small', 'fitting'])
def test_busy_lane_preserves_records_and_holds_no_subset(lanes, busy):
    # A pre-protocol client may hold a mutex without a current JSON record.
    # Kernel exclusion, rather than the record, decides whether it is occupied.
    for label, path in lanes.items():
        path.write_text('previous-' + label)
    with lanes[busy].open('a+') as other:
        fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(locks.RenderBusy):
            with locks.render_lock('capacity migration', exclusive_bridge=True, scan=False):
                pytest.fail('a competing lane was admitted')
        assert all(path.read_text() == 'previous-' + label for label, path in lanes.items())
        assert all(available(path) for label, path in lanes.items() if label != busy)
        assert not available(lanes[busy])
    # A refused compile must not wait ten minutes holding BIG before retrying.
    with locks.render_lock('capacity migration', kind='compile', exclusive_bridge=True, scan=False):
        assert all(not available(path) for path in lanes.values())


def test_foreign_process_scan_still_vetoes_capacity_bridge(lanes, monkeypatch):
    monkeypatch.setattr(locks, 'process_table', lambda: [(987, 1, '/tools/Blender')])
    with pytest.raises(locks.RenderBusy, match='no harness owns'):
        with locks.render_lock('capacity migration', exclusive_bridge=True, scan=True):
            pytest.fail('an unmanaged native process was ignored')
    assert all(available(path) and path.read_text() == '' for path in lanes.values())


@pytest.mark.parametrize('option', [dict(wait=1), dict(small_gib=1), dict(fitting_gib=1)])
def test_bridge_never_waits_or_selects_a_single_lane(lanes, option):
    with pytest.raises(ValueError, match='one nonblocking attempt'):
        with locks.render_lock('capacity migration', exclusive_bridge=True, scan=False, **option):
            pytest.fail('invalid bridge options accepted')
    assert all(not path.exists() for path in lanes.values())


def test_exception_releases_all_bridge_locks(lanes):
    with pytest.raises(RuntimeError, match='guard did not start'):
        with locks.render_lock('capacity migration', exclusive_bridge=True, scan=False):
            raise RuntimeError('guard did not start')
    assert all(available(path) and path.read_text() == '' for path in lanes.values())
