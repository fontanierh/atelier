"""The horses' rider contacts: verifies the committed library and samples where a rider sits, stands and holds the reins.

    blender -b --python games/yorimichi/assets/horses/build.py

The library under games/yorimichi/assets/horses/ is committed source like every other GLB in assets/: six breeds
(<breed>/horse.glb, with its eleven clips and solved rein bones) and seven tack sets (<breed>/tack/Saddle_<id>.glb,
Reins_<id>.glb), each self-contained with its base-colour images, plus the coat masks and coat variants under coats/.
manifest.json declares the breeds, tack sets, clips, coat masks and palettes once, and the size and checksum of every
GLB; this step checks those first.

It then measures each breed's rest contacts and samples the reference breed's clips at 60 Hz into
build/yorimichi/horses/manifest.json, in Yorimichi's rider space (metres, +X forward, +Y left, +Z up, origin on the
ground between the hooves):
- breeds.<slug>.contacts: saddle_root, seat_z, seat_offset_z, scale_ratio (to the reference breed's saddle height),
  stirrup_L/R (top centre of each stirrup tread) and grip_L/R (where the rider's fists hold the reins at Idle's first
  frame);
- clips.<clip>: duration, frames, loop and the per-frame trajectory of the seat, saddle, spine, neck, head, bit,
  stirrup treads, rein grips and rein bones, with the spine pitch.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'world'))
import yori  # noqa: E402

OUT = yori.OUT / 'horses'
FPS = 60
LIBRARY = json.loads((HERE / 'manifest.json').read_text())
BREEDS = tuple(LIBRARY['breeds'])
REFERENCE = LIBRARY['reference_breed']
SADDLE_HEIGHT = 1.5993   # the reference breed's Saddle_Root height (m): scale_ratio is a breed's height over this
SAMPLED = ('Saddle_Root', 'Spine_1', 'Spine_2', 'Neck_1', 'Head', 'Bit',
           'Stirrup_2_L', 'Stirrup_2_R', 'Reins_5_L', 'Reins_5_R', 'Reins_C')


def yori_vec(v_horse_world):
    """Convert horse.glb Blender world vector (+X left, -Y forward, +Z up) to Yorimichi space (+X forward, +Y left, +Z up)."""
    return [round(-v_horse_world.y, 4), round(v_horse_world.x, 4), round(v_horse_world.z, 4)]


def grips(r5L, r5R, rc):
    """The rider's closed-fist grip points on the curved rein arch between Reins_C and Reins_5_L/R (Blender world)."""
    return tuple(Vector((
        rc.x + 0.44 * (r5.x - rc.x),
        rc.y + 0.11 * (r5.y - rc.y),
        rc.z + 0.44 * (r5.z - rc.z) + 0.001,
    )) for r5 in (r5L, r5R))


def open_horse(slug):
    """A fresh scene at FPS holding the breed's horse.glb, and its armature."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps = FPS
    sc.render.fps_base = 1.0
    bpy.ops.import_scene.gltf(filepath=str(HERE / slug / 'horse.glb'))
    return sc, [o for o in bpy.data.objects if o.type == 'ARMATURE'][0]


def play(arm, clip_name):
    act = bpy.data.actions[clip_name]
    arm.animation_data_create()
    arm.animation_data.action = act
    arm.animation_data.action_slot = act.slots[0]
    return act


def measure_breed_contacts(slug):
    """`slug`'s contacts (Yorimichi space) and its stirrup tread centres at rest (Blender world): the saddle leather's
    seat height, the top centre of each étrier tread, and the rein grips at Idle's first frame."""
    sc, arm = open_horse(slug)
    mw = arm.matrix_world.copy()

    bpy.ops.import_scene.gltf(filepath=str(HERE / slug / 'tack/Saddle_00.glb'))
    sad_mesh = [o for o in bpy.data.objects if o.type == 'MESH' and 'Saddle_00_Model__Mt_Saddle' in o.name][0]
    mw_sad = sad_mesh.matrix_world.copy()

    rest_bones = {b.name: mw @ b.head_local for b in arm.data.bones}
    s = rest_bones['Saddle_Root'].z / SADDLE_HEIGHT
    sad_y = rest_bones['Saddle_Root'].y

    seat_zs = [
        (mw_sad @ v.co).z for v in sad_mesh.data.vertices
        if abs((mw_sad @ v.co).x) < 0.04 * s and (sad_y - 0.12 * s) <= (mw_sad @ v.co).y <= (sad_y - 0.05 * s)
    ]
    seat_z = max(seat_zs)
    seat_offset_z = seat_z - rest_bones['Saddle_Root'].z

    tread_rest_w = {}
    for side in ('L', 'R'):
        vg_idx = sad_mesh.vertex_groups[f'Stirrup_2_{side}'].index
        st_pts = [
            mw_sad @ v.co for v in sad_mesh.data.vertices
            if any(g.group == vg_idx and g.weight > 0.3 for g in v.groups)
        ]
        min_z = min(p.z for p in st_pts)
        bot_pts = [p for p in st_pts if p.z <= min_z + 0.035 * s]
        tx = 0.5 * (min(p.x for p in bot_pts) + max(p.x for p in bot_pts))
        ty = 0.5 * (min(p.y for p in bot_pts) + max(p.y for p in bot_pts))
        tz = min_z + 0.022 * s
        tread_rest_w[side] = Vector((tx, ty, tz))

    play(arm, 'Idle')
    sc.frame_set(0)
    bpy.context.view_layer.update()
    grip_L, grip_R = grips(*(mw @ arm.pose.bones[b].head for b in ('Reins_5_L', 'Reins_5_R', 'Reins_C')))
    contacts = {
        'scale_ratio': round(s, 5),
        'saddle_root': yori_vec(rest_bones['Saddle_Root']),
        'seat_z': round(seat_z, 4),
        'seat_offset_z': round(seat_offset_z, 4),
        'stirrup_L': yori_vec(tread_rest_w['L']),
        'stirrup_R': yori_vec(tread_rest_w['R']),
        'grip_L': yori_vec(grip_L),
        'grip_R': yori_vec(grip_R),
    }
    return contacts, tread_rest_w


def sample_reference_clips(contacts, tread_rest_w):
    """Every clip of the reference breed sampled at 60 Hz in Yorimichi rider space, from its contacts and stirrup
    tread centres (measure_breed_contacts)."""
    sc, arm = open_horse(REFERENCE)
    mw = arm.matrix_world.copy()
    rest_bones = {b.name: mw @ b.head_local for b in arm.data.bones}
    s = rest_bones['Saddle_Root'].z / SADDLE_HEIGHT
    seat_offset_z = contacts['seat_offset_z']
    rest_st_inv = {
        side: (mw @ arm.data.bones[f'Stirrup_2_{side}'].matrix_local).inverted()
        for side in ('L', 'R')
    }

    clips_out = {}
    for clip_name, clip in LIBRARY['clips'].items():
        act = play(arm, clip_name)
        f_end_60 = round(act.frame_range[1])
        duration = round(f_end_60 / FPS, 4)
        is_loop = clip['loop']
        n_frames_60 = max(1, round(duration * FPS) + (0 if is_loop else 1))

        frames = []
        for f60 in range(n_frames_60):
            sc.frame_set(min(f_end_60, f60))
            bpy.context.view_layer.update()
            pts = {b: (mw @ arm.pose.bones[b].head).copy() for b in SAMPLED}
            tread_L = (mw @ arm.pose.bones['Stirrup_2_L'].matrix) @ rest_st_inv['L'] @ tread_rest_w['L']
            tread_R = (mw @ arm.pose.bones['Stirrup_2_R'].matrix) @ rest_st_inv['R'] @ tread_rest_w['R']
            grip_L, grip_R = grips(pts['Reins_5_L'], pts['Reins_5_R'], pts['Reins_C'])
            seat = pts['Saddle_Root'] + Vector((0.0, -0.095 * s, seat_offset_z))

            # Spine pitch from Spine_1 -> Spine_2
            sp_vec = (pts['Spine_2'] - pts['Spine_1']).normalized()
            pitch_deg = math.degrees(math.asin(max(-1.0, min(1.0, sp_vec.z))))

            frames.append({
                'seat': yori_vec(seat),
                'saddle_root': yori_vec(pts['Saddle_Root']),
                'spine_2': yori_vec(pts['Spine_2']),
                'neck_1': yori_vec(pts['Neck_1']),
                'head': yori_vec(pts['Head']),
                'bit': yori_vec(pts['Bit']),
                'stirrup_L': yori_vec(tread_L),
                'stirrup_R': yori_vec(tread_R),
                'grip_L': yori_vec(grip_L),
                'grip_R': yori_vec(grip_R),
                'reins_5_L': yori_vec(pts['Reins_5_L']),
                'reins_5_R': yori_vec(pts['Reins_5_R']),
                'reins_c': yori_vec(pts['Reins_C']),
                'pitch_deg': round(pitch_deg, 3),
            })

        clips_out[clip_name] = {
            'duration': duration,
            'fps': FPS,
            'frames': n_frames_60,
            'loop': is_loop,
            'trajectory': frames,
        }
    return clips_out


def verify_library():
    """Every GLB manifest.json lists, at its recorded size and checksum."""
    for rel, info in LIBRARY['glbs'].items():
        p = HERE / rel
        assert p.is_file(), f'Missing horse GLB: {p}'
        raw = p.read_bytes()
        assert len(raw) == info['bytes'], f'Size mismatch on {p}'
        assert hashlib.sha256(raw).hexdigest() == info['sha256'], f'SHA256 mismatch on {p}'


def verify_and_build():
    """Verify the committed horse asset library and write `build/yorimichi/horses/manifest.json`."""
    verify_library()
    measured = {}
    for slug in BREEDS:
        measured[slug] = measure_breed_contacts(slug)
        contacts = measured[slug][0]
        print(f'VERIFIED BREED {slug}: seat_z={contacts["seat_z"]:.3f}m scale={contacts["scale_ratio"]:.4f}', flush=True)

    ref_clips = sample_reference_clips(*measured[REFERENCE])
    build_manifest = {
        'reference_breed': REFERENCE,
        'fps': FPS,
        'breeds': {slug: {'name': LIBRARY['breeds'][slug]['name'], 'contacts': measured[slug][0]} for slug in BREEDS},
        'clips': ref_clips,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'manifest.json').write_text(json.dumps(build_manifest, indent=1) + '\n')
    print(f'HORSES BUILD COMPLETE: {len(BREEDS)} breeds, {len(ref_clips)} clips -> {OUT / "manifest.json"}', flush=True)


if __name__ == '__main__':
    verify_and_build()
