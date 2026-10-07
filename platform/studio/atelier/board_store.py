"""The board's durable store: the SQLite mailbox and its schema, the message model (posts, web sends, threads and
audiences), agents' tasks and removal, operator tasks, and the limits that keep messages short and notifications rare."""
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager

from . import paths


TOPICS = ('info', 'request', 'handoff', 'blocked', 'release', 'evidence', 'ack', 'alert')


# The project owner's name on the board. Their messages are authoritative (AGENTS.md), so only the web board, behind
# its Tailscale identity check, sends as them; the command line refuses the name.
OPERATOR = 'operator'
# The web board folds a message longer than this; board_web_assets/board.js uses the same limits.
PREVIEW_CHARS, PREVIEW_LINES = 500, 8


def folds(text):
    """Whether people will see this message folded behind "Read more" on the web board."""
    from .board_files import split_attachments
    text = split_attachments(text)[0].strip()
    return len(text) > PREVIEW_CHARS or len(text.split('\n')) > PREVIEW_LINES


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
            CREATE INDEX IF NOT EXISTS messages_reply_to ON messages(reply_to);
            CREATE TABLE IF NOT EXISTS observations (name TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS operator_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created REAL NOT NULL, agent TEXT NOT NULL,
                message INTEGER NOT NULL REFERENCES messages(id), closed REAL, closed_by TEXT, note TEXT
            );
            CREATE TABLE IF NOT EXISTS subscribers (
                agent TEXT PRIMARY KEY, cursor INTEGER NOT NULL DEFAULT 0,
                pid INTEGER, heartbeat REAL, checkout TEXT, stop INTEGER NOT NULL DEFAULT 0,
                error TEXT
            );
        ''')
        # `task` is the agent's one-line assignment; `removed` hides an evicted agent from the board's lists.
        for column, kind in (('supervised', 'TEXT'), ('task', 'TEXT'), ('removed', 'INTEGER NOT NULL DEFAULT 0')):
            if column not in {row['name'] for row in db.execute('PRAGMA table_info(subscribers)')}:
                try:
                    db.execute(f'ALTER TABLE subscribers ADD COLUMN {column} {kind}')
                except sqlite3.OperationalError:
                    if column not in {row['name'] for row in db.execute('PRAGMA table_info(subscribers)')}:
                        raise
        # `notify` marks a message its sender explicitly flagged for a push notification to the operator.
        if 'notify' not in {row['name'] for row in db.execute('PRAGMA table_info(messages)')}:
            try:
                db.execute('ALTER TABLE messages ADD COLUMN notify INTEGER NOT NULL DEFAULT 0')
            except sqlite3.OperationalError:
                if 'notify' not in {row['name'] for row in db.execute('PRAGMA table_info(messages)')}:
                    raise
        # An operator task's `body` is its ask once its agent edited it (the original stays in its message).
        for column, kind in (('body', 'TEXT'), ('edited', 'REAL')):
            if column not in {row['name'] for row in db.execute('PRAGMA table_info(operator_tasks)')}:
                try:
                    db.execute(f'ALTER TABLE operator_tasks ADD COLUMN {column} {kind}')
                except sqlite3.OperationalError:
                    if column not in {row['name'] for row in db.execute('PRAGMA table_info(operator_tasks)')}:
                        raise
        yield db
        db.commit()
    finally:
        db.close()


# Phone notifications are for what the operator asked to hear about or must see now, so each agent gets a few an hour.
NOTIFY_PER_HOUR = 3


def notify_allowed(db, sender, now=None):
    since = (now or time.time()) - 3600
    # Operator task asks and edits always push, so they leave this allowance alone.
    used = db.execute('SELECT count(*) FROM messages WHERE sender=? AND notify=1 AND created>? '
                      'AND id NOT IN (SELECT message FROM operator_tasks) '
                      'AND NOT (coalesce(reply_to, 0) IN (SELECT message FROM operator_tasks) '
                      "AND body LIKE 'Updated the ask:%')", (sender, since))
    return used.fetchone()[0] < NOTIFY_PER_HOUR


def post(sender, body, recipient='*', topic='info', reply_to=None, dedup=None, notify=False):
    """Post a message. With notify, it also pushes a phone notification to the operator, within NOTIFY_PER_HOUR;
    past the limit the message is still posted, without the push. Returns the message ID."""
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
        notify = bool(notify) and notify_allowed(db, sender)
        result = db.execute('''INSERT OR IGNORE INTO messages
            (created, sender, recipient, topic, body, reply_to, dedup, notify) VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (time.time(), sender, recipient, topic, body, reply_to, dedup, int(notify)))
        if result.rowcount:
            return result.lastrowid
        return db.execute('SELECT id FROM messages WHERE dedup=?', (dedup,)).fetchone()['id']


def thread_rows(db, message_id):
    """The conversation holding message_id: its root (every copy of a web broadcast) and all replies below it."""
    row = db.execute('SELECT * FROM messages WHERE id=?', (message_id,)).fetchone()
    if not row:
        raise LookupError(f'message {message_id} is not on the board')
    seen = {row['id']}
    while row['reply_to'] and len(seen) < 200:
        parent = db.execute('SELECT * FROM messages WHERE id=?', (row['reply_to'],)).fetchone()
        if not parent or parent['id'] in seen:
            break
        row = parent; seen.add(row['id'])
    roots = [dict(row)]
    if (row['dedup'] or '').startswith(('web-broadcast:', 'web-direct:')):
        prefix = row['dedup'].rsplit(':', 1)[0] + ':'
        roots = [dict(r) for r in db.execute('SELECT * FROM messages WHERE dedup LIKE ? ORDER BY id', (prefix+'%',))]
    ids = [r['id'] for r in roots]
    replies = [dict(r) for r in db.execute(
        f"WITH RECURSIVE t(id) AS (SELECT id FROM messages WHERE reply_to IN ({','.join('?' * len(ids))}) "
        'UNION SELECT m.id FROM messages m JOIN t ON m.reply_to=t.id) '
        'SELECT * FROM messages WHERE id IN t ORDER BY id LIMIT 500', ids)]
    return with_audience(db, roots), with_audience(db, replies)


def set_task(agent, text):
    """Record the agent's one-line assignment, shown beside its name on the board. Empty text clears it."""
    agent_name(agent)
    text = ' '.join((text or '').split())
    if len(text) > 160:
        raise ValueError('keep the task to one line of at most 160 characters')
    with database() as db:
        if not db.execute('UPDATE subscribers SET task=? WHERE agent=?', (text or None, agent)).rowcount:
            raise LookupError(f'{agent} is not registered on the board; subscribe or wait first')
    return text


def remove(agent):
    """Take an evicted agent off the board. Its listener is retired (a supervised one through launchd), so nothing
    more queues for it, and it leaves every list. History stays, and subscribing again brings the agent back."""
    agent_name(agent)
    with database() as db:
        row = db.execute('SELECT supervised FROM subscribers WHERE agent=?', (agent,)).fetchone()
    if row is None:
        raise LookupError(f'{agent} is not registered on the board')
    if row['supervised']:
        from . import board_service
        board_service.retire(agent)
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('UPDATE subscribers SET stop=1, removed=1 WHERE agent=?', (agent,))
        # Nobody is left to unblock: its tasks leave the operator's list, in the same transaction.
        for (task,) in db.execute('SELECT id FROM operator_tasks WHERE agent=? AND closed IS NULL', (agent,)).fetchall():
            _close_task(db, task, agent, '', removed=True)


# Operator tasks: an agent that cannot go on without the operator's guidance, help or confirmation opens one, and the
# web board lists it where the operator answers or dismisses it in a tap. They are for real blocks only: an agent
# holds at most OPEN_TASKS at once (editing its ask when what it needs changes), each says in a few lines what it
# needs, and the agent dismisses its own as soon as it no longer applies. The question is an ordinary message to the
# operator, so answers are its thread replies.
OPEN_TASKS, TASK_CHARS = 1, 500


def _ask(body):
    body = (body or '').strip()
    if not body or len(body) > TASK_CHARS:
        raise ValueError(f'say what you need from the operator in at most {TASK_CHARS} characters; put detail in a '
                         'reply to the task\'s thread')
    return body


def open_task(agent, body):
    """Open an operator task for `agent`. It posts the question to the operator (a `blocked` message, always pushed to
    their phone, outside NOTIFY_PER_HOUR) and returns (task id, message id)."""
    agent_name(agent)
    if agent == OPERATOR:
        raise ValueError('operator tasks are opened by agents, for the operator')
    body = _ask(body)
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM subscribers WHERE agent=? AND removed=0', (agent,)).fetchone():
            raise LookupError(f'{agent} is not on the board; subscribe before opening an operator task')
        held = [row[0] for row in db.execute(
            'SELECT id FROM operator_tasks WHERE agent=? AND closed IS NULL ORDER BY id', (agent,))]
        if len(held) >= OPEN_TASKS:
            raise ValueError(f'you already have open operator task {held[0]}; change its ask (board operator-task edit '
                             f'--agent {agent} {held[0]} "...") or dismiss it if it no longer applies')
        now = time.time()
        message = db.execute('INSERT INTO messages (created, sender, recipient, topic, body, notify) '
                             "VALUES (?, ?, ?, 'blocked', ?, 1)", (now, agent, OPERATOR, body)).lastrowid
        task = db.execute('INSERT INTO operator_tasks (created, agent, message) VALUES (?, ?, ?)',
                          (now, agent, message)).lastrowid
    return task, message


def edit_task(task_id, agent, body):
    """Change the ask of `agent`'s open operator task. The Tasks page shows the new ask, and a note in its thread
    records it, pushed to the operator like the ask was. Returns that note's message id."""
    agent_name(agent)
    body = _ask(body)
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM operator_tasks WHERE id=?', (task_id,)).fetchone()
        if row is None:
            raise LookupError(f'operator task {task_id} does not exist')
        if row['agent'] != agent:
            raise ValueError(f"operator task {task_id} is {row['agent']}'s; only it can change the ask")
        if row['closed'] is not None:
            raise ValueError(f'operator task {task_id} was dismissed; open a new one if you still need the operator')
        now = time.time()
        db.execute('UPDATE operator_tasks SET body=?, edited=? WHERE id=?', (body, now, task_id))
        return db.execute("INSERT INTO messages (created, sender, recipient, topic, body, reply_to, notify) "
                          "VALUES (?, ?, ?, 'info', ?, ?, 1)",
                          (now, agent, OPERATOR, f'Updated the ask: {body}', row['message'])).lastrowid


def close_task(task_id, by, note='', operator=False, removed=False):
    """Dismiss an open operator task. The operator (`by` the web board's sender, with operator) may dismiss any, an
    agent only its own; removing an agent dismisses its tasks (removed). The thread records it, so the agent hears
    when the operator dismissed its task and the operator sees why an agent dropped one. False if already closed."""
    agent_name(by)
    if not isinstance(note or '', str):
        raise ValueError('the dismissal note must be text')
    note = ' '.join((note or '').split())
    if len(note) > 300:
        raise ValueError('keep the dismissal note to at most 300 characters')
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        return _close_task(db, task_id, by, note, operator, removed)


def _close_task(db, task_id, by, note, operator=False, removed=False):
    """close_task's work inside the caller's transaction."""
    row = db.execute('SELECT * FROM operator_tasks WHERE id=?', (task_id,)).fetchone()
    if row is None:
        raise LookupError(f'operator task {task_id} does not exist')
    if not (operator or removed) and by != row['agent']:
        raise ValueError(f"operator task {task_id} is {row['agent']}'s; only it or the operator can dismiss it")
    if row['closed'] is not None:
        return False
    now = time.time()
    db.execute('UPDATE operator_tasks SET closed=?, closed_by=?, note=? WHERE id=?', (now, by, note or None, task_id))
    if removed:
        sender, recipient, text = 'board-watch', OPERATOR, 'Dismissed this operator task: its agent left the board.'
    elif operator:
        sender, recipient, text = by, row['agent'], 'Dismissed this operator task.'
    else:
        sender, recipient, text = row['agent'], OPERATOR, 'Dismissed this operator task: it no longer applies.'
    db.execute("INSERT INTO messages (created, sender, recipient, topic, body, reply_to) VALUES (?, ?, ?, 'info', ?, ?)",
               (now, sender, recipient, text + (f' {note}' if note else ''), row['message']))
    return True


def tasks(db, agent=None, include_closed=False):
    """Operator tasks, oldest first, each with its question and its thread's newest reply."""
    conditions, parameters = [], []
    if agent:
        conditions.append('t.agent=?'); parameters.append(agent)
    if not include_closed:
        conditions.append('t.closed IS NULL')
    where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
    rows = [dict(row) for row in db.execute(
        'SELECT t.id, t.created, t.agent, t.message, t.closed, t.closed_by, t.note, t.edited, '
        'coalesce(t.body, m.body) AS body, m.created AS asked FROM operator_tasks t JOIN messages m ON m.id=t.message'
        + where + ' ORDER BY t.id LIMIT 200', parameters)]
    for row in rows:
        replies = db.execute(
            'WITH RECURSIVE r(id) AS (SELECT id FROM messages WHERE reply_to=? '
            'UNION SELECT m.id FROM messages m JOIN r ON m.reply_to=r.id) '
            # An edit's note is the ask itself, already on the card, so it is not a reply.
            'SELECT sender, body, created FROM messages WHERE id IN r '
            "AND NOT (sender=? AND body LIKE 'Updated the ask:%') ORDER BY id", (row['message'], row['agent'])).fetchall()
        row['replies'] = len(replies)
        row['last_reply'] = dict(replies[-1]) if replies else None
    return rows


def send_web(sender, body, request_id, topic='request', recipient='*', reply_to=None):
    """Atomically address every non-stopped subscriber, including addressed-only listeners.

    `recipient` is '*', one agent, or a list of agents (the people a message @mentions). A list
    is sent like a broadcast to just those agents: one addressed copy each, shown as one message.
    A retry of the same request returns the original recipient snapshot. The dedup
    prefix lets the web UI display the addressed copies as one broadcast without
    changing existing delivery cursors or the ordinary '*' broadcast semantics.
    """
    agent_name(sender)
    group = None
    if isinstance(recipient, list):
        if not 1 <= len(recipient) <= 50 or not all(isinstance(name, str) for name in recipient):
            raise ValueError('choose up to 50 registered recipients')
        group = sorted({agent_name(name) for name in recipient})
        if len(group) == 1:
            recipient, group = group[0], None
    if group is None and recipient != '*':
        if not isinstance(recipient, str):
            raise ValueError('choose a registered recipient')
        agent_name(recipient)
    if not isinstance(body, str) or not body.strip() or len(body) > 8000 or topic not in TOPICS:
        raise ValueError('use a known topic and a nonempty message of at most 8000 characters')
    if reply_to is not None and (isinstance(reply_to, bool) or not isinstance(reply_to, int) or reply_to < 1):
        raise ValueError('reply_to must be a message id')
    try:
        key = str(uuid.UUID(request_id))
    except (ValueError, AttributeError, TypeError):
        raise ValueError('broadcast request_id must be a UUID') from None
    # A mention group is stored as a broadcast to just those agents; `~m` lets the feed say who, not "everyone".
    prefix = f'web-broadcast:{key}~m:' if group else f'web-broadcast:{key}:'
    direct = f'web-direct:{key}:'
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        existing = [dict(row) for row in db.execute(
            'SELECT * FROM messages WHERE dedup LIKE ? OR dedup LIKE ? ORDER BY id', (f'web-broadcast:{key}%', direct+'%'))]
        if existing:
            if (any(row['sender'] != sender or row['body'] != body or row['topic'] != topic
                    or row['reply_to'] != reply_to for row in existing)
                    or ((recipient == '*' or group) and not existing[0]['dedup'].startswith(prefix))
                    or (group and sorted(row['recipient'] for row in existing) != group)
                    or (not group and recipient != '*'
                        and (len(existing) != 1 or existing[0]['dedup'] != direct+recipient))):
                raise ValueError('this broadcast request_id already belongs to a different message')
            return existing
        agents = [row['agent'] for row in db.execute(
            'SELECT agent FROM subscribers WHERE stop=0 AND agent!=? ORDER BY agent', (sender,))]
        if group:
            missing = [name for name in group if name not in agents]
            if missing:
                raise ValueError(f"Not registered or retired: {', '.join(missing)}.")
            agents = group
        elif recipient != '*':
            if recipient not in agents:
                raise ValueError('This agent is not registered or has been retired.')
            agents = [recipient]
            prefix = direct
        if not agents:
            raise ValueError('No agents are currently registered for broadcasts.')
        if reply_to is not None and not db.execute('SELECT 1 FROM messages WHERE id=?', (reply_to,)).fetchone():
            raise ValueError('The message you are replying to no longer exists.')
        created = time.time()
        for agent in agents:
            agent_name(agent)
            db.execute('''INSERT INTO messages (created, sender, recipient, topic, body, reply_to, dedup)
                VALUES (?, ?, ?, ?, ?, ?, ?)''', (created, sender, agent, topic, body, reply_to, prefix+agent))
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
        return with_audience(db, [dict(row) for row in rows])


def with_audience(db, rows):
    """Add `audience`, everyone a message reached: ['*'] for the whole board, every addressed copy's recipient for a
    web broadcast (each agent holds one copy, so the copy alone looks direct), or the one recipient."""
    groups = {}
    for row in rows:
        dedup = row.get('dedup') or ''
        if dedup.startswith('web-broadcast:'):
            prefix = dedup.rsplit(':', 1)[0] + ':'
            if prefix not in groups:
                groups[prefix] = [r[0] for r in db.execute(
                    'SELECT recipient FROM messages WHERE dedup LIKE ? ORDER BY recipient', (prefix + '%',))]
            row['audience'] = groups[prefix]
        else:
            row['audience'] = [row['recipient']]
    return rows


def audience_text(item):
    audience = item.get('audience') or [item['recipient']]
    if audience == ['*']:
        return 'to the whole board'
    if len(audience) == 1:
        return 'direct: only you' if audience[0] == item['recipient'] else f'to {audience[0]}'
    return f"broadcast to {len(audience)} agents: {', '.join(audience)}"
