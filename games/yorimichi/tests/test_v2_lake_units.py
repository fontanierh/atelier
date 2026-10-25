"""Actual Lake declarations, selected source proofs and original native/material behavior without Unreal jobs."""
from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import numpy as np
import pytest
from atelier import mesh_ir
from atelier.build_v2.blender_validate import decode_mesh_payload
from atelier.build_v2.recipe_dependencies import extract
from atelier.export_manifest import publish_receipt

ROOT = Path(__file__).resolve().parents[3]; GAME = ROOT / 'games/yorimichi'
sys.path[:0] = [str(GAME), str(GAME/'world'), str(GAME/'unreal/Scripts')]


def load(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT/relative)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


units = load('games/yorimichi/v2_lake_units.py', 'lake_units_test')
body = load(units.FINISH, 'lake_finish_test')


@pytest.fixture(scope='module')
def geometry():
    factory = load('games/yorimichi/lake_atomic_build.py', 'lake_factory_test')
    rows = extract(factory.steps(NS(out=ROOT/'build/yorimichi')), checkout=ROOT, build_root=ROOT/'build')
    return load('games/yorimichi/v2_geometry_templates.py', 'lake_templates_test').geometry_templates(rows, checkout=ROOT)


def natives():
    return {units.VILLAGE: {'unit':'actual.village.material','item':'asset','package':units.VILLAGE,
        'dependencies':[{'unit':'actual.village.texture','item':'texture','package':'/Game/Japan/Textures/T_Village'}]}}


def test_five_actual_parents_get_independent_followers_and_only_water_authored_material(geometry):
    before = deepcopy(geometry); result = units.attach_followers(geometry, natives(), checkout=ROOT)
    assert geometry == before and len(result['templates']) == len(result['module_requirements']) == 5
    water, = result['units']
    assert water['id'] == units.WATER_UNIT and water['op'] == {'kind':'unreal.author','version':'1'}
    assert water['script'] == units.CALL and water['inputs'] == []
    assert water['params'] == {'args':{'module':units.WATER_SOURCE,'function':'create','arguments':[],
                                    'keyword_arguments':{},'expected_package':units.WATER},'settings':[]}
    assert water['outputs'][0]['class'] == 'Material' and water['outputs'][0]['logical_path'] == units.WATER
    assert result['packages'] == {units.WATER:{'unit':units.WATER_UNIT,'item':'asset','package':units.WATER}}
    assert result['staged_inputs'][units.WATER_UNIT] == {} and result['content_slots'] == {}
    assert {units.CALL,units.WATER_SOURCE} <= set(water['code'])
    for template in result['templates']:
        raw, finish = [f['unit'] for f in template['followers']]
        parent = finish['params']['args']['parent']
        assert raw['params']['destination'] == '/Game/_Raw/Lake/$piece'
        assert raw['outputs'][0]['destination'] == 'store' and raw['outputs'][0]['class'] == 'RawStaticMesh'
        assert finish['params']['destination'] == '/Game/Japan/Lake/Pieces/$piece'
        assert finish['outputs'][0]['destination'] == 'checkout' and len(finish['outputs'][0]['files']) == 6
        assert finish['inputs'][2]['source'] == {'kind':'group_member','unit':template['producer'],'group':'geometry','piece':'$piece'}
        expected = units.WATER if parent == 'Lake_Water' else units.VILLAGE
        assert finish['params']['args']['native_inputs']['native0'] == expected
        assert len(finish['inputs']) == (4 if parent == 'Lake_Water' else 5)
        assert all((ROOT/p).is_file() for p in finish['code'])
        assert 'games/yorimichi/unreal/Scripts/lake_native.py' in finish['code']
        assert result['module_requirements'][template['unit_prefix']][0]['name'] == 'Yorimichi'


@pytest.mark.parametrize('damage',['missing_material','wrong_material','partial','format','parent'])
def test_incomplete_native_roles_or_source_family_refuse(geometry, damage):
    graph = deepcopy(geometry); refs = natives()
    if damage == 'missing_material': refs = {}
    elif damage == 'wrong_material': refs[units.VILLAGE]['package'] = units.WATER
    elif damage == 'partial': graph['templates'].pop()
    elif damage == 'format': graph['templates'][0]['params']['format'] = 'glb'
    else: graph['templates'][0]['producer'] = 'foreign'
    with pytest.raises(ValueError): units.attach_followers(graph, refs, checkout=ROOT)


class Props:
    def __init__(self, **values): self.values=values
    def get_editor_property(self, key): return self.values[key]
    def set_editor_property(self, key, value): self.values[key]=value
class Asset:
    def __init__(self, path='node'): self.path=path
    def get_path_name(self): return self.path+'.'+self.path.rsplit('/',1)[-1]
class Material(Asset): pass
class Mesh(Asset):
    def get_num_triangles(self, lod): return self.triangles
    def get_num_lods(self): return self.lods
    def set_num_source_models(self, count): self.lods=count
    def get_material(self, i): return self.material
    def set_material(self, i, value): self.material=value
    def get_editor_property(self, key): return self.body
    def get_bounding_box(self): return NS(min=NS(**dict(zip('xyz',self.low))),max=NS(**dict(zip('xyz',self.high))))


def case(tmp_path, monkeypatch, *, water=False):
    key = 'Lake_Water' if water else 'Lake_Cabin'
    source=tmp_path/'source'; payload=tmp_path/'payload'; source.mkdir();payload.mkdir()
    piece=dict(positions=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],faces=[[0,1,2]],normals=[[0.,0.,1.]]*3,
               materials=[0],smooth=[False],uvs=[('UVMap',[[0.,0.],[1.,0.],[0.,1.]])],colours=[])
    packet=mesh_ir.encode(piece,key=key,slots=['LakePalette'],matrix=np.eye(4).tolist(),options={})
    (payload/(key+'.npz')).write_bytes(packet)
    _,_,facts=decode_mesh_payload(packet,expected_asset=key)
    (source/(key+'.fbx')).write_bytes(b'producer-verified FBX')
    receipt=publish_receipt(source,key=key,primary=key+'.fbx',triangles=1,bounds=[facts['min'],facts['max']],
        metadata={'geometry_sha256':hashlib.sha256(packet).hexdigest(),'slots':['LakePalette'],'polygons':1,'collision_hulls':0,'uv_channels':['UVMap']})
    raw_path='/Game/_Raw/Lake/'+key; destination='/Game/Japan/Lake/Pieces/'+key
    raw=Mesh(raw_path);raw.triangles=1;raw.lods=2;raw.uvs=1;raw.simple=raw.convex=0
    raw.static_materials=[Props(imported_material_slot_name='LakePalette')];raw.material=None
    raw.settings=Props(use_full_precision_u_vs=True);raw.body=Props(collision_trace_flag='old')
    raw.low,raw.high=[0.,-100.,0.],[100.,0.,0.]
    material_path=units.WATER if water else units.VILLAGE
    assets={raw_path:raw,material_path:Material(material_path)};events=[]
    content=tmp_path/'Content';content.mkdir()
    state=NS(raw=raw,source=source,payload=payload,receipt=receipt,assets=assets,events=events,cook=True,save=True,primary=True,post_save=False)
    def duplicate(path,target):
        result=deepcopy(assets[path]);result.path=target;assets[target]=result;events.append('duplicate');return result
    def save(mesh,dirty):
        assert dirty is True;events.append('save')
        if state.primary:
            path=content/(mesh.path.removeprefix('/Game/')+'.uasset');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'primary')
        if state.post_save:mesh.uvs=2
        return state.save
    def remove(mesh):mesh.simple=mesh.convex=0;return True
    def cooked(mesh,triangles,simple):assert triangles==1 and simple is False;events.append('validate');return state.cook
    editor=NS(get_lod_build_settings=lambda mesh,lod:mesh.settings,set_lod_build_settings=lambda *a:None,
        get_simple_collision_count=lambda mesh:mesh.simple,get_convex_collision_count=lambda mesh:mesh.convex,
        remove_collisions=remove,get_num_uv_channels=lambda mesh,lod:mesh.uvs)
    unreal=NS(StaticMesh=Mesh,MaterialInterface=Material,StaticMeshEditorSubsystem=object(),load_module=lambda name:None,
        get_editor_subsystem=lambda cls:editor,CollisionTraceFlag=NS(CTF_USE_COMPLEX_AS_SIMPLE='complex'),
        CitySurfaceValidation=NS(validate_collision=cooked),EditorAssetLibrary=NS(load_asset=assets.get,does_asset_exist=lambda p:p in assets,
            duplicate_asset=duplicate,save_loaded_asset=save))
    monkeypatch.setitem(sys.modules,'unreal',unreal)
    context=NS(job_dir=str(tmp_path),content_dir=str(content),inputs={'raw':'raw-item','source_export':str(source),'payload':str(payload),'native0':'material-item'},
        packages={'raw':[raw_path],'source_export':[],'payload':[],'native0':[material_path]},outputs=[destination],params={'op':'finish','kind':'static_mesh',
        'source':'raw','destination':destination,'package_sources':{'raw':raw_path},'args':{'parent':key,'source_export':'source_export','payload':'payload',
        'material':'native0','native_inputs':{'native0':material_path}}})
    return state,context,unreal


@pytest.mark.parametrize('water',[False,True])
def test_original_parent_material_lod_uv_complex_collision_and_real_primary(tmp_path,monkeypatch,water):
    state,context,_=case(tmp_path,monkeypatch,water=water)
    mesh=body.run(context)
    assert state.raw.lods==2 and state.raw.settings.values['use_full_precision_u_vs'] is True and state.raw.material is None
    assert mesh.lods==1 and mesh.settings.values['use_full_precision_u_vs'] is False
    assert mesh.material.path==(units.WATER if water else units.VILLAGE) and mesh.body.values['collision_trace_flag']=='complex'
    assert state.events==['duplicate','validate','save','validate']


@pytest.mark.parametrize('damage',['source','payload','parent','triangles','uv','bounds','nonfinite_bounds','slot','material','cook','save','primary','post_save','validator'])
def test_invalid_current_source_or_native_state_cannot_complete(tmp_path,monkeypatch,damage):
    state,context,unreal=case(tmp_path,monkeypatch)
    if damage=='source':(state.source/(state.receipt['asset']+'.fbx')).write_bytes(b'changed')
    elif damage=='payload':(state.payload/'extra.npz').write_bytes(b'foreign')
    elif damage=='parent':context.params['args']['parent']='Lake_Plants'
    elif damage=='triangles':state.raw.triangles=2
    elif damage=='uv':state.raw.uvs=2
    elif damage=='bounds':state.raw.low=[1.,-100.,0.]
    elif damage=='nonfinite_bounds':state.raw.low=[float('nan'),-100.,0.]
    elif damage=='slot':state.raw.static_materials[0].values['imported_material_slot_name']='Other'
    elif damage=='material':context.params['args']['native_inputs']['native0']=units.WATER
    elif damage=='cook':state.cook=False
    elif damage=='save':state.save=False
    elif damage=='primary':state.primary=False
    elif damage=='post_save':state.post_save=True
    else:unreal.CitySurfaceValidation=None
    with pytest.raises(ValueError):body.run(context)


def test_source_export_root_codec_reaches_selected_body_without_source_mutation(tmp_path,monkeypatch):
    from atelier.build_v2 import recipe_job,unreal_inputs
    state,context,_=case(tmp_path,monkeypatch)
    archive=tmp_path/'inputs/source.tree.tar';archive.parent.mkdir();recipe_job.pack_root(state.source,archive)
    before=archive.read_bytes();runtime=tmp_path/'runtime';runtime.mkdir()
    prepared=unreal_inputs.stage_inputs(tmp_path,[{'name':'source_export','path':'inputs/source.tree.tar','identity':{'state':'digest'}}],
        Path(context.content_dir),runtime_dir=runtime)
    context.inputs['source_export']=prepared['inputs']['source_export'];context.packages['source_export']=prepared['packages']['source_export']
    assert body.run(context).path==context.outputs[0] and archive.read_bytes()==before


def test_original_water_create_is_import_inert_and_generic_body_keeps_exact_graph(tmp_path,monkeypatch,geometry):
    nodes=[];connections=[];saves=[];assets={}
    def create(name,folder,cls,factory):asset=Material(folder+'/'+name);asset.props={};asset.set_editor_property=asset.props.__setitem__;assets[asset.path]=asset;return asset
    def node(mat,cls,x,y):value=Props();value.kind=cls;nodes.append(value);return value
    def save(asset,*args):saves.append((asset.path,args));return True
    unreal=NS(EditorAssetLibrary=NS(load_asset=assets.get,does_asset_exist=lambda p:p in assets,save_loaded_asset=save),
        AssetToolsHelpers=NS(get_asset_tools=lambda:NS(create_asset=create)),Material=Material,MaterialFactoryNew=lambda:None,
        MaterialEditingLibrary=NS(delete_all_material_expressions=lambda mat:None,create_material_expression=node,
            connect_material_expressions=lambda *a:connections.append(a),connect_material_property=lambda *a:connections.append(a),recompile_material=lambda mat:None),
        CustomInput=Props,CustomMaterialOutputType=NS(CMOT_FLOAT1=1,CMOT_FLOAT3=3),
        MaterialProperty=NS(MP_BASE_COLOR='base',MP_NORMAL='normal',MP_ROUGHNESS='roughness',MP_SPECULAR='specular',MP_METALLIC='metallic'))
    for name in ('TextureCoordinate','Time','Custom','Constant'):setattr(unreal,'MaterialExpression'+name,name)
    monkeypatch.setitem(sys.modules,'unreal',unreal)
    original=load(units.WATER_SOURCE,'lake_original_water_test');assert assets=={} and nodes==[]
    target=tmp_path/units.WATER_SOURCE;target.parent.mkdir(parents=True);target.write_bytes((ROOT/units.WATER_SOURCE).read_bytes())
    water,=units.attach_followers(geometry,natives(),checkout=ROOT)['units']
    generic=load(units.CALL,'lake_generic_author_test')
    generic.run(NS(job_dir=tmp_path,inputs={},packages={},outputs=[units.WATER],params=water['params']))
    assert list(assets)==[units.WATER] and len(saves)==2
    custom=[n.values['code'] for n in nodes if n.kind=='Custom']
    assert len(custom)==3 and all(code.startswith(original.RIPPLE) for code in custom)
    assert all('float2(UV.x,1.-UV.y)' in code and 'for(int i=0;i<7;i++)' in code for code in custom)
    assert {n.values['r'] for n in nodes if n.kind=='Constant'}=={.55,.08}
    assert assets[units.WATER].props=={'used_with_instanced_static_meshes':True}
