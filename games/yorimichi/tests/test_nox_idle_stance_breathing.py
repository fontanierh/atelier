"""The selected stance keeps a breathing, planted, closed idle loop.

The clip is built here without the stance helpers: the downloaded reference idle is
breathed with phase-shifted local turns at Reference Nml_Wait amplitudes (waist 0.75
deg and 0.66 cm sway, spine/chest up to 1.2 deg per joint, arms 2.9 deg). Its own
two-bone solve keeps the ankles planted. The last frame repeats the first.
"""
from types import SimpleNamespace

import numpy as np
import pytest

from test_nox_idle_stance import profile, rig, stance

FRAMES = 9
UP = np.array([0., 0., 1.])
# Local turns in the parent's frame: axis, amplitude in degrees, phase.
BREATH = {'spine': ((0, 1, 0), 1.0, .3), 'spine_mid': ((.2, 1, 0), .8, .6), 'chest': ((0, 1, .3), 1.2, .9),
          'neck': ((1, 0, 0), .8, 1.2), 'clavicle_L': ((1, 0, 0), 1.5, .5), 'clavicle_R': ((1, 0, 0), -1.5, .5),
          'upperarm_L': ((1, .4, 0), 2.9, 1.4), 'upperarm_R': ((1, -.4, 0), 2.9, 1.7), 'forearm_L': ((0, 0, 1), 2., 2.)}
TURNED = ('spine', 'spine_mid', 'upperarm_L', 'upperarm_R')
LEGS = {f'{key}_{s}' for key in ('thigh', 'shin') for s in 'LR'}


def skew(v):
    return np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])


def rotate(axis, degrees):
    k = skew(np.asarray(axis, float) / np.linalg.norm(axis))
    angle = np.deg2rad(degrees)
    return np.eye(3) + np.sin(angle) * k + (1 - np.cos(angle)) * k @ k


def arc(a, b):
    a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
    k = skew(np.cross(a, b))
    return np.eye(3) + k + k @ k / (1 + a @ b)


def degrees(m):
    return np.rad2deg(np.arccos(np.clip((np.trace(m) - 1) / 2, -1, 1)))


def rotation_axis(m):
    v = np.array([m[2, 1] - m[1, 2], m[0, 2] - m[2, 0], m[1, 0] - m[0, 1]])
    return v / np.linalg.norm(v)


def unit(v):
    return v / np.linalg.norm(v)


def breathing_clip():
    order, parent, rr, rp, rotations, positions, _, _ = rig()
    assert set(BREATH) <= set(parent)
    idle = {b: rotations[b][1] for b in order}
    head = {b: positions[b][1] for b in order}
    offset = {b: rr[parent[b]].T @ (rp[b] - rp[parent[b]]) for b in order if parent[b]}
    rot = {b: np.zeros((FRAMES, 3, 3)) for b in order}
    pos = {b: np.zeros((FRAMES, 3)) for b in order}
    # Breathing drops the waist 1.5 cm so the source legs have slack for the sway.
    phases = 2 * np.pi * (np.arange(FRAMES) % (FRAMES - 1)) / (FRAMES - 1)
    for f, t in enumerate(phases):
        for b in order:
            p = parent[b]
            if not p:
                rot[b][f], pos[b][f] = idle[b], head[b]
            elif b == 'pelvis':
                rot[b][f] = rotate((.3, .2, 1), .75 * np.sin(t)) @ idle[b]
                pos[b][f] = head[b] + [.0066 * np.sin(t), .004 * np.sin(t + .7), -.015 + .002 * np.sin(t + 1.3)]
            else:
                local = idle[p].T @ idle[b]
                if b in BREATH:
                    axis, amplitude, shift = BREATH[b]
                    local = rotate(axis, amplitude * np.sin(t + shift)) @ local
                rot[b][f] = rot[p][f] @ local
                pos[b][f] = pos[p][f] + rot[p][f] @ offset[b]
        for s in 'LR':
            thigh, shin, foot = (f'{key}_{s}' for key in ('thigh', 'shin', 'foot'))
            hip, goal = pos[thigh][f], head[foot]
            a, b = np.linalg.norm(offset[shin]), np.linalg.norm(offset[foot])  # thigh, shin lengths
            reach = goal - hip
            distance = np.linalg.norm(reach)
            assert abs(a - b) < distance < a + b
            axis = reach / distance
            bend = head[shin] - head[thigh]
            bend = rot['pelvis'][f] @ idle['pelvis'].T @ (bend - unit(head[foot] - head[thigh]) * (bend @ unit(head[foot] - head[thigh])))
            pole = unit(bend - axis * (bend @ axis))
            along = (a * a - b * b + distance * distance) / (2 * distance)
            knee = hip + axis * along + pole * np.sqrt(a * a - along * along)
            rot[thigh][f] = arc(rot[thigh][f] @ offset[shin], knee - hip) @ rot[thigh][f]
            pos[shin][f] = hip + rot[thigh][f] @ offset[shin]
            rot[shin][f] = rot[thigh][f] @ idle[thigh].T @ idle[shin]
            rot[shin][f] = arc(rot[shin][f] @ offset[foot], goal - pos[shin][f]) @ rot[shin][f]
            pos[foot][f] = pos[shin][f] + rot[shin][f] @ offset[foot]
            rot[foot][f] = idle[foot]
            carried = {foot}
            for c in order:
                if parent[c] in carried:
                    carried.add(c)
                    rot[c][f] = rot[parent[c]][f] @ idle[parent[c]].T @ idle[c]
                    pos[c][f] = pos[parent[c]][f] + rot[parent[c]][f] @ offset[c]
    return order, parent, rr, rp, rot, pos, offset


@pytest.fixture(scope='module')
def clip():
    order, parent, rr, rp, rot, pos, offset = breathing_clip()
    source_rot = {b: v.copy() for b, v in rot.items()}
    source_pos = {b: v.copy() for b, v in pos.items()}
    selected = profile()
    receipt = stance.apply(order, parent, rr, rp, rot, pos, selected)
    ref = selected['reference_frame']
    left = source_pos['upperarm_L'][ref] - source_pos['upperarm_R'][ref]
    left = unit(left - UP * left[2])
    return SimpleNamespace(order=order, parent=parent, rp=rp, offset=offset, rot=rot, pos=pos, source_rot=source_rot,
                           source_pos=source_pos, profile=selected, receipt=receipt, ref=ref, left=left,
                           forward=np.cross(left, UP))


def test_source_clip_breathes_with_planted_ankles_and_closes(clip):
    for b in clip.order:
        np.testing.assert_array_equal(clip.source_rot[b][-1], clip.source_rot[b][0])
        np.testing.assert_array_equal(clip.source_pos[b][-1], clip.source_pos[b][0])
    for s in 'LR':
        foot = clip.source_pos[f'foot_{s}']
        assert np.abs(foot - foot[0]).max() < 1e-9
    assert np.ptp(clip.source_pos['pelvis'][:, 0]) > .01
    assert max(degrees(clip.source_rot['chest'][f] @ clip.source_rot['chest'][0].T) for f in range(FRAMES)) > .5


def test_every_frame_is_forward_kinematics_of_its_rotations(clip):
    for b in clip.order:
        r = clip.rot[b]
        np.testing.assert_allclose(r @ np.swapaxes(r, -1, -2), np.broadcast_to(np.eye(3), r.shape), atol=1e-9)
        np.testing.assert_allclose(np.linalg.det(r), 1, atol=1e-9)
        p = clip.parent[b]
        if p and p != 'root':  # the pelvis head is animated, not a rest offset
            expected = clip.pos[p] + np.einsum('fij,j->fi', clip.rot[p], clip.offset[b])
            np.testing.assert_allclose(clip.pos[b], expected, atol=1e-7, err_msg=b)


def test_ankles_stay_planted_on_the_narrowed_goals(clip):
    spacing = clip.profile['foot_spacing_m']
    for s, sign in (('L', 1), ('R', -1)):
        shift = clip.left * sign * spacing / 2
        for b in ('foot', 'toe'):
            np.testing.assert_allclose(clip.pos[f'{b}_{s}'], clip.source_pos[f'{b}_{s}'] + shift, atol=1e-7)
        np.testing.assert_allclose(clip.rot[f'foot_{s}'], clip.source_rot[f'foot_{s}'], atol=1e-12)
        assert clip.receipt[f'stance_fk_ankle_{s}_cm'] < 1e-4
        assert clip.receipt[f'stance_planted_drift_{s}_cm'] < 1e-4


def test_legs_keep_length_bend_forward_and_hinge_without_roll(clip):
    for s in 'LR':
        thigh, shin, foot = (f'{key}_{s}' for key in ('thigh', 'shin', 'foot'))
        hip, knee, ankle = clip.pos[thigh], clip.pos[shin], clip.pos[foot]
        for upper, lower in ((thigh, shin), (shin, foot)):
            np.testing.assert_allclose(np.linalg.norm(clip.pos[lower] - clip.pos[upper], axis=1),
                                       np.linalg.norm(clip.rp[lower] - clip.rp[upper]), atol=1e-8)
        for f in range(FRAMES):
            line = unit(ankle[f] - hip[f])
            out = knee[f] - hip[f]
            assert (out - line * (out @ line)) @ clip.forward > .05, (s, f)
            # The knee keeps the source's hinge in thigh space and lands on the solved leg plane.
            old_hinge = unit(np.cross(clip.source_pos[shin][f] - clip.source_pos[thigh][f],
                                      clip.source_pos[foot][f] - clip.source_pos[shin][f]))
            hinge = clip.source_rot[thigh][f].T @ old_hinge
            np.testing.assert_allclose(clip.rot[thigh][f] @ hinge, unit(np.cross(knee[f] - hip[f], ankle[f] - knee[f])), atol=1e-6)
            change = (clip.rot[thigh][f].T @ clip.rot[shin][f]) @ (clip.source_rot[thigh][f].T @ clip.source_rot[shin][f]).T
            assert degrees(change) > 1
            assert np.linalg.norm(np.cross(rotation_axis(change), hinge)) < 1e-6


def test_only_the_selected_joints_change_their_local_motion(clip):
    for b in clip.order:
        p = clip.parent[b]
        if not p or b in LEGS or b.startswith('foot_'):
            continue
        local = np.swapaxes(clip.rot[p], -1, -2) @ clip.rot[b]
        source = np.swapaxes(clip.source_rot[p], -1, -2) @ clip.source_rot[b]
        if b not in TURNED:
            np.testing.assert_allclose(local, source, atol=1e-12, err_msg=b)
            continue
        # One constant turn about the reference parent's body-left axis, so breathing survives.
        delta = {'spine': clip.profile['lean_deg'], 'spine_mid': clip.profile['upper_back_deg']}
        delta.update({f'upperarm_{s}': clip.profile['arm_swing_deg'][s] for s in 'LR'})
        expected = rotate(clip.source_rot[p][clip.ref].T @ clip.left, delta[b])
        np.testing.assert_allclose(local @ np.swapaxes(source, -1, -2), np.broadcast_to(expected, local.shape), atol=1e-12, err_msg=b)


def test_pelvis_shift_is_constant_and_the_loop_still_closes(clip):
    shift = clip.pos['pelvis'] - clip.source_pos['pelvis']
    np.testing.assert_allclose(shift[:, :2], np.broadcast_to((clip.forward * clip.profile['pelvis_forward_m'])[:2], (FRAMES, 2)), atol=1e-12)
    assert np.all(shift[:, 2] <= 0) and -shift[:, 2].min() <= clip.receipt['pelvis_lowering_cm'] / 100 + 1e-7
    np.testing.assert_allclose(clip.rot['pelvis'], clip.source_rot['pelvis'], atol=1e-12)
    for b in clip.order:
        np.testing.assert_allclose(clip.rot[b][-1], clip.rot[b][0], atol=1e-12, err_msg=b)
        np.testing.assert_allclose(clip.pos[b][-1], clip.pos[b][0], atol=1e-12, err_msg=b)
