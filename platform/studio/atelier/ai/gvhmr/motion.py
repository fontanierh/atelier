"""SMPL-X body parameters to the motion representation the shared retargeter reads.

GVHMR predicts SMPL-X parameters per frame: `global_orient` (3), `body_pose` (21×3, axis-angle), `transl` (3) and
`betas` (10). The 22 body joints rest with identity rotations, so each joint's local SMPL-X rotation is already the
parent-relative delta in canonical axes that [platform/web/motion](../../../../web/motion/README.md) composes down the
rig. The global frame is
gravity-aligned and Y-up, and the rest body faces +Z, matching that canonical frame. Hands, jaw and eyes stay out:
GVHMR does not estimate them.
"""
import numpy as np
from scipy.spatial.transform import Rotation

NAMES = ['pelvis', 'left_hip', 'right_hip', 'spine1', 'left_knee', 'right_knee', 'spine2', 'left_ankle',
         'right_ankle', 'spine3', 'left_foot', 'right_foot', 'neck', 'left_collar', 'right_collar', 'head',
         'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow', 'left_wrist', 'right_wrist']
PARENTS = [-1, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 9, 9, 12, 13, 14, 16, 17, 18, 19]
FEET = ['left_foot', 'right_foot']


def rest_joints(body_model, betas):
    """Rest positions of the 22 body joints for one shape, from an SMPL-X model file's arrays."""
    betas = np.asarray(betas, dtype=np.float64)
    shapedirs = np.asarray(body_model['shapedirs'], dtype=np.float64)[:, :, :len(betas)]
    vertices = np.asarray(body_model['v_template'], dtype=np.float64) + shapedirs @ betas
    regressor = body_model['J_regressor']
    regressor = regressor.toarray() if hasattr(regressor, 'toarray') else np.asarray(regressor, dtype=np.float64)
    parents = np.asarray(body_model['kintree_table'])[0, :len(NAMES)].astype(np.int64)
    parents[0] = -1
    if parents.tolist() != PARENTS:
        raise ValueError('body model is not SMPL-X: unexpected body joint hierarchy')
    return regressor[:len(NAMES)] @ vertices


def body_motion(params, body_model, fps=30):
    """Return the motion dict for `params` (GVHMR `smpl_params_global` or `smpl_params_incam`, as arrays).

    One body shape is used for the whole take: the mean of GVHMR's per-frame betas.
    """
    params = {k: np.asarray(v, dtype=np.float64) for k, v in params.items()}
    frames = len(params['transl'])
    betas = params['betas'].reshape(frames, -1).mean(0)
    rest = rest_joints(body_model, betas)
    axis_angle = np.concatenate([params['global_orient'].reshape(frames, 1, 3),
                                 params['body_pose'].reshape(frames, -1, 3)[:, :len(NAMES) - 1]], axis=1)
    local = Rotation.from_rotvec(axis_angle.reshape(-1, 3)).as_matrix().reshape(frames, len(NAMES), 3, 3)
    world = np.empty_like(local)
    positions = np.empty((frames, len(NAMES), 3))
    world[:, 0] = local[:, 0]
    positions[:, 0] = rest[0] + params['transl']
    for j in range(1, len(NAMES)):
        p = PARENTS[j]
        world[:, j] = world[:, p] @ local[:, j]
        positions[:, j] = positions[:, p] + world[:, p] @ (rest[j] - rest[p])
    quats = Rotation.from_matrix(local.reshape(-1, 3, 3)).as_quat().reshape(frames, len(NAMES), 4)
    return {
        'fps': fps,
        'frames': frames,
        'names': NAMES,
        'parents': PARENTS,
        'rest_positions': rest.tolist(),
        'rest_root': rest[0].tolist(),
        'rotations': quats.tolist(),
        'root_positions': positions[:, 0].tolist(),
        'joint_positions': positions.tolist(),
        'betas': betas.tolist(),
        'canonical_to_gltf': [0, 0, 0, 1],
    }


def camera_anchored_transl(global_params, incam_params, body_model):
    """Experimental, locked-off camera only: `global_params['transl']` with its height taken from the in-camera body.

    GVHMR's world trajectory can flatten jumps that its in-camera estimate keeps. One camera-to-world rotation is
    fixed on frame 0, R = R_global[0] @ R_incam[0].T, and the in-camera pelvis is carried into the world from the
    frame-0 global pelvis: p(t) = R @ (p_c(t) - p_c(0)) + p_global(0), where a pelvis is the rest root plus `transl`
    (SMPL-X rotates the body about its pelvis). Only the height of p(t) is kept; X and Z, every rotation and frame 0
    stay exactly as GVHMR's world output has them. Returns the new `transl` and the anchor for provenance.
    """
    g = {k: np.asarray(v, dtype=np.float64) for k, v in global_params.items()}
    c = {k: np.asarray(v, dtype=np.float64) for k, v in incam_params.items()}
    frames = len(g['transl'])
    rest_root = rest_joints(body_model, g['betas'].reshape(frames, -1).mean(0))[0]
    R = (Rotation.from_rotvec(g['global_orient'].reshape(frames, 3)[0])
         * Rotation.from_rotvec(c['global_orient'].reshape(frames, 3)[0]).inv()).as_matrix()
    pelvis_cam = rest_root + c['transl'].reshape(frames, 3)
    origin = rest_root + g['transl'].reshape(frames, 3)[0]
    anchored = (pelvis_cam - pelvis_cam[0]) @ R.T + origin
    transl = g['transl'].reshape(frames, 3).copy()
    transl[:, 1] = anchored[:, 1] - rest_root[1]
    return transl, {'root_height': 'camera', 'anchor_frame': 0, 'camera_to_world': R.tolist(),
                    'world_pelvis_at_anchor': origin.tolist()}


def load_body_model(path):
    """The arrays `body_motion` needs from SMPLX_NEUTRAL.npz."""
    with np.load(path, allow_pickle=True) as data:
        return {k: data[k] for k in ('v_template', 'shapedirs', 'J_regressor', 'kintree_table')}
