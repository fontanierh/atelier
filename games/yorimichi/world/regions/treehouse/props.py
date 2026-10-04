"""Tree house Tripo props into game meshes (Blender, headless).

    atelier build yorimichi world.treehouse_props

For every prop in tools/treehouse_props.py with a GLB in assets/treehouse/props/<slug>/:
turn it so its front faces -y (TURN), scale its longest side to its size in metres, stand it on z = 0 centred on
its footprint, give it white vertex colours and one material slot, add a collision box for the solid ones, and write
build/yorimichi/treehouse/props/TH_P_<slug>.fbx and .png (its texture) and props.json (gain: the texture's mean brightness
brought to the palette's, measured over the surface, not the atlas). Also renders four views per prop (front, right, back,
left) for checking the turn; `python games/yorimichi/world/regions/treehouse/props.py sheet` puts them in one
picture (Blender has no PIL).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import json, math, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(yori.GAME/'tools'))
try:
    import bpy
except ImportError:
    bpy = None
from treehouse_props import PROPS, OUT as SRC

OUT = yori.OUT/'treehouse'/'props'
# degrees about z applied after import so the prop's front faces -y (checked on the previews)
TURN = {'backpack': -90, 'bell': -90, 'futon': 180, 'kamado': -90, 'bookshelf': -90, 'crate_desk': -90}
SIZE = {'log_table': 1.35}
# the palette brightness (linear luminance) each prop's texture is brought to
TARGET = dict(kamado=.055, stump_kettle=.05, telescope=.06, backpack=.07, bell=.07, globe=.09, basket=.08, barrel=.05,
              futon=.20, log_table=.055, bookshelf=.055, crate_desk=.055, planter=.065)
SOLID = {'kamado', 'stump_kettle', 'barrel', 'log_table', 'bookshelf', 'crate_desk', 'planter'}


def lin(a):
    return np.where(a <= .04045, a/12.92, ((a+.055)/1.055)**2.4)


def one(slug):
    return fit(slug, SRC/slug/f'{slug}.glb', f'TH_P_{slug}', SIZE.get(slug, PROPS[slug][3]), TURN.get(slug, 0.),
               TARGET[slug], slug in SOLID, OUT)


def fit(slug, glb, key, size, turn, target, solid, out):
    """One Tripo GLB as a game mesh key in out (the steps above); world/regions/hidamari/props.py fits the city's."""
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
    ext = v.max(0)-v.min(0); k = size/ext.max()
    v = v*k; lo, hi = v.min(0), v.max(0); v -= [(lo[0]+hi[0])/2, (lo[1]+hi[1])/2, lo[2]]
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
    render(slug, obj, img, v, out)
    objs = [obj]
    if solid:
        lo, hi = v.min(0), v.max(0); c = (lo+hi)/2; s = (hi-lo)*[.86, .86, 1.]
        bpy.ops.mesh.primitive_cube_add(size=1, location=tuple(c)); box = bpy.context.object
        box.name = f'UCX_{key}_00'; box.scale = tuple(s); bpy.ops.object.transform_apply(scale=True); objs.append(box)
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.fbx(filepath=str(out/f'{key}.fbx'), use_selection=True, apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL',
                             axis_forward='-Y', axis_up='Z', object_types={'MESH'}, mesh_smooth_type='FACE', bake_anim=False,
                             use_custom_props=False, path_mode='STRIP')
    return key, dict(gain=round(target/max(lum, 1e-4), 4), surface_luminance=round(lum, 4), triangles=sum(len(p.vertices)-2 for p in me.polygons),
                     size=[round(float(x), 3) for x in (v.max(0)-v.min(0))], boxes=int(solid), turn=turn)


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


def sheet():
    """The four views of every prop in one picture, a prop per row."""
    from PIL import Image, ImageDraw
    slugs = [s for s in PROPS if (OUT/f'view-{s}-0front.png').exists()]; S = 220
    im = Image.new('RGB', (4*S, S*len(slugs)), (235, 235, 235)); d = ImageDraw.Draw(im)
    for row, slug in enumerate(slugs):
        for i, name in enumerate(('front', 'right', 'back', 'left')):
            im.paste(Image.open(OUT/f'view-{slug}-{i}{name}.png').convert('RGB').resize((S, S)), (i*S, row*S))
            d.text((i*S+5, row*S+5), f'{slug} {name}', fill=(0, 0, 0))
    im.save(OUT/'preview.jpg', quality=88)


def main():
    report = {}
    for slug in PROPS:
        if (SRC/slug/f'{slug}.glb').exists():
            key, info = one(slug); report[key] = info; print(key, info, flush=True)
    (OUT/'props.json').write_text(json.dumps(report, indent=1)+'\n')
    print('TREEHOUSE PROPS COMPLETE', len(report), flush=True)


if __name__ == '__main__':
    sheet() if sys.argv[-1] == 'sheet' else main()
