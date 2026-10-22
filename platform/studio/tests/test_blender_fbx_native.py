"""Explicit guarded receiving canary; hosted CI runs the source-level exporter checks."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from atelier import engine
from atelier.harness.safety import guarded

pytestmark = pytest.mark.skipif(os.environ.get('ATELIER_NATIVE_FBX_CANARY') != '1',
    reason='requires explicit local Blender admission and native fixtures')


def test_native_fbx_cross_process_order_path_and_roundtrip(tmp_path):
    fixture = Path(__file__).with_name('fixtures') / 'fbx_export.py'
    before = hashlib.sha256(fixture.read_bytes()).hexdigest()
    for name, seed in (('first', '0'), ('second', '91')):
        command = [engine.blender(), '-b', '--factory-startup', '--threads', '3',
                   '--python-exit-code', '1', '--python', str(fixture), '--', '--output', str(tmp_path/name)]
        if name == 'second':
            command.append('--reverse')
        code = guarded.run(command, tmp_path/(name+'.guard'), timeout=900,
            purpose='native FBX determinism and receiving canary', kind='job',
            env=dict(os.environ, PYTHONHASHSEED=seed))
        assert code == 0
        assert json.loads((tmp_path/name/'result.json').read_text())['uv_channels'] == 6
        assert 'FBX CANARY COMPLETE' in (tmp_path/(name+'.guard')/'stdout.log').read_text()
    for name in ('static.fbx', 'skeletal.fbx', 'clip.fbx'):
        assert (tmp_path/'first'/name).read_bytes() == (tmp_path/'second'/name).read_bytes(), name
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == before
