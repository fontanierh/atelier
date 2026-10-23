"""Execute the model/placement boundary without Blender; preserve authored geometry."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from atelier import build, build_batches, build_checkpoints, build_products
from test_volcano_layers import RECIPE


@pytest.fixture
def library(monkeypatch):
    monkeypatch.syspath_prepend(str(RECIPE.REGIONS))
    from brinecove import foliage_library, foliage_models
    return foliage_library, foliage_models


def encoded(builder):
    return json.dumps(builder.__dict__, sort_keys=True, separators=(',', ':')).encode()


def test_every_original_prototype_keeps_vertices_faces_uvs_normals_and_materials(library):
    from brinecove import flora
    baseline = json.loads((Path(__file__).parent / 'fixtures/brinecove-prototype-geometry.json').read_text())
    actual = {name: hashlib.sha256(encoded(mesh)).hexdigest() for name, mesh in flora.prototypes().items()}
    assert actual == baseline
    assert list(actual) == list(baseline)


@pytest.mark.parametrize('fault', ['none', 'missing', 'extra', 'duplicate', 'linked'])
def test_catalogue_binds_complete_membership_and_preserves_authored_order(tmp_path, monkeypatch, library, fault):
    from brinecove import foliage_names
    monkeypatch.setattr(foliage_names, '__file__', str(tmp_path / 'foliage_names.py'))
    folder = tmp_path / 'foliage_models'
    folder.mkdir()
    names = ['palm_0', 'bloom_0']
    for name in names: (folder / (name + '.json')).write_text('{}')
    if fault == 'missing': (folder / 'palm_0.json').unlink()
    if fault == 'extra': (folder / 'extra_0.json').write_text('{}')
    if fault == 'duplicate': names.append('palm_0')
    if fault == 'linked':
        (folder / 'palm_0.json').unlink()
        (folder / 'palm_0.json').symlink_to(folder / 'bloom_0.json')
    (tmp_path / 'foliage_catalog.json').write_text(json.dumps(names))
    if fault == 'none':
        assert [p.stem for p in foliage_names.definitions()] == names
    else:
        with pytest.raises(ValueError): foliage_names.definitions()


def test_real_model_declarations_have_independent_inputs_and_complete_owners(tmp_path):
    steps = RECIPE.brinecove_model_steps(tmp_path)
    build.check_modules(steps)
    assert len(steps) == 36
    build_products.Graph(steps)
    for step in steps:
        command = step.commands[0]
        assert step.toolchain and step.batch and step.heavy and command.factory_startup and command.threads == 3
        definitions = [p for p in step.inputs if p.suffix == '.json']
        assert len(definitions) == 1 and definitions[0].stem == step.name.rsplit('.', 1)[-1]
        forbidden = {'layout.py', 'flora.py', 'build.py', 'kit.py', 'surfaces.py', 'region.py', 'foliage_library.py'}
        assert not forbidden.intersection(p.name for p in step.inputs)
        assert all('terrain' not in str(p) and 'textures' not in p.parts for p in step.inputs)
    assembly = RECIPE.brinecove_steps(tmp_path)[0]
    assert {step.products[0].name for step in steps} <= set(assembly.reads)
    assert not {step.products[1].name for step in steps} & set(assembly.reads)
    assert RECIPE.paths.STUDIO / 'atelier/model_export.py' in assembly.inputs
    assert RECIPE.paths.STUDIO / 'atelier/mesh_partition.py' in assembly.inputs
    assert RECIPE.REGIONS / 'brinecove/foliage_catalog.json' in assembly.inputs
    assert RECIPE.REGIONS / 'brinecove/review_build.py' not in assembly.inputs


def test_fresh_model_batch_serializes_the_actual_declared_arguments(tmp_path):
    steps = RECIPE.brinecove_model_steps(tmp_path)
    ctx = SimpleNamespace(out=tmp_path, game='fixture', logs=tmp_path / 'logs', stamps=tmp_path / 'stamps')
    session = build_batches.Session(ctx, [(step, 'key', {}) for step in steps], {}, None, {}, None, {})
    session.write_plan()
    actions = json.loads((session.folder / 'plan.json').read_text())['actions']
    assert len(actions) == 36
    for step, action in zip(steps, actions):
        assert action['args'] == list(step.commands[0].args)
        assert Path(action['args'][0]).is_file()
        assert Path(action['args'][1]) == step.products[0].paths[0]
        assert Path(action['args'][2]) == step.products[1].paths[0]


def test_model_entrypoint_imports_in_an_isolated_embedded_interpreter(tmp_path):
    script = RECIPE.REGIONS / 'brinecove/export_foliage_model.py'
    # No installed Atelier, PYTHONPATH, test sys.path, or script cwd: embedded tools
    # must find the committed Studio package from the entrypoint itself.
    result = subprocess.run([sys.executable, '-I', '-S', '-c',
                             'import runpy, sys; runpy.run_path(sys.argv[1])', str(script)],
                            cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_actual_graph_preserves_models_for_placement_edits_and_rebuilds_only_changed_model(tmp_path, monkeypatch, library):
    lib, models = library
    out = tmp_path / 'out'
    ctx = SimpleNamespace(out=out, game='fixture', logs=out / 'logs', stamps=out / 'stamps', uproject=None)
    selected = [step for step in RECIPE.brinecove_model_steps(out)
                if step.name.endswith(('.bloom_0', '.bloom_1'))]
    executed, definitions, steps = [], [], []
    for original in selected:
        definition = next(p for p in original.inputs if p.suffix == '.json')
        copy = tmp_path / definition.name
        copy.write_bytes(definition.read_bytes())
        definitions.append(copy)
        folder = original.products[0].paths[0]
        query = original.products[1].paths[0]
        def generate(ctx, log, source=copy, folder=folder, task=original.name, query=query):
            executed.append(task)
            mesh = models.build(json.loads(source.read_text()))
            data = encoded(mesh)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / 'model.glb').write_bytes(data)
            model = dict(name=lib.name(source.stem), sha256=hashlib.sha256(data).hexdigest(),
                         triangles=sum(len(face) - 2 for face in mesh.faces), slots=sorted(set(mesh.mats)),
                         bounds_m=[[min(v[i] for v in mesh.verts) for i in range(3)],
                                   [max(v[i] for v in mesh.verts) for i in range(3)]],
                         collision=False, lods=True)
            (folder / 'model.json').write_text(json.dumps(model, sort_keys=True))
            # Cache-control fixture bytes; actual query serialization is native-tested separately.
            query.parent.mkdir(parents=True, exist_ok=True); query.write_bytes(data)
        steps.append(replace(original, commands=[build.Call(original.name, generate)],
                             inputs=[copy, *[p for p in original.inputs if p != definition]],
                             cache=False, heavy=False, toolchain=False, batch=None))
    monkeypatch.setattr(lib, 'definitions', lambda: definitions)
    placement = tmp_path / 'placement.json'
    placement.write_text('{"x": 0}')
    def assemble(ctx, log):
        executed.append('assembly')
        (out / 'geometry.json').write_text(json.dumps(lib.load(out / 'models/brinecove/plants'), sort_keys=True))
        (out / 'runtime.json').write_bytes(placement.read_bytes())
    steps.append(build.Step('assembly', [build.Call('assemble model instances', assemble)], inputs=[placement],
        reads=[p.name for step in steps for p in step.products],
        products=[build.Product('fixture.geometry', (out / 'geometry.json',)),
                  build.Product('fixture.runtime', (out / 'runtime.json',))]))
    monkeypatch.setattr(build, 'Context', lambda *a, **kw: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=lambda _: steps))
    monkeypatch.setattr(build_checkpoints, 'configured', lambda _: None)
    def run():
        executed.clear()
        assert build.build('fixture', ['assembly'], echo=lambda _: None) == 0
        return list(executed)
    assert run() == [step.name for step in steps[:-1]] + ['assembly']
    old_models = {file: file.read_bytes() for file in (out / 'models').rglob('*') if file.is_file()}
    geometry = (out / 'geometry.json').read_bytes()
    assert run() == []
    placement.write_text('{"x": 42}')
    assert run() == ['assembly']
    assert (out / 'geometry.json').read_bytes() == geometry
    assert all(file.read_bytes() == data for file, data in old_models.items())
    definition = definitions[0]
    changed = json.loads(definition.read_text())
    changed['parameters']['radius'] += .25
    definition.write_text(json.dumps(changed))
    assert run() == [steps[0].name, 'assembly']
    assert (out / 'geometry.json').read_bytes() != geometry
    assert all(file.read_bytes() == data for file, data in old_models.items() if definitions[1].stem in file.parts)


@pytest.mark.parametrize('fault', ['missing', 'extra', 'linked', 'changed', 'wrong_name'])
def test_incomplete_or_unproved_model_library_refuses(tmp_path, monkeypatch, library, fault):
    lib, _ = library
    definition = tmp_path / 'bloom_0.json'
    monkeypatch.setattr(lib, 'definitions', lambda: [definition])
    folder = tmp_path / 'library/bloom_0'
    folder.mkdir(parents=True)
    model = folder / 'model.glb'
    model.write_bytes(b'geometry')
    record = dict(name=lib.name('bloom_0'), sha256=hashlib.sha256(model.read_bytes()).hexdigest(),
                  triangles=1, bounds_m=[[0, 0, 0], [1, 1, 1]], slots=['leaf'], collision=False, lods=True)
    if fault == 'wrong_name': record['name'] = lib.name('bloom_1')
    (folder / 'model.json').write_text(json.dumps(record))
    if fault == 'missing': model.unlink()
    if fault == 'extra': (folder / 'unexpected.glb').write_bytes(b'extra')
    if fault == 'linked': model.rename(folder / 'original'); model.symlink_to(folder / 'original')
    if fault == 'changed': model.write_bytes(b'new geometry')
    with pytest.raises(ValueError): lib.load(folder.parent)


def test_real_model_entrypoint_publishes_a_verifiable_independent_product(tmp_path, monkeypatch, library):
    lib, _ = library
    from brinecove import export_foliage_model as exporter
    from atelier.gltf import glb_pack
    definition = next(p for p in lib.definitions() if p.stem == 'bloom_0')
    calls, exported = [], []
    monkeypatch.setitem(sys.modules, 'bpy', SimpleNamespace(
        ops=SimpleNamespace(wm=SimpleNamespace(read_factory_settings=lambda **kw: calls.append(kw)),
                            object=SimpleNamespace(select_all=lambda **kw: None)),
        context=SimpleNamespace(view_layer=SimpleNamespace(objects=SimpleNamespace(active=None))),
        data=SimpleNamespace(materials=SimpleNamespace(new=lambda name: SimpleNamespace(use_nodes=False)))))
    def object_from_builder(builder, materials):
        exported.append((builder, materials))
        return SimpleNamespace(select_set=lambda value: None)
    monkeypatch.setattr(exporter, 'mesh_object', object_from_builder)
    def glb(destination, *, options):
        assert options == dict(export_apply=True, export_image_format='NONE')
        mesh = exported[-1][0]
        # Only Blender's serialization is stubbed; execute the production metadata
        # readback and library validation against a real GLB container.
        document = dict(meshes=[{'primitives': [{'indices': 0, 'attributes': {'POSITION': 1}}]}],
            accessors=[{'count': 3}, {'min': [0, 1, 2], 'max': [3, 4, 5]}],
            materials=[{'name': 'BC_' + slot} for slot in sorted(set(mesh.mats))])
        destination.write_bytes(glb_pack(document, b''))
    monkeypatch.setattr(exporter, 'export_atomic_glb', glb)
    folder = tmp_path / 'library' / definition.stem
    exporter.main(definition, folder)
    monkeypatch.setattr(lib, 'definitions', lambda: [definition])
    model = lib.load(folder.parent)['bloom_0']
    assert calls == [{'use_empty': True}]
    assert len(exported) == 1 and exported[0][0].name == lib.name('bloom_0')
    assert model['bounds_m'] == [[0, -5, 1], [3, -2, 4]]
    assert model['triangles'] == 1 and model['slots'] == sorted(exported[0][1])
