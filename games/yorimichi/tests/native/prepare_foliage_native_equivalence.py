"""Host-only freeze of foliage original/current inputs. Never launch native tools.

Run only after the producer's whole caller has stopped; input identities must remain
unchanged through complete independent texture/FBX/manifest staging.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

import numpy as np

GAME=Path(__file__).resolve().parents[2];REPO=GAME.parents[1]
sys.path[:0]=[str(GAME/'world'),str(GAME/'tools'),str(Path(__file__).parent)]
import yori  # noqa: E402,F401
from atelier import engine,mesh_ir  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.build_inputs import local_imports  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from atelier.mesh_geometry import SIDECARS  # noqa: E402
from atomic_equivalence import guard_binding,source_binding  # noqa: E402
from atomic_equivalence_io import artifact,require  # noqa: E402
import foliage_native_equivalence as proof  # noqa: E402
from track_native_equivalence import check_input,private_launch,sha  # noqa: E402

SOURCE_HEAD='bb24d59b212512cff336fc4382063379d67c8e4e'


def head(folder):
    require(not subprocess.check_output(['git','status','--porcelain'],cwd=folder),'Freeze clean source/receiver')
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=folder).decode().strip()


def identity(path):
    st=Path(path).lstat()
    return [st.st_dev,st.st_ino,st.st_mode,st.st_size,st.st_mtime_ns,st.st_ctime_ns]


def source_control(name,entry,path):
    meta,piece=mesh_ir.decode(Path(path).read_bytes());require(meta['asset']==name,'Source control logical identity differs')
    positions=np.asarray(piece['positions'],dtype=float)
    matrix=np.asarray(meta['matrix'],dtype=float);require(matrix.shape==(4,4) and np.isfinite(matrix).all() and np.array_equal(matrix[3],[0.,0.,0.,1.]),'Invalid source object transform')
    vertices=(np.column_stack((positions,np.ones(len(positions))))@matrix.T)[:,:3]*[100.,-100.,100.]
    require(vertices.ndim==2 and vertices.shape[1]==3 and np.isfinite(vertices).all(),'Missing actual source positions')
    best=None
    for face in piece['faces']:
        for k in range(1,len(face)-1):
            triangle=vertices[[face[0],face[k],face[k+1]]];normal=np.cross(triangle[1]-triangle[0],triangle[2]-triangle[0]);area=float(np.linalg.norm(normal))
            if area>0 and(best is None or area>best[0]):best=(area,triangle.mean(0),normal/area)
    require(best is not None,'No real source triangle for query control')
    _,center,normal=best
    positive=dict(start=(center+normal*200.).tolist(),end=(center-normal*200.).tolist(),channel='Pawn',trace_complex=True)
    far=vertices.max(0)+10000.;negative=dict(start=far.tolist(),end=(far+[0,0,100.]).tolist(),channel='Pawn',trace_complex=True)
    rows=[]
    for row in proof.query_plan(name,entry):
        # Simple Default/no-hull and NoCollision negatives use actual surface controls.
        permits_surface=entry['query_only'] and (row['mode']=='complex' or entry['collision']=='complex')
        query=dict(positive if row['kind'].endswith('positive') or not permits_surface else negative,
                   trace_complex=row['mode']=='complex')
        if row['kind'].startswith('capsule'):
            query.update(radius_cm=.1,half_height_cm=.1,orientation=[0.,0.,0.,1.])
        rows.append(dict(id=row['id'],kind=row['kind'],input=query))
    return rows


def freeze_textures(producer,bind):
    """Resolve every actual shared-material texture before any independent output write."""
    names=proof.catalog_literal('TEXTURES');require(len(names)==22,'Wrong genuine material texture catalogue')
    return {name:bind(Path(producer)/'build/yorimichi/textures'/name)for name in names}


def prepare(args):
    for key in ('proof','producer','receiving'):setattr(args,key,real_directory(getattr(args,key).absolute()))
    root=real_directory(args.output.absolute());require(not root.exists(),'Fresh receiving fixture required')
    source_head,receiver_head=head(REPO),head(args.receiving)
    producer_head=head(args.producer)
    # A real completed producer caller/guard is mandatory; no invented stamp/report stands in.
    whole=json.loads(artifact(dict(path=str(args.producer_whole.absolute()),sha256=sha(args.producer_whole))))
    require(whole.get('exit_code')==0,'Producer whole caller did not succeed')
    guard=json.loads(artifact(dict(path=str(args.producer_guard.absolute()),sha256=sha(args.producer_guard))))
    late=guard.get('late_reporters',{})
    require(guard.get('state')=='child_exited' and guard.get('cleanup_complete') is True and guard.get('processes')==[]
        and guard.get('footprint_bytes')==0 and not late.get('unresolved') and not late.get('unresolved_pids') and not late.get('scan_failed'),
        'Producer guard is not independently terminal/empty')
    inputs={};pins={}
    def bind(path,digest=None):
        path=Path(path).absolute();digest=sha(path)if digest is None else digest
        check_input(path,digest);inputs[str(path)]=digest;pins[str(path)]=identity(path);return path
    bind(args.producer_whole);bind(args.producer_guard)
    handoff=json.loads(bind(args.proof/'handoff.json').read_bytes())
    require(handoff['literal_fbx_exact']==102 and handoff['source_packet_exact']==102
        and handoff['legacy_manifest_values_exact']==18,'Missing complete frozen foliage source proof')
    for row in handoff['proofs']:bind(row['path'],row['sha256'])
    for stem, marker in (('original','FOLIAGE CONTROL COMPLETE original 102'),
                         ('selected-normal-domain','FOLIAGE CONTROL COMPLETE selected 102')):
        receipt=bind(args.proof/(stem+'.guard/memory-health-tree.json'))
        stdout=bind(args.proof/(stem+'.guard/stdout.log'));whole_path=bind(args.proof/(stem+'-whole.json'))
        guard_binding(dict(receipt=dict(path=str(receipt),sha256=sha(receipt)),stdout=dict(path=str(stdout),sha256=sha(stdout)),
            marker=marker,whole_result=dict(path=str(whole_path),sha256=sha(whole_path))))
    original=json.loads(bind(args.proof/'original-source-authority.json').read_bytes())
    current=json.loads(bind(args.proof/'actual-source-authority.json').read_bytes())
    require(original['base']=='913d39edd3b00f015755e3b34762fe20c2af3692' and original['files']
        and current['head']==SOURCE_HEAD and current['files'],'Wrong/incomplete frozen source authority')
    for authority in(original,current):
        for row in authority['files']:source_binding({key:row[key]for key in('revision','path','sha256')},repo=REPO)
    comparison=json.loads(bind(args.proof/'comparison-normal-domain.json').read_bytes())
    rows=comparison['rows'];require(len(rows)==102 and len({row['key']for row in rows})==102,'Missing frozen source rows')
    by_key={row['key']:row for row in rows};manifests={};manifest_paths={}
    old_data=args.proof/'original-repo/build/yorimichi/foliage';new_data=args.producer/'build/yorimichi/foliage'
    names=proof.owner_names()
    require(len(names)==18,'Wrong actual native owner catalogue')
    for name in names:
        a,b=bind(old_data/name/'manifest.json'),bind(new_data/name/'manifest.json')
        data=json.loads(a.read_bytes());require(data==json.loads(b.read_bytes()),'Actual native manifest differs: '+name)
        manifests[name]=data;manifest_paths[name]=(a,b)
    expected=proof.inventory(manifests)
    require(set(by_key)==set(expected)|{name+'_Seed'for name in names},'Source census omits an authored LOD/Seed')
    for row in rows:
        require(row['fbx_equal'] is True and row['source_equal'] is True
            and row['original_fbx']['sha256']==row['actual_fbx']['sha256']
            and row['original_source']['sha256']==row['actual_source']['sha256'],'Literal original/current source differs')
        for key in('original_fbx','actual_fbx','original_source','actual_source'):bind(row[key]['path'],row[key]['sha256'])
    texture_paths=freeze_textures(args.producer,bind);textures=tuple(texture_paths)
    scripts=GAME/'unreal/Scripts';roots=(GAME,GAME/'world',GAME/'tools',REPO/'platform/studio')
    for entry in [scripts/'shared_materials.py',scripts/'import_foliage.py',scripts/'atomic_equivalence_capture.py',Path(__file__),
        Path(proof.__file__),Path(__file__).with_name('run_foliage_native_equivalence.py'),Path(__file__).with_name('track_native_equivalence.py'),
        Path(__file__).with_name('run_track_native_equivalence.py'),GAME/'tools/atomic_equivalence.py',GAME/'tools/atomic_equivalence_io.py']:
        bind(entry)
        for dependency in local_imports(entry,roots):bind(dependency)
    for name in('NativeAtomicEquivalence.cpp','NativeAtomicEquivalence.h','JapanWorld.cpp'):
        bind(args.receiving/'games/yorimichi/unreal/Source/Yorimichi'/name)
    controls={name:source_control(name,item,by_key[name]['original_source']['path'])for name,item in expected.items()}
    proof.validate_controls(controls,manifests)
    package='/Game/AtelierValidation/Foliage_'+uuid.uuid4().hex[:12]
    for name,(relative,digest)in proof.MAPPED.items():
        source_binding(dict(revision='913d39edd3b00f015755e3b34762fe20c2af3692',path='games/yorimichi/'+relative,sha256=digest),repo=REPO)
        proof.mapped_tree(name,GAME,package)
    engine_root=engine.unreal_root();bind(engine_root/'Engine/Config/BaseEngine.ini')
    function=engine_root/'Engine/Content/Functions/Engine_MaterialFunctions02/Utility/DitherTemporalAA.uasset'
    bind(function);absent=[]
    for suffix in SIDECARS:
        if suffix=='.uasset':continue
        path=function.with_suffix(suffix)
        if path.exists()or path.is_symlink():bind(path)
        else:absent.append(str(path))
    launches={phase:private_launch(root,phase,engine_root)for phase in('original','current')}
    # All source/census/tool/material proof precedes independent output copies.
    root.mkdir(parents=True);(root/'private-ddc').mkdir();texture_copy=root/'textures';texture_copy.mkdir()
    for name,path in texture_paths.items():
        target=texture_copy/name;shutil.copyfile(path,target);bind(target,inputs[str(path)])
    for phase in('original','current'):
        folder=root/'frozen'/phase
        for name,data in manifests.items():
            target=folder/'foliage'/name/'manifest.json';target.parent.mkdir(parents=True)
            original_path=manifest_paths[name][int(phase=='current')];shutil.copyfile(original_path,target);bind(target,inputs[str(original_path)])
        for key,row in by_key.items():
            owner=next(name for name in names if key==name or key.startswith(name+'_'))
            path=Path(row['original_fbx'if phase=='original'else'actual_fbx']['path']);target=folder/'foliage'/owner/(key+'.fbx')
            shutil.copyfile(path,target);bind(target,row['original_fbx']['sha256'])
        output=root/phase;output.mkdir();(output/'user').mkdir()
    for path,digest in inputs.items():check_input(path,digest);require(identity(path)==pins[path],'Source identity changed during staging')
    require(not any(pathlib_path.exists()or pathlib_path.is_symlink()for pathlib_path in map(Path,absent)),
        'Engine material companion membership changed during staging')
    textures_input={str(texture_copy/name):sha(texture_copy/name)for name in textures}
    for phase in('original','current'):
        spec=dict(schema=1,phase=phase,source=str(REPO),source_head=source_head,receiving=str(args.receiving),receiving_head=receiver_head,
            package=package,output=str(root/phase),producer=str(args.producer),producer_head=producer_head,content=str(args.receiving/'games/yorimichi/unreal/Content'),launch=launches[phase],
            original_data=str(root/'frozen/original'),current_data=str(root/'frozen/current'),textures=str(texture_copy),
            textures_input=textures_input,manifests=manifests,controls=controls,inputs=inputs,absent_inputs=absent,
            coverage=dict(source_fbx=102,source_authored_lods=84,source_seed=18,native_owners=18,native_packages=84,native_pages=150,
                production_runtime=False,normal_native_reuse=False))
        atomic_json(root/phase/'spec.json',spec)
    require(head(REPO)==source_head and head(args.receiving)==receiver_head and head(args.producer)==producer_head,
        'Source/receiver/producer changed during staging')
    atomic_json(root/'prepare-result.json',dict(prepared=True,native_launched=False,source_head=source_head,receiving_head=receiver_head,
        inputs=inputs,source_identity_pins=pins,producer_head=producer_head,independent_texture_count=22))
    print('FOLIAGE NATIVE INPUTS PREPARED; NO NATIVE LAUNCH',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in('proof','producer','receiving','producer-whole','producer-guard','output'):parser.add_argument('--'+name,type=Path,required=True)
    prepare(parser.parse_args())


if __name__=='__main__':main()
