"""Export the fox hunter (animation-r05) for Unreal: skeletal mesh, material, textures and the fifteen clips.

    blender -b --threads 4 --python-exit-code 1 --python japan/tools/export_fox_hunter_unreal.py -- [--rev animation-r05] [--clips Idle,Run] [--clips-only]

Writes `japan/out/fox_hunter/{fbx,textures,export.json}`. The character is scaled to 1.70 m (the brief: slightly
taller than the 1.48 m player), the floor put at the sole height used by the player export, and the bones renamed
with the same aliases as the player (`root`, `pelvis`, `hand_R`...). Loops are exported with their seam frame
(frame N carries the frame-0 pose, so Unreal's loop wraps over one frame step instead of a doubled frame). Root
motion clips (dashes, turns, hurt) keep their travel on the root bone; the report records the travel and yaw
measured after export, the strike bones and hit windows of the attacks, and the reach of every strike in
centimetres, all of which the Unreal importer reads.
"""
from pathlib import Path
import argparse, hashlib, json, math, sys
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from atelier.character.names import slug, mixamo_aliases as aliases

HERE = Path(__file__).resolve().parent   # the current revision's source file and manifest
OUT = yori.OUT / 'fox_hunter'

HEIGHT_M = 1.70
SOLE_CM = .65
STRIKE = {'RightHand': ('hand_R', 'finger_end_1_R'), 'LeftHand': ('hand_L', 'finger_end_1_L'), 'RightFoot': ('foot_R', 'toe_R'), 'LeftFoot': ('foot_L', 'toe_L')}


def fcurves(action):
    out = []
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                out.extend(bag.fcurves)
    return out


def set_clip(arm, action):
    arm.animation_data.action = action
    if arm.animation_data.action_slot is None and action.slots:
        arm.animation_data.action_slot = action.slots[0]
    assert arm.animation_data.action_slot is not None, ('no slot assigned', action.name)


def ue_point(p):
    """Blender world (metres, Z up) -> Unreal component space (cm, Y mirrored); the armature already carries the export transform."""
    return [round(p.x * 100, 3), round(-p.y * 100, 3), round(p.z * 100, 3)]


def main(args):
    source = HERE if args.rev == 'animation-r05' else Path(args.rev).resolve()
    blend = next(source.glob('FoxHunter-Anim-*.blend'))
    manifest = json.loads((source / 'manifest.json').read_text())
    OUT.mkdir(parents=True, exist_ok=True); (OUT / 'fbx').mkdir(exist_ok=True); (OUT / 'textures').mkdir(exist_ok=True)
    sha = hashlib.sha256(blend.read_bytes()).hexdigest()
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'; scene.unit_settings.scale_length = 1
    fps = manifest['fps']; scene.render.fps = fps
    arm = next(o for o in scene.objects if o.type == 'ARMATURE')
    body = next(o for o in scene.objects if o.type == 'MESH' and o.vertex_groups)
    for track in arm.animation_data.nla_tracks: track.mute = True
    arm.animation_data.action = None
    arm.data.pose_position = 'REST'
    bpy.context.view_layer.update()
    points = [body.matrix_world @ v.co for v in body.data.vertices]
    floor, top = min(p.z for p in points), max(p.z for p in points)
    scale = HEIGHT_M / (top - floor)
    transform = Matrix.Diagonal((scale, scale, scale, 1)) @ Matrix.Translation((0, 0, -floor + SOLE_CM / 100 / scale))
    arm.matrix_world = transform @ arm.matrix_world
    bpy.context.view_layer.update()
    assert abs((body.matrix_world @ body.data.vertices[0].co).z - (transform @ (Matrix.Identity(4)) @ points[0]).z) < 1e-5, 'mesh does not follow the armature'
    names = aliases()
    assert set(names) == {b.name for b in arm.data.bones}, 'bone set differs from the shared mixamorig contract'
    for old, new in names.items(): arm.data.bones[old].name = new
    for action in bpy.data.actions:
        for fc in fcurves(action):
            for old, new in names.items():
                fc.data_path = fc.data_path.replace('pose.bones["' + old + '"]', 'pose.bones["' + new + '"]')
    stale = [d.data_path for d in arm.animation_data.drivers if 'mixamorig' in d.data_path]
    stale += [v.targets[0].data_path for d in arm.animation_data.drivers for v in d.driver.variables if v.targets and 'mixamorig' in (v.targets[0].data_path or '')]
    assert not stale, ('drivers still reference the old bone names', stale[:5])
    arm.name = 'Armature'; body.name = 'FoxHunter'
    materials = {}
    for material in body.data.materials:
        old = material.name; material.name = 'M_FoxHunter_' + slug(old)
        shader = next(n for n in material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        color = shader.inputs['Base Color']; texture = None
        if color.is_linked and color.links[0].from_node.type == 'TEX_IMAGE':
            image = color.links[0].from_node.image
            data = image.packed_file.data if image.packed_file else None
            target = OUT / 'textures' / ('T_FoxHunter_' + slug(image.name) + ('.jpg' if data and data[:3] == b'\xff\xd8\xff' else '.png'))
            if data: target.write_bytes(data)
            else: image.save_render(str(target))
            texture = str(target.relative_to(OUT))
        materials[material.name] = {'source_name': old, 'texture': texture, 'base_color': list(color.default_value), 'two_sided': not material.use_backface_culling,
                                    'roughness': float(shader.inputs['Roughness'].default_value), 'metallic': float(shader.inputs['Metallic'].default_value), 'specular': .3}
    bpy.context.view_layer.update()
    MW = arm.matrix_world
    rest = {b: ue_point(MW @ arm.data.bones[b].head_local) for b in ['root', 'pelvis', 'head', 'hand_R', 'finger_end_1_R', 'hand_L', 'finger_end_1_L', 'foot_R', 'toe_R', 'foot_L']}
    feet = {side: (MW @ arm.data.bones['foot_' + side].head_local).z * 100 for side in ['L', 'R']}

    def select(objects):
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects:
            obj.hide_viewport = False; obj.hide_set(False); obj.select_set(True)
        bpy.context.view_layer.objects.active = arm

    common = dict(use_selection=True, apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z', add_leaf_bones=False,
                  use_armature_deform_only=False, bake_anim_use_nla_strips=False, bake_anim_use_all_actions=False, bake_anim_simplify_factor=0,
                  bake_anim_step=1, mesh_smooth_type='FACE', use_mesh_modifiers=False, path_mode='ABSOLUTE')
    if not args.clips_only:
        select([arm, body])
        bpy.ops.export_scene.fbx(filepath=str(OUT / 'fbx/FoxHunter.fbx'), object_types={'ARMATURE', 'MESH'}, bake_anim=False, **common)
    arm.data.pose_position = 'POSE'
    wanted = args.clips.split(',') if args.clips else None
    clips = {}
    for name, info in manifest['clips'].items():
        if wanted and name not in wanted: continue
        action = bpy.data.actions[info['action']]
        set_clip(arm, action)
        loop = info['kind'] == 'loop'
        last = int(round(action.frame_range[1]))
        if loop:
            # the loop period is `seconds`; frame N (= frame 0) closes it
            last = int(round(info['seconds'] * fps))
            action.use_frame_range = False
            for fc in fcurves(action):
                fc.keyframe_points.insert(last, fc.evaluate(0), options={'FAST'})
                fc.update()

        def snapshot(frame):
            scene.frame_set(frame); bpy.context.view_layer.update()
            return {b: (MW @ arm.pose.bones[b].head).copy() for b in ['root', 'pelvis', 'hand_R', 'hand_L', 'foot_L', 'foot_R']}, arm.pose.bones['root'].matrix.to_quaternion()
        first, q0 = snapshot(0); final, q1 = snapshot(last)
        if loop:
            seam = max((first[b] - final[b]).length for b in first)
            assert seam < 2e-3, (name, 'loop seam', seam)
        travel = (final['root'] - first['root']); yaw = math.degrees((q0.inverted() @ q1).to_euler('XYZ').z)
        entry = {'action': action.name, 'frames': last, 'duration': last / fps, 'sample_rate': fps, 'loop': loop, 'kind': info['kind'],
                 'root_motion': bool(info.get('root_motion')), 'holds_last_pose': bool(info.get('holds_last_pose')),
                 'travel_cm': [round(travel.x * 100, 2), round(-travel.y * 100, 2), round(travel.z * 100, 2)], 'yaw_degrees': round(-yaw, 2),
                 'travel_speed_cm_s': round(info['travel_speed_units_per_s'] * scale * 100, 2) if 'travel_speed_units_per_s' in info else 0.}
        if info.get('strike'):
            bone, tip = STRIKE[info['strike']]
            w0, w1 = info['hit_window_seconds']
            path = []
            for frame in range(int(math.floor(w0 * fps)), int(math.ceil(w1 * fps)) + 1):
                scene.frame_set(frame); bpy.context.view_layer.update()
                origin = MW @ arm.pose.bones['root'].head
                for b in (bone, tip):
                    p = MW @ arm.pose.bones[b].head
                    path.append({'frame': frame, 'bone': b, 'forward_cm': round((p.x - origin.x) * 100, 1), 'side_cm': round(-(p.y - origin.y) * 100, 1), 'height_cm': round(p.z * 100, 1)})
            entry.update({'hit_window': [w0, w1], 'strike_bone': bone, 'strike_tip_bone': tip, 'strike_path': path,
                          'reach_cm': max(p['forward_cm'] for p in path), 'strike_height_cm': [min(p['height_cm'] for p in path), max(p['height_cm'] for p in path)]})
        scene.frame_start, scene.frame_end = 0, last
        scene.frame_set(0)
        select([arm, body])
        bpy.ops.export_scene.fbx(filepath=str(OUT / 'fbx' / f'A_Fox{name}.fbx'), object_types={'ARMATURE', 'MESH'}, bake_anim=True, **common)
        clips[name] = entry
        print('FOX_CLIP_EXPORTED', name, entry['duration'], 'travel', entry['travel_cm'], 'yaw', entry['yaw_degrees'], flush=True)
    arm.animation_data.action = None
    report = {'source': blend.name, 'source_sha256': sha, 'manifest_rig': manifest['rig'], 'fps': fps, 'model_scale': scale, 'height_cm': HEIGHT_M * 100,
              'sole_cm': SOLE_CM, 'source_floor': floor, 'source_top': top, 'rest_ankles_cm': feet, 'rest_bones_cm': rest, 'bones': names, 'materials': materials,
              'mesh': 'fbx/FoxHunter.fbx', 'clips': clips, 'facing': manifest['facing'], 'capsule': {'radius_cm': 26, 'half_height_cm': round(HEIGHT_M * 100 / 2 + 1, 1)}}
    (OUT / (args.report or 'export.json')).write_text(json.dumps(report, indent=2) + '\n')
    print('FOX_UNREAL_EXPORT_READY', len(clips), 'clips, scale', round(scale, 4), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--rev', default='animation-r05')
    parser.add_argument('--clips')
    parser.add_argument('--clips-only', action='store_true')
    parser.add_argument('--report')
    main(parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []))
