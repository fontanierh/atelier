"""Compact yellow-torso contact correctives for the unchanged dressed sprint.

The tailored cut stays untouched in standing. Two smooth fields move both cloth
walls inward as the forearms pass, using a body-derived radial clearance limit.
Only the yellow lower torso moves; this is authored pose correction, not physics.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import math

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import intersect_ray_tri

from cairo_outfit_correctives import set_clip


def _smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def _crossings(a, b):
    for triangle, target in ((a, b), (b, a)):
        for i in range(3):
            origin = triangle[i]
            edge = triangle[(i + 1) % 3] - origin
            length = edge.length
            if length < 1e-8:
                continue
            point = intersect_ray_tri(*target, edge / length, origin, True)
            if point is not None and -1e-7 <= (point-origin).dot(edge) / length**2 <= 1.0000001:
                return True
    return False


class ArmContactProbe:
    """Exact exposed-white/outer-yellow triangle crossings, not BVH boxes.

    The reference garment's yellow cuff stops before bind |Y| = 0.27 m.
    White faces beyond that point are exposed forearm; deliberate underlap
    inside the yellow upper sleeve is excluded from this acceptance check.
    """
    def __init__(self, shirt):
        self.shirt = shirt
        points = np.array([v.co[:] for v in shirt.data.vertices])
        yellow = np.array([d.value for d in shirt.data.attributes['yellow_layer'].data]) > .5
        self.torso = []
        self.white = {'Left': [], 'Right': []}
        for polygon in shirt.data.polygons:
            ids = list(polygon.vertices)
            center = points[ids].mean(axis=0)
            if (all(yellow[i] for i in ids) and abs(center[1]) < .138 and center[2] < .122
                    and polygon.normal.dot(Vector((center[0]-.024, center[1], 0))) > 0):
                self.torso.append(ids)
            elif all(not yellow[i] for i in ids) and abs(center[1]) >= .27:
                self.white['Left' if center[1] > 0 else 'Right'].append(ids)

    def check(self):
        bpy.context.view_layer.update()
        evaluated = self.shirt.evaluated_get(bpy.context.evaluated_depsgraph_get())
        points = [evaluated.matrix_world @ v.co for v in evaluated.data.vertices]
        torso = BVHTree.FromPolygons(points, self.torso)
        counts = {}
        for side, faces in self.white.items():
            tree = BVHTree.FromPolygons(points, faces)
            crossing_faces = set()
            for a, b in torso.overlap(tree):
                if b in crossing_faces:
                    continue
                if _crossings([points[i] for i in self.torso[a]], [points[i] for i in faces[b]]):
                    crossing_faces.add(b)
            counts[side] = len(crossing_faces)
        return counts


def _make_fields(shirt, body, maximum_inset, body_margin):
    points = np.array([v.co[:] for v in shirt.data.shape_keys.key_blocks[0].data])
    yellow = np.array([d.value for d in shirt.data.attributes['yellow_layer'].data]) > .5
    matrix = shirt.matrix_world.inverted() @ body.matrix_world
    body_tree = BVHTree.FromPolygons([matrix @ v.co for v in body.data.vertices],
                                   [list(p.vertices) for p in body.data.polygons])
    shirt_tree = BVHTree.FromPolygons([Vector(p) for p in points],
        [list(p.vertices) for p in shirt.data.polygons if all(yellow[i] for i in p.vertices)])
    angles = np.linspace(-math.pi, math.pi, 145)
    heights = np.linspace(-.060, .110, 69)
    field = np.zeros((len(heights), len(angles)))
    for iz, z in enumerate(heights):
        for ia, theta in enumerate(angles):
            direction = Vector((math.cos(theta), math.sin(theta), 0))
            origin = Vector((.023, 0, z)) + direction * .4
            skin = body_tree.ray_cast(origin, -direction, 1)[0]
            cloth = shirt_tree.ray_cast(origin, -direction, 1)[0]
            if skin is not None and cloth is not None:
                field[iz, ia] = max(0, (cloth-skin).dot(direction) - body_margin)
    # A shared spatial field avoids independently projecting the two thin walls.
    # Smoothing removes reconstructed skin ripples from the broad cotton panel.
    for _ in range(3):
        field = (np.roll(field, 1, 1) + field*2 + np.roll(field, -1, 1)) / 4
        field[1:-1] = (field[:-2] + field[1:-1]*2 + field[2:]) / 4
    radial = points[:, :2] - [.023, 0]
    theta = np.arctan2(radial[:, 1], radial[:, 0])
    direction = radial / np.maximum(np.linalg.norm(radial, axis=1)[:, None], 1e-10)
    zf = np.clip((points[:, 2]-heights[0]) / (heights[-1]-heights[0]) * (len(heights)-1),
                 0, len(heights)-1-1e-7)
    af = np.clip((theta+math.pi) / (2*math.pi) * (len(angles)-1), 0, len(angles)-1-1e-7)
    zi, ai = zf.astype(int), af.astype(int)
    zt, at = zf-zi, af-ai
    amount = (field[zi, ai]*(1-zt)*(1-at) + field[zi+1, ai]*zt*(1-at)
              + field[zi, ai+1]*(1-zt)*at + field[zi+1, ai+1]*zt*at)
    amount = np.minimum(amount, maximum_inset)
    amount *= (yellow * _smooth(-.005, .035, points[:, 0])
               * (1-_smooth(.130, .150, np.abs(points[:, 1])))
               * (1-_smooth(.060, .110, points[:, 2])))
    keys = {}
    for side, sign in [('Left', 1), ('Right', -1)]:
        key = shirt.shape_key_add(name=side+' · torso arm clearance')
        strength = _smooth(-.010, .040, sign*points[:, 1])
        corrected = points.copy()
        corrected[:, :2] -= direction * (amount*strength)[:, None]
        key.data.foreach_set('co', corrected.astype(np.float32).ravel())
        keys[side] = key
    return keys, {'maximum_inset_m': float(amount.max()), 'body_radial_margin_m': body_margin,
                  'white_layer_max_displacement_m': 0.0,
                  'field': 'Smooth radial lower-front/side torso inset; shared by outer and inner cloth walls'}


def apply_arm_clearance(shirt, arm, scene, *, maximum_inset=.012, body_margin=.002):
    """Add two portable morphs and key them into existing standing/sprint slots.

    Call once after static tailoring, before native save / animated GLB export.
    Requires the preserved fitting body, yellow_layer attribute and existing
    Standing · outfit review / Sprint · dressed actions. No files are written.
    Returns the sampled exact-contact report and per-frame morph values.
    """
    if any('torso arm clearance' in k.name for k in shirt.data.shape_keys.key_blocks):
        raise ValueError('Arm-clearance correction already exists; rebuild from the clean static cut.')
    body = next(o for o in scene.objects if o.get('base_body'))
    keys, report = _make_fields(shirt, body, maximum_inset, body_margin)
    probe = ArmContactProbe(shirt)
    set_clip(arm, bpy.data.actions['Sprint · dressed'])
    required = {side: np.zeros(80) for side in keys}
    before, unsolved = [], []
    for step in range(80):
        frame = 1 + step*.5
        scene.frame_set(int(frame), subframe=frame % 1)
        for key in keys.values():
            key.value = 0
        counts = probe.check()
        before.append({'frame': frame, **counts})
        for side in keys:
            if counts[side] == 0:
                continue
            # At most eight checks are needed for this bounded two-key field.
            # Keep a small amplitude reserve for interpolation/contact tolerance.
            for level in np.linspace(.125, 1, 8):
                keys[side].value = float(level)
                if probe.check()[side] == 0:
                    required[side][step] = min(1, float(level)+.10)
                    break
            else:
                required[side][step] = 1
                unsolved.append({'frame': frame, 'side': side})
    # Circular dilation supplies approach/release lead-in. A short averaging
    # kernel makes continuous humps while never dropping below sampled needs.
    values = {}
    for side, samples in required.items():
        envelope = np.maximum.reduce([np.roll(samples, n) for n in range(-5, 6)])
        curve = sum(np.roll(envelope, n) for n in range(-4, 5)) / 9
        curve = np.maximum(curve, samples)
        # Integer key samples must also cover both intervening half-frame needs.
        full = np.maximum.reduce([curve[::2], np.roll(curve, 1)[::2], np.roll(curve, -1)[::2]])
        values[side] = full
    for action_name in ('Standing · outfit review', 'Sprint · dressed'):
        action = bpy.data.actions[action_name]
        set_clip(arm, action)
        for frame in range(1, 42):
            scene.frame_set(frame)
            for side, key in keys.items():
                key.value = float(values[side][(frame-1) % 40]) if action_name.startswith('Sprint') else 0
                key.keyframe_insert('value', frame=frame)
        slot = shirt.data.shape_keys.animation_data.action_slot
        for layer in action.layers:
            for strip in layer.strips:
                bag = strip.channelbag(slot)
                if bag:
                    for fc in bag.fcurves:
                        if 'torso arm clearance' in fc.data_path:
                            for point in fc.keyframe_points:
                                point.interpolation = 'LINEAR'
    set_clip(arm, bpy.data.actions['Sprint · dressed'])
    after = []
    for step in range(80):
        frame = 1+step*.5
        scene.frame_set(int(frame), subframe=frame % 1)
        after.append({'frame': frame, **probe.check()})
    report.update({'morphs': [key.name for key in keys.values()],
        'sample_interval_frames': .5, 'before': before, 'after': after,
        'unsolved_during_search': unsolved,
        'values': {side: values[side].tolist() for side in values},
        'scope': 'Yellow torso pose correction only; body, white layers, weights and bone animation unchanged.'})
    shirt['arm_clearance'] = 'Two smooth yellow torso contact keys; unchanged standing cut and skeleton'
    set_clip(arm, bpy.data.actions['Standing · outfit review'])
    scene.frame_set(1)
    return report
