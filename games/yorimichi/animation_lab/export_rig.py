"""Blender: export the fox skin, authored clips, and a body-only conditioning rig."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import bpy
from mathutils import Matrix, Vector


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args(sys.argv[sys.argv.index('--') + 1:])
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(args.source.resolve()))
    scene = bpy.context.scene
    arm = next(o for o in scene.objects if o.type == 'ARMATURE')
    meshes = [o for o in scene.objects if o.type == 'MESH' and any(m.type == 'ARMATURE' and m.object == arm for m in o.modifiers)]
    arm.animation_data.action = None
    for track in arm.animation_data.nla_tracks:
        track.mute = True
    arm.data.pose_position = 'REST'
    bpy.context.view_layer.update()
    # Keep the full skin; condition on the same anatomical body joints used by Mixamo.
    core = ['Hips', 'Spine', 'Spine1', 'Spine2', 'Neck', 'Head',
            'LeftShoulder', 'LeftArm', 'LeftForeArm', 'LeftHand',
            'RightShoulder', 'RightArm', 'RightForeArm', 'RightHand',
            'LeftUpLeg', 'LeftLeg', 'LeftFoot', 'LeftToeBase',
            'RightUpLeg', 'RightLeg', 'RightFoot', 'RightToeBase']
    selected = {b.name for b in arm.data.bones if b.name.replace('mixamorig:', '') in core}
    pending = [b for b in arm.data.bones if b.name in selected and (not b.parent or b.parent.name not in selected)]
    ordered = []
    while pending:
        b = pending.pop(0)
        ordered.append(b)
        pending.extend(c for c in b.children if c.name in selected)
    assert len(ordered) == len(core), [b.name for b in ordered]
    canonical = Matrix(((0, 1, 0), (0, 0, 1), (1, 0, 0)))  # +X forward, +Z up -> +Z forward, +Y up
    points = [canonical @ (arm.matrix_world @ b.head_local) for b in ordered]
    center = Vector((points[0].x, 0, points[0].z))
    names = [b.name for b in ordered]
    parents = [names.index(b.parent.name) if b.parent and b.parent.name in selected else -1 for b in ordered]
    positions = [list(p - center) for p in points]
    rig = {'names': names, 'parents': parents, 'positions': positions,
           'source_sha256': hashlib.sha256(args.source.read_bytes()).hexdigest(), 'fps': 30,
           'conditioning_bones': len(ordered), 'skin_bones': len(arm.data.bones),
           'armature': arm.name, 'canonical_center': list(center)}
    (out / 'rig.json').write_text(json.dumps(rig, indent=2) + '\n')
    for im in bpy.data.images:
        if max(im.size) > 1024:
            im.scale(1024, 1024)
    arm.data.pose_position = 'POSE'
    scene.render.fps = 30
    for o in scene.objects:
        o.select_set(o == arm or o in meshes)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.gltf(filepath=str(out / 'fox.glb'), export_format='GLB', use_selection=True,
        export_yup=True, export_skins=True, export_animations=True, export_animation_mode='ACTIONS',
        export_force_sampling=True, export_current_frame=False, export_image_format='JPEG', export_jpeg_quality=85)
    print(json.dumps({'skin_bones': rig['skin_bones'], 'conditioning_bones': len(ordered), 'glb_bytes': (out / 'fox.glb').stat().st_size}))


if __name__ == '__main__':
    main()
