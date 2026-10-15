"""Crater Park editor server (tailnet only, behind `tailscale serve --set-path /parkeditor`).

Serves the editor files and a tiny JSON API:
  GET  api/park               current park.json (with "rev")
  POST api/save               {"park": {...}, "base_rev": N, "label": "optional"} -> {"rev", "saved_at", "version"}
                              409 when the park changed since base_rev (another tab or an agent saved)
  GET  api/versions           [{"file", "saved_at", "label", "pieces"}] newest first
  GET  api/version?f=NAME     one saved version
Every save rewrites park.json atomically. A version snapshot goes to versions/ when asked (label) or when the
last snapshot is older than 5 minutes, so the history keeps working states without one file per keystroke.

usage: python3 server.py [port] [data_dir]

Live channel (Claude <-> the owner's open editor):
  GET  api/poll?since=SEQ&tab=ID  long-poll for events: {"type": "park", rev} after any save, {"type": "cmd", op, ...}
  POST api/cmd                    {"op": ..., "to": "active" | tab | omitted for all} -> pushed to editors
  POST api/viewstate              editors report camera, selection, hover, visibility (GET returns the most active tab)
  POST api/snapshot               editors upload a PNG of their exact view for a "snapshot" command (req id)
"""
import json, os, sys, time, threading
from datetime import datetime
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

H = Path(__file__).resolve().parent
DATA = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else H      # test instances use their own data dir
PARK = DATA / 'park.json'
VERS = DATA / 'versions'
VERS.mkdir(exist_ok=True)
SNAPS = DATA / 'snapshots'
SNAPS.mkdir(exist_ok=True)
LOCK = threading.Lock()
SNAP_EVERY = 300

# ---- live channel: editors long-poll api/poll for events; Claude posts commands and edits
EV_LOCK = threading.Condition()
EVENTS = []          # [{seq, type, ...}]
SEQ = [0]
VIEW = {}            # tab id -> latest view state from that editor
def emit(ev):
    with EV_LOCK:
        SEQ[0] += 1
        ev = dict(ev, seq=SEQ[0], t=time.time())
        EVENTS.append(ev)
        del EVENTS[:-500]
        EV_LOCK.notify_all()
    return ev['seq']
def active_tab():
    if not VIEW:
        return None
    return max(VIEW.values(), key=lambda v: v.get('active_at', 0)).get('tab')


def read_park():
    d = json.loads(PARK.read_text())
    d.setdefault('rev', 0)
    return d


def write_atomic(path, text):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(text)
    os.replace(tmp, path)


def versions():
    out = []
    for f in sorted(VERS.glob('park-*.json'), reverse=True):
        try:
            meta = json.loads(f.read_text()).get('_version', {})
        except Exception:
            meta = {}
        out.append({'file': f.name, 'saved_at': meta.get('saved_at'), 'label': meta.get('label', ''), 'pieces': meta.get('pieces')})
    return out


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(H), **kw)

    # keep-alive: the tailnet proxy reuses connections instead of opening one per request (thousands of closed
    # connections left in TIME_WAIT made new ones stall for seconds)
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        pass

    def log_request(self, code='-', size='-'):
        with open(H / 'requests.log', 'a') as f:
            f.write(f"{time.strftime('%H:%M:%S')} {self.command} {urlparse(self.path).path} {code} {self.headers.get('User-Agent', '')[:60]}\n")

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        if p.endswith('/api/park'):
            with LOCK:
                return self._json(read_park())
        if p.endswith('/api/versions'):
            return self._json(versions())
        if p.endswith('/api/poll'):
            q = parse_qs(u.query)
            since = int(q.get('since', ['0'])[0]); tab = q.get('tab', [''])[0]
            if q.get('init'):
                return self._json({'seq': SEQ[0], 'events': []})
            deadline = time.time() + 25
            with EV_LOCK:
                if since > SEQ[0]:
                    since = 0      # server restarted
                while time.time() < deadline:
                    out = [e for e in EVENTS if e['seq'] > since and (not e.get('to') or e.get('to') == tab)]
                    if out:
                        break
                    EV_LOCK.wait(timeout=max(0.1, deadline - time.time()))
                out = [e for e in EVENTS if e['seq'] > since and (not e.get('to') or e.get('to') == tab)]
                return self._json({'seq': SEQ[0], 'events': out})
        if p.endswith('/api/viewstate'):
            tab = active_tab()
            return self._json({'active': VIEW.get(tab) if tab else None, 'tabs': list(VIEW.values())})
        if p.endswith('/api/snapshot'):
            req = parse_qs(u.query).get('req', [''])[0]
            f = SNAPS / f'{Path(req).name}.png'
            return self._json({'ready': f.exists(), 'file': str(f) if f.exists() else None})
        if p.endswith('/api/version'):
            f = parse_qs(u.query).get('f', [''])[0]
            path = VERS / Path(f).name
            if not path.exists():
                return self._json({'error': 'no such version'}, 404)
            return self._json(json.loads(path.read_text()))
        # never serve server-side files
        if any(p.endswith(x) for x in ('.py', '.sh', '.log')) or '/snapshots/' in p or '/versions/' in p:
            return self._json({'error': 'not found'}, 404)
        return super().do_GET()

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get('Content-Length', '0'))
        if u.path.endswith('/api/viewstate'):
            try:
                v = json.loads(self.rfile.read(n))
            except Exception:
                return self._json({'error': 'bad json'}, 400)
            v['received_at'] = time.time()
            VIEW[v.get('tab', '?')] = v
            for k in [k for k, x in VIEW.items() if time.time() - x['received_at'] > 3600]:
                VIEW.pop(k, None)
            (DATA / 'viewstate.json').write_text(json.dumps(v, indent=1))
            return self._json({'ok': True})
        if u.path.endswith('/api/cmd'):
            try:
                c = json.loads(self.rfile.read(n))
            except Exception:
                return self._json({'error': 'bad json'}, 400)
            if c.get('to') == 'active':
                c['to'] = active_tab()
            seq = emit({'type': 'cmd', **c})
            return self._json({'seq': seq, 'to': c.get('to')})
        if u.path.endswith('/api/snapshot'):
            import base64
            try:
                body = json.loads(self.rfile.read(n))
                data = body['png'].split(',', 1)[1]
                name = Path(body.get('req') or 'latest').name
                (SNAPS / f'{name}.png').write_bytes(base64.b64decode(data))
                (SNAPS / 'latest.png').write_bytes(base64.b64decode(data))
                if body.get('view'):
                    (SNAPS / f'{name}.json').write_text(json.dumps(body['view'], indent=1))
            except Exception as e:
                return self._json({'error': str(e)}, 400)
            return self._json({'ok': True})
        if not u.path.endswith('/api/save'):
            self.close_connection = True; return self._json({'error': 'not found'}, 404)
        try:
            body = json.loads(self.rfile.read(n))
            park = body['park']
            assert isinstance(park.get('pieces'), list)
        except Exception as e:
            return self._json({'error': f'bad request: {e}'}, 400)
        with LOCK:
            cur = read_park()
            if not body.get('force') and int(body.get('base_rev', -1)) != int(cur.get('rev', 0)):
                return self._json({'error': 'conflict', 'rev': cur.get('rev', 0), 'saved_at': cur.get('saved_at')}, 409)
            now = datetime.now().astimezone()
            park['rev'] = int(cur.get('rev', 0)) + 1
            park['saved_at'] = now.isoformat(timespec='seconds')
            write_atomic(PARK, json.dumps(park, indent=1))
            vs = sorted(VERS.glob('park-*.json'))
            last = vs[-1].stat().st_mtime if vs else 0
            label = (body.get('label') or '').strip()
            version = None
            if label or time.time() - last > SNAP_EVERY:
                version = f'park-{now.strftime("%Y%m%d-%H%M%S")}.json'
                snap = dict(park)
                snap['_version'] = {'saved_at': park['saved_at'], 'label': label or 'autosave', 'pieces': len(park['pieces'])}
                (VERS / version).write_text(json.dumps(snap))
        emit({'type': 'park', 'rev': park['rev'], 'by': body.get('by') or 'editor', 'tab': body.get('tab'), 'label': label})
        return self._json({'rev': park['rev'], 'saved_at': park['saved_at'], 'version': version})


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8904
    if not PARK.exists():
        sys.exit('park.json missing: run import_v4.py first')
    if not list(VERS.glob('park-*.json')):
        d = read_park()
        d['_version'] = {'saved_at': datetime.now().astimezone().isoformat(timespec='seconds'), 'label': 'imported from v4 design', 'pieces': len(d['pieces'])}
        (VERS / f'park-{datetime.now().strftime("%Y%m%d-%H%M%S")}.json').write_text(json.dumps(d))
    ThreadingHTTPServer.request_queue_size = 64      # editors post view state every second; a burst must not refuse connections
    srv = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    srv.daemon_threads = True
    srv.serve_forever()
