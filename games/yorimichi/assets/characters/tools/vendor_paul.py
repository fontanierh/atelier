"""Convert the pinned HarasValley Garçon rig into a self-contained source GLB.

Run under atelier.safety.guarded with Blender. --source is the acquired folder
containing garcon_rig.blend and T_Garcon_{Body,Head}.png; --output is build output.
Geometry, UVs, skin weights and proportions come from the existing player model.
Only units, facing, floor placement and bone names change.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector


def aliases():
    names = {'root': 'root', 'pelvis': 'pelvis', 'spine_01': 'spine',
             'spine_03': 'spine_mid', 'spine_05': 'chest', 'neck_01': 'neck', 'head': 'head'}
    for side, suffix in [('l', 'L'), ('r', 'R')]:
        for old, new in [('clavicle', 'clavicle'), ('upperarm', 'upperarm'), ('lowerarm', 'forearm'),
                         ('hand', 'hand'), ('thigh', 'thigh'), ('calf', 'shin'), ('foot', 'foot'), ('ball', 'toe')]:
            names[f'{old}_{side}'] = f'{new}_{suffix}'
        for digit, finger in enumerate(('index', 'middle', 'ring', 'pinky')):
            for level, target in [(1, f'finger_{digit}'), (2, f'finger_tip_{digit}'), (3, f'finger_end_{digit}')]:
                names[f'{finger}_{level:02}_{side}'] = f'{target}_{suffix}'
        for level, target in [(1, 'thumb'), (2, 'thumb_tip'), (3, 'thumb_end')]:
            names[f'thumb_{level:02}_{side}'] = f'{target}_{suffix}'
    return names


def main(args):
    source, output = args.source, args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(source / 'garcon_rig.blend'))
    mesh = bpy.data.objects['SKM_Garcon']
    arm = next(m.object for m in mesh.modifiers if m.type == 'ARMATURE')
    arm.animation_data_clear()
    arm.data.pose_position = 'REST'
    for bone in arm.pose.bones:
        bone.matrix_basis.identity()
    bpy.context.view_layer.update()
    names = aliases()
    if 'root' not in arm.data.bones:
        assert arm.data.bones['pelvis'].parent is None, 'Unexpected pelvis parent'
        bpy.ops.object.select_all(action='DESELECT')
        arm.select_set(True)
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode='EDIT')
        root = arm.data.edit_bones.new('root')
        floor = min((mesh.matrix_world @ v.co).z for v in mesh.data.vertices)
        root.head = arm.matrix_world.inverted() @ Vector((0, 0, floor))
        root.tail = root.head + Vector((0, 0, 10))
        arm.data.edit_bones['pelvis'].parent = root
        bpy.ops.object.mode_set(mode='OBJECT')
    actual = {b.name for b in arm.data.bones}
    assert set(names) <= actual, sorted(set(names) - actual)
    names.update({n: n for n in actual - set(names)})
    assert len(set(names.values())) == len(names), 'Bone name collision'
    world = {o: o.matrix_world.copy() for o in (arm, mesh)}
    for obj in (arm, mesh):
        obj.parent = None
        obj.matrix_world = world[obj]
    points = [mesh.matrix_world @ v.co for v in mesh.data.vertices]
    floor, top = min(p.z for p in points), max(p.z for p in points)
    scale = 1.65 / (top - floor)
    transform = Matrix.Rotation(math.pi / 2, 4, 'Z') @ Matrix.Diagonal((scale, scale, scale, 1)) @ Matrix.Translation((0, 0, -floor))
    bpy.ops.object.select_all(action='DESELECT')
    for obj in (arm, mesh):
        obj.hide_set(False)
        obj.hide_viewport = obj.hide_render = False
        obj.matrix_world = transform @ world[obj]
        obj.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for group in mesh.vertex_groups:
        if group.name in names:
            group.name = names[group.name]
    for old, new in names.items():
        arm.data.bones[old].name = new
    arm.name = 'Armature'
    mesh.name = 'Garcon_Body'
    assert len(mesh.data.materials) == 2
    parts = set()
    for i, material in enumerate(mesh.data.materials):
        material.name = f'M_Garcon_{i}'
        shader = next(n for n in material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        link = shader.inputs['Base Color'].links[0]
        assert link.from_node.type == 'TEX_IMAGE'
        part = 'Head' if 'Bust' in link.from_node.image.name or 'Head' in link.from_node.image.name else 'Body'
        parts.add(part)
        image = bpy.data.images.load(str(source / f'T_Garcon_{part}.png'), check_existing=False)
        image.colorspace_settings.name = 'sRGB'
        image.pack()
        link.from_node.image = image
    assert parts == {'Head', 'Body'}, 'Both original atlases are required'
    scene = bpy.context.scene
    scene.unit_settings.system, scene.unit_settings.scale_length = 'METRIC', 1
    assert all(arm.data.bones[f'toe_{s}'].head_local.x > arm.data.bones[f'foot_{s}'].head_local.x for s in 'LR')
    bpy.ops.export_scene.gltf(filepath=str(output), export_format='GLB', use_selection=True,
                             export_animations=False, export_skins=True, export_yup=True)
    report = dict(native=output.name, native_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                  height_cm=165, facing='+X', floor_m=0, bones=names,
                  secondary_bones=sorted(set(names.values()) - set(aliases().values())),
                  geometry=dict(vertices=len(mesh.data.vertices), triangles=sum(len(p.vertices)-2 for p in mesh.data.polygons)),
                  source_scale=scale, materials=[m.name for m in mesh.data.materials])
    output.with_suffix('.json').write_text(json.dumps(report, indent=2)+'\n')
    print('GARCON VENDOR COMPLETE', json.dumps(report), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []))
