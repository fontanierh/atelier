#!/usr/bin/env python3
"""Build Kiyo, the tide-reader, entirely in headless Blender.

    blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tide-reader/build.py -- \
      --views front,profile,back,three_quarter,face,hat --export

The script creates the mesh and 23-bone core humanoid rig from code, joins the
parts into one skinned mesh, renders orthographic review views, packs the three
approved Sunburst sheets into the native file, and exports a GLB. Run it through
`atelier.safety.guarded` on this machine. Output is under build/yorimichi/tide-reader/.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'world'))
import yori  # noqa: E402

sys.path.insert(0, str(HERE))
from kiyo_mesh import build_model  # noqa: E402
from kiyo_rig import build_rig  # noqa: E402

OUT = yori.OUT / 'tide-reader'
CORE = ['root', 'pelvis', 'spine', 'spine_mid', 'chest', 'neck', 'head',
        'clavicle_L', 'upperarm_L', 'forearm_L', 'hand_L',
        'clavicle_R', 'upperarm_R', 'forearm_R', 'hand_R',
        'thigh_L', 'shin_L', 'foot_L', 'toe_L', 'thigh_R', 'shin_R', 'foot_R', 'toe_R']

VIEWS = {
    'front': ((0, -5, .83), (0, 0, .80), 1.72, (820, 1080)),
    'profile': ((-5, 0, .83), (0, 0, .80), 1.72, (820, 1080)),
    'back': ((0, 5, .83), (0, 0, .80), 1.72, (820, 1080)),
    'three_quarter': ((-3.4, -3.8, .96), (0, 0, .81), 1.72, (820, 1080)),
    'face': ((0, -5, 1.285), (0, 0, 1.285), .66, (820, 820)),
    'hat': ((-2.7, -4.2, 1.48), (0, 0, 1.405), .82, (820, 820)),
}


def studio():
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1
    scene.render.fps = 30
    world = bpy.data.worlds.new('Warm neutral studio')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (.31, .32, .35, 1)
    world.node_tree.nodes['Background'].inputs[1].default_value = .85
    scene.world = world
    bpy.ops.mesh.primitive_circle_add(vertices=64, radius=.52, fill_type='NGON', location=(0, 0, .0055))
    floor = bpy.context.object
    floor.name = 'Studio floor'
    material = bpy.data.materials.new('Studio matte grey')
    material.use_nodes = True
    material.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (.245, .255, .278, 1)
    material.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 1
    floor.data.materials.append(material)
    for name, location, energy, size, colour in (
            ('Key', (-3.0, -4.2, 5.2), 520, 4.0, (1.0, .94, .86)),
            ('Fill', (3.3, -2.6, 3.0), 300, 4.5, (.88, .92, 1.0)),
            ('Rim', (1.5, 3.7, 4.0), 360, 3.2, (1.0, .95, .88))):
        data = bpy.data.lights.new(name, 'AREA')
        data.energy, data.shape, data.size, data.color = energy, 'DISK', size, colour
        light = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(light)
        light.location = location
        light.rotation_euler = (Vector((0, 0, .9)) - light.location).to_track_quat('-Z', 'Y').to_euler()
    camera_data = bpy.data.cameras.new('Review camera')
    camera = bpy.data.objects.new('Review camera', camera_data)
    bpy.context.collection.objects.link(camera)
    camera_data.type = 'ORTHO'
    scene.camera = camera
    scene.render.engine = 'BLENDER_EEVEE'
    if hasattr(scene, 'eevee') and hasattr(scene.eevee, 'taa_render_samples'):
        scene.eevee.taa_render_samples = 64
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'None'
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = False
    return camera


def join_body(arm, parts):
    for part in parts:
        for group in part.vertex_groups:
            if group.name not in arm.data.bones:
                raise ValueError(f'{part.name}: vertex group {group.name!r} has no rig bone')
    bpy.ops.object.select_all(action='DESELECT')
    for part in parts:
        part.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    body = bpy.context.object
    body.name = body.data.name = 'Kiyo_Body'
    body.parent = arm
    modifier = body.modifiers.new('Kiyo skin', 'ARMATURE')
    modifier.object = arm
    modifier.use_deform_preserve_volume = False
    body['character'] = 'Kiyo, the tide-reader of Hidamari'
    body['references'] = 'sheet.jpg; details.jpg; poses.jpg'
    body['scale'] = 'metres, soles at z=0.0065, facing -Y'
    material = body.data.materials[0] if body.data.materials else None
    if material:
        material.name = 'M_Kiyo_Palette'
    return body


def inspect_body(body, arm):
    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = body.evaluated_get(depsgraph)
    points = [evaluated.matrix_world @ vertex.co for vertex in evaluated.data.vertices]
    floor = min(point.z for point in points)
    top = max(point.z for point in points)
    groups = {group.index: group.name for group in body.vertex_groups}
    unweighted, excess, weight_min, weight_max = [], [], 9.0, 0.0
    for vertex in body.data.vertices:
        weights = [(groups[g.group], g.weight) for g in vertex.groups if g.weight > 1e-7]
        if not weights:
            unweighted.append(vertex.index)
            continue
        if len(weights) > 4:
            excess.append((vertex.index, len(weights)))
        total = sum(weight for _, weight in weights)
        weight_min, weight_max = min(weight_min, total), max(weight_max, total)
    triangles = sum(len(poly.vertices) - 2 for poly in body.data.polygons)
    bone_names = {bone.name for bone in arm.data.bones}
    report = {
        'vertices': len(body.data.vertices),
        'polygons': len(body.data.polygons),
        'triangles': triangles,
        'materials': [material.name for material in body.data.materials],
        'colour_attributes': [attribute.name for attribute in body.data.color_attributes],
        'bones': sorted(bone_names),
        'core_bones_present': sorted(set(CORE) & bone_names),
        'missing_core_bones': sorted(set(CORE) - bone_names),
        'unweighted_vertices': unweighted[:20],
        'unweighted_count': len(unweighted),
        'over_four_influences': excess[:20],
        'weight_sum_min': weight_min,
        'weight_sum_max': weight_max,
        'height_m': top - floor,
        'top_m': top,
        'floor_m': floor,
        'dimensions_m': list(body.dimensions),
    }
    if report['missing_core_bones']:
        raise ValueError('missing humanoid core bones: ' + ', '.join(report['missing_core_bones']))
    if unweighted:
        raise ValueError(f'{len(unweighted)} unweighted vertices, first {unweighted[:10]}')
    if excess:
        raise ValueError(f'{len(excess)} vertices have more than four influences')
    if not (1.50 <= report['height_m'] <= 1.60):
        raise ValueError(f'height {report["height_m"]:.3f} m is outside the 1.50-1.60 m design')
    if abs(floor - .0065) > .006:
        raise ValueError(f'feet are not on the shared floor: {floor:.4f} m')
    return report


def render_views(camera, names):
    scene = bpy.context.scene
    review = OUT / 'review'
    review.mkdir(parents=True, exist_ok=True)
    for name in names:
        location, target, scale, (width, height) = VIEWS[name]
        camera.location = location
        camera.rotation_euler = (Vector(target) - camera.location).to_track_quat('-Z', 'Y').to_euler()
        camera.data.ortho_scale = scale
        scene.render.resolution_x = width
        scene.render.resolution_y = height
        scene.render.resolution_percentage = 100
        scene.render.filepath = str(review / f'{name}.png')
        bpy.ops.render.render(write_still=True)
        print('KIYO RENDERED', name, flush=True)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--views', default='front,profile,back,three_quarter,face,hat')
    parser.add_argument('--no-render', action='store_true')
    parser.add_argument('--export', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    arm = build_rig()
    parts = build_model()
    body = join_body(arm, parts)
    camera = studio()
    report = inspect_body(body, arm)
    report['source_sha256'] = {name: sha(HERE / 'kiyo_mesh.py') for name in ('kiyo_mesh.py',)}
    report['rig_sha256'] = sha(HERE / 'kiyo_rig.py')
    report['reference_sha256'] = {name: sha(HERE / 'references' / f'{name}.jpg')
                                  for name in ('sheet', 'details', 'poses')}
    packed = {}
    for name in ('sheet', 'details', 'poses'):
        image = bpy.data.images.load(str(HERE / 'references' / f'{name}.jpg'))
        image.pack()
        image.filepath = image.filepath_raw = f'//references/{name}.jpg'
        packed[name] = bool(image.packed_file)
    report['packed_references'] = packed
    if not all(packed.values()):
        raise ValueError(f'not every approved reference packed into the native file: {packed}')
    camera.location, camera.data.ortho_scale = (-3.4, -3.8, .96), 1.72
    camera.rotation_euler = (Vector((0, 0, .81)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
    scene.frame_start = scene.frame_end = 1
    scene.frame_set(1)
    source_blend = OUT / 'Kiyo-r01.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(source_blend))
    if not args.no_render:
        render_views(camera, [name for name in args.views.split(',') if name])
    if args.export:
        bpy.ops.object.select_all(action='DESELECT')
        body.select_set(True)
        arm.select_set(True)
        bpy.context.view_layer.objects.active = arm
        glb = OUT / 'Kiyo-r01.glb'
        bpy.ops.export_scene.gltf(filepath=str(glb), export_format='GLB', use_selection=True,
                                  export_animations=False, export_skins=True, export_yup=True,
                                  export_apply=False)
        report['glb_sha256'] = sha(glb)
        report['glb_bytes'] = glb.stat().st_size
    report['blend_sha256'] = sha(source_blend)
    report['blend_bytes'] = source_blend.stat().st_size
    (OUT / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    print('KIYO BUILD COMPLETE', json.dumps({key: report[key] for key in
          ('vertices', 'triangles', 'height_m', 'floor_m', 'unweighted_count', 'weight_sum_min', 'weight_sum_max')}), flush=True)


if __name__ == '__main__':
    main()
