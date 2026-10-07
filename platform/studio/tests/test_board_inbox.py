"""Slack-style Threads and Activity for the board's sender, with read state kept on the board."""
import json
import sqlite3
import threading
import time
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from atelier import board, board_inbox, board_web


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv('ATELIER_CACHE', str(tmp_path / 'cache'))
    monkeypatch.setenv('ATELIER_RENDER_LOCK', str(tmp_path / 'render.lock'))
    with board.database() as db:
        db.executemany('INSERT INTO subscribers (agent,pid,heartbeat,stop) VALUES (?,?,?,?)',
                       [('one', 1, time.time(), 0), ('two', 1, time.time(), 0), ('three', None, 0, 0)])
    return tmp_path


def ask(recipient, body):
    """The operator writes from the web board; returns the first addressed copy's id."""
    return board.send_web('operator', body, str(uuid.uuid4()), 'request', recipient)[0]['id']


def view(name, **query):
    with sqlite3.connect(board.root() / 'agent-board.sqlite3') as db:
        db.row_factory = sqlite3.Row
        if name == 'threads':
            return board_inbox.threads(db, 'operator', **query)
        if name == 'summary':
            return board_inbox.summary(db, 'operator')
        return board_inbox.activity(db, 'operator', **query)


def test_threads_list_unread_first_then_newest_reply_and_reading_or_replying_clears_them(cache):
    first = ask('one', 'Can you look at the ramp?')
    second = ask('two', 'Can you look at the bowl?')
    board.post('one', 'Looking.', 'operator', reply_to=first)
    board.post('two', 'Looking too.', 'operator', reply_to=second)
    # Agents talking among themselves, with no part for the operator, is not one of the operator's threads.
    other = board.post('one', 'Spare cycles?', 'two')
    board.post('two', 'No.', 'one', reply_to=other)
    listed = view('threads')
    assert [t['id'] for t in listed['threads']] == [second, first] and listed['unread'] == 2
    assert listed['threads'][0]['latest'][0]['body_html'] == '<p>Looking too.</p>\n'
    assert listed['threads'][0]['reply_audience'] == ['two']

    board_inbox.mark_read('operator', first)
    assert [(t['id'], t['unread']) for t in view('threads')['threads']] == [(second, 1), (first, 0)]
    # A new reply in the older thread brings it back to the top, unread.
    board.post('one', 'Found it.', 'operator', reply_to=first)
    assert [(t['id'], t['unread']) for t in view('threads')['threads']] == [(first, 1), (second, 1)]
    # Replying reads everything before the reply.
    board.send_web('operator', 'Thanks!', str(uuid.uuid4()), 'info', 'two', reply_to=second)
    assert [(t['id'], t['unread']) for t in view('threads')['threads']] == [(first, 1), (second, 0)]
    assert view('summary')['threads'] == 1
    # Marks never move back, and a mark through an older message leaves the newer reply unread.
    board_inbox.mark_read('operator', first, through=first)
    assert view('threads')['threads'][0]['unread'] == 1
    board_inbox.mark_read('operator', everything=True)
    assert view('threads')['unread'] == 0 and view('summary') == {'threads': 0, 'activity': 0}


def test_mentions_join_a_thread_and_unfollowing_hides_it_until_the_next_mention(cache):
    root = board.post('one', 'Plan for the park?', 'two')
    board.post('two', 'Asking @operator.', 'one', reply_to=root)
    threads = view('threads')['threads']
    assert [t['id'] for t in threads] == [root] and threads[0]['participants'] == ['one', 'two']
    assert [i['kind'] for i in view('activity')['items']] == ['mention']
    board.post('one', 'While we wait: the left side.', 'two', reply_to=root)
    assert view('activity')['items'][0]['kind'] == 'reply'

    board_inbox.mark_read('operator', root, follow=False)
    assert view('threads')['threads'] == []
    board.post('two', 'Still discussing.', 'one', reply_to=root)
    assert view('threads')['threads'] == [] and view('summary') == {'threads': 0, 'activity': 0}
    board.post('one', '@operator, we need you.', 'two', reply_to=root)
    assert [t['id'] for t in view('threads')['threads']] == [root]
    # An e-mail-like address or a longer name is not a mention.
    board.post('one', 'Mail ops@operator.example or ask @operators.', 'two')
    assert view('activity', kind='mention')['total'] == 2


def test_activity_is_newest_first_with_kinds_unread_filters_and_grouped_acks(cache):
    hello = board.post('three', 'Hello operator.', 'operator')
    shout = board.send_web('operator', 'Freeze merges for an hour.', str(uuid.uuid4()), 'request')
    copies = {row['recipient']: row['id'] for row in shout}
    board.post('one', 'Frozen.', 'operator', 'ack', reply_to=copies['one'])
    board.post('two', 'Frozen here too.', 'operator', 'ack', reply_to=copies['two'])
    chat = ask('one', 'Status?')
    board.post('one', 'Building.', 'operator', reply_to=chat)
    board.post('one', 'cc two', 'two', reply_to=chat)
    board.post('two', 'Seen.', 'one', reply_to=chat)
    # An acknowledgement of another agent's message is theirs, not the operator's.
    board.post('two', 'Got it.', 'one', 'ack', reply_to=board.post('one', 'Note', 'two'))

    items = view('activity')['items']
    assert [(i['kind'], i['count']) for i in items] == [('reply', 2), ('reply', 1), ('ack', 2), ('dm', 1)]
    assert items[0]['senders'] == ['one', 'two'] and items[0]['thread'] == chat
    assert items[2]['senders'] == ['one', 'two'] and items[2]['target']['body'] == 'Freeze merges for an hour.'
    assert items[3]['id'] == hello and items[3]['root'] is None and items[3]['reply_audience'] == ['three']
    unread = view('activity')['unread']
    # Acknowledgements are shown as unread, but only real messages raise the badge.
    assert unread == {'all': 3, 'mention': 0, 'reply': 2, 'dm': 1, 'ack': 1}
    # Nor do they make a thread unread: the broadcast's thread is listed, read.
    assert view('summary') == {'threads': 1, 'activity': 3}
    assert [(t['id'], t['unread']) for t in view('threads')['threads']] == [(chat, 3), (copies['one'], 0)]
    assert [i['kind'] for i in view('activity', kind='dm')['items']] == ['dm']
    board_inbox.mark_read('operator', hello)
    assert [i['id'] for i in view('activity', unread_only=True)['items']] == [items[0]['id'], items[1]['id'], items[2]['id']]
    with pytest.raises(ValueError):
        view('activity', kind='reaction')


def test_history_from_before_read_state_starts_read(cache):
    first = ask('one', 'Old question')
    board.post('one', 'Old answer', 'operator', reply_to=first)
    with board.database() as db:
        db.execute('DROP TABLE reads')
    assert view('summary') == {'threads': 0, 'activity': 0}
    with board.database():
        pass
    assert view('summary') == {'threads': 0, 'activity': 0} and view('threads')['total'] == 1
    board.post('one', 'New answer', 'operator', reply_to=first)
    assert view('summary') == {'threads': 1, 'activity': 1}


@pytest.fixture
def http_server(cache):
    server = board_web.Server(('127.0.0.1', 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown(); server.server_close(); thread.join(timeout=3)


def request(server, path, payload=None, headers=None):
    url = f'http://127.0.0.1:{server.server_port}'
    values = {'Origin': url, 'Content-Type': 'application/json', 'X-Board-CSRF': server.csrf, **(headers or {})}
    req = Request(url+path, data=None if payload is None else json.dumps(payload).encode(), headers=values)
    try:
        response = urlopen(req, timeout=3)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.loads(response.read())


def test_http_views_badges_and_csrf_protected_read_marks(http_server):
    root = ask('one', 'Can you check **this**?')
    reply = board.post('one', 'Checked.', 'operator', reply_to=root)
    status, state = request(http_server, '/api/state')
    assert status == 200 and state['inbox'] == {'threads': 1, 'activity': 1}
    status, threads = request(http_server, '/api/threads?limit=5')
    assert status == 200 and threads['threads'][0]['root']['body_html'] == '<p>Can you check <strong>this</strong>?</p>\n'
    status, activity = request(http_server, '/api/activity?kind=reply&unread=1')
    assert status == 200 and [i['id'] for i in activity['items']] == [reply]
    assert request(http_server, '/api/activity?kind=nope')[0] == 400
    assert request(http_server, '/api/threads?limit=0')[0] == 400

    assert request(http_server, '/api/read', {'id': reply}, {'X-Board-CSRF': 'wrong'})[0] == 403
    assert request(http_server, '/api/read', {'id': '1'})[0] == 400
    assert request(http_server, '/api/read', {'id': 99999})[0] == 400
    assert request(http_server, '/api/read', {'id': reply, 'follow': 'no'})[0] == 400
    status, marked = request(http_server, '/api/read', {'id': reply, 'through': reply})
    assert status == 200 and marked['read'].startswith('web-direct:')
    assert request(http_server, '/api/state')[1]['inbox'] == {'threads': 0, 'activity': 0}
    board.post('one', 'One more thing.', 'operator', reply_to=reply)
    assert request(http_server, '/api/read', {'all': True}) == (200, {'read': '*'})
    assert request(http_server, '/api/state')[1]['inbox'] == {'threads': 0, 'activity': 0}
