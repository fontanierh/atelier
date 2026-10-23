"""Receive independently cached Bike meshes with one complete original steering joint."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402
import json
from pathlib import Path
import sys
import unreal

HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));sys.path.insert(0,str(yori.GAME))
from atelier import native_membership  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from bike_atomic_products import read,PARTS,STEERING,DESTINATION  # noqa: E402
from mesh_import import import_mesh  # noqa: E402
from bike_material import material  # noqa: E402


def receive(out=None):
    """@cc [owner:fontanierh,label:correctness;performance] receive-complete-independent-bike
    Admit untouched saved packages independently, preserving original legacy FBX options,
    M_Bike, half-precision UVs, wheel CPU support and default-trace zero-hull current LOD0
    cooked geometry. ALL eleven current pieces MUST validate and dirty-only save before
    old steering retirement. Persist exact actual render union bounds/true sphere on all
    four steering assets as complete cooked user data; no source sphere approximation.
    """
    root=Path(out) if out is not None else yori.OUT;manifest=read(root);library=unreal.EditorAssetLibrary
    # The flat shared Assets directory is not exclusive: inventory only this exact family.
    previous=native_membership.inventory(library,DESTINATION,'BK_')
    if previous-{DESTINATION+'/'+key for key in (*PARTS,'BK_Steer')}:raise ValueError('Foreign Bike native member')
    unreal.SystemLibrary.execute_console_command(None,'Interchange.FeatureFlags.Import.FBX 0')
    unreal.SystemLibrary.execute_console_command(None,'Editor.AsyncStaticMeshCompilation 0')
    unreal.load_module('StaticMeshEditor');editor=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem);assert editor
    mat=material();assert mat and library.save_loaded_asset(mat,True)
    meshes={};report={}
    for name in PARTS:
        entry=manifest['parts'][name];wheel=name in ('BK_WheelFront','BK_WheelRear')
        def valid(mesh,wheel=wheel,entry=entry):
            return (mesh.get_num_lods()==1 and mesh.get_num_triangles(0)==entry['triangles']
                and bool(mesh.get_editor_property('allow_cpu_access'))==wheel
                and not editor.get_lod_build_settings(mesh,0).get_editor_property('use_full_precision_u_vs')
                and unreal.BikeMeshComponent.validate_part(mesh,entry['triangles']))
        mesh=import_mesh(root/'bike/assets'/(name+'.fbx'),DESTINATION,name,fresh_slots=True,reuse_validator=valid)
        assert mesh.get_path_name().split('.')[0]==DESTINATION+'/'+name
        assert mesh.get_num_lods()==1 and mesh.get_num_triangles(0)==entry['triangles'],(name,'render geometry')
        assert len(mesh.static_materials)==1 and str(mesh.static_materials[0].get_editor_property('imported_material_slot_name'))=='BikePalette'
        if mesh.get_material(0)!=mat:mesh.set_material(0,mat)
        if wheel and not mesh.get_editor_property('allow_cpu_access'):mesh.set_editor_property('allow_cpu_access',True)
        assert bool(mesh.get_editor_property('allow_cpu_access'))==wheel,(name,'original wheel CPU support')
        assert editor.get_num_uv_channels(mesh,0)==1
        assert not editor.get_lod_build_settings(mesh,0).get_editor_property('use_full_precision_u_vs'),(name,'original UV precision')
        assert unreal.BikeMeshComponent.validate_part(mesh,entry['triangles']),(name,'current original cooked surface')
        bounds=mesh.get_bounding_box();expected_min=(entry['min'][0],-entry['max'][1],entry['min'][2]);expected_max=(entry['max'][0],-entry['min'][1],entry['max'][2])
        for actual,expected in ((bounds.min,expected_min),(bounds.max,expected_max)):
            assert all(abs(getattr(actual,axis)-target*100)<.3 for axis,target in zip(('x','y','z'),expected)),(name,'original axis/scale')
        meshes[name]=mesh;report[name]=dict(triangles=entry['triangles'],min=[bounds.min.x,bounds.min.y,bounds.min.z],max=[bounds.max.x,bounds.max.y,bounds.max.z])
    steering=[meshes[name] for name in STEERING]
    assert unreal.BikeMeshComponent.prepare_steering_bounds(steering),'Incomplete actual steering bounds'
    logical=json.loads(unreal.BikeMeshComponent.steering_bounds(steering))
    for name,mesh in meshes.items():assert library.save_loaded_asset(mesh,True),(name,'native save failed')
    return dict(out=root,parts=report,steering=logical,previous=previous)


def retire(received,*,runtime_members):
    if runtime_members!=list(PARTS):raise ValueError('Bike runtime physical consumers have not migrated completely')
    library=unreal.EditorAssetLibrary
    if set(received['parts'])!=set(PARTS):raise ValueError('Incomplete current Bike receiving set')
    retired=native_membership.retire_replaced(library,{DESTINATION+'/BK_Steer':[DESTINATION+'/'+key for key in STEERING]})
    content=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir()))
    folder=content/DESTINATION.removeprefix('/Game/');real_directory(folder)
    assert not list(folder.glob('BK_Steer.*')),'Old Bike steering parent remains physically saved'
    (received['out']/'bike/import-report.json').write_text(json.dumps(dict(complete=True,parts=received['parts'],steering_bounds=received['steering'],retired=retired),indent=2)+'\n')
    return retired


def main():
    received=receive();retire(received,runtime_members=list(PARTS));unreal.log('BIKE IMPORT COMPLETE')


if __name__=='__main__':main()
