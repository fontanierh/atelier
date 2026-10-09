"""Import a character's adventure clips (assets/characters/adventure/retarget.py) as its merged move set, as its
adventure.toml (assets/characters/<id>/adventure.toml) lays it out. ADVENTURE_CHARACTER picks the character (default: cairo).

    UnrealEditor-Cmd Yorimichi.uproject -run=pythonscript -script=Scripts/import_adventure_moveset.py -unattended -nosplash -NullRHI -stdout

Each build/yorimichi/<id>/adventure/fbx/A_<Clip>.fbx is imported onto the character's skeleton (`mesh`) at 30 fps into
`dest`, with the shared character compression and no root motion. `definition` is a copy of `base` (mesh, framing,
skate bones) with Reference's moves in place of the base's own: the adventure locomotion, crouching and armed blends and every
action, on the character's clips, plus the donor's double jump and its bokken guard, parry and recoil for the guard
without the shield (the donor is the character whose adventure.toml has a [donor] table, Cairo: on the donor these are its own
imported clips, on anyone else their retargeted copies at the donor's rate). The base's sword set, dashes and roll are
cleared; the move set brings the adventure library's. With `keep_base_actions` the base's own clips (another character's gestures) stay
beside the move set's, and the donor's gestures fill in where the base has none.

Writes Content/Data/<id>/adventure.json, the move record the character gives UAdventureMoveSet. It is Reference's record (moves.py
`record`, from the roster) with every length measured on Reference's body (action paths, gait speeds, the swim hang) scaled
by the character's size against Reference's (`body` / Reference's scale), and BodyScale, the factor for the adventure library's metres (`body`, its
hip height over Reference's in adventure units). Reference's equipment is reused at its scale: each piece's hold moves from Reference's hand
to the character's in the palm's frame, and its carry on the back from Reference's chest to the character's in the body's
frame. The paraglider is placed from both glides instead (Glide's clip, posed): its canopy keeps its angle to the body
and its bar's middle goes between the character's hands, since its palms turn differently from Reference's around the bar.
The character's [fit] tables then fit the carried pieces to its own mesh (`equipment`). Also writes
build/yorimichi/<id>/adventure/unreal_import.json. When `definition` lies outside the base's folder, that folder's assets
must be byte-identical afterwards.
"""
import os
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import hashlib, json, math, sys, tomllib
from pathlib import Path
import unreal as U
sys.path.insert(0, str(Path(__file__).resolve().parent))
import animation_compression

CHARACTER = os.environ.get('ADVENTURE_CHARACTER', 'cairo')
CHARS = yori.ASSETS / 'characters'
adventure = {p.parent.name: tomllib.loads(p.read_text()) for p in CHARS.glob('*/adventure.toml')}
SPEC = adventure[CHARACTER]
# The donor of the set's own clips (its double jump and bokken guard): the one character with a [donor] table.
DONOR_ID = next(c for c, spec in adventure.items() if 'donor' in spec)
DONOR = adventure[DONOR_ID]['donor']
OUT = yori.OUT / CHARACTER / 'adventure'
CONFIG = json.loads((OUT / 'export.json').read_text())
REFERENCE = next(c for c in json.loads((yori.OUT / 'adventure' / 'export.json').read_text())['characters'] if c['name'] == 'Reference')
CONTENT = Path(__file__).resolve().parents[1] / 'Content'
ROSTER = next(c for c in json.loads((CONTENT / 'Data' / 'adventure' / 'reference.json').read_text())['characters'] if c['name'] == 'Reference')
DATA = CONTENT / 'Data' / CHARACTER
DEST = SPEC['dest']
NAME = SPEC['mesh'].rsplit('/SK_', 1)[1]   # the character's asset name (SK_<Name>)
E = U.EditorAssetLibrary; AT = U.AssetToolsHelpers.get_asset_tools(); P = U.AnimPoseExtensions
BODY = CONFIG['body']                      # its hips over Reference's, in adventure units
SIZE = BODY / CONFIG['reference_scale']         # it over Reference as it plays (its mesh is scaled down)
# The carried pieces fitted to its own mesh (adventure.toml [fit], with the measurements behind each number): `carry` places
# a piece from its chest bone (`fitted`), `push` moves it out (cm along Rig.body's axes: backward, left, up), `tilt`
# pitches it about its left axis through the sword's pommel, `yaw` turns it across its back about a mount `mount` of
# the sword's length below the pommel, and `crouch` gives the second carry the game blends to as it crouches.
FIT = SPEC.get('fit', {})
CARRY, PUSH, TILT, YAW = (FIT.get(k, {}) for k in ('carry', 'push', 'tilt', 'yaw'))
MOUNT, CROUCH = FIT.get('mount', 0.), FIT.get('crouch', {})


def ends(mesh, R, p, scale):
    """The two ends of a piece's longest axis (component cm), from its mesh's bounds: the one higher on him first."""
    box = E.load_asset(mesh).get_bounding_box()
    lo, hi = [box.min.x, box.min.y, box.min.z], [box.max.x, box.max.y, box.max.z]
    k = max(range(3), key=lambda i: hi[i] - lo[i])
    middle = [(a + b) * .5 for a, b in zip(lo, hi)]
    out = []
    for v in (lo[k], hi[k]):
        local = list(middle); local[k] = v
        out.append(add(p, mul(apply(R, local), scale)))
    return sorted(out, key=lambda e: -e[2])


def digests(folder):
    return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*.uasset')}


def fbx(name, skeleton, fps=None):
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
                            custom_sample_rate=fps or CONFIG['fps'], import_bone_tracks=True, delete_existing_morph_target_curves=True,
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
    """A 1D blend of `sequences` by ground speed (cm/s), each sample played at its rate (as import_adventure.py's)."""
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


# --- Equipment: Reference's holds carried onto the wearer's hands and back ----------------------------------------------
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
    """The rotation whose Y axis is y and whose Z axis is z made perpendicular to it (adventure/retarget.py's)."""
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
        """The body's frame: forward, left (shoulder to shoulder, level) and the world's up (adventure/retarget.py's)."""
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
    """A carried piece's rotation and pivot from its fit (CARRY): its Z axis (a shield's face) squared to the back, on
    the side it points to now, then turned by `pitch` about the body's left axis."""
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


def glider(reference, wearer, item, scale):
    """The paraglider's hold, from Reference and the wearer posed at the glide. Reference holds it at Weapon_R (`item['hand']`), its bar
    across both hands: the wearer's grips are Reference's weapon bones moved from each palm to its, the bar's middle goes between
    them and the canopy keeps its angle to the body. Returns the hold and each grip's miss (cm) once placed."""
    Bs, Bt = reference.body(), wearer.body()
    grips = []
    for side in 'RL':
        role = f'hand_{side}'
        Fs, ls = reference.hand(side)
        Ft, lt = wearer.hand(side)
        weapon = reference.at(f'Weapon_{side}')
        grips.append((weapon, add(wearer.at(role), apply(Ft, mul(apply_t(Fs, sub(weapon, reference.at(role))), lt / ls)))))
    middle_s = mul(add(grips[0][0], grips[1][0]), .5)
    middle_t = mul(add(grips[0][1], grips[1][1]), .5)
    to_wearer = lambda v: mul(apply(Bt, apply_t(Bs, v)), BODY)   # a length in Reference's body frame, in the wearer's
    R = compose(Bt, compose_t(Bs, reference.rotation(item['hand'])))
    p = add(middle_t, to_wearer(sub(reference.at(item['hand']), middle_s)))
    held = U.MathLibrary.make_relative_transform(transform(R, p, scale), wearer.transform('hand_R'))
    miss = [round(math.sqrt(dot(d, d)), 1) for d in (sub(add(middle_t, to_wearer(sub(s, middle_s))), t) for s, t in grips)]
    return held, miss


def equipment(reference, wearer, glide):
    """The wearer's equipment record: Reference's pieces, held in its hands and carried on its chest as on Reference's. Reference holds
    a piece at a weapon bone under his wrist (Weapon_R, Weapon_L) and carries it at a bone under his chest (Pod_A). The
    paraglider (the piece with a clip) is held as in `glide`, the two rigs posed at the glide."""
    C = compose(wearer.body(), [apply_t(reference.body(), axis) for axis in ([1., 0, 0], [0., 1, 0], [0., 0, 1])])   # A_t A_s^T
    scale = ROSTER['scale'] * SIZE
    record, checks, tilt_centre = {}, {}, {}
    for slot, item in sorted(ROSTER['moves']['equipment'].items(), key=lambda kv: kv[0] != 'sword'):   # the sword's pommel is TILT's centre
        entry = {key: item[key] for key in ('mesh', 'clip', 'looks') if key in item}
        entry['hand'] = entry['back'] = ''
        if item.get('hand'):
            side = item['hand'][-1]
            role = f'hand_{side}'
            Fs, ls = reference.hand(side)
            Ft, lt = wearer.hand(side)
            piece = reference.transform(item['hand'])          # the piece sits at the weapon bone
            offset = sub([piece.translation.x, piece.translation.y, piece.translation.z], reference.at(role))
            R = compose(Ft, compose_t(Fs, reference.rotation(item['hand'])))
            p = add(wearer.at(role), apply(Ft, mul(apply_t(Fs, offset), lt / ls)))
            held = U.MathLibrary.make_relative_transform(transform(R, p, scale), wearer.transform(role))
            entry['hand'], entry['held'] = role, record_of(held)
            checks[slot] = {'hand_cm': [round(ls, 2), round(lt, 2)]}
            if 'clip' in item:
                held, miss = glider(*glide, item, scale)
                entry['held'], checks[slot]['grip_miss_cm'] = record_of(held), miss
                # Its place on the body on the neutral glide and the elbows there, in the root bone's frame (the clip's
                # root is turned from the game's: in component space the glider came out a quarter turn off): the game
                # holds the glider from a glide's first frame, before a straight glide has fitted it to the hands.
                root = glide[1].transform(P.get_bone_names(glide[1].pose)[0])
                on_body = U.MathLibrary.compose_transforms(held, glide[1].transform('hand_R'))
                entry['on_root'] = record_of(U.MathLibrary.make_relative_transform(on_body, root))
                entry['elbows_on_root'] = [[round(v, 3) for v in (lambda e: [e.x, e.y, e.z])(U.MathLibrary.inverse_transform_location(
                    root, U.Vector(*glide[1].at(f'forearm_{side}'))))] for side in 'RL']
        if item.get('back') and item.get('carry'):
            carry = item['carry']
            local = U.Transform(U.Vector(*carry['location']), U.Quat(*carry['rotation']).rotator(), U.Vector(1, 1, 1))
            piece = U.MathLibrary.compose_transforms(local, reference.transform(item['back']))
            Rp = [[v.x, v.y, v.z] for v in (piece.rotation.rotate_vector(U.Vector(1, 0, 0)), piece.rotation.rotate_vector(U.Vector(0, 1, 0)),
                                            piece.rotation.rotate_vector(U.Vector(0, 0, 1)))]
            offset = sub([piece.translation.x, piece.translation.y, piece.translation.z], reference.at('chest'))
            R, p = compose(C, Rp), add(wearer.at('chest'), mul(apply(C, offset), BODY))
            if slot in CARRY:
                R, p = fitted(R, wearer, CARRY[slot])
            if slot in PUSH:
                p = add(p, apply(wearer.body(), PUSH[slot]))
            if slot in TILT:
                T = turn(wearer.body()[1], -TILT[slot])
                if slot == 'sword':
                    tilt_centre['sword'] = ends(item['mesh'], R, p, scale)[0]
                centre = tilt_centre['sword']
                R, p = compose(T, R), add(centre, apply(T, sub(p, centre)))
            if slot in YAW:
                T = turn(wearer.body()[0], YAW[slot])
                if slot == 'sword':
                    top, bottom = ends(item['mesh'], R, p, scale)
                    tilt_centre['mount'] = add(top, mul(sub(bottom, top), MOUNT))
                centre = tilt_centre['mount']
                R, p = compose(T, R), add(centre, apply(T, sub(p, centre)))
            on_back = U.MathLibrary.make_relative_transform(transform(R, p, scale), wearer.transform('chest'))
            entry['back'], entry['carry'] = 'chest', record_of(on_back)
            if CROUCH and slot in YAW:
                if slot == 'sword':
                    top, bottom = ends(item['mesh'], R, p, scale)
                    along = unit(sub(top, bottom))
                    # the chest's backward axis, as the candidates were filmed
                    back = cross(sub(wearer.at('clavicle_L'), wearer.at('clavicle_R')), sub(wearer.at('neck'), wearer.at('chest')))
                    back = mul(back, 1. if dot(back, sub(p, wearer.at('chest'))) > 0. else -1.)
                    back = unit(sub(back, mul(along, dot(back, along))))
                    tilt_centre['crouch'] = (add(top, mul(sub(bottom, top), CROUCH['pivot'])), back, cross(back, along))
                centre, back, side = tilt_centre['crouch']
                T = compose(turn(side, CROUCH['pitch']), turn(back, CROUCH['yaw']))
                Rc, pc = compose(T, R), add(add(centre, apply(T, sub(p, centre))), mul(back, CROUCH['out']))
                crouched = U.MathLibrary.make_relative_transform(transform(Rc, pc, scale), wearer.transform('chest'))
                entry['crouch'] = record_of(crouched)
            # Where it sits in the wearer's reference pose (component cm): the fit's frame, for checking it offline.
            checks.setdefault(slot, {})['carry'] = {'pivot': [round(v, 2) for v in p], 'axes': [[round(v, 5) for v in a] for a in R],
                                                    'chest': [round(v, 2) for v in wearer.at('chest')],
                                                    'body': [[round(v, 5) for v in a] for a in wearer.body()]}
        record[slot] = entry
    return record, checks


# --- Import ----------------------------------------------------------------------------------------------------------

base, target = SPEC['base'], SPEC['definition']
base_folder = base.rsplit('/', 1)[0]
protect = not target.startswith(base_folder + '/')   # the copy goes elsewhere: the base's own assets must not change
base_files = CONTENT / base_folder.removeprefix('/Game/')
before = digests(base_files) if protect else {}
mesh = E.load_asset(SPEC['mesh']); assert mesh, f'import {NAME} first (unreal.{CHARACTER.replace("-", "_")})'
skeleton = mesh.skeleton
reference_mesh = E.load_asset(ROSTER['mesh']); assert reference_mesh, 'import the adventure characters first (unreal.adventure)'
if E.does_directory_exist(DEST):
    E.delete_directory(DEST)
E.make_directory(DEST)

clips = {}
for name, clip in CONFIG['clips'].items():
    sequence = fbx(name, skeleton)
    length = sequence.get_editor_property('sequence_length')
    assert abs(length - clip['frames'] / CONFIG['fps']) < .002, (name, length, clip['frames'])
    clips[name] = sequence
for name, clip in CONFIG.get('own', {}).items():   # the donor's own clips, retargeted onto another character
    sequence = fbx(name, skeleton, clip['fps'])
    assert abs(sequence.get_editor_property('sequence_length') - clip['frames'] / clip['fps']) < .002, (name, clip)
    clips['Own' + name] = sequence
U.log(f'Adventure: {len(clips)} clips imported for {NAME}')

moves = REFERENCE['moves']
clip = lambda name: clips[name]
blend = lambda kind, title: speed_blend(f'BS_{NAME}Adventure{title}', skeleton, [clip(s['clip']) for s in moves['blends'][kind]],
                                        [round(s['speed'] * SIZE, 1) for s in moves['blends'][kind]], [s['rate'] for s in moves['blends'][kind]])
locomotion, crouching, armed = blend('locomotion', 'Locomotion'), blend('crouching', 'Crouching'), blend('armed', 'ArmedLocomotion')
gaits = [round(s['speed'] * SIZE, 1) for s in moves['blends']['locomotion']]
actions = {'Idle': clip(REFERENCE['roles']['idle'])}
actions.update({action: clip(entry['clip']) for action, entry in ROSTER['moves']['actions'].items()})


def own(clip):
    """One of the donor's clips in the set: the donor's own imported clip on itself, its retargeted copy on anyone else."""
    sequence = E.load_asset(f"{DONOR['folder']}/A_{clip}") if CHARACTER == DONOR_ID else clips.get('Own' + clip)
    assert sequence, f'no {clip} (build unreal.{DONOR_ID}, or retarget.py --dump-own)'
    return sequence


# The merged move set's double jump is the donor's own somersault (UAdventureMoveSet::StartDoubleJump).
actions['DoubleJump'] = own(DONOR['double_jump'])
# The donor's guard without the shield (adventure.toml [donor.actions]: its clips and authored windows).
own_timing = {}
for action, timing in DONOR['actions'].items():
    timing = dict(timing)
    clip_name = timing.pop('clip')
    actions[action] = sequence = own(clip_name)
    length = round(sequence.get_editor_property('sequence_length'), 4)
    own_timing[action] = {'clip': clip_name, 'length': length, 'loop': False, 'root': 'keep', 'rate': 1., 'start': 0.,
                          'end': length, 'blend': .05, 'active': [], 'guard': [], 'input': -1, 'cancel': -1, 'idle': -1, 'bind': -1,
                          'unbind': -1, **timing}

base_definition = E.load_asset(base)
assert base_definition, f'{base} could not be loaded'
# Class defaults can keep a deleted definition alive. Preserve the target and its references on incremental imports.
definition = E.load_asset(target) if E.does_asset_exist(target) else E.duplicate_asset(base, target)
assert definition, f'{base} could not be copied'
for key in ('mesh', 'rest_ankle_heights', 'sole_height', 'camera_height', 'skate_bones', 'skate_board_scale'):
    definition.set_editor_property(key, base_definition.get_editor_property(key))
# The donor's everyday gestures ([donor] gestures: wave, interact, sit), retargeted, where the base has none of its own.
for name in DONOR['gestures']:
    if 'Own' + name in clips:
        actions.setdefault(name, clips['Own' + name])
# The base's own clips (another character's gestures: Kaede's bow and words) stay beside the move set's.
for action, sequence in (dict(base_definition.get_editor_property('actions')) if SPEC['keep_base_actions'] else {}).items():
    actions.setdefault(str(action), sequence)
for key, value in dict(locomotion=locomotion, crouching=crouching, armed_locomotion=armed, armed_crouching=None, actions=actions,
                       use_authored_movement=True, walk_speed=gaits[1], jog_speed=gaits[1], run_speed=gaits[2], sprint_speed=gaits[3],
                       crouch_speed=round(moves['blends']['crouching'][-1]['speed'] * SIZE, 1),
                       ground_dash_profile=[], air_dash_profile=[], roll_profile=[], roll_dive_takeoff=0., roll_dive_touchdown=0.,
                       sword_mesh=None, sword_clips=[]).items():
    definition.set_editor_property(key, value)
E.save_loaded_asset(definition, False)

# The move record: Reference's, its body-measured lengths scaled to the character.
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
params['TwoHandedGuard'] = 1   # the donor's bokken guard holds the grip with both hands
names = {**REFERENCE['skate'], 'pelvis': 'Waist'}   # adventure/retarget.py's bone map
reference, wearer = Rig(reference_mesh.skeleton, names), Rig(skeleton, {})
glide, options = ROSTER['moves']['actions']['Glide']['clip'], U.AnimPoseEvaluationOptions()
reference_glide = E.load_asset(ROSTER['clips'][glide]['path']); assert reference_glide, ('Reference has no glide clip', glide)
gear, gear_checks = equipment(reference, wearer, (Rig(reference_mesh.skeleton, names, P.get_anim_pose_at_time(reference_glide, 0., options)),
                                            Rig(skeleton, {}, P.get_anim_pose_at_time(clips[glide], 0., options))))
body_check = wearer.at('pelvis')[2] / reference.at('pelvis')[2]
record = {'actions': scaled, 'params': params, 'equipment': gear}
DATA.mkdir(parents=True, exist_ok=True)
(DATA / 'adventure.json').write_text(json.dumps(record, indent=1) + '\n')

after = digests(base_files) if protect else {}
changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
report = {'source': CONFIG['source'], 'source_sha256': CONFIG['source_sha256'], 'body': BODY, 'size': SIZE,
          'body_from_reference_poses': round(body_check, 4), 'gaits_cm': gaits, 'equipment': gear, 'hands': gear_checks,
          'definition': definition.get_path_name(), 'clips': {n: {'path': s.get_path_name(), 'length': round(s.get_editor_property('sequence_length'), 4)}
                                                               for n, s in clips.items()}, 'changed_base_files': changed}
(OUT / 'unreal_import.json').write_text(json.dumps(report, indent=1) + '\n')
assert not changed, (f'{base_folder} assets changed', changed)
assert max(gear_checks['glider']['grip_miss_cm']) < 6., ('the glider bar misses the hands', gear_checks['glider'])
assert abs(body_check - BODY) < .02, ('the reference poses disagree with the export', body_check, BODY)
U.log(f'{CHARACTER.upper().replace("-", " ")} ADVENTURE IMPORT COMPLETE: {len(clips)} clips, {len(actions)} actions, body {BODY}, size {SIZE:.3f}')
