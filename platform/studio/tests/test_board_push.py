"""Phone notifications: only flagged messages, capped per agent, end-to-end encrypted, and deep-linked."""
import base64
import hashlib
import hmac
import json
import os
import stat
import struct
import uuid

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from atelier import board, board_push

from test_board_web import cache, http_server, request  # noqa: F401  (shared fixtures)


def browser():
    """A browser's push keys, as a subscription carries them."""
    key, auth = ec.generate_private_key(ec.SECP256R1()), os.urandom(16)
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return key, {'endpoint': 'https://web.push.apple.com/QGuQyavXutnMH', 'keys': {'p256dh': board_push.b64(public),
                                                                                  'auth': board_push.b64(auth)}}


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


class Push:
    """Records pushes instead of reaching the push service."""
    def __init__(self, status=201):
        self.calls, self.status = [], status

    def post(self, url, content, headers, timeout):
        self.calls.append((url, content, headers))
        return type('Response', (), {'status_code': self.status})()


def test_payloads_are_encrypted_for_the_browser_and_signed_for_the_push_service(cache):
    key, subscription = browser()
    board_push.subscribe(subscription)
    client = Push()
    message = {'id': 42, 'sender': 'hidamari', 'topic': 'blocked', 'body': '**Blocked** on your call: ship `v2`?'}
    assert board_push.send(message, 'https://board.example.ts.net', client) == 1
    url, body, headers = client.calls[0]
    shown = json.loads(decrypt(body, key, base64.urlsafe_b64decode(subscription['keys']['auth'] + '==')))
    assert shown == {'title': 'hidamari · Blocked', 'body': 'Blocked on your call: ship v2?', 'url': '/?m=42',
                     'tag': 'board-42'}
    assert headers['Content-Encoding'] == 'aes128gcm' and headers['TTL'] == '86400'

    token, public = headers['Authorization'].removeprefix('vapid t=').split(', k=')
    head, claims, signature = token.split('.')
    assert json.loads(board_push.unb64(claims))['aud'] == 'https://web.push.apple.com'
    raw = board_push.unb64(signature)
    verifier = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), board_push.unb64(public))
    verifier.verify(encode_dss_signature(int.from_bytes(raw[:32], 'big'), int.from_bytes(raw[32:], 'big')),
                    f'{head}.{claims}'.encode(), ec.ECDSA(hashes.SHA256()))
    assert stat.S_IMODE((board.root() / 'board-push' / 'vapid.pem').stat().st_mode) == 0o600


def test_only_real_push_services_with_valid_keys_can_subscribe(cache):
    _, subscription = browser()
    for endpoint in ('http://web.push.apple.com/x', 'https://evil.example/x', 'https://web.push.apple.com.evil.example/x',
                     'https://user@web.push.apple.com/x', 'https://web.push.apple.com:8443/x'):
        with pytest.raises(ValueError):
            board_push.subscribe({**subscription, 'endpoint': endpoint})
    with pytest.raises(ValueError):
        board_push.subscribe({**subscription, 'keys': {'p256dh': 'AAAA', 'auth': subscription['keys']['auth']}})
    board_push.subscribe(subscription)
    assert list(board_push.subscriptions()) == [subscription['endpoint']]
    assert stat.S_IMODE((board.root() / 'board-push' / 'subscriptions.json').stat().st_mode) == 0o600


def test_only_flagged_new_messages_push_and_each_agent_gets_a_few_an_hour(cache):
    _, subscription = browser()
    board_push.subscribe(subscription)
    old = board.post('one', 'Before the server started.', 'operator', notify=True)
    pusher = board_push.Pusher('operator', 'https://board.example.ts.net')
    plain = board.post('one', 'Routine progress.', 'operator')
    flagged = [board.post('two', f'Urgent {n}', 'operator', topic='alert', notify=True) for n in range(4)]
    mine = board.post('operator', 'From the operator.', 'two', notify=True)
    client = Push()
    pusher.step(client)
    assert len(client.calls) == 3, 'three of the four flagged alerts; never old, plain or the operator\'s own'
    with board.database() as db:
        flags = {row['id']: row['notify'] for row in db.execute('SELECT id, notify FROM messages')}
    assert flags[old] == 1 and flags[plain] == 0 and [flags[i] for i in flagged] == [1, 1, 1, 0]
    assert flags[mine] == 1, 'flagged, yet never pushed: the operator is not notified of their own message'
    pusher.step(client)
    assert len(client.calls) == 3, 'each message pushes once'

    # An operator task's ask always pushes, past the allowance two has spent, titled as one and opening the Tasks page.
    task, ask = board.open_task('two', 'Can I ship r8?')
    due = pusher.due()
    assert [m['id'] for m in due] == [ask]
    shown = board_push.payload(due[0])
    assert shown['title'] == 'two · Operator task' and shown['url'] == f'/?task={task}' and shown['body'] == 'Can I ship r8?'
    pusher.step(client)
    assert len(client.calls) == 4
    board.edit_task(task, 'two', 'Can I ship r9?')   # an edited ask pushes the same way
    shown = board_push.payload(pusher.due()[0])
    assert shown['url'] == f'/?task={task}' and shown['body'] == 'Updated the ask: Can I ship r9?'

    gone = Push(status=410)
    board.post('one', 'Another urgent one.', 'operator', notify=True)
    pusher.step(gone)
    assert board_push.subscriptions() == {}, 'a subscription the push service has dropped is forgotten'


def test_cli_flag_and_http_endpoints(http_server, capsys):
    from types import SimpleNamespace
    args = dict(action='post', agent='one', to='operator', topic='info', reply_to=None, attach=[], all_agents=False)
    for n in range(4):
        assert board.main(SimpleNamespace(**args, message=f'Done {n}.', notify_operator=True)) == 0
    assert 'used your 3 notifications' in capsys.readouterr().err
    assert board.main(SimpleNamespace(**{**args, 'to': '*', 'all_agents': True}, message='x', notify_operator=True)) == 1

    status, body, _ = request(http_server, '/api/push/key')
    assert status == 200 and len(board_push.unb64(json.loads(body)['key'])) == 65
    assert request(http_server, '/sw.js')[0] == 200
    _, subscription = browser()
    assert request(http_server, '/api/push/subscribe', {'subscription': subscription})[0] == 200
    assert request(http_server, '/api/push/subscribe', {'subscription': {'endpoint': 'https://x.example/'}})[0] == 400
    assert request(http_server, '/api/push/unsubscribe', {'endpoint': subscription['endpoint']},
                   headers={'X-Board-CSRF': 'wrong'})[0] == 403
    assert request(http_server, '/api/push/unsubscribe', {'endpoint': subscription['endpoint']})[0] == 200
    assert board_push.subscriptions() == {}
