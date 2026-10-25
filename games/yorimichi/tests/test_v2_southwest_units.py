"""Actual Southwest D2 ownership, selected source proofs and original native finishing without Unreal."""
from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import numpy as np
import pytest
from atelier import mesh_ir, mesh_collision
from atelier.build_v2.blender_validate import decode_mesh_payload
from atelier.build_v2.recipe_dependencies import extract
from atelier.export_manifest import publish_receipt

ROOT=Path(__file__).resolve().parents[3]; GAME=ROOT/'games/yorimichi'
sys.path[:0]=[str(GAME),str(GAME/'world')]


def load(relative,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/relative)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


units=load('games/yorimichi/v2_southwest_units.py','southwest_units_test')
body=load(units.FINISH,'southwest_finish_test')


@pytest.fixture(scope='module')
def geometry():
    factory=load('games/yorimichi/southwest_atomic_build.py','southwest_factory_test')
    rows=extract(factory.steps(NS(out=ROOT/'build/yorimichi')),checkout=ROOT,build_root=ROOT/'build')
    return load('games/yorimichi/v2_geometry_templates.py','southwest_templates_test').geometry_templates(rows,checkout=ROOT)


def natives():
    return {units.MATERIAL:{'unit':'actual.village.material','item':'asset','package':units.MATERIAL,
        'dependencies':[{'unit':'actual.village.texture','item':'texture','package':'/Game/Japan/Textures/T_Village'}]}}


def test_actual_sixteen_parent_templates_bind_only_existing_material_and_own_piece_items(geometry):
    before=deepcopy(geometry);result=units.attach_followers(geometry,natives(),checkout=ROOT)
    assert geometry==before and len(result['templates'])==len(result['module_requirements'])==16
    assert {t['unit_prefix'].rsplit('.',1)[-1] for t in result['templates']} >= {'Tree_PineLean_A','Tree_PineLean_B'}
    assert 'units' not in result and 'packages' not in result
    for template in result['templates']:
        raw,finish=[f['unit'] for f in template['followers']]
        assert raw['params']['destination']=='/Game/_Raw/Southwest/$piece'
        assert raw['outputs'][0]['class']=='RawStaticMesh' and raw['outputs'][0]['destination']=='store'
        assert finish['params']['destination']=='/Game/Japan/Southwest/Pieces/$piece'
        assert finish['outputs'][0]['class']=='StaticMesh' and finish['outputs'][0]['destination']=='checkout'
        assert len(finish['outputs'][0]['files'])==6 and finish['outputs'][0]['files'][0]['required']
        assert finish['inputs'][2]['source']=={'kind':'group_member','unit':template['producer'],'group':'geometry','piece':'$piece'}
        assert finish['params']['args']['native_inputs']=={'native0':units.MATERIAL,'native1':'/Game/Japan/Textures/T_Village'}
        assert len(finish['inputs'])==5
        assert units.EMPTY_COLLISION in finish['code'] and 'platform/studio/atelier/native_packages.py' in finish['code']
        assert all((ROOT/p).is_file() for p in finish['code'])
        assert not any(i['source'].get('unit')=='world.southwest' for i in finish['inputs'])
        assert result['module_requirements'][template['unit_prefix']][0]['name']=='Yorimichi'


@pytest.mark.parametrize('damage',['missing_material','wrong_material','partial','format','parent'])
def test_missing_native_role_or_changed_original_source_family_refuses(geometry,damage):
    graph=deepcopy(geometry);refs=natives()
    if damage=='missing_material':refs={}
    elif damage=='wrong_material':refs[units.MATERIAL]['package']='/Game/Other'
    elif damage=='partial':graph['templates'].pop()
    elif damage=='format':graph['templates'][0]['params']['format']='glb'
    else:graph['templates'][0]['producer']='foreign'
    with pytest.raises(ValueError):units.attach_followers(graph,refs,checkout=ROOT)


def test_other_family_requirements_survive_extension(geometry):
    graph=deepcopy(geometry);graph['module_requirements']={'other.export.Parent':[{'name':'Other'}]}
    assert units.attach_followers(graph,natives(),checkout=ROOT)['module_requirements']['other.export.Parent']==[{'name':'Other'}]


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
    def set_num_source_models(self,count):self.lods=count
    def get_material(self,i):return self.material
    def set_material(self,i,value):self.material=value
    def get_editor_property(self,key):return self.body
    def get_bounding_box(self):return NS(min=NS(**dict(zip('xyz',self.low))),max=NS(**dict(zip('xyz',self.high))))


def case(tmp_path,monkeypatch,*,tree=False,matrix=None,authored_hull=False):
    key='Tree_PineLean_A' if tree else 'SW_CoconutStand'
    source=tmp_path/'source';payload=tmp_path/'payload';source.mkdir();payload.mkdir()
    piece=dict(positions=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],faces=[[0,1,2]],normals=[[0.,0.,1.]]*3,
               materials=[0],smooth=[False],uvs=[('UVMap',[[0.,0.],[1.,0.],[0.,1.]])],colours=[])
    hulls=[]
    if authored_hull:
        tetra=dict(positions=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]],faces=[[0,1,2],[0,3,1],[1,3,2],[0,2,3]],
            normals=[[0.,0.,1.]]*12,materials=[0]*4,smooth=[False]*4,uvs=[],colours=[])
        hulls=[mesh_collision.encode(tetra,slots=['Hull'],matrix=np.eye(4).tolist())]
    packet=mesh_ir.encode(piece,key=key,slots=['Southwest_Palette'],matrix=matrix if matrix is not None else np.eye(4).tolist(),options={},collisions=hulls)
    (payload/(key+'.npz')).write_bytes(packet);_,_,facts=decode_mesh_payload(packet,expected_asset=key)
    (source/(key+'.fbx')).write_bytes(b'producer-verified FBX')
    receipt=publish_receipt(source,key=key,primary=key+'.fbx',triangles=1,bounds=[facts['min'],facts['max']],
        metadata={'geometry_sha256':hashlib.sha256(packet).hexdigest(),'slots':['Southwest_Palette'],'polygons':1,
                  'collision_hulls':len(hulls),'uv_channels':['UVMap']})
    cleanup=tmp_path/units.EMPTY_COLLISION;cleanup.parent.mkdir(parents=True)
    cleanup.write_text((ROOT/units.EMPTY_COLLISION).read_text()+'\nraise RuntimeError("old module top level executed")\n')
    raw_path='/Game/_Raw/Southwest/'+key;destination='/Game/Japan/Southwest/Pieces/'+key
    raw=Mesh(raw_path);raw.triangles=1;raw.lods=2;raw.uvs=1;raw.simple=raw.convex=1
    raw.static_materials=[Props(imported_material_slot_name='Southwest_Palette')];raw.material=None
    raw.settings=Props(use_full_precision_u_vs=True);raw.body=Props(collision_trace_flag='old')
    raw.low,raw.high=[0.,-100.,0.],[100.,0.,0.]
    assets={raw_path:raw,units.MATERIAL:Material(units.MATERIAL)};events=[]
    content=tmp_path/'Content';content.mkdir()
    state=NS(raw=raw,source=source,payload=payload,receipt=receipt,assets=assets,events=events,cook=True,save=True,
             primary=True,post_save=False,remove=True,clear=True,cleanup=cleanup)
    def duplicate(path,target):
        result=deepcopy(assets[path]);result.path=target;assets[target]=result;events.append('duplicate');return result
    def save(mesh,only_if_is_dirty=False):
        assert only_if_is_dirty is False;events.append('save')
        if state.primary:
            path=content/(mesh.path.removeprefix('/Game/')+'.uasset');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'primary')
        if state.post_save:mesh.uvs=2
        return state.save
    def remove(mesh):
        events.append('remove')
        if state.clear:mesh.simple=mesh.convex=0
        return state.remove
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
        packages={'raw':[raw_path],'source_export':[],'payload':[],'native0':[units.MATERIAL]},outputs=[destination],params={'op':'finish','kind':'static_mesh',
        'source':'raw','destination':destination,'package_sources':{'raw':raw_path},'args':{'parent':key,'source_export':'source_export','payload':'payload',
        'material':'native0','native_inputs':{'native0':units.MATERIAL}}})
    return state,context,unreal


@pytest.mark.parametrize('tree',[False,True])
def test_original_empty_cleanup_material_half_uv_cooked_lod_and_checked_save(tmp_path,monkeypatch,tree):
    state,context,_=case(tmp_path,monkeypatch,tree=tree)
    cleanup=body.empty_collision(context)
    assert cleanup.__code__.co_filename==str(state.cleanup)
    mesh=body.run(context)
    assert state.raw.lods==2 and state.raw.settings.values['use_full_precision_u_vs'] is True and state.raw.material is None
    assert state.raw.simple==state.raw.convex==1
    assert mesh.lods==1 and mesh.settings.values['use_full_precision_u_vs'] is False
    assert mesh.material.path==units.MATERIAL and mesh.body.values['collision_trace_flag']=='complex'
    assert mesh.simple==mesh.convex==0 and state.events==['duplicate','remove','validate','save','validate']


@pytest.mark.parametrize('damage',['source','payload','parent','triangles','uv','bounds','nonfinite_bounds','slot','material',
                                  'cook','save','primary','post_save','validator','remove','clear','cleanup'])
def test_invalid_source_cleanup_or_native_state_cannot_complete(tmp_path,monkeypatch,damage):
    state,context,unreal=case(tmp_path,monkeypatch)
    if damage=='source':(state.source/(state.receipt['asset']+'.fbx')).write_bytes(b'changed')
    elif damage=='payload':(state.payload/'extra.npz').write_bytes(b'foreign')
    elif damage=='parent':context.params['args']['parent']='SW_Boat'
    elif damage=='triangles':state.raw.triangles=2
    elif damage=='uv':state.raw.uvs=2
    elif damage=='bounds':state.raw.low=[1.,-100.,0.]
    elif damage=='nonfinite_bounds':state.raw.low=[float('nan'),-100.,0.]
    elif damage=='slot':state.raw.static_materials[0].values['imported_material_slot_name']='Other'
    elif damage=='material':context.params['args']['native_inputs']['native0']='/Game/Other'
    elif damage=='cook':state.cook=False
    elif damage=='save':state.save=False
    elif damage=='primary':state.primary=False
    elif damage=='post_save':state.post_save=True
    elif damage=='validator':unreal.CitySurfaceValidation=None
    elif damage=='remove':state.remove=False
    elif damage=='clear':state.clear=False
    else:state.cleanup.unlink()
    with pytest.raises((ValueError,AssertionError,RuntimeError)):body.run(context)


@pytest.mark.parametrize('damage',['frame','authored_hull'])
def test_source_diagnostics_never_become_native_hulls_or_a_changed_frame(tmp_path,monkeypatch,damage):
    matrix=np.eye(4);matrix[0,3]=1.
    state,context,_=case(tmp_path,monkeypatch,matrix=matrix.tolist() if damage=='frame' else None,authored_hull=damage=='authored_hull')
    with pytest.raises(ValueError):body.run(context)
    assert state.events==[]


def test_source_export_root_codec_preserves_actual_selected_source_before_finish(tmp_path,monkeypatch):
    from atelier.build_v2 import recipe_job,unreal_inputs
    state,context,_=case(tmp_path,monkeypatch)
    archive=tmp_path/'inputs/source.tree.tar';archive.parent.mkdir();recipe_job.pack_root(state.source,archive)
    before=archive.read_bytes();runtime=tmp_path/'runtime';runtime.mkdir()
    prepared=unreal_inputs.stage_inputs(tmp_path,[{'name':'source_export','path':'inputs/source.tree.tar','identity':{'state':'digest'}}],
        Path(context.content_dir),runtime_dir=runtime)
    context.inputs['source_export']=prepared['inputs']['source_export'];context.packages['source_export']=prepared['packages']['source_export']
    assert body.run(context).path==context.outputs[0] and archive.read_bytes()==before
