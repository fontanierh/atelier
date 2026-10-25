"""Source/query boundaries and complete ordinary per-piece skate exports."""
import importlib.util
import ast
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import numpy as np
import pytest

GAME=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(GAME/'world'),str(GAME/'world/regions')]
from skatepark import features,atomic_source as source  # noqa: E402


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def test_selected_gardens_construct_only_owned_mesh_and_preserve_seeded_geometry():
    furniture,planting=features.gardens()
    own_furniture,other=features.gardens('SM_SkateParkFurniture')
    assert other is None and source.geometry_sha(furniture)==source.geometry_sha(own_furniture)
    other,own_planting=features.gardens('SM_SkateParkPlanting')
    assert other is None and source.geometry_sha(planting)==source.geometry_sha(own_planting)
    with pytest.raises(ValueError):features.gardens('SM_SkatePier')


def test_exact_sample_projection_preserves_selected_piling_geometry_and_refuses_missing_or_unused():
    rows,sample=source.recorder(lambda h,x,y:float(np.sin(x/37)+np.cos(y/41)-4))
    old=features.pilings(None,sample_fn=sample)
    packet=json.loads(json.dumps(dict(schema=1,name='SM_SkatePierPilings',samples=rows)))
    read,complete=source.lookup(packet,'SM_SkatePierPilings')
    current=features.pilings(None,sample_fn=read);complete()
    assert source.geometry_sha(current)==source.geometry_sha(old) and len(rows)==285
    damaged=dict(packet,samples=dict(packet['samples']));damaged['samples'].pop(next(iter(rows)))
    read,_=source.lookup(damaged,'SM_SkatePierPilings')
    with pytest.raises(ValueError,match='exact skate terrain'):features.pilings(None,sample_fn=read)
    damaged['samples']=dict(packet['samples'],foreign=1.)
    read,complete=source.lookup(damaged,'SM_SkatePierPilings');features.pilings(None,sample_fn=read)
    with pytest.raises(ValueError,match='membership'):complete()


def test_material_geometry_keeps_authored_order_and_excludes_texture_report_changes(tmp_path):
    names=['concrete','ceramic','steel','wood','basalt','mural']
    data={name:dict(repeat_m=1.+i,maps={'albedo':name+'.png'},metallic=0.) for i,name in enumerate(names)}
    path=tmp_path/'textures.json';path.write_text(json.dumps(data));first=source.material_projection(path)
    assert [row['name'] for row in first['materials']]==names+['painted']
    data['concrete']['maps']['albedo']='new-colour.png';data['concrete']['report']='proof-only'
    path.write_text(json.dumps(data));assert source.material_projection(path)==first
    data['wood']['repeat_m']=float('nan');path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='UV scale'):source.material_projection(path)


def test_skate_query_data_and_every_cold_selected_constructor_are_explicit(tmp_path):
    helper=module('skate_atomic_recipe',GAME/'skatepark_atomic_build.py')
    steps=helper.steps(SimpleNamespace(out=tmp_path.resolve()));by={step.name:step for step in steps}
    assert set(by['world.skatepark.query_data'].needs)=={'world.layout'}
    assert not by['world.skatepark.ao'].needs
    planners=[step for step in steps if '.geometry.' in step.name]
    assert len(planners)==10
    for step in planners:
        assert step.cache and step.commands[0].factory_startup and step.commands[0].threads==3
        assert not any('exports/world.' in str(path) for path in step.inputs)
        if step.name.rsplit('.',1)[-1] in helper.BOARD:assert not step.reads
    assert {'skatepark.meshes','skatepark.runtime','skatepark.queries'}=={p.name for p in by['world.skatepark'].products}
    assert by['world.skatepark'].cache


def test_each_discovered_skate_piece_has_independent_cached_actual_fbx_roundtrip(tmp_path):
    helper=module('skate_atomic_recipe_warm',GAME/'skatepark_atomic_build.py');out=tmp_path.resolve()
    for region,names in (('skatepark',helper.PARK),('skatepark_board',helper.BOARD)):
        for name in names:
            folder=out/'planned_exports'/region/name;folder.mkdir(parents=True)
            (folder/'plan.json').write_text(json.dumps(dict(schema=1,parent=name,complete=True,triangle_limit=32768,
                source_triangles=1,pieces=[dict(name=name,payload=name+'.npz',triangles=1)])))
    steps=helper.steps(SimpleNamespace(out=out));roundtrip=[step for step in steps if '.roundtrip.' in step.name]
    assert len(roundtrip)==10
    for step in roundtrip:
        name=step.name.rsplit('.',1)[-1]
        region='skatepark_board' if name in helper.BOARD else 'skatepark'
        assert step.reads==['world.'+region+'.export.'+name]
        assert step.cache and step.commands[0].factory_startup and step.commands[0].threads==3
    final=next(step for step in steps if step.name=='world.skatepark')
    assert {'skatepark.roundtrip.'+name for name in helper.PARK+helper.BOARD}<=set(final.reads)


def test_native_current_admission_checks_zero_hulls_lod_uv_and_keeps_one_coherent_policy():
    file=GAME/'unreal/Scripts/import_skatepark.py'
    nodes=[node for node in ast.parse(file.read_text()).body if isinstance(node,ast.FunctionDef)
           and node.name in ('current_geometry','receive')]
    body=SimpleNamespace(get_editor_property=lambda key:'complex')
    values=dict(lod_for_collision=0,complex_collision_mesh=None,body_setup=body,allow_cpu_access=True)
    mesh=SimpleNamespace(get_name=lambda:'SM_SkatePier',get_num_lods=lambda:1,get_num_triangles=lambda level:1,
        get_editor_property=values.__getitem__)
    collision=dict(simple=0,convex=0,uv=1);calls=[]
    editor=SimpleNamespace(get_num_uv_channels=lambda mesh,level:collision['uv'],
        get_simple_collision_count=lambda mesh:collision['simple'],get_convex_collision_count=lambda mesh:collision['convex'])
    def importer(*args,**kwargs):calls.append(kwargs);return mesh
    scope=dict(BLOCKS={'SM_SkatePier':True},build={'meshes':{'SM_SkatePier':{'triangles':1}}},
        park={'meshes':[{'name':'SM_SkatePier'}]},mesh_editor=editor,
        unreal=SimpleNamespace(CollisionTraceFlag=SimpleNamespace(CTF_USE_COMPLEX_AS_SIMPLE='complex',CTF_USE_SIMPLE_AS_COMPLEX='simple')),
        import_mesh=importer,prepare_source=lambda *args:pytest.fail('Do not mutate before the common admission miss'))
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(file),'exec'),scope)
    assert scope['current_geometry'](mesh)
    for field in ('simple','convex','uv'):
        prior=collision[field];collision[field]=1 if field!='uv' else 2
        assert not scope['current_geometry'](mesh);collision[field]=prior
    values['allow_cpu_access']=False;assert not scope['current_geometry'](mesh);values['allow_cpu_access']=True
    scope['receive']('one.fbx','/Game/SkatePark','SM_SkatePier',True)
    scope['receive']('one.fbx','/Game/SkatePark','SM_SkatePier',True)
    assert all(call['reuse_validator'] is scope['current_geometry'] and callable(call['before_import']) for call in calls)


def test_actual_skate_assembly_requires_all_roundtrips_before_retiring_owned_files(tmp_path):
    from atelier import mesh_ir,export_manifest
    from atelier.atomic_files import atomic_json
    from skatepark import assemble_atomic
    out=tmp_path.resolve();data=out/'skatepark-data';matrix=np.eye(4).tolist()
    piece=dict(positions=np.asarray([[0,0,0],[1,0,0],[0,1,0]]),normals=np.tile([0,0,1],(3,1)),
        faces=[[0,1,2]],materials=[0],smooth=[False],uvs=[('UVMap',np.zeros((3,2)))],colours=[])
    for name in source.PARK+source.BOARD:
        region='skatepark_board' if name in source.BOARD else 'skatepark'
        folder=out/'planned_exports'/region/name;folder.mkdir(parents=True)
        payload=mesh_ir.encode(piece,key=name,slots=['Palette'],matrix=matrix,options={});mesh_ir.write(folder/(name+'.npz'),payload)
        digest=export_manifest.sha(folder/(name+'.npz'))
        row=dict(name=name,payload=name+'.npz',sha256=digest,triangles=1,polygons=1,collision_hulls=0,min=[0,0,0],max=[1,1,0],source_faces=[0])
        atomic_json(folder/'plan.json',dict(schema=1,parent=name,complete=True,triangle_limit=32768,source_triangles=1,
            partition='explicit',collision_owner=None,
            source_polygons=1,source_collision_hulls=0,slots=['Palette'],matrix=matrix,pieces=[row]))
        atomic_json(data/'records'/(name+'.json'),dict(name=name,triangles=1,vertices=3,min=[0,0,0],max=[1,1,0],pieces=[name],material_slots=['Palette']))
        export=out/('exports/world.'+region+'.export')/name;export.mkdir(parents=True);(export/(name+'.fbx')).write_bytes(b'opaque verified primary')
        receipt=export_manifest.publish_receipt(export,key=name,primary=name+'.fbx',triangles=1,bounds=[[0,0,0],[1,1,0]],metadata=dict(geometry_sha256=digest))
        atomic_json(data/'roundtrip'/(name+'.json'),dict(schema=1,name=name,complete=True,fbx_sha256=receipt['sha256'],input_sha256=digest,triangles=1,imported_triangles=1,bounds_error_mm=0.))
    logical=json.loads((GAME/'world/regions/skatepark/park.json').read_text())
    atomic_json(data/'queries/logical.json',logical);atomic_json(data/'queries/report.json',{})
    atomic_json(data/'ao/report.json',{});(data/'queries/collision.json').write_bytes(b'exact original physics bytes')
    folder=out/'skatepark/assets';folder.mkdir(parents=True)
    obsolete=folder/'SM_SkatePier_Piece0000000000000000.fbx';obsolete.write_bytes(b'old owned source')
    proof=data/'roundtrip/SM_SkateDeck.json';saved=proof.read_bytes();proof.unlink()
    with pytest.raises(FileNotFoundError):assemble_atomic.main(['--out',str(out)])
    assert obsolete.read_bytes()==b'old owned source' and not (out/'skatepark/runtime-park.json').exists()
    proof.write_bytes(saved);assemble_atomic.main(['--out',str(out)])
    assert not obsolete.exists() and (out/'skatepark/collision.json').read_bytes()==b'exact original physics bytes'
    report=json.loads((out/'skatepark/build-report.json').read_text())
    assert set(report['identity']['exports'])=={'assets/'+name+'.fbx' for name in source.PARK}|{'board/'+name+'.fbx' for name in source.BOARD}
    before={p:p.stat().st_mtime_ns for part in ('assets','board') for p in (out/'skatepark'/part).glob('*.fbx')}
    assemble_atomic.main(['--out',str(out)])
    assert {p:p.stat().st_mtime_ns for p in before}==before


def test_roundtrip_counts_exact_shared_index_opposite_faces_without_changing_export_geometry():
    faces=[[0,1,2],[2,1,0],[3,4,5],[6,7,8,9]]
    piece=dict(faces=faces,triangles=5)
    assert source.imported_triangle_count(piece)==4
    assert piece['faces']==faces and piece['triangles']==5
    # Coordinate-coincident but independently indexed faces remain independent.
    assert source.imported_triangle_count(dict(faces=[[0,1,2],[3,4,5]]))==2


def test_skate_collision_bytes_use_existing_managed_scratch_under_real_recipe_guard(tmp_path):
    import io
    import subprocess
    from atelier.build_v2.recipe_worker import RecipeWorker
    from atelier.build_v2 import recipe_job
    root=tmp_path.resolve();(root/recipe_job.RUNTIME).mkdir();(root/'output').mkdir()
    (root/'entry.py').write_text('def run(context): pass\n')
    request={'script':'entry.py','code':['entry.py'],'inputs':[],
             'outputs':[{'path':'products/query.tree.tar'}],
             'params':{'recipe':{'paths':{},'outputs':[{'path':'build/data/queries/collision.json'}]}}}
    worker=RecipeWorker(io.BytesIO(),io.BytesIO(),True)
    worker.prepare_job(request,str(root));config=worker.configuration(request,str(root),99)
    program='''
import importlib.util,json,sys
from pathlib import Path
from atelier.atomic_files import managed_temporaries
from atelier.build_v2.python_job import PathGuard
values=json.load(sys.stdin);config=values['config']
spec=importlib.util.spec_from_file_location('skate_source',values['source'])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
root=Path(values['job_dir']);destination=Path(config['working_directory'])/'build/data/queries/collision.json'
guard=PathGuard(str(root),config['read_subpaths'],config['read_literals'],lambda _:None,
                config['write_subpaths'],config['working_directory'],config['mkdir_existing'])
with managed_temporaries(root/'.recipe-runtime/tmp'):
    guard.install()
    module.write_bytes(destination,b'exact original collision bytes')
assert not guard.allowed('write',str(destination.parent))
assert not guard.allowed('write',str(destination.with_name('foreign')))
'''
    payload={'config':config,'source':source.__file__,'job_dir':str(root)}
    result=subprocess.run([sys.executable,'-c',program],input=json.dumps(payload),text=True,capture_output=True)
    assert result.returncode==0,result.stdout+result.stderr
    assert (root/recipe_job.RUNTIME/'view/build/data/queries/collision.json').read_bytes()==b'exact original collision bytes'
    assert list((root/recipe_job.RUNTIME/'tmp').iterdir())==[]
    ordinary=tmp_path/'ordinary/collision.json';source.write_bytes(ordinary,b'ordinary sibling semantics')
    assert ordinary.read_bytes()==b'ordinary sibling semantics'
@pytest.mark.parametrize('name', [*source.BOARD, 'SM_SkateParkFurniture'])
def test_actual_selected_planner_declares_whole_board_and_explicit_park_policy(tmp_path, monkeypatch, name):
    fake_bpy = SimpleNamespace(ops=SimpleNamespace(wm=SimpleNamespace(read_factory_settings=lambda **kwargs: None)),
                               data=SimpleNamespace(materials=SimpleNamespace(new=lambda name: name)))
    monkeypatch.setitem(sys.modules, 'bpy', fake_bpy)
    planner = module('selected_skate_policy', GAME / 'world/regions/skatepark/plan_atomic.py')
    obj = SimpleNamespace(data=SimpleNamespace(materials=[SimpleNamespace(name='SkateParkPalette')]))
    monkeypatch.setattr(planner.geom, 'to_object', lambda *args: obj)
    monkeypatch.setattr(planner.geom, 'shade', lambda *args: None)
    monkeypatch.setattr(planner.source, 'material_objects', lambda path: 'Palette')
    monkeypatch.setattr(planner, 'capture', lambda data: {
        'vertex_indices': np.array([0, 1, 2]), 'starts': [0], 'counts': [3],
        'positions': np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])})
    calls = []
    def plan(obj, root, **kwargs):
        calls.append(kwargs)
        return {'pieces': [{'name': name}]}
    monkeypatch.setattr(planner, 'plan', plan)
    planner.main(['--asset', name, '--record', str(tmp_path / 'record.json'),
                  '--output', str(tmp_path / 'geometry')])
    assert len(calls) == 1 and calls[0]['options'] == planner.OPTIONS
    if name in source.BOARD:
        assert calls[0]['partition'] == 'whole' and calls[0]['face_groups'] is None
    else:
        assert calls[0]['partition'] == 'explicit' and calls[0]['face_groups'] == [(name, (0,))]
    assert json.loads((tmp_path / 'record.json').read_text())['pieces'] == [name]
