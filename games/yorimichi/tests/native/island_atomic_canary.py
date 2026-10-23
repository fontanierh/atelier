"""Normally guarded actual-source island split equivalence; no donor mutation or native compile."""
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
parser.add_argument('--assets', nargs='+')
args = parser.parse_args()
root = real_directory(args.output.absolute())
if os.path.lexists(root): raise ValueError('Fresh canary evidence root required')
fixture = Path(__file__).resolve().parents[1] / 'fixtures/island_atomic_equivalence.py'
command = [engine.blender(), '-b', '--factory-startup', '--threads', '3', '--python-exit-code', '1',
           '--python', str(fixture), '--', '--donor', str(args.donor.absolute()), '--output', str(root / 'products'),
           *(['--assets', *args.assets] if args.assets else [])]
code = guarded.run(command, root / 'guard', timeout=1200, kind='job',
                   purpose='actual island predecessor and bounded atomic export conservation',
                   env=dict(os.environ, PYTHONHASHSEED='0'))
if code: raise SystemExit(code)
assert 'ISLAND ATOMIC EQUIVALENCE COMPLETE' in (root / 'guard/stdout.log').read_text()
result = json.loads((root / 'products/result.json').read_text())
guard = json.loads((root / 'guard/memory-health-tree.json').read_text())
assert result['complete'] and result['exact_source_channels'] and result['exact_piece_channel_union']
assert result['numeric_exported_polygon_union']
assert guard['state'] == 'child_exited' and guard['cleanup_complete'] and not guard['processes']
assert not guard.get('late_reporters', {}).get('unresolved', [])
print('GUARDED ACTUAL ISLAND ATOMIC EXPORT PASS', flush=True)
