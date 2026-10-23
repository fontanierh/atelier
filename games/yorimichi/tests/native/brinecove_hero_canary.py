"""Ordinary bounded guard for committed coastal hero export and texture parity."""
import argparse
import json
import os
from pathlib import Path

from atelier import engine
from atelier.export_manifest import real_directory
from atelier.harness.safety import guarded

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
root = real_directory(args.output.absolute())
if os.path.lexists(root): raise ValueError('Hero proof requires a fresh evidence root')
fixture = Path(__file__).resolve().parents[1] / 'fixtures/brinecove_hero_exports.py'
code = guarded.run([engine.blender(), '-b', '--factory-startup', '--threads', '3', '--python-exit-code', '1',
    '--python', str(fixture), '--', '--output', str(root / 'products')], root / 'guard', timeout=300,
    kind='job', purpose='actual coastal hero atomic geometry and material conservation', env=dict(os.environ, PYTHONHASHSEED='0'))
if code: raise SystemExit(code)
assert 'COASTAL HERO EXPORT CANARY COMPLETE' in (root / 'guard/stdout.log').read_text()
value = json.loads((root / 'products/result.json').read_text())
assert value['complete'] and value['serialized_geometry_equal'] and value['exact_material_texture_equal']
guard = json.loads((root / 'guard/memory-health-tree.json').read_text())
assert guard['state'] == 'child_exited' and guard['cleanup_complete'] and not guard['processes']
assert not guard.get('late_reporters', {}).get('unresolved')
print('GUARDED COASTAL HERO EXPORT PASS', flush=True)
