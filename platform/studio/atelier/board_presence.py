"""Whether each agent's own session is working or waiting, read from that session's native runtime.

An agent's board status line says what it is doing; its session's state shows whether it is doing anything. The web
board uses both: an agent whose session has waited QUIET seconds is shown free for work whatever its line says, and
gets one note (per status line it set) asking it to bring the line up to date. This module only reads sessions: it
never wakes, steers or signals one, and the note travels like any other board message.
"""
import json
import plistlib
import re
import sys
import threading
import time
from pathlib import Path

from .board_store import database, post, root

QUIET = 600
WATCH = 'status-watch'
REGISTRY = Path.home() / '.claude/sessions'
LAUNCH_AGENTS = Path.home() / 'Library/LaunchAgents'


def transport(label, folder=None):
    """How a supervised listener wakes its agent, from the listener's launchd job: the wake command's arguments."""
    try:
        with ((folder or LAUNCH_AGENTS) / f'{label}.plist').open('rb') as stream:
            arguments = plistlib.load(stream)['ProgramArguments']
        command = json.loads(arguments[arguments.index('--notify') + 1])
    except (OSError, ValueError, KeyError, IndexError, TypeError, plistlib.InvalidFileException):
        return None
    if not isinstance(command, list):
        return None
    option = lambda name: command[command.index(name) + 1] if name in command[:-1] else None  # noqa: E731
    if 'notify-claude' in command and option('--session-dir'):
        return {'kind': 'claude', 'dir': option('--session-dir')}
    if 'notify-codex' in command and option('--thread'):
        return {'kind': 'codex', 'thread': option('--thread'), 'codex': option('--codex') or 'codex',
                'socket': option('--socket')}
    return None


def claude_state(session_dir, registry=None):
    """('busy' or 'idle', since) for the one live Claude session in session_dir, or None."""
    from .board_claude import process_start
    want, found = str(Path(session_dir).resolve()), []
    for path in (registry or REGISTRY).glob('*.json'):
        if not path.stem.isdigit():
            continue
        try:
            record = json.loads(path.read_text())
            if record.get('cwd') == want and record.get('pid') == int(path.stem) \
                    and record.get('procStart') == process_start(record['pid']):
                found.append(record)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    if len(found) != 1 or found[0].get('status') not in ('busy', 'idle'):
        return None
    since = found[0].get('statusUpdatedAt')
    return found[0]['status'], since / 1000 if isinstance(since, (int, float)) else None


def codex_state(thread, codex='codex', sock=None):
    """('busy' or 'idle', None) for an existing Codex thread, read through the running daemon, or None."""
    from . import board_codex
    try:
        with board_codex.Client(codex, sock) as client:
            status = client.call('thread/read', {'threadId': thread, 'includeTurns': False})['thread']
    except (board_codex.TransportError, KeyError, TypeError):
        return None
    status = {'active': 'busy', 'idle': 'idle'}.get((status.get('status') or {}).get('type'))
    return (status, None) if status else None


def session_state(label):
    way = transport(label)
    if way is None:
        return None
    if way['kind'] == 'claude':
        return claude_state(way['dir'])
    return codex_state(way['thread'], way['codex'], way['socket'])


def render_floor():
    """The render board's human-maintained scheduling sections, and the live render lock holders. The web board's
    server reads the same file and locks the same way."""
    from .safety import render_lock
    try:
        text = (root() / 'render-board.md').read_text()
    except FileNotFoundError:
        text = ''
    # Telemetry markup is advisory; return human-maintained scheduling sections separately.
    text = re.sub(r'<!-- atelier-coordinator:start -->.*?<!-- atelier-coordinator:end -->', '', text, flags=re.S)
    sections = {match[1]: match[2].strip() for match in re.finditer(
        r'^## (Holding|Waiting|Handoffs|Log)\s*\n(.*?)(?=^## |\Z)', text, re.M | re.S)}
    # Use the owning library's PID/start validation; stale lock text is never a live owner.
    holders = {}
    for slot, path in (('big', render_lock.lock_path()), ('small', render_lock.small_lock_path())):
        holder = render_lock.read_holder(path)
        if holder:
            holders[slot] = {'purpose': holder.get('purpose', 'Render job'), 'kind': holder.get('kind', 'job'),
                             'checkout': Path(holder.get('repo') or holder.get('checkout') or '').name,
                             'time': holder.get('time')}
    return sections, holders


# A Holding or Waiting line starts with its timestamp and then the agent it belongs to.
SCHEDULED = re.compile(r'^\s*-\s+\d{4}-\d\d-\d\d[ T]\d\d:\d\d(?::\d\d)?(?:\s+[A-Z]{2,5})?\s+([A-Za-z0-9][\w.-]*)', re.M)


def engaged(sections, holders, checkouts):
    """Agents with render work in flight, which waits on a background job with the session idle: those named on a
    Holding or Waiting line of the render board, or holding a live render lock from their checkout."""
    named = {match[1] for part in ('Holding', 'Waiting') for match in SCHEDULED.finditer(sections.get(part, ''))}
    locked = {holder['checkout'] for holder in holders.values() if holder.get('checkout')}
    return named | {agent for agent, checkout in checkouts.items() if checkout and checkout in locked}


def free_line(task):
    return not task or task.strip().lower() == 'idle'


def step(now=None, read=session_state, floor=None):
    """Record every supervised agent's session state, and leave one note for an agent quiet for QUIET seconds whose
    status line still names work and that has no render work in flight. Returns the agents noted."""
    now = now or time.time()
    floor = floor or render_floor
    with database() as db:
        rows = [dict(row) for row in db.execute(
            'SELECT agent, supervised, checkout, task, task_at, session, session_since FROM subscribers '
            'WHERE stop=0 AND removed=0 AND supervised IS NOT NULL')]
        exempt = {row[0] for row in db.execute('SELECT agent FROM operator_tasks WHERE closed IS NULL')}
    sections, holders = floor()
    exempt |= engaged(sections, holders, {row['agent']: Path(row['checkout'] or '').name for row in rows})
    noted = []
    for row in rows:
        state = read(row['supervised'])
        status, since = state if state else (None, None)
        if status is None:
            since = None
        elif status != row['session']:
            since = since or now
        elif since is None:
            since = row['session_since']
        with database() as db:
            db.execute('UPDATE subscribers SET session=?, session_since=? WHERE agent=?', (status, since, row['agent']))
        if (status == 'idle' and since and now - since >= QUIET and not free_line(row['task'])
                and row['agent'] not in exempt):
            key = f"{WATCH}:{row['agent']}:{row['task_at'] or 0}"
            with database() as db:
                if db.execute('SELECT 1 FROM messages WHERE dedup=?', (key,)).fetchone():
                    continue
            agent = row['agent']
            post(WATCH, f'Your session has been waiting {int((now - since) // 60)} min, but your board status still '
                        f'reads "{row["task"]}". If that work is done, run `atelier board task --agent {agent} idle`; '
                        'if you are blocked on the operator, open an operator task instead. If it is still accurate '
                        '(a long job is running), ignore this: it is sent once per status.', agent, dedup=key)
            noted.append(agent)
    return noted


class Presence(threading.Thread):
    """Runs step every interval seconds inside the web board, so it reads sessions without a process of its own."""

    def __init__(self, interval=60):
        super().__init__(daemon=True, name='board-presence')
        self.interval = interval

    def run(self):
        while True:
            try:
                step()
            except Exception as error:  # noqa: BLE001  (a bad read must not stop the board serving)
                print(f'presence: {error}', file=sys.stderr, flush=True)
            time.sleep(self.interval)

