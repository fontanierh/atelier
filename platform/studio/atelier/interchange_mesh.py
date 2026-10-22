"""Geometry-only Interchange imports for owners that author their own materials."""
import re
from pathlib import Path


def import_static_mesh(source, destination, name):
    """@cc [owner:fontanierh,label:correctness;performance] geometry-only-native-import
    An owner supplying its own materials MUST import its combined static mesh directly
    at its final path without creating throwaway materials/textures or rename redirectors.
    Geometry options and source material-slot identities MUST remain intact. Returned
    paths MUST identify exactly the requested saved mesh; unexpected products MUST fail.
    This helper MUST NOT delete existing packages or alter another owner's materials.
    """
    import unreal
    if (not re.fullmatch(r'/Game(?:/[A-Za-z0-9_]+)+', destination)
            or not re.fullmatch(r'[A-Za-z0-9_]+', name)):
        raise ValueError('Invalid owned mesh destination')
    generic = unreal.InterchangeGenericAssetsPipeline()
    generic.set_editor_property('asset_name', name)
    material = generic.get_editor_property('material_pipeline')
    material.set_editor_property('import_materials', False)
    material.get_editor_property('texture_pipeline').set_editor_property('import_textures', False)
    mesh = generic.get_editor_property('mesh_pipeline')
    mesh.set_editor_property('import_static_meshes', True)
    mesh.set_editor_property('import_skeletal_meshes', False)
    mesh.set_editor_property('combine_static_meshes_behavior', unreal.InterchangeCombineStaticMeshesBehavior.ALL)
    mesh.set_editor_property('build_nanite', False)
    generic.get_editor_property('animation_pipeline').set_editor_property('import_animations', False)
    stack = unreal.InterchangePipelineStackOverride()
    stack.add_pipeline(generic)
    stack.add_pipeline(unreal.InterchangeGLTFPipeline())
    task = unreal.AssetImportTask()
    task.filename = str(Path(source))
    task.destination_path = destination
    task.destination_name = name
    task.options = stack
    task.automated = True
    task.replace_existing = True
    task.save = True
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    target = destination + '/' + name
    expected = target + '.' + name
    if list(map(str, task.imported_object_paths)) != [expected]:
        raise RuntimeError(f'Unexpected geometry-only import products for {name}: {task.imported_object_paths}')
    result = unreal.EditorAssetLibrary.load_asset(target)
    if not isinstance(result, unreal.StaticMesh):
        raise RuntimeError('Geometry-only import did not produce the requested static mesh: ' + name)
    return result
