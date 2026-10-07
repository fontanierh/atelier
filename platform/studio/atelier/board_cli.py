"""The `atelier board` command line: its arguments and what each action does."""
import json
import math
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path

from . import paths
from .board_store import (
    NOTIFY_PER_HOUR, OPERATOR, PREVIEW_CHARS, PREVIEW_LINES, TASK_CHARS, TOPICS, agent_name, close_task,
    database, edit_task, folds, messages, notify_allowed, open_task, post, send_web, set_task, tasks, thread_rows,
)


def configure(sub):
    p = sub.add_parser('board', help='machine-local agent messages and subscriptions')
    actions = p.add_subparsers(dest='action', required=True)
    p = actions.add_parser('post')
    p.add_argument('--agent', required=True); p.add_argument('--to', default='*')
    p.add_argument('--all-agents', action='store_true',
                   help='one addressed copy to every registered agent (reaches addressed-only listeners), shown as one '
                        'broadcast with per-agent delivery; instead of --to')
    p.add_argument('--topic', choices=TOPICS, default='info')
    p.add_argument('--reply-to', type=int, help='reply in the thread of this message ID')
    p.add_argument('--notify-operator', action='store_true',
                   help='also push a phone notification to the operator; only when they asked to be told or it is '
                        f'urgent (at most {NOTIFY_PER_HOUR} an hour)')
    p.add_argument('--attach', action='append', default=[], metavar='FILE',
                   help='attach a file (repeatable, up to 10); it is copied to the board and shown inline on the web')
    p.add_argument('message', nargs='?', default='', help='message text (use - to read stdin; may be empty with --attach)')
    p = actions.add_parser('task', help='set your one-line assignment, shown beside your name on the board')
    p.add_argument('--agent', required=True)
    p.add_argument('text', help='one line, at most 160 characters (empty clears it)')
    p = actions.add_parser('operator-task', help='ask the operator to unblock you; sparingly, and dismiss it once '
                           'it no longer applies', description=(
        'Open an operator task only when you cannot go on without the operator: guidance, help or a confirmation '
        'only they can give. It lands on the Tasks page of the web board, where they reply or dismiss it, and is '
        'pushed to their phone. You hold at most one at a time: when what you need changes, edit its ask. Replies '
        'arrive as thread replies to its message; dismiss the task yourself as soon as it no longer applies.'))
    task_actions = p.add_subparsers(dest='task_action', required=True)
    q = task_actions.add_parser('open', help='open a task: what you need from the operator, in a few lines')
    q.add_argument('--agent', required=True)
    q.add_argument('message', help=f'at most {TASK_CHARS} characters, the ask first (use - to read stdin)')
    q = task_actions.add_parser('edit', help='change your open task\'s ask; the operator is notified')
    q.add_argument('--agent', required=True); q.add_argument('id', type=int)
    q.add_argument('message', help=f'the new ask, at most {TASK_CHARS} characters (use - to read stdin)')
    q = task_actions.add_parser('list', help='open operator tasks (yours with --agent)')
    q.add_argument('--agent'); q.add_argument('--all', action='store_true', help='include dismissed tasks')
    q = task_actions.add_parser('dismiss', help='dismiss your task once it no longer applies')
    q.add_argument('--agent', required=True); q.add_argument('id', type=int)
    q.add_argument('--note', default='', help='optional one line on why, kept in its thread')
    p = actions.add_parser('thread', help='print a whole thread: the original, then every reply in order')
    p.add_argument('id', type=int, help='any message ID in the thread')
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
    actions.add_parser('guard-claude', help='PreToolUse hook: bound foreground commands and job output checks')
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
    # The listener imports this module for its re-exports, so it is imported here, at call time.
    from .board import background, notify_command, subscribe
    try:
        if getattr(args, 'agent', None):
            agent_name(args.agent)
        if args.action == 'post':
            if args.agent == OPERATOR:
                raise ValueError('only the web board posts as operator; post under your own agent name')
            text = sys.stdin.read(8001) if args.message == '-' else args.message
            if args.attach:
                from .board_files import store_file, with_attachments
                text = with_attachments(text, [store_file(path)['id'] for path in args.attach])
            if args.reply_to is not None:
                with database() as db:
                    if not db.execute('SELECT 1 FROM messages WHERE id=?', (args.reply_to,)).fetchone():
                        raise ValueError(f'message {args.reply_to} is not on the board')
            notify = args.notify_operator
            if notify:
                with database() as db:
                    if not notify_allowed(db, args.agent):
                        print(f'Note: you have used your {NOTIFY_PER_HOUR} notifications for this hour; posting '
                              'without a push.', file=sys.stderr)
            if args.all_agents:
                if args.to != '*':
                    raise ValueError('use either --to or --all-agents')
                if notify:
                    raise ValueError('--notify-operator is for one message to the operator; use it with --to operator')
                rows = send_web(args.agent, text, str(uuid.uuid4()), args.topic, '*', args.reply_to)
                print(' '.join(str(row['id']) for row in rows))
            else:
                print(post(args.agent, text, args.to, args.topic, args.reply_to, notify=notify))
            if folds(text):
                print(f'Note: over {PREVIEW_CHARS} characters or {PREVIEW_LINES} lines, so people see this folded behind '
                      '"Read more". Lead with the point and keep posts short; put detail in an attachment or a thread '
                      'reply.', file=sys.stderr)
        elif args.action == 'task':
            text = set_task(args.agent, args.text)
            print(f'{args.agent}: {text}' if text else f'{args.agent}: task cleared')
        elif args.action == 'operator-task':
            if getattr(args, 'agent', None) == OPERATOR:
                raise ValueError('operator tasks are for agents; the operator answers them on the web board')
            if args.task_action == 'open':
                text = sys.stdin.read() if args.message == '-' else args.message
                task, message = open_task(args.agent, text)
                print(f'operator task {task} (message {message}); replies arrive in its thread. Dismiss it with '
                      f'atelier board operator-task dismiss --agent {args.agent} {task} as soon as it no longer applies.')
            elif args.task_action == 'edit':
                edit_task(args.id, args.agent, sys.stdin.read() if args.message == '-' else args.message)
                print(f'operator task {args.id} updated; the operator was notified.')
            elif args.task_action == 'list':
                with database() as db:
                    for row in tasks(db, args.agent, include_closed=args.all):
                        print(json.dumps(row))
            else:
                if not close_task(args.id, args.agent, args.note):
                    print(f'operator task {args.id} was already dismissed')
                else:
                    print(f'operator task {args.id} dismissed')
        elif args.action == 'thread':
            with database() as db:
                roots, replies = thread_rows(db, args.id)
            for row in roots + replies:
                print(json.dumps(row))
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
        elif args.action == 'guard-claude':
            from . import board_toolguard
            return board_toolguard.main()
    except (ValueError, LookupError, sqlite3.Error) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0
