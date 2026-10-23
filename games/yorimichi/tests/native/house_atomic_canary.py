"""Guarded comparison of selected house geometry with the original eight-asset authoring order."""
import argparse
import json
import os
from pathlib import Path

from atelier import engine
from atelier.export_manifest import real_directory
from atelier.harness.safety import guarded

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--world', type=Path, required=True)
parser.add_argument('--heightmap', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
root = real_directory(args.output.absolute())
if root.exists():
    raise ValueError('House canary requires a fresh evidence root')
fixture = Path(__file__).resolve().parents[1] / 'fixtures/house_atomic_context.py'
command = [engine.blender(), '-b', '--factory-startup', '--threads', '3', '--python-exit-code', '1',
           '--python', str(fixture), '--', '--world', str(args.world.absolute()),
           '--heightmap', str(args.heightmap.absolute()), '--output', str(root / 'products')]
code = guarded.run(command, root / 'guard', timeout=300, kind='job',
                   purpose='actual eight-house source geometry and final-query conservation',
                   env=dict(os.environ, PYTHONHASHSEED='0'))
if code:
    raise SystemExit(code)
assert 'HOUSE ATOMIC CONTEXT COMPLETE' in (root / 'guard/stdout.log').read_text()
result = json.loads((root / 'products/result.json').read_text())
guard = json.loads((root / 'guard/memory-health-tree.json').read_text())
assert result['complete'] and result['exact_geometry_corner_conservation'] and len(result['assets']) == 8
assert guard['state'] == 'child_exited' and guard['cleanup_complete'] and not guard['processes']
assert not guard.get('late_reporters', {}).get('unresolved', [])
print('GUARDED EIGHT-HOUSE SOURCE CONSERVATION PASS', flush=True)
