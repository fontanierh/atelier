"""Run real named-product propagation with tiny outputs instead of native tools."""
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_checkpoints

GAME = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('region_products', GAME / 'region_products.py')
products = importlib.util.module_from_spec(spec); spec.loader.exec_module(products)
RECIPE = build.load_recipe('yorimichi')


def export(folder, config):
    (folder / 'glb').mkdir(parents=True, exist_ok=True)
    (folder / 'textures').mkdir(exist_ok=True)
    names = ['SM_BC_Ground_0_0', 'SM_BC_Plant_Palm', 'SM_BC_Pier']
    if config.get('extra'): names.append('SM_BC_Plant_New')
    for path in (folder / 'glb').glob('*'): path.unlink()
    meshes = []
    for name in names:
        raw = (name + str(config.get('ground' if 'Ground' in name else 'plant' if 'Plant' in name else 'pier', 0))).encode()
        path = 'glb/' + name + '.glb'; (folder / path).write_bytes(raw)
        meshes.append(dict(name=name, path=path, sha256=hashlib.sha256(raw).hexdigest(),
                           bounds_m=[[0, 0, 0], [1, 1, 1]], slots=['Paint'], collision='Plant' not in name))
    (folder / 'textures/paint.png').write_bytes(('paint'+str(config.get('texture', 0))).encode())
    report = dict(meshes=meshes, materials={'Paint': {'texture': 'paint.png', 'roughness': config.get('material', .5)}})
    groups = []
    for name in names:
        transform = dict(translation_cm=[config.get('placement', 0) if 'Plant' in name else config.get('solid_move', 0), 0, 0],
                         rotation=[0, 0, 0], scale=[1, 1, 1])
        groups.append(dict(asset='/Game/Brinecove/Meshes/'+name+'.'+name,
                           plant='Plant' in name, transforms=[transform], materials=['Paint']))
    runtime = dict(origin_cm=[0, 0, 0], bounds_m=[0, 0, 10, 10], clearance_m=[0, 0, 10, 10], zones=[], groups=groups)
    (folder / 'build-report.json').write_text(json.dumps(report))
    (folder / 'runtime.json').write_text(json.dumps(runtime))


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    out = tmp_path / 'out'; source = tmp_path / 'settings.json'
    ctx = SimpleNamespace(game='fixture', out=out, logs=out/'logs', stamps=out/'stamps', uproject=None)
    executed = []
    def generator(ctx, log):
        executed.append('export'); export(out/'brinecove', json.loads(source.read_text()))
    producer = build.Step('export', [build.Call('tiny region exporter', generator)], inputs=[source],
                          outputs=[out/'brinecove/build-report.json', out/'brinecove/runtime.json'])
    real = RECIPE.brinecove_steps(out)[1]
    def project(ctx, log):
        executed.append('products')
        products.publish(out/'brinecove', out/'products/brinecove', ground_prefix='SM_BC_Ground_', plant_prefix='SM_BC_Plant_')
    projection = replace(real, name='products', commands=[build.Call('project consumed views', project)],
                         needs=['export', 'world.brinecove.textures'], cache=False, audit=False)
    selector = replace(RECIPE.region_texture_step(out, 'brinecove'), needs=['export'])
    steps = [producer, selector, projection]
    def consume(name, reads, needs=()):
        destination = out/(name+'.json')
        def run(ctx, log):
            executed.append(name)
            destination.write_text(json.dumps({p:(out/'products/brinecove'/ (p.split('.')[-1]+'.json')).read_text() for p in reads},sort_keys=True))
        steps.append(build.Step(name, [build.Call(name, run)], reads=reads, needs=list(needs), outputs=[destination]))
    consume('import', ['brinecove.geometry','brinecove.materials'])
    consume('map', ['brinecove.map'])
    consume('clearance', ['brinecove.clearance'])
    consume('stage', ['brinecove.runtime'], ['map'])
    consume('package', [], ['import','stage','clearance'])
    monkeypatch.setattr(build, 'Context', lambda *a, **k: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=lambda _: steps))
    monkeypatch.setattr(build_checkpoints, 'configured', lambda _: None)
    state = {}
    def run():
        source.write_text(json.dumps(state, sort_keys=True))
        executed.clear()
        assert build.build('fixture', ['package'], echo=lambda _: None) == 0
        return set(executed)
    assert run() == {'export','products','import','map','clearance','stage','package'}
    return SimpleNamespace(run=run,state=state,out=out,steps=steps)


@pytest.mark.parametrize('edit,expected', [
    ({}, set()),
    ({'placement': 10}, {'export','products','map','stage','package'}),
    ({'texture': 1}, {'export','products','import','package'}),
    ({'material': .9}, {'export','products','import','package'}),
    ({'plant': 1}, {'export','products','import','package'}),
    ({'solid_move': 10}, {'export','products','clearance','stage','package'}),
    ({'ground': 1}, {'export','products','import','map','clearance','stage','package'}),
    ({'pier': 1}, {'export','products','import','clearance','package'}),
    ({'extra': True}, {'export','products','import','map','stage','package'}),
])
def test_only_actual_consumers_execute(pipeline, edit, expected):
    p=pipeline
    before={path:path.read_bytes() for path in p.out.glob('*.json')}
    p.state.update(edit)
    assert p.run() == expected
    for path, raw in before.items():
        if path.stem not in expected:
            assert path.read_bytes() == raw


def test_model_removal_updates_membership_and_placements_without_ferry_rebuild(pipeline):
    p=pipeline; p.state['extra']=True; p.run()
    del p.state['extra']
    assert p.run() == {'export','products','import','map','stage','package'}
    assert not (p.out/'brinecove/glb/SM_BC_Plant_New.glb').exists()


@pytest.mark.parametrize('fault', ['missing','extra','changed','linked'])
def test_model_inventory_cannot_hide_missing_extra_changed_or_linked_members(tmp_path,fault):
    folder=tmp_path/'region'; export(folder,{})
    path=folder/'glb/SM_BC_Pier.glb'
    if fault=='missing': path.unlink()
    elif fault=='extra': (folder/'glb/unlisted.glb').write_bytes(b'unlisted')
    elif fault=='changed': path.write_bytes(b'changed')
    else:
        original=folder/'original.bin'; path.rename(original); path.symlink_to(original)
    with pytest.raises(ValueError): products.views(folder,ground_prefix='SM_BC_Ground_',plant_prefix='SM_BC_Plant_')


@pytest.mark.parametrize('collision', [True, False])
def test_brinecove_boolean_collision_flags_do_not_declare_hull_sources(tmp_path, collision):
    export(tmp_path, {})
    path = tmp_path / 'build-report.json'
    report = json.loads(path.read_text())
    for mesh in report['meshes']: mesh['collision'] = collision
    path.write_text(json.dumps(report))
    view = products.views(tmp_path, ground_prefix='SM_BC_Ground_', plant_prefix='SM_BC_Plant_')
    assert all(mesh['collision'] is collision for mesh in view['geometry']['meshes'])
    assert set(view['geometry']['files']) == {mesh['path'] for mesh in report['meshes']}


@pytest.mark.parametrize('collision', [0, 1, 'yes', [], {}])
def test_invalid_collision_source_schema_refuses(tmp_path, collision):
    export(tmp_path, {})
    path = tmp_path / 'build-report.json'
    report = json.loads(path.read_text())
    report['meshes'][0]['collision'] = collision
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match='collision-source'):
        products.views(tmp_path, ground_prefix='SM_BC_Ground_', plant_prefix='SM_BC_Plant_')


def test_recipe_consumers_follow_named_brinecove_inputs(tmp_path):
    steps=RECIPE.steps(SimpleNamespace(out=tmp_path/'out',game='yorimichi',uproject=RECIPE.GAME/'unreal/Yorimichi.uproject'))
    by_name={step.name:step for step in steps}
    assert set(by_name['unreal.brinecove'].reads)=={'brinecove.geometry','brinecove.materials'}
    assert 'world.brinecove' not in by_name['world.map'].needs
    assert 'brinecove.map' in by_name['world.map'].reads
    assert 'brinecove.runtime' in by_name['data.stage'].reads
    assert 'world.brinecove.meshes' not in by_name['world.ferry_probes'].needs
    assert 'brinecove.query_data' in by_name['world.ferry_probes'].reads
    assert 'brinecove.clearance' not in by_name['world.ferry_probes'].reads


def test_real_projection_runs_with_complete_audited_inputs(tmp_path, monkeypatch):
    out=tmp_path/'out'; export(out/'brinecove',{})
    ctx=SimpleNamespace(game='fixture',out=out,logs=out/'logs',stamps=out/'stamps',uproject=None)
    selector=replace(RECIPE.region_texture_step(out,'brinecove'),needs=[])
    step=RECIPE.brinecove_steps(out)[1]
    step=replace(step,needs=[selector.name])
    monkeypatch.setattr(build,'Context',lambda *a,**k:ctx)
    monkeypatch.setattr(build,'load_recipe',lambda _:SimpleNamespace(steps=lambda _:[selector,step]))
    monkeypatch.setattr(build_checkpoints,'configured',lambda _:None)
    monkeypatch.setenv('ATELIER_CACHE',str(tmp_path/'cache'))
    assert build.build('fixture',[step.name],echo=lambda _:None)==0
    stamp=json.loads((ctx.stamps/(step.name+'.json')).read_text())
    assert stamp['audit_receipt']['execution']=='audited-python-v1'
    assert set(stamp['products'])=={'brinecove.'+name for name in ('geometry','materials','runtime','map','clearance')}
    assert build.build('fixture',[step.name],echo=lambda _:None)==0


@pytest.mark.parametrize('field,filename',[('texture','paint.dds'),('layers','layer.tif'),('normals','normal.hdr')])
def test_every_consumed_texture_field_binds_actual_bytes_regardless_extension(tmp_path,field,filename):
    folder=tmp_path/'region'; export(folder,{})
    report=json.loads((folder/'build-report.json').read_text())
    if field=='texture':report['materials']['Paint'][field]=filename
    else:report['materials']['Paint'][field]={'LayerA':filename}
    (folder/'build-report.json').write_text(json.dumps(report))
    path=folder/'textures'/filename;path.write_bytes(b'original texture')
    before=products.views(folder,ground_prefix='SM_BC_Ground_',plant_prefix='SM_BC_Plant_')
    path.write_bytes(b'changed texture')
    after=products.views(folder,ground_prefix='SM_BC_Ground_',plant_prefix='SM_BC_Plant_')
    assert before['materials']!=after['materials']
    assert all(before[name]==after[name] for name in ('geometry','map','clearance','runtime'))
    path.unlink()
    with pytest.raises(ValueError,match='absent'):
        products.views(folder,ground_prefix='SM_BC_Ground_',plant_prefix='SM_BC_Plant_')


def test_actual_runtime_staging_copies_the_published_runtime_view(tmp_path,monkeypatch):
    import io
    runtime=RECIPE.runtime_data
    out=tmp_path/'out';export(out/'brinecove',{})
    products.publish(out/'brinecove',out/'products/brinecove',ground_prefix='SM_BC_Ground_',plant_prefix='SM_BC_Plant_')
    published=(out/'products/brinecove/runtime.json').read_bytes()
    (out/'brinecove/runtime.json').write_text('raw export must not be the staging input')
    destination=tmp_path/'Content/Data'
    monkeypatch.setattr(runtime,'staged',lambda _:('brinecove/runtime.json',))
    monkeypatch.setattr(runtime.courses,'load',lambda *a:None)
    monkeypatch.setattr(runtime.paths,'content_data',lambda _:destination)
    runtime.stage_data(SimpleNamespace(out=out,game='fixture'),io.StringIO())
    assert (destination/'brinecove/runtime.json').read_bytes()==published


def test_legacy_clearance_control_reads_projection_without_raw_runtime_or_materials(tmp_path):
    import ast,math
    import numpy as np
    out=tmp_path/'out';export(out/'brinecove',{})
    products.publish(out/'brinecove',out/'products/brinecove',ground_prefix='SM_BC_Ground_',plant_prefix='SM_BC_Plant_')
    (out/'brinecove/runtime.json').write_text('raw runtime must not be read')
    (out/'brinecove/build-report.json').write_text('raw material report must not be read')
    file=GAME/'assets/vehicles/ferry/terminals/world_probe.py'
    function=next(node for node in ast.parse(file.read_text()).body if isinstance(node,ast.FunctionDef) and node.name=='legacy_brinecove')
    opened=[]
    scope=dict(json=json,math=math,np=np,S=SimpleNamespace(BOUNDS={'brinecove':[-5,-5,5,5]}),Z_BAND=(-1,1),
        sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest(),
        import_file=lambda p:opened.append(p) or [],unreal_to_blender=lambda t:t,
        triangles=lambda *a:np.zeros((1,3,3)),clip=lambda tris,*a:tris,clear_scene=lambda:None,label=lambda n:n)
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(file),'exec'),scope)
    ground,solid,names,sources,frame=scope['legacy_brinecove'](out)
    assert {path.stem for path in opened}=={'SM_BC_Ground_0_0','SM_BC_Pier'}
    assert len(ground)==1 and len(solid)==1 and names==['SM_BC_Pier']
    assert 'products/brinecove/clearance.json' in sources
    assert 'brinecove/runtime.json' not in sources and 'brinecove/build-report.json' not in sources
    assert frame['origin_cm']==[0,0,0]
