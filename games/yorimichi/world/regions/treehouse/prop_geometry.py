"""Fit one committed model without loading the region membership or other source models."""
import math
from pathlib import Path
import numpy as np
try:
    import bpy
except ImportError:
    bpy = None
import yori
OUT=yori.OUT/'treehouse/props'

def lin(a):
    return np.where(a <= .04045, a/12.92, ((a+.055)/1.055)**2.4)


def fit(slug, glb, key, size, turn, target, solid, out, upright=False, *, publisher=None, diagnostic_views=True):
    """One Tripo GLB as a game mesh key in out (the steps above); world/regions/hidamari/props.py fits the city's.
    `upright` (a tree): its height, not its longest side, is scaled to size, and it stands centred on its trunk's base
    (the middle of its lowest 4%, the root flare), not on its footprint, so a leaning crown keeps its trunk on the spot;
    the report adds `crown`, the farthest any vertex reaches from that axis in plan."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    bpy.ops.object.select_all(action='DESELECT')
    for o in meshes: o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1: bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    for o in list(bpy.context.scene.objects):
        if o is not obj: o.select_set(False)
    obj.parent = None
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    me = obj.data
    v = np.zeros(len(me.vertices)*3); me.vertices.foreach_get('co', v); v = v.reshape(-1, 3)
    t = math.radians(turn); rz = np.array([[math.cos(t), -math.sin(t), 0], [math.sin(t), math.cos(t), 0], [0, 0, 1]])
    v = v@rz.T
    ext = v.max(0)-v.min(0); k = size/(ext[2] if upright else ext.max())
    v = v*k; lo, hi = v.min(0), v.max(0)
    if upright:
        root = v[v[:, 2] < lo[2]+.04*(hi[2]-lo[2])]
        v -= [float(np.median(root[:, 0])), float(np.median(root[:, 1])), lo[2]]
    else:
        v -= [(lo[0]+hi[0])/2, (lo[1]+hi[1])/2, lo[2]]
    me.vertices.foreach_set('co', v.ravel()); me.update()
    # the texture, and its brightness over the surface
    mat = me.materials[0]; img = None
    for n in mat.node_tree.nodes:
        if n.type == 'TEX_IMAGE' and n.image: img = n.image; break
    px = np.array(img.pixels[:], dtype=np.float32).reshape(img.size[1], img.size[0], -1)[..., :3]
    uv = np.zeros(len(me.loops)*2); me.uv_layers.active.data.foreach_get('uv', uv); uv = uv.reshape(-1, 2)
    area = np.zeros(len(me.polygons)); me.polygons.foreach_get('area', area)
    start = np.zeros(len(me.polygons), int); me.polygons.foreach_get('loop_start', start)
    cu = uv[start]; iy = np.clip((cu[:, 1] % 1)*img.size[1], 0, img.size[1]-1).astype(int); ix = np.clip((cu[:, 0] % 1)*img.size[0], 0, img.size[0]-1).astype(int)
    samp = px[iy, ix]                                         # bottom row first
    lum = float((lin(samp)@[.2126, .7152, .0722]*area).sum()/area.sum())   # pixels of a byte image are its sRGB values
    out.mkdir(parents=True, exist_ok=True)
    img.filepath_raw = str(out/f'{key}.png'); img.file_format = 'PNG'
    if max(img.size) > 1024: img.scale(1024, 1024)
    img.save()
    new = bpy.data.materials.new(key); obj.data.materials.clear(); obj.data.materials.append(new)
    col = me.color_attributes.new(name='Color', type='FLOAT_COLOR', domain='POINT')
    col.data.foreach_set('color', np.tile([1., 1., 1., 0.], len(me.vertices)).astype(np.float32))
    obj.name = key; me.name = key
    if diagnostic_views:
        render(slug, obj, img, v, out)
    else:
        new.use_nodes = True  # Same final material state as the original diagnostic renderer.
        # FBX material AmbientColor reads this scene input even with AmbientFactor=0.
        bpy.context.scene.world=bpy.context.scene.world or bpy.data.worlds.new('W')
    objs = [obj]
    if solid:
        lo, hi = v.min(0), v.max(0); c = (lo+hi)/2; s = (hi-lo)*[.86, .86, 1.]
        bpy.ops.mesh.primitive_cube_add(size=1, location=tuple(c)); box = bpy.context.object
        box.name = f'UCX_{key}_00'; box.scale = tuple(s); bpy.ops.object.transform_apply(scale=True); objs.append(box)
    if publisher is None and sum(len(p.vertices)-2 for p in me.polygons)>32768:
        raise ValueError('Large prop exports require independently bounded source pieces')
    if publisher is None:
        bpy.ops.object.select_all(action='DESELECT')
        for o in objs: o.select_set(True)
        bpy.context.view_layer.objects.active = obj
        from atelier.blender.fbx import export_fbx as export_scene_fbx
        export_scene_fbx(filepath=str(out/f'{key}.fbx'), use_selection=True, apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL',
                                 axis_forward='-Y', axis_up='Z', object_types={'MESH'}, mesh_smooth_type='FACE', bake_anim=False,
                                 use_custom_props=False, path_mode='STRIP')
    else:
        publisher(obj, objs[1:])
    info = dict(gain=round(target/max(lum, 1e-4), 4), surface_luminance=round(lum, 4), triangles=sum(len(p.vertices)-2 for p in me.polygons),
                size=[round(float(x), 3) for x in (v.max(0)-v.min(0))], boxes=int(solid), turn=turn)
    if upright: info['crown'] = round(float(np.hypot(v[:, 0], v[:, 1]).max()), 3)
    return key, info


def render(slug, obj, img, v, out=OUT):
    """Four textured orthographic views (front from -y, right from +x, back, left) for checking the turn."""
    from mathutils import Vector
    sc = bpy.context.scene; sc.render.engine = 'BLENDER_WORKBENCH'
    sc.display.shading.light = 'STUDIO'; sc.display.shading.color_type = 'TEXTURE'
    sc.render.resolution_x = sc.render.resolution_y = 320; sc.render.film_transparent = False
    sc.world = sc.world or bpy.data.worlds.new('W')
    mat = obj.data.materials[0]; mat.use_nodes = True; nt = mat.node_tree
    t = nt.nodes.new('ShaderNodeTexImage'); t.image = img
    nt.links.new(t.outputs['Color'], nt.nodes['Principled BSDF'].inputs['Base Color']); nt.nodes.active = t
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
    ext = (v.max(0)-v.min(0)); cam.data.type = 'ORTHO'; cam.data.ortho_scale = float(ext.max())*1.15
    mid = Vector((0, 0, float(ext[2])/2))
    for i, (name, d) in enumerate((('front', (0, -1)), ('right', (1, 0)), ('back', (0, 1)), ('left', (-1, 0)))):
        cam.location = mid+Vector((d[0], d[1], .35)).normalized()*10
        cam.rotation_euler = (mid-cam.location).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = str(out/f'view-{slug}-{i}{name}.png'); bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam); nt.nodes.remove(t)   # an image in the exported material clashes with its name in Unreal

