"""Prospective Track07 DATA recovery. Never import, delete, repair or certify native assets.

Parent runs prepare/finalize OUTSIDE the admitted data verifier. Only validate is
queued under the ordinary guarded Python lifecycle; it never starts subprocesses.
The original whole255/guard/captures are immutable and never become a native pass.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE=Path(__file__).resolve().parent;GAME=HERE.parents[1]
sys.path[:0]=[str(HERE),str(GAME/'tools')]
from atelier.atomic_files import atomic_json  # noqa: E402
from atomic_equivalence_io import artifact,canonical,require  # noqa: E402
import track_native_equivalence as proof  # noqa: E402
from track_material_roster import STATION_MATERIALS,library_membership,source_tables  # noqa: E402

OLD_HEAD='40d5dfed3b057849b6493a2054938152c129ebb6'
OLD_SPEC='b88ed516ff4e4856f294b93a09c28ea12478d46be885fbeb247b6aae04d5e547'
FAILURE='Foreign or leftover imported Track assets'


def binding(path):
    path=Path(path).absolute();return dict(path=str(path),sha256=proof.sha(path))


def read(row):return json.loads(artifact(row))


def failed_authority(spec,whole,failure,guard,stdout,runtime):
    """Require the exact postcapture failure, never successful old guard admission."""
    require(spec['phase']=='original' and spec['source_head']==OLD_HEAD and whole['source_head']==OLD_HEAD
        and whole['spec_sha256']==OLD_SPEC and type(whole['exit_code']) is int and whole['exit_code']==255,
        'Not the frozen failed original Track07 caller')
    require(failure['original_error']==dict(type='EvidenceError',message=FAILURE)
        and failure['remaining_own_actors']==0 and failure['cleanup_failures']==[]
        and failure['actor_cleanup_only'] is True and failure['packages_left_for_explicit_recovery'] is True,
        'Different failure or uncertain actor cleanup')
    late=guard.get('late_reporters',{})
    require(guard.get('state')=='child_exited' and guard.get('cleanup_complete') is True
        and guard.get('processes')==[] and guard.get('footprint_bytes')==0
        and not late.get('unresolved') and not late.get('unresolved_pids') and not late.get('scan_failed'),
        'Failed old caller is not positively empty')
    expected=proof.runtime_inventory(runtime)
    markers=re.findall(r'^(?:\[[0-9.:-]+\]\[\s*[0-9]+\]LogPython: )?TRACK ACTUAL SAVED NATIVE original ([0-9]+)/137 (SM_[A-Za-z0-9_]+)$',stdout,re.M)
    require(markers==[(str(i),name)for i,name in enumerate(sorted(expected),1)],'Incomplete/duplicate old capture markers')
    require('TRACK ACTUAL ORIGINAL/CURRENT137/362 NATIVE FIXTURE COMPLETE' not in stdout,
        'Failed old caller unexpectedly has a success marker')
    return expected


def input_identity_vectors(spec,original,current):
    """Exact137/362 identity carry; actual bytes are independently bound before/after."""
    old=proof.runtime_inventory(original);new=proof.runtime_inventory(current)
    require(old==new and canonical(original)==canonical(current),'Original/current runtime values differ')
    vectors=[]
    for name,levels in sorted(old.items()):
        for level in range(levels):
            relative=original['meshes'][name]['lods'][level]
            require(relative=='meshes/'+name+'_LOD'+str(level)+'.glb','Wrong carried GLB relative path')
            paths=[str(Path(spec[phase+'_track'])/relative)for phase in ('original','current')]
            digests=[spec['inputs'].get(path)for path in paths]
            require(all(isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v)for v in digests)
                and digests[0]==digests[1],'Missing/different original/current declared GLB identity')
            vectors.append(dict(mesh=name,lod=level,original=paths[0],current=paths[1],sha256=digests[0]))
    require(len(old)==137 and len(vectors)==362,'Incomplete carried137/362 input vector')
    return dict(logical_meshes=137,authored_lods=362,rows=vectors)


def current_owner_bindings(spec,current_source):
    """Only the two actual Python owners and explicitly observed Track C++ are carried."""
    root=Path(current_source).absolute()
    pairs=[(spec['importer'],'games/yorimichi/unreal/Scripts/import_belmonte_track.py'),
           (spec['material_owner'],'games/yorimichi/unreal/Scripts/import_belmonte.py')]
    for name in ('BelmonteTrack.cpp','BelmonteTrack.h'):
        paths=[path for path in spec['inputs']if Path(path).name==name]
        require(len(paths)<=1,'Ambiguous observed Track source binding')
        if paths:pairs.append((paths[0],'games/yorimichi/unreal/Source/Yorimichi/'+name))
    result={}
    for observed,relative in pairs:
        expected=spec['inputs'].get(observed)
        require(isinstance(expected,str) and re.fullmatch('[0-9a-f]{64}',expected),'Missing observed production owner identity')
        proof.check_input(observed,expected);path=root/relative;proof.check_input(path,expected)
        result[relative]=dict(observed=dict(path=observed,sha256=expected),current=dict(path=str(path),sha256=expected))
    return result


def host_state(spec,current_source=None):
    """Git/SDK/module probes are exclusively before/after the guarded data child."""
    require('unreal' not in sys.modules and 'bpy' not in sys.modules,'Host authority cannot run inside native')
    source=Path(spec['source'])
    require(not subprocess.check_output(['git','status','--porcelain'],cwd=source),'Frozen source must remain clean')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()
    require(head==OLD_HEAD,'Frozen Track07 source changed')
    from atomic_equivalence import source_binding
    for path,digest in spec['inputs'].items():
        candidate=Path(path)
        if (candidate.is_relative_to(source) and candidate.relative_to(source).parts[0] in ('games','platform')
                and candidate.suffix in ('.py','.cpp','.h')):
            source_binding(dict(revision=OLD_HEAD,path=candidate.relative_to(source).as_posix(),sha256=digest),repo=source)
    # Use the receiving checkout's own environment/recipe, never this new tool's recipe.
    receiver=Path(spec['receiving'])
    code="""import json,sys
from pathlib import Path
from atelier import build,paths
assert paths.REPO.resolve()==Path(sys.argv[1]).resolve()
sys.path.insert(0,str(paths.REPO/'games/yorimichi/tools'))
from network_review_common import current_native_build
print(json.dumps(current_native_build(build.Context('yorimichi'))))
"""
    native=json.loads(subprocess.check_output([str(receiver/'.venv/bin/python'),'-c',code,str(receiver)],cwd=receiver,text=True))
    current=None
    if current_source is not None:
        current_source=Path(current_source).absolute()
        require(not subprocess.check_output(['git','status','--porcelain'],cwd=current_source),'Current source must be clean')
        current=dict(root=str(current_source),head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=current_source,text=True).strip(),
            files=current_owner_bindings(spec,current_source))
    return dict(source_head=head,native=native,current_source=current,
        native_probe_helper=binding(receiver/'games/yorimichi/tools/network_review_common.py'))


def prepare(spec_path,output,*,current_source=None):
    """Freeze metadata/code authority only; do not parse/hash raw native geometry here."""
    output=Path(output).absolute();require(not os.path.lexists(output),'Fresh recovery plan required')
    spec_row=binding(spec_path);require(spec_row['sha256']==OLD_SPEC,'Wrong sealed old spec')
    spec=read(spec_row);folder=Path(spec['output']);runtime_path=Path(spec['original_track'])/'runtime/track.json'
    rows={key:binding(path)for key,path in dict(spec=spec_path,whole=folder/'whole-result.json',
        failure=folder/'failed-fixture-state.json',guard=folder/'guard/memory-health-tree.json',
        current_runtime=Path(spec['current_track'])/'runtime/track.json',
        runtime=runtime_path,report=runtime_path.with_name('import-report.json')).items()}
    from track_guard_stdout import snapshot
    rows['stdout'],stdout_source=snapshot(rows['guard'],rows['whole'],folder/'guard/stdout.log',
        output.with_suffix('.native-stdout.snapshot.log'),expected_exit=255)
    values={key:read(row)for key,row in rows.items()if key!='stdout'}
    expected=failed_authority(spec,values['whole'],values['failure'],values['guard'],artifact(rows['stdout']).decode(),values['runtime'])
    state=host_state(spec,current_source);require(state['native']==values['whole']['native'],'Current native inventory differs from failed observation')
    descriptors={name:binding(folder/'captures/original'/name/'native-descriptor.json')for name in expected}
    require({p.name for p in (folder/'captures/original').iterdir()}==set(expected),'Foreign/missing retained capture directory')
    from atelier.source_imports import local_imports
    support={path for entry in (Path(__file__),Path(proof.__file__))
             for path in local_imports(entry,(GAME,GAME.parents[1]/'platform/studio'))}
    support.update((Path(__file__),HERE/'track_material_roster.py',HERE/'track_observation_data.py',HERE/'track_query_surface.py'))
    support.update(GAME.parents[1]/'platform/studio/atelier'/name for name in
        ('atomic_files.py','export_manifest.py','paths.py','gltf.py','mesh_ir.py','mesh_geometry.py'))
    validation_inputs={str(path.absolute()):proof.sha(path)for path in support}
    atomic_json(output,dict(validation_inputs=validation_inputs,schema=1,kind='track07-observation-plan',old_spec_sha256=OLD_SPEC,
        metadata=rows,descriptors=descriptors,host_before=state,stdout_source_observation=stdout_source,
        failed_old_whole=255,observation_validation_only=True,cleanup_pending=True))
    print('TRACK07 OBSERVATION PLAN PREPARED; NO NATIVE/DATA VALIDATION',flush=True)


def rebuild_saved_archives(descriptor,name,spec,*,check_current_packages=False):
    """Retain recorded SHA authority; deterministic archive paths never invent bytes."""
    saved=[]
    for row in descriptor['saved_packages']:
        path=Path(row['path']);base=Path(spec['content'])/spec['package'].removeprefix('/Game/')/'Library'
        require(path.parent==base and path.stem==name and path.suffix in proof.SIDECARS,
                'Saved source package escaped logical owner')
        archive=Path(spec['output'])/'saved-packages/original'/(hashlib.sha256(str(path).encode()).hexdigest()+path.suffix)
        bound=dict(path=str(archive),sha256=row['sha256']);artifact(bound);saved.append(bound)
        if check_current_packages:artifact(row)
    require(saved and sum(Path(row['path']).suffix=='.uasset'for row in saved)==1,'Saved archive primary missing/duplicated')
    require(len({row['path']for row in saved})==len(saved),'Duplicate saved archive')
    descriptor=copy.deepcopy(descriptor);descriptor['saved_packages']=saved
    return descriptor,saved


VALIDATION_MODULES=('atelier.atomic_files','atelier.export_manifest','atelier.paths','atelier.gltf',
    'atelier.mesh_ir','atelier.mesh_geometry','atomic_equivalence_io','atomic_equivalence')


def validation_environment(plan):
    """Refuse a shadow installed helper even when a different declared file is intact."""
    for name in VALIDATION_MODULES:
        module=sys.modules.get(name)
        if module is None:continue
        path=Path(module.__file__).absolute();expected=plan['validation_inputs'].get(str(path))
        require(expected is not None,'Actual data helper is outside the frozen source closure: '+name)
        proof.check_input(path,expected)


def validate(plan_path,plan_sha,output,*,check_current_packages=False):
    """@cc [owner:fontanierh,label:correctness] failed-track-observation-not-admission
    Failed whole255 observations MUST remain data-only with cleanup pending. Complete
    frozen source, saved archive, raw native pages, slots, queries and roster MUST
    validate without subprocesses. This MUST NOT create a native/cache/task pass,
    rewrite old evidence, remove assets or claim original/current equivalence.
    """
    output=Path(output).absolute();require(not os.path.lexists(output),'Fresh data report required')
    plan_row=dict(path=str(Path(plan_path).absolute()),sha256=plan_sha);plan=read(plan_row)
    require(plan['schema']==1 and plan['kind']=='track07-observation-plan' and plan['old_spec_sha256']==OLD_SPEC,'Wrong recovery plan')
    rows=plan['metadata'];spec=read(rows['spec']);require(rows['spec']['sha256']==OLD_SPEC,'Old spec binding changed')
    runtime=read(rows['runtime']);report=read(rows['report']);whole=read(rows['whole'])
    expected=failed_authority(spec,whole,read(rows['failure']),read(rows['guard']),artifact(rows['stdout']).decode(),runtime)
    require(plan['host_before']['native']==whole['native'] and plan['host_before']['source_head']==OLD_HEAD,'Unbound host/native preparation')
    for path,digest in plan['validation_inputs'].items():proof.check_input(path,digest)
    validation_environment(plan)
    proof.bound_inputs(spec)
    vectors=input_identity_vectors(spec,runtime,read(rows['current_runtime']))
    current_source=plan['host_before'].get('current_source')
    if current_source is not None:
        require(current_owner_bindings(spec,current_source['root'])==current_source['files'],'Carried source bytes changed')
    proof.owner_tree(spec['importer'],spec['package']+'/Prerequisites/Materials')
    tables=source_tables(runtime,spec['original_track'])
    owned,witnesses=library_membership(runtime,report,spec['package']+'/Library',tables)
    require(set(witnesses)&STATION_MATERIALS==STATION_MATERIALS,'Missing four real station material owners')
    observed=set(read(rows['failure'])['partial_namespace']['observed_packages'])
    library={p for p in observed if p.startswith(spec['package']+'/Library/')}
    require(library==owned,'Corrected exact Library roster still differs')
    material_names,texture_names=proof.material_inputs(json.loads(Path(spec['material_report']).read_bytes()),spec['material_data'])
    common={spec['package']+'/Prerequisites/Materials/'+name for name in ['M_Belmonte','M_BelmonteJoin',*material_names]}
    common.update(spec['package']+'/Prerequisites/Textures/'+Path(name).stem for name in texture_names)
    require(observed==owned|common,'Unknown/missing package outside corrected Library roster')
    require(set(plan['descriptors'])==set(expected),'Incomplete planned137 descriptor roster')
    records={};references={name:[] for name in STATION_MATERIALS};archive_rows=[]
    for index,name in enumerate(sorted(expected),1):
        descriptor=read(plan['descriptors'][name]);require(descriptor['inputs']==[rows['spec']],'Capture not bound to original frozen spec')
        require(descriptor['meshes']==[spec['package']+'/Library/'+name+'.'+name], 'Capture mesh path differs')
        descriptor,saved=rebuild_saved_archives(descriptor,name,spec,check_current_packages=check_current_packages)
        archive_rows.extend(saved);records[name]=descriptor
        for page_row in descriptor['raw_pages']:
            page=read(page_row)
            if page['first']!=0:continue
            for slot in page['slots']:
                for material in STATION_MATERIALS:
                    if slot['material']==report['materials'][material]:
                        references[material].append(dict(mesh=name,lod=page['lod'],slot=slot['name'],page=page_row))
        print('TRACK07 RETAINED OBSERVATION '+str(index)+'/137 '+name,flush=True)
    require(all(references.values()),'One of four station materials has no actual saved native slot reference')
    for name,refs in references.items():
        source_users={row['mesh']for row in witnesses[name]['sources']}
        require(any(ref['mesh']in source_users for ref in refs),'Native material lacks the exact source/runtime witness')
    # Validate every raw observation independently; preserve exact known query noncoverage.
    # The strict paired comparator remains unchanged and still rejects these records.
    from track_observation_data import validate as validate_data
    diagnostic=validate_data(records,runtime,spec['controls'],
        progress=lambda name:print('TRACK07 STRICT RAW OBSERVATION DATA '+name,flush=True))
    validation_environment(plan)
    proof.bound_inputs(spec)
    if current_source is not None:
        require(current_owner_bindings(spec,current_source['root'])==current_source['files'],'Carried source bytes changed during verification')
    for path,digest in plan['validation_inputs'].items():proof.check_input(path,digest)
    for row in rows.values():artifact(row)
    require(read(plan_row)==plan,'Frozen observation plan changed')
    result=dict(schema=1,kind='track07-observation-data',plan=plan_row,failed_old_whole=255,
        observation_validation_only=True,cleanup_pending=True,complete=False,native_complete=False,
        source_input_identity_carry=current_source is not None,independent_paired_native_execution=False,
        current_compiled_main_claim=False,current_source=current_source,input_identity_vectors=vectors,diagnostic=diagnostic,
        original_current_equivalence=False,normal_task_reuse=False,records=records,station_material_witnesses=witnesses,
        actual_slot_references=references,owned_packages=sorted(owned|common),saved_archives=archive_rows,current_package_bytes_checked=check_current_packages,
        source_head=OLD_HEAD,native=whole['native'],logical_meshes=137,authored_lods=362,
        scope='Retained failed original observations only; host after-check/new guard finalization pending')
    atomic_json(output,result)
    print('TRACK07 OBSERVATION DATA VALIDATION COMPLETE '+plan_sha+' '+proof.sha(output),flush=True)


def finalize(plan_path,plan_sha,data_path,guard_path,whole_path,output,*,current_source=None):
    """New verifier whole0/empty and HOST after-check, without accepting old whole255."""
    require(not os.path.lexists(output),'Fresh final observation report required')
    plan_row=dict(path=str(Path(plan_path).absolute()),sha256=plan_sha);plan=read(plan_row);spec=read(plan['metadata']['spec'])
    from atomic_equivalence import guard_binding
    data_row=binding(data_path);data=read(data_row)
    require(data['plan']==plan_row and data['failed_old_whole']==255 and data['observation_validation_only'] is True
        and data['cleanup_pending'] is True and data['complete'] is False and data['native_complete'] is False,
        'Data report tried to promote failed observations')
    from track_guard_stdout import snapshot
    receipt=binding(Path(guard_path)/'memory-health-tree.json');whole_row=binding(whole_path)
    stdout,stdout_source=snapshot(receipt,whole_row,Path(guard_path)/'stdout.log',Path(output).with_suffix('.data-stdout.snapshot.log'),expected_exit=0)
    evidence=dict(receipt=receipt,stdout=stdout,whole_result=whole_row,marker='TRACK07 OBSERVATION DATA VALIDATION COMPLETE '+plan_sha+' '+data_row['sha256'])
    guard_binding(evidence)  # ONLY the new data-verifier caller, never the old255 caller.
    prepared_current=plan['host_before'].get('current_source')
    require(data['source_input_identity_carry'] is (prepared_current is not None),'Unwitnessed source input carry')
    require((prepared_current is None and current_source is None) or
        (prepared_current is not None and current_source is not None and str(Path(current_source).absolute())==prepared_current['root']),
        'Finalize current-source scope differs from preparation')
    after=host_state(spec) if current_source is None else host_state(spec,current_source)
    require(after==plan['host_before'],'Host source/native identities changed across data verification')
    for path,digest in plan['validation_inputs'].items():proof.check_input(path,digest)
    for row in plan['metadata'].values():artifact(row)
    atomic_json(output,dict(schema=1,kind='track07-observation-host-final',data=data_row,new_data_guard=evidence,stdout_source_observation=stdout_source,
        failed_old_whole=255,observation_validation_only=True,cleanup_pending=True,complete=False,native_complete=False,
        source_input_identity_carry=data['source_input_identity_carry'],independent_paired_native_execution=False,
        current_compiled_main_claim=False,current_source=prepared_current,
        original_current_equivalence=False,normal_task_reuse=False,source_head=OLD_HEAD,native=data['native']))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','validate','finalize'))
    p.add_argument('--current-source',type=Path)
    p.add_argument('--spec',type=Path);p.add_argument('--plan',type=Path);p.add_argument('--plan-sha256')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--check-current-packages',action='store_true')
    p.add_argument('--data',type=Path);p.add_argument('--guard',type=Path);p.add_argument('--whole',type=Path);a=p.parse_args()
    if a.mode=='prepare':prepare(a.spec,a.output,current_source=a.current_source)
    elif a.mode=='validate':validate(a.plan,a.plan_sha256,a.output,check_current_packages=a.check_current_packages)
    else:finalize(a.plan,a.plan_sha256,a.data,a.guard,a.whole,a.output,current_source=a.current_source)


if __name__=='__main__':main()
