"""Loopback grip editor. Tailscale Serve exposes this dedicated path to the operator's tailnet."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import mimetypes
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import unquote, urlsplit
from grip_data import bone_names as bones, mirror_left, neutral_reach
from source_identity import CHARACTERS as CHARACTER_ROOT, playable_ids, profile_path

WEB = Path(__file__).resolve().parent
GAME = WEB.parents[1]
ROOT = GAME.parents[1]
MODELS = ROOT / 'build/yorimichi/kart-grip-editor'
SAVES = CHARACTER_ROOT
VENDOR = GAME / 'tools/character_review_web/vendor'
CHARACTERS = playable_ids()
WRITE_LOCK = threading.Lock()


def validate(data, meta):
    """@cc [owner:fontanierh,label:correctness] kart-authored-wheel-grips
    Saved hands MUST contain every hand/finger frame relative to the same unsteered wheel,
    identify the exact loaded skin, and derive the right hand from the authored left hand.
    Steering preview MUST NOT modify the saved grip. Runtime playback MUST apply the wheel
    transform to these saved frames rather than re-solving the fingers against animation.
    """
    if not isinstance(data, dict) or data.get('schema') != 1 or data.get('character') != meta['id']:
        raise ValueError('Wrong character or grip format')
    if data.get('model_sha256') != meta['model_sha256'] or data.get('authored_side') != 'L' or data.get('mirror') != 'anatomical-bind':
        raise ValueError('The model changed or the pose is not mirrored')
    if set(data.get('hands', {})) != {'L', 'R'}:
        raise ValueError('Only the authored left hand and mirrored right hand are allowed')
    for side in 'LR':
        frames = data.get('hands', {}).get(side, {})
        if set(frames) != set(bones(side)):
            raise ValueError('Every hand and finger joint must be saved')
        for values in frames.values():
            if not isinstance(values, list) or len(values) != 16 or not all(
                    isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n) for n in values):
                raise ValueError('Invalid finger transform')
            if max(abs(n) for n in values) > 20 or any(abs(values[i] - v) > 1e-6 for i, v in ((3, 0), (7, 0), (11, 0), (15, 1))):
                raise ValueError('Invalid affine finger transform')
            # Wheel-local positions are unscaled metres; rotations must remain rigid.
            columns = [values[i:i+3] for i in (0, 4, 8)]
            expected = 1 / meta['scale']
            for column in columns:
                if abs(math.hypot(*column) - expected) > .005:
                    raise ValueError('Finger scaling is not editable')
            for a, b in ((0, 1), (0, 2), (1, 2)):
                if abs(sum(x*y for x, y in zip(columns[a], columns[b]))) > .005:
                    raise ValueError('Sheared finger transform')
    expected = mirror_left(data['hands']['L'], meta)
    for name, frame in expected.items():
        if any(abs(a - b) > 1e-5 for a, b in zip(frame, data['hands']['R'][name])):
            raise ValueError('The other hand must be mirrored, not edited independently')
    result = {k: data[k] for k in ('schema', 'character', 'model_sha256', 'authored_side', 'mirror', 'hands')}
    left_pole = data.get('arm_poles', {}).get('L', meta['layout'].get('elbow', [-.10, .33, .57]))
    if not isinstance(left_pole, list) or len(left_pole) != 3 or not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and abs(v) < 2 for v in left_pole):
        raise ValueError('Invalid elbow position')
    if left_pole[1] <= 0:
        raise ValueError('Keep the left elbow on the left of the kart')
    mirrored = [left_pole[0], -left_pole[1], left_pole[2]]
    if data.get('arm_poles', {}).get('R', mirrored) != mirrored:
        raise ValueError('The other elbow must be mirrored')
    result['arm_poles'] = {'L': left_pole, 'R': mirrored}
    lean = data.get('shoulder_lean_degrees', 0)
    if not isinstance(lean, (int, float)) or not math.isfinite(lean) or not -15 <= lean <= 45:
        raise ValueError('Invalid shoulder lean')
    result['shoulder_lean_degrees'] = lean
    height = data.get('wheel_height_offset', 0)
    if not isinstance(height, (int, float)) or not math.isfinite(height) or abs(height) > .25:
        raise ValueError('Invalid wheel height')
    result['wheel_height_offset'] = height
    tilt = data.get('wheel_tilt_offset_degrees', 0)
    if not isinstance(tilt, (int, float)) or not math.isfinite(tilt) or not 15 <= meta['layout']['steering_tilt_degrees'] + tilt <= 75:
        raise ValueError('Invalid wheel angle')
    result['wheel_tilt_offset_degrees'] = tilt
    return result


def handler(models=MODELS, saves=SAVES):
    token_path = models / '.save-token'
    models.mkdir(parents=True, exist_ok=True)
    if not token_path.exists():
        token_path.write_text(secrets.token_urlsafe(32)); token_path.chmod(0o600)
    token = token_path.read_text().strip()

    class Handler(BaseHTTPRequestHandler):
        def respond(self, body, kind='application/json', status=200):
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self' blob:; frame-ancestors 'self'")
            self.end_headers(); self.wfile.write(body)

        def json(self, value, status=200):
            self.respond(json.dumps(value, allow_nan=False).encode(), status=status)

        def route(self):
            # Serve works both at loopback / and under the dedicated Tailscale path.
            route = unquote(urlsplit(self.path).path)
            if route.startswith('/kart-grips'):
                route = route[len('/kart-grips'):] or '/'
            return route

        def do_GET(self):
            route = self.route()
            if route == '/config.json':
                return self.json({'characters': list(CHARACTERS), 'token': token})
            pieces = route.strip('/').split('/')
            if len(pieces) == 2 and pieces[0] in ('meta', 'saved') and pieces[1] in CHARACTERS:
                name = pieces[1]
                path = models / f'{name}.json' if pieces[0] == 'meta' else profile_path(name, saves)
                if not path.exists():
                    return self.json({'pose': None, 'revision': ''}) if pieces[0] == 'saved' else self.json({'error': 'Model export not ready'}, 503)
                raw = path.read_bytes()
                return self.json({'pose': json.loads(raw), 'revision': hashlib.sha256(raw).hexdigest()}) if pieces[0] == 'saved' else self.respond(raw)
            base = WEB
            relative = route.lstrip('/') or 'index.html'
            if route.startswith('/vendor/'):
                base, relative = VENDOR, route[len('/vendor/'):]
            elif route.startswith('/models/'):
                base, relative = models, route[len('/models/'):]
                if relative not in {f'{name}.glb' for name in (*CHARACTERS, 'kart')}:
                    return self.send_error(404)
            elif relative not in ('index.html', 'app.js', 'style.css', 'grip_math.js'):
                return self.send_error(404)
            path = (base / relative).resolve()
            if not path.is_relative_to(base.resolve()) or not path.is_file():
                return self.send_error(404)
            kind = 'text/javascript' if path.suffix == '.js' else mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
            self.respond(path.read_bytes(), kind)

        def do_POST(self):
            if self.route() != '/save' or self.headers.get('X-Grip-Token') != token:
                return self.json({'error': 'Reload the editor before saving'}, 403)
            try:
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size <= 200_000:
                    raise ValueError('Invalid save size')
                incoming = json.loads(self.rfile.read(size))
                name = incoming.get('character')
                if name not in CHARACTERS:
                    raise ValueError('Unknown character')
                meta = json.loads((models / f'{name}.json').read_text())
                pose = validate(incoming, meta)
                misses = neutral_reach(pose, meta)
                if max(misses.values(), default=0) > .01:
                    raise ValueError(f'Arm reach exceeded by {max(misses.values())*1000:.0f} mm; bring the wheel closer before saving')
                pose.update(frame='Blender metres; wheel-local, unsteered; +X shaft, +Y left',
                            scale=meta['scale'], layout=meta['layout'], bind_world=meta['bind_world'],
                            saved_at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
                with WRITE_LOCK:
                    path = profile_path(name, saves)
                    prior = path.read_bytes() if path.exists() else b''
                    revision = hashlib.sha256(prior).hexdigest() if prior else ''
                    if incoming.get('revision', '') != revision:
                        return self.json({'error': 'A newer pose was saved. Reload before saving.'}, 409)
                    archive = models / 'history' / name
                    archive.mkdir(parents=True, exist_ok=True)
                    if prior:
                        (archive / f'{time.time_ns()}.json').write_bytes(prior)
                    raw = (json.dumps(pose, indent=2, allow_nan=False) + '\n').encode()
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_name('.' + path.name + '.tmp')
                    temporary.write_bytes(raw); temporary.replace(path)
                self.json({'ok': True, 'revision': hashlib.sha256(raw).hexdigest()})
            except (ValueError, TypeError, KeyError, AttributeError) as error:
                self.json({'error': str(error)}, 400)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8923)
    parser.add_argument('--models', type=Path, default=MODELS)
    parser.add_argument('--saves', type=Path, default=SAVES)
    args = parser.parse_args()
    print(f'Kart grip editor listening at http://127.0.0.1:{args.port}/', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), handler(args.models, args.saves)).serve_forever()


if __name__ == '__main__':
    main()
