"""Durable, checkout-local barriers and metadata for explicit portable-pool transfers."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import time
import uuid

JOURNAL = '.pool-transfer-in-progress.json'
MAX_JSON = 8 * 1024 * 1024


def read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
                or info.st_size > MAX_JSON):
            raise ValueError('Pool metadata must be an owned bounded regular single-link file')
        raw = stream.read(MAX_JSON + 1)
    if len(raw) > MAX_JSON:
        raise ValueError('Pool metadata exceeds its size bound')
    return json.loads(raw)


def write(path, value):
    path = Path(path)
    raw = (json.dumps(value, sort_keys=True) + '\n').encode()
    if len(raw) > MAX_JSON:
        raise ValueError('Pool metadata exceeds its size bound')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    try:
        with temporary.open('xb') as stream:
            os.chmod(temporary, 0o600)
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        temporary.replace(path)
        sync(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def sync(folder):
    fd = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def token(value):
    return type(value) is str and re.fullmatch('[a-f0-9]{32}', value) is not None


def valid_name(value):
    return type(value) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,159}', value) is not None


def owned_roots(value):
    if not isinstance(value, list) or not value or any(type(p) is not str for p in value):
        raise ValueError('Pool journal has no valid output scope')
    roots = [Path(p) for p in value]
    for raw, path in zip(value, roots):
        if (path.is_absolute() or not path.parts or str(path) != raw
                or any(p.casefold() in ('', '.', '..', 'content', 'binaries', 'intermediate') for p in path.parts)
                or path.parts[0].casefold() in ('logs', 'stamps') or '\\' in str(path)):
            raise ValueError('Pool journal output scope is unsafe')
    folded = [tuple(part.casefold() for part in path.parts) for path in roots]
    if any(a == b[:len(a)] or b == a[:len(b)] for i,a in enumerate(folded) for b in folded[i+1:]):
        raise ValueError('Pool journal output roots overlap')
    return roots


def validate(value, *, game, step, out, pool):
    fields = {'schema','action','game','step','out','pool','key','fingerprint','roots','invocation'}
    if (type(value) is not dict or set(value) != fields or type(value['schema']) is not int or value['schema'] != 1
            or value['action'] not in ('publish','restore') or value['game'] != game or value['step'] != step
            or not valid_name(game) or not valid_name(step) or not token(value['invocation'])
            or value['out'] != str(Path(out).resolve()) or value['pool'] != str(Path(pool).resolve())
            or type(value['key']) is not str or re.fullmatch('[a-f0-9]{64}', value['key']) is None
            or type(value['fingerprint']) is not str or not value['fingerprint']):
        raise ValueError('Pool journal identity differs; preserve it and use its original scope')
    owned_roots(value['roots'])
    return value


def stage(pool, invocation):
    if not token(invocation):
        raise ValueError('Invalid pool invocation')
    return Path(pool) / ('.pending-' + invocation)


@contextmanager
def transaction(out):
    """A file-publication mutex, acquired only after admission or during parent finalization."""
    folder = Path(out) / 'logs'
    folder.mkdir(parents=True, exist_ok=True)
    fd = os.open(folder / '.pool-transfer.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    with os.fdopen(fd, 'r+b') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            raise ValueError('Pool transaction mutex must be an owned regular single-link file')
        began = spoken = time.monotonic()
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                now = time.monotonic()
                if now - began >= 30:
                    raise ValueError('Pool transfer finalization is still busy; no files changed') from None
                if now - spoken >= 5:
                    print('Waiting for the pool transfer transaction to finish', flush=True)
                    spoken = now
                time.sleep(.05)
        yield


def destination(out, root):
    """Never follow an existing output link, including a link above a nested owned root."""
    owned_roots([str(root)])
    current = Path(out)
    for part in Path(root).parts:
        current /= part
        if current.is_symlink():
            raise ValueError('Pool output scope contains a symlink')
    return current
