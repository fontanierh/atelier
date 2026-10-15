"""Atomic report publication is retryable; malformed or unsafe evidence remains a refusal."""
import json
import os
import time
import pytest

from atelier import capacity_protocol as wire
from atelier.capacity_broker import CapacityBroker


@pytest.mark.parametrize('stage', ['before-stat', 'during-read'])
@pytest.mark.parametrize('strict', [False, True])
def test_atomic_replacement_reopens_only_guard_reports(tmp_path, monkeypatch, stage, strict):
    report = tmp_path / 'report.json'
    report.write_text('{"generation":1}')
    replacement = tmp_path / 'next.json'
    replacement.write_text('{"generation":2}')
    operation = 'fstat' if stage == 'before-stat' else 'read'
    original = getattr(os, operation)
    calls = []
    def race(*args):
        if not calls:
            replacement.replace(report)
        calls.append(True)
        return original(*args)
    monkeypatch.setattr(wire.os, operation, race)
    if strict:
        with pytest.raises(wire.CapacityError):
            wire.private_file(report, limit=wire.MAX_FRAME, private=False)
    else:
        assert json.loads(wire.guard_report(report)) == {'generation': 2}


def test_continuous_replacement_is_bounded(tmp_path, monkeypatch):
    report = tmp_path / 'report.json'
    report.write_text('{}')
    original = os.read
    calls = []
    def race(fd, count):
        replacement = tmp_path / 'next.json'
        replacement.write_text('{}')
        replacement.replace(report)
        calls.append(True)
        return original(fd, count)
    monkeypatch.setattr(wire.os, 'read', race)
    with pytest.raises(wire.CapacityError, match='repeatedly replaced'):
        wire.guard_report(report)
    assert len(calls) == 3


@pytest.mark.parametrize('bad', ['mode', 'symlink', 'hardlink', 'oversized', 'malformed'])
def test_persistent_invalid_guard_report_refuses(tmp_path, bad):
    report = tmp_path / 'report.json'
    report.write_text('{broken' if bad == 'malformed' else '{}')
    if bad == 'mode':
        report.chmod(0o666)
    elif bad == 'symlink':
        target = tmp_path / 'target.json'
        report.rename(target)
        report.symlink_to(target)
    elif bad == 'hardlink':
        os.link(report, tmp_path / 'other.json')
    elif bad == 'oversized':
        report.write_bytes(b'x' * (wire.MAX_FRAME + 1))
    with pytest.raises(wire.CapacityError):
        wire.decode(wire.guard_report(report))


@pytest.mark.parametrize('invalid', [None, 'stale', 'child'])
def test_replacement_still_requires_valid_receipt_identity_and_freshness(tmp_path, monkeypatch, invalid):
    process, tree, replacement = (tmp_path / name for name in ('process.json', 'tree.json', 'next.json'))
    limit = 128 * 1024**2
    receipt = dict(time=time.time(), state='running', limit_bytes=limit, pid=20, process_start=20)
    process.write_text(json.dumps(receipt))
    if invalid == 'stale':
        receipt['time'] -= 10
    if invalid == 'child':
        receipt['pid'] = 21
    replacement.write_text(json.dumps(receipt))
    tree.write_text(json.dumps(dict(observed_monotonic=time.monotonic(), state='running',
                                   limit_bytes=limit, owner=20, owner_started=20, processes=[], footprint_bytes=0)))
    guards = {name: dict(pid=30, start=30, report=str(path))
              for name, path in [('process_guard', process), ('tree_guard', tree)]}
    original = os.read
    def race(fd, count):
        if replacement.exists():
            replacement.replace(process)
        return original(fd, count)
    monkeypatch.setattr(wire.os, 'read', race)
    def validate():
        return wire.validate_guards(guards, (20, 20), (10, 10), limit, 128,
                                    started=lambda pid: pid, alive=lambda pin: True, child_of=lambda *args: True)
    if invalid:
        with pytest.raises(wire.CapacityError, match='stale or mismatched' if invalid == 'stale' else 'another child'):
            validate()
    else:
        assert validate().footprint_bytes == 0


def test_guard_health_logs_stable_reason_without_exception_paths(capsys):
    broker = object.__new__(CapacityBroker)
    def fail(*args):
        raise OSError('secret path or token must not be logged')
    broker.guards = fail
    broker._root_exited = lambda record: False
    record = dict(guards={}, child=[101, 1001], principal=[100, 1000], limit_bytes=1,
                  request=dict(resources={'memory_mib': 1}, owner='builder', purpose='City export'))
    assert broker._guard_health(record) is None
    assert record['state'] == 'uncertain'
    output = capsys.readouterr().err
    assert 'OSError' in output and 'builder' in output and 'City export' in output and '101' in output
    assert 'secret path' not in output
