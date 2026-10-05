"""Real local sockets exercise native Claude framing and delivery failure handling."""
import json
import os
import socket
import threading
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest

from atelier import board_claude as transport


@contextmanager
def inbox(tmp_path, monkeypatch, status=None, freeze=False):
    temporary = tempfile.TemporaryDirectory(prefix='atelier-inbox-', dir='/tmp')
    directory = Path(temporary.name)  # macOS Unix sockets have a short pathname limit.
    path = directory / 'worker.sock'
    registry = tmp_path / 'registry'
    registry.mkdir()
    session = tmp_path / 'conversation'
    session.mkdir()
    record = {'cwd': str(session), 'pid': os.getpid(), 'procStart': transport.process_start(os.getpid()),
              'sessionId': 'existing-conversation', 'messagingSocketPath': str(path)}
    (registry / f'{os.getpid()}.json').write_text(json.dumps(record))
    key = registry / f'{os.getpid()}.test.key'
    key.write_text(json.dumps({'peerToken': 'fixture-only-key', 'procStart': record['procStart']}))
    key.chmod(0o600)
    frames, failures = [], []
    release = threading.Event()
    with socket.socket(socket.AF_UNIX) as server:
        server.bind(str(path)); server.listen(1)

        def receive():
            try:
                connection, _ = server.accept()
                with connection:
                    stream = connection.makefile('rb')
                    frames.append(json.loads(stream.readline()))
                    frames.append(json.loads(stream.readline()))
                    stream.close()
                    if freeze:
                        release.wait(2)
                if status:
                    reply = frames[-1]['from'].removeprefix('uds:')
                    with socket.socket(socket.AF_UNIX) as client:
                        client.connect(reply)
                        client.sendall((json.dumps({'type': 'control', 'action': 'peer_message_status',
                            'orig_msg_id': frames[-1]['msg_id'], 'status': status})+'\n').encode())
                        release.wait(.15)  # Native macOS sender keeps ancestry evidence alive briefly.
            except Exception as error:
                failures.append(error)

        thread = threading.Thread(target=receive, daemon=True)
        thread.start()
        try:
            yield session, registry, frames, record, key
        finally:
            release.set(); thread.join(timeout=3)
    assert not failures
    temporary.cleanup()


def test_authenticated_frame_reaches_existing_session_and_cleans_only_own_reply(tmp_path, monkeypatch):
    with inbox(tmp_path, monkeypatch) as (session, registry, frames, record, key):
        assert 'acknowledgement is pending' in transport.notify(session, '**Board request**', 'bypass', registry)
        assert frames[0] == {'type': 'auth', 'token': 'fixture-only-key'}
        assert frames[1]['session_id'] == 'existing-conversation'
        assert 'from-mode="bypass"' in frames[1]['message']['content']
        assert '**Board request**' in frames[1]['message']['content']
        assert record['sessionId'] == 'existing-conversation'
        assert not Path(frames[1]['from'].removeprefix('uds:')).exists()
        assert key.exists()


@pytest.mark.parametrize('status', ['held', 'refused', 'dropped'])
def test_negative_receipts_fail_instead_of_claiming_delivery(tmp_path, monkeypatch, status):
    with inbox(tmp_path, monkeypatch, status=status) as (session, registry, *_):
        with pytest.raises(transport.TransportError, match=status):
            transport.notify(session, 'request', registry=registry)


def test_frozen_event_loop_times_out(tmp_path, monkeypatch):
    with inbox(tmp_path, monkeypatch, freeze=True) as (session, registry, *_):
        with pytest.raises(TimeoutError):
            transport.notify(session, 'request', registry=registry, timeout=.2)


def test_recycled_pid_is_rejected_before_connecting(tmp_path, monkeypatch):
    registry = tmp_path / 'registry'; registry.mkdir()
    (registry / '123.json').write_text(json.dumps({'cwd': str(tmp_path), 'pid': 123, 'procStart': 'old'}))
    monkeypatch.setattr(transport, 'process_start', lambda pid: 'new')
    with pytest.raises(transport.TransportError, match='exactly one'):
        transport.resolve(tmp_path, registry)
