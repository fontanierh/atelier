"""One fox library and API, with guarded workers in each model's own environment."""

from contextlib import ExitStack
import json
from pathlib import Path
import re
import subprocess
import threading
import urllib.error
import urllib.request

from server import HERE, Lab, original_library, presets_for, validate_request

NAMES = {'unimate': 'UniMate', 'kimodo': 'Kimodo'}


def split_id(public_id):
    if not re.fullmatch(r'(unimate|kimodo)_[A-Za-z0-9_]+', public_id):
        return None
    return public_id.split('_', 1)


def public_job(job, generator):
    result = {**job, 'source_id': job['id'], 'id': generator + '_' + job['id'],
              'generator': NAMES[generator]}
    if job.get('motion'):
        result['motion'] = f'/results/{result["id"]}/motion.json'
    if job.get('provenance'):
        result['provenance'] = f'/results/{result["id"]}/provenance.json'
    return result


class Backend:
    def __init__(self, generator, root, runtime, start=True):
        self.generator, self.root = generator, Path(root).resolve()
        self.stack = ExitStack()
        self.process = self.monitor = None
        self.address = Path(runtime) / generator / 'address.json'
        if not start or not (self.root / 'venv/bin/python').is_file():
            return
        from atelier.safety.guard import attach, reap
        try:
            self.address.parent.mkdir(parents=True, exist_ok=True)
            self.address.unlink(missing_ok=True)
            log = self.stack.enter_context((self.address.parent / 'stdout.log').open('w'))
            self.process = subprocess.Popen([
                str(self.root / 'venv/bin/python'), '-u', str(HERE / 'server.py'),
                '--generator', generator, '--root', str(self.root), '--port', '0',
                '--port-file', str(self.address),
            ], stdout=log, stderr=subprocess.STDOUT)
            self.stack.callback(reap, self.process)
            self.monitor = self.stack.enter_context(attach(
                self.process.pid, self.address.parent / 'memory-health.json', duration=None))
        except BaseException:
            self.close()
            raise

    def request(self, path, data=None):
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError(f'{NAMES[self.generator]} worker is unavailable; run setup')
        if self.monitor is not None and self.monitor.poll() is not None:
            from atelier.safety.guard import reap
            reap(self.process)
            raise RuntimeError(f'{NAMES[self.generator]} memory guard stopped')
        try:
            port = json.loads(self.address.read_text())['port']
        except (OSError, ValueError, KeyError):
            raise RuntimeError(f'{NAMES[self.generator]} worker is starting') from None
        request = urllib.request.Request(f'http://127.0.0.1:{port}{path}',
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Content-Type': 'application/json'} if data is not None else {})
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            message = json.load(exc).get('error', 'Worker request failed')
            if exc.code == 400:
                raise ValueError(message) from None
            raise RuntimeError(message) from None
        except (OSError, TimeoutError):
            raise RuntimeError(f'{NAMES[self.generator]} worker is starting or disconnected') from None

    def status(self):
        try:
            state = self.request('/api/status')
            state.pop('models', None)
            return {**state, 'name': NAMES[self.generator]}
        except RuntimeError as exc:
            running = self.process is not None and self.process.poll() is None
            return {'status': 'loading' if running else 'error', 'message': str(exc),
                    'name': NAMES[self.generator], 'active': None}

    def close(self):
        self.stack.close()


class UnifiedLab:
    def __init__(self, root, roots, start=True):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.roots = {key: Path(path).resolve() for key, path in roots.items()}
        self.backends = {}
        self.active = None
        self.lock = threading.Lock()
        hashes = set()
        for path in self.roots.values():
            rig = path / 'assets/rig.json'
            if rig.is_file():
                hashes.add(json.loads(rig.read_text())['source_sha256'])
        if len(hashes) > 1:
            raise ValueError('Model labs exported different fox revisions; rerun setup for both')
        self.asset_root = next((path for path in self.roots.values()
                                if (path / 'assets/fox.glb').is_file()), self.root)
        try:
            for generator, path in self.roots.items():
                self.backends[generator] = Backend(generator, path, self.root / 'workers', start=start)
        except BaseException:
            self.close()
            raise

    def close(self):
        for backend in self.backends.values():
            backend.close()

    def library_payload(self):
        results = []
        for generator, root in self.roots.items():
            # Reading persisted takes also works while a worker is loading or unavailable.
            results.extend(public_job(job, generator) for job in Lab(root, warm=False, generator=generator).jobs.values())
        return {'generator': 'both', 'default_generator': 'kimodo',
                'generators': [{'id': key, 'name': NAMES[key]} for key in self.roots],
                'presets_by_generator': {key: presets_for(key) for key in self.roots},
                'originals': original_library(),
                'results': sorted(results, key=lambda job: job['created'], reverse=True)}

    def get_job(self, job_id):
        parts = split_id(job_id)
        if not parts or parts[0] not in self.backends:
            return None
        generator, source_id = parts
        try:
            job = self.backends[generator].request('/api/jobs/' + source_id)
        except RuntimeError:
            file = self.roots[generator] / 'results' / source_id / 'job.json'
            try:
                job = json.loads(file.read_text())
            except (OSError, ValueError):
                return None
        return public_job(job, generator)

    def refresh_active(self):
        if self.active:
            job = self.get_job(self.active)
            if job and job['status'] in ('complete', 'failed'):
                self.active = None
            elif job is None:
                # A worker crash must not keep the other model permanently blocked.
                generator, _ = split_id(self.active)
                if self.backends[generator].status()['status'] == 'error':
                    self.active = None

    def status_payload(self):
        with self.lock:
            self.refresh_active()
            models = {key: backend.status() for key, backend in self.backends.items()}
            if not self.active:
                self.active = next((key + '_' + value['active'] for key, value in models.items() if value.get('active')), None)
            status = ('ready' if any(m['status'] == 'ready' for m in models.values())
                      else 'loading' if any(m['status'] == 'loading' for m in models.values()) else 'error')
            return {'status': status, 'models': models, 'active': self.active}

    def create(self, data):
        if not isinstance(data, dict) or data.get('generator') not in self.backends:
            raise ValueError('Choose UniMate or Kimodo to generate this motion')
        generator = data['generator']
        validate_request(data, generator)
        with self.lock:
            self.refresh_active()
            if self.active:
                raise RuntimeError('An animation is already generating. Wait for it to finish.')
            job = public_job(self.backends[generator].request('/api/generate', data), generator)
            self.active = job['id']
            return job

    def result_folder(self, job_id):
        parts = split_id(job_id)
        if not parts or parts[0] not in self.roots:
            return None
        folder = self.roots[parts[0]] / 'results' / parts[1]
        return folder if (folder / 'job.json').is_file() else None

    def output_folder(self, job_id):
        if job_id in {item['id'] for item in original_library()}:
            return self.root / 'exports' / job_id
        folder = self.result_folder(job_id)
        return folder.parent.parent / 'exports' / folder.name if folder else None
