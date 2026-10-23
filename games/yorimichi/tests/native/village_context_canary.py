"""Normal guarded immutable Village source/context capture; no native receiver or cold world."""
import argparse
import json
import os
from pathlib import Path

from atelier import engine
from atelier.export_manifest import real_directory
from atelier.harness.safety import guarded

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--donor', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
root = real_directory(args.output.absolute())
if os.path.lexists(root): raise ValueError('Fresh Village source context evidence required')
fixture = Path(__file__).resolve().parents[1] / 'fixtures/village_atomic_context.py'
command = [engine.blender(), '-b', '--factory-startup', '--threads', '3', '--python-exit-code', '1',
           '--python', str(fixture), '--', '--donor', str(args.donor.absolute()), '--output', str(root / 'products')]
code = guarded.run(command, root / 'guard', timeout=600, kind='job', purpose='immutable Village constructor and RNG census',
                   env=dict(os.environ, PYTHONHASHSEED='0'))
if code: raise SystemExit(code)
assert 'VILLAGE ORIGINAL CONTEXT COMPLETE' in (root / 'guard/stdout.log').read_text()
result = json.loads((root / 'products/result.json').read_text())
receipt = json.loads((root / 'guard/memory-health-tree.json').read_text())
assert result['complete'] and len(result['census']) == 12
assert receipt['state'] == 'child_exited' and receipt['cleanup_complete'] and not receipt['processes']
assert not receipt.get('late_reporters', {}).get('unresolved', [])
print('GUARDED ORIGINAL VILLAGE CONTEXT PASS', flush=True)
