"""Private per-launch context for identifying late owned crash reporters.

This is lifecycle evidence within one user's process tree, not a security boundary
against another process deliberately copying that user's environment.
"""
from dataclasses import dataclass, field
from contextlib import contextmanager
import os
import re
import secrets
import threading
from types import MappingProxyType

ENVIRONMENT_KEY = 'ATELIER_OWNED_LAUNCH_NONCE'
LINEAGE_KEY = 'ATELIER_OWNED_LAUNCH_ANCESTORS'
MAX_ANCESTORS = 8
_ORIGIN = object()


def marker_tokens(current, lineage):
    """Strict, ordered launch ancestry; malformed metadata never becomes foreign proof."""
    if (not isinstance(current, str) or not re.fullmatch('[0-9a-f]{64}', current)
            or not isinstance(lineage, str) or len(lineage) > MAX_ANCESTORS * 65):
        raise ValueError('Invalid private launch ancestry')
    ancestors = lineage.split(':') if lineage else []
    values = (*ancestors, current)
    if (len(ancestors) > MAX_ANCESTORS or len(set(values)) != len(values)
            or any(not re.fullmatch('[0-9a-f]{64}', value) for value in ancestors)):
        raise ValueError('Invalid private launch ancestry')
    return values


@dataclass(frozen=True)
class LaunchContext:
    environment: object = field(repr=False)
    nonce: str = field(repr=False)
    _claimed: bool = field(default=False, repr=False, compare=False)
    _origin: object = field(default=None, repr=False, compare=False)
    _lock: object = field(default_factory=threading.Lock, repr=False, compare=False)

    def claim(self, environment):
        """One guarded invocation owns a context; retries stay inside that invocation."""
        with self._lock:
            if (self._origin is not _ORIGIN or self._claimed or not re.fullmatch('[0-9a-f]{64}', self.nonce)
                    or dict(environment) != dict(self.environment)
                    or environment.get(ENVIRONMENT_KEY) != self.nonce):
                raise ValueError('Invalid, changed or already used launch ownership context')
            marker_tokens(environment.get(ENVIRONMENT_KEY), environment.get(LINEAGE_KEY))
            object.__setattr__(self, '_claimed', True)
            return self.nonce


def prepare(environment=None):
    """Prepare BEFORE an exact launch request hashes its environment.

    Nested launches preserve bounded ancestry so an outer guard can reconcile an
    orphan if the inner monitor dies. Every launch still receives a fresh identity.
    No caller environment is mutated, and the marker must never enter reusable keys.
    """
    environment = dict(os.environ if environment is None else environment)
    ancestors = ()
    if ENVIRONMENT_KEY in environment or LINEAGE_KEY in environment:
        ancestors = marker_tokens(environment.get(ENVIRONMENT_KEY), environment.get(LINEAGE_KEY))
        if len(ancestors) > MAX_ANCESTORS:
            raise ValueError('Private launch ancestry depth exhausted')
    nonce = secrets.token_hex(32)
    if nonce in ancestors:
        raise ValueError('Private launch identity collision')
    environment[ENVIRONMENT_KEY] = nonce
    environment[LINEAGE_KEY] = ':'.join(ancestors)
    return LaunchContext(MappingProxyType(environment), nonce, _origin=_ORIGIN)


@contextmanager
def private_pipe(nonce):
    """Send context to a monitor through one inherited FD, never its argv or logs."""
    if not isinstance(nonce, str) or not re.fullmatch('[0-9a-f]{64}', nonce):
        raise ValueError('Invalid private launch marker')
    reader, writer = os.pipe()
    try:
        try:
            if os.write(writer, nonce.encode('ascii')) != 64:
                raise OSError('Incomplete private context write')
        finally:
            os.close(writer)
        yield reader
    finally:
        os.close(reader)


def read_private_pipe(descriptor):
    try:
        value = os.read(descriptor, 65)
        if len(value) != 64 or not re.fullmatch(b'[0-9a-f]{64}', value):
            raise ValueError('Invalid private context transport')
        return value.decode('ascii')
    finally:
        os.close(descriptor)
