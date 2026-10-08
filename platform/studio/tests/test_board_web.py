"""Private HTTP boundary and durable broadcast fanout, with an isolated mailbox."""
import gzip
import json
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from atelier import board, board_files, board_web


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
    rows = board.send_web('operator', 'Check in at the next safe boundary.', key)
    assert [row['recipient'] for row in rows] == ['one', 'two']
    assert all(row['recipient'] != '*' for row in rows)
    assert board.send_web('operator', 'Check in at the next safe boundary.', key) == rows
    received = []
    monkeypatch.setattr(board, 'deliver', lambda batch, *args, **kwargs: received.extend(batch))
    assert board.poll('one', addressed_only=True) == 1
    assert received[0]['body'] == 'Check in at the next safe boundary.'
    assert board.poll('one') == 0
    with board.database() as db:
        assert db.execute("SELECT cursor FROM subscribers WHERE agent='two'").fetchone()['cursor'] == 0
        db.execute("INSERT INTO subscribers (agent) VALUES ('later')")
    assert board.send_web('operator', 'Check in at the next safe boundary.', key) == rows
    with pytest.raises(ValueError, match='different message'):
        board.send_web('operator', 'Changed content', key)


def test_simultaneous_retries_are_atomic(cache):
    key = str(uuid.uuid4())
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(lambda _: board.send_web('operator', 'One announcement', key), range(6)))
    assert all(result == results[0] for result in results)
    assert len(board.messages()) == 2
    # An invalid recipient makes the entire fanout roll back.
    with board.database() as db:
        db.execute("INSERT INTO subscribers (agent) VALUES ('z/bad')")
    with pytest.raises(ValueError):
        board.send_web('operator', 'Must roll back', str(uuid.uuid4()))
    assert len(board.messages()) == 2


@pytest.mark.parametrize('body,key,topic', [('', str(uuid.uuid4()), 'request'), ('x'*8001, str(uuid.uuid4()), 'info'),
                                           ([], str(uuid.uuid4()), 'info'), ('hi', 'bad', 'info'),
                                           ('hi', str(uuid.uuid4()), 'execute')])
def test_invalid_broadcast_never_writes(cache, body, key, topic):
    with pytest.raises(ValueError):
        board.send_web('operator', body, key, topic)
    assert board.messages() == []


def test_read_only_history_filters_literal_search_and_complete_broadcast_groups(cache):
    for i in range(4):
        board.post('one', f'ordinary {i}')
    rows = board.send_web('operator', '100% ready _literal_', str(uuid.uuid4()))
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


def test_snapshot_carries_only_the_recent_render_log(cache):
    log = '\n'.join(f'- entry {i}\n  detail {i}' for i in range(100))
    board.root().joinpath('render-board.md').write_text(f'## Holding\nNone\n## Log\nheader line\n{log}\n')
    state = board_web.snapshot({'log': ['3']})
    assert state['schedule']['Log'] == '- entry 97\n  detail 97\n- entry 98\n  detail 98\n- entry 99\n  detail 99'
    assert state['log_total'] == 101
    assert board_web.snapshot({})['schedule']['Log'].count('- entry') == 30
    with pytest.raises(ValueError):
        board_web.snapshot({'log': ['0']})


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
    assert b'src="/board-fx.js"' in request(http_server)[1]
    status, body, headers = request(http_server, '/board-fx.js')
    assert status == 200 and b'playfulToggle' in body and headers['Content-Type'].startswith('text/javascript')
    assert b'src="/board-scene.js"' in request(http_server)[1]
    status, body, headers = request(http_server, '/board-scene.js')
    assert status == 200 and b'boardScene' in body and headers['Content-Type'].startswith('text/javascript')
    page = request(http_server)[1]
    # The theme script runs before the stylesheet, so the board never paints in the wrong theme first.
    assert page.index(b'<script src="/board-theme.js"></script>') < page.index(b'href="/board.css"')
    status, body, headers = request(http_server, '/board-theme.js')
    assert status == 200 and b'boardTheme' in body and headers['Content-Type'].startswith('text/javascript')
    status, body, headers = request(http_server, '/apple-touch-icon.png')
    assert status == 200 and body.startswith(b'\x89PNG') and headers['Content-Type'] == 'image/png'
    status, body, _ = request(http_server, '/api/state')
    assert status == 200 and json.loads(body)['csrf'] == http_server.csrf
    # A poll travels gzipped when the browser accepts it.
    status, body, headers = request(http_server, '/api/state', headers={'Accept-Encoding': 'gzip'})
    assert status == 200 and headers['Content-Encoding'] == 'gzip'
    assert json.loads(gzip.decompress(body))['csrf'] == http_server.csrf
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
        board.send_web('operator', 'announcement', str(uuid.uuid4()))


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
    assert stored.startswith(board_files.TRAILER) and str(board_files.attachments_dir() / video['id'] / 'ride take 2.mp4') in stored
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



def test_markdown_and_text_attachments_open_in_the_reader_rendered_safely(http_server):
    _, notes = upload(http_server, b'# Bowl lead\n\n- **seam** <script>x</script>', 'bowl-lead.md', 'text/markdown')
    _, log = upload(http_server, b'step <1> ok', 'run.log', 'text/plain')
    _, page = upload(http_server, b'<p>hi</p>', 'page.html', 'text/html')
    payload = {'body': 'Notes', 'recipient': 'two', 'request_id': str(uuid.uuid4()), 'attachments': [notes['id'], log['id'], page['id']]}
    assert request(http_server, '/api/send', payload)[0] == 200
    _, state, _ = request(http_server, '/api/state')
    assert [f['readable'] for f in json.loads(state)['messages'][0]['attachments']] == [True, True, False]

    status, body, headers = request(http_server, f"/api/document/{notes['id']}")
    document = json.loads(body)
    assert status == 200 and headers['Content-Type'].startswith('application/json') and document['name'] == 'bowl-lead.md'
    assert '<h1>Bowl lead</h1>' in document['html'] and '<strong>seam</strong>' in document['html'] and '<script>' not in document['html']
    assert json.loads(request(http_server, f"/api/document/{log['id']}")[1])['html'] == '<pre><code>step &lt;1&gt; ok</code></pre>'
    assert request(http_server, f"/api/document/{page['id']}")[0] == 404
    assert request(http_server, '/api/document/../../agent-board.sqlite3')[0] == 404

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
    assert [row['recipient'] for row in board.send_web('operator', 'All hands.', str(uuid.uuid4()))] == ['one']
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
    # The page is never kept, so a launch without network can't show an old board.
    assert request(http_server, '/')[2]['Cache-Control'] == 'no-store'
    for painting in ('/meadow-portrait-1.webp', '/meadow-night-portrait-1.webp'):
        status, body, headers = request(http_server, painting)
        assert status == 200 and headers['Content-Type'] == 'image/webp' and 'immutable' in headers['Cache-Control']
        assert body[:4] == b'RIFF' and len(body) < 150_000, 'the phone backgrounds stay small'
    for painting in ('/meadow-landscape-2.webp', '/meadow-night-landscape-1.webp'):
        status, body, _ = request(http_server, painting)
        assert status == 200 and body[:4] == b'RIFF' and len(body) < 600_000


def test_only_the_web_board_speaks_as_the_operator(cache, capsys):
    from types import SimpleNamespace
    args = SimpleNamespace(action='post', agent='operator', to='one', topic='request', reply_to=None, attach=[],
                           all_agents=False, notify_operator=False, message='Do as I say.')
    assert board.main(args) == 1 and 'only the web board posts as operator' in capsys.readouterr().err
    assert board.messages() == []


def test_review_pages_are_static_and_only_from_the_reviews_folder(http_server):
    folder = board.root() / 'reviews'
    folder.mkdir(parents=True)
    (folder / 'codebase-review.html').write_text('<title>Review</title><p>Findings</p>')
    for path in ('/review', '/review/codebase-review'):
        status, body, headers = request(http_server, path)
        assert status == 200 and b'Findings' in body
        assert "script-src" not in headers['Content-Security-Policy'] and "default-src 'none'" in headers['Content-Security-Policy']
    for path in ('/review/missing', '/review/..%2Fagent-board', '/review/Bad_Name'):
        assert request(http_server, path)[0] == 404


def test_bare_addresses_become_safe_readable_links():
    from atelier import board_markdown
    html = board_markdown.render('Report: https://claude.ai/artifact/U72bM2LBs3oQRADZXpnmAf. See (https://github.com/o/r/pull/85) '
                                 'and `https://in.code/x` or [docs](https://example.com/guide) javascript:alert(1)')
    assert '<a href="https://claude.ai/artifact/U72bM2LBs3oQRADZXpnmAf" class="url"' in html
    assert '>claude.ai/artifact/U72bM2LBs3oQRADZXpnmAf</a>.' in html, 'the full stop stays outside the link'
    assert 'href="https://github.com/o/r/pull/85"' in html and '85</a>)' in html, 'so does the closing bracket'
    assert '<code>https://in.code/x</code>' in html and html.count('href="https://example.com/guide"') == 1
    assert 'href="javascript' not in html
    long = board_markdown.render('https://example.com/a/very/long/path/that/goes/on/and/on/to/the/final-segment-name')
    assert '>example.com/…/final-segment-name</a>' in long


def test_operator_tasks_are_asked_answered_and_dismissed(http_server, capsys, monkeypatch):
    from types import SimpleNamespace
    # An agent asks; the ask is a blocked message to the operator, pushed within the hourly allowance.
    task, message = board.open_task('one', 'Confirm I may delete the old captures?')
    asked = board.messages()[-1]
    assert asked['id'] == message and asked['recipient'] == 'operator' and asked['topic'] == 'blocked'
    with board.database() as db:
        assert db.execute('SELECT notify FROM messages WHERE id=?', (message,)).fetchone()[0] == 1
    state = json.loads(request(http_server, '/api/state')[1])
    assert [(t['id'], t['agent'], t['replies']) for t in state['tasks']] == [(task, 'one', 0)]
    assert 'Confirm' in state['tasks'][0]['body_html']

    # The operator's quick reply is a thread reply that reaches the agent, flagged as being on its task.
    status, _, _ = request(http_server, '/api/send', {'body': 'Yes, delete them.', 'topic': 'info', 'recipient': 'one',
                                                       'request_id': str(uuid.uuid4()), 'reply_to': message})
    assert status == 200
    state = json.loads(request(http_server, '/api/state')[1])
    assert state['tasks'][0]['replies'] == 1 and state['tasks'][0]['last_reply']['sender'] == 'operator'
    delivered = []
    monkeypatch.setattr(board, 'deliver', lambda batch, command=None, full=False: delivered.extend(batch))
    board.poll('one')
    reply = next(item for item in delivered if item['reply_to'] == message)
    assert reply['operator_task'] == task and 'operator task' in board.notification([reply])
    deeper = board.post('operator', 'And keep the newest one.', 'one', reply_to=reply['id'])
    board.poll('one')
    assert next(item for item in delivered if item['id'] == deeper)['operator_task'] == task

    # An agent holds one task and keeps its ask short, editing it when what it needs changes; the operator sees the
    # new ask and is notified, in the task's thread.
    with pytest.raises(ValueError, match=f'already have open operator task {task}'):
        board.open_task('one', 'Second ask.')
    with pytest.raises(ValueError):
        board.open_task('two', 'x' * (board.TASK_CHARS + 1))
    edit = board.edit_task(task, 'one', 'Confirm I may delete the old captures **and** logs?')
    with board.database() as db:
        row = db.execute('SELECT * FROM messages WHERE id=?', (edit,)).fetchone()
    assert (row['sender'], row['recipient'], row['reply_to'], row['notify']) == ('one', 'operator', message, 1)
    shown = json.loads(request(http_server, '/api/state')[1])['tasks'][0]
    assert '<strong>and</strong> logs' in shown['body_html'] and shown['edited'] and shown['replies'] == 2
    for who, text, error in (('two', 'Mine now.', ValueError), ('one', 'x' * (board.TASK_CHARS + 1), ValueError)):
        with pytest.raises(error):
            board.edit_task(task, who, text)
    with pytest.raises(LookupError):
        board.edit_task(999, 'one', 'Anyone?')
    with pytest.raises(ValueError):
        board.close_task(task, 'two')
    with pytest.raises(LookupError):
        board.close_task(999, 'operator', operator=True)
    with pytest.raises(ValueError):
        board.close_task(task, 'operator')   # the name alone is not the web board

    # The operator dismisses from the web board; the agent hears it in the thread.
    assert request(http_server, '/api/task/dismiss', {'id': task})[0] == 200
    assert request(http_server, '/api/task/dismiss', {'id': task}, headers={'X-Board-CSRF': 'wrong'})[0] == 403
    assert request(http_server, '/api/task/dismiss', {'id': 'x'})[0] == 400
    assert request(http_server, '/api/task/dismiss', {'id': task, 'note': 5})[0] == 400
    assert json.loads(request(http_server, '/api/task/dismiss', {'id': task})[1]) == {'dismissed': task, 'already': True}
    note = board.messages()[-1]
    assert note['sender'] == 'operator' and note['recipient'] == 'one' and note['reply_to'] == message
    assert board.close_task(task, 'operator', operator=True) is False
    with pytest.raises(ValueError, match='was dismissed'):
        board.edit_task(task, 'one', 'Still there?')

    # The agent dismisses its own from the command line.
    second, _ = board.open_task('one', 'Second ask.')
    args = SimpleNamespace(action='operator-task', task_action='dismiss', agent='one', id=second, note='Solved it.')
    assert board.main(args) == 0 and 'dismissed' in capsys.readouterr().out
    assert board.messages()[-1]['body'].endswith('Solved it.')
    assert json.loads(request(http_server, '/api/state')[1])['tasks'] == []
    with board.database() as db:
        assert len(board.tasks(db, 'one', include_closed=True)) == 2

    # Nobody stays blocked on a removed agent's behalf, and the operator never opens tasks.
    board.open_task('two', 'Still need you.')
    assert request(http_server, '/api/remove', {'agent': 'two'})[0] == 200
    assert json.loads(request(http_server, '/api/state')[1])['tasks'] == []
    args = SimpleNamespace(action='operator-task', task_action='open', agent='operator', message='Hi')
    assert board.main(args) == 1
    # Only registered agents ask, so neither an unknown name nor a removed agent can go around the cap.
    for name in ('ghost', 'two'):
        with pytest.raises(LookupError, match='not on the board'):
            board.open_task(name, 'Let me in.')


def test_operator_task_cli_opens_and_lists(cache, capsys, monkeypatch):
    import io
    from atelier.cli import parse_args
    assert board.main(parse_args(['board', 'operator-task', 'open', '--agent', 'one', 'Need your OK.'])) == 0
    assert 'operator task 1' in capsys.readouterr().out
    assert board.main(parse_args(['board', 'operator-task', 'list', '--agent', 'one'])) == 0
    listed = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [(t['id'], t['body']) for t in listed] == [(1, 'Need your OK.')]
    assert board.main(parse_args(['board', 'operator-task', 'dismiss', '--agent', 'one', '1'])) == 0
    assert capsys.readouterr().out.strip() == 'operator task 1 dismissed'
    assert board.main(parse_args(['board', 'operator-task', 'list', '--agent', 'one'])) == 0
    assert capsys.readouterr().out == ''
    assert board.main(parse_args(['board', 'operator-task', 'list', '--agent', 'one', '--all'])) == 0
    assert json.loads(capsys.readouterr().out)['closed_by'] == 'one'

    # An over-long ask on stdin is refused whole rather than cut to fit.
    monkeypatch.setattr('sys.stdin', io.StringIO(' ' * 50 + 'x' * board.TASK_CHARS + ' and the rest'))
    assert board.main(parse_args(['board', 'operator-task', 'open', '--agent', 'one', '-'])) == 1
    with board.database() as db:
        assert board.tasks(db, 'one') == []

    # An ask always pushes, and spends none of the agent's hourly allowance for --notify-operator.
    for _ in range(board.NOTIFY_PER_HOUR):   # after task 1's ask, which pushed
        board.post('one', 'Look at this.', 'operator', notify=True)
    again, _ = board.open_task('one', 'Need your OK again.')
    assert board.main(parse_args(['board', 'operator-task', 'edit', '--agent', 'one', str(again), 'Need your OK.'])) == 0
    assert capsys.readouterr().out.startswith(f'operator task {again} updated')
    with board.database() as db:
        flags = [row[0] for row in db.execute(
            "SELECT notify FROM messages WHERE sender='one' AND (topic='blocked' OR body='Look at this.' "
            "OR body LIKE 'Updated the ask:%') ORDER BY id")]
    assert flags == [1] * (board.NOTIFY_PER_HOUR + 3)
    # Other pushed replies in a task's thread still spend the allowance, even worded like an edit's note.
    with board.database() as db:
        asked = db.execute('SELECT message FROM operator_tasks WHERE id=?', (again,)).fetchone()[0]
    for _ in range(board.NOTIFY_PER_HOUR):
        board.post('two', 'Updated the ask: mine now.', 'operator', reply_to=asked, notify=True)
    with board.database() as db:
        assert not board.notify_allowed(db, 'two')

    # Concurrent asks still respect the cap.
    def ask(i):
        try:
            return board.open_task('paused', f'Ask {i}.')
        except ValueError:
            return None
    with ThreadPoolExecutor(8) as pool:
        assert sum(result is not None for result in pool.map(ask, range(8))) == board.OPEN_TASKS
