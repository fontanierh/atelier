"""Reference-constrained sprint generation and bounded, periodic arm variation.

The owned stride is authoritative. This is an explicitly hybrid animation,
not a claim that text-only UniMate reproduces the original's contacts.
"""
import numpy as np

ARM_JOINTS = ('LeftShoulder', 'RightShoulder', 'LeftArm', 'RightArm', 'LeftForeArm', 'RightForeArm')
FREE_FEATURE_JOINTS = ('LeftArm', 'RightArm', 'LeftForeArm', 'RightForeArm', 'LeftHand', 'RightHand')


def reference_features(reference, rig, scale, floor):
    from Quaternions import Quaternions
    from unimate.utils.motion_utils import compute_unimate_motion_feats, recover_unimate_joint_pos_from_rot
    positions = np.array(reference['positions'], dtype=np.float32) * scale
    positions[:, :, 1] -= floor * scale
    positions[:, :, [0, 2]] -= positions[0, 0, [0, 2]]
    positions[:, :, 2] += np.arange(len(positions))[:, None] / reference['fps'] * reference['travel_speed'] * scale
    rotations = np.array(reference['rotations'])[:, :, [3, 0, 1, 2]]
    features = compute_unimate_motion_feats(positions, Quaternions(rotations), rig['parents'], Quaternions.id(len(positions)))
    # Verify the source-to-model conversion independently before using it as a
    # constraint. A bad reference must fail rather than quietly lock bad feet.
    points = np.array(rig['positions']) * scale
    points[:, 1] -= floor * scale
    offsets = points.copy()
    for j, p in enumerate(rig['parents']):
        if p >= 0:
            offsets[j] -= points[p]
    recovered = recover_unimate_joint_pos_from_rot(features, rig['parents'], offsets)
    error = np.abs(recovered - positions[:-1]).max() / scale
    if error > 0.0001:
        raise ValueError(f'Authored run reference failed FK validation: {error:.6f} m')
    keep = np.array([name.split(':')[-1] not in FREE_FEATURE_JOINTS for name in rig['names']])
    return features.astype(np.float32), keep, float(error)


def bounded_blend(reference, generated, strength, limit_degrees=18.):
    a = np.asarray(reference, dtype=np.float64)
    b = np.asarray(generated, dtype=np.float64)
    length = np.linalg.norm(b)
    if length < 1e-8:
        return a.copy()
    b /= length
    dot = np.dot(a, b)
    if dot < 0:
        b, dot = -b, -dot
    dot = np.clip(dot, 0., 1.)
    angle = np.arccos(dot)
    fraction = strength * min(1., np.deg2rad(limit_degrees) / max(2 * angle, 1e-12))
    if angle < 1e-5:
        q = (1 - fraction) * a + fraction * b
    else:
        q = (np.sin((1 - fraction) * angle) * a + np.sin(fraction * angle) * b) / np.sin(angle)
    return q / np.linalg.norm(q)


def make_sprint_loop(motion, reference, strength=.35):
    count = reference['cycle_frames']
    raw = np.asarray(motion['rotations'])
    original = np.asarray(reference['rotations'])[:count]
    rotations = original.copy()
    for j, name in enumerate(motion['names']):
        if name.split(':')[-1] not in ARM_JOINTS:
            continue
        for f in range(count):
            samples = raw[f::count, j].copy()
            samples[np.sum(samples * original[f, j], axis=1) < 0] *= -1
            rotations[f, j] = bounded_blend(original[f, j], samples.mean(axis=0), strength)
    positions = np.asarray(reference['positions'])[:count, 0].copy()
    angles = np.rad2deg(2 * np.arccos(np.clip(np.abs(np.sum(rotations * original, axis=-1)), 0, 1)))
    motion.update(rotations=np.concatenate([rotations, rotations[:1]]).round(8).tolist(),
                  root_positions=np.concatenate([positions, positions[:1]]).round(8).tolist(),
                  frames=count + 1, fps=reference['fps'], loop=True,
                  reference_clip=reference['reference_clip'], travel_speed=reference['travel_speed'],
                  local_tracks={name: values[:count] + values[:1] for name, values in reference['detail_tracks'].items()},
                  guided={'label': 'Original gait + UniMate arm variation', 'strength': strength,
                          'generated_joints': list(ARM_JOINTS), 'max_joint_change_degrees': 18 * strength,
                          'actual_max_joint_change_degrees': float(angles.max()),
                          'preserved': 'root, stride, torso, head, wrists, fingers and foot contacts'})
    return motion
