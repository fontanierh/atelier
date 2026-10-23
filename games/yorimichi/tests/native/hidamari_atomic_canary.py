"""Guarded original city constructor context and selected source conservation."""
import argparse
import json
import os
from pathlib import Path

from atelier import engine
from atelier.export_manifest import real_directory
from atelier.harness.safety import guarded

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--donor', required=True, type=Path)
parser.add_argument('--output', required=True, type=Path)
args = parser.parse_args()
root = real_directory(args.output.absolute())
if os.path.lexists(root):
    raise ValueError('City context requires fresh evidence')
fixture = Path(__file__).resolve().parents[1] / 'fixtures/hidamari_atomic_context.py'
command = [engine.blender(), '-b', '--factory-startup', '--threads', '3', '--python-exit-code', '1',
           '--python', str(fixture), '--', '--donor', str(args.donor.absolute()),
           '--output', str(root / 'products')]
code = guarded.run(command, root / 'guard', timeout=900, kind='job',
    purpose='original city context and selected geometry conservation',
    env=dict(os.environ, PYTHONHASHSEED='0'))
if code:
    raise SystemExit(code)
assert 'HIDAMARI ATOMIC CONTEXT COMPLETE' in (root / 'guard/stdout.log').read_text()
result = json.loads((root / 'products/result.json').read_text())
guard = json.loads((root / 'guard/memory-health-tree.json').read_text())
assert result['complete'] and result['ordered_attribute_hash_equality'] and len(result['selected']) == result['logical_assets'] == 86
assert guard['state'] == 'child_exited' and guard['cleanup_complete'] and not guard['processes']
assert not guard.get('late_reporters', {}).get('unresolved', [])
print('GUARDED CITY SOURCE CONTEXT PASS', flush=True)
