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
@pytest.mark.parametrize('entrypoint', ['region', 'world'])
def test_hidamari_terrain_reimport_replaces_seed_slots_and_keeps_terrain_materials(importer, monkeypatch, tmp_path, initial, entrypoint):
    """Run the real region owner, village adapter, FBX migration and material assignment."""
    p = importer
    scripts = Path(__file__).resolve().parents[1] / 'unreal/Scripts'
    terrain_package = '/Game/Japan/Terrain'
    names = ('Ground', 'Road', 'Sand', 'Coast', 'CoastRock')
    materials = {name: object() for name in names}

    class Slot:
        def __init__(self, name, material=None):
            self.values = dict(material_slot_name=name, imported_material_slot_name=name, material_interface=material)
        def get_editor_property(self, name):
            return self.values[name]
        def set_editor_property(self, name, value):
            self.values[name] = value
        def copy(self):
            return Slot(self.values['material_slot_name'], self.values['material_interface'])

    p.source_slots.update({'Village_Sign.fbx': [Slot('VillagePalette')],
                          'terrain.fbx': [Slot(name) for name in names]})
    previous = None
    if initial != 'new':
        previous = p.assets[terrain_package] = Mesh(ImportData() if initial == 'legacy' else object())
        previous.static_materials = [Slot('VillagePalette')] if initial == 'legacy' else [Slot(name) for name in names]
    unrelated = p.assets['/Game/Other/Mesh'] = Mesh(object())
    p.assets.update({'/Game/Japan/Materials/MI_' + name: material for name, material in materials.items()
                     if name != 'CoastRock'})
    p.assets['/Game/Japan/Materials/M_Village'] = object()
    saved, logs, sand_calls, coast_calls, rock_calls, events, sea_calls = [], [], [], [], [], [], []
    collision = {}
    def coast_rock_instance():
        events.append('create-rock')
        rock_calls.append('rock')
        p.assets['/Game/Japan/Materials/MI_CoastRock'] = materials['CoastRock']
        return materials['CoastRock']
    original_load = p.unreal.EditorAssetLibrary.load_asset
    def load(path):
        if path == '/Game/Japan/Materials/MI_CoastRock':
            events.append('lookup-rock')
            assert rock_calls, 'Rock material must exist before its slot is bound'
        return original_load(path)
    p.unreal.EditorAssetLibrary.load_asset = load
    original_execute = p.unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks
    def execute(tasks):
        if any(Path(task.filename).name == 'terrain.fbx' for task in tasks):
            events.append('import-terrain')
            assert p.assets.get('/Game/Japan/Materials/MI_CoastRock') is materials['CoastRock']
        original_execute(tasks)
        p.assets[terrain_package].values['body_setup'] = SimpleNamespace(set_editor_property=collision.__setitem__)
    p.module.AT.import_asset_tasks = execute
    p.unreal.AssetToolsHelpers.get_asset_tools = lambda: SimpleNamespace(import_asset_tasks=execute)
    p.unreal.EditorAssetLibrary.save_loaded_asset = saved.append
    p.unreal.MaterialEditingLibrary = SimpleNamespace()
    p.unreal.SystemLibrary = SimpleNamespace(execute_console_command=lambda *args: None)
    p.unreal.CollisionTraceFlag = SimpleNamespace(CTF_USE_COMPLEX_AS_SIMPLE='complex')
    p.unreal.log = logs.append
    monkeypatch.setattr(sys, 'path', list(sys.path))
    monkeypatch.delenv('HIDAMARI_ASSETS', raising=False)
    for name, module in {
        'yori': SimpleNamespace(OUT=tmp_path), 'atmosphere': SimpleNamespace(), 'mesh_import': p.module,
        'harbor_material': SimpleNamespace(material=lambda **kwargs: object()),
        'arcade_material': SimpleNamespace(material=lambda **kwargs: object()),
        'plaza_material': SimpleNamespace(water_material=lambda *args: object(), paving_material=lambda: object()),
        'city_material': SimpleNamespace(),
        'import_southwest': SimpleNamespace(sand_material=lambda: sand_calls.append('sand'),
                                            sea_plane=lambda: sea_calls.append('sea')),
        'forest_ground': SimpleNamespace(coast_instance=lambda *args: coast_calls.append('coast'),
                                        coast_rock_instance=coast_rock_instance),
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    for name in ('import_village', 'mesh_materials'):
        spec = importlib.util.spec_from_file_location(name, scripts / (name + '.py'))
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
    (tmp_path / 'hidamari').mkdir()
    (tmp_path / 'hidamari/manifest.json').write_text('{}')
    run_city = lambda: runpy.run_path(str(scripts / 'import_hidamari.py'), init_globals={'NORTH': False})
    built = []
    if entrypoint == 'world':
        # Execute the production orchestration, real city importer, village adapter and
        # FBX migration together. Unrelated character/level work is outside this fixture.
        import glob
        import os
        (tmp_path / 'world.json').write_text('{}')
        script = scripts / 'setup_project.py'
        tree = ast.parse(script.read_text())
        body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main']
        forest = SimpleNamespace(get_editor_property=lambda name: object())
        generic = []
        owner = dict(__file__=str(script), OUT=str(tmp_path), os=os, glob=glob,
                     EAL=p.unreal.EditorAssetLibrary, unreal=p.unreal, FOLIAGE=set(),
                     purge=lambda: pytest.fail("Upfront purge would destroy reusable packages"), material_bindings=lambda: {},
                     instance=lambda *args: forest, forest_ground_material=lambda: object(),
                     import_fbx=lambda *args: generic.append(args), assign=lambda *args: None,
                     build_level=lambda mesh, *args: built.append(mesh))
        exec(compile(ast.Module(body=body, type_ignores=[]), str(script), 'exec'), owner)
        real_run_path = runpy.run_path
        def nested(path, **kwargs):
            if Path(path).name == 'import_wanderer.py':
                return {}
            return real_run_path(path, **kwargs)
        monkeypatch.setattr(runpy, 'run_path', nested)
        run_city = owner['main']
    for _ in range(2):
        events.clear()
        run_city()
        mesh = p.assets[terrain_package]
        assert mesh.centimetres == 1200
        assert isinstance(mesh.values['asset_import_data'], ImportData)
        assert [slot.values['imported_material_slot_name'] for slot in mesh.static_materials] == list(names)
        assert [slot.values['material_interface'] for slot in mesh.static_materials] == list(materials.values())
        assert events.index('create-rock') < events.index('import-terrain') < events.index('lookup-rock')
        assert events.count('create-rock') == 1 and events.count('lookup-rock') == 1
        assert mesh.static_materials[-1].values['material_interface'] is materials['CoastRock']
        assert saved[-1] is mesh
    if previous is not None:
        assert mesh is previous
    assert [name for name, _, _ in p.calls] == ['terrain.fbx'] * (3 if initial == 'interchange' else 2)
    assert collision == {'collision_trace_flag': 'complex'}
    assert p.assets['/Game/Other/Mesh'] is unrelated and unrelated.centimetres is None
    assert json.loads((tmp_path / 'hidamari/import-report.json').read_text()) == {}
    assert sand_calls == ['sand', 'sand']
    assert rock_calls == ['rock', 'rock']
    assert coast_calls == ['coast'] * (4 if entrypoint == 'world' else 2)
    assert logs == ['HIDAMARI IMPORT COMPLETE'] * 2
    if entrypoint == 'world':
        assert built == [mesh, mesh]  # the level receives the final imported package
        assert generic == []  # no earlier full terrain import, including the first build
        assert coast_calls == ['coast'] * 4  # setup material plus final city binding per run
    assert sea_calls == (['sea', 'sea'] if entrypoint == 'world' else [])  # the sea plane is the world's


@pytest.mark.parametrize('initial', ['new', 'stale-slots', 'stale-lods'])
@pytest.mark.parametrize('save_succeeds', [True, False])
def test_treehouse_trees_seed_from_existing_fbx_before_reimport(importer, monkeypatch, tmp_path, initial, save_succeeds):
    """Run the real tree owner and FBX adapter, including missing-source reimport failure."""
    p = importer
    scripts = Path(__file__).resolve().parents[1] / 'unreal/Scripts'
    package = '/Game/Japan/Assets/Tree_Treehouse'
    source = tmp_path / 'treehouse/trees'
    source.mkdir(parents=True)
    (source / 'trees.json').write_text(json.dumps({
        'Tree_Treehouse': dict(slot='LeafAmber', leaf='LeafAmber', crown_hi=12.0),
    }))
    (source / 'Tree_Treehouse.fbx').touch()
    seed = tmp_path / 'village/assets/Village_Sign.fbx'
    seed.parent.mkdir(parents=True)
    seed.touch()

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
    monkeypatch.setattr(Mesh, 'set_num_source_models', lambda self, count: setattr(self, 'lods', count), raising=False)
    monkeypatch.setattr(Mesh, 'get_bounding_box', lambda self: SimpleNamespace(max=SimpleNamespace(z=self.centimetres)), raising=False)
    if initial != 'new':
        stale = p.assets[package] = Mesh(ImportData())
        stale.static_materials = [Slot('Bark'), Slot('OldLeaf' if initial == 'stale-slots' else 'LeafAmber')]
        stale.lods = 2 if initial == 'stale-lods' else 1
    p.source_slots.update({'Village_Sign.fbx': [Slot('VillagePalette')],
                          'Tree_Treehouse.fbx': [Slot('Bark'), Slot('LeafAmber')]})
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
    monkeypatch.setattr(sys, 'path', list(sys.path))
    for name, module in {'yori': SimpleNamespace(OUT=tmp_path), 'atmosphere': SimpleNamespace(),
                         'see_through': SimpleNamespace(), 'mesh_import': p.module}.items():
        monkeypatch.setitem(sys.modules, name, module)
    # This commandlet runs main() unconditionally; load its real definitions without
    # importing unrelated room meshes and material graphs.
    script = scripts / 'import_treehouse.py'
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
    report = {}
    for _ in range(2):
        owner['trees'](report)
        mesh = p.assets[package]
        assert mesh.centimetres == 1200 and mesh.get_num_lods() == 1
        assert [slot.values['imported_material_slot_name'] for slot in mesh.static_materials] == ['Bark', 'LeafAmber']
        assert [slot.values['material_interface'] for slot in mesh.static_materials] == list(materials.values())
        assert saved[-1] is mesh
    assert [name for name, _, _ in p.calls] == ['Village_Sign.fbx', 'Tree_Treehouse.fbx', 'Tree_Treehouse.fbx']
    assert deleted == ([] if initial == 'new' else [package])
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


def test_world_without_city_retains_terrain_import_binding_and_collision(tmp_path, monkeypatch):
    import os
    scripts = Path(__file__).resolve().parents[1] / 'unreal/Scripts'
    script = scripts / 'setup_project.py'
    tree = ast.parse(script.read_text())
    body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main']
    (tmp_path / 'world.json').write_text('{}')
    collision, calls = {}, []
    mesh = SimpleNamespace(get_editor_property=lambda name: SimpleNamespace(set_editor_property=collision.__setitem__))
    forest = SimpleNamespace(get_editor_property=lambda name: object())
    unreal = SimpleNamespace(CollisionTraceFlag=SimpleNamespace(CTF_USE_COMPLEX_AS_SIMPLE='complex'))
    library = SimpleNamespace(load_asset=lambda path: mesh if path == '/Game/Japan/Terrain' else None,
                              save_loaded_asset=lambda asset: calls.append(('save', asset)))
    monkeypatch.delenv('JAPAN_ONLY', raising=False)
    rock = object()
    def coast_rock_instance():
        calls.append(('rock', rock))
        return rock
    monkeypatch.setitem(sys.modules, 'forest_ground', SimpleNamespace(coast_instance=lambda *args: object(),
                                                                   coast_rock_instance=coast_rock_instance))
    monkeypatch.setitem(sys.modules, 'import_southwest', SimpleNamespace(sea_plane=lambda: calls.append(('sea',))))
    monkeypatch.setattr(runpy, 'run_path', lambda *args, **kwargs: {})
    owner = dict(__file__=str(script), OUT=str(tmp_path), os=os,
                 glob=SimpleNamespace(glob=lambda pattern: []), EAL=library, unreal=unreal, FOLIAGE=set(),
                 purge=lambda: pytest.fail("Upfront purge would destroy reusable packages"), material_bindings=lambda: {}, instance=lambda *args: forest,
                 forest_ground_material=lambda: object(),
                 import_fbx=lambda *args: calls.append(('import', *args)),
                 assign=lambda *args: calls.append(('bind', *args)),
                 build_level=lambda terrain, *args: calls.append(('level', terrain)))
    exec(compile(ast.Module(body=body, type_ignores=[]), str(script), 'exec'), owner)
    owner['main']()
    assert [c[0] for c in calls] == ['rock', 'import', 'bind', 'save', 'sea', 'level']
    assert calls[1][1:] == (str(tmp_path / 'terrain.fbx'), '/Game/Japan', 'Terrain')
    assert calls[2][1] == '/Game/Japan/Terrain' and calls[2][2]['CoastRock'] is rock
    assert calls[-1][1] is mesh and calls[-3][1] is mesh  # level and terrain save; the sea plane between
    assert collision == {'collision_trace_flag': 'complex'}


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
