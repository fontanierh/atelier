"""Current city distance LOD finishing shared by whole-control and bounded owners."""
import unreal


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
