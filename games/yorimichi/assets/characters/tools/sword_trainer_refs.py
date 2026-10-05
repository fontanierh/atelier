"""Reference renders of Cairo for the sword trainer's concepts: front (T-pose rest) and three-quarter (standing).

    blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/sword_trainer_refs.py -- OUT_DIR

The concepts are drawn beside these so the trainer keeps Cairo's proportions language and painted, flat-shaded look.
"""
import sys
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'cairo' / 'Cairo-Game-r18.blend'
out = Path(sys.argv[sys.argv.index('--') + 1])
out.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
scene = bpy.context.scene
arm = next(o for o in scene.objects if o.type == 'ARMATURE')
for o in scene.objects:
    if o.type == 'MESH' and o.name.startswith('Bokken'):
        o.hide_render = True
scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items} else 'BLENDER_EEVEE'
scene.render.resolution_x = scene.render.resolution_y = 1024
scene.render.film_transparent = False
world = scene.world or bpy.data.worlds.new('World')
scene.world = world
world.use_nodes = True
world.node_tree.nodes['Background'].inputs[0].default_value = (.78, .78, .78, 1)
cam = scene.camera
for name, action, yaw in (('cairo_front_tpose', None, 90.), ('cairo_three_quarter', 'Standing · outfit review', 55.)):
    arm.animation_data_create()
    arm.animation_data.action = bpy.data.actions.get(action) if action else None
    for pb in arm.pose.bones:
        if not action:
            pb.matrix_basis.identity()
    scene.frame_set(1)
    bpy.context.view_layer.update()
    # Frame the whole body: Cairo faces +X in his blend.
    pts = [o.matrix_world @ Vector(c) for o in scene.objects if o.type == 'MESH' and not o.hide_render for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    mid = (lo + hi) / 2
    import math
    a = math.radians(yaw)
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = max(hi.x - lo.x, hi.z - lo.z) * 1.15
    cam.location = mid + Vector((math.sin(a) * 6, -math.cos(a) * 6, 0))
    cam.rotation_euler = (math.radians(90), 0, a)
    scene.render.filepath = str(out / f'{name}.png')
    bpy.ops.render.render(write_still=True)
    print('REF', scene.render.filepath, flush=True)
