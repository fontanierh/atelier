"""Export Kaede, the sword trainer, for Unreal: her skinned mesh, textures and her own clips (the bow and her words).

    blender -b --python games/yorimichi/assets/characters/sword-trainer/export_unreal.py

Reads the current revision (character.toml `source`, checked against source-manifest.json) and writes
build/yorimichi/sword-trainer/: fbx/SwordTrainer.fbx, fbx/A_<Clip>.fbx, textures/ and export.json. `prepare` is also what
botw/retarget.py --character sword-trainer retargets Link's move set onto: the revision scaled to 1.68 m with the soles
on the floor (0.65 cm under, as Cairo's), and her Tripo rig's Mixamo bone names renamed to the humanoid contract's.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import tomllib
from types import SimpleNamespace
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from atelier.character.names import slug, mixamo_aliases  # noqa: E402

SOURCE = Path(__file__).resolve().parent
OUT = yori.OUT / 'sword-trainer'
HEIGHT = 1.68
FPS = 30
# Cairo's FBX settings (cairo/export_unreal.py FBX): every humanoid clip in the game is exported the same way.
FBX = dict(use_selection=True, apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z',
           add_leaf_bones=False, use_armature_deform_only=False, bake_anim_use_nla_strips=False, bake_anim_use_all_actions=False,
           bake_anim_simplify_factor=0, bake_anim_step=1, mesh_smooth_type='FACE', use_mesh_modifiers=False, path_mode='ABSOLUTE')


def rename_bones_in_actions(names):
    """Blender repairs only the attached action when a bone is renamed: every other clip's curves are fixed here."""
    for action in bpy.data.actions:
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for fc in bag.fcurves:
                        for old, new in names.items():
                            fc.data_path = fc.data_path.replace('pose.bones["' + old + '"]', 'pose.bones["' + new + '"]')


def prepare(source):
    """Open the revision in `source` at 1.68 m, soles on the floor, bones and meshes renamed. Returns record, native,
    scene, arm, meshes, transform, scale, floor and original_names."""
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
    arm.animation_data_create()
    arm.animation_data.action = None
    arm.data.pose_position = 'REST'
    bpy.context.view_layer.update()
    points = []
    for obj in meshes:
        ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        points.extend(ev.matrix_world @ v.co for v in ev.data.vertices)
    floor, top = min(p.z for p in points), max(p.z for p in points)
    scale = HEIGHT / (top - floor)
    from mathutils import Matrix
    transform = Matrix.Diagonal((scale, scale, scale, 1)) @ Matrix.Translation((0, 0, -floor + .0065 / scale))
    for obj in [arm, *meshes]:
        obj.matrix_world = transform @ obj.matrix_world.copy()
    arm.data.pose_position = 'POSE'
    original_names = mixamo_aliases()
    assert set(original_names) == {b.name for b in arm.data.bones}, sorted({b.name for b in arm.data.bones} ^ set(original_names))
    for old, new in original_names.items():
        arm.data.bones[old].name = new
    arm.name = 'Armature'   # Unreal recognises and omits the FBX armature node
    for i, obj in enumerate(meshes):
        obj.name = 'SwordTrainer_' + slug(obj.get('body_region') or f'part{i}')
    rename_bones_in_actions(original_names)
    bpy.context.view_layer.update()
    return SimpleNamespace(record=record, native=native, scene=scene, arm=arm, meshes=meshes, transform=transform, scale=scale,
                           floor=floor, original_names=original_names)


def main(args):
    (OUT / 'fbx').mkdir(parents=True, exist_ok=True)
    (OUT / 'textures').mkdir(exist_ok=True)
    kaede = prepare(SOURCE)
    record, scene, arm, meshes = kaede.record, kaede.scene, kaede.arm, kaede.meshes
    feet = {side: list(arm.matrix_world @ arm.data.bones['foot_' + side].head_local) for side in 'LR'}
    materials = {}
    for obj in meshes:
        for material in obj.data.materials:
            if material.name in materials:
                continue
            old = material.name
            material.name = 'M_SwordTrainer_' + slug(old)
            shader = next(n for n in material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
            color = shader.inputs['Base Color']
            texture = None
            if color.is_linked:
                node = color.links[0].from_node
                assert node.type == 'TEX_IMAGE', (old, 'unsupported base colour graph', node.type)
                image = node.image
                data = image.packed_file.data if image.packed_file else None
                target = OUT / 'textures' / ('T_' + slug(old) + ('.jpg' if data and data[:3] == b'\xff\xd8\xff' else '.png'))
                if data:
                    target.write_bytes(data)
                else:
                    image.save_render(str(target))
                texture = str(target.relative_to(OUT))
            materials[material.name] = {'source_name': old, 'base_color': list(color.default_value), 'texture': texture,
                                        'two_sided': False, 'roughness': .7, 'metallic': 0., 'specular': .3}

    def select(objects):
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects:
            obj.hide_viewport = False
            obj.hide_set(False)
            obj.select_set(True)
        bpy.context.view_layer.objects.active = arm

    arm.animation_data.action = None
    arm.data.pose_position = 'REST'
    select([arm, *meshes])
    bpy.ops.export_scene.fbx(filepath=str(OUT / 'fbx' / 'SwordTrainer.fbx'), object_types={'ARMATURE', 'MESH'}, bake_anim=False, **FBX)
    arm.data.pose_position = 'POSE'
    clips = {}
    for role in record['roles']:
        action = bpy.data.actions[role['clip']]
        arm.animation_data.action = action
        if arm.animation_data.action_slot is None and action.slots:
            arm.animation_data.action_slot = action.slots[0]
        scene.frame_start, scene.frame_end = map(int, action.frame_range)
        scene.frame_set(scene.frame_start)
        select([arm])
        bpy.ops.export_scene.fbx(filepath=str(OUT / 'fbx' / ('A_' + role['role'] + '.fbx')), object_types={'ARMATURE'}, bake_anim=True, **FBX)
        clips[role['role']] = {'action': role['clip'], 'frames': scene.frame_end - scene.frame_start + 1, 'fps': FPS,
                               'duration': (scene.frame_end - scene.frame_start) / FPS, 'loop': bool(role.get('loop'))}
        print('SWORD TRAINER CLIP', role['role'], flush=True)
    report = {'source': kaede.native.name, 'source_sha256': record['native_sha256'], 'model_scale': kaede.scale,
              'height_cm': HEIGHT * 100, 'sole_cm': .65, 'source_floor': kaede.floor,
              'rest_ankles_cm': {side: p[2] * 100 for side, p in feet.items()}, 'bones': kaede.original_names,
              'materials': materials, 'clips': clips}
    (OUT / 'export.json').write_text(json.dumps(report, indent=2) + '\n')
    print('SWORD TRAINER EXPORT READY', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    main(parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []))
