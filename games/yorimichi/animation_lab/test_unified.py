"""Shared-library identity, model routing and cross-model job serialization."""
from functools import partial
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from server import Handler
from unified import UnifiedLab


class Worker:
    def __init__(self, generator):
        self.generator = generator
        self.jobs = {}
        self.requests = []

    def status(self):
        return {'name': self.generator, 'status': 'ready', 'active': None, 'device': 'cpu'}

    def request(self, path, data=None):
        if path.startswith('/api/jobs/'):
            if path.split('/')[-1] not in self.jobs:
                raise RuntimeError('Unknown job')
            return self.jobs[path.split('/')[-1]]
        self.requests.append(data)
        job = {'id': 'new_take', 'status': 'running', 'progress': 0, 'generator': self.generator}
        self.jobs[job['id']] = job
        return job.copy()

    def close(self):
        pass


class UnifiedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.roots = {key: (root / key).resolve() for key in ('unimate', 'kimodo')}
        self.lab = UnifiedLab(root / 'lab', self.roots, start=False)
        self.lab.backends = {key: Worker(key) for key in self.roots}
        self.addCleanup(self.lab.close)

    def save_take(self, generator, title):
        folder = self.roots[generator] / 'results/same_id'
        folder.mkdir(parents=True)
        job = {'id': 'same_id', 'status': 'complete', 'created': 1, 'title': title,
               'reference_clip': None, 'motion': '/results/same_id/motion.json',
               'provenance': '/results/same_id/provenance.json'}
        if generator == 'kimodo':
            job['generator'] = 'Kimodo'
        (folder / 'job.json').write_text(json.dumps(job))
        (folder / 'motion.json').write_text(json.dumps({'title': title}))
        return folder

    def test_colliding_ids_and_legacy_takes_keep_their_model_and_files(self):
        self.save_take('unimate', 'old UniMate take')
        self.save_take('kimodo', 'new Kimodo take')
        jobs = {job['id']: job for job in self.lab.library_payload()['results']}
        self.assertEqual(set(jobs), {'unimate_same_id', 'kimodo_same_id'})
        self.assertEqual(jobs['unimate_same_id']['generator'], 'UniMate')
        self.assertEqual(jobs['kimodo_same_id']['motion'], '/results/kimodo_same_id/motion.json')
        self.assertIsNone(jobs['unimate_same_id']['reference_clip'])
        for key in self.roots:
            self.assertEqual(self.lab.result_folder(key + '_same_id'), self.roots[key] / 'results/same_id')
            self.assertEqual(self.lab.output_folder(key + '_same_id'), self.roots[key] / 'exports/same_id')

    def test_cross_model_generation_is_serial_and_recovers_after_failure(self):
        job = self.lab.create({'generator': 'kimodo', 'prompt': 'roll forward', 'duration': 4, 'steps': 100})
        self.assertEqual(job['id'], 'kimodo_new_take')
        self.assertEqual(self.lab.backends['kimodo'].requests[0]['duration'], 4)
        with self.assertRaisesRegex(RuntimeError, 'already generating'):
            self.lab.create({'generator': 'unimate', 'prompt': 'jump forward'})
        self.lab.backends['kimodo'].jobs['new_take']['status'] = 'failed'
        next_job = self.lab.create({'generator': 'unimate', 'prompt': 'jump forward'})
        self.assertEqual(next_job['id'], 'unimate_new_take')
        self.assertEqual(len(self.lab.backends['unimate'].requests), 1)

    def test_validation_uses_requested_model_and_unknown_models_fail(self):
        for data in [{'generator': 'other', 'prompt': 'roll forward'},
                     {'generator': 'unimate', 'prompt': 'roll forward', 'steps': 100},
                     {'generator': 'kimodo', 'prompt': 'roll forward', 'duration': 11}]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.lab.create(data)
        self.assertFalse(any(worker.requests for worker in self.lab.backends.values()))

    def test_saved_takes_remain_readable_when_worker_is_down(self):
        self.save_take('kimodo', 'Backflip')
        self.assertEqual(self.lab.get_job('kimodo_same_id')['title'], 'Backflip')
        for unsafe in ['same_id', 'other_same_id', 'kimodo_../same_id', 'kimodo_%2e%2e']:
            self.assertIsNone(self.lab.result_folder(unsafe))
            self.assertIsNone(self.lab.output_folder(unsafe))

    def test_http_reads_and_exports_route_to_the_correct_existing_root(self):
        self.save_take('unimate', 'UniMate')
        self.save_take('kimodo', 'Kimodo')
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, lab=self.lab))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            for key, title in [('unimate', 'UniMate'), ('kimodo', 'Kimodo')]:
                with urllib.request.urlopen(base + f'/results/{key}_same_id/motion.json') as response:
                    self.assertEqual(json.load(response)['title'], title)
            body = b'glTF' + b'exported take'
            request = urllib.request.Request(base + '/api/save/kimodo_same_id/fox.glb', data=body, method='POST')
            with urllib.request.urlopen(request) as response:
                self.assertEqual(response.status, 201)
            self.assertEqual((self.roots['kimodo'] / 'exports/same_id/fox.glb').read_bytes(), body)
            self.assertFalse((self.roots['unimate'] / 'exports/same_id/fox.glb').exists())
            for path in ['/results/kimodo_../job.json', '/results/kimodo_same_id/.env', '/exports/unknown/fox.glb']:
                with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError):
                    urllib.request.urlopen(base + path)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
