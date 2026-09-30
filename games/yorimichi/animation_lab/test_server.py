"""Exercise validation, local-only serving, job cleanup and persistence without the GPU."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
from server import Handler, Lab, validate_request


class RequestTests(unittest.TestCase):
    def test_prompt_cannot_inject_command_arguments(self):
        prompt = 'Run fast; $(touch ignored) --device cuda'
        self.assertEqual(validate_request({'prompt': prompt, 'seed': 0})['prompt'], prompt)
        self.assertEqual(validate_request({'prompt': prompt, 'seed': 0})['seed'], 0)

    def test_invalid_numeric_values_rejected(self):
        for field, values in [('seed', [True, -1, 1.2, 2147483648]), ('steps', [True, 7, 65]), ('guidance', [float('nan'), float('inf'), True, 0])]:
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    validate_request({'prompt': 'jump forward', field: value})

    def test_generation_failure_releases_slot(self):
        with tempfile.TemporaryDirectory() as temp:
            lab = Lab(temp, warm=False)
            lab.state['status'] = 'ready'
            engine = unittest.mock.Mock()
            engine.generate.side_effect = RuntimeError('bad model output')
            lab.engine = engine
            with patch('server.threading.Thread'):
                job = lab.create({'prompt': 'jump forward'})
                with self.assertRaises(RuntimeError):
                    lab.create({'prompt': 'run forward'})
            lab.run(lab.jobs[job['id']])
            self.assertIsNone(lab.active)
            self.assertEqual(lab.jobs[job['id']]['status'], 'failed')
            self.assertEqual(json.loads((Path(temp)/'results'/job['id']/'job.json').read_text())['status'], 'failed')

    def test_http_origin_host_and_file_boundaries(self):
        with tempfile.TemporaryDirectory() as temp:
            lab = Lab(temp, warm=False)
            server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, lab=lab))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with urllib.request.urlopen(base+'/api/status') as response:
                    self.assertEqual(response.status, 200)
                for path, headers, code in [('/api/status', {'Host': 'evil.example'},403),
                                            ('/api/status', {'Origin': 'http://evil.example'},403),
                                            ('/results/../model/checkpoint.pt',{},404),
                                            ('/.env',{},404), ('/assets/../../AGENTS.md',{},404)]:
                    with self.subTest(path=path, headers=headers), self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(urllib.request.Request(base+path, headers=headers))
                    self.assertEqual(error.exception.code, code)
                # Artifact uploads are limited to known takes and valid file types.
                for path, body, code in [('/api/save/unknown/fox.glb', b'glTF', 404),
                                         ('/api/save/Fox_Idle/fox.glb', b'bad', 400),
                                         ('/api/save/Fox_Idle/../../.env', b'bad', 404)]:
                    request = urllib.request.Request(base+path, data=body, method='POST')
                    with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(request)
                    self.assertEqual(error.exception.code, code)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == '__main__':
    unittest.main()
