"""Feedback refers to the exact inspected model and cannot overwrite operator marks during QA."""
import importlib.util
import json
from pathlib import Path
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import hashlib
import pytest

spec = importlib.util.spec_from_file_location('character_review', Path(__file__).resolve().parents[1] / 'tools/character_review.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def mark():
    return dict(mesh='Head', faceIndex=15, modelPoint=[0., 1., 0.], camera=[0., 0., 2.], target=[0., 0., 0.],
                pose=dict(rootPosition=[0., 0., 0.], rootQuaternion=[0., 0., 0., 1.], bones=[['head', [0., 0., 0., 1.]]]))


def test_wrong_model_and_nonfinite_pose_are_rejected():
    data = dict(schema=1, model='abc', by='operator', marks=[mark()])
    with pytest.raises(ValueError):
        review.feedback(data, 'changed-model')
    data['marks'][0]['pose']['bones'][0][1][1] = float('nan')
    with pytest.raises(ValueError):
        review.feedback(data, 'abc')


def test_routes_and_automated_saves_preserve_operator_feedback(tmp_path):
    model = tmp_path / 'model.glb'
    model.write_bytes(b'test model')
    output = tmp_path / 'feedback'
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    server = ThreadingHTTPServer(('127.0.0.1', 0), review.handler(model, output))
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        assert urlopen(base + '/model.glb').read() == model.read_bytes()
        assert json.loads(urlopen(base + '/config.json').read())['sha256'] == digest
        with pytest.raises(HTTPError) as exc:
            urlopen(base + '/%2e%2e/character_review.py')
        assert exc.value.code == 404
        for by in ('operator', 'automated'):
            body = json.dumps(dict(schema=1, model=digest, by=by, marks=[mark()])).encode()
            with urlopen(Request(base + '/feedback', body, {'Content-Type': 'application/json'})) as response:
                assert response.status == 200
        assert json.loads((output / 'latest.json').read_text())['by'] == 'operator'
        assert json.loads((output / 'automated-latest.json').read_text())['by'] == 'automated'
        assert len(list(output.glob('*.json'))) == 4
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
