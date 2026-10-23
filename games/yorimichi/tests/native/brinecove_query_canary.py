"""Normal bounded guard for the export-independent coastal query boundary."""
import argparse
import json
import os
from pathlib import Path

from atelier import engine
from atelier.export_manifest import real_directory
from atelier.harness.safety import guarded

parser = argparse.ArgumentParser(description=__doc__)
for flag in ('baseline', 'rim', 'output'): parser.add_argument('--' + flag, type=Path, required=True)
args = parser.parse_args()
root = real_directory(args.output.absolute())
if os.path.lexists(root): raise ValueError('Coastal query canary requires fresh evidence')
fixture = Path(__file__).resolve().parents[1] / 'fixtures/brinecove_query_geometry.py'
code = guarded.run([engine.blender(), '-b', '--factory-startup', '--threads', '3', '--python-exit-code', '1',
    '--python', str(fixture), '--', '--baseline', str(args.baseline.absolute()), '--rim', str(args.rim.absolute()),
    '--output', str(root / 'products')], root / 'guard', timeout=180, kind='job',
    purpose='actual coastal source query versus prior GLB query conservation', env=dict(os.environ, PYTHONHASHSEED='0'))
if code: raise SystemExit(code)
assert 'COASTAL SOURCE QUERY CANARY COMPLETE' in (root / 'guard/stdout.log').read_text()
value = json.loads((root / 'products/result.json').read_text())
assert value['complete'] and value['exact_query_triangle_cycles']
guard = json.loads((root / 'guard/memory-health-tree.json').read_text())
assert guard['state'] == 'child_exited' and guard['cleanup_complete'] and not guard['processes']
assert not guard.get('late_reporters', {}).get('unresolved')
print('GUARDED COASTAL SOURCE QUERY PASS', flush=True)
