"""Opt-in legacy worker proof using the launcher's existing lock and both live monitors.

This is a lifecycle invariant for trusted Atelier callers, not a same-UID sandbox. Received
lock descriptors are close-only duplicates; validation never changes their shared flock state.
"""
import errno
import fcntl
import os
from pathlib import Path
import re
import socket
import stat
import time

from .. import capacity_protocol as wire


def require_legacy():
    """The experimental installer has no broker or cutover lifecycle proof yet."""
    from .. import capacity_compat, capacity_runtime
    if 'ATELIER_CAPACITY_CLIENT' in os.environ:
        raise wire.CapacityError('Package installation currently supports unconfigured legacy admission only')
    for path in (capacity_runtime.DEFAULT_CONFIG, capacity_compat.DEFAULT_RECORD):
        try:
            Path(path).lstat()
        except FileNotFoundError:
            continue
        except OSError:
            raise wire.CapacityError('Cannot establish absent capacity configuration') from None
        raise wire.CapacityError('Package installation refuses any capacity configuration or cutover marker')


def _pin(info):
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
        raise wire.CapacityError('Worker lock must be an owned single-link regular file')
    return dict(device=info.st_dev, inode=info.st_ino, mode=stat.S_IMODE(info.st_mode))


def _held(descriptor, path, pin, holder, owner, repo):
    """Probe an independently opened description, never the transferred lock description."""
    from .render_lock import PROTOCOL, lock_path
    path = Path(wire.text(path, maximum=4096))
    if path != lock_path().absolute():
        raise wire.CapacityError('Worker proof uses another legacy mutex')
    if not path.is_absolute() or _pin(os.fstat(descriptor)) != pin or _pin(path.lstat()) != pin:
        raise wire.CapacityError('Worker lock inode changed')
    actual = wire.decode(wire.private_file(path, limit=wire.MAX_FRAME, private=False))
    if (actual != holder or actual.get('pid') != owner[0] or actual.get('started') != owner[1]
            or actual.get('repo') != repo or actual.get('slot') != 'big' or actual.get('kind') != 'job'
            or actual.get('capacity_bridge') or actual.get('protocol') != PROTOCOL):
        raise wire.CapacityError('Worker lock holder differs from its guarded controller')
    probe = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if _pin(os.fstat(probe)) != pin:
            raise wire.CapacityError('Worker lock changed before its conflict probe')
        try:
            fcntl.flock(probe, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno not in (errno.EAGAIN, errno.EACCES):
                raise
        else:
            fcntl.flock(probe, fcntl.LOCK_UN)
            raise wire.CapacityError('Worker controller no longer holds exclusive legacy admission')
    finally:
        os.close(probe)


class WorkerBinding:
    """Framework-owned producer; only guarded.run publishes after both guards and GO."""
    def __init__(self, nonce, request_sha256, repo):
        if not re.fullmatch('[0-9a-f]{32}', nonce) or not re.fullmatch('[0-9a-f]{64}', request_sha256):
            raise ValueError('A worker binding needs exact request identities')
        self.nonce, self.request_sha256, self.repo = nonce, request_sha256, str(Path(repo).absolute())
        self.sender, self.receiver = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sender.settimeout(2.)
        self.receiver.settimeout(2.)
        self.lock = None
        self.sent = False

    @property
    def descriptor(self):
        return self.receiver.fileno()

    def capture(self, handle, path, holder):
        if self.lock is not None or self.sent:
            raise wire.CapacityError('Worker binding cannot reuse a lock context')
        self.lock = (handle, str(Path(path).absolute()), dict(holder))

    def publish(self, child, guards, limit_bytes):
        require_legacy()
        if self.sent or self.lock is None:
            raise wire.CapacityError('Worker binding has no fresh legacy context')
        owner = (os.getpid(), wire.process_start(os.getpid()))
        child = wire.identity(child)
        if not wire.direct_child(owner, child):
            raise wire.CapacityError('Worker is not the actual guarded child')
        wire.validate_guards(guards, child, owner, limit_bytes, (limit_bytes + 1024**2 - 1) // 1024**2)
        handle, path, holder = self.lock
        pin = _pin(os.fstat(handle.fileno()))
        _held(handle.fileno(), path, pin, holder, owner, self.repo)
        value = dict(schema=1, nonce=self.nonce, request_sha256=self.request_sha256, repo=self.repo,
                     owner=list(owner), child=list(child), guards=guards, limit_bytes=limit_bytes,
                     lock_path=path, lock_pin=pin, holder=holder, observed_monotonic=time.monotonic())
        wire.send(self.sender, value, handle.fileno(), deadline=time.monotonic() + 2.)
        self.sent = True
        self.sender.close()

    def close(self):
        self.sender.close()
        self.receiver.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class WorkerProof:
    """Close-only worker witness; all live checks must still hold at mutation boundaries."""
    def __init__(self, value, descriptor):
        self.value, self.descriptor = value, descriptor

    @classmethod
    def receive(cls, channel, *, nonce, request_sha256, parent, repo, limit_bytes):
        received = None
        try:
            require_legacy()
            channel.settimeout(2.)
            value, received = wire.receive(channel, descriptor=True, deadline=time.monotonic() + 2.)
            wire.fields(value, ('schema', 'nonce', 'request_sha256', 'repo', 'owner', 'child', 'guards',
                                'limit_bytes', 'lock_path', 'lock_pin', 'holder', 'observed_monotonic'))
            observed = value['observed_monotonic']
            if (type(value['schema']) is not int or value['schema'] != 1 or value['nonce'] != nonce
                    or value['request_sha256'] != request_sha256 or value['repo'] != str(repo)
                    or wire.identity(value['owner']) != wire.identity(parent)
                    or value['limit_bytes'] != limit_bytes or type(observed) not in (int, float)
                    or not 0 <= time.monotonic() - observed <= 3):
                raise wire.CapacityError('Worker proof is stale or bound to another invocation')
            proof = cls(value, received)
            proof.check()
            received = None
            return proof
        finally:
            if received is not None:
                os.close(received)

    def check(self):
        """@cc [owner:fontanierh,label:safety] live-legacy-worker-binding
        Useful worker mutations MUST require the actual live parent/child, both fresh owned guard
        receipts and the same still-held exclusive legacy lock. A nonce or caller request alone
        MUST NOT prove admission. Received lock descriptions MUST be close-only; only an independent
        nonblocking probe MAY be flocked and unlocked. Broker/cutover modes MUST refuse.
        """
        require_legacy()
        value = self.value
        owner, child = wire.identity(value['owner']), wire.identity(value['child'])
        actual = (os.getpid(), wire.process_start(os.getpid()))
        if child != actual or os.getppid() != owner[0] or not wire.direct_child(owner, child):
            raise wire.CapacityError('Worker proof belongs to another live process')
        limit = wire.integer(value['limit_bytes'], minimum=1)
        wire.fields(value['guards'], ('process_guard', 'tree_guard'))
        monitors = [wire.identity((item['pid'], item['start'])) for item in value['guards'].values()]
        if len(set(monitors)) != 2 or any(pin in (owner, child) for pin in monitors):
            raise wire.CapacityError('Worker requires two distinct owned monitor processes')
        wire.validate_guards(value['guards'], child, owner, limit, (limit + 1024**2 - 1) // 1024**2)
        _held(self.descriptor, value['lock_path'], value['lock_pin'], value['holder'], owner, value['repo'])
        if not wire.live(owner) or not wire.live(child):
            raise wire.CapacityError('Worker controller exited during proof validation')

    def close(self):
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
