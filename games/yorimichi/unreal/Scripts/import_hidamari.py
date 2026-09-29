"""Import only the eastern city plus refreshed terrain backdrop, preserving gameplay assets."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json,sys,os
from pathlib import Path
import unreal
sys.path.insert(0,str(Path(__file__).resolve().parent))
from import_village import import_mesh,material
from mountain_material import material as mountain_material
from harbor_material import material as harbor_material
from arcade_material import material as arcade_material
from plaza_material import water_material,paving_material
ROOT = yori.OUT;OUT=ROOT/'hidamari'
unreal.SystemLibrary.execute_console_command(None,'Interchange.FeatureFlags.Import.FBX 0')
mat=unreal.EditorAssetLibrary.load_asset('/Game/Japan/Materials/M_Village') or material()
manifest=json.loads((OUT/'manifest.json').read_text());only=set(filter(None,os.environ.get('HIDAMARI_ASSETS','').split(',')))
arcade_mat=arcade_material() if not only or any(n.startswith(('HD_Arcade','HD_Plaza','HD_Shop_')) or n in ['HD_ClockHall','HD_Square','HD_Station','HD_Shrine','HD_Park','HD_Streets','HD_CivicGardens'] for n in only) else None
paving_mat=arcade_material(paving=True) if not only or only & {'HD_ArcadeFloor','HD_PlazaFloor'} else None
plaza_paving=paving_material() if not only or 'HD_PlazaFloor' in only else None
plaza_water=water_material() if not only or 'HD_PlazaWater' in only else None
pond_water=water_material('M_PondWater') if not only or 'HD_InlandWater' in only else None
harbor_mat=harbor_material() if not only or only & {'HD_Harbor','HD_Boat'} else None
water_mat=harbor_material(water=True) if not only or 'HD_Sea' in only else None
report=json.loads((OUT/'import-report.json').read_text()) if only and (OUT/'import-report.json').exists() else {}
mountain_mat=mountain_material() if not only or any(n.startswith('HD_North') for n in only) else None
def distance_lods(mesh,name,levels):
    """Reduce render geometry only; retain authored UCX and LOD0 complex collision."""
    unreal.load_module('StaticMeshEditor')
    subsystem=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    assert subsystem is not None,'StaticMeshEditor subsystem is unavailable'
    original_collision=(subsystem.get_simple_collision_count(mesh),subsystem.get_convex_collision_count(mesh))
    original_triangles=mesh.get_num_triangles(0)
    options=unreal.StaticMeshReductionOptions()
    options.set_editor_property('auto_compute_lod_screen_size',False)
    settings=[]
    for fraction,size in levels:
        level=unreal.StaticMeshReductionSettings()
        level.set_editor_property('percent_triangles',fraction)
        level.set_editor_property('screen_size',size)
        settings.append(level)
    options.set_editor_property('reduction_settings',settings)
    count=len(levels)
    assert subsystem.set_lods(mesh,options)==count,(name,'LOD generation')
    assert subsystem.get_lod_count(mesh)==count,(name,'missing LOD')
    screen_sizes=[size for _,size in levels]
    assert subsystem.set_lod_screen_sizes(mesh,screen_sizes),(name,'LOD screen sizes')
    mesh.set_editor_property('lod_for_collision',0)
    collision=(subsystem.get_simple_collision_count(mesh),subsystem.get_convex_collision_count(mesh))
    result={'count':subsystem.get_lod_count(mesh),
            'vertices':[subsystem.get_number_verts(mesh,i) for i in range(count)],
            'triangles':[mesh.get_num_triangles(i) for i in range(count)],
            'screen_sizes':list(subsystem.get_lod_screen_sizes(mesh)),
            'collision_lod':mesh.get_editor_property('lod_for_collision'),
            'simple_collision_count':collision[0],'convex_collision_count':collision[1]}
    assert all(n>0 for n in result['vertices']),(name,'empty LOD')
    assert all(a>b for a,b in zip(result['vertices'],result['vertices'][1:])),(name,'LOD reduction failed',result)
    assert result['triangles'][0]==original_triangles,(name,'LOD0 changed')
    assert len(result['screen_sizes'])==count
    assert all(abs(a-b)<1e-5 for a,b in zip(result['screen_sizes'],screen_sizes)),(name,'incorrect LOD screen sizes',result)
    assert collision==original_collision,(name,'authored collision changed',original_collision,collision)
    assert result['collision_lod']==0,(name,'complex collision must use original geometry')
    unreal.log('DISTANCE LODS '+name+' '+str(result))
    return result


for name,entry in manifest.items():
    if only and name not in only:continue
    mesh=import_mesh(OUT/'assets'/f'{name}.fbx','/Game/Japan/Assets',name)
    if name.startswith('HD_North'): selected=mountain_mat
    elif name=='HD_Sea': selected=water_mat
    elif name in ('HD_Harbor','HD_Boat'): selected=harbor_mat
    elif name=='HD_PlazaWater': selected=plaza_water
    elif name=='HD_InlandWater': selected=pond_water
    elif name=='HD_PlazaFloor': selected=plaza_paving
    elif name=='HD_ArcadeFloor': selected=paving_mat
    elif name.startswith(('HD_Arcade','HD_Plaza','HD_Shop_')) or name in ('HD_ClockHall','HD_Square','HD_Station','HD_Shrine','HD_Park','HD_Streets','HD_CivicGardens'): selected=arcade_mat
    else: selected=mat
    assert selected,(name,'missing material')
    mesh.set_material(0,selected)
    lod_report=None
    if name=='HD_NorthTreeBackdropPine':
        # The simple pine reaches the reduction floor in its second LOD.
        lod_report=distance_lods(mesh,name,[(1.,1.),(.25,.06)])
    elif name.startswith('HD_NorthTree'):
        # Keep close silhouettes; simplify sub-pixel distant crowns instead of culling them.
        lod_report=distance_lods(mesh,name,[(1.,1.),(.25,.06),(.08,.03)])
    elif (name.startswith('HD_Shop_') and name[8:].isdigit()) or name in ('HD_Station','HD_Shrine'):
        # Full detail close up, progressively lighter street and distant skyline geometry.
        lod_report=distance_lods(mesh,name,[(1.,1.),(.5,.28),(.15,.12),(.04,.05)])
    body=mesh.get_editor_property('body_setup')
    body.set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE if not entry['collision_boxes'] else unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AND_COMPLEX)
    box=mesh.get_bounding_box()
    assert abs(box.max.z-entry['max'][2]*100)<.3,(name,'unit conversion',box.max.z)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    report[name]={'imported':True,'triangles':entry['triangles'],'max_z_cm':box.max.z,'material':selected.get_path_name()}
    if lod_report:report[name]['lods']=lod_report
if not only or os.environ.get('HIDAMARI_TERRAIN')=='1':
    mesh=import_mesh(ROOT/'terrain.fbx','/Game/Japan','Terrain')
    for i,slot in enumerate(mesh.static_materials):
        key=str(slot.get_editor_property('imported_material_slot_name')).split('.')[0]
        mat=unreal.EditorAssetLibrary.load_asset('/Game/Japan/Materials/MI_'+key)
        assert mat,key
        mesh.set_material(i,mat)
    mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)
(OUT/'import-report.json').write_text(json.dumps(report,indent=2)+'\n')
unreal.log('HIDAMARI IMPORT COMPLETE')
