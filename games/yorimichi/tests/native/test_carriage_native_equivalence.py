"""Source-only finite-boundary regressions; none certify a real Unreal result."""
import ast
import json
from pathlib import Path
import subprocess
import sys
import types

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import carriage_native_equivalence as proof  # noqa: E402

GAME = HERE.parents[1]
IMPORTER = GAME / 'unreal/Scripts/import_belmonte_train.py'
SERVICE = GAME / 'tools/belmonte_train_service.py'


def test_complete_importer_unchanged_except_dispatch_and_loop_wrapper():
    original = ast.parse(IMPORTER.read_bytes()); tree, loop = proof.owner_tree(IMPORTER)
    assert ast.dump(tree) == ast.dump(ast.Module(body=original.body[:-1], type_ignores=[]))
    main = next(n for n in original.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    assert any(ast.dump(loop.body[0]) == ast.dump(n) for n in main.body)
    assert proof.ast_sha(loop.body[0]) == proof.LOOP_SHA
    assert not any(isinstance(n, ast.Call) and ast.unparse(n.func) in ('BM.preflight_service', 'main') for n in ast.walk(loop))


def test_finite_service_projection_uses_actual_conversion_and_door_motion():
    service = proof.projection_module(SERVICE)
    p = dict(collision_boxes=[dict(name='fixed', group='fixed', box=[-1, 2, -3, 4, 5, 6]),
                             dict(name='moving', group='door', part='door', box=[0, 1, -2, -1, 1, 3])],
             doors=[dict(id='door', kind='staff', box=[0, 1, -2, -1, 1, 3], collision='moving',
                         leaves=[dict(name='Door_leaf', kind='hinged', pivot=[1, 2, 3], swing_deg=-95)], handles=[])])
    actual = service.project(p, p, 'SM_BT_Locomotive')
    assert actual['collision'] == [[-100, -400, 500, 200, 300, 600]]
    assert actual['switchable'] == [dict(name='moving', group='door', part='door', box=[0, 100, 100, 100, 200, 300])]
    leaf = actual['doors'][0]['leaves'][0]
    assert leaf == dict(node='Door_leaf', mesh='/Game/BelmonteTrain/Doors/SM_BTD_Locomotive_leaf.SM_BTD_Locomotive_leaf',
                        pivot=[100, -200, 300], motion='hinged', yaw=95.)
    assert 'furniture' not in actual and service.RENDER['screen_sizes'] == [1., .6, .15]


@pytest.mark.parametrize('change', ['collision', 'door', 'helper'])
def test_changed_actual_service_or_importer_refused(tmp_path, change):
    source = SERVICE.read_text() if change != 'helper' else IMPORTER.read_text()
    source = source.replace("b.get('group', 'fixed') == 'fixed'", "b.get('group', 'fixed') != 'fixed'", 1) if change == 'collision' else source
    source = source.replace("yaw=-float(leaf.get('swing_deg', 90))", "yaw=float(leaf.get('swing_deg', 90))", 1) if change == 'door' else source
    source = source.replace("'build_nanite', False", "'build_nanite', True", 1) if change == 'helper' else source
    path = tmp_path / 'changed.py'; path.write_text(source)
    with pytest.raises(ValueError): (proof.owner_tree if change == 'helper' else proof.projection_module)(path)


def test_exact_original_loop_forwards_lod_boxes_and_door_material_finishing():
    # Executes the real loop, with observable native API doubles, not a second importer.
    _, loop = proof.owner_tree(IMPORTER); calls = []
    class Material:
        def get_editor_property(self, key): return {'imported_material_slot_name': 'paint', 'material_interface': 'genuine-parent'}[key]
        def set_editor_property(self, key, value): calls.append(('material', key, value))
    class Mesh:
        def get_editor_property(self, key): return [Material()] if key == 'static_materials' else self
        def set_editor_property(self, key, value): calls.append(('property', key, value))
        def get_num_lods(self): return 3
        def get_num_triangles(self, index): return [10, 8, 2][index]
        def get_path_name(self): return '/owned/body'
        def get_bounding_box(self): return types.SimpleNamespace(min=types.SimpleNamespace(x=0,y=0,z=0), max=types.SimpleNamespace(x=1,y=1,z=1))
    owner = types.ModuleType('actual_loop_test'); owner.__file__ = str(IMPORTER); owner.TRAIN = Path('/fixture')
    owner.ROOT = '/owned'; owner.with_lods = lambda *args: calls.append(('lods', args[:3])) or Mesh()
    owner.import_mesh = lambda *args: calls.append(('door', args)) or Mesh(); owner.box = lambda value: value
    owner.sha = lambda path: 'actual-source-bound-by-host'
    owner.E = types.SimpleNamespace(save_loaded_asset=lambda *args,**kw: calls.append(('save',)),
        does_directory_exist=lambda path: True, delete_directory=lambda path: calls.append(('delete',path)))
    owner.unreal = types.SimpleNamespace(BelmonteTrainImportLibrary=types.SimpleNamespace(set_simple_boxes=lambda mesh,boxes: len(boxes)),
        CollisionTraceFlag=types.SimpleNamespace(CTF_USE_SIMPLE_AS_COMPLEX=7),log=lambda msg: None,log_warning=lambda msg: pytest.fail(msg))
    vehicle = dict(id='locomotive', name='SM_BT_Locomotive', levels=['a','b','c'], collision=[[0,0,0,1,1,1]],
                   switchable=[{}], doors=[dict(leaves=[dict(glb='door.glb',mesh='/Game/BelmonteTrain/Doors/SM_BTD_Locomotive_leaf.asset')])])
    result = proof.execute_vehicle_loop(owner, loop, [vehicle], [1,.6,.15], {},
        types.SimpleNamespace(get_lod_screen_sizes=lambda mesh: [1,.6,.15]))
    assert result['vehicles']['SM_BT_Locomotive']['door_leaves'] == 1
    assert ('property', 'lod_for_collision', 0) in calls
    assert ('property', 'collision_trace_flag', 7) in calls
    assert ('material', 'material_interface', 'genuine-parent') in calls
    assert ('delete', '/owned/Source/SM_BTD_Locomotive_leaf') in calls
    assert sum(c[0] == 'save' for c in calls) == 2
    assert not hasattr(owner, 'mesh') and not hasattr(owner, 'part')


def test_source_control_has_real_positive_negative_segments():
    controls = proof.controls_for_boxes([[1,2,3,4,6,8]])
    assert {c['kind'] for c in controls} == {'ray_positive','ray_negative','capsule_positive','capsule_negative'}
    assert all(c['input']['channel'] == 'Pawn' and c['input']['trace_complex'] for c in controls)
    with pytest.raises(ValueError): proof.controls_for_boxes([[1,2,3,1,6,8]])


def test_unreal_import_closure_is_stdlib_only(tmp_path):
    code = '''
import importlib.abc, pathlib, sys, types
native=pathlib.Path(sys.argv[1]); game=native.parents[1]
sys.path[:0]=[str(native),str(game/'unreal/Scripts')]
class BlockHost(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname=='atomic_equivalence' or fullname.split('.')[0] in ('numpy','mesh_ir') or fullname=='atelier.mesh_ir':
   raise ModuleNotFoundError(fullname)
sys.meta_path.insert(0,BlockHost())
u=types.ModuleType('unreal');u.EditorAssetLibrary=object()
u.AssetToolsHelpers=types.SimpleNamespace(get_asset_tools=lambda:object())
u.AssetRegistryHelpers=types.SimpleNamespace(get_asset_registry=lambda:object())
sys.modules['unreal']=u
import carriage_native_equivalence as p
import atomic_equivalence_capture
path=game/'unreal/Scripts/import_belmonte_train.py'
tree,loop=p.owner_tree(path);owner=types.ModuleType('unchanged');owner.__file__=str(path)
exec(compile(tree,str(path),'exec'),owner.__dict__)
assert callable(owner.with_lods) and callable(owner.main)
assert p.ast_sha(loop.body[0])==p.LOOP_SHA
assert callable(p.projection_module(game/'tools/belmonte_train_service.py').project)
assert 'numpy' not in sys.modules and 'atomic_equivalence' not in sys.modules
print('STDLIB CARRIAGE SLICE VERIFIED')
'''
    result = subprocess.run([sys.executable,'-I','-S','-c',code,str(HERE)], cwd=tmp_path, capture_output=True,text=True,timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'STDLIB CARRIAGE SLICE VERIFIED' in result.stdout


def test_exact_material_texture_comparator_does_not_waive_one_pixel(tmp_path, monkeypatch):
    a=tmp_path/'a.png';b=tmp_path/'b.png';a.write_bytes(b'actual pixels');b.write_bytes(b'actual pixelx')
    row=lambda path: dict(class_path='/Script/Engine.Texture2D', pixels=dict(path=str(path),sha256=proof.sha(path)))
    monkeypatch.setattr(proof,'inventory',lambda vehicles: {})
    with pytest.raises(ValueError, match='material/texture differs'):
        proof.compare({'original':{},'current':{}},[],{'original':{'texture':row(a)},'current':{'texture':row(b)}},
                      {'original':{},'current':{}})


def test_cleanup_and_native_capture_are_not_allowed_before_guard_evidence():
    path=HERE/'run_carriage_native_equivalence.py'; tree=ast.parse(path.read_bytes())
    run=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run')
    calls=[ast.unparse(n.func) for n in ast.walk(run) if isinstance(n,ast.Call)]
    assert 'guard_binding' in calls and 'strict_cleanup' in calls and 'current_native_build' in calls
    text=path.read_text();assert text.index('guard_binding(evidence)') < text.index('strict_cleanup(spec,')
    assert 'track_tree=True' in text and 'carriage_tree' not in text


def test_only_proven_mic_change_detection_and_lighting_ids_are_normalized(tmp_path):
    def row(name, guid, suffix=''):
        p=tmp_path/name
        p.write_text('Begin Object Class=/Script/Engine.MaterialInstanceConstant Name="actual"\n'
                     '   ParameterStateId='+guid+'\n'
                     '   LightingGuid='+guid+'\n'
                     '   Parent="/InterchangeAssets/gltf/actual"\n'
                     '   ScalarParameterValues(0)=(ParameterInfo=(Name="Roughness"),ParameterValue=0.25,ExpressionGUID='+('A'*32)+')\n'
                     '   BasePropertyOverrides=(bOverride_TwoSided=True,TwoSided=True)\n'+suffix+'End Object\n')
        return dict(path=str(p),sha256=proof.sha(p))
    a=row('a.t3d','1'*32); b=row('b.t3d','2'*32)
    cls='/Script/Engine.MaterialInstanceConstant'
    assert proof.material_text(a,cls)==proof.material_text(b,cls)
    c=row('c.t3d','2'*32,'   TextureParameterValues(0)=(ParameterValue="/actual/changed")\n')
    assert proof.material_text(a,cls)!=proof.material_text(c,cls)
    with pytest.raises(ValueError): proof.material_text(a,'/Script/Engine.Texture2D')
    p=Path(b['path']);p.write_text(p.read_text().replace('ParameterValue=0.25','ParameterValue=0.26'))
    b['sha256']=proof.sha(p)
    assert proof.material_text(a,cls)!=proof.material_text(b,cls)
    d=row('d.t3d','not-a-guid')
    with pytest.raises(ValueError): proof.material_text(d,cls)


def test_incomplete_positive_native_census_refuses():
    vehicles=[dict(id=k,name='SM_BT_'+''.join(s.title() for s in k.split('-')),levels=['a','b','c'],
                   collision=[],switchable=[],doors=[]) for k in proof.COACHES]
    with pytest.raises(ValueError, match='positive census'): proof.inventory(vehicles)
    with pytest.raises(ValueError, match='seven-coach'): proof.inventory(vehicles[:-1])


def texture_text_row(tmp_path, name, guid, *, source_id='A'*32, settings='TC_Default', extra=''):
    path=tmp_path/name
    path.write_text('Begin Object Class=/Script/Engine.Texture2D Name="actual"\n'
                    '   Source=(Id='+source_id+',SizeX=1,SizeY=1)\n'
                    '   CompressionSettings='+settings+'\n'
                    '   LightingGuid='+guid+'\n'+extra+'End Object\n')
    return dict(path=str(path),sha256=proof.sha(path))


def test_texture_lighting_identity_only_source_and_settings_remain_strict(tmp_path):
    a=texture_text_row(tmp_path,'a.t3d','1'*32);b=texture_text_row(tmp_path,'b.t3d','2'*32)
    cls='/Script/Engine.Texture2D'
    assert proof.material_text(a,cls)==proof.material_text(b,cls)
    assert proof.material_text(a,'/Script/Engine.Material')!=proof.material_text(b,'/Script/Engine.Material')
    source=texture_text_row(tmp_path,'source.t3d','2'*32,source_id='B'*32)
    settings=texture_text_row(tmp_path,'settings.t3d','2'*32,settings='TC_Normalmap')
    assert proof.material_text(a,cls)!=proof.material_text(source,cls)
    assert proof.material_text(a,cls)!=proof.material_text(settings,cls)
    assert Path(a['path']).read_bytes()!=Path(b['path']).read_bytes()  # Raw artifacts remain intact.


@pytest.mark.parametrize('case',['nested','duplicate','malformed','missing'])
def test_texture_identity_wrong_scope_duplicate_malformed_or_missing_refuses(tmp_path, case):
    row=texture_text_row(tmp_path,'bad.t3d','1'*32)
    path=Path(row['path']);text=path.read_text()
    line='   LightingGuid='+'1'*32+'\n'
    if case=='nested': text=text.replace(line,'   Begin Object Name="nested"\n'+line+'   End Object\n')
    if case=='duplicate': text=text.replace(line,line+line)
    if case=='malformed': text=text.replace(line,'   LightingGuid=not-a-guid\n')
    if case=='missing': text=text.replace(line,'')
    path.write_text(text);row['sha256']=proof.sha(path)
    with pytest.raises(ValueError): proof.material_text(row,'/Script/Engine.Texture2D')


def test_texture_lighting_normalization_does_not_waive_changed_png(tmp_path, monkeypatch):
    a=texture_text_row(tmp_path,'a.t3d','1'*32);b=texture_text_row(tmp_path,'b.t3d','2'*32)
    old=tmp_path/'old.png';new=tmp_path/'new.png';old.write_bytes(b'actual source pixels');new.write_bytes(b'actual source pixelx')
    def row(text,pixels):
        return dict(class_path='/Script/Engine.Texture2D',text=text,pixels=dict(path=str(pixels),sha256=proof.sha(pixels)))
    monkeypatch.setattr(proof,'inventory',lambda vehicles: {})
    with pytest.raises(ValueError,match='material/texture differs'):
        proof.compare({'original':{},'current':{}},[],
            {'original':{'texture':row(a,old)},'current':{'texture':row(b,new)}},{'original':{},'current':{}})


@pytest.mark.parametrize('field', ['ParameterStateId', 'LightingGuid'])
@pytest.mark.parametrize('fault', ['nested', 'duplicate', 'missing', 'malformed', 'wrong_class'])
def test_mic_cache_identity_scope_is_exact(tmp_path, field, fault):
    cls='/Script/Engine.MaterialInstanceConstant';path=tmp_path/'mic.t3d'
    text='Begin Object Class='+cls+' Name="actual"\n'
    text+='   ParameterStateId='+('1'*32)+'\n   LightingGuid='+('2'*32)+'\nEnd Object\n'
    line='   '+field+'='+('1' if field=='ParameterStateId' else '2')*32+'\n'
    if fault=='nested': text=text.replace(line,'   Begin Object Name="nested"\n'+line+'   End Object\n')
    if fault=='duplicate': text=text.replace(line,line+line)
    if fault=='missing': text=text.replace(line,'')
    if fault=='malformed': text=text.replace(line,'   '+field+'=not-a-guid\n')
    if fault=='wrong_class': text=text.replace('Class='+cls,'Class=/Script/Engine.Material')
    path.write_text(text);row=dict(path=str(path),sha256=proof.sha(path))
    with pytest.raises(ValueError): proof.material_text(row,cls)


@pytest.mark.parametrize('extra', [
    '   Source=(Id='+'A'*32+')\n',
    '   ScalarParameterValues(0)=(ParameterValue=0.25,ExpressionGUID='+'B'*32+')\n',
    '   OtherGuid='+'C'*32+'\n',
    '   Parent="/actual/first"\n',
    '   CompressionSettings=TC_Default\n',
    '   Begin Object Name="nested"\n      OtherGuid='+'D'*32+'\n   End Object\n',
])
def test_mic_other_guids_nested_fields_and_material_state_remain_strict(tmp_path, extra):
    cls='/Script/Engine.MaterialInstanceConstant'
    def row(name, param, lighting, suffix):
        path=tmp_path/name
        path.write_text('Begin Object Class='+cls+' Name="actual"\n   ParameterStateId='+param+'\n'
                        '   LightingGuid='+lighting+'\n'+suffix+'End Object\n')
        return dict(path=str(path),sha256=proof.sha(path))
    a=row('a.t3d','1'*32,'2'*32,extra)
    same=row('same.t3d','3'*32,'4'*32,extra)
    assert proof.material_text(a,cls)==proof.material_text(same,cls)
    changed=extra.replace('A'*32,'E'*32).replace('B'*32,'E'*32).replace('C'*32,'E'*32).replace('D'*32,'E'*32)
    changed=changed.replace('/actual/first','/actual/second').replace('TC_Default','TC_Normalmap')
    b=row('b.t3d','3'*32,'4'*32,changed)
    assert proof.material_text(a,cls)!=proof.material_text(b,cls)
    # Other reflected classes receive no generated-ID policy at all.
    assert proof.material_text(a,'/Script/Engine.Material')!=proof.material_text(same,'/Script/Engine.Material')


@pytest.mark.parametrize('sides', [('original','current'), ('original',), ('current',)])
@pytest.mark.parametrize('fault', ['missing_lod', 'unavailable', 'empty_source', 'mixed_availability'])
def test_matching_missing_authored_carriage_source_lod_never_passes(tmp_path, monkeypatch, sides, fault):
    # Isolate the authored-LOD predicate; the real roster/raw parser have their own tests.
    import copy
    name='SM_SavedSource';material='/Game/Fixture/Texture'
    pixels=tmp_path/'pixels';pixels.write_bytes(b'exact opaque artifact bytes')
    page=tmp_path/'page.json';page.write_text(json.dumps(dict(slots=[dict(material=material+'.Texture')])))
    row=dict(policy_scope='fixture',raw_pages=[dict(path=str(page),sha256=proof.sha(page))],
             **{field:[] for field in proof.FIELDS})
    row.update(render_lods={level:['render corner'] for level in range(3)},
               source_lods={level:['saved source corner'] for level in range(3)},
               source_presence={level:{True} for level in range(3)})
    records={phase:{name:copy.deepcopy(row)}for phase in ('original','current')}
    materials={phase:{material:dict(class_path='/Script/Engine.Texture2D',
                    pixels=dict(path=str(pixels),sha256=proof.sha(pixels)))}for phase in records}
    poses={phase:{}for phase in records}
    monkeypatch.setattr(proof,'inventory',lambda vehicles:{name:3})
    monkeypatch.setattr(proof,'whole_bounds',lambda record:'equal bound')
    monkeypatch.setattr(proof,'native_raw_set',lambda record,logical:record)
    assert proof.compare(records,[],materials,poses)['fixture_geometry_complete']
    for side in sides:
        changed=records[side][name]
        if fault=='missing_lod': changed['source_lods'].pop(1);changed['source_presence'].pop(1)
        elif fault=='unavailable': changed['source_presence'][1]={False};changed['source_lods'].pop(1)
        elif fault=='empty_source': changed['source_lods'][1]=[]
        else: changed['source_presence'][1]={True,False}
    with pytest.raises(ValueError,match='authored saved source LOD coverage'):
        proof.compare(records,[],materials,poses)
