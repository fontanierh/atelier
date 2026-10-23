"""Host-bound original Bike source census with no Git subprocess inside Blender."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from atelier import build,paths
from atelier.atomic_files import atomic_json
from atelier.build_inputs import local_imports
from atelier.export_manifest import real_directory
from atelier.harness.safety import guarded

GAME=Path(__file__).resolve().parents[2];REPO=GAME.parents[1]
BASELINE='283329c07ea04bee34587022a3d43827468c66d7'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    root=real_directory(args.output.absolute())
    if os.path.lexists(root):raise ValueError('Fresh Bike census root required')
    def git(*args):return subprocess.check_output(['git',*args],cwd=REPO)
    if git('status','--porcelain'):raise ValueError('Freeze Bike census source')
    head=git('rev-parse','HEAD').decode().strip();root.mkdir()
    original=root/'original.py';original.write_bytes(git('show',BASELINE+':games/yorimichi/assets/vehicles/bike/build.py'))
    fixture=Path(__file__).with_name('bike_original_census.py')
    files=set(local_imports(GAME/'assets/vehicles/bike/build.py',(GAME/'world',paths.STUDIO)))
    files.update(local_imports(fixture,(GAME/'world',GAME/'tools',GAME/'tests/fixtures',paths.STUDIO)))
    files.update((Path(__file__),fixture,original,GAME/'tools/atomic_equivalence.py',GAME/'tests/fixtures/source_packets.py'))
    def identities():return {str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files)}
    before=identities();spec=root/'spec.json';atomic_json(spec,dict(output=str(root/'products'),original=str(original),inputs=before))
    ctx=build.Context('yorimichi');command=build.Blender(fixture,('--spec',str(spec),'--sha256',hashlib.sha256(spec.read_bytes()).hexdigest()),threads=3,factory_startup=True)
    code=guarded.run(command.argv(ctx),root/'guard',timeout=300,kind='job',purpose='actual original Bike export and steering semantic census',env=ctx.env(),progress=15.,track_tree=True)
    atomic_json(root/'whole-result.json',dict(exit_code=code,source_head=head,baseline=BASELINE))
    if code:raise SystemExit(code)
    assert identities()==before and git('rev-parse','HEAD').decode().strip()==head and not git('status','--porcelain')
    guard=json.loads((root/'guard/memory-health-tree.json').read_text())
    assert guard['state']=='child_exited' and guard['cleanup_complete'] and not guard['processes'] and not guard.get('late_reporters',{}).get('unresolved')
    assert 'BIKE ORIGINAL CENSUS COMPLETE' in (root/'guard/stdout.log').read_text()
    print('BIKE ORIGINAL GUARDED CENSUS PASS',flush=True)


if __name__=='__main__':main()
