"""Geometry-only imports must not generate a temporary material/rename workload."""
import sys
from types import SimpleNamespace as NS
import pytest
from atelier.interchange_mesh import import_static_mesh


class Properties:
    def __init__(self, **values): self.values = values
    def get_editor_property(self, name): return self.values[name]
    def set_editor_property(self, name, value): self.values[name] = value


@pytest.fixture
def scene(monkeypatch):
    class Generic(Properties):
        def __init__(self):
            super().__init__(mesh_pipeline=Properties(), animation_pipeline=Properties(),
                             material_pipeline=Properties(texture_pipeline=Properties()))
    class Mesh: pass
    class Stack:
        def __init__(self): self.pipelines = []
        def add_pipeline(self, pipeline): self.pipelines.append(pipeline)
    tasks, loaded = [], []
    result = Mesh()
    def execute(items):
        tasks.extend(items)
        for task in items:
            task.imported_object_paths = [task.destination_path + '/' + task.destination_name + '.' + task.destination_name]
    def load(path):
        loaded.append(path)
        return result
    unreal = NS(InterchangeGenericAssetsPipeline=Generic, StaticMesh=Mesh,
        InterchangePipelineStackOverride=Stack, InterchangeGLTFPipeline=lambda: object(),
        InterchangeCombineStaticMeshesBehavior=NS(ALL='ALL'), AssetImportTask=NS,
        AssetToolsHelpers=NS(get_asset_tools=lambda: NS(import_asset_tasks=execute)),
        EditorAssetLibrary=NS(load_asset=load))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    return NS(unreal=unreal, result=result, tasks=tasks, loaded=loaded)


def test_direct_final_mesh_import_does_not_need_rename_or_delete_api(scene):
    assert import_static_mesh('source.glb', '/Game/Owned/Meshes', 'SM_Mesh') is scene.result
    task, = scene.tasks
    generic, _ = task.options.pipelines
    assert generic.values['asset_name'] == 'SM_Mesh'
    assert generic.values['material_pipeline'].values['import_materials'] is False
    assert generic.values['material_pipeline'].values['texture_pipeline'].values['import_textures'] is False
    assert scene.loaded == ['/Game/Owned/Meshes/SM_Mesh']
    assert task.save is True and task.automated is True and task.replace_existing is True


@pytest.mark.parametrize('paths', [[], ['/Game/Owned/Meshes/Other.Other'],
    ['/Game/Owned/Meshes/SM_Mesh.SM_Mesh', '/Game/Owned/Temp/Material.Material']])
def test_missing_or_unexpected_import_products_fail_before_owner_finishing(scene, paths):
    def execute(items):
        items[0].imported_object_paths = paths
    scene.unreal.AssetToolsHelpers.get_asset_tools = lambda: NS(import_asset_tasks=execute)
    with pytest.raises(RuntimeError, match='Unexpected'):
        import_static_mesh('source.glb', '/Game/Owned/Meshes', 'SM_Mesh')
    assert scene.loaded == []


def test_wrong_native_class_is_not_success(scene):
    scene.unreal.EditorAssetLibrary.load_asset = lambda _: object()
    with pytest.raises(RuntimeError, match='static mesh'):
        import_static_mesh('source.glb', '/Game/Owned/Meshes', 'SM_Mesh')


@pytest.mark.parametrize('root,name', [('/Game', 'Mesh'), ('/Game/Owned/../Other', 'Mesh'),
    ('/Other/Owned', 'Mesh'), ('/Game/Owned', '../Other'), ('/Game/Owned', '')])
def test_invalid_owner_names_refuse_before_native_import(scene, root, name):
    with pytest.raises(ValueError, match='destination'):
        import_static_mesh('source.glb', root, name)
    assert scene.tasks == []
