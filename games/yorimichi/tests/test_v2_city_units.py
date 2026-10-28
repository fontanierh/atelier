"""Actual desktop city declarations, narrow parent projection and current native policy."""
import hashlib
import importlib.util
import json
from pathlib import Path
from copy import deepcopy
import sys
import tarfile
import subprocess
import shutil
from types import SimpleNamespace as NS

import numpy as np
import pytest
from atelier import mesh_ir,mesh_collision
from atelier.build_v2 import recipe_job
from atelier.build_v2.recipe_dependencies import extract
from atelier.export_manifest import publish_receipt

ROOT=Path(__file__).resolve().parents[3];GAME=ROOT/'games/yorimichi'
sys.path[:0]=[str(GAME),str(GAME/'world'),str(GAME/'unreal/Scripts')]


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


units=load('games/yorimichi/v2_city_units.py','city_units_test')
body=load(units.SCRIPT,'city_finish_test');projection=load(units.PARENT,'city_parent_test')


@pytest.fixture(scope='module')
def declaration():
    recipe=load('games/yorimichi/build.py','city_recipe_test')
    rows=extract(recipe.steps(NS(out=ROOT/'build/yorimichi',game='yorimichi',uproject=GAME/'unreal/Yorimichi.uproject')),checkout=ROOT,build_root=ROOT/'build')
    geometry=load('games/yorimichi/v2_geometry_templates.py','city_templates_test').geometry_templates(rows,checkout=ROOT)
    geometry['templates']=[t for t in geometry['templates'] if t['unit_prefix'].startswith('world.hidamari.export.')]
    textured,slugs=units._surface_policy(ROOT);paths=set()
    for parent in body.SOURCES:
        slots=['HDS_'+s for s in slugs] if parent in textured or parent.startswith(('HD_Shop_','HD_ArcadeShop_','HD_House_')) else ['Palette']
        paths.update(body.piece_material_paths(parent,slots).values())
    natives={path:{'unit':'material.'+path.rsplit('/',1)[-1],'item':'asset','package':path,'dependencies':['/Game/SharedTexture']} for path in paths}
    natives['/Game/SharedTexture']={'unit':'texture','item':'asset','package':'/Game/SharedTexture'}
    return geometry,units.attach_followers(geometry,natives,checkout=ROOT),natives


def test_actual_86_parents_exact_source_root_and_current_destination(declaration):
    original,result,_=declaration
    assert len(result['templates'])==len(body.SOURCES)==86 and all('followers' not in t for t in original['templates'])
    assert len(result['units'])==86 and 'aliases' not in result and 'packages' not in result
    for unit in result['units']:
        assert unit['op']=={'kind':'py_data','version':'1'} and unit['params']=={} and unit['script']==units.PARENT
        assert unit['inputs'][0]['source']['item']=='product0' and unit['outputs'][0]['files']==[{'path':'plan.json','required':True}]
    for template in result['templates']:
        raw,finish=[f['unit'] for f in template['followers']];parent=finish['params']['args']['parent']
        assert raw['params']['destination']=='/Game/_Raw/City/$piece' and finish['params']['destination']==body.DESTINATION+'/$piece'
        assert finish['inputs'][2]['source']=={'kind':'group_member','unit':template['producer'],'group':'geometry','piece':'$piece'}
        assert finish['inputs'][3]['source']=={'kind':'item','unit':'unreal.city.parent.'+parent,'item':'parent'}
        assert all(i.get('whole') for i in finish['inputs'])
        assert result['module_requirements'][template['unit_prefix']][0]['name']=='Yorimichi'
        assert units.ROSTER in finish['code']
        assert not any(path.endswith('import_city_atomic.py') for path in finish['code'])
    clock=next(t for t in result['templates'] if t['unit_prefix'].endswith('.HD_ClockHall'))['followers'][1]['unit']
    assert '/Game/Japan/Materials/MI_Road' in clock['params']['args']['native_inputs'].values()
    assert '/Game/SharedTexture' in clock['params']['args']['native_inputs'].values()


class DataContext:
    params={}
    outputs={'plan.json':None}
    def __init__(self,source,output):self.inputs={'source':source};self.output_dir=output
    def input(self,name):return self.inputs[name]
    def output(self,name):assert name=='plan.json';return self.output_dir/name


def packet(name='HD_Boat',slots=None,hulls=None,offset=0.):
    piece=dict(positions=[[offset,0.,0.],[offset+1,0.,0.],[offset,1.,0.]],faces=[[0,1,2]],normals=[[0.,0.,1.]]*3,materials=[0],smooth=[False],uvs=[('UVMap',[[0.,0.],[1.,0.],[0.,1.]])],colours=[])
    return mesh_ir.encode(piece,key=name,slots=slots or ['Palette'],matrix=np.eye(4).tolist(),options={},collisions=hulls or [])


def source_plan(tmp_path,offset=0.):
    root=tmp_path/'original';root.mkdir(exist_ok=True);name='HD_Boat';raw=packet(name,offset=offset);(root/(name+'.npz')).write_bytes(raw)
    row=dict(name=name,payload=name+'.npz',sha256=hashlib.sha256(raw).hexdigest(),triangles=1,polygons=1,source_faces=[0],slots=['Palette'],source_material_indices=[0],min=[offset,0.,0.],max=[offset+1,1.,0.],collision_hulls=0)
    value=dict(schema=1,complete=True,parent=name,triangle_limit=32768,partition='whole',collision_owner=None,source_triangles=1,source_polygons=1,source_collision_hulls=0,slots=['Palette'],matrix=np.eye(4).tolist(),pieces=[row])
    (root/'plan.json').write_text(json.dumps(value));return root


def project_case(tmp_path,offset=0.):
    source=source_plan(tmp_path,offset);item=tmp_path/('item'+str(offset));(item/'products').mkdir(parents=True)
    recipe_job.pack_root(source,item/'products/0-0.tree.tar');output=tmp_path/('result'+str(offset));output.mkdir();return DataContext(item,output)


def test_projection_validates_actual_root_codec_and_stops_unconsumed_geometry_changes(tmp_path):
    a=project_case(tmp_path);projection.run(a);b=project_case(tmp_path,2.);projection.run(b)
    assert (a.output_dir/'plan.json').read_bytes()==(b.output_dir/'plan.json').read_bytes()
    assert json.loads((a.output_dir/'plan.json').read_text())=={'parent':'HD_Boat','source_collision_hulls':0,'source_material_slots':['Palette']}
    assert {p.name for p in a.output_dir.iterdir()}=={'plan.json'}


@pytest.mark.parametrize('damage',['payload','membership','bounds','archive'])
def test_invalid_complete_original_plan_cannot_publish_parent_facts(tmp_path,damage):
    source=source_plan(tmp_path)
    if damage=='payload':(source/'HD_Boat.npz').write_bytes(b'bad')
    else:
        path=source/'plan.json';value=json.loads(path.read_text())
        if damage=='membership':value['pieces'][0]['source_faces']=[1]
        elif damage=='bounds':value['pieces'][0]['max']=[2,2,2]
        path.write_text(json.dumps(value))
    item=tmp_path/'item';(item/'products').mkdir(parents=True);archive=item/'products/0-0.tree.tar';recipe_job.pack_root(source,archive)
    if damage=='archive':archive.write_bytes(b'bad')
    output=tmp_path/'output';output.mkdir()
    with pytest.raises((ValueError,RuntimeError,tarfile.ReadError)):
        projection.run(DataContext(item,output))
    assert not list(output.iterdir())


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
    def get_material(self,index):return self.materials[index]
    def set_material(self,index,value):self.materials[index]=value
    def get_editor_property(self,name):return self.body if name=='body_setup' else super().get_editor_property(name)
    def set_num_source_models(self,count):self.triangles=self.triangles[:count]
    def get_bounding_box(self):return NS(min=NS(**dict(zip('xyz',self.low))),max=NS(**dict(zip('xyz',self.high))))


def native_case(tmp_path,monkeypatch,declaration,parent='HD_Boat',whole_hulls=0,own_hulls=False):
    template=next(t for t in declaration[1]['templates'] if t['unit_prefix'].endswith('.'+parent));unit=template['followers'][1]['unit'];params=deepcopy(unit['params'])
    slots=['HDS_timber'] if parent in ('HD_ClockHall','HD_Shop_00','HD_House_00') else ['Palette'];key=parent
    hulls=[]
    if own_hulls:
        tetra=dict(positions=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]],faces=[[0,1,2],[0,3,1],[1,3,2],[0,2,3]],normals=[[0.,0.,1.]]*12,materials=[0]*4,smooth=[False]*4,uvs=[],colours=[])
        hulls=[mesh_collision.encode(tetra,slots=['Hull'],matrix=np.eye(4).tolist())]
    raw_bytes=packet(key,slots,hulls);source=tmp_path/'export';payload=tmp_path/'payload';source.mkdir();payload.mkdir();(source/(key+'.fbx')).write_bytes(b'certified own FBX');(payload/(key+'.npz')).write_bytes(raw_bytes)
    publish_receipt(source,key=key,primary=key+'.fbx',triangles=1,bounds=[[0.,0.,0.],[1.,1.,0.]],metadata={'geometry_sha256':hashlib.sha256(raw_bytes).hexdigest(),'slots':slots,'polygons':1,'collision_hulls':len(hulls),'uv_channels':['UVMap']})
    metadata=tmp_path/'parent';metadata.mkdir();parent_slots=slots+(['HDS_plaster'] if slots[0].startswith('HDS_') else [])
    (metadata/'plan.json').write_text(json.dumps({'parent':parent,'source_material_slots':parent_slots,'source_collision_hulls':whole_hulls}))
    inputs={'source_export':source,'payload':payload,'parent':metadata,'raw':'raw'};raw_path='/Game/_Raw/City/'+key;packages={'source_export':[],'payload':[],'parent':[],'raw':[raw_path]};assets={};events=[]
    for slot,path in params['args']['native_inputs'].items():inputs[slot]='native';packages[slot]=[path];assets[path]=Material(path)
    raw=Mesh(raw_path);raw.triangles=[1];raw.vertices=[3];raw.body=Props(collision_trace_flag='raw');raw.settings=Props(use_full_precision_u_vs=False,generate_lightmap_u_vs=False)
    raw.static_materials=[Props(imported_material_slot_name=s) for s in slots];raw.materials=[None]*len(slots);raw.low=[0.,-100.,0.];raw.high=[100.,0.,0.]
    raw.hulls=[[[p[0]*100,-p[1]*100,p[2]*100] for p in h['vertices']] for h in hulls];raw.simple=0;raw.values.update(allow_cpu_access=False,lod_for_collision=0);assets[raw_path]=raw
    content=tmp_path/'Content';content.mkdir();state=NS(save=True,primary=True,post=False,cook=True,cooked=[])
    def save(asset,only_if_is_dirty=False):
        assert only_if_is_dirty is False;events.append('save')
        if state.primary:
            path=content/(asset.path.removeprefix('/Game/')+'.uasset');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'primary')
        if state.post:asset.triangles[0]+=1
        return state.save
    def duplicate(path,target):mesh=deepcopy(assets[path]);mesh.path=target;assets[target]=mesh;events.append('duplicate');return mesh
    def set_lods(mesh,options):
        count=len(options.values['reduction_settings']);mesh.triangles=[1]*count;mesh.vertices=[3,2,1,1][:count];return count
    def clear(mesh):mesh.hulls=[];mesh.simple=0;events.append('cleanup');return True
    def cook(mesh,count,authored):state.cooked.append(authored);return state.cook
    editor=NS(get_lod_build_settings=lambda m,i:m.settings,set_lod_build_settings=lambda m,i,s:setattr(m,'settings',s),get_num_uv_channels=lambda m,i:1,
        get_simple_collision_count=lambda m:m.simple,get_convex_collision_count=lambda m:len(m.hulls),remove_collisions=clear,
        set_lods=set_lods,get_lod_count=lambda m:len(m.triangles),set_lod_screen_sizes=lambda m,s:setattr(m,'screens',s) or True,
        get_lod_screen_sizes=lambda m:m.screens,get_number_verts=lambda m,i:m.vertices[i])
    unreal=NS(EditorAssetLibrary=NS(load_asset=assets.get,does_asset_exist=lambda p:p in assets,save_loaded_asset=save,duplicate_asset=duplicate),
        StaticMesh=Mesh,MaterialInterface=Material,load_module=lambda name:None,StaticMeshEditorSubsystem=object(),get_editor_subsystem=lambda cls:editor,
        CollisionTraceFlag=NS(CTF_USE_COMPLEX_AS_SIMPLE='complex',CTF_USE_SIMPLE_AND_COMPLEX='simple-complex'),CitySurfaceValidation=NS(collision_vertices=lambda m:json.dumps(m.hulls),validate_collision=cook),
        StaticMeshReductionOptions=Props,StaticMeshReductionSettings=Props,log=lambda text:None)
    monkeypatch.setitem(sys.modules,'unreal',unreal)
    sys.modules.pop('city_distance_lods',None)
    path=tmp_path/body.EMPTY;path.parent.mkdir(parents=True);path.write_text("raise AssertionError('old helper importer executed')\n"+(ROOT/body.EMPTY).read_text())
    params['package_sources']['raw']=raw_path;params['destination']=body.DESTINATION+'/'+key
    return state,raw,events,NS(job_dir=tmp_path,content_dir=content,inputs=inputs,packages=packages,params=params,outputs=[params['destination']])


@pytest.mark.parametrize('parent,count',[('HD_Boat',1),('HD_ClockHall',1),('HD_Shop_00',4),('HD_House_00',3),('HD_ArcadeTree',1),('HD_NorthGate',1)])
def test_current_native_parent_policies_materials_lods_and_owned_save(tmp_path,monkeypatch,declaration,parent,count):
    state,raw,events,context=native_case(tmp_path,monkeypatch,declaration,parent)
    mesh=body.run(context)
    assert mesh.get_num_lods()==count and raw.materials==[None] and not raw.settings.values['use_full_precision_u_vs']
    assert mesh.settings.values['use_full_precision_u_vs'] and not mesh.settings.values['generate_lightmap_u_vs']
    assert state.cooked and not any(state.cooked) and events[-1]=='save'
    assert mesh.materials[0].path==body.piece_material_paths(parent,['HDS_timber'] if parent in ('HD_ClockHall','HD_Shop_00','HD_House_00') else ['Palette'])[mesh.static_materials[0].values['imported_material_slot_name']]
    if parent=='HD_ArcadeTree':assert mesh.values['allow_cpu_access'] is True


@pytest.mark.parametrize('own',[False,True])
def test_whole_parent_hull_policy_survives_zero_hull_sibling(tmp_path,monkeypatch,declaration,own):
    state,raw,_,context=native_case(tmp_path,monkeypatch,declaration,whole_hulls=1,own_hulls=own)
    mesh=body.run(context)
    assert mesh.body.values['collision_trace_flag']=='simple-complex' and all(state.cooked) and mesh.hulls==raw.hulls


@pytest.mark.parametrize('damage',['save','primary','post','bounds','lightmap','cook','hulls','material','source'])
def test_wrong_or_unsaved_current_city_piece_cannot_finish(tmp_path,monkeypatch,declaration,damage):
    state,raw,_,context=native_case(tmp_path,monkeypatch,declaration)
    if damage=='save':state.save=False
    elif damage=='primary':state.primary=False
    elif damage=='post':state.post=True
    elif damage=='bounds':raw.high[0]=float('nan')
    elif damage=='lightmap':raw.settings.values['generate_lightmap_u_vs']=True
    elif damage=='cook':state.cook=False
    elif damage=='hulls':context.params['args']['parent']='HD_NorthGate'
    elif damage=='material':context.params['args']['native_inputs']={}
    else:(Path(context.inputs['payload'])/'sibling.npz').write_bytes(b'foreign')
    with pytest.raises((ValueError,RuntimeError)):body.run(context)


def test_zero_hull_cleanup_is_only_on_owned_duplicate(tmp_path,monkeypatch,declaration):
    _,raw,events,context=native_case(tmp_path,monkeypatch,declaration);raw.simple=1
    mesh=body.run(context)
    assert raw.simple==1 and mesh.simple==0 and 'cleanup' in events



def test_actual_native_slot_order_uses_original_name_based_binding(tmp_path,monkeypatch,declaration):
    _,raw,_,context=native_case(tmp_path,monkeypatch,declaration,'HD_ClockHall')
    slots=['HDS_timber','HDS_plaster']
    piece=dict(positions=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],faces=[[0,1,2],[0,2,1]],normals=[[0.,0.,1.]]*6,materials=[0,1],smooth=[False]*2,uvs=[('UVMap',[[0.,0.],[1.,0.],[0.,1.]]*2)],colours=[])
    key='HD_ClockHall';packet=mesh_ir.encode(piece,key=key,slots=slots,matrix=np.eye(4).tolist(),options={},collisions=[])
    (Path(context.inputs['payload'])/(key+'.npz')).write_bytes(packet)
    publish_receipt(context.inputs['source_export'],key=key,primary=key+'.fbx',triangles=2,bounds=[[0.,0.,0.],[1.,1.,0.]],metadata={'geometry_sha256':hashlib.sha256(packet).hexdigest(),'slots':slots,'polygons':2,'collision_hulls':0,'uv_channels':['UVMap']})
    raw.triangles=[2];raw.static_materials=[Props(imported_material_slot_name=slot) for slot in reversed(slots)];raw.materials=[None,None]
    result=body.run(context)
    assert [m.path for m in result.materials]==['/Game/Japan/Hidamari/Materials/MI_HD_plaster','/Game/Japan/Hidamari/Materials/MI_HD_timber']


def test_changed_native_hull_vertices_refuse_without_clearing_positive_owner(tmp_path,monkeypatch,declaration):
    _,raw,events,context=native_case(tmp_path,monkeypatch,declaration,whole_hulls=1,own_hulls=True)
    raw.hulls[0][0][0]=5.
    with pytest.raises(ValueError):body.run(context)
    assert 'cleanup' not in events and 'save' not in events


def test_actual_declared_native_body_imports_from_staged_code_and_header(tmp_path,declaration):
    finish=declaration[1]['templates'][0]['followers'][1]['unit']
    for relative in finish['code']:
        target=tmp_path/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/relative,target)
    program="import pathlib,runpy,sys; root=pathlib.Path(sys.argv[1]); sys.path[:0]=[str(root/p) for p in ('games/yorimichi','games/yorimichi/world','games/yorimichi/unreal/Scripts','platform/studio')]; scope=runpy.run_path(str(root/sys.argv[2])); assert len(scope['SOURCES'])==86; import city_atomic_products; assert pathlib.Path(city_atomic_products.__file__).is_relative_to(root)"
    result=subprocess.run([sys.executable,'-I','-c',program,str(tmp_path),units.SCRIPT],text=True,capture_output=True)
    assert result.returncode==0,result.stderr
