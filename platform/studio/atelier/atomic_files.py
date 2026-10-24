"""Atomic JSON metadata writes shared by embedded native code and build controllers."""
import json
import os
import stat
from pathlib import Path
import tempfile
from contextlib import contextmanager
from contextvars import ContextVar

_MANAGED_TEMPORARY = ContextVar("atelier_managed_atomic_temporary", default=None)


@contextmanager
def managed_temporaries(directory):
    """Private managed-body scratch scope; never grants permission or changes defaults."""
    directory = Path(directory)
    if not directory.is_absolute() or '..' in directory.parts:
        raise ValueError("atomic temporary scope requires an absolute owned path")
    descriptor = os.open(directory.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in directory.parts[1:]:
            try:
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            except FileNotFoundError:
                os.mkdir(component, 0o700, dir_fd=descriptor)
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor); descriptor = child
        info = os.fstat(descriptor)
        token = _MANAGED_TEMPORARY.set((directory, descriptor, info.st_dev, info.st_ino))
        try:
            yield
        finally:
            _MANAGED_TEMPORARY.reset(token)
    finally:
        os.close(descriptor)

def atomic_json(path, value):
    """@cc [owner:fontanierh,label:correctness;safety] scoped-atomic-json-temporaries
    Default writes MUST retain their original sibling temporary semantics. A managed
    scope MUST bind its held real scratch directory and require a real destination
    parent on the same filesystem before temporary creation/replace; cross-device
    writes MUST refuse without copy fallback. Scope MUST NOT enlarge product or audit
    ownership. JSON bytes, mode, fsync and atomic replacement MUST remain unchanged.
    See test_atomic_files.py and the original-observer scratch integration test.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    scope = _MANAGED_TEMPORARY.get()
    temporary_parent = path.parent
    if scope is not None:
        temporary_parent, descriptor, device, inode = scope
        current = temporary_parent.lstat()
        held = os.fstat(descriptor)
        if (current.st_dev, current.st_ino) != (device, inode) or (held.st_dev, held.st_ino) != (device, inode):
            raise ValueError('managed atomic temporary directory changed')
        parent = path.parent.lstat()
        if not stat.S_ISDIR(parent.st_mode):
            raise ValueError('managed atomic destination parent is not a real directory')
        if parent.st_dev != device:
            raise ValueError('managed atomic temporary and destination are on different filesystems')
    with tempfile.NamedTemporaryFile(mode='w', dir=temporary_parent, prefix='.write-', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
