"""Actual Kart constructors, native source/collision fidelity and byte-exact authored runtime data."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tarfile
from types import SimpleNamespace as NS

import numpy as np
import pytest
from atelier import mesh_ir,mesh_collision
from atelier.build_v2 import recipe_job
from atelier.build_v2.blender_validate import decode_mesh_payload
from atelier.build_v2.recipe_dependencies import extract
from atelier.export_manifest import publish_receipt

ROOT=Path(__file__).resolve().parents[3];GAME=ROOT/'games/yorimichi'
sys.path[:0]=[str(GAME),str(GAME/'world')]


def load(relative,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/relative)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


units=load('games/yorimichi/v2_kart_units.py','kart_units_test')
body=load(units.FINISH,'kart_finish_test');data_body=load(units.DATA,'kart_data_test')


@pytest.fixture(scope='module')
def declaration():
    factory=load('games/yorimichi/vehicle_atomic_build.py','kart_factory_test')
    rows=extract(factory.steps(NS(out=ROOT/'build/yorimichi'),'kart'),checkout=ROOT,build_root=ROOT/'build')
    geometry=load('games/yorimichi/v2_geometry_templates.py','kart_templates_test').geometry_templates(rows,checkout=ROOT)
    return geometry,units.attach_followers(geometry,{},checkout=ROOT)


def test_actual_four_rigid_parents_material_and_complete_data_sources(declaration):
    original,result=declaration
    assert all('followers' not in t for t in original['templates']) and len(result['templates'])==4
    material,data=result['units'];assert material['id']==units.MATERIAL_UNIT and data['id']==units.DATA_UNIT
    assert material['script']==units.CALL and material['params']['args']['function']=='material'
    assert material['outputs'][0]['class']=='Material' and material['outputs'][0]['logical_path']==units.MATERIAL
    assert data['op']=={'kind':'py_data','version':'1'} and data['params']=={} and len(data['outputs'])==6
    inputs={i['name']:i['source'] for i in data['inputs']}
    assert inputs['cockpit']=={'kind':'item','unit':'world.kart.sources','item':'product4'}
    assert inputs['manifest']=={'kind':'item','unit':'world.kart','item':'product0'}
    assert {k for k in inputs if k.startswith('grip.')}=={'grip.cairo','grip.modori','grip.nox','grip.paul'}
    assert {k for k in inputs if k.startswith('model.')}=={'model.cairo','model.modori','model.nox','model.paul'}
    assert all(i.get('whole') for i in data['inputs'])
    assert all(o['class']=='JsonData' and o['destination']=='checkout' and o['files'][0]['install_path'].startswith('games/yorimichi/unreal/Content/Data/kart/') for o in data['outputs'])
    assert result['data_targets']==[units.DATA_UNIT] and 'aliases' not in result
    for template in result['templates']:
        raw,finish=[f['unit'] for f in template['followers']]
        assert raw['params']['destination']=='/Game/_Raw/Kart/$piece'
        assert finish['params']['destination']=='/Game/Japan/Kart/$piece'
        assert finish['inputs'][2]['source']=={'kind':'group_member','unit':template['producer'],'group':'geometry','piece':'$piece'}
        assert finish['inputs'][3]['source']=={'kind':'item','unit':units.MATERIAL_UNIT,'item':'asset'}
        assert result['module_requirements'][template['unit_prefix']][0]['name']=='Yorimichi'
        assert all((ROOT/p).is_file() for p in finish['code'])


class DataContext:
    params={}
    def __init__(self,inputs,outputs,output):self.inputs=inputs;self.outputs=outputs;self.output_dir=output
    def input(self,name):
        if self.inputs[name] is None:raise ValueError('missing input')
        return Path(self.inputs[name])
    def output(self,name):
        assert name in self.outputs;path=self.output_dir/name;path.parent.mkdir(parents=True,exist_ok=True);return path


def data_case(tmp_path,declaration):
    unit=declaration[1]['units'][1]
    cockpit_module=load('games/yorimichi/assets/vehicles/kart/cockpit.py','kart_actual_cockpit_test')
    cockpit=cockpit_module.load();cockpit_file=tmp_path/'actual-cockpit.json'
    cockpit_file.write_text(json.dumps(cockpit,indent=1)+'\n')
    names=('SM_Kart_Body','SM_Kart_Seat','SM_Kart_Wheel','SM_Kart_SteeringWheel')
    manifest={name:{'triangles':100} for name in names};manifest['layout']=cockpit
    manifest_file=tmp_path/'actual-manifest.json';manifest_file.write_text(json.dumps(manifest))
    assets=tmp_path/'source-assets';assets.mkdir();(assets/'part.fbx').write_bytes(b'actual complete source root')
    inputs={}
    for slot,path in [('cockpit',cockpit_file),('manifest',manifest_file)]:
        root=tmp_path/slot;root.mkdir()
        if slot=='manifest':recipe_job.pack_root(assets,root/'products-0.tree.tar')
        recipe_job.pack_root(path,root/'products-1.tree.tar');inputs[slot]=root
    for incoming in unit['inputs'][2:]:
        source=ROOT/incoming['source']['path'];target=tmp_path/'inputs'/incoming['name']
        if source.is_file():target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);inputs[incoming['name']]=target
        else:inputs[incoming['name']]=None
    output=tmp_path/'output';output.mkdir()
    return DataContext(inputs,[o['files'][0]['path'] for o in unit['outputs']],output),cockpit_file


def test_data_uses_original_apis_and_copies_exact_cockpit_grip_bytes(tmp_path,declaration):
    context,cockpit=data_case(tmp_path,declaration);data_body.run(context)
    assert (context.output_dir/'cockpit.json').read_bytes()==cockpit.read_bytes()
    identity=load(units.IDENTITY,'kart_identity_expected_test')
    assert (context.output_dir/'prepared-models.json').read_text()==json.dumps(identity.prepared_models(),indent=2)+'\n'
    for name in identity.playable_ids():assert (context.output_dir/'grips'/f'{name}.json').read_bytes()==identity.profile_path(name).read_bytes()
    assert not (context.output_dir/'.kart-inputs').exists()
    assert {p.relative_to(context.output_dir).as_posix() for p in context.output_dir.rglob('*') if p.is_file()}==set(context.outputs)


@pytest.mark.parametrize('damage',['layout','model','roster','missing','archive','budget'])
def test_invalid_authored_data_refuses_before_any_runtime_output(tmp_path,declaration,damage):
    context,_=data_case(tmp_path,declaration)
    if damage=='layout':
        path=context.inputs['grip.cairo'];pose=json.loads(path.read_text());pose['layout']['schema']=2;path.write_text(json.dumps(pose))
    elif damage=='model':
        path=context.inputs['model.cairo'];model=json.loads(path.read_text());model['model_sha256']='wrong';path.write_text(json.dumps(model))
    elif damage=='roster':context.inputs.pop('grip.cairo')
    elif damage=='missing':context.inputs['model.cairo']=None
    elif damage=='archive':next(context.inputs['cockpit'].glob('*.tree.tar')).write_bytes(b'bad archive')
    else:
        path=context.inputs['manifest']/'products-1.tree.tar';path.unlink();source=tmp_path/'large.json'
        cockpit=json.loads((tmp_path/'actual-cockpit.json').read_text());source.write_text(json.dumps({**{n:{'triangles':2000} for n in ('SM_Kart_Body','SM_Kart_Seat','SM_Kart_Wheel','SM_Kart_SteeringWheel')},'layout':cockpit}))
        recipe_job.pack_root(source,path)
    with pytest.raises((ValueError,KeyError,RuntimeError,tarfile.ReadError)):data_body.run(context)
    assert not list(context.output_dir.iterdir())


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


def native_case(tmp_path,monkeypatch,body_mesh=False):
    name='SM_Kart_Body' if body_mesh else 'SM_Kart_Wheel';source=tmp_path/'source';payload=tmp_path/'payload';source.mkdir();payload.mkdir()
    piece=dict(positions=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],faces=[[0,1,2]],normals=[[0.,0.,1.]]*3,materials=[0],smooth=[False],uvs=[('UVMap',[[0.,0.],[1.,0.],[0.,1.]])],colours=[])
    hulls=[]
    if body_mesh:
        tetra=dict(positions=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]],faces=[[0,1,2],[0,3,1],[1,3,2],[0,2,3]],normals=[[0.,0.,1.]]*12,materials=[0]*4,smooth=[False]*4,uvs=[],colours=[])
        hulls=[mesh_collision.encode(tetra,slots=['Hull'],matrix=np.eye(4).tolist())]
    packet=mesh_ir.encode(piece,key=name,slots=['KartPalette'],matrix=np.eye(4).tolist(),options={},collisions=hulls)
    (payload/(name+'.npz')).write_bytes(packet);_,_,facts=decode_mesh_payload(packet,expected_asset=name)
    (source/(name+'.fbx')).write_bytes(b'producer verified FBX')
    publish_receipt(source,key=name,primary=name+'.fbx',triangles=1,bounds=[facts['min'],facts['max']],metadata={'geometry_sha256':hashlib.sha256(packet).hexdigest(),'slots':['KartPalette'],'polygons':1,'collision_hulls':len(hulls),'uv_channels':['UVMap']})
    raw_path='/Game/_Raw/Kart/'+name;dest='/Game/Japan/Kart/'+name
    raw=Mesh(raw_path);raw.triangles=raw.lods=raw.uvs=1;raw.material=None;raw.static_materials=[Props(imported_material_slot_name='KartPalette')]
    raw.body=Props(collision_trace_flag='original-default');raw.settings=Props(use_full_precision_u_vs=True)
    raw.hulls=[[[p[0]*100,-p[1]*100,p[2]*100] for p in h['vertices']] for h in hulls]
    raw.low,raw.high=[0.,-100.,0.],[100.,0.,0.];assets={raw_path:raw,units.MATERIAL:Material(units.MATERIAL)};events=[]
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
    context=NS(job_dir=str(tmp_path),content_dir=str(content),inputs={'raw':'raw','material':'mat','source_export':str(source),'payload':str(payload)},packages={'raw':[raw_path],'material':[units.MATERIAL],'source_export':[],'payload':[]},outputs=[dest],params={'op':'finish','kind':'static_mesh','source':'raw','destination':dest,'package_sources':{'raw':raw_path},'args':{'parent':name,'source_export':'source_export','payload':'payload','material':'material'}})
    return state,context,unreal


@pytest.mark.parametrize('body_mesh',[False,True])
def test_native_preserves_original_imported_collision_uv_precision_and_exact_hulls(tmp_path,monkeypatch,body_mesh):
    state,context,_=native_case(tmp_path,monkeypatch,body_mesh)
    mesh=body.run(context)
    assert mesh.body.values['collision_trace_flag']=='original-default' and mesh.settings.values['use_full_precision_u_vs'] is True
    assert mesh.hulls==state.raw.hulls and state.raw.material is None and state.events==['duplicate','save']


@pytest.mark.parametrize('damage',['triangles','bounds','uv','hulls','save','primary','post','slot','validator'])
def test_wrong_native_geometry_or_collision_cannot_finish(tmp_path,monkeypatch,damage):
    state,context,unreal=native_case(tmp_path,monkeypatch,True)
    if damage=='triangles':state.raw.triangles=2
    elif damage=='bounds':state.raw.low=[1.,-100.,0.]
    elif damage=='uv':state.raw.uvs=2
    elif damage=='hulls':state.raw.hulls[0][0][0]=10.
    elif damage=='save':state.save=False
    elif damage=='primary':state.primary=False
    elif damage=='post':state.post=True
    elif damage=='slot':state.raw.static_materials[0].values['imported_material_slot_name']='Other'
    else:unreal.CitySurfaceValidation=None
    with pytest.raises((ValueError,RuntimeError)):body.run(context)


def test_original_kart_material_is_inert_and_existing_generic_call_preserves_graph(tmp_path,monkeypatch,declaration):
    assets={};nodes=[];saves=[]
    def create(name,folder,cls,factory):asset=Material(folder+'/'+name);assets[asset.path]=asset;return asset
    def node(mat,cls,x,y):value=Props();value.kind=cls;nodes.append(value);return value
    def save(asset,*args):saves.append((asset.path,args));return True
    unreal=NS(EditorAssetLibrary=NS(load_asset=assets.get,does_asset_exist=lambda path:path in assets,save_loaded_asset=save),
        AssetToolsHelpers=NS(get_asset_tools=lambda:NS(create_asset=create)),Material=Material,MaterialFactoryNew=lambda:None,
        MaterialEditingLibrary=NS(delete_all_material_expressions=lambda mat:None,create_material_expression=node,
            connect_material_expressions=lambda *a:True,connect_material_property=lambda *a:True,recompile_material=lambda mat:None),
        LinearColor=lambda *v:v,CustomInput=Props,CustomMaterialOutputType=NS(CMOT_FLOAT3=3),
        MaterialProperty=NS(MP_BASE_COLOR='base',MP_ROUGHNESS='roughness',MP_SPECULAR='specular'))
    for name in ('VertexColor','Custom','VectorParameter','Multiply','Constant'):setattr(unreal,'MaterialExpression'+name,name)
    monkeypatch.setitem(sys.modules,'unreal',unreal)
    load(units.MATERIAL_SOURCE,'inert_kart_material_test');assert assets=={} and nodes==[]
    path=tmp_path/units.MATERIAL_SOURCE;path.parent.mkdir(parents=True);path.write_bytes((ROOT/units.MATERIAL_SOURCE).read_bytes())
    material=declaration[1]['units'][0]
    generic=load(units.CALL,'kart_generic_author_test')
    generic.run(NS(job_dir=tmp_path,inputs={},packages={},outputs=[units.MATERIAL],params=material['params']))
    assert list(assets)==[units.MATERIAL] and len(saves)==2
    assert {n.values['r'] for n in nodes if n.kind=='Constant'}=={.82,.2}
    assert next(n.values['default_value'] for n in nodes if n.kind=='VectorParameter')==(1,1,1,1)
    assert next(n.values['code'] for n in nodes if n.kind=='Custom')=='return lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C));'
