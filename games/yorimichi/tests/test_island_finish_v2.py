"""Island finish orchestration and native refusal contracts; no Unreal launch."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('island_finish_v2', ROOT / 'games/yorimichi/world/island_finish_v2.py')
finish = importlib.util.module_from_spec(spec); spec.loader.exec_module(finish)
RAW = '/Game/_Raw/Island/Terrain_piece'
DEST = '/Game/Experiments/IslandTerrain/v1_atomic/Terrain_piece'


class Props:
    def __init__(self, **values): self.values = values
    def get_editor_property(self, name): return self.values[name]
    def set_editor_property(self, name, value): self.values[name] = value


class Asset:
    def __init__(self, path): self.path = path
    def get_path_name(self): return self.path + '.' + self.path.rpartition('/')[2]


class Material(Asset):
    pass


class Mesh(Asset):
    def __init__(self, path):
        super().__init__(path)
        self.triangles, self.lods, self.uvs, self.simple, self.convex = 4, 1, 1, 2, 1
        self.static_materials = [Props(imported_material_slot_name=x) for x in ('Ground','Coast')]
        self.materials = [None, None]
        self.settings = Props(use_full_precision_u_vs=True)
        self.body = Props(collision_trace_flag='default')
        self.minimum, self.maximum = [100.,-500.,300.], [400.,-200.,600.]
    def get_num_triangles(self, lod): assert lod == 0; return self.triangles
    def get_num_lods(self): return self.lods
    def get_material(self, index): return self.materials[index]
    def set_material(self, index, value): self.materials[index] = value
    def get_editor_property(self, name): assert name == 'body_setup'; return self.body
    def get_bounding_box(self): return NS(min=NS(**dict(zip('xyz',self.minimum))),max=NS(**dict(zip('xyz',self.maximum))))


@pytest.fixture
def case(tmp_path, monkeypatch):
    source = tmp_path / 'inputs/source_export'; source.mkdir(parents=True)
    primary = source / 'Terrain_piece.fbx'; primary.write_bytes(b'FBX bytes already validated by the source producer')
    receipt = {'schema':1,'asset':'Terrain_piece','primary':primary.name,'triangles':4,
               'bounds':[[1.,2.,3.],[4.,5.,6.]],'sha256':hashlib.sha256(primary.read_bytes()).hexdigest(),
               'metadata':{'slots':['Ground','Coast'],'geometry_sha256':'a'*64,
                           'collision_hulls':0,'polygons':2,'uv_channels':['UVMap']}}
    (source / 'export.json').write_text(json.dumps(receipt))
    raw = Mesh(RAW); assets = {RAW:raw,'/Game/Japan/Materials/MI_Ground':Material('/Game/Japan/Materials/MI_Ground'),
                              '/Game/Japan/Materials/MI_Coast':Material('/Game/Japan/Materials/MI_Coast')}
    events = []
    state = NS(raw=raw, assets=assets, events=events, collision_ok=True, remove_ok=True, save_ok=True, source=source, receipt=receipt)
    def duplicate(source, destination):
        events.append(('duplicate',source,destination)); result=deepcopy(assets[source]);result.path=destination;assets[destination]=result;return result
    def save(mesh, only_dirty):
        events.append(('save',mesh.path)); assert only_dirty is True
        if getattr(state,'change_after_save',False): mesh.static_materials[0].values['imported_material_slot_name']='ForeignAfterSave'
        return state.save_ok
    def collision(mesh, triangles, authored):
        events.append(('validate',mesh.path));assert mesh is not raw and triangles==mesh.triangles and authored is False
        assert mesh.simple == mesh.convex == 0 and mesh.body.values['collision_trace_flag']=='complex'
        return state.collision_ok
    def remove(mesh):
        events.append(('remove',mesh.path))
        if state.remove_ok: mesh.simple=mesh.convex=0
        return state.remove_ok
    editor = NS(get_lod_build_settings=lambda mesh,lod:mesh.settings,
                set_lod_build_settings=lambda mesh,lod,value:setattr(mesh,'settings',value),
                get_simple_collision_count=lambda mesh:mesh.simple,get_convex_collision_count=lambda mesh:mesh.convex,
                remove_collisions=remove,get_num_uv_channels=lambda mesh,lod:mesh.uvs)
    library = NS(load_asset=lambda path:assets.get(path),does_asset_exist=lambda path:path in assets,
                 duplicate_asset=duplicate,save_loaded_asset=save)
    unreal = NS(StaticMesh=Mesh,MaterialInterface=Material,EditorAssetLibrary=library,StaticMeshEditorSubsystem=object(),
                get_editor_subsystem=lambda _:editor,load_module=lambda name:events.append(('module',name)),
                CollisionTraceFlag=NS(CTF_USE_COMPLEX_AS_SIMPLE='complex'),AtelierBuildWorkerLibrary=NS(validate_mesh_collision=collision))
    monkeypatch.setitem(sys.modules,'unreal',unreal)
    context = NS(job_dir=str(tmp_path),inputs={'raw':'raw-item','source_export':str(source),'ground':'ground-item','coast':'coast-item'},
                 packages={'raw':[RAW],'ground':['/Game/Japan/Materials/MI_Ground'],'coast':['/Game/Japan/Materials/MI_Coast']},outputs=[DEST],
                 params={'op':'finish','kind':'static_mesh','source':'raw','destination':DEST,
                         'args':{'source_export':'source_export','materials':{'Ground':'ground','Coast':'coast'}}})
    return state, context, unreal


def test_finish_duplicates_then_binds_and_validates_exact_native_destination(case):
    state, context, _ = case; before = deepcopy(state.raw.__dict__)
    mesh = finish.run(context)
    assert state.raw.__dict__['materials'] == before['materials'] == [None,None]
    assert state.raw.settings.values['use_full_precision_u_vs'] is True and state.raw.simple == 2 and state.raw.convex == 1
    assert mesh.path==DEST and mesh.settings.values['use_full_precision_u_vs'] is False
    assert [material.path for material in mesh.materials] == ['/Game/Japan/Materials/MI_Ground','/Game/Japan/Materials/MI_Coast']
    assert [event[0] for event in state.events] == ['module','duplicate','remove','validate','save','validate']
    assert (state.source / 'export.json').read_text() == json.dumps(state.receipt)


@pytest.mark.parametrize('failure', ['triangles','lod','bounds','uv','remove','cook','save','post_save_slots','slot','missing_material','wrong_material_type','missing_validator','overlap','ambiguous','receipt_sha','extra_source'])
def test_invalid_source_or_current_native_state_cannot_finish(case, failure):
    state, context, unreal = case
    if failure=='triangles': state.raw.triangles=5
    elif failure=='lod': state.raw.lods=2
    elif failure=='bounds': state.raw.minimum[0]+=1
    elif failure=='uv': state.raw.uvs=2
    elif failure=='remove': state.remove_ok=False
    elif failure=='cook': state.collision_ok=False
    elif failure=='save': state.save_ok=False
    elif failure=='post_save_slots': state.change_after_save=True
    elif failure=='slot': state.raw.static_materials[0].values['imported_material_slot_name']='Foreign'
    elif failure=='missing_material': del context.params['args']['materials']['Ground']
    elif failure=='wrong_material_type': context.params['args']['materials']['Ground']='raw'
    elif failure=='missing_validator': del unreal.AtelierBuildWorkerLibrary
    elif failure=='overlap': context.params['destination']=RAW;context.outputs=[RAW]
    elif failure=='ambiguous': context.packages['raw'].append('/Game/_Raw/Other')
    elif failure=='receipt_sha': (state.source / state.receipt['primary']).write_bytes(b'corrupt')
    elif failure=='extra_source': (state.source / 'extra').mkdir()
    with pytest.raises(ValueError): finish.run(context)
    if failure not in ('save','post_save_slots'):
        assert not any(event[0]=='save' for event in state.events)
    assert state.raw.settings.values['use_full_precision_u_vs'] is True


def test_explicit_package_selection_and_parent_material_superset_are_supported(case):
    state, context, _ = case
    context.packages['raw']=[RAW,'/Game/_Raw/Other'];context.params['package_sources']={'raw':RAW}
    context.params['args']['materials']['UnusedParentSlot']='ground'
    assert finish.run(context).path==DEST


def glb_export(case, *, second_uv=False):
    import struct
    from atelier import encoded_glb
    from atelier.gltf import glb_pack
    state, context, _ = case
    positions = [[1.,3.,-2.],[4.,3.,-2.],[1.,6.,-2.]]
    binary = struct.pack('<9f6f3H',*(x for row in positions for x in row),0.,0.,1.,0.,0.,1.,0,1,2)
    attributes = {'POSITION':0,'TEXCOORD_0':1}
    if second_uv: attributes['TEXCOORD_1']=1
    doc = {'asset':{'version':'2.0'},'buffers':[{'byteLength':len(binary)}],
           'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':36},
                          {'buffer':0,'byteOffset':36,'byteLength':24},
                          {'buffer':0,'byteOffset':60,'byteLength':6}],
           'accessors':[{'bufferView':0,'componentType':5126,'type':'VEC3','count':3},
                        {'bufferView':1,'componentType':5126,'type':'VEC2','count':3},
                        {'bufferView':2,'componentType':5123,'type':'SCALAR','count':3}],
           'materials':[{'name':'Ground'},{'name':'Coast'}],
           'meshes':[{'primitives':[{'attributes':attributes,'indices':2,'material':0}]}],
           'nodes':[{'mesh':0}],'scenes':[{'nodes':[0]}],'scene':0}
    data = glb_pack(doc,binary)
    packet = encoded_glb.encode(data,key='Terrain_piece')
    root = Path(context.job_dir) / 'inputs/glb-export'
    source = Path(context.job_dir) / 'Terrain_piece.mesh'; source.write_bytes(packet)
    receipt = encoded_glb.export(source,root)
    receipt['metadata']['payload_sha256']=hashlib.sha256(packet).hexdigest()
    (root / 'export.json').write_text(json.dumps(receipt))
    context.inputs['source_export']=str(root)
    state.raw.triangles=1;state.raw.minimum=[100.,-200.,300.];state.raw.maximum=[400.,-200.,600.]
    state.raw.static_materials=[Props(imported_material_slot_name='Ground')];state.raw.materials=[None]
    return receipt


def test_current_encoded_glb_receipt_derives_used_slots_uv_and_original_native_bounds(case):
    glb_export(case)
    state, context, _ = case
    mesh = finish.run(context)
    assert mesh.triangles == 1 and len(mesh.static_materials) == 1
    assert mesh.materials[0].path == '/Game/Japan/Materials/MI_Ground'
    assert mesh.minimum == [100.,-200.,300.] and mesh.maximum == [400.,-200.,600.]
    assert len([event for event in state.events if event[0]=='save']) == 1


def test_second_actual_glb_uv_channel_refuses_before_native_mutation(case):
    glb_export(case,second_uv=True)
    state, context, _ = case
    with pytest.raises(ValueError,match='exactly one source UV'): finish.run(context)
    assert not state.events and DEST not in state.assets
