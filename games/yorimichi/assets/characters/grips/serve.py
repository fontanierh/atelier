"""The grip poser's web server: the page, the character's body and props, and the poses a person saves.

    uv run python games/yorimichi/assets/characters/grips/serve.py --character modori --port 8897 \
        [--allowed-user LOGIN]

It listens on loopback only; `tailscale serve --bg --set-path /grips http://127.0.0.1:8897` publishes it on the tailnet,
whose proxy adds the visitor's login (Tailscale-User-Login). With --allowed-user, only that login (or a loopback visitor)
gets in. Every save is kept: build/yorimichi/grips/<character>/poses/<time>.json, the newest also as poses.json, with
the view snapshots it sends beside it (snapshots/<time>-<grip>-<view>.png).
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import argparse
import base64
import json
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402

WEB = Path(__file__).resolve().parent / 'web'
TYPES = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
         '.json': 'application/json', '.glb': 'model/gltf-binary', '.png': 'image/png'}
LIMIT = 24 << 20   # a save with its snapshots


class Handler(BaseHTTPRequestHandler):
    server_version = 'GripPoser'

    def log_message(self, fmt, *args):
        sys.stderr.write('%s %s\n' % (time.strftime('%H:%M:%S'), fmt % args))

    def allowed(self):
        host = self.headers.get('Host', '')
        # anything that came through the Tailscale proxy (which adds X-Forwarded-For) must carry the allowed login
        local = host.split(':')[0] in ('127.0.0.1', 'localhost') and 'X-Forwarded-For' not in self.headers
        if self.server.allowed_user and not local and self.headers.get('Tailscale-User-Login', '') != self.server.allowed_user:
            self.reply(403, b'This Tailscale account cannot use the grip poser.', 'text/plain')
            return False
        return True

    def route(self):
        path = urlsplit(self.path).path
        return path[len('/grips'):] if path.startswith('/grips') else path

    def reply(self, status, body, kind, cache='no-cache'):
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', cache)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def file(self, path):
        if not path.is_file():
            return self.reply(404, b'Not found', 'text/plain')
        self.reply(200, path.read_bytes(), TYPES.get(path.suffix, 'application/octet-stream'))

    def do_GET(self):
        if not self.allowed():
            return
        path = self.route()
        out = self.server.out
        if path in ('', '/', '/index.html'):
            return self.file(WEB / 'index.html')
        if re.fullmatch(r'/[a-z]+\.(js|css)', path):
            return self.file(WEB / path[1:])
        if path in ('/data/moments.json', '/data/body.glb'):
            return self.file(out / path.split('/')[-1])
        if path in ('/data/ReferenceSword.glb', '/data/ReferenceGlider.glb'):
            return self.file(yori.OUT / 'adventure' / 'glb' / path.split('/')[-1])
        if path == '/api/poses':
            saved = out / 'poses.json'
            return self.reply(200, saved.read_bytes() if saved.is_file() else b'{}', 'application/json')
        self.reply(404, b'Not found', 'text/plain')

    def do_POST(self):
        if not self.allowed():
            return
        # a page of this origin only (the custom header needs a script of ours, not a form elsewhere)
        if self.route() != '/api/poses' or self.headers.get('X-Grip-Poser') != '1':
            return self.reply(404, b'Not found', 'text/plain')
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length <= LIMIT:
            return self.reply(413, b'Too large', 'text/plain')
        try:
            data = json.loads(self.rfile.read(length))
            assert isinstance(data, dict) and isinstance(data.get('grips'), dict)
        except (ValueError, AssertionError):
            return self.reply(400, b'A poses object is required', 'text/plain')
        stamp = time.strftime('%Y%m%d-%H%M%S') + f'-{int(time.time() * 1000) % 1000:03d}'
        out = self.server.out
        (out / 'poses').mkdir(exist_ok=True)
        (out / 'snapshots').mkdir(exist_ok=True)
        shots = data.pop('snapshots', None) or {}
        names = []
        for key, url in shots.items():
            if re.fullmatch(r'[a-z]+_[RL]-[a-z]+', key) and isinstance(url, str) and url.startswith('data:image/png;base64,'):
                name = f'{stamp}-{key}.png'
                (out / 'snapshots' / name).write_bytes(base64.b64decode(url.split(',', 1)[1]))
                names.append(name)
        data['saved'] = {'at': stamp, 'by': self.headers.get('Tailscale-User-Login', 'local'), 'snapshots': names}
        body = json.dumps(data, indent=1) + '\n'
        (out / 'poses' / f'{stamp}.json').write_text(body)
        (out / 'poses.json').write_text(body)
        self.reply(200, json.dumps({'saved': stamp, 'snapshots': len(names)}).encode(), 'application/json')


def main(args):
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.out = yori.OUT / 'grips' / args.character
    server.allowed_user = args.allowed_user
    print(f'Grip poser for {args.character} on http://127.0.0.1:{args.port}/grips/', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--character', default='modori')
    parser.add_argument('--port', type=int, default=8897)
    parser.add_argument('--allowed-user', default='')
    main(parser.parse_args())
