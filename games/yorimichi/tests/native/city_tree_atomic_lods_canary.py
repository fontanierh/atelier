"""Bounded normal guard for actual per-piece city tree LOD conservation."""
import argparse
import json
import os
from pathlib import Path
import subprocess

from atelier import engine
from atelier.export_manifest import real_directory
from atelier.harness.safety import guarded

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
root = real_directory(args.output.absolute())
if os.path.lexists(root): raise ValueError('Tree LOD canary requires fresh evidence')
repo = Path(__file__).resolve().parents[4]
def source():
    status = subprocess.check_output(['git','status','--porcelain'], cwd=repo, text=True)
    if status: raise ValueError('Tree LOD canary requires committed clean source')
    return subprocess.check_output(['git','rev-parse','HEAD'], cwd=repo, text=True).strip()
head = source()
fixture = Path(__file__).resolve().parents[1]/'fixtures/city_tree_atomic_lods.py'
code = guarded.run([engine.blender(),'-b','--factory-startup','--threads','3','--python-exit-code','1',
    '--python',str(fixture),'--','--output',str(root/'products')],root/'guard',timeout=300,kind='job',
    purpose='actual per-piece city tree LOD geometry and atomic export conservation',env=dict(os.environ,PYTHONHASHSEED='0'))
if code: raise SystemExit(code)
assert head == source()
assert 'ATOMIC CITY TREE LOD CANARY COMPLETE' in (root/'guard/stdout.log').read_text()
result = json.loads((root/'products/result.json').read_text())
assert result['complete'] and result['exact_exported_corners'] and result['exact_base_payloads'] and result['exact_base_face_membership']
receipt = json.loads((root/'guard/memory-health-tree.json').read_text())
assert receipt['state']=='child_exited' and receipt['cleanup_complete'] and not receipt['processes']
assert not receipt.get('late_reporters',{}).get('unresolved')
print('GUARDED CITY TREE ATOMIC LODS PASS',head,flush=True)
