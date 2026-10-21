"""Import only the eastern city plus refreshed terrain backdrop, preserving gameplay assets."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json,sys,os
from pathlib import Path
import unreal
sys.path.insert(0,str(Path(__file__).resolve().parent))
from import_village import import_mesh,material
from mesh_materials import assign_materials
from harbor_material import material as harbor_material
from arcade_material import material as arcade_material
from plaza_material import water_material,paving_material
import city_material
ROOT = yori.OUT;OUT=ROOT/'hidamari'
unreal.SystemLibrary.execute_console_command(None,'Interchange.FeatureFlags.Import.FBX 0')
manifest=json.loads((OUT/'manifest.json').read_text());asked=set(filter(None,os.environ.get('HIDAMARI_ASSETS','').split(',')))
# A name ending in * asks for every manifest asset it begins: unreal.north imports HD_North* (the volcano, its
# materials and textures). The world import (setup_project.py) runs this with NORTH=False and leaves those out.
only={a for a in asked if not a.endswith('*')}|{n for n in manifest for a in asked if a.endswith('*') and n.startswith(a[:-1])}
assert only or not asked,('no Hidamari assets match',sorted(asked))
north=globals().get('NORTH',True)
# Hidamari owns the final harbour package. Every world reimport uses the same audited rail opening.
harbor_source=None
if 'HD_Harbor' in manifest and (not only or 'HD_Harbor' in only):
    from regions.hidamari.ferry_source import validated_harbor
    harbor_source=validated_harbor(yori.OUT,yori.REPO)
mat=unreal.EditorAssetLibrary.load_asset('/Game/Japan/Materials/M_Village') or material()
arcade_mat=arcade_material() if not only or any(n.startswith(('HD_Arcade','HD_Plaza','HD_Shop_')) or n in ['HD_ClockHall','HD_Square','HD_Station','HD_Shrine','HD_Park','HD_Streets','HD_CivicGardens'] for n in only) else None
paving_mat=arcade_material(paving=True) if not only or only & {'HD_ArcadeFloor','HD_PlazaFloor'} else None
plaza_paving=paving_material() if not only or 'HD_PlazaFloor' in only else None
plaza_water=water_material() if not only or 'HD_PlazaWater' in only else None
pond_water=water_material('M_PondWater') if not only or 'HD_InlandWater' in only else None
harbor_mat=harbor_material() if not only or only & {'HD_Harbor','HD_Boat'} else None
water_mat=harbor_material(water=True) if not only or 'HD_Sea' in only else None
report=json.loads((OUT/'import-report.json').read_text()) if only and (OUT/'import-report.json').exists() else {}
# The textured city (world/regions/hidamari/surfaces.py): a manifest entry with slots has one per surface.
city_mis=city_material.materials() if any('slots' in e for n,e in manifest.items() if not only or n in only) else {}
if any('road' in e.get('slots',{}) for n,e in manifest.items() if not only or n in only):
    # The arrival road runs on from the island road in the island road's own material (shared_materials.py).
    city_mis['road']=unreal.EditorAssetLibrary.load_asset('/Game/Japan/Materials/MI_Road')
    assert city_mis['road'],'MI_Road (setup_project) must exist before the arrival road is imported'
mountain_mat=gate_mat=rock_mat=None
if north:
    from mountain_material import material as mountain_material,gate_material,rock_material
    mountain_mat=mountain_material() if not only or any(n.startswith('HD_North') for n in only) else None
    rock_mat=rock_material(mountain_mat) if mountain_mat else None
    gate_mat=gate_material() if not only or 'HD_NorthGate' in only else None
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
    # Small meshes bottom out (a 140-triangle pine keeps 180 vertices at LOD1 and LOD2): never grow, and end smaller.
    assert all(a>=b for a,b in zip(result['vertices'],result['vertices'][1:])) and result['vertices'][-1]<result['vertices'][0],(name,'LOD reduction failed',result)
    assert result['triangles'][0]==original_triangles,(name,'LOD0 changed')
    assert len(result['screen_sizes'])==count
    assert all(abs(a-b)<1e-5 for a,b in zip(result['screen_sizes'],screen_sizes)),(name,'incorrect LOD screen sizes',result)
    assert collision==original_collision,(name,'authored collision changed',original_collision,collision)
    assert result['collision_lod']==0,(name,'complex collision must use original geometry')
    unreal.log('DISTANCE LODS '+name+' '+str(result))
    return result


def prop_lods(mesh,name,mi,levels):
    """A fitted prop's authored distance LODs (props.json `lods`: [triangles, screen size] per LOD, world/regions/hidamari
    /props.py): <name>_LOD<n>.fbx imported under /Game/Japan/Hidamari/PropLODs/<name> with the prop's material, set as
    LOD n of the mesh, at its screen size. LOD0 and the mesh's (absent) collision stay as imported."""
    unreal.load_module('StaticMeshEditor')
    subsystem=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    assert subsystem is not None,'StaticMeshEditor subsystem is unavailable'
    if subsystem.get_lod_count(mesh)>1:mesh.set_num_source_models(1)   # a reimport keeps no stale LOD
    original=mesh.get_num_triangles(0)
    folder='/Game/Japan/Hidamari/PropLODs/'+name
    for level in range(1,len(levels)):
        source=import_mesh(OUT/'props'/f'{name}_LOD{level}.fbx',folder,f'{name}_LOD{level}',fresh_slots=True)
        assert len(source.static_materials)==1,(name,level,'material slots',len(source.static_materials))
        source.set_material(0,mi)
        assert unreal.EditorAssetLibrary.save_loaded_asset(source,False),(name,level,'save LOD source')
        assert subsystem.set_lod_from_static_mesh(mesh,level,source,0,True)==level,(name,level,'LOD')
    sizes=[float(size) for _,size in levels]
    assert subsystem.set_lod_screen_sizes(mesh,sizes),(name,'LOD screen sizes')
    result={'count':subsystem.get_lod_count(mesh),'triangles':[mesh.get_num_triangles(i) for i in range(len(levels))],
            'screen_sizes':list(subsystem.get_lod_screen_sizes(mesh))}
    assert result['count']==len(levels),(name,'missing LOD',result)
    assert result['triangles'][0]==original,(name,'LOD0 changed',result)
    # Unreal drops degenerate faces: within 2% of what Blender wrote, and each LOD lighter than the one before.
    assert all(abs(a-b)<=max(2,.02*b) for a,b in zip(result['triangles'],[t for t,_ in levels])),(name,'LOD triangles',result,levels)
    assert all(a>b for a,b in zip(result['triangles'],result['triangles'][1:])),(name,'LOD reduction',result)
    assert all(abs(a-b)<1e-5 for a,b in zip(result['screen_sizes'],sizes)),(name,'LOD screen sizes',result)
    unreal.log('PROP LODS '+name+' '+str(result))
    return result


for name,entry in manifest.items():
    if (only and name not in only) or (not north and name.startswith('HD_North')):continue
    if name == 'HD_Streets':
        # The independent production piece owner imports this source and retires
        # the old native parent only after complete saved-piece validation.
        report.pop(name, None)
        continue
    source=harbor_source if name=='HD_Harbor' else OUT/'assets'/f'{name}.fbx'
    mesh=import_mesh(source,'/Game/Japan/Assets',name,fresh_slots='slots' in entry)
    if name=='HD_NorthGate': selected=gate_mat
    elif name.startswith('HD_NorthRock'): selected=rock_mat
    elif name.startswith('HD_North'): selected=mountain_mat
    elif name=='HD_Sea': selected=water_mat
    elif name in ('HD_Harbor','HD_Boat'): selected=harbor_mat
    elif name=='HD_PlazaWater': selected=plaza_water
    elif name=='HD_InlandWater': selected=pond_water
    elif name=='HD_PlazaFloor': selected=plaza_paving
    elif name=='HD_ArcadeFloor': selected=paving_mat
    elif name.startswith(('HD_Arcade','HD_Plaza','HD_Shop_')) or name in ('HD_ClockHall','HD_Square','HD_Station','HD_Shrine','HD_Park','HD_Streets','HD_CivicGardens'): selected=arcade_mat
    else: selected=mat
    if 'slots' in entry:
        # Its UVs are metres (up to 1.4 km on the terrain): half-precision UVs would band the textures.
        unreal.load_module('StaticMeshEditor')
        lod_settings_subsystem=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        build=lod_settings_subsystem.get_lod_build_settings(mesh,0)
        if not build.get_editor_property('use_full_precision_u_vs'):
            build.set_editor_property('use_full_precision_u_vs',True);lod_settings_subsystem.set_lod_build_settings(mesh,0,build)
        slots=[]
        for slot in mesh.static_materials:
            key=str(slot.get_editor_property('imported_material_slot_name')).split('.')[0].removeprefix('HDS_')
            assert key in city_mis,(name,'unknown surface',key)
            slots.append(key)
        assert sorted(slots)==sorted(entry['slots']),(name,slots,sorted(entry['slots']))
        assign_materials(mesh,[city_mis[key] for key in slots])
        selected=city_mis[slots[0]]
    else:
        assert selected,(name,'missing material')
        mesh.set_material(0,selected)
    lod_report=None
    if (name.startswith('HD_Shop_') and name[8:].isdigit()) or name in ('HD_Station','HD_Shrine'):
        # Full detail close up, progressively lighter street and distant skyline geometry.
        lod_report=distance_lods(mesh,name,[(1.,1.),(.5,.28),(.15,.12),(.04,.05)])
    elif name.startswith('HD_House_'):
        # The back-lane houses are mostly seen over the shop roofs: drop detail sooner.
        lod_report=distance_lods(mesh,name,[(1.,1.),(.4,.3),(.12,.12)])
    body=mesh.get_editor_property('body_setup')
    body.set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE if not entry['collision_boxes'] else unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AND_COMPLEX)
    box=mesh.get_bounding_box()
    assert abs(box.max.z-entry['max'][2]*100)<.3,(name,'unit conversion',box.max.z)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    report[name]={'imported':True,'triangles':entry['triangles'],'max_z_cm':box.max.z,'material':selected.get_path_name()}
    if 'slots' in entry:report[name]['surfaces']=entry['slots']
    if lod_report:report[name]['lods']=lod_report
# The Tripo street props (world/regions/hidamari/props.py), placed by city.json like the rest of the city, and the
# caldera's conifers (Tree_Caldera_*, craterpark/v2/trees.py), which the crater park plants from park.json `trees`.
if (OUT/'props'/'props.json').exists() and (not only or any(n.startswith('HD_P_') for n in only)):
    par=city_mis.get('_parent') or city_material.materials()['_parent']
    props=json.loads((OUT/'props'/'props.json').read_text())
    for key,mi in city_material.prop_materials(par,report.setdefault('HD_P',{})).items():
        if only and key not in only and 'HD_P_' not in only:continue
        # Fresh slots: a conserved placeholder slot would keep slot 0 while the prop's faces draw from a second,
        # unassigned slot (the engine's grey grid material).
        mesh=import_mesh(OUT/'props'/f'{key}.fbx','/Game/Japan/Assets',key,fresh_slots=True)
        assert len(mesh.static_materials)==1,(key,'material slots',len(mesh.static_materials))
        mesh.set_material(0,mi)
        # Solid props have a box; the others (plants, bicycles, the conifers) are walked through.
        mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_DEFAULT if props[key]['boxes'] else unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
        lods=prop_lods(mesh,key,mi,props[key]['lods']) if props[key].get('lods') else None
        unreal.EditorAssetLibrary.save_loaded_asset(mesh)
        report[key]={'imported':True,'triangles':props[key]['triangles'],'material':mi.get_path_name()}
        if lods:report[key]['lods']=lods
if not only or os.environ.get('HIDAMARI_TERRAIN')=='1':
    from forest_ground import coast_instance,coast_rock_instance
    coast_rock_instance()
    # Fresh slots: setup_project's Interchange import is migrated through the village seed, whose one slot
    # (VillagePalette) would otherwise stay; the terrain's slots are its own (Ground, Road, Sand, ...).
    mesh=import_mesh(ROOT/'terrain.fbx','/Game/Japan','Terrain',fresh_slots=True)
    from import_southwest import sand_material
    sand_material()   # the beach slot; the south-west import (later in a fresh build) owns it
    coast_instance()
    materials=[]
    for slot in mesh.static_materials:
        key=str(slot.get_editor_property('imported_material_slot_name')).split('.')[0]
        mat=unreal.EditorAssetLibrary.load_asset('/Game/Japan/Materials/MI_'+key)
        assert mat,key
        materials.append(mat)
    assign_materials(mesh,materials)
    mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)
(OUT/'import-report.json').write_text(json.dumps(report,indent=2)+'\n')
unreal.log('HIDAMARI IMPORT COMPLETE')
