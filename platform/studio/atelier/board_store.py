"""The board's durable store: the SQLite mailbox and its schema, the message model (posts, web sends, threads and
audiences), agents' tasks and removal, and the limits that keep messages short and notifications rare."""
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
            CREATE TABLE IF NOT EXISTS observations (name TEXT PRIMARY KEY, value TEXT NOT NULL);
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
        yield db
        db.commit()
    finally:
        db.close()


# Phone notifications are for what the operator asked to hear about or must see now, so each agent gets a few an hour.
NOTIFY_PER_HOUR = 3


def notify_allowed(db, sender, now=None):
    since = (now or time.time()) - 3600
    used = db.execute('SELECT count(*) FROM messages WHERE sender=? AND notify=1 AND created>?', (sender, since))
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
        db.execute('UPDATE subscribers SET stop=1, removed=1 WHERE agent=?', (agent,))


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
