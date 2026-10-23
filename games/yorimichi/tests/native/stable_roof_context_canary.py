"""Normal guarded immutable Barn roof-state observer, not a world or engine build."""
import argparse
import json
import os
from pathlib import Path
import subprocess

from atelier import engine
from atelier.atomic_files import atomic_json
from atelier.export_manifest import real_directory
from atelier.harness.safety import guarded

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
root = real_directory(args.output.absolute())
if os.path.lexists(root): raise ValueError('Fresh Barn roof witness required')
checkout = Path(__file__).resolve().parents[4]
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip()
fixture = Path(__file__).resolve().parents[1] / 'fixtures/stable_roof_context.py'
command = [engine.blender(), '-b', '--factory-startup', '--threads', '3', '--python-exit-code', '1',
           '--python', str(fixture), '--', '--baseline', str(args.baseline.absolute()), '--output', str(root / 'products')]
code = guarded.run(command, root / 'guard', timeout=300, kind='job', purpose='immutable original Stable Barn roof context',
                   env=dict(os.environ, PYTHONHASHSEED='0'))
atomic_json(root / 'whole-result.json', dict(exit_code=code, source_head=head))
if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip() != head:
    raise ValueError('Roof witness source head changed')
if code: raise SystemExit(code)
assert 'STABLE IMMUTABLE ROOF CONTEXT COMPLETE' in (root / 'guard/stdout.log').read_text()
receipt = json.loads((root / 'guard/memory-health-tree.json').read_text())
assert receipt['state'] == 'child_exited' and receipt['cleanup_complete'] and not receipt['processes']
assert not receipt.get('late_reporters', {}).get('unresolved', [])
print('GUARDED ORIGINAL STABLE ROOF CONTEXT PASS', flush=True)
