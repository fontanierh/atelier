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


def head(repo):
    return subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                          check=True).stdout.strip()


def advance(repo):
    subprocess.run(['git', '-C', str(repo), '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-q',
                    '--allow-empty', '-m', 'advance'], check=True)


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
    receipt = capture.receipt('donor-runtime', checkout, DONE, poses, names, sizes, 8., head(checkout), 'process')
    sha = compare.hashlib.sha256(poses.read_bytes()).hexdigest()
    assert compare.receipt_errors('donor', receipt, names, sha, tmp_path / 'donor') == []
    assert receipt['revision']['dirty'] is False and len(receipt['revision']['commit']) == 40
    assert receipt['revision']['launch'] == 'process'


def test_captures_of_different_sizes_fail(tmp_path, checkout):
    poses = tmp_path / 'poses.json'
    poses.write_text(json.dumps({'schema': 1, 'poses': [{'name': 'a'}, {'name': 'b'}]}))
    with pytest.raises(ValueError, match='different sizes'):
        capture.receipt('v2', checkout, DONE, poses, ['a', 'b'], [[64, 36], [32, 18]], 8., head(checkout), 'session')


def test_a_receipt_names_the_launch_commit_and_refuses_a_moved_checkout(tmp_path, checkout):
    poses = tmp_path / 'poses.json'
    poses.write_text(json.dumps({'schema': 1, 'poses': [{'name': 'a'}]}))
    launched = head(checkout)
    bound = capture.receipt('v2', checkout, DONE, poses, ['a'], [[64, 36]], 8., launched, 'session')
    assert bound['revision'] == {'commit': launched, 'dirty': False, 'launch': 'session'}
    advance(checkout)
    with pytest.raises(ValueError, match='launched at'):
        capture.receipt('v2', checkout, DONE, poses, ['a'], [[64, 36]], 8., launched, 'session')


def test_compare_rejects_a_receipt_without_a_proven_launch(tmp_path, checkout):
    poses = tmp_path / 'poses.json'
    poses.write_text(json.dumps({'schema': 1, 'poses': [{'name': 'a'}]}))
    receipt = capture.receipt('v2', checkout, DONE, poses, ['a'], [[64, 36]], 8., head(checkout), 'session')
    shot(tmp_path / 'v2', 'a')
    sha = compare.hashlib.sha256(poses.read_bytes()).hexdigest()
    del receipt['revision']['launch']
    assert any('revision' in e for e in compare.receipt_errors('v2', receipt, ['a'], sha, tmp_path / 'v2'))


def test_a_game_without_a_session_needs_head_unmoved_since_it_started(checkout, monkeypatch):
    moved = capture.head_moved(checkout)
    assert moved > 0
    command = f'UnrealEditor {checkout.resolve()}/Game.uproject -game'

    def fake(argv, **kwargs):
        out = {'lsof': '4242\n', 'command=': command, 'lstart=': ''}
        key = 'lsof' if argv[0] == 'lsof' else argv[2]
        if key == 'lstart=':
            out[key] = capture.datetime.datetime.fromtimestamp(moved + offset).strftime('%a %b %d %H:%M:%S %Y')
        if argv[0] == 'git':
            return real(argv, **kwargs)
        return subprocess.CompletedProcess(argv, 0, out[key], '')

    real = subprocess.run
    monkeypatch.setattr(capture.subprocess, 'run', fake)
    offset = 5
    assert capture.process_revision(checkout, 8830) == head(checkout)
    offset = -5
    with pytest.raises(ValueError, match='HEAD moved after the game'):
        capture.process_revision(checkout, 8830)
    command = 'UnrealEditor /elsewhere/Game.uproject -game'
    with pytest.raises(ValueError, match='does not run a project of'):
        capture.process_revision(checkout, 8830)
