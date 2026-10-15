"""Durable compatibility barrier for full capacity admission.

Legacy launchers open the existing lane files for writing. Sealing those same inodes
refuses fresh legacy opens, but cannot revoke a preopened descriptor. Full activation
therefore requires an authoritative new OS boot after the seal, never a process scan.
"""
from contextlib import ExitStack
from dataclasses import asdict
import errno
import fcntl
import os
from pathlib import Path
import re
import stat
import uuid

from . import capacity_protocol as wire

DEFAULT_RECORD = Path.home() / '.cache/atelier/capacity/cutover.json'
PROTOCOL = 3


def read(path=None):
    path = Path(path or DEFAULT_RECORD)
    try:
        path.lstat()
    except FileNotFoundError:
        return None
    parent = path.parent.stat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid() or parent.st_mode & 0o077:
        raise wire.CapacityError('Capacity cutover directory must be private and owned')
    value = wire.decode(wire.private_file(path, limit=wire.MAX_FRAME))
    wire.fields(value, ('schema', 'state', 'activation_id', 'seal_boot_id', 'policy_sha256',
                        'socket', 'disk_pool', 'locks', 'total', 'reserve', 'protocol'))
    if (type(value['schema']) is not int or value['schema'] != 1
            or type(value['protocol']) is not int or value['protocol'] != PROTOCOL
            or value['state'] not in ('preparing', 'sealed', 'active')):
        raise wire.CapacityError('Unsupported capacity cutover record')
    for key in ('activation_id', 'seal_boot_id', 'policy_sha256', 'socket', 'disk_pool'):
        wire.text(value[key], maximum=4096)
    try:
        if str(uuid.UUID(value['seal_boot_id'])) != value['seal_boot_id']:
            raise ValueError
        if uuid.UUID(value['activation_id']).hex != value['activation_id']:
            raise ValueError
    except ValueError:
        raise wire.CapacityError('Invalid cutover activation or boot identity') from None
    if (re.fullmatch('[0-9a-f]{64}', value['policy_sha256']) is None
            or not Path(value['socket']).is_absolute() or not Path(value['disk_pool']).is_absolute()):
        raise wire.CapacityError('Invalid cutover policy or endpoint')
    wire.fields(value['locks'], ('big', 'small', 'fitting'))
    for item in value['locks'].values():
        wire.fields(item, ('path', 'device', 'inode', 'ctime_ns', 'mode'))
        if not Path(wire.text(item['path'], maximum=4096)).is_absolute():
            raise wire.CapacityError('Capacity lane path must be absolute')
        for key in ('device', 'inode', 'ctime_ns', 'mode'):
            wire.integer(item[key])
    if wire.resources(value['reserve']).excess(wire.resources(value['total'])):
        raise wire.CapacityError('Cutover reserve exceeds total capacity')
    return value


def _pin(path, info):
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1):
        raise wire.CapacityError('Capacity lanes must be owned single-link regular files')
    return dict(path=str(path), device=info.st_dev, inode=info.st_ino,
                ctime_ns=info.st_ctime_ns, mode=stat.S_IMODE(info.st_mode))


def _write_denied(path):
    try:
        fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    except OSError as error:
        if error.errno in (errno.EACCES, errno.EPERM):
            return
        raise wire.CapacityError('Cannot establish the legacy write-open barrier') from None
    else:
        os.close(fd)
        raise wire.CapacityError('Legacy write-open is still permitted, including through an ACL')


def verify(path=None, *, policy_sha256=None, active=True, handles=None):
    """@cc [owner:fontanierh,label:safety] durable-capacity-compatibility
    Full capacity MUST require unchanged sealed single-link legacy inodes, actual same-UID
    write-open denial and a positive OS boot change after sealing. Missing observations,
    a process scan or an operator assertion MUST NOT establish closure of preopened FDs.
    No failure MAY unseal the lane files or fall back to legacy admission.
    """
    if Path(path or DEFAULT_RECORD) != DEFAULT_RECORD or os.environ.get('ATELIER_RENDER_LOCK'):
        raise wire.CapacityError('Full capacity requires the fixed machine compatibility paths')
    value = read(path)
    if value is None or value['state'] != ('active' if active else 'sealed'):
        raise wire.CapacityError('Capacity cutover is not active' if active else 'Capacity cutover is not sealed')
    if policy_sha256 is not None and value['policy_sha256'] != policy_sha256:
        raise wire.CapacityError('Capacity cutover policy differs from the reviewed broker policy')
    if wire.boot_id() == value['seal_boot_id']:
        raise wire.CapacityError('Full capacity requires a verified new OS boot after sealing legacy lanes')
    from .safety.render_lock import lock_paths
    if {name: str(p) for name, p in lock_paths().items()} != {name: item['path'] for name, item in value['locks'].items()}:
        raise wire.CapacityError('Capacity lane paths differ from the fixed compatibility barrier')
    for name, item in value['locks'].items():
        path = Path(item['path'])
        for parent in path.parents:
            if parent.is_symlink() and str(parent) not in ('/tmp', '/var', '/etc'):
                raise wire.CapacityError('Capacity lane ancestors cannot be symlinks')
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        try:
            pin = _pin(path, os.fstat(fd))
            if pin != item or pin['mode'] != 0o400:
                raise wire.CapacityError('Capacity lane inode, seal or change identity was modified')
            if handles is not None and _pin(path, os.fstat(handles[name].fileno())) != item:
                raise wire.CapacityError('Shared capacity lock belongs to a replaced lane inode')
            _write_denied(path)
            if _pin(path, os.lstat(path)) != item:
                raise wire.CapacityError('Capacity lane changed during verification')
        finally:
            os.close(fd)
    return value


def refuse_unmanaged(purpose):
    if read() is not None:
        raise wire.CapacityError(f'{purpose} has no full-capacity lifecycle; use a migrated guarded entry point')


def _save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    info = path.parent.stat()
    if path.parent.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise wire.CapacityError('Capacity cutover directory must be private and owned')
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(wire.encode(value))
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _policy(config):
    from .capacity_broker import load_config
    settings = load_config(config)
    if settings.get('mode') != 'capacity' or Path(settings['cutover']) != DEFAULT_RECORD:
        raise wire.CapacityError('Full capacity needs the machine default cutover record')
    return settings


def prepare(config):
    """Seal only under every existing exclusive mutex; never remove, replace or auto-unseal them."""
    from .safety.render_lock import lock_paths
    settings = _policy(config)
    if os.environ.get('ATELIER_RENDER_LOCK'):
        raise wire.CapacityError('A cutover cannot seal overridden legacy lane paths')
    if read() is not None:
        raise wire.CapacityError('A cutover record already exists; do not overwrite its closure evidence')
    paths = lock_paths()
    big = paths['big']
    with ExitStack() as stack:
        admission = stack.enter_context(big.with_name(f'{big.stem}.admission{big.suffix}').open('a+'))
        fcntl.flock(admission, fcntl.LOCK_EX | fcntl.LOCK_NB)
        handles = {}
        for name, path in paths.items():
            fd = os.open(path, os.O_RDWR | os.O_NONBLOCK | os.O_NOFOLLOW)
            handle = stack.enter_context(os.fdopen(fd, 'r+b'))
            _pin(path, os.fstat(fd))
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            handles[name] = handle
        value = dict(schema=1, state='preparing', activation_id=uuid.uuid4().hex,
                     seal_boot_id=wire.boot_id(), policy_sha256=settings['policy_sha256'],
                     protocol=PROTOCOL, socket=str(settings['state_directory'] / 'broker.sock'),
                     disk_pool=str(settings['disk_pool']),
                     total=asdict(settings['total']), reserve=asdict(settings['reserve']),
                     locks={name: _pin(paths[name], os.fstat(h.fileno())) for name, h in handles.items()})
        _save(DEFAULT_RECORD, value)  # A partial seal must already refuse upgraded launchers.
        for handle in handles.values():
            os.fchmod(handle.fileno(), 0o400)
            os.fsync(handle.fileno())
        value['locks'] = {name: _pin(paths[name], os.fstat(h.fileno())) for name, h in handles.items()}
        for path in paths.values():
            _write_denied(path)
        value['state'] = 'sealed'
        _save(DEFAULT_RECORD, value)
    return value


def activate(config):
    settings = _policy(config)
    value = verify(policy_sha256=settings['policy_sha256'], active=False)
    with ExitStack() as stack:
        handles = {}
        for name, item in value['locks'].items():
            fd = os.open(item['path'], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
            handle = stack.enter_context(os.fdopen(fd, 'rb'))
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            handles[name] = handle
        value = verify(policy_sha256=settings['policy_sha256'], active=False, handles=handles)
        value['state'] = 'active'
        _save(DEFAULT_RECORD, value)
    return value
