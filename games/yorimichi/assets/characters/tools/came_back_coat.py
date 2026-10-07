"""The came-back rival dressed in his long coat: the Tripo coat fitted onto the rigged Tripo body, skinned to its Mixamo
skeleton, and the skirt simulated as cloth (the torso and sleeves ride the skeleton; the skirt hangs from the hips).

    blender -b --python-exit-code 1 --python came_back_coat.py -- --body <rigged.fbx> --texture <basecolor.png> \\
        --coat <coat.fbx> --output <out> --stage fit
    blender -b --python-exit-code 1 --python came_back_coat.py -- ... --stage sim

Run both under the guard (python -m atelier.safety.guarded --small 3 ...).

1. Fit: Tripo exports each model normalised (the body 1 m tall, the coat 1 m from cuff to cuff), so the coat is scaled
   until its cuffs sit on the wrist bones, moved so the cuff centres meet the wrists and the coat's chest is centred on
   the body's chest depth, then every coat vertex closer than GAP to the body (below the head: the hair may fall over
   the collar) is pushed out along the body's normal, the push smoothed over the coat so the cloth does not crease.
   The coat takes the body's bone weights from the nearest point of the body, the skirt blending to the hips, and a
   `cloth_pin` group: 1 on the torso and the sleeves, falling to 0 just below the hips. Writes fit/fit.json, renders
   fit/fit-*.png (T-pose, with the body) and CameBack-Fit.blend.
2. Sim: a short scripted take (rest, arms down, a few steps forward, a quick turn) drives the skeleton; the coat's
   cloth modifier follows the armature, the pin group holds the torso and the sleeves to it and the body collides.
   Gravity is scaled by the model's size (1 m for a 1.75 m character) so the cloth falls at real speed. Writes
   sim/frame-*.png, sim/coat-sim.mp4 and CameBack-Coat.blend (baked). The Blender cloth is a look check: in Unreal the
   coat will be Chaos Cloth painted from the same pin weights, or skirt bones.
"""
import argparse, json, math, subprocess, sys, time
from pathlib import Path
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

ap = argparse.ArgumentParser()
ap.add_argument('--body', required=True)
ap.add_argument('--texture', required=True)
ap.add_argument('--coat', required=True)
ap.add_argument('--output', required=True)
ap.add_argument('--stage', choices=['fit', 'sim'], required=True)
a = ap.parse_args(sys.argv[sys.argv.index('--') + 1:])
out = Path(a.output).resolve(); out.mkdir(parents=True, exist_ok=True)

GAP = .004            # metres between the body and the coat's inside, at the model's 1 m scale
HEAD_Z = .80          # the body above this (the head and hair) does not push the coat
PIN = (.44, .52)      # the pin falls from 1 (at the upper height) to 0 (at the lower) down the skirt
SKIRT = (.42, .50)    # below the upper height the weights blend to the hips, all hips by the lower
REAL_HEIGHT = 1.75    # metres, for gravity
T0 = time.time()


def say(*args):
    print(f'[{time.time() - T0:5.0f} s]', *args, flush=True)


def world_co(o):
    dg = bpy.context.evaluated_depsgraph_get()
    m = o.evaluated_get(dg).to_mesh()
    co = np.array([tuple(o.matrix_world @ v.co) for v in m.vertices])
    o.evaluated_get(dg).to_mesh_clear()
    return co


def setup_camera(scene, size):
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = scene.render.resolution_y = size
    w = bpy.data.worlds.new('review'); scene.world = w; w.use_nodes = True
    w.node_tree.nodes['Background'].inputs[0].default_value = (.6, .6, .62, 1)
    cam = bpy.data.objects.new('review', bpy.data.cameras.new('review')); scene.collection.objects.link(cam)
    scene.camera = cam; cam.data.type = 'ORTHO'
    return cam


def aim(cam, yaw, scale, target):
    r = math.radians(yaw)
    cam.data.ortho_scale = scale
    cam.location = Vector(target) + Vector((3 * math.cos(r), 3 * math.sin(r), 0))
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat('-Z', 'Y').to_euler()


if a.stage == 'fit':
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(Path(a.body).resolve()))
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE'); arm.name = 'CameBack-Rig'
    body = next(o for o in bpy.data.objects if o.type == 'MESH'); body.name = 'CameBack-Body'
    nt = body.data.materials[0].node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    img = bpy.data.images.load(str(Path(a.texture).resolve())); img.pack()
    bsdf.inputs['Base Color'].links[0].from_node.image = img
    for link in [l for l in nt.links if l.to_node == bsdf and l.to_socket.name == 'Normal']:
        nt.links.remove(link)   # Tripo's normal map was baked with the smears in it

    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=str(Path(a.coat).resolve()))
    coat = next(o for o in bpy.data.objects if o not in before and o.type == 'MESH'); coat.name = 'CameBack-Coat'
    bpy.ops.object.select_all(action='DESELECT'); coat.select_set(True); bpy.context.view_layer.objects.active = coat
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for o in [o for o in bpy.data.objects if o not in before and o != coat]:
        bpy.data.objects.remove(o)

    # --- scale and place: cuffs on the wrists, chest on the chest ------------------------------------------------------
    bones = arm.data.bones
    wl = arm.matrix_world @ bones['mixamorig:LeftHand'].head_local
    wr = arm.matrix_world @ bones['mixamorig:RightHand'].head_local
    co = np.array([tuple(v.co) for v in coat.data.vertices])
    cl = co[co[:, 0] > co[:, 0].max() - .015].mean(0)    # the cuff rings, his left (+X) and his right
    cr = co[co[:, 0] < co[:, 0].min() + .015].mean(0)
    s = (wl.x - wr.x) / (cl[0] - cr[0])
    t = np.array((wl + wr) / 2) - s * (cl + cr) / 2
    co = co * s + t
    bco = world_co(body)
    band = lambda c: (c[:, 2] > .62) & (c[:, 2] < .70) & (np.abs(c[:, 0]) < .1)
    body_y = (bco[band(bco), 1].min() + bco[band(bco), 1].max()) / 2
    coat_y = (co[band(co), 1].min() + co[band(co), 1].max()) / 2
    co[:, 1] += body_y - coat_y
    fit = {'scale': round(float(s), 4), 'translate': [round(float(v), 4) for v in t],
           'chest_shift_y': round(float(body_y - coat_y), 4),
           'collar_top_z': round(float(co[:, 2].max()), 4), 'hem_z': round(float(co[:, 2].min()), 4)}
    say('PLACED', json.dumps(fit))

    # --- push out of the body, smoothed over the coat ------------------------------------------------------------------
    dg = bpy.context.evaluated_depsgraph_get()
    bm_ = body.evaluated_get(dg).to_mesh()
    bv = [body.matrix_world @ v.co for v in bm_.vertices]
    polys = [tuple(p.vertices) for p in bm_.polygons if max(bv[i].z for i in p.vertices) < HEAD_Z]
    torso = BVHTree.FromPolygons(bv, polys)
    body.evaluated_get(dg).to_mesh_clear()
    edges = np.array([tuple(e.vertices) for e in coat.data.edges])
    nbr = [[] for _ in range(len(co))]
    for i, j in edges:
        nbr[i].append(j); nbr[j].append(i)

    def smooth(d, passes):
        for _ in range(passes):
            d = np.array([(d[i] + d[nb].sum(0)) / (1 + len(nb)) if nb else d[i] for i, nb in enumerate(nbr)])
        return d

    def inside():
        push = np.zeros_like(co); depth = np.zeros(len(co))
        for i, v in enumerate(co):
            p, n, _, dist = torso.find_nearest(Vector(v), .05)
            if p is None:
                continue
            d = (Vector(v) - p).dot(n)
            if d < GAP:
                push[i] = np.array(n) * (GAP - d); depth[i] = GAP - d
        return push, depth

    first = None
    for it in range(6):
        push, depth = inside()
        first = first or {'touching': int((depth > 0).sum()), 'deepest_mm': round(float(depth.max() * 1000), 1)}
        say(f'push pass {it}: {int((depth > 0).sum())} vertices closer than {GAP * 1000:.0f} mm, deepest {depth.max() * 1000:.1f} mm')
        if depth.max() < .0005:
            break
        # spread each push to its neighbours, then keep at least the push each vertex needs
        sp = smooth(push, 3)
        need = np.linalg.norm(push, axis=1); got = np.linalg.norm(sp, axis=1)
        sp[need > got] = push[need > got]
        co += sp
    _, depth = inside()
    fit.update(before_push=first, after_push={'touching': int((depth > .0005).sum()),
                                              'deepest_mm': round(float(depth.max() * 1000), 1)})
    for v, c in zip(coat.data.vertices, co):
        v.co = c
    coat.data.update()

    # --- weights from the body; the skirt from the hips ----------------------------------------------------------------
    names = [g.name for g in body.vertex_groups]
    Wb = np.zeros((len(body.data.vertices), len(names)), np.float32)
    for v in body.data.vertices:
        for g in v.groups:
            Wb[v.index, g.group] = g.weight
    allb = BVHTree.FromPolygons([body.matrix_world @ v.co for v in body.data.vertices],
                                [tuple(p.vertices) for p in body.data.polygons])
    bvco = np.array([tuple(body.matrix_world @ v.co) for v in body.data.vertices])
    Wc = np.zeros((len(co), len(names)), np.float32)
    for i, v in enumerate(co):
        p, _, f, _ = allb.find_nearest(Vector(v))
        vid = list(body.data.polygons[f].vertices)
        d = np.linalg.norm(bvco[vid] - np.array(p), axis=1)
        w = 1 / (d + 1e-5); w /= w.sum()
        Wc[i] = w @ Wb[vid]
    hips = names.index('mixamorig:Hips')
    tk = np.clip((SKIRT[1] - co[:, 2]) / (SKIRT[1] - SKIRT[0]), 0, 1)
    Wc *= (1 - tk)[:, None]; Wc[:, hips] += tk
    order = np.argsort(-Wc, 1)[:, 4:]              # four influences
    np.put_along_axis(Wc, order, 0, 1)
    Wc /= np.maximum(Wc.sum(1, keepdims=True), 1e-6)
    for gi, name in enumerate(names):
        used = np.nonzero(Wc[:, gi] > 1e-3)[0]
        if len(used):
            g = coat.vertex_groups.new(name=name)
            for i in used:
                g.add([int(i)], float(Wc[i, gi]), 'REPLACE')
    pin = coat.vertex_groups.new(name='cloth_pin')
    sleeve = np.abs(co[:, 0]) > .17
    pw = np.where(sleeve, 1, np.clip((co[:, 2] - PIN[0]) / (PIN[1] - PIN[0]), 0, 1))
    for i, w in enumerate(pw):
        pin.add([i], float(w), 'REPLACE')
    coat.parent = arm
    mod = coat.modifiers.new('Armature', 'ARMATURE'); mod.object = arm
    fit.update(free_vertices=int((pw == 0).sum()), pinned_vertices=int((pw == 1).sum()), vertices=len(co))
    (out / 'fit').mkdir(exist_ok=True)
    (out / 'fit' / 'fit.json').write_text(json.dumps(fit, indent=2) + '\n')
    say('FIT', json.dumps(fit))

    scene = bpy.context.scene
    cam = setup_camera(scene, 900)
    for name, yaw in [('front', -90), ('q_left', -50), ('side', 0), ('back', 90)]:
        aim(cam, yaw, 1.1, (0, 0, .5))
        scene.render.filepath = str(out / 'fit' / f'fit-{name}.png'); bpy.ops.render.render(write_still=True)
    for name, yaw in [('front', -90), ('side', 0)]:      # the collar and the shoulders
        aim(cam, yaw, .35, (0, 0, .76))
        scene.render.filepath = str(out / 'fit' / f'fit-collar-{name}.png'); bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam)
    bpy.ops.wm.save_as_mainfile(filepath=str(out / 'CameBack-Fit.blend'), compress=True)
    say('FIT SAVED')


def turn(pb, axis, degrees):
    """A rotation by `degrees` about an armature-space axis, as the bone's own quaternion (from the rest pose)."""
    ml = pb.bone.matrix_local.to_3x3()
    return (ml.inverted() @ Matrix.Rotation(math.radians(degrees), 3, axis) @ ml).to_quaternion()


def combine(pb, *steps):
    q = None
    for axis, deg in steps:
        r = turn(pb, axis, deg)
        q = r if q is None else r @ q
    return q


if a.stage == 'sim':
    bpy.ops.wm.open_mainfile(filepath=str(out / 'CameBack-Fit.blend'))
    scene = bpy.context.scene
    arm, body, coat = (bpy.data.objects[n] for n in ('CameBack-Rig', 'CameBack-Body', 'CameBack-Coat'))
    scene.render.fps = 24
    START, ARMS, WALK, STOP, TURN, END = 1, 24, 30, 90, 100, 130
    scene.frame_start, scene.frame_end = START, END
    scene.gravity = (0, 0, -9.81 / REAL_HEIGHT)   # the model is 1 m tall

    # --- the take: rest, arms down, walk forward (-Y), stop, a quick turn to his left -----------------------------------
    pbs = arm.pose.bones
    for pb in pbs:
        pb.rotation_mode = 'QUATERNION'
    X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))
    speed = .55 / 24                                # metres a frame, at 1 m tall
    period = 26
    for f in range(START, END + 1):
        lower = min(max((f - 8) / (ARMS - 8), 0), 1); lower = lower * lower * (3 - 2 * lower)
        walking = WALK <= f < STOP
        ph = 2 * math.pi * (f - WALK) / period if walking else 0
        ramp = min((f - WALK) / 8, 1, (STOP - f) / 8) if walking else 0
        swing = math.sin(ph) * ramp
        pose = {
            'mixamorig:LeftArm': [(Y, 68 * lower), (X, 18 * swing)],
            'mixamorig:RightArm': [(Y, -68 * lower), (X, -18 * swing)],
            'mixamorig:LeftForeArm': [(Z, 12 * lower)],
            'mixamorig:RightForeArm': [(Z, -12 * lower)],
            'mixamorig:LeftUpLeg': [(X, -28 * swing)],
            'mixamorig:RightUpLeg': [(X, 28 * swing)],
            'mixamorig:LeftLeg': [(X, 40 * max(0, math.sin(ph + .9)) * ramp)],
            'mixamorig:RightLeg': [(X, 40 * max(0, -math.sin(ph + .9)) * ramp)],
            'mixamorig:Spine1': [(Z, 6 * swing)],
        }
        for name, steps in pose.items():
            pbs[name].rotation_quaternion = combine(pbs[name], *steps)
            pbs[name].keyframe_insert('rotation_quaternion', frame=f)
        hips = pbs['mixamorig:Hips']
        hips.location = (0, 0, 0)
        hips.keyframe_insert('location', frame=f)
        walked = sum(speed * (min((g - WALK) / 8, 1, (STOP - g) / 8) if WALK <= g < STOP else 0) for g in range(START, f))
        tt = min(max((f - STOP - 2) / (TURN - STOP - 2), 0), 1); tt = tt * tt * (3 - 2 * tt)
        arm.location = (0, -walked, 0)
        arm.rotation_euler = (0, 0, math.radians(110) * tt)
        arm.keyframe_insert('location', frame=f); arm.keyframe_insert('rotation_euler', frame=f)

    # --- cloth: after the armature; the body collides ------------------------------------------------------------------
    col = body.modifiers.new('Collision', 'COLLISION')
    body.collision.thickness_outer = .003
    body.collision.thickness_inner = .002
    body.collision.cloth_friction = 5
    cloth = coat.modifiers.new('Cloth', 'CLOTH')
    cs, cc = cloth.settings, cloth.collision_settings
    cs.quality = 10
    cs.mass = .25
    cs.air_damping = 1
    cs.tension_stiffness = cs.compression_stiffness = 20
    cs.shear_stiffness = 8
    cs.bending_stiffness = 1.5
    cs.vertex_group_mass = 'cloth_pin'
    cs.pin_stiffness = 2
    cc.collision_quality = 4
    cc.distance_min = .002
    cc.use_self_collision = True
    cc.self_distance_min = .0015
    cloth.point_cache.frame_start, cloth.point_cache.frame_end = START, END

    say(f'baking frames {START}-{END}')
    for f in range(START, END + 1):
        scene.frame_set(f)
        if f % 10 == 0 or f == END:
            say(f'baked frame {f}/{END}')

    # --- render: a camera that follows him -------------------------------------------------------------------------
    cam = setup_camera(scene, 640)
    scene.eevee.taa_render_samples = 16
    (out / 'sim').mkdir(exist_ok=True)
    for f in range(START, END + 1):
        scene.frame_set(f)
        aim(cam, -60, 1.2, (arm.location.x, arm.location.y, .5))
        scene.render.filepath = str(out / 'sim' / f'frame-{f:04d}.png')
        bpy.ops.render.render(write_still=True)
        if f % 10 == 0 or f == END:
            say(f'rendered frame {f}/{END}')
    bpy.data.objects.remove(cam)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', '24', '-i', str(out / 'sim' / 'frame-%04d.png'),
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '24', str(out / 'sim' / 'coat-sim.mp4')], check=True)
    scene.frame_set(START)
    bpy.ops.wm.save_as_mainfile(filepath=str(out / 'CameBack-Coat.blend'), compress=True)
    say('SIM SAVED')
