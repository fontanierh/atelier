"""Phone notifications: only flagged messages, capped per agent, end-to-end encrypted, and deep-linked."""
import base64
import hashlib
import hmac
import json
import os
import stat
import struct
import uuid

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from atelier import board

from board_server import Server
from test_board_web import cache, http_server, request  # noqa: F401  (shared fixtures)


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def unb64(text):
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def subscriptions():
    path = board.root() / 'board-push' / 'subscriptions.json'
    return json.loads(path.read_text()) if path.exists() else {}


def browser():
    """A browser's push keys, as a subscription carries them."""
    key, auth = ec.generate_private_key(ec.SECP256R1()), os.urandom(16)
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return key, {'endpoint': 'https://web.push.apple.com/QGuQyavXutnMH', 'keys': {'p256dh': b64(public),
                                                                                  'auth': b64(auth)}}


def decrypt(body, key, auth):
    """What the browser does with an aes128gcm push body (RFC 8291), independent of the sender's code."""
    salt, (size, length) = body[:16], struct.unpack('!IB', body[16:21])
    sender, ciphertext = body[21:21 + length], body[21 + length:]
    receiver = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    shared = key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), sender))
    expand = lambda salt, secret, info, n: hmac.new(hmac.new(salt, secret, hashlib.sha256).digest(),
                                                    info + b'\x01', hashlib.sha256).digest()[:n]
    ikm = expand(auth, shared, b'WebPush: info\x00' + receiver + sender, 32)
    plain = AESGCM(expand(salt, ikm, b'Content-Encoding: aes128gcm\x00', 16)).decrypt(
        expand(salt, ikm, b'Content-Encoding: nonce\x00', 12), ciphertext, None)
    assert size == 4096 and plain.endswith(b'\x02')
    return plain[:-1]


class Relay:
    """Stands in for every push service: records each push the board sends, and answers with `status`."""
    def __init__(self, status=201):
        self.calls, self.status = [], status
        relay = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers['Content-Length']))
                relay.calls.append((self.headers['X-Push-Endpoint'], body, self.headers))
                self.send_response(relay.status)
                self.send_header('Content-Length', '0')
                self.end_headers()

            def log_message(self, *_):
                pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/'

    def wait(self, count, settle=0.4):
        """Until `count` pushes have arrived, then a moment more to catch any that should not."""
        deadline = time.time() + 10
        while len(self.calls) < count and time.time() < deadline:
            time.sleep(0.02)
        time.sleep(settle)
        return len(self.calls)

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def relay():
    relay = Relay()
    yield relay
    relay.close()


def start(cache, relay):
    """The board server, pushing through the relay and checking for new messages often."""
    return Server(cache, origins=['https://board.example.ts.net'],
                  env={'ATELIER_BOARD_PUSH_RELAY': relay.url, 'ATELIER_BOARD_PUSH_INTERVAL': '0.05'})


def subscribe(server, subscription):
    return request(server, '/api/push/subscribe', {'subscription': subscription})[0]


def shown(call, key, subscription):
    return json.loads(decrypt(call[1], key, unb64(subscription['keys']['auth'])))


def test_payloads_are_encrypted_for_the_browser_and_signed_for_the_push_service(cache, relay):
    server = start(cache, relay)
    try:
        key, subscription = browser()
        assert subscribe(server, subscription) == 200
        message = board.post('one', '**Blocked** on your call: ship `v2`?', 'operator', topic='blocked', notify=True)
        assert relay.wait(1) == 1
        endpoint, body, headers = relay.calls[0]
        assert endpoint == subscription['endpoint']
        assert shown(relay.calls[0], key, subscription) == {
            'title': 'one · Blocked', 'body': 'Blocked on your call: ship v2?', 'url': f'/?m={message}',
            'tag': f'board-{message}'}
        assert headers['Content-Encoding'] == 'aes128gcm' and headers['TTL'] == '86400'

        token, public = headers['Authorization'].removeprefix('vapid t=').split(', k=')
        head, claims, signature = token.split('.')
        assert json.loads(unb64(claims))['aud'] == 'https://web.push.apple.com'
        raw = unb64(signature)
        verifier = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), unb64(public))
        verifier.verify(encode_dss_signature(int.from_bytes(raw[:32], 'big'), int.from_bytes(raw[32:], 'big')),
                        f'{head}.{claims}'.encode(), ec.ECDSA(hashes.SHA256()))
        assert stat.S_IMODE((board.root() / 'board-push' / 'vapid.pem').stat().st_mode) == 0o600
        # The test button sends a sample to every device.
        status, body, _ = request(server, '/api/push/test', {})
        assert status == 200 and json.loads(body) == {'delivered': 1} and relay.wait(2) == 2
    finally:
        server.stop()


def test_only_real_push_services_with_valid_keys_can_subscribe(http_server):
    _, subscription = browser()
    for endpoint in ('http://web.push.apple.com/x', 'https://evil.example/x', 'https://web.push.apple.com.evil.example/x',
                     'https://user@web.push.apple.com/x', 'https://web.push.apple.com:8443/x'):
        assert subscribe(http_server, {**subscription, 'endpoint': endpoint}) == 400
    assert subscribe(http_server, {**subscription, 'keys': {'p256dh': 'AAAA', 'auth': subscription['keys']['auth']}}) == 400
    assert subscribe(http_server, subscription) == 200
    assert list(subscriptions()) == [subscription['endpoint']]
    assert stat.S_IMODE((board.root() / 'board-push' / 'subscriptions.json').stat().st_mode) == 0o600


def test_only_flagged_new_messages_push_and_each_agent_gets_a_few_an_hour(cache, relay):
    old = board.post('one', 'Before the server started.', 'operator', notify=True)
    server = start(cache, relay)
    try:
        key, subscription = browser()
        assert subscribe(server, subscription) == 200
        plain = board.post('one', 'Routine progress.', 'operator')
        flagged = [board.post('two', f'Urgent {n}', 'operator', topic='alert', notify=True) for n in range(4)]
        mine = board.post('operator', 'From the operator.', 'two', notify=True)
        assert relay.wait(3) == 3, 'three of the four flagged alerts; never old, plain or the operator\'s own'
        assert [shown(call, key, subscription)['tag'] for call in relay.calls] == [f'board-{i}' for i in flagged[:3]]
        with board.database() as db:
            flags = {row['id']: row['notify'] for row in db.execute('SELECT id, notify FROM messages')}
        assert flags[old] == 1 and flags[plain] == 0 and [flags[i] for i in flagged] == [1, 1, 1, 0]
        assert flags[mine] == 1, 'flagged, yet never pushed: the operator is not notified of their own message'

        # An operator task's ask always pushes, past the allowance two has spent, titled as one and opening the Tasks
        # page.
        task, ask = board.open_task('two', 'Can I ship r8?')
        assert relay.wait(4) == 4
        assert shown(relay.calls[3], key, subscription) == {
            'title': 'two · Operator task', 'body': 'Can I ship r8?', 'url': f'/?task={task}', 'tag': f'board-{ask}'}
        board.edit_task(task, 'two', 'Can I ship r9?')   # an edited ask pushes the same way
        assert relay.wait(5) == 5
        edited = shown(relay.calls[4], key, subscription)
        assert edited['url'] == f'/?task={task}' and edited['body'] == 'Updated the ask: Can I ship r9?'

        relay.status = 410
        board.post('one', 'Another urgent one.', 'operator', notify=True)
        assert relay.wait(6) == 6
        assert subscriptions() == {}, 'a subscription the push service has dropped is forgotten'
    finally:
        server.stop()


def test_cli_flag_and_http_endpoints(http_server, capsys):
    from types import SimpleNamespace
    args = dict(action='post', agent='one', to='operator', topic='info', reply_to=None, attach=[], all_agents=False)
    for n in range(4):
        assert board.main(SimpleNamespace(**args, message=f'Done {n}.', notify_operator=True)) == 0
    assert 'used your 3 notifications' in capsys.readouterr().err
    assert board.main(SimpleNamespace(**{**args, 'to': '*', 'all_agents': True}, message='x', notify_operator=True)) == 1

    status, body, _ = request(http_server, '/api/push/key')
    assert status == 200 and len(unb64(json.loads(body)['key'])) == 65
    assert request(http_server, '/sw.js')[0] == 200
    _, subscription = browser()
    assert request(http_server, '/api/push/subscribe', {'subscription': subscription})[0] == 200
    assert request(http_server, '/api/push/subscribe', {'subscription': {'endpoint': 'https://x.example/'}})[0] == 400
    assert request(http_server, '/api/push/unsubscribe', {'endpoint': subscription['endpoint']},
                   headers={'X-Board-CSRF': 'wrong'})[0] == 403
    assert request(http_server, '/api/push/unsubscribe', {'endpoint': subscription['endpoint']})[0] == 200
    assert subscriptions() == {}
