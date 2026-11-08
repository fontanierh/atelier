"""Integral turn aprons and explicit port seams, in native y-up metres.

A turn is built once between two approach cut planes. Its quarter pipe owns the
transition; its floor polygon stops exactly at that transition's foot row. No
coplanar rectangle or hidden wall is placed under the floor.
"""
import math

import numpy as np

from . import bowls, dsl, primitives as P, solids
from .curves import Curve, GAUSS_W, GAUSS_X, Line


def direction(degrees):
    a = math.radians(degrees)
    return np.array([math.cos(a), math.sin(a)])


def boundary_row(mesh, point, tangent, *, tolerance=1e-6, level=True, span=None):
    """Read one actual open section, including curved shoulders and caps."""
    m = mesh.where(role=dsl.RIDING)
    V, F = m.welded(1e-7)
    edges = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    edges, count = np.unique(np.sort(edges, axis=1), axis=0, return_counts=True)
    edges = edges[count == 1]
    distance = (V[:, [0, 2]] - point) @ tangent
    edges = edges[(np.abs(distance[edges]) <= tolerance).all(1)]
    if span is not None:
        if not math.isfinite(span) or span <= 0:
            raise ValueError('junction: port span must be finite and positive')
        n = np.array([-tangent[1],tangent[0]])
        lateral = (V[:, [0,2]] - point) @ n
        edges = edges[(np.abs(lateral[edges]) <= span / 2. + tolerance).all(1)]
    if not len(edges):
        raise ValueError('junction: no open section on the specified cut plane')
    degree = np.bincount(edges.ravel(), minlength=len(V))
    ids = np.unique(edges)
    if (degree[ids] > 2).any() or np.count_nonzero(degree[ids] == 1) != 2:
        raise ValueError('junction: the port must be one unbranched open chain')
    if level and np.ptp(V[ids, 1]) > tolerance:
        raise ValueError('junction: approach shoulders must fade to a level port')
    n = np.array([-tangent[1], tangent[0]])
    ends = ids[degree[ids] == 1]
    here = int(ends[np.argmin(V[ends][:, [0, 2]] @ n)])
    adjacent = {int(i): [] for i in ids}
    for a, b in edges:
        adjacent[int(a)].append(int(b))
        adjacent[int(b)].append(int(a))
    chain, previous = [], -1
    while True:
        chain.append(here)
        nxt = [i for i in adjacent[here] if i != previous]
        if not nxt:
            break
        previous, here = here, nxt[0]
    if len(chain) != len(ids):
        raise ValueError('junction: disconnected port section')
    return V[chain]


def _hull_with_samples(rows):
    """Keep every supplied boundary sample; only free perimeter edges subdivide."""
    samples = np.concatenate(rows)
    _, ids = np.unique(np.round(samples / 1e-8).astype('i8'), axis=0, return_index=True)
    samples = samples[np.sort(ids)]
    hull = bowls.convex_hull(samples[:, [0, 2]])
    out = []
    for a, b in zip(hull, np.roll(hull, -1, axis=0), strict=True):
        delta = b - a
        u = (samples[:, [0, 2]] - a) @ delta / (delta @ delta)
        distance = np.linalg.norm(samples[:, [0, 2]] - (a + u[:, None] * delta), axis=1)
        ids = np.flatnonzero((distance < 1e-7) & (u >= -1e-9) & (u <= 1 + 1e-9))
        edge = samples[ids[np.argsort(u[ids])]]
        # A port or QP foot is an exact shared chain. New samples are allowed
        # only on the connecting, unowned perimeter edges.
        for p, q in zip(edge[:-1], edge[1:], strict=True):
            owned = False
            for row in rows:
                v = row[-1] - row[0]
                uv = (np.array([p, q]) - row[0]) @ v / (v @ v)
                d = np.linalg.norm(np.array([p, q]) - (row[0] + uv[:, None] * v), axis=1)
                if (d < 1e-7).all() and (uv >= -1e-9).all() and (uv <= 1 + 1e-9).all():
                    owned = True
                    break
            n = 1 if owned else max(1, math.ceil(np.linalg.norm(q - p) / 2.5))
            out.append(p + np.arange(n)[:, None] / n * (q - p))
    loop = np.concatenate(out)
    for row in rows:
        for p in row:
            if np.linalg.norm(loop - p, axis=1).min() > 1e-7:
                raise ValueError('junction: a supplied port is not on the floor perimeter')
    return loop


def elbow(spec, *, ground=None, on_ground=True, rows=None):
    """@cc [owner:fontanierh,label:correctness] integral-elbow-floor
    The floor MUST meet both exact approach rows and the QP foot row once.
    All riding geometry MUST stay between the approach cut planes. A sloping
    or nonlevel port MUST fail rather than be silently covered by an apron.
    """
    if abs(spec['grade_t']) > 1e-8:
        raise ValueError('junction: level the complete elbow approach before its port')
    A, B = direction(spec['heading_in']), direction(spec['heading_out'])
    W, E = np.asarray(spec['corner']), np.asarray(spec['exit_corner'])
    n, t = np.asarray(spec['n']), np.asarray(spec['t'])
    y, radius = float(spec['y']), float(spec['r'])
    pin = W - A * (spec['s'] - spec['s_in'])
    pout = E + B * (spec['s_out'] - spec['s'] - spec['drift'])
    if rows is None:
        rows = [bowls.port_row(pin, A, y, spec['width']), bowls.port_row(pout, B, y, spec['width'])]
    for row in rows:
        if np.abs(np.asarray(row)[:, 1] - y).max() > 1e-6:
            raise ValueError('junction: mismatched approach heights')
    # A wall extends behind its foot, away from both ports. Trim its along-wall
    # range at those ports before building; a long rectangle would overlap arms.
    centre = np.asarray(spec['centre'])
    lo, hi = -float(spec['half_length']), float(spec['half_length'])
    for p, a in ((pin, A), (pout, -B)):
        c, k = float((centre - p) @ a), float(t @ a)
        if abs(k) < 1e-10:
            if c < -1e-8:
                raise ValueError('junction: wall lies outside an approach cut')
        elif k > 0:
            lo = max(lo, -c / k)
        else:
            hi = min(hi, -c / k)
    if hi - lo < spec.get('lip_min', 12.):
        raise ValueError('junction: too little wall remains between the approaches')
    lip = centre - n * radius
    name = f"{spec['line']}.elbow{spec['index']}"
    wall = P.quarter_pipe(Line(lip + t * lo, lip + t * hi), floor_y=y,
                          height=radius + spec['vert'], radius=radius, deck=spec['deck'], floor=0.,
                          ground=ground if on_ground else y, feature=name, front='ground', on_ground=True)
    # The first column is the exact floor seam, not an extra strip of floor.
    foot = wall.mesh.V[wall.mesh.seams[name + '.left']]
    loop = _hull_with_samples([np.asarray(r) for r in rows] + [foot])
    apron = solids.polygon(loop, outward=[0., 1., 0.], feature=name + '.apron', role=dsl.RIDING)
    mesh = dsl.Mesh.concat([wall.mesh, apron])
    feet = solids.check_open(mesh, name=name)
    if len(feet) != 1:
        raise ValueError(f'{name}: turn must have one continuous outer boundary')
    # The external wall end caps may stand outside the cut planes at height;
    # all RIDING faces, including the rear deck, must be inside both cuts.
    riding = mesh.where(role=dsl.RIDING).V
    for p, a in ((pin, A), (pout, -B)):
        if ((riding[:, [0, 2]] - p) @ a).min() < -1e-6:
            raise ValueError(f'{name}: transition overlaps an approach')
    checks = wall.checks + [{'kind': 'junction', 'feature': name, 'ports': [r.tolist() for r in rows],
                              'wall_height_m': radius + spec['vert'], 'wall_length_m': hi - lo,
                              'floor_area_m2': float(apron.areas().sum())}]
    if not on_ground:
        loop = feet[0]
        base = loop.copy()
        base[:, 1] = float(y) - 1.5
        skirts = []
        for i in range(len(loop)):
            j = (i + 1) % len(loop)
            edge = loop[[i, j]]
            port = False
            for p,a,row in ((pin,A,rows[0]),(pout,B,rows[1])):
                n = np.array([-a[1],a[0]])
                bounds = (np.asarray(row)[:,[0,2]]-p) @ n
                lateral = (edge[:,[0,2]]-p) @ n
                port |= (np.abs((edge[:,[0,2]]-p) @ a).max() < 1e-7
                         and lateral.min() >= bounds.min()-1e-7
                         and lateral.max() <= bounds.max()+1e-7)
            d = loop[j] - loop[i]
            skirts.append(solids.grid(np.array([[loop[i], base[i]], [loop[j], base[j]]]),
                                       outward=[d[2], 0., -d[0]], feature=name,
                                       role=dsl.BASE if port else dsl.SIDE))
        cap = solids.polygon(base, outward=[0., -1., 0.], feature=name, role=dsl.SIDE)
        mesh = dsl.Mesh.concat([mesh, *skirts, cap])
        solids.check_closed(mesh, name=name)
        feet = []
    return P.Built(mesh, wall.rails, checks, feet)


class MergeCurve(Curve):
    """A C2 lateral approach: 80 m long, 11 m shift, zero yaw and curvature at both ports.

    The arc-length table and Newton inversion evaluate actual distance along the
    curve, rather than assuming that the plan x coordinate is that distance.
    """
    def __init__(self, origin, heading, sign, length=80., wide=21., narrow=10.):
        self.origin, self.forward = np.asarray(origin, 'f8'), direction(heading)
        self.left = np.array([-self.forward[1], self.forward[0]])
        self.sign, self.run, self.wide, self.narrow = float(sign), float(length), float(wide), float(narrow)
        self.us = np.linspace(0., 1., 129)
        self.ss = np.r_[0., np.cumsum(self._integral(self.us[:-1], self.us[1:]))]
        self.length = float(self.ss[-1])

    def _eval(self, u, order=0):
        u = np.atleast_1d(np.asarray(u, 'f8'))
        delta = self.sign * (self.narrow - self.wide)
        if order == 0:
            q = u ** 3 * (10. + u * (-15. + 6. * u))
            return ((u - 1)[:, None] * self.run * self.forward +
                    (self.sign * self.wide + delta * q)[:, None] * self.left + self.origin)
        if order == 1:
            q = 30. * u ** 2 * (1 - u) ** 2
            return self.run * self.forward + (delta * q)[:, None] * self.left
        q = 60. * u * (1 - u) * (1 - 2 * u)
        return (delta * q)[:, None] * self.left

    def _integral(self, a, b):
        u = (a + b)[:, None] / 2 + (b - a)[:, None] / 2 * GAUSS_X
        speed = np.linalg.norm(self._eval(u.ravel(), 1), axis=1).reshape(u.shape)
        return (speed * GAUSS_W).sum(1) * (b - a) / 2

    def _u(self, t):
        t = np.clip(np.atleast_1d(np.asarray(t, 'f8')), 0., self.length)
        u = np.interp(t, self.ss, self.us)
        for _ in range(3):
            i = np.clip(np.searchsorted(self.us, u, side='right') - 1, 0, len(self.us) - 2)
            error = self.ss[i] + self._integral(self.us[i], u) - t
            u -= error / np.linalg.norm(self._eval(u, 1), axis=1)
        return np.clip(u, 0., 1.)

    def point(self, t):
        return self._eval(self._u(t))

    def tangent(self, t):
        d = self._eval(self._u(t), 1)
        return d / np.linalg.norm(d, axis=1, keepdims=True)

    def curvature(self, t):
        u = self._u(t)
        a, b = self._eval(u, 1), self._eval(u, 2)
        return (a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]) / np.linalg.norm(a, axis=1) ** 3


def shared_merge(origin, heading, floor_y, *, length=35., approach=80., feature='S14', height=7., radius=6.):
    """@cc [owner:fontanierh,label:correctness] convergent-shared-surface
    Two 18 m floors MUST converge into one 38 m floor without intersecting
    shoulder walls. The shared body MUST be built once. Its exact inlet row
    MUST include both approaches' floor and cap samples; no buried divider.
    """
    if approach < 80.:
        raise ValueError('shared merge: the 11 m lateral shift requires at least 80 m approach')
    forward = direction(heading)
    left = np.array([-forward[1], forward[0]])
    arms, curves, lateral = [], [], []
    for sign in (-1, 1):
        path = MergeCurve(origin, heading, sign, approach)
        station = np.linspace(0., path.length, 4097)
        if np.abs(path.curvature(station)).max() > 1 / 80. + 1e-9:
            raise ValueError('shared merge: approach curvature is tighter than R80')
        curves.append(path)
        outer = P.Side('bowl', height=height, radius=radius, fade=(0., 0.))
        # The approach offset vanishes cubically. A fixed-radius wall's reach
        # is proportional to sqrt(height) near zero, so its height must fade
        # cubically in the cosine ease (distance^6) to avoid interpenetration.
        inner = P.Side('bowl', height=height, radius=radius, fade=(0., path.length), fade_power=3.)
        arm = P.ramp(path, P.from_additions(floor_y, 0., [('line', path.length)]), 18.,
                     left=outer if sign > 0 else inner, right=inner if sign > 0 else outer,
                     ground=floor_y, feature=feature + ('.upper' if sign > 0 else '.lower'), on_ground=True)
        arms.append(arm)
        row = boundary_row(arm.mesh, np.asarray(origin) + sign * 10. * left, forward, level=False)
        row = row[np.abs(row[:, 1] - floor_y) < 1e-7]
        lateral.extend((row[:, [0, 2]] - origin) @ left)
    across = np.asarray(sorted(set(round(float(v), 8) for v in lateral if abs(v) <= 19. + 1e-7)))
    across[[0, -1]] = [-19., 19.]
    body = P.ramp(Line(origin, np.asarray(origin) + length * forward),
                  P.from_additions(floor_y, 0., [('line', length)]), 38., across=across,
                  left=P.Side('bowl', height=height, radius=radius, fade=(0., 0.)),
                  right=P.Side('bowl', height=height, radius=radius, fade=(0., 0.)),
                  ground=floor_y, feature=feature + '.shared', on_ground=True)
    built = P.Built.concat(arms + [body])
    built.foot = solids.check_open(built.mesh, name=feature)
    if len(built.foot) != 1:
        raise ValueError('shared merge: the joined riding surface has an open internal seam')
    built.checks.append({'kind': 'shared_merge', 'feature': feature, 'owners': ['L1', 'L4'],
                         'floor_width_m': 38., 'inlet_width_m': 18., 'wall_height_m': height,
                         'wall_radius_m': radius, 'approach_m': approach, 'shared_m': length,
                         'min_approach_radius_m': float(1 / max(np.abs(p.curvature(np.linspace(0, p.length, 4097))).max() for p in curves))})
    return built
