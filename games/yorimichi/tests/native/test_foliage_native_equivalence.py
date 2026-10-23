"""Hermetic foliage receiving/source mapping faults. These tests never launch native tools."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types

import numpy as np
import pytest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import foliage_native_equivalence as proof
from prepare_foliage_native_equivalence import freeze_current_fbx,freeze_textures,source_control
from atelier import mesh_ir

PACKAGE='/Game/AtelierValidation/Foliage_0123456789ab'


def manifests():
    result={}
    for name in proof.owner_names():
        levels=6 if name.startswith('Tree_')else 3
        result[name]=dict(screen_sizes=[1/(k+1)for k in range(levels)],triangles=[3]*levels,
            collision='complex'if name.startswith('Tree_')else'default',import_trunk_collision=False,materials=['Bark'])
    return result


def test_complete_native_census_distinguishes_assembled_lods_sources_and_unused_seed():
    data=manifests();rows=proof.inventory(data)
    assert len(rows)==84 and sum(v['lods']for v in rows.values())==150
    assert sum(v['placed']for v in rows.values())==18 and sum(not v['placed']for v in rows.values())==66
    assert sum(v['query_only']for v in rows.values())==10 and not any(n.endswith('_Seed')for n in rows)
    assert sum(len(d['screen_sizes'])for d in data.values())==84


@pytest.mark.parametrize('bad',['missing','foreign','wrong_lods','bad_triangles','missing_field'])
def test_manifest_census_refuses_missing_changed_and_foreign_owners(bad):
    data=manifests();name=next(iter(data))
    if bad=='missing':data.pop(name)
    elif bad=='foreign':data['Tree_Foreign']=data.pop(name)
    elif bad=='wrong_lods':data[name]['screen_sizes'].pop()
    elif bad=='bad_triangles':data[name]['triangles'][0]=0
    else:data[name].pop('collision')
    with pytest.raises(ValueError):proof.inventory(data)


@pytest.mark.parametrize('name',proof.MAPPED)
def test_every_real_source_maps_only_exhaustive_literals_and_reverses_exact_full_ast(name):
    relative,digest=proof.MAPPED[name];path=proof.GAME/relative
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    original=ast.parse(path.read_bytes());mapped=proof.mapped_tree(name,proof.GAME,PACKAGE)
    changed=[]
    for node in ast.walk(mapped):
        if not isinstance(node,ast.Constant)or not isinstance(node.value,str):continue
        if node.value.startswith(PACKAGE+'/Japan'):
            changed.append(node.value);node.value='/Game/Japan'+node.value.removeprefix(PACKAGE+'/Japan')
        elif node.value.startswith(PACKAGE+'/SeeThrough'):
            changed.append(node.value);node.value='/Game/SeeThrough'+node.value.removeprefix(PACKAGE+'/SeeThrough')
        elif node.value==PACKAGE.removeprefix('/Game/')+'/Japan/Assets':
            changed.append(node.value);node.value='Japan/Assets'
        assert not node.value.startswith('/Game/AtelierValidation')
    if name in('shared_materials','import_foliage'):mapped.body.append(original.body[-1])
    assert changed and ast.dump(mapped)==ast.dump(original)


def test_changed_source_unknown_mapping_and_foreign_namespace_refuse(tmp_path):
    relative,_=proof.MAPPED['import_foliage'];path=tmp_path/relative;path.parent.mkdir(parents=True)
    path.write_bytes((proof.GAME/relative).read_bytes()+b'\nextra_native_behavior=True\n')
    with pytest.raises(ValueError):proof.mapped_tree('import_foliage',tmp_path,PACKAGE)
    with pytest.raises(ValueError):proof.mapped_tree('unknown',proof.GAME,PACKAGE)
    with pytest.raises(ValueError):proof.mapped_tree('import_foliage',proof.GAME,'/Game/Japan')


def test_real_mapped_header_validator_reads_only_its_exclusive_package_path(tmp_path):
    module=types.ModuleType('mapped_header');tree=proof.mapped_tree('foliage_package_repair',proof.GAME,PACKAGE)
    exec(compile(tree,'actual package-header validator','exec'),module.__dict__)
    content=tmp_path/'Content';foreign=content/'Japan/Assets/Tree_Broad_A.uasset';foreign.parent.mkdir(parents=True)
    foreign.write_bytes(b'foreign invalid package must stay unread')
    module.require_valid_or_missing(content,'Tree_Broad_A')
    own=content/PACKAGE.removeprefix('/Game/')/'Japan/Assets/Tree_Broad_A.uasset';own.parent.mkdir(parents=True)
    own.write_bytes(b'invalid fixture')
    with pytest.raises(RuntimeError):module.require_valid_or_missing(content,'Tree_Broad_A')
    assert foreign.read_bytes()==b'foreign invalid package must stay unread'


def packet(tmp_path,matrix=None,key='Tree_Broad_A'):
    piece=dict(positions=[[0,0,0],[2,0,0],[0,2,0]],faces=[[0,1,2]],normals=[[0,0,1]]*3,
        materials=[0],smooth=[True],uvs=[('UVMap',[[0,0],[1,0],[0,1]])],colours=[])
    payload=mesh_ir.encode(piece,key=key,slots=['Bark'],matrix=np.eye(4).tolist()if matrix is None else matrix,options={})
    path=tmp_path/'source.npz';path.write_bytes(payload);return path


def test_controls_derive_actual_transformed_source_geometry_and_current_collision_policy(tmp_path):
    matrix=np.eye(4);matrix[:3,3]=[10,20,30];path=packet(tmp_path,matrix.tolist())
    tree=source_control('Tree_Broad_A',dict(query_only=True,collision='complex'),path)
    assert {r['kind']for r in tree}=={'ray_positive','ray_negative','capsule_positive','capsule_negative'}
    ray=next(r['input']for r in tree if r['kind']=='ray_positive')
    center=(np.asarray(ray['start'])+ray['end'])/2
    assert center.tolist()==pytest.approx([1066.6666666667,-2066.6666666667,3000])
    bush=source_control('Bush_Green_A',dict(query_only=False,collision='default'),packet(tmp_path,matrix.tolist(),key='Bush_Green_A'))
    assert {r['kind']for r in bush}=={'ray_negative','capsule_negative'}
    assert bush[0]['input']==ray  # Negative checks lie on real geometry, rather than safely outside it.


def controls(data):
    rows={}
    for name,entry in proof.inventory(data).items():
        rows[name]=[]
        for item in proof.query_plan(name,entry):
            query=dict(start=[0.,0.,1.],end=[0.,0.,-1.],channel='Pawn',trace_complex=item['mode']=='complex')
            if item['kind'].startswith('capsule'):query.update(radius_cm=.1,half_height_cm=.1,orientation=[0.,0.,0.,1.])
            rows[name].append(dict(id=item['id'],kind=item['kind'],input=query))
    return rows

@pytest.mark.parametrize('fault',['missing_source','positive_nocollision','no_tree_positive','nan','bad_capsule','wrong_channel'])
def test_current_policy_controls_refuse_false_coverage(fault):
    data=manifests();rows=controls(data);proof.validate_controls(rows,data)
    tree=next(n for n in rows if n.startswith('Tree_')and'_LOD'not in n)
    source=next(n for n in rows if'_LOD'in n)
    if fault=='missing_source':rows.pop(source)
    elif fault=='positive_nocollision':rows[source][0]['kind']='ray_positive'
    elif fault=='no_tree_positive':rows[tree]=[r for r in rows[tree]if r['kind'].endswith('negative')]
    elif fault=='nan':rows[tree][0]['input']['start'][0]=float('nan')
    elif fault=='bad_capsule':rows[tree][1]['input']['radius_cm']=-1
    else:rows[tree][0]['input']['channel']='Visibility'
    with pytest.raises(ValueError):proof.validate_controls(rows,data)


def test_actual_unreal_imports_and_shader_owner_definitions_are_stdlib_only(tmp_path):
    code=r'''
import importlib.abc,pathlib,sys,types
native=pathlib.Path(sys.argv[1]);sys.path.insert(0,str(native))
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname=='atomic_equivalence'or fullname.split('.')[0]in('numpy','mesh_ir')or fullname=='atelier.mesh_ir':raise ModuleNotFoundError(fullname)
sys.meta_path.insert(0,Block())
u=types.ModuleType('unreal');u.log=print;u.EditorAssetLibrary=types.SimpleNamespace();u.MaterialEditingLibrary=types.SimpleNamespace()
u.AssetToolsHelpers=types.SimpleNamespace(get_asset_tools=lambda:object())
u.AssetRegistryHelpers=types.SimpleNamespace(get_asset_registry=lambda:object())
u.CustomMaterialOutputType=types.SimpleNamespace(CMOT_FLOAT1=object())
u.MaterialProperty=types.SimpleNamespace(MP_OPACITY_MASK=object());sys.modules['unreal']=u
import foliage_native_equivalence as p
spec=dict(source=str(p.GAME.parents[1]),receiving=str(p.GAME.parents[1]),phase='original',package='/Game/AtelierValidation/Foliage_0123456789ab',
 original_data=sys.argv[2],textures=sys.argv[2])
with p.production_modules(spec)as modules:
 import atomic_equivalence_capture as capture
 assert callable(modules['shared_materials'].main)and callable(modules['shared_materials'].wind_graph)
 assert callable(modules['import_foliage'].main)and callable(modules['import_foliage_lods'].apply_lods)
 assert all(path.startswith(spec['package']+'/')for path in modules['asset_catalog'].shared_packages())
 assert callable(capture.capture)
assert 'numpy'not in sys.modules and'atomic_equivalence'not in sys.modules
print('ACTUAL FOLIAGE OWNER/SHADER IMPORT CLOSURE VERIFIED')
'''
    result=subprocess.run([sys.executable,'-I','-S','-c',code,str(HERE),str(tmp_path)],cwd=tmp_path,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'ACTUAL FOLIAGE OWNER/SHADER IMPORT CLOSURE VERIFIED'in result.stdout


def compared_records(data):
    result={'original':{},'current':{}}
    for phase in result:
        for name,item in proof.inventory(data).items():
            probes=[]
            for row in controls(data)[name]:
                probes.append(dict(row,hit=None if row['kind'].endswith('negative')else{'blocking':True}))
            result[phase][name]=dict(policy_scope='fixture',bounds=b'exact bounds',
                render_lods={k:('actual native corners',)for k in range(item['lods'])},
                source_lods={k:('actual saved corners',)for k in range(item['lods'])},
                cooked=('actual cooked',),hulls=(),policy=b'exact policy',settings=b'exact settings',
                source_presence={k:{True}for k in range(item['lods'])},probes=dict(controls=probes))
    return result


@pytest.mark.parametrize('fault',[*proof.FIELDS,'bounds','queries','missing_source','missing_lod','failed_negative','promoted_scope','both_missing_saved_md'])
def test_aggregate_comparison_propagates_every_strict_native_field_and_scope(monkeypatch,fault):
    data=manifests();rows=compared_records(data);name=next(iter(rows['current']));row=rows['current'][name]
    # Generic raw validators have their own real-record faults; this isolates aggregation, never native admission.
    monkeypatch.setattr(proof,'native_raw_set',lambda record,logical:record)
    monkeypatch.setattr(proof,'component_collision',lambda record,item:None)
    monkeypatch.setattr(proof,'whole_bounds',lambda record:record['bounds'])
    result=proof.compare(rows,data)
    assert result['native_pages']==150 and result['source_lod_packages']==66
    assert result['complete']is False and result['production_runtime_complete']is False and result['normal_native_reuse']is False
    if fault=='bounds':row['bounds']=b'changed actual sphere/box'
    elif fault=='queries':row['probes']['controls'][0]['input']['start'][0]+=1
    elif fault=='missing_source':rows['current'].pop(next(n for n in rows['current']if'_LOD'in n))
    elif fault=='missing_lod':row['render_lods'].pop(0)
    elif fault=='failed_negative':
        for phase in rows:
            rows[phase][name]['probes']['controls'][-1]['hit']={'blocking':True}
    elif fault=='promoted_scope':row['policy_scope']='production'
    elif fault=='both_missing_saved_md':
        for phase in rows:
            rows[phase][name]['source_presence'][0]={False}
            rows[phase][name]['source_lods'].pop(0)
    else:row[fault]=('different native evidence',)
    with pytest.raises(ValueError):proof.compare(rows,data)


@pytest.mark.parametrize('fault',['missing','link','parent_link','directory'])
def test_actual_twenty_two_texture_preflight_refuses_before_any_copy(tmp_path,fault):
    producer=tmp_path/'producer';folder=producer/'build/yorimichi/textures';folder.mkdir(parents=True)
    names=proof.catalog_literal('TEXTURES')
    for name in names:(folder/name).write_bytes(('genuine fixture '+name).encode())
    last=folder/names[-1];last.unlink()
    if fault=='link':
        foreign=tmp_path/'foreign';foreign.write_bytes(b'not an admitted source');last.symlink_to(foreign)
    elif fault=='directory':last.mkdir()
    elif fault=='parent_link':
        last.write_bytes(b'present');saved=folder.with_name('retained');folder.rename(saved);folder.symlink_to(saved,target_is_directory=True)
    output=tmp_path/'independent-copy'
    def bind(path):proof.check_input(path,proof.sha(path));return path
    with pytest.raises((ValueError,FileNotFoundError,IsADirectoryError)):freeze_textures(producer,bind)
    assert not output.exists() and not output.is_symlink()


def test_source_stage_closure_and_owner_execution_precede_no_bypass():
    stage=ast.parse((HERE/'prepare_foliage_native_equivalence.py').read_text())
    prepare=next(n for n in stage.body if isinstance(n,ast.FunctionDef)and n.name=='prepare')
    writes=[n.lineno for n in ast.walk(prepare)if isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)and n.func.attr=='mkdir']
    checks=[n.lineno for n in ast.walk(prepare)if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='freeze_textures']
    assert max(checks)<min(writes)
    native=ast.parse(Path(proof.__file__).read_text());run=next(n for n in native.body if isinstance(n,ast.FunctionDef)and n.name=='run_native')
    assert sum(isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)and n.func.attr=='main'for n in ast.walk(run))==2
    assert not any(isinstance(n,ast.Attribute)and n.attr in('legacy_options_match','_source_mesh')for n in ast.walk(run))


def test_simple_and_complex_paths_follow_actual_disabled_trunk_trace_flags(tmp_path):
    path=packet(tmp_path,key='Tree_Ginkgo')
    default=source_control('Tree_Ginkgo',dict(query_only=True,collision='default'),path)
    assert len(default)==6
    assert all(row['kind'].endswith('negative')for row in default if not row['input']['trace_complex'])
    complex_as_simple=source_control('Tree_Broad_A',dict(query_only=True,collision='complex'),packet(tmp_path))
    assert len(complex_as_simple)==8
    assert sum(row['kind'].endswith('positive')for row in complex_as_simple)==4
    assert len(source_control('Bush_Green_A',dict(query_only=False,collision='default'),packet(tmp_path,key='Bush_Green_A')))==4


@pytest.mark.parametrize('fault',['flag','object','pawn','camera'])
def test_actual_component_collision_flags_cannot_be_substituted_by_equal_misses(fault):
    item=dict(query_only=True,placed=True)
    value=dict(collision_enabled=1,object_channel=0,responses=[2,2,2,2,0])
    proof.validate_component_policy(value,item)
    if fault=='flag':value['collision_enabled']=0
    elif fault=='object':value['object_channel']=1
    elif fault=='pawn':value['responses'][2]=0
    else:value['responses'][4]=2
    with pytest.raises(ValueError):proof.validate_component_policy(value,item)
    proof.validate_component_policy(dict(collision_enabled=0,object_channel=0,responses=[2,2,2,2,2]),dict(query_only=False,placed=False))


@pytest.mark.parametrize('name',['ATELIER_BUILD_TASK','ATELIER_MESH_REUSE_NONCE'])
def test_fixture_never_inherits_or_manufactures_task_receipt_context(name):
    proof.require_fixture_context({})
    with pytest.raises(ValueError):proof.require_fixture_context({name:'real normal task context'})


def test_optional_engine_material_companions_are_bound_as_absent_not_ignored(tmp_path):
    path=tmp_path/'actual-shader.uasset';path.write_bytes(b'actual bound function')
    absent=tmp_path/'actual-shader.uexp'
    spec=dict(schema=1,inputs={str(path):proof.sha(path)},absent_inputs=[str(absent)])
    proof.bound_inputs(spec);absent.write_bytes(b'new data changes actual shader input')
    with pytest.raises(ValueError):proof.bound_inputs(spec)


@pytest.mark.parametrize('fault',[None,'changed','missing','linked'])
def test_current_receiving_binds_completed_producer_fbx_not_control_copy(tmp_path,fault):
    producer=tmp_path/'producer';owner='Tree_Broad_A';key=owner+'_LOD1'
    path=producer/'build/yorimichi/foliage'/owner/(key+'.fbx');path.parent.mkdir(parents=True)
    control=tmp_path/'control.fbx';control.write_bytes(b'validated original FBX bytes')
    path.write_bytes(control.read_bytes());digest=proof.sha(control)
    rows={key:dict(actual_fbx=dict(path=str(control),sha256=digest))}
    if fault=='changed':path.write_bytes(b'different real producer output')
    elif fault=='missing':path.unlink()
    elif fault=='linked':path.unlink();path.symlink_to(control)
    def bind(actual,expected):
        proof.check_input(actual,expected);return actual
    if fault is not None:
        with pytest.raises((ValueError,FileNotFoundError)):freeze_current_fbx(producer,rows,[owner],bind)
    else:
        assert freeze_current_fbx(producer,rows,[owner],bind)=={key:path}
    assert control.read_bytes()==b'validated original FBX bytes'


def producer_collection(tmp_path):
    from argparse import Namespace
    producer=tmp_path/'producer';root=producer/'build/yorimichi/foliage-proof/ordinary';root.mkdir(parents=True)
    keys={f'Owner_{k}'for k in range(102)};steps=[];guards=[]
    def put(path,value):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value));return dict(path=str(path),sha256=proof.sha(path))
    for index,(key,kind) in enumerate((key,kind)for key in sorted(keys)for kind in('source','export')):
        step='world.foliage.'+kind+'.'+key;batch=f'{index+1:032x}'
        folder=producer/'build/yorimichi/logs'/('batch.'+batch+'.guard')
        steps.append(dict(name=step,batch=batch,fingerprint='a'*64))
        guard=dict(state='child_exited',cleanup_complete=True,processes=[],footprint_bytes=0,
            owner=index+1,owner_started=index+1000,late_reporters=dict(unresolved=[],unresolved_pids=[],scan_failed=False))
        observation=dict(schema=1,cleanup_and_capacity_close=True,root=[guard['owner'],guard['owner_started']])
        guards.append(dict(step=step,receipt=put(folder/'memory-health-tree.json',guard),
            observation=put(folder/'successful-tree-observation.json',observation),stdout=put(folder/'stdout.log',{'actual':'completed'})))
    steps.extend(dict(name=f'world.other_{k}',batch=None,fingerprint='b'*64)for k in range(59))
    steps.append(dict(name='world.foliage_lods',batch=None,fingerprint='c'*64))
    head='d'*40
    snapshot=dict(checkout=str(producer),head=head,target='world.foliage_lods',steps=steps,guards=guards)
    commands={name:dict(command='actual command '+name,exit_code=0,steps=264 if name!='receiver'else 39)
        for name in('producer','noop','receiver')}
    handoff=dict(head=head,source_clean=True,commands=copy.deepcopy(commands),artifacts=[])
    def seal():
        handoff['artifacts']=[put(root/'whole-results.json',commands),put(root/'producer-after-noop.json',snapshot)]
        put(root/'handoff.json',handoff)
    seal()
    args=Namespace(producer=producer,producer_handoff=root/'handoff.json',producer_whole=None,producer_guard=None)
    return args,head,keys,snapshot,commands,handoff,seal


@pytest.mark.parametrize('fault',[None,'head','nonzero','commands','missing_guard','wrong_sha','pending','unresolved',
    'unknown_step','omitted_step','duplicate_step','snapshot_head','target','step_inventory','observation','observation_root','alias_guard'])
def test_sealed_collection_binds_all204_actual_guard_steps_before_staging(tmp_path,fault):
    from prepare_foliage_native_equivalence import producer_evidence,producer_guard_membership
    args,head,keys,snapshot,commands,handoff,seal=producer_collection(tmp_path)
    if fault=='head':handoff['head']='e'*40
    elif fault=='nonzero':commands['producer']['exit_code']=1;handoff['commands']=copy.deepcopy(commands)
    elif fault=='commands':handoff['commands']['producer']['command']='different caller'
    elif fault=='missing_guard':snapshot['guards'].pop()
    elif fault=='wrong_sha':snapshot['guards'][0]['receipt']['sha256']='0'*64
    elif fault in('pending','unresolved','observation','observation_root'):
        kind='receipt'if fault in('pending','unresolved')else'observation'
        row=snapshot['guards'][0][kind];path=Path(row['path']);value=json.loads(path.read_bytes())
        if fault=='pending':value['cleanup_complete']=False
        elif fault=='unresolved':value['late_reporters']['unresolved_pids']=[123]
        elif fault=='observation':value['cleanup_and_capacity_close']=False
        else:value['root']=[999,999]
        path.write_text(json.dumps(value));row['sha256']=proof.sha(path)
    elif fault=='unknown_step':snapshot['guards'][0]['step']='world.foliage.source.Foreign'
    elif fault=='omitted_step':keys.remove(next(iter(keys)))
    elif fault=='duplicate_step':snapshot['guards'][0]['step']=snapshot['guards'][1]['step']
    elif fault=='snapshot_head':snapshot['head']='e'*40
    elif fault=='target':snapshot['target']='world.other'
    elif fault=='step_inventory':snapshot['steps'][-1]['name']=snapshot['steps'][0]['name']
    elif fault=='alias_guard':snapshot['guards'][1]['receipt']=snapshot['guards'][0]['receipt']
    seal();bound={}
    def bind(path,digest=None):
        path=Path(path).absolute();digest=proof.sha(path)if digest is None else digest
        proof.check_input(path,digest);bound[str(path)]=digest;return path
    def check():
        observed=producer_evidence(args,head,bind)
        producer_guard_membership(observed,keys,args.producer,bind)
    if fault:
        with pytest.raises((ValueError,FileNotFoundError)):check()
    else:
        check()
        assert len(bound)==3+204*3
        assert all(str(Path(row['receipt']['path']))in bound for row in snapshot['guards'])
    assert not (tmp_path/'fixture-output').exists()


def test_existing_singular_producer_mode_and_mode_exclusivity(tmp_path):
    from argparse import Namespace
    from prepare_foliage_native_equivalence import producer_evidence
    whole=tmp_path/'whole.json';whole.write_text('{"exit_code":0}')
    guard=tmp_path/'guard.json';guard.write_text(json.dumps(dict(state='child_exited',cleanup_complete=True,processes=[],footprint_bytes=0)))
    args=Namespace(producer_whole=whole,producer_guard=guard,producer_handoff=None)
    assert producer_evidence(args,'unused',lambda path:Path(path)) is None
    args.producer_handoff=tmp_path/'handoff.json'
    with pytest.raises(ValueError,match='Select producer'):producer_evidence(args,'unused',lambda path:Path(path))
    args.producer_handoff=None;args.producer_guard=None
    with pytest.raises(ValueError,match='Select producer'):producer_evidence(args,'unused',lambda path:Path(path))
