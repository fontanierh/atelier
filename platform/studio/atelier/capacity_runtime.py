"""Select conservative configured profiles for the common guarded-launch path.

Absence of the machine client configuration keeps the existing launcher. Once configured,
bad settings or an unavailable broker are errors; no implicit fallback can bypass capacity.
The migration bridge remains exclusive and does not change tool worker settings.
"""
from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import stat
import uuid

from .capacity import Resources
from .paths import REPO

DEFAULT_CONFIG = Path.home() / '.cache/atelier/capacity/client.json'
MAX_CONFIG_BYTES = 65536


def read_configuration(path):
    """Read an owner-only single-link configuration, without following its final symlink."""
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('capacity configuration must use an absolute path')
    parent = path.parent.resolve(strict=True)
    info = parent.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError('capacity configuration directory must be owner-only')
    descriptor = os.open(parent / path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as handle:
        info = os.fstat(handle.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) & 0o077 or info.st_size > MAX_CONFIG_BYTES):
            raise ValueError('capacity configuration must be a private owned regular file')
        raw = handle.read(MAX_CONFIG_BYTES + 1)
    if len(raw) > MAX_CONFIG_BYTES:
        raise ValueError('capacity configuration exceeds 64 KiB')
    return json.loads(raw)


def configured_session(*, kind, limit_gib, timeout, folder=None, purpose=None, config=None):
    """@cc [owner:fontanierh,label:safety] configured-capacity-never-falls-back
    A configured common launcher MUST refuse invalid profiles or unavailable admission. The full
    reservation MUST cover its existing guard ceiling; profiles MUST NOT raise that guard limit or
    silently change worker counts. Every request MUST claim its own checkout's named lock.
    """
    selected = config or os.environ.get('ATELIER_CAPACITY_CLIENT')
    path = Path(selected) if selected is not None else DEFAULT_CONFIG
    try:
        path.lstat()
    except FileNotFoundError:
        if selected is None:
            return None
        raise ValueError('configured capacity client file is missing') from None
    value = read_configuration(path)
    if (not isinstance(value, dict) or set(value) != {'schema', 'socket', 'profiles'}
            or value['schema'] != 1 or not isinstance(value['socket'], str)
            or not Path(value['socket']).is_absolute() or not isinstance(value['profiles'], dict)):
        raise ValueError('unsupported capacity client configuration')
    if set(value['profiles']) != {'job', 'game', 'compile'}:
        raise ValueError('capacity client needs job, game and compile profiles')
    profile = value['profiles'].get(kind)
    if not isinstance(profile, dict) or set(profile) != {'resources', 'locks'}:
        raise ValueError('capacity profile needs resources and named locks')
    resources = Resources(**profile['resources'])
    if (not math.isfinite(limit_gib) or limit_gib <= 0
            or not math.isfinite(timeout) or timeout < 0):
        raise ValueError('capacity launch needs a positive finite guard ceiling and nonnegative finite timeout')
    if resources.memory_mib < math.ceil(limit_gib * 1024):
        raise ValueError('capacity profile reservation is smaller than the actual guard ceiling')
    if resources.cpu_millis == 0 or resources.io_slots == 0:
        raise ValueError('capacity profiles must reserve CPU and I/O capacity')
    locks = profile['locks']
    if (not isinstance(locks, list) or any(not isinstance(lock, str) or not lock for lock in locks)
            or len(locks) != len(set(locks))):
        raise ValueError('capacity profile named locks must be unique nonempty strings')
    from .capacity_client import AdmissionSession
    # The broker keeps an uncharged request's ready age when a controller is refused or
    # restarted. Its independent run nonce fences the previous attempt's exec gate.
    request_id = uuid.uuid5(uuid.NAMESPACE_URL, str(REPO) + '\n' + kind + '\n' + str(folder or '')).hex
    request = dict(id=request_id, owner=os.environ.get('ATELIER_AGENT') or 'launcher', checkout=str(REPO),
                   purpose=str(purpose or kind), phase=kind,
                   resources=asdict(resources), locks=sorted(set(locks) | {'checkout:' + str(REPO)}),
                   seconds=math.ceil(timeout) if timeout > 0 else 300)
    return AdmissionSession(value['socket'], request)
