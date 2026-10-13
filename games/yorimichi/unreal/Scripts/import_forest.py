"""Import the Tuscan leaf-card library and its explicitly authored HISM LODs."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'world'))
import yori  # noqa: E402
import json
import unreal as U
from import_village import import_mesh
from import_foliage_lods import main as import_lods
from foliage_material import enable_bark_lod_blend
import forest_impostor_material


def main():
    E=U.EditorAssetLibrary;M=U.MaterialEditingLibrary;AT=U.AssetToolsHelpers.get_asset_tools()
    U.SystemLibrary.execute_console_command(None,'Interchange.FeatureFlags.Import.FBX 0')
    output=yori.OUT/'forest'
    foliage=E.load_asset('/Game/Japan/Materials/M_Foliage');assert foliage
    for slot in ['Bark','BarkOlive']:
        bark=E.load_asset('/Game/Japan/Materials/MI_'+slot);assert bark,slot
        enable_bark_lod_blend(bark);E.save_loaded_asset(bark)
    for slot,entry in json.loads((output/'textures/textures.json').read_text()).items():
        task=U.AssetImportTask();task.filename=str(output/'textures'/entry['file'])
        task.destination_path='/Game/Japan/Textures';task.destination_name='T_'+slot
        task.automated=True;task.replace_existing=True;task.save=True;AT.import_asset_tasks([task])
        texture=E.load_asset('/Game/Japan/Textures/T_'+slot);assert texture
        texture.set_editor_property('srgb',True);texture.set_editor_property('max_texture_size',1024)
        texture.set_editor_property('do_scale_mips_for_alpha_coverage',True)
        texture.set_editor_property('alpha_coverage_thresholds',U.Vector4(0,0,0,.333))
        E.save_loaded_asset(texture)
        path='/Game/Japan/Materials/MI_'+slot
        mi=E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset('MI_'+slot,'/Game/Japan/Materials',U.MaterialInstanceConstant,U.MaterialInstanceConstantFactoryNew())
        M.set_material_instance_parent(mi,foliage);M.set_material_instance_texture_parameter_value(mi,'Tex',texture)
        M.update_material_instance(mi);E.save_loaded_asset(mi)
    report={}
    trees=json.loads((output/'trees.json').read_text())
    first=next(iter(trees.values()))
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
        mesh=import_mesh(output/(name+'.fbx'),'/Game/Japan/Assets',name,fresh_slots=True)
        for i,slot in enumerate(mesh.get_editor_property('static_materials')):
            key=str(slot.get_editor_property('imported_material_slot_name')).split('.')[0]
            material=E.load_asset('/Game/Japan/Materials/MI_'+key);assert material,(name,key)
            mesh.set_material(i,material)
        height=mesh.get_bounding_box().max.z/100
        assert abs(height-entry['height'])<.05,(name,height,entry['height'])
        mesh.set_editor_property('allow_cpu_access',False)
        mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',U.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
        E.save_loaded_asset(mesh);report[name]={'height_m':height,'triangles':mesh.get_num_triangles(0)}
    import_lods(output=output,manifest_file='trees.json',shared_materials=False)
    (output/'import-report.json').write_text(json.dumps(report,indent=2)+'\n')
    U.log('FOREST IMPORT COMPLETE: '+json.dumps(report))


if __name__=='__main__':main()
