"""Normal guarded finite GLB material proof with all Git work in outer host preflight."""
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
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
root = real_directory(args.output.absolute())
if os.path.lexists(root): raise ValueError('Fresh material proof root required')
checkout = Path(__file__).resolve().parents[4]
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip()
source = checkout / 'games/yorimichi/tests/fixtures/stable-predecessor-283329c07.txt'
original = subprocess.check_output(['git', 'show', '283329c07:games/yorimichi/world/regions/hidamari_stable/build.py'], cwd=checkout)
if source.read_bytes() != original: raise ValueError('Original material source snapshot differs from immutable Git')
counter = subprocess.check_output(['git', 'show', 'f72c3bb75588d75b16c777554e49e4a1f69be7d2:games/yorimichi/tools/atomic_equivalence.py'], cwd=checkout)
root.mkdir(); frozen = root / 'independent-counter.py'; frozen.write_bytes(counter)
fixture = Path(__file__).resolve().parents[1] / 'fixtures/vertex_material_glb_canary.py'
command = [engine.blender(), '-b', '--factory-startup', '--threads', '3', '--python-exit-code', '1',
    '--python', str(fixture), '--', '--output', str(root / 'products'), '--counter', str(frozen),
    '--counter-sha', hashlib.sha256(counter).hexdigest(), '--source-sha', hashlib.sha256(original).hexdigest()]
code = guarded.run(command, root / 'guard', timeout=180, kind='job', purpose='finite source material exact GLB conservation',
                   env=dict(os.environ, PYTHONHASHSEED='0'))
atomic_json(root / 'whole-result.json', dict(exit_code=code, source_head=head))
if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip() != head:
    raise ValueError('Material proof source changed')
if code: raise SystemExit(code)
assert 'FINITE MATERIAL EXACT GLB EQUIVALENCE COMPLETE' in (root / 'guard/stdout.log').read_text()
receipt = json.loads((root / 'guard/memory-health-tree.json').read_text())
assert receipt['state'] == 'child_exited' and receipt['cleanup_complete'] and not receipt['processes']
assert not receipt.get('late_reporters', {}).get('unresolved', [])
print('GUARDED FINITE MATERIAL GLB PROOF PASS', flush=True)
