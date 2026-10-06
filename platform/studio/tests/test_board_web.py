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
    assert status == 200 and b'Send a message' in body and b'id="recipient"' in body
    assert "script-src 'self'" in headers['Content-Security-Policy']
    status, body, headers = request(http_server, '/manifest.webmanifest')
    assert status == 200 and json.loads(body)['display'] == 'standalone'
    assert headers['Content-Type'] == 'application/manifest+json'
    status, body, headers = request(http_server, '/apple-touch-icon.png')
    assert status == 200 and body.startswith(b'\x89PNG') and headers['Content-Type'] == 'image/png'
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


def test_direct_send_is_private_routing_atomic_and_retry_safe(http_server):
    payload = {'body': '**Please review**\n\n- Check the new clips.',
               'recipient': 'two', 'request_id': str(uuid.uuid4())}
    status, response, _ = request(http_server, '/api/send', payload)
    assert status == 200 and json.loads(response)['recipients'] == ['two']
    assert [row['recipient'] for row in board.messages()] == ['two']
    assert request(http_server, '/api/send', payload)[1] == response
    for target in ('one', '*', 'paused', 'unknown', None, ['one']):
        assert request(http_server, '/api/send', dict(payload, recipient=target))[0] == 400
    assert request(http_server, '/api/broadcast', payload)[0] == 400
    assert len(board.messages()) == 1
    assert request(http_server, '/api/send', dict(payload, request_id=str(uuid.uuid4())),
                   {'X-Board-CSRF': 'wrong'})[0] == 403


def test_preview_and_history_share_safe_markdown_without_posts_or_cursor_changes(http_server):
    body = ('## Progress\n\n**Done** with `code`.\n\n- One\n- Two\n\n'
            '[Evidence](https://example.test/review)\n\n'
            '<script>window.pwned=true</script>\n<img src=x onerror=alert(1)>\n'
            '[bad](javascript:alert(1))\n![remote](https://example.test/pixel.png)')
    status, response, _ = request(http_server, '/api/preview', {'body': body})
    rendered = json.loads(response)['html']
    assert status == 200 and '<h2>Progress</h2>' in rendered and '<strong>Done</strong>' in rendered
    assert '<ul>' in rendered and '<code>code</code>' in rendered and 'noopener noreferrer' in rendered
    assert '<script' not in rendered and '<img' not in rendered and 'href="javascript:' not in rendered
    assert board.messages() == []
    number = board.post('one', body, recipient='two')
    state = board_web.snapshot({})
    assert state['messages'][0]['body_html'] == rendered
    assert not state['messages'][0]['acknowledged']
    # A transport cursor and an unrelated sender's reply are not an acknowledgement.
    with board.database() as db:
        db.execute("UPDATE subscribers SET cursor=? WHERE agent='two'", (number,))
    board.post('one', 'wrong owner ack', recipient='operator', topic='ack', reply_to=number)
    assert not next(m for m in board_web.snapshot({})['messages'] if m['id'] == number)['acknowledged']
    board.post('two', '**Received** — review in two minutes.', recipient='one', topic='ack', reply_to=number)
    assert next(m for m in board_web.snapshot({})['messages'] if m['id'] == number)['acknowledged']
    assert request(http_server, '/api/preview', {'body': body}, {'Origin': 'https://attacker.test'})[0] == 403


def upload(server, data, name, mime, headers=None):
    url = f'http://127.0.0.1:{server.server_port}'
    values = {'Origin': url, 'Content-Type': mime, 'X-Board-CSRF': server.csrf, 'X-File-Name': name}
    values.update(headers or {})
    try:
        response = urlopen(Request(url+'/api/upload', data=data, headers=values), timeout=3)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.loads(response.read())


def test_attachments_upload_send_stream_and_never_render_inline_markup(http_server):
    clip = bytes(range(256)) * 40
    status, video = upload(http_server, clip, 'ride%20take%202.mp4', 'video/mp4')
    assert status == 200 and video['size'] == len(clip) and video['name'] == 'ride take 2.mp4'
    _, page = upload(http_server, b'<script>alert(1)</script>', '../../evil.html', 'text/html')
    assert page['name'] == 'evil.html'
    assert upload(http_server, b'x', 'a.txt', 'text/plain', {'X-Board-CSRF': 'wrong'})[0] == 403

    payload = {'body': '', 'recipient': 'two', 'request_id': str(uuid.uuid4()), 'attachments': [video['id'], page['id']]}
    assert request(http_server, '/api/send', payload)[0] == 200
    stored = board.messages()[0]['body']
    # Agents reading with the CLI get absolute paths they can open.
    assert stored.startswith(board_web.TRAILER) and str(board_web.attachments_dir() / video['id'] / 'ride take 2.mp4') in stored
    assert request(http_server, '/api/send', dict(payload, request_id=str(uuid.uuid4()), attachments=['f'*24]))[0] == 400

    _, state, _ = request(http_server, '/api/state')
    message = json.loads(state)['messages'][0]
    assert message['body_html'] == '' and [item['name'] for item in message['attachments']] == ['ride take 2.mp4', 'evil.html']

    status, body, headers = request(http_server, message['attachments'][0]['url'], headers={'Range': 'bytes=100-199'})
    assert status == 206 and body == clip[100:200] and headers['Content-Range'] == f'bytes 100-199/{len(clip)}'
    assert headers['Content-Type'] == 'video/mp4' and 'sandbox' in headers['Content-Security-Policy']
    status, body, headers = request(http_server, message['attachments'][1]['url'])
    assert status == 200 and headers['Content-Type'] == 'application/octet-stream'
    assert headers['Content-Disposition'].startswith('attachment')
    assert request(http_server, '/api/attachment/../../agent-board.sqlite3')[0] == 404
    assert request(http_server, message['attachments'][0]['url'], headers={'Host': 'board.example.ts.net'})[0] == 403


def test_threads_collect_replies_to_replies_and_web_replies_keep_their_thread(http_server):
    root = board.post('one', 'Can someone check the ramp?', recipient='operator', topic='request')
    ack = board.post('two', 'On it.', recipient='one', topic='ack', reply_to=root)
    deeper = board.post('one', 'Thanks, the left side first.', recipient='two', reply_to=ack)
    board.post('two', 'Unrelated news.')
    payload = {'body': 'Looks good to me.', 'recipient': 'one', 'request_id': str(uuid.uuid4()), 'reply_to': root}
    status, response, _ = request(http_server, '/api/send', payload)
    mine = json.loads(response)['messages'][0]
    assert status == 200 and mine['reply_to'] == root
    # A retry must keep the same thread, and the same request cannot move to another thread.
    assert request(http_server, '/api/send', payload)[1] == response
    assert request(http_server, '/api/send', dict(payload, reply_to=ack))[0] == 400
    assert request(http_server, '/api/send', dict(payload, request_id=str(uuid.uuid4()), reply_to=99999))[0] == 400
    assert request(http_server, '/api/send', dict(payload, request_id=str(uuid.uuid4()), reply_to='1'))[0] == 400

    for member in (root, ack, deeper, mine['id']):
        status, body, _ = request(http_server, f'/api/thread?id={member}')
        thread = json.loads(body)
        assert status == 200 and [row['id'] for row in thread['root']] == [root]
        assert [row['id'] for row in thread['replies']] == [ack, deeper, mine['id']]
    assert thread['root'][0]['acknowledged'] is False and thread['replies'][0]['body_html'] == '<p>On it.</p>\n'
    assert request(http_server, '/api/thread?id=99999')[0] == 404


def test_agents_see_every_recipient_and_direct_views_exclude_broadcast_copies(http_server):
    broadcast = {'body': 'Everyone: freeze canonical.', 'request_id': str(uuid.uuid4())}
    assert request(http_server, '/api/broadcast', broadcast)[0] == 200
    direct = {'body': 'Only for one.', 'recipient': 'one', 'request_id': str(uuid.uuid4())}
    assert request(http_server, '/api/send', direct)[0] == 200
    reply = board.post('one', 'Got it.', recipient='operator', reply_to=board.messages()[-1]['id'])

    # Each agent holds one copy of a broadcast, so the copy alone looks direct: the audience says otherwise.
    copies = [row for row in board.messages(agent='one', addressed_only=True)]
    assert copies[0]['audience'] == ['one', 'two'] and copies[1]['audience'] == ['one']
    text = board.notification(copies)
    assert 'broadcast to 2 agents: one, two' in text and 'direct: only you' in text

    _, body, _ = request(http_server, '/api/state?dm=one')
    ids = [m['id'] for m in json.loads(body)['messages']]
    assert ids == [reply, copies[1]['id']], 'the direct view has the DM and its reply, never the broadcast copy'
    agents = {a['agent']: a for a in json.loads(body)['agents']}
    assert agents['one']['last_to_me'] == reply and agents['two']['last_to_me'] == 0


def test_uploads_keep_media_size_so_the_feed_can_reserve_space(http_server):
    status, image = upload(http_server, b'\x89PNG' + b'\0' * 64, 'shot.png', 'image/png',
                           {'X-Media-Width': '1320', 'X-Media-Height': '2868'})
    assert status == 200 and (image['width'], image['height']) == (1320, 2868)
    _, bad = upload(http_server, b'x' * 10, 'odd.png', 'image/png', {'X-Media-Width': '-4', 'X-Media-Height': 'tall'})
    assert bad['width'] is None and bad['height'] is None


def test_mentions_reach_exactly_the_mentioned_agents_as_one_message(http_server):
    with board.database() as db:
        db.execute("INSERT INTO subscribers (agent) VALUES ('three')")
    key = str(uuid.uuid4())
    mention = {'body': '@two @one please pair on this.', 'recipient': ['two', 'one'], 'request_id': key}
    status, body, _ = request(http_server, '/api/send', mention)
    assert status == 200 and json.loads(body)['recipients'] == ['one', 'two']
    rows = json.loads(body)['messages']
    assert all(row['dedup'].startswith(f'web-broadcast:{key}~m:') for row in rows), 'one message to both, by name'
    assert request(http_server, '/api/send', {**mention, 'recipient': '*'})[0] == 400
    assert json.loads(request(http_server, '/api/send', mention)[1])['messages'] == rows, 'a retry is the same send'
    assert request(http_server, '/api/send', {**mention, 'recipient': ['one']})[0] == 400
    assert board.messages(agent='three', addressed_only=True) == []
    assert board.messages(agent='one', addressed_only=True)[0]['audience'] == ['one', 'two']

    before = len(board.messages())
    retired = {'body': 'Hi', 'recipient': ['one', 'paused'], 'request_id': str(uuid.uuid4())}
    status, body, _ = request(http_server, '/api/send', retired)
    assert status == 400 and 'paused' in json.loads(body)['error'] and len(board.messages()) == before
    single = {'body': 'Just you.', 'recipient': ['one'], 'request_id': str(uuid.uuid4())}
    assert json.loads(request(http_server, '/api/send', single)[1])['messages'][0]['dedup'].startswith('web-direct:')


def test_removing_an_evicted_agent_hides_it_and_stops_delivery_but_keeps_history(http_server, monkeypatch):
    said = board.post('two', 'Last words before eviction.')
    status, body, _ = request(http_server, '/api/remove', {'agent': 'two'})
    assert status == 200
    state = json.loads(request(http_server, '/api/state')[1])
    assert 'two' not in {a['agent'] for a in state['agents']} and said in {m['id'] for m in state['messages']}
    assert request(http_server, '/api/send', {'body': 'Hi', 'recipient': 'two', 'request_id': str(uuid.uuid4())})[0] == 400
    assert [row['recipient'] for row in board.broadcast('operator', 'All hands.', str(uuid.uuid4()))] == ['one']
    assert request(http_server, '/api/remove', {'agent': 'nobody'})[0] == 400
    assert request(http_server, '/api/remove', {'agent': 'one'}, headers={'X-Board-CSRF': 'wrong'})[0] == 403

    # A supervised listener is retired through its service manager, so launchd cannot bring it back.
    from atelier import board_service
    retired = []
    monkeypatch.setattr(board_service, 'retire', retired.append)
    with board.database() as db:
        db.execute("UPDATE subscribers SET supervised='label' WHERE agent='one'")
    assert request(http_server, '/api/remove', {'agent': 'one'})[0] == 200 and retired == ['one']

    # Subscribing again brings an agent back.
    with board.subscriber('two', http_server.server_address[0]):
        state = json.loads(request(http_server, '/api/state')[1])
        assert 'two' in {a['agent'] for a in state['agents']}


def test_each_agent_has_a_one_line_task_on_the_board(http_server):
    assert board.set_task('one', '  Build the\n  agent board app  ') == 'Build the agent board app'
    agents = {a['agent']: a for a in json.loads(request(http_server, '/api/state')[1])['agents']}
    assert agents['one']['task'] == 'Build the agent board app' and agents['two']['task'] is None
    with pytest.raises(ValueError):
        board.set_task('one', 'x' * 161)
    with pytest.raises(LookupError):
        board.set_task('nobody', 'Anything')
    assert board.set_task('one', '') == ''
    assert json.loads(request(http_server, '/api/state')[1])['agents'][0]['task'] is None


def test_posts_that_would_fold_on_the_web_board_warn_the_agent(cache, capsys):
    from types import SimpleNamespace
    assert not board.folds('Short and to the point.')
    assert board.folds('x' * 501) and board.folds('\n'.join('line' for _ in range(9)))
    assert not board.folds('Fits.\n\nAttachments (files on this machine):\n' + '\n'.join(f'- /tmp/{i}' for i in range(20)))
    args = SimpleNamespace(action='post', agent='one', to='*', topic='info', reply_to=None, attach=[], all_agents=False,
                           notify_operator=False)
    assert board.main(SimpleNamespace(**vars(args), message='Short.')) == 0
    assert 'folded' not in capsys.readouterr().err
    assert board.main(SimpleNamespace(**vars(args), message='y' * 600)) == 0
    assert 'folded behind "Read more"' in capsys.readouterr().err


def test_static_files_load_fast_gzipped_revalidated_and_paintings_cached(http_server):
    import gzip
    status, body, headers = request(http_server, '/board.js', headers={'Accept-Encoding': 'gzip'})
    assert status == 200 and headers['Content-Encoding'] == 'gzip' and headers['Cache-Control'] == 'no-cache'
    assert gzip.decompress(body) == (board_web.ASSETS / 'board.js').read_bytes()
    assert request(http_server, '/board.js', headers={'If-None-Match': headers['ETag']})[0] == 304
    status, body, headers = request(http_server, '/meadow-portrait-1.webp')
    assert status == 200 and headers['Content-Type'] == 'image/webp' and 'immutable' in headers['Cache-Control']
    assert body[:4] == b'RIFF' and len(body) < 150_000, 'the phone background stays small'
