"""Model UE's stored-data reimport precedence; native equivalence remains a separate gate."""
import importlib.util
from pathlib import Path
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


@pytest.fixture
def importer(monkeypatch, tmp_path):
    assets, calls = {}, []

    def execute(tasks):
        for task in tasks:
            package = task.destination_path + '/' + task.destination_name
            mesh = assets.get(package)
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
                           seed=tmp_path / 'seed.fbx', package='/Game/Owned/Mesh')


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
