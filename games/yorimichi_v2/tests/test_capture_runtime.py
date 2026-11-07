"""Runtime parity capture (tools/parity/capture_runtime.py): its receipt is one compare.py accepts, and mixed sizes fail."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


capture = load('v2_capture_runtime', 'tools/parity/capture_runtime.py')
compare = load('v2_parity_compare_rt', 'tools/parity/compare.py')
DONE = {'map': '/Game/Japan/Maps/Japan', 'engine_version': '5.8.2-56702186',
        'render': {'renderer': 'runtime viewport screenshot (LiveLibrary.Screenshot)', 'quality': {'r.ForwardShading': 1.0}}}


def shot(folder, name, size=(64, 36)):
    folder.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.zeros((size[1], size[0], 3), dtype=np.uint8)).save(folder / f'{name}.png')
    return folder / f'{name}.png'


@pytest.fixture
def checkout(tmp_path):
    repo = tmp_path / 'repo'
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    subprocess.run(['git', '-C', str(repo), '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-q',
                    '--allow-empty', '-m', 'seed'], check=True)
    return repo


def test_a_runtime_receipt_passes_compare_s_receipt_checks(tmp_path, checkout):
    poses = tmp_path / 'poses.json'
    poses.write_text(json.dumps({'schema': 1, 'poses': [{'name': 'coast'}, {'name': 'pier'}]}))
    names = ['coast', 'pier']
    sizes = [capture.png_size(shot(tmp_path / 'donor', n)) for n in names]
    assert sizes == [[64, 36], [64, 36]]
    receipt = capture.receipt('donor-runtime', checkout, DONE, poses, names, sizes, 8.)
    sha = compare.hashlib.sha256(poses.read_bytes()).hexdigest()
    assert compare.receipt_errors('donor', receipt, names, sha, tmp_path / 'donor') == []
    assert receipt['revision']['dirty'] is False and len(receipt['revision']['commit']) == 40


def test_captures_of_different_sizes_fail(tmp_path, checkout):
    poses = tmp_path / 'poses.json'
    poses.write_text(json.dumps({'schema': 1, 'poses': [{'name': 'a'}, {'name': 'b'}]}))
    with pytest.raises(ValueError, match='different sizes'):
        capture.receipt('v2', checkout, DONE, poses, ['a', 'b'], [[64, 36], [32, 18]], 8.)
