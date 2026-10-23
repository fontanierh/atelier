"""Opt-in checkout custody in the aggregate tree monitor: exclusion survives uncertainty.

Real BSD flock descriptors and disposable processes only. A conflicting installer is a separate
open file description asking for LOCK_EX. No test kills a process that owns real admission.
"""
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from atelier.harness.safety import tree_guard

darwin = pytest.mark.skipif(sys.platform != 'darwin', reason='the tree monitor samples macOS processes')


def lock(path):
    """A locked open file description and the custodian's same-description duplicate."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return fd, fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, 3)


def refused(path):
    fd = os.open(path, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return False
    except BlockingIOError:
        return True
    finally:
        os.close(fd)


def acquired_within(path, seconds=10.):
    """Block on the installer's lock in a thread; a bounded handshake, not a sleep."""
    done = threading.Event()
    fd = os.open(path, os.O_RDWR)

    def take():
        fcntl.flock(fd, fcntl.LOCK_EX)
        done.set()
    threading.Thread(target=take, daemon=True).start()
    ok = done.wait(seconds)
    if ok:
        os.close(fd)
    return ok


def fake_tree(samples):
    return SimpleNamespace(root=(1, 10), same=lambda pin: True, reporters=None, sample=samples)


def custody_of(fd):
    return tree_guard.custody_descriptors([fd])


def test_descriptors_are_validated_before_any_release(tmp_path):
    original, duplicate = lock(tmp_path / 'checkout.lock')
    read, write = os.pipe()
    closed = os.dup(duplicate)
    os.close(closed)
    for bad in ([True], [1], [duplicate, duplicate], [read], [closed]):
        with pytest.raises((ValueError, OSError)):
            tree_guard.custody_descriptors(bad)
    found = tree_guard.custody_descriptors([duplicate])
    info = os.fstat(original)
    assert found == [(duplicate, (info.st_dev, info.st_ino))]
    for fd in (original, duplicate, read, write):
        os.close(fd)


def test_monitor_cli_rejects_invalid_custody_before_readiness(tmp_path):
    report = tmp_path / 'tree.json'
    for extra in (['--custody-fd', '1'], ['--custody-fd', '7', '--custody-fd', '7']):
        result = subprocess.run([sys.executable, '-m', 'atelier.harness.safety.tree_guard', '--child',
                                 '--pid', str(os.getpid()), '--expected-start', '1', '--report', str(report),
                                 *extra], capture_output=True, text=True, timeout=30)
        assert result.returncode == 2 and 'custody' in result.stderr
        assert not report.exists(), 'no readiness receipt, so no worker can be released'


def test_default_monitor_behaviour_is_unchanged(tmp_path, monkeypatch):
    samples = iter(([], []))
    monkeypatch.setattr(tree_guard, 'OwnedTree', lambda *args: fake_tree(lambda: next(samples)))
    monkeypatch.setattr(tree_guard, 'drain_owned', lambda tree, **kw: False)
    before = signal.getsignal(signal.SIGTERM)
    path = tmp_path / 'tree.json'
    assert tree_guard.run_child(1, 10, path) == 1
    value = json.loads(path.read_text())
    assert value['state'] == 'cleanup_incomplete' and 'custody' not in value
    assert 'monitor' not in value, 'monitors without custody publish no identity'
    assert signal.getsignal(signal.SIGTERM) is before


def test_uncertainty_keeps_exclusion_until_cleanup_is_verified(tmp_path, monkeypatch):
    lock_path = tmp_path / 'checkout.lock'
    original, duplicate = lock(lock_path)
    os.close(original)  # the launcher's own descriptor is gone; only the custodian's remains
    # Main loop: the root has exited but cleanup is unverified. Then the continuation meets
    # telemetry and cleanup exceptions, an unverified drain, and finally a verified one.
    drains = iter([False, RuntimeError('lost'), OSError('telemetry'), False, True])
    samples = iter([[], [], OSError('sample'), [], []])

    def next_or_raise(values):
        value = next(values)
        if isinstance(value, BaseException):
            raise value
        return value
    tree = fake_tree(lambda: next_or_raise(samples))
    monkeypatch.setattr(tree_guard, 'OwnedTree', lambda *args: tree)
    monkeypatch.setattr(tree_guard, 'drain_owned', lambda candidate, **kw: next_or_raise(drains))
    writes = []
    original_write = tree_guard.write_report

    def flaky_write(path, value):
        writes.append(json.loads(json.dumps(value)))
        if 2 <= len(writes) <= 3:
            raise OSError('receipt unwritable')  # never a reason to release
        original_write(path, value)
    monkeypatch.setattr(tree_guard, 'write_report', flaky_write)
    pauses = []

    def pause(seconds):
        assert refused(lock_path), 'exclusion must hold while cleanup is unverified'
        pauses.append(seconds)
    monkeypatch.setattr(tree_guard, '_custody_pause', pause)
    path = tmp_path / 'tree.json'
    code = tree_guard.run_child(1, 10, path, custody=custody_of(duplicate))
    assert code == 1, 'late cleanup never turns a failed job into success'
    assert pauses and all(seconds > 0 for seconds in pauses), 'a bounded cadence, not a busy loop'
    value = json.loads(path.read_text())
    assert value['state'] == 'cleanup_incomplete' and value['termination_reason'] == 'child_exited'
    assert value['cleanup_complete'] is False and value['late_cleanup_complete'] is True
    assert value['custody']['held'] is False and value['custody']['released'] == 'late_cleanup_complete'
    assert any(w.get('custody', {}).get('held') is True for w in writes)
    with pytest.raises(OSError):
        os.fstat(duplicate)
    assert not refused(lock_path)


def test_monitor_error_holds_custody_instead_of_unwinding(tmp_path, monkeypatch):
    lock_path = tmp_path / 'checkout.lock'
    original, duplicate = lock(lock_path)
    os.close(original)
    calls = iter([KeyError('broken sample'), [], []])

    def sample():
        value = next(calls)
        if isinstance(value, BaseException):
            raise value
        return value
    monkeypatch.setattr(tree_guard, 'OwnedTree', lambda *args: fake_tree(sample))
    drains = iter([False, True])
    monkeypatch.setattr(tree_guard, 'drain_owned', lambda candidate, **kw: next(drains))
    monkeypatch.setattr(tree_guard, '_custody_pause', lambda seconds: None)
    path = tmp_path / 'tree.json'
    assert tree_guard.run_child(1, 10, path, custody=custody_of(duplicate)) == 1
    value = json.loads(path.read_text())
    assert value['termination_reason'] == 'monitor_error' and value['late_cleanup_complete'] is True
    assert not refused(lock_path)


def recorded_writes(monkeypatch):
    writes = []
    original_write = tree_guard.write_report

    def record(path, value):
        writes.append(json.loads(json.dumps(value)))
        original_write(path, value)
    monkeypatch.setattr(tree_guard, 'write_report', record)
    return writes


def identities(monkeypatch, *values):
    """The monitor's own identity as process_tree reports it, call by call (the last repeats)."""
    calls = []

    def identity():
        calls.append(1)
        return list(values[min(len(calls), len(values)) - 1])
    monkeypatch.setattr(tree_guard, '_monitor_identity', identity)
    return calls


def test_a_custody_monitor_pins_its_identity_once_and_publishes_it_on_every_receipt(tmp_path, monkeypatch):
    lock_path = tmp_path / 'checkout.lock'
    original, duplicate = lock(lock_path)
    os.close(original)
    root = dict(pid=1, started=10, footprint_bytes=1)
    # Running twice, then the root exits with cleanup unverified: the continuation holds custody
    # and releases it late. A later lookup of the identity would differ; it is never used.
    samples = iter([[root], [root], [], [], [], []])
    monkeypatch.setattr(tree_guard, 'OwnedTree', lambda *args: fake_tree(lambda: next(samples)))
    monkeypatch.setattr(tree_guard, 'drain_owned', scripted(iter([False, False, True])))
    monkeypatch.setattr(tree_guard.time, 'sleep', lambda seconds: None)
    monkeypatch.setattr(tree_guard, '_custody_pause', lambda seconds: None)
    calls = identities(monkeypatch, [os.getpid(), 4242], [os.getpid(), 5353])
    writes = recorded_writes(monkeypatch)
    assert tree_guard.run_child(1, 10, tmp_path / 'tree.json', custody=custody_of(duplicate)) == 1
    assert len(calls) == 1, 'pinned once'
    assert [w['state'] for w in writes[:2]] == ['running', 'running']
    assert writes[0]['monitor'] == [os.getpid(), 4242], 'in the first readiness receipt'
    assert all(w['monitor'] == [os.getpid(), 4242] for w in writes), 'identical on every receipt'
    custody = [w['custody'] for w in writes if 'custody' in w]
    assert any(c['held'] for c in custody) and custody[-1]['released'] == 'late_cleanup_complete'
    assert all(c['monitor'] == [os.getpid(), 4242] for c in custody if 'monitor' in c)
    assert writes[-1]['late_cleanup_complete'] is True
    assert not refused(lock_path)


def test_the_exception_fallback_keeps_the_pinned_identity(tmp_path, monkeypatch):
    lock_path = tmp_path / 'checkout.lock'
    original, duplicate = lock(lock_path)
    os.close(original)
    monkeypatch.setattr(tree_guard, 'OwnedTree',
                        lambda *args: fake_tree(scripted(iter([KeyError('broken sample'), [], []]))))
    monkeypatch.setattr(tree_guard, 'drain_owned', scripted(iter([False, True])))
    monkeypatch.setattr(tree_guard, '_custody_pause', lambda seconds: None)
    identities(monkeypatch, [os.getpid(), 4242], [os.getpid(), 5353])
    writes = recorded_writes(monkeypatch)
    assert tree_guard.run_child(1, 10, tmp_path / 'tree.json', custody=custody_of(duplicate)) == 1
    assert writes and all(w['termination_reason'] == 'monitor_error' for w in writes)
    assert all(w['monitor'] == [os.getpid(), 4242] == w['custody']['monitor'] for w in writes)
    assert not refused(lock_path)


@pytest.mark.parametrize('identity', [[None, None], [0, 4242], [True, 4242], [1, 4242], [-1, 4242]])
def test_an_unpinnable_monitor_is_never_ready_and_keeps_custody(tmp_path, monkeypatch, identity):
    lock_path = tmp_path / 'checkout.lock'
    original, duplicate = lock(lock_path)
    os.close(original)
    if identity[0] is None:
        identity = [os.getpid(), None]
    elif identity[0] == 1:
        identity = [os.getpid(), True]
    elif identity[0] == -1:
        identity = [os.getpid() + 1, 4242]  # not this process
    identities(monkeypatch, identity)
    root = dict(pid=1, started=10, footprint_bytes=1)
    monkeypatch.setattr(tree_guard, 'OwnedTree', lambda *args: fake_tree(scripted(iter([[root], [], []]))))
    monkeypatch.setattr(tree_guard, 'drain_owned', scripted(iter([False, True])))
    pauses = []
    monkeypatch.setattr(tree_guard, '_custody_pause', holding_pause(lock_path, pauses))
    writes = recorded_writes(monkeypatch)
    assert tree_guard.run_child(1, 10, tmp_path / 'tree.json', custody=custody_of(duplicate)) == 1
    assert pauses, 'custody was held until cleanup was verified'
    assert not any(w['state'] == 'running' for w in writes), 'no readiness receipt'
    assert not any('monitor' in w for w in writes), 'no usable identity is published'
    assert writes[-1]['termination_reason'] == 'monitor_error'
    assert not refused(lock_path)


def test_complete_cleanup_releases_immediately_with_its_receipt(tmp_path, monkeypatch):
    lock_path = tmp_path / 'checkout.lock'
    original, duplicate = lock(lock_path)
    os.close(original)
    samples = iter(([], []))
    monkeypatch.setattr(tree_guard, 'OwnedTree', lambda *args: fake_tree(lambda: next(samples)))
    monkeypatch.setattr(tree_guard, 'drain_owned', lambda candidate, **kw: True)
    path = tmp_path / 'tree.json'
    assert tree_guard.run_child(1, 10, path, custody=custody_of(duplicate)) == 0
    value = json.loads(path.read_text())
    info = os.stat(lock_path)
    assert value['state'] == 'child_exited' and value['custody'] == dict(
        held=False, released='cleanup_complete', lock_files=[[info.st_dev, info.st_ino]])
    assert not refused(lock_path)


class Unprintable(Exception):
    def __repr__(self):
        raise RuntimeError('repr failed')

    __str__ = __repr__


class FullStream:
    """A stderr whose every write fails, like a full or revoked log."""
    def write(self, text):
        raise OSError('log full')

    def flush(self):
        raise OSError('log full')


def failing_outputs(monkeypatch, attempts):
    def full_report(path, value):
        attempts.append(json.loads(json.dumps(value, default=repr)))
        raise OSError('receipt full')
    monkeypatch.setattr(tree_guard, 'write_report', full_report)
    monkeypatch.setattr(tree_guard.sys, 'stderr', FullStream())


def scripted(values):
    def step(*args, **kwargs):
        value = next(values)
        if isinstance(value, BaseException):
            raise value
        return value
    return step


def holding_pause(lock_path, pauses):
    def pause(seconds):
        assert refused(lock_path), 'exclusion must hold while cleanup is unverified'
        pauses.append(seconds)
    return pause


def test_failed_reports_logs_and_reprs_never_end_the_hold(tmp_path, monkeypatch):
    """front-man's repro: both the receipt and the log fail while cleanup is unknown."""
    lock_path = tmp_path / 'checkout.lock'
    original, duplicate = lock(lock_path)
    os.close(original)
    attempts, pauses = [], []
    failing_outputs(monkeypatch, attempts)
    monkeypatch.setattr(tree_guard, 'drain_owned', scripted(iter([Unprintable(), False, OSError('x'), True])))
    monkeypatch.setattr(tree_guard, '_custody_pause', holding_pause(lock_path, pauses))
    tree = fake_tree(scripted(iter([[], []])))
    value = dict(state='cleanup_incomplete', termination_reason='memory_limit', cleanup_complete=False,
                 unserialisable={1, 2})
    assert tree_guard.keep_custody(tree, tmp_path / 'tree.json', value, custody_of(duplicate), 1) == 1
    assert len(pauses) == 3 and attempts, 'it kept retrying and kept trying to publish'
    assert value['state'] == 'cleanup_incomplete' and value['termination_reason'] == 'memory_limit'
    assert value['cleanup_complete'] is False and value['late_cleanup_complete'] is True
    assert value['custody']['released'] == 'late_cleanup_complete'
    assert '<unprintable Unprintable>' in [a['custody'].get('last_error') for a in attempts]
    with pytest.raises(OSError):
        os.fstat(duplicate)
    assert not refused(lock_path)


def test_monitor_error_with_failed_outputs_still_holds_until_verified(tmp_path, monkeypatch):
    """The same failures through run_child's exception fallback, with an unprintable error."""
    lock_path = tmp_path / 'checkout.lock'
    original, duplicate = lock(lock_path)
    os.close(original)
    attempts, pauses = [], []
    failing_outputs(monkeypatch, attempts)

    def same(pin):
        raise Unprintable()
    tree = SimpleNamespace(root=(1, 10), same=same, reporters=None, sample=scripted(iter([[], [{'pid': 2}], []])))
    monkeypatch.setattr(tree_guard, 'OwnedTree', lambda *args: tree)
    monkeypatch.setattr(tree_guard, 'drain_owned', scripted(iter([False, False, True])))
    monkeypatch.setattr(tree_guard, '_custody_pause', holding_pause(lock_path, pauses))
    assert tree_guard.run_child(1, 10, tmp_path / 'tree.json', custody=custody_of(duplicate)) == 1
    assert len(pauses) == 2
    final = attempts[-1]
    assert final['state'] == 'cleanup_incomplete' and final['termination_reason'] == 'monitor_error'
    assert final['error'] == '<unprintable Unprintable>' and final['cleanup_complete'] is False
    assert final['late_cleanup_complete'] is True and final['custody']['released'] == 'late_cleanup_complete'
    assert not refused(lock_path)


def test_hold_backs_off_throttles_unchanged_refreshes_and_publishes_changes_at_once(tmp_path, monkeypatch):
    lock_path = tmp_path / 'checkout.lock'
    original, duplicate = lock(lock_path)
    os.close(original)
    stuck = [dict(pid=2, started=20, footprint_bytes=1)]
    moved = [dict(pid=2, started=20, footprint_bytes=999)]  # a footprint change alone is not a state change
    other = [dict(pid=3, started=30, footprint_bytes=1)]
    samples = [stuck] * 3 + [moved] * 3 + [other] * 3 + [[]]
    monkeypatch.setattr(tree_guard, 'drain_owned', scripted(iter([False] * 9 + [True])))
    tree = fake_tree(scripted(iter(samples)))
    writes, pauses = [], []
    original_write = tree_guard.write_report

    def counted(path, value):
        writes.append(json.loads(json.dumps(value)))
        original_write(path, value)
    monkeypatch.setattr(tree_guard, 'write_report', counted)
    monkeypatch.setattr(tree_guard, '_custody_pause', holding_pause(lock_path, pauses))
    value = dict(state='cleanup_incomplete', termination_reason='child_exited', cleanup_complete=False)
    assert tree_guard.keep_custody(tree, tmp_path / 'tree.json', value, custody_of(duplicate), 1) == 1
    assert pauses == [.25, .5, 1., 2., 4., 5., .25, .5, 1.], 'backoff to 5 s, reset on a real change'
    held = [w['custody'] for w in writes if w['custody']['held']]
    # the initial hold, the first observation, then only the change to another process
    assert [h['remaining'][0]['pid'] if h['remaining'] else None for h in held] == [None, 2, 3]
    assert writes[-1]['custody']['released'] == 'late_cleanup_complete'
    assert not refused(lock_path)


def test_an_unchanged_hold_still_refreshes_its_receipt_on_the_throttle(tmp_path, monkeypatch):
    lock_path = tmp_path / 'checkout.lock'
    original, duplicate = lock(lock_path)
    os.close(original)
    clock = [1000.]
    monkeypatch.setattr(tree_guard.time, 'monotonic', lambda: clock[0])
    stuck = [dict(pid=2, started=20, footprint_bytes=1)]
    monkeypatch.setattr(tree_guard, 'drain_owned', scripted(iter([False] * 4 + [True])))
    tree = fake_tree(scripted(iter([stuck] * 4 + [[]])))
    writes = []
    original_write = tree_guard.write_report
    monkeypatch.setattr(tree_guard, 'write_report', lambda path, value: (writes.append(1), original_write(path, value)))

    def pause(seconds):
        clock[0] += 8.  # two unchanged pauses reach the refresh interval
    monkeypatch.setattr(tree_guard, '_custody_pause', pause)
    value = dict(state='cleanup_incomplete', termination_reason='child_exited', cleanup_complete=False)
    tree_guard.keep_custody(tree, tmp_path / 'tree.json', value, custody_of(duplicate), 1)
    # initial, first observation, one throttled refresh after 16 s unchanged, then the release
    assert len(writes) == 4
    assert not refused(lock_path)


def test_term_and_hup_while_holding_never_end_the_custodian(tmp_path):
    lock_path = tmp_path / 'checkout.lock'
    original, duplicate = lock(lock_path)
    acks_read, acks_write = os.pipe()
    flag = tmp_path / 'recovered'
    pid = os.fork()
    if pid == 0:  # disposable custodian, no admission
        try:
            os.close(original)
            os.close(acks_read)
            tree_guard.OwnedTree = lambda *args: fake_tree(lambda: [])
            tree_guard.drain_owned = lambda candidate, **kw: flag.exists()

            def pause(seconds):
                os.write(acks_write, b'.')
                import time
                time.sleep(.02)
            tree_guard._custody_pause = pause
            os._exit(tree_guard.run_child(1, 10, tmp_path / 'tree.json', custody=custody_of(duplicate)))
        except BaseException:
            os._exit(99)
    os.close(duplicate)
    os.close(acks_write)
    os.close(original)  # every descriptor outside the custodian is closed
    assert os.read(acks_read, 1) == b'.'
    os.kill(pid, signal.SIGTERM)
    os.kill(pid, signal.SIGHUP)
    assert os.read(acks_read, 1) == b'.' and os.read(acks_read, 1) == b'.'
    assert os.waitpid(pid, os.WNOHANG) == (0, 0), 'the custodian survived TERM and HUP'
    assert refused(lock_path)
    flag.write_text('cleanup verified\n')
    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 1
    value = json.loads((tmp_path / 'tree.json').read_text())
    assert value['late_cleanup_complete'] is True and value['custody']['released'] == 'late_cleanup_complete'
    assert acquired_within(lock_path)


class FakeProcess:
    def __init__(self, *args, **kwargs):
        self.args, self.kwargs, self.pid, self.ended = args, kwargs, 4242, []
        FakeProcess.last = self

    def wait(self, timeout=None):
        if self.ended:
            return -signal.SIGTERM
        raise subprocess.TimeoutExpired('monitor', timeout)

    def poll(self):
        return None

    def terminate(self):
        self.ended.append('terminate')

    def kill(self):
        self.ended.append('kill')


def attach(monkeypatch, tmp_path, custody_fds):
    from atelier.harness.safety import guard, process_tree
    monkeypatch.setattr(process_tree, 'started', lambda pid: 777)
    monkeypatch.setattr(guard.subprocess, 'Popen', FakeProcess)
    with pytest.raises(RuntimeError, match='readiness failed'):
        with guard.attach_tree(123, tmp_path / 'tree.json', None, custody_fds=custody_fds):
            raise RuntimeError('readiness failed')  # the error still propagates
    return FakeProcess.last


def test_attach_tree_detaches_a_custodian_and_still_ends_default_monitors(tmp_path, monkeypatch, capsys):
    original, duplicate = lock(tmp_path / 'checkout.lock')
    held = attach(monkeypatch, tmp_path, [duplicate])
    assert held.ended == [], 'a possibly holding custodian is never terminated or killed'
    assert held.kwargs['pass_fds'] == (duplicate,) and held.args[0].count('--custody-fd') == 1
    assert 'custody monitor retained: pid 4242 start 777' in capsys.readouterr().out
    plain = attach(monkeypatch, tmp_path, ())
    assert plain.ended[:1] == ['terminate'] and 'pass_fds' not in plain.kwargs
    assert os.fstat(duplicate), 'attach_tree never closes the caller descriptor'
    os.close(original)
    os.close(duplicate)


def test_attach_tree_refuses_invalid_custody_before_starting_a_monitor(tmp_path, monkeypatch):
    from atelier.harness.safety import guard
    monkeypatch.setattr(guard.subprocess, 'Popen', lambda *a, **k: pytest.fail('no monitor may start'))
    with pytest.raises(ValueError):
        with guard.attach_tree(123, tmp_path / 'tree.json', None, custody_fds=[True]):
            pass


def test_guarded_refuses_custody_for_the_child_before_any_session(tmp_path, monkeypatch):
    from atelier.harness.safety import guarded
    import atelier.harness.capacity_runtime as runtime
    monkeypatch.setattr(runtime, 'configured_session', lambda **kw: pytest.fail('no admission session'))
    original, duplicate = lock(tmp_path / 'checkout.lock')
    with pytest.raises(ValueError, match='never reach the guarded child'):
        guarded.run(['true'], tmp_path / 'report', pass_fds=(duplicate,), custody_fds=(duplicate,))
    with pytest.raises(ValueError):
        guarded.run(['true'], tmp_path / 'report2', custody_fds=(1,))
    os.close(original)
    os.close(duplicate)


READER = 'import sys; sys.stdin.buffer.read()'


@darwin
def test_real_monitor_keeps_exclusion_after_the_launcher_closes_until_the_reader_exits(tmp_path):
    from atelier.harness.safety import guard
    lock_path = tmp_path / 'checkout.lock'
    original, duplicate = lock(lock_path)
    reader = subprocess.Popen([sys.executable, '-c', READER], stdin=subprocess.PIPE)
    report = tmp_path / 'tree.json'
    with guard.attach_tree(reader.pid, report, None, custody_fds=[duplicate]) as monitor:
        monitor.ready()
        from atelier.harness.safety import process_tree
        pinned = [monitor.process.pid, process_tree.started(monitor.process.pid)]
        assert json.loads(report.read_text())['monitor'] == pinned, 'the real monitor, from its first receipt'
        os.close(original)
        os.close(duplicate)  # the launcher holds nothing now; the reader is still alive
        assert refused(lock_path)
        reader.stdin.close()
        reader.wait(timeout=10)
    assert acquired_within(lock_path)
    value = json.loads(report.read_text())
    assert value['state'] == 'child_exited' and value['cleanup_complete'] is True
    assert value['custody']['released'] == 'cleanup_complete'
    assert value['monitor'] == pinned


CONTROLLER = r'''
import fcntl, os, subprocess, sys
from atelier.harness.safety import guard
fd = os.open(sys.argv[1], os.O_RDWR)
fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
reader = subprocess.Popen([sys.executable, '-c', 'import sys; sys.stdin.buffer.read()'], stdin=subprocess.PIPE)
with guard.attach_tree(reader.pid, sys.argv[2], None, custody_fds=[fd]) as monitor:
    monitor.ready()
    print('ready', flush=True)
    sys.stdin.read()
'''


@darwin
def test_custody_survives_a_killed_disposable_controller_until_the_drain_confirms(tmp_path):
    lock_path = tmp_path / 'checkout.lock'
    lock_path.write_text('')
    report = tmp_path / 'tree.json'
    controller = subprocess.Popen([sys.executable, '-c', CONTROLLER, str(lock_path), str(report)],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    assert controller.stdout.readline().strip() == 'ready'
    assert refused(lock_path)
    controller.kill()  # disposable stand-in with fake admission; its own fd closes now
    controller.wait(timeout=10)
    assert acquired_within(lock_path)
    value = json.loads(report.read_text())
    # The lock became available only after the custodian's drain confirmed cleanup.
    assert value['state'] == 'controller_exited' and value['cleanup_complete'] is True
    assert value['custody']['held'] is False
