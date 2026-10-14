"""Paul's game source: Tripo's auto-rig (skeleton and skin weights) on the textured graft.

/Applications/Blender.app/Contents/MacOS/Blender -b --python-exit-code 1 --python \
    games/yorimichi/assets/characters/tools/paul_rig.py -- \
    --graft <dir>/Paul-graft.blend --rigged <tripo rigged>.glb --output <dir> [--poses]

Tripo Studio rigged a single-texture export of the graft (paul_body_graft.py; turned to face -Y): 65 bones with
Mixamo names, fingers included. Its viewer and its file keep only one texture, so the graft's own mesh, UVs and two
materials stay, and only the rig comes over:

1. The rigged file is brought back into the graft's frame (facing +X, 1.65 m): turned +90 degrees about Z, scaled
   by the graft's height over its own, then fitted rigidly onto the graft (Tripo re-centres and straightens it).
2. Every graft vertex takes the weights of the rigged mesh's vertex at the same place (the two are the same surface;
   the largest distance is recorded and must stay under MATCH_TOLERANCE).
3. Paul.glb: the armature and the textured mesh, no clips, textures packed. rig.json records the match.
`--poses` renders test poses (arms down, arms forward, elbows bent, a crouch) to review the skinning.
"""
import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree
import numpy as np

MATCH_TOLERANCE = .002      # m


def args():
    p = argparse.ArgumentParser()
    p.add_argument('--graft', required=True)
    p.add_argument('--rigged', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--poses', action='store_true')
    return p.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])


def icp(src, dst, iterations=30):
    """The rigid transform taking src onto dst (nearest points, Kabsch), from their bounding-box centres."""
    tree = KDTree(len(dst))
    for i, p in enumerate(dst):
        tree.insert(p, i)
    tree.balance()
    c = (dst.min(0) + dst.max(0)) / 2 - (src.min(0) + src.max(0)) / 2
    c[2] = dst[:, 2].min() - src[:, 2].min()
    R, T = np.eye(3), c
    sub = src[::10]
    for _ in range(iterations):
        y = sub @ R.T + T
        pairs = np.array([tree.find(p)[0][:] for p in y])
        my, mp = y.mean(0), pairs.mean(0)
        U, _, Vt = np.linalg.svd((y - my).T @ (pairs - mp))
        Ri = Vt.T @ U.T
        if np.linalg.det(Ri) < 0:
            Vt[-1] *= -1
            Ri = Vt.T @ U.T
        R, T = Ri @ R, Ri @ (T - my) + mp
    m = Matrix.Identity(4)
    for i in range(3):
        for j in range(3):
            m[i][j] = R[i, j]
        m[i][3] = T[i]
    return m


def plain_materials(body):
    """Each material as the pipeline reads it: its texture straight into a Principled BSDF's Base Color, named
    M_Paul_<slot> (glTF imports a colour factor as a mix node, and the old head's import left stale names)."""
    images = []
    for slot in body.material_slots:
        image = next(n.image for n in slot.material.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image
                     and 'normal' not in n.image.name.lower())
        images.append(image)
    for m in [m for m in bpy.data.materials if m.name.startswith('M_Paul_')]:
        m.name = 'old_' + m.name
    for i, (slot, image) in enumerate(zip(body.material_slots, images)):
        m = bpy.data.materials.new(f'M_Paul_{i}')
        m.use_nodes = True
        nt = m.node_tree
        bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
        tex = nt.nodes.new('ShaderNodeTexImage'); tex.image = image
        nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
        bsdf.inputs['Roughness'].default_value = .8
        slot.material = m
    for m in [m for m in bpy.data.materials if m.name.startswith('old_M_Paul_')]:
        bpy.data.materials.remove(m)


def main():
    a = args()
    out = Path(a.output); out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=a.graft)
    body = bpy.data.objects['Paul_Body']
    for o in list(bpy.data.objects):
        if o is not body:
            bpy.data.objects.remove(o, do_unlink=True)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=a.rigged)
    new = [o for o in bpy.data.objects if o not in before]
    arm = next(o for o in new if o.type == 'ARMATURE')
    src = max((o for o in new if o.type == 'MESH'), key=lambda o: len(o.data.vertices))
    for o in new:
        if o not in (arm, src):
            bpy.data.objects.remove(o, do_unlink=True)
    for img in [i for i in bpy.data.images if i.name.startswith('tripo')]:
        bpy.data.images.remove(img)

    bco = np.array([v.co[:] for v in body.data.vertices])
    sco = np.array([src.matrix_world @ v.co for v in src.data.vertices])
    scale = (bco[:, 2].max() - bco[:, 2].min()) / (sco[:, 2].max() - sco[:, 2].min())
    turn = Matrix.Rotation(math.radians(90), 4, 'Z') @ Matrix.Scale(scale, 4)
    world = src.matrix_world.copy()
    src.parent = None
    src.matrix_world = world
    src.data.transform(turn @ src.matrix_world); src.matrix_world = Matrix()
    # Tripo re-centres the model and straightens it (about 4 degrees about Z here): fit it back onto the graft
    fit = icp(np.array([v.co[:] for v in src.data.vertices]), bco)
    src.data.transform(fit)
    arm.matrix_world = fit @ turn @ arm.matrix_world
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True); bpy.context.view_layer.objects.active = arm
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    fit_report = {'translation': [round(x, 5) for x in fit.to_translation()],
                  'rotation_deg': [round(math.degrees(x), 3) for x in fit.to_euler()]}

    tree = KDTree(len(src.data.vertices))
    for i, v in enumerate(src.data.vertices):
        tree.insert(v.co, i)
    tree.balance()
    names = {g.index: g.name for g in src.vertex_groups}
    body.vertex_groups.clear()
    groups = {n: body.vertex_groups.new(name=n) for n in names.values()}
    dist = np.zeros(len(body.data.vertices))
    for v in body.data.vertices:
        co, j, d = tree.find(v.co)
        dist[v.index] = d
        for g in src.data.vertices[j].groups:
            if g.weight > 0:
                groups[names[g.group]].add([v.index], g.weight, 'REPLACE')
    report = {'rigged': Path(a.rigged).name, 'graft': Path(a.graft).name, 'scale': round(scale, 6), 'fit': fit_report,
              'bones': len(arm.data.bones), 'match_max_m': float(dist.max()), 'match_mean_m': float(dist.mean()),
              'vertices': len(body.data.vertices), 'blender_version': bpy.app.version_string}
    print('RIG', json.dumps(report))
    assert dist.max() < MATCH_TOLERANCE, ('the rigged mesh is not the graft', dist.max())
    bpy.data.objects.remove(src, do_unlink=True)

    body.parent = arm
    body.matrix_parent_inverse = arm.matrix_world.inverted()
    mod = body.modifiers.new('Armature', 'ARMATURE'); mod.object = arm
    arm.name = 'Armature'
    plain_materials(body)
    for im in bpy.data.images:
        if im.users and not im.packed_file:
            im.pack()
    bpy.ops.wm.save_as_mainfile(filepath=str(out / 'Paul-rig.blend'))
    bpy.ops.export_scene.gltf(filepath=str(out / 'Paul.glb'), export_format='GLB', export_skins=True,
                              export_animations=False, export_image_format='AUTO')
    (out / 'rig.json').write_text(json.dumps(report, indent=1) + '\n')
    if a.poses:
        poses(arm, body, out)


POSES = {
    # bone: (axis in the armature's frame, degrees); the character faces +X, his left is +Y
    'arms_down': {'mixamorig:LeftArm': ('X', -70), 'mixamorig:RightArm': ('X', 70)},
    'arms_forward': {'mixamorig:LeftArm': ('Z', -80), 'mixamorig:RightArm': ('Z', 80)},
    'elbows': {'mixamorig:LeftArm': ('X', -60), 'mixamorig:RightArm': ('X', 60),
               'mixamorig:LeftForeArm': ('Y', -100), 'mixamorig:RightForeArm': ('Y', -100)},
    'arms_up': {'mixamorig:LeftArm': ('X', 60), 'mixamorig:RightArm': ('X', -60)},
    'crouch': {'mixamorig:LeftUpLeg': ('Y', -80), 'mixamorig:RightUpLeg': ('Y', -80),
               'mixamorig:LeftLeg': ('Y', 110), 'mixamorig:RightLeg': ('Y', 110),
               'mixamorig:LeftArm': ('X', -70), 'mixamorig:RightArm': ('X', 70)},
    'fist': {'mixamorig:LeftArm': ('X', -70), 'mixamorig:RightArm': ('X', 70)},
}


def pose_bone(arm, name, axis, deg):
    """Turn a bone about an axis of the armature's frame through its own head (parents first)."""
    pb = arm.pose.bones[name]
    bpy.context.view_layer.update()
    m = pb.matrix.copy()
    r = Matrix.Rotation(math.radians(deg), 4, axis)
    head = m.to_translation()
    pb.matrix = Matrix.Translation(head) @ r @ Matrix.Translation(-head) @ m
    bpy.context.view_layer.update()


def poses(arm, body, out):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    sc.view_settings.view_transform = 'Standard'
    sc.world = bpy.data.worlds.new('w'); sc.world.use_nodes = True
    sc.world.node_tree.nodes['Background'].inputs[0].default_value = (.85, .83, .8, 1)
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
    cam.data.type = 'ORTHO'
    order = ['Arm', 'ForeArm', 'Hand', 'UpLeg', 'Leg']

    def shot(name, target, direction, scale, res):
        sc.render.resolution_x, sc.render.resolution_y = res
        cam.data.ortho_scale = scale
        cam.location = Vector(target) + Vector(direction).normalized() * 4
        cam.rotation_euler = (Vector(target) - cam.location).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = str(out / 'poses' / f'{name}.png'); bpy.ops.render.render(write_still=True)
    for pname, spec in POSES.items():
        for pb in arm.pose.bones:
            pb.matrix_basis = Matrix()
        for bone in sorted(spec, key=lambda b: next((i for i, k in enumerate(order) if b.endswith(k)), 9)):
            pose_bone(arm, bone, *spec[bone])
        if pname == 'fist':
            for pb in arm.pose.bones:
                if 'Hand' in pb.name and pb.name[-1] in '123' and 'Thumb' not in pb.name:
                    pb.rotation_mode = 'XYZ'; pb.rotation_euler = (math.radians(70), 0, 0)
        bpy.context.view_layer.update()
        if pname == 'fist':
            for side, y in (('L', .2), ('R', -.2)):
                shot(f'{pname}_{side}_out', (0, y * 1.0, .95), (0, 1 if side == 'L' else -1, 0), .35, (700, 700))
                shot(f'{pname}_{side}_front', (0, y * 1.0, .95), (1, 0, 0), .35, (700, 700))
            continue
        for view, d in (('front', (1, 0, 0)), ('q', (1, -1, .1)), ('back', (-1, .4, .1))):
            shot(f'{pname}_{view}', (0, 0, .85 if pname != 'crouch' else .6), d, 1.9, (700, 1000))
        shot(f'{pname}_armpit', (0, -.15, 1.2), (.3, -1, -.2), .5, (700, 700))


main()
