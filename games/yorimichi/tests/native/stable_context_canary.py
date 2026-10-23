"""Guarded immutable Stable source census; production ENABLED stays false."""
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
if os.path.lexists(root): raise ValueError('Fresh Stable original-source evidence required')
fixture = Path(__file__).resolve().parents[1] / 'fixtures/stable_atomic_context.py'
command = [engine.blender(), '-b', '--factory-startup', '--threads', '3', '--python-exit-code', '1',
           '--python', str(fixture), '--', '--output', str(root / 'products')]
code = guarded.run(command, root / 'guard', timeout=600, kind='job', purpose='immutable disabled-owner Stable constructor census',
                   env=dict(os.environ, PYTHONHASHSEED='0'))
if code: raise SystemExit(code)
assert 'STABLE ORIGINAL CONTEXT COMPLETE' in (root / 'guard/stdout.log').read_text()
result = json.loads((root / 'products/result.json').read_text())
receipt = json.loads((root / 'guard/memory-health-tree.json').read_text())
assert result['complete'] and result['source_policy_enabled'] is False
assert receipt['state'] == 'child_exited' and receipt['cleanup_complete'] and not receipt['processes']
assert not receipt.get('late_reporters', {}).get('unresolved', [])
print('GUARDED ORIGINAL STABLE CONTEXT PASS', flush=True)
