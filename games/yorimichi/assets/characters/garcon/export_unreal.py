"""Prepare the vendored Garçon for the shared move-set and bike retargeters."""
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'world'))
import yori  # noqa: E402

SOURCE = Path(__file__).resolve().parent
OUT = yori.OUT / 'garcon'
HEIGHT, FPS = 1.65, 30
FBX = dict(use_selection=True, apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z',
           add_leaf_bones=False, use_armature_deform_only=False, bake_anim_use_nla_strips=False, bake_anim_use_all_actions=False,
           bake_anim_simplify_factor=0, bake_anim_step=1, mesh_smooth_type='FACE', use_mesh_modifiers=False, path_mode='ABSOLUTE')


def prepare(source):
    record = json.loads((source / 'source-manifest.json').read_text())
    native = source / record['native']
    assert hashlib.sha256(native.read_bytes()).hexdigest() == record['native_sha256'], 'Garcon source checksum mismatch'
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(native))
    scene = bpy.context.scene
    scene.unit_settings.system, scene.unit_settings.scale_length = 'METRIC', 1
    scene.render.fps = FPS
    arms = [o for o in scene.objects if o.type == 'ARMATURE']
    assert len(arms) == 1
    arm = arms[0]
    meshes = [o for o in scene.objects if o.type == 'MESH' and any(m.type == 'ARMATURE' for m in o.modifiers)]
    assert meshes and sum(len(o.data.materials) for o in meshes) == 2, 'Missing Garcon body/head materials'
    world = {o: o.matrix_world.copy() for o in (arm, *meshes)}
    for obj in (arm, *meshes):
        obj.parent = None
        obj.matrix_world = world[obj]
    arm.animation_data_clear()
    arm.data.pose_position = 'REST'
    bpy.context.view_layer.update()
    points = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
    floor, top = min(p.z for p in points), max(p.z for p in points)
    scale = HEIGHT / (top-floor)
    transform = Matrix.Diagonal((scale, scale, scale, 1)) @ Matrix.Translation((0, 0, -floor + .0065/scale))
    bpy.ops.object.select_all(action='DESELECT')
    for obj in (arm, *meshes):
        obj.matrix_world = transform @ world[obj]
        obj.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    names = {b.name: b.name for b in arm.data.bones}
    assert set(names) == set(record['bones'].values()), 'Vendored Garcon rig changed'
    assert arm.data.bones['pelvis'].parent.name == 'root'
    assert all(arm.data.bones[f'toe_{s}'].head_local.x > arm.data.bones[f'foot_{s}'].head_local.x for s in 'LR')
    arm.name = 'Armature'
    arm.data.pose_position = 'POSE'
    for i, mesh in enumerate(meshes):
        mesh.name = f'Garcon_Part{i}'
    bpy.context.view_layer.update()
    return SimpleNamespace(record=record, native=native, scene=scene, arm=arm, meshes=meshes,
                           transform=transform, scale=scale, floor=floor, original_names=names,
                           secondary_bones=set(record['secondary_bones']))


def main():
    (OUT/'fbx').mkdir(parents=True, exist_ok=True)
    (OUT/'textures').mkdir(exist_ok=True)
    rig = prepare(SOURCE)
    materials = {}
    for obj in rig.meshes:
        for material in obj.data.materials:
            if material.name in materials:
                continue
            shader = next(n for n in material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
            color = shader.inputs['Base Color']
            assert color.is_linked and color.links[0].from_node.type == 'TEX_IMAGE'
            image = color.links[0].from_node.image
            target = OUT/'textures'/f'T_{material.name}.png'
            if image.packed_file:
                target.write_bytes(image.packed_file.data)
            else:
                image.save_render(str(target))
            materials[material.name] = dict(base_color=list(color.default_value), texture=str(target.relative_to(OUT)),
                                           two_sided=False, roughness=.8, metallic=0., specular=.2)
    rig.arm.data.pose_position = 'REST'
    bpy.ops.export_scene.fbx(filepath=str(OUT/'fbx/Garcon.fbx'), object_types={'ARMATURE','MESH'}, bake_anim=False, **FBX)
    feet = {s: rig.arm.matrix_world @ rig.arm.data.bones[f'foot_{s}'].head_local for s in 'LR'}
    report = dict(source=rig.native.name, source_sha256=rig.record['native_sha256'], height_cm=165, sole_cm=.65,
                  model_scale=rig.scale, source_floor=rig.floor, facing='+X',
                  rest_ankles_cm={s:p.z*100 for s,p in feet.items()}, bones=rig.original_names,
                  secondary_bones=sorted(rig.secondary_bones), materials=materials, clips={})
    (OUT/'export.json').write_text(json.dumps(report,indent=2)+'\n')
    print('GARCON EXPORT READY', flush=True)


if __name__ == '__main__':
    main()
