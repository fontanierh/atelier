"""Private, loopback-only UI for the existing board. Standard library, no build step."""
import gzip
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

from . import board, board_markdown, board_push
from .board_files import (INLINE_TYPES, attachment, read_json, split_attachments, store_upload,
                          with_attachments)

ASSETS = Path(__file__).with_name('board_web_assets')
STATIC = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/board.css': ('board.css', 'text/css; charset=utf-8'),
          '/board.js': ('board.js', 'text/javascript; charset=utf-8'),
          '/icon.svg': ('icon.svg', 'image/svg+xml'),
          '/apple-touch-icon.png': ('apple-touch-icon.png', 'image/png'),
          '/manifest.webmanifest': ('manifest.webmanifest', 'application/manifest+json'),
          '/sw.js': ('sw.js', 'text/javascript; charset=utf-8'),
          '/meadow-portrait-1.webp': ('meadow-portrait-1.webp', 'image/webp'),
          '/meadow-landscape-1.webp': ('meadow-landscape-1.webp', 'image/webp')}
_assets = {}


def asset(filename):
    """A static file, its ETag and (for text) a gzip copy, reread only when the file changes on disk."""
    path = ASSETS / filename
    stamp = path.stat().st_mtime_ns
    cached = _assets.get(filename)
    if not cached or cached[0] != stamp:
        data = path.read_bytes()
        packed = None if filename.endswith(('.webp', '.png')) else gzip.compress(data, 9)
        cached = _assets[filename] = (stamp, data, f'"{hashlib.sha256(data).hexdigest()[:24]}"', packed)
    return cached[1:]
PUSH_PATHS = ('/api/push/subscribe', '/api/push/unsubscribe', '/api/push/test')


def snapshot(query, remote_status=None, sender='operator'):
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
    direct = query.get('dm', [''])[0]
    if direct:
        # A direct conversation: only messages between this agent and the board's sender, never broadcast copies.
        board.agent_name(direct)
        conditions.append("((sender=? AND recipient=?) OR (sender=? AND recipient=?)) "
                          "AND (dedup IS NULL OR dedup NOT LIKE 'web-broadcast:%')")
        parameters.extend((direct, sender, sender, direct))
    elif agent:
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
        for row in db.execute('SELECT agent,cursor,pid,heartbeat,checkout,stop,supervised,error,task FROM subscribers '
                              'WHERE removed=0 ORDER BY agent'):
            item = dict(row)
            item['listening'] = bool(item['pid'] and not item['stop'] and 0 <= now-(item['heartbeat'] or 0) < 90)
            item['pending'] = db.execute(
                'SELECT count(*) FROM messages WHERE recipient=? AND id>? AND sender!=?',
                (item['agent'], item['cursor'], item['agent'])).fetchone()[0]
            item['checkout'] = Path(item['checkout']).name if item['checkout'] else None
            item['supervised'] = bool(item['supervised'])
            # Transport errors are generated diagnostics, not exception/argv disclosures.
            item['delivery_error'] = bool(item.pop('error'))
            # The newest message this agent sent the board's own sender: the UI marks unread direct messages with it.
            item['last_to_me'] = db.execute('SELECT max(id) FROM messages WHERE sender=? AND recipient=?',
                                            (item['agent'], sender)).fetchone()[0] or 0
            agents.append(item)
        total = db.execute('SELECT count(*) FROM messages').fetchone()[0]
        # Fetch complete fanouts even when a history/filter boundary cuts through one.
        prefixes = {row['dedup'].rsplit(':', 1)[0]+':' for row in rows[:limit]
                    if (row['dedup'] or '').startswith('web-broadcast:')}
        copies = {row['id']: row for row in rows[:limit]}
        for prefix in prefixes:
            for row in db.execute('SELECT * FROM messages WHERE dedup LIKE ?', (prefix+'%',)):
                copies[row['id']] = dict(row)
        ack_ids = {row[0] for row in db.execute('SELECT reply.reply_to FROM messages reply '
                   'JOIN messages original ON original.id=reply.reply_to '
                   "WHERE reply.topic='ack' AND reply.sender=original.recipient")}
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
    output = sorted(copies.values(), key=lambda row: row['id'], reverse=True)
    for item in output:
        decorate(item, ack_ids)
    return {'time': now, 'messages': output,
            'has_more': len(rows) > limit, 'agents': agents, 'total': total, 'schedule': sections,
            'holders': holders, 'sessions': sessions,
            'resources': {'fresh': 0 <= now-telemetry.get('time', 0) < 120,
                          'cpu': telemetry.get('cpu_busy_percent'),
                          'available_gib': (telemetry.get('memory') or {}).get('available_gib')}}


def decorate(item, ack_ids):
    text, item['attachments'] = split_attachments(item['body'])
    item['body_html'] = board_markdown.render(text)
    item['acknowledged'] = item['id'] in ack_ids
    return item


def thread(message_id):
    """A whole conversation: the root (every copy of a web broadcast) and all replies beneath it, oldest first."""
    path = board.root() / 'agent-board.sqlite3'
    with sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True, timeout=5) as db:
        db.row_factory = sqlite3.Row
        roots, replies = board.thread_rows(db, message_id)
        ids = [r['id'] for r in roots]
        ack_ids = {r[0] for r in db.execute(
            'SELECT reply.reply_to FROM messages reply JOIN messages original ON original.id=reply.reply_to '
            f"WHERE reply.topic='ack' AND reply.sender=original.recipient AND reply.reply_to IN ({','.join('?' * len(ids + [r['id'] for r in replies]))})",
            ids + [r['id'] for r in replies])}
    return {'root': [decorate(r, ack_ids) for r in roots], 'replies': [decorate(r, ack_ids) for r in replies]}


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
        # VAPID asks for a contact; the board's own HTTPS origin identifies this machine without personal details.
        self.push_subject = next((origin for origin in origins), 'https://localhost')
        self.csrf = secrets.token_urlsafe(32)
        super().__init__(address, Handler)
        # Port 0 is used by integration tests; origin needs the actual bound port.
        self.origins.update((f'http://127.0.0.1:{self.server_port}', f'http://localhost:{self.server_port}'))


class Handler(BaseHTTPRequestHandler):
    server_version = 'AtelierBoard'

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def send(self, status, body, mime='application/json; charset=utf-8', cache='no-store', headers=(), csp=None):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', cache)
        for name, value in headers:
            self.send_header(name, value)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', csp or "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def static(self, filename, mime):
        """Fast loads: the versioned paintings cache for a year (a new painting gets a new name); the app's own files
        revalidate with an ETag, so a reload costs a 304 until they change, and travel gzipped."""
        data, tag, packed = asset(filename)
        cache = 'public, max-age=31536000, immutable' if filename.endswith('.webp') else 'no-cache'
        if self.headers.get('If-None-Match') == tag:
            self.send_response(304)
            self.send_header('ETag', tag)
            self.send_header('Cache-Control', cache)
            self.end_headers()
            return
        headers = [('ETag', tag), ('Vary', 'Accept-Encoding')]
        if packed and 'gzip' in self.headers.get('Accept-Encoding', ''):
            data = packed
            headers.append(('Content-Encoding', 'gzip'))
        self.send(200, data, mime, cache, headers)

    def review(self, name):
        """A report page (an agents' research write-up) from the board cache, for the same people as the board.
        Pages are static: no scripts run, and only their own inline styles and Google Fonts load."""
        path = board.root() / 'reviews' / f'{name}.html'
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', name) or not path.is_file():
            self.send(404, {'error': 'There is no review by that name.'}); return
        self.send(200, path.read_bytes(), 'text/html; charset=utf-8', 'no-cache',
                  csp="default-src 'none'; style-src 'unsafe-inline' https://fonts.googleapis.com; "
                      "font-src https://fonts.gstatic.com; img-src data:; base-uri 'none'; form-action 'none'; "
                      "frame-ancestors 'none'")

    def send_attachment(self, ident):
        item = attachment(ident)
        if not item:
            self.send(404, {'error': 'This attachment is no longer available.'}); return
        size, start, end, status = item['size'], 0, item['size'] - 1, 200
        # Byte ranges let Safari stream and seek videos.
        ranged = re.fullmatch(r'bytes=(\d*)-(\d*)', self.headers.get('Range', '').strip())
        if ranged and (ranged[1] or ranged[2]):
            if ranged[1]:
                start, end = int(ranged[1]), min(int(ranged[2]) if ranged[2] else size - 1, size - 1)
            else:
                start = max(0, size - int(ranged[2]))
            if start > end:
                self.send_response(416); self.send_header('Content-Range', f'bytes */{size}')
                self.send_header('Content-Length', '0'); self.end_headers(); return
            status = 206
        inline = item['mime'] in INLINE_TYPES
        self.send_response(status)
        self.send_header('Content-Type', item['mime'] if inline else 'application/octet-stream')
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Accept-Ranges', 'bytes')
        if status == 206:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.send_header('Content-Disposition', f"{'inline' if inline else 'attachment'}; filename*=UTF-8''{quote(item['name'])}")
        self.send_header('Cache-Control', 'private, max-age=86400')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "sandbox; default-src 'none'; img-src 'self'; media-src 'self'")
        self.end_headers()
        with item['path'].open('rb') as source:
            source.seek(start)
            remaining = end - start + 1
            while remaining:
                chunk = source.read(min(1 << 20, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

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
                self.static(*STATIC[parsed.path])
            elif parsed.path == '/api/state':
                state = snapshot(parse_qs(parsed.query), self.server.remote_status, self.server.sender)
                state.update(csrf=self.server.csrf, sender=self.server.sender)
                self.send(200, state)
            elif parsed.path == '/review' or parsed.path.startswith('/review/'):
                self.review(parsed.path.removeprefix('/review').strip('/') or 'codebase-review')
            elif parsed.path == '/api/push/key':
                self.send(200, {'key': board_push.public_key()})
            elif parsed.path == '/api/thread':
                try:
                    self.send(200, thread(int(parse_qs(parsed.query).get('id', ['0'])[0])))
                except LookupError:
                    self.send(404, {'error': 'This conversation is no longer on the board.'})
            elif parsed.path.startswith('/api/attachment/'):
                self.send_attachment(parsed.path.split('/')[3])
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
        if self.path not in ('/api/broadcast', '/api/send', '/api/preview', '/api/upload', '/api/remove', *PUSH_PATHS):
            self.send(404, {'error': 'Not found.'}); return
        origin = self.headers.get('Origin', '')
        if (origin not in self.server.origins or urlsplit(origin).netloc != self.headers.get('Host')
                or not hmac.compare_digest(self.headers.get('X-Board-CSRF', '').encode(), self.server.csrf.encode())):
            self.send(403, {'error': 'Please refresh the board before sending.'}); return
        if self.path == '/api/upload':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                stored = store_upload(self.rfile, length, self.headers.get('X-File-Name', ''),
                                      self.headers.get('Content-Type', '').split(';')[0].strip(),
                                      self.headers.get('X-Media-Width'), self.headers.get('X-Media-Height'))
                self.send(200, {key: stored[key] for key in ('id', 'name', 'mime', 'size', 'width', 'height')})
            except ValueError as error:
                self.close_connection = True
                self.send(413 if 'MB' in str(error) else 400, {'error': str(error)})
            except OSError:
                self.close_connection = True
                self.send(503, {'error': 'The file could not be saved. Try again.'})
            return
        if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
            self.send(415, {'error': 'A JSON message is required.'}); return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 40000:
                self.send(413, {'error': 'Message is too large.'}); return
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('A message object is required.')
            if self.path == '/api/preview':
                body = data.get('body')
                if not isinstance(body, str) or len(body) > 8000:
                    raise ValueError('Preview needs a message of at most 8000 characters.')
                self.send(200, {'html': board_markdown.render(body)})
                return
            if self.path in PUSH_PATHS:
                self.push(data)
                return
            if self.path == '/api/remove':
                agent = data.get('agent')
                if not isinstance(agent, str):
                    raise ValueError('Choose an agent to remove.')
                board.remove(agent)
                self.send(200, {'removed': agent})
                return
            recipient = data.get('recipient', '*') if self.path == '/api/send' else '*'
            body = with_attachments(data.get('body'), data.get('attachments') or [])
            messages = board.send_web(self.server.sender, body, data.get('request_id'),
                                      data.get('topic', 'request'), recipient, data.get('reply_to'))
            self.send(200, {'messages': messages, 'recipients': [row['recipient'] for row in messages]})
        except (ValueError, TypeError, UnicodeError, LookupError) as error:
            self.send(400, {'error': str(error)})
        except sqlite3.Error:
            self.send(503, {'error': 'The board is busy. Retry to safely finish this same message.'})
        except OSError:
            self.send(503, {'error': 'The board could not save that. Try again.'})

    def push(self, data):
        if self.path == '/api/push/subscribe':
            board_push.subscribe(data.get('subscription'))
            self.send(200, {'subscribed': True})
        elif self.path == '/api/push/unsubscribe':
            endpoint = data.get('endpoint')
            if not isinstance(endpoint, str):
                raise ValueError('A push endpoint is required.')
            board_push.unsubscribe(endpoint)
            self.send(200, {'subscribed': False})
        else:
            # A sample notification, so the person can check this device receives them.
            sample = {'id': 0, 'sender': 'Atelier board', 'topic': 'info', 'body': 'Notifications work on this device.'}
            self.send(200, {'delivered': board_push.send(sample, self.server.push_subject)})

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
    board_push.Pusher(server.sender, server.push_subject).start()
    print(f'Agent board listening on http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
