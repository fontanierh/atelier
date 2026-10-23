"""Host-only immutable Village native fixture preparation; never launch or mutate Unreal."""
import argparse
import ast
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from atelier import mesh_ir
from atelier.atomic_files import atomic_json
from atelier.build_cache import copy_file
from atelier.build_inputs import local_imports
from atelier.export_manifest import real_directory
from atelier.model_files import regular_files

GAME=Path(__file__).resolve().parents[2];REPO=GAME.parents[1]
sys.path[:0]=[str(GAME),str(GAME/'world'),str(GAME/'world/regions')]
from village.catalogue import ASSETS  # noqa: E402


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identities(paths):
    result={}
    for path in sorted(set(map(Path,paths))):
        real_directory(path.parent)
        if path.is_symlink() or not path.is_file():raise ValueError('Missing or linked explicit native fixture input')
        st=path.stat();result[str(path.absolute())]=dict(sha256=sha(path),stat=[st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns])
    return result


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def stopped(root):
    row=json.loads((root/'guard/memory-health-tree.json').read_text())
    if (row.get('state')!='child_exited' or row.get('cleanup_complete') is not True or row.get('processes')!=[]
            or row.get('late_reporters',{}).get('unresolved') or row.get('late_reporters',{}).get('scan_failed')):
        raise ValueError('Original/atomic producer guard is not positively empty')


def original_finishing(data):
    """Retain the exact original full asset loop; only its outer fixture invocation changes."""
    tree=ast.parse(data)
    main=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='main')
    loops=[node for node in main.body if isinstance(node,ast.For) and ast.unparse(node.target)=='(name, entry)']
    if len(loops)!=1:raise ValueError('Unknown immutable original Village finishing loop')
    fn=ast.FunctionDef(name='finish_original',args=ast.arguments(posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[]),
        body=[loops[0]],decorator_list=[])
    module=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]))
    return ast.unparse(module)+'\n'


def legacy_bounds(root,packets):
    """Whole immutable source bounds include every original packet and its authored frame."""
    import numpy as np
    lows=[];highs=[];triangles=0
    if not packets:raise ValueError('Missing complete original source packet inventory')
    for row in packets:
        meta,piece=mesh_ir.decode((root/row['path']).read_bytes())
        matrix=np.asarray(meta['matrix']);positions=piece['positions']@matrix[:3,:3].T+matrix[:3,3]
        lows.append(positions.min(0));highs.append(positions.max(0));triangles+=piece['triangles']
    return dict(min=np.min(lows,axis=0).tolist(),max=np.max(highs,axis=0).tolist(),triangles=triangles)


def probe_geometry(out,groups):
    import numpy as np
    from atelier.conventions import to_unreal
    result={}
    for parent,group in groups.items():
        pieces={};edges={};bounds=[]
        for row in group['pieces']:
            folder=out/'planned_exports/village'/parent
            meta,data=mesh_ir.decode((folder/(row['name']+'.npz')).read_bytes())
            matrix=np.asarray(meta['matrix']);world=data['positions']@matrix[:3,:3].T+matrix[:3,3]
            positions=np.asarray([to_unreal(point) for point in world]);bounds.extend(positions.tolist());candidates=[]
            for face in data['faces']:
                points=positions[face];normal=np.cross(points[1]-points[0],points[2]-points[0]);length=float(np.linalg.norm(normal))
                if length<1e-8:continue
                normal/=length;centroid=points.mean(0)
                candidate=dict(point=centroid.tolist(),normal=normal.tolist())
                candidates.append((length,candidate))
                for a,b in zip(face,face[1:]+face[:1]):
                    key=tuple(sorted((tuple(positions[a].astype('<f4')),tuple(positions[b].astype('<f4')))))
                    if key[0]==key[1]:continue
                    midpoint=(positions[a]+positions[b])*.5
                    near=dict(point=(midpoint*.99+centroid*.01).tolist(),normal=normal.tolist())
                    edges.setdefault(key,{}).setdefault(row['name'],near)
            if not candidates:raise ValueError('Native positive probes require actual positive source triangles')
            pieces[row['name']]=[value for _,value in sorted(candidates,key=lambda value:-value[0])[:64]]
        seams={}
        for owners in edges.values():
            for a in sorted(owners):
                for b in sorted(owners):
                    if a>=b:continue
                    points=seams.setdefault((a,b),{a:[],b:[]})
                    if len(points[a])<16:
                        points[a].append(owners[a]);points[b].append(owners[b])
        result[parent]=dict(pieces=pieces,seams=[dict(a=a,b=b,points=points) for (a,b),points in sorted(seams.items())],
            negative=(np.max(bounds,axis=0)+10000).tolist())
    return result


def prepare(original,atomic,output,content,baseline,project,native_files):
    """@cc [owner:fontanierh,label:correctness] frozen-actual-village-native-inputs
    The complete twelve original and nineteen atomic members MUST come from independently
    stopped real producers. Bind their exact files, source closure and immutable original
    importer/finishing bytes before native execution. Normal production file assemblers MUST
    create complete current manifests; no fabricated success, omitted family or tiny substitute.
    Git authority MUST stay on this outer host, never inside the guarded native child.
    """
    if os.path.lexists(output):raise ValueError('Fresh native fixture workspace required')
    real_directory(output.parent);real_directory(content)
    if project.suffix!='.uproject' or project.parent/'Content'!=content or not native_files:
        raise ValueError('Explicit isolated native descriptor/modules are required')
    if not any(path.name=='UnrealEditor.modules' for path in native_files) or not any(path.suffix=='.dylib' for path in native_files):
        raise ValueError('Bound compiled module manifest and actual module binaries are required')
    native_before=identities([project,*native_files])
    if subprocess.check_output(['git','status','--porcelain'],cwd=REPO,text=True).strip():raise ValueError('Commit fixture source first')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    baseline=subprocess.check_output(['git','rev-parse',baseline],cwd=REPO,text=True).strip()
    stopped(original);stopped(atomic);old=original/'products';new=atomic/'products'
    before={old/'result.json',old/'baseline-signatures.json',old/'contexts.json',old/'data/world.json',old/'data/heightmap.npy',
        new/'result.json',original/'guard/memory-health-tree.json',atomic/'guard/memory-health-tree.json'}
    census=json.loads((old/'result.json').read_text());proof=json.loads((new/'result.json').read_text())
    if not census.get('complete') or not proof.get('complete') or set(census['census'])!=set(ASSETS) or set(proof['assets'])!=set(ASSETS):
        raise ValueError('Full actual original/atomic Village proof census required')
    baseline_packets=json.loads((old/'baseline-signatures.json').read_text())
    for parent in ASSETS:
        before.add(old/'data/village/assets'/(parent+'.fbx'));before.add(old/'original-hulls'/(parent+'.json'))
        before.update(old/'baseline'/parent/row['path'] for row in baseline_packets[parent]['packets'])
        plan=json.loads((new/'plans'/parent/'plan.json').read_text());before.add(new/'plans'/parent/'plan.json')
        for row in plan['pieces']:
            before.add(new/'plans'/parent/row['payload'])
            folder=new/'exports'/row['name'];before.update(folder/name for name in regular_files(folder))
    original_inputs=identities(before);output.mkdir();out=output/'out';archive=output/'original';archive.mkdir();out.mkdir()
    originals={}
    for name in ('import_village','mesh_import','atmosphere'):
        relative='games/yorimichi/unreal/Scripts/'+name+'.py'
        payload=subprocess.check_output(['git','show',baseline+':'+relative],cwd=REPO)
        target=archive/(name+'.py');target.write_bytes(payload);originals[relative]=sha(target)
    (archive/'finish.py').write_text(original_finishing((archive/'import_village.py').read_text()))
    from village.atomic_sources import publish,contexts
    import numpy as np
    publish(json.loads((old/'data/world.json').read_text()),np.load(old/'data/heightmap.npy',allow_pickle=False),out/'village-source-data',contexts())
    legacy={}
    for parent in ASSETS:
        source=new/'plans'/parent;target=out/'planned_exports/village'/parent;target.mkdir(parents=True)
        for name in regular_files(source):copy_file(source/name,target/name)
        plan=json.loads((target/'plan.json').read_text())
        for row in plan['pieces']:
            a=new/'exports'/row['name'];b=out/'exports/world.village.export'/row['name'];b.mkdir(parents=True)
            for name in regular_files(a):copy_file(a/name,b/name)
        primary=out/'village-original/assets'/(parent+'.fbx');primary.parent.mkdir(parents=True,exist_ok=True)
        copy_file(old/'data/village/assets'/(parent+'.fbx'),primary)
        bounds=legacy_bounds(old/'baseline'/parent,baseline_packets[parent]['packets'])
        if bounds['triangles']!=census['census'][parent]['source_triangles']:
            raise ValueError('Original source packet inventory omits whole geometry: '+parent)
        legacy[parent]=dict(collision_boxes=census['census'][parent]['collision_hulls'],max=bounds['max'])
    atomic_json(out/'village-original/manifest.json',legacy)
    recipe=load('native_fixture_village_recipe',GAME/'village_atomic_build.py');ctx=SimpleNamespace(out=out)
    step=next(step for step in recipe.steps(ctx) if step.name=='world.village.assembled');step.commands[0].fn(ctx,io.StringIO())
    products=load('native_fixture_village_products',GAME/'village_atomic_products.py');products.assemble(out);groups=products.read(out)
    if len(groups)!=12 or sum(len(row['pieces']) for row in groups.values())!=19:raise ValueError('Actual fixture requires all12→19')
    atomic_json(out/'native-probe-geometry.json',probe_geometry(out,groups))
    scripts=[Path(__file__),Path(__file__).with_name('village_native_equivalence.py'),GAME/'unreal/Scripts/import_village_atomic.py',
        GAME/'unreal/Scripts/atomic_equivalence_capture.py',GAME/'unreal/Scripts/mesh_import.py',GAME/'village_atomic_products.py',
        GAME/'tools/atomic_equivalence.py',GAME/'unreal/Source/Yorimichi/NativeAtomicEquivalence.cpp',
        GAME/'unreal/Source/Yorimichi/NativeAtomicEquivalence.h']
    closure=set(scripts)
    for script in scripts:
        if script.suffix=='.py':closure.update(local_imports(script,(GAME/'world',GAME/'world/regions',GAME,GAME/'unreal/Scripts',REPO/'platform/studio',REPO/'platform/harness')))
    frozen=[archive/name for name in regular_files(archive)]
    frozen.extend(out/name for name in regular_files(out))
    frozen.extend([project,*native_files])
    value=dict(schema=1,region='village-native',repo=str(REPO),source_head=head,baseline_revision=baseline,
        original_sources=originals,original_inputs=original_inputs,source_files=identities(closure),frozen_files=identities(frozen),
        out=str(out),archive=str(archive),content=str(content.absolute()),project=str(project),native_files=native_before,output=str(output/'native'),
        scope='full12 immutable original→19 actual saved assets; fixture component policy only')
    file=output/'spec.json';atomic_json(file,value)
    if identities(before)!=original_inputs or identities(native_before)!=native_before:
        raise ValueError('Independent producer/native evidence changed during fixture preparation')
    print('VILLAGE NATIVE FIXTURE READY '+str(file)+' '+sha(file),flush=True)
    return value


def finalize(spec_file,expected_sha,guard,whole_exit):
    """Independent host comparison after observed outer whole0 and positive guard cleanup."""
    if sha(spec_file)!=expected_sha or whole_exit!=0:raise ValueError('Exact successful whole invocation required')
    value=json.loads(spec_file.read_text());subject=Path(value['repo'])
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=subject,text=True).strip()!=value['source_head']:
        raise ValueError('Native harness source revision changed')
    if subprocess.check_output(['git','status','--porcelain'],cwd=subject,text=True).strip():raise ValueError('Native harness source became dirty')
    for relative,digest in value['original_sources'].items():
        payload=subprocess.check_output(['git','show',value['baseline_revision']+':'+relative],cwd=subject)
        if hashlib.sha256(payload).hexdigest()!=digest:raise ValueError('Original importer authority differs')
    for field in ('original_inputs','source_files','frozen_files'):
        if identities(value[field])!=value[field]:raise ValueError('Frozen native evidence inputs changed')
    sys.path.insert(0,str(GAME/'tools'))
    import atomic_equivalence as eq
    native=Path(value['output']);result_file=native/'result.json';result=json.loads(result_file.read_text())
    if (result.get('schema')!=1 or result.get('complete') is not True or result.get('spec_sha256')!=expected_sha
            or result.get('source_head')!=value['source_head'] or set(result.get('parents',{}))!=set(ASSETS)
            or result.get('current_count')!=19 or result.get('foreign_reference_refused') is not True
            or result.get('repeat_membership') is not True or len(result.get('physical_retirement',[]))!=13
            or len(result.get('fixture_assets_absent',[]))!=21):raise ValueError('Full native receiving/lifecycle evidence missing')
    whole=spec_file.parent/'whole-result.json';atomic_json(whole,dict(exit_code=whole_exit))
    def artifact(path):return dict(path=str(path.absolute()),sha256=sha(path))
    binding=dict(receipt=artifact(guard/'memory-health-tree.json'),stdout=artifact(guard/'stdout.log'),
        marker='VILLAGE NATIVE EQUIVALENCE CAPTURE COMPLETE',whole_result=artifact(whole))
    eq.guard_binding(binding);compared={}
    for parent,row in result['parents'].items():
        compared[parent]=eq.compare_native(dict(row,baseline_guard=binding,actual_guard=binding),parent)
    if not all(row['geometry_complete'] and row['runtime_policy_complete'] is False for row in compared.values()):
        raise ValueError('Incomplete native geometry comparison or false runtime policy claim')
    report=dict(schema=1,native_geometry_complete=True,runtime_policy_complete=False,parents=compared,
        spec=artifact(spec_file),native_result=artifact(result_file),guard=binding,
        scope='all12 original→19 current saved source/GPU/cooked/hull/material/query fields; fixture policy only')
    atomic_json(spec_file.parent/'native-host-comparison.json',report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    first=commands.add_parser('prepare')
    first.add_argument('--original',type=Path,required=True);first.add_argument('--atomic',type=Path,required=True)
    first.add_argument('--output',type=Path,required=True);first.add_argument('--content',type=Path,required=True)
    first.add_argument('--baseline',default='283329c07');first.add_argument('--project',type=Path,required=True)
    first.add_argument('--native-files',type=Path,nargs='+',required=True)
    last=commands.add_parser('finalize');last.add_argument('--spec',type=Path,required=True)
    last.add_argument('--spec-sha256',required=True);last.add_argument('--guard',type=Path,required=True)
    last.add_argument('--whole-exit',type=int,required=True);args=parser.parse_args()
    if args.command=='prepare':prepare(args.original,args.atomic,args.output,args.content,args.baseline,args.project,args.native_files)
    else:finalize(args.spec,args.spec_sha256,args.guard,args.whole_exit)


if __name__=='__main__':main()
