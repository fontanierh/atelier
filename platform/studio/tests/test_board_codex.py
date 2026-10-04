"""Active-turn routing and races must never degrade into an invisible queue."""
import json
import tempfile
import threading
from pathlib import Path

import pytest
from websockets.sync.server import unix_serve

from atelier import board_codex


class Fake:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def call(self, method, params):
        self.calls.append((method, params))
        reply = next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        return reply


ACTIVE = {'thread': {'status': {'type': 'active'}}}
IDLE = {'thread': {'status': {'type': 'idle'}}}
TURN = {'data': [{'id': 'turn-1', 'status': 'inProgress'}]}


def test_busy_codex_steers_current_turn_and_never_queues():
    fake = Fake([ACTIVE, TURN, {'turnId': 'turn-1'}])
    assert board_codex.notify(fake, 'existing', 'new handoff') == 'steered'
    assert [method for method, _ in fake.calls] == ['thread/read', 'thread/turns/list', 'turn/steer']
    steer = fake.calls[-1][1]
    assert steer['expectedTurnId'] == 'turn-1'
    assert steer['input'][0]['text'] == 'new handoff'
    assert set(steer) == {'threadId', 'expectedTurnId', 'input', 'clientUserMessageId'}
    retry = Fake([ACTIVE, TURN, {'turnId': 'turn-1'}])
    board_codex.notify(retry, 'existing', 'new handoff')
    assert retry.calls[-1][1]['clientUserMessageId'] == steer['clientUserMessageId']


def test_idle_session_wakes_in_same_thread_without_settings_override():
    fake = Fake([IDLE, {}])
    assert board_codex.notify(fake, 'existing', 'handoff') == 'woke_idle'
    assert fake.calls[-1][0] == 'turn/start'
    assert fake.calls[-1][1]['threadId'] == 'existing'
    assert set(fake.calls[-1][1]) == {'threadId', 'input', 'clientUserMessageId'}


def test_turn_ending_race_refreshes_status_before_waking_idle():
    fake = Fake([ACTIVE, TURN, board_codex.RpcError({'code': -1}), IDLE, {}])
    assert board_codex.notify(fake, 'existing', 'handoff') == 'woke_idle'
    assert [method for method, _ in fake.calls] == ['thread/read', 'thread/turns/list', 'turn/steer', 'thread/read', 'turn/start']


def test_idle_becoming_busy_race_steers_new_turn():
    fake = Fake([IDLE, board_codex.RpcError({'code': -1}), ACTIVE, TURN, {}])
    assert board_codex.notify(fake, 'existing', 'handoff') == 'steered'


def test_unavailable_or_racing_session_is_failure_not_queue_success():
    fake = Fake([{'thread': {'status': {'type': 'notLoaded'}}}])
    with pytest.raises(board_codex.TransportError):
        board_codex.notify(fake, 'existing', 'handoff')
    fake = Fake([ACTIVE, {'data': []}, ACTIVE, {'data': []}])
    with pytest.raises(board_codex.TransportError):
        board_codex.notify(fake, 'existing', 'handoff')
    assert all('queue' not in method for method, _ in fake.calls)


def test_actual_unix_websocket_rpc_initializes_ignores_notifications_and_steers():
    calls = []
    def handle(connection):
        for raw in connection:
            request = json.loads(raw)
            method = request['method']; calls.append(method)
            if 'id' not in request:
                continue
            result = {'initialize': {}, 'thread/read': ACTIVE, 'thread/turns/list': TURN,
                      'turn/steer': {'turnId': 'turn-1'}}[method]
            connection.send(json.dumps({'method': 'test/notification', 'params': {}}))
            connection.send(json.dumps({'id': request['id'], 'result': result}))
    # Short socket path also works under macOS's Unix socket path-length limit.
    with tempfile.TemporaryDirectory(prefix='board-rpc-') as directory:
        path = str(Path(directory) / 'rpc.sock')
        with unix_serve(handle, path=path) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with board_codex.Client(sock=path) as client:
                    assert board_codex.notify(client, 'existing', 'handoff') == 'steered'
            finally:
                server.shutdown(); thread.join(timeout=3)
    assert calls == ['initialize', 'initialized', 'thread/read', 'thread/turns/list', 'turn/steer']
