"""Prepare the approved, embedded-texture Nox GLB for Unreal and shared retargeters.

The committed assembly remains in its original rig and units. Every build imports a fresh
copy, adds the floor root and renames the humanoid bones; the 180 weighted hair bones
and Mixamo endpoints remain as explicit neutral followers of their animated parents.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import tomllib
from types import SimpleNamespace
import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'world'))
import yori  # noqa: E402
from atelier.character.names import mixamo_aliases, slug  # noqa: E402

SOURCE = Path(__file__).resolve().parent
OUT = yori.OUT / 'nox'
HEIGHT = 1.78
FPS = 30
FBX = dict(use_selection=True, apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z',
           add_leaf_bones=False, use_armature_deform_only=False, bake_anim_use_nla_strips=False, bake_anim_use_all_actions=False,
           bake_anim_simplify_factor=0, bake_anim_step=1, mesh_smooth_type='FACE', use_mesh_modifiers=False, path_mode='ABSOLUTE')


def prepare(source):
    record = json.loads((source / 'source-manifest.json').read_text())
    native = source / tomllib.loads((source / 'character.toml').read_text())['source']
    assert hashlib.sha256(native.read_bytes()).hexdigest() == record['native_sha256'], 'Nox source checksum mismatch'
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(native))
    scene = bpy.context.scene
    scene.unit_settings.system, scene.unit_settings.scale_length = 'METRIC', 1
    scene.render.fps = FPS
    armatures = [o for o in scene.objects if o.type == 'ARMATURE']
    assert len(armatures) == 1, 'Nox requires one assembled skeleton'
    arm = armatures[0]
    meshes = [o for o in scene.objects if o.type == 'MESH' and any(m.type == 'ARMATURE' for m in o.modifiers)]
    assert len(meshes) == 2, 'Nox requires body and head on the same rig'
    # Importers may parent meshes to the armature. Preserve all world transforms once,
    # then detach before applying the same world transform to both rig and geometry.
    world = {o: o.matrix_world.copy() for o in [arm, *meshes]}
    for o in [arm, *meshes]:
        o.parent = None
        o.matrix_world = world[o]
    arm.animation_data_clear()
    arm.data.pose_position = 'REST'
    bpy.context.view_layer.update()
    original = mixamo_aliases()
    assert set(original) - {'Root'} <= {b.name for b in arm.data.bones}, 'Incomplete humanoid rig'
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    hips = arm.data.edit_bones['mixamorig:Hips']
    root = arm.data.edit_bones.new('Root')
    root.head, root.tail = (0, 0, 0), (0, 0, max(.01, hips.head.z * .5))
    hips.parent = root
    bpy.ops.object.mode_set(mode='OBJECT')
    points = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
    floor, top = min(p.z for p in points), max(p.z for p in points)
    scale = HEIGHT / (top - floor)
    transform = (Matrix.Rotation(math.pi / 2, 4, 'Z') @ Matrix.Diagonal((scale, scale, scale, 1))
                 @ Matrix.Translation((0, 0, -floor + .0065 / scale)))
    for o in [arm, *meshes]:
        o.matrix_world = transform @ world[o]
        o.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    names = {b.name: original.get(b.name, slug(b.name)) for b in arm.data.bones}
    assert len(set(names.values())) == len(names), 'Bone rename collision'
    # Rename vertex groups explicitly: glTF meshes need not be parented after detaching.
    for o in meshes:
        for g in o.vertex_groups:
            if g.name in names:
                g.name = names[g.name]
    for old, new in names.items():
        arm.data.bones[old].name = new
    arm.name = 'Armature'
    for o in meshes:
        groups = {g.index for g in o.vertex_groups if g.name.startswith('NoxLoc_')}
        hair = any(w.group in groups and w.weight > 0 for v in o.data.vertices for w in v.groups)
        o.name = 'Nox_Head' if hair else 'Nox_Body'
    arm.data.pose_position = 'POSE'
    secondary = set(names.values()) - set(original.values())
    assert len([n for n in secondary if n.startswith('NoxLoc_')]) == 180, 'Hair rig was lost'
    bpy.context.view_layer.update()
    return SimpleNamespace(record=record, native=native, scene=scene, arm=arm, meshes=meshes, transform=transform,
                           scale=scale, floor=floor, original_names=names, secondary_bones=secondary)


def seat_corrective(nox):
    """Verify the committed corrective targets before exporting their native names."""
    contract = nox.record.get('seat_corrective')
    if contract is None:
        return None
    grid = contract['grid_degrees']
    assert grid == [-25, 0, 35, 70, 105], 'Unexpected Nox hip-flexion grid'
    assert contract['gate_degrees'] == [35, 60], 'Unexpected Nox corrective gate'
    assert contract['interpolation'] == 'bilinear', 'Nox requires bounded bilinear interpolation'
    body = next(o for o in nox.meshes if o.name == 'Nox_Body')
    head = next(o for o in nox.meshes if o.name == 'Nox_Head')
    assert not head.data.shape_keys, 'The seat correction must not change the head'
    assert body.data.shape_keys, 'Missing Nox seat targets'
    keys = body.data.shape_keys.key_blocks
    basis = keys['Basis']
    angle = lambda value: 'm' + str(-value) if value < 0 else str(value)
    names = [f'NoxSeat_L{angle(left)}_R{angle(right)}' for left in grid for right in grid]
    assert set(keys.keys()) == {'Basis', *names}, 'Unexpected Nox body shape targets'
    targets = {}
    for name, (left, right) in zip(names, ((left, right) for left in grid for right in grid)):
        key = keys[name]
        assert key.value == 0, ('Nonzero neutral shape value', name)
        changed = sum((vertex.co - base.co).length_squared > 1e-16 for vertex, base in zip(key.data, basis.data))
        required = max(left, right) > 35
        assert changed == (contract['changed_vertices_per_target'] if required else 0), ('Nox shape footprint changed', name, changed)
        targets[name] = dict(left_degrees=left, right_degrees=right, nonzero_vertices=changed)
    return dict(grid_degrees=grid, gate_degrees=contract['gate_degrees'], interpolation='bilinear', targets=targets)


def main():
    (OUT / 'fbx').mkdir(parents=True, exist_ok=True)
    (OUT / 'textures').mkdir(exist_ok=True)
    nox = prepare(SOURCE)
    arm, meshes = nox.arm, nox.meshes
    corrective = seat_corrective(nox)
    feet = {s: list(arm.matrix_world @ arm.data.bones['foot_' + s].head_local) for s in 'LR'}
    assert all((arm.matrix_world @ arm.data.bones['toe_' + s].head_local).x > feet[s][0] for s in 'LR'), 'Nox must face +X'
    materials = {}
    for o in meshes:
        assert len(o.data.materials) == 1, 'Expected one atlas per part'
        mat = o.data.materials[0]
        mat.name = 'M_' + o.name
        shader = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        color = shader.inputs['Base Color']
        assert color.is_linked and color.links[0].from_node.type == 'TEX_IMAGE', 'Missing embedded atlas'
        image = color.links[0].from_node.image
        target = OUT / 'textures' / ('T_' + o.name + '.png')
        assert image.size[:] == (4096, 4096), 'Expected approved 4K atlas'
        if image.packed_file:
            target.write_bytes(image.packed_file.data)
        else:
            image.save_render(str(target))
        materials[mat.name] = dict(base_color=list(color.default_value), texture=str(target.relative_to(OUT)),
                                   two_sided=True, roughness=1., metallic=0., specular=0.)
    arm.data.pose_position = 'REST'
    bpy.ops.export_scene.fbx(filepath=str(OUT / 'fbx/Nox.fbx'), object_types={'ARMATURE', 'MESH'}, bake_anim=False, **FBX)
    report = dict(source=nox.native.name, source_sha256=nox.record['native_sha256'], model_scale=nox.scale,
                  height_cm=HEIGHT * 100, sole_cm=.65, source_floor=nox.floor, facing='+X',
                  rest_ankles_cm={s: p[2] * 100 for s, p in feet.items()}, bones=nox.original_names,
                  secondary_bones=sorted(nox.secondary_bones), meshes={o.name: len(o.data.vertices) for o in meshes},
                  materials=materials, clips={}, seat_corrective=corrective)
    (OUT / 'export.json').write_text(json.dumps(report, indent=2) + '\n')
    print('NOX EXPORT READY', json.dumps({k: report[k] for k in ('height_cm', 'rest_ankles_cm', 'meshes')}), flush=True)


if __name__ == '__main__':
    main()
