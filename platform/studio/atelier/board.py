"""Durable machine-local agent messages and lightweight background subscriptions.

The Markdown render board remains the scheduling ledger. Messages wake its owners;
this module never acquires render slots, launches heavy work or signals processes.
"""
import fcntl
import hashlib
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from . import paths

TOPICS = ('info', 'request', 'handoff', 'blocked', 'release', 'evidence', 'ack', 'alert')


def agent_name(value):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', value):
        raise ValueError('agent names need 1–80 letters, digits, dots, underscores or hyphens')
    return value


def root():
    return paths.cache_dir()


@contextmanager
def database():
    db = sqlite3.connect(root() / 'agent-board.sqlite3', timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA foreign_keys=ON')
        db.executescript('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created REAL NOT NULL,
                sender TEXT NOT NULL, recipient TEXT NOT NULL, topic TEXT NOT NULL,
                body TEXT NOT NULL, reply_to INTEGER REFERENCES messages(id),
                dedup TEXT UNIQUE
            );
            CREATE TABLE IF NOT EXISTS observations (name TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS subscribers (
                agent TEXT PRIMARY KEY, cursor INTEGER NOT NULL DEFAULT 0,
                pid INTEGER, heartbeat REAL, checkout TEXT, stop INTEGER NOT NULL DEFAULT 0,
                error TEXT
            );
        ''')
        columns = {row['name'] for row in db.execute('PRAGMA table_info(subscribers)')}
        if 'supervised' not in columns:
            try:
                db.execute('ALTER TABLE subscribers ADD COLUMN supervised TEXT')
            except sqlite3.OperationalError:
                if 'supervised' not in {row['name'] for row in db.execute('PRAGMA table_info(subscribers)')}:
                    raise
        yield db
        db.commit()
    finally:
        db.close()


def post(sender, body, recipient='*', topic='info', reply_to=None, dedup=None):
    agent_name(sender)
    if recipient != '*':
        agent_name(recipient)
    if topic not in TOPICS or not body.strip() or len(body) > 8000:
        raise ValueError('use a known topic and a nonempty message of at most 8000 characters')
    with database() as db:
        if dedup:
            existing = db.execute('SELECT id FROM messages WHERE dedup=?', (dedup,)).fetchone()
            if existing:
                return existing['id']
        result = db.execute('''INSERT OR IGNORE INTO messages
            (created, sender, recipient, topic, body, reply_to, dedup) VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (time.time(), sender, recipient, topic, body, reply_to, dedup))
        if result.rowcount:
            return result.lastrowid
        return db.execute('SELECT id FROM messages WHERE dedup=?', (dedup,)).fetchone()['id']


def broadcast(sender, body, request_id, topic='request'):
    return send_web(sender, body, request_id, topic)


def send_web(sender, body, request_id, topic='request', recipient='*'):
    """Atomically address every non-stopped subscriber, including addressed-only listeners.

    A retry of the same request returns the original recipient snapshot. The dedup
    prefix lets the web UI display the addressed copies as one broadcast without
    changing existing delivery cursors or the ordinary '*' broadcast semantics.
    """
    agent_name(sender)
    if recipient != '*':
        if not isinstance(recipient, str):
            raise ValueError('choose a registered recipient')
        agent_name(recipient)
    if not isinstance(body, str) or not body.strip() or len(body) > 8000 or topic not in TOPICS:
        raise ValueError('use a known topic and a nonempty message of at most 8000 characters')
    try:
        key = str(uuid.UUID(request_id))
    except (ValueError, AttributeError, TypeError):
        raise ValueError('broadcast request_id must be a UUID') from None
    prefix = f'web-broadcast:{key}:'
    direct = f'web-direct:{key}:'
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        existing = [dict(row) for row in db.execute(
            'SELECT * FROM messages WHERE dedup LIKE ? OR dedup LIKE ? ORDER BY id', (prefix+'%', direct+'%'))]
        if existing:
            if (any(row['sender'] != sender or row['body'] != body or row['topic'] != topic for row in existing)
                    or (recipient == '*' and not existing[0]['dedup'].startswith(prefix))
                    or (recipient != '*' and (len(existing) != 1 or existing[0]['dedup'] != direct+recipient))):
                raise ValueError('this broadcast request_id already belongs to a different message')
            return existing
        agents = [row['agent'] for row in db.execute(
            'SELECT agent FROM subscribers WHERE stop=0 AND agent!=? ORDER BY agent', (sender,))]
        if recipient != '*':
            if recipient not in agents:
                raise ValueError('This agent is not registered or has been retired.')
            agents = [recipient]
            prefix = direct
        if not agents:
            raise ValueError('No agents are currently registered for broadcasts.')
        created = time.time()
        for agent in agents:
            agent_name(agent)
            db.execute('''INSERT INTO messages (created, sender, recipient, topic, body, dedup)
                VALUES (?, ?, ?, ?, ?, ?)''', (created, sender, agent, topic, body, prefix+agent))
        return [dict(row) for row in db.execute(
            'SELECT * FROM messages WHERE dedup LIKE ? ORDER BY id', (prefix+'%',))]


def messages(after=0, agent=None, limit=100, addressed_only=False):
    with database() as db:
        if agent:
            recipients = 'recipient=?' if addressed_only else "recipient IN ('*', ?)"
            rows = db.execute(f'SELECT * FROM messages WHERE id>? AND sender!=? AND {recipients} '
                              'ORDER BY id LIMIT ?', (after, agent, agent, limit))
        else:
            rows = db.execute('SELECT * FROM messages WHERE id>? ORDER BY id LIMIT ?', (after, limit))
        return [dict(row) for row in rows]


def notification(batch):
    # Keep argv comfortably bounded, even with long messages. The complete record stays in the board.
    lines = ['Atelier agent board: new messages (advisory coordination, not render admission).']
    for item in batch:
        lines.append(f"#{item['id']} {item['sender']} -> {item['recipient']} [{item['topic']}]: {item['body'][:600]}")
    lines.append('Read full messages with atelier board read; check render-board.md and live locks. '
                 'Acknowledge actionable handoffs through atelier board post --topic ack --reply-to ID. '
                 'Preserve first-ready age; never signal other owners or bypass safety.')
    return '\n'.join(lines)


def notify_command(value):
    command = json.loads(value)
    if not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command):
        raise ValueError('--notify must be a JSON array of executable and arguments')
    if '{message}' not in command:
        raise ValueError('--notify must include a separate {message} argument')
    return command


def deliver(batch, command=None, full=False):
    text = notification(batch)
    if command is None:
        print(text, flush=True)
        if full:
            for item in batch:
                print(json.dumps(item), flush=True)
    else:
        # No shell interpolation. Transport failures leave the cursor unchanged for retry.
        result = subprocess.run([text if x == '{message}' else x for x in command],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError(f'notification command exited {result.returncode}: {result.stderr[-1000:]}')


def poll(agent, command=None, addressed_only=False, full=False):
    with database() as db:
        row = db.execute('SELECT cursor FROM subscribers WHERE agent=?', (agent,)).fetchone()
    batch = messages(row['cursor'], agent, limit=20, addressed_only=addressed_only)
    if batch:
        if full:
            deliver(batch, command, full=True)
        else:
            deliver(batch, command)
        with database() as db:
            db.execute('UPDATE subscribers SET cursor=?, error=NULL WHERE agent=?', (batch[-1]['id'], agent))
    return len(batch)


def render_board_changes():
    """Bridge legacy handoffs to mailbox subscribers, ignoring the telemetry-only block."""
    path = root() / 'render-board.md'
    try:
        text = path.read_text()
    except FileNotFoundError:
        return
    text = re.sub(r'<!-- atelier-coordinator:start -->.*?<!-- atelier-coordinator:end -->',
                  '', text, flags=re.S)
    sections = {match[1]: hashlib.sha256(match[2].encode()).hexdigest()
                for match in re.finditer(r'^## (Holding|Waiting|Handoffs|Log)\s*\n(.*?)(?=^## |\Z)',
                                         text, re.M | re.S)}
    if not sections:
        sections = {'board': hashlib.sha256(text.encode()).hexdigest()}
    # One shared transaction prevents every subscriber publishing the same change.
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT value FROM observations WHERE name='render-board'").fetchone()
        try:
            previous = json.loads(row['value']) if row else None
        except ValueError:  # Upgrade from the original single digest.
            previous = {}
        if previous == sections:
            return
        db.execute("INSERT INTO observations VALUES ('render-board', ?) "
                   "ON CONFLICT(name) DO UPDATE SET value=excluded.value", (json.dumps(sections),))
        if row:
            changed = ', '.join(sorted(k for k in sections.keys() | previous.keys()
                                       if sections.get(k) != previous.get(k)))
            db.execute("INSERT INTO messages (created, sender, recipient, topic, body) VALUES (?, ?, ?, ?, ?)",
                       (time.time(), 'board-watch', '*', 'info',
                        f'Render scheduling board changed ({changed}): read {path}. '
                        'Acknowledge requests and offer a concrete safe-boundary handoff. '
                        'Recheck live locks before admission; this notice does not grant a slot.'))


def stalled_logs(agent, checkout, seconds, now=None):
    """Advisory lack-of-output notices only for this checkout's validated live owner.

    A quiet log is not proof of a deadlock. Require a fresh running guard report and
    matching PID/start before publishing one notice per job and unchanged log.
    """
    from .safety import render_lock as locks
    from .safety.memory_guard import usage
    now = time.time() if now is None else now
    holders = [locks.read_holder(locks.lock_path()), locks.read_holder(locks.small_lock_path())]
    holder = next((h for h in holders if h and h.get('repo', h.get('checkout')) == str(checkout)), None)
    if not holder:
        return
    members = locks.family(holder['pid'])
    build = paths.build_root() if checkout == paths.REPO else checkout / 'build'
    for report in build.glob('*/logs/*/memory-health.json'):
        try:
            health = json.loads(report.read_text())
            if health.get('state') != 'running' or not 0 <= now-health['time'] <= 90:
                continue
            pid = health['pid']
            if pid not in members or usage(pid).started != health['process_start']:
                continue
            log = report.with_name('stdout.log')
            modified = log.stat().st_mtime
            quiet = now-max(modified, holder['time'])
            if quiet < seconds:
                continue
            key = f"stall:{agent}:{holder['pid']}:{holder.get('started')}:{report}:{modified}"
            post('board-watch', f"No stdout progress for {quiet/60:.0f} min in your live job "
                 f"{holder.get('purpose')} (owner PID {holder['pid']}). Guard report is fresh/running. "
                 f"Inspect {log} and {report}; acknowledge with diagnosis/updated ETA or safely end "
                 'your own job and release. Quiet output alone does not prove a stall. '
                 'Preserve ready age on requeue and offer the next safe boundary to waiting owners.',
                 recipient=agent, topic='alert', dedup=key)
        except (OSError, ValueError, KeyError, TypeError, ProcessLookupError):
            continue


@contextmanager
def subscriber(agent, checkout):
    """One transport or background wait per owner, sharing its durable cursor."""
    agent_name(agent)
    folder = root() / 'board-subscribers'
    folder.mkdir(exist_ok=True)
    with (folder / f'{agent}.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(f'{agent} already has a subscriber; use board status or unsubscribe first')
        with database() as db:
            db.execute('''INSERT INTO subscribers (agent, pid, heartbeat, checkout) VALUES (?, ?, ?, ?)
                ON CONFLICT(agent) DO UPDATE SET pid=excluded.pid, heartbeat=excluded.heartbeat,
                checkout=excluded.checkout, stop=0, error=NULL''',
                (agent, os.getpid(), time.time(), str(checkout)))
        try:
            yield
        finally:
            with database() as db:
                db.execute('UPDATE subscribers SET pid=NULL WHERE agent=?', (agent,))


def subscribe(agent, command, interval=5, stall_after=900, timeout=None, addressed_only=False, checkout=None, managed=False):
    """Continuous delivery, or exit after one printed batch when timeout is provided."""
    checkout = Path(checkout or paths.REPO).resolve()
    deadline = None if timeout is None else time.monotonic()+timeout
    with subscriber(agent, checkout):
        while True:
            with database() as db:
                row = db.execute('SELECT stop FROM subscribers WHERE agent=?', (agent,)).fetchone()
                if row['stop'] and not managed:
                    return 0
                db.execute('UPDATE subscribers SET heartbeat=?,stop=0 WHERE agent=?', (time.time(), agent))
            delay = interval
            try:
                render_board_changes()
                stalled_logs(agent, checkout, stall_after)
                count = poll(agent, command, addressed_only, full=deadline is not None)
                if count and deadline is not None:
                    return 0
            except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                with database() as db:
                    db.execute('UPDATE subscribers SET error=? WHERE agent=?', (str(error), agent))
                print(str(error), file=sys.stderr, flush=True)
                delay = 30  # Retry without dropping messages or hammering a failed transport.
            if deadline is not None:
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    return 3
                delay = min(delay, remaining)
            time.sleep(delay)


def background(args):
    if args.notify is None:
        raise ValueError('background subscriptions require --notify to wake your existing agent session')
    folder = root() / 'board-subscribers'
    folder.mkdir(exist_ok=True)
    log = folder / f'{args.agent}.log'
    command = [sys.executable, '-m', 'atelier.cli', 'board', 'subscribe', '--agent', args.agent,
               '--notify', args.notify, '--interval', str(args.interval), '--stall-after', str(args.stall_after),
               '--checkout', str(Path(args.checkout).resolve())]
    if args.addressed_only:
        command.append('--addressed-only')
    env = dict(os.environ, PYTHONPATH=str(paths.STUDIO) + os.pathsep + os.environ.get('PYTHONPATH', ''))
    with log.open('a') as output:
        child = subprocess.Popen(command, cwd=paths.REPO, env=env, stdin=subprocess.DEVNULL,
                                 stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
    deadline = time.monotonic()+5
    while time.monotonic() < deadline:
        with database() as db:
            row = db.execute('SELECT pid FROM subscribers WHERE agent=?', (args.agent,)).fetchone()
        if row and row['pid'] == child.pid:
            print(f'subscribed {args.agent}: PID {child.pid}; log {log}')
            return 0
        if child.poll() is not None:
            raise ValueError(f'subscriber exited {child.returncode}; inspect {log}')
        time.sleep(.1)
    raise ValueError(f'subscriber startup not confirmed; inspect {log} and board status')


def configure(sub):
    p = sub.add_parser('board', help='machine-local agent messages and subscriptions')
    actions = p.add_subparsers(dest='action', required=True)
    p = actions.add_parser('post')
    p.add_argument('--agent', required=True); p.add_argument('--to', default='*')
    p.add_argument('--topic', choices=TOPICS, default='info'); p.add_argument('--reply-to', type=int)
    p.add_argument('message', help='message text (use - to read stdin)')
    p = actions.add_parser('read')
    p.add_argument('--agent'); p.add_argument('--after', type=int, default=0)
    p.add_argument('--limit', type=int, default=100)
    p = actions.add_parser('subscribe')
    p.add_argument('--agent', required=True); p.add_argument('--background', action='store_true')
    p.add_argument('--notify', help='JSON argv; a separate {message} argument receives the notification')
    watch_options(p)
    p.add_argument('--managed', action='store_true', help='service-owned listener; use board retire to stop it')
    p = actions.add_parser('supervise', help='install a persistent macOS login/crash supervised listener')
    p.add_argument('--agent', required=True); p.add_argument('--notify', required=True)
    p.add_argument('--checkout', default=str(paths.REPO)); p.add_argument('--addressed-only', action='store_true')
    p = actions.add_parser('retire', help='retire a persistent listener without deleting history')
    p.add_argument('--agent', required=True)
    p = actions.add_parser('wait', help='print one new batch and exit; re-arm as a background task')
    p.add_argument('--agent', required=True)
    p.add_argument('--timeout', type=float, default=3600, help='exit 3 without delivery on timeout')
    watch_options(p)
    p = actions.add_parser('unsubscribe'); p.add_argument('--agent', required=True)
    actions.add_parser('status')
    p = actions.add_parser('serve', help='live board UI and durable broadcasts on loopback')
    p.add_argument('--port', type=int, default=8890)
    p.add_argument('--public-origin', action='append', default=[], help='exact HTTPS origin of your private proxy')
    p.add_argument('--allowed-user', help='require this Tailscale user identity through the proxy')
    p.add_argument('--sender', default='operator', help='stable board sender name for UI broadcasts')
    p.add_argument('--remote-status', type=Path, help='optional remote-session watchdog status JSON')
    p = actions.add_parser('notify-codex', help='steer an existing active Codex session from a board subscription')
    p.add_argument('--thread', required=True, help='existing Codex thread UUID')
    p.add_argument('--codex', default='codex', help='Codex executable used to locate the running daemon')
    p.add_argument('--socket', type=Path, help='explicit existing app-server Unix socket')
    p.add_argument('message')
    p = actions.add_parser('remote-watch', help='bounded recovery for explicitly owned macOS Claude remote services')
    p.add_argument('--config', type=Path, required=True, help='private machine service configuration JSON')
    p = actions.add_parser('notify-claude', help='deliver to an existing native Claude inbox without a second writer')
    p.add_argument('--session-dir', type=Path, required=True, help='working directory of the existing remote session')
    p.add_argument('--permission-class', choices=('prompting', 'bypass'), default='prompting',
                   help='actual permission class of the authorized sender; never escalate to evade an inbound hold')
    p.add_argument('message')


def watch_options(parser):
    parser.add_argument('--interval', type=float, default=5)
    parser.add_argument('--stall-after', type=float, default=900, help='seconds without stdout progress (default: 900)')
    parser.add_argument('--addressed-only', action='store_true', help='ignore broadcast messages')
    parser.add_argument('--checkout', default=str(paths.REPO), help='owner checkout to monitor (default: this checkout)')


def main(args):
    try:
        if getattr(args, 'agent', None):
            agent_name(args.agent)
        if args.action == 'post':
            text = sys.stdin.read(8001) if args.message == '-' else args.message
            print(post(args.agent, text, args.to, args.topic, args.reply_to))
        elif args.action == 'read':
            if args.after < 0 or not 1 <= args.limit <= 1000:
                raise ValueError('--after must be nonnegative; --limit must be 1–1000')
            for row in messages(args.after, args.agent, args.limit):
                print(json.dumps(row))
        elif args.action in ('subscribe', 'wait'):
            if not getattr(args, 'managed', False):
                with database() as db:
                    row = db.execute('SELECT supervised FROM subscribers WHERE agent=?', (args.agent,)).fetchone()
                    if row and row['supervised']:
                        raise ValueError('This owner already has a persistent listener; do not re-arm a fallback wait')
            if not 1 <= args.interval <= 60 or not math.isfinite(args.stall_after) or args.stall_after < 60:
                raise ValueError('--interval must be 1–60 seconds; --stall-after must be at least 60')
            if args.action == 'wait':
                if not math.isfinite(args.timeout) or args.timeout < 0:
                    raise ValueError('--timeout must be finite and nonnegative')
                return subscribe(args.agent, None, args.interval, args.stall_after,
                                 timeout=args.timeout, addressed_only=args.addressed_only, checkout=args.checkout)
            command = notify_command(args.notify) if args.notify else None
            if args.managed and command is None:
                raise ValueError('managed listeners require an existing-session notification transport')
            if args.managed and args.background:
                raise ValueError('managed listeners are started by the service manager, without --background')
            if args.background:
                return background(args)
            return subscribe(args.agent, command, args.interval, args.stall_after,
                             addressed_only=args.addressed_only, checkout=args.checkout, managed=args.managed)
        elif args.action in ('supervise', 'retire'):
            from . import board_service
            return board_service.install(args) if args.action == 'supervise' else board_service.retire(args.agent)
        elif args.action == 'unsubscribe':
            with database() as db:
                row = db.execute('SELECT supervised FROM subscribers WHERE agent=?', (args.agent,)).fetchone()
                if row and row['supervised']:
                    print('Persistent listener remains armed; use board retire only when permanently retiring this session')
                    return 0
                db.execute('UPDATE subscribers SET stop=1 WHERE agent=?', (args.agent,))
            print('stop requested; subscriber exits after its current bounded notification/poll')
        elif args.action == 'status':
            with database() as db:
                for row in db.execute('SELECT * FROM subscribers ORDER BY agent'):
                    item = dict(row)
                    item['responsive'] = bool(item['pid'] and time.time()-(item['heartbeat'] or 0) < 90)
                    print(json.dumps(item))
        elif args.action == 'serve':
            from . import board_web
            return board_web.serve(args)
        elif args.action == 'notify-codex':
            from . import board_codex
            try:
                with board_codex.Client(args.codex, args.socket) as client:
                    print(board_codex.notify(client, args.thread, args.message))
            except (OSError, board_codex.TransportError) as error:
                print(str(error), file=sys.stderr)
                return 1
        elif args.action == 'notify-claude':
            from . import board_claude
            try:
                print(board_claude.notify(args.session_dir, args.message, args.permission_class))
            except (OSError, ValueError, subprocess.SubprocessError, board_claude.TransportError) as error:
                # Native credentials and message bodies never enter transport logs.
                print(str(error) if isinstance(error, board_claude.TransportError)
                      else 'Claude inbox unavailable; delivery remains pending', file=sys.stderr)
                return 1
        elif args.action == 'remote-watch':
            from . import board_remote
            return board_remote.main(args.config)
    except (ValueError, sqlite3.Error) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0
