"""Clean up Kaede's Tripo model for rigging, and render it for review (the fox hunter's clean-up stage).

    blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/sword_trainer_cleanup.py -- \\
        --input <asset>/tripo-r02/raw/output_model_url.fbx --output <asset>/cleanup-r01 [--yaw DEGREES]

The provider's mesh is never changed in place. The clean-up: one mesh (the parts joined), the vertices Tripo split at
seams welded back (0.1 mm), loose specks under 0.2% of the mesh removed, normals made consistent, the figure turned to
face +X (its left +Y, Cairo's frame; `--yaw` turns it further), its soles on z = 0 and its middle on the vertical axis,
at 1.68 m. The texture stays packed. Writes cleanup.glb (the input to Tripo's rig), Kaede-Cleanup-r01.blend, four
orthographic renders (front, left, back, right), and cleanup.json with the counts before and after.
"""
import argparse, json, math, sys
from pathlib import Path
import bpy, bmesh
from mathutils import Matrix, Vector

ap = argparse.ArgumentParser()
ap.add_argument('--input', required=True)
ap.add_argument('--output', required=True)
ap.add_argument('--yaw', type=float, default=0.)
a = ap.parse_args(sys.argv[sys.argv.index('--') + 1:])
out = Path(a.output); out.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
src = Path(a.input)
if src.suffix.lower() == '.fbx':
    bpy.ops.import_scene.fbx(filepath=str(src))
else:
    bpy.ops.import_scene.gltf(filepath=str(src))
scene = bpy.context.scene
meshes = [o for o in scene.objects if o.type == 'MESH']
before = {'objects': len(meshes), 'vertices': sum(len(o.data.vertices) for o in meshes), 'faces': sum(len(o.data.polygons) for o in meshes),
          'materials': sorted({m.name for o in meshes for m in o.data.materials if m})}
for o in list(scene.objects):
    if o.type not in ('MESH',):
        bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.object.select_all(action='DESELECT')
for o in meshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
if len(meshes) > 1:
    bpy.ops.object.join()
body = bpy.context.view_layer.objects.active
body.name = 'Kaede body'
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

bm = bmesh.new(); bm.from_mesh(body.data)
welded = len(bm.verts)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=.0001 * max(body.dimensions))
welded -= len(bm.verts)
# Loose specks: islands with under 0.2% of the vertices.
bm.verts.ensure_lookup_table()
seen, islands = set(), []
for v in bm.verts:
    if v.index in seen:
        continue
    stack, island = [v], []
    seen.add(v.index)
    while stack:
        x = stack.pop(); island.append(x)
        for e in x.link_edges:
            y = e.other_vert(x)
            if y.index not in seen:
                seen.add(y.index); stack.append(y)
    islands.append(island)
small = [i for i in islands if len(i) < .002 * len(bm.verts)]
bmesh.ops.delete(bm, geom=[v for i in small for v in i], context='VERTS')
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
bm.to_mesh(body.data); bm.free()

# Facing: the T-pose arms span the widest horizontal axis; the toes stand out in front of the ankles.
co = [body.matrix_world @ v.co for v in body.data.vertices]
lo = Vector((min(p.x for p in co), min(p.y for p in co), min(p.z for p in co)))
hi = Vector((max(p.x for p in co), max(p.y for p in co), max(p.z for p in co)))
span = hi - lo
arms_along_x = span.x > span.y
feet = [p for p in co if p.z < lo.z + .04 * span.z]
mid = (lo + hi) / 2
if arms_along_x:   # facing +Y or -Y: the feet reach further toward the front
    front = 1. if max(p.y for p in feet) - mid.y > mid.y - min(p.y for p in feet) else -1.
    facing = math.degrees(math.atan2(front, 0.))
else:
    front = 1. if max(p.x for p in feet) - mid.x > mid.x - min(p.x for p in feet) else -1.
    facing = 0. if front > 0 else 180.
turn = -facing + a.yaw   # to +X
body.data.transform(Matrix.Rotation(math.radians(turn), 4, 'Z'))
co = [v.co for v in body.data.vertices]
lo = Vector((min(p.x for p in co), min(p.y for p in co), min(p.z for p in co)))
hi = Vector((max(p.x for p in co), max(p.y for p in co), max(p.z for p in co)))
scale = 1.68 / (hi.z - lo.z)
body.data.transform(Matrix.Diagonal((scale, scale, scale, 1)) @ Matrix.Translation((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)))
body.data.update()
for img in bpy.data.images:
    if img.source == 'FILE' and not img.packed_file and img.has_data:
        img.pack()
after = {'vertices': len(body.data.vertices), 'faces': len(body.data.polygons), 'welded': welded, 'specks_removed': len(small),
         'specks_vertices': sum(len(i) for i in small), 'islands': len(islands) - len(small), 'facing_degrees_found': facing, 'turned': turn,
         'dimensions_m': [round(x, 4) for x in body.dimensions]}

# Review renders: orthographic, the figure in frame, a plain grey world.
scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items} else 'BLENDER_EEVEE'
scene.render.resolution_x = scene.render.resolution_y = 900
world = bpy.data.worlds.new('World'); scene.world = world; world.use_nodes = True
world.node_tree.nodes['Background'].inputs[0].default_value = (.7, .7, .7, 1); world.node_tree.nodes['Background'].inputs[1].default_value = 1.2
sun = bpy.data.objects.new('Sun', bpy.data.lights.new('Sun', 'SUN')); scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(50), 0, math.radians(30)); sun.data.energy = 2.5
cam = bpy.data.objects.new('Camera', bpy.data.cameras.new('Camera')); scene.collection.objects.link(cam); scene.camera = cam
cam.data.type = 'ORTHO'; cam.data.ortho_scale = 1.9
for name, yaw in (('front', 0.), ('left', 90.), ('back', 180.), ('right', -90.)):
    r = math.radians(yaw)
    cam.location = Vector((math.cos(r) * 5, math.sin(r) * 5, .84))
    cam.rotation_euler = (math.radians(90), 0, r + math.radians(90))
    scene.render.filepath = str(out / f'{name}.png')
    bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(out / 'Kaede-Cleanup-r01.blend'))
bpy.ops.object.select_all(action='DESELECT'); body.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(out / 'cleanup.glb'), export_format='GLB', use_selection=True, export_yup=True)
(out / 'cleanup.json').write_text(json.dumps({'input': str(src), 'before': before, 'after': after}, indent=2) + '\n')
print('CLEANUP OK', json.dumps(after))
