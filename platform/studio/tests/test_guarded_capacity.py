"""Exercise the actual guarded launcher hook with small owned Python children."""
from contextlib import contextmanager
import os
import sys
from types import SimpleNamespace

import pytest

from atelier.safety import guarded


class Admission:
    def __init__(self, events, *, fail=None):
        self.events, self.fail = events, fail
        self.writer = None
        self.child = None
        self.final = None

    def offer(self):
        self.events.append('offer')
        if self.fail == 'offer':
            raise RuntimeError('broker unavailable')

    def gate(self):
        reader, self.writer = os.pipe()
        self.events.append('gate')
        return reader

    def start(self, **binding):
        self.events.append('grant')
        self.child = binding
        assert self.events.index('process-ready') < self.events.index('grant')
        assert self.events.index('tree-ready') < self.events.index('grant')
        if self.fail == 'grant':
            raise RuntimeError('broker restarted before GO')
        os.write(self.writer, b'1')
        os.close(self.writer)
        self.writer = None

    def check(self, *, descendants):
        self.events.append('heartbeat')
        if self.fail == 'heartbeat':
            raise RuntimeError('broker lost during run')

    def close(self, *, child=None, child_start=None, descendants=()):
        self.events.append('close')
        if self.writer is not None:
            os.close(self.writer)
            self.writer = None
        if child is not None:
            assert child.poll() is not None, 'capacity closed before child reap'
        self.final = (child, child_start, descendants)


@pytest.fixture
def guards(monkeypatch):
    events = []

    @contextmanager
    def locked(purpose, **kwargs):
        assert kwargs['exclusive_bridge'] is True
        assert kwargs['small_gib'] is None
        events.append('bridge')
        kwargs['on_slot']('big', 'test bridge')
        try:
            yield
        finally:
            events.append('unlock')

    @contextmanager
    def process_monitor(*args, **kwargs):
        events.append('process-attach')
        try:
            yield SimpleNamespace(pid=os.getpid(), poll=lambda: None)
        finally:
            events.append('process-detach')

    @contextmanager
    def tree_monitor(*args, **kwargs):
        events.append('tree-attach')
        try:
            yield SimpleNamespace(process=SimpleNamespace(pid=os.getpid()),
                                  ready=lambda: events.append('tree-ready'),
                                  check=lambda: events.append('tree-check'),
                                  finish=lambda: events.append('tree-finish'))
        finally:
            events.append('tree-detach')

    monkeypatch.setattr(guarded, 'render_lock', locked)
    monkeypatch.setattr(guarded, 'attach_memory_guard', process_monitor)
    monkeypatch.setattr(guarded, 'attach_tree', tree_monitor)
    monkeypatch.setattr(guarded, 'wait_ready', lambda *args: events.append('process-ready'))
    return events


def test_capacity_go_follows_guards_and_close_follows_reap(tmp_path, guards):
    session = Admission(guards)
    result = guarded.run([sys.executable, '-c', 'print("executed")'], tmp_path / 'guard',
                         admission=session, small_gib=1)
    assert result == 0
    assert 'executed' in (tmp_path / 'guard/stdout.log').read_text()
    assert guards.index('offer') < guards.index('bridge') < guards.index('gate')
    assert guards.index('close') < guards.index('tree-detach') < guards.index('unlock')
    assert guards.count('close') == 1
    assert session.child['limit_bytes'] == 10 * 1024**3
    assert session.final[0].returncode == 0


@pytest.mark.parametrize('performance', [False, True])
def test_configured_guarded_launch_forwards_performance_before_admission(tmp_path, guards, monkeypatch, performance):
    from atelier import capacity_runtime
    requested = []
    session = Admission(guards)

    def configured(**options):
        requested.append(options)
        return session

    monkeypatch.setattr(capacity_runtime, 'configured_session', configured)
    assert guarded.run([sys.executable, '-c', 'pass'], tmp_path / 'guard', performance=performance) == 0
    assert len(requested) == 1 and requested[0]['performance'] is performance
    assert guards.count('offer') == guards.count('bridge') == guards.count('close') == 1


def test_explicit_session_cannot_silently_ignore_performance_window(tmp_path, guards):
    with pytest.raises(ValueError, match='must request performance exclusion'):
        guarded.run([sys.executable, '-c', 'pass'], tmp_path, admission=Admission(guards), performance=True)
    assert guards == []


def test_explicit_performance_session_uses_its_one_existing_admission(tmp_path, guards):
    session = Admission(guards)
    session.request = {'performance': True}
    assert guarded.run([sys.executable, '-c', 'pass'], tmp_path, admission=session, performance=True) == 0
    assert guards.count('offer') == guards.count('close') == 1


@pytest.mark.parametrize('failure', ['offer', 'grant', 'heartbeat'])
def test_capacity_failure_does_not_fall_back_and_owned_child_is_reaped(tmp_path, guards, failure):
    session = Admission(guards, fail=failure)
    marker = tmp_path / 'executed'
    code = f'from pathlib import Path; import time; Path({str(marker)!r}).touch(); time.sleep(30)'
    with pytest.raises(RuntimeError, match='broker'):
        guarded.run([sys.executable, '-c', code], tmp_path / 'guard', admission=session)
    assert guards.count('close') == 1
    if failure == 'offer':
        assert 'bridge' not in guards
    if failure in ('offer', 'grant'):
        assert not marker.exists()
    if session.final[0] is not None:
        assert session.final[0].returncode is not None
        assert guards.index('close') < guards.index('process-detach') < guards.index('unlock')


def test_lock_refusal_cancels_unallocated_offer(tmp_path, guards, monkeypatch):
    @contextmanager
    def refused(*args, **kwargs):
        raise RuntimeError('legacy lane occupied')
        yield
    monkeypatch.setattr(guarded, 'render_lock', refused)
    session = Admission(guards)
    with pytest.raises(RuntimeError, match='lane occupied'):
        guarded.run([sys.executable, '-c', 'pass'], tmp_path / 'guard', admission=session)
    assert guards == ['offer', 'close']
    assert session.final == (None, None, ())


def test_missing_launcher_identity_refuses_before_tree_or_guards(tmp_path, guards, monkeypatch):
    monkeypatch.setattr(guarded.process_tree, 'started', lambda pid: None)
    monkeypatch.setattr(guarded, 'Descendants', lambda *args: pytest.fail('an unpinned tree was constructed'))
    session = Admission(guards)
    marker = tmp_path / 'executed'
    with pytest.raises(RuntimeError, match='could not pin'):
        guarded.run([sys.executable, '-c', f'open({str(marker)!r},"w").write("ran")'],
                    tmp_path / 'guard', admission=session)
    assert not marker.exists()
    assert session.final[0].returncode is not None
    assert 'process-attach' not in guards and 'grant' not in guards


@pytest.mark.parametrize('failed_guard', ['process', 'tree'])
def test_guard_readiness_failure_never_executes_and_closes_before_detach(tmp_path, guards, monkeypatch, failed_guard):
    def refuse(*args):
        raise RuntimeError('guard readiness failed')

    if failed_guard == 'process':
        monkeypatch.setattr(guarded, 'wait_ready', refuse)
    else:
        original = guarded.attach_tree

        @contextmanager
        def unready(*args, **kwargs):
            with original(*args, **kwargs) as monitor:
                monitor.ready = refuse
                yield monitor
        monkeypatch.setattr(guarded, 'attach_tree', unready)
    session = Admission(guards)
    marker = tmp_path / 'executed'
    with pytest.raises(RuntimeError, match='guard readiness'):
        guarded.run([sys.executable, '-c', f'open({str(marker)!r},"w").write("ran")'],
                    tmp_path / 'guard', admission=session)
    assert not marker.exists() and 'grant' not in guards
    assert session.final[0].returncode is not None
    assert guards.index('close') < guards.index('tree-detach') < guards.index('unlock')


def test_uncertain_release_fails_successful_command_and_still_unwinds(tmp_path, guards):
    session = Admission(guards)
    close = session.close

    def uncertain(**kwargs):
        close(**kwargs)
        raise RuntimeError('capacity release uncertain')
    session.close = uncertain
    with pytest.raises(RuntimeError, match='release uncertain'):
        guarded.run([sys.executable, '-c', 'pass'], tmp_path / 'guard', admission=session)
    assert session.final[0].returncode == 0
    assert guards.count('close') == 1
    assert guards.index('close') < guards.index('tree-detach') < guards.index('unlock')


@pytest.mark.parametrize('options', [dict(lock=False), dict(fitting_gib=1)])
def test_capacity_hook_cannot_bypass_legacy_bridge(tmp_path, options):
    with pytest.raises(ValueError, match='legacy bridge'):
        guarded.run([sys.executable, '-c', 'pass'], tmp_path, admission=object(), **options)
