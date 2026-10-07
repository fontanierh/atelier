"""The board's sender's inbox, as in Slack: Threads (every conversation with replies they are part of, unread first,
then newest reply first, each with its latest replies and a reply box) and Activity (everything that involves them,
newest first: @mentions, replies in their threads, direct messages, and acknowledgements grouped like reactions).

Read state lives on the board, in the `reads` table, so every device agrees. A thread is read up to the newest of: its
own mark, the reader's "mark all read", the baseline the table was created with (history from before this feature
starts read), and the reader's own newest message in it (replying means you read what came before)."""
import re
from functools import lru_cache

from . import board, board_markdown
from .board_files import split_attachments

MENTION = re.compile(r'(?:^|[^\w@.-])@([A-Za-z0-9][\w.-]*)')
SNIPPET = 160


def is_system(sender):
    """Automatic notices (render-watch and the like); the feed folds them away and they never make anything unread."""
    return bool(re.search(r'(^|-)watch$', sender))


def mentions(body, reader):
    return any(name.rstrip('.-').lower() == reader.lower() for name in MENTION.findall(body or ''))


@lru_cache(maxsize=4096)
def _html(text):
    return board_markdown.render(text)


def card(row):
    """A message as the inbox shows it: rendered body, attachments and a one-line snippet."""
    text, files = split_attachments(row['body'])
    flat = re.sub(r'\s+', ' ', re.sub(r'[*_`#>]+', '', text)).strip()
    return {**{key: row[key] for key in ('id', 'created', 'sender', 'recipient', 'topic', 'reply_to', 'dedup')},
            'body': row['body'], 'body_html': _html(text), 'attachments': files, 'acknowledged': False,
            'snippet': flat[:SNIPPET] + ('…' if len(flat) > SNIPPET else '') if flat else ('Attachment' if files else '')}


def group_key(row):
    """Every addressed copy of one web send is one message."""
    dedup = row['dedup'] or ''
    return dedup.rsplit(':', 1)[0] if dedup.startswith(('web-broadcast:', 'web-direct:')) else f"m{row['id']}"


def has_reads(db):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='reads'").fetchone())


class Inbox:
    """Every thread on the board seen from `reader`, built from one pass over the message index."""

    def __init__(self, db, reader):
        self.db, self.reader = db, reader
        rows = db.execute('SELECT id, created, sender, recipient, topic, reply_to, dedup, notify FROM messages '
                          'ORDER BY id').fetchall()
        candidates = db.execute("SELECT id, body FROM messages WHERE sender!=? AND instr(lower(body), ?)>0",
                                (reader, '@' + reader.lower())).fetchall()
        self.mentioned = {row['id'] for row in candidates if mentions(row['body'], reader)}
        self.rows = {row['id']: row for row in rows}
        self.threads, self.thread_of = {}, {}
        root_of = {}
        for row in rows:
            parent = row['reply_to']
            root = root_of.get(parent, row['id']) if parent in self.rows else row['id']
            root_of[row['id']] = root
            key = group_key(self.rows[root])
            thread = self.threads.setdefault(key, {'key': key, 'roots': [], 'messages': []})
            (thread['roots'] if root == row['id'] else thread['messages']).append(row)
            self.thread_of[row['id']] = key
        marks = {}
        if has_reads(db):
            for row in db.execute("SELECT reader, thread, last_read, unfollowed FROM reads WHERE reader IN (?, '*')",
                                  (reader,)):
                marks[(row['reader'], row['thread'])] = row
        mark = lambda who, key, field='last_read': (marks.get((who, key)) or {field: None})[field]
        # Without the table (an older store) nothing is unread yet.
        baseline = mark('*', '*') if has_reads(db) else (rows[-1]['id'] if rows else 0)
        self.everything_read = max(baseline or 0, mark(reader, '*') or 0)
        for key, thread in self.threads.items():
            every = thread['roots'] + thread['messages']
            own = [row['id'] for row in every if row['sender'] == reader]
            involved = [row['id'] for row in every if self.involves(row)]
            thread['first_involved'] = min(involved) if involved else None
            thread['read'] = max(self.everything_read, mark(reader, key) or 0, max(own, default=0))
            thread['unfollowed'] = mark(reader, key, 'unfollowed')
            # Unfollowing hides a thread until someone @mentions you in it again.
            if thread['unfollowed'] and any(row['id'] > thread['unfollowed'] and row['id'] in self.mentioned
                                            for row in thread['messages']):
                thread['unfollowed'] = None
            thread['following'] = thread['first_involved'] is not None and not thread['unfollowed']
            thread['newest'] = every[-1]

    def involves(self, row):
        return self.reader in (row['sender'], row['recipient']) or row['id'] in self.mentioned

    def from_others(self, row):
        return row['sender'] != self.reader and not is_system(row['sender'])

    def unread(self, row):
        return self.from_others(row) and row['id'] > self.threads[self.thread_of[row['id']]]['read']

    def new_in_thread(self, row):
        """Unread, and more than an acknowledgement: acks are like reactions and never make a thread unread."""
        return row['topic'] != 'ack' and self.unread(row)

    def replies(self, thread):
        """The thread's replies as messages: a web reply's addressed copies are one."""
        groups = {}
        for row in thread['messages']:
            groups.setdefault(group_key(row), []).append(row)
        return list(groups.values())

    def open_threads(self):
        """Threads with replies that the reader started, joined, was addressed or @mentioned in, and still follows."""
        return [t for t in self.threads.values() if t['messages'] and t['following']]

    def audience(self, thread):
        """Who a reply from the reader goes to, before the web board drops retired agents: '*' for a thread the reader
        opened to the whole board, else the agent who started it (or those the reader's opening addressed) and
        everyone who joined in. Mirrors threadAudience in board.js."""
        roots, reader = thread['roots'], self.reader
        first = roots[0]
        if first['sender'] == reader and ('~m:' not in (first['dedup'] or '')) and (
                first['recipient'] == '*' or (first['dedup'] or '').startswith('web-broadcast:')):
            return '*'
        names = [row['recipient'] for row in roots] if first['sender'] == reader else [first['sender']]
        for row in thread['messages']:
            names.append(row['recipient'] if row['sender'] == reader else row['sender'])
        return [name for name in dict.fromkeys(names) if name not in ('*', reader) and not is_system(name)]

    def bodies(self, ids):
        ids = list(ids)
        if not ids:
            return {}
        found = self.db.execute(f"SELECT * FROM messages WHERE id IN ({','.join('?' * len(ids))})", ids)
        return {row['id']: card(dict(row)) for row in found}


def threads(db, reader, limit=30, latest=3):
    """The Threads view: unread threads first, then the rest, each by newest reply, as Slack orders them."""
    inbox = Inbox(db, reader)
    listed = inbox.open_threads()
    for thread in listed:
        thread['unread_ids'] = [row['id'] for row in thread['messages'] + thread['roots'] if inbox.new_in_thread(row)]
    listed.sort(key=lambda t: (not t['unread_ids'], -t['newest']['id']))
    page = listed[:limit]
    shown = {id for t in page for id in [t['roots'][0]['id']] + [g[0]['id'] for g in inbox.replies(t)[-latest:]]}
    bodies = inbox.bodies(shown)
    items = []
    for thread in page:
        groups, root = inbox.replies(thread), thread['roots'][0]
        unread_groups = {group_key(row) for row in thread['messages'] if row['id'] in thread['unread_ids']}
        latest_cards = [{**bodies[g[0]['id']], 'audience': sorted({row['recipient'] for row in g}),
                         'unread': group_key(g[0]) in unread_groups} for g in groups[-latest:]]
        items.append({
            'id': root['id'], 'key': thread['key'],
            'root': {**bodies[root['id']], 'audience': [row['recipient'] for row in thread['roots']],
                     'unread': root['id'] in thread['unread_ids']},
            'latest': latest_cards, 'replies': len(groups), 'unread': len(unread_groups),
            'participants': list(dict.fromkeys(row['sender'] for row in thread['roots'][:1] + thread['messages'])),
            'reply_audience': inbox.audience(thread),
            'last_activity': thread['newest']['created'], 'newest': thread['newest']['id']})
    return {'threads': items, 'total': len(listed), 'unread': sum(1 for t in listed if t['unread_ids'])}


KINDS = ('mention', 'reply', 'dm', 'ack')


def activity_entries(inbox):
    """What involves the reader, oldest first: an @mention, a direct message, a reply addressed to them, the other
    replies in a thread they were in by then (one entry per thread, as Slack folds a thread's new replies), and
    the acknowledgements of their own message (one entry per message, like reactions)."""
    reader, entries = inbox.reader, {}
    for row in inbox.rows.values():
        if not inbox.from_others(row):
            continue
        thread = inbox.threads[inbox.thread_of[row['id']]]
        in_thread = (row['reply_to'] is not None and thread['first_involved'] is not None
                     and thread['first_involved'] < row['id'] and not thread['unfollowed'])
        target = inbox.rows.get(row['reply_to'])
        if row['id'] in inbox.mentioned:
            kind, key = 'mention', f"i{row['id']}"
        elif row['topic'] == 'ack' and target:
            if target['sender'] != reader:
                continue
            kind, key = 'ack', f'a{group_key(target)}'
        elif row['recipient'] == reader:
            kind, key = ('reply' if row['reply_to'] else 'dm'), f"i{row['id']}"
        elif in_thread:
            kind, key = 'reply', f"t{thread['key']}"
        else:
            continue
        entry = entries.setdefault(key, {'kind': kind, 'rows': [], 'unread': 0, 'thread': thread})
        entry['rows'].append(row)
        entry['unread'] += inbox.unread(row)
        if kind == 'ack':
            entry['target'] = target['id']
    for entry in entries.values():
        entry['newest'] = entry['rows'][-1]
    return list(entries.values())


def activity(db, reader, kind='', unread_only=False, limit=60):
    """The Activity view, newest first, and its unread counts. Acknowledgements show as read or unread but never count
    toward the badge, which only real messages raise."""
    if kind and kind not in KINDS:
        raise ValueError('unknown activity kind')
    inbox = Inbox(db, reader)
    entries, counts = activity_entries(inbox), dict.fromkeys(('all', *KINDS), 0)
    for entry in entries:
        if entry['unread']:
            counts[entry['kind']] += 1
            counts['all'] += entry['kind'] != 'ack'
    entries.sort(key=lambda entry: -entry['newest']['id'])
    entries = [entry for entry in entries if (not kind or entry['kind'] == kind) and (entry['unread'] or not unread_only)]
    total, entries = len(entries), entries[:limit]
    wanted = set()
    for entry in entries:
        wanted.update((entry['newest']['id'], entry['thread']['roots'][0]['id'], entry.get('target') or 0))
    bodies = inbox.bodies(wanted - {0})
    items = []
    for entry in entries:
        newest, thread = entry['newest'], entry['thread']
        root = thread['roots'][0]
        # A thread's folded replies say how many are new and from whom; once read, the entry is its newest reply.
        rows = [row for row in entry['rows'] if inbox.unread(row)] or entry['rows'][-1:]
        if entry['kind'] != 'reply':
            rows = entry['rows']
        item = {'kind': entry['kind'], 'id': newest['id'], 'created': newest['created'],
                'unread': entry['unread'], 'count': len(rows), 'thread': root['id'],
                'replies': len(inbox.replies(thread)), 'message': bodies.get(newest['id']),
                'senders': list(dict.fromkeys(row['sender'] for row in rows)),
                'reply_audience': inbox.audience(thread),
                'root': None if root['id'] == newest['id'] else bodies.get(root['id'])}
        if entry['kind'] == 'ack':
            item['target'] = bodies.get(entry['target'])
        items.append(item)
    return {'items': items, 'total': total, 'unread': counts}


def summary(db, reader):
    """The badges: threads with unread replies, and unread activity (acknowledgements aside)."""
    inbox = Inbox(db, reader)
    unread_threads = sum(1 for t in inbox.open_threads()
                         if any(inbox.new_in_thread(row) for row in t['roots'] + t['messages']))
    unread_activity = sum(1 for entry in activity_entries(inbox) if entry['kind'] != 'ack' and entry['unread'])
    return {'threads': unread_threads, 'activity': unread_activity}


def mark_read(reader, message_id=None, through=None, everything=False, follow=None):
    """Mark a conversation read up to `through` (the newest message the reader saw in it; its newest message when
    omitted), mark everything read, or follow/unfollow a thread. Marks only move forward. Returns the thread's key."""
    board.agent_name(reader)
    with board.database() as db:
        db.execute('BEGIN IMMEDIATE')
        newest = db.execute('SELECT coalesce(max(id), 0) FROM messages').fetchone()[0]
        if everything:
            db.execute("INSERT INTO reads (reader, thread, last_read) VALUES (?, '*', ?) "
                       'ON CONFLICT (reader, thread) DO UPDATE SET last_read=max(last_read, excluded.last_read)',
                       (reader, newest))
            return '*'
        if isinstance(message_id, bool) or not isinstance(message_id, int):
            raise ValueError('Choose a message.')
        if through is not None and (isinstance(through, bool) or not isinstance(through, int)):
            raise ValueError('through must be a message id')
        roots, replies = board.thread_rows(db, message_id)
        key = group_key(roots[0])
        last = max(row['id'] for row in roots + replies)
        mark = last if through is None else max(0, min(through, last))
        db.execute('INSERT INTO reads (reader, thread, last_read) VALUES (?, ?, ?) '
                   'ON CONFLICT (reader, thread) DO UPDATE SET last_read=max(last_read, excluded.last_read)',
                   (reader, key, mark))
        if follow is not None:
            # Unfollowing remembers where: only a later @mention brings the thread back.
            db.execute('UPDATE reads SET unfollowed=? WHERE reader=? AND thread=?',
                       (None if follow else last, reader, key))
        return key
