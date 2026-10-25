"""Actual remaining Hidamari factory and independent original native body checks."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
from copy import deepcopy

import numpy as np
import pytest
from atelier import mesh_ir,mesh_collision
from atelier.build_v2 import recipe_job
from atelier.build_v2.recipe_dependencies import extract
from atelier.export_manifest import publish_receipt

ROOT=Path(__file__).resolve().parents[3];GAME=ROOT/'games/yorimichi'
sys.path[:0]=[str(GAME),str(GAME/'world'),str(GAME/'unreal/Scripts')]


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


units=load('games/yorimichi/v2_hidamari_units.py','hd_units_test')
body=load(units.SCRIPT,'hd_body_test')


@pytest.fixture(scope='module')
def declaration():
    factory=load('games/yorimichi/hidamari_prop_build.py','hd_factory_test')
    rows=extract(factory.steps(NS(out=ROOT/'build/yorimichi')),checkout=ROOT,build_root=ROOT/'build')
    geometry=load('games/yorimichi/v2_geometry_templates.py','hd_templates_test').geometry_templates(rows,checkout=ROOT)
    return geometry,units.attach_followers(geometry,{},checkout=ROOT)


def test_actual_complete_prop_family_and_original_material_source_closure(declaration):
    original,result=declaration
    assert len(result['templates'])==48 and all('followers' not in t for t in original['templates'])
    assert len(result['units'])==182 and len(result['packages'])==123
    assert result['composition_requirements']==['unreal.city_tiles','world.hidamari_props'] and 'aliases' not in result
    by_id={u['id']:u for u in result['units']}
    for template in result['templates']:
        raw,finish=[f['unit'] for f in template['followers']];args=finish['params']['args'];name=args['name'];level=args['level']
        assert finish['inputs'][2]['source']=={'kind':'group_member','unit':template['producer'],'group':'geometry','piece':'$piece'}
        assert finish['inputs'][3]['source']=={'kind':'item','unit':template['producer'],'item':'product1'}
        assert args['data']['file']=='products/1-0.tree.tar'
        assert finish['params']['destination']==('/Game/Japan/Hidamari/PropLODs/'+args['base']+'/' if level else '/Game/Japan/Assets/')+'$piece'
        assert len(args['lod_records'])==(3 if name.startswith('Tree_') and not level else 0)
        if args['lod_records']:
            assert len(args['lods']['derived_items']['templates'])==3
            assert all(t['follower']==1 and t['item']=='asset' for t in args['lods']['derived_items']['templates'])
        assert result['module_requirements'][template['unit_prefix']][0]['name']=='Yorimichi'
    city=by_id['unreal.hidamari.texture.raw.T_HD_plaster']
    assert city['inputs'][0]['source']=={'kind':'item','unit':'world.hidamari_textures','item':'output0'}
    assert city['params']['input_roots']=={'source':{'archive_member':'outputs/0.tree.tar','name':'source'}}
    assert city['params']['source_member']=='plaster.png'
    prop=by_id['unreal.hidamari.texture.raw.T_HD_P_bicycle']
    assert prop['inputs'][0]['source']['item']=='product1'
    for unit in result['units']:
        assert all((ROOT/p).is_file() for p in unit['code'])
        assert all(not p.endswith('import_hidamari.py') for p in unit['code'])


class Props:
    def __init__(self,**values):self.values=values
    def get_editor_property(self,name):return self.values[name]
    def set_editor_property(self,name,value):self.values[name]=value
class Asset(Props):
    def __init__(self,path):super().__init__();self.path=path
    def get_path_name(self):return self.path+'.'+self.path.rsplit('/',1)[-1]
class Material(Asset):pass
class Mesh(Asset):
    def get_num_triangles(self,index):return self.triangles[index]
    def get_num_lods(self):return len(self.triangles)
    def get_material(self,index):return self.material
    def set_material(self,index,value):self.material=value
    def get_editor_property(self,key):return self.body if key=='body_setup' else super().get_editor_property(key)
    def get_bounding_box(self):return NS(min=NS(x=0.,y=-100.,z=0.),max=NS(x=100.,y=0.,z=0.))


class Enum:
    def __getattr__(self,name):return name
class Unreal(NS):
    def __getattr__(self,name):
        if name.startswith('MaterialExpression'):return name
        return Enum()


def native(tmp_path,monkeypatch):
    assets={};events=[];state=NS(save=True,primary=True,post=False)
    content=tmp_path/'Content';content.mkdir();nodes=[];scalars={}
    def create(name,folder,cls,factory):asset=Material(folder+'/'+name);assets[asset.path]=asset;return asset
    def node(mat,cls,*xy):value=Props();value.kind=cls;nodes.append(value);return value
    def save(asset,only_if_is_dirty=True):
        events.append(('save',asset.path))
        if state.primary:
            target=content/(asset.path.removeprefix('/Game/')+'.uasset');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b'actual primary')
        if state.post and isinstance(asset,Mesh):asset.triangles[0]+=1
        return state.save
    def duplicate(source,target):asset=deepcopy(assets[source]);asset.path=target;assets[target]=asset;events.append(('duplicate',target));return asset
    editor=NS(get_lod_build_settings=lambda mesh,index:mesh.settings,get_num_uv_channels=lambda mesh,index:1,
        set_lod_from_static_mesh=lambda mesh,index,source,source_lod,recompute:mesh.triangles.append(source.triangles[0]) or index,
        set_lod_screen_sizes=lambda mesh,values:setattr(mesh,'screens',values) or True,get_lod_screen_sizes=lambda mesh:mesh.screens)
    unreal=Unreal(Material=Material,MaterialInterface=Material,StaticMesh=Mesh,CustomInput=Props,LinearColor=lambda *args:args,MaterialFactoryNew=lambda:None,
        MaterialInstanceConstant=Material,MaterialInstanceConstantFactoryNew=lambda:None,
        AssetToolsHelpers=NS(get_asset_tools=lambda:NS(create_asset=create)),
        EditorAssetLibrary=NS(load_asset=assets.get,does_asset_exist=lambda p:p in assets,save_loaded_asset=save,duplicate_asset=duplicate),
        MaterialEditingLibrary=NS(delete_all_material_expressions=lambda mat:None,create_material_expression=node,connect_material_expressions=lambda *a:True,
            connect_material_property=lambda *a:True,recompile_material=lambda mat:None,layout_material_expressions=lambda mat:None,set_material_instance_parent=lambda mi,parent:mi.set_editor_property('parent',parent),
            set_material_instance_texture_parameter_value=lambda mi,key,tex:mi.set_editor_property(key,tex),
            set_material_instance_scalar_parameter_value=lambda mi,key,value:scalars.update({(mi.path,key):value}),update_material_instance=lambda mi:None),
        load_module=lambda name:None,StaticMeshEditorSubsystem=object(),get_editor_subsystem=lambda cls:editor,
        CitySurfaceValidation=NS(collision_vertices=lambda mesh:json.dumps(mesh.hulls)))
    monkeypatch.setitem(sys.modules,'unreal',unreal)
    return state,assets,events,content,nodes,scalars


def freeze(tmp_path,name,record):
    root=tmp_path/name;root.mkdir();source=tmp_path/(name+'-data');source.mkdir();(source/'record.json').write_text(json.dumps(record))
    archive=root/'products/1-0.tree.tar';archive.parent.mkdir();recipe_job.pack_root(source,archive);return root


@pytest.mark.parametrize('package',['M_PlazaWater','M_PondWater','M_PlazaPaving','M_Arcade','M_ArcadePaving','M_Harbor','M_HarborWater','M_HDCity','MI_HD_plaster','MI_HD_P_bicycle'])
def test_original_material_factories_use_only_declared_native_reads_and_keyed_data(tmp_path,monkeypatch,declaration,package):
    _,assets,_,content,nodes,scalars=native(tmp_path,monkeypatch)
    unit=next(u for u in declaration[1]['units'] if u['id']=='unreal.hidamari.material.'+package);args=unit['params']['args']
    inputs={};packages={}
    for slot,path in args['native_inputs'].items():assets[path]=Material(path);inputs[slot]='native';packages[slot]=[path]
    if args['data']:
        if args.get('prop'):record={'schema':1,'name':'HD_P_bicycle','parent':'HD_P_bicycle','lod':0,'info':{'gain':1.6}}
        else:record={'plaster':{'tile_m':2.}}
        root=freeze(tmp_path,'metadata',record)
        if not args.get('prop'):
            old=root/'products/1-0.tree.tar';target=root/'outputs/0.tree.tar';target.parent.mkdir();old.unlink()
            # Same actual ROOT codec; select original textures.json instead of prop record.
            source=tmp_path/'palette';source.mkdir();(source/'textures.json').write_text(json.dumps(record));recipe_job.pack_root(source,target)
        inputs['data']=root;packages['data']=[]
    for name in ('city_material','arcade_material','harbor_material','plaza_material'):
        path=tmp_path/body.SCRIPTS/(name+'.py');path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text("raise AssertionError('old material module executed')\n"+(GAME/'unreal/Scripts'/(name+'.py')).read_text())
    result=body.run(NS(job_dir=tmp_path,content_dir=content,params=unit['params'],inputs=inputs,packages=packages,outputs=[args['package']]))
    assert result.path==args['package']
    if package=='MI_HD_P_bicycle':assert scalars[(result.path,'Gain')]==.8 and scalars[(result.path,'Macro')]==0.
    elif package=='MI_HD_plaster':assert scalars[(result.path,'Tile')]==2.
    else:assert nodes


def prop_case(tmp_path,monkeypatch,declaration,tree=False,solid=False):
    state,assets,events,content,_,_=native(tmp_path,monkeypatch);name='Tree_Caldera_BlackPine_A' if tree else 'HD_P_bus_stop' if solid else 'HD_P_bicycle'
    template=next(t for t in declaration[1]['templates'] if t['unit_prefix'].endswith('.'+name));unit=template['followers'][1]['unit'];params=deepcopy(unit['params']);args=params['args']
    definition=tmp_path/'definition.json';definition.write_bytes((GAME/'assets/hidamari/prop-export-parameters'/(name+'.json')).read_bytes());inputs={'definition':definition};packages={'definition':[]}
    for slot,path in args['native_inputs'].items():assets[path]=Material(path);inputs[slot]='native';packages[slot]=[path]
    piece=dict(positions=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],faces=[[0,1,2]],normals=[[0.,0.,1.]]*3,materials=[0],smooth=[False],uvs=[('UVMap',[[0.,0.],[1.,0.],[0.,1.]])],colours=[])
    hulls=[]
    if solid:
        tetra=dict(positions=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]],faces=[[0,1,2],[0,3,1],[1,3,2],[0,2,3]],normals=[[0.,0.,1.]]*12,materials=[0]*4,smooth=[False]*4,uvs=[],colours=[])
        hulls=[mesh_collision.encode(tetra,slots=['Hull'],matrix=np.eye(4).tolist())]
    packet=mesh_ir.encode(piece,key=name,slots=['OriginalProp'],matrix=np.eye(4).tolist(),options={},collisions=hulls)
    payload=tmp_path/'payload';payload.mkdir();(payload/(name+'.npz')).write_bytes(packet);inputs['payload']=payload;packages['payload']=[]
    source=tmp_path/'export';source.mkdir();(source/(name+'.fbx')).write_bytes(b'actual source')
    publish_receipt(source,key=name,primary=name+'.fbx',triangles=1,bounds=[[0.,0.,0.],[1.,1.,0.]],metadata={'geometry_sha256':hashlib.sha256(packet).hexdigest(),'slots':['OriginalProp'],'polygons':1,'collision_hulls':len(hulls),'uv_channels':['UVMap']})
    inputs['source_export']=source;packages['source_export']=[]
    record={'schema':1,'name':name,'parent':name,'lod':0,'level':[1,1.],'info':{'boxes':int(solid),'gain':1.},'hulls':hulls}
    inputs['data']=freeze(tmp_path,'base-record',record);packages['data']=[]
    raw_path='/Game/_Raw/Hidamari/'+name;raw=Mesh(raw_path);raw.triangles=[1];raw.body=Props(collision_trace_flag='raw');raw.settings=Props(use_full_precision_u_vs=True)
    raw.static_materials=[Props(imported_material_slot_name='OriginalProp')];raw.material=None;raw.hulls=[[[p[0]*100,-p[1]*100,p[2]*100] for p in h['vertices']] for h in hulls];assets[raw_path]=raw;inputs['raw']='raw';packages['raw']=[raw_path]
    if tree:
        # Use a large independent original triangle count so the real strict LOD reduction check is exercised.
        raw.triangles=[1000]
        root=json.loads((source/'export.json').read_text());root['triangles']=1000
        # Rebuild source packet and receipt rather than bypassing its own native source proof.
        piece['faces']=[[0,1,2]]*1000;piece['normals']=[[0.,0.,1.]]*3000;piece['materials']=[0]*1000;piece['smooth']=[False]*1000;piece['uvs']=[('UVMap',[[0.,0.],[1.,0.],[0.,1.]]*1000)]
        packet=mesh_ir.encode(piece,key=name,slots=['OriginalProp'],matrix=np.eye(4).tolist(),options={},collisions=[]);(payload/(name+'.npz')).write_bytes(packet)
        publish_receipt(source,key=name,primary=name+'.fbx',triangles=1000,bounds=[[0.,0.,0.],[1.,1.,0.]],metadata={'geometry_sha256':hashlib.sha256(packet).hexdigest(),'slots':['OriginalProp'],'polygons':1000,'collision_hulls':0,'uv_channels':['UVMap']})
        record['level']=[1000,1.];(tmp_path/'base-record-data/record.json').write_text(json.dumps(record));(inputs['data']/'products/1-0.tree.tar').unlink();recipe_job.pack_root(tmp_path/'base-record-data',inputs['data']/'products/1-0.tree.tar')
        rows=[]
        for index,(count,size) in enumerate(((300,.25),(100,.1),(30,.04)),1):
            key=name+'_LOD'+str(index);slot='derived_'+str(index);path='/Game/Japan/Hidamari/PropLODs/'+name+'/'+key
            asset=deepcopy(raw);asset.path=path;asset.triangles=[count];asset.material=assets[args['material']];assets[path]=asset;inputs[slot]='native';packages[slot]=[path];rows.append({'piece':key,'root':'lods/'+key,'slot':slot})
            value={**record,'name':key,'lod':index,'level':[count,size]};selection=args['lod_records'][index-1]
            inputs[selection['slot']]=freeze(tmp_path,'lod-record'+str(index),value);packages[selection['slot']]=[]
        args['lods']={'derived_items':{'root':'lods','members':rows}}
    destination='/Game/Japan/Assets/'+name;params['destination']=destination;params['package_sources']['raw']=raw_path
    return state,assets,events,raw,NS(job_dir=tmp_path,content_dir=content,params=params,inputs=inputs,packages=packages,outputs=[destination])


@pytest.mark.parametrize('tree',[False,True])
def test_prop_and_complete_conifer_lods_save_only_their_owned_package(tmp_path,monkeypatch,declaration,tree):
    _,_,events,raw,context=prop_case(tmp_path,monkeypatch,declaration,tree)
    result=body.run(context)
    assert raw.material is None and raw.triangles==([1000] if tree else [1])
    assert result.get_num_lods()==(4 if tree else 1) and result.body.values['collision_trace_flag']=='CTF_USE_SIMPLE_AS_COMPLEX'
    assert [path for action,path in events if action=='save']==list(context.outputs)


@pytest.mark.parametrize('damage',['save','primary','post','hulls','roster','lod'])
def test_incomplete_or_unsaved_props_cannot_finish(tmp_path,monkeypatch,declaration,damage):
    state,assets,_,raw,context=prop_case(tmp_path,monkeypatch,declaration,tree=True)
    if damage=='save':state.save=False
    elif damage=='primary':state.primary=False
    elif damage=='post':state.post=True
    elif damage=='hulls':raw.hulls=[[[0,0,0],[1,0,0],[0,1,0],[0,0,1]]]
    elif damage=='roster':context.params['args']['lods']['derived_items']['members'].pop()
    else:assets[context.packages['derived_2'][0]].material=None
    with pytest.raises((ValueError,RuntimeError)):body.run(context)


def test_conifer_preserves_original_two_percent_import_tolerance_and_lod0(tmp_path,monkeypatch,declaration):
    _,_,_,raw,context=prop_case(tmp_path,monkeypatch,declaration,tree=True)
    raw.triangles[0]=999
    result=body.run(context)
    assert result.get_num_triangles(0)==999 and result.get_num_lods()==4


def test_constructor_rejects_incomplete_source_family(declaration):
    geometry=deepcopy(declaration[0]);geometry['templates'].pop()
    with pytest.raises(ValueError,match='48'):units.attach_followers(geometry,{},checkout=ROOT)


def test_solid_prop_retains_original_default_trace_and_complete_authored_hull(tmp_path,monkeypatch,declaration):
    _,_,_,raw,context=prop_case(tmp_path,monkeypatch,declaration,solid=True)
    result=body.run(context)
    assert result.body.values['collision_trace_flag']=='CTF_USE_DEFAULT' and result.hulls==raw.hulls and len(result.hulls)==1
