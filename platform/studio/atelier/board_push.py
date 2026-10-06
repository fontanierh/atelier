"""Web Push to the operator's phone, only for messages an agent explicitly flags with board post --notify-operator.

Subscriptions come from the board's own Home Screen app. Payloads are encrypted end to end (RFC 8291), so the push
service relays them without reading them, and requests are signed with this machine's VAPID key (RFC 8292).
"""
import base64
import hashlib
import hmac
import json
import os
import re
import sqlite3
import struct
import threading
import time
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import board
from .board_files import split_attachments

# Only the browser vendors' push services: the server never POSTs to an arbitrary URL from a subscription.
PUSH_HOSTS = ('web.push.apple.com', 'fcm.googleapis.com', 'updates.push.services.mozilla.com', 'notify.windows.com')
TOPIC_NAMES = {'request': 'Request', 'handoff': 'Handoff', 'blocked': 'Blocked', 'release': 'Release',
               'evidence': 'Evidence', 'ack': 'Ack', 'alert': 'Alert'}
_lock = threading.Lock()


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def unb64(text):
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def folder():
    path = board.root() / 'board-push'
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def private_file(path, data):
    temporary = path.with_suffix('.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'wb') as output:
        output.write(data)
    os.replace(temporary, path)


def vapid_key():
    """This machine's signing key, created on first use and kept private to the user."""
    path = folder() / 'vapid.pem'
    with _lock:
        if not path.exists():
            key = ec.generate_private_key(ec.SECP256R1())
            private_file(path, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                 serialization.NoEncryption()))
    return serialization.load_pem_private_key(path.read_bytes(), None)


def public_key(key=None):
    key = key or vapid_key()
    return b64(key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))


def subscriptions():
    try:
        return json.loads((folder() / 'subscriptions.json').read_text())
    except (FileNotFoundError, ValueError):
        return {}


def save(items):
    private_file(folder() / 'subscriptions.json', json.dumps(items, indent=1).encode())


def subscribe(subscription):
    if not isinstance(subscription, dict):
        raise ValueError('A push subscription is required.')
    endpoint, keys = subscription.get('endpoint'), subscription.get('keys') or {}
    parts = urlsplit(endpoint if isinstance(endpoint, str) else '')
    if (parts.scheme != 'https' or parts.username or parts.port not in (None, 443) or len(endpoint) > 2000
            or not any(parts.hostname == host or (parts.hostname or '').endswith('.' + host) for host in PUSH_HOSTS)):
        raise ValueError('This push service is not supported.')
    try:
        p256dh, auth = unb64(keys['p256dh']), unb64(keys['auth'])
    except (KeyError, TypeError, ValueError):
        raise ValueError('The push subscription keys are missing.') from None
    if len(p256dh) != 65 or p256dh[0] != 4 or len(auth) != 16:
        raise ValueError('The push subscription keys are invalid.')
    with _lock:
        items = subscriptions()
        items[endpoint] = {'p256dh': keys['p256dh'], 'auth': keys['auth'], 'added': time.time()}
        save(items)


def unsubscribe(endpoint):
    with _lock:
        items = subscriptions()
        if items.pop(endpoint, None) is not None:
            save(items)


def hkdf(salt, secret, info, length):
    prk = hmac.new(salt, secret, hashlib.sha256).digest()
    return hmac.new(prk, info + b'\x01', hashlib.sha256).digest()[:length]


def encrypt(payload, p256dh, auth, salt=None, server_key=None):
    """RFC 8291 aes128gcm: one record, encrypted for the browser's key and authentication secret."""
    receiver = unb64(p256dh)
    server_key = server_key or ec.generate_private_key(ec.SECP256R1())
    sender = server_key.public_key().public_bytes(serialization.Encoding.X962,
                                                  serialization.PublicFormat.UncompressedPoint)
    shared = server_key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), receiver))
    ikm = hkdf(unb64(auth), shared, b'WebPush: info\x00' + receiver + sender, 32)
    salt = salt or os.urandom(16)
    key = hkdf(salt, ikm, b'Content-Encoding: aes128gcm\x00', 16)
    nonce = hkdf(salt, ikm, b'Content-Encoding: nonce\x00', 12)
    body = AESGCM(key).encrypt(nonce, payload + b'\x02', None)
    return salt + struct.pack('!IB', 4096, len(sender)) + sender + body


def vapid(endpoint, subject, key=None):
    """The Authorization header: a short-lived ES256 token for this push service, signed by the machine's key."""
    key = key or vapid_key()
    parts = urlsplit(endpoint)
    header = b64(json.dumps({'typ': 'JWT', 'alg': 'ES256'}, separators=(',', ':')).encode())
    claims = b64(json.dumps({'aud': f'{parts.scheme}://{parts.netloc}', 'exp': int(time.time()) + 12 * 3600,
                             'sub': subject}, separators=(',', ':')).encode())
    r, s = decode_dss_signature(key.sign(f'{header}.{claims}'.encode(), ec.ECDSA(hashes.SHA256())))
    token = f'{header}.{claims}.{b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))}'
    return f'vapid t={token}, k={public_key(key)}'


def payload(message):
    """What the notification shows, and where tapping it goes: the message's thread."""
    text = split_attachments(message['body'])[0]
    text = re.sub(r'[*_`#>]+', '', text)
    text = ' '.join(text.split())
    topic = TOPIC_NAMES.get(message['topic'], message['topic']) if message['topic'] != 'info' else ''
    return {'title': message['sender'] + (f' · {topic}' if topic else ''),
            'body': text[:240] + ('…' if len(text) > 240 else '') or 'Sent you files',
            'url': f"/?m={message['id']}", 'tag': f"board-{message['id']}"}


def send(message, subject, client=None, key=None):
    """Push one message to every subscribed device; drop subscriptions the push service says are gone."""
    data = json.dumps(payload(message)).encode()
    key = key or vapid_key()
    delivered = 0
    for endpoint, item in subscriptions().items():
        try:
            response = (client or httpx).post(endpoint, content=encrypt(data, item['p256dh'], item['auth']), timeout=10,
                                              headers={'TTL': '86400', 'Urgency': 'high', 'Content-Encoding': 'aes128gcm',
                                                       'Content-Type': 'application/octet-stream',
                                                       'Authorization': vapid(endpoint, subject, key)})
        except httpx.HTTPError:
            continue
        if response.status_code in (404, 410):
            unsubscribe(endpoint)
        elif response.status_code < 300:
            delivered += 1
    return delivered


class Pusher(threading.Thread):
    """Watches the board for newly flagged messages and pushes each once. It starts after the newest message, so a
    restart never replays old notifications."""

    def __init__(self, sender, subject, interval=3):
        super().__init__(daemon=True, name='board-push')
        self.sender, self.subject, self.interval = sender, subject, interval
        self.after = self.newest()

    @staticmethod
    def connect():
        path = board.root() / 'agent-board.sqlite3'
        db = sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def newest(self):
        with self.connect() as db:
            return db.execute('SELECT coalesce(max(id), 0) FROM messages').fetchone()[0]

    def due(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                'SELECT * FROM messages WHERE id>? AND notify=1 AND sender!=? ORDER BY id LIMIT 20',
                (self.after, self.sender))]

    def step(self, client=None):
        for message in self.due():
            self.after = message['id']
            if subscriptions():
                send(message, self.subject, client)

    def run(self):
        while True:
            try:
                self.step()
            except (OSError, sqlite3.Error, ValueError) as error:
                print(f'push: {type(error).__name__}', flush=True)
            time.sleep(self.interval)
