"""Atomic JSON metadata writes shared by embedded native code and build controllers."""
import json
import os
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
    path.parent.mkdir(parents=True, exist_ok=True)
    scope = _MANAGED_TEMPORARY.get()
    temporary_parent = path.parent
    if scope is not None:
        temporary_parent, descriptor, device, inode = scope
        current = temporary_parent.lstat()
        held = os.fstat(descriptor)
        if (current.st_dev, current.st_ino) != (device, inode) or (held.st_dev, held.st_ino) != (device, inode):
            raise ValueError('managed atomic temporary directory changed')
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            if os.fstat(parent).st_dev != device:
                raise ValueError('managed atomic temporary and destination are on different filesystems')
        finally:
            os.close(parent)
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
