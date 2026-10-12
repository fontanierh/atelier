"""Inspect a GLB and save clipping feedback, using the committed local web viewer.

    uv run python games/yorimichi/tools/character_review.py --model games/yorimichi/assets/characters/nox/Nox.glb

Loopback only. Feedback goes to the ignored build workspace; model hashes tie each
mark to its exact source. The optional hair demo does not simulate an animated game body.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import mimetypes
from pathlib import Path
import time
from urllib.parse import unquote, urlsplit

WEB = Path(__file__).with_name('character_review_web')
REPO = Path(__file__).resolve().parents[3]


def vector(value, count):
    return (isinstance(value, list) and len(value) == count
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in value))


def feedback(data, model):
    """Validate a captured pose before saving it; no user-controlled output filename."""
    if not isinstance(data, dict) or data.get('schema') != 1 or data.get('model') != model:
        raise ValueError('Feedback must name the loaded model hash')
    marks = data.get('marks')
    if not isinstance(marks, list) or len(marks) > 500:
        raise ValueError('Too many marks')
    for mark in marks:
        if not isinstance(mark, dict) or not isinstance(mark.get('mesh'), str) or len(mark['mesh']) > 200:
            raise ValueError('Invalid mesh')
        if not isinstance(mark.get('faceIndex'), int) or not 0 <= mark['faceIndex'] < 10_000_000:
            raise ValueError('Invalid face')
        if not all(vector(mark.get(n), 3) for n in ('modelPoint', 'camera', 'target')):
            raise ValueError('Invalid point or camera')
        pose = mark.get('pose', {})
        if not vector(pose.get('rootPosition'), 3) or not vector(pose.get('rootQuaternion'), 4):
            raise ValueError('Invalid root pose')
        bones = pose.get('bones')
        if not isinstance(bones, list) or len(bones) > 1000:
            raise ValueError('Invalid bone poses')
        for bone in bones:
            if not isinstance(bone, list) or len(bone) != 2 or not isinstance(bone[0], str) or len(bone[0]) > 200 or not vector(bone[1], 4):
                raise ValueError('Invalid bone rotation')
    return {**data, 'by': 'operator' if data.get('by') == 'operator' else 'automated'}


def handler(model, output, hair=None):
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    config = dict(label=model.stem, filename=model.name, sha256=digest, hair=bool(hair))

    class Handler(BaseHTTPRequestHandler):
        def response(self, body, kind, status=200, head=False):
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self' blob:; frame-ancestors 'self'")
            self.end_headers()
            if not head:
                self.wfile.write(body)

        def get(self, head=False):
            route = unquote(urlsplit(self.path).path)
            if route == '/config.json':
                return self.response(json.dumps(config).encode(), 'application/json', head=head)
            files = {'/model.glb': model, '/': WEB / 'index.html'}
            if hair:
                files['/hair.json'] = hair
            file = files.get(route)
            if file is None:
                candidate = (WEB / route.lstrip('/')).resolve()
                if candidate.is_relative_to(WEB.resolve()) and candidate.is_file():
                    file = candidate
            if file is None:
                return self.send_error(404)
            kind = 'text/javascript' if file.suffix == '.js' else mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
            self.response(file.read_bytes(), kind, head=head)

        def do_HEAD(self):
            self.get(True)

        def do_GET(self):
            self.get()

        def do_POST(self):
            if urlsplit(self.path).path != '/feedback':
                return self.send_error(404)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 2_000_000:
                    raise ValueError('Invalid request size')
                data = feedback(json.loads(self.rfile.read(length)), digest)
                output.mkdir(parents=True, exist_ok=True)
                raw = json.dumps(data, indent=2, allow_nan=False) + '\n'
                (output / f'{time.time_ns()}.json').write_text(raw)
                (output / ('latest.json' if data['by'] == 'operator' else 'automated-latest.json')).write_text(raw)
                self.response(b'{"ok":true}', 'application/json')
            except (ValueError, TypeError, AttributeError):
                self.send_error(400)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, type=Path)
    parser.add_argument('--hair', type=Path, help='optional neutral-pose browser hair configuration')
    parser.add_argument('--output', type=Path, default=REPO / 'build/yorimichi/character-review/feedback')
    parser.add_argument('--port', type=int, default=8899)
    args = parser.parse_args()
    if args.model.suffix != '.glb' or not args.model.is_file() or args.hair and not args.hair.is_file():
        parser.error('Provide an existing GLB and optional hair JSON')
    print(f'Character review: http://127.0.0.1:{args.port}/; saves: {args.output}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), handler(args.model.resolve(), args.output, args.hair)).serve_forever()


if __name__ == '__main__':
    main()
