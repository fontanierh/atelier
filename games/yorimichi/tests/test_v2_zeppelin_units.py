"""Actual Zeppelin D2 declarations, selected source codec and fake native fidelity."""
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


units=load('games/yorimichi/v2_zeppelin_units.py','zeppelin_units_test')
body=load(units.FINISH,'zeppelin_finish_test')


def geometry():
    factory=load('games/yorimichi/world/regions/zeppelin/atomic.py','zeppelin_factory_test')
    rows=extract(factory.steps(NS(out=ROOT/'build/yorimichi')),checkout=ROOT,build_root=ROOT/'build')
    return load('games/yorimichi/v2_geometry_templates.py','zeppelin_templates_test').geometry_templates(rows,checkout=ROOT)


@pytest.fixture(scope='module')
def declaration():
    original=geometry()
    natives={units.MATERIAL:{'unit':'village.material','item':'asset','package':units.MATERIAL,'dependencies':['/Game/Palette']},
        '/Game/Palette':{'unit':'palette','item':'asset','package':'/Game/Palette'}}
    return original,units.attach_followers(original,natives,checkout=ROOT)


def test_actual_ten_parents_and_independent_fabric_owner(declaration):
    original,result=declaration
    assert len(result['templates'])==10 and all('followers' not in t for t in original['templates'])
    assert 'aliases' not in result and 'data_targets' not in result
    assert len(result['units'])==1
    unit=result['units'][0]
    assert unit['script']==units.FINISH and unit['inputs']==[] and unit['params']=={'args':{'op':'fabric'},'settings':[]}
    assert unit['outputs'][0]['logical_path']==units.FABRIC and unit['outputs'][0]['class']=='Material'
    assert units.MATERIAL_SOURCE in unit['code']
    actual=[]
    for template in result['templates']:
        raw,finish=[f['unit'] for f in template['followers']];parent=finish['params']['args']['parent'];actual.append(parent)
        assert raw['params']['destination']=='/Game/_Raw/Zeppelin/$piece'
        assert finish['params']['destination']=='/Game/Japan/Assets/$piece'
        assert finish['inputs'][2]['source']=={'kind':'group_member','unit':template['producer'],'group':'geometry','piece':'$piece'}
        args=finish['params']['args'];native=args['native_inputs']
        assert native[args['material']]==units.MATERIAL
        assert args['fabric']==('fabric' if parent=='ZP_Airship' else None)
        assert len(native)==(3 if parent=='ZP_Airship' else 2)
        if parent=='ZP_Airship':assert native[args['fabric']]==units.FABRIC
        assert result['module_requirements'][template['unit_prefix']][0]['name']=='Yorimichi'
        assert all((ROOT/path).is_file() for path in finish['code'])
        assert units.MATERIAL_SOURCE not in finish['code']
    assert tuple(actual)==body.PARENTS


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
    def get_material(self,i):return self.materials[i]
    def set_material(self,i,value):self.materials[i]=value
    def get_editor_property(self,key):return self.body
    def get_bounding_box(self):return NS(min=NS(**dict(zip('xyz',self.low))),max=NS(**dict(zip('xyz',self.high))))


def native_case(tmp_path,monkeypatch,name='ZP_Motors'):
    source=tmp_path/'source';payload=tmp_path/'payload';source.mkdir();payload.mkdir()
    piece=dict(positions=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],faces=[[0,1,2]],normals=[[0.,0.,1.]]*3,materials=[0],smooth=[False],uvs=[('UVMap',[[0.,0.],[1.,0.],[0.,1.]])],colours=[])
    hulls=[];slots=['ZeppelinPalette','ZeppelinFabric'] if name=='ZP_Airship' else ['ZeppelinPalette']
    packet=mesh_ir.encode(piece,key=name,slots=slots,matrix=np.eye(4).tolist(),options=body.OPTIONS,collisions=hulls)
    (payload/(name+'.npz')).write_bytes(packet);facts={'min':[0.,0.,0.],'max':[1.,1.,0.]}
    (source/(name+'.fbx')).write_bytes(b'producer verified FBX')
    publish_receipt(source,key=name,primary=name+'.fbx',triangles=1,bounds=[facts['min'],facts['max']],metadata={'geometry_sha256':hashlib.sha256(packet).hexdigest(),'slots':slots,'polygons':1,'collision_hulls':len(hulls),'uv_channels':['UVMap']})
    raw_path='/Game/_Raw/Zeppelin/'+name;dest='/Game/Japan/Assets/'+name
    raw=Mesh(raw_path);raw.triangles=raw.lods=raw.uvs=1;raw.materials=[None]*len(slots);raw.static_materials=[Props(imported_material_slot_name=slot) for slot in slots]
    raw.body=Props(collision_trace_flag='original-default');raw.settings=Props(use_full_precision_u_vs=True)
    raw.hulls=[[[p[0]*100,-p[1]*100,p[2]*100] for p in h['vertices']] for h in hulls]
    raw.low,raw.high=[0.,-100.,0.],[100.,0.,0.]
    assets={raw_path:raw,units.MATERIAL:Material(units.MATERIAL),units.FABRIC:Material(units.FABRIC)};events=[]
    content=tmp_path/'Content';content.mkdir();state=NS(raw=raw,assets=assets,events=events,save=True,primary=True,post=False,cook=True)
    def duplicate(path,target):mesh=deepcopy(assets[path]);mesh.path=target;assets[target]=mesh;events.append('duplicate');return mesh
    def save(mesh,only_if_is_dirty=False):
        assert only_if_is_dirty is False;events.append('save')
        if state.primary:
            path=content/(mesh.path.removeprefix('/Game/')+'.uasset');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'primary')
        if state.post:mesh.uvs=2
        return state.save
    editor=NS(get_lod_build_settings=lambda mesh,lod:mesh.settings,get_num_uv_channels=lambda mesh,lod:mesh.uvs)
    unreal=NS(StaticMesh=Mesh,MaterialInterface=Material,StaticMeshEditorSubsystem=object(),get_editor_subsystem=lambda cls:editor,load_module=lambda name:None,
        CollisionTraceFlag=NS(CTF_USE_COMPLEX_AS_SIMPLE='complex'),CitySurfaceValidation=NS(collision_vertices=lambda mesh:json.dumps(mesh.hulls),validate_collision=lambda mesh,triangles,simple:state.cook),EditorAssetLibrary=NS(load_asset=assets.get,does_asset_exist=lambda p:p in assets,duplicate_asset=duplicate,save_loaded_asset=save))
    monkeypatch.setitem(sys.modules,'unreal',unreal)
    context=NS(job_dir=str(tmp_path),content_dir=str(content),inputs={'raw':'raw','material':'mat','source_export':str(source),'payload':str(payload)},packages={'raw':[raw_path],'material':[units.MATERIAL],'source_export':[],'payload':[]},outputs=[dest],params={'op':'finish','kind':'static_mesh','source':'raw','destination':dest,'package_sources':{'raw':raw_path},'args':{'parent':name,'source_export':'source_export','payload':'payload','material':'material','fabric':None,'native_inputs':{'material':units.MATERIAL}}})
    if name=='ZP_Airship':
        context.inputs['fabric']='fabric';context.packages['fabric']=[units.FABRIC];context.params['args']['fabric']='fabric';context.params['args']['native_inputs']['fabric']=units.FABRIC
    return state,context,unreal


@pytest.mark.parametrize('name',body.PARENTS)
def test_native_preserves_imported_policies_and_selects_original_material(tmp_path,monkeypatch,name):
    state,context,_=native_case(tmp_path,monkeypatch,name)
    mesh=body.run(context)
    assert mesh.body.values['collision_trace_flag']=='complex' and mesh.settings.values['use_full_precision_u_vs'] is True
    assert mesh.hulls==[] and state.raw.materials==[None]*len(mesh.materials) and state.events==['duplicate','save']
    assert mesh.materials[0].path==units.MATERIAL
    if name=='ZP_Airship':assert mesh.materials[1].path==units.FABRIC
    assert state.raw.body.values['collision_trace_flag']=='original-default'


@pytest.mark.parametrize('damage',['triangles','bounds','uv','hulls','save','primary','post','slot','validator','cook'])
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
    elif damage=='cook':state.cook=False
    else:unreal.CitySurfaceValidation=None
    with pytest.raises((ValueError,RuntimeError)):body.run(context)


@pytest.mark.parametrize('damage',['matrix','options','export','payload','material','fresh','finite','native'])
def test_source_and_owned_package_checks_precede_save(tmp_path,monkeypatch,damage):
    state,context,_=native_case(tmp_path,monkeypatch)
    if damage in ('matrix','options'):
        root=Path(context.inputs['payload']);path=root/'ZP_Motors.npz'
        meta,piece=mesh_ir.decode(path.read_bytes())
        if damage=='matrix':meta['matrix'][0][3]=1.
        else:meta['options']['axis_forward']='X'
        packet=mesh_ir.encode(piece,key=meta['asset'],slots=meta['slots'],matrix=meta['matrix'],options=meta['options'],collisions=[])
        path.write_bytes(packet)
    elif damage=='export':(Path(context.inputs['source_export'])/'other.fbx').write_bytes(b'sibling')
    elif damage=='payload':(Path(context.inputs['payload'])/'other.npz').write_bytes(b'sibling')
    elif damage=='material':context.params['args']['native_inputs']['material']=units.FABRIC
    elif damage=='fresh':state.assets[context.outputs[0]]=Mesh(context.outputs[0])
    elif damage=='finite':state.raw.low[0]=float('nan')
    else:context.params['args']['native_inputs']['missing']='/Game/Missing'
    with pytest.raises(ValueError):body.run(context)
    assert 'save' not in state.events


def test_fbx_options_match_the_actual_existing_zeppelin_planner():
    tree=ast.parse((GAME/'world/regions/zeppelin/plan_asset.py').read_text())
    call=next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='plan')
    options=next(kw.value for kw in call.keywords if kw.arg=='options')
    assert {kw.arg:ast.literal_eval(kw.value) for kw in options.keywords}==body.OPTIONS
    assert next(kw.value.value for kw in call.keywords if kw.arg=='partition')=='whole'
    source=(GAME/'world/regions/zeppelin/primitives.py').read_text()
    assert "data.materials.append(fabric)" in source and "fabric.name='ZeppelinFabric'" in source


def fabric_case(tmp_path,monkeypatch):
    assets={};nodes=[];saves=[];links=[];state=NS(save=True,primary=True)
    class AuthoredMaterial(Material,Props):
        def __init__(self,path):Material.__init__(self,path);Props.__init__(self)
    def create(name,folder,cls,factory):asset=AuthoredMaterial(folder+'/'+name);assets[asset.path]=asset;return asset
    def node(mat,cls,x,y):value=Props();value.kind=cls;nodes.append(value);return value
    content=tmp_path/'Content';content.mkdir()
    def save(asset,only_if_is_dirty=True):
        saves.append(only_if_is_dirty)
        if state.primary:
            path=content/(asset.path.removeprefix('/Game/')+'.uasset');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'actual primary')
        return state.save
    unreal=NS(EditorAssetLibrary=NS(load_asset=assets.get,does_asset_exist=lambda path:path in assets,save_loaded_asset=save),
        AssetToolsHelpers=NS(get_asset_tools=lambda:NS(create_asset=create)),Material=AuthoredMaterial,MaterialFactoryNew=lambda:None,
        MaterialEditingLibrary=NS(delete_all_material_expressions=lambda mat:None,create_material_expression=node,
            connect_material_expressions=lambda *a:links.append(a) or True,connect_material_property=lambda *a:links.append(a) or True,recompile_material=lambda mat:None),
        LinearColor=lambda *v:v,CustomInput=Props,CustomMaterialOutputType=NS(CMOT_FLOAT3=3),
        MaterialProperty=NS(MP_EMISSIVE_COLOR='emissive'),MaterialShadingModel=NS(MSM_UNLIT='unlit'))
    for name in ('VertexColor','PixelNormalWS','PixelDepth','VectorParameter','Custom'):
        setattr(unreal,'MaterialExpression'+name,name)
    monkeypatch.setitem(sys.modules,'unreal',unreal)
    path=tmp_path/body.ORIGINAL;path.parent.mkdir(parents=True)
    # Every actual importer top-level import/call remains present but cannot run.
    path.write_text("raise AssertionError('original importer top-level executed')\n"+(ROOT/body.ORIGINAL).read_text()+"\nraise AssertionError('original footer executed')\n")
    context=NS(job_dir=tmp_path,content_dir=content,inputs={},packages={},outputs=[units.FABRIC],params={'args':{'op':'fabric'},'settings':[]})
    return state,context,assets,nodes,saves,links,path


def test_original_fabric_graph_executes_without_any_poisoned_importer_top_level(tmp_path,monkeypatch):
    _,context,assets,nodes,saves,links,_=fabric_case(tmp_path,monkeypatch)
    asset=body.run(context)
    assert list(assets)==[units.FABRIC] and saves==[True,False]
    assert asset.values=={'shading_model':'unlit'}
    assert [n.kind for n in nodes]==['VertexColor','PixelNormalWS','PixelDepth','VectorParameter','Custom']
    sun=nodes[3];shade=nodes[4]
    assert sun.values=={'parameter_name':'SunDirection','default_value':(-.646,-.173,.743,0)}
    assert [p.values['input_name'] for p in shade.values['inputs']]==['C','N','D','Z']
    assert shade.values['output_type']==3
    assert shade.values['code']=='float3 Base=lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C)); float light=.72+.58*smoothstep(-1.,1.,dot(normalize(N),normalize(D))); return lerp(Base*light,float3(.64,.68,.76),saturate((Z-7000.)/220000.)*.5);'
    assert len(links)==5 and links[-1][-1]=='emissive'


@pytest.mark.parametrize('damage',['save','primary','fresh','source','duplicate','foreign','inputs'])
def test_fabric_cannot_certify_unowned_or_unsaved_material(tmp_path,monkeypatch,damage):
    state,context,assets,_,_,_,path=fabric_case(tmp_path,monkeypatch)
    if damage=='save':state.save=False
    elif damage=='primary':state.primary=False
    elif damage=='fresh':assets[units.FABRIC]=Material(units.FABRIC)
    elif damage=='source':path.unlink()
    elif damage=='duplicate':path.write_text(path.read_text()+'\ndef fabric_material():return None\n')
    elif damage=='foreign':context.outputs=['/Game/Other']
    else:context.inputs={'ambient':'input'}
    with pytest.raises((ValueError,RuntimeError)):body.run(context)


@pytest.mark.parametrize('damage',['slot','fabric','roster'])
def test_airship_cannot_lose_or_misbind_its_original_fabric_slot(tmp_path,monkeypatch,damage):
    state,context,_=native_case(tmp_path,monkeypatch,'ZP_Airship')
    if damage=='slot':state.raw.static_materials[1].values['imported_material_slot_name']='OtherFabric'
    elif damage=='fabric':context.params['args']['native_inputs']['fabric']=units.MATERIAL
    else:state.raw.static_materials.pop()
    with pytest.raises(ValueError):body.run(context)
    assert 'save' not in state.events
