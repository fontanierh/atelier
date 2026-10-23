"""Guarded current Stable source/GLB conservation with immutable authority outside Blender."""
import argparse
import hashlib
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
parser.add_argument('--roof', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
root = real_directory(args.output.absolute())
if os.path.lexists(root): raise ValueError('Fresh Stable current evidence required')
checkout = Path(__file__).resolve().parents[4]
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip()
source = checkout / 'games/yorimichi/tests/fixtures/stable-predecessor-283329c07.txt'
if source.read_bytes() != subprocess.check_output(['git', 'show', '283329c07:games/yorimichi/world/regions/hidamari_stable/build.py'], cwd=checkout):
    raise ValueError('Original Stable source snapshot differs from immutable Git')
counter = subprocess.check_output(['git', 'show', 'f72c3bb75588d75b16c777554e49e4a1f69be7d2:games/yorimichi/tools/atomic_equivalence.py'], cwd=checkout)
root.mkdir(); frozen = root / 'independent-counter.py'; frozen.write_bytes(counter)
fixture = Path(__file__).resolve().parents[1] / 'fixtures/stable_atomic_equivalence.py'
command = [engine.blender(), '-b', '--factory-startup', '--threads', '3', '--python-exit-code', '1', '--python', str(fixture), '--',
    '--baseline', str(args.baseline.absolute()), '--roof', str(args.roof.absolute()), '--output', str(root / 'products'),
    '--counter', str(frozen), '--counter-sha', hashlib.sha256(counter).hexdigest()]
code = guarded.run(command, root / 'guard', timeout=600, kind='job', purpose='complete selected Stable original source and GLB equivalence',
                   env=dict(os.environ, PYTHONHASHSEED='0'))
atomic_json(root / 'whole-result.json', dict(exit_code=code, source_head=head))
if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip() != head:
    raise ValueError('Stable current source changed while executing')
if code: raise SystemExit(code)
assert 'STABLE ATOMIC EQUIVALENCE COMPLETE' in (root / 'guard/stdout.log').read_text()
result = json.loads((root / 'products/result.json').read_text())
receipt = json.loads((root / 'guard/memory-health-tree.json').read_text())
assert result['complete'] and len(result['sources']) == 24 and result['numeric_glb_corner_material_union']
assert receipt['state'] == 'child_exited' and receipt['cleanup_complete'] and not receipt['processes']
assert not receipt.get('late_reporters', {}).get('unresolved', [])
print('GUARDED COMPLETE STABLE ATOMIC EXPORT PASS', flush=True)
