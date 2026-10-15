"""Model UE's stored-data reimport precedence; native equivalence remains a separate gate."""
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
        FBXImportType=SimpleNamespace(FBXIT_STATIC_MESH='static'),
        VertexColorImportOption=SimpleNamespace(REPLACE='replace'),
        FBXNormalImportMethod=SimpleNamespace(FBXNIM_IMPORT_NORMALS='normals'),
    )
    monkeypatch.setitem(sys.modules, 'unreal', fake)
    script = Path(__file__).resolve().parents[1] / 'unreal/Scripts/mesh_import.py'
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
    needs_seed = initial == 'interchange' or (initial == 'new' and not source_is_seed)
    assert [name for name, _, _ in p.calls] == (['seed.fbx'] if needs_seed else []) + [source.name]
    if previous is not None:
        assert mesh is previous
    if initial != 'new' or needs_seed:
        assert mesh.values['static_materials'] == []
    assert p.assets['/Game/Other/Mesh'] is unrelated and unrelated.centimetres is None
    p.calls.clear()
    assert p.module.import_mesh(source, '/Game/Owned', 'Mesh', seed=p.seed) is mesh
    assert p.calls == [(source.name, p.package, expected_size)]


def test_failed_seed_cannot_continue_to_the_final_source(importer, monkeypatch):
    p = importer
    calls = []
    monkeypatch.setattr(p.module, '_import_mesh', lambda *args: calls.append(args) or Mesh(object()))
    with pytest.raises(RuntimeError, match='establish legacy import data'):
        p.module.import_mesh(p.source, '/Game/Owned', 'Mesh', seed=p.seed)
    assert len(calls) == 1 and calls[0][0] == p.seed


@pytest.mark.parametrize('initial', ['new', 'interchange', 'legacy'])
def test_hidamari_terrain_reimport_replaces_seed_slots_and_keeps_terrain_materials(importer, monkeypatch, tmp_path, initial):
    """Run the real region owner, village adapter, FBX migration and material assignment."""
    p = importer
    scripts = Path(__file__).resolve().parents[1] / 'unreal/Scripts'
    terrain_package = '/Game/Japan/Terrain'
    names = ('Ground', 'Road', 'Sand')
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
    p.assets.update({'/Game/Japan/Materials/MI_' + name: material for name, material in materials.items()})
    p.assets['/Game/Japan/Materials/M_Village'] = object()
    saved, logs, sand_calls = [], [], []
    collision = {}
    original_execute = p.unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks
    def execute(tasks):
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
        'import_southwest': SimpleNamespace(sand_material=lambda: sand_calls.append('sand')),
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    for name in ('import_village', 'mesh_materials'):
        spec = importlib.util.spec_from_file_location(name, scripts / (name + '.py'))
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
    (tmp_path / 'hidamari').mkdir()
    (tmp_path / 'hidamari/manifest.json').write_text('{}')
    for _ in range(2):
        runpy.run_path(str(scripts / 'import_hidamari.py'), init_globals={'NORTH': False})
        mesh = p.assets[terrain_package]
        assert isinstance(mesh.values['asset_import_data'], ImportData)
        assert [slot.values['imported_material_slot_name'] for slot in mesh.static_materials] == list(names)
        assert [slot.values['material_interface'] for slot in mesh.static_materials] == list(materials.values())
        assert saved[-1] is mesh
    if previous is not None:
        assert mesh is previous
    assert [name for name, _, _ in p.calls] == ([] if initial == 'legacy' else ['Village_Sign.fbx']) + ['terrain.fbx'] * 2
    assert collision == {'collision_trace_flag': 'complex'}
    assert p.assets['/Game/Other/Mesh'] is unrelated and unrelated.centimetres is None
    assert json.loads((tmp_path / 'hidamari/import-report.json').read_text()) == {}
    assert sand_calls == ['sand', 'sand'] and logs == ['HIDAMARI IMPORT COMPLETE'] * 2
