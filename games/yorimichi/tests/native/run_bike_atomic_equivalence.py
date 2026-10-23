"""Host-bound semantic Bike proof using frozen independently executed original artifacts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from atelier import build,paths
from atelier.atomic_files import atomic_json
from atelier.build_inputs import local_imports
from atelier.export_manifest import real_directory
from atelier.harness.safety import guarded

GAME=Path(__file__).resolve().parents[2];REPO=GAME.parents[1]
BASELINE='283329c07ea04bee34587022a3d43827468c66d7'
sys.path.insert(0,str(GAME/'world'))
import vehicle_sources  # noqa: E402


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--baseline',type=Path,required=True);args=parser.parse_args()
    root=real_directory(args.output.absolute());baseline=args.baseline.resolve()
    if os.path.lexists(root):raise ValueError('Fresh Bike proof root required')
    def git(*args):return subprocess.check_output(['git',*args],cwd=REPO)
    if git('status','--porcelain'):raise ValueError('Freeze Bike source before proof')
    head=git('rev-parse','HEAD').decode().strip()
    old_source=baseline.parent/'original.py';assert old_source.read_bytes()==git('show',BASELINE+':games/yorimichi/assets/vehicles/bike/build.py')
    prior=json.loads((baseline.parent/'whole-result.json').read_text());assert prior['exit_code']==0 and prior['baseline']==BASELINE
    prior_guard=json.loads((baseline.parent/'guard/memory-health-tree.json').read_text())
    assert prior_guard['cleanup_complete'] and not prior_guard['processes'] and prior_guard['state']=='child_exited'
    root.mkdir();layout_source=root/'layout-source.json'
    vehicle_sources.publish('bike',root/'sources',layout_output=layout_source)
    fixture=Path(__file__).with_name('bike_atomic_equivalence.py')
    files=set(local_imports(fixture,(GAME/'world',GAME/'tools',paths.STUDIO)))
    files.update(local_imports(GAME/'vehicle_atomic_build.py',(GAME, GAME/'world',paths.STUDIO)))
    files.update(local_imports(GAME/'world/vehicle_sources.py',(GAME/'world',paths.STUDIO)))
    files.update((Path(__file__),fixture,old_source,baseline/'result.json',baseline/'data/bike/manifest.json',layout_source,GAME/'assets/vehicles/bike/build.py'))
    sources={path.stem:str(path) for path in (root/'sources').glob('*.json')};files.update(Path(path) for path in sources.values())
    census=json.loads((baseline/'result.json').read_text())
    for key,value in census['assets'].items():
        files.add(baseline/'data/bike/assets'/(key+'.fbx'))
        files.update(baseline/'baseline'/key/row['path'] for row in value['packets'])
    def identities():return {str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files)}
    before=identities();spec=root/'spec.json';atomic_json(spec,dict(output=str(root/'products'),baseline=str(baseline),sources=sources,layout_source=str(layout_source),inputs=before))
    ctx=build.Context('yorimichi');command=build.Blender(fixture,('--spec',str(spec),'--sha256',hashlib.sha256(spec.read_bytes()).hexdigest()),threads=3,factory_startup=True)
    code=guarded.run(command.argv(ctx),root/'guard',timeout=300,kind='job',purpose='strict original Bike semantic source and serialized FBX union',env=ctx.env(),progress=15.,track_tree=True)
    atomic_json(root/'whole-result.json',dict(exit_code=code,source_head=head,baseline=BASELINE))
    if code:raise SystemExit(code)
    assert identities()==before and git('rev-parse','HEAD').decode().strip()==head and not git('status','--porcelain')
    guard=json.loads((root/'guard/memory-health-tree.json').read_text())
    assert guard['state']=='child_exited' and guard['cleanup_complete'] and not guard['processes'] and not guard.get('late_reporters',{}).get('unresolved')
    assert 'BIKE ATOMIC ORIGINAL EQUIVALENCE COMPLETE' in (root/'guard/stdout.log').read_text()
    print('BIKE ATOMIC GUARDED ORIGINAL EQUIVALENCE PASS',flush=True)


if __name__=='__main__':main()
