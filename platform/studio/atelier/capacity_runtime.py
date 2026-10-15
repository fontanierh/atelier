"""Select conservative configured profiles for the common guarded-launch path.

Absence of the machine client configuration keeps the existing launcher. Once configured,
bad settings or an unavailable broker are errors; no implicit fallback can bypass capacity.
The migration bridge remains exclusive and does not change tool worker settings.
"""
from dataclasses import asdict, replace
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


def _worker_profile(command):
    """Recognize only explicit Blender worker limits; never change the command's settings."""
    if not command or Path(command[0]).name.lower() != 'blender':
        return None
    args = list(map(str, command[1:]))
    args = args[:args.index('--')] if '--' in args else args
    counts = []
    for index, arg in enumerate(args):
        if arg in ('--threads', '-t'):
            if index + 1 >= len(args):
                raise ValueError('Blender thread limit has no value')
            counts.append(args[index + 1])
        elif arg.startswith('--threads='):
            counts.append(arg.split('=', 1)[1])
        elif arg.startswith('-t') and arg[2:].isdigit():
            counts.append(arg[2:])
    if not counts:
        return None
    try:
        workers = [int(value) for value in counts]
    except ValueError:
        raise ValueError('Blender thread limit must be explicit and bounded') from None
    if any(value <= 0 for value in workers) or len(set(workers)) != 1:
        raise ValueError('Blender thread limit must be one positive explicit value')
    return workers[0]


def validate_session_profile(admission, *, kind, command, limit_gib):
    """@cc [owner:fontanierh,label:safety] explicit-capacity-command-envelope
    Explicit full sessions MUST cover the actual unchanged command workers and guard ceiling,
    claim the actual checkout lock, and reserve CPU and I/O. Unknown commands, games and compiles
    MUST remain exclusive; an explicit session MUST NOT bypass configured-launch profile rules.
    """
    from . import capacity_protocol as wire
    request = admission.request
    workers = _worker_profile(command)
    resources = wire.resources(request.get('resources'))
    if (request.get('checkout') != str(REPO) or 'checkout:' + str(REPO) not in request.get('locks', [])):
        raise ValueError('Full-capacity session must hold the actual checkout named lock')
    if not resources.cpu_millis or not resources.io_slots:
        raise ValueError('Full-capacity session must reserve CPU and I/O capacity')
    if request.get('phase') != kind:
        raise ValueError('Full-capacity session phase differs from the actual launch kind')
    if request.get('performance') is not True and (kind in ('game', 'compile') or workers is None):
        raise ValueError('Full-capacity games, compiles and unknown commands require exclusive admission')
    if workers is None:
        if request.get('workers') is not None:
            raise ValueError('Unknown commands cannot declare bounded Blender workers')
        from . import capacity_compat
        proof = capacity_compat.verify(admission.cutover)
        if resources.cpu_millis < proof['total']['cpu_millis'] - proof['reserve']['cpu_millis']:
            raise ValueError('Unknown commands must reserve the complete managed CPU budget')
    if workers is not None:
        declared = request.get('workers')
        if type(declared) is not int or declared < workers or resources.cpu_millis < declared * 1000:
            raise ValueError('Full-capacity session does not cover actual unchanged Blender workers')
    if kind == 'compile' and resources.cpu_millis < 3000:
        raise ValueError('Full-capacity compile reservation must cover the existing three workers')
    if not math.isfinite(limit_gib) or limit_gib <= 0 or resources.memory_mib < math.ceil(limit_gib * 1024):
        raise ValueError('Full-capacity session reservation does not cover the actual guard ceiling')


def configured_session(*, kind, limit_gib, timeout, folder=None, purpose=None, config=None, performance=False,
                       command=None):
    """@cc [owner:fontanierh,label:safety] configured-capacity-never-falls-back
    A configured common launcher MUST refuse invalid profiles or unavailable admission. The full
    reservation MUST cover its existing guard ceiling; profiles MUST NOT raise that guard limit or
    silently change worker counts. Every request MUST claim its own checkout's named lock.
    Performance requests MUST preserve their explicit exclusion flag in the broker request.
    """
    if type(performance) is not bool:
        raise ValueError('capacity performance request must be a boolean')
    from . import capacity_compat
    barrier = capacity_compat.read()
    selected = config or os.environ.get('ATELIER_CAPACITY_CLIENT')
    path = Path(selected) if selected is not None else DEFAULT_CONFIG
    try:
        path.lstat()
    except FileNotFoundError:
        if selected is None:
            if barrier is not None:
                raise ValueError('A capacity cutover exists; missing client configuration cannot fall back to slots')
            return None
        raise ValueError('configured capacity client file is missing') from None
    value = read_configuration(path)
    bridge = (isinstance(value, dict) and set(value) == {'schema', 'socket', 'profiles'}
              and type(value.get('schema')) is int and value['schema'] == 1)
    full = (isinstance(value, dict) and set(value) == {'schema', 'socket', 'profiles', 'cutover'}
            and type(value.get('schema')) is int and value['schema'] == 2)
    if (not (bridge or full) or not isinstance(value['socket'], str)
            or not Path(value['socket']).is_absolute() or not isinstance(value['profiles'], dict)):
        raise ValueError('unsupported capacity client configuration')
    if bridge and barrier is not None:
        raise ValueError('A sealed capacity cutover refuses legacy bridge clients')
    proof = None
    if full:
        if Path(value['cutover']) != capacity_compat.DEFAULT_RECORD:
            raise ValueError('Full capacity must use the machine default compatibility record')
        proof = capacity_compat.verify(value['cutover'])
        if value['socket'] != proof['socket']:
            raise ValueError('Capacity endpoint differs from the sealed machine policy')
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
    if full:
        workers = _worker_profile(command)
        exclusive = performance or kind in ('game', 'compile') or workers is None
        budget = proof['total']['cpu_millis'] - proof['reserve']['cpu_millis']
        floor = workers * 1000 if workers is not None else budget
        if kind == 'compile':
            floor = max(floor, 3000)  # Existing UBT/compiler tuning remains three workers.
        resources = replace(resources, cpu_millis=max(resources.cpu_millis, floor))
        performance = exclusive
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
                   seconds=math.ceil(timeout) if timeout > 0 else 300, performance=performance)
    if full and workers is not None:
        request['workers'] = workers
    return AdmissionSession(value['socket'], request, **({'cutover': value['cutover']} if full else {}))
