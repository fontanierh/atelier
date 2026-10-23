"""Freeze original Git sources on the host before bounded independent vehicle proof."""
import argparse
import hashlib
import importlib.util
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
    parser=argparse.ArgumentParser();parser.add_argument('--family',choices=('sailboat','kei','kart'),required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=real_directory(args.output.absolute())
    if os.path.lexists(root):raise ValueError('Fresh vehicle proof root required')
    def git(*args):return subprocess.check_output(['git',*args],cwd=REPO)
    if git('status','--porcelain'):raise ValueError('Freeze source before vehicle proof')
    head=git('rev-parse','HEAD').decode().strip();root.mkdir();archive=root/'archive';archive.mkdir()
    original=archive/'build.py'
    original.write_bytes(git('show',BASELINE+':games/yorimichi/assets/vehicles/'+args.family+'/build.py'))
    kernel=archive/'village_mesh.py';kernel.write_bytes(git('show',BASELINE+':games/yorimichi/world/regions/village/mesh.py'))
    if (GAME/'world/regions/village/mesh.py').read_bytes()!=kernel.read_bytes():raise ValueError('Original primitive kernel changed')
    module_spec=importlib.util.spec_from_file_location('host_vehicle_source_projection',GAME/'world/vehicle_sources.py')
    source_module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(source_module)
    layout=root/'cockpit.json' if args.family=='kart' else None
    sources=root/'sources';source_module.publish(args.family,sources,layout_output=layout)
    fixture=Path(__file__).with_name('vehicle_atomic_equivalence.py')
    observer=GAME/'tests/fixtures/village_atomic_context.py'
    files=set(local_imports(GAME/'world/plan_vehicle_part.py',(GAME/'world',paths.STUDIO)))
    files.update(local_imports(GAME/'world/export_region_piece.py',(GAME/'world',paths.STUDIO)))
    files.update(local_imports(GAME/'vehicle_atomic_build.py',(GAME,GAME/'world',paths.STUDIO)))
    files.update(local_imports(GAME/'world/regions/village/mesh.py',(GAME/'world',)))
    files.update((Path(__file__),fixture,observer,GAME/'vehicle_atomic_build.py',GAME/'region_exports.py',
        GAME/'tools/atomic_equivalence.py',GAME/'tests/native/fbx_corners.py',original,kernel,*sources.iterdir(),
        GAME/'assets/vehicles'/args.family/'build.py'))
    if args.family=='kart':
        for name in ('cockpit.py','cockpit.json'):
            (archive/name).write_bytes(git('show',BASELINE+':games/yorimichi/assets/vehicles/kart/'+name))
            files.update((archive/name,GAME/'assets/vehicles/kart'/name))
        files.add(layout)
    def identities():
        result={}
        for path in sorted(files):
            real_directory(path.parent)
            if path.is_symlink() or not path.is_file():raise ValueError('Nonregular vehicle proof input')
            result[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        return result
    before=identities();spec=root/'spec.json'
    edit={'sailboat':('SB_Boom','-2.22','-2.24'),
          'kei':('SM_Kei_Pickup','(0.56, 0.46, 0.36)','(0.58, 0.46, 0.36)'),
          'kart':('SM_Kart_Seat','(0.4, 0.39, 0.045)','(0.4, 0.39, 0.05)')}[args.family]
    atomic_json(spec,dict(family=args.family,output=str(root/'products'),original=str(original),kernel=str(kernel),edit=edit,
        layout=str(layout) if layout else None,hull_observer=str(observer),
        sources={key:str(sources/(key+'.json')) for key in source_module.FAMILIES[args.family]['builders']},inputs=before))
    ctx=build.Context('yorimichi');command=build.Blender(fixture,('--spec',str(spec),'--sha256',hashlib.sha256(spec.read_bytes()).hexdigest()),threads=3,factory_startup=True)
    code=guarded.run(command.argv(ctx),root/'guard',timeout=180,kind='job',purpose=args.family+' complete original independent source and FBX equivalence',env=ctx.env(),progress=15.,track_tree=True)
    atomic_json(root/'whole-result.json',dict(exit_code=code,source_head=head,baseline=BASELINE))
    if code:raise SystemExit(code)
    assert identities()==before and git('rev-parse','HEAD').decode().strip()==head and not git('status','--porcelain')
    guard=json.loads((root/'guard/memory-health-tree.json').read_text())
    assert guard['state']=='child_exited' and guard['cleanup_complete'] and not guard['processes'] and not guard.get('late_reporters',{}).get('unresolved')
    assert 'VEHICLE ATOMIC ORIGINAL EQUIVALENCE COMPLETE' in (root/'guard/stdout.log').read_text()
    atomic_json(root/'host-result.json',dict(complete=True,source_head=head,baseline=BASELINE,whole_exit=0,guard_empty=True))
    print('VEHICLE WHOLE SOURCE/FBX PROOF PASS',flush=True)


if __name__=='__main__':main()
