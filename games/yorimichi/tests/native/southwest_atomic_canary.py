"""Guarded actual immutable-source/corner/export conservation for all sixteen Southwest owners."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from atelier import engine
from atelier.export_manifest import real_directory
from atelier.harness.safety import guarded

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
args = parser.parse_args()
root = real_directory(args.output.absolute())
if root.exists(): raise ValueError('Southwest canary requires a fresh root')
repo = Path(__file__).resolve().parents[4]
legacy = root/'immutable-original';legacy.mkdir(parents=True)
source = 'games/yorimichi/world/regions/southwest/'
revision = '283329c07'
bindings = {}
for name in ('build.py','mesh.py','stand.py','fishing.py','temple.py','island.py'):
    payload = subprocess.run(['git','show',revision+':'+source+name],cwd=repo,check=True,capture_output=True,timeout=10).stdout
    (legacy/name).write_bytes(payload);bindings[name] = hashlib.sha256(payload).hexdigest()
# Fishing's imported construction helpers are part of the original complete source closure.
village = 'games/yorimichi/world/regions/village/mesh.py'
expected = subprocess.run(['git','show',revision+':'+village],cwd=repo,check=True,capture_output=True,timeout=10).stdout
assert (repo/village).read_bytes() == expected, 'Original village helper changed; conservation needs its exact immutable closure'
(root/'original-sources.json').write_text(json.dumps(dict(revision=revision,files=bindings),indent=2)+'\n')
fixture = Path(__file__).resolve().parents[1]/'fixtures/southwest_atomic_context.py'
command = [engine.blender(),'-b','--factory-startup','--threads','3','--python-exit-code','1','--python',str(fixture),
    '--','--legacy',str(legacy),'--output',str(root/'products')]
code = guarded.run(command,root/'guard',timeout=300,kind='job',
    purpose='Southwest immutable sixteen-owner exact geometry/query/serialized export conservation',
    env=dict(os.environ,PYTHONHASHSEED='0'))
if code: raise SystemExit(code)
assert 'SOUTHWEST ATOMIC CONSERVATION COMPLETE' in (root/'guard/stdout.log').read_text()
result = json.loads((root/'products/result.json').read_text())
receipt = json.loads((root/'guard/memory-health-tree.json').read_text())
assert result['complete'] and len(result['assets']) == 16 and result['actual_fbx_corner_conservation']
assert receipt['state'] == 'child_exited' and receipt['cleanup_complete'] and not receipt['processes']
assert not receipt.get('late_reporters',{}).get('unresolved',[])
print('GUARDED SIXTEEN-OWNER SOUTHWEST SOURCE CONSERVATION PASS',flush=True)
