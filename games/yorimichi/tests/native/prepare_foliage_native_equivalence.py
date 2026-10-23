"""Host-only freeze of foliage original/current inputs. Never launch native tools.

Run only after the producer's whole caller has stopped; input identities must remain
unchanged through complete independent texture/FBX/manifest staging.
"""
import argparse
import json
import re
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
from atomic_equivalence_io import require  # noqa: E402
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


def freeze_current_fbx(producer,rows,names,bind):
    """Bind real completed native inputs, never substitute the earlier control outputs."""
    result={}
    for key,row in rows.items():
        owners=[name for name in names if key==name or key.startswith(name+'_')]
        require(len(owners)==1,'Ambiguous actual foliage source owner')
        path=Path(producer)/'build/yorimichi/foliage'/owners[0]/(key+'.fbx')
        result[key]=bind(path,row['actual_fbx']['sha256'])
    return result


def producer_empty(guard):
    late=guard.get('late_reporters',{})
    require(guard.get('state')=='child_exited' and guard.get('cleanup_complete') is True and guard.get('processes')==[]
        and guard.get('footprint_bytes')==0 and not late.get('unresolved') and not late.get('unresolved_pids') and not late.get('scan_failed'),
        'Producer guard is not independently terminal/empty')


def producer_evidence(args,producer_head,bind):
    """Read an actual singular caller or its sealed collection, never invent wrappers."""
    collection=getattr(args,'producer_handoff',None)
    require(bool(collection)!=bool(args.producer_whole) and (not collection or args.producer_guard is None)
        and (not args.producer_whole or args.producer_guard is not None),'Select producer handoff OR whole plus guard')
    if collection is None:
        whole=json.loads(bind(args.producer_whole).read_bytes())
        require(whole.get('exit_code')==0,'Producer whole caller did not succeed')
        producer_empty(json.loads(bind(args.producer_guard).read_bytes()))
        return None
    path=bind(collection);handoff=json.loads(path.read_bytes())
    require(handoff.get('head')==producer_head and handoff.get('source_clean') is True,'Producer handoff head/clean source differs')
    declared=handoff['artifacts'];metadata={}
    for row in declared:
        item=Path(row['path']).absolute()
        require(item.parent==path.parent and item.name not in metadata,'Aliased/foreign handoff artifact')
        metadata[item.name]=bind(item,row['sha256'])
    require({'whole-results.json','producer-after-noop.json'}<=set(metadata),'Missing producer collection metadata')
    whole=json.loads(metadata['whole-results.json'].read_bytes())
    require(set(whole)=={'producer','noop','receiver'} and handoff.get('commands')==whole,'Producer commands differ from bound whole collection')
    require(whole['producer'].get('exit_code')==0 and whole['producer'].get('steps')==264,'Producer whole caller did not succeed264 steps')
    snapshot=json.loads(metadata['producer-after-noop.json'].read_bytes())
    require(snapshot.get('head')==producer_head and snapshot.get('checkout')==str(args.producer)
        and snapshot.get('target')=='world.foliage_lods','Producer snapshot head/checkout/target differs')
    steps=snapshot['steps'];names=[row['name']for row in steps]
    require(len(steps)==264 and len(set(names))==264 and 'world.foliage_lods' in names
        and all(re.fullmatch('[0-9a-f]{64}',row['fingerprint'])for row in steps),'Incomplete producer step inventory')
    return snapshot


def producer_guard_membership(snapshot,keys,producer,bind):
    """@cc [owner:fontanierh,label:correctness;safety] foliage-normal-producer-guard-closure
    A sealed producer collection MUST cover both source and export for every one
    of the102 exact comparison keys. Each unique recorded guard MUST retain its
    bound receipt, successful observation and stdout, positive empty cleanup and
    matching ordered action-start, selected-source/export completion and batch-completion
    stdout markers. Hash binding alone MUST NOT prove batch/step membership.
    Missing, extra or pending proof MUST refuse
    before any fixture output is written; collection proof is not native reuse.
    """
    if snapshot is None:return
    expected={'world.foliage.'+kind+'.'+key for key in keys for kind in('source','export')}
    require(len(keys)==102 and len(expected)==204,'Incomplete comparison keys for producer guard coverage')
    steps={row['name']:row for row in snapshot['steps']};guards=snapshot['guards']
    names=[row['step']for row in guards]
    require(len(guards)==204 and len(set(names))==204 and set(names)==expected
        and set(steps)&expected==expected,'Missing/unknown/duplicate producer guard step')
    require({name for name in steps if name.startswith(('world.foliage.source.','world.foliage.export.'))}==expected,
        'Producer action inventory differs from comparison keys')
    paths=set()
    for row in guards:
        require(set(row)=={'step','receipt','observation','stdout'},'Invalid producer guard record')
        batch=steps[row['step']]['batch']
        require(isinstance(batch,str) and re.fullmatch('[0-9a-f]{32}',batch),'Missing producer batch identity')
        folder=producer/'build/yorimichi/logs'/('batch.'+batch+'.guard')
        payload={}
        for kind,name in(('receipt','memory-health-tree.json'),('observation','successful-tree-observation.json'),('stdout','stdout.log')):
            record=row[kind];path=Path(record['path']).absolute()
            require(path==folder/name and str(path) not in paths,'Aliased/foreign producer guard artifact')
            paths.add(str(path));path=bind(path,record['sha256'])
            payload[kind]=path.read_text()if kind=='stdout'else json.loads(path.read_bytes())
        step=row['step'];kind,key=step.removeprefix('world.foliage.').split('.',1)
        prefixes=('ATELIER ACTION START ','FOLIAGE SELECTED SOURCE COMPLETE ',
                  'ATOMIC FOLIAGE EXPORT COMPLETE ','ATELIER BATCH COMPLETE ')
        markers=[line for line in payload['stdout'].splitlines()if line.startswith(prefixes)]
        completion=('FOLIAGE SELECTED SOURCE COMPLETE '+key)if kind=='source'else('ATOMIC FOLIAGE EXPORT COMPLETE '+key)
        require(len(markers)==3 and markers[0]=='ATELIER ACTION START '+step
            and markers[2]=='ATELIER BATCH COMPLETE '+batch
            and (re.fullmatch(re.escape(completion)+r' [1-9][0-9]*',markers[1])if kind=='source'else markers[1]==completion),
            'Producer stdout action/batch membership differs')
        receipt,observation=payload['receipt'],payload['observation'];producer_empty(receipt)
        require(observation.get('schema')==1 and observation.get('cleanup_and_capacity_close') is True
            and observation.get('root')==[receipt['owner'],receipt['owner_started']],
            'Producer successful observation differs from actual guard')


def prepare(args):
    for key in ('proof','producer','receiving'):setattr(args,key,real_directory(getattr(args,key).absolute()))
    root=real_directory(args.output.absolute());require(not root.exists(),'Fresh receiving fixture required')
    source_head,receiver_head=head(REPO),head(args.receiving)
    producer_head=head(args.producer)
    inputs={};pins={}
    def bind(path,digest=None):
        path=Path(path).absolute();digest=sha(path)if digest is None else digest
        check_input(path,digest);inputs[str(path)]=digest;pins[str(path)]=identity(path);return path
    producer_snapshot=producer_evidence(args,producer_head,bind)
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
    producer_guard_membership(producer_snapshot,set(by_key),args.producer,bind)
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
    actual_fbx=freeze_current_fbx(args.producer,by_key,names,bind)
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
    bind(engine_root/'Engine/Source/Runtime/Engine/Classes/Engine/EngineTypes.h')
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
            path=Path(row['original_fbx']['path'])if phase=='original'else actual_fbx[key]
            target=folder/'foliage'/owner/(key+'.fbx')
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
    for name in('proof','producer','receiving','output'):parser.add_argument('--'+name,type=Path,required=True)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--producer-whole',type=Path);mode.add_argument('--producer-handoff',type=Path)
    parser.add_argument('--producer-guard',type=Path)
    args=parser.parse_args()
    if bool(args.producer_whole)!=bool(args.producer_guard):parser.error('--producer-whole requires --producer-guard; handoff forbids it')
    prepare(args)


if __name__=='__main__':main()
