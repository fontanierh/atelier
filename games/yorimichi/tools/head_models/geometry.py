"""Exact cyclic-triangle verification with bounded temporary arrays for dense meshes."""
import numpy as np


def canonical_triangles(triangles):
    """@cc [owner:fontanierh,label:correctness] dense-native-triangle-proof
    Canonicalization MUST preserve float32 positions, winding and duplicate triangle
    counts. Only cyclic vertex rotations and signed-zero normalization MAY compare equal.
    Nonfinite coordinates MUST reject. Temporary rotation arrays MUST be chunk bounded.
    """
    triangles = np.asarray(triangles, dtype='<f4')
    if triangles.ndim != 3 or triangles.shape[1:] != (3, 3):
        raise ValueError('Expected triangle positions shaped N×3×3')
    result = np.empty(len(triangles), dtype='V36')
    for first in range(0, len(triangles), 65536):
        chunk = triangles[first:first+65536].copy()
        if not np.isfinite(chunk).all():
            raise ValueError('Nonfinite native triangle')
        chunk[chunk == 0] = 0
        rotations = np.stack([np.roll(chunk, k, axis=1) for k in range(3)], axis=1)
        records = rotations.reshape(len(chunk), 3, 9).view('V36').reshape(len(chunk), 3)
        best = np.argsort(records, axis=1)[:, 0]
        result[first:first+len(chunk)] = records[np.arange(len(chunk)), best]
    result.sort()
    return result


def same_triangles(before, after):
    if len(before) != len(after):
        return False
    return np.array_equal(canonical_triangles(before), canonical_triangles(after))
