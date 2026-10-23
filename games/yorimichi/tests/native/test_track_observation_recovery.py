"""Small synthetic recovery faults; never read retained Track07 blobs or launch tools."""
import ast
import json
from pathlib import Path
import struct
import sys

import pytest

HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import recover_track_native_observations as recovery
import track_material_roster as roster

ROOT='/Game/AtelierValidation/Track_0123456789ab/Library'


def sample():
    names=sorted(roster.STATION_MATERIALS)
    runtime=dict(meshes={'SM_ST_Test':dict(materials=[*names,'MI_ST_CoachRoof'])})
    report=dict(meshes={'SM_ST_Test':{}},materials={name:ROOT+'/Materials/'+name+'.'+name for name in names})
    sources={'SM_ST_Test':dict(path='meshes/SM_ST_Test_LOD0.glb',names=set(names))}
    return runtime,report,sources


def test_exact_four_owned_materials_require_source_and_report_witnesses():
    runtime,report,sources=sample();owned,witness=roster.library_membership(runtime,report,ROOT,sources)
    assert len(owned)==6 and set(witness)==roster.STATION_MATERIALS
    assert ROOT+'/Materials/MI_ST_CoachRoof' not in owned
    assert all(row['owner_function']=='import_belmonte_track.track_material' for row in witness.values())


@pytest.mark.parametrize('fault',['unknown','wrong_path','missing_runtime','missing_source','false_name','missing_mesh','foreign_root','missing_report','source_path'])
def test_finite_roster_rejects_unknown_paths_and_unconsumed_names(fault):
    runtime,report,sources=sample();name='MI_ST_Coach';root=ROOT
    if fault=='unknown':report['materials']['MI_ST_Unknown']=ROOT+'/Materials/MI_ST_Unknown.MI_ST_Unknown'
    elif fault=='wrong_path':report['materials'][name]='/Game/Japan/Materials/'+name+'.'+name
    elif fault=='missing_runtime':runtime['meshes']['SM_ST_Test']['materials'].remove(name)
    elif fault=='missing_source':sources['SM_ST_Test']['names'].remove(name)
    elif fault=='false_name':report['materials']['MI_ST_CoachRoof']=ROOT+'/Materials/MI_ST_CoachRoof.MI_ST_CoachRoof'
    elif fault=='missing_mesh':sources.clear()
    elif fault=='missing_report':report['materials'].pop(name)
    elif fault=='source_path':sources['SM_ST_Test']['path']='meshes/SM_ST_Foreign_LOD0.glb'
    else:root='/Game/Japan'
    with pytest.raises(ValueError):roster.library_membership(runtime,report,root,sources)


def test_source_witness_uses_primitive_material_not_unused_table_entry(tmp_path):
    doc=dict(nodes=[dict(mesh=0)],meshes=[dict(primitives=[dict(material=0)])],
             materials=[dict(name='MI_ST_Coach'),dict(name='MI_ST_CoachRoof')])
    payload=json.dumps(doc).encode();payload+=b' '*((-len(payload))%4)
    path=tmp_path/'source.glb';path.write_bytes(struct.pack('<5I',0x46546c67,2,20+len(payload),len(payload),0x4e4f534a)+payload)
    assert roster.glb_material_names(path)=={'MI_ST_Coach'}


def failed_rows():
    spec=dict(phase='original',source_head=recovery.OLD_HEAD)
    whole=dict(source_head=recovery.OLD_HEAD,spec_sha256=recovery.OLD_SPEC,exit_code=255)
    failure=dict(original_error=dict(type='EvidenceError',message=recovery.FAILURE),remaining_own_actors=0,
        cleanup_failures=[],actor_cleanup_only=True,packages_left_for_explicit_recovery=True)
    guard=dict(state='child_exited',cleanup_complete=True,processes=[],footprint_bytes=0)
    return spec,whole,failure,guard


@pytest.mark.parametrize('fault',[None,'whole0','source','spec','actors','cleanup','different_failure','live_guard','late','missing_marker','duplicate','success_marker'])
def test_failed255_authority_never_becomes_success(monkeypatch,fault):
    monkeypatch.setattr(recovery.proof,'runtime_inventory',lambda _:dict(SM_TK_Test=1))
    spec,whole,failure,guard=failed_rows()
    text='[2026.10.23-20.19.25:538][  0]LogPython: TRACK ACTUAL SAVED NATIVE original 1/137 SM_TK_Test\n'
    if fault=='whole0':whole['exit_code']=0
    elif fault=='source':spec['source_head']='a'*40
    elif fault=='spec':whole['spec_sha256']='b'*64
    elif fault=='actors':failure['remaining_own_actors']=1
    elif fault=='cleanup':failure['cleanup_failures']=['unresolved']
    elif fault=='different_failure':failure['original_error']['message']='a different import failure'
    elif fault=='live_guard':guard['processes']=[123]
    elif fault=='late':guard['late_reporters']=dict(unresolved=True)
    elif fault=='missing_marker':text=''
    elif fault=='duplicate':text+=text
    elif fault=='success_marker':text+='TRACK ACTUAL ORIGINAL/CURRENT137/362 NATIVE FIXTURE COMPLETE\n'
    if fault is None:assert recovery.failed_authority(spec,whole,failure,guard,text,{})==dict(SM_TK_Test=1)
    else:
        with pytest.raises(ValueError):recovery.failed_authority(spec,whole,failure,guard,text,{})


def test_guarded_data_verifier_has_no_process_or_cleanup_execution():
    tree=ast.parse(Path(recovery.__file__).read_text())
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='validate')
    forbidden={'subprocess','host_state','guard_binding','retire_owned','strict_cleanup','import_mesh','unlink','rmdir','rmtree'}
    assert not any(isinstance(n,ast.Name) and n.id in forbidden or isinstance(n,ast.Attribute) and n.attr in forbidden for n in ast.walk(node))
    outputs=[ast.literal_eval(n.value) for n in ast.walk(node) if isinstance(n,ast.keyword) and n.arg in ('failed_old_whole','observation_validation_only','cleanup_pending','complete','native_complete')]
    assert outputs==[255,True,True,False,False]


@pytest.mark.parametrize('fault',[None,'changed','linked','wrong_owner','duplicate','current_changed'])
def test_saved_archives_are_exact_and_current_package_reads_are_explicit(tmp_path,fault):
    import hashlib
    spec=dict(content=str(tmp_path/'Content'),package=ROOT.removesuffix('/Library'),output=str(tmp_path/'old-output'))
    source=Path(spec['content'])/spec['package'].removeprefix('/Game/')/'Library/SM_TK_Test.uasset'
    data=b'actual saved package bytes';digest=hashlib.sha256(data).hexdigest()
    source.parent.mkdir(parents=True);source.write_bytes(data)
    archive=Path(spec['output'])/'saved-packages/original'/(hashlib.sha256(str(source).encode()).hexdigest()+source.suffix)
    archive.parent.mkdir(parents=True);archive.write_bytes(data)
    row=dict(path=str(source),sha256=digest);descriptor=dict(saved_packages=[row])
    if fault=='changed':archive.write_bytes(b'changed archive')
    elif fault=='linked':archive.unlink();archive.symlink_to(source)
    elif fault=='wrong_owner':row['path']=str(source.with_name('SM_TK_Foreign.uasset'))
    elif fault=='duplicate':descriptor['saved_packages'].append(row)
    elif fault=='current_changed':source.write_bytes(b'changed current bytes')
    if fault is None or fault=='current_changed':
        rebuilt,saved=recovery.rebuild_saved_archives(descriptor,'SM_TK_Test',spec)
        assert rebuilt['saved_packages']==saved==[dict(path=str(archive),sha256=digest)]
        assert descriptor['saved_packages']==[row]  # Never rewrite the retained descriptor.
        if fault=='current_changed':
            with pytest.raises(ValueError):recovery.rebuild_saved_archives(descriptor,'SM_TK_Test',spec,check_current_packages=True)
    else:
        with pytest.raises((ValueError,FileNotFoundError)):recovery.rebuild_saved_archives(descriptor,'SM_TK_Test',spec)


@pytest.mark.parametrize('fault',[None,'data_changed','new_whole255','carry_without_source'])
def test_host_finalizer_binds_new_report_sha_and_never_accepts_failed_verifier(tmp_path,monkeypatch,fault):
    from atelier.atomic_files import atomic_json
    spec=tmp_path/'old-spec.json';atomic_json(spec,dict(source='frozen'))
    state=dict(source_head=recovery.OLD_HEAD,native={'actual':'compiled inventory'})
    plan=tmp_path/'plan.json';atomic_json(plan,dict(metadata=dict(spec=recovery.binding(spec)),validation_inputs={},host_before=state))
    plan_row=recovery.binding(plan)
    data=tmp_path/'data.json';body=dict(plan=plan_row,failed_old_whole=255,observation_validation_only=True,
        cleanup_pending=True,complete=False,native_complete=False,native=state['native'],source_input_identity_carry=False)
    if fault=='carry_without_source':body['source_input_identity_carry']=True
    atomic_json(data,body);data_sha=recovery.proof.sha(data)
    guard=tmp_path/'new-guard';guard.mkdir()
    atomic_json(guard/'memory-health-tree.json',dict(state='child_exited',cleanup_complete=True,processes=[],footprint_bytes=0))
    (guard/'stdout.log').write_text('TRACK07 OBSERVATION DATA VALIDATION COMPLETE '+plan_row['sha256']+' '+data_sha)
    whole=tmp_path/'new-whole.json';atomic_json(whole,dict(exit_code=255 if fault=='new_whole255' else 0))
    if fault=='data_changed':atomic_json(data,dict(body,tampered=True))
    monkeypatch.setattr(recovery,'host_state',lambda _:state)
    output=tmp_path/'new-host.json'
    if fault is None:
        recovery.finalize(plan,plan_row['sha256'],data,guard,whole,output)
        result=json.loads(output.read_text())
        assert result['failed_old_whole']==255 and result['cleanup_pending'] and result['observation_validation_only']
        assert not result['native_complete'] and not result['original_current_equivalence'] and not result['normal_task_reuse']
    else:
        with pytest.raises(ValueError):recovery.finalize(plan,plan_row['sha256'],data,guard,whole,output)
        assert not output.exists()



def carry_fixture(tmp_path):
    import hashlib
    runtime=dict(meshes={});spec=dict(schema=1,original_track=str(tmp_path/'original'),current_track=str(tmp_path/'current'),inputs={})
    digest=hashlib.sha256(b'exact GLB').hexdigest()
    for index in range(137):
        name=f'SM_TK_Test_{index:03}';levels=3 if index<88 else 2
        runtime['meshes'][name]=dict(lods=[f'meshes/{name}_LOD{level}.glb'for level in range(levels)],
            screen_sizes=[1.,.5,.1][:levels],materials=['MI_TK_Bank'])
        for phase in ('original','current'):
            for relative in runtime['meshes'][name]['lods']:spec['inputs'][str(Path(spec[phase+'_track'])/relative)]=digest
    return spec,runtime


@pytest.mark.parametrize('fault',[None,'one_glb_vector','vector_omission','runtime_value','missing_mesh','missing_lod','runtime_type'])
def test_exact137_362_input_vectors_refuse_partial_or_changed_carry(tmp_path,fault):
    import copy
    spec,runtime=carry_fixture(tmp_path);current=copy.deepcopy(runtime)
    key=next(iter(spec['inputs']))
    if fault=='one_glb_vector':spec['inputs'][key]='a'*64
    elif fault=='vector_omission':spec['inputs'].pop(key)
    elif fault=='runtime_value':current['new_unobserved_runtime_field']=True
    elif fault=='missing_mesh':current['meshes'].pop(next(iter(current['meshes'])))
    elif fault=='missing_lod':current['meshes'][next(iter(current['meshes']))]['lods'].pop()
    elif fault=='runtime_type':runtime['typed_field']=1;current['typed_field']=True
    if fault is None:
        vector=recovery.input_identity_vectors(spec,runtime,current)
        assert len(vector['rows'])==362 and vector['logical_meshes']==137
    else:
        with pytest.raises(ValueError):recovery.input_identity_vectors(spec,runtime,current)


def test_declared_vector_equality_does_not_replace_actual_glb_byte_validation(tmp_path):
    import hashlib
    spec,runtime=carry_fixture(tmp_path)
    first=next(iter(spec['inputs']));path=Path(first);path.parent.mkdir(parents=True);path.write_bytes(b'changed actual GLB')
    # The declared vectors alone still agree; the independent actual-byte gate refuses.
    assert recovery.input_identity_vectors(spec,runtime,runtime)['authored_lods']==362
    one=dict(schema=1,inputs={first:hashlib.sha256(b'exact GLB').hexdigest()})
    with pytest.raises(ValueError):recovery.proof.bound_inputs(one)


@pytest.mark.parametrize('fault',[None,'owner_byte','owner_missing','cpp_byte'])
def test_current_source_binding_is_exact_scoped_owner_bytes(tmp_path,fault):
    import hashlib
    observed=tmp_path/'observed';current=tmp_path/'current';inputs={};paths={}
    for relative in ('unreal/Scripts/import_belmonte_track.py','unreal/Scripts/import_belmonte.py',
                     'unreal/Source/Yorimichi/BelmonteTrack.cpp','unreal/Source/Yorimichi/BelmonteTrack.h'):
        old=observed/relative;new=current/'games/yorimichi'/relative
        for path in (old,new):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(('actual '+relative).encode())
        inputs[str(old)]=hashlib.sha256(old.read_bytes()).hexdigest();paths[Path(relative).name]=new
    spec=dict(inputs=inputs,importer=str(observed/'unreal/Scripts/import_belmonte_track.py'),
              material_owner=str(observed/'unreal/Scripts/import_belmonte.py'))
    if fault=='owner_byte':paths['import_belmonte_track.py'].write_bytes(b'changed owner')
    elif fault=='owner_missing':paths['import_belmonte.py'].unlink()
    elif fault=='cpp_byte':paths['BelmonteTrack.cpp'].write_bytes(b'changed scoped runtime')
    if fault is None:
        bindings=recovery.current_owner_bindings(spec,current)
        assert len(bindings)==4 and not any('NativeAtomicEquivalence' in key for key in bindings)
    else:
        with pytest.raises((ValueError,FileNotFoundError)):recovery.current_owner_bindings(spec,current)
