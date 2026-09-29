"""Explicit meter-to-centimeter FBX import for isolated experimental meshes."""
import unreal as U


def import_static_mesh(assets, path, destination, name):
    task = U.AssetImportTask()
    for key,value in dict(filename=str(path),destination_path=destination,destination_name=name,
                          automated=True,replace_existing=False,save=True).items():
        task.set_editor_property(key,value)
    options = U.FbxImportUI()
    for key,value in dict(automated_import_should_detect_type=False,
                          mesh_type_to_import=U.FBXImportType.FBXIT_STATIC_MESH,
                          import_materials=False,import_textures=False).items():
        options.set_editor_property(key,value)
    data = options.get_editor_property('static_mesh_import_data')
    # The legacy FBX defaults do NOT convert the file's meters to Unreal cm.
    # Interchange/other importers can have different defaults. Never inherit them.
    for key,value in dict(convert_scene=True,convert_scene_unit=True,import_uniform_scale=1.,
                          combine_meshes=True,auto_generate_collision=False,
                          normal_import_method=U.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS,
                          vertex_color_import_option=U.VertexColorImportOption.REPLACE).items():
        data.set_editor_property(key,value)
    task.set_editor_property('options',options)
    assets.import_asset_tasks([task])
    mesh = U.EditorAssetLibrary.load_asset(destination+'/'+name)
    if not mesh: raise RuntimeError('import failed: '+str(path))
    return mesh
