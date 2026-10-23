"""Carriage service source boundaries preserve exact local node data before serialization."""
import copy
import importlib.util
import json
from pathlib import Path
import struct
import sys
from types import ModuleType

import pytest

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'world'))
from train import carriage_mesh as M, carriage_source as S  # noqa: E402


def fixture():
    positions = struct.pack('<9f', 0, 0, 0, 1, 0, 0, 0, 1, 0)
    normals = struct.pack('<9f', 0, 0, 1, 0, 0, 1, 0, 0, 1)
    indices = struct.pack('<3H', 0, 1, 2)
    binary = positions + normals + indices
    doc = dict(asset=dict(version='2.0'), scene=0, scenes=[dict(name='Scene', nodes=[0])],
        nodes=[dict(name='Vehicle', children=[1, 2], extras=dict(frame='original')),
               dict(name='Body', mesh=0), dict(name='Door_hinge', translation=[10, 0, 0], children=[3]),
               dict(name='Door_glass', mesh=0, extras=dict(pivot='local'))],
        materials=[dict(name='M_BT_Steel', pbrMetallicRoughness=dict(metallicFactor=1))],
        meshes=[dict(name='Linked', primitives=[dict(attributes=dict(POSITION=0, NORMAL=1), indices=2, material=0)])],
        accessors=[dict(bufferView=0, componentType=5126, count=3, type='VEC3'),
                   dict(bufferView=1, componentType=5126, count=3, type='VEC3'),
                   dict(bufferView=2, componentType=5123, count=3, type='SCALAR')],
        bufferViews=[dict(buffer=0, byteOffset=0, byteLength=36), dict(buffer=0, byteOffset=36, byteLength=36),
                     dict(buffer=0, byteOffset=72, byteLength=6)], buffers=[dict(byteLength=len(binary))])
    return doc, binary


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_every_linked_instance_counts_and_original_local_frame_drives_bounds():
    doc, binary = fixture()
    info = M.geometry(doc, binary)
    assert info == dict(triangles=2, bounds=[[0., 0., 0.], [11., 1., 0.]], slots=['M_BT_Steel'])
    doc['nodes'][0]['children'].append(1)
    with pytest.raises(ValueError, match='repeated'): M.geometry(doc, binary)


def test_raw_source_packet_precedes_any_glb_serialization_and_is_deterministic():
    doc, binary = fixture()
    source = S.encode('SM_BT_Test_LOD0', doc, binary)
    assert source == S.encode('SM_BT_Test_LOD0', doc, binary)
    assert not source.startswith(b'glTF')
    value, actual = S.decode(source, key='SM_BT_Test_LOD0')
    assert value['document'] == doc and actual == binary
    with pytest.raises(ValueError, match='changed'): S.decode(source[:-1] + bytes([source[-1] ^ 1]))


def test_body_and_leaf_subsets_retain_only_consumed_nodes_materials_and_buffers():
    doc, binary = fixture()
    body, door = S.subsets(doc, binary, mesh='SM_BT_Test', level=0, leaves={'Door_hinge': 'SM_BTD_Test_hinge'})
    assert body[0] == 'SM_BT_Test_LOD0' and door[0] == 'SM_BTD_Test_hinge'
    assert [n['name'] for n in body[1]['nodes']] == ['Vehicle', 'Body']
    assert [n['name'] for n in door[1]['nodes']] == ['Vehicle', 'Door_hinge', 'Door_glass']
    assert door[1]['nodes'][1]['translation'] == [10, 0, 0]
    assert door[1]['nodes'][2]['extras'] == dict(pivot='local')
    before = S.encode(door[0], door[1], door[2])
    changed = copy.deepcopy(doc)
    changed['materials'].append(dict(name='Unconsumed sibling'))
    changed['meshes'].append(copy.deepcopy(changed['meshes'][0]))
    changed['meshes'][1]['primitives'][0]['material'] = 1
    changed['nodes'][1]['mesh'] = 1
    _, revised = S.subsets(changed, binary, mesh='SM_BT_Test', level=0, leaves={'Door_hinge': 'SM_BTD_Test_hinge'})
    assert S.encode(revised[0], revised[1], revised[2]) == before
    assert S.subsets(doc, binary, mesh='SM_BT_Test', level=2, leaves={}) == [('SM_BT_Test_LOD2', doc, binary)]


@pytest.mark.parametrize('change', [
    lambda d: d['accessors'][0].update(sparse={}),
    lambda d: d['nodes'][0].update(children=[0]),
    lambda d: d['meshes'][0]['primitives'][0].update(targets=[]),
    lambda d: d['accessors'][2].update(count=300000),
    lambda d: d['nodes'][2].update(scale=[0, 1, 1]),
    lambda d: d.update(images=[dict(uri='external.png')]),
])
def test_incomplete_or_unsupported_node_corner_and_texture_policy_refuses(change):
    doc, binary = fixture(); change(doc)
    with pytest.raises(ValueError): M.geometry(doc, binary)


def test_instance_budget_cannot_be_hidden_by_shared_mesh_data():
    doc, binary = fixture()
    doc['nodes'] = [dict(name='Root', children=list(range(1, 32770)))] + [dict(mesh=0) for _ in range(32769)]
    with pytest.raises(ValueError, match='oversized'): S.encode('SM_BT_TooBig_LOD0', doc, binary)


def test_selected_plan_and_export_preserve_current_runtime_subset_bytes(tmp_path):
    from atelier.export_manifest import validate
    doc, binary = fixture()
    original = tmp_path / 'original.glb'; S.G.write(original, doc, binary)
    source = tmp_path / 'SM_BT_Test_LOD0.source'; source.write_bytes(S.encode(source.stem, doc, binary))
    plan = tmp_path / 'plan'
    load('carriage_plan_test', GAME / 'world/train/plan_carriage.py').main([
        '--source', str(source), '--asset', source.stem, '--output', str(plan)])
    value = json.loads((plan / 'plan.json').read_text())
    assert value['source_triangles'] == 2 and len(value['pieces']) == 1
    product = tmp_path / 'product'
    load('carriage_export_test', GAME / 'world/train/export_carriage.py').main([
        '--input', str(plan / (source.stem + '.glbdata')), '--output', str(product), '--format', '.glb'])
    assert (product / (source.stem + '.glb')).read_bytes() == original.read_bytes()
    assert validate(product, key=source.stem)['triangles'] == 2


def _fake_save_gltf():
    sort_order = ['asset', 'scene', 'scenes', 'nodes', 'materials', 'meshes', 'accessors', 'bufferViews', 'buffers']
    return sort_order


def test_source_writer_restores_original_on_success_and_failure(monkeypatch):
    names = ['io_scene_gltf2', 'io_scene_gltf2.blender', 'io_scene_gltf2.blender.exp',
             'io_scene_gltf2.blender.exp.export', 'io_scene_gltf2.io', 'io_scene_gltf2.io.exp',
             'io_scene_gltf2.io.exp.export', 'io_scene_gltf2.blender.com', 'io_scene_gltf2.blender.com.json_util']
    modules = {name: ModuleType(name) for name in names}
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
        parent, _, child = name.rpartition('.')
        if parent in modules: setattr(modules[parent], child, module)
    exporter = modules['io_scene_gltf2.blender.exp.export']
    def original(json, buffer, export_settings): pytest.fail('combined GLB serialized')
    exporter.__write_file = original
    writer = modules['io_scene_gltf2.io.exp.export']
    writer.save_gltf = _fake_save_gltf
    exporter.__file__ = writer.__file__ = __file__
    import hashlib
    expected = {key: hashlib.sha256(Path(__file__).read_bytes()).hexdigest() for key in ('exporter', 'writer')}
    modules['io_scene_gltf2.blender.com.json_util'].BlenderJSONEncoder = json.JSONEncoder
    doc, binary = fixture(); received = []
    with S.capture_writer(lambda d, b, p: received.append((d, b, p)), expected=expected):
        exporter.__write_file(doc, binary, dict(gltf_format='GLB', gltf_filepath='SM_BT_Test_LOD0.glb'))
    assert exporter.__write_file is original and received[0][:2] == (doc, binary)
    with pytest.raises(RuntimeError):
        with S.capture_writer(lambda *args: None, expected=expected): raise RuntimeError('constructor failure')
    assert exporter.__write_file is original

    with pytest.raises(ValueError, match='prepared identity'):
        with S.capture_writer(lambda *args: pytest.fail('unbound addon accepted'),
                              expected=dict(expected, exporter='0' * 64)):
            pytest.fail('unbound addon accepted')
    assert exporter.__write_file is original


def test_actual_atlas_fixture_requires_unchanged_constructor_prefix_and_helpers(tmp_path):
    control = load('carriage_immutable_prefix_test', GAME / 'tools/train_carriage_source_control.py')
    original = tmp_path / 'original.py'; current = tmp_path / 'current.py'
    original.write_text('def helper():\n    return 7\ndef build(coach, images):\n    data = helper()\n    files = {}\n    return data\n')
    current.write_text('def helper():\n    return 7\ndef runtime_placements(coach):\n    return {}\n'
        'def build(coach, images, *, source_sink=None):\n    data = helper()\n'
        '    if source_sink is not None:\n        return source_sink(data)\n    files = {}\n    return data\n')
    control.same_original_constructor_prefix(original, current)
    text = current.read_text(); current.write_text(text.replace('data = helper()', 'data = 99'))
    with pytest.raises(ValueError, match='constructor source changed'):
        control.same_original_constructor_prefix(original, current)
    current.write_text(text.replace('return 7', 'return 8'))
    with pytest.raises(ValueError, match='helper source changed'):
        control.same_original_constructor_prefix(original, current)


def test_all_seven_projected_layouts_and_access_queries_keep_collision_and_boarding(monkeypatch):
    from train import carriage_request as R, construct_carriage as C, collision as CO, layout as L
    original_access = CO.A
    import train
    monkeypatch.setitem(sys.modules, 'train.access', original_access)
    monkeypatch.setattr(train, 'access', original_access)
    for coach, builder in R.BUILDERS.items():
        value = R.request(coach)
        current = C.decode(value['layout'], L); original = builder()
        assert current == original
        expected = (CO.named_boxes(original, 'Mesh'), CO.doors(original), CO.boarding(original))
        queries = C.install_access(value['access'], L)
        with monkeypatch.context() as context:
            context.setattr(CO, 'A', queries)
            assert (CO.named_boxes(current, 'Mesh'), CO.doors(current), CO.boarding(current)) == expected
        assert all(pair[0] == coach for pair in queries.locked_gangways())
        assert queries.players() == original_access.players()
        assert queries.tallest() == original_access.tallest()
    sys.modules['train.access'] = original_access
    train.access = original_access


def test_coach_layout_projection_has_complete_types_and_no_sibling_roster():
    from train import carriage_request as R, construct_carriage as C, layout as L
    value = R.request('restaurant')
    assert set(value) == {'schema', 'coach', 'layout', 'access'}
    actual = C.decode(value['layout'], L)
    assert isinstance(actual.body.bogies, tuple)
    assert isinstance(actual.rooms, list) and isinstance(actual.rooms[0], L.Room)
    broken = copy.deepcopy(value['layout']); broken['fields'].pop('body')
    with pytest.raises(ValueError, match='Incomplete'): C.decode(broken, L)
    broken = copy.deepcopy(value['layout']); broken['type'] = 'foreign'
    with pytest.raises(ValueError, match='Foreign'): C.decode(broken, L)


def ready_fixture(tmp_path):
    from atelier import export_assembly
    from atelier.atomic_files import atomic_json
    from atelier.export_manifest import publish_receipt, sha
    root = tmp_path / 'train'; root.mkdir()
    doc, binary = fixture()
    pieces = S.subsets(doc, binary, mesh='SM_BT_Test', level=0, leaves={'Door_hinge': 'SM_BTD_Test_hinge'})
    body = pieces[0][1:]; door = pieces[1][1:]
    members = [(f'SM_BT_Test_LOD{k}', body) for k in (0, 1, 2)] + [('SM_BTD_Test_hinge', door)]
    items = []; receipts = {}
    for key, (scene, data) in members:
        product = tmp_path / 'exports' / key; product.mkdir(parents=True)
        path = product / (key + '.glb'); path.write_bytes(M.glb(scene, data)); info = M.geometry(scene, data)
        receipts[key] = publish_receipt(product, key=key, primary=path.name, triangles=info['triangles'], bounds=info['bounds'],
            metadata=dict(slots=info['slots'], geometry_sha256=sha(path)))
        items.append(export_assembly.Item(key, product))
    export_assembly.assemble(items, root / 'atomic')
    coach = root / 'test'; coach.mkdir(); placements = coach / 'test-placements.json'; placements.write_text('{}')
    levels = []
    for k in (0, 1, 2):
        key = f'SM_BT_Test_LOD{k}'; source = root / 'atomic' / (key + '.glb')
        (coach / source.name).write_bytes(source.read_bytes()); levels.append(dict(path='test/' + source.name, sha256=sha(source)))
    library = root / 'service-meshes.json'
    atomic_json(library, dict(schema=1, complete=True, atomic_manifest_sha256=sha(root / 'atomic/manifest.json'),
        coaches=dict(test=dict(mesh='SM_BT_Test', levels=levels, placements_sha256=sha(placements),
            doors=dict(Door_hinge=dict(asset='SM_BTD_Test_hinge', path='atomic/SM_BTD_Test_hinge.glb',
                                      sha256=sha(root / 'atomic/SM_BTD_Test_hinge.glb')))))))
    train = dict(vehicles=[dict(id='test', name='SM_BT_Test', doors=[dict(leaves=[dict(node='Door_hinge',
        mesh='/Game/BelmonteTrain/Doors/SM_BTD_Test_hinge.SM_BTD_Test_hinge', pivot=[1000, 0, 0], motion='hinged', yaw=90)])])])
    return root, library, train


def test_service_copies_bounded_bodies_and_doors_without_geometry_rediscovery(tmp_path, monkeypatch):
    from train.service_meshes import copy_to_service
    root, library, train = ready_fixture(tmp_path)
    with monkeypatch.context() as context:
        context.setattr(S.G, 'keep', lambda *args, **kwargs: pytest.fail('file assembly reconstructed geometry'))
        copy_to_service(root, train, root / 'service/glb', library)
    vehicle = train['vehicles'][0]; leaf = vehicle['doors'][0]['leaves'][0]
    assert vehicle['levels'] == ['service/glb/SM_BT_Test_LOD0.glb', 'service/glb/SM_BT_Test_LOD1.glb', 'test/SM_BT_Test_LOD2.glb']
    assert leaf['glb'] == 'service/glb/doors/SM_BTD_Test_hinge.glb'
    assert leaf['pivot'] == [1000, 0, 0] and leaf['yaw'] == 90
    for path in vehicle['levels'] + [leaf['glb']]:
        assert (root / path).read_bytes() == (root / 'atomic' / Path(path).name).read_bytes()
    files = [root / path for path in vehicle['levels'] + [leaf['glb']]]
    mtimes = {path: path.stat().st_mtime_ns for path in files}
    copy_to_service(root, train, root / 'service/glb', library)
    assert {path: path.stat().st_mtime_ns for path in files} == mtimes


@pytest.mark.parametrize('failure', ['source', 'missing_door', 'foreign_destination'])
def test_service_rejects_stale_or_incomplete_libraries_before_any_write(tmp_path, failure):
    from train.service_meshes import copy_to_service
    root, library, train = ready_fixture(tmp_path); destination = root / 'service/glb'
    if failure == 'source': (root / 'test/SM_BT_Test_LOD1.glb').write_bytes(b'changed')
    elif failure == 'missing_door': train['vehicles'][0]['doors'][0]['leaves'][0]['node'] = 'missing'
    else:
        destination.mkdir(parents=True); (destination / 'foreign.txt').write_text('foreign')
    with pytest.raises(ValueError): copy_to_service(root, train, destination, library)
    assert not (destination / 'SM_BT_Test_LOD0.glb').exists()


def test_cold_normal_graph_declares_all_seven_source_owners_without_installed_blender(tmp_path, monkeypatch):
    from atelier import engine
    from atelier.build_products import Graph
    from types import SimpleNamespace
    recipe = load('carriage_cold_graph_test', GAME / 'train_carriage_build.py')
    monkeypatch.setattr(engine, 'blender', lambda: str(tmp_path / 'missing/Blender.app/Contents/MacOS/Blender'))
    steps = recipe.steps(SimpleNamespace(out=tmp_path)); by_name = {step.name: step for step in steps}
    assert len(steps) == 16
    Graph(steps).select(['world.belmonte_train'])
    for coach in recipe.COACHES:
        request = by_name['world.belmonte_train.request.' + coach]
        source = by_name['world.belmonte_train.source.' + coach]
        assert request.cache and request.optional_inputs
        assert source.cache and source.replan and len(source.products) == 1
        command, = source.commands
        assert command.factory_startup and command.threads == 3
        assert command.args[:2] == ('--request', str(tmp_path / 'belmonte-train-requests' / (coach + '.json')))
        assert not {'access.py', 'consist.py', 'definition.py'}.intersection(path.name for path in source.inputs)
        # The original atlas key genuinely reads these exact source files.
        assert {'build.py', 'layout.py', 'parts.py', 'fittings.py', 'textures.py'} <= {path.name for path in source.inputs}


def test_selected_carriage_plan_key_uses_own_packet_without_sibling_source_identity(tmp_path):
    from atelier import build
    from types import SimpleNamespace
    recipe = load('carriage_selected_graph_test', GAME / 'train_carriage_build.py')
    folder = tmp_path / 'belmonte-train-sources/restaurant/packets'; folder.mkdir(parents=True)
    key = 'SM_BT_Restaurant_LOD0'; packet = folder / (key + '.source')
    doc, binary = fixture(); packet.write_bytes(S.encode(key, doc, binary))
    (folder / 'inventory.json').write_text(json.dumps(dict(schema=1, coach='restaurant', complete=True,
        pieces=[dict(name=key, source=packet.name)])))
    steps = {step.name: step for step in recipe.steps(SimpleNamespace(out=tmp_path))}
    planner = steps['world.belmonte_train.geometry.' + key]
    assert planner.cache and planner.reads == [] and planner.references == ['belmonte_train.source.restaurant']
    assert packet in planner.inputs and folder / 'inventory.json' not in planner.inputs
    before = build.fingerprint(planner, {'product:belmonte_train.source.restaurant': 'parent-before'})
    (folder / 'sibling.source').write_bytes(b'unrelated current sibling')
    assert build.fingerprint(planner, {'product:belmonte_train.source.restaurant': 'parent-after'}) == before
    packet.write_bytes(S.encode(key, dict(doc, extras=dict(actual_selected_edit=True)), binary))
    assert build.fingerprint(planner, {'product:belmonte_train.source.restaurant': 'parent-after'}) != before
    export = steps['world.belmonte_train.export.' + key]
    assert export.cache and len(export.products) == 1 and export.commands[0].script.name == 'export_carriage.py'


def full_source_fixture(tmp_path, monkeypatch):
    import hashlib
    from PIL import Image
    from atelier.atomic_files import atomic_json
    from atelier.export_manifest import publish_receipt
    products = load('all_coach_files_fixture', GAME / 'train_carriage_products.py')
    monkeypatch.setattr(products.T, 'ALL', {'Tiny': None})
    monkeypatch.setattr(products.T, 'JPEG', set())
    fitted = {'tiny.glb': b'unit fixture fitted source', 'tiny.json': b'{"fixture":true}'}
    monkeypatch.setattr(products, 'fitted_sources', lambda: {key: hashlib.sha256(data).hexdigest() for key, data in fitted.items()})
    image = tmp_path / 'tiny.png'; Image.new('RGB', (8, 8), (4, 5, 6)).save(image); image_data = image.read_bytes()
    doc, binary = fixture()
    policies = dict(version=1, frame='original frame', envelope=dict(width=3.6), coupling=dict(gap=0), human_gauges={})
    for coach in products.COACHES:
        title = ''.join(part.title() for part in coach.split('-')); mesh = 'SM_BT_' + title
        folder = tmp_path / 'belmonte-train-sources' / coach; packets = folder / 'packets'; packets.mkdir(parents=True)
        node = 'Door_hinge'; door_key = 'SM_BTD_' + title + '_hinge'
        parts = S.subsets(doc, binary, mesh=mesh, level=0, leaves={node: door_key})
        body = parts[0][1:]; door = parts[1][1:]
        members = [(mesh + '_LOD0', body), (mesh + '_LOD1', body), (mesh + '_LOD2', (doc, binary)), (door_key, door)]
        rows = []
        for key, (scene, data) in members:
            rows.append(S.write(packets, key, scene, data))
            product = tmp_path / 'exports/world.belmonte_train.export' / key; product.mkdir(parents=True)
            path = product / (key + '.glb'); path.write_bytes(M.glb(scene, data)); observed = M.geometry(scene, data)
            publish_receipt(product, key=key, primary=path.name, triangles=observed['triangles'], bounds=observed['bounds'],
                metadata=dict(slots=observed['slots'], geometry_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        info = dict(title=coach, mesh=mesh, triangles=dict(LOD0=2, LOD1=2, LOD2=2), layout_checks=[], mesh_checks={})
        atomic_json(packets / 'info.json', info)
        atomic_json(packets / 'placements.json', dict(windows=[], doors=[dict(leaves=[dict(name=node)])]))
        atomic_json(packets / 'inventory.json', dict(schema=1, complete=True, coach=coach, mesh=mesh,
            pieces=rows, doors={node: door_key}, original_triangles=info['triangles'], policies=policies))
        (folder / 'textures').mkdir(); (folder / 'textures/Tiny.png').write_bytes(image_data)
        fit_root = folder / 'authoring/furniture'; fit_root.mkdir(parents=True)
        for key, data in fitted.items(): (fit_root / key).write_bytes(data)
        files = {path.relative_to(folder).as_posix(): dict(bytes=path.stat().st_size,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for path in folder.rglob('*') if path.is_file()}
        atomic_json(folder / 'source.json', dict(schema=1, coach=coach, complete=True, files=files, info=info))
    return products


def test_all_seven_file_assembly_preserves_policies_bytes_and_retires_owned_legacy_files(tmp_path, monkeypatch):
    products = full_source_fixture(tmp_path, monkeypatch)
    manifest = products.assemble(tmp_path)
    root = tmp_path / 'belmonte-train'
    assert set(manifest['coaches']) == set(products.COACHES) and manifest['frame'] == 'original frame'
    ready = json.loads((root / 'service-meshes.json').read_text())
    assert ready['complete'] and set(ready['coaches']) == set(products.COACHES)
    for coach, spec in ready['coaches'].items():
        for level in spec['levels']:
            assert (root / level['path']).read_bytes() == (root / 'atomic' / Path(level['path']).name).read_bytes()
    old = root / 'restaurant/old-authoring.blend'; old.write_bytes(b'previously owned diagnostic source')
    manifest['coaches']['restaurant']['files'][old.name] = dict(bytes=old.stat().st_size, sha256=products.sha(old))
    (root / 'manifest.json').write_text(json.dumps(manifest))
    native_lod = root / 'restaurant/SM_BT_Restaurant_LOD0.glb'; before = native_lod.stat().st_mtime_ns
    products.assemble(tmp_path)
    assert not old.exists() and native_lod.stat().st_mtime_ns == before


def test_all_seven_assembly_refuses_foreign_members_before_any_copy(tmp_path, monkeypatch):
    products = full_source_fixture(tmp_path, monkeypatch)
    products.assemble(tmp_path)
    foreign = tmp_path / 'belmonte-train/first-class/unowned.txt'; foreign.write_text('foreign')
    monkeypatch.setattr(products, 'copy', lambda *args: pytest.fail('assembly wrote before complete preflight'))
    with pytest.raises(ValueError, match='Foreign'): products.assemble(tmp_path)
    assert foreign.read_text() == 'foreign'


@pytest.mark.parametrize('field', ['position', 'uv', 'material'])
def test_same_count_current_carriage_packet_refuses_old_export_before_publication(tmp_path, monkeypatch, field):
    import hashlib
    products = full_source_fixture(tmp_path, monkeypatch)
    products.assemble(tmp_path)
    root = tmp_path / 'belmonte-train'
    before = {p.relative_to(root): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
    folder = tmp_path / 'belmonte-train-sources/locomotive'
    inventory_path = folder / 'packets/inventory.json'
    inventory = json.loads(inventory_path.read_text()); row = inventory['pieces'][0]
    packet_path = folder / 'packets' / row['source']
    packet, binary = S.read(packet_path, key=row['name']); doc = packet['document']
    if field == 'position':
        binary = struct.pack('<f', 0.5) + binary[4:]
    elif field == 'uv':
        offset = len(binary) + (-len(binary) % 4); binary += b'\0' * (-len(binary) % 4)
        doc['bufferViews'].append(dict(buffer=0, byteOffset=offset, byteLength=24))
        doc['accessors'].append(dict(bufferView=len(doc['bufferViews']) - 1, componentType=5126, count=3, type='VEC2'))
        doc['meshes'][0]['primitives'][0]['attributes']['TEXCOORD_0'] = len(doc['accessors']) - 1
        binary += struct.pack('<6f', .25, 0, 1, 0, 0, 1); doc['buffers'][0]['byteLength'] = len(binary)
    else:
        doc['materials'][0]['pbrMetallicRoughness']['metallicFactor'] = 0.5
    packet_path.write_bytes(S.encode(row['name'], doc, binary))
    assert S.read(packet_path)[0]['triangles'] == row['triangles']
    row['sha256'] = hashlib.sha256(packet_path.read_bytes()).hexdigest()
    inventory_path.write_text(json.dumps(inventory))
    source_path = folder / 'source.json'; source = json.loads(source_path.read_text())
    for path in (packet_path, inventory_path):
        source['files'][path.relative_to(folder).as_posix()] = dict(bytes=path.stat().st_size, sha256=products.sha(path))
    source_path.write_text(json.dumps(source))
    # The complete new source is internally valid; only its old export is stale.
    products.source(folder, 'locomotive')
    monkeypatch.setattr(products.export_assembly, 'assemble', lambda *a: pytest.fail('published before source binding'))
    monkeypatch.setattr(products, 'copy', lambda *a: pytest.fail('copied before source binding'))
    with pytest.raises(ValueError, match='export differs from current source packet'): products.assemble(tmp_path)
    assert {p.relative_to(root): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()} == before


def test_carriage_assembly_declares_actual_packet_encoder_closure(tmp_path):
    from types import SimpleNamespace
    recipe = load('carriage_assembly_encoder_recipe', GAME / 'train_carriage_build.py')
    step = next(s for s in recipe.steps(SimpleNamespace(out=tmp_path)) if s.name == 'world.belmonte_train')
    assert GAME / 'world/train/carriage_mesh.py' in step.inputs
    assert GAME / 'world/train/carriage_source.py' in step.inputs
    assert any(path.name == 'gltf_partition.py' for path in step.inputs)
