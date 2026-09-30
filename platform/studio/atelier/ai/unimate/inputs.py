"""Explicit, character-independent inputs to the released f60 model."""
from dataclasses import dataclass
import numpy as np


def validate_rig(rig, canonical_to_gltf):
    names, parents = rig['names'], rig['parents']
    n = len(names)
    if n < 2 or len(set(names)) != n or not all(isinstance(name, str) and name for name in names):
        raise ValueError('Rig needs at least two uniquely named joints')
    if len(parents) != n or parents[0] != -1 or any(
        type(p) is not int or not 0 <= p < j for j, p in enumerate(parents[1:], 1)
    ):
        raise ValueError('Rig must be a connected tree with root first and parents before children')
    points = np.asarray(rig['positions'], dtype=np.float32)
    if points.shape != (n, 3) or not np.isfinite(points).all():
        raise ValueError('Rig positions must be finite canonical world points, one per joint')
    if not any(np.linalg.norm(points[j] - points[p]) > 0 for j, p in enumerate(parents[1:], 1)):
        raise ValueError('Rig has no nonzero bone lengths')
    vocabulary = rig['clean_names']
    if len(vocabulary) != n or not all(isinstance(name, str) and name.strip() for name in vocabulary):
        raise ValueError('Supply one anatomical training label per joint')
    axis = np.asarray(canonical_to_gltf, dtype=np.float64)
    if axis.shape != (4,) or not np.isfinite(axis).all() or not np.isclose(np.linalg.norm(axis), 1):
        raise ValueError('canonical_to_gltf must be a unit xyzw quaternion')
    # Caller data is retained for provenance, without modifying its vocabulary.
    return dict(rig)


@dataclass(frozen=True)
class MotionConstraint:
    """Unnormalized (60, joints, 12) features and a per-joint lock mask.

    The caller authors reference conversion and any final blending/loop policy.
    """
    features: object
    locked_joints: object
    start_time: float = .55

    def normalized(self, mean, std):
        features = np.asarray(self.features, dtype=np.float32)
        mask = np.asarray(self.locked_joints)
        if features.shape != (60, len(mean), 12) or not np.isfinite(features).all():
            raise ValueError('Constraint features must be finite with shape (60, joints, 12)')
        if mask.shape != (len(mean),) or mask.dtype != np.bool_:
            raise ValueError('Constraint lock mask must contain one boolean per joint')
        if not 0 <= self.start_time < 1:
            raise ValueError('Constraint start_time must be in [0, 1)')
        return (features - mean) / std, mask
