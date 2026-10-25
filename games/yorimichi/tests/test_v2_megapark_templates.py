"""Actual generated MegaPark membership, existing FileSet/derived ABI and consumed native audit."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import numpy as np
import pytest
from atelier.build_v2 import file_groups,recipe_job
import test_v2_megapark_units as old

ROOT=old.ROOT;GAME=old.GAME
sys.path[:0]=[str(GAME),str(GAME/'world'),str(GAME/'world/regions')]
templates=old.load('games/yorimichi/v2_megapark_templates.py','mp_dynamic_templates_test')
projection=old.load(templates.BODY,'mp_dynamic_members_test');park=templates.park
body=old.load(park.SCRIPT,'mp_dynamic_native_test')


@pytest.fixture(scope='module')
def rows():return old.rows.__wrapped__()


@pytest.fixture(scope='module')
def bundle(rows):return templates.megapark_templates(rows,checkout=ROOT)


def test_actual_cold_bundle_has_fixed_texture_owners_and_generated_author_template(rows,bundle):
    assert len(bundle['units'])==825 and len(bundle['packages'])==413 and len(bundle['templates'])==1
    by_id={u['id']:u for u in bundle['units']}
    assert sum(u['id'].startswith('unreal.megapark.texture.raw.') for u in bundle['units'])==409
    roles=[u for u in bundle['units'] if u['id'].startswith('unreal.megapark.texture.T_') and u['params'].get('args',{}).get('action')=='texture']
    assert len(roles)==405 and all(u['inputs'][1]['source']['kind']=='group_member' for u in roles)
    assert all(u['op']['kind']=='recipe.python' and u['output_groups'][0]['encoding']=='file_set' for u in bundle['units'] if u['id'] in (templates.ROLES,templates.MATERIALS))
    template=bundle['templates'][0];author=template['followers'][0]['unit']
    assert template['derive_payload'] is False and template['op']['kind']=='recipe.python'
    assert author['op']['kind']=='unreal.author' and author['outputs'][0]['class']=='MaterialInstance' and author['outputs'][0]['destination']=='checkout'
    assert author['outputs'][0]['logical_path']=='/Game/MegaPark/Materials/$piece'
    assert len(author['params']['args']['texture_inputs'])==405 and set(author['params']['args']['parents'])=={'0','1','2'}
    assert bundle['material_items']['derived_items']['templates'][0]['follower']==0
    assert bundle['audit_unit'] in bundle['required_targets'] and bundle['module_requirements'][templates.PREFIX]
    geometry=old.geometry.__wrapped__(rows)
    extended=park.attach_followers(geometry,{**bundle['packages'],'material_items':bundle['material_items']},rows=rows,checkout=ROOT)
    for t in extended['templates']:
        if not t['unit_prefix'].startswith('world.megapark.export.') or t['unit_prefix'].endswith('.SM_MP_ImportSeed'):continue
        finish=t['followers'][1]['unit'];assert finish['params']['args']['audit'] is True
        assert [o['id'] for o in finish['outputs']]==['asset','geometry','report']
        assert finish['params']['args']['materials']==bundle['material_items']
    audit=by_id[bundle['audit_unit']]
    assert audit['params']['recipe']['outputs'][0]['path'].endswith('/import-report.json')
    assert any(i['source'].get('unit')=='unreal.megapark.level' for i in audit['inputs'])


def case(tmp_path):
    source=tmp_path/'source';source.mkdir();textures={}
    for tid in ('0xaa','0xbb'):
        png=tid+'.png';raw=tid.encode();(source/png).write_bytes(raw);textures[tid]={'png':png,'sha256':hashlib.sha256(raw).hexdigest()}
    source_map=source/'map.json';source_map.write_text(json.dumps({'textures':textures}))
    build=tmp_path/'build.json';report={'source_sha256':hashlib.sha256(source_map.read_bytes()).hexdigest(),'textures':textures,
        'materials':{'0xa1':{'alpha_mode':0,'retail_texture_ids':{'diffuse':'0xaa','lightmap':'0xbb'},'retail_parameters':{'detailNormalUVScale':['4']}}}}
    build.write_text(json.dumps(report));restyle=tmp_path/'restyle';restyle.mkdir();(restyle/'textures.json').write_text(json.dumps({'textures':{},'lightmaps':{'0xbb':2.5}}))
    return build,restyle,source_map


def test_actual_spec_roles_fileset_and_selected_recipe_binding(tmp_path):
    build,restyle,source=case(tmp_path);out=tmp_path/'members'
    projection.project(build,restyle,source,out,'materials',())
    group=file_groups.write_file_set(out,tmp_path/'group',parent='MegaParkMaterials',selectors=['*.json'])
    assert [r['name'] for r in group['pieces']]==['MI_a1']
    spec=json.loads((out/'MI_a1.json').read_text());assert spec['material']['retail_parameters']['detailNormalUVScale']==['4'] and spec['lightmap_norm']==2.5
    roles=tmp_path/'roles';projection.project(build,restyle,source,roles,'roles',())
    assert json.loads((roles/'T_bb.json').read_text())=={'tid':'0xbb','roles':['lightmap']}
    view=tmp_path/'view';path=view/templates.BODY;path.parent.mkdir(parents=True);path.write_bytes((ROOT/templates.BODY).read_bytes())
    selected=view/'selected';selected.mkdir();(selected/'MI_a1.json').write_bytes((out/'MI_a1.json').read_bytes())
    binding=templates._call(ROOT,'copy_member',(ROOT/'selected/MI_a1.json',ROOT/'member.json'))['call']
    recipe_job.bind(binding,view)()
    assert (view/'member.json').read_bytes()==(out/'MI_a1.json').read_bytes()


@pytest.mark.parametrize('damage',['png','role','tid','alpha','restyle','alias'])
def test_corrupt_or_speculative_members_refuse_before_output(tmp_path,damage):
    build,restyle,source=case(tmp_path);data=json.loads(build.read_text())
    if damage=='png':(source.parent/'0xaa.png').write_bytes(b'changed')
    elif damage=='role':data['materials']['0xa1']['retail_texture_ids']['unknown']='0xaa'
    elif damage=='tid':data['materials']['0xa1']['retail_texture_ids']['diffuse']='0xunknown'
    elif damage=='alpha':data['materials']['0xa1']['alpha_mode']=3
    elif damage=='restyle':(restyle/'textures.json').write_text(json.dumps({'textures':{'0xaa':{'png':'missing.png','sha256':'0'*64}},'lightmaps':{}}))
    else:data['materials']['0xA1']=deepcopy(data['materials']['0xa1'])
    build.write_text(json.dumps(data));out=tmp_path/'members'
    with pytest.raises(ValueError):projection.project(build,restyle,source,out,'materials',())
    assert not out.exists()


def test_dynamic_instance_uses_only_own_actual_spec_and_original_parameters(tmp_path,monkeypatch):
    assets={};defaults,inputs=old.defaults(assets);state,_=old.editor(tmp_path,monkeypatch,assets)
    parent=old.Material('/Game/MegaPark/Materials/M_RetailOpaque');rock=old.Texture('/Game/MegaPark/Textures/T_2c70170a001d0133');light=old.Texture('/Game/MegaPark/Textures/T_bb')
    assets.update({a.path:a for a in (parent,rock,light)})
    spec={'key':'0xa1','material':{'alpha_mode':0,'retail_texture_ids':{'diffuse':'0x2c70170a001d0133','lightmap':'0xbb'},'retail_parameters':{'detailNormalUVScale':['4']},'seam':True},'lightmap_norm':2.5}
    inputs.update(parent=('native',[parent.path]),rock=('native',[rock.path]),light=('native',[light.path]),spec=(old.write(tmp_path,0,'MI_a1.json',spec),[]))
    args={'action':'instance','spec':'spec','piece':'MI_a1','parents':{'0':'parent'},'texture_inputs':{'0x2c70170a001d0133':'rock','0xbb':'light'},'defaults':defaults}
    result=body.run(old.context(tmp_path,{'args':args,'settings':[]},inputs,['/Game/MegaPark/Materials/MI_a1']))
    assert state.scalars[result.path]['Moss']==1. and state.scalars[result.path]['LightmapNorm']==2.5 and state.scalars[result.path]['DetailScale']==4.
    assert state.scalars[result.path]['SpecularScale']==0. and state.textures[result.path]['Diffuse'] is rock


@pytest.mark.parametrize('roles,srgb,compression,clamp',[([],True,'default',False),(['lightmap'],False,'default',True),(['normal'],False,'normal',False),(['detail','diffuse'],False,'normal',False)])
def test_role_aware_texture_finishes_from_its_own_member(tmp_path,monkeypatch,roles,srgb,compression,clamp):
    raw_path='/Game/_Raw/MegaPark/Textures/T_aa';raw=old.Texture(raw_path);assets={raw_path:raw};old.editor(tmp_path,monkeypatch,assets)
    unreal=sys.modules['unreal'];unreal.TextureCompressionSettings=NS(TC_DEFAULT='default',TC_NORMALMAP='normal');unreal.TextureAddress=NS(TA_CLAMP='clamp')
    def duplicate(source,target):
        asset=old.Texture(target);assets[target]=asset;return asset
    unreal.EditorAssetLibrary.duplicate_asset=duplicate
    save=unreal.EditorAssetLibrary.save_loaded_asset
    unreal.EditorAssetLibrary.save_loaded_asset=lambda asset,only_if_is_dirty:save(asset,only_if_dirty=only_if_is_dirty)
    folder=tmp_path/'roles';folder.mkdir();(folder/'T_aa.json').write_text(json.dumps({'tid':'0xaa','roles':roles}))
    ctx=old.context(tmp_path,{'op':'finish','kind':'texture','source':'raw','destination':'/Game/MegaPark/Textures/T_aa','package_sources':{'raw':raw_path},'args':{'action':'texture','tid':'0xaa','roles':'roles'}},
        {'raw':('native',[raw_path]),'roles':(str(folder),[])},['/Game/MegaPark/Textures/T_aa'])
    result=body.run(ctx);assert result.values['srgb'] is srgb and result.values['compression_settings']==compression
    assert ('address_x' in result.values)==clamp and raw.values=={}


def test_native_finish_declares_and_emits_actual_sdk_dump_and_finite_report(tmp_path,monkeypatch):
    state,assets,ctx=old.piece_case(tmp_path,monkeypatch);unreal=sys.modules['unreal'];unreal.Vector=lambda *v:v
    editor=unreal.get_editor_subsystem;unreal.get_editor_subsystem=lambda cls:NS(**vars(editor(cls)),get_num_uv_channels=lambda m,i:1)
    piece=ctx.outputs[0].rsplit('/',1)[-1];binary='data/imported-geometry/'+piece+'.bin';report='data/imported-reports/'+piece+'.json'
    path=tmp_path/'output'/binary;path.parent.mkdir(parents=True);calls=[]
    def dump(mesh,origin,target):calls.append((mesh.path,origin,target));np.zeros((1,3,3),dtype='<f8').tofile(target);return True
    unreal.MeshImportAudit=NS(dump_mesh_triangles=dump);ctx.params['args']['audit']=True;ctx.data_outputs=(binary,report)
    result=body.run(ctx)
    assert calls[0][2]==str(path) and path.stat().st_size==72 and result[report]['triangles']==1 and result[report]['uv_channels']==1
    assert result[report]['placed'] is False and state.saves==[ctx.outputs[0]]


def audit_case(tmp_path):
    source=tmp_path/'source';source.mkdir();triangles=np.array([[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]]])
    np.savez(source/'mesh.npz',triangles=triangles)
    source_map=source/'map.json';source_map.write_text(json.dumps({'models':[],'collision':[{'id':'TEST','npz':'mesh.npz'}]}))
    output=tmp_path/'audit';output.mkdir();key='UC_MP_TEST'
    entry={'name':key,'source_id':'TEST','triangles':1,'bounds':{'minimum':[0,0,0],'maximum':[1,1,0]}}
    build=output/'build.json';build.write_text(json.dumps({'source_sha256':hashlib.sha256(source_map.read_bytes()).hexdigest(),'render':[],'collision':[entry],'seam':[],
        'materials':{'0xa1':{}},'textures':{},'rails':[]}));letters=output/'letters.npz';np.savez(letters,triangles=triangles)
    geometry=tmp_path/'geometry';path=geometry/'data/imported-geometry'/(key+'.bin');path.parent.mkdir(parents=True);(triangles[:,:,[0,2,1]]*100).astype('<f8').tofile(path)
    report=tmp_path/'report';path=report/'data/imported-reports'/(key+'.json');path.parent.mkdir(parents=True);path.write_text(json.dumps({'name':key,'triangles':1,'bounds_error_cm':0.,'uv_channels':1,'collision':True,'placed':True}))
    level=tmp_path/'level';primary=level/'content/Game/MegaPark/Maps/SuperUltraMegaPark.umap';primary.parent.mkdir(parents=True);primary.write_bytes(b'completed map Item')
    def member(path,name):return (NS(products=[NS(paths=[path])]),name)
    args=[build,letters,source_map,output,[member(geometry,key)],[member(report,key)],[member(tmp_path/'material','MI_a1')],ROOT/templates.VERIFIER,level]
    return args,geometry,report


def test_consumed_audit_runs_original_verifier_and_retains_actual_binary_and_report(tmp_path):
    args,geometry,_=audit_case(tmp_path);projection.audit(*args)
    result=json.loads((args[3]/'import-report.json').read_text());verified=json.loads((args[3]/'geometry-verification.json').read_text())
    assert result['meshes'][0]=={'name':'UC_MP_TEST','triangles':1,'bounds_error_cm':0.,'uv_channels':1,'collision':True,'placed':True}
    assert result['collision_triangles']==1 and result['materials']==1 and verified['status']=='passed'
    assert (args[3]/'imported-geometry/UC_MP_TEST.bin').read_bytes()==(geometry/'data/imported-geometry/UC_MP_TEST.bin').read_bytes()


@pytest.mark.parametrize('damage',['dump','report','member','material','level','geometry'])
def test_audit_gate_cannot_pass_missing_or_changed_actual_native_artifacts(tmp_path,damage):
    args,geometry,report=audit_case(tmp_path)
    if damage=='dump':(geometry/'data/imported-geometry/UC_MP_TEST.bin').unlink()
    elif damage=='report':(report/'data/imported-reports/UC_MP_TEST.json').write_text('{}')
    elif damage=='member':args[4]=[]
    elif damage=='material':args[6]=[]
    elif damage=='level':(args[8]/'content/Game/MegaPark/Maps/SuperUltraMegaPark.umap').unlink()
    else:
        path=geometry/'data/imported-geometry/UC_MP_TEST.bin';values=np.fromfile(path,dtype='<f8');values[0]+=1.;values.tofile(path)
    with pytest.raises((ValueError,AssertionError)):projection.audit(*args)
    assert not (args[3]/'geometry-verification.json').exists()
