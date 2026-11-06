"""In-process Git LFS lock server implementing the locking API (git-lfs docs/api/locking.md).

The owner is the HTTP Basic user (``Authorization: Basic base64(user:password)``). Failure injection:
``down`` answers 503 to everything; ``drop_after_create`` holds paths whose create succeeds on the server
but whose reply is lost (the connection closes without a response).
"""
import base64
import itertools
import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MEDIA = 'application/vnd.git-lfs+json'


def basic(user, password='x'):
    return 'Basic ' + base64.b64encode(f'{user}:{password}'.encode()).decode()


class FakeLfs:
    def __init__(self):
        self.locks = {}  # id -> lock record
        self.lock = threading.Lock()
        self.ids = itertools.count(1)
        self.down = False
        self.drop_after_create = set()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def _user(self):
                header = self.headers.get('Authorization', '')
                if header.startswith('Basic '):
                    return base64.b64decode(header[6:]).decode().split(':', 1)[0]
                return None

            def _reply(self, status, payload):
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header('Content-Type', MEDIA)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _body(self):
                length = int(self.headers.get('Content-Length') or 0)
                return json.loads(self.rfile.read(length) or b'{}') if length else {}

            def _guard(self):
                if fake.down:
                    self._reply(503, {'message': 'service unavailable'})
                    return None
                user = self._user()
                if not user:
                    self.send_response(401)
                    self.send_header('LFS-Authenticate', 'Basic realm="fake"')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return None
                return user

            def do_GET(self):
                user = self._guard()
                if user is None:
                    return
                url = urllib.parse.urlsplit(self.path)
                if not url.path.rstrip('/').endswith('/locks'):
                    return self._reply(404, {'message': 'not found'})
                q = urllib.parse.parse_qs(url.query)
                with fake.lock:
                    found = sorted(fake.locks.values(), key=lambda l: int(l['id']))
                found = [l for l in found if ('path' not in q or l['path'] == q['path'][0])
                         and ('id' not in q or l['id'] == q['id'][0])]
                start = int(q.get('cursor', ['0'])[0] or 0)
                limit = int(q.get('limit', ['100'])[0] or 100)
                page = found[start:start + limit]
                nxt = str(start + limit) if start + limit < len(found) else ''
                self._reply(200, {'locks': page, 'next_cursor': nxt})

            def do_POST(self):
                user = self._guard()
                if user is None:
                    return
                path = urllib.parse.urlsplit(self.path).path.rstrip('/')
                body = self._body()
                if path.endswith('/locks/verify'):
                    with fake.lock:
                        every = sorted(fake.locks.values(), key=lambda l: int(l['id']))
                    return self._reply(200, {'ours': [l for l in every if l['owner']['name'] == user],
                                             'theirs': [l for l in every if l['owner']['name'] != user],
                                             'next_cursor': ''})
                if path.endswith('/locks'):
                    target = body.get('path')
                    if not target:
                        return self._reply(422, {'message': 'path is required'})
                    with fake.lock:
                        existing = [l for l in fake.locks.values() if l['path'] == target]
                        if existing:
                            return self._reply(409, {'lock': existing[0], 'message': 'already created lock'})
                        record = {'id': str(next(fake.ids)), 'path': target, 'owner': {'name': user},
                                  'locked_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
                        fake.locks[record['id']] = record
                    if target in fake.drop_after_create:
                        self.close_connection = True
                        self.connection.close()
                        return
                    return self._reply(201, {'lock': record})
                if path.endswith('/unlock'):
                    lock_id = urllib.parse.unquote(path.split('/')[-2])
                    with fake.lock:
                        record = fake.locks.get(lock_id)
                        if not record:
                            return self._reply(404, {'message': 'unknown lock'})
                        if record['owner']['name'] != user and not body.get('force'):
                            return self._reply(403, {'message': 'not the lock owner'})
                        del fake.locks[lock_id]
                    return self._reply(200, {'lock': record})
                return self._reply(404, {'message': 'not found'})

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.1}, daemon=True).start()
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}'

    def add(self, path, owner):
        """A pre-existing lock (for example a bootstrap writer's)."""
        with self.lock:
            record = {'id': str(next(self.ids)), 'path': path, 'owner': {'name': owner}, 'locked_at': ''}
            self.locks[record['id']] = record
            return record['id']

    def at(self, path):
        with self.lock:
            return [l for l in self.locks.values() if l['path'] == path]

    def close(self):
        self.server.shutdown()
        self.server.server_close()
