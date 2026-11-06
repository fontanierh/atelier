"""Live sessions: which running game an `atelier live` command reaches.

`atelier play` writes one record per game it launches with the live bridge, in this machine's
`~/.cache/atelier/live-sessions/<session>.json` (`ATELIER_CACHE` moves it), and removes it when the launcher exits.
A record names the session (a random ID the game gets as `-livesession=ID`), the game and its Unreal project, the
checkout and its revision, the loopback port the bridge listens on (`-liveport=N`, a free port distinct from every other
live session), the launcher process (PID and start time) and the owning agent (`ATELIER_AGENT`).

Before any command the client asks the bridge's `GET /identity` and checks it against the record: the same session ID,
a process descending from the recorded launcher, the same project file in the same checkout. Any mismatch, a stale
launcher, or nothing answering is an error; nothing falls back to another game or to the old fixed port 8830.

Records hold machine-local paths and stay in the cache; they are never committed.
"""
import contextlib, hashlib, json, os, secrets, socket, subprocess, time, urllib.error, urllib.request
from pathlib import Path

from . import paths

SCHEMA = 1
LEGACY_PORT = 8830   # the bridge's configured default; a session never allocates it


class SessionError(RuntimeError):
    """A live command has no verified target. The message says why and what to pass instead."""


def directory(create=True):
    return paths.cache_dir('live-sessions', create=create)


def checkout_root(path=None):
    return Path(path or paths.REPO).resolve()


def checkout_id(path=None):
    """A stable identity for a checkout on this machine: a hash of its real path (two worktrees always differ)."""
    return hashlib.sha256(str(checkout_root(path)).encode()).hexdigest()[:16]


def revision(root):
    try:
        out = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ''
    return out.stdout.strip() if out.returncode == 0 else ''


# ------------------------------------------------------------------ processes
def process_start(pid):
    """The start time of process `pid`, or None when no such process exists. Raises when it cannot tell."""
    try:
        from atelier.harness.safety import process_tree
    except (ImportError, OSError, AttributeError):   # not macOS: the libproc helper is unavailable
        out = subprocess.run(['ps', '-o', 'lstart=', '-p', str(int(pid))], capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    return process_tree.started(int(pid))


def parent(pid):
    out = subprocess.run(['ps', '-o', 'ppid=', '-p', str(int(pid))], capture_output=True, text=True, timeout=10)
    text = out.stdout.strip()
    return int(text) if text.isdigit() else None


def descends(pid, ancestor, limit=32):
    """True when `pid` is `ancestor` or one of its descendants."""
    for _ in range(limit):
        if pid is None or pid <= 1:
            return False
        if pid == ancestor:
            return True
        pid = parent(pid)
    return False


def launcher_state(record):
    """'live' while the recorded launcher is the same process, 'gone' once it provably is not (no such PID, or the PID
    now belongs to a process with another start time), 'unknown' when that cannot be determined."""
    launcher = record.get('launcher') or {}
    try:
        start = process_start(launcher['pid'])
    except (KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError):
        return 'unknown'
    if start is None or start != launcher.get('start'):
        return 'gone'
    return 'live'


# ------------------------------------------------------------------ records
def _path(session):
    if not session or not all(c in '0123456789abcdef' for c in session):
        raise SessionError(f'malformed session ID {session!r}')
    return directory() / f'{session}.json'


def _write(record):
    path = _path(record['session'])
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(record, indent=1, sort_keys=True) + '\n')
    temporary.replace(path)


def load_all():
    """Every record on this machine: (record, None), or (None, problem) for a file that is not a valid record."""
    folder = directory(create=False)
    if not folder.is_dir():
        return []
    found = []
    for path in sorted(folder.glob('*.json')):
        try:
            record = json.loads(path.read_text())
            if record.get('schema') != SCHEMA or record.get('session') != path.stem:
                raise ValueError('not a session record')
            found.append((record, None))
        except (OSError, ValueError, AttributeError) as error:
            found.append((None, f'{path.name}: {error}'))
    return found


def records():
    return [record for record, _ in load_all() if record is not None]


@contextlib.contextmanager
def _locked():
    """Serializes port allocation between launchers on this machine."""
    import fcntl
    fd = os.open(directory() / '.lock', os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def port_free(port):
    with socket.socket() as s:
        try:
            s.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def create(game, uproject, *, port=None, task='', checkout=None, env=None):
    """Write the record for a game about to start from `checkout` (default: this one) and return it. `port` keeps an
    explicitly requested -liveport; otherwise a free loopback port no other live session uses is allocated."""
    env = os.environ if env is None else env
    root = checkout_root(checkout)
    project = Path(uproject).resolve()
    with _locked():
        taken = {r.get('port') for r in records() if launcher_state(r) != 'gone'}
        if port is None:
            for _ in range(64):
                port = free_port()
                if port not in taken and port != LEGACY_PORT:
                    break
            else:
                raise SessionError('no free loopback port for the live bridge')
        elif port in taken:
            raise SessionError(f'loopback port {port} already belongs to another live session (atelier live sessions)')
        pid = os.getpid()
        record = dict(
            schema=SCHEMA, session=secrets.token_hex(16), game=game,
            project=(project.relative_to(root).as_posix() if project.is_relative_to(root) else str(project)),
            project_name=project.stem,
            checkout=str(root), checkout_id=checkout_id(root), revision=revision(root), port=int(port),
            launcher=dict(pid=pid, start=process_start(pid)),
            agent=env.get('ATELIER_AGENT', ''), task=task, created=time.strftime('%Y-%m-%dT%H:%M:%S%z'))
        _write(record)
    return record


def launch_args(record):
    """The Unreal arguments that put the bridge on the record's port and give it the record's session ID."""
    return [f'-liveport={record["port"]}', f'-livesession={record["session"]}']


@contextlib.contextmanager
def launched(game, uproject, extra, *, task='', checkout=None):
    """Around a launcher's game run: yields (Unreal arguments, record) and removes the record when the run ends, however
    it ends. A `-liveport=N` in `extra` is kept as the session's port; `-nolive` means no bridge and no record."""
    extra = list(extra)
    lowered = [a.lower() for a in extra]
    if '-nolive' in lowered:
        yield extra, None
        return
    if any(a.startswith('-livesession=') for a in lowered):
        raise SessionError('pass no -livesession: the launcher assigns each game its session')
    ports = [a.split('=', 1)[1] for a in lowered if a.startswith('-liveport=')]
    if len(ports) > 1 or (ports and not ports[0].isdigit()) or (ports and not 0 < int(ports[0]) < 65536):
        raise SessionError('pass at most one -liveport=N with N from 1 to 65535')
    record = create(game, uproject, port=int(ports[0]) if ports else None, task=task, checkout=checkout)
    try:
        yield [*extra, *(a for a in launch_args(record) if not (ports and a.startswith('-liveport=')))], record
    finally:
        remove(record)


def remove(record):
    """Remove a record this process wrote (the launcher on exit)."""
    if record is not None:
        _path(record['session']).unlink(missing_ok=True)


def prune():
    """Remove the records whose launcher is provably gone. Never signals any process. Returns the removed records."""
    removed = []
    with _locked():
        for record in records():
            if launcher_state(record) == 'gone':
                _path(record['session']).unlink(missing_ok=True)
                removed.append(record)
    return removed


# ------------------------------------------------------------------ the handshake
def identity(port, timeout=2.):
    """What the bridge on loopback `port` says it is (GET /identity)."""
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{int(port)}/identity', timeout=timeout) as r:
            value = json.loads(r.read().decode())
    except urllib.error.HTTPError as error:
        raise SessionError(f'loopback port {port} answers without a live identity (HTTP {error.code}): '
                           'a game from before live sessions, or not a game') from None
    except (OSError, ValueError) as error:
        raise SessionError(f'nothing answers on loopback port {port}: {error}') from None
    if not isinstance(value, dict):
        raise SessionError(f'loopback port {port} answered a malformed identity')
    return value


def verify(record, timeout=2.):
    """@cc [owner:fontanierh,label:safety] live-session-target
    A live command MUST reach only a process whose /identity carries the record's session ID, descends from the
    record's still-live launcher (PID and start time) and runs the record's project file in the record's checkout.
    Any mismatch, missing identity or stale launcher MUST be an error, never a fallback to another session or port.
    Pruning MUST remove only records whose launcher is provably gone and MUST NOT signal any process.

    Prove that the process on the record's port is the game the record describes; return its identity."""
    session, port = record['session'], record['port']
    state = launcher_state(record)
    if state != 'live':
        raise SessionError(f'session {session} is stale: its launcher (PID {record.get("launcher", {}).get("pid")}) '
                           f'is {"gone" if state == "gone" else "not verifiable"}; `atelier live sessions --prune` '
                           'removes gone records')
    try:
        found = identity(port, timeout)
    except SessionError as error:
        raise SessionError(f'session {session}: {error}') from None
    if found.get('session') != session:
        raise SessionError(f'session {session}: loopback port {port} is held by another process '
                           f'(session {found.get("session") or "none"}, PID {found.get("pid")})')
    pid = found.get('pid')
    if type(pid) is float and pid.is_integer():
        pid = int(pid)
    if type(pid) is not int or not descends(pid, record['launcher']['pid']):
        raise SessionError(f'session {session}: the process on port {port} (PID {pid}) was not started by the '
                           f'recorded launcher (PID {record["launcher"]["pid"]})')
    expected = (Path(record['checkout']) / record['project']).resolve()
    reported = found.get('project_file') or ''
    if found.get('project') != record['project_name'] or not reported or Path(reported).resolve() != expected:
        raise SessionError(f'session {session}: the game on port {port} runs project {found.get("project")!r} '
                           f'from {reported or "an unknown file"}, not {expected}')
    return found


def select(session=None, game=None, checkout=None):
    """The one live record a command targets. With `session` (an ID or a unique prefix), that record; otherwise the one
    live session of `game` (any game when None) launched from `checkout` (default: this checkout). Errors otherwise."""
    root = checkout_root(checkout)
    mine = checkout_id(root)
    known = records()
    if session:
        matches = [r for r in known if r['session'].startswith(session)]
        if not matches:
            raise SessionError(f'no live session {session} on this machine (atelier live sessions)')
        if len(matches) > 1:
            raise SessionError(f'session prefix {session} is ambiguous: ' + ', '.join(r['session'] for r in matches))
        record = matches[0]
        if record.get('checkout_id') != mine:
            raise SessionError(f'session {record["session"]} was launched from {record.get("checkout")}, not {root}; '
                               'pass --checkout PATH to target another checkout')
        if game and record.get('game') != game:
            raise SessionError(f'session {record["session"]} runs {record.get("game")}, not {game}')
        return record
    candidates = [r for r in known if r.get('checkout_id') == mine and (not game or r.get('game') == game)
                  and launcher_state(r) == 'live']
    if len(candidates) == 1:
        return candidates[0]
    what = f'{game} ' if game else ''
    if not candidates:
        raise SessionError(f'no live {what}session launched from {root}: start one with `atelier play GAME`, '
                           'or pass --session ID (or --port N for a game without a session record)')
    raise SessionError(f'{len(candidates)} live {what}sessions launched from {root}; pass --session ID: '
                       + ', '.join(f'{r["session"][:12]} ({r["game"]}, port {r["port"]})' for r in candidates))
