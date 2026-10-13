"""An opt-in standing pose, applied to world-space animation samples with planted ankles.

Plain numpy so the authored selection can be checked without Blender. Distances are
game metres; rotations act on subtrees. The original idle's breathing remains.
"""
import json
from pathlib import Path

import numpy as np


def unit(v):
    length = np.linalg.norm(v, axis=-1, keepdims=True)
    if np.any(length < 1e-9):
        raise ValueError('Degenerate stance direction')
    return v / length


def turn(axis, degrees):
    axis = unit(np.asarray(axis, float))
    angle = np.deg2rad(degrees)
    x, y, z = np.moveaxis(axis, -1, 0)
    k = np.zeros(axis.shape[:-1] + (3, 3))
    k[..., 0, 1], k[..., 0, 2], k[..., 1, 0] = -z, y, z
    k[..., 1, 2], k[..., 2, 0], k[..., 2, 1] = -x, -y, x
    return np.eye(3) + np.sin(angle)[..., None, None] * k + (1 - np.cos(angle))[..., None, None] * (k @ k)


def frame(direction, hinge):
    y = unit(direction)
    x = unit(np.cross(y, hinge))
    return np.stack((x, y, unit(np.cross(x, y))), -1)


def load(path, source_sha256):
    choice = json.loads(Path(path).read_text())
    if choice.get('format') != 'atelier.nox.pose-lab' or choice.get('version') != 1:
        raise ValueError('Unsupported standing-pose choice')
    ref, settings = choice['reference'], choice['settings']
    if ref['model_sha256'] != source_sha256:
        raise ValueError('Standing-pose choice belongs to a different model')
    if ref['clip'] != 'Nml_Wait' or ref['frame'] != 1:
        raise ValueError('Standing-pose reference is not the sampled idle')
    # This authored stance changes only these six controls. Fail rather than silently
    # ignoring a later operator selection with additional controls.
    if settings['kneeBend'] or settings['footTurnout']:
        raise ValueError('This standing-pose authoring requires zero extra bend/turnout')
    for side in 'LR':
        if any(settings[side][key] for key in ('spread', 'twist', 'bend')):
            raise ValueError('This standing-pose authoring requires zero arm spread/twist/bend')
    conversion = float(ref['display_to_game_distance_scale'])
    values = np.array([conversion, settings['hips'], settings['footSpacing'], settings['lean'], settings['back'],
                       settings['kneesOut'], settings['L']['swing'], settings['R']['swing']], float)
    if not np.isfinite(values).all() or not 0.95 < conversion < 1.05:
        raise ValueError('Invalid standing-pose values or units')
    return dict(reference_frame=ref['frame'], pelvis_forward_m=settings['hips'] * conversion / 100,
                foot_spacing_m=settings['footSpacing'] * conversion / 100, lean_deg=settings['lean'],
                upper_back_deg=settings['back'], knees_out_deg=settings['kneesOut'],
                arm_swing_deg={side: settings[side]['swing'] for side in 'LR'})


def apply(order, parent, rest_rot, rest_pos, rotations, positions, profile):
    """Modify a sampled idle in place; zero controls are an exact no-op.

    `rotations` and `positions` hold one array per bone, with frame first. A
    reference pole prevents a near-straight leg reversing its knee during the
    pelvis shift. Frames on both sides of the knee share the same hinge plane.
    """
    controls = [profile[k] for k in ('pelvis_forward_m', 'foot_spacing_m', 'lean_deg', 'upper_back_deg', 'knees_out_deg')]
    controls += list(profile['arm_swing_deg'].values())
    if not any(controls):
        return {'stance': 'zero'}
    original_rot = {bone: value.copy() for bone, value in rotations.items()}
    original_pos = {bone: value.copy() for bone, value in positions.items()}
    ref = int(profile['reference_frame'])
    if not 0 <= ref < len(positions['pelvis']):
        raise ValueError('Standing-pose reference frame is outside the clip')
    up = np.array([0., 0., 1.])
    left = original_pos['upperarm_L'][ref] - original_pos['upperarm_R'][ref]
    left[2] = 0.
    left = unit(left)
    forward = np.cross(left, up)
    # Each local turn follows its adjusted parent, so descendants keep the source
    # animation's local motion, including hands, fingers and secondary bones.
    deltas = {'spine': profile['lean_deg'], 'spine_mid': profile['upper_back_deg']}
    deltas.update({f'upperarm_{s}': profile['arm_swing_deg'][s] for s in 'LR'})
    for bone in order:
        p = parent[bone]
        if not p:
            continue
        local = np.swapaxes(original_rot[p], -1, -2) @ original_rot[bone]
        # The viewer's axes are expressed in the reference parent's frame.
        if bone in deltas:
            axis_parent = original_rot[p][ref].T @ left
            local = turn(axis_parent, deltas[bone]) @ local
        rotations[bone] = rotations[p] @ local
        if bone == 'pelvis':
            positions[bone] = original_pos[bone] + forward * profile['pelvis_forward_m']
        else:
            offset = rest_rot[p].T @ (rest_pos[bone] - rest_pos[p])
            positions[bone] = positions[p] + np.einsum('fij,j->fi', rotations[p], offset)
    goals, lengths, poles = {}, {}, {}
    lowering = np.zeros(len(positions['pelvis']))
    for s, sign in (('L', 1), ('R', -1)):
        thigh, shin, foot = (f'{key}_{s}' for key in ('thigh', 'shin', 'foot'))
        goals[s] = original_pos[foot] + left * sign * profile['foot_spacing_m'] / 2
        lengths[s] = (float(np.linalg.norm(rest_pos[shin] - rest_pos[thigh])), float(np.linalg.norm(rest_pos[foot] - rest_pos[shin])))
        a0 = unit(original_pos[foot][ref] - original_pos[thigh][ref])
        v = original_pos[shin][ref] - original_pos[thigh][ref]
        pole = unit(v - a0 * np.dot(v, a0))
        poles[s] = np.einsum('fij,j->fi', original_rot['pelvis'] @ original_rot['pelvis'][ref].T, pole)
        offset = positions[thigh] - goals[s]
        maximum = sum(lengths[s]) * .99998
        vertical = np.sqrt(np.maximum(0, maximum * maximum - np.sum(offset[:, :2] ** 2, 1)))
        lowering = np.maximum(lowering, offset[:, 2] - vertical)
    # One pelvis height serves both legs; keep the authored length, never stretch.
    for bone in order:
        if bone != 'root':
            positions[bone][:, 2] -= lowering
    receipt = {'stance': 'selected', 'pelvis_lowering_cm': round(float(lowering.max()) * 100, 5)}
    for s, sign in (('L', 1), ('R', -1)):
        thigh, shin, foot = (f'{key}_{s}' for key in ('thigh', 'shin', 'foot'))
        hip = positions[thigh]
        reach = goals[s] - hip
        distance = np.linalg.norm(reach, axis=1)
        axis = unit(reach)
        a, b = lengths[s]
        if np.any(distance > a + b + 1e-7) or np.any(distance < abs(a - b) + 1e-8):
            raise ValueError('Standing-pose leg target is outside its reach')
        pole = unit(poles[s] - axis * np.sum(poles[s] * axis, 1, keepdims=True))
        pole = np.einsum('fij,fj->fi', turn(axis, -sign * profile['knees_out_deg']), pole)
        along = (a*a - b*b + distance*distance) / (2*distance)
        knee = hip + axis * along[:, None] + pole * np.sqrt(np.maximum(0, a*a - along*along))[:, None]
        upper, lower = unit(knee - hip), unit(goals[s] - knee)
        hinge = unit(np.cross(upper, lower))
        old_upper = unit(original_pos[shin] - original_pos[thigh])
        old_lower = unit(original_pos[foot] - original_pos[shin])
        # The source IK leaves a small bend, so the knee hinge remains defined.
        old_hinge = unit(np.cross(old_upper, old_lower))
        rotations[thigh] = frame(upper, hinge) @ np.swapaxes(frame(old_upper, old_hinge), -1, -2) @ original_rot[thigh]
        rotations[shin] = frame(lower, hinge) @ np.swapaxes(frame(old_lower, old_hinge), -1, -2) @ original_rot[shin]
        rotations[foot] = original_rot[foot].copy()
        positions[shin], positions[foot] = knee, goals[s]
        offset1 = rest_rot[thigh].T @ (rest_pos[shin] - rest_pos[thigh])
        offset2 = rest_rot[shin].T @ (rest_pos[foot] - rest_pos[shin])
        fk_knee = hip + np.einsum('fij,j->fi', rotations[thigh], offset1)
        fk_ankle = fk_knee + np.einsum('fij,j->fi', rotations[shin], offset2)
        error = np.linalg.norm(fk_ankle - goals[s], axis=1)
        receipt[f'stance_fk_ankle_{s}_cm'] = round(float(error.max()) * 100, 6)
        drift = np.linalg.norm(goals[s] - goals[s][0], axis=1)
        receipt[f'stance_planted_drift_{s}_cm'] = round(float(drift.max()) * 100, 6)
        if error.max() > 1e-5:
            raise ValueError(f'Standing-pose exported rotations miss the {s} ankle target')
    # Carry the corrected leg's endpoints while feet/toes retain the source heading.
    for bone in order:
        p = parent[bone]
        if p and any(p.startswith(key) for key in ('thigh_', 'shin_', 'foot_', 'toe_')) and bone not in rotations_to_keep():
            local = np.swapaxes(original_rot[p], -1, -2) @ original_rot[bone]
            rotations[bone] = rotations[p] @ local
            offset = rest_rot[p].T @ (rest_pos[bone] - rest_pos[p])
            positions[bone] = positions[p] + np.einsum('fij,j->fi', rotations[p], offset)
    receipt['lowest_toe_cm'] = round(float(min(positions[f'toe_{s}'][:, 2].min() for s in 'LR')) * 100, 2)
    return receipt


def rotations_to_keep():
    return {'thigh_L', 'thigh_R', 'shin_L', 'shin_R', 'foot_L', 'foot_R'}
