"""Private HTTP boundary and durable broadcast fanout, with an isolated mailbox."""
import json
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from atelier import board, board_web


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv('ATELIER_CACHE', str(tmp_path / 'cache'))
    monkeypatch.setenv('ATELIER_RENDER_LOCK', str(tmp_path / 'render.lock'))
    with board.database() as db:
        db.executemany('INSERT INTO subscribers (agent,pid,heartbeat,stop) VALUES (?,?,?,?)',
                       [('one', 1, time.time(), 0), ('two', None, 0, 0), ('paused', None, 0, 1)])
    return tmp_path


def test_broadcast_reaches_addressed_only_and_offline_agents_without_duplicate_delivery(cache, monkeypatch):
    key = str(uuid.uuid4())
    rows = board.broadcast('operator', 'Check in at the next safe boundary.', key)
    assert [row['recipient'] for row in rows] == ['one', 'two']
    assert all(row['recipient'] != '*' for row in rows)
    assert board.broadcast('operator', 'Check in at the next safe boundary.', key) == rows
    received = []
    monkeypatch.setattr(board, 'deliver', lambda batch, *args, **kwargs: received.extend(batch))
    assert board.poll('one', addressed_only=True) == 1
    assert received[0]['body'] == 'Check in at the next safe boundary.'
    assert board.poll('one') == 0
    with board.database() as db:
        assert db.execute("SELECT cursor FROM subscribers WHERE agent='two'").fetchone()['cursor'] == 0
        db.execute("INSERT INTO subscribers (agent) VALUES ('later')")
    assert board.broadcast('operator', 'Check in at the next safe boundary.', key) == rows
    with pytest.raises(ValueError, match='different message'):
        board.broadcast('operator', 'Changed content', key)


def test_simultaneous_retries_are_atomic(cache):
    key = str(uuid.uuid4())
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(lambda _: board.broadcast('operator', 'One announcement', key), range(6)))
    assert all(result == results[0] for result in results)
    assert len(board.messages()) == 2
    # An invalid recipient makes the entire fanout roll back.
    with board.database() as db:
        db.execute("INSERT INTO subscribers (agent) VALUES ('z/bad')")
    with pytest.raises(ValueError):
        board.broadcast('operator', 'Must roll back', str(uuid.uuid4()))
    assert len(board.messages()) == 2


@pytest.mark.parametrize('body,key,topic', [('', str(uuid.uuid4()), 'request'), ('x'*8001, str(uuid.uuid4()), 'info'),
                                           ([], str(uuid.uuid4()), 'info'), ('hi', 'bad', 'info'),
                                           ('hi', str(uuid.uuid4()), 'execute')])
def test_invalid_broadcast_never_writes(cache, body, key, topic):
    with pytest.raises(ValueError):
        board.broadcast('operator', body, key, topic)
    assert board.messages() == []


def test_read_only_history_filters_literal_search_and_complete_broadcast_groups(cache):
    for i in range(4):
        board.post('one', f'ordinary {i}')
    rows = board.broadcast('operator', '100% ready _literal_', str(uuid.uuid4()))
    board.root().joinpath('render-board.md').write_text('## Holding\nNone\n## Waiting\n- review\n')
    initial = board_web.snapshot({'limit': ['1']})
    assert [m['id'] for m in initial['messages']] == [rows[1]['id'], rows[0]['id']]
    assert initial['has_more']
    assert initial['schedule']['Waiting'] == '- review'
    previous = board_web.snapshot({'before': [str(rows[0]['id'])], 'limit': ['2']})
    assert [m['id'] for m in previous['messages']] == [4, 3]
    assert len(board_web.snapshot({'q': ['%']})['messages']) == 2
    assert board_web.snapshot({'q': ['%not-a-wildcard']})['messages'] == []
    assert len(board_web.snapshot({'agent': ['one'], 'topic': ['request']})['messages']) == 2
    assert {a['agent']: a['cursor'] for a in initial['agents']} == {'one': 0, 'two': 0, 'paused': 0}
    assert [a['pending'] for a in initial['agents'] if a['agent'] == 'two'] == [1]


@pytest.fixture
def http_server(cache):
    server = board_web.Server(('127.0.0.1', 0), origins=['https://board.example.ts.net'], allowed_user='owner@example.test')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown(); server.server_close(); thread.join(timeout=3)


def request(server, path='/', payload=None, headers=None):
    url = f'http://127.0.0.1:{server.server_port}'
    values = {'Origin': url, 'Content-Type': 'application/json', 'X-Board-CSRF': server.csrf}
    values.update(headers or {})
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(url+path, data=data, headers=values)
    try:
        response = urlopen(req, timeout=3)
    except HTTPError as error:
        response = error
    with response:
        body = response.read()
        return response.status, body, response.headers


def test_http_static_and_read_only_api(http_server):
    status, body, headers = request(http_server)
    assert status == 200 and b'Broadcast to everyone' in body
    assert "script-src 'self'" in headers['Content-Security-Policy']
    status, body, _ = request(http_server, '/api/state')
    assert status == 200 and json.loads(body)['csrf'] == http_server.csrf
    assert request(http_server, '/../../agent-board.sqlite3')[0] == 404
    assert request(http_server, '/api/state?limit=99999')[0] == 400
    assert request(http_server, '/api/state', headers={'Host': 'attacker.test'})[0] == 403
    assert request(http_server, '/api/state', headers={'Host': 'board.example.ts.net'})[0] == 403
    assert request(http_server, '/api/state', headers={'Host': 'board.example.ts.net', 'Tailscale-User-Login': 'owner@example.test'})[0] == 200


def test_http_broadcast_validates_csrf_identity_origin_and_idempotency(http_server):
    payload = {'body': '<script>alert("inert text")</script> $(never execute)', 'request_id': str(uuid.uuid4())}
    for headers in ({'Origin': 'https://attacker.test'}, {'X-Board-CSRF': 'wrong'}, {'Origin': ''},
                    {'Host': 'board.example.ts.net', 'Origin': 'https://board.example.ts.net'}):
        assert request(http_server, '/api/broadcast', payload, headers)[0] == 403
    assert board.messages() == []
    headers = {'Host': 'board.example.ts.net', 'Origin': 'https://board.example.ts.net', 'Tailscale-User-Login': 'owner@example.test'}
    status, body, _ = request(http_server, '/api/broadcast', payload, headers)
    assert status == 200 and json.loads(body)['recipients'] == ['one', 'two']
    assert request(http_server, '/api/broadcast', payload, headers)[1] == body
    assert len(board.messages()) == 2
    assert request(http_server, '/api/broadcast', {'body': ''})[0] == 400
    assert request(http_server, '/api/broadcast', ['not an object'])[0] == 400
    assert request(http_server, '/api/broadcast', payload, {'Content-Type': 'text/plain'})[0] == 415


def test_no_recipients_is_visible_instead_of_claiming_delivery(cache):
    with board.database() as db:
        db.execute('UPDATE subscribers SET stop=1')
    with pytest.raises(ValueError, match='No agents'):
        board.broadcast('operator', 'announcement', str(uuid.uuid4()))
