"""Import Cairo's Breath of the Wild clips (assets/characters/cairo/botw.py) into /Game/CairoBotw, for Cairo with
the merged move set (his default in play; -rider=CairoBotw in scripted sessions).

    UnrealEditor-Cmd Yorimichi.uproject -run=pythonscript -script=Scripts/import_cairo_botw.py -unattended -nosplash -NullRHI -stdout

Each build/yorimichi/cairo/botw/fbx/A_<Clip>.fbx is imported onto SK_Cairo's skeleton at 30 fps as A_<Clip>, with the
shared character compression and no root motion. DA_CairoBotw is DA_Cairo (mesh, framing, skate bones) with Link's
moves in place of Cairo's own: the BOTW locomotion, crouching and armed blends and every action, on Cairo's clips, and
his own double jump, and his own bokken guard, parry and recoil for the guard without the shield (OWN). Cairo's own sword set, dashes and roll are cleared; the move set brings BOTW's.

Writes Content/Data/cairo/botw.json, the move record ACairoCharacter gives UBotwMoveSet. It is Link's record (moves.py
`record`, from the roster) with every length measured on Link's body (action paths, gait speeds, the swim hang) scaled
by Cairo's size against Link's (`body` / Link's scale), and BodyScale, the factor for BOTW's metres (`body`, Cairo's hip
height over Link's in BOTW units). Link's equipment is reused at Cairo's scale: each piece's hold moves from Link's
hand to Cairo's in the palm's frame, and its carry on the back from Link's chest to Cairo's in the body's frame. The
paraglider is placed from both glides instead (Glide's clip, posed): its canopy keeps its angle to the body and its
bar's middle goes between Cairo's hands, since his palms turn differently from Link's around the bar. A piece in
CARRY sits where it was fitted to Cairo's own mesh instead of where Link's chest puts it. Also writes
build/yorimichi/cairo/botw/unreal_import.json. Cairo's own assets must be byte-identical afterwards.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import hashlib, json, math, sys
from pathlib import Path
import unreal as U
sys.path.insert(0, str(Path(__file__).resolve().parent))
import animation_compression

OUT = yori.OUT / 'cairo' / 'botw'
CONFIG = json.loads((OUT / 'export.json').read_text())
LINK = next(c for c in json.loads((yori.OUT / 'botw' / 'export.json').read_text())['characters'] if c['name'] == 'Link')
CONTENT = Path(__file__).resolve().parents[1] / 'Content'
ROSTER = next(c for c in json.loads((CONTENT / 'Data' / 'botw' / 'roster.json').read_text())['characters'] if c['name'] == 'Link')
DATA = CONTENT / 'Data' / 'cairo'
DEST = '/Game/CairoBotw'
E = U.EditorAssetLibrary; AT = U.AssetToolsHelpers.get_asset_tools(); P = U.AnimPoseExtensions
# The paraglider's two handle tubes (right, left) in its own frame (cm): the straight stretch at the bottom of each of
# its U-shaped handles, measured on the mesh's vertices. The game fits the glider so they fall in Cairo's hands and puts
# each hand on its own.
GLIDER_GRIPS = [[[-24.8, -14.2, 1.2], [-30.5, 2.8, 1.1]], [[25.4, -14.2, 1.6], [30.1, 2.9, 1.0]]]
BODY = CONFIG['body']                      # Cairo's hips over Link's, in BOTW units
SIZE = BODY / CONFIG['link_scale']         # Cairo over Link as he plays (his mesh is scaled down)
# Carried pieces fitted to Cairo's mesh. Moved from Link's chest, the shield sank 4 cm into his deeper torso standing,
# and its top half stood behind his bigger head, which ran through it. `offset` (cm, his component space) goes from his
# chest bone to the piece's pivot along Rig.body's axes (level backward, left, up); the piece keeps its turn on Link's
# back, its face squared to his back and then turned by `pitch` degrees about his left axis (see `fitted`). The shield
# stands 2.7 cm off his back. In Link's idle, walk, run, dash, crouch, lock-on, glide, climb and swim retargeted onto
# him, his torso and clothes come at most 1 cm through its plate. It sits low enough that his head stays clear of it,
# except in the crouch: there his chest leans 70 degrees forward and his head dips 6 cm into its top edge.
CARRY = {'shield': {'offset': [16.59, 8.69, -13.13], 'pitch': 16}}
# Carried pieces moved out from where Link's chest puts them (cm along Rig.body's axes: backward, left, up): Link's sword
# and its sheath, placed from his slimmer chest, sank into Cairo's deeper torso with only the hilt showing at his neck.
PUSH = {'sword': [7., 0., 0.], 'sheath': [7., 0., 0.]}   # fitted in game: 4 cm still sank in at the hip running, 12 floated


def digests(folder):
    return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*.uasset')}


def fbx(name, skeleton):
    task = U.AssetImportTask()
    for prop, value in dict(filename=str(OUT / 'fbx' / f'A_{name}.fbx'), destination_path=DEST, destination_name=f'A_{name}',
                            automated=True, replace_existing=True, save=True).items():
        task.set_editor_property(prop, value)
    options = U.FbxImportUI()
    for prop, value in dict(automated_import_should_detect_type=False, import_materials=False, import_textures=False, import_as_skeletal=True,
                            import_mesh=False, import_animations=True, skeleton=skeleton, mesh_type_to_import=U.FBXImportType.FBXIT_ANIMATION).items():
        options.set_editor_property(prop, value)
    data = options.get_editor_property('anim_sequence_import_data')
    for prop, value in dict(animation_length=U.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME, use_default_sample_rate=False,
                            custom_sample_rate=CONFIG['fps'], import_bone_tracks=True, delete_existing_morph_target_curves=True,
                            do_not_import_curve_with_zero=False, convert_scene=True).items():
        data.set_editor_property(prop, value)
    task.set_editor_property('options', options)
    AT.import_asset_tasks([task])
    clip = next((a for a in (E.load_asset(p) for p in task.get_editor_property('imported_object_paths')) if isinstance(a, U.AnimSequence)), None)
    assert clip and clip.get_editor_property('skeleton') == skeleton, ('import failed', name)
    clip.set_editor_property('enable_root_motion', False)
    animation_compression.apply_to(clip)
    E.save_loaded_asset(clip)
    return clip


def speed_blend(name, skeleton, sequences, speeds, rates):
    """A 1D blend of `sequences` by ground speed (cm/s), each sample played at its rate (as import_botw.py's)."""
    factory = U.BlendSpaceFactory1D()
    factory.set_editor_property('target_skeleton', skeleton)
    blend = AT.create_asset(name, DEST, U.BlendSpace1D, factory)
    params = list(blend.get_editor_property('blend_parameters'))
    for key, value in dict(display_name='Speed (cm/s)', min=0., max=speeds[-1]).items():
        params[0].set_editor_property(key, value)
    blend.set_editor_property('blend_parameters', params)
    blend.set_editor_property('scale_animation', True)
    smoothing = list(blend.get_editor_property('interpolation_param'))
    smoothing[0].set_editor_property('interpolation_time', .12)
    blend.set_editor_property('interpolation_param', smoothing)
    assert U.WandererContentLibrary.configure_blend_space_with_rates(blend, sequences, speeds, rates), name
    E.save_loaded_asset(blend, False)
    return blend


# --- Equipment: Link's holds carried onto Cairo's hands and back ---------------------------------------------------
# Rotations are lists of their three columns (x, y, z axes), in each mesh's component space at the reference pose.

def sub(a, b): return [x - y for x, y in zip(a, b)]
def add(a, b): return [x + y for x, y in zip(a, b)]
def mul(a, s): return [x * s for x in a]
def dot(a, b): return sum(x * y for x, y in zip(a, b))
def cross(a, b): return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
def unit(a): return mul(a, 1. / math.sqrt(dot(a, a)))
def apply(R, v): return [sum(R[k][i] * v[k] for k in range(3)) for i in range(3)]   # R v
def apply_t(R, v): return [dot(column, v) for column in R]                         # R^T v
def compose(A, B): return [apply(A, column) for column in B]                       # A B
def compose_t(A, B): return [apply_t(A, column) for column in B]                   # A^T B


def frame(y, z):
    """The rotation whose Y axis is y and whose Z axis is z made perpendicular to it (botw.py's)."""
    y = unit(y)
    z = unit(sub(z, mul(y, dot(z, y))))
    return [cross(y, z), y, z]


class Rig:
    """A skeleton's pose (its reference pose unless given): each bone's component-space position (cm) and rotation."""

    def __init__(self, skeleton, names, pose=None):
        self.names = names   # role -> bone
        self.pose = pose or P.get_reference_pose(skeleton)

    def transform(self, bone):
        return P.get_bone_pose(self.pose, bone, U.AnimPoseSpaces.WORLD)

    def at(self, role):
        t = self.transform(self.names.get(role, role)).translation
        return [t.x, t.y, t.z]

    def rotation(self, bone):
        q = self.transform(bone).rotation
        return [[v.x, v.y, v.z] for v in (q.rotate_vector(U.Vector(1, 0, 0)), q.rotate_vector(U.Vector(0, 1, 0)), q.rotate_vector(U.Vector(0, 0, 1)))]

    def body(self):
        """The body's frame: forward, left (shoulder to shoulder, level) and the world's up (botw.py's)."""
        left = sub(self.at('upperarm_L'), self.at('upperarm_R'))
        left = unit([left[0], left[1], 0.])
        up = [0., 0., 1.]
        return [unit(cross(left, up)), left, up]

    def hand(self, side):
        """The palm's frame (y from the wrist to the knuckles, z from the index to the little finger) and its length."""
        knuckles = mul(add(self.at(f'finger_0_{side}'), self.at(f'finger_3_{side}')), .5)
        reach = sub(knuckles, self.at(f'hand_{side}'))
        return frame(reach, sub(self.at(f'finger_3_{side}'), self.at(f'finger_0_{side}'))), math.sqrt(dot(reach, reach))


def turn(axis, degrees):
    """The rotation by `degrees` about the unit vector `axis` (Rodrigues), as the images of the three axes."""
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    return [add(add(mul(e, c), mul(cross(axis, e), s)), mul(axis, dot(axis, e) * (1. - c))) for e in ([1., 0, 0], [0., 1, 0], [0., 0, 1])]


def align(a, b):
    """The smallest rotation taking the unit vector a onto the unit vector b."""
    v = cross(a, b)
    s = math.sqrt(dot(v, v))
    return turn(unit(v), math.degrees(math.atan2(s, dot(a, b)))) if s > 1e-9 else turn([1., 0, 0], 0.)


def fitted(R, rig, fit):
    """A carried piece's rotation and pivot from its fit (CARRY): its Z axis (a shield's face) squared to his back, on
    the side it points to now, then turned by `pitch` about his left axis."""
    B = rig.body()
    face = B[0] if dot(R[2], B[0]) > 0 else mul(B[0], -1.)
    R = compose(turn(B[1], fit['pitch']), compose(align(unit(R[2]), face), R))
    return R, add(rig.at('chest'), apply(B, fit['offset']))


def transform(R, p, scale):
    rotation = U.MathLibrary.make_rot_from_xz(U.Vector(*R[0]), U.Vector(*R[2]))
    return U.Transform(U.Vector(*p), rotation, U.Vector(scale, scale, scale))


def record_of(t):
    q = t.rotation
    return {'location': [round(v, 3) for v in (t.translation.x, t.translation.y, t.translation.z)],
            'rotation': [round(v, 6) for v in (q.x, q.y, q.z, q.w)], 'scale': round(t.scale3d.x, 4)}


def glider(link, cairo, item, scale):
    """The paraglider's hold, from Link and Cairo posed at the glide. Link holds it at Weapon_R (`item['hand']`), its bar
    across both hands: Cairo's grips are Link's weapon bones moved from each palm to his, the bar's middle goes between
    them and the canopy keeps its angle to the body. Returns the hold and each grip's miss (cm) once placed."""
    Bs, Bt = link.body(), cairo.body()
    grips = []
    for side in 'RL':
        role = f'hand_{side}'
        Fs, ls = link.hand(side)
        Ft, lt = cairo.hand(side)
        weapon = link.at(f'Weapon_{side}')
        grips.append((weapon, add(cairo.at(role), apply(Ft, mul(apply_t(Fs, sub(weapon, link.at(role))), lt / ls)))))
    middle_s = mul(add(grips[0][0], grips[1][0]), .5)
    middle_t = mul(add(grips[0][1], grips[1][1]), .5)
    to_cairo = lambda v: mul(apply(Bt, apply_t(Bs, v)), BODY)   # a length in Link's body frame, in Cairo's
    R = compose(Bt, compose_t(Bs, link.rotation(item['hand'])))
    p = add(middle_t, to_cairo(sub(link.at(item['hand']), middle_s)))
    held = U.MathLibrary.make_relative_transform(transform(R, p, scale), cairo.transform('hand_R'))
    miss = [round(math.sqrt(dot(d, d)), 1) for d in (sub(add(middle_t, to_cairo(sub(s, middle_s))), t) for s, t in grips)]
    return held, miss


def equipment(link, cairo, glide):
    """Cairo's equipment record: Link's pieces, held in Cairo's hands and carried on Cairo's chest as on Link's. Link holds
    a piece at a weapon bone under his wrist (Weapon_R, Weapon_L) and carries it at a bone under his chest (Pod_A). The
    paraglider (the piece with a clip) is held as in `glide`, the two rigs posed at the glide."""
    C = compose(cairo.body(), [apply_t(link.body(), axis) for axis in ([1., 0, 0], [0., 1, 0], [0., 0, 1])])   # A_t A_s^T
    scale = ROSTER['scale'] * SIZE
    record, checks = {}, {}
    for slot, item in ROSTER['moves']['equipment'].items():
        entry = {key: item[key] for key in ('mesh', 'clip', 'looks') if key in item}
        entry['hand'] = entry['back'] = ''
        if item.get('hand'):
            side = item['hand'][-1]
            role = f'hand_{side}'
            Fs, ls = link.hand(side)
            Ft, lt = cairo.hand(side)
            piece = link.transform(item['hand'])          # the piece sits at the weapon bone
            offset = sub([piece.translation.x, piece.translation.y, piece.translation.z], link.at(role))
            R = compose(Ft, compose_t(Fs, link.rotation(item['hand'])))
            p = add(cairo.at(role), apply(Ft, mul(apply_t(Fs, offset), lt / ls)))
            held = U.MathLibrary.make_relative_transform(transform(R, p, scale), cairo.transform(role))
            entry['hand'], entry['held'] = role, record_of(held)
            checks[slot] = {'hand_cm': [round(ls, 2), round(lt, 2)]}
            if 'clip' in item:
                held, miss = glider(*glide, item, scale)
                entry['grips'] = GLIDER_GRIPS
                entry['held'], checks[slot]['grip_miss_cm'] = record_of(held), miss
        if item.get('back') and item.get('carry'):
            carry = item['carry']
            local = U.Transform(U.Vector(*carry['location']), U.Quat(*carry['rotation']).rotator(), U.Vector(1, 1, 1))
            piece = U.MathLibrary.compose_transforms(local, link.transform(item['back']))
            Rp = [[v.x, v.y, v.z] for v in (piece.rotation.rotate_vector(U.Vector(1, 0, 0)), piece.rotation.rotate_vector(U.Vector(0, 1, 0)),
                                            piece.rotation.rotate_vector(U.Vector(0, 0, 1)))]
            offset = sub([piece.translation.x, piece.translation.y, piece.translation.z], link.at('chest'))
            R, p = compose(C, Rp), add(cairo.at('chest'), mul(apply(C, offset), BODY))
            if slot in CARRY:
                R, p = fitted(R, cairo, CARRY[slot])
            if slot in PUSH:
                p = add(p, apply(cairo.body(), PUSH[slot]))
            on_back = U.MathLibrary.make_relative_transform(transform(R, p, scale), cairo.transform('chest'))
            entry['back'], entry['carry'] = 'chest', record_of(on_back)
            # Where it sits in his reference pose (component cm): the fit's frame, for checking it offline.
            checks.setdefault(slot, {})['carry'] = {'pivot': [round(v, 2) for v in p], 'axes': [[round(v, 5) for v in a] for a in R],
                                                    'chest': [round(v, 2) for v in cairo.at('chest')],
                                                    'body': [[round(v, 5) for v in a] for a in cairo.body()]}
        record[slot] = entry
    return record, checks


# --- Import ----------------------------------------------------------------------------------------------------------

cairo_folder = CONTENT / 'Cairo'
before = digests(cairo_folder)
mesh = E.load_asset('/Game/Cairo/SK_Cairo'); assert mesh, 'import Cairo first (unreal.cairo)'
skeleton = mesh.skeleton
link_mesh = E.load_asset(ROSTER['mesh']); assert link_mesh, 'import the BOTW characters first (unreal.botw)'
if E.does_directory_exist(DEST):
    E.delete_directory(DEST)
E.make_directory(DEST)

clips = {}
for name, clip in CONFIG['clips'].items():
    sequence = fbx(name, skeleton)
    length = sequence.get_editor_property('sequence_length')
    assert abs(length - clip['frames'] / CONFIG['fps']) < .002, (name, length, clip['frames'])
    clips[name] = sequence
U.log(f'CAIRO BOTW: {len(clips)} clips imported')

moves = LINK['moves']
clip = lambda name: clips[name]
blend = lambda kind, title: speed_blend(f'BS_CairoBotw{title}', skeleton, [clip(s['clip']) for s in moves['blends'][kind]],
                                        [round(s['speed'] * SIZE, 1) for s in moves['blends'][kind]], [s['rate'] for s in moves['blends'][kind]])
locomotion, crouching, armed = blend('locomotion', 'Locomotion'), blend('crouching', 'Crouching'), blend('armed', 'ArmedLocomotion')
gaits = [round(s['speed'] * SIZE, 1) for s in moves['blends']['locomotion']]
actions = {'Idle': clip(LINK['roles']['idle'])}
actions.update({action: clip(entry['clip']) for action, entry in ROSTER['moves']['actions'].items()})
# The merged move set's double jump is Cairo's own somersault (UBotwMoveSet::StartDoubleJump), on his own skeleton.
actions['DoubleJump'] = E.load_asset('/Game/Cairo/A_DoubleJump')
assert actions['DoubleJump'], 'Cairo has no double jump (build unreal.cairo)'
# Without the shield he guards and parries with his own two-handed bokken clips rather than Link's sword-only ones
# (which barely show the blade on him): his guard stance, his parry and its recoil, timed by their authored windows
# (source-manifest.json: the parry deflects from 0.0333 s to 0.3 s and may be cancelled from 0.3333 s; the recoil's
# counter opens at 0.1 s).
OWN = {'SwordGuardCarry': ('A_SwordIdle', {'loop': True}),
       'SwordParry': ('A_SwordParry', {'guard': [[0.0333, 0.3]], 'input': 0.3333, 'cancel': 0.3333, 'idle': 0.4}),
       'SwordGuardHit': ('A_SwordParryHit', {'guard': [[0.0, 0.15]], 'input': 0.1, 'cancel': 0.1, 'idle': 0.15})}
own_timing = {}
for action, (asset, timing) in OWN.items():
    sequence = E.load_asset(f'/Game/Cairo/{asset}')
    assert sequence, (f'Cairo has no {asset} (build unreal.cairo)')
    actions[action] = sequence
    length = round(sequence.get_editor_property('sequence_length'), 4)
    own_timing[action] = {'clip': asset[2:], 'length': length, 'loop': False, 'root': 'keep', 'rate': 1., 'start': 0., 'end': length,
                          'blend': .05, 'active': [], 'guard': [], 'input': -1, 'cancel': -1, 'idle': -1, 'bind': -1, 'unbind': -1, **timing}

definition = E.duplicate_asset('/Game/Cairo/DA_Cairo', f'{DEST}/DA_CairoBotw')
assert definition, 'DA_Cairo could not be copied'
for key, value in dict(locomotion=locomotion, crouching=crouching, armed_locomotion=armed, armed_crouching=None, actions=actions,
                       use_authored_movement=True, walk_speed=gaits[1], jog_speed=gaits[1], run_speed=gaits[2], sprint_speed=gaits[3],
                       crouch_speed=round(moves['blends']['crouching'][-1]['speed'] * SIZE, 1),
                       ground_dash_profile=[], air_dash_profile=[], roll_profile=[], roll_dive_takeoff=0., roll_dive_touchdown=0.,
                       sword_mesh=None, sword_clips=[]).items():
    definition.set_editor_property(key, value)
E.save_loaded_asset(definition, False)

# The move record: Link's, its body-measured lengths scaled to Cairo.
scaled = {}
for name, entry in ROSTER['moves']['actions'].items():
    entry = dict(entry)
    if 'path' in entry:
        entry['path'] = [[round(x * SIZE, 2), round(y * SIZE, 2), round(z * SIZE, 2), yaw] for x, y, z, yaw in entry['path']]
    if 'speed' in entry:
        entry['speed'] = round(entry['speed'] * SIZE, 1)
    scaled[name] = entry
scaled.update(own_timing)
params = dict(ROSTER['moves']['params'])
params['SwimHang'] = round(params['SwimHang'] * SIZE, 2)
params['BodyScale'] = BODY
params['TwoHandedGuard'] = 1   # his own bokken guard (OWN) holds the grip with both hands
names = {**LINK['skate'], 'pelvis': 'Waist'}   # botw.py's bone map
link, cairo = Rig(link_mesh.skeleton, names), Rig(skeleton, {})
glide, options = ROSTER['moves']['actions']['Glide']['clip'], U.AnimPoseEvaluationOptions()
link_glide = E.load_asset(ROSTER['clips'][glide]['path']); assert link_glide, ('Link has no glide clip', glide)
gear, gear_checks = equipment(link, cairo, (Rig(link_mesh.skeleton, names, P.get_anim_pose_at_time(link_glide, 0., options)),
                                            Rig(skeleton, {}, P.get_anim_pose_at_time(clips[glide], 0., options))))
body_check = cairo.at('pelvis')[2] / link.at('pelvis')[2]
record = {'actions': scaled, 'params': params, 'equipment': gear}
DATA.mkdir(parents=True, exist_ok=True)
(DATA / 'botw.json').write_text(json.dumps(record, indent=1) + '\n')

after = digests(cairo_folder)
changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
report = {'source': CONFIG['source'], 'source_sha256': CONFIG['source_sha256'], 'body': BODY, 'size': SIZE,
          'body_from_reference_poses': round(body_check, 4), 'gaits_cm': gaits, 'equipment': gear, 'hands': gear_checks,
          'definition': definition.get_path_name(), 'clips': {n: {'path': s.get_path_name(), 'length': round(s.get_editor_property('sequence_length'), 4)}
                                                               for n, s in clips.items()}, 'changed_cairo_files': changed}
(OUT / 'unreal_import.json').write_text(json.dumps(report, indent=1) + '\n')
assert not changed, ('Cairo assets changed', changed)
assert max(gear_checks['glider']['grip_miss_cm']) < 6., ('the glider bar misses his hands', gear_checks['glider'])
assert abs(body_check - BODY) < .02, ('the reference poses disagree with the export', body_check, BODY)
U.log(f'CAIRO BOTW IMPORT COMPLETE: {len(clips)} clips, {len(actions)} actions, body {BODY}, size {SIZE:.3f}')
