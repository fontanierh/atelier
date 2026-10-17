"""Suzu, the bell-ringer of Hidamari: build her model, rig and clips headless, and render review views.

    blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/bell-ringer/build.py -- \
        --views front,three_quarter,side,back,face,head_profile [--animations] [--export] [--study NAME]
"""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
KIT = HERE.parent / 'wanderer' / 'kit'
sys.path.insert(0, str(HERE.parents[2] / 'world'))
import yori  # noqa: E402
sys.path.insert(0, str(KIT))
sys.path.insert(0, str(HERE))
from suzu_mesh import build_model  # noqa: E402
from suzu_rig import build_rig  # noqa: E402
import pipeline  # noqa: E402

OUT = yori.OUT / 'bell-ringer'


def studio():
    scene = bpy.context.scene
    world = bpy.data.worlds.new('Neutral reference studio')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (.36, .37, .39, 1)
    world.node_tree.nodes['Background'].inputs[1].default_value = 1.0
    scene.world = world
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, .0065))
    floor = bpy.context.object
    floor.name = 'Studio floor'
    material = bpy.data.materials.new('Studio grey')
    material.diffuse_color = (.235, .24, .25, 1)
    material.use_nodes = True
    material.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (.235, .24, .25, 1)
    material.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 1
    floor.data.materials.append(material)
    for name, location, power, size, colour in [
            ('Key', (-3, -4, 6), 250, 4, (1, .94, .86)),
            ('Fill', (3, -2, 3), 150, 4, (.88, .92, 1)),
            ('Rim', (1, 3, 4), 140, 3, (1, .95, .9))]:
        data = bpy.data.lights.new(name, 'AREA')
        data.energy, data.shape, data.size, data.color = power, 'DISK', size, colour
        light = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(light)
        light.location = location
        light.rotation_euler = (Vector((0, 0, .85))-light.location).to_track_quat('-Z', 'Y').to_euler()
    data = bpy.data.cameras.new('Review camera')
    camera = bpy.data.objects.new('Review camera', data)
    bpy.context.collection.objects.link(camera)
    data.type = 'ORTHO'
    scene.camera = camera
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 32
    scene.cycles.use_denoising = True
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'None'
    scene.render.image_settings.file_format = 'PNG'
    return camera


# Orthographic review cameras: (position, target, ortho scale).
VIEWS = {
    'front': ((0, -5, 1.06), (0, 0, .72), 1.62),
    'three_quarter': ((-2.8, -5, 1.18), (0, 0, .72), 1.62),
    'side': ((-5, 0, .74), (0, 0, .72), 1.62),
    'right': ((5, 0, .74), (0, 0, .72), 1.62),
    'back': ((0, 5, 1.06), (0, 0, .72), 1.62),
    'back_three_quarter': ((3, 5, 1.16), (0, 0, .72), 1.62),
    'face': ((0, -5, 1.19), (0, 0, 1.19), .52),
    'face_three_quarter': ((-2.2, -5, 1.20), (0, 0, 1.19), .52),
    'head_side': ((-5, -1.4, 1.24), (0, 0, 1.19), .52),
    'head_back': ((0, 5, 1.20), (0, 0, 1.16), .52),
    'feet': ((0, -5, .30), (0, 0, .10), .56),
    'calibrated_front': ((0, -5, .72), (0, 0, .72), 1.48),
    'calibrated_side': ((-5, 0, .72), (0, 0, .72), 1.48),
}


def main():
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument('--views', default='front,three_quarter,side,back,face,head_profile')
    parser.add_argument('--study')
    parser.add_argument('--resolution', type=int, default=800)
    parser.add_argument('--engine', default='CYCLES')
    parser.add_argument('--samples', type=int, default=32)
    parser.add_argument('--animations', action='store_true')
    parser.add_argument('--export', action='store_true')
    parser.add_argument('--no-render', action='store_true')
    parser.add_argument('--action', default='', help='render a clip pose instead of the rest/idle pose')
    parser.add_argument('--frame', type=int, default=1)
    option = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    if option.study:
        if option.export:
            raise ValueError('Study output cannot replace production exports')
        OUT = OUT/'studies'/option.study
    OUT.mkdir(parents=True, exist_ok=True)
    if option.export:
        (OUT/'build.json').unlink(missing_ok=True)
    source_hashes = pipeline.source_hashes()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.render.fps = 60
    arm = build_rig()
    parts = build_model()
    bpy.ops.object.select_all(action='DESELECT')
    for ob in parts:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    body = bpy.context.object
    body.name = body.data.name = 'Suzu_Body'
    body.parent = arm
    modifier = body.modifiers.new('Suzu skin', 'ARMATURE')
    modifier.object = arm
    body['reference'] = 'references/sheet.jpg; four views, face close-ups, bell and hair detail'
    body['design'] = 'Suzu, the bell-ringer of Hidamari: silver bun, indigo haori, rust obi, straw bell rope'
    for material in body.data.materials:
        material.name = 'Suzu_Palette'
        # Flatter emission than the villager's material: her silver hair and cream collar read as painted shapes in
        # the reference sheet, and the reference is what the model has to match.
        bsdf = material.node_tree.nodes['Principled BSDF']
        bsdf.inputs['Emission Strength'].default_value = .18
    if option.animations:
        import suzu_motion as animate
        animate.build_actions(arm, OUT)
    camera = studio()
    engines = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items}
    if option.engine.upper() != 'CYCLES':
        wanted = option.engine.upper()
        engine = 'BLENDER_EEVEE' if wanted in ('EEVEE', 'BLENDER_EEVEE') else wanted
        if engine not in engines:
            engine = 'BLENDER_EEVEE'
        scene.render.engine = engine
        if scene.render.engine == 'BLENDER_EEVEE':
            scene.eevee.taa_render_samples = option.samples
    else:
        scene.cycles.samples = option.samples
    scene.render.resolution_x = option.resolution
    scene.render.resolution_y = round(option.resolution*1.15)
    scene.render.resolution_percentage = 100
    manifest = {
        'vertices': len(body.data.vertices),
        'triangles': sum(len(p.vertices)-2 for p in body.data.polygons),
        'bones': {b.name: b.parent.name if b.parent else None for b in arm.data.bones},
        'materials': [m.name for m in body.data.materials],
        'sole_z_m': .0065, 'ankle_height_cm': 13.5, 'character_version': 'suzu_v1',
        'height_m': round(max(v.co.z for v in body.data.vertices)-min(v.co.z for v in body.data.vertices), 4),
        'source_hashes': source_hashes,
    }
    (OUT/'model_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    if option.export:
        folder = OUT/'fbx'
        folder.mkdir(exist_ok=True)
        active = arm.animation_data.action if arm.animation_data else None
        if arm.animation_data:
            arm.animation_data.action = None
        for pb in arm.pose.bones:
            pb.matrix_basis.identity()
        bpy.context.view_layer.update()
        bpy.ops.object.select_all(action='DESELECT')
        body.select_set(True)
        arm.select_set(True)
        bpy.context.view_layer.objects.active = arm
        common = dict(use_selection=True, apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL',
                      axis_forward='-Y', axis_up='Z', add_leaf_bones=False, use_armature_deform_only=True,
                      bake_anim_use_nla_strips=False, bake_anim_use_all_actions=False,
                      bake_anim_simplify_factor=0, mesh_smooth_type='FACE', colors_type='SRGB')
        bpy.ops.export_scene.fbx(filepath=str(folder/'Suzu.fbx'), object_types={'ARMATURE', 'MESH'},
                                 bake_anim=False, **common)
        if option.animations:
            body.select_set(False)
            for name, settings in animate.ACTIONS.items():
                arm.animation_data.action = bpy.data.actions[name]
                scene.frame_start, scene.frame_end = 1, settings['frames']
                scene.frame_set(1)
                bpy.ops.export_scene.fbx(filepath=str(folder/(name+'.fbx')), object_types={'ARMATURE'},
                                         bake_anim=True, **common)
        if arm.animation_data:
            arm.animation_data.action = active
    # Keep the design sheet inside the native file so the model stays reviewable.
    image = bpy.data.images.load(str(HERE/'references'/'sheet.jpg'), check_existing=True)
    image.pack()
    scene.frame_start, scene.frame_end = 1, 181
    if option.action and arm.animation_data:
        arm.animation_data.action = bpy.data.actions[option.action]
        scene.frame_end = round(bpy.data.actions[option.action].frame_range[1])
        scene.frame_set(option.frame)
    else:
        scene.frame_set(1)
    camera.location, target, camera.data.ortho_scale = VIEWS['three_quarter']
    camera.rotation_euler = (Vector(target)-camera.location).to_track_quat('-Z', 'Y').to_euler()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Suzu.blend'))
    if not option.no_render:
        review = OUT/'review'
        review.mkdir(exist_ok=True)
        for name in option.views.split(','):
            arm.data.pose_position = 'REST' if name.startswith('calibrated_') else 'POSE'
            bpy.context.view_layer.update()
            camera.location, target, camera.data.ortho_scale = VIEWS[name]
            camera.rotation_euler = (Vector(target)-camera.location).to_track_quat('-Z', 'Y').to_euler()
            scene.render.filepath = str(review/(name+'.png'))
            bpy.ops.render.render(write_still=True)
            print('RENDERED', name, flush=True)
    if option.export and option.animations:
        pipeline.mark(source_hashes)
    print('SUZU BUILD COMPLETE', manifest, flush=True)


if __name__ == '__main__':
    main()
