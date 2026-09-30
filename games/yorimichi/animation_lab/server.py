"""Loopback animation playground: persistent local models, serial jobs, owned assets only."""
import argparse
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
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


def presets_for(generator):
    recipes = PRESETS
    if generator == 'kimodo':
        recipes = [('backflip', 'Backflip', 'Movement', 'A person does a backflip.', 99), *PRESETS]
    else:
        recipes = [('backflip', 'Backflip', 'Movement', 'A person does a backflip', 99), *PRESETS]
    return [{'slug': s, 'title': t, 'category': c, 'prompt': p, 'seed': seed} for s,t,c,p,seed in recipes]


def validate_request(data, generator='unimate'):
    if not isinstance(data, dict):
        raise ValueError('Expected a JSON object')
    prompt = data.get('prompt')
    if not isinstance(prompt, str) or not 3 <= len(prompt.strip()) <= 1000:
        raise ValueError('Enter a prompt between 3 and 1000 characters')
    seed = data.get('seed', 42)
    steps = data.get('steps', 100 if generator == 'kimodo' else 32)
    guidance = data.get('guidance', 3.)
    if type(seed) is not int or not 0 <= seed <= 2147483647:
        raise ValueError('Seed must be an integer from 0 to 2147483647')
    maximum_steps = 250 if generator == 'kimodo' else 64
    if type(steps) is not int or not 8 <= steps <= maximum_steps:
        raise ValueError(f'Steps must be an integer from 8 to {maximum_steps}')
    if type(guidance) not in (int, float) or not 1.01 <= guidance <= 8:
        raise ValueError('Guidance must be between 1.01 and 8')
    reference = data.get('reference_clip')
    if reference is not None and (not isinstance(reference, str) or reference not in {'Fox_' + name for name in ORIGINAL_PROMPTS}):
        raise ValueError('Unknown original comparison clip')
    guided = data.get('guided_sprint', False)
    if type(guided) is not bool or (guided and reference != 'Fox_Run'):
        raise ValueError('Guided sprint requires the Fox_Run reference')
    params = {'prompt': prompt.strip(), 'seed': seed, 'steps': steps, 'guidance': float(guidance),
              'reference_clip': reference, 'guided_sprint': guided}
    if generator == 'kimodo':
        if guided:
            raise ValueError('Kimodo uses prompt-only generation on SOMA')
        duration = data.get('duration', 3)
        if type(duration) not in (int, float) or not 1 <= duration <= 10:
            raise ValueError('Duration must be between 1 and 10 seconds')
        params['frames'] = round(duration * 30)
    return params


class Lab:
    def __init__(self, root, device='mps', warm=True, generator='unimate'):
        self.root = Path(root).resolve()
        self.generator = generator
        self.generator_name = 'Kimodo' if generator == 'kimodo' else 'UniMate'
        (self.root / 'results').mkdir(parents=True, exist_ok=True)
        self.engine = None
        self.lock = threading.Lock()
        self.state = {'status': 'loading', 'message': f'Loading {self.generator_name} and the fox rig…', 'device': device}
        self.active = None
        self.jobs = {}
        for path in (self.root / 'results').glob('*/job.json'):
            try:
                job = json.loads(path.read_text())
                if job['status'] == 'complete' and job.get('generator', 'UniMate') == self.generator_name:
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

    @property
    def asset_root(self):
        return self.root

    def status_payload(self):
        return {**self.state, 'generator': self.generator_name, 'active': self.active,
                'models': {self.generator: {**self.state, 'name': self.generator_name}}}

    def library_payload(self):
        with self.lock:
            results = [j.copy() for j in self.jobs.values() if j['status'] == 'complete']
        return {'generator': self.generator_name, 'default_generator': self.generator,
                'generators': [{'id': self.generator, 'name': self.generator_name}],
                'presets': presets_for(self.generator),
                'presets_by_generator': {self.generator: presets_for(self.generator)},
                'originals': original_library(), 'results': sorted(results, key=lambda j: j['created'], reverse=True)}

    def get_job(self, job_id):
        job = self.jobs.get(job_id)
        return job.copy() if job else None

    def result_folder(self, job_id):
        return self.root / 'results' / job_id if job_id in self.jobs else None

    def output_folder(self, job_id):
        if job_id in self.jobs or job_id in {item['id'] for item in original_library()}:
            return self.root / 'exports' / job_id
        return None

    def load(self, device):
        try:
            if self.generator == 'kimodo':
                from kimodo_engine import Engine
            else:
                from engine import Engine
            self.engine = Engine(self.root, device)
            self.state = {'status': 'ready', 'message': f'{self.generator_name} ready', 'device': self.engine.device,
                          'model': 'Kimodo SOMA RP v1.1' if self.generator == 'kimodo' else 'UniMate f60 v2 · EMA 100000',
                          'frames': 90 if self.generator == 'kimodo' else 60,
                          'rig': self.engine.rig['conditioning_bones'], 'skin_bones': self.engine.rig['skin_bones']}
        except Exception as exc:
            self.state = {'status': 'error', 'message': 'Model could not load. Check the server log and run setup.py.', 'device': device}
            print(f'Model load failed: {exc}', flush=True)

    def create(self, data):
        params = validate_request(data, self.generator)
        with self.lock:
            if self.state['status'] != 'ready':
                raise RuntimeError(self.state['message'])
            if self.active:
                raise RuntimeError('An animation is already generating. Wait for it to finish.')
            job_id = uuid.uuid4().hex
            job = {'id': job_id, 'status': 'queued', 'progress': 0, 'created': time.time(),
                   'title': data.get('title', 'Custom motion') if isinstance(data.get('title', 'Custom motion'), str) else 'Custom motion',
                   'category': data.get('category', 'Custom') if data.get('category') in ('Attacks', 'Movement') else 'Custom',
                   'generator': self.generator_name, **params}
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
            duration_args = {'frames': job['frames']} if self.generator == 'kimodo' else {}
            features, motion, provenance = self.engine.generate(job['prompt'], job['seed'], job['guidance'], job['steps'], progress,
                                                               guided_sprint=job['guided_sprint'], **duration_args)
            provenance['reference_clip'] = job['reference_clip']
            provenance['reference_usage'] = ('authored gait constraint' if job['guided_sprint']
                                             else 'comparison only' if job['reference_clip'] else 'none')
            if self.generator == 'kimodo':
                self.engine.np.savez_compressed(folder / 'source-motion.npz', **features)
            else:
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
            folder = self.lab.output_folder(parts[3]) if len(parts) == 5 else None
            if folder is None or parts[4] not in ('fox.glb', 'pose.png', 'preview.gif'):
                return self.json(404, {'error': 'Unknown motion or artifact'})
            try:
                size = int(self.headers.get('Content-Length', 0))
                if not 1 <= size <= 16 * 1024 * 1024:
                    raise ValueError('Artifact exceeds the 16 MiB limit')
                body = self.rfile.read(size)
                signatures = {'fox.glb': (b'glTF',), 'pose.png': (b'\x89PNG\r\n\x1a\n',),
                              'preview.gif': (b'GIF87a', b'GIF89a')}
                if not body.startswith(signatures[parts[4]]):
                    raise ValueError('Expected an exported GLB, PNG, or GIF')
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
            return self.json(200, self.lab.status_payload())
        if path == '/api/library':
            return self.json(200, self.lab.library_payload())
        if path.startswith('/api/jobs/'):
            job = self.lab.get_job(path.split('/')[-1])
            return self.json(200 if job else 404, job.copy() if job else {'error': 'Unknown job'})
        files = {'/': HERE / 'index.html', '/style.css': HERE / 'style.css',
                 '/app.js': self.lab.root / 'web/app.js', '/assets/fox.glb': self.lab.asset_root / 'assets/fox.glb',
                 '/assets/rig.json': self.lab.asset_root / 'assets/rig.json'}
        source = files.get(path)
        if path.startswith('/exports/'):
            parts = path.split('/')
            if len(parts) == 4 and parts[3] in ('fox.glb', 'pose.png', 'preview.gif'):
                folder = self.lab.output_folder(parts[2])
                source = folder / parts[3] if folder else None
        if path.startswith('/results/'):
            parts = path.split('/')
            if len(parts) == 4 and parts[3] in ('motion.json', 'provenance.json', 'features.npy', 'source-motion.npz', 'job.json'):
                folder = self.lab.result_folder(parts[2])
                source = folder / parts[3] if folder else None
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


def main():
    from contextlib import ExitStack
    import signal
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path)
    ap.add_argument('--port', type=int)
    ap.add_argument('--device', choices=['mps', 'cpu', 'cuda'])
    ap.add_argument('--generator', choices=['both', 'unimate', 'kimodo'], default='both')
    ap.add_argument('--unimate-root', type=Path, default=REPO / 'build/yorimichi/unimate')
    ap.add_argument('--kimodo-root', type=Path, default=REPO / 'build/yorimichi/kimodo')
    ap.add_argument('--port-file', type=Path, help=argparse.SUPPRESS)
    args = ap.parse_args()
    args.root = args.root or REPO / 'build/yorimichi' / ('motion_lab' if args.generator == 'both' else args.generator)
    port = args.port if args.port is not None else (8842 if args.generator == 'unimate' else 8843)
    with ExitStack() as stack:
        if args.generator == 'both':
            from unified import UnifiedLab
            lab = UnifiedLab(args.root, {'unimate': args.unimate_root, 'kimodo': args.kimodo_root})
            stack.callback(lab.close)
        else:
            device = args.device or ('cpu' if args.generator == 'kimodo' else 'mps')
            lab = Lab(args.root, device, generator=args.generator)
        server = ThreadingHTTPServer(('127.0.0.1', port), partial(Handler, lab=lab))
        stack.callback(server.server_close)
        if args.port_file:
            args.port_file.write_text(json.dumps({'port': server.server_port}))
        print(f'Fox motion lab: http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
