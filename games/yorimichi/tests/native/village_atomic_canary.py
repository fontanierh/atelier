"""Normal guarded complete Village source/FBX conservation, without a cold native build."""
import argparse
import json
import os
from pathlib import Path

from atelier import engine
from atelier.export_manifest import real_directory
from atelier.harness.safety import guarded

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
root = real_directory(args.output.absolute())
if os.path.lexists(root): raise ValueError('Fresh Village atomic evidence required')
fixture = Path(__file__).resolve().parents[1] / 'fixtures/village_atomic_equivalence.py'
command = [engine.blender(), '-b', '--factory-startup', '--threads', '3', '--python-exit-code', '1',
           '--python', str(fixture), '--', '--baseline', str(args.baseline.absolute()), '--output', str(root / 'products')]
code = guarded.run(command, root / 'guard', timeout=600, kind='job', purpose='complete independent Village source and FBX equivalence',
                   env=dict(os.environ, PYTHONHASHSEED='0'))
if code: raise SystemExit(code)
assert 'VILLAGE ATOMIC EQUIVALENCE COMPLETE' in (root / 'guard/stdout.log').read_text()
result = json.loads((root / 'products/result.json').read_text())
receipt = json.loads((root / 'guard/memory-health-tree.json').read_text())
assert result['complete'] and len(result['assets']) == 12 and result['numeric_exported_polygon_union']
assert receipt['state'] == 'child_exited' and receipt['cleanup_complete'] and not receipt['processes']
assert not receipt.get('late_reporters', {}).get('unresolved', [])
print('GUARDED COMPLETE VILLAGE ATOMIC EXPORT PASS', flush=True)
