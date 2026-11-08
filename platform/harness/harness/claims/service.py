"""Authenticated HTTP JSON API in front of the claim store.

Every request needs ``Authorization: Bearer <token>``. The token is read from ``ATELIER_CLAIMS_TOKEN`` or a
private file (``--token-file``); it is never stored in the repository. The token admits a team member; the
``actor`` field names which registered principal is acting. Coordinator operations additionally require the
actor to be one of the service's configured coordinators.
"""
import hmac
import json
import os
import re
import stat
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .store import ClaimError

MAX_BODY = 1 << 20
DEFAULT_PORT = 8840


def read_token(token_file=None, env='ATELIER_CLAIMS_TOKEN'):
    if os.environ.get(env):
        return os.environ[env].strip()
    if token_file is None:
        token_file = os.environ.get(env + '_FILE') or Path.home() / '.config' / 'atelier' / 'claims.token'
    path = Path(token_file)
    try:
        mode = path.stat().st_mode
        token = path.read_text().strip()
    except OSError as error:
        raise SystemExit(f'claims token: set {env} or create the private file {path} ({error.strerror})')
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise SystemExit(f'claims token file {path} must be private (chmod 600)')
    if len(token) < 16:
        raise SystemExit('claims token must be at least 16 characters')
    return token


def _routes(store):
    s = store

    def b(body, *keys, **defaults):
        return {k: body.get(k, defaults.get(k)) for k in keys}

    return [
        ('GET', r'/status', lambda m, q, body: s.status()),
        ('GET', r'/events', lambda m, q, body: s.events(int(q.get('after', ['0'])[0]), int(q.get('limit', ['500'])[0]))),
        ('POST', r'/principals', lambda m, q, body: s.register_principal(**b(body, 'name', 'kind', 'git_account'))),
        ('POST', r'/machines', lambda m, q, body: s.register_machine(body.get('id'))),
        ('POST', r'/workspaces', lambda m, q, body: s.register_workspace(**b(body, 'principal', 'machine'), workspace=body.get('id'))),
        ('GET', r'/workspaces/(?P<id>[^/]+)', lambda m, q, body: s.workspace(m['id'])),
        ('POST', r'/workspaces/(?P<id>[^/]+)/heartbeat', lambda m, q, body: s.heartbeat(body.get('actor'), m['id'])),
        ('POST', r'/tasks', lambda m, q, body: s.create_task(
            body.get('actor'), body.get('id'), body.get('title'), body.get('workspace'), body.get('target_branch', 'main'),
            body.get('branch'), body.get('base_revision'), body.get('depends_on'), body.get('reads'))),
        ('GET', r'/tasks/(?P<id>[^/]+)', lambda m, q, body: s.task(m['id'])),
        ('GET', r'/tasks/(?P<id>[^/]+)/coverage', lambda m, q, body: s.coverage(m['id'])),
        ('POST', r'/tasks/(?P<id>[^/]+)/coverage', lambda m, q, body: s.coverage(m['id'], body.get('paths'))),
        ('POST', r'/tasks/(?P<id>[^/]+)/update', lambda m, q, body: s.update_task(
            body.get('actor'), m['id'], body.get('status'), body.get('branch'), body.get('base_revision'), body.get('note'))),
        ('POST', r'/tasks/(?P<id>[^/]+)/push', lambda m, q, body: s.record_push(
            body.get('actor'), m['id'], body.get('revision'), bool(body.get('ok')), body.get('detail'))),
        ('POST', r'/tasks/(?P<id>[^/]+)/merged', lambda m, q, body: s.record_merge(body.get('actor'), m['id'], body.get('revision'))),
        ('POST', r'/tasks/(?P<id>[^/]+)/cancel', lambda m, q, body: s.cancel_task(
            body.get('actor'), m['id'], body.get('disposition'), body.get('note'))),
        ('POST', r'/claims', lambda m, q, body: s.request(
            body.get('actor'), body.get('task'), body.get('workspace'), body.get('scopes'), body.get('lock_paths'),
            body.get('paths'), body.get('prefixes'), body.get('base_revision'))),
        ('GET', r'/claims/(?P<id>\d+)', lambda m, q, body: s.claim(int(m['id']))),
        ('POST', r'/claims/(?P<id>\d+)/extend', lambda m, q, body: s.extend(
            body.get('actor'), int(m['id']), body.get('lock_paths'), body.get('paths'))),
        ('POST', r'/claims/(?P<id>\d+)/lock-intent', lambda m, q, body: s.lock_intent(body.get('actor'), int(m['id']), body.get('path'))),
        ('POST', r'/claims/(?P<id>\d+)/lock-result', lambda m, q, body: s.lock_result(
            body.get('actor'), int(m['id']), body.get('path'), body.get('outcome'), body.get('lock_id'),
            body.get('owner'), body.get('detail'))),
        ('POST', r'/claims/(?P<id>\d+)/activate', lambda m, q, body: s.activate(body.get('actor'), int(m['id']))),
        ('POST', r'/claims/(?P<id>\d+)/abort', lambda m, q, body: s.abort(body.get('actor'), int(m['id']), body.get('reason'))),
        ('POST', r'/claims/(?P<id>\d+)/cancel', lambda m, q, body: s.cancel(
            body.get('actor'), int(m['id']), body.get('disposition'), body.get('note'))),
        ('POST', r'/claims/(?P<id>\d+)/unlocked', lambda m, q, body: s.unlocked(body.get('actor'), int(m['id']), body.get('path'))),
        ('POST', r'/claims/(?P<id>\d+)/recover', lambda m, q, body: s.recover(
            body.get('actor'), int(m['id']), body.get('action'), body.get('reason'), body.get('old_writer_stopped', False),
            body.get('preserved'), body.get('to_workspace'), body.get('path'), body.get('decision'), body.get('lock_id'))),
        ('POST', r'/reconcile', lambda m, q, body: s.reconcile(body.get('actor'))),
    ]


class Service:
    """The claims HTTP server. ``serve_forever`` in a thread or the foreground; ``close`` stops it."""

    def __init__(self, store, token, host='127.0.0.1', port=DEFAULT_PORT):
        routes = [(method, re.compile(pattern + r'$'), handler) for method, pattern, handler in _routes(store)]
        expected = ('Bearer ' + token).encode()

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def _reply(self, status, payload):
                data = json.dumps(payload, sort_keys=True).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _handle(self, method):
                given = self.headers.get('Authorization', '').encode()
                if not hmac.compare_digest(given, expected):
                    return self._reply(401, {'error': 'unauthorized', 'message': 'a valid bearer token is required'})
                url = urllib.parse.urlsplit(self.path)
                length = int(self.headers.get('Content-Length') or 0)
                if length > MAX_BODY:
                    return self._reply(413, {'error': 'too_large', 'message': 'request body is too large'})
                try:
                    body = json.loads(self.rfile.read(length) or b'{}') if length else {}
                    if not isinstance(body, dict):
                        raise ValueError('body must be a JSON object')
                except ValueError as error:
                    return self._reply(400, {'error': 'invalid', 'message': str(error)})
                for verb, pattern, handler in routes:
                    match = pattern.match(url.path)
                    if match and verb == method:
                        try:
                            return self._reply(200, handler(match, urllib.parse.parse_qs(url.query), body))
                        except ClaimError as error:
                            return self._reply(error.status, error.payload())
                        except (TypeError, ValueError) as error:
                            return self._reply(400, {'error': 'invalid', 'message': str(error)})
                return self._reply(404, {'error': 'not_found', 'message': f'no route {method} {url.path}'})

            def do_GET(self):
                self._handle('GET')

            def do_POST(self):
                self._handle('POST')

        self.store = store
        self.server = ThreadingHTTPServer((host, port), Handler)
        self.server.daemon_threads = True
        self.address = self.server.server_address

    @property
    def url(self):
        host, port = self.address[:2]
        return f'http://{host}:{port}'

    def serve_forever(self):
        self.server.serve_forever(poll_interval=0.2)

    def start(self):
        thread = threading.Thread(target=self.serve_forever, daemon=True, name='claims-service')
        thread.start()
        return thread

    def close(self):
        self.server.shutdown()
        self.server.server_close()
