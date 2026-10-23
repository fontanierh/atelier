"""Original Hidamari conifer LOD geometry, selected independently before serialization."""
from types import SimpleNamespace


def make_lod(src, info, key, n, settings):
    """Construct one LOD directly from the fitted base, never from a sibling export."""
    import bpy, bmesh
    caldera=SimpleNamespace(**settings)
    if type(n) is not int or not 0<n<len(caldera.LODS):raise ValueError('Invalid selected conifer LOD')
    share, screen, how=caldera.LODS[n]
    def tris(obj):
        return sum(len(p.vertices)-2 for p in obj.data.polygons)

    def apply(obj, mod):
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=mod.name)

    def decimate(obj, share):
        """Collapse obj to `share` of LOD0's triangles."""
        mod = obj.modifiers.new('decimate', 'DECIMATE'); mod.decimate_type = 'COLLAPSE'; mod.use_collapse_triangulate = True
        mod.ratio = min(1., share*info['triangles']/max(tris(obj), 1)); apply(obj, mod)
    bpy.ops.object.select_all(action='DESELECT')
    obj = src.copy(); obj.data = src.data.copy(); bpy.context.scene.collection.objects.link(obj)
    obj.name = obj.data.name = f'{key}_LOD{n}'
    bm = bmesh.new(); bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4); bm.to_mesh(obj.data); bm.free()
    if how == 'shell':
        h = src.dimensions.z
        mod = obj.modifiers.new('shell', 'SOLIDIFY'); mod.thickness = caldera.SHELL[0]*h; mod.offset = 0; apply(obj, mod)
        mod = obj.modifiers.new('remesh', 'REMESH'); mod.mode = 'VOXEL'; mod.voxel_size = caldera.SHELL[1]*h
        mod.adaptivity = 0; apply(obj, mod)
        obj.data.materials.clear(); obj.data.materials.append(src.data.materials[0])
        # the trunk below BASE[0] of the height decimated on its own, to BASE[1] of the triangles, then joined
        bm = bmesh.new(); bm.from_mesh(obj.data)
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:]+bm.edges[:]+bm.faces[:], plane_co=(0, 0, caldera.BASE[0]*h),
                               plane_no=(0, 0, 1))
        bm.to_mesh(obj.data); bm.free()
        bpy.ops.object.select_all(action='DESELECT'); obj.select_set(True); bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='DESELECT'); bpy.ops.object.mode_set(mode='OBJECT')
        for p in obj.data.polygons: p.select = p.center.z < caldera.BASE[0]*h
        bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.separate(type='SELECTED'); bpy.ops.object.mode_set(mode='OBJECT')
        base, = [o for o in bpy.context.selected_objects if o is not obj]
        decimate(base, caldera.BASE[1]*share); decimate(obj, (1-caldera.BASE[1])*share)
        bpy.ops.object.select_all(action='DESELECT'); obj.select_set(True); base.select_set(True)
        bpy.context.view_layer.objects.active = obj; bpy.ops.object.join()
    else:
        decimate(obj, share)
    if how == 'shell':
        obj.data.uv_layers.new(name=src.data.uv_layers.active.name)
        mod = obj.modifiers.new('uv', 'DATA_TRANSFER'); mod.object = src; mod.use_loop_data = True
        mod.data_types_loops = {'UV'}; mod.loop_mapping = 'POLYINTERP_NEAREST'; apply(obj, mod)
        col = obj.data.color_attributes.new(name='Color', type='FLOAT_COLOR', domain='POINT')
        col.data.foreach_set('color', [1., 1., 1., 0.]*len(obj.data.vertices))
    assert 0 < tris(obj) < info['triangles'] and len(obj.data.materials) == 1, (key, n, tris(obj))
    # still standing on its root (the planting sinks each tree TREE_SINK into the ground)
    low = min(v.co.z for v in obj.data.vertices)
    assert low < caldera.FLOAT, (key, n, 'stands', low, 'above the ground')
    return obj, [tris(obj), screen]
