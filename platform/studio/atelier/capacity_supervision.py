"""Install explicit macOS login/crash supervision for the machine capacity broker.

Installing the broker does not enable clients. Client migration uses a separate private
configuration only after the broker and guarded launch path have been validated.
"""
import hashlib
import os
from pathlib import Path
import plistlib
import stat
import subprocess
import sys

from . import paths

LABEL = 'com.atelier.capacity'


def configuration(config):
    from .capacity_broker import load_config
    from .capacity_protocol import MAX_FRAME, private_file
    config = Path(config)
    raw = private_file(config, limit=MAX_FRAME)
    settings = load_config(config)
    if private_file(config, limit=MAX_FRAME) != raw:
        raise ValueError('capacity configuration changed while preparing supervision')
    state = Path(settings['state_directory'])
    if (not state.is_absolute() or not settings['disk_pool'].is_absolute() or not settings['disk_pool'].is_dir()
            or settings['reserve'].excess(settings['total'])):
        raise ValueError('invalid capacity paths or host reserve')
    return dict(Label=LABEL, ProgramArguments=[sys.executable, '-m', 'atelier.cli', 'capacity', 'serve', str(config)],
                WorkingDirectory=str(paths.REPO), EnvironmentVariables={
                    'PYTHONPATH': str(paths.STUDIO), 'ATELIER_CAPACITY_SERVICE_CONFIG_SHA256': hashlib.sha256(raw).hexdigest()},
                RunAtLoad=True, KeepAlive=True, ThrottleInterval=5,
                StandardOutPath=str(state / 'broker.log'), StandardErrorPath=str(state / 'broker.log'))


def install(config, *, echo=print):
    """Do not replace or interrupt a running broker; a config change requires an explicit drain."""
    if sys.platform != 'darwin':
        raise ValueError('capacity supervise uses macOS launchd; use your service manager on other systems')
    value = configuration(config)
    path = Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist')
    domain = f'gui/{os.getuid()}'
    result = subprocess.run(['launchctl', 'print', domain + '/' + LABEL], capture_output=True, text=True, timeout=8)
    if result.returncode == 0:
        if not path.exists() or plistlib.loads(path.read_bytes()) != value:
            raise ValueError('existing capacity service differs; drain and retire it before changing configuration')
        echo('Capacity broker is already supervised; client migration is separate.')
        return 0
    # launchd opens its log before starting Python. Create only the configured private
    # directory, never a client activation file or a scheduler grant.
    state = Path(value['StandardOutPath']).parent
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = state.lstat()
    if state.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('capacity state directory must be private and owned')
    descriptor = os.open(state / 'broker.log', os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
                or info.st_mode & 0o077):
            raise ValueError('capacity service log must be a private owned single-link regular file')
    finally:
        os.close(descriptor)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.plist.tmp').open('xb') as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(plistlib.dumps(value))
        handle.flush()
        os.fsync(handle.fileno())
    path.with_suffix('.plist.tmp').replace(path)
    result = subprocess.run(['launchctl', 'bootstrap', domain, str(path)], capture_output=True, text=True, timeout=8)
    if result.returncode:
        raise ValueError('could not start capacity supervision: ' + result.stderr.strip())
    echo('Capacity broker supervision installed. Clients have not been enabled.')
    return 0
