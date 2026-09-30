"""Loopback animation playground: persistent UniMate model, serial jobs, owned assets only."""
import argparse
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import re
from pathlib import Path
import threading
import time
from urllib.parse import unquote, urlsplit
import uuid

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

ORIGINAL_PROMPTS = {
    'Idle': 'A person stands in a relaxed fighting stance.',
    'Creep': 'A person takes short crouching steps forward.',
    'Run': 'A person sprints forward at full speed.',
    'AttackR_A': 'A fighter slashes diagonally downward with the right hand.',
    'AttackL_A': 'A fighter slashes diagonally downward with the left hand.',
    'AttackL_B': 'A fighter swings the left hand across the body.',
    'AttackR_B': 'A fighter swings the right hand across the body.',
    'Kick': 'A fighter kicks forward with the right foot.',
    'DashForward': 'A fighter dashes forward.',
    'DashBackward': 'A fighter quickly steps backwards.',
    'TurnLeft': 'A person turns left by half a turn.',
    'TurnRight': 'A person turns right by half a turn.',
    'Hurt': 'A person recoils backwards after a hit.',
    'Death': 'A person collapses to the ground.',
    'Jump': 'A person jumps up and lands on both feet.',
}
LEGACY_COMPARISONS = {
    'Forward sprint': 'Fox_Run', 'Sprint · corrected vocabulary / seed 10': 'Fox_Run',
    'Sprint · corrected vocabulary / seed 19': 'Fox_Run', 'Diagonal claw': 'Fox_AttackR_A',
    'Diagonal claw · corrected vocabulary': 'Fox_AttackR_A', 'Roundhouse kick': 'Fox_Kick',
    'Low sweep': 'Fox_Kick', 'Retreating steps': 'Fox_DashBackward', 'Jump & land': 'Fox_Jump',
}


def original_library():
    clips = json.loads((REPO / 'games/yorimichi/assets/characters/fox-hunter/manifest.json').read_text())['clips']
    return [{'id': 'Fox_' + name, 'prompt': ORIGINAL_PROMPTS[name], **meta} for name, meta in clips.items()]

PRESETS = [
    ('diagonal-claw', 'Diagonal claw', 'Attacks', 'A human fighter winds up the right arm, slashes diagonally down across the body with the right hand, then returns to a fighting stance.', 42),
    ('double-strike', 'Double strike', 'Attacks', 'A human fighter throws a quick left punch followed by a powerful right punch, then returns to a fighting stance.', 117),
    ('roundhouse', 'Roundhouse kick', 'Attacks', 'A human performs a fast right roundhouse kick, turning the hips and extending the right leg sideways, then lowers the leg and recovers balance.', 73),
    ('low-sweep', 'Low sweep', 'Attacks', 'A human fighter crouches and sweeps the right leg in a low spinning kick, then stands up.', 204),
    ('sprint', 'Forward sprint', 'Movement', 'A human runs forward quickly with alternating long strides and pumping arms.', 19),
    ('sidestep', 'Lateral dodge', 'Movement', 'A human fighter quickly sidesteps to the left, bends the knees and keeps both hands raised defensively.', 89),
    ('backstep', 'Retreating steps', 'Movement', 'A human fighter takes quick steps backwards with bent knees while holding both hands up in a defensive guard.', 312),
    ('jump', 'Jump & land', 'Movement', 'A human bends the knees, jumps straight up with both feet leaving the ground, then lands and bends the knees to absorb the impact.', 56),
]


def validate_request(data):
    if not isinstance(data, dict):
        raise ValueError('Expected a JSON object')
    prompt = data.get('prompt')
    if not isinstance(prompt, str) or not 3 <= len(prompt.strip()) <= 1000:
        raise ValueError('Enter a prompt between 3 and 1000 characters')
    seed = data.get('seed', 42)
    steps = data.get('steps', 32)
    guidance = data.get('guidance', 3.)
    if type(seed) is not int or not 0 <= seed <= 2147483647:
        raise ValueError('Seed must be an integer from 0 to 2147483647')
    if type(steps) is not int or not 8 <= steps <= 64:
        raise ValueError('Steps must be an integer from 8 to 64')
    if type(guidance) not in (int, float) or not 1.01 <= guidance <= 8:
        raise ValueError('Guidance must be between 1.01 and 8')
    reference = data.get('reference_clip')
    if reference is not None and (not isinstance(reference, str) or reference not in {'Fox_' + name for name in ORIGINAL_PROMPTS}):
        raise ValueError('Unknown original comparison clip')
    guided = data.get('guided_sprint', False)
    if type(guided) is not bool or (guided and reference != 'Fox_Run'):
        raise ValueError('Guided sprint requires the Fox_Run reference')
    return {'prompt': prompt.strip(), 'seed': seed, 'steps': steps, 'guidance': float(guidance),
            'reference_clip': reference, 'guided_sprint': guided}


class Lab:
    def __init__(self, root, device='mps', warm=True):
        self.root = Path(root).resolve()
        (self.root / 'results').mkdir(parents=True, exist_ok=True)
        self.engine = None
        self.lock = threading.Lock()
        self.state = {'status': 'loading', 'message': 'Loading UniMate and the fox rig…', 'device': device}
        self.active = None
        self.jobs = {}
        for path in (self.root / 'results').glob('*/job.json'):
            try:
                job = json.loads(path.read_text())
                if job['status'] == 'complete':
                    # Organize the first experiment's known comparison targets.
                    # New jobs record an explicit choice, including None for a
                    # standalone generation; never infer over that choice.
                    if 'reference_clip' not in job:
                        job['reference_clip'] = LEGACY_COMPARISONS.get(job['title'])
                    self.jobs[job['id']] = job
            except (OSError, ValueError, KeyError):
                continue
        if warm:
            threading.Thread(target=self.load, args=(device,), daemon=True).start()

    def load(self, device):
        try:
            from engine import Engine
            self.engine = Engine(self.root, device)
            self.state = {'status': 'ready', 'message': 'UniMate ready', 'device': self.engine.device,
                          'model': 'UniMate f60 v2 · EMA 100000', 'frames': 60,
                          'rig': self.engine.rig['conditioning_bones'], 'skin_bones': self.engine.rig['skin_bones']}
        except Exception as exc:
            self.state = {'status': 'error', 'message': 'Model could not load. Check the server log and run setup.py.', 'device': device}
            print(f'Model load failed: {exc}', flush=True)

    def create(self, data):
        params = validate_request(data)
        with self.lock:
            if self.state['status'] != 'ready':
                raise RuntimeError(self.state['message'])
            if self.active:
                raise RuntimeError('An animation is already generating. Wait for it to finish.')
            job_id = uuid.uuid4().hex
            job = {'id': job_id, 'status': 'queued', 'progress': 0, 'created': time.time(),
                   'title': data.get('title', 'Custom motion') if isinstance(data.get('title', 'Custom motion'), str) else 'Custom motion',
                   'category': data.get('category', 'Custom') if data.get('category') in ('Attacks', 'Movement') else 'Custom',
                   **params}
            job['title'] = job['title'][:80]
            self.jobs[job_id] = job
            self.active = job_id
        threading.Thread(target=self.run, args=(job,), daemon=True).start()
        return job.copy()

    def run(self, job):
        folder = self.root / 'results' / job['id']
        try:
            folder.mkdir()
            job['status'] = 'running'
            def progress(i, total):
                job['progress'] = round(i / total * 100)
            features, motion, provenance = self.engine.generate(job['prompt'], job['seed'], job['guidance'], job['steps'], progress,
                                                               guided_sprint=job['guided_sprint'])
            provenance['reference_clip'] = job['reference_clip']
            provenance['reference_usage'] = ('authored gait constraint' if job['guided_sprint']
                                             else 'comparison only' if job['reference_clip'] else 'none')
            self.engine.np.save(folder / 'features.npy', features)
            (folder / 'motion.json').write_text(json.dumps(motion))
            (folder / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
            job.update(status='complete', progress=100, seconds=provenance['seconds'], diagnostics=provenance['diagnostics'],
                       conditioning_version=provenance['conditioning_version'],
                       guided=motion.get('guided'), loop=motion.get('loop', False), travel_speed=motion.get('travel_speed'),
                       motion=f'/results/{job["id"]}/motion.json', provenance=f'/results/{job["id"]}/provenance.json', frames=motion['frames'], fps=motion['fps'])
        except Exception as exc:
            job.update(status='failed', message='Generation failed; see the server log for details.')
            print(f'Generation {job["id"]} failed: {exc}', flush=True)
        finally:
            try:
                (folder / 'job.json').write_text(json.dumps(job, indent=2) + '\n')
            finally:
                with self.lock:
                    self.active = None


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, lab, **kwargs):
        self.lab = lab
        super().__init__(*args, **kwargs)

    def trusted(self):
        host = self.headers.get('Host', '')
        allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        origin = self.headers.get('Origin')
        return host in allowed and (origin is None or origin in {'http://' + h for h in allowed})

    def json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self.trusted():
            return self.json(403, {'error': 'This playground accepts local requests only'})
        if self.path.startswith('/api/save/'):
            parts = self.path.split('/')
            allowed_originals = {'Fox_' + c for c in json.loads((REPO / 'games/yorimichi/assets/characters/fox-hunter/manifest.json').read_text())['clips']}
            if len(parts) != 5 or (parts[3] not in self.lab.jobs and parts[3] not in allowed_originals) or parts[4] not in ('fox.glb', 'pose.png'):
                return self.json(404, {'error': 'Unknown motion or artifact'})
            try:
                size = int(self.headers.get('Content-Length', 0))
                if not 1 <= size <= 16 * 1024 * 1024:
                    raise ValueError('Artifact exceeds the 16 MiB limit')
                body = self.rfile.read(size)
                if not body.startswith(b'glTF' if parts[4] == 'fox.glb' else b'\x89PNG\r\n\x1a\n'):
                    raise ValueError('Expected an exported GLB or PNG')
                folder = self.lab.root / 'exports' / parts[3]
                folder.mkdir(parents=True, exist_ok=True)
                (folder / parts[4]).write_bytes(body)
                return self.json(201, {'url': f'/exports/{parts[3]}/{parts[4]}'})
            except ValueError as exc:
                return self.json(400, {'error': str(exc)})
        if self.path != '/api/generate':
            return self.json(404, {'error': 'Unknown endpoint'})
        try:
            size = int(self.headers.get('Content-Length', 0))
            if not 1 <= size <= 8192 or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('Expected a small JSON request')
            job = self.lab.create(json.loads(self.rfile.read(size)))
            self.json(202, job)
        except (ValueError, UnicodeError) as exc:
            self.json(400, {'error': str(exc)})
        except RuntimeError as exc:
            self.json(409, {'error': str(exc)})

    def do_GET(self):
        if not self.trusted():
            return self.json(403, {'error': 'Local access only'})
        path = unquote(urlsplit(self.path).path)
        if path == '/api/status':
            return self.json(200, {**self.lab.state, 'active': self.lab.active})
        if path == '/api/library':
            with self.lab.lock:
                results = [j.copy() for j in self.lab.jobs.values() if j['status'] == 'complete']
            return self.json(200, {'presets': [{'slug': s, 'title': t, 'category': c, 'prompt': p, 'seed': seed} for s,t,c,p,seed in PRESETS],
                                   'originals': original_library(), 'results': sorted(results, key=lambda j: j['created'], reverse=True)})
        if path.startswith('/api/jobs/'):
            job = self.lab.jobs.get(path.split('/')[-1])
            return self.json(200 if job else 404, job.copy() if job else {'error': 'Unknown job'})
        files = {'/': HERE / 'index.html', '/style.css': HERE / 'style.css',
                 '/app.js': self.lab.root / 'web/app.js', '/assets/fox.glb': self.lab.root / 'assets/fox.glb',
                 '/assets/rig.json': self.lab.root / 'assets/rig.json'}
        source = files.get(path)
        if path.startswith('/exports/'):
            parts = path.split('/')
            if len(parts) == 4 and re.fullmatch(r'[A-Za-z0-9_]+', parts[2]) and parts[3] in ('fox.glb', 'pose.png'):
                source = self.lab.root / 'exports' / parts[2] / parts[3]
        if path.startswith('/results/'):
            parts = path.split('/')
            if len(parts) == 4 and parts[2] in self.lab.jobs and parts[3] in ('motion.json', 'provenance.json', 'features.npy', 'job.json'):
                source = self.lab.root / 'results' / parts[2] / parts[3]
        if source is None or not source.is_file():
            return self.json(404, {'error': 'File not found'})
        body = source.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mimetypes.guess_type(source.name)[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(len(body)))
        if path.startswith('/exports/'):
            self.send_header('Content-Disposition', f'attachment; filename="{source.parent.name}-{source.name}"')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, default=REPO / 'build/yorimichi/unimate')
    ap.add_argument('--port', type=int, default=8842)
    ap.add_argument('--device', choices=['mps', 'cpu', 'cuda'], default='mps')
    args = ap.parse_args()
    lab = Lab(args.root, args.device)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), partial(Handler, lab=lab))
    print(f'Fox motion lab: http://127.0.0.1:{args.port}', flush=True)
    server.serve_forever()
