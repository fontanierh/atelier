"""Durable machine-local agent messages and lightweight background subscriptions.

The Markdown render board remains the scheduling ledger. Messages wake its owners;
this module never acquires render slots, launches heavy work or signals processes.

The store lives in `board_store` and the command line in `board_cli`; both stay importable from here.
"""
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from . import paths
# The store's names stay importable from here, as they were before the split.
from .board_store import (
    NOTIFY_PER_HOUR, OPEN_TASKS, OPERATOR, TASK_CHARS, TOPICS, agent_name, audience_text,
    close_task, database, edit_task, messages, notify_allowed, open_task, post, remove, root, send_web, set_task,
    tasks, thread_rows, with_audience
)  # noqa: F401


def notification(batch):
    # Keep argv comfortably bounded, even with long messages. The complete record stays in the board.
    lines = ['Atelier agent board: new messages (advisory coordination, not render admission).']
    for item in batch:
        thread = f" reply to #{item['reply_to']}" if item.get('reply_to') else ''
        if item.get('operator_task'):
            thread += f" on your operator task {item['operator_task']}; dismiss it once it no longer applies"
        lines.append(f"#{item['id']} {item['sender']} -> {item['recipient']} ({audience_text(item)}{thread}) "
                     f"[{item['topic']}]: {item['body'][:600]}")
    lines.append('Read full messages with atelier board read; check render-board.md and live locks. '
                 'Acknowledge actionable handoffs through atelier board post --topic ack --reply-to ID. '
                 'Write clear, well-formatted posts in plain words, point first; there is no length cap. Blocked on the '
                 'operator\'s guidance or confirmation? Open one operator task (board operator-task open), sparingly, '
                 'and dismiss it when unblocked. Preserve first-ready age; never signal other owners or bypass safety.')
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
        # A reply anywhere in an open operator task's thread says so, and reminds the agent to dismiss it.
        with database() as db:
            open_tasks = {r['message']: r['id'] for r in db.execute(
                'SELECT id, message FROM operator_tasks WHERE agent=? AND closed IS NULL', (agent,))}
            for item in batch if open_tasks else ():
                parent, hops = item.get('reply_to'), 0
                while parent and parent not in open_tasks and hops < 200:
                    row = db.execute('SELECT reply_to FROM messages WHERE id=?', (parent,)).fetchone()
                    parent, hops = row and row['reply_to'], hops + 1
                if parent in open_tasks:
                    item['operator_task'] = open_tasks[parent]
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
                checkout=excluded.checkout, stop=0, removed=0, error=NULL''',
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


from .board_cli import configure, main, watch_options  # noqa: E402,F401  (after the definitions it uses)
