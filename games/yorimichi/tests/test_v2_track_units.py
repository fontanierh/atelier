"""Actual railway declarations and original material/collision rules through the cold native ABI."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace as NS

import pytest
from atelier.build_v2.recipe_dependencies import extract
from atelier.gltf import glb_pack

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path[:0] = [str(GAME), str(GAME / 'world')]
import v2_track_units as track
from v2_texture_units import Unsupported
spec = importlib.util.spec_from_file_location('track_body_tests', GAME / 'world/track_v2.py')
body = importlib.util.module_from_spec(spec); spec.loader.exec_module(body)
BASE = {'unit':'existing.parent', 'item':'asset', 'package':track.PARENT}
IRON = '/Game/Belmonte/Materials/MI_BM_Iron'
TEXTURES = {'derived_items': {'root':'build/v2-derived/exact-iron-texture', 'templates':[
    {'producer':'existing.texture.members', 'group':'members', 'unit_prefix':'existing.texture',
     'piece':'IronTexture', 'follower':1, 'item':'texture'}]}}
NATIVES = {track.PARENT: BASE, IRON:{'unit':'existing.iron', 'item':'asset', 'package':IRON,
                                  'dependencies':[BASE], 'derived_dependencies':[TEXTURES]}}


@pytest.fixture(scope='module')
def actual():
    spec = importlib.util.spec_from_file_location('track_recipe_tests', GAME / 'build.py')
    recipe = importlib.util.module_from_spec(spec); sys.modules[spec.name]=recipe; spec.loader.exec_module(recipe)
    context = NS(uproject=GAME / 'unreal/Yorimichi.uproject', out=ROOT / 'build/yorimichi')
    wanted = {'unreal.belmonte_track','world.belmonte_track','world.belmonte_track_data','world.belmonte.meshes','unreal.belmonte'}
    steps = [s for s in recipe.steps(context) if s.name in wanted]
    assert {s.name for s in steps} == wanted
    products = {p.name for s in steps for p in s.products}
    for step in steps:
        step.needs=[n for n in step.needs if n in wanted]; step.after=[]
        step.reads=[r for r in step.reads if r in products]; step.references=[r for r in step.references if r in products]
    return extract(steps, checkout=ROOT, build_root=ROOT/'build')


def test_cold_track_binds_actual_products_and_single_native_owners(actual):
    result=track.track_units(actual, checkout=ROOT, natives=NATIVES)
    assert set(result) == {'units','staged_inputs','content_slots','packages','aliases','module_requirements','templates','groups'}
    assert not result['module_requirements'] and len(result['templates']) == 5
    units={u['id']:u for u in result['units']}
    assert set(result['aliases']['unreal.belmonte_track']) <= set(units)
    assert [i['source'] for i in units['track.members.mesh3']['inputs']] == [
        {'kind':'item','unit':'world.belmonte_track','item':'product0'},
        {'kind':'item','unit':'world.belmonte_track_data','item':'product0'},
        {'kind':'item','unit':'world.belmonte.meshes','item':'product1'}]
    templates={t['unit_prefix'].rsplit('.',1)[1]:t for t in result['templates']}
    for kind in ('materials','glow_materials'):
        author=templates[kind]['followers'][0]['unit']
        assert len(author['outputs']) == 1 and author['op']['kind'] == 'unreal.author'
    for count in (1,2,3):
        followers=templates['mesh'+str(count)]['followers']; assert len(followers)==count+1
        finish=followers[-1]['unit']; assert finish['params']['args']['closure']==[TEXTURES]
        assert len(finish['inputs'])==len({i['name'] for i in finish['inputs']})
        assert finish['params']['args']['levels']==['level'+str(i) for i in range(count)]
        for raw in followers[:-1]: assert raw['unit']['outputs'][0]['destination']=='store'
    for t in result['templates']:
        for f in t['followers']:
            assert set(f['staged_inputs']) == {i['name'] for i in f['unit']['inputs']}
            assert all((ROOT/p).is_file() for p in f['unit']['code'])
    token=units['unreal.belmonte_track.report']['params']['args']['meshes']['derived_items']['templates']
    assert [t['follower'] for t in token]==[1,2,3]
    for key in ('unreal.belmonte_track.runtime','unreal.belmonte_track.report'):
        assert len(units[key]['outputs'])==1 and len(units[key]['outputs'][0]['files'])==1


@pytest.mark.parametrize('damage',['command','library','runtime','material-view'])
def test_track_declaration_drift_refuses(actual,damage):
    rows=deepcopy(actual); found={r['id']:r for r in rows}
    if damage=='command':found['unreal.belmonte_track']['commands'][0]['marker']='OTHER'
    else:
        unit={'library':'world.belmonte_track','runtime':'world.belmonte_track_data','material-view':'world.belmonte.meshes'}[damage]
        found[unit]['products']=[]
    with pytest.raises(Unsupported):track.track_units(rows,checkout=ROOT,natives=NATIVES)


def test_missing_or_cyclic_native_closure_refuses(actual):
    with pytest.raises(Unsupported):track.track_units(actual,checkout=ROOT,natives={})
    refs=deepcopy(NATIVES);refs[IRON]['dependencies']=[IRON]
    with pytest.raises(Unsupported,match='Cyclic'):track.track_units(actual,checkout=ROOT,natives=refs)
    refs=deepcopy(NATIVES);refs[IRON]['dependencies']=['/Game/Belmonte/Materials/Absent']
    with pytest.raises(Unsupported,match='Missing transitive'):track.track_units(actual,checkout=ROOT,natives=refs)


def library(tmp_path):
    root=tmp_path/'track'; root.mkdir()
    runtime={'meshes':{},'pieces':[],'instances':[],'exposure':{'bias':-3.5}}
    for count in (1,2,3):
        key='SM_Test'+str(count); levels=[]
        for level in range(count):
            relative=f'atomic/meshes/{key}_LOD{level}.glb'; p=root/relative;p.parent.mkdir(parents=True,exist_ok=True)
            record={'name':'MI_TK_TunnelLining','pbrMetallicRoughness':{'baseColorFactor':[.075,.07,.065,1.],'roughnessFactor':.95}}
            glow={'name':'MI_TK_LampGlow','emissiveFactor':[1.,.72,.38],'extensions':{'KHR_materials_emissive_strength':{'emissiveStrength':8.}}}
            p.write_bytes(glb_pack({'asset':{'version':'2.0'},'materials':[{'name':'MI_B_iron'},record,glow]},b''));levels.append(relative)
        runtime['meshes'][key]={'asset':body.ROOT+'/'+key+'.'+key,'lods':levels,'materials':['MI_B_iron','MI_TK_TunnelLining','MI_TK_LampGlow'],
                                'screen_sizes':[1.,.3,.05][:count]}
        runtime['pieces'].append({'name':key,'collision':count-1})
    runtime['instances']=[{'mesh':body.ROOT+'/SM_Test3.SM_Test3','collision':True}]
    p=root/'runtime/track.json';p.parent.mkdir();p.write_text(json.dumps(runtime))
    view=tmp_path/'materials.json';view.write_text(json.dumps({'materials':{'/Game/Haras/Belmonte/Materials/MI_B_iron.MI_B_iron':{'name':'MI_BM_Iron'}}}))
    return root,view,runtime


def test_projection_preserves_first_material_records_lods_and_collision(tmp_path):
    root,view,runtime=library(tmp_path); values=body.members(root,view)
    for count in (1,2,3):
        value=values['mesh'+str(count)]['SM_Test'+str(count)]
        assert len(value['levels'])==count and value['collision']==count-1
        assert value['belmonte']=={'MI_B_iron':IRON}
    assert values['materials']['MI_TK_LampGlow']['bias']==-3.5
    assert values['record']['Record']['runtime']==runtime
    body.project(root,view,tmp_path/'glow','glow_materials')
    assert [p.name for p in (tmp_path/'glow').iterdir()]==['MI_TK_LampGlow.json']
    selected=tmp_path/'selected';selected.mkdir();value=values['mesh2']['SM_Test2']
    (selected/'SM_Test2.json').write_text(json.dumps(value));body.select(selected,tmp_path/'member','SM_Test2')
    assert json.loads((tmp_path/'member/meta.json').read_text())['count']==2
    assert not (tmp_path/'member/level2').exists()


def test_missing_escape_and_unknown_belmonte_sources_refuse(tmp_path):
    root,view,runtime=library(tmp_path)
    runtime['meshes']['SM_Test1']['lods']=['../escaped.glb']
    (root/'runtime/track.json').write_text(json.dumps(runtime))
    with pytest.raises(ValueError,match='escaping'):body.members(root,view)
    root2=tmp_path/'second';root2.mkdir();root,view,runtime=library(root2)
    view.write_text(json.dumps({'materials':{}}))
    with pytest.raises(ValueError,match='Belmonte material'):body.members(root,view)


class Asset:
    def __init__(self,path,**props):self.path,self.props=path,props
    def get_path_name(self):return self.path+'.'+self.path.rsplit('/',1)[-1]
    def get_editor_property(self,k):return self.props[k]
    def set_editor_property(self,k,v):self.props[k]=v
    def get_num_lods(self):return self.props.get('lods',1)
    def get_num_triangles(self,l):return 12//(l+1)
    def set_material(self,i,m):self.props.setdefault('bound',{})[i]=m


@pytest.fixture
def editor(tmp_path,monkeypatch):
    assets,saves,scalars,vectors={},[],{},{}
    def duplicate(source,target):assets[target]=Asset(target,**deepcopy(assets[source.split('.')[0]].props));return assets[target]
    def create(key,folder,*a):assets[folder+'/'+key]=Asset(folder+'/'+key);return assets[folder+'/'+key]
    def lod(asset,level,*a):asset.props['lods']=level+1;return level
    E=NS(load_asset=lambda p:assets.get(p.split('.')[0]),does_asset_exist=lambda p:p in assets,duplicate_asset=duplicate,
         save_loaded_asset=lambda a,*v,**kw:saves.append(a.path) or True)
    M=NS(set_material_instance_parent=lambda a,p:a.props.update(parent=p),
         set_material_instance_vector_parameter_value=lambda a,k,v:vectors.update({k:v}),
         set_material_instance_scalar_parameter_value=lambda a,k,v:scalars.update({k:v}),update_material_instance=lambda a:None)
    unreal=NS(EditorAssetLibrary=E,MaterialEditingLibrary=M,AssetToolsHelpers=NS(get_asset_tools=lambda:NS(create_asset=create)),
        MaterialInstanceConstant=object,MaterialInstanceConstantFactoryNew=lambda:object(),LinearColor=lambda *v:list(v),
        StaticMeshEditorSubsystem=object,get_editor_subsystem=lambda cls:NS(remove_collisions=lambda a:a.props.update(cleared=True),
            set_lod_from_static_mesh=lod,set_lod_screen_sizes=lambda a,s:a.props.update(sizes=s) or True),
        CollisionTraceFlag=NS(CTF_USE_COMPLEX_AS_SIMPLE='complex'))
    monkeypatch.setitem(sys.modules,'unreal',unreal)
    original=tmp_path/body.ORIGINAL;original.parent.mkdir(parents=True);shutil.copyfile(ROOT/body.ORIGINAL,original)
    for path in (track.PARENT,IRON,track.GLOW):assets[path]=Asset(path)
    return NS(root=tmp_path,assets=assets,saves=saves,scalars=scalars,vectors=vectors,unreal=unreal)


def stage(editor,meta):
    root=editor.root/'meta';root.mkdir(exist_ok=True);(root/'meta.json').write_text(json.dumps(meta));return str(root)


def derived(values):return {'derived_items':{'members':[{'piece':k,'slot':v} for k,v in values.items()]}}


@pytest.mark.parametrize('kind',['MI_TK_TunnelLining','MI_TK_LampGlow','MI_ST_Green'])
def test_original_material_body_retains_darkening_glow_exposure_and_parent(editor,kind):
    parent=track.GLOW if kind=='MI_TK_LampGlow' else track.PARENT
    meta={'name':kind,'bias':-3.5,'record':{'pbrMetallicRoughness':{'baseColorFactor':[.1,.2,.3,1.],'roughnessFactor':.7},
             'emissiveFactor':[1.,.72,.38],'extensions':{'KHR_materials_emissive_strength':{'emissiveStrength':8.}}}}
    destination=body.ROOT+'/Materials/'+kind
    ctx=NS(job_dir=str(editor.root),inputs={'meta':stage(editor,meta),'parent':'x'},packages={'meta':[],'parent':[parent]},
           outputs=[destination],params={'args':{'action':'material','name':kind,'meta':'meta','parent':'parent'}})
    asset=body.run(ctx)
    assert asset.props['parent'] is editor.assets[parent] and all(p==destination for p in editor.saves)
    if kind=='MI_TK_LampGlow':assert editor.scalars['Strength']==8.*2**3.5
    else:
        assert editor.scalars['Brightness']==(.5 if kind=='MI_TK_TunnelLining' else 1.)
        assert editor.scalars['WhiteVertex']==1. and editor.scalars['Roughness']==.7


@pytest.mark.parametrize('count,collision',[(1,-1),(2,1),(3,5)])
def test_mesh_finish_retains_original_lods_slots_collision_and_save_failure(editor,count,collision):
    key='SM_Test';destination=body.ROOT+'/'+key
    slots=[Asset('slot0',material_slot_name='Iron',imported_material_slot_name='MI_B_iron_LOD0'),
           Asset('slot1',material_slot_name='MI_TK_TunnelLining',imported_material_slot_name='')]
    raw=Asset('/Game/_Raw/Track',static_materials=slots,body_setup=Asset('body'),lods=1);editor.assets[raw.path]=raw
    local=Asset(body.ROOT+'/Materials/MI_TK_TunnelLining');editor.assets[local.path]=local
    spec={'materials':['MI_B_iron','MI_TK_TunnelLining'],'screen_sizes':[1.,.3,.05][:count]}
    meta={'name':key,'count':count,'spec':spec,'collision':collision,'belmonte':{'MI_B_iron':IRON}}
    args={'action':'mesh','name':key,'meta':'meta','levels':['raw']*count,
          'materials':derived({'MI_TK_TunnelLining':'local'}),'belmonte':['iron']}
    ctx=NS(job_dir=str(editor.root),inputs={'meta':stage(editor,meta),'raw':'x','local':'x','iron':'x'},
           packages={'meta':[],'raw':[raw.path],'local':[local.path],'iron':[IRON]},outputs=[destination],params={'args':args})
    asset=body.run(ctx)
    assert asset.get_num_lods()==count and asset.props['cleared'] is True
    assert asset.props['bound']=={0:editor.assets[IRON],1:local} and 'bound' not in raw.props
    if collision>=0:
        assert asset.props['lod_for_collision']==min(collision,count-1)
        assert asset.props['body_setup'].props=={'collision_trace_flag':'complex','double_sided_geometry':True}
    else:assert 'collision_trace_flag' not in asset.props['body_setup'].props
    assert editor.saves==[destination]
    editor.unreal.EditorAssetLibrary.save_loaded_asset=lambda *a,**kw:False
    with pytest.raises(RuntimeError,match='save failed'):body.run(ctx)


@pytest.mark.parametrize('field',['runtime','report'])
def test_single_json_record_preserves_runtime_and_original_report(editor,field):
    key='SM_Test';slots=[Asset('slot',material_slot_name='MI_B_iron',imported_material_slot_name='MI_B_iron_LOD0')]
    mesh=Asset(body.ROOT+'/'+key,lods=2,static_materials=slots);editor.assets[mesh.path]=mesh
    runtime={'meshes':{key:{'materials':['MI_B_iron','UnusedDeclaredSlot'],'lods':['a','b']}},'other':'preserved'}
    metadata={'runtime':runtime,'belmonte':{'MI_B_iron':IRON},'collision':{key:1}}
    output=body.RUNTIME if field=='runtime' else body.REPORT
    args={'action':'record','field':field,'meta':'meta','meshes':derived({key:'mesh'}),'materials':derived({}),'belmonte':['iron']}
    ctx=NS(job_dir=str(editor.root),inputs={'meta':stage(editor,metadata),'mesh':'x','iron':'x'},
           packages={'meta':[],'mesh':[mesh.path],'iron':[IRON]},outputs=[],data_outputs=[output],params={'args':args})
    result=body.run(ctx)
    if field=='runtime':assert result=={body.RUNTIME:runtime}
    else:
        assert result[body.REPORT]=={'meshes':{key:{'lods':2,'triangles':[12,6],'collision_lod':1}},
                                    'materials':{'MI_B_iron':editor.assets[IRON].get_path_name()}}
    ctx.data_outputs=[body.RUNTIME,body.REPORT]
    with pytest.raises(ValueError,match='exactly one'):body.run(ctx)


def test_glow_parent_uses_original_unlit_emission_and_one_package(editor):
    nodes=[]
    def expression(*a):
        node=Asset('expression');nodes.append(node);return node
    mel=editor.unreal.MaterialEditingLibrary
    mel.create_material_expression=expression;mel.connect_material_expressions=lambda *a:True
    mel.connect_material_property=lambda *a:True;mel.recompile_material=lambda *a:None
    editor.unreal.Material=object;editor.unreal.MaterialFactoryNew=lambda:object()
    editor.unreal.MaterialShadingModel=NS(MSM_UNLIT='unlit')
    editor.unreal.MaterialExpressionVectorParameter=object;editor.unreal.MaterialExpressionScalarParameter=object
    editor.unreal.MaterialExpressionMultiply=object;editor.unreal.MaterialProperty=NS(MP_EMISSIVE_COLOR='emission')
    ctx=NS(job_dir=str(editor.root),outputs=[track.GLOW],inputs={},packages={},params={'args':{'action':'glow'}})
    asset=body.run(ctx)
    assert asset.props=={'shading_model':'unlit','used_with_instanced_static_meshes':True}
    assert any(n.props.get('parameter_name')=='Strength' and n.props['default_value']==8. for n in nodes)
    assert all(p==track.GLOW for p in editor.saves)
