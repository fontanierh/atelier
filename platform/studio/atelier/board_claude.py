"""Deliver to an existing Claude inbox; never launch a second transcript writer."""
import hashlib
import errno
import json
import os
import socket
import select
import stat
import struct
import subprocess
import sys
import time
import uuid
from pathlib import Path


class TransportError(Exception):
    pass


def process_start(pid):
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'lstart='], capture_output=True,
                            text=True, timeout=2, env={**os.environ, 'TZ': 'UTC', 'LC_ALL': 'C'})
    return result.stdout.strip() if result.returncode == 0 else None


def private_file(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise TransportError('Claude inbox key is not a private regular file')
        return json.loads(stream.read(4096))


def resolve(session_dir, registry=None):
    """Resolve every time: service restarts replace PIDs and sockets, not board owners."""
    registry = registry or Path.home() / '.claude/sessions'
    matches = []
    for path in registry.glob('*.json'):
        if not path.stem.isdigit():
            continue
        try:
            record = json.loads(path.read_text())
            if record.get('cwd') != str(Path(session_dir).resolve()):
                continue
            pid = record.get('pid')
            if pid != int(path.stem) or record.get('procStart') != process_start(pid):
                continue
            inbox = Path(record['messagingSocketPath'])
            info, parent = inbox.lstat(), inbox.parent.lstat()
            if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid()
                    or not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid()
                    or stat.S_IMODE(parent.st_mode) != 0o700):
                continue
            keys = list(registry.glob(f'{pid}.*.key'))
            if len(keys) != 1:
                continue
            key = private_file(keys[0])
            if key.get('procStart') != record['procStart'] or not isinstance(key.get('peerToken'), str):
                continue
            matches.append((record, key['peerToken']))
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
            continue
    if len(matches) != 1:
        raise TransportError('Expected exactly one live Claude inbox in the registered session directory')
    return matches[0]


def peer_pid(client):
    if sys.platform == 'darwin':
        return struct.unpack('i', client.getsockopt(0, 2, 4))[0]  # LOCAL_PEERPID
    if sys.platform.startswith('linux'):
        pid, uid, _ = struct.unpack('3i', client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if uid != os.getuid():
            raise TransportError('Claude inbox belongs to another OS user')
        return pid
    raise TransportError('Claude inbox adapter requires macOS or Linux')


def notify(session_dir, message, permission_class='prompting', registry=None, timeout=4):
    record, token = resolve(session_dir, registry)
    inbox = Path(record['messagingSocketPath'])
    # Receipts for held/refused/dropped messages use a private reply socket in the
    # native namespace. It is our socket only, never a Claude process or registry row.
    reply = inbox.parent / f'{os.getpid()}.sock'
    msg_id = str(uuid.uuid5(uuid.NAMESPACE_URL, hashlib.sha256(message.encode()).hexdigest()))
    sender = 'uds:' + str(reply)
    body = message.replace('</cross-session-message>', '&lt;/cross-session-message&gt;')
    wrapped = (f'<cross-session-message from="{sender}" from-name="Atelier board" '
               f'from-mode="{permission_class}">\n{body}\n</cross-session-message>')
    frame = {'type': 'user', 'session_id': record['sessionId'], 'from': sender, 'msg_id': msg_id,
             'message': {'role': 'user', 'content': wrapped}}
    with socket.socket(socket.AF_UNIX) as receipts:
        receipts.bind(str(reply))  # Refuse collisions; never unlink another process's socket.
        reply.chmod(0o600)
        try:
            receipts.listen(4)
            with socket.socket(socket.AF_UNIX) as client:
                client.settimeout(timeout)
                client.connect(str(inbox))
                if peer_pid(client) != record['pid'] or process_start(record['pid']) != record['procStart']:
                    raise TransportError('Claude inbox process changed before delivery')
                client.sendall((json.dumps({'type': 'auth', 'token': token}) + '\n' + json.dumps(frame) + '\n').encode())
                # Listen for negative receipts while waiting for the target to close.
                # Receiving concurrently keeps the receipt sender's PID verifiable.
                deadline, end_after = time.monotonic()+timeout, time.monotonic()+.15
                closed, ended, grace = False, False, None
                while True:
                    now = time.monotonic()
                    if not ended and now >= end_after:
                        try:
                            client.shutdown(socket.SHUT_WR)
                        except OSError as error:
                            if error.errno != errno.ENOTCONN:
                                raise
                        ended = True
                    if closed and now >= grace:
                        break
                    if now >= deadline:
                        raise TimeoutError('Claude inbox event loop did not respond')
                    wait = min(deadline-now, max(0, end_after-now) if not ended else deadline-now,
                               max(0, grace-now) if closed else deadline-now)
                    readable, _, _ = select.select([receipts] if closed else [receipts, client], [], [], wait)
                    if receipts in readable:
                        connection, _ = receipts.accept()
                        with connection:
                            connection.settimeout(1)
                            try:
                                verified = peer_pid(connection) == record['pid']
                            except OSError:
                                verified = False
                            if not verified:
                                raise TransportError('Claude receipt could not be verified; delivery remains pending')
                            receipt = json.loads(connection.makefile('rb').readline(16000))
                            if (receipt.get('action') != 'peer_message_status'
                                    or receipt.get('orig_msg_id') != msg_id):
                                raise TransportError('Unexpected Claude inbox receipt')
                            if receipt.get('status') != 'delivered':
                                raise TransportError('Claude inbox reported ' + str(receipt.get('status', 'unknown')))
                    if client in readable:
                        if client.recv(1) != b'':
                            raise TransportError('Unexpected Claude inbox response')
                        closed, grace = True, time.monotonic()+.3
        finally:
            reply.unlink(missing_ok=True)
    return 'Sent to existing Claude inbox; agent acknowledgement is pending'
