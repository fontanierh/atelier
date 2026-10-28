"""Actual Sailboat D2 declarations, selected source codec and fake native fidelity."""
from copy import deepcopy
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import numpy as np
import pytest
from atelier import mesh_ir
from atelier.build_v2.recipe_dependencies import extract
from atelier.export_manifest import publish_receipt

ROOT=Path(__file__).resolve().parents[3];GAME=ROOT/'games/yorimichi'
sys.path[:0]=[str(GAME),str(GAME/'world')]


def load(relative,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/relative)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


units=load('games/yorimichi/v2_sailboat_units.py','sailboat_units_test')
body=load(units.FINISH,'sailboat_finish_test')


def geometry():
    factory=load('games/yorimichi/vehicle_atomic_build.py','sailboat_factory_test')
    rows=extract(factory.steps(NS(out=ROOT/'build/yorimichi'),'sailboat'),checkout=ROOT,build_root=ROOT/'build')
    return load('games/yorimichi/v2_geometry_templates.py','sailboat_templates_test').geometry_templates(rows,checkout=ROOT)


@pytest.fixture(scope='module')
def declaration():
    original=geometry()
    natives={units.MATERIAL:{'unit':'village.material','item':'asset','package':units.MATERIAL,'dependencies':['/Game/Palette']},
        '/Game/Palette':{'unit':'palette','item':'asset','package':'/Game/Palette'}}
    return original,units.attach_followers(original,natives,checkout=ROOT)


def test_actual_five_parents_and_independent_material_owners(declaration):
    original,result=declaration
    assert len(result['templates'])==5 and all('followers' not in t for t in original['templates'])
    assert 'aliases' not in result and 'data_targets' not in result
    assert len(result['units'])==2
    for unit,package,wake in zip(result['units'],(units.CLOTH,units.FOAM),(False,True)):
        assert unit['script']==units.CALL and unit['inputs']==[] and unit['params']['settings']==[]
        assert unit['params']['args']=={'module':units.MATERIAL_SOURCE,'function':'material','arguments':[],
            'keyword_arguments':{'wake':True} if wake else {},'expected_package':package}
        assert unit['outputs'][0]['logical_path']==package and unit['outputs'][0]['class']=='Material'
        assert units.MATERIAL_SOURCE in unit['code']
    for template in result['templates']:
        raw,finish=[f['unit'] for f in template['followers']];parent=finish['params']['args']['parent']
        assert raw['params']['destination']=='/Game/_Raw/Sailboat/$piece'
        assert finish['params']['destination']=='/Game/Japan/Assets/$piece'
        assert finish['inputs'][2]['source']=={'kind':'group_member','unit':template['producer'],'group':'geometry','piece':'$piece'}
        native=finish['params']['args']['native_inputs']
        expected=units.CLOTH if parent=='SB_Sail' else units.FOAM if parent=='SB_Wake' else units.MATERIAL
        assert native[finish['params']['args']['material']]==expected
        assert len(native)==(1 if parent in ('SB_Sail','SB_Wake') else 2)
        assert result['module_requirements'][template['unit_prefix']][0]['name']=='Yorimichi'
        assert all((ROOT/path).is_file() for path in finish['code'])
        assert not any(path.endswith('import_sailboat.py') for path in finish['code'])


@pytest.mark.parametrize('damage',['missing','duplicate','format','followed','native','transitive'])
def test_constructor_refuses_incomplete_or_ambient_sources(damage):
    value=geometry();natives={units.MATERIAL:{'unit':'village','item':'asset','package':units.MATERIAL}}
    if damage=='missing':value['templates'].pop()
    elif damage=='duplicate':value['templates'].append(deepcopy(value['templates'][0]))
    elif damage=='format':value['templates'][0]['params']['format']='obj'
    elif damage=='followed':value['templates'][0]['followers']=[{}]
    elif damage=='native':natives={}
    else:natives[units.MATERIAL]['dependencies']=['/Game/Missing']
    with pytest.raises(ValueError):units.attach_followers(value,natives,checkout=ROOT)


def test_actual_source_projection_selects_only_one_builder_and_no_collider():
    sources=load('games/yorimichi/world/vehicle_sources.py','sailboat_source_test')
    values=sources.projection((GAME/'assets/vehicles/sailboat/build.py').read_text(),'sailboat')
    assert set(values)==set(sources.FAMILIES['sailboat']['builders'])
    for name,value in values.items():
        tree=ast.parse(value['program']);functions={n.name for n in tree.body if isinstance(n,ast.FunctionDef)}
        assert functions & set(sources.FAMILIES['sailboat']['builders'].values())=={value['builder']}
        assert not any(isinstance(n,ast.Attribute) and n.attr=='collider' for n in ast.walk(tree))
        assert 'main' not in functions and 'OUT' not in value['program']


class Props:
    def __init__(self,**values):self.values=values
    def get_editor_property(self,key):return self.values[key]
    def set_editor_property(self,key,value):self.values[key]=value
class Asset:
    def __init__(self,path):self.path=path
    def get_path_name(self):return self.path+'.'+self.path.rsplit('/',1)[-1]
class Material(Asset):pass
class Mesh(Asset):
    def get_num_triangles(self,lod):return self.triangles
    def get_num_lods(self):return self.lods
    def get_material(self,i):return self.material
    def set_material(self,i,value):self.material=value
    def get_editor_property(self,key):return self.body
    def get_bounding_box(self):return NS(min=NS(**dict(zip('xyz',self.low))),max=NS(**dict(zip('xyz',self.high))))


def native_case(tmp_path,monkeypatch,name='SB_Hull'):
    source=tmp_path/'source';payload=tmp_path/'payload';source.mkdir();payload.mkdir()
    piece=dict(positions=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],faces=[[0,1,2]],normals=[[0.,0.,1.]]*3,materials=[0],smooth=[False],uvs=[('UVMap',[[0.,0.],[1.,0.],[0.,1.]])],colours=[])
    hulls=[]
    packet=mesh_ir.encode(piece,key=name,slots=['SailboatPalette'],matrix=np.eye(4).tolist(),options=body.OPTIONS,collisions=hulls)
    (payload/(name+'.npz')).write_bytes(packet);facts={'min':[0.,0.,0.],'max':[1.,1.,0.]}
    (source/(name+'.fbx')).write_bytes(b'producer verified FBX')
    publish_receipt(source,key=name,primary=name+'.fbx',triangles=1,bounds=[facts['min'],facts['max']],metadata={'geometry_sha256':hashlib.sha256(packet).hexdigest(),'slots':['SailboatPalette'],'polygons':1,'collision_hulls':len(hulls),'uv_channels':['UVMap']})
    raw_path='/Game/_Raw/Sailboat/'+name;dest='/Game/Japan/Assets/'+name
    raw=Mesh(raw_path);raw.triangles=raw.lods=raw.uvs=1;raw.material=None;raw.static_materials=[Props(imported_material_slot_name='SailboatPalette')]
    raw.body=Props(collision_trace_flag='original-default');raw.settings=Props(use_full_precision_u_vs=True)
    raw.hulls=[[[p[0]*100,-p[1]*100,p[2]*100] for p in h['vertices']] for h in hulls]
    package=units.CLOTH if name=='SB_Sail' else units.FOAM if name=='SB_Wake' else units.MATERIAL
    raw.low,raw.high=[0.,-100.,0.],[100.,0.,0.];assets={raw_path:raw,package:Material(package)};events=[]
    content=tmp_path/'Content';content.mkdir();state=NS(raw=raw,assets=assets,events=events,save=True,primary=True,post=False)
    def duplicate(path,target):mesh=deepcopy(assets[path]);mesh.path=target;assets[target]=mesh;events.append('duplicate');return mesh
    def save(mesh,only_if_is_dirty=False):
        assert only_if_is_dirty is False;events.append('save')
        if state.primary:
            path=content/(mesh.path.removeprefix('/Game/')+'.uasset');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'primary')
        if state.post:mesh.uvs=2
        return state.save
    editor=NS(get_lod_build_settings=lambda mesh,lod:mesh.settings,get_num_uv_channels=lambda mesh,lod:mesh.uvs)
    unreal=NS(StaticMesh=Mesh,MaterialInterface=Material,StaticMeshEditorSubsystem=object(),get_editor_subsystem=lambda cls:editor,load_module=lambda name:None,
        CitySurfaceValidation=NS(collision_vertices=lambda mesh:json.dumps(mesh.hulls)),EditorAssetLibrary=NS(load_asset=assets.get,does_asset_exist=lambda p:p in assets,duplicate_asset=duplicate,save_loaded_asset=save))
    monkeypatch.setitem(sys.modules,'unreal',unreal)
    context=NS(job_dir=str(tmp_path),content_dir=str(content),inputs={'raw':'raw','material':'mat','source_export':str(source),'payload':str(payload)},packages={'raw':[raw_path],'material':[package],'source_export':[],'payload':[]},outputs=[dest],params={'op':'finish','kind':'static_mesh','source':'raw','destination':dest,'package_sources':{'raw':raw_path},'args':{'parent':name,'source_export':'source_export','payload':'payload','material':'material','native_inputs':{'material':package}}})
    return state,context,unreal


@pytest.mark.parametrize('name',['SB_Hull','SB_Sail','SB_Boom','SB_Rudder','SB_Wake'])
def test_native_preserves_imported_policies_and_selects_original_material(tmp_path,monkeypatch,name):
    state,context,_=native_case(tmp_path,monkeypatch,name)
    mesh=body.run(context)
    assert mesh.body.values['collision_trace_flag']=='original-default' and mesh.settings.values['use_full_precision_u_vs'] is True
    assert mesh.hulls==[] and state.raw.material is None and state.events==['duplicate','save']
    assert mesh.material.path==context.params['args']['native_inputs']['material']


@pytest.mark.parametrize('damage',['triangles','bounds','uv','hulls','save','primary','post','slot','validator'])
def test_wrong_native_geometry_or_collision_cannot_finish(tmp_path,monkeypatch,damage):
    state,context,unreal=native_case(tmp_path,monkeypatch)
    if damage=='triangles':state.raw.triangles=2
    elif damage=='bounds':state.raw.low=[1.,-100.,0.]
    elif damage=='uv':state.raw.uvs=2
    elif damage=='hulls':state.raw.hulls=[[[0,0,0],[1,0,0],[0,1,0],[0,0,1]]]
    elif damage=='save':state.save=False
    elif damage=='primary':state.primary=False
    elif damage=='post':state.post=True
    elif damage=='slot':state.raw.static_materials[0].values['imported_material_slot_name']='Other'
    else:unreal.CitySurfaceValidation=None
    with pytest.raises((ValueError,RuntimeError)):body.run(context)


@pytest.mark.parametrize('wake',[False,True])
def test_original_material_module_is_inert_and_selected_graph_is_preserved(tmp_path,monkeypatch,declaration,wake):
    assets={};nodes=[];saves=[];connections=[]
    class AuthoredMaterial(Material,Props):
        def __init__(self,path):Material.__init__(self,path);Props.__init__(self)
    def create(name,folder,cls,factory):asset=AuthoredMaterial(folder+'/'+name);assets[asset.path]=asset;return asset
    def node(mat,cls,x,y):value=Props();value.kind=cls;nodes.append(value);return value
    def save(asset,*args):saves.append(asset.path);return True
    unreal=NS(EditorAssetLibrary=NS(load_asset=assets.get,does_asset_exist=lambda path:path in assets,save_loaded_asset=save),
        AssetToolsHelpers=NS(get_asset_tools=lambda:NS(create_asset=create)),Material=AuthoredMaterial,MaterialFactoryNew=lambda:None,
        MaterialEditingLibrary=NS(delete_all_material_expressions=lambda mat:None,create_material_expression=node,
            connect_material_expressions=lambda *a:True,connect_material_property=lambda n,out,prop:connections.append(prop) or True,recompile_material=lambda mat:None),
        LinearColor=lambda *v:v,CustomInput=Props,CustomMaterialOutputType=NS(CMOT_FLOAT3=3,CMOT_FLOAT1=1),
        MaterialProperty=NS(**{'MP_'+name:name for name in ('BASE_COLOR','ROUGHNESS','SPECULAR','OPACITY','WORLD_POSITION_OFFSET')}),
        BlendMode=NS(BLEND_TRANSLUCENT='translucent'),TranslucencyLightingMode=NS(TLM_SURFACE_PER_PIXEL_LIGHTING='surface'))
    for name in ('VertexColor','Time','WorldPosition','Custom','Constant','ScalarParameter','VectorParameter'):
        setattr(unreal,'MaterialExpression'+name,name)
    monkeypatch.setitem(sys.modules,'unreal',unreal)
    load(units.MATERIAL_SOURCE,'inert_sailboat_material_test');assert assets=={} and nodes==[]
    path=tmp_path/units.MATERIAL_SOURCE;path.parent.mkdir(parents=True);path.write_bytes((ROOT/units.MATERIAL_SOURCE).read_bytes())
    unit=declaration[1]['units'][int(wake)];package=units.FOAM if wake else units.CLOTH
    load(units.CALL,'sailboat_original_author_test').run(NS(job_dir=tmp_path,inputs={},packages={},outputs=[package],params=unit['params']))
    assert list(assets)==[package] and saves==[package,package]
    assert assets[package].values['two_sided'] is True
    assert {n.values['r'] for n in nodes if n.kind=='Constant'}=={.95,.1}
    parameters={n.values['parameter_name']:n.values['default_value'] for n in nodes if n.kind in ('ScalarParameter','VectorParameter')}
    assert parameters==({'WakeAmount':0.} if wake else {'SailFill':1.,'FlutterDirection':(0,1,0,0)})
    assert ('OPACITY' in connections)==wake and 'WORLD_POSITION_OFFSET' in connections
    assert ('blend_mode' in assets[package].values)==wake
    codes=[n.values['code'] for n in nodes if n.kind=='Custom']
    assert codes[0]=='return lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C));'
    assert len(codes)==(3 if wake else 2)


@pytest.mark.parametrize('damage',['matrix','options','export','payload','material','fresh','finite','native'])
def test_source_and_owned_package_checks_precede_save(tmp_path,monkeypatch,damage):
    state,context,_=native_case(tmp_path,monkeypatch)
    if damage in ('matrix','options'):
        root=Path(context.inputs['payload']);path=root/'SB_Hull.npz'
        meta,piece=mesh_ir.decode(path.read_bytes())
        if damage=='matrix':meta['matrix'][0][3]=1.
        else:meta['options']['axis_forward']='X'
        packet=mesh_ir.encode(piece,key=meta['asset'],slots=meta['slots'],matrix=meta['matrix'],options=meta['options'],collisions=[])
        path.write_bytes(packet)
    elif damage=='export':(Path(context.inputs['source_export'])/'other.fbx').write_bytes(b'sibling')
    elif damage=='payload':(Path(context.inputs['payload'])/'other.npz').write_bytes(b'sibling')
    elif damage=='material':context.params['args']['native_inputs']['material']=units.CLOTH
    elif damage=='fresh':state.assets[context.outputs[0]]=Mesh(context.outputs[0])
    elif damage=='finite':state.raw.low[0]=float('nan')
    else:context.params['args']['native_inputs']['missing']='/Game/Missing'
    with pytest.raises(ValueError):body.run(context)
    assert 'save' not in state.events


def test_fbx_options_match_the_actual_existing_vehicle_planner():
    tree=ast.parse((GAME/'world/plan_vehicle_part.py').read_text())
    assignment=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='OPTIONS' for t in n.targets))
    assert {kw.arg:ast.literal_eval(kw.value) for kw in assignment.value.keywords}==body.OPTIONS
