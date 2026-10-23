"""Deliver mailbox notifications to an existing Codex session's active turn."""
import json
import os
import subprocess
import time
import uuid
from contextlib import ExitStack
from pathlib import Path

from websockets.sync.client import unix_connect
from websockets.exceptions import WebSocketException


# The listener kills a notification command after 30 s. Discovery and delivery share 25 s, and
# discovery may use at most 40% of it (10 s), so the steer itself always keeps at least 15 s.
DELIVERY_BUDGET, DISCOVERY_SHARE, PROBE_BUDGET = 25., .4, 5.
# A notLoaded thread is resumed once, then polled on fresh connections. The
# listener kills the command at 30 s, so the last few seconds stay reserved for
# the delivery itself.
WAKE_POLL_SECONDS, WAKE_POLL_LIMIT, WAKE_RESERVE, RESUME_BUDGET = 1., 20., 4., 5.


class TransportError(RuntimeError):
    pass


class RpcError(TransportError):
    def __init__(self, error):
        super().__init__('Codex rejected the request; board delivery must retry.')
        self.error = error


class Client:
    """A bounded connection to the existing daemon, never a new agent or server.

    One deadline covers the daemon lookup, the socket open and every call, so a whole delivery stays
    inside the listener's 30 s notification command bound.
    """
    def __init__(self, codex='codex', sock=None, home=None, budget=DELIVERY_BUDGET):
        self.connection = ExitStack()
        self.codex = codex
        self.path = None
        self.deadline = time.monotonic()+budget
        try:
            if not sock:
                sock = daemon_socket(codex, home, timeout=self.remaining(5))
                if not sock:
                    raise TransportError('Codex daemon is unavailable; board cursor retained.')
            self.path = str(sock)
            self.socket = self.connection.enter_context(
                unix_connect(str(sock), open_timeout=self.remaining(5), close_timeout=1, max_size=2*1024*1024))
        except (OSError, ValueError, KeyError, WebSocketException, subprocess.SubprocessError):
            self.connection.close()
            raise TransportError('Codex connection unavailable; board cursor retained.') from None
        self.sequence = 0

    def remaining(self, cap):
        return max(.05, min(cap, self.deadline-time.monotonic()))

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
        # The close handshake also spends this client's deadline, at most one second, never past it.
        if hasattr(self, 'socket'):
            self.socket.close_timeout = max(0., min(1., self.deadline-time.monotonic()))
        try:
            self.connection.close()
        except Exception:
            pass

    def reopen(self, budget=None):
        """A fresh connection to the same daemon. thread/resume may drop the first one, which is normal."""
        if not self.path:
            raise TransportError('Codex session cannot be reopened; board cursor retained.')
        if budget is None:
            budget = max(.05, self.deadline-time.monotonic())
        return Client(self.codex, self.path, budget=budget)

    def __exit__(self, *_):
        self.close()


def daemon_socket(codex='codex', home=None, timeout=5.):
    """The running app-server daemon's socket for one Codex home (default: the inherited one), or None."""
    env = dict(os.environ, CODEX_HOME=str(home)) if home else None
    result = subprocess.run([codex, 'app-server', 'daemon', 'version'], capture_output=True,
                            text=True, timeout=timeout, check=True, env=env)
    status = json.loads(result.stdout)
    return status['socketPath'] if status.get('status') == 'running' else None


def codex_homes():
    """Candidate Codex homes on this machine: the inherited one, ~/.codex, and ~/.codex-* daemon homes."""
    found = [Path(os.environ['CODEX_HOME'])] if os.environ.get('CODEX_HOME') else []
    found.append(Path.home() / '.codex')
    found += sorted(p for p in Path.home().glob('.codex-*') if (p / 'app-server-daemon').is_dir())
    return list(dict.fromkeys(p.expanduser().resolve() for p in found))


def locate(thread, codex='codex', homes=None, budget=DELIVERY_BUDGET*DISCOVERY_SHARE):
    """@cc [owner:fontanierh,label:correctness] codex-thread-daemon
    Without an explicit socket or home, delivery MUST use the one running daemon that owns the thread.
    A daemon owns it when thread/read succeeds (any status, including notLoaded); other daemons reject
    it. No owner, or more than one, MUST fail with the board cursor retained, never guess a daemon.
    All probes MUST share one bounded discovery budget; a candidate left unchecked counts as unreachable.
    """
    deadline = time.monotonic()+budget
    owners, unreachable, seen = [], False, set()
    for home in codex_homes() if homes is None else homes:
        left = deadline-time.monotonic()
        if left <= 0:
            unreachable = True
            break
        try:
            sock = daemon_socket(codex, home, timeout=min(PROBE_BUDGET, left))
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            sock = None
        if not sock:
            unreachable = True
            continue
        if sock in seen:
            continue
        seen.add(sock)
        try:
            with Client(codex, sock, budget=min(PROBE_BUDGET, max(0., deadline-time.monotonic()))) as client:
                client.call('thread/read', {'threadId': thread, 'includeTurns': False})
            owners.append(sock)
        except RpcError:
            continue
        except TransportError:
            unreachable = True
    if len(owners) > 1:
        raise TransportError('Codex thread found in more than one daemon; board cursor retained.')
    if not owners:
        raise TransportError('No running Codex daemon has this thread; board cursor retained.' if not unreachable
                             else 'Codex thread owner unavailable; board cursor retained.')
    return owners[0]


def connect(thread, codex='codex', sock=None, home=None, homes=None, budget=DELIVERY_BUDGET):
    """Client for the thread's daemon: an explicit socket, then an explicit home, then the discovered owner.
    Discovery and delivery share one budget, and discovery never takes the delivery's reserved share."""
    start = time.monotonic()
    if sock:
        return Client(codex, sock, budget=budget)
    if home:
        return Client(codex, home=home, budget=budget)
    owner = locate(thread, codex, homes, budget=budget*DISCOVERY_SHARE)
    return Client(codex, owner, budget=max(.05, budget-(time.monotonic()-start)))


def notify(client, thread, message, *, allow_wake=True):
    """Steer a busy thread; wake a positively confirmed idle existing thread.

    A notLoaded thread is resumed once, polled on fresh connections until it is
    idle or active, then delivered on another fresh connection. Never spawn or
    overwrite a session's settings. A turn ending between read and steer gets one
    fresh status check before retry.
    """
    message_id = str(uuid.uuid5(uuid.NAMESPACE_URL, thread+'\n'+message))
    for attempt in range(2):
        metadata = client.call('thread/read', {'threadId': thread, 'includeTurns': False})['thread']
        status = metadata.get('status', {}).get('type')
        if status == 'notLoaded':
            if not allow_wake:
                raise TransportError('Codex session is unavailable; board cursor retained.')
            return wake_and_deliver(client, thread, message, message_id)
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


def wake_and_deliver(client, thread, message, message_id):
    """Resume one notLoaded thread, wait for it to load, then deliver on a new connection.

    The resume connection may close as soon as the daemon starts loading the
    thread; that is success, so the poll decides. Every attempt shares the
    caller's deadline, and the last few seconds are reserved for delivery.
    """
    deadline = client.deadline
    resume = max(.05, min(RESUME_BUDGET, deadline-time.monotonic()-WAKE_RESERVE))
    try:
        with client.reopen(budget=resume) as resumer:
            resumer.call('thread/resume', {'threadId': thread})
    except TransportError:
        pass

    status = None
    limit = min(WAKE_POLL_LIMIT, max(0., deadline-time.monotonic()-WAKE_RESERVE))
    stop = time.monotonic()+limit
    while time.monotonic() < stop:
        left = deadline-time.monotonic()
        if left <= WAKE_RESERVE:
            break
        try:
            with client.reopen(budget=min(2., max(.05, left-WAKE_RESERVE))) as probe:
                metadata = probe.call('thread/read', {'threadId': thread, 'includeTurns': False})['thread']
                status = metadata.get('status', {}).get('type')
        except TransportError:
            status = None
        if status in ('idle', 'active'):
            break
        time.sleep(min(WAKE_POLL_SECONDS, max(0., deadline-time.monotonic()-WAKE_RESERVE)))

    remaining = deadline-time.monotonic()
    if remaining <= .05:
        raise TransportError('Codex session did not wake; board cursor retained.')
    with client.reopen(budget=remaining) as delivery:
        return notify(delivery, thread, message, allow_wake=False)
