"""Private, loopback-only UI for the existing board. Standard library, no build step."""
import hmac
import json
import re
import secrets
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import board

ASSETS = Path(__file__).with_name('board_web_assets')
STATIC = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/board.css': ('board.css', 'text/css; charset=utf-8'),
          '/board.js': ('board.js', 'text/javascript; charset=utf-8'),
          '/icon.svg': ('icon.svg', 'image/svg+xml')}


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def snapshot(query, remote_status=None):
    """Reads never advance subscriber cursors or acquire render locks."""
    before = int(query.get('before', ['0'])[0])
    limit = int(query.get('limit', ['150'])[0])
    if before < 0 or not 1 <= limit <= 300:
        raise ValueError('invalid history page')
    conditions, parameters = [], []
    if before:
        conditions.append('id<?'); parameters.append(before)
    topic = query.get('topic', [''])[0]
    if topic:
        if topic not in board.TOPICS:
            raise ValueError('unknown topic')
        conditions.append('topic=?'); parameters.append(topic)
    agent = query.get('agent', [''])[0]
    if agent:
        board.agent_name(agent)
        conditions.append("(sender=? OR recipient=? OR recipient='*')"); parameters.extend((agent, agent))
    search = query.get('q', [''])[0].strip()
    if len(search) > 200:
        raise ValueError('search is too long')
    if search:
        conditions.append("(body LIKE ? ESCAPE '\\' OR sender LIKE ? ESCAPE '\\' OR recipient LIKE ? ESCAPE '\\')")
        pattern = '%'+search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')+'%'
        parameters.extend((pattern, pattern, pattern))
    where = ' WHERE '+' AND '.join(conditions) if conditions else ''
    path = board.root() / 'agent-board.sqlite3'
    now = time.time()
    with sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True, timeout=5) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(row) for row in db.execute(
            'SELECT * FROM messages'+where+' ORDER BY id DESC LIMIT ?', (*parameters, limit+1))]
        agents = []
        for row in db.execute('SELECT agent,cursor,pid,heartbeat,checkout,stop FROM subscribers ORDER BY agent'):
            item = dict(row)
            item['listening'] = bool(item['pid'] and not item['stop'] and 0 <= now-(item['heartbeat'] or 0) < 90)
            item['pending'] = db.execute(
                'SELECT count(*) FROM messages WHERE recipient=? AND id>? AND sender!=?',
                (item['agent'], item['cursor'], item['agent'])).fetchone()[0]
            item['checkout'] = Path(item['checkout']).name if item['checkout'] else None
            agents.append(item)
        total = db.execute('SELECT count(*) FROM messages').fetchone()[0]
        # Fetch complete fanouts even when a history/filter boundary cuts through one.
        prefixes = {row['dedup'].rsplit(':', 1)[0]+':' for row in rows[:limit]
                    if (row['dedup'] or '').startswith('web-broadcast:')}
        copies = {row['id']: row for row in rows[:limit]}
        for prefix in prefixes:
            for row in db.execute('SELECT * FROM messages WHERE dedup LIKE ?', (prefix+'%',)):
                copies[row['id']] = dict(row)
    ledger = board.root() / 'render-board.md'
    try:
        text = ledger.read_text()
    except FileNotFoundError:
        text = ''
    # Telemetry markup is advisory; return human-maintained scheduling sections separately.
    text = re.sub(r'<!-- atelier-coordinator:start -->.*?<!-- atelier-coordinator:end -->', '', text, flags=re.S)
    sections = {match[1]: match[2].strip() for match in re.finditer(
        r'^## (Holding|Waiting|Handoffs|Log)\s*\n(.*?)(?=^## |\Z)', text, re.M | re.S)}
    telemetry = read_json(board.root() / 'render-supervisor/latest.json') or {}
    sessions = []
    if remote_status:
        remote = read_json(remote_status) or {}
        for label, item in remote.get('sessions', {}).items():
            url = item.get('url', '')
            if not re.fullmatch(r'https://claude\.ai/code/session_[A-Za-z0-9]+', url):
                continue
            sessions.append({'name': item.get('name', label), 'url': url,
                             'health': item.get('health'), 'connection': item.get('connection'),
                             'fresh': 0 <= now-item.get('checked_at', 0) < 120})
    # Use the owning library's PID/start validation; stale lock text is never a live owner.
    from .safety import render_lock
    holders = {}
    for slot, path in (('big', render_lock.lock_path()), ('small', render_lock.small_lock_path())):
        holder = render_lock.read_holder(path)
        if holder:
            holders[slot] = {'purpose': holder.get('purpose', 'Render job'), 'kind': holder.get('kind', 'job'),
                             'checkout': Path(holder.get('repo') or holder.get('checkout') or '').name,
                             'time': holder.get('time')}
    return {'time': now, 'messages': sorted(copies.values(), key=lambda row: row['id'], reverse=True),
            'has_more': len(rows) > limit, 'agents': agents, 'total': total, 'schedule': sections,
            'holders': holders, 'sessions': sessions,
            'resources': {'fresh': 0 <= now-telemetry.get('time', 0) < 120,
                          'cpu': telemetry.get('cpu_busy_percent'),
                          'available_gib': (telemetry.get('memory') or {}).get('available_gib')}}


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, *, origins=(), allowed_user=None, sender='operator', remote_status=None):
        board.agent_name(sender)
        self.origins = {f'http://127.0.0.1:{address[1]}', f'http://localhost:{address[1]}'}
        for origin in origins:
            parsed = urlsplit(origin)
            if parsed.scheme != 'https' or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
                raise ValueError('public-origin must be an exact HTTPS origin without a path')
            self.origins.add(origin)
        self.allowed_user, self.sender, self.remote_status = allowed_user, sender, remote_status
        self.csrf = secrets.token_urlsafe(32)
        super().__init__(address, Handler)
        # Port 0 is used by integration tests; origin needs the actual bound port.
        self.origins.update((f'http://127.0.0.1:{self.server_port}', f'http://localhost:{self.server_port}'))


class Handler(BaseHTTPRequestHandler):
    server_version = 'AtelierBoard'

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def send(self, status, body, mime='application/json; charset=utf-8'):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def permitted(self):
        host = self.headers.get('Host', '')
        if host not in {urlsplit(origin).netloc for origin in self.server.origins}:
            self.send(403, {'error': 'This host is not configured for the board.'})
            return False
        local = host in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')
        if self.server.allowed_user and not local:
            if self.headers.get('Tailscale-User-Login', '') != self.server.allowed_user:
                self.send(403, {'error': 'Your Tailscale account does not have access to this board.'})
                return False
        return True

    def do_GET(self):
        if not self.permitted():
            return
        parsed = urlsplit(self.path)
        try:
            if parsed.path in STATIC:
                filename, mime = STATIC[parsed.path]
                self.send(200, (ASSETS / filename).read_bytes(), mime)
            elif parsed.path == '/api/state':
                state = snapshot(parse_qs(parsed.query), self.server.remote_status)
                state.update(csrf=self.server.csrf, sender=self.server.sender)
                self.send(200, state)
            elif parsed.path == '/healthz':
                with sqlite3.connect(f'{(board.root()/"agent-board.sqlite3").as_uri()}?mode=ro', uri=True) as db:
                    db.execute('SELECT id FROM messages LIMIT 1').fetchall()
                self.send(200, {'ok': True})
            else:
                self.send(404, {'error': 'Not found.'})
        except ValueError as error:
            self.send(400, {'error': str(error)})
        except (OSError, sqlite3.Error):
            self.send(503, {'error': 'The board is temporarily unavailable. Your draft is preserved; please retry.'})

    def do_POST(self):
        if not self.permitted():
            return
        if self.path != '/api/broadcast':
            self.send(404, {'error': 'Not found.'}); return
        origin = self.headers.get('Origin', '')
        if (origin not in self.server.origins or urlsplit(origin).netloc != self.headers.get('Host')
                or not hmac.compare_digest(self.headers.get('X-Board-CSRF', '').encode(), self.server.csrf.encode())):
            self.send(403, {'error': 'Please refresh the board before sending.'}); return
        if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
            self.send(415, {'error': 'A JSON message is required.'}); return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 40000:
                self.send(413, {'error': 'Message is too large.'}); return
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('A message object is required.')
            messages = board.broadcast(self.server.sender, data.get('body'), data.get('request_id'), data.get('topic', 'request'))
            self.send(200, {'messages': messages, 'recipients': [row['recipient'] for row in messages]})
        except (ValueError, TypeError, UnicodeError) as error:
            self.send(400, {'error': str(error)})
        except sqlite3.Error:
            self.send(503, {'error': 'The board is busy. Retry to safely finish this same broadcast.'})

    def log_message(self, *_):
        # Message bodies, identities, query strings and CSRF tokens stay out of service logs.
        pass


def serve(args):
    if not 1 <= args.port <= 65535:
        raise ValueError('port must be 1–65535')
    with board.database():
        pass
    server = Server(('127.0.0.1', args.port), origins=args.public_origin, allowed_user=args.allowed_user,
                    sender=args.sender, remote_status=args.remote_status)
    print(f'Agent board listening on http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
