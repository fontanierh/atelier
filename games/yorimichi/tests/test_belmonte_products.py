"""Exercise the real regional views, incremental graph and material/runtime consumers."""
from dataclasses import replace
import ast
import hashlib
import io
import json
from types import SimpleNamespace

import pytest

from atelier import build, build_checkpoints, build_products
from test_region_products import products, RECIPE


def export(folder, settings):
    (folder / 'glb').mkdir(parents=True, exist_ok=True)
    (folder / 'textures').mkdir(exist_ok=True)
    meshes, groups = [], []
    for name in ('SM_BM_House', 'SM_BM_Ground'):
        raw = (name + str(settings.get('geometry', 0))).encode()
        member = 'glb/' + name + '.glb'
        (folder / member).write_bytes(raw)
        entry = dict(name=name, path=member, sha256=hashlib.sha256(raw).hexdigest(),
                     triangles=1, bounds_m=[[0, 0, 0], [1, 2, 3]], slots=['paint'])
        if name == 'SM_BM_House':
            raw = str(settings.get('collision', 0)).encode()
            (folder / 'glb/House_Collision.glb').write_bytes(raw)
            entry['collision'] = dict(path='meshes/House_Collision.glb', sha256=hashlib.sha256(raw).hexdigest())
        meshes.append(entry)
        groups.append(dict(asset=f'/Game/Belmonte/Meshes/{name}.{name}', plant=False,
                           materials=[settings.get('binding', 'paint')], transforms=[{'x': settings.get('placement', 0)}]))
    groups.append(dict(asset='/Game/Japan/Assets/Tree.Tree', plant=True, materials=[],
                       transforms=[{'x': settings.get('tree', 0)}]))
    # Numeric layer colours are consumed material values, not texture paths.
    material = dict(texture='paint.png', layers={'Dry': [.2, .3, .4]}, roughness=settings.get('material', .5))
    material['name'] = 'MI_BM_paint'
    (folder / 'textures/paint.png').write_bytes(str(settings.get('texture', 0)).encode())
    (folder / 'build-report.json').write_text(json.dumps(dict(meshes=meshes, materials={'paint': material},
                                                            planting={'count': settings.get('tree', 0)})))
    (folder / 'runtime.json').write_text(json.dumps(dict(groups=groups, signs=settings.get('signs', []))))


@pytest.mark.parametrize('edit,consumers', [
    ({}, set()),
    ({'placement': 10}, {'stage'}),
    ({'tree': 20}, {'stage'}),
    ({'signs': ['new sign']}, {'stage'}),
    ({'material': .7}, {'import', 'track'}),
    ({'binding': 'other'}, {'import', 'track', 'stage'}),
    ({'texture': 1}, {'import', 'track'}),
    ({'geometry': 1}, {'import'}),
    ({'collision': 1}, {'import'}),
])
def test_actual_graph_propagates_only_consumed_belmonte_views(tmp_path, monkeypatch, edit, consumers):
    out = tmp_path / 'out'
    source = tmp_path / 'settings.json'
    ctx = SimpleNamespace(game='fixture', out=out, logs=out / 'logs', stamps=out / 'stamps', uproject=None)
    ran = []
    def generate(ctx, log):
        ran.append('export')
        export(out / 'belmonte', json.loads(source.read_text()))
    producer = build.Step('export', [build.Call('tiny export', generate)], inputs=[source],
                          outputs=[out / 'belmonte/build-report.json', out / 'belmonte/runtime.json'])
    projection = RECIPE.belmonte_steps(out)[1]
    def project(ctx, log):
        ran.append('products')
        products.publish_library(out / 'belmonte', out / 'products/belmonte')
    steps = [producer, replace(projection, name='products', commands=[build.Call('views', project)],
                               needs=['export'], cache=False, audit=False)]
    actual = {step.name: step for step in RECIPE.belmonte_steps(out)}
    for name, reads in [('import', actual['unreal.belmonte'].reads),
                        ('track', actual['unreal.belmonte_track'].reads), ('stage', ['belmonte.runtime'])]:
        def consume(ctx, log, name=name, reads=reads):
            ran.append(name)
            def path(product):
                return (out / (product.split('.')[-1] + '.json') if '.native_' in product else
                        out / 'products/belmonte' / (product.split('.')[-1] + '.json'))
            (out / (name + '.json')).write_text(json.dumps({r: path(r).read_text() for r in reads}, sort_keys=True))
            if name == 'import':
                (out / 'native_meshes.json').write_bytes(path('belmonte.geometry').read_bytes())
                (out / 'native_materials.json').write_bytes(path('belmonte.materials').read_bytes())
                (out / 'native_tv.json').write_text('independent screen material')
        owned = ([build.Product('belmonte.' + kind, (out / (kind + '.json'),))
                  for kind in ('native_meshes', 'native_materials', 'native_tv')]
                 + [build.Product('belmonte.native_report', (out / 'import.json',))]) if name == 'import' else []
        steps.append(build.Step(name, [build.Call(name, consume)], reads=reads,
                                products=owned, outputs=[out / (name + '.json')]))
    monkeypatch.setattr(build, 'Context', lambda *a, **kw: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=lambda _: steps))
    monkeypatch.setattr(build_checkpoints, 'configured', lambda _: None)
    def run(settings):
        source.write_text(json.dumps(settings))
        ran.clear()
        assert build.build('fixture', ['import', 'track', 'stage'], echo=lambda _: None) == 0
        return set(ran)
    assert run({}) == {'export', 'products', 'import', 'track', 'stage'}
    assert run({}) == set()
    before = {p: p.read_bytes() for p in out.glob('*.json')}
    assert run(edit) == ({'export', 'products', *consumers} if edit else set())
    for path, raw in before.items():
        changed = set(consumers)
        if 'import' in consumers:
            changed.update(('native_meshes', 'native_materials', 'native_tv'))
        if path.stem not in changed:
            assert path.read_bytes() == raw


@pytest.mark.parametrize('fault', ['missing_hull', 'changed_hull', 'extra_model', 'missing_bindings'])
def test_collision_membership_hashes_and_default_bindings_are_required(tmp_path, fault):
    export(tmp_path, {})
    if fault == 'missing_hull': (tmp_path / 'glb/House_Collision.glb').unlink()
    if fault == 'changed_hull': (tmp_path / 'glb/House_Collision.glb').write_bytes(b'changed')
    if fault == 'extra_model': (tmp_path / 'glb/extra.glb').write_bytes(b'extra')
    if fault == 'missing_bindings':
        runtime = json.loads((tmp_path / 'runtime.json').read_text())
        runtime['groups'] = [group for group in runtime['groups'] if group['plant']]
        (tmp_path / 'runtime.json').write_text(json.dumps(runtime))
    with pytest.raises(ValueError): products.library_views(tmp_path, collision_basename=True, bindings=True)


def test_first_default_binding_matches_native_owner_and_ignores_later_instance_materials(tmp_path):
    export(tmp_path, {})
    path = tmp_path / 'runtime.json'
    runtime = json.loads(path.read_text())
    runtime['groups'].append(dict(runtime['groups'][0], materials=['later binding'], transforms=[]))
    path.write_text(json.dumps(runtime))
    view = products.library_views(tmp_path, collision_basename=True, bindings=True)
    assert view['materials']['bindings']['SM_BM_House'] == ['paint']
    assert 'textures/paint.png' in view['materials']['files']
    assert 'glb/House_Collision.glb' in view['geometry']['files']


def test_actual_recipe_and_runtime_staging_use_named_belmonte_views(tmp_path, monkeypatch):
    ctx = SimpleNamespace(out=tmp_path, game='yorimichi', uproject=RECIPE.GAME / 'unreal/Yorimichi.uproject')
    steps = {step.name: step for step in RECIPE.steps(ctx)}
    build_products.Graph(list(steps.values()))
    assert set(steps['unreal.belmonte'].reads) == {'belmonte.geometry', 'belmonte.materials'}
    assert 'world.belmonte.meshes' not in steps['unreal.belmonte'].needs
    assert 'world.belmonte.meshes' not in steps['unreal.belmonte_track'].needs
    assert 'unreal.belmonte' not in steps['unreal.belmonte_track'].needs
    assert steps['unreal.belmonte_track'].reads == ['belmonte.materials', 'belmonte.native_materials']
    native = {p.name: p for p in steps['unreal.belmonte'].products}
    content = RECIPE.GAME / 'unreal/Content'
    assert native['belmonte.native_meshes'].paths == (content / 'Belmonte/Meshes',)
    assert native['belmonte.native_materials'].paths == (content / 'Belmonte/Materials', content / 'Belmonte/Textures')
    assert native['belmonte.native_tv'].paths == (content / 'Racing/M_RacingTv.uasset',)
    assert {path.name for path in native['belmonte.native_tv'].optional_paths} == {
        'M_RacingTv' + suffix for suffix in ('.uexp', '.ubulk', '.uptnl', '.m.ubulk', '.upayload')}
    assert not steps['unreal.belmonte'].cache
    assert 'belmonte.runtime' in steps['data.stage'].reads and 'world.belmonte' not in steps['data.stage'].needs
    export(tmp_path / 'belmonte', {})
    products.publish_library(tmp_path / 'belmonte', tmp_path / 'products/belmonte')
    report = json.loads((tmp_path / 'belmonte/build-report.json').read_text())
    geometry = json.loads((tmp_path / 'products/belmonte/geometry.json').read_text())
    assert geometry['meshes'] == report['meshes']  # Preserve the real native import traversal order.
    expected = (tmp_path / 'products/belmonte/runtime.json').read_bytes()
    (tmp_path / 'belmonte/runtime.json').write_text('raw runtime must not be consumed')
    runtime = RECIPE.runtime_data
    destination = tmp_path / 'Content/Data'
    monkeypatch.setattr(runtime, 'staged', lambda _: ('belmonte/runtime.json',))
    monkeypatch.setattr(runtime.courses, 'load', lambda *a: None)
    monkeypatch.setattr(runtime.paths, 'content_data', lambda _: destination)
    runtime.stage_data(ctx, io.StringIO())
    assert (destination / 'belmonte/runtime.json').read_bytes() == expected


def test_actual_track_material_mapping_reads_the_published_view(tmp_path):
    export(tmp_path / 'belmonte', {})
    products.publish_library(tmp_path / 'belmonte', tmp_path / 'products/belmonte')
    (tmp_path / 'belmonte/build-report.json').write_text('unconsumed broad report')
    script = RECIPE.SCRIPTS / 'import_belmonte_track.py'
    module = ast.parse(script.read_text())
    source = next(n for n in module.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == 'BELMONTE_REPORT' for t in n.targets))
    main = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    mapping = next(n for n in main.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'belmonte' for t in n.targets))
    scope = dict(yori=SimpleNamespace(OUT=tmp_path), json=json)
    exec(compile(ast.Module(body=[source, mapping], type_ignores=[]), str(script), 'exec'), scope)
    assert scope['belmonte'] == {'paint': '/Game/Belmonte/Materials/MI_BM_paint'}


def test_real_library_projection_has_complete_audited_inputs(tmp_path, monkeypatch):
    out = tmp_path / 'out'
    export(out / 'belmonte', {})
    ctx = SimpleNamespace(out=out, game='fixture', logs=out / 'logs', stamps=out / 'stamps', uproject=None)
    step = replace(RECIPE.belmonte_steps(out)[1], needs=[])
    monkeypatch.setattr(build, 'Context', lambda *a, **kw: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=lambda _: [step]))
    monkeypatch.setattr(build_checkpoints, 'configured', lambda _: None)
    monkeypatch.setenv('ATELIER_CACHE', str(tmp_path / 'cache'))
    assert build.build('fixture', [step.name], echo=lambda _: None) == 0
    record = json.loads((ctx.stamps / (step.name + '.json')).read_text())
    assert record['audit_receipt']['execution'] == 'audited-python-v1'
    assert set(record['products']) == {'belmonte.geometry', 'belmonte.materials', 'belmonte.runtime'}
