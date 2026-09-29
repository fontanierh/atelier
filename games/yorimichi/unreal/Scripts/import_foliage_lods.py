"""Add explicit LODs to existing foliage, preserving LOD0, materials and collision."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json
from pathlib import Path
import sys
import unreal as U

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from foliage_material import enable_distance_fade, enable_bark_lod_blend, supports_lod_blend


def verify_lods(target,screen_sizes,meshes):
    name=target.get_name()
    count=target.get_num_lods()
    assert count==len(screen_sizes),(name,'missing LOD')
    actual=list(meshes.get_lod_screen_sizes(target))
    assert all(abs(a-b)<1e-5 for a,b in zip(actual,screen_sizes)),(name,'LOD distances')
    slots=[s.get_editor_property('material_interface') for s in target.get_editor_property('static_materials')]
    assert all(m and supports_lod_blend(m) for m in slots),(name,'a material disables HISM blending')
    palettes=[]
    for level in range(count):
        palettes.append(sorted({target.get_material(meshes.get_lod_material_slot(target,level,section)).get_path_name()
                                for section in range(target.get_num_sections(level))}))
    assert all(p==palettes[0] for p in palettes),(name,'LOD changes the source palette',palettes)
    return {'vertices':[meshes.get_number_verts(target,i) for i in range(count)],
            'screen_sizes':actual,'materials_by_lod':palettes,'all_slots_blend':True}


def main(names=None):
    output=yori.OUT/'foliage_lods'
    manifest=json.loads((output/'manifest.json').read_text())
    if names is not None: manifest={name:manifest[name] for name in names}
    assets=U.AssetToolsHelpers.get_asset_tools()
    editor=U.EditorAssetLibrary
    U.load_module('StaticMeshEditor')
    meshes=U.get_editor_subsystem(U.StaticMeshEditorSubsystem)
    if meshes is None: raise RuntimeError('StaticMeshEditor subsystem is unavailable')
    report=json.loads((output/'import.json').read_text()) if names is not None and (output/'import.json').exists() else {}
    for name,data in manifest.items():
        target=editor.load_asset('/Game/Japan/Assets/'+name)
        if not target: raise RuntimeError('Missing detailed foliage: '+name)
        original_vertices=meshes.get_number_verts(target,0)
        lod_count=len(data['screen_sizes'])
        for level in range(1,lod_count):
            lod_name=f'{name}_LOD{level}'
            task=U.AssetImportTask()
            task.set_editor_property('filename',str(output/(lod_name+'.fbx')))
            task.set_editor_property('destination_path','/Game/Japan/FoliageLODs')
            task.set_editor_property('destination_name',lod_name)
            task.set_editor_property('automated',True)
            task.set_editor_property('replace_existing',True)
            task.set_editor_property('save',True)
            options=U.FbxImportUI()
            options.set_editor_property('automated_import_should_detect_type',False)
            options.set_editor_property('mesh_type_to_import',U.FBXImportType.FBXIT_STATIC_MESH)
            options.set_editor_property('import_materials',False)
            options.set_editor_property('import_textures',False)
            info=options.get_editor_property('static_mesh_import_data')
            info.set_editor_property('combine_meshes',True)
            info.set_editor_property('auto_generate_collision',False)
            info.set_editor_property('normal_import_method',U.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
            info.set_editor_property('vertex_color_import_option',U.VertexColorImportOption.REPLACE)
            task.set_editor_property('options',options)
            assets.import_asset_tasks([task])
            source=editor.load_asset('/Game/Japan/FoliageLODs/'+lod_name)
            if not source: raise RuntimeError('LOD import failed: '+lod_name)
            for index,slot in enumerate(source.get_editor_property('static_materials')):
                key=str(slot.get_editor_property('imported_material_slot_name')).split('.')[0]
                material=editor.load_asset('/Game/Japan/Materials/MI_'+key)
                if not material: raise RuntimeError('LOD material missing: '+key)
                source.set_material(index,material)
            editor.save_loaded_asset(source)
            assert meshes.set_lod_from_static_mesh(target,level,source,0,True)==level
        assert meshes.set_lod_screen_sizes(target,data['screen_sizes'])
        assert meshes.get_number_verts(target,0)==original_vertices,'LOD0 changed'
        assert target.get_num_lods()==lod_count
        editor.save_loaded_asset(target)
    foliage=editor.load_asset('/Game/Japan/Materials/M_Foliage')
    enable_distance_fade(foliage)
    U.MaterialEditingLibrary.recompile_material(foliage)
    editor.save_loaded_asset(foliage)
    bark=editor.load_asset('/Game/Japan/Materials/MI_Bark')
    if not bark: raise RuntimeError('Bark material is missing')
    enable_bark_lod_blend(bark)
    editor.save_loaded_asset(bark)
    for name,data in manifest.items():
        report[name]=verify_lods(editor.load_asset('/Game/Japan/Assets/'+name),data['screen_sizes'],meshes)
    (output/'import.json').write_text(json.dumps(report,indent=2)+'\n')
    U.log('FOLIAGE LOD IMPORT COMPLETE: '+json.dumps(report))


if __name__ == '__main__': main()
