"""Kaede's rig and her own clips: Tripo's body rig with fingers, the bow and her words, saved as a revision.

    blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/sword_trainer_rig.py -- \\
        --input <asset>/tripo-rig-r01/raw/output_model_url.glb --output <asset>/rig-r01

Input: Tripo's rig of the approved clean-up (23 body bones with Mixamo names under `Root`, the character facing +X,
her left +Y). Adds the 30 finger bones (tripo_fingers.add_fingers) for the humanoid contract's 53, then authors her
own clips at 30 fps on that rig: Bow (a standing bow, 2.2 s) and Talk (an explaining gesture with a nod, 2.6 s). Every
move set clip is retargeted onto her later (botw/retarget.py --character sword-trainer); these two are hers alone.

Poses are written in her frame (forward +X, left +Y, up +Z): each bone turns about an axis of that frame through its
own head, on top of its parent's posed place, so a pitch is always a pitch. Writes SwordTrainer-Rig-r01.blend,
source-manifest.json (the roles and the blend's hash), review renders (rest, bow, talk, a squat and a reach to test the
skinning) and rig.json.
"""
import argparse, hashlib, json, math, sys
from pathlib import Path
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E401,E402,F401 - puts atelier on the path
from atelier.blender.tripo_fingers import add_fingers  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--input', required=True)
ap.add_argument('--output', required=True)
ap.add_argument('--no-renders', action='store_true')
a = ap.parse_args(sys.argv[sys.argv.index('--') + 1:])
out = Path(a.output); out.mkdir(parents=True, exist_ok=True)
NAME = 'SwordTrainer-Rig-r01'
FPS = 30
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(a.input))
scene = bpy.context.scene
scene.render.fps = FPS
for o in list(scene.objects):
    if o.type == 'MESH' and not o.vertex_groups:   # Blender's bone-shape helper from the glTF import
        bpy.data.objects.remove(o, do_unlink=True)
arm = next(o for o in scene.objects if o.type == 'ARMATURE')
body = next(o for o in scene.objects if o.type == 'MESH')
arm.name, body.name = 'Kaede rig', 'Kaede body'
body['body_region'] = 'body'
assert len(arm.data.bones) == 23 and 'Root' in arm.data.bones, [b.name for b in arm.data.bones]
fingers = add_fingers(arm, body)
assert len(arm.data.bones) == 53

# --- pose authoring --------------------------------------------------------------------------------------------
P = lambda side, part: f'mixamorig:{side}{part}'
ORDER = [b.name for b in sorted(arm.data.bones, key=lambda b: len(b.parent_recursive))]
AXES = {'pitch': Vector((0, 1, 0)), 'roll': Vector((1, 0, 0)), 'yaw': Vector((0, 0, 1))}


def pose(spec):
    """Put the rig in a pose: {bone: [(axis, degrees), ...]} turned in her frame about each bone's head, parents first.
    `pitch` positive bends forward (the head toward +X), `roll` positive tips toward her right, `yaw` turns left."""
    for pb in arm.pose.bones:
        pb.rotation_mode = 'QUATERNION'
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    for name in ORDER:
        turns = spec.get(name)
        if not turns:
            continue
        pb = arm.pose.bones[name]
        M = pb.matrix.copy()
        head = M.translation.copy()
        for axis, deg in turns:
            R = Matrix.Rotation(math.radians(deg), 4, AXES[axis])
            M = Matrix.Translation(head) @ R @ Matrix.Translation(-head) @ M
        pb.matrix = M
        bpy.context.view_layer.update()


def key(frame):
    for pb in arm.pose.bones:
        pb.keyframe_insert('rotation_quaternion', frame=frame)
        pb.keyframe_insert('location', frame=frame)


def merge(*specs):
    out = {}
    for s in specs:
        for k, v in s.items():
            out.setdefault(k, []).extend(v)
    return out


# Arms hang from the T-pose: the upper arms lowered 72 degrees and a little forward, the elbows soft, the hands turned
# so the palms face the thighs.
def hang(side):
    sign = 1. if side == 'Left' else -1.
    return {P(side, 'Arm'): [('roll', -72 * sign), ('pitch', -6)], P(side, 'ForeArm'): [('pitch', -12)], P(side, 'Hand'): [('yaw', -80 * sign)]}


HANG = merge(hang('Left'), hang('Right'))


def finger_curl(deg, sides=('Left', 'Right')):
    """The fingers curled toward the palm (hanging hands: palm to the thigh)."""
    spec = {}
    for side in sides:
        sign = 1. if side == 'Left' else -1.
        for f in ('Index', 'Middle', 'Ring', 'Pinky'):
            for i in (1, 2, 3):
                spec[P(side, f'Hand{f}{i}')] = [('roll', -deg * sign * (1. if i == 1 else .8))]
    return spec


STAND = merge(HANG, finger_curl(12))


def clip(name, keys):
    action = bpy.data.actions.new(name)
    arm.animation_data_create()
    arm.animation_data.action = action
    for frame, spec in keys:
        pose(spec)
        key(frame)
    for fc in action.fcurves if hasattr(action, 'fcurves') else []:
        for kp in fc.keyframe_points:
            kp.interpolation = 'BEZIER'
    action.use_fake_user = True
    return action


# A 30 degree bow hinged at the hips (the legs stay upright), the back straight, the hands sliding down the thighs.
BOW_DOWN = merge(STAND, {P('', 'Hips'): [('pitch', 18)], P('Left', 'UpLeg'): [('pitch', -18)], P('Right', 'UpLeg'): [('pitch', -18)],
                         P('', 'Spine'): [('pitch', 6)], P('', 'Spine1'): [('pitch', 4)], P('', 'Spine2'): [('pitch', 2)],
                         P('', 'Head'): [('pitch', 4)], P('Left', 'Arm'): [('pitch', 24)], P('Right', 'Arm'): [('pitch', 24)]})
bow = clip('Bow', [(0, STAND), (14, BOW_DOWN), (40, BOW_DOWN), (58, STAND), (66, STAND)])
# Words: the right hand comes up before her, forearm forward, palm up; a nod; the hand opens out; back down.
EXPLAIN = merge(hang('Left'), finger_curl(12, ('Left',)), finger_curl(6, ('Right',)),
                {P('Right', 'Arm'): [('yaw', 35), ('roll', 70)], P('Right', 'ForeArm'): [('pitch', -75)], P('Right', 'Hand'): [('pitch', -10)],
                 P('', 'Head'): [('pitch', -3)], P('', 'Spine2'): [('yaw', 6)]})
NOD = merge(EXPLAIN, {P('', 'Head'): [('pitch', 12)], P('', 'Neck'): [('pitch', 4)]})
OPEN = merge(EXPLAIN, {P('Right', 'Arm'): [('yaw', -15)], P('Right', 'ForeArm'): [('yaw', -15)]})
talk = clip('Talk', [(0, STAND), (12, EXPLAIN), (26, NOD), (36, EXPLAIN), (52, OPEN), (66, EXPLAIN), (80, STAND)])

# --- review ---------------------------------------------------------------------------------------------------
checks = {}
if not a.no_renders:
    scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items} else 'BLENDER_EEVEE'
    scene.render.resolution_x = scene.render.resolution_y = 800
    world = bpy.data.worlds.new('World'); scene.world = world; world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (.7, .7, .7, 1)
    sun = bpy.data.objects.new('Sun', bpy.data.lights.new('Sun', 'SUN')); scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(50), 0, math.radians(30)); sun.data.energy = 2.5
    cam = bpy.data.objects.new('Review camera', bpy.data.cameras.new('Review camera')); scene.collection.objects.link(cam); scene.camera = cam
    cam.data.type = 'ORTHO'; cam.data.ortho_scale = 1.25
    SQUAT = merge(STAND, {P('Left', 'UpLeg'): [('pitch', -70)], P('Right', 'UpLeg'): [('pitch', -70)],
                          P('Left', 'Leg'): [('pitch', 110)], P('Right', 'Leg'): [('pitch', 110)],
                          P('Left', 'Foot'): [('pitch', -40)], P('Right', 'Foot'): [('pitch', -40)], P('', 'Spine'): [('pitch', 25)]})
    REACH = {P('Left', 'Arm'): [('yaw', 80), ('roll', -20)], P('Right', 'Arm'): [('roll', -150)], P('Right', 'ForeArm'): [('pitch', -60)],
             P('', 'Spine1'): [('yaw', 25)], **finger_curl(70)}
    shots = [('rest', None, 0), ('stand', STAND, 0), ('bow', BOW_DOWN, 90), ('talk', OPEN, 30), ('squat', SQUAT, 60), ('reach', REACH, 30)]
    arm.animation_data.action = None
    for name, spec, yaw in shots:
        pose(spec or {})
        r = math.radians(yaw)
        cam.location = Vector((math.cos(r) * 5, math.sin(r) * 5, .5)); cam.rotation_euler = (math.radians(90), 0, r + math.radians(90))
        scene.render.filepath = str(out / f'{name}.png'); bpy.ops.render.render(write_still=True)
    pose({})
arm.animation_data.action = None
bpy.ops.wm.save_as_mainfile(filepath=str(out / f'{NAME}.blend'), compress=True)
digest = hashlib.sha256((out / f'{NAME}.blend').read_bytes()).hexdigest()
manifest = {'native': f'{NAME}.blend', 'native_sha256': digest, 'fps': FPS, 'height_cm': 168,
            'rig': 'humanoid contract with fingers: 23 Tripo body bones (Mixamo names under Root) and 30 finger bones',
            'roles': [{'role': 'Bow', 'clip': 'Bow', 'loop': False, 'notes': 'a standing bow: down by 0.47 s, held to 1.33 s, up by 1.93 s'},
                      {'role': 'Talk', 'clip': 'Talk', 'loop': False, 'notes': 'the right hand up, palm up, a nod, the hand opens, down'}]}
(out / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
(out / 'rig.json').write_text(json.dumps({'input': '/'.join(Path(a.input).parts[-3:]), 'bones': len(arm.data.bones), 'vertices': len(body.data.vertices),
                                          'fingers': fingers, 'clips': {'Bow': list(bow.frame_range), 'Talk': list(talk.frame_range)}}, indent=2) + '\n')
print('RIG OK', json.dumps({'bones': len(arm.data.bones), 'fingers': fingers['detection'], 'sha256': digest}))
