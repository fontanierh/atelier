"""Ordinary bounded guarded proof for actual coastal Harbor atomic GLB exports."""
import argparse
import json
import os
from pathlib import Path

from atelier import engine
from atelier.export_manifest import real_directory
from atelier.harness.safety import guarded

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--reference', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
output = real_directory(args.output.absolute())
if os.path.lexists(output): raise ValueError('Coastal export canary requires fresh evidence')
fixture = Path(__file__).resolve().parents[1] / 'fixtures/brinecove_atomic_exports.py'
command = [engine.blender(), '-b', '--factory-startup', '--threads', '3', '--python-exit-code', '1',
           '--python', str(fixture), '--', '--reference', str(args.reference.absolute()),
           '--output', str(output / 'products')]
code = guarded.run(command, output / 'guard', timeout=300, kind='job',
    purpose='actual Harbor bounded atomic GLB source conservation', env=dict(os.environ, PYTHONHASHSEED='0'))
if code: raise SystemExit(code)
assert 'COASTAL ATOMIC EXPORT CANARY COMPLETE' in (output / 'guard/stdout.log').read_text()
value = json.loads((output / 'products/result.json').read_text())
assert value['complete'] and value['serialized_glb_corner_equality'] and value['complete_runtime_policy_equal']
guard = json.loads((output / 'guard/memory-health-tree.json').read_text())
assert guard['state'] == 'child_exited' and guard['cleanup_complete'] and not guard['processes']
assert not guard.get('late_reporters', {}).get('unresolved')
print('GUARDED COASTAL ATOMIC EXPORT PASS', flush=True)
