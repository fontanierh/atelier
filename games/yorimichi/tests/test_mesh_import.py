"""Model UE's stored-data reimport precedence; native equivalence remains a separate gate."""
import ast
import importlib.util
import json
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

import pytest


class ImportData:
    def __init__(self):
        self.values = {'convert_scene_unit': False, 'import_uniform_scale': 1.0}

    def set_editor_property(self, name, value):
        self.values[name] = value

    def get_editor_property(self, name):
        return self.values[name]


class Mesh:
    def __init__(self, data):
        self.values = {'asset_import_data': data, 'static_materials': ['old slot']}
        self.centimetres = None

    def get_editor_property(self, name):
        return self.values[name]

    def set_editor_property(self, name, value):
        self.values[name] = value

    @property
    def static_materials(self):
        return self.values['static_materials']

    @static_materials.setter
    def static_materials(self, value):
        self.values['static_materials'] = value

    def set_material(self, index, material):
        self.static_materials[index].set_editor_property('material_interface', material)


@pytest.fixture
def importer(monkeypatch, tmp_path):
    assets, calls, source_slots = {}, [], {}

    def execute(tasks):
        for task in tasks:
            package = task.destination_path + '/' + task.destination_name
            mesh = assets.get(package)
            new = mesh is None
            migrated = not new and not isinstance(mesh.values['asset_import_data'], ImportData)
            if mesh is None:
                mesh = assets[package] = Mesh(task.options.static_mesh_import_data)
            elif not isinstance(mesh.values['asset_import_data'], ImportData):
                # UE 5.8 FbxFactory::FactoryCreateFile calls UpdateReimportPaths first.
                # GetImportDataForStaticMesh replaces Interchange data with stored defaults;
                # Reimport then uses that data instead of the task's configured options.
                mesh.values['asset_import_data'] = ImportData()
            data = mesh.values['asset_import_data']
            metres = 0.1 if Path(task.filename).name == 'seed.fbx' else 12.0
            mesh.centimetres = metres * (100 if data.values['convert_scene_unit'] else 1)
            imported_slots = source_slots.get(Path(task.filename).name)
            # A fresh/migrated package gets source slots. Legacy reimport conserves existing
            # slots, including a migration seed's palette, unless the caller cleared them.
            if imported_slots is not None and (new or migrated or not mesh.static_materials):
                mesh.static_materials = [slot.copy() for slot in imported_slots]
            calls.append((Path(task.filename).name, package, mesh.centimetres))
            task.imported_object_paths = [package]

    fake = SimpleNamespace(
        EditorAssetLibrary=SimpleNamespace(does_asset_exist=lambda path: path in assets,
                                          load_asset=lambda path: assets.get(path)),
        AssetToolsHelpers=SimpleNamespace(get_asset_tools=lambda: SimpleNamespace(import_asset_tasks=execute)),
        AssetImportTask=SimpleNamespace,
        FbxImportUI=lambda: SimpleNamespace(static_mesh_import_data=ImportData()),
        FbxStaticMeshImportData=ImportData,
        AssetRegistryHelpers=SimpleNamespace(create_asset_data=lambda mesh: SimpleNamespace(
            get_tag_value=lambda name: 'True' if mesh.values.get('nanite_enabled', False) else 'False')),
        FBXImportType=SimpleNamespace(FBXIT_STATIC_MESH='static'),
        VertexColorImportOption=SimpleNamespace(REPLACE='replace'),
        FBXNormalImportMethod=SimpleNamespace(FBXNIM_IMPORT_NORMALS='normals'),
    )
    monkeypatch.setitem(sys.modules, 'unreal', fake)
    script = Path(__file__).resolve().parents[1] / 'unreal/Scripts/mesh_import.py'
    monkeypatch.syspath_prepend(str(script.parent))
    spec = importlib.util.spec_from_file_location('fixture_mesh_import', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return SimpleNamespace(module=module, assets=assets, calls=calls, source=tmp_path / 'mesh.fbx',
                           seed=tmp_path / 'seed.fbx', package='/Game/Owned/Mesh', source_slots=source_slots, unreal=fake)


@pytest.mark.parametrize('initial', ['new', 'interchange', 'legacy'])
@pytest.mark.parametrize('source_is_seed', [False, True], ids=['distinct-source', 'source-is-seed'])
def test_import_units_are_correct_for_new_migrated_and_repeated_packages(importer, initial, source_is_seed):
    p = importer
    source = p.seed if source_is_seed else p.source
    expected_size = 10 if source_is_seed else 1200
    previous = None
    if initial != 'new':
        previous = p.assets[p.package] = Mesh(ImportData() if initial == 'legacy' else object())
    unrelated = p.assets['/Game/Other/Mesh'] = Mesh(object())
    mesh = p.module.import_mesh(source, '/Game/Owned', 'Mesh', seed=p.seed, fresh_slots=True)
    assert mesh.centimetres == expected_size
    needs_seed = initial == 'interchange'
    assert [name for name, _, _ in p.calls] == ([source.name] if needs_seed else []) + [source.name]
    if previous is not None:
        assert mesh is previous
    if initial != 'new' or needs_seed:
        assert mesh.values['static_materials'] == []
    assert p.assets['/Game/Other/Mesh'] is unrelated and unrelated.centimetres is None
    p.calls.clear()
    assert p.module.import_mesh(source, '/Game/Owned', 'Mesh', seed=p.seed) is mesh
    assert p.calls == [(source.name, p.package, expected_size)]


def test_failed_source_migration_cannot_continue_to_final_pass(importer, monkeypatch):
    p = importer
    p.assets[p.package] = Mesh(object())
    calls = []
    monkeypatch.setattr(p.module, '_import_mesh', lambda *args: calls.append(args) or Mesh(object()))
    with pytest.raises(RuntimeError, match='establish legacy import data'):
        p.module.import_mesh(p.source, '/Game/Owned', 'Mesh', seed=p.seed)
    assert len(calls) == 1 and calls[0][0] == p.source


@pytest.mark.parametrize('initial', ['new', 'interchange', 'legacy'])
def test_hidamari_material_owner_preserves_independent_city_and_island_packages(importer, monkeypatch, tmp_path, initial):
    """The real legacy dispatch supplies materials but never recreates delegated geometry."""
    p = importer
    scripts = Path(__file__).resolve().parents[1] / 'unreal/Scripts'
    game = scripts.parents[1]
    package = '/Game/Japan/Terrain'
    previous = None
    if initial != 'new':
        previous = p.assets[package] = Mesh(ImportData() if initial == 'legacy' else object())
    unrelated = p.assets['/Game/Other/Mesh'] = Mesh(object())
    p.assets['/Game/Japan/Materials/M_Village'] = object()
    monkeypatch.setattr(sys, 'path', list(sys.path))
    monkeypatch.delenv('HIDAMARI_ASSETS', raising=False)
    p.unreal.SystemLibrary = SimpleNamespace(execute_console_command=lambda *args: None)
    p.unreal.MaterialEditingLibrary = SimpleNamespace()
    logs = []; p.unreal.log = logs.append
    for name, module in {
        'yori': SimpleNamespace(OUT=tmp_path, GAME=game), 'atmosphere': SimpleNamespace(), 'mesh_import': p.module,
        'harbor_material': SimpleNamespace(material=lambda **kwargs: object()),
        'arcade_material': SimpleNamespace(material=lambda **kwargs: object()),
        'plaza_material': SimpleNamespace(water_material=lambda *args: object(), paving_material=lambda: object()),
        'city_material': SimpleNamespace(),
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.delitem(sys.modules, 'import_village', raising=False)
    spec = importlib.util.spec_from_file_location('city_logical_fixture',game/'world/regions/hidamari/logical_catalogue.py')
    catalogue = importlib.util.module_from_spec(spec); spec.loader.exec_module(catalogue)
    folder = tmp_path/'hidamari'; folder.mkdir()
    manifest = folder/'manifest.json'
    manifest.write_text(json.dumps(dict.fromkeys(catalogue.ASSETS, {})))
    for _ in range(2):
        runpy.run_path(str(scripts/'import_hidamari.py'), init_globals={'NORTH':False})
        assert p.assets.get(package) is previous
        assert p.assets['/Game/Other/Mesh'] is unrelated
        assert p.calls == []
    assert logs == ['HIDAMARI IMPORT COMPLETE'] * 2
    # Incomplete logical material membership must fail before any raw source pass.
    manifest.write_text('{}')
    with pytest.raises(AssertionError, match='Incomplete logical city material metadata'):
        runpy.run_path(str(scripts/'import_hidamari.py'), init_globals={'NORTH':False})
    assert p.calls == []


@pytest.mark.parametrize('initial', ['new', 'stale-slots', 'stale-lods'])
@pytest.mark.parametrize('save_succeeds', [True, False])
def test_treehouse_trees_receive_their_own_source_and_current_collision(importer, monkeypatch, tmp_path, initial, save_succeeds):
    """Run current tree receiving and FBX admission without an unrelated source seed."""
    p = importer
    scripts = Path(__file__).resolve().parents[1] / 'unreal/Scripts'
    package = '/Game/Japan/Assets/Tree_Treehouse'
    source = tmp_path / 'treehouse/trees'
    source.mkdir(parents=True)
    (source / 'trees.json').write_text(json.dumps({
        'Tree_Treehouse': dict(slot='LeafAmber', leaf='LeafAmber', crown_hi=12.0, triangles=42),
    }))
    (source / 'Tree_Treehouse.fbx').touch()

    class Slot:
        def __init__(self, name, material=None):
            self.values = dict(imported_material_slot_name=name, material_interface=material)
        def get_editor_property(self, name):
            return self.values[name]
        def set_editor_property(self, name, value):
            self.values[name] = value
        def copy(self):
            return Slot(self.values['imported_material_slot_name'], self.values['material_interface'])

    monkeypatch.setattr(Mesh, 'get_num_lods', lambda self: getattr(self, 'lods', 1), raising=False)
    monkeypatch.setattr(Mesh, 'get_num_triangles', lambda self, lod: 42, raising=False)
    monkeypatch.setattr(Mesh, 'get_name', lambda self: 'Tree_Treehouse', raising=False)
    monkeypatch.setattr(Mesh, 'set_num_source_models', lambda self, count: setattr(self, 'lods', count), raising=False)
    monkeypatch.setattr(Mesh, 'get_bounding_box', lambda self: SimpleNamespace(max=SimpleNamespace(z=self.centimetres)), raising=False)
    if initial != 'new':
        stale = p.assets[package] = Mesh(ImportData())
        stale.static_materials = [Slot('Bark'), Slot('OldLeaf' if initial == 'stale-slots' else 'LeafAmber')]
        stale.lods = 2 if initial == 'stale-lods' else 1
    p.source_slots.update({'Tree_Treehouse.fbx': [Slot('Bark'), Slot('LeafAmber')]})
    materials = {name: object() for name in ('Bark', 'LeafAmber')}
    for name in ('M_Foliage', 'MI_LeafCrimson', 'MI_LeafAmber', 'MI_Bark'):
        p.assets['/Game/Japan/Materials/' + name] = materials.get(name.removeprefix('MI_'), object())
    saved, collision, deleted = [], {}, []
    original_execute = p.module.AT.import_asset_tasks

    def execute(tasks):
        for task in tasks:
            if Path(task.filename).suffix == '.png':
                p.assets['/Game/Japan/Textures/' + Path(task.filename).stem] = ImportData()
                continue
            assert Path(task.filename).is_file(), 'FBX import needs a real source file'
            previous = p.assets.get(task.destination_path + '/' + task.destination_name)
            if previous:
                stored_source = previous.values['asset_import_data'].values.get('source_filename')
                assert stored_source is None or Path(stored_source).is_file(), 'Reimport would open a source-file dialog'
            original_execute([task])
            mesh = p.assets[task.destination_path + '/' + task.destination_name]
            mesh.values['asset_import_data'].values['source_filename'] = task.filename
            mesh.values['body_setup'] = SimpleNamespace(set_editor_property=collision.__setitem__)

    def duplicate_asset(source_path, destination):
        assert source_path == '/Engine/BasicShapes/Cube'
        mesh = p.assets[destination] = Mesh(ImportData())
        mesh.values['asset_import_data'].values['source_filename'] = str(tmp_path / 'missing-engine-cube.fbx')
        return mesh

    p.module.AT.import_asset_tasks = execute
    p.unreal.AssetToolsHelpers.get_asset_tools = lambda: p.module.AT
    p.unreal.EditorAssetLibrary.duplicate_asset = duplicate_asset
    p.unreal.EditorAssetLibrary.delete_asset = lambda path: deleted.append(path) or p.assets.pop(path)
    p.unreal.EditorAssetLibrary.save_loaded_asset = lambda asset: saved.append(asset) or save_succeeds
    p.unreal.MaterialEditingLibrary = SimpleNamespace(**{name: lambda *args: None for name in (
        'set_material_instance_parent', 'set_material_instance_texture_parameter_value', 'update_material_instance')})
    p.unreal.SystemLibrary = SimpleNamespace(execute_console_command=lambda *args: None)
    p.unreal.Vector4 = lambda *args: args
    p.unreal.TextureMipGenSettings = SimpleNamespace(TMGS_SIMPLE_AVERAGE='average')
    p.unreal.CollisionTraceFlag = SimpleNamespace(CTF_USE_SIMPLE_AS_COMPLEX='none')
    p.unreal.StaticMeshEditorSubsystem = object
    p.unreal.get_editor_subsystem = lambda cls: SimpleNamespace(get_simple_collision_count=lambda mesh: 0, get_convex_collision_count=lambda mesh: 0)
    p.unreal.CitySurfaceValidation = SimpleNamespace(collision_vertices=lambda mesh: '[]')
    monkeypatch.setattr(sys, 'path', list(sys.path))
    for name, module in {'yori': SimpleNamespace(OUT=tmp_path), 'atmosphere': SimpleNamespace(),
                         'see_through': SimpleNamespace(), 'mesh_import': p.module}.items():
        monkeypatch.setitem(sys.modules, name, module)
    # This commandlet runs main() unconditionally; load its real definitions without
    # importing unrelated room meshes and material graphs.
    script = scripts / 'import_treehouse.py'
    monkeypatch.delitem(sys.modules, 'treehouse_atomic_native', raising=False)
    tree = ast.parse(script.read_text(), filename=str(script))
    assert isinstance(tree.body[-1], ast.Expr) and isinstance(tree.body[-1].value, ast.Call)
    assert tree.body[-1].value.func.id == 'main'
    tree.body.pop()
    owner = {'__file__': str(script)}
    exec(compile(tree, str(script), 'exec'), owner)
    if not save_succeeds:
        with pytest.raises(AssertionError):
            owner['trees']({})
        assert saved and not p.calls  # A failed prerequisite save must stop before the mesh import.
        return
    monkeypatch.setattr(owner['atomic_native'], 'HULLS', {'Tree_Treehouse': []})
    report = {}
    for _ in range(2):
        owner['trees'](report)
        mesh = p.assets[package]
        assert mesh.centimetres == 1200 and mesh.get_num_lods() == 1
        assert [slot.values['imported_material_slot_name'] for slot in mesh.static_materials] == ['Bark', 'LeafAmber']
        assert [slot.values['material_interface'] for slot in mesh.static_materials] == list(materials.values())
        assert saved[-1] is mesh
    assert [name for name, _, _ in p.calls] == ['Tree_Treehouse.fbx', 'Tree_Treehouse.fbx']
    assert deleted == []  # The current receiver preserves package identity and refreshes its own source.
    assert collision == {'collision_trace_flag': 'none'}
    assert report == {'trees': ['Tree_Treehouse', 'Tree_Treehouse']}


def test_see_through_commandlet_resolves_sibling_without_scripts_on_path(monkeypatch):
    """A fresh commandlet must reach the real collection check without prior world imports."""
    scripts = Path(__file__).resolve().parents[1] / 'unreal/Scripts'
    pipeline = scripts.parents[1] / 'assets/characters/pipeline'
    monkeypatch.setattr(sys, 'path', [path for path in sys.path if path not in (str(scripts), str(pipeline))])
    for name in ('see_through', 'definition'):
        monkeypatch.setitem(sys.modules, name, None)
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, 'unreal', SimpleNamespace(
        EditorAssetLibrary=SimpleNamespace(does_asset_exist=lambda path: False),
        MaterialEditingLibrary=SimpleNamespace(),
        MaterialProperty=SimpleNamespace(MP_OPACITY_MASK='opacity'),
        CustomMaterialOutputType=SimpleNamespace(CMOT_FLOAT1='float'),
    ))
    with pytest.raises(RuntimeError, match='Build unreal.materials: missing /Game/SeeThrough/MPC_SeeThrough'):
        runpy.run_path(str(scripts / 'import_see_through.py'), run_name='__main__')
    assert Path(sys.modules['see_through'].__file__) == scripts / 'see_through.py'
    assert Path(sys.modules['definition'].__file__) == pipeline / 'definition.py'


def test_world_asset_owner_requires_island_materials_without_reimporting_terrain(tmp_path, monkeypatch):
    import os
    script = Path(__file__).resolve().parents[1]/'unreal/Scripts/setup_project.py'
    body = [n for n in ast.parse(script.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='main']
    (tmp_path/'world.json').write_text('{}')
    calls = []; materials = {'/Game/Japan/Materials/MI_'+name:object() for name in ('FarForest','Coast')}
    monkeypatch.delenv('JAPAN_ONLY', raising=False)
    monkeypatch.setitem(sys.modules,'world_props',SimpleNamespace(read=lambda out:{}))
    monkeypatch.setattr(runpy,'run_path',lambda path,**kwargs:calls.append(Path(path).name))
    owner=dict(__file__=str(script),OUT=str(tmp_path),Path=Path,os=os,
        EAL=SimpleNamespace(load_asset=materials.get),unreal=SimpleNamespace(),
        material_bindings=lambda:{},LOG=calls.append,
        purge=lambda:pytest.fail('Never purge receiving evidence'),
        import_fbx=lambda *args:pytest.fail('Island geometry must not be imported here'),
        build_level=lambda *args:pytest.fail('Island map must not be recreated here'))
    exec(compile(ast.Module(body=body,type_ignores=[]),str(script),'exec'),owner)
    for _ in range(2):owner['main']()
    assert calls == ['import_wanderer.py','WORLD ASSETS IMPORT COMPLETE']*2
    materials.pop('/Game/Japan/Materials/MI_Coast')
    with pytest.raises(RuntimeError,match='Build unreal.island.*Coast'):owner['main']()
    assert len(calls)==4


def test_verified_default_reuse_skips_geometry_and_defers_receipt(importer, monkeypatch):
    p = importer
    mesh = p.module.import_mesh(p.source, '/Game/Owned', 'Mesh', seed=p.seed)
    assert p.module.legacy_options_match(mesh)
    p.calls.clear()
    deferred = []
    reuse = SimpleNamespace(defer_validated=deferred.append)
    monkeypatch.setattr(p.module, 'common_fbx_mesh', lambda *a, **k: (mesh, reuse))
    assert p.module.import_mesh(p.source, '/Game/Owned', 'Mesh', seed=p.seed) is mesh
    assert p.calls == [] and deferred == ['/Game/Owned/Mesh']


def test_default_reuse_miss_preserves_seed_migration(importer, monkeypatch):
    p = importer
    events = []
    reuse = SimpleNamespace(imported=lambda name: events.append(('imported', name)),
                            defer_validated=lambda name: events.append(('pending', name)))
    monkeypatch.setattr(p.module, 'common_fbx_mesh', lambda *a, **k: (None, reuse))
    p.module.import_mesh(p.source, '/Game/Owned', 'Mesh', seed=p.seed)
    assert [name for name, _, _ in p.calls] == ['mesh.fbx']
    assert events == [('imported', p.package), ('pending', p.package)]


def test_failed_default_import_does_not_publish_pending_receipt(importer, monkeypatch):
    p = importer
    pending = []
    reuse = SimpleNamespace(imported=pending.append, defer_validated=pending.append)
    monkeypatch.setattr(p.module, 'common_fbx_mesh', lambda *a, **k: (None, reuse))
    def failed(*args, **kwargs):
        raise RuntimeError('native import failed')
    monkeypatch.setattr(p.module, '_import_mesh', failed)
    with pytest.raises(RuntimeError, match='native import failed'):
        p.module.import_mesh(p.source, '/Game/Owned', 'Mesh', seed=p.seed)
    assert pending == []


@pytest.mark.parametrize('key,value', [('convert_scene_unit', False), ('build_nanite', True)])
def test_reuse_validator_refuses_legacy_option_drift(importer, key, value):
    p = importer
    mesh = p.module.import_mesh(p.source, '/Game/Owned', 'Mesh', seed=p.seed)
    mesh.values['asset_import_data'].values[key] = value
    assert not p.module.legacy_options_match(mesh)


def test_unrelated_seed_is_not_read_or_imported_even_when_missing(importer):
    p = importer
    class UnreadableSeed:
        def __fspath__(self): raise AssertionError('Unrelated bootstrap file was consumed')
    assert p.module.import_mesh(p.source, '/Game/Owned', 'Mesh', seed=UnreadableSeed()) is p.assets[p.package]
    assert [name for name, _, _ in p.calls] == ['mesh.fbx']


def test_non_fbx_migration_uses_source_twice_and_clears_migration_palette(importer):
    p = importer
    p.assets[p.package] = Mesh(object())
    p.source_slots['mesh.fbx'] = []
    mesh = p.module.import_mesh(p.source, '/Game/Owned', 'Mesh', seed=p.seed)
    assert [name for name, _, _ in p.calls] == ['mesh.fbx', 'mesh.fbx']
    assert [size for _, _, size in p.calls] == [12., 1200.]
    assert isinstance(mesh.get_editor_property('asset_import_data'), ImportData)


def test_reimport_corrects_stored_nanite_drift_before_receipt(importer):
    p = importer
    mesh = p.module.import_mesh(p.source, '/Game/Owned', 'Mesh')
    mesh.values['asset_import_data'].values['build_nanite'] = True
    assert not p.module.legacy_options_match(mesh)
    assert p.module.import_mesh(p.source, '/Game/Owned', 'Mesh') is mesh
    assert mesh.values['asset_import_data'].values['build_nanite'] is False
    assert p.module.legacy_options_match(mesh)


def test_failed_final_options_cannot_certify_or_queue_receipt(importer, monkeypatch):
    p = importer
    mesh = p.module.import_mesh(p.source, '/Game/Owned', 'Mesh')
    mesh.values['asset_import_data'].values['build_nanite'] = True
    events = []
    monkeypatch.setattr(p.module, 'common_fbx_mesh', lambda *a, **kw: (None, SimpleNamespace(
        imported=lambda _: events.append('imported'), defer_validated=lambda _: events.append('pending'))))
    monkeypatch.setattr(p.module, '_source_mesh', lambda *a: mesh)
    with pytest.raises(RuntimeError, match='declared options'):
        p.module.import_mesh(p.source, '/Game/Owned', 'Mesh')
    assert events == ['imported']


def test_actual_nanite_drift_cannot_hide_behind_correct_stored_import_options(importer, monkeypatch):
    p = importer
    mesh = p.module.import_mesh(p.source, '/Game/Owned', 'Mesh')
    mesh.values['nanite_enabled'] = True
    assert mesh.values['asset_import_data'].values['build_nanite'] is False
    assert not p.module.legacy_options_match(mesh)
    events = []
    monkeypatch.setattr(p.module, 'common_fbx_mesh', lambda *a, **kw: (None, SimpleNamespace(
        imported=lambda _: events.append('imported'), defer_validated=lambda _: events.append('pending'))))
    with pytest.raises(RuntimeError, match='declared options'):
        p.module.import_mesh(p.source, '/Game/Owned', 'Mesh')
    assert events == ['imported']


@pytest.mark.parametrize('hit', [False, True])
def test_owner_reset_runs_only_between_admission_miss_and_raw_import(importer, monkeypatch, hit):
    p = importer
    mesh = p.module.import_mesh(p.source, '/Game/Owned', 'Mesh')
    events = []
    reuse = SimpleNamespace(imported=lambda name: events.append('imported'),
                            defer_validated=lambda name: events.append('pending'))
    def admit(*args, **kwargs):
        events.append('admit')
        return (mesh if hit else None), reuse
    monkeypatch.setattr(p.module, 'common_fbx_mesh', admit)
    original = p.module._source_mesh
    def raw(*args):
        events.append('raw')
        return original(*args)
    monkeypatch.setattr(p.module, '_source_mesh', raw)
    result = p.module.import_mesh(p.source, '/Game/Owned', 'Mesh', before_import=lambda: events.append('reset'))
    assert result is mesh
    assert events == (['admit', 'pending'] if hit else ['admit', 'reset', 'raw', 'imported', 'pending'])


def test_failed_owner_preparation_never_imports_or_defers_a_receipt(importer, monkeypatch):
    p = importer
    events = []
    reuse = SimpleNamespace(imported=events.append, defer_validated=events.append)
    monkeypatch.setattr(p.module, 'common_fbx_mesh', lambda *a, **k: (None, reuse))
    def refuse():
        raise RuntimeError('Owner preparation refused')
    with pytest.raises(RuntimeError, match='Owner preparation refused'):
        p.module.import_mesh(p.source, '/Game/Owned', 'Mesh', before_import=refuse)
    assert p.calls == [] and events == []


@pytest.mark.parametrize('accepts', [False, True])
def test_owner_requirement_participates_in_current_native_admission(importer, monkeypatch, accepts):
    p = importer
    mesh = p.module.import_mesh(p.source, '/Game/Owned', 'Mesh')
    p.calls.clear()
    reads = []
    def requirement(value):
        assert value is mesh
        reads.append('current-owner-check')
        return accepts
    def admit(*args, **kwargs):
        assert kwargs['validation_functions'] == ('legacy_options_match', '_reuse_matches')
        return (mesh if kwargs['validator'](mesh) else None), None
    monkeypatch.setattr(p.module, 'common_fbx_mesh', admit)
    p.module.import_mesh(p.source, '/Game/Owned', 'Mesh', reuse_validator=requirement)
    assert reads == ['current-owner-check']
    assert bool(p.calls) is not accepts


def test_base_and_lod_share_the_real_common_pending_receipt_packet(importer, monkeypatch, tmp_path):
    from atelier import mesh_reuse, native_candidates, unreal_mesh_reuse as native
    p = importer
    p.source.write_bytes(b'base source')
    lod = tmp_path/'Mesh_LOD1.fbx'
    lod.write_bytes(b'LOD source')
    ctx = SimpleNamespace(out=tmp_path, uproject=tmp_path/'unreal/Game.uproject', game='fixture')
    current = {'engine': 'fixture'}
    monkeypatch.setattr(native, 'native_context', lambda _: ctx)
    monkeypatch.setattr(native, 'context', lambda _: current)
    monkeypatch.setattr(native_candidates, 'load_all', lambda *args: [])
    monkeypatch.setattr(native, '_COMMON_FBX', {})
    monkeypatch.setattr(native, 'imported_source_matches', lambda *args: True)
    p.unreal.load_asset = p.assets.get
    p.unreal.EditorLoadingAndSavingUtils = SimpleNamespace(get_dirty_content_packages=lambda: [])
    owner = Path(__file__).parents[1]/'unreal/Scripts/import_foliage.py'
    task = 'unreal.foliage.Fixture'
    nonce = 'a'*24
    for key,value in dict(ATELIER_BUILD_TASK=task, ATELIER_BUILD_GAME='fixture',
                          ATELIER_BUILD_SCRIPT=str(owner.resolve()), ATELIER_MESH_REUSE_NONCE=nonce).items():
        monkeypatch.setenv(key,value)
    predicate = lambda mesh: True
    p.module.import_mesh(p.source, '/Game/Owned', 'Mesh', reuse_validator=predicate)
    p.module.import_mesh(lod, '/Game/Owned', 'Mesh_LOD1', reuse_validator=predicate)
    packet = json.loads(mesh_reuse.pending_path(ctx,task,nonce).read_text())
    assert len(native._COMMON_FBX) == 1
    assert set(packet['entries']) == {'/Game/Owned/Mesh','/Game/Owned/Mesh_LOD1'}
    assert packet['counts']['imported'] == 2
