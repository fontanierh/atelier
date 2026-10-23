"""Explicit bounded native atomic-export check, outside the hosted Python suite."""
import argparse
import json
import os
from pathlib import Path

from atelier import engine
from atelier.harness.safety import guarded

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
output = args.output.resolve()
if output.exists(): raise ValueError('Canary requires a fresh root')
fixture = Path(__file__).resolve().parents[1] / 'fixtures/atomic_mesh_export.py'
command = [engine.blender(), '-b', '--factory-startup', '--threads', '3', '--python-exit-code', '1',
           '--python', str(fixture), '--', '--output', str(output / 'products')]
code = guarded.run(command, output / 'guard', timeout=300, kind='job',
                   purpose='atomic source export conservation and deterministic reconstruction',
                   env=dict(os.environ, PYTHONHASHSEED='0'))
if code: raise SystemExit(code)
assert 'ATOMIC MESH EXPORT CANARY COMPLETE' in (output / 'guard/stdout.log').read_text()
result = json.loads((output / 'products/result.json').read_text())
assert result['complete'] and result['exact_corner_conservation'] and result['oversized_refused']
assert result['exported_fbx_corners_equal'] and result['colour_layers'] == 4
print('GUARDED ATOMIC MESH CANARY PASS', flush=True)
