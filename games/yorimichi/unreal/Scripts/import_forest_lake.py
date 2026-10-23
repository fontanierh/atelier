"""Receive only current independent lake pieces; the island owner receives terrain."""
import sys
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[2]/'world'),str(Path(__file__).resolve().parent)]
import yori  # noqa: E402
import hashlib
import json
import unreal
from mesh_import import import_mesh
from atelier.export_manifest import real_directory
import forest_lake_material
import lake_native


def main():
    root=yori.OUT/'forest_lake';E=unreal.EditorAssetLibrary
    real_directory(root/'assets')
    value=lake_native.read(root)
    if value.get('schema')!=2 or value.get('complete') is not True or set(value['parents'])!=set(lake_native.OWNERS):
        raise ValueError('Lake requires complete current logical membership')
    names=[name for parent in lake_native.OWNERS for name in value['parents'][parent]]
    if len(names)!=len(set(names)) or set(names)!=set(value['assets']) or any(not lake_native.owned(n) for n in names):
        raise ValueError('Invalid current lake piece inventory')
    previous=lake_native.inventory(E)
    unreal.SystemLibrary.execute_console_command(None,'Interchange.FeatureFlags.Import.FBX 0')
    unreal.load_module('StaticMeshEditor')
    editor=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    material=E.load_asset('/Game/Japan/Materials/M_Village');assert material
    water=forest_lake_material.create()
    report={}
    for name in names:
        row=value['assets'][name]
        if (row['parent'] not in lake_native.OWNERS or name not in value['parents'][row['parent']]
                or not (name==row['parent'] or name.startswith(row['parent']+'_cell_'))
                or row['fbx']!='assets/'+name+'.fbx' or type(row['triangles']) is not int
                or not 0<row['triangles']<=32768):
            raise ValueError('Lake piece belongs to a different logical asset')
        source=root/row['fbx']
        if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('Lake export changed')
        mesh=import_mesh(source,lake_native.DEST,name,fresh_slots=True)
        mesh.set_num_source_models(1)
        if mesh.get_num_triangles(0)!=row['triangles'] or editor.get_num_uv_channels(mesh,0)!=1:
            raise ValueError('Current lake geometry/UV inventory differs: '+name)
        if len(mesh.static_materials)!=1:raise ValueError('Lake palette grouping changed: '+name)
        if str(mesh.static_materials[0].get_editor_property('imported_material_slot_name'))!='LakePalette':
            raise ValueError('Lake source material identity changed: '+name)
        bounds=mesh.get_bounding_box()
        lower=[row['min'][0]*100.,-row['max'][1]*100.,row['min'][2]*100.]
        upper=[row['max'][0]*100.,-row['min'][1]*100.,row['max'][2]*100.]
        for axis,lo,hi in zip(('x','y','z'),lower,upper):
            if abs(getattr(bounds.min,axis)-lo)>.1 or abs(getattr(bounds.max,axis)-hi)>.1:
                raise ValueError('Lake current bounds changed: '+name)
        mesh.set_material(0,water if row['parent']=='Lake_Water' else material)
        settings=editor.get_lod_build_settings(mesh,0)
        if settings.get_editor_property('use_full_precision_u_vs'):
            settings.set_editor_property('use_full_precision_u_vs',False);editor.set_lod_build_settings(mesh,0,settings)
        assert not editor.get_lod_build_settings(mesh,0).get_editor_property('use_full_precision_u_vs')
        body=mesh.get_editor_property('body_setup');assert body
        body.set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        assert unreal.CitySurfaceValidation.validate_collision(mesh,row['triangles'],False),(name,'current cooked LOD0 query')
        assert E.save_loaded_asset(mesh),(name,'save failed')
        report[name]=dict(parent=row['parent'],triangles=mesh.get_num_triangles(0),materials=1,
                          uv_channels=editor.get_num_uv_channels(mesh,0),full_precision=False)
    retired=lake_native.retire(E,previous,names,yori.GAME/'unreal/Content')
    (root/'import-report.json').write_text(json.dumps(dict(meshes=report,retired=retired),indent=2)+'\n')
    unreal.log('LAKE IMPORT COMPLETE')


if __name__=='__main__':main()
