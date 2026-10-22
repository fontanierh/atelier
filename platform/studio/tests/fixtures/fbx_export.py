"""Small native FBX canary: static/UCX, six UVs, colour, textures, skin and animation."""
import argparse
import json
from pathlib import Path
import sys

import bpy

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--reverse', action='store_true')
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from atelier.blender.fbx import export_fbx

output = args.output.resolve()
output.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
image = bpy.data.images.new('Albedo', width=2, height=2)
image.pixels = [1., 0., 0., 1.] * 4
texture_source = output / ('other-author-textures' if args.reverse else 'author-textures')
texture_source.mkdir()
image.filepath_raw = str(texture_source / 'albedo.png')
image.file_format = 'PNG'
image.save()
materials = []
for name in ('Leaf', 'Metal'):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    if name == 'Leaf':
        node = material.node_tree.nodes.new('ShaderNodeTexImage')
        node.image = image
        material.node_tree.links.new(node.outputs['Color'], material.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
    materials.append(material)
mesh = bpy.data.meshes.new('ProbeGeometry')
mesh.from_pydata([(0, 0, 0), (2, 0, 0), (2, 1, 1), (0, 1, 0)], [], [(0, 1, 2), (0, 2, 3)])
for material in materials:
    mesh.materials.append(material)
mesh.polygons[1].material_index = 1
for channel in range(6):
    uv = mesh.uv_layers.new(name='UV' + str(channel))
    for loop in mesh.loops:
        uv.data[loop.index].uv = (channel + loop.vertex_index * .125, loop.index * .125)
colour = mesh.color_attributes.new(name='Colour', type='FLOAT_COLOR', domain='CORNER')
for loop in mesh.loops:
    colour.data[loop.index].color = (float(loop.vertex_index % 2), 0., 1., 1.)
mesh.normals_split_custom_set([(0., 0., 1.)] * len(mesh.loops))
probe = bpy.data.objects.new('Probe', mesh)
bpy.context.collection.objects.link(probe)
bpy.ops.mesh.primitive_cube_add(size=1, location=(1., .5, .5))
hull = bpy.context.object
hull.name = 'UCX_Probe_00'
bpy.ops.object.armature_add()
arm = bpy.context.object
arm.name = 'Rig'
bpy.ops.object.mode_set(mode='EDIT')
root = arm.data.edit_bones[0]
root.name = 'Root'
child = arm.data.edit_bones.new('Child')
child.head, child.tail, child.parent = (0, 0, 1), (0, 0, 2), root
bpy.ops.object.mode_set(mode='OBJECT')
skin = bpy.data.objects.new('Skin', mesh.copy())
bpy.context.collection.objects.link(skin)
skin.parent = arm
modifier = skin.modifiers.new('Skin', 'ARMATURE')
modifier.object = arm
for name in ('Root', 'Child'):
    skin.vertex_groups.new(name=name).add(list(range(4)), .5, 'REPLACE')
for frame, x in ((1, 0.), (20, .25)):
    arm.pose.bones['Child'].location.x = x
    arm.pose.bones['Child'].keyframe_insert(data_path='location', frame=frame)
scene = bpy.context.scene
scene.frame_start, scene.frame_end = 1, 20
# Different authoring locations and filenames must not enter exported metadata.
bpy.ops.wm.save_as_mainfile(filepath=str(output / ('other-author.blend' if args.reverse else 'author.blend')))
common = dict(use_selection=True, apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL',
              axis_forward='-Y', axis_up='Z', mesh_smooth_type='FACE', colors_type='SRGB',
              add_leaf_bones=False, path_mode='COPY', use_tspace=False, use_custom_props=False,
              bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False, bake_anim_simplify_factor=0.)
for kind in (('clip', 'skeletal', 'static') if args.reverse else ('static', 'skeletal', 'clip')):
    scene.frame_set(1)
    arm.data.pose_position = 'POSE' if kind == 'clip' else 'REST'
    bpy.context.view_layer.update()
    if kind == 'clip':
        for frame in (1,20):
            scene.frame_set(frame)
            bpy.context.view_layer.update()
            print('SOURCE CLIP', frame, tuple(arm.pose.bones['Child'].matrix.translation), flush=True)
        scene.frame_set(1)
        bpy.context.view_layer.update()
    bpy.ops.object.select_all(action='DESELECT')
    selected = [probe, hull] if kind == 'static' else [arm, skin] if kind == 'skeletal' else [arm]
    for obj in selected:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = selected[0]
    export_fbx(filepath=str(output / (kind + '.fbx')),
               object_types={'MESH'} if kind == 'static' else {'ARMATURE', 'MESH'} if kind == 'skeletal' else {'ARMATURE'},
               bake_anim=kind == 'clip', **common)
    print('FBX CANARY EXPORTED', kind, flush=True)
print('FBX EXPORT CANARY COMPLETE', flush=True)
