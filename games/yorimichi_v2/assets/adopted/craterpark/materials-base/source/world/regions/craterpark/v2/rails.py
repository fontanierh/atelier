"""Grind rails (plan/pipeline.md 5.7): emitted from features, never detected. A rail is a dsl.Rail of points every
0.5 m along its grind edge (corners kept). Also the round grind rail as a solid: a tube on posts.

Posts stand on the support surface: their bottoms are base faces over a footprint the network cuts (review point 1),
and their tops end inside the rail tube (a render-only exception, a few square centimetres per post).
"""
import itertools

import numpy as np

from . import dsl, solids

STEP = .5           # metres between rail points
RAIL_RADIUS = .03   # metres (6 cm round bar)
POST_RADIUS = .022  # metres: inside the tube, so a post's top ends within the rail
POST_SPACING = 3.   # metres between posts at most
POST_SIDES = 8


def resample(points, step=STEP, closed=False):
    """The polyline's points every `step` metres or less along each segment, its corners and ends kept exactly. A
    closed line's first point is not repeated at its end."""
    P = np.asarray(points, 'f8')
    if closed and np.linalg.norm(P[0] - P[-1]) > 1e-9:
        P = np.concatenate([P, P[:1]])
    # keep corners: points where the direction turns by more than 1 degree, plus the ends
    d = np.diff(P, axis=0); L = np.linalg.norm(d, axis=1)
    P, d, L = np.concatenate([P[:1], P[1:][L > 1e-9]]), d[L > 1e-9], L[L > 1e-9]
    u = d / L[:, None]
    turn = np.r_[True, (u[1:] * u[:-1]).sum(1) < np.cos(np.radians(1.)), True]
    s = np.concatenate([[0.], np.cumsum(L)])
    keys = s[turn]
    out = []
    for a, b in itertools.pairwise(keys):
        n = max(1, int(np.ceil((b - a) / step - 1e-9)))
        out.append(np.linspace(a, b, n + 1)[:-1])
    t = np.concatenate(out + [[s[-1]]])
    Q = np.stack([np.interp(t, s, P[:, k]) for k in range(3)], 1)
    return Q[:-1] if closed else Q


def edge_rail(points, closed=False, feature=''):
    """A dsl.Rail along a grind edge (a ledge's top arris, a wall's cap edge)."""
    return dsl.Rail(resample(points, closed=closed), closed, feature)


def round_rail(axis, *, ground, feature='rail', radius=RAIL_RADIUS, post_radius=POST_RADIUS,
               spacing=POST_SPACING, sides=12):
    """A round grind rail along `axis` (k, 3) (its centreline; flat, down or kinked) on posts down to `ground` (float
    or f(x, z)): (mesh, rail). The rail's grind line is the tube's top."""
    P = np.asarray(axis, 'f8')
    g = ground if callable(ground) else (lambda x, z: np.full(np.shape(x), float(ground)))
    parts = [solids.tube(P, radius, feature=feature, sides=sides, role=dsl.RAIL, material=dsl.STEEL)]
    s = np.concatenate([[0.], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
    n = max(1, int(np.ceil((s[-1] - 2 * post_radius) / spacing)))
    at = np.linspace(post_radius * 2, s[-1] - post_radius * 2, n + 1)
    ang = 2 * np.pi * (np.arange(POST_SIDES) + .5) / POST_SIDES
    for t in at:
        c = np.array([np.interp(t, s, P[:, k]) for k in range(3)])
        loop = np.stack([c[0] + post_radius * np.cos(ang), c[2] + post_radius * np.sin(ang)], 1)
        y0 = float(g(np.array([c[0]]), np.array([c[2]]))[0])
        parts.append(solids.prism(loop, y0, c[1], feature=feature, material=dsl.STEEL, top_role=dsl.RAIL,
                                  side_role=dsl.RAIL))
    mesh = dsl.Mesh.concat(parts)
    mesh.features = (feature,)
    mesh.feature[:] = 0
    return mesh, dsl.Rail(resample(P + [0., radius, 0.]), False, feature)
