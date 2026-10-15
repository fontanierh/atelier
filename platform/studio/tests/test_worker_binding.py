"""Legacy worker lifecycle checks; no native commands or machine lock paths."""
import errno
import fcntl
import json
import os
from pathlib import Path
import socket
import time

import pytest

from atelier import capacity_compat, capacity_protocol as wire, capacity_runtime
from atelier.safety import worker_binding as binding


@pytest.fixture(autouse=True)
def private_configuration(tmp_path, monkeypatch):
    monkeypatch.delenv('ATELIER_CAPACITY_CLIENT', raising=False)
    monkeypatch.setattr(capacity_runtime, 'DEFAULT_CONFIG', tmp_path / 'client.json')
    monkeypatch.setattr(capacity_compat, 'DEFAULT_RECORD', tmp_path / 'cutover.json')


@pytest.mark.parametrize('which', ['explicit', 'client', 'broken-client', 'preparing', 'sealed', 'active', 'malformed', 'broken-cutover', 'unreadable'])
def test_configured_and_cutover_modes_refuse_without_creating_paths(tmp_path, monkeypatch, which):
    if which == 'explicit':
        monkeypatch.setenv('ATELIER_CAPACITY_CLIENT', str(tmp_path / 'absent.json'))
    elif which == 'unreadable':
        original = Path.lstat
        def lstat(path, *args, **kwargs):
            if path == capacity_compat.DEFAULT_RECORD:
                raise PermissionError(errno.EACCES, 'fixture')
            return original(path, *args, **kwargs)
        monkeypatch.setattr(Path, 'lstat', lstat)
    else:
        path = capacity_runtime.DEFAULT_CONFIG if 'client' in which else capacity_compat.DEFAULT_RECORD
        if which.startswith('broken'):
            path.symlink_to(tmp_path / 'missing')
        else:
            path.write_text(json.dumps({'state': which}) if which != 'malformed' else '{')
    with pytest.raises(wire.CapacityError):
        binding.require_legacy()


@pytest.fixture
def locked(tmp_path, monkeypatch):
    path = tmp_path / 'render.lock'
    monkeypatch.setenv('ATELIER_RENDER_LOCK', str(path))
    owner = (os.getpid(), wire.process_start(os.getpid()))
    repo = str(tmp_path)
    holder = dict(pid=owner[0], started=owner[1], repo=repo, slot='big', kind='job', protocol=2)
    with path.open('w+') as stream:
        json.dump(holder, stream)
        stream.flush()
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        descriptor = os.dup(stream.fileno())
        try:
            yield stream, descriptor, path, binding._pin(os.fstat(descriptor)), holder, owner, repo
        finally:
            os.close(descriptor)
            fcntl.flock(stream, fcntl.LOCK_UN)


def test_transferred_description_is_close_only_and_keeps_parent_lock(locked, monkeypatch):
    stream, descriptor, path, pin, holder, owner, repo = locked
    original = fcntl.flock
    def flock(fd, flags):
        assert fd not in (descriptor, stream.fileno())
        return original(fd, flags)
    monkeypatch.setattr(fcntl, 'flock', flock)
    binding._held(descriptor, str(path), pin, holder, owner, repo)
    monkeypatch.setattr(fcntl, 'flock', original)
    os.set_inheritable(descriptor, False)
    assert not os.get_inheritable(descriptor)
    with path.open('r') as probe:
        with pytest.raises(BlockingIOError):
            original(probe.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)


@pytest.mark.parametrize('change', ['unlocked', 'replaced', 'holder'])
def test_lost_or_changed_lock_refuses(locked, change):
    stream, descriptor, path, pin, holder, owner, repo = locked
    if change == 'unlocked':
        fcntl.flock(stream, fcntl.LOCK_UN)
    elif change == 'replaced':
        path.unlink()
        path.write_text(json.dumps(holder))
    else:
        stream.seek(0)
        json.dump({**holder, 'pid': owner[0] + 1}, stream)
        stream.truncate()
        stream.flush()
    with pytest.raises(wire.CapacityError):
        binding._held(descriptor, str(path), pin, holder, owner, repo)


@pytest.mark.parametrize('change', ['nonce', 'digest', 'repo', 'parent', 'limit', 'stale', 'fields', 'dead'])
def test_invalid_bound_frame_closes_received_descriptor(tmp_path, monkeypatch, change):
    parent = [os.getppid(), wire.process_start(os.getppid())]
    value = dict(schema=1, nonce='a' * 32, request_sha256='b' * 64, repo=str(tmp_path),
                 owner=parent, child=[os.getpid(), wire.process_start(os.getpid())], guards={},
                 limit_bytes=1024**3, lock_path=str(tmp_path / 'lock'), lock_pin={}, holder={},
                 observed_monotonic=time.monotonic())
    if change == 'nonce':
        value['nonce'] = 'c' * 32
    elif change == 'digest':
        value['request_sha256'] = 'c' * 64
    elif change == 'repo':
        value['repo'] += '/other'
    elif change == 'parent':
        value['owner'] = [parent[0] + 1, parent[1]]
    elif change == 'limit':
        value['limit_bytes'] += 1
    elif change == 'stale':
        value['observed_monotonic'] -= 60
    elif change == 'fields':
        value['extra'] = True
    else:
        monkeypatch.setattr(wire, 'direct_child', lambda *_: False)
    source = os.open(tmp_path / 'descriptor', os.O_CREAT | os.O_RDWR, 0o600)
    received = os.dup(source)
    try:
        monkeypatch.setattr(wire, 'receive', lambda *args, **kwargs: (value, received))
        left, right = socket.socketpair()
        with left as channel, right:
            with pytest.raises(wire.CapacityError):
                binding.WorkerProof.receive(channel, nonce='a' * 32, request_sha256='b' * 64,
                                             parent=parent, repo=tmp_path, limit_bytes=1024**3)
        with pytest.raises(OSError):
            os.fstat(received)
    finally:
        os.close(source)


@pytest.mark.parametrize('loss', ['process-stale', 'tree-stale', 'monitor-exit', 'same-monitor', 'changed-child'])
def test_worker_checks_live_guard_facts_again_before_mutation(tmp_path, monkeypatch, loss):
    owner = (os.getppid(), wire.process_start(os.getppid()))
    child = (os.getpid(), wire.process_start(os.getpid()))
    process_report, tree_report = tmp_path / 'process.json', tmp_path / 'tree.json'
    process_report.write_text(json.dumps(dict(pid=child[0], process_start=child[1], time=time.time(),
                                              state='running', limit_bytes=1024**3)))
    tree_report.write_text(json.dumps(dict(owner=child[0], owner_started=child[1], observed_monotonic=time.monotonic(),
                                           state='running', limit_bytes=1024**3, processes=[], footprint_bytes=1)))
    guards = dict(process_guard=dict(pid=10001, start=1, report=str(process_report)),
                  tree_guard=dict(pid=10002, start=2, report=str(tree_report)))
    value = dict(owner=list(owner), child=list(child), guards=guards, limit_bytes=1024**3,
                 lock_path='unused', lock_pin={}, holder={}, repo=str(tmp_path))
    monkeypatch.setattr(wire, 'direct_child', lambda *_: True)
    # Use the real receipt parser with injected kernel observations only; no native monitor.
    original_validate = wire.validate_guards
    def validate(*args):
        return original_validate(*args, started=lambda pid: {10001: 1, 10002: 2}.get(pid),
                                 child_of=lambda *_: True,
                                 alive=lambda pin: not (loss == 'monitor-exit' and pin[0] == 10002))
    monkeypatch.setattr(wire, 'validate_guards', validate)
    monkeypatch.setattr(binding, '_held', lambda *_: None)
    proof = binding.WorkerProof(value, -1)
    if loss == 'process-stale':
        data = json.loads(process_report.read_text()); data['time'] -= 60
        process_report.write_text(json.dumps(data))
    elif loss == 'tree-stale':
        data = json.loads(tree_report.read_text()); data['observed_monotonic'] -= 60
        tree_report.write_text(json.dumps(data))
    elif loss == 'same-monitor':
        guards['tree_guard'] = guards['process_guard']
    elif loss == 'changed-child':
        value['child'][1] += 1
    with pytest.raises(wire.CapacityError):
        proof.check()


def test_transferred_lock_is_cloexec_and_closed_after_proof(tmp_path, monkeypatch):
    parent = [os.getppid(), wire.process_start(os.getppid())]
    value = dict(schema=1, nonce='a' * 32, request_sha256='b' * 64, repo=str(tmp_path),
                 owner=parent, child=[os.getpid(), wire.process_start(os.getpid())], guards={},
                 limit_bytes=1024**3, lock_path='unused', lock_pin={}, holder={}, observed_monotonic=time.monotonic())
    monkeypatch.setattr(binding.WorkerProof, 'check', lambda *_: None)
    with (tmp_path / 'lock').open('w+') as original:
        left, right = socket.socketpair()
        with left, right:
            wire.send(left, value, original.fileno())
            with binding.WorkerProof.receive(right, nonce='a' * 32, request_sha256='b' * 64,
                                             parent=parent, repo=tmp_path, limit_bytes=1024**3) as proof:
                received = proof.descriptor
                assert received != original.fileno() and not os.get_inheritable(received)
            with pytest.raises(OSError):
                os.fstat(received)
            assert os.fstat(original.fileno())


@pytest.mark.parametrize('frame', ['missing-fd', 'extra-fd', 'oversized'])
def test_private_binding_frame_is_bounded_and_closes_unexpected_fds(tmp_path, monkeypatch, frame):
    import array
    import threading
    parent = [os.getppid(), wire.process_start(os.getppid())]
    left, right = socket.socketpair()
    with left, right, (tmp_path / 'original').open('w+') as original:
        payload = wire.encode({'schema': 1}) if frame != 'oversized' else b'x' * (wire.MAX_FRAME + 1)
        ancillary = [] if frame != 'extra-fd' else [(socket.SOL_SOCKET, socket.SCM_RIGHTS,
                                                    array.array('i', [original.fileno(), original.fileno()]))]
        def send():
            left.settimeout(1.)
            try:
                sent = left.sendmsg([payload], ancillary)
                left.sendall(payload[sent:])
                left.shutdown(socket.SHUT_WR)
            except OSError:
                pass  # Oversized receiver may close before the bounded writer finishes.
        sender = threading.Thread(target=send, daemon=True)
        sender.start()
        closed = []
        close = os.close
        def record_close(fd):
            closed.append(fd)
            close(fd)
        with monkeypatch.context() as edits:
            edits.setattr(os, 'close', record_close)
            with pytest.raises(wire.CapacityError):
                binding.WorkerProof.receive(right, nonce='a' * 32, request_sha256='b' * 64,
                                             parent=parent, repo=tmp_path, limit_bytes=1024**3)
        sender.join(timeout=2)
        assert not sender.is_alive()
        if frame == 'extra-fd':
            assert len(closed) == 2
            for fd in closed:
                with pytest.raises(OSError):
                    os.fstat(fd)
        assert os.fstat(original.fileno())
