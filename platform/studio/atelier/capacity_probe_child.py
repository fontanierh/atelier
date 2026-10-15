"""Fixed, harmless children of the closed-roster capacity experiment; no workload API."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

TIMEOUT = 3
MAX_FRAME = 2048


def process_start(pid):
    """OS birth identity, never a nonce and never an inference that a process died."""
    if sys.platform == 'darwin':
        # The fixed script also runs with -I -S; use this checkout's existing libproc API.
        root = str(Path(__file__).resolve().parent.parent)
        if root not in sys.path:
            sys.path.insert(0, root)
        from atelier.safety.memory_guard import usage
        value = int(usage(pid).started)
    elif sys.platform.startswith('linux'):
        with open(f'/proc/{pid}/stat', 'rb') as source:
            data = source.read(4097)
        if len(data) > 4096:
            raise ValueError('Unsupported process identity record')
        value = int(data[data.rindex(b')') + 2:].split()[19])
    else:
        raise ValueError('Closed probes require macOS or Linux process identities')
    if value <= 0:
        raise ValueError('Process start identity is unavailable')
    return value


def pinned():
    return [os.getpid(), process_start(os.getpid())]


def send(channel, record):
    data = json.dumps(record, separators=(',', ':'), allow_nan=False).encode() + b'\n'
    if len(data) > MAX_FRAME:
        raise ValueError('Probe frame exceeds limit')
    channel.settimeout(TIMEOUT)
    channel.sendall(data)


def receive(channel):
    deadline = time.monotonic() + TIMEOUT
    data = bytearray()
    while len(data) < MAX_FRAME:
        channel.settimeout(max(0.001, deadline - time.monotonic()))
        byte = channel.recv(1)
        if not byte:
            raise ValueError('Probe channel closed before a receipt')
        if byte == b'\n':
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError('Duplicate probe frame field')
                    result[key] = value
                return result
            record = json.loads(data, object_pairs_hook=unique)
            if not isinstance(record, dict):
                raise ValueError('Invalid probe frame')
            return record
        data.extend(byte)
        if time.monotonic() >= deadline:
            raise TimeoutError('Probe channel deadline exceeded')
    raise ValueError('Probe frame exceeds limit')


def binding(record):
    if (set(record) != {'epoch', 'nonce'} or type(record['epoch']) is not int or record['epoch'] <= 0 or
            not isinstance(record['nonce'], str) or len(record['nonce']) != 64 or
            any(c not in '0123456789abcdef' for c in record['nonce'])):
        raise ValueError('Invalid probe binding')
    return record


def expect(record, expected):
    # JSON equality also distinguishes booleans/floats from integer epoch and start fields.
    def canonical(value):
        return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if canonical(record) != canonical(expected):
        raise ValueError('Probe receipt or gate binding mismatch')


def command(role, descriptor):
    # Neither caller nor recipe can supply executable code or arbitrary child arguments.
    return [sys.executable, '-I', '-S', str(Path(__file__).resolve()), role, str(descriptor)]


def reap(child):
    """Only an owned Popen handle is signalled; wait is required even after kill."""
    try:
        return child.wait(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        child.terminate()
    try:
        return child.wait(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        child.kill()
        return child.wait(timeout=TIMEOUT)


def worker(channel):
    """@cc [owner:fontanierh,label:safety] fixed-probe-useful-byte
    This fixed worker MUST write its sole useful byte only after an exact private-channel gate
    matches its epoch, nonce and OS birth identity. EOF, timeout and malformed gates MUST emit
    no useful byte. It MUST NOT launch any descendants or accept executable work from callers.
    """
    bound = binding(receive(channel))
    own = pinned()
    send(channel, dict(kind='worker-ready', worker=own, **bound))
    gate = receive(channel)
    expect(gate, dict(kind='go', worker=own, **bound))
    if pinned() != own:
        raise ValueError('Probe gate binding mismatch')
    os.write(1, b'P')  # The sole useful byte; unreachable before the exact gate message.


def launcher(channel):
    bound = binding(receive(channel))
    own = pinned()
    parent, child_end = socket.socketpair()
    child = None
    ready = None
    try:
        child = subprocess.Popen(command('worker', child_end.fileno()), pass_fds=(child_end.fileno(),),
                                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        child_end.close()
        send(parent, bound)
        ready = receive(parent)
        expected = dict(kind='worker-ready', worker=[child.pid, process_start(child.pid)], **bound)
        expect(ready, expected)
        send(channel, dict(kind='ready', launcher=own, worker=ready['worker'], **bound))
        gate = receive(channel)
        expect(gate, dict(kind='go', launcher=own, worker=ready['worker'], **bound))
        if pinned() != own:
            raise ValueError('Probe launcher gate binding mismatch')
        send(parent, dict(kind='go', worker=ready['worker'], **bound))
    finally:
        child_end.close()
        parent.close()  # EOF refuses useful work if any earlier stage failed.
        if child is not None:
            code = reap(child)
            useful = child.stdout.read(2) == b'P'
            child.stdout.close()
            if ready is not None:
                send(channel, dict(kind='waited', launcher=own, worker=ready['worker'],
                                   returncode=code, useful_byte=useful, **bound))


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3 or sys.argv[1] not in ('launcher', 'worker'):
            raise ValueError('Fixed probe role required')
        with socket.socket(fileno=int(sys.argv[2])) as channel:
            (launcher if sys.argv[1] == 'launcher' else worker)(channel)
    except Exception:
        sys.exit(1)  # Never print process paths, raw protocol input or internal exceptions.
