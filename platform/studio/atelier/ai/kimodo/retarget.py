"""Transfer SOMA canonical rotation deltas to an explicitly mapped target rig."""


def retarget_motion(output, rig, skeleton, joint_map, *, foot_names, canonical_to_gltf):
    import numpy as np
    from scipy.spatial.transform import Rotation

    names, parents = rig["names"], rig["parents"]
    rest = np.asarray(rig["positions"], dtype=float)
    if len(names) != len(parents) or rest.shape != (len(names), 3) or parents[0] != -1:
        raise ValueError("Expected a root-first target skeleton")
    if any(
        parent < 0 or parent >= joint for joint, parent in enumerate(parents[1:], 1)
    ):
        raise ValueError("Target parents must precede their children")
    indices = [skeleton.bone_index[joint_map[name]] for name in names]
    # SOMA's raw matrices already rotate its canonical anatomical rest offsets.
    # Its standard-T-pose/BVH offsets describe different bone axes and must not
    # be applied to these canonical deltas.
    desired = np.asarray(output["global_rot_mats"])[:, indices]
    local = np.empty_like(desired)
    for joint, parent in enumerate(parents):
        # Fold source-only intermediate joints (for example the second neck)
        # by measuring relative to the target's mapped parent.
        local[:, joint] = (
            desired[:, joint]
            if parent == -1
            else desired[:, parent].transpose(0, 2, 1) @ desired[:, joint]
        )
    feet = [names.index(name) for name in foot_names]
    target_floor = rest[feet, 1].min()
    source_rest = skeleton.neutral_joints.cpu().numpy()
    source_height = (
        source_rest[skeleton.root_idx, 1]
        - source_rest[[indices[foot] for foot in feet], 1].min()
    )
    if source_height <= 0:
        raise ValueError("Source skeleton must be Y-up with feet below its root")
    scale = (rest[0, 1] - target_floor) / source_height
    root = np.asarray(output["root_positions"], dtype=float).copy() * scale
    root[:, [0, 2]] -= root[0, [0, 2]]
    root[:, [0, 2]] += rest[0, [0, 2]]
    root[:, 1] += target_floor
    positions = np.zeros((len(root), len(names), 3))
    positions[:, 0] = root
    for joint, parent in enumerate(parents):
        if parent >= 0:
            positions[:, joint] = positions[:, parent] + np.einsum(
                "tij,j->ti", desired[:, parent], rest[joint] - rest[parent]
            )
    # Constant placement adjustment only; no IK, authored pose or timing edits.
    floor_offset = target_floor - positions[:, feet, 1].min()
    root[:, 1] += floor_offset
    positions[:, :, 1] += floor_offset
    if not np.isfinite(local).all() or not np.isfinite(root).all():
        raise ValueError("Non-finite motion output")
    quats = (
        Rotation.from_matrix(local.reshape(-1, 3, 3))
        .as_quat()
        .reshape(len(root), len(names), 4)
    )
    angle = np.unwrap(np.arctan2(desired[:, 0, 2, 1], desired[:, 0, 1, 1]))
    diagnostics = {
        "root_travel_m": float(np.linalg.norm(root[-1, [0, 2]] - root[0, [0, 2]])),
        "scale": float(scale),
        "floor_offset_m": float(floor_offset),
        "root_height_range_m": [float(root[:, 1].min()), float(root[:, 1].max())],
        "hip_rotation_degrees": float(np.degrees(angle[-1] - angle[0])),
        "foot_clearance_max_m": float(
            (positions[:, feet, 1].min(axis=1) - target_floor).max()
        ),
    }
    motion = {
        "frames": len(root),
        "fps": 30,
        "names": names,
        "rotations": quats.tolist(),
        "root_positions": root.tolist(),
        "rest_root": rest[0].tolist(),
        "canonical_to_gltf": canonical_to_gltf,
        "loop": False,
        "positions": positions.tolist(),
    }
    return motion, diagnostics
