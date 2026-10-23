"""Import the Tuscan leaf-card library and its explicitly authored HISM LODs."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'world'))
import yori  # noqa: E402
import json
import unreal as U
sys.path.insert(0,str(Path(__file__).resolve().parent))
from mesh_import import import_mesh
import import_foliage_lods
import forest_native
from foliage_slots import restore_authored_slots
import forest_impostor_material
from asset_catalog import check_material_namespace


def main():
    E=U.EditorAssetLibrary;M=U.MaterialEditingLibrary;AT=U.AssetToolsHelpers.get_asset_tools()
    U.SystemLibrary.execute_console_command(None,'Interchange.FeatureFlags.Import.FBX 0')
    previous=forest_native.inventory(E)
    output=yori.OUT/'forest/assembled'
    source_textures=yori.OUT/'forest/textures'
    foliage=E.load_asset('/Game/Japan/Materials/M_Foliage');assert foliage
    textures = json.loads((source_textures/'textures.json').read_text())
    check_material_namespace(textures, 'forest')
    for slot,entry in textures.items():
        task=U.AssetImportTask();task.filename=str(source_textures/entry['file'])
        task.destination_path='/Game/Japan/Textures';task.destination_name='T_'+slot
        task.automated=True;task.replace_existing=True;task.save=True;AT.import_asset_tasks([task])
        texture=E.load_asset('/Game/Japan/Textures/T_'+slot);assert texture
        texture.set_editor_property('srgb',True);texture.set_editor_property('max_texture_size',1024)
        texture.set_editor_property('do_scale_mips_for_alpha_coverage',True)
        texture.set_editor_property('alpha_coverage_thresholds',U.Vector4(0,0,0,.4))
        E.save_loaded_asset(texture)
        path='/Game/Japan/Materials/MI_'+slot
        mi=E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset('MI_'+slot,'/Game/Japan/Materials',U.MaterialInstanceConstant,U.MaterialInstanceConstantFactoryNew())
        M.set_material_instance_parent(mi,foliage);M.set_material_instance_texture_parameter_value(mi,'Tex',texture)
        M.update_material_instance(mi);E.save_loaded_asset(mi)
    report={}
    trees=json.loads((output/'trees.json').read_text())
    forest_native.configure(trees)
    # Preserve the former declared-species default independently of sorted assembly JSON.
    first=trees['Tree_Tuscan_Cypress']
    task=U.AssetImportTask();task.filename=str(output/first['impostor']['atlases']['normal'])
    task.destination_path='/Game/Japan/Textures';task.destination_name='T_ForestNormalDefault'
    task.automated=True;task.replace_existing=True;task.save=True;AT.import_asset_tasks([task])
    normal=E.load_asset('/Game/Japan/Textures/T_ForestNormalDefault');assert normal
    normal.set_editor_property('srgb',False)
    normal.set_editor_property('compression_settings',U.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
    E.save_loaded_asset(normal)
    proxy_master=forest_impostor_material.parent(normal)
    for name,entry in trees.items():
        forest_impostor_material.instance(name,entry['impostor'],output,proxy_master)
        mesh=import_mesh(output/(name+'.fbx'),'/Game/Japan/Assets',name,fresh_slots=True,
                         before_import=lambda name=name:forest_native.prepare_source(name,'/Game/Japan/Assets'),
                         reuse_validator=forest_native.reusable_collision)
        mesh.set_num_source_models(1)
        restore_authored_slots(mesh,name)   # a reused base keeps its far crown's slot
        for i,slot in enumerate(mesh.get_editor_property('static_materials')):
            key=str(slot.get_editor_property('imported_material_slot_name')).split('.')[0]
            material=E.load_asset('/Game/Japan/Materials/MI_'+key);assert material,(name,key)
            mesh.set_material(i,material)
        height=mesh.get_bounding_box().max.z/100
        assert abs(height-entry['height'])<.05,(name,height,entry['height'])
        mesh.set_editor_property('allow_cpu_access',False)
        mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',U.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
        assert E.save_loaded_asset(mesh),(name,'base save failed')
        report[name]={'height_m':height,'triangles':mesh.get_num_triangles(0)}
    # The base and every source LOD share the SAME declared current reuse predicate.
    original=import_foliage_lods.import_mesh
    def source_lod(path,destination,name,**kwargs):
        return original(path,destination,name,**kwargs,
                        before_import=lambda:forest_native.prepare_source(name,destination))
    try:
        import_foliage_lods.import_mesh=source_lod
        U.load_module('StaticMeshEditor')
        meshes=U.get_editor_subsystem(U.StaticMeshEditorSubsystem)
        lod_report={}
        for name,data in trees.items():
            target=E.load_asset('/Game/Japan/Assets/'+name)
            lod_report[name]=import_foliage_lods.apply_lods(target,data,output,meshes,
                seed=None,folder='/Game/Japan/FoliageLODs',reuse_validator=forest_native.reusable_collision)
        native=yori.OUT/'forest/native';native.mkdir(parents=True,exist_ok=True)
        (native/'import.json').write_text(json.dumps(lod_report,indent=2)+'\n')
    finally:
        import_foliage_lods.import_mesh=original
    current=forest_native.validate_current(trees)
    retired=forest_native.retire(E,previous,current,yori.GAME/'unreal/Content')
    report['_retired']=retired
    (yori.OUT/'forest/import-report.json').write_text(json.dumps(report,indent=2)+'\n')
    U.log('FOREST IMPORT COMPLETE: '+json.dumps(report))


if __name__=='__main__':main()
