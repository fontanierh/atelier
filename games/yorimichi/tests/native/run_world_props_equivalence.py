"""Host-bound immutable prop proof; all Git work stays outside the guarded native child."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

from atelier import build,paths
from atelier.atomic_files import atomic_json
from atelier.build_cache import copy_file
from atelier.build_inputs import local_imports
from atelier.export_manifest import real_directory
from atelier.harness.safety import guarded

GAME=Path(__file__).resolve().parents[2]
REPO=GAME.parents[1]
BASELINE='283329c07ea04bee34587022a3d43827468c66d7'


def git(*args,cwd=REPO):return subprocess.check_output(['git',*args],cwd=cwd,text=True).strip()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identities(paths):
    result={}
    for path in sorted(set(paths)):
        real_directory(path.parent);stat=path.stat()
        if path.is_symlink() or not path.is_file():raise ValueError('Proof inputs must be regular files')
        result[str(path)]=dict(sha256=sha(path),stat=[stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns])
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--donor',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=real_directory(args.output.absolute())
    if root.exists():raise ValueError('Fresh exclusive proof output required')
    if git('status','--porcelain'):raise ValueError('Freeze the proof checkout before native work')
    head=git('rev-parse','HEAD');donor=args.donor.resolve();donor_head=git('rev-parse','HEAD',cwd=donor)
    root.mkdir();archive=root/'archive';archive.mkdir();sources=root/'sources';sources.mkdir()
    for name in ('build_assets.py','asset_mesh.py','material_specs.py'):
        raw=subprocess.check_output(['git','show',BASELINE+':games/yorimichi/world/'+name],cwd=REPO)
        (archive/name).write_bytes(raw)
        if (GAME/'world'/name).read_bytes()!=raw:raise ValueError('Original prop primitive closure differs: '+name)
    module_spec=importlib.util.spec_from_file_location('host_prop_source_projection',GAME/'world/prop_sources.py')
    module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(module)
    module.publish(sources)
    textures=root/'textures';textures.mkdir()
    donor_paths=[]
    for name in sorted({row['texture'] for row in module.MATERIALS.values() if row.get('texture')}):
        path=donor/'build/yorimichi/textures'/name;donor_paths.append(path)
        copy_file(path,textures/name)
        if sha(path)!=sha(textures/name):raise ValueError('Texture independent copy differs')
    fixture=Path(__file__).with_name('world_props_equivalence.py')
    roots=(GAME/'world',paths.STUDIO)
    code=set(local_imports(GAME/'world/plan_world_prop.py',roots))
    code.update(local_imports(GAME/'world/export_region_piece.py',roots))
    code.update((Path(__file__),fixture,GAME/'tools/atomic_equivalence.py',GAME/'world/prop_sources.py',
                 GAME/'tests/fixtures/world-props-predecessor-283329c07.txt',GAME/'tests/native/fbx_corners.py'))
    from atelier import mesh_ir,mesh_collision
    code.update((Path(mesh_ir.__file__),Path(mesh_collision.__file__)))
    input_files=[*code,*donor_paths,*archive.iterdir(),*sources.iterdir(),*textures.iterdir()]
    before=identities(input_files)
    spec=root/'spec.json';atomic_json(spec,dict(output=str(root/'products'),original=str(archive/'build_assets.py'),
        textures=str(textures),sources={key:str(sources/(key+'.json')) for key in module.BUILDERS},inputs=before))
    ctx=build.Context('yorimichi')
    command=build.Blender(fixture,('--spec',str(spec),'--sha256',sha(spec)),threads=3,factory_startup=True)
    print('World prop proof: frozen source and16 texture copies; submitting bounded original/selected comparison',flush=True)
    code=guarded.run(command.argv(ctx),root/'guard',timeout=180,kind='job',
        purpose='PR575 fourteen original props full source and actual FBX conservation',env=ctx.env(),progress=15.,track_tree=True)
    atomic_json(root/'whole-result.json',dict(exit_code=code))
    if code:raise SystemExit(code)
    terminal=json.loads((root/'guard/memory-health-tree.json').read_text())
    assert terminal['state']=='child_exited' and terminal['cleanup_complete'] and terminal['processes']==[]
    assert not terminal.get('late_reporters',{}).get('unresolved')
    assert 'WORLD PROPS ORIGINAL EQUIVALENCE COMPLETE' in (root/'guard/stdout.log').read_text()
    assert identities(input_files)==before and git('rev-parse','HEAD')==head and not git('status','--porcelain')
    assert git('rev-parse','HEAD',cwd=donor)==donor_head
    result=json.loads((root/'products/result.json').read_text());assert result['complete'] and len(result['assets'])==14
    atomic_json(root/'host-result.json',dict(complete=True,source_head=head,donor_head=donor_head,
        baseline=BASELINE,whole_exit=0,guard_empty=True,result_sha256=sha(root/'products/result.json')))
    print('WORLD PROPS WHOLE SOURCE/FBX PROOF PASS',flush=True)


if __name__=='__main__':main()
