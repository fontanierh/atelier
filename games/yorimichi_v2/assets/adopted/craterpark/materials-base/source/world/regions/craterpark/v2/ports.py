"""Exact visible end walls around openings in elevated riding rooms."""
import numpy as np

from . import dsl, solids


def _clip(loop, axis, centre, bound, greater):
    distance = (loop - centre) @ axis - bound
    inside = distance >= -1e-10 if greater else distance <= 1e-10
    out = []
    for i in range(len(loop)):
        j = (i + 1) % len(loop)
        if inside[i]:
            out.append(loop[i])
        if inside[i] != inside[j]:
            fraction = distance[i] / (distance[i] - distance[j])
            p = loop[i] + fraction * (loop[j] - loop[i])
            p += (bound - (p - centre) @ axis) * axis
            out.append(p)
    if not out:
        return np.zeros((0, 3))
    out = np.asarray(out)
    keep = np.r_[True, np.linalg.norm(np.diff(out, axis=0), axis=1) > 1e-9]
    out = out[keep]
    if len(out) > 1 and np.linalg.norm(out[0] - out[-1]) < 1e-9:
        out = out[:-1]
    return out


def cap(loop, *, axis, centre, outward, openings, feature):
    """@cc [owner:fontanierh,label:correctness] exact-end-openings
    Each opening MUST be cut along its actual lateral bounds, never by triangle
    centroids. Only its closing faces MAY be BASE. All remaining end wall MUST
    be visible SIDE. Both upper and underside rows MUST already sample each cut.
    """
    loop = np.asarray(loop, 'f8')
    axis = np.asarray(axis, 'f8')
    centre = np.asarray(centre, 'f8')
    w = (loop - centre) @ axis
    spans = sorted((float(a), float(b)) for a, b in openings)
    if any(not np.isfinite([a, b]).all() or not w.min() <= a < b <= w.max() for a, b in spans):
        raise ValueError('opening bounds must lie inside the end section')
    if any(a[1] > b[0] for a, b in zip(spans[:-1], spans[1:])):
        raise ValueError('end openings cannot overlap')
    cuts = np.unique([w.min(), w.max(), *[v for pair in spans for v in pair]])
    for cut in cuts[1:-1]:
        at = loop[np.abs(w - cut) < 1e-7]
        if len(at) < 2 or np.ptp(at[:, 1]) < .3:
            raise ValueError(f'end opening at {cut:g} needs matching upper and underside samples')
    parts = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        if b - a < 1e-8:
            continue
        polygon = _clip(_clip(loop, axis, centre, a, True), axis, centre, b, False)
        if len(polygon) < 3:
            continue
        hidden = any(x <= (a + b) / 2 <= y for x, y in spans)
        parts.append(solids.polygon(polygon, outward=outward, feature=feature,
                                    role=dsl.BASE if hidden else dsl.SIDE))
    return parts
