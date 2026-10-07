"""Export Modori, the rival, for Unreal: his skinned body and coat with their textures.

    blender -b --python games/yorimichi/assets/characters/modori/export_unreal.py

Reads the current revision (character.toml `source`, checked against source-manifest.json) and writes
build/yorimichi/modori/: fbx/Modori.fbx, textures/ and export.json. `prepare` is also what cairo/botw.py --character
modori retargets Link's move set onto: the revision turned to face +X, scaled to 1.75 m with the soles on the floor
(0.65 cm under, as Cairo's), Tripo Studio's Mixamo rig given a `Root` and its end bones (finger tips, head top, toe
ends; they carry no weights) dropped, and its bones renamed to the humanoid contract's. The coat's `cloth_pin` group
(1 where the coat follows the body, 0 where it hangs free) travels as its vertex colour, for the cloth in Unreal.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import sys
import tomllib
from types import SimpleNamespace
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from atelier.character.names import slug, mixamo_aliases  # noqa: E402

SOURCE = Path(__file__).resolve().parent
OUT = yori.OUT / 'modori'
HEIGHT = 1.75
FPS = 30
# Cairo's FBX settings (cairo/export_unreal.py FBX): every humanoid clip in the game is exported the same way.
FBX = dict(use_selection=True, apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z',
           add_leaf_bones=False, use_armature_deform_only=False, bake_anim_use_nla_strips=False, bake_anim_use_all_actions=False,
           bake_anim_simplify_factor=0, bake_anim_step=1, mesh_smooth_type='FACE', use_mesh_modifiers=False, path_mode='ABSOLUTE')
PIN = 'cloth_pin'


def drop_end_bones(arm):
    """Remove the Mixamo end bones the contract has no name for; they must carry no weights."""
    names = mixamo_aliases()
    extra = [b.name for b in arm.data.bones if b.name not in names]
    for obj in bpy.data.objects:
        if obj.type == 'MESH':
            for name in extra:
                group = obj.vertex_groups.get(name)
                if group is not None:
                    assert not any(g.group == group.index and g.weight > 0 for v in obj.data.vertices for g in v.groups), \
                        (obj.name, name, 'an end bone carries weights')
                    obj.vertex_groups.remove(group)
    return extra


def edit_armature(arm, extra):
    """Drop the end bones and give the rig a `Root` at the floor under the hips (Blender's name, the contract's root)."""
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bones = arm.data.edit_bones
    for name in extra:
        bones.remove(bones[name])
    hips = bones['mixamorig:Hips']
    root = bones.new('Root')
    root.head = (0., 0., 0.)
    root.tail = (0., 0., hips.head.z * .5)
    root.roll = 0.
    hips.parent = root
    bpy.ops.object.mode_set(mode='OBJECT')


def prepare(source):
    """Open the revision in `source` facing +X at 1.75 m, soles on the floor, bones and meshes renamed. Returns record,
    native, scene, arm, meshes, transform, scale, floor and original_names."""
    record = json.loads((source / 'source-manifest.json').read_text())
    toml = source / 'character.toml'
    native = source / (tomllib.loads(toml.read_text())['source'] if toml.exists() else Path(record['native']).name)
    assert hashlib.sha256(native.read_bytes()).hexdigest() == record['native_sha256'], 'the source differs from its manifest'
    bpy.ops.wm.open_mainfile(filepath=str(native))
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1
    scene.render.fps = FPS
    arm = next(o for o in scene.objects if o.type == 'ARMATURE')
    meshes = [o for o in scene.objects if o.type == 'MESH' and o.vertex_groups and not o.get('not_exported')]
    # The look-check take and the Blender simulation stay in the source: the cloth is Unreal's.
    arm.animation_data_create()
    arm.animation_data.action = None
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)
    for obj in meshes:
        for modifier in [m for m in obj.modifiers if m.type in ('CLOTH', 'COLLISION')]:
            obj.modifiers.remove(modifier)
    arm.data.pose_position = 'REST'
    bpy.context.view_layer.update()
    extra = drop_end_bones(arm)
    edit_armature(arm, extra)
    points = []
    for obj in meshes:
        ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        points.extend(ev.matrix_world @ v.co for v in ev.data.vertices)
    floor, top = min(p.z for p in points), max(p.z for p in points)
    scale = HEIGHT / (top - floor)
    from mathutils import Matrix
    # Tripo Studio faces -Y; the game's characters face +X (a quarter turn anticlockwise).
    transform = (Matrix.Rotation(math.pi / 2, 4, 'Z') @ Matrix.Diagonal((scale, scale, scale, 1))
                 @ Matrix.Translation((0, 0, -floor + .0065 / scale)))
    for obj in [arm, *meshes]:
        obj.matrix_world = transform @ obj.matrix_world.copy()
    # Bake the turn and scale into the data, so the rest pose, the clips and the FBX all start from identity objects.
    bpy.ops.object.select_all(action='DESELECT')
    for obj in [arm, *meshes]:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    arm.data.pose_position = 'POSE'
    original_names = mixamo_aliases()
    assert set(original_names) == {b.name for b in arm.data.bones}, sorted({b.name for b in arm.data.bones} ^ set(original_names))
    for old, new in original_names.items():
        arm.data.bones[old].name = new
    arm.name = 'Armature'   # Unreal recognises and omits the FBX armature node
    for obj in meshes:
        obj.name = 'Modori_' + ('Coat' if obj.vertex_groups.get(PIN) else 'Body')
    bpy.context.view_layer.update()
    return SimpleNamespace(record=record, native=native, scene=scene, arm=arm, meshes=meshes, transform=transform, scale=scale,
                           floor=floor, original_names=original_names, dropped=extra)


def outer_shell(coat, arm):
    """Which coat vertices are on its outer surface. Tripo's coat is a solid with thickness, an outer and an inner surface
    joined at the hems: a vertex is outer when its normal points away from the bone carrying most of its weight (its
    nearest point on that bone's segment), inner when it points back at the body."""
    bones = {g.index: arm.data.bones.get(g.name) for g in coat.vertex_groups}
    out = {}
    for v in coat.data.vertices:
        g = max((g for g in v.groups if bones.get(g.group) is not None), key=lambda g: g.weight, default=None)
        if g is None:
            out[v.index] = True; continue
        bone = bones[g.group]
        a, b = arm.matrix_world @ bone.head_local, arm.matrix_world @ bone.tail_local
        d = b - a
        t = min(1., max(0., (v.co - a).dot(d) / max(d.length_squared, 1e-12)))
        out[v.index] = v.normal.dot(v.co - (a + d * t)) >= 0.
    return out


# Passes of averaging the pin over each vertex's neighbours. Tripo's cloth_pin falls from 1 to 0 within a ring or two at
# the hips, so the coat leaning with his torso above it creased into a sharp corner against the skirt hanging below as he
# leant into a run (the operator's photo, #6349); averaged, the coat comes free over about a hand's width.
SOFTEN_PASSES = 20


def soften(coat, weight):
    """The pin weights averaged with their neighbours' (along the mesh's edges) SOFTEN_PASSES times; a vertex fully pinned
    and far from the free part stays pinned."""
    near = {i: [] for i in weight}
    for e in coat.data.edges:
        a, b = e.vertices
        near[a].append(b); near[b].append(a)
    for _ in range(SOFTEN_PASSES):
        weight = {i: (w + sum(weight[j] for j in near[i])) / (1 + len(near[i])) for i, w in weight.items()}
    return weight


def pin_colours(coat, arm):
    """The coat's cloth_pin weights as its vertex colour (red), the mask Unreal's cloth paints its max distance from, and
    its outer surface as green (1 outer, 0 inner): Unreal simulates the outer surface and carries the inner one on it."""
    group = coat.vertex_groups[PIN]
    weight = {v.index: next((g.weight for g in v.groups if g.group == group.index), 0.) for v in coat.data.vertices}
    weight = soften(coat, weight)
    outer = outer_shell(coat, arm)
    attribute = coat.data.color_attributes.new(PIN, 'BYTE_COLOR', 'CORNER')
    for loop in coat.data.loops:
        w = weight[loop.vertex_index]
        attribute.data[loop.index].color = (w, float(outer[loop.vertex_index]), w, 1.)
    coat.data.color_attributes.active_color = attribute
    coat.data.color_attributes.render_color_index = coat.data.color_attributes.active_color_index
    values = list(weight.values())
    return {'vertices': len(values), 'pinned': sum(w >= .999 for w in values), 'free': sum(w <= .001 for w in values),
            'outer': sum(outer.values())}


# The coat's collision (Unreal cloth collides with capsules): each (bone carrying it, from joint, to joint, the bones
# whose skin sets its radius), measured on the body alone, so the coat hangs on his legs and hips, not on itself.
COLLIDERS = [('pelvis', 'thigh_L', 'thigh_R', ('pelvis',)), ('spine', 'spine', 'chest', ('spine', 'spine_mid')),
             ('thigh_L', 'thigh_L', 'shin_L', ('thigh_L',)), ('thigh_R', 'thigh_R', 'shin_R', ('thigh_R',)),
             ('shin_L', 'shin_L', 'foot_L', ('shin_L',)), ('shin_R', 'shin_R', 'foot_R', ('shin_R',))]

MARGIN_CM = 1.


def colliders(arm, body):
    """Capsules for the cloth, in centimetres: a segment between two joints and the radius that holds 99% of the skin
    of the bones around it, and MARGIN_CM. At 80%, taking the coat's thickness for the margin, his baggy trousers came
    through the coat at the thighs."""
    import numpy as np
    head = {b.name: np.array(arm.matrix_world @ b.head_local) for b in arm.data.bones}
    names = {g.index: g.name for g in body.vertex_groups}
    points = {}
    for v in body.data.vertices:
        if v.groups:
            strongest = max(v.groups, key=lambda g: g.weight)
            points.setdefault(names[strongest.group], []).append(np.array(body.matrix_world @ v.co))
    out = []
    for bone, start, end, skin in COLLIDERS:
        a, b = head[start], head[end]
        p = np.array([q for name in skin for q in points.get(name, [])])
        assert len(p) > 20, (bone, 'too little skin to size its capsule', len(p))
        t = np.clip((p - a) @ (b - a) / ((b - a) @ (b - a)), 0, 1)
        distance = np.linalg.norm(p - (a + t[:, None] * (b - a)), axis=1)
        out.append({'bone': bone, 'from': start, 'to': end, 'radius_cm': round(float(np.percentile(distance, 99)) * 100 + MARGIN_CM, 2)})
    return out


def main(args):
    (OUT / 'fbx').mkdir(parents=True, exist_ok=True)
    (OUT / 'textures').mkdir(exist_ok=True)
    modori = prepare(SOURCE)
    record, arm, meshes = modori.record, modori.arm, modori.meshes
    feet = {side: list(arm.matrix_world @ arm.data.bones['foot_' + side].head_local) for side in 'LR'}
    toes = {side: list(arm.matrix_world @ arm.data.bones['toe_' + side].head_local) for side in 'LR'}
    assert all(toes[s][0] > feet[s][0] for s in 'LR'), ('Modori must face +X', feet, toes)
    materials = {}
    for obj in meshes:
        for material in obj.data.materials:
            if material.name in materials:
                continue
            old = material.name
            material.name = 'M_' + obj.name
            shader = next(n for n in material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
            color = shader.inputs['Base Color']
            texture = None
            if color.is_linked:
                node = color.links[0].from_node
                assert node.type == 'TEX_IMAGE', (old, 'unsupported base colour graph', node.type)
                image = node.image
                data = image.packed_file.data if image.packed_file else None
                target = OUT / 'textures' / ('T_' + obj.name + ('.jpg' if data and data[:3] == b'\xff\xd8\xff' else '.png'))
                if data:
                    target.write_bytes(data)
                else:
                    image.save_render(str(target))
                texture = str(target.relative_to(OUT))
            materials[material.name] = {'source_name': old, 'base_color': list(color.default_value), 'texture': texture,
                                        'two_sided': obj.name.endswith('Coat'), 'roughness': 1., 'metallic': 0., 'specular': 0.}
    coat = next(o for o in meshes if o.name.endswith('Coat'))
    pins = pin_colours(coat, arm)
    capsules = colliders(arm, next(o for o in meshes if o.name.endswith('Body')))
    bpy.ops.object.select_all(action='DESELECT')
    for obj in [arm, *meshes]:
        obj.hide_viewport = False
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = arm
    arm.data.pose_position = 'REST'
    bpy.ops.export_scene.fbx(filepath=str(OUT / 'fbx' / 'Modori.fbx'), object_types={'ARMATURE', 'MESH'}, bake_anim=False,
                             colors_type='LINEAR', **FBX)
    report = {'source': modori.native.name, 'source_sha256': record['native_sha256'], 'model_scale': modori.scale,
              'height_cm': HEIGHT * 100, 'sole_cm': .65, 'source_floor': modori.floor, 'facing': '+X',
              'rest_ankles_cm': {side: p[2] * 100 for side, p in feet.items()}, 'bones': modori.original_names,
              'dropped_bones': modori.dropped, 'meshes': {o.name: len(o.data.vertices) for o in meshes},
              'cloth': {'mesh': coat.name, 'mask': PIN, 'channel': 'vertex colour red (pin), green (outer surface)', 'colliders': capsules, **pins},
              'materials': materials, 'clips': {}}
    (OUT / 'export.json').write_text(json.dumps(report, indent=2) + '\n')
    print('MODORI EXPORT READY', json.dumps({k: report[k] for k in ('model_scale', 'rest_ankles_cm', 'meshes', 'cloth')}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    main(parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []))
