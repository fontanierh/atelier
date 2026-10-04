"""Deliver mailbox notifications to an existing Codex session's active turn."""
import json
import subprocess
import time
import uuid
from contextlib import ExitStack

from websockets.sync.client import unix_connect
from websockets.exceptions import WebSocketException


class TransportError(RuntimeError):
    pass


class RpcError(TransportError):
    def __init__(self, error):
        super().__init__('Codex rejected the request; board delivery must retry.')
        self.error = error


class Client:
    """A bounded connection to the existing daemon, never a new agent or server."""
    def __init__(self, codex='codex', sock=None):
        self.connection = ExitStack()
        try:
            if not sock:
                result = subprocess.run([codex, 'app-server', 'daemon', 'version'], capture_output=True,
                                        text=True, timeout=5, check=True)
                status = json.loads(result.stdout)
                if status.get('status') != 'running':
                    raise TransportError('Codex daemon is unavailable; board cursor retained.')
                sock = status['socketPath']
            self.socket = self.connection.enter_context(
                unix_connect(str(sock), open_timeout=5, close_timeout=1, max_size=2*1024*1024))
        except (OSError, ValueError, KeyError, WebSocketException, subprocess.SubprocessError):
            self.connection.close()
            raise TransportError('Codex connection unavailable; board cursor retained.') from None
        self.sequence = 0
        self.deadline = time.monotonic()+20

    def send(self, value):
        try:
            self.socket.send(json.dumps(value))
        except (OSError, WebSocketException):
            raise TransportError('Codex transport disconnected; board cursor retained.') from None

    def call(self, method, params):
        self.sequence += 1
        request_id = self.sequence
        self.send({'id': request_id, 'method': method, 'params': params})
        while time.monotonic() < self.deadline:
            try:
                message = json.loads(self.socket.recv(timeout=max(0, self.deadline-time.monotonic())))
            except (OSError, ValueError, WebSocketException):
                raise TransportError('Codex transport disconnected; board cursor retained.') from None
            if message.get('id') != request_id:
                continue
            if 'error' in message:
                raise RpcError(message['error'])
            return message.get('result', {})
        raise TransportError('Codex delivery timed out; board cursor retained.')

    def __enter__(self):
        try:
            self.call('initialize', {'clientInfo': {'name': 'atelier_board', 'version': '0.1.0'},
                                     'capabilities': {'experimentalApi': True}})
            self.send({'method': 'initialized'})
            return self
        except Exception:
            self.close()
            raise

    def close(self):
        self.connection.close()

    def __exit__(self, *_):
        self.close()


def notify(client, thread, message):
    """Steer a busy thread; wake a positively confirmed idle existing thread.

    Never interrupt, resume, spawn, or overwrite a session's settings. A turn
    ending between read and steer gets one fresh status check before retry.
    """
    message_id = str(uuid.uuid5(uuid.NAMESPACE_URL, thread+'\n'+message))
    for attempt in range(2):
        metadata = client.call('thread/read', {'threadId': thread, 'includeTurns': False})['thread']
        status = metadata.get('status', {}).get('type')
        if status == 'active':
            page = client.call('thread/turns/list', {'threadId': thread, 'limit': 1,
                                                   'sortDirection': 'desc', 'itemsView': 'notLoaded'})
            turns = page.get('data', [])
            active = next((turn for turn in turns if turn.get('status') == 'inProgress'), None)
            if not active:
                continue
            try:
                client.call('turn/steer', {'threadId': thread, 'expectedTurnId': active['id'],
                                          'input': [{'type': 'text', 'text': message}], 'clientUserMessageId': message_id})
                return 'steered'
            except RpcError:
                if attempt == 0:
                    continue
                raise
        if status == 'idle':
            try:
                client.call('turn/start', {'threadId': thread, 'input': [{'type': 'text', 'text': message}],
                                          'clientUserMessageId': message_id})
                return 'woke_idle'
            except RpcError:
                if attempt == 0:
                    continue
                raise
        raise TransportError('Codex session is unavailable; board cursor retained.')
    raise TransportError('Codex turn changed during delivery; board cursor retained for retry.')
