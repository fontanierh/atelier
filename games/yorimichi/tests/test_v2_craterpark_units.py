"""Cold CraterPark declarations and selected source refusal; no native launch."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import numpy as np
import pytest
from atelier.build_v2.recipe_dependencies import extract
from atelier.build_v2.recipe_job import pack_root

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path[:0] = [str(GAME), str(GAME / 'world'), str(GAME / 'world/regions')]
import v2_craterpark_units as units  # noqa: E402
import craterpark_members_v2 as members  # noqa: E402
import craterpark_finish_v2 as body  # noqa: E402


def load(path, label):
    spec = importlib.util.spec_from_file_location(label, ROOT / path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def rows():
    build = load('games/yorimichi/build.py', 'craterpark_build_test')
    ctx = NS(game='yorimichi', out=ROOT / 'build/yorimichi', uproject=None)
    steps = [s for s in build.world_steps(ctx) + build.unreal_steps(ctx) if 'craterpark' in s.name]
    names = {s.name for s in steps}; products = {p.name for s in steps for p in s.products}
    for step in steps:
        step.reads = [r for r in step.reads if r in products]
        step.needs = [n for n in step.needs if n in names]
        step.after = [n for n in step.after if n in names]
    return extract(steps, checkout=ROOT, build_root=ROOT / 'build')


@pytest.fixture(scope='module')
def declared(rows):
    return units.attach_followers({'templates': [], 'groups': {}}, rows=rows, checkout=ROOT)


def test_actual_cold_rows_declare_complete_native_and_source_seams(declared):
    assert len(declared['templates']) == 4
    assert len(declared['groups']) == 4
    assert declared['source_join']['required'] is True
    assert set(declared['source_join']['selected_exports']) == {'render', 'collision', 'seed'}
    assert 'world.craterpark' not in declared['aliases']
    assert all(u['outputs'][0]['id'] == 'archive' for u in declared['units'] if u.get('output_groups'))
    assert all(o['kind'] == 'tree' for t in declared['templates'] for o in t['params']['recipe']['outputs'])
    parents = [u for u in declared['units'] if '.parent.' in u['id']]
    assert len(parents) == 5
    instances = [u for u in declared['units'] if '.material.' in u['id']]
    assert len(instances) == len(json.loads((ROOT / units.CATALOGUE).read_bytes())) + 1
    assert all(u['outputs'][0]['class'] == 'MaterialInstance' for u in instances)
    assert all(units.ORIGINAL in u['code'] for u in parents + instances)
    for unit in instances:
        if not unit['params']['args']['coping']:
            assert declared['staged_inputs'][unit['id']]['catalogue'] == 'inputs/catalogue/materials.json'
    seed = next(t for t in declared['templates'] if t['producer'].endswith('.seed'))
    assert seed['followers'] == []
    render = next(t for t in declared['templates'] if t['producer'].endswith('.render'))
    raw, finish = [f['unit'] for f in render['followers']]
    assert raw['inputs'][0]['source'] == {'kind': 'item', 'unit': '$export', 'item': 'asset'}
    assert finish['inputs'][0]['source'] == {'kind': 'item', 'unit': '$previous', 'item': 'raw'}
    assert finish['params']['args']['materials']['coping_steel'].startswith('material')
    assert {o['id'] for o in finish['outputs']} == {'asset', 'geometry', 'report'}
    for output in finish['outputs'][:1]:
        assert len(output['files']) == 6
        assert all('install_path' in f for f in output['files'])


@pytest.mark.parametrize('change', ['source', 'restyle', 'library', 'importer'])
def test_refuse_changed_original_ownership(rows, change):
    changed = deepcopy(rows)
    by_id = {r['id']: r for r in changed}
    if change == 'source': by_id['world.craterpark.inputs']['products'][0]['paths'] = ['somewhere']
    if change == 'restyle': by_id['world.craterpark_restyle']['outputs'] = ['build/yorimichi/craterpark/textures/textures.json']
    if change == 'library': by_id['world.craterpark']['products'][0]['paths'].pop()
    if change == 'importer': by_id['unreal.craterpark']['commands'][0]['script']['path'] = 'other.py'
    with pytest.raises(units.Unsupported):
        units.attach_followers({}, rows=changed, checkout=ROOT)


def source_archive(tmp_path, *, mutation=None):
    root = tmp_path / 'source'; root.mkdir()
    assets = []
    for name, kind in [('SM_CP_Test', 'render'), ('UC_CP_Test', 'collision'), ('SM_CP_ImportSeed', 'seed')]:
        path = root / (name + '.npz')
        np.savez(path, spec=np.asarray(json.dumps({'name': name, 'kind': kind})))
        assets.append({'name': name, 'kind': kind, 'packet': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    (root / 'metadata.npz').write_bytes(b'opaque assembler-owned metadata')
    report = {'schema': 1, 'complete': True, 'assets': assets}
    if mutation: mutation(root, report)
    (root / 'inputs.json').write_text(json.dumps(report))
    archive = tmp_path / 'source.tree.tar'
    pack_root(root, archive)
    return archive


def test_selected_packet_members_keep_exact_bytes_and_seed(tmp_path):
    archive = source_archive(tmp_path)
    for kind, expected in [('render', 'SM_CP_Test.npz'), ('collision', 'UC_CP_Test.npz'), ('seed', 'SM_CP_ImportSeed.npz')]:
        destination = tmp_path / kind
        members.project(archive, destination, kind)
        assert [p.name for p in destination.iterdir()] == [expected]
        assert (destination / expected).read_bytes() == (tmp_path / 'source' / expected).read_bytes()


@pytest.mark.parametrize('mutation', [
    lambda root, report: (root / 'SM_CP_Test.npz').write_bytes(b'changed'),
    lambda root, report: (root / 'unexpected').write_bytes(b'extra'),
    lambda root, report: report['assets'].append(dict(report['assets'][0])),
    lambda root, report: report.update(complete=False),
])
def test_incomplete_foreign_or_changed_source_refuses(tmp_path, mutation):
    archive = source_archive(tmp_path, mutation=mutation)
    with pytest.raises(ValueError):
        members.project(archive, tmp_path / 'selected', 'render')


def test_linked_root_and_selected_texture_refuse(tmp_path):
    target = tmp_path / 'archive'; target.write_bytes(b'not archive')
    alias = tmp_path / 'alias'; alias.symlink_to(target)
    with pytest.raises(ValueError, match='archive'):
        members.project(alias, tmp_path / 'selected', 'render')
    source = tmp_path / 'textures'; source.mkdir(); (source / 'texture.png').symlink_to(target)
    with pytest.raises(ValueError):
        members.select_texture(source, tmp_path / 'owned', 'texture')


@pytest.mark.parametrize('finish,painted,aligned,expected', [
    (None, False, False, 'Flat'), (None, False, True, 'World'), (None, True, True, 'Textured'),
    ('lacquer', True, False, 'Lacquer'), ('lacquer', False, True, 'World'), ('metal', True, False, 'Steel')])
def test_original_material_precedence(finish, painted, aligned, expected):
    spec = {'id': 'material_024', 'texture': 'source', 'finish': finish}
    paint = {'png': 'paint.png', 'sha256': 'a' * 64}
    world = {'png': 'world.png', 'sha256': 'b' * 64, 'metres': 8.}
    kind, entry, actual_aligned = body.material_policy(spec, {'textures': {'source': paint} if painted else {},
        'world_aligned': {'material_024': world} if aligned else {}})
    assert kind == expected
    assert entry == (paint if painted else world if aligned else None)
    assert actual_aligned == (world if aligned else None)


class Props:
    def __init__(self, **values): self.values = values
    def get_editor_property(self, name): return self.values[name]
    def set_editor_property(self, name, value): self.values[name] = value


class Asset:
    def __init__(self, path): self.path = path
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[-1]


class Mesh(Asset):
    def __init__(self, path, slot):
        super().__init__(path)
        self.triangles, self.lods, self.uvs, self.simple, self.convex = 1, 1, 1, 0, 0
        self.static_materials = [Props(imported_material_slot_name=slot)]
        self.settings = Props(use_full_precision_u_vs=False, remove_degenerates=True, distance_field_resolution_scale=1.)
        self.body = Props(collision_trace_flag='default', double_sided_geometry=False)
        self.allow_cpu_access = True
        self.high = 100.
    def get_num_lods(self): return self.lods
    def get_num_triangles(self, index): return self.triangles
    def get_material(self, index): return self.static_materials[index].values.get('material_interface')
    def get_editor_property(self, name): return self.body if name == 'body_setup' else getattr(self, name)
    def set_editor_property(self, name, value): setattr(self, name, value)
    def get_bounding_box(self): return NS(min=NS(x=0., y=-100., z=0.), max=NS(x=self.high, y=0., z=0.))


@pytest.fixture
def native_case(tmp_path, monkeypatch):
    from atelier import mesh_ir
    from atelier.export_manifest import publish_receipt
    piece = 'SM_CP_Test'
    source, payload, metadata = [tmp_path / name for name in ('source', 'payload', 'metadata')]
    for path in (source, payload, metadata): path.mkdir()
    packet = mesh_ir.encode(dict(positions=[[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]], faces=[[0, 1, 2]],
        normals=[[0., 0., 1.]] * 3, materials=[0], smooth=[False],
        uvs=[('UVMap', [[0., 0.], [1., 0.], [0., 1.]])], colours=[]), key=piece,
        slots=['material_024'], matrix=np.eye(4).tolist(), options={}, collisions=[])
    (payload / (piece + '.npz')).write_bytes(packet); (source / (piece + '.fbx')).write_bytes(b'fbx')
    publish_receipt(source, key=piece, primary=piece + '.fbx', triangles=1, bounds=[[0, 0, 0], [1, 1, 0]],
        metadata={'geometry_sha256': hashlib.sha256(packet).hexdigest(), 'uv_channels': ['UVMap']})
    (metadata / (piece + '.json')).write_text(json.dumps({'schema': 1, 'entry': {'name': piece, 'native_origin': [10., 20., 30.]}}))
    raw = '/Game/_Raw/CraterPark/Meshes/' + piece; dest = units.ROOT + '/Meshes/' + piece
    material = units.ROOT + '/Materials/MI_CP_material_024'
    assets = {raw: Mesh(raw, 'material_024'), material: Asset(material)}
    state = NS(assets=assets, checks=0, saves=0, mutate=False)
    def duplicate(source, target):
        value = deepcopy(assets[source]); value.path = target; assets[target] = value; return value
    def save(value):
        state.saves += 1
        if state.mutate: value.uvs = 2
        return True
    def validate(mesh, triangles, authored):
        assert mesh is not assets[raw] and triangles == 1 and authored is False
        state.checks += 1
        return True
    def dump(mesh, origin, path):
        Path(path).parent.mkdir(parents=True)
        np.asarray([[[1000., 3000., 2000.], [1100., 3000., 2000.], [1000., 2900., 2000.]]], dtype='<f8').tofile(path)
        return True
    editor = NS(get_lod_build_settings=lambda mesh, i: mesh.settings,
        set_lod_build_settings=lambda mesh, i, settings: setattr(mesh, 'settings', settings),
        get_num_uv_channels=lambda mesh, i: mesh.uvs, get_simple_collision_count=lambda mesh: mesh.simple,
        get_convex_collision_count=lambda mesh: mesh.convex)
    unreal = NS(StaticMesh=Mesh, MaterialInterface=Asset, load_module=lambda _: None, StaticMeshEditorSubsystem='editor',
        get_editor_subsystem=lambda _: editor, CollisionTraceFlag=NS(CTF_USE_COMPLEX_AS_SIMPLE='complex'),
        EditorAssetLibrary=NS(load_asset=assets.get, does_asset_exist=lambda p: p in assets,
                              duplicate_asset=duplicate, save_loaded_asset=save),
        AtelierBuildWorkerLibrary=NS(validate_mesh_collision=validate),
        MeshImportAudit=NS(dump_mesh_triangles=dump), Vector=lambda *v: v)
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    import shutil
    verifier = tmp_path / body.VERIFIER; verifier.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / body.VERIFIER, verifier)
    inputs = {'raw': 'raw', 'source_export': source, 'payload': payload, 'metadata': metadata, 'material': 'material'}
    context = NS(job_dir=str(tmp_path), inputs=inputs, packages={slot: [] for slot in inputs}, outputs=[dest],
        data_outputs=['data/geometry/' + piece + '.bin', 'data/reports/' + piece + '.json'],
        params={'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': dest,
                'args': {'action': 'mesh', 'piece': piece, 'collision': False, 'source_export': 'source_export',
                         'payload': 'payload', 'metadata': 'metadata', 'materials': {'material_024': 'material'}}})
    context.packages.update(raw=[raw], material=[material])
    return state, context


def test_current_native_finish_retains_original_policy_and_audit(native_case):
    state, context = native_case
    result = body.run(context)
    mesh = state.assets[context.outputs[0]]
    assert mesh.allow_cpu_access is False
    assert mesh.settings.values == {'use_full_precision_u_vs': True, 'remove_degenerates': False, 'distance_field_resolution_scale': 0.}
    assert mesh.body.values == {'collision_trace_flag': 'complex', 'double_sided_geometry': False}
    assert state.checks == 2 and state.saves == 1
    assert next(iter(result.values()))['triangles'] == 1
    assert state.assets[context.packages['raw'][0]].allow_cpu_access is True


@pytest.mark.parametrize('damage', ['triangles', 'bounds', 'slot', 'simple', 'payload', 'after_save'])
def test_current_native_mismatch_refuses(native_case, damage):
    state, context = native_case; raw = state.assets[context.packages['raw'][0]]
    if damage == 'triangles': raw.triangles = 2
    if damage == 'bounds': raw.high = 101.
    if damage == 'slot': raw.static_materials[0].values['imported_material_slot_name'] = 'Other'
    if damage == 'simple': raw.simple = 1
    if damage == 'payload': (context.inputs['payload'] / 'SM_CP_Test.npz').write_bytes(b'changed')
    if damage == 'after_save': state.mutate = True
    with pytest.raises(ValueError): body.run(context)


def test_native_summary_requires_complete_actual_source_library(tmp_path):
    build = tmp_path / 'build.json'
    build.write_text(json.dumps({'render': [{'name': 'SM_CP_Test', 'triangles': 3}], 'collision': []}))
    archive = tmp_path / 'build.tree.tar'; pack_root(build, archive)
    child_root = tmp_path / 'child'; report = child_root / 'data/reports/SM_CP_Test.json'
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({'name': 'SM_CP_Test', 'triangles': 3, 'collision': False,
                                 'bounds_error_cm': .001, 'uv_channels': 1}))
    child = NS(products=[NS(paths=[child_root])]); values = [(child, 'SM_CP_Test')]
    members.native_summary(archive, values, [], tmp_path / 'summary')
    assert json.loads((tmp_path / 'summary/native.json').read_text())['meshes'][0]['triangles'] == 3
    with pytest.raises(ValueError, match='membership'):
        members.native_summary(archive, [], [], tmp_path / 'missing')
    changed = members.read_json(report); changed['triangles'] = 4; report.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match='differs'):
        members.native_summary(archive, values, [], tmp_path / 'changed')


def test_native_triangle_observation_cannot_be_certified_by_counts_and_bounds(native_case, monkeypatch):
    state, context = native_case
    unreal = sys.modules['unreal']
    original = unreal.MeshImportAudit.dump_mesh_triangles
    def changed(mesh, origin, path):
        original(mesh, origin, path)
        points = np.fromfile(path, dtype='<f8').reshape(-1, 3)
        points[1, 0] -= 20.
        points.tofile(path)
        return True
    monkeypatch.setattr(unreal.MeshImportAudit, 'dump_mesh_triangles', changed)
    with pytest.raises(AssertionError, match='vertex'):
        body.run(context)
