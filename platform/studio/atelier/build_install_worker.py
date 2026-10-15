"""Private guarded installation and closed registry worker; no public native restoration CLI."""
import fcntl
import os
from pathlib import Path
import re
import stat
import sys

from . import build_install as install, capacity_protocol as wire, paths


def _parent(value):
    parent = wire.identity(value)
    child = (os.getpid(), wire.process_start(os.getpid()))
    if os.getppid() != parent[0] or not wire.live(parent) or not wire.direct_child(parent, child):
        raise install.InstallError('Package worker is not the bound controller child')
    return child


def _spec(descriptor):
    """@cc [owner:fontanierh,label:safety] guarded-package-request
    Installation MUST accept only the private read-only unlinked request inherited by the actual
    controller child. The source, nonce, checkout and recovery transaction MUST remain bound; a
    caller assertion or alternate command MUST NOT substitute for the normal guarded lifecycle.
    """
    info = os.fstat(descriptor)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 0
            or stat.S_IMODE(info.st_mode) != 0o400 or info.st_size > install.MAX_JSON
            or fcntl.fcntl(descriptor, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY):
        raise install.InstallError('Package worker requires its private read-only inherited request')
    try:
        value = install._decode(os.pread(descriptor, install.MAX_JSON + 1, 0))
    finally:
        os.close(descriptor)
    install._fields(value, ('schema', 'operation', 'nonce', 'parent', 'repo', 'game', 'snapshot',
                            'snapshot_sha256', 'source', 'source_pin', 'transaction'))
    if (type(value['schema']) is not int or value['schema'] != 1
            or value['operation'] not in ('install', 'recover')
            or type(value['nonce']) is not str or not re.fullmatch('[0-9a-f]{32}', value['nonce'])
            or value['repo'] != str(paths.REPO) or install._digest(value['snapshot']) != value['snapshot_sha256']):
        raise install.InstallError('Package worker request has a foreign source, nonce or scope')
    _parent(value['parent'])
    return value


def _install(descriptor):
    value = _spec(descriptor)
    scope = install.Scope(paths.REPO, value['game'])
    if value['operation'] == 'recover':
        journal = install._journal(scope)
        if journal['nonce'] != value['transaction'] or journal['snapshot_sha256'] != value['snapshot_sha256']:
            raise install.InstallError('Recovery request differs from its durable transaction')
        install._execute(scope, resume=True)
    else:
        if value['transaction'] != value['nonce']:
            raise install.InstallError('Install request has a mismatched transaction identity')
        source = Path(value['source'])
        if install._directory(source) != value['source_pin']:
            raise install.InstallError('Package source root changed before the guarded worker began')
        install._execute(scope, value['snapshot'], source, nonce=value['nonce'])


def _registry():
    value = install._decode(sys.stdin.buffer.read(install.MAX_JSON + 1))
    install._fields(value, ('schema', 'backend', 'nonce', 'repo', 'game', 'content_pin', 'parent', 'child'))
    child = _parent(value['parent'])
    if (type(value['schema']) is not int or value['schema'] != 1 or value['backend'] != install.BACKEND
            or list(child) != value['child']):
        raise install.InstallError('Registry request belongs to another supported query process')
    scope = install.Scope(Path(value['repo']), value['game'])
    journal = install._journal(scope)
    if journal['phase'] != 'registry-pending' or journal['nonce'] != value['nonce']:
        raise install.InstallError('Registry query does not match a pending package transaction')
    result = install.registry_catalog(scope, value)
    result.update(parent=value['parent'], child=list(child))
    sys.stdout.buffer.write(install._encode(result))
    sys.stdout.buffer.flush()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if len(argv) == 2 and argv[0] == 'install':
            _install(int(argv[1]))
        elif argv == ['registry']:
            _registry()
        else:
            raise install.InstallError('A bound internal worker request is required')
        return 0
    except (OSError, ValueError, KeyError, TypeError, wire.CapacityError, install.InstallError) as error:
        print(f'Package worker refused: {error}', file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
