"""Bounded normal guard for all coastal prototype source-query products."""
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
if os.path.lexists(root): raise ValueError('Prototype query canary requires fresh evidence')
repo = Path(__file__).resolve().parents[4]
def source():
    if subprocess.check_output(['git','status','--porcelain'], cwd=repo, text=True):
        raise ValueError('Prototype query canary requires clean committed source')
    return subprocess.check_output(['git','rev-parse','HEAD'], cwd=repo, text=True).strip()
head = source()
fixture = Path(__file__).resolve().parents[1]/'fixtures/brinecove_plant_queries.py'
code = guarded.run([engine.blender(),'-b','--factory-startup','--threads','3','--python-exit-code','1',
    '--python',str(fixture),'--','--output',str(root/'products')],root/'guard',timeout=300,kind='job',
    purpose='all coastal prototype query and unchanged atomic GLB conservation',env=dict(os.environ,PYTHONHASHSEED='0'))
if code: raise SystemExit(code)
assert head == source()
assert 'COASTAL PROTOTYPE QUERY CANARY COMPLETE' in (root/'guard/stdout.log').read_text()
result = json.loads((root/'products/result.json').read_text())
assert result['complete'] and len(result['prototypes'])==36
assert result['exact_query_triangle_cycles'] and result['unchanged_glb_bytes']
receipt = json.loads((root/'guard/memory-health-tree.json').read_text())
assert receipt['state']=='child_exited' and receipt['cleanup_complete'] and not receipt['processes']
assert not receipt.get('late_reporters',{}).get('unresolved')
print('GUARDED COASTAL PROTOTYPE QUERIES PASS',head,flush=True)
